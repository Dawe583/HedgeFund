"""Alpha-signal bot — the adapter from a vendored cross-sectional alpha to
the kernel's per-symbol strategy contract.

The alphas in trading/factors/zoo are cross-sectional: their output at bar
t is a wide frame row, one value per universe member. This bot reads ONE
symbol's column of a precomputed alpha series — the series is injected
into the frame by the basket machinery's inject hook or aligned onto the
per-symbol frame by index — and trades the sign of the z-scored alpha:
positive alpha means the cross-section favors this asset, negative the
opposite. The direction convention follows each alpha's bench verdict:
alive alphas trade the sign as-is, reversed alphas trade inverted — the
bench measures which is which on OUR tape, so inversion is never a guess.

Leakage discipline: the alpha at bar t is computed from panel data up to
bar t by construction of the zoo's own operators (delta requires d >= 1,
negative shifts are absent — the vendored base enforces it). What this bot
must not do is peek at bar t's alpha before bar t closes — entries fill at
the next open through the kernel's unchanged execution semantics, which is
exactly the one-bar delay the whole design already measures.
"""

from __future__ import annotations

import math

import numpy as np

from trading.backtest.engine import Signal
from trading.bots.base import BaseStrategy


class AlphaSignal(BaseStrategy):
    name = "alphasig"
    timeframe = "4h"

    def __init__(
        self,
        entry_z: float = 1.5,
        exit_z: float = 0.5,
        invert: bool = False,
        alpha_col: str = "alpha_val",
        stop_atr: float = 3.0,
        tp_rr: float = 2.0,
    ) -> None:
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.invert = invert
        self.alpha_col = alpha_col
        self.stop_atr = stop_atr
        self.tp_rr = tp_rr

    def signal(self, i: int, df) -> Signal | None:
        try:
            row = df.iloc[i]
            v = row.get(self.alpha_col)
            z = row.get("alpha_z")
            if z is None and v is not None:
                # alpha_z is injected when available; raw fallback uses the
                # cross-sectionally-scaled value directly
                z = v
            if z is None or not math.isfinite(float(z)):
                return None
            z = float(z)
            if self.invert:
                z = -z
            if z >= self.entry_z:
                return Signal(side="long", confidence=min(0.9, 0.55 + 0.05 * z), stop_atr=self.stop_atr, tp_rr=self.tp_rr)
            if z <= -self.entry_z:
                return Signal(side="short", confidence=min(0.9, 0.55 + 0.05 * abs(z)), stop_atr=self.stop_atr, tp_rr=self.tp_rr)
            if abs(z) <= self.exit_z:
                return Signal(side="flat", confidence=0.6, stop_atr=self.stop_atr, tp_rr=self.tp_rr)
            return None
        except Exception:
            return None


def compute_alpha_panel(compute_fn, research_db: str, symbols: list[str], timeframe: str) -> "object":
    """Run one vendored alpha over the universe and return the wide frame —
    the input to per-symbol injection. Cross-sectional ranks inside the
    zoo's formulas mean the alpha is only meaningful computed on the whole
    universe at once, which is exactly what the bench measures."""
    from trading.alpha_bench import load_panel

    panel = load_panel(research_db, symbols, timeframe)
    return compute_fn(panel)


def align_alpha_series(alpha_wide, symbol: str) -> "object":
    """One symbol's column of the wide alpha frame as a series, z-scored
    against its own expanding history — expanding, never centered: the
    z-score at bar t uses only alpha values from bars <= t."""
    import pandas as pd

    s = alpha_wide[symbol].dropna()
    expanding_mean = s.expanding(min_periods=50).mean()
    expanding_std = s.expanding(min_periods=50).std()
    z = (s - expanding_mean) / (expanding_std + 1e-12)
    return pd.DataFrame({"alpha_val": s, "alpha_z": z})
