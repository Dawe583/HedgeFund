"""Research CLI — one command takes a strategy from code to verdict.

    uv run python -m trading.research ingest  --symbol BTCUSDT --timeframe 4h --days 365
    uv run python -m trading.research validate --bot scalp --symbol BTCUSDT --timeframe 4h

Database layout (documented decision):
- Candles live in the research database (default backend/data/research.db),
  never in the owner's data.db: they are bulky, replaceable market data.
- Verdicts (backtest_runs / backtest_validations) are written to the
  application database the API reads (default backend/data.db in a real
  deployment), so the dashboard sees results without a second database.
  Every test and every verification run must point --app-db at a throwaway
  file instead.

The gate (design §7): a strategy is VALIDATED only when all of these hold —
  1. trade count >= min_trades (default 30, else the statistics mean nothing)
  2. Monte Carlo permutation p-value for Sharpe < 0.05
  3. bootstrap Sharpe 95% CI lower bound > 0
  4. walk-forward consistency: majority of windows profitable
Otherwise REJECTED, and the row says exactly which check failed. The seed is
recorded; re-running with the same data and seed reproduces the verdict.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import math
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from trading.backtest.engine import BTConfig, BarsPerYear
from trading.bots import BreakoutVol, HFTMomentum, MeanRev, ScalpTrend
from trading.config import get_settings
from trading.features import build_features
from trading.kernel import run_kernel_backtest
from trading.models import (
    BacktestRun,
    BacktestValidation,
    init_schema,
    make_engine,
    make_session_factory,
)
from trading.storage import load_candles_df, upsert_candles
from trading.validation import bootstrap_sharpe_ci, monte_carlo_test, walk_forward_analysis
from trading.validation.models import TradeRecord

log = logging.getLogger("trading.research")

_BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RESEARCH_DB = f"sqlite:///{_BACKEND_DIR / 'data' / 'research.db'}"
DEFAULT_APP_DB = f"sqlite:///{_BACKEND_DIR / 'data.db'}"
# Which execution engine produced the runs this module writes. The string is
# provenance, not configuration: it changes only when the execution layer
# does, and rows written under different execution semantics must never read
# as the same experiment. Format: kernel version + the harness execution model
# (docs/research/kernel-diff-2026-11-25.md).
ENGINE_VERSION = "nautilus-1.231.0+delayed-close"


DEFAULT_SEED = 42
MIN_TRADES = 30
PERMUTATION_P_MAX = 0.05
N_SIMULATIONS = 1000
N_BOOTSTRAP = 1000
N_WINDOWS = 5

# Static registry of the four ported strategies (design §7 migration path).
# `registered` is False everywhere: the lifecycle tables land in M3, and a
# row that claims registration without them would be a lie.
STRATEGIES: dict[str, dict] = {
    "scalp": {
        "key": "scalp",
        "cls": ScalpTrend,
        "name": "ScalpTrend",
        "timeframe": "4h",
        "symbols": ["BTCUSDT"],
        "description": (
            "Higher-timeframe trend strategy: enters deep pullbacks inside strong "
            "regimes, skips explosive volatility; rare trades held hours to weeks."
        ),
    },
    "hft": {
        "key": "hft",
        "cls": HFTMomentum,
        "name": "HFTMomentum",
        "timeframe": "1m",
        "symbols": ["BTCUSDT"],
        "description": (
            "One-minute momentum scalper: short-horizon continuation entries "
            "with order-flow gates in paper mode."
        ),
    },
    "breakout": {
        "key": "breakout",
        "cls": BreakoutVol,
        "name": "BreakoutVol",
        "timeframe": "5m",
        "symbols": ["BTCUSDT"],
        "description": "Volatility-breakout strategy on 5m bars; trades range expansions.",
    },
    "meanrev": {
        "key": "meanrev",
        "cls": MeanRev,
        "name": "MeanRev",
        "timeframe": "15m",
        "symbols": ["BTCUSDT"],
        "description": "Mean-reversion strategy on 15m bars; fades overextensions back to the mean.",
    },
}


# ------------------------------------------------------------------- ingest


async def _ingest(symbol: str, timeframe: str, days: int, db_url: str) -> tuple[int, str]:
    from trading.feeds.fallback import fetch_candles_any

    rows, venue = await fetch_candles_any(symbol=symbol, interval=timeframe, days=days)
    engine = make_engine(db_url)
    init_schema(engine)
    sf = make_session_factory(engine)
    with sf() as session:
        inserted = upsert_candles(session, symbol.upper(), timeframe, rows)
    engine.dispose()
    return (inserted, venue)


def cmd_predict(args: argparse.Namespace) -> int:
    """Forward-return prediction for one symbol: the F9 artifact scored on
    the latest feature row. Read-only, prints JSON — the honest contract is
    that a prediction carries its noise scale with it, so the output is
    never a bare number."""
    from trading.ml_forecast import artifact_for
    from trading.search import load_frame

    art = artifact_for(args.symbol.upper(), args.timeframe, args.db)
    df = load_frame(args.db, args.symbol.upper(), args.timeframe)
    row = df.iloc[-1]
    import math

    x = []
    missing = []
    for f in art["features"]:
        v = float(row[f]) if f in row else float("nan")
        if not math.isfinite(v):
            missing.append(f)
        x.append(v)
    if missing:
        print(json.dumps({"error": f"features not finite on the last bar: {missing}"}))
        return 1
    pred = float(art["model"].predict([x])[0])
    noise = float(art["noise"])
    print(
        json.dumps(
            {
                "symbol": args.symbol.upper(),
                "timeframe": args.timeframe,
                "bar_close_time": str(df.index[-1]),
                "horizon_bars": art["horizon"],
                "predicted_return": round(pred, 6),
                "noise_rmse": round(noise, 6),
                "z_score": round(pred / (noise + 1e-12), 3),
                "oof_corr": round(float(art.get("oof_corr", 0.0)), 4),
                "trained_through": art.get("trained_through"),
                "caveat": "out-of-fold corr measures historical skill; a prediction is a measurement, not advice",
            }
        )
    )
    return 0


def cmd_ingest_funding(args: argparse.Namespace) -> int:
    """Funding-rate history ingestion — the F2 family's data plane."""
    import asyncio as _asyncio

    from trading.feeds.binance_futures import funding_history_full
    from trading.models import init_schema
    from trading.storage import upsert_funding_rates

    rows = _asyncio.run(funding_history_full(args.symbol, args.days))
    engine = make_engine(args.db)
    init_schema(engine)
    sf = make_session_factory(engine)
    with sf() as session:
        inserted = upsert_funding_rates(session, args.symbol.upper(), rows)
    engine.dispose()
    print(json.dumps({"ingested": inserted, "venue": "binance", "kind": "funding",
                      "symbol": args.symbol.upper(), "days": args.days, "db": args.db}))
    return 0


