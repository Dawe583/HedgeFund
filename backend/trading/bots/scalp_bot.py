"""SCALP-BOT — higher-timeframe trend strategy, confidence-gated.

Horizon: holds hours–weeks. Trades rarely; only when trend regime,
pullback location and volatility align. Confidence maps to signal strength
and later to position sizing (0.25x Kelly cap upstream).
"""

import math

from trading.backtest.engine import Signal
from trading.bots.base import BaseStrategy


class ScalpTrend(BaseStrategy):
    name = "scalp"
    timeframe = "4h"

    def __init__(
        self,
        # Quality-tuned 2026-09-09 (walk-forward verdict: scalp 1h ~0.73
        # trades/day, 1/4 folds PF>1 -> accept ~1 quality trade/day,
        # optimize winrate/PF not frequency):
        # - regime_min 1.2->1.5: only strong trends (fold 2 PF>1 came
        #   from strong-regime bars; weak trends drive WR 11-39%).
        # - rsi 74/26->70/30: demand room before RSI extreme so we stop
        #   chasing topped/bottomed extensions.
        # - pullback_band 1.5->1.0: only deep pullbacks near EMA-fast;
        #   extended entries hurt PF.
        # - vol_ceiling 6.0->4.0: skip explosive regimes whose stop-outs
        #   dwarf avg wins (report: avg loss >> avg win).
        # stop/tp unchanged (2.2 / 2.0).
        regime_min: float = 1.5,  # trend strength in ATR units
        rsi_long_max: float = 70.0,
        rsi_short_min: float = 30.0,
        pullback_band: float = 1.0,
        vol_ceiling_pct: float = 4.0,
        stop_atr: float = 2.2,
        tp_rr: float = 2.0,
    ):
        self.regime_min = regime_min
        self.rsi_long_max = rsi_long_max
        self.rsi_short_min = rsi_short_min
        self.pullback_band = pullback_band
        self.vol_ceiling_pct = vol_ceiling_pct
        self.stop_atr = stop_atr
        self.tp_rr = tp_rr

    def signal(self, i: int, df) -> Signal | None:
        # Never raises: bounds/NaN guards keep Signal API total (paper loop
        # calls signal() on every bar including warmup/short frames).
        try:
            if df is None or i < 96 or i >= len(df):
                return None
            row = df.iloc[i]
            vals = [row["trend_strength"], row["rsi"], row["atr_pct"], row["regime"]]
            if any(isinstance(v, float) and math.isnan(v) for v in vals):
                return None

            atr_pct = float(row["atr_pct"])
            if math.isnan(atr_pct) or atr_pct <= 0:
                return None
            if atr_pct * 100 > self.vol_ceiling_pct:
                return None  # chaos filter — skip explosive regimes

            close, fast = float(row["close"]), float(row["ema_fast"])
            if math.isnan(close) or math.isnan(fast):
                return None
            dist_atr = abs(close - fast) / max(atr_pct * close, 1e-9)

            ts = float(row["trend_strength"])
            long_setup = (
                ts >= self.regime_min
                and row["rsi"] <= self.rsi_long_max
                and dist_atr <= self.pullback_band
            )
            short_setup = (
                ts <= -self.regime_min
                and row["rsi"] >= self.rsi_short_min
                and dist_atr <= self.pullback_band
            )

            if not (long_setup or short_setup):
                return None

            # confidence: stronger regime + calmer vol + room before RSI extreme => higher p
            strength = min(1.0, abs(ts) / 3.0)
            calm = max(0.0, 1.0 - (atr_pct * 100) / self.vol_ceiling_pct)
            room = (
                (self.rsi_long_max - row["rsi"]) / 24.0
                if long_setup
                else (row["rsi"] - self.rsi_short_min) / 24.0
            )
            conf = 0.55 + 0.30 * strength + 0.10 * calm + 0.05 * max(0.0, min(room, 1.0))
            conf = round(min(conf, 0.95), 3)
            side = "long" if long_setup else "short"
            return Signal(side=side, confidence=conf, stop_atr=self.stop_atr, tp_rr=self.tp_rr)
        except Exception:
            return None
