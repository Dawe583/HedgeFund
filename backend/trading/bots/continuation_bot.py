"""F7 — continuation at 1h. The F5 mirror, measurement-derived.

Declared in program-2026-11-26 §3 BEFORE any parameter was swept: F5's
ledger shows fading 1.5–2.5 ATR extensions loses gross (mean Sharpe −2.00
across 48/48 cells), so the inversion is the hypothesis — extensions
continue at the hourly horizon in crypto majors, unconditionally. The
family shares F5's deviation measure exactly; the mirror changes only the
direction of the trade and drops the regime filter, because F5's ledger
shows the filter changed nothing — continuation was unconditional there,
so conditioning is not where the edge would live here either.

The honest asymmetry a mirror cannot wave away: continuation entries ride
momentum INTO extension, so the stop placement that protected fades is
wrong-shaped here — a tight stop under an extension-buy is noise-food,
which is why the grid widens stops relative to F5 instead of copying them.
"""

import math

import numpy as np

from trading.backtest.engine import Signal
from trading.bots.base import BaseStrategy


class Continuation1h(BaseStrategy):
    name = "continuation1h"
    timeframe = "1h"

    def __init__(
        self,
        dev_lookback: int = 24,  # bars for the reference mean — 1 day at 1h
        entry_dev: float = 2.0,  # extension in ATR units required to ride
        exit_dev: float = 0.3,  # continuation over when |dev| falls back inside
        stop_atr: float = 3.0,  # wider than F5's — noise-food avoidance, see module docstring
        tp_rr: float = 2.0,
        confidence: float = 0.7,
    ):
        self.dev_lookback = dev_lookback
        self.entry_dev = entry_dev
        self.exit_dev = exit_dev
        self.stop_atr = stop_atr
        self.tp_rr = tp_rr
        self.confidence = confidence

    def _dev_z(self, i: int, df) -> float | None:
        """Close's distance from its rolling mean in ATR units, or None
        whenever the inputs cannot honestly exist."""
        if i < self.dev_lookback or i >= len(df):
            return None
        close_now = float(df["close"].iloc[i])
        atr_pct = float(df["atr_pct"].iloc[i])
        if any(math.isnan(v) for v in (close_now, atr_pct)) or atr_pct <= 0:
            return None
        closes = df["close"].values
        window = closes[i - self.dev_lookback + 1: i + 1]
        mean = float(window.mean())
        atr_abs = atr_pct * close_now  # atr_pct is already a fraction (atr/close), not percent —
        # the original /100 shrank every ATR 100x and inflated dev_z 100x, so F5/F7/F8
        # all measured thresholds ~100x tighter than declared (measured 2026-11-26:
        # |dev_z| >= 1.5 on 99% of OOS bars — impossible for honest ATR units)
        return (close_now - mean) / atr_abs

    def signal(self, i: int, df) -> Signal | None:
        try:
            dev_z = self._dev_z(i, df)
            if dev_z is None:
                return None

            if abs(dev_z) <= self.exit_dev:
                return Signal(side="flat", confidence=self.confidence, stop_atr=self.stop_atr, tp_rr=self.tp_rr)

            # ride the extension — the mirror of F5, nothing else
            if dev_z >= self.entry_dev:
                return Signal(side="long", confidence=self.confidence, stop_atr=self.stop_atr, tp_rr=self.tp_rr)
            if dev_z <= -self.entry_dev:
                return Signal(side="short", confidence=self.confidence, stop_atr=self.stop_atr, tp_rr=self.tp_rr)
            return None
        except Exception:
            return None
