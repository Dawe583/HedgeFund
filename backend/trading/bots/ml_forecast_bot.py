"""F9 — ML return forecaster, declared in program-day2-plan's spirit and
registered here BEFORE the first sweep.

Mechanism hypothesis: the tape's short-horizon conditional structure is
visible to a gradient-boosted regression on the harness's own feature
frame — returns over multiple horizons, volatility, volume, regime and
cross-sectional state — when the model is trained strictly out-of-fold
(embargoed walk-forward, never random-split: leakage in time series ML is
the classic way these projects lie to themselves, and this program exists
to not lie).

The bot is the production-shaped artifact: at each bar it scores the
current feature row with the trained model and trades the predicted
sign when |prediction| exceeds a threshold proportional to the model's
measured noise. Training happens OFFLINE (trading/ml_forecast.py) into a
pickled artifact with its training metadata — the bot never fits at
runtime, so backtest and paper see exactly the same predictor, which is
the parity the whole design stands on.

Leakage discipline, stated here because it is the whole game:
  - features use only current/past bars (build_features is causal)
  - labels are forward returns — used ONLY in training, never at inference
  - train/test splits are walk-forward with an embargo gap of the label
    horizon, so no label window overlaps a training row's feature window
  - the swept artifact stores its training window; the kernel validation
    slices are disjoint by the program's own in/out-of-sample split
"""

from __future__ import annotations

import math

from trading.backtest.engine import Signal
from trading.bots.base import BaseStrategy


class MLForecast(BaseStrategy):
    name = "mlforecast"
    timeframe = "1h"

    def __init__(
        self,
        artifact: dict,
        entry_z: float = 1.0,   # predicted return must exceed entry_z x noise
        exit_z: float = 0.2,    # position closes when prediction collapses inside
        stop_atr: float = 3.0,
        tp_rr: float = 2.0,
    ) -> None:
        self.model = artifact["model"]
        self.features = artifact["features"]
        self.noise = float(artifact["noise"])  # out-of-fold RMSE of the forward return
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.stop_atr = stop_atr
        self.tp_rr = tp_rr

    def _predict(self, row) -> float | None:
        try:
            x = []
            for f in self.features:
                v = float(row[f]) if f in row else float("nan")
                if not math.isfinite(v):
                    return None
                x.append(v)
            return float(self.model.predict([x])[0])
        except Exception:
            return None

    def signal(self, i: int, df) -> Signal | None:
        try:
            row = df.iloc[i]
            pred = self._predict(row)
            if pred is None:
                return None
            z = pred / (self.noise + 1e-12)
            if abs(z) <= self.exit_z:
                return Signal(side="flat", confidence=0.6, stop_atr=self.stop_atr, tp_rr=self.tp_rr)
            if z >= self.entry_z:
                conf = min(0.9, 0.55 + 0.1 * z)
                return Signal(side="long", confidence=conf, stop_atr=self.stop_atr, tp_rr=self.tp_rr)
            if z <= -self.entry_z:
                conf = min(0.9, 0.55 + 0.1 * abs(z))
                return Signal(side="short", confidence=conf, stop_atr=self.stop_atr, tp_rr=self.tp_rr)
            return None
        except Exception:
            return None
