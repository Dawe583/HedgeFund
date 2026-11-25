"""New bots: BreakoutVol + MeanRev — signal fires, confidence range, NaN safety."""

import math

import numpy as np
import pandas as pd

from trading.bots import BreakoutVol, MeanRev


def _trend_df(n=120, breakout_idx=100):
    # steady uptrend then a high-volume breakout bar
    close = 60000.0 + np.arange(n) * 10.0
    close[breakout_idx] += 150.0  # push above prior highs
    open_ = close - 30.0
    high = np.maximum(open_, close) + 5.0
    low = np.minimum(open_, close) - 5.0
    df = pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": close,
        "volume": np.full(n, 100.0),
        "vol_z": np.full(n, 0.2),
        "body_pct": (close - open_) / open_,
        "range_pos": np.full(n, 0.6),
        "regime": np.full(n, 0.4),
        "atr_pct": np.full(n, 0.0004),
        "trend_strength": np.full(n, 1.5),
        "rsi": np.full(n, 60.0),
        "ema_fast": pd.Series(close).ewm(span=21, adjust=False).mean().to_numpy(),
    })
    df.loc[breakout_idx, "vol_z"] = 2.5
    return df, breakout_idx


def _range_df(n=120, fade_idx=100):
    # flat market with an oversold dip at fade_idx
    rng = np.random.default_rng(7)
    close = 65000.0 + np.sin(np.arange(n) * 0.4) * 120.0 + rng.normal(0, 8, n)
    open_ = close + rng.normal(0, 5, n)
    high = np.maximum(open_, close) + 20.0
    low = np.minimum(open_, close) - 20.0
    ema = pd.Series(close).ewm(span=21, adjust=False).mean().to_numpy()
    df = pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": close,
        "volume": np.full(n, 100.0),
        "vol_z": np.full(n, 0.3),
        "body_pct": (close - open_) / open_,
        "range_pos": np.full(n, 0.5),
        "regime": np.full(n, 0.02),
        "atr_pct": np.full(n, 0.0006),
        "trend_strength": np.full(n, 0.1),
        "rsi": np.full(n, 50.0),
        "ema_fast": ema,
    })
    # force oversold + stretched-below-mean at fade_idx
    df.loc[fade_idx, "rsi"] = 32.0
    df.loc[fade_idx, "close"] = ema[fade_idx] - 1.2 * 0.0006 * 65000.0
    df.loc[fade_idx, "range_pos"] = 0.05
    return df, fade_idx


def test_breakout_fires_on_trend():
    strat = BreakoutVol()
    df, idx = _trend_df()
    sig = strat.signal(idx, df)
    assert sig is not None, "breakout should fire on trending breakout bar"
    assert sig.side == "long"
    assert 0.0 <= sig.confidence <= 1.0


def test_meanrev_fires_on_range():
    strat = MeanRev()
    df, idx = _range_df()
    sig = strat.signal(idx, df)
    assert sig is not None, "meanrev should fire on oversold ranging bar"
    assert sig.side == "long"
    assert 0.0 <= sig.confidence <= 1.0


def test_confidence_in_range_many_bars():
    b, m = BreakoutVol(), MeanRev()
    df_t, _ = _trend_df()
    df_r, _ = _range_df()
    for i in range(len(df_t)):
        for s, d in ((b, df_t), (m, df_r)):
            sig = s.signal(i, d)
            if sig is not None:
                assert 0.0 <= sig.confidence <= 1.0
                assert sig.side in ("long", "short")


def test_no_nan_crash():
    b, m = BreakoutVol(), MeanRev()
    n = 60
    df = pd.DataFrame({
        "open": np.full(n, np.nan), "high": np.full(n, np.nan),
        "low": np.full(n, np.nan), "close": np.full(n, np.nan),
        "vol_z": np.full(n, np.nan), "body_pct": np.full(n, np.nan),
        "range_pos": np.full(n, np.nan), "regime": np.full(n, np.nan),
        "atr_pct": np.full(n, np.nan), "trend_strength": np.full(n, np.nan),
        "rsi": np.full(n, np.nan),
        "ema_fast": np.full(n, np.nan),
    })
    for i in range(n):
        assert b.signal(i, df) is None
        assert m.signal(i, df) is None
    # short / empty frames must not raise either
    assert b.signal(0, df.iloc[:5]) is None
    assert m.signal(200, df) is None
