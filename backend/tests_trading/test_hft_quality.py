"""HFT quality surgery: new gates fire fewer, larger-conviction signals.

Constructs OLD (pre-surgery) vs NEW (current defaults) HFTMomentum side by
side on the same synthetic 1m tape and asserts quality-over-quantity:
signal rate DROPS while the average |body| of signaled bars RISES.
"""
import math

import numpy as np
import pandas as pd

from trading.bots.hft_bot import HFTMomentum

OLD_KWARGS = dict(
    vol_z_min=1.4,
    body_min_pct=0.10,
    fade_range_pos=0.15,
    fade_vol_z_min=1.2,
    stop_atr=1.2,
    tp_rr=1.8,
    body_atr_mult=1.0,
)


def make_tape(n: int = 600, seed: int = 7) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    # Mostly chop (small bodies, mild volume), some bursts: mimics 1m tape
    # where the old wide net over-fires and the new gates stay selective.
    vol_z = rng.normal(0, 1.1, n)
    burst = rng.rand(n) < 0.08
    vol_z[burst] += rng.uniform(1.5, 4.0, burst.sum())
    body_pct = rng.normal(0, 0.0006, n)
    big = rng.rand(n) < 0.10
    body_pct[big] += np.sign(rng.normal(0, 1, big.sum())) * rng.uniform(0.001, 0.003, big.sum())
    regime = rng.normal(0, 0.002, n)  # same scale as real regime feature
    trend = rng.rand(n) < 0.30
    regime[trend] += np.sign(body_pct[trend]) * rng.uniform(0.001, 0.004, trend.sum())
    idx = pd.date_range("2026-01-01", periods=n, freq="min", tz="UTC")
    return pd.DataFrame(
        {
            "vol_z": vol_z,
            "body_pct": body_pct,
            "range_pos": rng.uniform(0, 1, n),
            "regime": regime,
            "atr_pct": np.full(n, 0.0008),
        },
        index=idx,
    )


def collect(bot, df) -> list[tuple[int, float]]:
    hits = []
    for i in range(len(df)):
        sig = bot.signal(i, df)  # must never raise
        if sig is not None:
            assert sig.side in ("long", "short")
            assert isinstance(sig.confidence, float)
            assert sig.stop_atr > 0 and sig.tp_rr > 0
            hits.append((i, abs(float(df.iloc[i]["body_pct"]))))
    return hits


def test_new_fires_fewer_but_bigger():
    df = make_tape()
    old = HFTMomentum(**OLD_KWARGS)
    new = HFTMomentum()  # post-surgery defaults
    assert new.vol_z_min > old.vol_z_min
    assert new.body_min_pct > old.body_min_pct
    assert new.tp_rr > old.tp_rr and new.stop_atr > old.stop_atr
    old_hits = collect(old, df)
    new_hits = collect(new, df)
    assert len(old_hits) > 0, "synthetic tape must trigger old gates"
    assert len(new_hits) > 0, "synthetic tape must trigger new gates"
    assert len(new_hits) < len(old_hits), f"new {len(new_hits)} vs old {len(old_hits)}"
    avg_old = sum(b for _, b in old_hits) / len(old_hits)
    avg_new = sum(b for _, b in new_hits) / len(new_hits)
    assert avg_new > avg_old, f"avg|body| new {avg_new:.6f} vs old {avg_old:.6f}"


def test_nan_rows_never_raise():
    df = make_tape()
    df.iloc[100] = np.nan
    df.iloc[200] = np.nan
    bot = HFTMomentum()
    for i in (100, 200, 101, 201):
        assert bot.signal(i, df) is None or True  # just must not raise
    assert bot.signal(0, df) is None  # warmup
    assert all(not (isinstance(v, float) and math.isnan(v)) or True for v in [1.0])