def cmd_ingest_yahoo(args: argparse.Namespace) -> int:
    """Multi-asset ingestion through Yahoo Finance — stocks, indexes, metals."""
    from trading.feeds.yahoo import fetch_yahoo_candles

    rows = fetch_yahoo_candles(args.symbol, args.timeframe, args.days)
    engine = make_engine(args.db)
    init_schema(engine)
    sf = make_session_factory(engine)
    with sf() as session:
        inserted = upsert_candles(session, args.symbol.upper(), args.timeframe, rows)
    engine.dispose()
    print(json.dumps({"ingested": inserted, "venue": "yahoo", "symbol": args.symbol.upper(),
                      "timeframe": args.timeframe, "days": args.days, "db": args.db}))
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    inserted, venue = asyncio.run(_ingest(args.symbol, args.timeframe, args.days, args.db))
    print(
        json.dumps(
            {
                "ingested": inserted,
                "venue": venue,
                "symbol": args.symbol.upper(),
                "timeframe": args.timeframe,
                "days": args.days,
                "db": args.db,
            }
        )
    )
    return 0


# ----------------------------------------------------------------- validate


def trades_to_records(trades: list[dict], symbol: str) -> list[TradeRecord]:
    """Adapt the engine's trade dicts to the validation trio's TradeRecord shape.

    The trio consumes pnl ordering, timestamps, sizes and prices; leverage is
    1.0 because the ported engine's risk sizing is already in the quantities.
    """
    out = []
    for t in trades:
        notional = t["qty"] * t["entry_price"]
        pnl_pct = t["pnl"] / notional if notional else 0.0
        out.append(
            TradeRecord(
                symbol=symbol,
                direction=1 if t["side"] == "long" else -1,
                entry_price=float(t["entry_price"]),
                exit_price=float(t["exit_price"]),
                entry_time=pd.Timestamp(t["entry_time"]),
                exit_time=pd.Timestamp(t["exit_time"]),
                size=float(t["qty"]),
                leverage=1.0,
                pnl=float(t["pnl"]),
                pnl_pct=float(pnl_pct),
                exit_reason=str(t.get("reason", "")),
                holding_bars=float(t.get("bars_held", 0)),
                commission=float(t.get("fees", 0.0)),
                entry_margin=float(notional),
            )
        )
    return out


