"""MEANREV-BOT — RSI + EMA-stretch fade for ranging BTC intraday, 15m–1h horizon.

Loose turbo-desk gates (~5 trades/day): fade an RSI extreme or a
stretched distance from EMA-fast back toward the mean.
Pure pandas/numpy; signal() never raises.
"""

import math

from trading.backtest.engine import Signal
from trading.bots.base import BaseStrategy


class MeanRev(BaseStrategy):
    name = "meanrev"
    timeframe = "15m"

    def __init__(
        self,
        rsi_long: float = 45.0,
        rsi_short: float = 55.0,
        stretch_atr: float = 0.3,
        stop_atr: float = 1.6,
        tp_rr: float = 1.6,
        max_bars_in_trade: int = 96,
    ):
        self.rsi_long = rsi_long
        self.rsi_short = rsi_short
        self.stretch_atr = stretch_atr
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
            if df is None or i < 30 or i >= len(df):
                return None
            row = df.iloc[i]
            close = self._f(row, "close", float("nan"))
            if math.isnan(close):
                return None
            rsi = self._f(row, "rsi", 50.0)
            ema_fast = self._f(row, "ema_fast", float("nan"))
            if math.isnan(ema_fast):
                try:
                    ema_fast = float(df["close"].iloc[max(0, i - 21):i + 1].mean())
                except Exception:
                    ema_fast = close
            atr_dec = self._f(row, "atr_pct", 0.0004)
            if atr_dec <= 0 or math.isnan(atr_dec):
                atr_dec = 0.0004
            dist_atr = (close - ema_fast) / max(atr_dec * close, 1e-9)

            long_rsi = rsi <= self.rsi_long
            short_rsi = rsi >= self.rsi_short
            long_stretch = dist_atr <= -self.stretch_atr and rsi <= 50.0
            short_stretch = dist_atr >= self.stretch_atr and rsi >= 50.0

            # loose location: fade only when price is on the stretched side
            long_setup = (long_rsi or long_stretch) and close <= ema_fast + 0.1 * atr_dec * close
            short_setup = (short_rsi or short_stretch) and close >= ema_fast - 0.1 * atr_dec * close
            if not (long_setup or short_setup):
                return None

            if long_setup:
                rsi_depth = max(0.0, min((self.rsi_long - rsi + 10.0) / 25.0, 1.0)) if rsi <= self.rsi_long else 0.3
                stretch = max(0.0, min(abs(dist_atr) / 2.0, 1.0))
                conf = 0.52 + 0.20 * rsi_depth + 0.12 * stretch
                side = "long"
            else:
                rsi_depth = max(0.0, min((rsi - self.rsi_short + 10.0) / 25.0, 1.0)) if rsi >= self.rsi_short else 0.3
                stretch = max(0.0, min(abs(dist_atr) / 2.0, 1.0))
                conf = 0.52 + 0.20 * rsi_depth + 0.12 * stretch
                side = "short"
            conf = round(float(min(max(conf, 0.0), 0.9)), 3)
            return Signal(side=side, confidence=conf, stop_atr=self.stop_atr, tp_rr=self.tp_rr)
        except Exception:
            return None
