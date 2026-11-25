"""Prime local-gate tool tests — QUANT/HFT threshold alignment.

Covers: compute_ev approval at RR1.8/WR45%/vol2.0/atr0.05/conf0.6,
atr_filter 1m envelope boundaries, vol_filter 1m floor at 1.5,
trend_alignment tol kwarg (default 0.5, hft 1.5), quant per-bot min_rr.
"""

from trading.agents.quant import QuantAnalyst
from trading.agents.tools import atr_filter, compute_ev, trend_alignment, vol_filter
from trading.backtest.engine import Signal


def test_compute_ev_approves_reference_setup():
    out = compute_ev(
        realized_wr=0.45, rr=1.8, vol_z=2.0, atr_pct=0.05, conf=0.6, n_trades=0
    )
    assert out["approved"] is True, out["reason"]
    assert 0.5 <= out["size_multiplier"] <= 1.75


def test_compute_ev_rejects_thin_rr_while_sample_thin():
    # turbo: thin-sample floor is rr>=1.5 (was 1.8) — more opportunities pass
    out = compute_ev(
        realized_wr=0.45, rr=1.5, vol_z=2.0, atr_pct=0.05, conf=0.6, n_trades=0
    )
    assert out["approved"] is True, out["reason"]
    out = compute_ev(
        realized_wr=0.45, rr=1.3, vol_z=2.0, atr_pct=0.05, conf=0.6, n_trades=0
    )
    assert out["approved"] is False  # n<20 needs rr>=1.5


def test_atr_filter_1m_boundaries():
    ok, _ = atr_filter(0.05, "1m")
    assert ok
    ok, _ = atr_filter(0.02, "1m")
    assert ok
    ok, _ = atr_filter(1.5, "1m")
    assert ok
    ok, _ = atr_filter(0.01, "1m")
    assert not ok
    ok, _ = atr_filter(1.6, "1m")
    assert not ok


def test_vol_filter_1m_floor_1_5():
    # turbo: 1m floor lowered to 1.0 for ~5 opportunities/day
    ok, _ = vol_filter(1.0, 1.0, "1m")
    assert ok, "1m vol_z 1.0 must pass (turbo floor)"
    ok, _ = vol_filter(0.9, 1.0, "1m")
    assert not ok
    ok, _ = vol_filter(2.0, 1.0, "1m")
    assert ok
    # thin rvol still rejected
    ok, _ = vol_filter(2.0, 0.2, "1m")
    assert not ok


def test_trend_alignment_default_tol():
    ok, _ = trend_alignment("short", 1.0)
    assert not ok  # tol 0.5 default vetoes
    ok, _ = trend_alignment("short", 1.0, tol=1.5)
    assert ok  # hft band approves


def test_quant_per_bot_min_rr():
    q = QuantAnalyst(bot_stats={"hft": {"wr": 0.45, "n": 30}})
    sig = Signal(side="long", confidence=0.6, tp_rr=1.6)
    ctx = {
        "signal": sig,
        "bot": "hft",
        "vol_z": 2.0,
        "atr_pct": 0.05,
        "trend_strength": 0.1,
    }
    assert q.math(ctx)["approved"] is True  # default min_rr 1.5
    assert q.math({**ctx, "min_rr": 1.8})["approved"] is False