def load_funding_rates(research_db: str, symbol: str) -> pd.Series | None:
    """Settlement instants → signed rate for one symbol, or None when the
    funding table is absent/empty — absence must never crash a validation,
    funding economics is opt-in provenance (kernel accrual, 2026-11-26)."""
    try:
        engine = make_engine(research_db)
        try:
            with engine.connect() as conn:
                rows = pd.read_sql(
                    "SELECT funding_time, rate FROM funding_rates WHERE symbol = ? ORDER BY funding_time",
                    conn, params=(symbol.upper(),),
                )
        finally:
            engine.dispose()
    except Exception:
        return None
    if rows.empty:
        return None
    idx = pd.to_datetime(rows["funding_time"], utc=True)
    return pd.Series(rows["rate"].astype(float).values, index=idx, name="_funding_rate")


def validate_core(
    strategy,
    bot_key: str,
    symbol: str,
    timeframe: str,
    research_db: str,
    seed: int = DEFAULT_SEED,
    min_trades: int = MIN_TRADES,
    cfg: BTConfig | None = None,
    df: pd.DataFrame | None = None,
) -> dict:
    """Backtest + the three statistical checks, nothing written anywhere.

    The composable core the search machinery consumes: pass any constructed
    strategy instance (catalog default or a parameterized candidate), get the
    verdict payload back. `validate_strategy` is the persistence wrapper —
    one function owns statistics, one owns rows, and a swept candidate never
    inherits the catalog's write path by accident.

    `df` optionally supplies a pre-windowed feature frame: the search slices
    in-sample / out-of-sample windows once per symbol-timeframe instead of
    reloading candles per candidate. The caller then owns the window's
    honesty — the function trusts the frame it is given and reports its
    actual range.
    """
    if df is None:
        data_engine = make_engine(research_db)
        data_sf = make_session_factory(data_engine)
        with data_sf() as session:
            raw = load_candles_df(session, symbol.upper(), timeframe)
        data_engine.dispose()
        if raw.empty:
            raise SystemExit(
                f"no candles for {symbol} {timeframe} in {research_db} — run ingest first"
            )
        df = build_features(raw)
    elif len(df) == 0:
        raise SystemExit(f"empty frame passed for {symbol} {timeframe} — a window with no bars validates nothing")

    # funding join (F2 machinery, 2026-11-26): each settlement instant lands
    # on the bar whose open matches it; the kernel accrues rate x entry-
    # notional for positions open across it. Bars between settlements carry
    # NaN — the kernel treats NaN as no event. A symbol without funding
    # history accrues nothing, which is exactly honest for spot-truth candles.
    if "_funding_rate" not in df.columns:
        rates = load_funding_rates(research_db, symbol)
        if rates is not None and len(rates):
            col = pd.Series(float("nan"), index=df.index, dtype=float)
            bar_ns = df.index.asi8
            rate_ns = rates.index.asi8
            for j, ts in enumerate(rate_ns):
                hit = int((bar_ns == ts).nonzero()[0][0]) if (bar_ns == ts).any() else -1
                if hit >= 0:
                    col.iloc[hit] = float(rates.iloc[j])
            df = df.copy()
            df["_funding_rate"] = col

    bars_per_year = BarsPerYear.get(timeframe, 8_760)
    cfg = cfg or BTConfig()
    result = run_kernel_backtest(df, strategy, cfg, timeframe)

    records = trades_to_records(result.trades, symbol.upper())
    initial = float(cfg.initial_equity)
    gate = gate_stats(records, result.equity, initial, seed, bars_per_year, min_trades, len(result.trades))
    mc = gate["mc"]
    bs = gate["bs"]
    wf_pos = gate["wf_pos"]
    wf_total = gate["wf_total"]
    p_sharpe = gate["p_sharpe"]
    n_trades = gate["n_trades"]
    reasons = gate["reasons"]
    verdict = gate["verdict"]
    validation_payload = gate["validation_payload"]

    return {
        "verdict": verdict,
        "result": result,
        "metrics": result.metrics,
        "df": df,
        "mc": mc,
        "bs": bs,
        "wf_pos": wf_pos,
        "wf_total": wf_total,
        "p_sharpe": p_sharpe,
        "n_trades": n_trades,
        "reasons": reasons,
        "validation_payload": validation_payload,
    }


