"""HFT-BOT — crypto micro-momentum + mean-reversion, 1m–5m horizon.

Two sub-signals:
- breakout: volume spike + strong body in direction of short momentum,
  with regime-drift alignment (chop filter)
- fade: extreme wick rejection against flat regime (mean reversion)

Quality-over-quantity surgery (2026-09-09, see docs/TEAM/hft-surgery.md):
walk-forward verdict was PF 0.05-0.35 on all OOS folds, avg loss ($6.06)
dwarfing avg win ($3.83), and confidence gates non-binding (all signals
conf >= 0.59). So the fix is strategy-level: tighter entry gates (fewer,
larger-conviction signals) + wider stop / higher RR (avg win > avg loss).
Every default below carries a WHY comment. Signal API
(side/confidence/stop_atr/tp_rr) is unchanged; signal() never raises
(NaN rows return None).
"""

import math

from trading.backtest.engine import Signal
from trading.bots.base import BaseStrategy


class HFTMomentum(BaseStrategy):
    name = "hft"
    timeframe = "1m"

    def __init__(
        self,
        # WHY 1.4->2.2: on data/ci.db 1m, vol_z 1.4 sits ~88th pct (fires on
        # routine flow); 2.2 sits ~96th pct (true volume burst where 1m
        # momentum persists). Cuts churn trades.
        vol_z_min: float = 2.2,
        # WHY 0.10->0.16: |body| 0.10% admits the top ~12% of 1m bodies
        # (mean |body| ~0.036%); 0.16% admits the top ~4-5% — conviction
        # candles only.
        body_min_pct: float = 0.16,
        # WHY 0.15->0.08: close in the outer 15% of the bar range admits
        # mid-bar closes as "rejection"; outer 8% selects true pin-bar
        # wick rejection.
        fade_range_pos: float = 0.08,
        # WHY 1.2->2.0: vol_z 1.2 is ~85th pct (normal flow); fades need
        # capitulation volume, 2.0 ~ 95th pct.
        fade_vol_z_min: float = 2.0,
        # WHY 1.2->1.6: 1m noise + stop-first fills chopped tight stops
        # (OOS WR 19-41%); a wider stop survives microstructure noise.
        stop_atr: float = 1.6,
        # WHY 1.8->2.5: at RR 1.8, avg win $3.83 < avg loss $6.06 net of
        # 0.045% fees + slippage; RR 2.5 makes avg win > avg loss and drops
        # breakeven WR to 1/(1+2.5) = 28.6% (old OOS WR band 19-41%).
        tp_rr: float = 2.5,
        max_bars_in_trade: int = 45,  # unchanged: 1m horizon cap still fits
        # WHY 1.0->1.5: the OR-branch was the leak — body_atr >= 1.0 sits
        # ~70th pct, so small bodies in compressed ATR slipped through the
        # absolute floor; 1.5 sits ~93rd pct (expansion candles only).
        body_atr_mult: float = 1.5,
        # WHY new (replaces hardcoded 0.15): |regime| < 0.15 was NON-BINDING
        # (dataset max |regime| is 0.0137, so it passed everything); 0.002
        # sits ~75th pct of |regime| and selects genuinely flat spots.
        flat_regime_max: float = 0.002,
        # WHY new: breakout continuation needs drift; without alignment the
        # breakout arm bought into chop that the fade arm is built for.
        # 0.0015 sits ~65th pct of |regime|; side must match regime sign.
        breakout_regime_min: float = 0.0015,
    ):
        self.vol_z_min = vol_z_min
        self.body_min_pct = body_min_pct
        self.fade_range_pos = fade_range_pos
        self.fade_vol_z_min = fade_vol_z_min
        self.stop_atr = stop_atr
        self.tp_rr = tp_rr
        self.max_bars_in_trade = max_bars_in_trade
        self.body_atr_mult = body_atr_mult
        self.flat_regime_max = flat_regime_max
        self.breakout_regime_min = breakout_regime_min

    def signal(self, i: int, df) -> Signal | None:
        if i < 96:
            return None
        row = df.iloc[i]
        vals = [row["vol_z"], row["body_pct"], row["range_pos"], row["regime"], row["atr_pct"]]
        if any(isinstance(v, float) and math.isnan(v) for v in vals):
            return None

        body = float(row["body_pct"]) * 100  # candle body in %
        vol_z = float(row["vol_z"])
        regime = float(row["regime"])

        # --- breakout continuation: burst + conviction body + drift aligned ---
        atr_dec = float(row["atr_pct"])  # decimal, e.g. 0.0004 = 0.04%
        body_dec = float(row["body_pct"])  # decimal, same units as atr_pct
        body_atr = abs(body_dec) / max(atr_dec, 1e-9)
        body_ok = abs(body) >= self.body_min_pct or body_atr >= self.body_atr_mult
        if vol_z >= self.vol_z_min and body_ok:
            side = "long" if body > 0 else "short"
            # Chop filter: momentum needs drift behind it; flat-regime
            # breakouts are left to the fade arm.
            aligned = (regime >= self.breakout_regime_min and side == "long") or (
                regime <= -self.breakout_regime_min and side == "short"
            )
            if aligned:
                strength = min(1.0, (vol_z - self.vol_z_min) / 3.0)
                conf = round(min(0.55 + 0.25 * strength + min(abs(body) / 1.0, 0.15), 0.9), 3)
                return Signal(side=side, confidence=conf, stop_atr=self.stop_atr, tp_rr=self.tp_rr)
            return None

        # --- exhaustion fade: high-volume rejection wick against flat regime ---
        # close pinned at the LOW of its bar => buyers stepped in => bounce long
        # NOTE: tp_rr keeps full RR (>= quant floor 1.5); the wider stop
        # (x1.2 below) compensates instead of cutting RR.
        rng = float(row["range_pos"])
        flat_regime = abs(regime) < self.flat_regime_max
        reject_low = rng <= self.fade_range_pos
        reject_high = rng >= 1 - self.fade_range_pos
        if flat_regime and vol_z >= self.fade_vol_z_min and (reject_low or reject_high):
            side = "long" if reject_low else "short"
            depth = abs(rng - 0.5) * 2  # 1 = extreme rejection
            conf = round(min(0.58 + 0.10 * depth + min(vol_z / 10, 0.10), 0.85), 3)
            return Signal(
                side=side,
                confidence=conf,
                stop_atr=self.stop_atr * 1.2,
                tp_rr=self.tp_rr,
            )

        return None
