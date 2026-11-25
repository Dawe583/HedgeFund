"""Turbo market tools — free, deterministic pre-trade filters.

Funding-rate extremes, open-interest shocks and volatility-regime gates.
All pure functions: never raise, never touch the network. The live values
(funding, OI) are passed in by the caller from the snapshot/intel feed;
when unavailable the tool abstains (returns ok=True) instead of blocking.
"""

from __future__ import annotations


def funding_gate(funding_rate: float | None, side: str) -> tuple[bool, str]:
    """Block longs when funding is extremely positive (crowded) and vice versa."""
    if funding_rate is None:
        return True, "funding n/a"
    # 0.05% per 8h ≈ very crowded; 0.1% = extreme
    if side == "long" and funding_rate > 0.001:
        return False, f"funding {funding_rate:.4f} too hot for long"
    if side == "short" and funding_rate < -0.001:
        return False, f"funding {funding_rate:.4f} too cold for short"
    return True, "funding ok"


def oi_gate(oi_change_pct: float | None) -> tuple[bool, str]:
    """Block entries on open-interest shocks (>8% in one interval = liquidation cascade risk)."""
    if oi_change_pct is None:
        return True, "OI n/a"
    if abs(oi_change_pct) > 8.0:
        return False, f"OI shock {oi_change_pct:+.1f}% — stand aside"
    return True, "OI ok"


def volatility_regime(atr_pct: float, tf: str = "1m") -> tuple[str, float]:
    """Classify volatility + return a size multiplier (calm→full, wild→half)."""
    bands = {"1m": (0.05, 0.4), "5m": (0.08, 0.6), "15m": (0.1, 0.9),
             "1h": (0.2, 1.5), "4h": (0.4, 2.5)}
    lo, hi = bands.get(tf, (0.05, 1.0))
    if atr_pct < lo:
        return "dead", 0.5
    if atr_pct > hi:
        return "wild", 0.5
    return "normal", 1.0


def opportunity_score(conf: float, vol_z: float, rr: float, regime: str) -> float:
    """0–100 ranked score so the scanner can sort concurrent setups."""
    base = conf * 60 + min(abs(vol_z) / 3.0, 1.0) * 25 + min(rr / 2.5, 1.0) * 15
    if regime != "normal":
        base *= 0.8
    return round(max(0.0, min(100.0, base)), 1)
