"""ScalpTrend quality: selectivity (fewer, better trades) + NaN safety."""

import numpy as np
import pandas as pd

from trading.bots.scalp_bot import ScalpTrend


def _scalp_df(n=200, seed=3):
    rng = np.random.default_rng(seed)
    close = 60000.0 + np.cumsum(rng.normal(8, 40, n))  # drift up
    open_ = close + rng.normal(0, 10, n)
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 25, n))
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 25, n))
    ema = pd.Series(close).ewm(span=21, adjust=False).mean().to_numpy()
    # mixed regimes: strong trend bars + weak trend + stretched + hot RSI
    ts = np.full(n, 1.6)          # strong uptrend -> fires when location ok
    ts[120:140] = 1.3             # weak trend: tuned (1.5) must skip, loose fires
    ts[150:160] = 2.2
    rsi = np.full(n, 60.0)
    rsi[150:160] = 72.0           # hot RSI: tuned (<=70) must skip, loose fires
    atr = np.full(n, 0.002)       # 0.2% calm
    atr[170:175] = 0.05           # 5% explosive: tuned (ceil 4) must skip
    df = pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": close,
        "volume": np.full(n, 100.0),
        "atr_pct": atr,
        "trend_strength": ts,
        "rsi": rsi,
        "regime": np.full(n, 0.5),
        "ema_fast": ema,
    })
    # pin close to EMA on most bars so pullback gate is satisfiable;
    # stretch a few bars far from EMA (tuned band 1.0 must skip them)
    df["close"] = df["ema_fast"] + rng.normal(0, 0.2 * 0.002 * 60000.0, n)
    df.loc[100:105, "close"] = df.loc[100:105, "ema_fast"] + 1.3 * 0.002 * 60000.0
    return df


def _count(strat, df):
    n = 0
    for i in range(len(df)):
        sig = strat.signal(i, df)
        assert sig is None or (
            sig.side in ("long", "short") and 0.0 <= sig.confidence <= 1.0
        ), "Signal API: side/confidence range"
        if sig is not None:
            assert sig.stop_atr == strat.stop_atr and sig.tp_rr == strat.tp_rr
            n += 1
    return n


def test_selectivity_tuned_fires_fewer_than_loose():
    df = _scalp_df()
    tuned = ScalpTrend()  # regime 1.5 / rsi 70/30 / band 1.0 / ceil 4.0
    loose = ScalpTrend(regime_min=0.8, rsi_long_max=80.0, rsi_short_min=20.0,
                       pullback_band=2.5, vol_ceiling_pct=10.0)
    n_tuned = _count(tuned, df)
    n_loose = _count(loose, df)
    assert n_loose > 0, "loose baseline must fire on this fixture"
    assert n_tuned <= n_loose, f"tuned {n_tuned} should be <=" f" loose {n_loose}"
    assert n_tuned < n_loose, f"tuned {n_tuned} must be strictly fewer than loose {n_loose}"


def test_no_crash_nan_short_and_oob():
    s = ScalpTrend()
    n = 150
    df = pd.DataFrame({
        "open": np.full(n, np.nan), "high": np.full(n, np.nan),
        "low": np.full(n, np.nan), "close": np.full(n, np.nan),
        "volume": np.full(n, np.nan), "atr_pct": np.full(n, np.nan),
        "trend_strength": np.full(n, np.nan), "rsi": np.full(n, np.nan),
        "regime": np.full(n, np.nan), "ema_fast": np.full(n, np.nan),
    })
    for i in range(n):
        assert s.signal(i, df) is None
    assert s.signal(0, df.iloc[:5]) is None   # short frame
    assert s.signal(500, df) is None          # out of range
    assert s.signal(100, None) is None        # null frame
    # NaN close/ema only (indicators valid) must also not raise
    df2 = _scalp_df()
    df2.loc[100, "close"] = np.nan
    df2.loc[101, "ema_fast"] = np.nan
    assert s.signal(100, df2) is None
    assert s.signal(101, df2) is None
