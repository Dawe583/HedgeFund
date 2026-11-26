"""REST endpoints for the fund overview: ledger wealth beside the engine's
own figure, and the reconciliation between them (design §8, rule D13).

The consolidated total is LEDGER wealth — the trading account is already
inside it through the broker statement, so the engine's equity is shown
beside it and never summed in (summing counts the same money twice). Both
sides of the reconciliation are statements about the same money: the
photograph is the broker statement, the events are the fills, and the gap
is what stands between them.

Everything here is honest about absence: an engine that never wrote an
equity row, an account never photographed, a dollar the feed cannot convert
— each is a measured answer to a question, not an error page.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import analytics, fx, models, positions, schemas
from app.database import commit, get_db

router = APIRouter(prefix="/api/overview", tags=["overview"])

# The settings key declaring which ledger institution is the trading desk's
# account. The mapping is a declaration, never a guess: two brokerage
# accounts side by side are indistinguishable to anything that would infer.
MAPPING_KEY = "trading_institution_id"


def _engine_equity(db: Session) -> schemas.OverviewTradingEquity:
    """The latest portfolio equity the engine wrote, or the honest absence.

    The equity_points table lives in the one shared database (design D3) but
    is written by the engine process, so a wealth-only schema — the test
    database, a database Alembic has not migrated — simply has nothing to
    report: `available` false, which is a state of the desk, not a failure
    of this endpoint."""
    try:
        names = inspect(db.get_bind()).get_table_names()
    except SQLAlchemyError:
        names = []
    if "equity_points" not in names:
        return schemas.OverviewTradingEquity(available=False)

    from trading.models import EquityPoint

    row = db.scalars(
        select(EquityPoint)
        .where(EquityPoint.bot == "portfolio")
        .order_by(EquityPoint.ts.desc())
        .limit(1)
    ).first()
    if row is None:
        return schemas.OverviewTradingEquity(available=False)

    # The ts arrives naive out of SQLite; the engine writes UTC, which the
    # frontend renders as such.
    ts = row.ts if isinstance(row.ts, dt.datetime) else None
    conv = fx.Converter(db)
    return schemas.OverviewTradingEquity(
        available=True,
        value=row.equity,
        # Strict conversion: `to_base` answers None when no rate exists, and
        # a dollar figure passed through as if it were euro would be the
        # wrong answer wearing the right one's clothes.
        value_base=conv.to_base(row.equity, "USD"),
        as_of=ts.isoformat() if ts is not None else str(row.ts),
    )


def _reconciliation(db: Session, engine: schemas.OverviewTradingEquity | None = None) -> schemas.OverviewReconciliation:
    """Ledger statement vs engine equity for the mapped trading account.

    The statement side is the ledger's own arithmetic — projected positions
    valued the way net worth values them, plus the cash register's
    projection — so the gap measures the engine against the same account the
    consolidated total already contains. `statement_date` says how fresh the
    photograph half of the comparison is: a gap against last month's
    statement is time plus divergence, never divergence alone."""
    missing: list[str] = []
    out = schemas.OverviewReconciliation()

    raw = db.get(models.Setting, MAPPING_KEY)
    institution_id: int | None = None
    if raw is not None and (raw.value or "").strip():
        try:
            institution_id = int((raw.value or "").strip())
        except ValueError:
            institution_id = None
    if institution_id is None:
        missing.append("no-mapping")

    inst = db.get(models.Institution, institution_id) if institution_id else None
    if institution_id is not None and inst is None:
        missing.append("institution-gone")

    # The caller hands in the equity it already read, so the figure beside net
    # worth and the figure inside the gap are the same row on one response —
    # an engine write between the two reads could otherwise make them disagree.
    if engine is None:
        engine = _engine_equity(db)
    if not engine.available:
        missing.append("no-engine-equity")

    statement_total: float | None = None
    if inst is not None:
        out.institution_id = inst.id
        out.institution_name = inst.name
        conv = fx.Converter(db)

        anchors = positions.latest_snapshot_by_institution(db)
        snap = anchors.get(inst.id)
        held = [p for p in positions.project(db, conv) if p.institution_id == inst.id]
        if snap is not None or held:
            out.statement_positions = sum(p.current_value for p in held)

        cash = analytics.compute_cash_position(db, inst.id, conv=conv)
        statement_cash: float | None = None
        if cash is not None and cash["anchor_date"] is not None:
            statement_cash = cash["projected"]
            out.statement_cash = cash["projected"]

        # Both sides are ISO strings (`snap.date` as stored, the anchor date
        # as the register parses it back): ISO orders as a string, so the
        # freshest photograph or balance is the plain maximum.
        dates = [str(d) for d in (snap.date if snap else None, cash["anchor_date"] if cash else None) if d]
        if dates:
            out.statement_date = max(dates)

        if out.statement_positions is None and statement_cash is None:
            missing.append("no-statement")
        else:
            statement_total = (out.statement_positions or 0.0) + (statement_cash or 0.0)
            out.statement_total = statement_total

    engine_base: float | None = None
    if engine.available:
        engine_base = fx.Converter(db).to_base(engine.value, "USD")
        out.engine_as_of = engine.as_of
        if engine_base is None:
            missing.append("equity-unconvertible")
        else:
            out.engine_equity_base = engine_base

    if statement_total is not None and engine_base is not None:
        out.gap = statement_total - engine_base
    out.missing = missing
    return out


@router.get("/fund", response_model=schemas.OverviewFund)
def get_fund_overview(db: Session = Depends(get_db)) -> schemas.OverviewFund:
    """Total wealth (the ledger's own figure, reused, never reimplemented),
    the engine's equity beside it, and the reconciliation gap between the
    broker statement and the engine — each honestly absent when it cannot
    be measured."""
    equity = _engine_equity(db)
    return schemas.OverviewFund(
        total_wealth=analytics.compute_summary(db),
        trading_equity=equity,
        reconciliation=_reconciliation(db, equity),
    )


@router.put("/trading-account", response_model=schemas.OverviewReconciliation)
def put_trading_account(
    payload: schemas.TradingAccountMapping, db: Session = Depends(get_db)
) -> schemas.OverviewReconciliation:
    """Declare which ledger institution is the trading desk's account — the
    declaration the reconciliation measures against. The institution must
    exist: mapping to a row that is not there would reconcile against air."""
    institution = db.get(models.Institution, payload.institution_id)
    if institution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="That institution does not exist. The trading account is a declaration about a real account, not a name to come.",
        )
    row = db.get(models.Setting, MAPPING_KEY)
    if row is None:
        db.add(models.Setting(key=MAPPING_KEY, value=str(payload.institution_id)))
    else:
        row.value = str(payload.institution_id)
    commit(db)
    return _reconciliation(db)
