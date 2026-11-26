"""F1 — time-series momentum, the search's highest-prior family.

docs/research/program-2026-11-26.md §3: multi-week trend, lookbacks 2–12
weeks, vol-scaled. The mechanism hypothesis is literature-standard:
futures markets across asset classes exhibit continuation at weekly-to-
monthly horizons, and crypto's retail flow amplifies it. What this bot is
deliberately NOT: a re-parameterized catalog bot. The catalog strategies
enter pullbacks and breakouts at intraday horizons; this one holds the
direction momentum assigns and exits when momentum dies — the signal IS
the position.

The bot is STATELESS by design. A restart re-arms positions in the kernel
but cannot restore pure-strategy memory, so a stateful momentum bot would
reboot with amnesia and contradict its own position. Instead the bot emits
direction hysteresis as a pure function of the frame: enter-long whenever
momentum is strong, exit whenever momentum has died — and the harness
deduplicates against its own position state (`in_position` / `flat_noop`
outcomes are the honest tape of that deduplication, not noise to hide).

Every number in the signal path is causal by construction: computed from
rows <= i of a frame the harness truncates at the just-closed bar.
"""

import math

from trading.backtest.engine import Signal
from trading.bots.base import BaseStrategy


class TrendMomentum(BaseStrategy):
    name = "trendmom"
    timeframe = "4h"

    def __init__(
        self,
        lookback_bars: int = 504,  # 12 weeks of 4h bars — the slow end of the literature range
        entry_z: float = 0.5,  # momentum/vol ratio required to be long (mirror for short)
        exit_z: float = 0.0,  # exit when |z| falls below this in the held direction — hysteresis band [exit_z, entry_z)
        vol_floor_pct: float = 0.2,  # vol below this reads as a dead market, not a quiet one — no trades
        vol_ceiling_pct: float = 8.0,  # chaos filter, same role as the catalog's
        stop_atr: float = 4.0,  # wide — momentum positions are meant to survive noise
        tp_rr: float = 8.0,  # far enough to barely bind — momentum exits on momentum death. The harness brackets every entry and has no optional-TP path, so the honest choice is a TP that reads as a catastrophe profit-cap, not a target
        confidence: float = 0.7,  # constant, above the gate: sizing is upstream, conviction is not a signal here
    ):
        self.lookback_bars = lookback_bars
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.vol_floor_pct = vol_floor_pct
        self.vol_ceiling_pct = vol_ceiling_pct
        self.stop_atr = stop_atr
        self.tp_rr = tp_rr
        self.confidence = confidence

    def _mom_z(self, i: int, df) -> float | None:
        """Total return over the lookback normalized by realized vol —
        the dimensionless momentum strength the z-thresholds consume.
        Returns None whenever the inputs cannot honestly exist."""
        if i < self.lookback_bars + 1 or i >= len(df):
            return None
        close_now = float(df["close"].iloc[i])
        close_then = float(df["close"].iloc[i - self.lookback_bars])
        atr_pct = float(df["atr_pct"].iloc[i])
        if any(math.isnan(v) for v in (close_now, close_then, atr_pct)):
            return None
        if atr_pct <= 0 or close_then <= 0:
            return None
        total_ret = close_now / close_then - 1.0
        # the vol of the LOOKBACK, not the bar: per-bar vol scaled by the
        # square root of the window length — the diffusion scaling a random
        # walk would produce, so z measures departure from noise
        window_vol = atr_pct * math.sqrt(self.lookback_bars)
        if window_vol <= 0:
            return None
        return total_ret / window_vol

    def _vol_ok(self, i: int, df) -> bool:
        atr_pct = float(df["atr_pct"].iloc[i])
        if math.isnan(atr_pct):
            return False
        pct = atr_pct * 100
        return self.vol_floor_pct <= pct <= self.vol_ceiling_pct

    def signal(self, i: int, df) -> Signal | None:
        # Never raises: the paper loop calls signal() on every bar including
        # warmup. The harness contract means df is truncated at i — iloc[i]
        # is always the just-closed bar, never the future.
        try:
            if df is None or i >= len(df):
                return None
            z = self._mom_z(i, df)
            if z is None or not self._vol_ok(i, df):
                return None

            if z >= self.entry_z:
                return Signal(side="long", confidence=self.confidence, stop_atr=self.stop_atr, tp_rr=self.tp_rr)
            if z <= -self.entry_z:
                return Signal(side="short", confidence=self.confidence, stop_atr=self.stop_atr, tp_rr=self.tp_rr)
            if abs(z) < self.exit_z:
                # momentum dead — exit whatever the harness holds in either
                # direction; nothing held means a recorded flat_noop, which
                # is the honest cost of statelessness
                return Signal(side="flat", confidence=self.confidence)
            return None
        except Exception:
            return None