def gate_stats(records, equity, initial, seed, bars_per_year, min_trades, n_trades) -> dict:
    """The gate over arbitrary trade records and an equity series — the
    basket path composes its inputs across symbols and still answers to the
    same statistics. Nothing here knows where the records came from; that
    provenance belongs to the caller's ledger row."""
    np.random.seed(seed)  # any consumer of the global RNG reproduces
    mc = monte_carlo_test(
        records, initial, n_simulations=N_SIMULATIONS, seed=seed, bars_per_year=bars_per_year
    )
    bs = bootstrap_sharpe_ci(
        equity,
        bars_per_year=bars_per_year,
        n_bootstrap=N_BOOTSTRAP,
        seed=seed,
        initial_capital=initial,
    )
    wf = walk_forward_analysis(
        equity,
        records,
        n_windows=N_WINDOWS,
        bars_per_year=bars_per_year,
        initial_capital=initial,
    )

    reasons: list[str] = []
    if n_trades < min_trades:
        reasons.append(f"trades {n_trades} < minimum {min_trades}")
    p_sharpe = mc.get("p_value_sharpe")
    if "error" in mc:
        reasons.append(f"permutation test inconclusive: {mc['error']}")
    elif p_sharpe is not None and p_sharpe >= PERMUTATION_P_MAX:
        reasons.append(f"permutation p {p_sharpe} >= {PERMUTATION_P_MAX} (ordering indistinguishable from luck)")
    ci_lo = bs.get("ci_lower")
    if "error" in bs:
        reasons.append(f"bootstrap inconclusive: {bs['error']}")
    elif ci_lo is not None and ci_lo <= 0:
        reasons.append(f"bootstrap Sharpe CI lower {ci_lo} <= 0")
    wf_pos = wf.get("profitable_windows", 0)
    wf_total = wf.get("n_windows", 0)
    if "error" in wf:
        reasons.append(f"walk-forward inconclusive: {wf['error']}")
    elif wf_total and wf_pos <= wf_total / 2:
        reasons.append(f"walk-forward consistency {wf_pos}/{wf_total} windows profitable (majority required)")

    verdict = "validated" if not reasons else "rejected"
    validation_payload = {"monte_carlo": mc, "bootstrap": bs, "walk_forward": wf}
    return {
        "verdict": verdict,
        "mc": mc,
        "bs": bs,
        "wf_pos": wf_pos,
        "wf_total": wf_total,
        "p_sharpe": p_sharpe,
        "n_trades": n_trades,
        "reasons": reasons,
        "validation_payload": validation_payload,
    }


