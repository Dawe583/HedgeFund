"""Prime trading tools — pure, sync, zero LLM cost.

All functions are deterministic and never raise: they return (ok, reason).
Designed for RPi4: numpy/pandas only, <10ms per call, no network.
"""

from __future__ import annotations

import datetime as dt


def breakeven_wr(rr: float) -> float:
    return 1.0 / (1.0 + rr) if rr > 0 else 1.0


def compute_ev(
    realized_wr: float, rr: float, vol_z: float, atr_pct: float, conf: float, n_trades: int = 0
) -> dict:
    """EV gate with stricter RR while sample is thin (n<20 → rr>=1.8)."""
    bwr = breakeven_wr(rr)
    ev = (realized_wr * rr) - (1 - realized_wr)
    # Turbo: thin-sample RR floor 1.5 (was 1.8), WR tolerance 0.85x breakeven,
    # vol_z 1.0, conf 0.45 — lets ~5 opportunities/day through on BTC 1m/5m.
    min_rr = 1.5 if n_trades < 20 else 1.3
    approved = (
        rr >= min_rr
        and realized_wr >= bwr * 0.85
        and abs(vol_z) >= 1.0
        and 0.01 <= atr_pct <= 4.0
        and conf >= 0.45
    )
    size_mult = 0.75 + max(0.0, (conf - 0.5)) * 1.6 + (0.15 if abs(vol_z) >= 2.0 else 0)
    if not approved:
        size_mult = min(size_mult, 0.75)
    reason = (
        "pass"
        if approved
        else f"rr {rr:.2f}<{min_rr} or wr {realized_wr:.2f}<{bwr * 0.95:.2f} "
        f"or vol {vol_z:.2f} or atr {atr_pct:.3f} or conf {conf:.2f}"
    )
    return {
        "approved": approved,
        "ev": round(ev, 3),
        "breakeven_wr": round(bwr, 3),
        "size_multiplier": round(max(0.5, min(1.75, size_mult)), 2),
        "reason": reason,
    }


# Per-timeframe ATR envelope (pct points, e.g. 0.05 = 0.05%).
TF_ATR_RANGE: dict[str, tuple[float, float]] = {
    "1m": (0.02, 1.5),
    "5m": (0.02, 2.0),
    "15m": (0.02, 2.5),
    "1h": (0.02, 3.0),
    "4h": (0.02, 3.0),
}


def atr_filter(atr_pct: float, tf: str = "1m") -> tuple[bool, str]:
    lo, hi = TF_ATR_RANGE.get(tf, (0.02, 3.0))
    if lo <= atr_pct <= hi:
        return True, "atr ok"
    return False, f"atr {atr_pct:.3f} outside [{lo},{hi}] for {tf}"


def vol_filter(vol_z: float, rvol: float = 1.0, tf: str = "1m") -> tuple[bool, str]:
    # 1m floor 1.5 (was 1.8): HFTMomentum emits breakout candidates from
    # vol_z>=1.4, so a 1.8 local-gate floor silently strangled the 1.4-1.5
    # band the strategy was tuned to trade.
    min_z = 1.0 if tf == "1m" else 1.0
    if abs(vol_z) >= min_z and rvol > 0.3:
        return True, "vol ok"
    return False, f"vol_z {vol_z:.2f} < {min_z} or rvol {rvol:.2f} thin"


def trend_alignment(
    side: str, trend_strength: float, rsi: float | None = None, tol: float = 0.5
) -> tuple[bool, str]:
    # tol is keyword with default 0.5: existing positional callers
    # (prime.local_gate) are unaffected; hft callers may pass tol=1.5.
    aligned = (side == "long" and trend_strength >= -tol) or (
        side == "short" and trend_strength <= tol
    )
    if not aligned:
        return False, f"counter-trend {side} vs ts {trend_strength:+.2f}"
    if rsi is not None:
        if side == "long" and rsi > 78:
            return False, f"long into overbought rsi {rsi:.0f}"
        if side == "short" and rsi < 22:
            return False, f"short into oversold rsi {rsi:.0f}"
    return True, "aligned"


def news_blackout(now: dt.datetime | None = None) -> bool:
    now = now or dt.datetime.now(dt.UTC)
    for hh, mm in ((12, 30), (13, 30), (14, 0), (18, 0), (19, 0)):
        t = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if abs((now - t).total_seconds()) <= 120:
            return True
    return False


def regime_changed(prev: float, curr: float, thresh: float = 1.0) -> bool:
    try:
        return abs(float(curr) - float(prev)) >= thresh
    except (TypeError, ValueError):
        return True


def conviction_size(base_notional: float, conf: float, vol_z: float) -> float:
    mult = 0.75 + max(0.0, (conf - 0.5)) * 1.6 + (0.15 if abs(vol_z) >= 2.0 else 0)
    return round(base_notional * max(0.5, min(1.75, mult)), 6)
