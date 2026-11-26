"""Sweep runner — phase-A screening over a declared candidate grid.

    uv run python -m trading.sweep --family F1 --phase A --jobs 8

What this is: the evaluation half of program-2026-11-26.md. Candidates come
from trading/candidates.py — declared grids, never runtime improvisation.
Every evaluation lands in the search ledger inside the worker that ran it;
a sweep interrupted mid-way leaves honest partial evidence, and re-running
appends new rows rather than resuming — the ledger counts evaluations, not
intentions.

Parallelism is over (candidate, symbol) cells in a process pool: backtests
are CPU-bound and the kernel import is heavy, so each worker imports once
and evaluates its share serially. SQLite serializes the ledger writes; WAL
mode makes that cheap.
"""

from __future__ import annotations

import argparse
import json
import sys

import pandas as pd


def evaluate_cell(payload: dict) -> dict:
    """Worker: one candidate on one symbol in one phase. Owns its ledger
    connection because sqlite connections do not cross processes. The
    candidate arrives as plain data — lambdas and closures do not pickle —
    and is reconstructed here from the registry."""
    from trading.backtest.engine import BTConfig
    from trading.bots.trend_bot import TrendMomentum
    from trading.bots.breakout_bot import BreakoutVol
    from trading.bots.continuation_bot import Continuation1h
    from trading.bots.hft_bot import HFTMomentum
    from trading.bots.meanrev_bot import MeanRev
    from trading.bots.scalp_bot import ScalpTrend
    from trading.bots.meanrev_regime_bot import MeanRevRegime
    from trading.bots.funding_carry_bot import FundingCarry
    from trading.search import Candidate, evaluate_candidate, in_sample, load_frame, open_ledger, out_of_sample, rails_off_config

    makers = {
        "trendmom": lambda p: TrendMomentum(**p),
        "meanrevregime": lambda p: MeanRevRegime(**p),
    "fundingcarry": lambda p: FundingCarry(**p),
        "continuation1h": lambda p: Continuation1h(**p),
        "scalp": lambda p: ScalpTrend(**p),
        "hft": lambda p: HFTMomentum(**p),
        "breakout": lambda p: BreakoutVol(**p),
        "meanrev": lambda p: MeanRev(**p),
    }
    make = makers.get(payload["bot_key"])
    if make is None:
        raise SystemExit(f"no maker registered for bot_key {payload['bot_key']!r}")
    candidate = Candidate(
        family=payload["family"],
        name=payload["candidate"],
        bot_key=payload["bot_key"],
        params=payload["params"],
        make=make,
        symbols=list(payload.get("basket") or [payload["symbol"]]),
        timeframe=payload["timeframe"],
    )
    conn = open_ledger(payload["ledger_path"])
    try:
        cfg = rails_off_config() if payload["phase"] == "A" else BTConfig()
        try:
            if payload.get("basket"):
                from trading.basket import evaluate_basket

                row = evaluate_basket(
                    conn,
                    candidate,
                    symbols=payload["basket"],
                    phase=payload["phase"],
                    research_db=payload["research_db"],
                    seed=payload["seed"],
                    cfg=cfg,
                )
                return {k: row.get(k) for k in ("id", "candidate", "symbol", "verdict", "trades_n", "permutation_p", "sharpe", "elapsed_s")}
            df = load_frame(payload["research_db"], payload["symbol"], payload["timeframe"])
            window = in_sample(df) if payload["phase"] == "A" else out_of_sample(df)
            row = evaluate_candidate(
                conn,
                candidate,
                phase=payload["phase"],
                df=window,
                research_db=payload["research_db"],
                seed=payload["seed"],
                cfg=cfg,
                symbol=payload["symbol"],
            )
            return {k: row[k] for k in ("id", "candidate", "symbol", "verdict", "trades_n", "permutation_p", "sharpe", "elapsed_s")}
        except BaseException as exc:
            # SystemExit included — load_frame uses it for missing data, and
            # a missing-data evaluation is an evaluation that failed: the
            # count of everything tried is the ledger's whole point, and an
            # error that lands nowhere is exactly the invisible selection
            # the program forbids. KeyboardInterrupt passes through below.
            if isinstance(exc, KeyboardInterrupt):
                raise
            # a crashed evaluation is still an evaluation — the count of
            # everything tried is the ledger's whole point, and an error
            # that lands nowhere is exactly the invisible selection the
            # program forbids. The row carries no statistics because none
            # honestly exist.
            import json as _json
            import time as _time

            import pandas as _pd

            from trading.search import ledger_append

            err_row = {
                "ts": _pd.Timestamp.now(tz="UTC").isoformat(),
                "family": candidate.family,
                "candidate": candidate.name,
                "symbol": "+".join(sorted(payload["basket"])) if payload.get("basket") else payload["symbol"],
                "timeframe": candidate.timeframe,
                "params_json": _json.dumps(candidate.params, sort_keys=True),
                "phase": payload["phase"],
                "verdict": "error",
                "seed": payload["seed"],
                "rails": "off" if payload["phase"] == "A" else "on",
                "reasons_json": _json.dumps([f"error: {type(exc).__name__}: {exc}"][:1]),
            }
            row_id = ledger_append(conn, err_row)
            return {"id": row_id, "candidate": candidate.name, "symbol": err_row["symbol"],
                    "verdict": "error", "error": str(exc)}
    finally:
        conn.close()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="trading.sweep")
    p.add_argument("--family", required=True, help="candidate family key (F1)")
    p.add_argument("--phase", required=True, choices=["A", "B"])
    p.add_argument("--candidates", default=None, help="comma-separated candidate names — default the whole grid")
    p.add_argument("--symbols", default=None, help="override the candidates' symbol lists, comma-separated")
    p.add_argument("--basket", default=None, help="comma-separated basket symbols — evaluates composites, not per-symbol cells")
    p.add_argument("--jobs", type=int, default=4)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--db", default="sqlite:////Users/dawe/Developer/HedgeFund/backend/data/research.db")
    args = p.parse_args(argv)

    from trading.candidates import GRIDS

    grid_fn = GRIDS.get(args.family)
    if grid_fn is None:
        raise SystemExit(f"unknown family {args.family!r}; declared families: {sorted(GRIDS)}")

    candidates = grid_fn()
    if args.candidates:
        wanted = set(args.candidates.split(","))
        candidates = [c for c in candidates if c.name in wanted]
        missing = wanted - {c.name for c in candidates}
        if missing:
            raise SystemExit(f"unknown candidates: {sorted(missing)}")
    if args.symbols:
        override = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        for c in candidates:
            c.symbols = override
    if not candidates:
        raise SystemExit("no candidates selected")

    # the ledger lives in the research db file — same file the candles are
    # read from, deliberate: the search's diary is a research artifact, and
    # one file means one backup carries both
    ledger_path = args.db.split("///")[-1] if "///" in args.db else args.db.removeprefix("sqlite:///")

    basket_syms = None
    if args.basket:
        basket_syms = sorted(s.strip().upper() for s in args.basket.split(",") if s.strip())
        if len(basket_syms) < 2:
            raise SystemExit("a basket of one symbol is a per-symbol evaluation — drop --basket")

    cells = []
    for cand in candidates:
        if basket_syms:
            cells.append({
                "family": cand.family,
                "candidate": cand.name,
                "bot_key": cand.bot_key,
                "params": cand.params,
                "basket": basket_syms,
                "timeframe": cand.timeframe,
                "phase": args.phase,
                "seed": args.seed,
                "research_db": args.db,
                "ledger_path": ledger_path,
            })
            continue
        for symbol in cand.symbols:
            cells.append({
                "family": cand.family,
                "candidate": cand.name,
                "bot_key": cand.bot_key,
                "params": cand.params,
                "symbol": symbol,
                "timeframe": cand.timeframe,
                "phase": args.phase,
                "seed": args.seed,
                "research_db": args.db,
                "ledger_path": ledger_path,
            })

    print(json.dumps({"event": "sweep_start", "cells": len(cells), "candidates": len(candidates),
                      "phase": args.phase, "jobs": args.jobs}), flush=True)

    results = []
    if args.jobs <= 1:
        for cell in cells:
            results.append(evaluate_cell(cell))
            print(json.dumps({"event": "cell", **results[-1]}), flush=True)
    else:
        from concurrent.futures import ProcessPoolExecutor, as_completed

        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            futures = {pool.submit(evaluate_cell, cell): cell for cell in cells}
            for fut in as_completed(futures):
                try:
                    row = fut.result()
                except Exception as exc:
                    cell = futures[fut]
                    row = {"candidate": cell["candidate"],
                           "symbol": cell.get("symbol") or "+".join(cell.get("basket") or []),
                           "verdict": "error", "error": str(exc)}
                results.append(row)
                print(json.dumps({"event": "cell", **row}, default=str), flush=True)

    validated = sum(1 for r in results if r.get("verdict") == "validated")
    errors = sum(1 for r in results if r.get("verdict") == "error")
    print(json.dumps({"event": "sweep_done", "cells": len(results), "validated": validated,
                      "errors": errors, "phase": args.phase}), flush=True)
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