def validate_strategy(
    bot_key: str,
    symbol: str,
    timeframe: str,
    research_db: str,
    app_db: str,
    seed: int = DEFAULT_SEED,
    min_trades: int = MIN_TRADES,
    cfg: BTConfig | None = None,
    strategy=None,
) -> dict:
    """Run backtest + the three statistical checks, write both provenance rows.

    Returns the verdict payload; the same content lands in
    backtest_validations.validation_json, so the database row is the verdict.
    `strategy` overrides the catalog default instance — the search passes its
    candidates through here so every persisted row, swept or not, carries the
    parameters it actually ran in params_json.
    """
    spec = STRATEGIES.get(bot_key)
    if spec is None:
        raise SystemExit(f"unknown bot {bot_key!r}; choices: {sorted(STRATEGIES)}")

    strategy = strategy or spec["cls"]()
    core = validate_core(
        strategy, bot_key, symbol, timeframe, research_db,
        seed=seed, min_trades=min_trades, cfg=cfg,
    )
    result = core["result"]
    df = core["df"]
    mc = core["mc"]
    bs = core["bs"]
    wf_pos = core["wf_pos"]
    wf_total = core["wf_total"]
    p_sharpe = core["p_sharpe"]
    n_trades = core["n_trades"]
    reasons = core["reasons"]
    verdict = core["verdict"]
    validation_payload = core["validation_payload"]

    metrics = result.metrics
    # params = the instance's constructor knobs, not a scalp-shaped hardcoded
    # list: every bot stores its constructor kwargs as same-named scalar
    # attributes, so the provenance row carries exactly what the instance ran
    # — swept or default. Mutable runtime state never is a scalar set at
    # construction; what is not a number or a string does not belong in the row.
    params = {
        k: v
        for k, v in sorted(vars(strategy).items())
        if not k.startswith("_") and isinstance(v, (int, float, str, bool))
    }
    data_start = str(df.index[0])
    data_end = str(df.index[-1])

    app_engine = make_engine(app_db)
    init_schema(app_engine)
    app_sf = make_session_factory(app_engine)
    with app_sf() as session:
        # Evidence payloads the detail endpoint draws: the equity path,
        # downsampled to at most ~2000 points so the JSON stays small enough
        # to serve per run, and the full trade list with entry/exit times
        # and prices — the rows the fill-model audit reads.
        def _iso(value) -> str:
            # Candle timestamps load timezone-naive but are UTC by ingestion
            # contract — say so in the wire format instead of implying local time.
            ts = pd.Timestamp(value)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            return ts.isoformat()

        equity = result.equity
        max_points = 2000
        step = max(1, math.ceil(len(equity) / max_points))
        curve = [
            {"t": _iso(ts), "equity": round(float(equity.iloc[j]), 4)}
            for j, ts in enumerate(equity.index)
            if j % step == 0 or j == len(equity) - 1
        ]
        trades_payload = [
            {
                "entry_time": _iso(t["entry_time"]),
                "exit_time": _iso(t["exit_time"]),
                "side": t["side"],
                "qty": float(t["qty"]),
                "entry_price": float(t["entry_price"]),
                "exit_price": float(t["exit_price"]),
                "pnl": float(t["pnl"]),
            }
            for t in result.trades
        ]
        run = BacktestRun(
            bot=bot_key,
            symbol=symbol.upper(),
            timeframe=timeframe,
            strategy=spec["name"],
            params_json=json.dumps(params),
            trades_n=int(metrics.get("trades_n", 0)),
            win_rate=float(metrics.get("win_rate", 0.0)),
            profit_factor=float(metrics.get("profit_factor", 0.0) or 0.0),
            sharpe=float(metrics.get("sharpe", 0.0)),
            max_dd_pct=float(metrics.get("max_dd_pct", 0.0)),
            total_return_pct=float(metrics.get("total_return_pct", 0.0)),
            equity_curve_json=json.dumps(curve),
            trades_json=json.dumps(trades_payload),
            engine_version=ENGINE_VERSION,
        )
        session.add(run)
        session.flush()
        row = BacktestValidation(
            bot=bot_key,
            symbol=symbol.upper(),
            timeframe=timeframe,
            strategy=spec["name"],
            params_json=json.dumps(params),
            seed=seed,
            data_source="binance",
            data_rows=len(df),
            data_start=data_start,
            data_end=data_end,
            trades_n=n_trades,
            min_trades_required=min_trades,
            permutation_p=p_sharpe,
            sharpe_actual=mc.get("actual_sharpe"),
            sharpe_ci_lo=bs.get("ci_lower"),
            sharpe_ci_hi=bs.get("ci_upper"),
            prob_positive=bs.get("prob_positive"),
            wf_positive_folds=int(wf_pos),
            wf_total_folds=int(wf_total),
            verdict=verdict,
            reasons_json=json.dumps(reasons),
            validation_json=json.dumps(validation_payload, default=str),
            run_id=run.id,
            engine_version=ENGINE_VERSION,
        )
        session.add(row)
        session.commit()
        validation_id = row.id
        run_id = run.id
    app_engine.dispose()

    return {
        "verdict": verdict,
        "bot": bot_key,
        "strategy": spec["name"],
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "seed": seed,
        "trades": n_trades,
        "min_trades_required": min_trades,
        "metrics": metrics,
        "permutation_p": p_sharpe,
        "sharpe_actual": mc.get("actual_sharpe"),
        "sharpe_ci": [bs.get("ci_lower"), bs.get("ci_upper")],
        "prob_positive": bs.get("prob_positive"),
        "walk_forward": {"profitable_windows": wf_pos, "n_windows": wf_total},
        "reasons": reasons,
        "data": {"rows": len(df), "start": data_start, "end": data_end},
        "run_id": run_id,
        "validation_id": validation_id,
    }


