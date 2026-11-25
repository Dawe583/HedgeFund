"""BREAKOUT-BOT — Donchian + volume breakout for BTC intraday, 5m–15m horizon.

Loose turbo-desk gates (~5 trades/day): prior lookback high/low break
confirmed by a light volume z-score and a small ATR-normalized body.
Pure pandas/numpy; signal() never raises.
"""

import math

from trading.backtest.engine import Signal
from trading.bots.base import BaseStrategy


class BreakoutVol(BaseStrategy):
    name = "breakout"
    timeframe = "5m"

    def __init__(
        self,
        lookback: int = 20,
        vol_z_min: float = 0.8,
        body_min_pct: float = 0.01,
        body_atr_mult: float = 0.25,
        stop_atr: float = 1.5,
        tp_rr: float = 1.6,
        max_bars_in_trade: int = 96,
    ):
        self.lookback = lookback
        self.vol_z_min = vol_z_min
        self.body_min_pct = body_min_pct
        self.body_atr_mult = body_atr_mult
        self.stop_atr = stop_atr
        self.tp_rr = tp_rr
        self.max_bars_in_trade = max_bars_in_trade

    def _f(self, row, key, default: float) -> float:
        try:
            v = float(row[key])
        except Exception:
            return default
        if isinstance(v, float) and math.isnan(v):
            return default
        return v

    def signal(self, i: int, df) -> Signal | None:
        try:
            if df is None or i < self.lookback + 5 or i >= len(df):
                return None
            row = df.iloc[i]
            close = self._f(row, "close", float("nan"))
            if math.isnan(close):
                return None
            vol_z = self._f(row, "vol_z", 0.0)
            body_dec = self._f(row, "body_pct", 0.0)
            atr_dec = self._f(row, "atr_pct", 0.0004)
            if atr_dec <= 0 or math.isnan(atr_dec):
                atr_dec = 0.0004

            # prior Donchian channel from high/low (fallback to close)
            try:
                highs = df["high"].iloc[max(0, i - self.lookback):i].to_numpy(dtype=float)
                lows = df["low"].iloc[max(0, i - self.lookback):i].to_numpy(dtype=float)
                import numpy as np
                prior_high = float(np.nanmax(highs)) if len(highs) else close
                prior_low = float(np.nanmin(lows)) if len(lows) else close
            except Exception:
                prior_high, prior_low = close, close
            if math.isnan(prior_high) or math.isnan(prior_low):
                return None

            long_break = close > prior_high
            short_break = close < prior_low
            if not (long_break or short_break):
                return None

            # loose volume gate
            if vol_z < self.vol_z_min:
                return None

            # loose body confirmation: absolute floor OR ATR-normalized
            body_pct = abs(body_dec) * 100.0
            body_atr = abs(body_dec) / max(atr_dec, 1e-9)
            if not (body_pct >= self.body_min_pct or body_atr >= self.body_atr_mult):
                return None

            # direction must roughly agree with body (loose: allow flat body)
            tol = self.body_min_pct / 100.0 / 2.0
            if long_break and body_dec < -tol:
                return None
            if short_break and body_dec > tol:
                return None

            side = "long" if long_break else "short"
            ch_range = max(prior_high - prior_low, close * atr_dec)
            pen = min(abs(close - (prior_high if long_break else prior_low)) / max(ch_range, 1e-9), 1.0)
            vol_strength = min(max((vol_z - self.vol_z_min) / 3.0, 0.0), 1.0)
            conf = 0.52 + 0.20 * vol_strength + 0.10 * min(body_atr / 2.0, 1.0) + 0.05 * (1.0 - pen)
            conf = round(float(min(max(conf, 0.0), 0.9)), 3)
            return Signal(side=side, confidence=conf, stop_atr=self.stop_atr, tp_rr=self.tp_rr)
        except Exception:
            return None
