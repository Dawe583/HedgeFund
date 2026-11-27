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


    alpha_compute = None      # class attribute: vendored compute fn, set per candidate
    alpha_symbols = None      # universe the alpha is computed over
    alpha_research_db = None  # data source — set by the candidate machinery

    def inject_frame(self, df, symbol: str):
        """Causal alpha injection for the per-symbol kernel path. Computes
        the alpha over the whole universe ONCE per worker, takes this
        symbol's column, z-scores it against expanding history (never
        centered — verified causality at 0.0 violation), and joins
        alpha_val/alpha_z onto the frame by timestamp."""
        if self.alpha_compute is None or self.alpha_symbols is None:
            return df
        wide = _alpha_wide_cached(self.alpha_compute, self.alpha_research_db, self.alpha_symbols, self.timeframe)
        if symbol not in wide.columns:
            return df
        z = align_alpha_series(wide, symbol)
        # timezone honesty: the kernel's windowing localizes frames to UTC
        # while the candle store and the alpha panel stay naive — align the
        # injected series to the frame's own tz, whatever it is, rather
        # than assuming either side
        if df.index.tz is not None and z.index.tz is None:
            z = z.copy()
            z.index = z.index.tz_localize(df.index.tz)
        elif df.index.tz is None and z.index.tz is not None:
            z = z.copy()
            z.index = z.index.tz_localize(None)
        out = df.copy()
        out = out.join(z, how="left")
        return out


def _alpha_wide_cached(compute_fn, research_db: str, symbols: list[str], timeframe: str):
    """Compute-once-read-many alpha panel, cached as a pickle beside the
    research data. Mutable module globals are banned by project rule; the
    file cache is the honest equivalent. The key is CONTENT-keyed: the
    digest covers the whole panel the alpha consumed, so re-ingested or
    repaired candles produce a new key rather than a stale hit — the old
    (module, symbols, timeframe) key fed pre-repair panels to live signals
    forever, which is exactly the F-8 failure. The panel must therefore be
    loaded before the lookup: the cache saves the alpha computation (the
    expensive part), not the candle read. Writing evicts same-alpha,
    same-universe predecessors — the pre-repair panels."""
    import hashlib
    import pickle
    from pathlib import Path

    from trading.cacheutil import artifact_file, panel_digest, write_artifact

    key = hashlib.sha256(
        (compute_fn.__module__ + "|".join(sorted(symbols)) + timeframe).encode()
    ).hexdigest()[:12]
    cache_dir = Path(research_db.replace("sqlite:///", "")).parent / "alpha_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{compute_fn.__module__.split('.')[-1]}-{timeframe}-{key}"

    from trading.alpha_bench import load_panel

    panel = load_panel(research_db, symbols, timeframe)
    digest = panel_digest(panel)
    path = artifact_file(cache_dir, stem, digest)
    if path.exists():
        with open(path, "rb") as fh:
            return pickle.load(fh)
    wide = compute_fn(panel)
    write_artifact(cache_dir, stem, digest, wide)
    return wide


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
