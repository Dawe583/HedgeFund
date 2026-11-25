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
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from trading.backtest.engine import BTConfig, BarsPerYear, run_backtest
from trading.bots import BreakoutVol, HFTMomentum, MeanRev, ScalpTrend
from trading.config import get_settings
from trading.features import build_features
from trading.harness import wrap as harness_wrap
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


def validate_strategy(
    bot_key: str,
    symbol: str,
    timeframe: str,
    research_db: str,
    app_db: str,
    seed: int = DEFAULT_SEED,
    min_trades: int = MIN_TRADES,
    cfg: BTConfig | None = None,
) -> dict:
    """Run backtest + the three statistical checks, write both provenance rows.

    Returns the verdict payload; the same content lands in
    backtest_validations.validation_json, so the database row is the verdict.
    """
    spec = STRATEGIES.get(bot_key)
    if spec is None:
        raise SystemExit(f"unknown bot {bot_key!r}; choices: {sorted(STRATEGIES)}")

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
    bars_per_year = BarsPerYear.get(timeframe, 8_760)
    strategy = spec["cls"]()
    cfg = cfg or BTConfig()
    result = run_backtest(df, harness_wrap(strategy), cfg, timeframe)

    records = trades_to_records(result.trades, symbol.upper())
    initial = float(cfg.initial_equity)

    np.random.seed(seed)  # any consumer of the global RNG reproduces
    mc = monte_carlo_test(
        records, initial, n_simulations=N_SIMULATIONS, seed=seed, bars_per_year=bars_per_year
    )
    bs = bootstrap_sharpe_ci(
        result.equity,
        bars_per_year=bars_per_year,
        n_bootstrap=N_BOOTSTRAP,
        seed=seed,
        initial_capital=initial,
    )
    wf = walk_forward_analysis(
        result.equity,
        records,
        n_windows=N_WINDOWS,
        bars_per_year=bars_per_year,
        initial_capital=initial,
    )

    reasons: list[str] = []
    n_trades = len(result.trades)
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

    metrics = result.metrics
    params = {
        k: getattr(strategy, k)
        for k in (
            "regime_min", "rsi_long_max", "rsi_short_min", "pullback_band",
            "vol_ceiling_pct", "stop_atr", "tp_rr",
        )
        if hasattr(strategy, k)
    }
    data_start = str(df.index[0])
    data_end = str(df.index[-1])

    app_engine = make_engine(app_db)
    init_schema(app_engine)
    app_sf = make_session_factory(app_engine)
    with app_sf() as session:
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

    p_val = sub.add_parser("validate", help="backtest + validation gate + verdict row")
    p_val.add_argument("--bot", required=True, choices=sorted(STRATEGIES))
    p_val.add_argument("--symbol", default="BTCUSDT")
    p_val.add_argument("--timeframe", default="4h")
    p_val.add_argument("--db", default=DEFAULT_RESEARCH_DB, help="candle store the backtest reads")
    p_val.add_argument("--app-db", default=DEFAULT_APP_DB, help="database the verdict rows land in")
    p_val.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p_val.add_argument("--min-trades", type=int, default=MIN_TRADES)
    p_val.set_defaults(fn=cmd_validate)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
