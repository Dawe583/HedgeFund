"""F8 — regime-aware continuation. Declared in program-2026-11-26 BEFORE the
first parameter was swept:

    F7's entries gated by a fast regime measure (Kaufman efficiency ratio
    over a short window): continuation only when the tape is demonstrably
    trending.

The measurement chain that legitimizes the hypothesis: F7 validated
in-sample (6 survivors, mean Sharpe +1.92) and died out-of-sample in 13
months (−0.31 across the board). The edge existed and stopped existing —
regime-dependence, not noise. If continuation only pays in trending tapes,
a fast regime filter should capture the difference IN-SAMPLE: the gate is
the hypothesis, and it is tested on the same in-sample window where F7
measured +1.92 unfiltered.

The gate is Kaufman's efficiency ratio over a short window — the same
measure F5 used at a long window for mean reversion, here fast because
continuation entries are fast: ER = |net displacement| / path length, 0
for a pure random walk, 1 for a straight trend. Entries pass only when
ER >= regime_min; exits are F7's own (dev_z collapse, stop, tp, timeout)
— the gate filters entries, never manages positions, because a position
already taken lives in the tape it was born into.
"""

from __future__ import annotations

import math

from trading.backtest.engine import Signal
from trading.bots.base import BaseStrategy


class RegimeContinuation(BaseStrategy):
    name = "regimecont"
    timeframe = "1h"

    def __init__(
        self,
        dev_lookback: int = 24,
        entry_dev: float = 1.5,
        exit_dev: float = 0.3,
        stop_atr: float = 3.0,
        tp_rr: float = 2.0,
        regime_lookback: int = 24,   # bars in the efficiency-ratio window — fast by design
        regime_min: float = 0.3,     # ER floor for entries: below this the tape is noise
        confidence: float = 0.7,
    ):
        self.dev_lookback = dev_lookback
        self.entry_dev = entry_dev
        self.exit_dev = exit_dev
        self.stop_atr = stop_atr
        self.tp_rr = tp_rr
        self.regime_lookback = regime_lookback
        self.regime_min = regime_min
        self.confidence = confidence

    def _measures(self, i: int, df) -> tuple[float, float] | None:
        """(deviation z in ATR units, efficiency ratio) or None whenever the
        inputs cannot honestly exist: insufficient history, dead volatility."""
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
        if atr_abs <= 0:
            return None
        dev_z = (close_now - mean) / atr_abs
        reg = closes[i - self.regime_lookback + 1: i + 1]
        if len(reg) < 8:
            return None
        net = abs(float(reg[-1]) - float(reg[0]))
        import numpy as np
        path = float(np.abs(np.diff(reg.astype(float))).sum())
        er = net / path if math.isfinite(path) and path > 0 else 0.0
        return dev_z, er

    def signal(self, i: int, df) -> Signal | None:
        try:
            measures = self._measures(i, df)
            if measures is None:
                return None
            dev_z, er = measures

            # exits are F7's own — unconditional, the gate filters entries only
            if abs(dev_z) <= self.exit_dev:
                return Signal(side="flat", confidence=self.confidence, stop_atr=self.stop_atr, tp_rr=self.tp_rr)

            # the gate: no trend evidence, no continuation — this IS the family
            if er < self.regime_min:
                return None

            if dev_z >= self.entry_dev:
                return Signal(side="long", confidence=self.confidence, stop_atr=self.stop_atr, tp_rr=self.tp_rr)
            if dev_z <= -self.entry_dev:
                return Signal(side="short", confidence=self.confidence, stop_atr=self.stop_atr, tp_rr=self.tp_rr)
            return None
        except Exception:
            return None
