"""Hard risk rails — evaluated before every paper/live action."""

import datetime as dt

from sqlalchemy import select

from trading.config import Settings

# Hard cap on total open notional as a fraction of equity (cross-bot).
MAX_GROSS_EXPOSURE_PCT = 2.0


class RiskManager:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or Settings()

    def size_position(self, equity: float, confidence: float, stop_dist_pct: float) -> float:
        """Risk-based sizing scaled by calibrated confidence, capped by Kelly fraction."""
        base_risk = equity * self.s.risk_per_trade_risk_pct
        conf_scalar = max(0.5, min(confidence / 0.8, 1.25)) * self.s.kelly_fraction_cap / 0.25 * 0.5
        risk_amount = base_risk * conf_scalar
        notional = risk_amount / max(stop_dist_pct, 1e-6)
        cap = equity * self.s.risk_max_exposure_pct
        return round(min(notional, cap), 6)

    def daily_loss_breached(self, day_start_equity: float, equity_now: float) -> bool:
        if day_start_equity <= 0:
            return False
        return (equity_now - day_start_equity) / day_start_equity <= -self.s.risk_max_daily_loss_pct

    def kill_switch(self, peak_equity: float, equity_now: float) -> bool:
        if peak_equity <= 0:
            return False
        return (equity_now - peak_equity) / peak_equity <= -self.s.risk_killswitch_dd_pct

    @staticmethod
    def gross_exposure_ok(
        open_notional: float, equity: float, cap: float = MAX_GROSS_EXPOSURE_PCT
    ) -> bool:
        """Total open notional (plus any new entry) must stay within cap × equity."""
        if equity <= 0:
            return False
        return open_notional <= equity * cap

    @staticmethod
    def is_news_blackout(now: dt.datetime | None = None) -> bool:
        """Placeholder blackout around top-tier macro prints (FOMC/CPI/NFP at 12:30/13:30/14:00/18:00/19:00 UTC).

        Wired to a real calendar feed in F5.
        """
        now = now or dt.datetime.now(dt.UTC)
        for hh, mm in ((12, 30), (13, 30), (14, 0), (18, 0), (19, 0)):
            t = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if abs((now - t).total_seconds()) <= 120:
                return True
        return False


KILLSWITCH_ROW = "__killswitch"


def killswitch_state(session_factory) -> dict:
    """Read persisted kill-switch state (shared across API/worker processes)."""
    from trading.models import BotStatus

    session = session_factory()
    try:
        row = session.get(BotStatus, KILLSWITCH_ROW)
        return {"tripped": bool(row and row.running is False), "note": row.note if row else ""}
    finally:
        session.close()


def set_killswitch(session_factory, tripped: bool, note: str = "") -> dict:
    from trading.models import BotStatus

    session = session_factory()
    try:
        row = session.get(BotStatus, KILLSWITCH_ROW)
        if row is None:
            row = BotStatus(name=KILLSWITCH_ROW, running=True, mode="risk", note="")
            session.add(row)
        row.running = not tripped
        row.note = note or ("manual kill-switch " + ("ON" if tripped else "OFF"))
        session.commit()
        return {"tripped": tripped, "note": row.note}
    finally:
        session.close()


def reset_kill_state(session_factory, note: str = "") -> dict:
    """The deliberate operator un-kill (F-4 hole 2, 2026-11-27): clears the
    manual `__killswitch` row AND the auto-trip state the paper engine
    persists beside peak_equity. One helper for both because un-killing only
    the manual row would leave the automatic drawdown trip latched in the kv
    store — a restart would silently re-kill the desk, and 'I turned it off'
    would be a lie. The trip metadata (`kill_trip_meta`) is intentionally
    KEPT: it is the evidence of what the market did, not a state to erase —
    the reset clears the latch, never the record.

    kv keys: `kill_tripped` (the latch) and `kill_trip_meta` (ts and
    drawdown at the trip, written by the paper engine at the instant it
    fires). The validation kernel deliberately has no such persistence: a
    backtest is one measurement and starts fresh by design; paper is a
    continuous life, and restarting the process is not a risk reset.
    """
    from trading.models import set_state

    out = set_killswitch(session_factory, False, note or "operator reset — kill state cleared")
    session = session_factory()
    try:
        set_state(session, "kill_tripped", False)
        session.commit()
    finally:
        session.close()
    return {**out, "auto_trip_cleared": True}


def portfolio_equity(session, start: float, positions: list | None = None) -> float:
    """Equity = start + realized PnL + unrealized PnL of open positions.

    `positions` items are (side, qty, entry_price, mark_price) tuples or
    objects exposing those attrs; marks are computed by the caller (last
    close) so this stays pure.
    """
    from trading.models import Trade

    realized = sum(t.pnl for t in session.execute(select(Trade)).scalars())
    unrealized = 0.0
    for p in positions or []:
        side, qty, entry, mark = (
            (p.side, p.qty, p.entry_price, p.mark_price) if hasattr(p, "mark_price") else p
        )
        sign = 1 if side == "long" else -1
        unrealized += (mark - entry) * qty * sign
    return start + realized + unrealized


# --- pure volatility-scaled sizing (stdlib only, no DB) ---

def vol_scaled_size(equity, base_notional, atr_pct, target_atr) -> float:
    """Scale base notional by target/realised volatility. Pure, never raises.

    scale = target_atr / atr_pct, clamped to [0, 2.0]; result is
    base_notional * scale clamped to [0, equity]. Any invalid or
    non-positive input returns 0.0.
    """
    try:
        eq = float(equity)
        base = float(base_notional)
        cur = float(atr_pct)
        tgt = float(target_atr)
        if not (eq > 0) or not (base > 0) or not (cur > 0) or not (tgt > 0):
            return 0.0
        for v in (eq, base, cur, tgt):
            if v != v:  # NaN guard
                return 0.0
        scale = tgt / cur
        if scale != scale:  # NaN
            return 0.0
        scale = max(0.0, min(scale, 2.0))
        size = base * scale
        return max(0.0, min(size, eq))
    except Exception:
        return 0.0

# --- confidence-to-size mapping: quality over quantity (pure, never raises) ---

def quality_size_mult(confidence) -> float:
    """Map calibrated confidence -> size multiplier (convex, pure, never raises).

    Curve (monotone, convex kinks — shallow at low confidence, steep at high):
      conf < 0.60            -> 0.50x  (low-quality setups halved)
      0.60 <= conf <= 0.75   -> 0.75x -> 1.00x linear (slope ~1.67)
      0.75 <  conf <= 0.85   -> 1.00x -> 1.25x linear (slope 2.5, steeper)
      conf > 0.85            -> 1.25x  (capped reward for top quality)

    Output clamped to [0.4, 1.3]. Invalid / NaN / inf input returns 0.5.
    """
    try:
        c = float(confidence)
        if c != c or c in (float("inf"), float("-inf")):
            return 0.5
        if c < 0.6:
            m = 0.5
        elif c <= 0.75:
            m = 0.75 + (c - 0.6) / 0.15 * 0.25
        elif c <= 0.85:
            m = 1.0 + (c - 0.75) / 0.10 * 0.25
        else:
            m = 1.25
        return max(0.4, min(m, 1.3))
    except Exception:
        return 0.5