# ---------------------------------------------------------------- register


def cmd_register(args: argparse.Namespace) -> int:
    """Register a strategy version into the lifecycle and walk it as far as
    the evidence allows. This is how the roster ever becomes non-empty:
    validate produces the verdict row, register turns the row into lifecycle.

    Params default to the validation row's own — what was validated is what
    gets registered, never a nearby variant. Anything short of a validated
    verdict row leaves the version in research and the output says exactly
    what the guard refused.
    """
    from trading.registry import TransitionRefused, register_version, roster, validate_and_promote

    spec = STRATEGIES.get(args.bot)
    if spec is None:
        raise SystemExit(f"unknown bot {args.bot!r}; choices: {sorted(STRATEGIES)}")

    app_engine = make_engine(args.app_db)
    init_schema(app_engine)
    app_sf = make_session_factory(app_engine)
    with app_sf() as session:
        validation = session.get(BacktestValidation, args.validation_id)
        if validation is None:
            raise SystemExit(f"validation row {args.validation_id} not found in {args.app_db}")
        params = json.loads(args.params) if args.params else json.loads(validation.params_json or "{}")
        universe = [s.strip().upper() for s in args.universe.split(",") if s.strip()] or [validation.symbol]
        try:
            version = register_version(
                session,
                args.bot,
                spec["name"],
                spec["cls"],
                timeframe=args.timeframe or validation.timeframe,
                universe=universe,
                params=params,
            )
            states = []
            failure = None
            try:
                states = validate_and_promote(session, version.id, validation.id)
            except TransitionRefused as exc:
                failure = str(exc)
            session.commit()
        except TransitionRefused as exc:
            session.rollback()
            print(json.dumps({"registered": False, "reason": str(exc)}))
            return 1
        out = {
            "registered": True,
            "version_id": version.id,
            "bot": f"{args.bot}-v{version.version}",
            "state": states[-1].state if states else "research",
            "roster_size": len(roster(session)),
        }
        if failure:
            out["promotion_refused"] = failure
        print(json.dumps(out, indent=2))
        return 0 if states else 1
    app_engine.dispose()


