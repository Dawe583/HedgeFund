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


def load_frame(research_db: str, symbol: str, timeframe: str) -> pd.DataFrame:
    """The full feature frame for one symbol-timeframe — loaded once per
    worker, then sliced per phase. Windows lose warm-up history by slicing:
    the first lookback-worth of in-sample bars can never signal, which is
    the honest price of the split — recorded in every row's data_start."""
    from trading.features import build_features
    from trading.models import make_engine, make_session_factory
    from trading.research import load_candles_df

    engine = make_engine(research_db)
    sf = make_session_factory(engine)
    with sf() as session:
        raw = load_candles_df(session, symbol.upper(), timeframe)
    engine.dispose()
    if raw.empty:
        raise SystemExit(f"no candles for {symbol} {timeframe} in {research_db} — run ingest first")
    return build_features(raw)


def evaluate_cell(payload: dict) -> dict:
    """Worker: one candidate on one symbol in one phase. Owns its ledger
    connection because sqlite connections do not cross processes. The
    candidate arrives as plain data — lambdas and closures do not pickle —
    and is reconstructed here from the registry."""
    from trading.backtest.engine import BTConfig
    from trading.bots.trend_bot import TrendMomentum
    from trading.search import Candidate, evaluate_candidate, in_sample, open_ledger, out_of_sample, rails_off_config

    makers = {"trendmom": lambda p: TrendMomentum(**p)}
    make = makers.get(payload["bot_key"])
    if make is None:
        raise SystemExit(f"no maker registered for bot_key {payload['bot_key']!r}")
    candidate = Candidate(
        family=payload["family"],
        name=payload["candidate"],
        bot_key=payload["bot_key"],
        params=payload["params"],
        make=make,
        symbols=[payload["symbol"]],
        timeframe=payload["timeframe"],
    )
    conn = open_ledger(payload["ledger_path"])
    try:
        df = load_frame(payload["research_db"], payload["symbol"], payload["timeframe"])
        window = in_sample(df) if payload["phase"] == "A" else out_of_sample(df)
        cfg = rails_off_config() if payload["phase"] == "A" else BTConfig()
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
    finally:
        conn.close()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="trading.sweep")
    p.add_argument("--family", required=True, help="candidate family key (F1)")
    p.add_argument("--phase", required=True, choices=["A", "B"])
    p.add_argument("--candidates", default=None, help="comma-separated candidate names — default the whole grid")
    p.add_argument("--symbols", default=None, help="override the candidates' symbol lists, comma-separated")
    p.add_argument("--jobs", type=int, default=4)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--db", default="sqlite:////Users/dawe/Developer/HedgeFund/backend/data/research.db")
    args = p.parse_args(argv)

    if args.family != "F1":
        raise SystemExit(f"unknown family {args.family!r}; declared families: F1")

    from trading.candidates import trend_momentum_candidates

    candidates = trend_momentum_candidates()
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

    cells = []
    for cand in candidates:
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
                    row = {"candidate": cell["candidate"].name, "symbol": cell["symbol"],
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
