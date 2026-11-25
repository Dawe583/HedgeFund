import numpy as np
import pandas as pd
import pytest

from trading.features import atr, build_features, candles_to_df, make_labels, rsi


@pytest.fixture
def ohlcv():
    rng = np.random.default_rng(42)
    n = 500
    close = np.cumsum(rng.normal(0, 5, n)) + 50_000
    high = close * (1 + np.abs(rng.normal(0, 0.002, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.002, n)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    vol = np.abs(rng.normal(1000, 200, n))
    idx = pd.date_range("2026-01-01", periods=n, freq="4h", tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    )


def test_rsi_bounds(ohlcv):
    r = rsi(ohlcv["close"], 14).dropna()
    assert ((r >= 0) & (r <= 100)).all()


def test_atr_positive(ohlcv):
    assert (atr(ohlcv, 14).dropna() > 0).all()


def test_build_features_columns(ohlcv):
    feats = build_features(ohlcv)
    for col in ("ema_sep", "rsi", "atr_pct", "rvol", "regime", "range_pos"):
        assert col in feats.columns


def test_labels_shape(ohlcv):
    labels = make_labels(ohlcv, horizon=6)
    assert len(labels) == len(ohlcv)
    assert set(labels.unique()) <= {-1, 0, 1}


def test_candles_roundtrip(ohlcv):
    rows = [
        {
            "open_time": idx,
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "close": r.close,
            "volume": r.volume,
        }
        for idx, r in ohlcv.iterrows()
    ]
    df = candles_to_df(rows)
    assert len(df) == len(ohlcv)