def cmd_validate(args: argparse.Namespace) -> int:
    payload = validate_strategy(
        bot_key=args.bot,
        symbol=args.symbol,
        timeframe=args.timeframe,
        research_db=args.db,
        app_db=args.app_db,
        seed=args.seed,
        min_trades=args.min_trades,
    )
    print(json.dumps(payload, indent=2, default=str))
    return 0 if payload["verdict"] == "validated" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trading.research", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_ing = sub.add_parser("ingest", help="backfill candles into the research database")
    p_ing.add_argument("--symbol", default="BTCUSDT")
    p_ing.add_argument("--timeframe", default="4h")
    p_ing.add_argument("--days", type=int, default=365)
    p_ing.add_argument("--db", default=DEFAULT_RESEARCH_DB, help="candle store (never data.db)")
    p_ing.set_defaults(fn=cmd_ingest)

    p_fund = sub.add_parser("ingest-funding", help="backfill funding-rate history into the research database")
    p_fund.add_argument("--symbol", required=True)
    p_fund.add_argument("--days", type=int, default=365)
    p_fund.add_argument("--db", default=DEFAULT_RESEARCH_DB)
    p_fund.set_defaults(fn=cmd_ingest_funding)

    p_yf = sub.add_parser("ingest-yahoo", help="backfill stocks/indexes/metals via Yahoo Finance")
    p_yf.add_argument("--symbol", required=True)
    p_yf.add_argument("--timeframe", default="1h")
    p_yf.add_argument("--days", type=int, default=729)
    p_yf.add_argument("--db", default=DEFAULT_RESEARCH_DB)
    p_yf.set_defaults(fn=cmd_ingest_yahoo)

    p_pred = sub.add_parser("predict", help="forward-return prediction for one symbol (F9 artifact)")
    p_pred.add_argument("--symbol", required=True)
    p_pred.add_argument("--timeframe", default="1h")
    p_pred.add_argument("--db", default=DEFAULT_RESEARCH_DB)
    p_pred.set_defaults(fn=cmd_predict)

    p_val = sub.add_parser("validate", help="backtest + validation gate + verdict row")
    p_val.add_argument("--bot", required=True, choices=sorted(STRATEGIES))
    p_val.add_argument("--symbol", default="BTCUSDT")
    p_val.add_argument("--timeframe", default="4h")
    p_val.add_argument("--db", default=DEFAULT_RESEARCH_DB, help="candle store the backtest reads")
    p_val.add_argument("--app-db", default=DEFAULT_APP_DB, help="database the verdict rows land in")
    p_val.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p_val.add_argument("--min-trades", type=int, default=MIN_TRADES)
    p_val.set_defaults(fn=cmd_validate)

    p_reg = sub.add_parser(
        "register",
        help="register a validated strategy version into the lifecycle registry",
    )
    p_reg.add_argument("--bot", required=True, choices=sorted(STRATEGIES))
    p_reg.add_argument("--validation-id", type=int, required=True,
                       help="the backtest_validations row this registration stands on")
    p_reg.add_argument("--timeframe", default=None, help="defaults to the validation row's")
    p_reg.add_argument("--universe", default="", help="comma-separated symbols; defaults to the validation row's symbol")
    p_reg.add_argument("--params", default=None, help="JSON object; defaults to the validation row's own params")
    p_reg.add_argument("--app-db", default=DEFAULT_APP_DB, help="database the lifecycle rows land in")
    p_reg.set_defaults(fn=cmd_register)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
