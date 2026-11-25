"""Technical market structure analytics — Coinglass-style overlays.

All functions take a candle DataFrame (open_time index + ohlcv) and return
JSON-serializable levels/zones the dashboard draws over price.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def swing_pivots(df: pd.DataFrame, lookback: int = 5) -> list[dict]:
    """Fractal highs/lows — classic liquidity pool markers."""
    hi, lo = df["high"], df["low"]
    pivots: list[dict] = []
    for i in range(lookback, len(df) - lookback):
        win_h = hi.iloc[i - lookback : i + lookback + 1]
        win_l = lo.iloc[i - lookback : i + lookback + 1]
        if hi.iloc[i] == win_h.max():
            pivots.append(
                {"type": "liquidity_high", "price": float(hi.iloc[i]), "ts": str(df.index[i])}
            )
        if lo.iloc[i] == win_l.min():
            pivots.append(
                {"type": "liquidity_low", "price": float(lo.iloc[i]), "ts": str(df.index[i])}
            )
    return pivots


def cluster_liquidity(pivots: list[dict], tol_pct: float = 0.15, min_touches: int = 2) -> list[dict]:
    """Cluster nearby pivot prices into liquidity zones (equal highs/lows)."""
    if not pivots:
        return []
    pts = sorted(pivots, key=lambda p: p["price"])
    clusters: list[list[dict]] = [[pts[0]]]
    for p in pts[1:]:
        ref = clusters[-1][-1]["price"]
        if abs(p["price"] - ref) / ref * 100 <= tol_pct:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    out = []
    for c in clusters:
        if len(c) >= min_touches:
            prices = [x["price"] for x in c]
            kinds = {x["type"] for x in c}
            out.append(
                {
                    "price": float(np.mean(prices)),
                    "low": float(min(prices)),
                    "high": float(max(prices)),
                    "touches": len(c),
                    "kind": "bid_side" if "liquidity_low" in kinds and "liquidity_high" not in kinds
                    else "ask_side" if "liquidity_high" in kinds and "liquidity_low" not in kinds
                    else "mixed",
                    "last_ts": c[-1]["ts"],
                }
            )
    return sorted(out, key=lambda z: -z["touches"])


def order_blocks(df: pd.DataFrame, impulse_atr_mult: float = 1.2, max_age_bars: int = 120) -> list[dict]:
    """Last opposite candle before an impulsive displacement move.

    Bearish OB = last up-candle before strong down-leg; bullish OB mirrored.
    Zone stays valid until price closes through it.
    """
    atr_pct = df["close"].pct_change().rolling(14).std()
    blocks: list[dict] = []
    n = len(df)
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    for i in range(20, n - 1):
        body = abs(c[i] - o[i])
        avg_body = np.nanmean(np.abs(c[max(0, i - 20) : i] - o[max(0, i - 20) : i]))
        if avg_body == 0 or np.isnan(avg_body):
            continue
        if body < impulse_atr_mult * avg_body:
            continue
        direction = 1 if c[i] > o[i] else -1
        # find last opposite candle within 5 bars before impulse start
        for j in range(i - 1, max(i - 6, 0), -1):
            opp = c[j] < o[j] if direction == 1 else c[j] > o[j]
            if opp:
                zone_lo, zone_hi = min(o[j], c[j]), max(o[j], c[j])
                # invalidate if already fully traded through since
                recent_low = l[i + 1 :].min() if i + 1 < n else 1e18
                recent_high = h[i + 1 :].max() if i + 1 < n else -1e18
                mitigated = (
                    (direction == 1 and recent_low < zone_lo)
                    or (direction == -1 and recent_high > zone_hi)
                )
                age = n - i
                if not mitigated and age <= max_age_bars:
                    blocks.append(
                        {
                            "type": "bullish_ob" if direction == 1 else "bearish_ob",
                            "low": float(zone_lo),
                            "high": float(zone_hi),
                            "created_ts": str(df.index[j]),
                            "age_bars": int(age),
                        }
                    )
                break
    # keep freshest per side
    out = [b for b in blocks if b["type"] == "bullish_ob"][-3:] + [
        b for b in blocks if b["type"] == "bearish_ob"
    ][-3:]
    return out


def volume_profile(df: pd.DataFrame, bins: int = 24, value_area_pct: float = 0.70) -> dict:
    """Volume-by-price histogram with POC and value area high/low."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    vol = df["volume"].to_numpy()
    price = typical.to_numpy()
    hist, edges = np.histogram(price, bins=bins, weights=vol)
    centers = (edges[:-1] + edges[1:]) / 2
    order = np.argsort(hist)[::-1]
    poc_i = order[0]
    total = hist.sum()
    va = {poc_i}
    acc = hist[poc_i]
    k = 1
    while acc / total < value_area_pct and k < len(hist):
        lo_i = poc_i - k
        hi_i = poc_i + k
        take_lo = lo_i >= 0 and (lo_i not in va)
        take_hi = hi_i < len(hist) and (hi_i not in va)
        gain_lo = hist[lo_i] if take_lo else -1
        gain_hi = hist[hi_i] if take_hi else -1
        if gain_lo < 0 and gain_hi < 0:
            break
        if gain_hi >= gain_lo:
            va.add(hi_i)
            acc += gain_hi
        if take_lo and gain_lo >= 0:
            va.add(lo_i)
            acc += gain_lo
        k += 1
    vah = float(edges[max(va) + 1])
    val = float(edges[min(va)])
    return {
        "poc": float(centers[poc_i]),
        "vah": vah,
        "val": val,
        "bins": [
            {"price": float(centers[i]), "volume": float(hist[i]), "in_va": i in va}
            for i in range(len(hist))
        ],
    }


def key_levels(df: pd.DataFrame) -> dict:
    """Aggregate snapshot used by both bots and the dashboard."""
    pivots = swing_pivots(df)
    vp = volume_profile(df)
    return {
        "liquidity_zones": cluster_liquidity(pivots)[:8],
        "recent_pivots": pivots[-12:],
        "order_blocks": order_blocks(df),
        "volume_profile": {"poc": vp["poc"], "vah": vp["vah"], "val": vp["val"]},
        "profile_bins": vp["bins"],
    }
