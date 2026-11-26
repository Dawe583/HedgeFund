"""MeanRevRegime unit tests — the regime filter is the hypothesis, so the
regime behavior is what gets pinned: ranging tapes fade, trending tapes
stay out, reversion completion goes flat."""

import numpy as np
import pandas as pd
import pytest

from trading.bots.meanrev_regime_bot import MeanRevRegime


def _tape(closes, freq="1h", start="2025-01-01"):
    idx = pd.date_range(start, periods=len(closes), freq=freq, tz="UTC")
    closes = np.asarray(closes, dtype=float)
    df = pd.DataFrame(index=idx)
    df["close"] = closes
    df["atr_pct"] = 0.5  # 0.5% of price per bar — quiet but alive
    return df


def test_no_signal_before_warmup():
    df = _tape(100 + np.cumsum(np.zeros(400)))
    bot = MeanRevRegime(regime_lookback=168)
    for i in (0, 100, 168):
        assert bot.signal(i, df) is None


def test_overextension_in_ranging_tape_fades():
    # quiet oscillation for 300 bars, then a sharp spike up: ranging regime,
    # dev extended positive → short fade
    rng = np.random.default_rng(7)
    base = 100 + np.cumsum(rng.normal(0, 0.05, 400))
    spike = base.copy()
    spike[-1] = base[-1] * 1.03  # 3% jump vs ~0.5% atr → dev z ≈ 6
    df = _tape(spike)
    bot = MeanRevRegime(entry_dev=2.0, regime_max=0.5)
    sig = bot.signal(len(df) - 1, df)
    assert sig is not None and sig.side == "short", f"expected short fade, got {sig}"


def test_trending_regime_stays_out():
    # hard ramp — regime z large; even an extended dev must not fade
    ramp = 100 + np.cumsum(np.full(400, 0.4))
    ramp[-1] *= 1.02  # extend further
    df = _tape(ramp)
    bot = MeanRevRegime(entry_dev=1.5, regime_max=0.5)
    assert bot.signal(len(df) - 1, df) is None


def test_quiet_tape_goes_flat_when_unextended():
    rng = np.random.default_rng(11)
    base = 100 + np.cumsum(rng.normal(0, 0.05, 400))
    df = _tape(base)  # dev z small at the last bar with high probability
    bot = MeanRevRegime(exit_dev=0.6)
    sig = bot.signal(len(df) - 1, df)
    if sig is not None:
        assert sig.side == "flat", f"unextended ranging tape must go flat or silent, got {sig.side}"


def test_stateless_same_inputs_same_signal():
    rng = np.random.default_rng(13)
    base = 100 + np.cumsum(rng.normal(0, 0.05, 400))
    df = _tape(base)
    a, b = MeanRevRegime(), MeanRevRegime()
    i = len(df) - 1
    sa, sb = a.signal(i, df), b.signal(i, df)
    assert (sa is None) == (sb is None)
    if sa is not None:
        assert sa.side == sb.side and sa.confidence == sb.confidence


def test_nan_close_no_signal():
    closes = 100 + np.cumsum(np.zeros(400))
    closes[-1] = np.nan
    df = _tape(closes)
    bot = MeanRevRegime()
    assert bot.signal(len(df) - 1, df) is None


def test_signal_never_raises_on_short_frame():
    df = _tape(np.array([100.0, 101.0]))
    bot = MeanRevRegime()
    assert bot.signal(1, df) is None
    assert bot.signal(0, df) is None
