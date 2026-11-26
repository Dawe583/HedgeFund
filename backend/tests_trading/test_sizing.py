"""M3 slice 3 acceptance tests — redesigned sizing, multi-symbol by construction.

Design §10/D10: three explicit sizing stages (risk budget, approved leverage
as a constant per-strategy multiplier, hard exposure caps); conviction NEVER
scales size; caps veto with a recorded reason, never resize.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading.backtest.engine import BTConfig, Signal
from trading.features import build_features
from trading.kernel import run_kernel_backtest


def _ohlcv(n=700, drift=2.0, seed=11, freq="4h"):
    """Same generator as the kernel tests — OHLC-consistent synthetic series."""
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


class BarOneFifty:
    """Long signal at exactly frame position 150, wide protective levels —
    the position exits on timeout, never stop/tp, so entry sizing is the
    only thing under measurement."""

    def __init__(self, confidence=0.9, at=150):
        self._confidence = confidence
        self._at = at

    def signal(self, i, df):
        if i == self._at:
            return Signal(side="long", confidence=self._confidence, stop_atr=2.0, tp_rr=1.5)
        return None


def _run(df, **cfg_kw):
    cfg = BTConfig(fee_pct=0.0, slippage_bps=0.0, confidence_min=0.5, max_bars_in_trade=10, **cfg_kw)
    return run_kernel_backtest(df, BarOneFifty(), cfg, "4h")


def test_confidence_never_scales_size():
    """The same signal at confidence 0.6 and 0.9 — both above the gate —
    must size identically. Conviction is a threshold, never a multiplier
    (design §10: dynamic leverage-by-conviction is deleted)."""
    df = build_features(_ohlcv())

    class Conf06(BarOneFifty):
        def __init__(self):
            super().__init__(confidence=0.6)

    cfg = BTConfig(fee_pct=0.0, slippage_bps=0.0, confidence_min=0.5, max_bars_in_trade=10)
    hi = run_kernel_backtest(df.copy(), BarOneFifty(confidence=0.9), cfg, "4h")
    lo = run_kernel_backtest(df.copy(), Conf06(), cfg, "4h")
    assert len(hi.trades) == len(lo.trades) == 1, "each run must produce exactly one trade"
    assert hi.trades[0]["qty"] == pytest.approx(lo.trades[0]["qty"], rel=1e-9)


def test_leverage_scales_size_linearly():
    """Approved leverage is the second sizing stage: leverage 2 vs leverage
    1 on identical signals must double the quantity (design §2: leverage is
    a constant mandate property, not a function of conviction)."""
    df = build_features(_ohlcv())
    one = _run(df.copy(), leverage=1.0, max_symbol_exposure=25.0, max_gross_exposure=25.0)
    two = _run(df.copy(), leverage=2.0, max_symbol_exposure=25.0, max_gross_exposure=25.0)
    assert len(one.trades) == len(two.trades) == 1
    # instrument qty precision rounds each leg independently — the ratio is
    # exact in continuous math, ±1 step in the discrete one
    assert two.trades[0]["qty"] == pytest.approx(one.trades[0]["qty"] * 2, rel=0.02)


def test_leverage_above_ceiling_raises():
    """The approved-leverage ceiling is hard: a config above it fails at
    construction, never at the first order."""
    with pytest.raises(ValueError, match="leverage"):
        BTConfig(leverage=25.01)
    with pytest.raises(ValueError, match="leverage"):
        BTConfig(leverage=0.0)
    with pytest.raises(ValueError, match="leverage"):
        BTConfig(leverage=-2.0)
    # the ceiling itself is legal — it was the legacy bound
    BTConfig(leverage=25.0)


def test_exposure_cap_veto_is_recorded_with_reason():
    """A candidate entry whose notional exceeds the per-symbol cap must not
    trade, and the veto must be visible in run state with the reason and the
    input numbers — a silent skip is unacceptable."""
    df = build_features(_ohlcv())
    # unlevered baseline on this tape sizes at ~2.3x equity notional
    # (measured: risk 2% / stop distance 2x ATR of ~0.86% of price)
    wide = _run(df.copy(), max_symbol_exposure=4.0, max_gross_exposure=8.0)
    assert len(wide.trades) == 1, "the uncapped baseline must trade — the tape is sized for it"
    base_notional = wide.trades[0]["qty"] * wide.trades[0]["entry_price"]
    base_equity = float(wide.equity.iloc[0])
    assert base_notional / base_equity > 2.0, "tape calibration drifted — re-measure before re-capping"

    capped = _run(df.copy(), max_symbol_exposure=2.0, max_gross_exposure=8.0)
    assert capped.trades == [], "an entry breaching the cap must be vetoed, never resized into compliance"
    vetoes = capped.metrics.get("vetoes", [])
    assert len(vetoes) == 1
    v = vetoes[0]
    assert v["reason"] == "symbol_exposure_cap"
    assert v["notional"] > v["equity"] * v["symbol_cap"], "the veto's numbers must show the breach"
    assert v["symbol_notional_open"] == 0.0
    assert v["instrument"].startswith("BTCUSDT")


def test_gross_cap_veto_records_gross_reason():
    df = build_features(_ohlcv())
    res = _run(df.copy(), max_symbol_exposure=2.0, max_gross_exposure=2.0)
    assert res.trades == []
    vetoes = res.metrics.get("vetoes", [])
    assert len(vetoes) == 1
    # with an empty book both caps breach on the same entry; the symbol cap
    # is checked first, so gross-only binding needs a book with other-symbol
    # exposure — covered in the desk test. Here assert the recorded reason
    # is one of the cap rails, never a silent skip.
    assert vetoes[0]["reason"] in ("symbol_exposure_cap", "gross_exposure_cap")


def test_gross_cap_binds_on_other_instrument_exposure():
    """Gross-only binding: the per-symbol cap passes (no exposure on this
    instrument), but the desk-wide gross — including another instrument's
    open notional — vetoes the entry with reason gross_exposure_cap. This
    is the multi-symbol property: caps read the desk's whole book."""
    from trading.kernel import ExposureBook

    df = build_features(_ohlcv())
    # calibrate the unlevered entry's notional ratio on this tape
    wide = _run(df.copy(), max_symbol_exposure=4.0, max_gross_exposure=8.0)
    entry_ratio = wide.trades[0]["qty"] * wide.trades[0]["entry_price"] / float(wide.equity.iloc[0])
    # seed the book with other-instrument exposure that leaves exactly
    # enough gross room for NOTHING: gross cap just above the seed alone
    book = ExposureBook()
    equity = 1_000.0  # BTConfig default initial equity
    seed_ratio = 3.0
    book.add("ETHUSDT-PERP.SIM", "seed-order-1", equity * seed_ratio)
    cfg = BTConfig(
        fee_pct=0.0, slippage_bps=0.0, confidence_min=0.5, max_bars_in_trade=10,
        max_symbol_exposure=4.0,  # entry ratio ~2.3 passes the symbol cap
        max_gross_exposure=seed_ratio + entry_ratio / 2,  # seed + entry exceeds it
    )
    res = run_kernel_backtest(df.copy(), BarOneFifty(), cfg, "4h", exposure_book=book)
    assert res.trades == [], "the gross cap must veto even when the symbol cap passes"
    vetoes = res.metrics.get("vetoes", [])
    assert len(vetoes) == 1
    assert vetoes[0]["reason"] == "gross_exposure_cap"
    assert vetoes[0]["gross_notional_open"] == pytest.approx(equity * seed_ratio)
    assert vetoes[0]["symbol_notional_open"] == 0.0


