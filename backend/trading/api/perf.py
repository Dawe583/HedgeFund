"""Per-bot performance summary + trade journal (read-only analytics)."""

from __future__ import annotations

from typing import Any, Iterable

from fastapi import APIRouter, Query
from sqlalchemy import select

router = APIRouter(prefix="/api/perf", tags=["perf"])


# ------------------------------------------------------------------ pure helpers
# Operate on plain dicts / objects so they are trivially unit-testable.


def _get(obj: Any, key: str, default: Any = 0.0) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def summarize_trades(rows: Iterable[Any]) -> dict[str, dict[str, float]]:
    """Per-bot aggregates: trades / wins / winrate / total_pnl / avg_conf."""
    agg: dict[str, dict[str, float]] = {}
    for r in rows:
        bot = str(_get(r, "bot", "unknown"))
        pnl = float(_get(r, "pnl", 0.0) or 0.0)
        conf = float(_get(r, "confidence", 0.0) or 0.0)
        e = agg.setdefault(bot, {"trades": 0, "wins": 0, "total_pnl": 0.0, "conf_sum": 0.0})
        e["trades"] += 1
        e["total_pnl"] += pnl
        e["conf_sum"] += conf
        if pnl > 0:
            e["wins"] += 1
    out: dict[str, dict[str, float]] = {}
    for bot, e in agg.items():
        n = int(e["trades"])
        out[bot] = {
            "trades": n,
            "wins": int(e["wins"]),
            "winrate": round(e["wins"] / n, 4) if n else 0.0,
            "total_pnl": round(e["total_pnl"], 4),
            "avg_conf": round(e["conf_sum"] / n, 4) if n else 0.0,
        }
    return out


def build_summary(rows: Iterable[Any], equity_start: float) -> dict[str, Any]:
    """Combine per-bot stats with equity_start / equity_now."""
    rows = list(rows)
    total_pnl = round(sum(float(_get(r, "pnl", 0.0) or 0.0) for r in rows), 4)
    return {
        "per_bot": summarize_trades(rows),
        "equity_start": equity_start,
        "equity_now": round(equity_start + total_pnl, 2),
    }


def format_trade(t: Any) -> dict[str, Any]:
    """Serialize one closed trade row (ORM object or dict) for the journal."""
    pnl = float(_get(t, "pnl", 0.0) or 0.0)
    qty = float(_get(t, "qty", 0.0) or 0.0)
    entry = float(_get(t, "entry_price", 0.0) or 0.0)
    notional = qty * entry
    return {
        "id": _get(t, "id", None),
        "bot": _get(t, "bot", ""),
        "symbol": _get(t, "symbol", ""),
        "side": _get(t, "side", ""),
        "qty": qty,
        "entry_price": entry,
        "exit_price": float(_get(t, "exit_price", 0.0) or 0.0),
        "entry_time": str(_get(t, "entry_time", "") or ""),
        "exit_time": str(_get(t, "exit_time", "") or ""),
        "pnl": round(pnl, 4),
        "pnl_pct": round(pnl / notional * 100, 4) if notional else 0.0,
        "confidence": float(_get(t, "confidence", 0.0) or 0.0),
    }


# ------------------------------------------------------------------ DB snapshots


def _summary_snapshot(limit: int = 2000) -> dict[str, Any]:
    from trading.config import get_settings
    from trading.models import EquityPoint, Trade, make_session_factory

    start = get_settings().paper_equity_start
    session = make_session_factory()()
    try:
        trades = (
            session.execute(select(Trade).order_by(Trade.exit_time.desc()).limit(limit))
            .scalars()
            .all()
        )
        summary = build_summary(
            [{"bot": t.bot, "pnl": t.pnl, "confidence": t.confidence} for t in trades],
            start,
        )
        # Prefer latest persisted equity point when available.
        latest = (
            session.execute(select(EquityPoint).order_by(EquityPoint.ts.desc()).limit(1))
            .scalars()
            .first()
        )
        if latest is not None:
            summary["equity_now"] = round(float(latest.equity), 2)
        return summary
    finally:
        session.close()


def _journal_snapshot(bot: str | None, limit: int) -> list[dict[str, Any]]:
    from trading.models import Trade, make_session_factory

    session = make_session_factory()()
    try:
        stmt = select(Trade).order_by(Trade.exit_time.desc()).limit(limit)
        if bot:
            stmt = select(Trade).where(Trade.bot == bot).order_by(Trade.exit_time.desc()).limit(limit)
        trades = session.execute(stmt).scalars().all()
        return [format_trade(t) for t in trades]
    finally:
        session.close()


# ------------------------------------------------------------------ routes (never raise)


@router.get("/summary")
async def perf_summary() -> dict[str, Any]:
    """Per-bot trades/wins/winrate/total_pnl/avg_conf + equity_start/now."""
    try:
        return _summary_snapshot()
    except Exception:  # noqa: BLE001 - read-only endpoint must never 500
        return {}


@router.get("/journal")
async def trade_journal(
    bot: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
) -> list[dict[str, Any]]:
    """Recent closed trades, optionally filtered by bot."""
    try:
        return _journal_snapshot(bot, limit)
    except Exception:  # noqa: BLE001 - read-only endpoint must never 500
        return []
