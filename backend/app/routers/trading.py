"""Read-only trading endpoints: what the engine did, what the gate said.

The trading engine is a separate concern from the wealth app — it writes its
own tables (candles, backtest runs, validation verdicts) into the database
TRADING_DATABASE_URL names, or the application's own database by default.
Nothing here writes; an engine that has never run is a first-class answer
(engine_state "offline", empty lists), never an error page. When the trading
tables do not exist yet — a database Alembic has not migrated, or the test
schema that only builds the wealth tables — every endpoint degrades to that
same offline answer instead of a 500.
"""

from __future__ import annotations

import datetime as dt
import json
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import inspect, select
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from trading.config import get_settings
from trading.models import (
    BacktestRun,
    BacktestValidation,
    BotStatus,
    make_engine,
)
from trading.research import STRATEGIES

router = APIRouter(prefix="/api/trading", tags=["trading"])

# A heartbeat older than this no longer means a running engine; the paper
# worker ticks every 10 seconds, so a minute of silence is death, not lag.
HEARTBEAT_ALIVE_S = 120


@lru_cache
def _session_factory() -> sessionmaker:
    """Sessions against the trading database, created once per process.

    make_engine is idempotent-safe: on a database Alembic already migrated
    its create_all is a no-op, and the legacy column guard only ever adds
    what is missing — reads here change nothing either way.
    """
    engine = make_engine(get_settings().database_url)
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_trading_db():
    db: Session = _session_factory()()
    try:
        yield db
    finally:
        db.close()


def _tables_present(db: Session) -> bool:
    try:
        names = inspect(db.get_bind()).get_table_names()
    except SQLAlchemyError:
        return False
    return "backtest_validations" in names and "backtest_runs" in names


def _as_iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.isoformat()
    return str(value)


@router.get("/status")
def trading_status(db: Session = Depends(get_trading_db)) -> dict:
    """Engine state at a glance; offline is an answer, not a failure."""
    try:
        present = _tables_present(db)
        db_ok = True
    except SQLAlchemyError:
        present, db_ok = False, False

    last_heartbeat: dt.datetime | None = None
    engine_state = "offline"
    validations_total = 0
    if db_ok and present:
        try:
            rows = db.execute(
                select(BotStatus).where(
                    BotStatus.name.notlike("__%"), BotStatus.last_heartbeat.isnot(None)
                )
            ).scalars().all()
            beats = [r.last_heartbeat for r in rows if r.last_heartbeat is not None]
            if beats:
                last_heartbeat = max(beats)
                ref = last_heartbeat
                if ref.tzinfo is None:
                    ref = ref.replace(tzinfo=dt.UTC)
                age = (dt.datetime.now(dt.UTC) - ref).total_seconds()
                if age <= HEARTBEAT_ALIVE_S:
                    engine_state = "running"
            validations_total = len(db.execute(select(BacktestValidation.id)).all())
        except OperationalError:
            present = False

    return {
        "engine_state": engine_state,
        "last_tick_at": _as_iso(last_heartbeat),
        "db_ok": db_ok and present,
        "strategies_registered": 0,  # lifecycle tables land in M3
        "validations_total": validations_total,
    }


@router.get("/strategies")
def trading_strategies() -> list[dict]:
    """The four ported strategies, straight from the static registry.

    Pure code facts — no database involved, because a registry row that
    claims lifecycle state before lifecycle tables exist would be lying.
    """
    return [
        {
            "key": spec["key"],
            "name": spec["name"],
            "timeframe": spec["timeframe"],
            "symbols": spec["symbols"],
            "description": spec["description"],
            "registered": False,
        }
        for spec in STRATEGIES.values()
    ]


def _run_payload(run: BacktestRun, validation: BacktestValidation | None) -> dict:
    return {
        "id": run.id,
        "bot": run.bot,
        "symbol": run.symbol,
        "timeframe": run.timeframe,
        "started_at": _as_iso(run.created_at),
        "trades_count": run.trades_n,
        "metrics": {
            "win_rate": run.win_rate,
            "profit_factor": run.profit_factor,
            "sharpe": run.sharpe,
            "max_dd_pct": run.max_dd_pct,
            "total_return_pct": run.total_return_pct,
        },
        "verdict": validation.verdict if validation else None,
        "validation": (
            {
                "permutation_p": validation.permutation_p,
                "sharpe_ci_lo": validation.sharpe_ci_lo,
                "sharpe_ci_hi": validation.sharpe_ci_hi,
                "wf_positive_folds": validation.wf_positive_folds,
                "wf_total_folds": validation.wf_total_folds,
            }
            if validation
            else None
        ),
        "created_at": _as_iso(run.created_at),
    }


@router.get("/backtest-runs")
def list_backtest_runs(db: Session = Depends(get_trading_db)) -> list[dict]:
    """The last 50 backtest runs, each with the verdict its validation reached."""
    if not _tables_present(db):
        return []
    try:
        runs = (
            db.execute(select(BacktestRun).order_by(BacktestRun.id.desc()).limit(50))
            .scalars()
            .all()
        )
        validations = (
            db.execute(select(BacktestValidation).order_by(BacktestValidation.id.desc()))
            .scalars()
            .all()
        )
    except OperationalError:
        return []
    by_run: dict[int, BacktestValidation] = {}
    for v in validations:
        if v.run_id is not None and v.run_id not in by_run:
            by_run[v.run_id] = v
    return [_run_payload(r, by_run.get(r.id)) for r in runs]


@router.get("/backtest-runs/{run_id}")
def backtest_run_detail(run_id: int, db: Session = Depends(get_trading_db)) -> dict:
    """One run with everything its verdict stands on: params, seed, data provenance."""
    if not _tables_present(db):
        raise HTTPException(status_code=404, detail="no trading tables in this database")
    run = db.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"backtest run {run_id} not found")
    validation = (
        db.execute(
            select(BacktestValidation)
            .where(BacktestValidation.run_id == run_id)
            .order_by(BacktestValidation.id.desc())
        )
        .scalars()
        .first()
    )
    payload = _run_payload(run, validation)
    payload["params"] = json.loads(run.params_json or "{}")
    if validation is not None:
        payload["provenance"] = {
            "seed": validation.seed,
            "data_source": validation.data_source,
            "data_rows": validation.data_rows,
            "data_start": validation.data_start,
            "data_end": validation.data_end,
        }
        payload["reasons"] = json.loads(validation.reasons_json or "[]")
        payload["prob_positive"] = validation.prob_positive
        payload["sharpe_actual"] = validation.sharpe_actual
        payload["min_trades_required"] = validation.min_trades_required
    else:
        payload["provenance"] = None
        payload["reasons"] = []
    return payload
