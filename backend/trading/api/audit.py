"""Agent execution audit — everything the desk executes, one timeline."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from trading.models import AgentPrediction, Trade, make_session_factory

router = APIRouter(prefix="/api", tags=["audit"])


def collect_executions(session_factory, limit: int = 150) -> dict:
    """Unified execution timeline — shared by the API router and static snapshots."""

    out: list[dict] = []
    counts = {"paper": 0, "forecast": 0, "live": 0}
    try:
        session = session_factory()
        try:
            trades = (
                session.execute(select(Trade).order_by(Trade.exit_time.desc()).limit(limit))
                .scalars()
                .all()
            )
            for t in trades:
                out.append(
                    {
                        "ts": str(t.exit_time),
                        "kind": "paper_fill",
                        "actor": t.bot,
                        "side": t.side,
                        "detail": f"{t.qty} @ {round(t.entry_price, 2)}",
                        "pnl": round(t.pnl, 4),
                        "confidence": t.confidence,
                        "venue": "paper",
                    }
                )
                counts["paper"] += 1

            preds = (
                session.execute(
                    select(AgentPrediction).order_by(AgentPrediction.ts.desc()).limit(limit)
                )
                .scalars()
                .all()
            )
            for p in preds:
                out.append(
                    {
                        "ts": str(p.ts),
                        "kind": "forecast",
                        "actor": p.bot,
                        "side": p.direction,
                        "detail": (p.reasoning or "")[:120],
                        "pnl": None,
                        "confidence": p.confidence,
                        "venue": "signal",
                    }
                )
                counts["forecast"] += 1
        finally:
            session.close()

        # live Hyperliquid fills — best effort, never raises
        try:
            from trading.venues.hyperliquid_live import get_live

            live = get_live()
            if live.configured:
                fills = live._info.user_fills(live.account) if live.account else []
                for f in fills or []:
                    out.append(
                        {
                            "ts": str(f.get("time")),
                            "kind": "live_fill",
                            "actor": "agent",
                            "side": "buy" if str(f.get("dir", "")).startswith("Buy") else "sell",
                            "detail": f"{f.get('sz')} {f.get('coin')} @ {f.get('px')}",
                            "pnl": float(f.get("closedPnl", 0) or 0),
                            "confidence": None,
                            "venue": "hyperliquid",
                        }
                    )
                    counts["live"] += 1
        except Exception:  # noqa: BLE001
            pass

        out.sort(key=lambda x: x.get("ts") or "", reverse=True)
        return {"executions": out[:limit], "counts": counts}
    except Exception:  # noqa: BLE001
        return {"executions": [], "counts": counts}


@router.get("/executions")
async def executions(limit: int = Query(150, le=500)):
    """Unified audit timeline: paper fills + agent forecasts (DB) + live HL fills (best effort)."""
    if limit <= 0:
        raise HTTPException(400, "limit must be a positive integer")
    return collect_executions(make_session_factory(), limit=limit)
