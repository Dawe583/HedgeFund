"""Read-only intelligence and alerts surfaces (design §8: INTELLIGENCE
panels + ALERTS stream).

One stream, honestly assembled: the wealth plane's chain runs and the
trading plane's agent insights are rows in two databases, merged here at
read time because that is the only place they meet. Nothing writes. Every
panel degrades to `available: false` when its store is absent — an engine
that never ran is a state of the desk, never an error page.

What the design names and this module deliberately does NOT have:

- **Memory browser** — it DOES exist: the learning loop (trading/agents/
  memory.py) persists working/shallow/deep tiers in `agent_memory`, so the
  tiers are read here as the loop wrote them.
- **Budget panel** — exists in the honest shape the store supports: the
  request counter is a single shared tally per day (agents/budget.py), so
  the panel reports day spend against the caps per priority tier. Per-tier
  SPEND is not tracked anywhere and is not fabricated.
- **Alerts** — in-app only, per the design: Telegram/webhook delivery is an
  M5+ extra. The stream merges rail events, validation rejections, stale
  engine heartbeats and the reconciliation gap state.
"""

from __future__ import annotations

import datetime as dt
import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import chain, crud, models
from app.database import get_db
from app.routers.overview import _reconciliation
from app.routers.trading import get_trading_db
from app.schemas_intelligence import (
    AlertItem,
    AlertsStream,
    BudgetTierCap,
    IntelligenceBudget,
    IntelligenceFeed,
    IntelligenceFeedItem,
    IntelligenceMemory,
    MemoryEntry,
)
from trading.agents.budget import RESERVE, RequestBudget
from trading.agents.openrouter import budget_path
from trading.config import get_settings
from trading.models import AgentInsight, AgentMemory, BacktestValidation, BotStatus, RiskEvent

router = APIRouter(prefix="/api", tags=["intelligence"])

# How far back the surfaces read. Ceilings, not pages: this is one person's
# machine, and the operator's question is "what happened lately", not an
# archive scan.
FEED_LIMIT = 100
ALERTS_LOOKBACK_DAYS = 7
MEMORY_PER_TIER = 40

# The heartbeat staleness budget — shared by value with routers/trading.py's
# HEARTBEAT_ALIVE_S. The two surfaces answer different questions (status
# lamp vs. alert stream) but must agree about what "silent" means.
HEARTBEAT_ALIVE_S = 120


