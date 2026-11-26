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

from app.schemas_trading import (
    TradingClosedTrade,
    TradingPosition,
    TradingRunDetail,
    TradingRailsStatus,
    TradingRunItem,
    TradingStatus,
    TradingStrategy,
)
from trading.config import get_settings
from trading.models import (
    BacktestRun,
    BacktestValidation,
    BotStatus,
    OpenPosition,
    Trade,
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


def _strategies_registered(db: Session) -> int:
    """Lifecycle-registry registration count — 0 on any database without the
    tables, because absent tables mean absent registrations, never an error."""
    try:
        from trading.models import Strategy as StrategyRow

        return len(db.execute(select(StrategyRow.id)).all())
    except (OperationalError, SQLAlchemyError):
        return 0


@router.get("/rails", response_model=TradingRailsStatus)
def trading_rails(db: Session = Depends(get_trading_db)) -> dict:
    """Per-bot rail state: the kill-switches, the daily loss consumed, the
    loss-streak cooldown, exposure against the caps, and the recent
    risk_events the rails wrote to explain themselves.

    Sources, honestly separated: the manual kill-switch and the halt
    sentinel are read LIVE (they are external halts — a cached answer would
    be a lie by design), the per-bot rails come from the desk runner's
    snapshots (kernel memory is the truth; the snapshot is its rendering),
    and the events come from the risk_events table. Empty is the first-class
    answer: an engine that never ran has rails and no rail state."""
    import os
    from pathlib import Path

    from trading.models import RiskEvent, get_state

    # external halts, live — never cached
    ks_row = db.get(BotStatus, "__killswitch")
    manual_tripped = bool(ks_row and ks_row.running is False)
    manual_note = ks_row.note if ks_row else ""
    sentinel_path = str(Path(get_settings().data_dir) / "HALT")

    bots: list[dict] = []
    try:
        names = [
            row.name
            for row in db.execute(select(BotStatus)).scalars()
            if row.name.startswith("__state_rails/")
        ]
    except (OperationalError, SQLAlchemyError):
        names = []
    for name in sorted(names):
        bot = name[len("__state_rails/"):]
        snap = get_state(db, f"rails/{bot}", None)
        if not isinstance(snap, dict):
            continue
        bots.append(
            {
                "bot": bot,
                "asof": snap.get("written_at"),
                "equity": snap.get("equity", 0.0),
                "peak_equity": snap.get("peak_equity", 0.0),
                "drawdown_pct": snap.get("drawdown_pct", 0.0),
                "killswitch_dd_pct": snap.get("killswitch_dd_pct", 0.0),
                "kill_tripped": bool(snap.get("kill_tripped", False)),
                "daily_loss": snap.get("daily_loss", 0.0),
                "daily_loss_limit": snap.get("daily_loss_limit", 0.0),
                "daily_loss_consumed": snap.get("daily_loss_consumed", 0.0),
                "daily_breached": bool(snap.get("daily_breached", False)),
                "loss_streak": snap.get("loss_streak", 0),
                "max_losses": snap.get("max_losses", 3),
                "cooldown_remaining_s": snap.get("cooldown_remaining_s", 0.0),
                "vetoes_total": snap.get("vetoes_total", 0),
                "exposure": snap.get("exposure"),
            }
        )

    events: list[dict] = []
    try:
        rows = (
            db.execute(select(RiskEvent).order_by(RiskEvent.id.desc()).limit(25))
            .scalars()
            .all()
        )
        events = [
            {
                "id": r.id,
                "created_at": _as_iso(r.created_at),
                "bot": r.bot,
                "symbol": r.symbol,
                "rail": r.rail,
                "decision": r.decision,
                "inputs": json.loads(r.inputs_json or "{}"),
            }
            for r in rows
        ]
    except (OperationalError, SQLAlchemyError):
        events = []

    return {
        "manual_killswitch": manual_tripped,
        "manual_killswitch_note": manual_note or "",
        "halt_sentinel": os.path.exists(sentinel_path),
        "halt_sentinel_path": sentinel_path,
        "bots": bots,
        "recent_events": events,
    }


@router.get("/status", response_model=TradingStatus)
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
                    # the underscores in the sentinel prefix are LIKE wildcards —
                    # unescaped, this filter excludes every bot name longer than
                    # one character (measured 2026-11-26: the engine lamp stayed
                    # offline with heartbeats present)
                    BotStatus.name.notlike("\\_\\_%", escape="\\"), BotStatus.last_heartbeat.isnot(None)
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
        "strategies_registered": _strategies_registered(db) if db_ok else 0,
        "validations_total": validations_total,
    }


