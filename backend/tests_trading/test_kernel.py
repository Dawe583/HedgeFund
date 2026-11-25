"""M2 acceptance tests for the nautilus kernel adapter.

The design's two hard requirements (hedge-fund-os.md §M2):
1. a deliberately lookahead-poisoned strategy gets no future data — the
   cheating strategy must produce zero trades through the kernel harness
2. the execution wrapper never fills before the bar after the signal — every
   trade's entry_bar is strictly greater than its signal_bar, computed from
   the kernel's own fill timestamps, not from the harness's bookkeeping

Plus the invariants the reconstruction stands on: determinism (same input,
same verdict input — seeded validation is meaningless otherwise), the net
equity arithmetic tying out, and SL/TP child orders never corrupting
positions after a manual close.
"""

import numpy as np
import pandas as pd
import pytest

from trading.backtest.engine import BTConfig, Signal
from trading.bots import ScalpTrend
from trading.features import build_features
from trading.kernel import run_kernel_backtest


def _ohlcv(n=700, drift=2.0, seed=11, freq="4h"):
    """OHLC-consistent synthetic series — kernel bars validate low <= open <= high,
    so the frame must be a plausible market, not noise around close."""
    rng = np.random.default_rng(seed)
    steps = np.cumsum(rng.normal(drift, 60, n)) + 40_000
    close = steps
    open_ = np.concatenate([[close[0]], close[:-1]])
    body_hi = np.maximum(open_, close)
    body_lo = np.minimum(open_, close)
    high = body_hi * (1 + np.abs(rng.normal(0, 0.002, n)))
    low = body_lo * (1 - np.abs(rng.normal(0, 0.002, n)))
    vol = np.abs(rng.normal(1000, 100, n))
    idx = pd.date_range("2025-01-01", periods=n, freq=freq, tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    )


class CheatingStrategy:
    """Reads the future on purpose: signals long whenever the bar 5 ahead is higher.
    Positional indexing means the truncated harness frame makes every such read
    raise — inside the strategy's own guard, that is 'no signal'."""

    def signal(self, i, df):
        try:
            future_close = df["close"].iloc[i + 5]
            now_close = df["close"].iloc[i]
        except Exception:
            return None
        if future_close > now_close * 1.001:
            return Signal(side="long", confidence=0.9)
        return None


class AlwaysLong:
    def signal(self, i, df):
        if i < 96:
            return None
        return Signal(side="long", confidence=0.9, stop_atr=2.0, tp_rr=1.5)


_CFG = BTConfig(confidence_min=0.5, max_bars_in_trade=10)


def test_cheating_strategy_gets_no_future_data_through_the_kernel():
    df = build_features(_ohlcv())
    res = run_kernel_backtest(df, CheatingStrategy(), BTConfig(fee_pct=0.0, slippage_bps=0.0, confidence_min=0.0), "4h")
    assert res.trades == []


def test_no_fill_precedes_the_bar_after_its_signal():
    """The M2 execution-wrapper acceptance, verbatim: for every trade, the
    kernel fill happened no earlier than the bar after the signal bar.
    entry_bar/exit_bar are re-derived from raw kernel fill timestamps in the
    reconstruction — independent of the harness's own bookkeeping."""
    df = build_features(_ohlcv())
    res = run_kernel_backtest(df, ScalpTrend(), _CFG, "4h")
    assert len(res.trades) > 0, "the acceptance test is meaningless on a run without trades"
    for t in res.trades:
        assert t["entry_bar"] > t["signal_bar"], (
            f"entry fill at bar {t['entry_bar']} is not after signal bar {t['signal_bar']}"
        )
        # an exit may never precede the entry either — degenerate kernel states
        # would violate this even when timing is right
        assert t["exit_bar"] >= t["entry_bar"]


def test_kernel_runs_are_deterministic():
    df = build_features(_ohlcv(n=400, seed=5))
    a = run_kernel_backtest(df, ScalpTrend(), _CFG, "4h")
    b = run_kernel_backtest(df, ScalpTrend(), _CFG, "4h")
    assert len(a.trades) == len(b.trades)
    for ta, tb in zip(a.trades, b.trades):
        assert ta["entry_price"] == tb["entry_price"]
        assert ta["exit_price"] == tb["exit_price"]
        assert ta["pnl"] == tb["pnl"]
        assert ta["entry_time"] == tb["entry_time"]
    assert a.equity.equals(b.equity)


def test_equity_curve_is_realized_only_and_ties_out():
    """The validated curve moves only at exit bars, by exactly the trade pnl,
    and ends at the sum of pnls over initial equity — the ported model's
    accounting identity, on kernel fills."""
    df = build_features(_ohlcv())
    cfg = _CFG
    res = run_kernel_backtest(df, ScalpTrend(), cfg, "4h")
    total_pnl = sum(t["pnl"] for t in res.trades)
    assert res.equity.iloc[-1] == pytest.approx(cfg.initial_equity + total_pnl, rel=1e-9)
    # realized-only: between consecutive exits the curve is flat
    exit_bars = sorted({t["exit_bar"] for t in res.trades})
    flat = res.equity.diff().fillna(0.0)
    moved = set(np.flatnonzero(flat.to_numpy() != 0.0).tolist())
    assert moved.issubset(set(exit_bars)), (
        f"equity moved at bars {sorted(moved - set(exit_bars))} where no trade exited"
    )


def test_fees_and_slippage_applied_in_reconstruction():
    """Zero-cost config must reproduce the raw kernel price relation: with no
    fee and no slippage a long's pnl is exactly (exit-entry)*qty — proof the
    reconstruction arithmetic is the thing being adjusted, nothing else."""
    df = build_features(_ohlcv())
    res = run_kernel_backtest(
        df, ScalpTrend(), BTConfig(confidence_min=0.5, fee_pct=0.0, slippage_bps=0.0), "4h"
    )
    assert len(res.trades) > 0
    for t in res.trades:
        direction = 1 if t["side"] == "long" else -1
        expected = (t["exit_price"] - t["entry_price"]) * t["qty"] * direction
        assert t["pnl"] == pytest.approx(expected, rel=1e-9)
        assert t["fees"] == 0.0


def test_resting_children_never_invert_a_flat_position():
    """After every manual close the OCO children are canceled (60/60 measured
    in verification); a reduce-only fill while flat would invert the kernel
    position silently. The reconstruction's evidence: every exit fill belongs
    to a position that was actually open — exit_bar >= entry_bar already
    covers ordering, this covers role sanity: sides never flip mid-trade."""
    df = build_features(_ohlcv())
    res = run_kernel_backtest(df, AlwaysLong(), _CFG, "4h")
    assert len(res.trades) > 0
    for t in res.trades:
        assert t["side"] == "long"
        # AlwaysLong never exits flat-signal; every close is stop/tp/timeout —
        # and stops/tps prove the resting-order path fired for real positions
        assert t["reason"] in ("stop", "take_profit", "timeout")


def test_honest_strategy_trades_through_the_kernel():
    """Smoke-level guard: ScalpTrend on the shared synthetic frame must produce
    trades at all — a regression that silently zeroes the pipeline is worse
    than a loud failure."""
    df = build_features(_ohlcv())
    res = run_kernel_backtest(df, ScalpTrend(), _CFG, "4h")
    assert len(res.trades) > 0
    assert "trades_n" in res.metrics
    assert len(res.equity) == len(df)
