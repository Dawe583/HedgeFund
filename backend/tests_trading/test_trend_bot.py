"""TrendMomentum unit tests — the F1 family's logic pinned on constructed tapes.

The strategy is the search's first family; a logic error here invalidates 40
ledger rows downstream, so the tapes are hand-built to answer exactly one
question each.
"""

import numpy as np
import pandas as pd

from trading.bots.trend_bot import TrendMomentum
from trading.features import build_features


def _tape(closes, freq="4h", start="2025-01-01"):
    """OHLCV from a close path — highs/lows tight around the close so ATR
    stays small and honest."""
    closes = np.asarray(closes, dtype=float)
    open_ = np.concatenate([[closes[0]], closes[:-1]])
    high = np.maximum(open_, closes) * 1.001
    low = np.minimum(open_, closes) * 0.999
    idx = pd.date_range(start, periods=len(closes), freq=freq, tz="UTC")
    return build_features(pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": closes, "volume": np.full(len(closes), 1000.0)},
        index=idx,
    ))


def _ramp(n=600, drift=20.0, base=40_000.0):
    """Steadily rising closes — momentum positive by construction. The drift
    must beat the tape's bar noise scaled by sqrt(lookback): the z-measure
    is honest enough that a gentle ramp correctly reads as noise, so the
    test tape trends hard."""
    return base + np.cumsum(np.full(n, drift))


def _flat(n=600, base=40_000.0):
    return np.full(n, base) + np.sin(np.arange(n) * 0.01) * 0.5  # tiny wobble, no direction


def test_no_signal_before_lookback_history():
    df = _tape(_ramp())
    bot = TrendMomentum(lookback_bars=504)
    for i in (0, 100, 504):
        assert bot.signal(i, df) is None


def test_rising_tape_emits_long():
    df = _tape(_ramp())
    bot = TrendMomentum(lookback_bars=504, entry_z=0.5)
    sig = bot.signal(len(df) - 1, df)
    assert sig is not None and sig.side == "long"


def test_falling_tape_emits_short():
    df = _tape(_ramp()[::-1].copy())
    bot = TrendMomentum(lookback_bars=504, entry_z=0.5)
    sig = bot.signal(len(df) - 1, df)
    assert sig is not None and sig.side == "short"


def test_flat_tape_emits_flat_exit_in_dead_zone():
    df = _tape(_flat())
    # exit_z above zero, no direction anywhere: z hovers near 0, inside the
    # dead band — the bot says flat
    bot = TrendMomentum(lookback_bars=504, entry_z=1.5, exit_z=0.5)
    sig = bot.signal(len(df) - 1, df)
    assert sig is not None and sig.side == "flat"


def test_hysteresis_band_is_silence():
    """z inside [exit_z, entry_z) means hold — no emission at all. Build it:
    rising tape, entry threshold just above the measured z, exit below it."""
    df = _tape(_ramp())
    probe = TrendMomentum(lookback_bars=504, entry_z=0.0)
    i = len(df) - 1
    z = probe._mom_z(i, df)
    assert z is not None and z > 0
    bot = TrendMomentum(lookback_bars=504, entry_z=z + 0.1, exit_z=z - 0.1)
    assert bot.signal(i, df) is None


def test_chaos_vol_kills_everything():
    """Explosive bars push atr_pct past the ceiling — no signal whatever
    momentum says."""
    df = _tape(_ramp())
    df.loc[:, "atr_pct"] = 0.20  # 20% per bar — beyond any ceiling
    bot = TrendMomentum(lookback_bars=504, entry_z=0.0)
    assert bot.signal(len(df) - 1, df) is None


def test_never_raises_on_garbage():
    bot = TrendMomentum()
    assert bot.signal(5, None) is None
    empty = pd.DataFrame(columns=["close", "atr_pct"])
    assert bot.signal(600, empty) is None


def test_statelessness_provenance():
    """Restart-safety is structural: two instances at the same bar emit
    identically — memory cannot diverge because none exists."""
    df = _tape(_ramp())
    a, b = TrendMomentum(), TrendMomentum()
    i = len(df) - 1
    sa, sb = a.signal(i, df), b.signal(i, df)
    assert (sa is None) == (sb is None)
    if sa is not None:
        assert sa.side == sb.side and sa.confidence == sb.confidence
