"""Basket composite validation — the slow families' only honest measurement.

docs/research/f1-ledger-2026-11-26.md established the structural fact: slow
momentum per-symbol cannot reach 30 trades in two years at any honest
lookback, while the edge signature is present. The measurement fix is
aggregation: the same candidate fired independently across N coins is a
single composite claim, and the composite's pooled trades carry the sample
size no single coin can.

What a basket is here, precisely: N independent slot backtests, each sized
against its own initial equity, ledger-composed afterwards. The composite
equity is the SUM of slot equities — the honest reading of "capital split
evenly into N independent slots, never rebalanced". The composite initial
capital is N × the slot's. This is NOT a portfolio harness: positions
never interact, margin never pools, and correlation structure enters the
verdict only through the statistics' honesty about it. That is the right
shape for screening; production truth stays phase B rails-on per the
program, and any basket survivor still owes the per-symbol walk before it
trades.

The approximation's known cost: the permutation test treats the pooled
trade sequence as exchangeable, but overlapping positions across coins
share volatility regimes — shuffling breaks clusters the same way it does
in single-symbol tests, so the bias direction is not new, only wider.
Recorded here because the ledger cannot say it.
"""

from __future__ import annotations

import json

import pandas as pd

from trading.backtest.engine import BTConfig, BarsPerYear
from trading.kernel import run_kernel_backtest
from trading.research import MIN_TRADES, gate_stats, trades_to_records
from trading.search import in_sample, ledger_append, load_frame, out_of_sample


def compose_basket(
    results: dict,
    initial: float,
) -> tuple[list, pd.Series]:
    """Pool trade records (time-ordered) and sum slot equities onto the
    union time grid. Slots contribute their starting cash before their
    first bar — an unborn slot is capital at rest, not zero — and
    forward-fill carries each slot's last equity so late-starting tapes do
    not pretend to be early ones."""
    records = []
    equities = {}
    for symbol, result in results.items():
        records.extend(trades_to_records(result.trades, symbol))
        equities[symbol] = result.equity
    records.sort(key=lambda r: r.exit_time)

    union_index = pd.DatetimeIndex(sorted(set().union(*[eq.index for eq in equities.values()])))
    composite = pd.Series(0.0, index=union_index)
    for eq in equities.values():
        aligned = eq.reindex(union_index, method="ffill")
        if len(eq.index):
            aligned.loc[aligned.index < eq.index[0]] = float(eq.iloc[0])
        composite = composite + aligned.fillna(0.0)
    return records, composite


def evaluate_basket(
    conn,
    candidate,
    *,
    symbols: list[str],
    phase: str,
    research_db: str,
    seed: int,
    cfg: BTConfig,
    dfs: dict[str, pd.DataFrame] | None = None,
    min_trades: int = MIN_TRADES,
) -> dict:
    """Evaluate one candidate as a basket composite across `symbols` and
    append the verdict to the ledger. `symbol` in the row is the joined
    basket — the composite IS the claim, per-leg provenance lives in
    legs_json. Same candidate, same phase: exactly one row per basket,
    because the ledger counts evaluations and a basket is one evaluation."""
    import time

    if phase not in ("A", "B"):
        raise ValueError(f"phase must be A or B, got {phase!r}")

    started = time.monotonic()
    window_fn = in_sample if phase == "A" else out_of_sample
    dfs = dfs or {s: load_frame(research_db, s, candidate.timeframe) for s in symbols}
    windows = {s: window_fn(df) for s, df in dfs.items()}
    # cross-sectional hook (F3, 2026-11-26): a candidate may reshape the
    # windows before any backtest — causal injection only, the hook's own
    # docstring owns the honesty argument. Probe the class once; instances
    # are per-slot afterwards exactly as before.
    injector = getattr(candidate.instance(), "inject_cross_section", None)
    if callable(injector):
        windows = injector(windows)

    initial = float(cfg.initial_equity)
    legs: dict[str, dict] = {}
    results = {}
    for symbol in sorted(symbols):
        window = windows[symbol]
        instance = candidate.instance()
        result = run_kernel_backtest(window, instance, cfg, candidate.timeframe)
        results[symbol] = result
        legs[symbol] = {
            "trades_n": len(result.trades),
            "sharpe": round(float(result.metrics.get("sharpe", 0.0)), 4),
            "bars": len(window),
        }

    records, composite = compose_basket(results, initial)
    n_trades = len(records)
    composite_initial = initial * len(symbols)
    bars_per_year = BarsPerYear.get(candidate.timeframe, 2190)
    gate = gate_stats(records, composite, composite_initial, seed, bars_per_year, min_trades, n_trades)
    elapsed = round(time.monotonic() - started, 2)

    first = windows[sorted(symbols)[0]]
    row = {
        "ts": pd.Timestamp.now(tz="UTC").isoformat(),
        "family": candidate.family,
        "candidate": candidate.name,
        "symbol": "+".join(sorted(symbols)),
        "timeframe": candidate.timeframe,
        "params_json": json.dumps(candidate.params, sort_keys=True),
        "phase": phase,
        "verdict": gate["verdict"],
        "trades_n": n_trades,
        "permutation_p": gate["p_sharpe"],
        "sharpe_ci_lo": gate["bs"].get("ci_lower"),
        "wf_positive": gate["wf_pos"],
        "wf_total": gate["wf_total"],
        "sharpe": gate["bs"].get("observed_sharpe"),
        "profit_factor": None,
        "max_dd_pct": gate["mc"].get("actual_max_dd"),
        "rails": "off" if phase == "A" else "on",
        "data_start": str(first.index[0]),
        "data_end": str(first.index[-1]),
        "data_rows": len(first),
        "seed": seed,
        "reasons_json": json.dumps(gate["reasons"]),
        "elapsed_s": elapsed,
        "legs_json": json.dumps(legs, sort_keys=True),
    }
    row_id = ledger_append(conn, row)
    return {"id": row_id, **row, "gate": gate, "legs": legs}
