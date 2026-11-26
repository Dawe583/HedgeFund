"""F12 — rolling-regime ML bot: reads the precomputed causal prediction
column and trades it through the kernel unchanged. The bot itself is
deliberately trivial — every interesting decision (window, cadence,
embargo) lives in the precompute, because a decision the backtest cannot
see is a decision that cannot be validated. Declared in program-2026-11-26
as F12 before the first sweep."""

from __future__ import annotations

import math

from trading.backtest.engine import Signal
from trading.bots.base import BaseStrategy


class MLRolling(BaseStrategy):
    name = "mlrolling"
    timeframe = "1h"

    # bound per candidate by the sweep worker
    roll_window: int = 2000
    roll_cadence: int = 24
    roll_horizon: int = 6
    roll_research_db: str | None = None

    def __init__(self, entry_z: float = 1.0, exit_z: float = 0.5, stop_atr: float = 3.0, tp_rr: float = 2.0) -> None:
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.stop_atr = stop_atr
        self.tp_rr = tp_rr

    def inject_frame(self, df, symbol: str):
        """Causal injection of the rolling predictions: expanding z-score,
        never centered — the same discipline as the alpha adapter, the same
        honesty argument. `_ml_pred` is the raw forward-return prediction,
        `_ml_pred_z` its expanding z-score."""
        from trading.ml_rolling import rolling_predictions_cached

        preds = rolling_predictions_cached(
            df, symbol, self.timeframe,
            horizon=self.roll_horizon, window=self.roll_window, cadence=self.roll_cadence,
        )
        out = df.copy()
        z = preds.copy()
        mean = preds.expanding(min_periods=200).mean()
        std = preds.expanding(min_periods=200).std()
        zscore = (preds - mean) / (std + 1e-12)
        out["_ml_pred"] = preds
        out["_ml_pred_z"] = zscore
        return out

    def signal(self, i: int, df) -> Signal | None:
        try:
            row = df.iloc[i]
            z = row.get("_ml_pred_z")
            if z is None or not math.isfinite(float(z)):
                return None
            z = float(z)
            if z >= self.entry_z:
                return Signal(side="long", confidence=min(0.9, 0.55 + 0.05 * z), stop_atr=self.stop_atr, tp_rr=self.tp_rr)
            if z <= -self.entry_z:
                return Signal(side="short", confidence=min(0.9, 0.55 + 0.05 * abs(z)), stop_atr=self.stop_atr, tp_rr=self.tp_rr)
            if abs(z) <= self.exit_z:
                return Signal(side="flat", confidence=0.6, stop_atr=self.stop_atr, tp_rr=self.tp_rr)
            return None
        except Exception:
            return None