def test_symbol_cap_above_gross_cap_rejected():
    """A cap configuration that can never be satisfied netting is a config
    bug, and it must fail loud at construction."""
    with pytest.raises(ValueError, match="symbol cap"):
        BTConfig(max_symbol_exposure=9.0, max_gross_exposure=5.0)


@pytest.fixture()
def session_factory(tmp_path):
    from trading.models import init_schema, make_engine, make_session_factory
    engine = make_engine(f"sqlite:///{tmp_path}/desk.db")
    init_schema(engine)
    return make_session_factory(engine)


# ---------------------------------------------------------------------------
# desk-level: two strategies share one exposure book — leverage is per
# strategy, caps read desk-wide truth
# ---------------------------------------------------------------------------


def _two_bot_desk(session_factory, cfg_a, cfg_b):
    """Boot a two-bot desk on identical replayed tapes and wait until both
    bots' entries are decided (fill OR veto). Modeled directly on
    test_desk.py's in-process multi-symbol test — nothing mocked."""
    import threading
    import time

    from trading.kernel import build_bars
    from trading.desk.node import DeskNode, DeskSpec
    from trading.desk.replay import ReplayFeeder

    # future-anchored tapes: replay compresses hours into ms, and the
    # sandbox's drain logic needs the tape ahead of wall clock (see test_desk)
    raw = _ohlcv(n=400)
    start = pd.Timestamp.now(tz="UTC").floor("4h") + pd.Timedelta("4h")
    raw.index = pd.date_range(start, periods=len(raw), freq="4h", tz="UTC")

    specs = [
        DeskSpec(bot="bot_a", symbol="BTCUSDT", timeframe="4h", strategy_cls=BarOneFifty, bt_config=cfg_a),
        DeskSpec(bot="bot_b", symbol="ETHUSDT", timeframe="4h", strategy_cls=BarOneFifty, bt_config=cfg_b),
    ]
    desk = DeskNode(specs=specs, session_factory=session_factory, seed_history=lambda s, t: [])
    desk.build()

    feeders = {}
    for spec, fid in (("bot_a", "feed-a"), ("bot_b", "feed-b")):
        feeder = ReplayFeeder(
            bars=build_bars(raw, desk.instruments[spec], "4h"),
            instrument=desk.instruments[spec], interval_ms=5, feeder_id=fid,
            quiescence=lambda s=spec: (
                desk._strategy_for(s)._k + 1 >= feeders[s].emitted
                and desk.states[s].order_chain_drained()
            ),
        )
        feeders[spec] = feeder
        desk.node.trader.add_actor(feeder)
    t = threading.Thread(target=desk.node.run, daemon=True)
    t.start()

    def decided(bot):
        st = desk.states[bot]
        entries = [f for f in st.fills if f["role"] == "entry"]
        return bool(entries) or bool(st.vetoes)

    deadline = time.time() + 60
    while time.time() < deadline and not (decided("bot_a") and decided("bot_b")):
        time.sleep(0.05)
    try:
        desk.node.stop()
    except Exception:
        pass
    return desk