def _aware(value: dt.datetime) -> dt.datetime:
    # sqlite drops tzinfo on the way back out; the rows are written UTC
    return value if value.tzinfo is not None else value.replace(tzinfo=dt.UTC)


def _position_payload(row: OpenPosition, now: dt.datetime) -> dict:
    return {
        "id": row.id,
        "bot": row.bot,
        "symbol": row.symbol,
        "side": row.side,
        "qty": row.qty,
        "entry_price": row.entry_price,
        "stop_loss": row.stop_loss,
        "take_profit": row.take_profit,
        "opened_at": _as_iso(row.opened_at),
        "age_seconds": max(0.0, (now - _aware(row.opened_at)).total_seconds()),
        "confidence": row.confidence,
        "signal_time": _as_iso(row.signal_time),
        "gate_source": row.gate_source,
    }


@router.get("/positions", response_model=list[TradingPosition])
def list_positions(db: Session = Depends(get_trading_db)) -> list[dict]:
    """Every open position the desk has written. Empty is the honest answer
    both for "no engine ever ran" and for "the engine runs flat" — the row
    set IS the state; the engine lamp on /status is how the two read apart."""
    if not _tables_present(db):
        return []
    try:
        rows = (
            db.execute(select(OpenPosition).order_by(OpenPosition.opened_at))
            .scalars()
            .all()
        )
    except OperationalError:
        return []
    now = dt.datetime.now(dt.UTC)
    return [_position_payload(r, now) for r in rows]


@router.get("/positions/recent-trades", response_model=list[TradingClosedTrade])
def list_recent_trades(db: Session = Depends(get_trading_db)) -> list[dict]:
    """The last 25 settled round-trips — evidence the desk actually traded,
    newest first. Same empty-is-honest contract as /positions."""
    if not _tables_present(db):
        return []
    try:
        rows = (
            db.execute(select(Trade).order_by(Trade.exit_time.desc()).limit(25))
            .scalars()
            .all()
        )
    except OperationalError:
        return []
    return [
        {
            "id": t.id,
            "bot": t.bot,
            "symbol": t.symbol,
            "side": t.side,
            "qty": t.qty,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "entry_time": _as_iso(t.entry_time),
            "exit_time": _as_iso(t.exit_time),
            "pnl": t.pnl,
            "fees": t.fees,
            "confidence": t.confidence,
            "mode": t.mode,
            "gate_source": t.gate_source,
        }
        for t in rows
    ]


@router.get("/strategies", response_model=list[TradingStrategy])
def trading_strategies(db: Session = Depends(get_trading_db)) -> list[dict]:
    """The catalog of ported strategies, with the lifecycle registry's
    answer beside each: registered means a strategies row exists — the
    explicit act — never that capital followed it (that is the roster,
    versions in state paper, which /rails and /status reflect)."""
    try:
        from trading.models import Strategy as StrategyRow

        registered_keys = {r.key for r in db.execute(select(StrategyRow)).scalars()}
    except (OperationalError, SQLAlchemyError):
        registered_keys = set()
    return [
        {
            "key": spec["key"],
            "name": spec["name"],
            "timeframe": spec["timeframe"],
            "symbols": spec["symbols"],
            "description": spec["description"],
            "registered": spec["key"] in registered_keys,
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
        "engine_version": run.engine_version,
    }


@router.get("/backtest-runs", response_model=list[TradingRunItem])
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


@router.get("/backtest-runs/{run_id}", response_model=TradingRunDetail)
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
        payload["prob_positive"] = None
        payload["sharpe_actual"] = None
        payload["min_trades_required"] = None
    # Evidence the run carries (migration c4a1b2d3e5f6; null before it): the
    # downsampled equity path for the chart and the per-trade fill audit.
    for key, column in (("equity_curve", "equity_curve_json"), ("trades", "trades_json")):
        raw = getattr(run, column, None)
        payload[key] = json.loads(raw) if raw else None
    return payload
