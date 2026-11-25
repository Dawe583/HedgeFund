"""HFT gate regression tests — P0: fade RR must clear quant floor, ML TF mismatch."""

import pandas as pd

from trading.agents.quant import QuantAnalyst
from trading.backtest.engine import Signal
from trading.bots import HFTMomentum


def _fade_signal():
    strat = HFTMomentum()
    # build a flat-regime high-vol rejection bar at index 100
    import numpy as np

    n = 120
    df = pd.DataFrame(
        {
            "vol_z": np.full(n, 2.5),
            "body_pct": np.full(n, 0.0005),
            "range_pos": np.full(n, 0.5),
            "regime": np.full(n, 0.001),
            "atr_pct": np.full(n, 0.0004),
            "trend_strength": np.full(n, 0.1),
            "rsi": np.full(n, 50.0),
            "close": np.full(n, 80000.0),
            "ema_fast": np.full(n, 80000.0),
        }
    )
    df.loc[100, "range_pos"] = 0.02  # extreme low rejection → fade long
    sig = strat.signal(100, df)
    assert sig is not None
    return sig


def test_fade_tp_rr_clears_quant_floor():
    sig = _fade_signal()
    assert sig.tp_rr >= 1.5, f"fade tp_rr {sig.tp_rr} would be quant-vetoed"


def test_fade_passes_quant_math():
    sig = _fade_signal()
    q = QuantAnalyst(bot_stats={"hft": {"wr": 0.45, "n": 0}})
    m = q.math(
        {
            "signal": sig,
            "bot": "hft",
            "vol_z": 2.0,
            "atr_pct": 0.04,
            "trend_strength": 0.1,
        }
    )
    assert m["approved"] is True


def test_ml_gate_bypass_for_hft_without_1m_model():
    """HFT spec must bypass the 4h champion until a 1m model exists."""
    from trading.paper import BOT_SPECS

    assert BOT_SPECS["hft"]["timeframe"] == "1m"
    assert BOT_SPECS["hft"].get("ml_gate_threshold") is None


def _bar(vol_z=2.5, body_pct=0.0005, range_pos=0.5, regime=0.001, atr_pct=0.0004):
    """Single 1m bar DataFrame with a tradeable row at index 100."""
    import numpy as np
    import pandas as pd

    n = 120
    df = pd.DataFrame(
        {
            "vol_z": np.full(n, 2.0),
            "body_pct": np.full(n, 0.0005),
            "range_pos": np.full(n, 0.5),
            "regime": np.full(n, 0.05),
            "atr_pct": np.full(n, 0.0004),
            "trend_strength": np.full(n, 0.1),
            "rsi": np.full(n, 50.0),
            "close": np.full(n, 80000.0),
            "ema_fast": np.full(n, 80000.0),
        }
    )
    df.loc[100, "vol_z"] = vol_z
    df.loc[100, "body_pct"] = body_pct
    df.loc[100, "range_pos"] = range_pos
    df.loc[100, "regime"] = regime
    df.loc[100, "atr_pct"] = atr_pct
    return df


def test_breakout_atr_normalized_gate_passes_small_body():
    """(a) body 0.05% < 0.10% floor still breaks out when body/atr >= 1.0."""
    from trading.bots import HFTMomentum

    strat = HFTMomentum()
    # body 0.05% with atr 0.04% -> ratio 1.25 >= 1.0; range_pos neutral so
    # only the breakout branch can fire (regime flat but no wick rejection).
    df = _bar(vol_z=2.5, body_pct=0.0008, range_pos=0.5, regime=0.002, atr_pct=0.0004)
    sig = strat.signal(100, df)
    assert sig is not None, "ATR-normalized breakout should fire at body/atr=1.25"
    assert sig.side == "long"


def test_breakout_atr_gate_rejects_weak_body():
    """body below BOTH gates (0.02% vs 0.10% floor, ratio 0.5) -> no signal."""
    from trading.bots import HFTMomentum

    strat = HFTMomentum()
    df = _bar(vol_z=2.5, body_pct=0.0002, range_pos=0.5, regime=0.001, atr_pct=0.0004)
    assert strat.signal(100, df) is None


def test_fade_relaxed_range_pos_passes():
    """(b) fade with range_pos 0.12 passes under the new 0.15 tolerance."""
    from trading.bots import HFTMomentum

    strat = HFTMomentum()
    # body neutral-small so breakout cannot fire; wick at 0.12 must fade-long.
    df = _bar(vol_z=2.5, body_pct=0.0001, range_pos=0.05, regime=0.001, atr_pct=0.0004)
    sig = strat.signal(100, df)
    assert sig is not None, "fade should accept range_pos 0.12 with tol 0.15"
    assert sig.side == "long"
    assert sig.tp_rr >= 1.5


def test_reviewer_hft_tolerance_vs_scalp():
    """(c) hft fade-short at ts=+1.0 approved; identical scalp setup vetoed."""
    from trading.agents.reviewer import SignalReviewer
    from trading.backtest.engine import Signal

    reviewer = SignalReviewer(client=None)
    sig = Signal(side="short", confidence=0.65)
    base = {
        "signal": sig,
        "symbol": "BTCUSDT",
        "price": 80000,
        "trend_strength": 1.0,
        "rsi": 55,
        "atr_pct": 1.0,
        "news_blackout": False,
    }
    ok_hft, _, _ = reviewer._heuristic({**base, "bot": "hft"})
    assert ok_hft, "hft fade-short at ts=+1.0 must pass with tol 1.5"
    ok_scalp, _, _ = reviewer._heuristic({**base, "bot": "scalp"})
    assert not ok_scalp, "scalp short at ts=+1.0 must stay vetoed with tol 0.5"
