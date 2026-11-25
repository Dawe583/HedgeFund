import numpy as np
import pandas as pd

from trading.analytics import (
    cluster_liquidity,
    key_levels,
    order_blocks,
    swing_pivots,
    volume_profile,
)


def _df_with_equal_highs():
    """Construct candles with double top at 100 and double bottom at 90."""
    rows = []
    price = 95.0
    for i in range(200):
        if i in (50, 80):
            high = 100.0  # equal highs — liquidity pool
        else:
            high = price + 0.4
        if i in (60, 120):
            low = 90.0  # equal lows
        else:
            low = price - 0.4
        rows.append(
            {
                "open_time": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(hours=i),
                "open": price,
                "high": max(high, price),
                "low": min(low, price),
                "close": price + (0.1 if i % 2 else -0.05),
                "volume": 10.0,
            }
        )
        price += np.sin(i / 12) * 0.8
    return pd.DataFrame(rows).set_index("open_time")


def test_swing_pivots_finds_extremes():
    df = _df_with_equal_highs()
    pivots = swing_pivots(df, lookback=5)
    highs = [p["price"] for p in pivots if p["type"] == "liquidity_high"]
    assert any(abs(h - 100.0) < 0.3 for h in highs)


def test_cluster_liquidity_merges_touches():
    df = _df_with_equal_highs()
    pivots = swing_pivots(df, lookback=5)
    zones = cluster_liquidity(pivots, tol_pct=0.15, min_touches=2)
    assert zones, "should find at least one clustered zone"
    top = zones[0]
    assert top["touches"] >= 2


def test_volume_profile_poc_in_value_area():
    df = _df_with_equal_highs()
    vp = volume_profile(df)
    assert vp["val"] <= vp["poc"] <= vp["vah"]
    assert len(vp["bins"]) == 24


def test_order_blocks_structure():
    df = _df_with_equal_highs()
    obs = order_blocks(df)
    for b in obs:
        assert b["low"] < b["high"]
        assert b["type"] in ("bullish_ob", "bearish_ob")
        assert b["age_bars"] >= 0


def test_key_levels_snapshot():
    df = _df_with_equal_highs()
    snap = key_levels(df)
    assert {"liquidity_zones", "order_blocks", "volume_profile", "recent_pivots"} <= set(snap)


def test_no_nan_leaks_into_levels():
    df = _df_with_equal_highs()
    snap = key_levels(df)
    for z in snap["liquidity_zones"]:
        assert not np.isnan(z["price"])
