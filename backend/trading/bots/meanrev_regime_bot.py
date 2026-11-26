"""F5 — mean reversion at regime scale. The filter is the hypothesis.

docs/research/program-2026-11-26.md §3: fade multi-bar overextension in
RANGING regimes only. The mechanism: mean reversion harvests noise in
range-bound tapes and gets run over in trending ones — the family's edge,
if it exists, lives in the regime classification, not in the fade. The
catalog MeanRev (p 0.011 cell) hints ordering information exists in the
family; it has NO regime filter, which is exactly what F5 adds. F1's
ledger is the warning: at 4h, ordering information exists but volatility
drowns it; mean reversion's horizon is bars-to-days, where the sample
size problem inverts — trades are frequent by construction.

Stateless by the same contract as TrendMomentum: restart-rearm cannot
restore pure-strategy memory, so everything is a function of the frame.
The harness owns position existence — `in_position`/`flat_noop` outcomes
deduplicate — and the strategy only ever says what the tape says now.
"""

import math

import numpy as np

from trading.backtest.engine import Signal
from trading.bots.base import BaseStrategy


class MeanRevRegime(BaseStrategy):
    name = "meanrevregime"
    timeframe = "1h"

    def __init__(
        self,
        dev_lookback: int = 48,  # bars for the mean being reverted to — 2 days at 1h
        entry_dev: float = 2.0,  # overextension in ATR units required to fade
        regime_max: float = 0.5,  # |trend z| above this: trending regime, no fading
        regime_lookback: int = 168,  # one week at 1h — the regime horizon
        exit_dev: float = 0.3,  # reversion done when |dev| falls below this
        stop_atr: float = 2.5,  # tight — a fade that keeps extending is wrong, not unlucky
        tp_rr: float = 1.5,  # mean reversion takes quick profits; the trend families hold
        confidence: float = 0.7,
    ):
        self.dev_lookback = dev_lookback
        self.entry_dev = entry_dev
        self.regime_max = regime_max
        self.regime_lookback = regime_lookback
        self.exit_dev = exit_dev
        self.stop_atr = stop_atr
        self.tp_rr = tp_rr
        self.confidence = confidence

    def _measures(self, i: int, df) -> tuple[float, float, float] | None:
        """(deviation z, regime z, atr absolute) or None whenever the inputs
        cannot honestly exist: insufficient history, dead volatility, NaNs.
        dev z — close's distance from its rolling mean in ATR units.
        regime — Kaufman efficiency ratio: net displacement over path
        length; random walk reads ~0 (ranging by construction), trend ~1."""
        need = max(self.dev_lookback, self.regime_lookback) + 1
        if i < need or i >= len(df):
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
        dev_z = (close_now - mean) / atr_abs

        # regime: Kaufman efficiency ratio over the regime horizon —
        # net displacement over path length. A pure random walk reads ~0
        # (ranging by construction, no drift exists), a straight trend ~1.
        # The first draft used diffusion-normalized total return, which is
        # mathematically wrong HERE: noise scaling is exactly what z-scores
        # are FOR, so a random walk reads |z|~0.8 and gets classified as
        # trending — the filter would ban the very tapes the family trades.
        seg = closes[i - self.regime_lookback: i + 1]
        net = abs(float(seg[-1]) - float(seg[0]))
        path = float(np.abs(np.diff(seg)).sum())
        if not np.isfinite(path) or path <= 0:
            return None
        regime_er = net / path
        return dev_z, regime_er, atr_abs

    def signal(self, i: int, df) -> Signal | None:
        try:
            measures = self._measures(i, df)
            if measures is None:
                return None
            dev_z, regime_er, _ = measures

            ranging = regime_er < self.regime_max
            if not ranging:
                return None

            # reversion complete — flat is the honest signal; the harness
            # closes what is open and records flat_noop for what is not
            if abs(dev_z) <= self.exit_dev:
                return Signal(side="flat", confidence=self.confidence, stop_atr=self.stop_atr, tp_rr=self.tp_rr)

            # fade the overextension
            if dev_z >= self.entry_dev:
                return Signal(side="short", confidence=self.confidence, stop_atr=self.stop_atr, tp_rr=self.tp_rr)
            if dev_z <= -self.entry_dev:
                return Signal(side="long", confidence=self.confidence, stop_atr=self.stop_atr, tp_rr=self.tp_rr)
            return None
        except Exception:
            return None
