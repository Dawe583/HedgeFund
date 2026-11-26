"""F2 — funding-carry direction. Declared in program-2026-11-26 before the
machinery existed:

    at persistently positive funding longs pay shorts — direction follows
    the funding regime, entries deviation-timed; whether harvesting the
    transfer survives price movement is the hypothesis.

Mechanism: funding is a transfer between crowded and uncrowded sides. A
persistently positive rate means longs are the crowded side — they pay
~7-8%/yr (measured across 10 symbols x 1095d, same evening) AND crowded
positioning unwinds against them. The bot rides the uncrowded side:

    regime = mean of the last `lookback` settlement rates
    long when regime <= -threshold, short when regime >= +threshold
    optional deviation timing: enter only when price is stretched AGAINST
    the intended side (cheap entry into the carry — dev_z sign opposes
    the position direction by at least entry_dev ATRs)
    exit on regime flip (sign change past the opposite threshold) or
    time-stop at max_bars bars

Funding reaches the frame through the kernel join: `_funding_rate` is NaN
except at settlement bars (every 8h). The strategy reads only past events —
the visible frame ends at the signal bar, so no lookahead is possible by
construction.
"""

from __future__ import annotations

import math

from trading.backtest.engine import Signal
from trading.bots.base import BaseStrategy


class FundingCarry(BaseStrategy):
    name = "fundingcarry"
    timeframe = "1h"

    def __init__(
        self,
        lookback: int = 9,          # settlement events in the regime mean (9 = 3 days)
        threshold: float = 0.00005, # 0.005%/8h regime significance bar
        entry_dev: float = 0.0,     # ATRs of contrary stretch required (0 = none)
        max_bars: int = 72,         # time-stop: 72h = 9 settlement events
    ) -> None:
        self.lookback = lookback
        self.threshold = threshold
        self.entry_dev = entry_dev
        self.max_bars = max_bars

    def _regime(self, df) -> float | None:
        """Mean of the last `lookback` settlement rates visible so far, or
        None when fewer than 3 events exist — a regime needs evidence, and
        a single print is noise, never a regime."""
        if "_funding_rate" not in df.columns:
            return None
        rates = df["_funding_rate"].dropna()
        if len(rates) < 3:
            return None
        window = rates.iloc[-self.lookback:]
        return float(window.mean())

    def signal(self, i: int, df) -> Signal | None:
        try:
            regime = self._regime(df.iloc[: i + 1])
            if regime is None:
                return None
            row = df.iloc[i]
            close = float(row["close"])
            atr_pct = float(row["atr_pct"]) if "atr_pct" in row else float("nan")
            if not (math.isfinite(close) and close > 0):
                return None
            atr_abs = atr_pct * close if math.isfinite(atr_pct) and atr_pct > 0 else close * 0.01

            # deviation in ATR units from the rolling 24h mean — computed
            # internally because the feature frame has no dev_z column; the
            # funding bot is the only consumer and a feature for one consumer
            # is premature abstraction
            look = df["close"].iloc[max(0, i - 24): i + 1]
            dev_z = 0.0
            if len(look) >= 8 and atr_abs > 0:
                dev_z = (close - float(look.mean())) / atr_abs
            # wide protective stops: carry positions sit through noise — the
            # harvest accrues per settlement, not per tick. 4 ATR stop, no
            # take-profit: the exit is the regime, not a price target.
            # the harness vocabulary requires a numeric tp_rr; the honest
            # "no price target" is 12x the stop — unreachable in practice,
            # so exits stay regime/timeout exactly as declared
            stop_atr, tp_rr = 4.0, 12.0

            direction = 0
            if regime >= self.threshold:
                direction = -1  # positive funding: longs pay — be short
            elif regime <= -self.threshold:
                direction = +1  # negative funding: shorts pay — be long
            if direction == 0:
                return None

            # deviation timing: enter only when price is stretched against
            # the intended side — the carry is the same, the entry is cheaper
            if self.entry_dev > 0:
                if direction == -1 and dev_z < self.entry_dev:
                    return None  # short wants price stretched UP first
                if direction == +1 and dev_z > -self.entry_dev:
                    return None  # long wants price stretched DOWN first

            side = "short" if direction == -1 else "long"
            confidence = min(1.0, abs(regime) / (3 * self.threshold))
            return Signal(side=side, confidence=confidence, stop_atr=stop_atr, tp_rr=tp_rr)
        except Exception:
            return None