def test_desk_per_strategy_leverage_produces_per_strategy_sizes(session_factory):
    """Two strategies with different approved leverage on identical signals
    must produce different sizes — leverage is a per-strategy mandate
    property, never desk-global. Wide caps keep sizing unconstrained so the
    ratio is pure leverage."""
    cfg_lo = BTConfig(fee_pct=0.0, slippage_bps=0.0, leverage=1.0, max_symbol_exposure=25.0, max_gross_exposure=25.0)
    cfg_hi = BTConfig(fee_pct=0.0, slippage_bps=0.0, leverage=2.0, max_symbol_exposure=25.0, max_gross_exposure=25.0)
    desk = _two_bot_desk(session_factory, cfg_lo, cfg_hi)

    qty_a = [f for f in desk.states["bot_a"].fills if f["role"] == "entry"]
    qty_b = [f for f in desk.states["bot_b"].fills if f["role"] == "entry"]
    assert qty_a and qty_b, "both entries must fill — caps are wide, tapes identical"
    assert qty_b[0]["qty"] == pytest.approx(qty_a[0]["qty"] * 2, rel=0.02), (
        f"leverage 2 must double leverage 1: {qty_b[0]['qty']} vs {qty_a[0]['qty']}"
    )


def test_desk_gross_cap_vetoes_second_symbol(session_factory):
    """The multi-symbol cap property end to end: two simultaneous entries on
    different instruments, each inside its own per-symbol cap, but their SUM
    over the gross cap — exactly one may open, the other is vetoed with
    reason gross_exposure_cap recorded in its run state."""
    # unlevered entries on this tape are ~2.3x equity each: 4.6x combined
    cfg = BTConfig(fee_pct=0.0, slippage_bps=0.0, max_symbol_exposure=4.0, max_gross_exposure=4.0)
    desk = _two_bot_desk(session_factory, cfg, cfg)

    entries = {
        bot: [f for f in desk.states[bot].fills if f["role"] == "entry"]
        for bot in ("bot_a", "bot_b")
    }
    vetoes = {bot: desk.states[bot].vetoes for bot in ("bot_a", "bot_b")}
    opened = sum(1 for bot in entries if entries[bot])
    vetoed = sum(1 for bot in vetoes if vetoes[bot])
    assert opened == 1 and vetoed == 1, (
        "exactly one entry may open under a 4.0 gross cap against 2x2.3x demand: "
        f"entries={ {b: len(v) for b, v in entries.items()} } vetoes={vetoes}"
    )
    vetoed_bot = next(bot for bot in vetoes if vetoes[bot])
    assert vetoes[vetoed_bot][0]["reason"] == "gross_exposure_cap"
    # the loser's veto must show the winner's exposure in the book —
    # desk-wide truth, not a per-bot blind spot
    assert vetoes[vetoed_bot][0]["gross_notional_open"] > 0
