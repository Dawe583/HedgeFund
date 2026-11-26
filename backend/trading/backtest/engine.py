"""Lightweight event-driven backtest engine shared by all bot strategies.

Conventions (anti-lookahead):
- a signal generated on bar i-1 fills at the OPEN of bar i
- intrabar SL/TP resolved from high/low; when both are touched in one bar,
  the STOP is assumed to fill first (conservative)
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from trading.config import get_settings


@dataclass(frozen=True)
class Signal:
    side: str  # "long" | "short" | "flat"
    confidence: float = 0.5
    stop_atr: float = 2.0
    tp_rr: float = 1.5  # take-profit as reward:risk multiple of the stop distance


MAX_APPROVED_LEVERAGE = 25.0  # absolute ceiling, legacy leverage_max bound — design pins no number, see BTConfig.leverage

@dataclass
class BTConfig:
    fee_pct: float = field(default_factory=lambda: get_settings().taker_fee_pct)
    slippage_bps: float = field(default_factory=lambda: get_settings().slippage_bps)
    initial_equity: float = field(default_factory=lambda: get_settings().paper_equity_start)
    risk_per_trade: float = field(default_factory=lambda: get_settings().risk_per_trade_risk_pct)
    confidence_min: float = 0.55
    max_bars_in_trade: int | None = None
    # Per-strategy APPROVED leverage — a mandate property (design §2/§10):
    # constant per strategy config, never a function of conviction. It scales
    # the risk-budget qty linearly; the exposure caps below are what make a
    # large approved value survivable. Default 1.0 (unlevered risk sizing);
    # ceiling 25x because the design pins no numeric max and 25 was the
    # legacy bound — anything above it was never approved for anyone.
    leverage: float = 1.0
    # Exposure caps, HARD: an entry that would breach either cap is vetoed
    # and the veto recorded — never resized into compliance, never silently
    # skipped. Values are notional/equity ratios. The defaults are calibrated
    # against the unlevered baseline, not the legacy 0.6 margin number:
    # risk_per_trade 2% over a 1×ATR stop on 0.5% bars implies ~4× equity
    # notional at leverage 1 — a cap below that would veto the unlevered
    # baseline itself and make the caps the sizing, which they are not. Caps
    # exist to refuse the extremes (tight stops, high approved leverage).
    max_symbol_exposure: float = 5.0
    max_gross_exposure: float = 8.0
    # Layer-0 hard rails (design §6, trading/rails.py) — per-strategy
    # configuration, evaluated in the harness BEFORE sizing. The 12% drawdown
    # kill-switch and the 5% daily loss limit default from settings; the
    # loss-streak cooldown constants live in risk_guard.py, one definition
    # for both storage backends. flatten_on_kill is honestly vacuous in the
    # harness's realized-only accounting — see rails.py's module docstring.
    killswitch_dd_pct: float = field(default_factory=lambda: get_settings().risk_killswitch_dd_pct)
    daily_loss_pct: float = field(default_factory=lambda: get_settings().risk_max_daily_loss_pct)
    loss_streak_max: int = 3
    cooldown_hours: float = 4.0
    flatten_on_kill: bool = False

    def __post_init__(self):
        if not (self.leverage > 0):
            raise ValueError(f"leverage must be positive, got {self.leverage}")
        if self.leverage > MAX_APPROVED_LEVERAGE:
            raise ValueError(f"leverage {self.leverage} exceeds approved ceiling {MAX_APPROVED_LEVERAGE}")
        if not (self.max_symbol_exposure > 0) or not (self.max_gross_exposure > 0):
            raise ValueError("exposure caps must be positive")
        if self.max_symbol_exposure > self.max_gross_exposure:
            raise ValueError("symbol cap above gross cap is never satisfiable netting")


@dataclass
class BTResult:
    trades: list[dict]
    equity: pd.Series
    metrics: dict


BarsPerYear = {"1m": 525_600, "5m": 105_120, "15m": 35_040, "1h": 8_760, "4h": 2_190, "1d": 365}


def _metrics(trades: list[dict], equity: pd.Series, bars_per_year: int) -> dict:
    if equity.empty:
        return {}
    rets = equity.pct_change().dropna()
    years = len(equity) / bars_per_year
    sharpe = 0.0
    if rets.std() > 0 and years > 0:
        sharpe = float(rets.mean() / rets.std() * math.sqrt(bars_per_year))
    peak = equity.cummax()
    dd = (equity - peak) / peak
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    losses = [t["pnl"] for t in trades if t["pnl"] <= 0]
    gross_w, gross_l = sum(wins), abs(sum(losses))
    pf = gross_w / gross_l if gross_l > 0 else float("inf") if gross_w > 0 else 0.0
    wr = len(wins) / len(trades) if trades else 0.0
    return {
        "trades_n": len(trades),
        "win_rate": round(wr, 4),
        "profit_factor": round(pf, 3),
        "sharpe": round(sharpe, 3),
        "max_dd_pct": round(float(dd.min()) * 100, 3),
        "total_return_pct": round(float(equity.iloc[-1] / equity.iloc[0] - 1) * 100, 3),
        "avg_win": round(sum(wins) / len(wins), 2) if wins else 0.0,
        "avg_loss": round(-sum(losses) / len(losses), 2) if losses else 0.0,
    }


def run_backtest(
    df: pd.DataFrame,
    strategy,
    cfg: BTConfig | None = None,
    timeframe: str = "1h",
) -> BTResult:
    """`strategy.signal(i, df)` -> Signal | None, called once per closed bar."""
    cfg = cfg or BTConfig()
    cols = ["open", "high", "low", "close"]
    o, h, l, c = (df[k].to_numpy() for k in cols)
    atr_arr = df["atr_pct"].to_numpy() * c  # absolute ATR
    n = len(df)

    fee = cfg.fee_pct / 100
    slip = cfg.slippage_bps / 10_000

    equity = float(cfg.initial_equity)
    eq_curve = []
    trades: list[dict] = []

    pos_side: str | None = None
    entry_px = qty = stop = tp = 0.0
    entry_i = -1
    conf = 0.0

    def _close(price: float, ts_i: int, reason: str):
        nonlocal equity, pos_side, entry_px, qty, stop, tp, entry_i, conf
        exit_fill = price * (1 - slip) if pos_side == "long" else price * (1 + slip)
        gross = (exit_fill - entry_px) * qty * (1 if pos_side == "long" else -1)
        fees = (entry_px + exit_fill) * qty * fee
        pnl = gross - fees
        equity += pnl
        trades.append(
            {
                "side": pos_side,
                "qty": qty,
                "entry_price": entry_px,
                "exit_price": exit_fill,
                "entry_time": df.index[entry_i],
                "exit_time": df.index[ts_i],
                "pnl": pnl,
                "fees": fees,
                "confidence": conf,
                "bars_held": ts_i - entry_i,
                "reason": reason,
            }
        )
        pos_side = None

    for i in range(n):
        # --- manage open position first (uses current bar's range) ---
        if pos_side is not None:
            if pos_side == "long":
                hit_sl, hit_tp = l[i] <= stop, h[i] >= tp
            else:
                hit_sl, hit_tp = h[i] >= stop, l[i] <= tp
            if hit_sl:  # conservative: stop first
                _close(stop, i, "stop")
            elif hit_tp:
                _close(tp, i, "take_profit")
            elif cfg.max_bars_in_trade and i - entry_i >= cfg.max_bars_in_trade:
                _close(c[i], i, "timeout")

        # --- resolve pending signal from previous bar at this bar's open ---
        sig = strategy.signal(i - 1, df) if i >= 1 else None
        if sig is not None and sig.side == "flat" and pos_side is not None:
            _close(o[i], i, "signal_exit")

        if (
            sig is not None
            and sig.side in ("long", "short")
            and pos_side is None
            and sig.confidence >= cfg.confidence_min
            and not math.isnan(atr_arr[i])
            and atr_arr[i] > 0
        ):
            stop_dist = sig.stop_atr * atr_arr[i]
            # same three sizing stages as the kernel harness: risk budget,
            # approved leverage as a constant multiplier, hard exposure caps.
            # Confidence stays a GATE, never a size multiplier.
            risk_amount = equity * cfg.risk_per_trade
            qty_local = cfg.leverage * risk_amount / stop_dist
            notional = qty_local * o[i]
            if equity <= 0 or notional > equity * cfg.max_symbol_exposure or notional > equity * cfg.max_gross_exposure:
                pass  # exposure-cap veto — caps are hard, never a resize
            else:
                fill = o[i] * (1 + slip) if sig.side == "long" else o[i] * (1 - slip)
                pos_side = sig.side
                entry_px = fill
                qty = qty_local
                entry_i = i
                conf = sig.confidence
                if sig.side == "long":
                    stop, tp = fill - stop_dist, fill + stop_dist * sig.tp_rr
                else:
                    stop, tp = fill + stop_dist, fill - stop_dist * sig.tp_rr

        eq_curve.append(equity)

    eq = pd.Series(eq_curve, index=df.index, name="equity")
    return BTResult(trades, eq, _metrics(trades, eq, BarsPerYear.get(timeframe, 8_760)))


def walk_forward(
    df: pd.DataFrame,
    strategy_factory: Callable[[], object],
    n_folds: int = 4,
    cfg: BTConfig | None = None,
    timeframe: str = "1h",
) -> list[dict]:
    """Sequential OOS evaluation: fold k is tested strictly after fold k-1."""
    folds = []
    size = len(df) // (n_folds + 1)
    for k in range(n_folds):
        test_start = size * (k + 1)
        test_end = size * (k + 2)
        window = df.iloc[max(0, test_start - 500) : test_end]  # 500-bar warmup carried in
        res = run_backtest(window, strategy_factory(), cfg, timeframe)
        folds.append(
            {
                "fold": k,
                "start": str(df.index[test_start]),
                "end": str(df.index[min(test_end, len(df)) - 1]),
                **res.metrics,
            }
        )
    return folds