def _aware(value: dt.datetime) -> dt.datetime:
    """SQLite returns naive datetimes; the engine writes UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.UTC)
    return value


def _tables(db: Session) -> set[str]:
    try:
        return set(inspect(db.get_bind()).get_table_names())
    except SQLAlchemyError:
        return set()


# ---------------------------------------------------------------- feed


def _chain_items(db: Session, limit: int) -> list[IntelligenceFeedItem]:
    items: list[IntelligenceFeedItem] = []
    for run in crud.get_chain_runs(db, limit=limit):
        challenge = (chain.challenge_of(run) or "unstated").lower()
        steps = len(run.steps)
        revisions = sum(1 for s in run.steps if s.role == "revision")
        summary = (
            f"{steps} steps, {revisions} revisions — {challenge}"
            + (f". {(run.verdict or '').strip().splitlines()[0][:140]}" if run.verdict else "")
        )
        # chain_runs.created_at is an ISO string (see models.py), not a
        # datetime — parse it back rather than trust either clock blindly.
        try:
            ts = dt.datetime.fromisoformat(str(run.created_at))
        except ValueError:
            continue
        items.append(
            IntelligenceFeedItem(
                ts=_aware(ts),
                source="wealth-chain",
                kind="chain-run",
                title="Analysis run",
                summary=summary,
                severity="warning" if challenge == "contested" else "info",
                ref=f"/api/advisor/chain/{run.id}",
            )
        )
    return items


def _insight_items(db: Session, limit: int) -> list[IntelligenceFeedItem]:
    rows = (
        db.execute(select(AgentInsight).order_by(AgentInsight.created_at.desc()).limit(limit))
        .scalars()
        .all()
    )
    return [
        IntelligenceFeedItem(
            ts=_aware(r.created_at),
            source=f"trading:{r.agent}",
            kind="insight",
            title=r.title,
            summary=(r.body or "").strip().splitlines()[0][:200] if r.body else "",
            severity=r.severity or "info",
            ref=None,
        )
        for r in rows
    ]


@router.get("/intelligence/feed", response_model=IntelligenceFeed)
def intelligence_feed(
    source: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    limit: int = Query(default=FEED_LIMIT, le=500),
    wealth_db: Session = Depends(get_db),
    trading_db: Session = Depends(get_trading_db),
) -> IntelligenceFeed:
    """The unified stream, newest first, filterable by source prefix and
    kind. `sources` answers what IS there before the filter, so an empty
    filtered page can be told apart from an empty desk."""
    items = _chain_items(wealth_db, limit)

    if "agent_insights" in _tables(trading_db):
        try:
            items.extend(_insight_items(trading_db, limit))
        except SQLAlchemyError:
            pass

    # The sources answer what IS there before the filter, so an empty filtered
    # page can be told apart from an empty desk.
    all_sources = sorted({i.source for i in items})
    if source:
        items = [i for i in items if i.source == source or i.source.startswith(source + ":")]
    if kind:
        items = [i for i in items if i.kind == kind]
    items.sort(key=lambda i: i.ts, reverse=True)
    return IntelligenceFeed(
        available=True,
        items=items[:limit],
        sources=all_sources,
    )


# ---------------------------------------------------------------- memory


@router.get("/intelligence/memory", response_model=IntelligenceMemory)
def intelligence_memory(
    limit: int = Query(default=MEMORY_PER_TIER, le=200),
    db: Session = Depends(get_trading_db),
) -> IntelligenceMemory:
    """The layered memory as the learning loop persists it: working (raw
    outcomes, decay fast), shallow (lessons), deep (reflections, durable).
    Unpruned rows are shown as stored — decay is the loop's business, the
    browser reports what is there."""
    empty = IntelligenceMemory(available=False, working=[], shallow=[], deep=[])
    if "agent_memory" not in _tables(db):
        return empty
    try:
        rows = (
            db.execute(select(AgentMemory).order_by(AgentMemory.created_at.desc()).limit(limit * 3))
            .scalars()
            .all()
        )
    except SQLAlchemyError:
        return empty

    tiers: dict[str, list[MemoryEntry]] = {"working": [], "shallow": [], "deep": []}
    for r in rows:
        if r.tier not in tiers or len(tiers[r.tier]) >= limit:
            continue
        tiers[r.tier].append(
            MemoryEntry(
                id=r.id,
                bot=r.bot,
                tier=r.tier,
                kind=r.kind,
                content=r.content,
                importance=r.importance,
                pnl_pct=r.pnl_pct,
                created_at=_aware(r.created_at),
            )
        )
    return IntelligenceMemory(available=True, **tiers)


# ---------------------------------------------------------------- budget


@router.get("/intelligence/budget", response_model=IntelligenceBudget)
def intelligence_budget() -> IntelligenceBudget:
    """Day spend against the free-tier caps, read from the same counter file
    the desk claims against. No file means no call was ever claimed:
    available false, not a zero — a zero would claim the day started."""
    s = get_settings()
    path = budget_path(s.database_url, s.data_dir)
    budget = RequestBudget(path, s.agent_daily_budget, s.agent_rpm_budget)
    if not path.exists():
        return IntelligenceBudget(available=False)
    snap = budget.snapshot()
    daily = snap["daily_budget"]
    return IntelligenceBudget(
        available=True,
        day=snap["day"],
        used=snap["used"],
        daily_budget=daily,
        remaining=snap["remaining"],
        rpm_budget=snap["rpm_budget"],
        tier_caps=[
            BudgetTierCap(tier=tier, cap=int(daily * frac)) for tier, frac in RESERVE.items()
        ],
    )


# ---------------------------------------------------------------- alerts


def _risk_alerts(db: Session, since: dt.datetime) -> list[AlertItem]:
    rows = (
        db.execute(
            select(RiskEvent).where(RiskEvent.created_at >= since).order_by(RiskEvent.id.desc()).limit(200)
        )
        .scalars()
        .all()
    )
    out: list[AlertItem] = []
    for r in rows:
        if r.decision in ("tripped", "breached"):
            severity = "critical"
        elif r.decision in ("veto", "cooldown_started"):
            severity = "warning"
        else:
            severity = "info"
        try:
            inputs = json.loads(r.inputs_json or "{}")
        except (ValueError, TypeError):
            inputs = {}
        reason = inputs.get("reason") or inputs.get("note") or ""
        symbol = f" {r.symbol}" if r.symbol else ""
        out.append(
            AlertItem(
                ts=_aware(r.created_at),
                severity=severity,
                kind=f"rail-{r.decision}",
                source="trading",
                title=f"{r.rail} — {r.bot}{symbol}",
                detail=str(reason)[:200] if reason else r.decision,
            )
        )
    return out


def _validation_alerts(db: Session, since: dt.datetime) -> list[AlertItem]:
    rows = (
        db.execute(
            select(BacktestValidation)
            .where(
                BacktestValidation.created_at >= since,
                BacktestValidation.verdict.in_(["rejected", "insufficient_data"]),
            )
            .order_by(BacktestValidation.id.desc())
            .limit(100)
        )
        .scalars()
        .all()
    )
    out: list[AlertItem] = []
    for r in rows:
        try:
            reasons = json.loads(r.reasons_json or "[]")
        except (ValueError, TypeError):
            reasons = []
        out.append(
            AlertItem(
                ts=_aware(r.created_at),
                severity="warning" if r.verdict == "rejected" else "info",
                kind=f"validation-{r.verdict}",
                source="trading",
                title=f"{r.strategy} on {r.symbol} {r.timeframe}",
                detail=(str(reasons[0])[:200] if reasons else r.verdict),
            )
        )
    return out


def _stale_engine_alerts(db: Session) -> list[AlertItem]:
    """A heartbeat that exists and has gone silent. An engine that NEVER ran
    is the status lamp's answer, not an alert — nothing here was ever
    measured, so nothing here went stale."""
    rows = db.execute(
        select(BotStatus).where(
            BotStatus.name.notlike("\\_\\_%", escape="\\"), BotStatus.last_heartbeat.isnot(None)
        )
    ).scalars().all()
    now = dt.datetime.now(dt.UTC)
    out: list[AlertItem] = []
    for r in rows:
        beat = _aware(r.last_heartbeat) if r.last_heartbeat else None
        if beat is None:
            continue
        age = (now - beat).total_seconds()
        if age > HEARTBEAT_ALIVE_S:
            out.append(
                AlertItem(
                    ts=beat,
                    severity="critical" if age > HEARTBEAT_ALIVE_S * 30 else "warning",
                    kind="engine-stale",
                    source="trading",
                    title=f"{r.name} heartbeat silent",
                    detail=f"last heartbeat {int(age // 60)} min ago"
                    + (f" — {r.note}" if r.note else ""),
                )
            )
    return out


def _reconciliation_alerts(wealth_db: Session) -> list[AlertItem]:
    """The reconciliation gap, as an alert only when it is material: a gap
    under 1% of the statement is measurement noise (the engine ticks more
    often than brokers photograph), not a discrepancy. `missing` states are
    absence, not alerts — except a measured gap, which is the point."""
    try:
        rec = _reconciliation(wealth_db)
    except SQLAlchemyError:
        return []
    if rec.gap is None or rec.statement_total in (None, 0):
        return []
    rel = abs(rec.gap) / abs(rec.statement_total)
    if rel < 0.01:
        return []
    return [
        AlertItem(
            ts=dt.datetime.now(dt.UTC),
            severity="critical" if rel > 0.05 else "warning",
            kind="reconciliation-gap",
            source="wealth",
            title=f"ledger/engine gap {rel * 100:.1f}% at {rec.institution_name or 'the trading account'}",
            detail=(
                f"statement {rec.statement_total:.2f} vs engine {rec.engine_equity_base:.2f}"
                if rec.engine_equity_base is not None
                else "engine equity unconvertible"
            ),
        )
    ]


@router.get("/alerts", response_model=AlertsStream)
def alerts_stream(
    wealth_db: Session = Depends(get_db),
    trading_db: Session = Depends(get_trading_db),
) -> AlertsStream:
    """The in-app alert stream: rail events, validation failures, stale
    heartbeats, reconciliation gaps — severity-typed, newest first. Delivery
    stays in-app per the design; nothing here pages anyone."""
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=ALERTS_LOOKBACK_DAYS)
    # risk_events.created_at arrives naive from SQLite but comparisons are
    # the DB's business; write the filter naive-UTC so the comparison is
    # apples to apples on both engines.
    since_naive = since.replace(tzinfo=None)

    tables = _tables(trading_db)
    items: list[AlertItem] = []
    readable = False
    try:
        if "risk_events" in tables:
            items.extend(_risk_alerts(trading_db, since_naive))
        if "backtest_validations" in tables:
            items.extend(_validation_alerts(trading_db, since_naive))
        if "bot_status" in tables:
            items.extend(_stale_engine_alerts(trading_db))
        readable = bool(tables)
    except SQLAlchemyError:
        pass

    try:
        items.extend(_reconciliation_alerts(wealth_db))
        readable = True
    except SQLAlchemyError:
        pass

    items.sort(key=lambda i: i.ts, reverse=True)
    return AlertsStream(available=readable, items=items[:200])
