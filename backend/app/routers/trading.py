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
from pathlib import Path
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import inspect, select
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.schemas_trading import (
    ApproveRequest,
    MLPredictionsLatest,
    MLPredictionTrackRecord,
    AuditChainVerification,
    AuditSignoffCreateRequest,
    MandateCreateRequest,
    OrderCardConfirmRequest,
    OrderCardCreateRequest,
    TradingMandates,
    TradingOrderCards,
    KillSwitchRequest,
    KillSwitchState,
    TradingApprovalResult,
    TradingClosedTrade,
    TradingModelRegistry,
    TradingRegistry,
    TradingDivergenceStatus,
    TradingPosition,
    TradingRunDetail,
    TradingRailsStatus,
    TradingRunItem,
    TradingSignalsToday,
    TradingStatus,
    TradingStrategy,
    TradingStrategyPanel,
    TradingValidationQueue,
)
from trading.config import get_settings
from trading.models import (
    Approval,
    BacktestRun,
    BacktestValidation,
    BotStatus,
    OpenPosition,
    RiskEvent,
    StrategyState,
    StrategyVersion,
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
                "divergence": snap.get("divergence"),
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
        "vetoes_today": _vetoes_today(db),
    }


def _vetoes_today(db: Session) -> list[dict]:
    """Today's refused entries (UTC day, server clock) — veto rows are
    risk_events with decision='veto', one tape for sizing caps and rails
    alike. The day boundary is the wall clock on purpose: 'today's vetoes'
    is the operator's question, and the operator's day is UTC here like
    every other clock in the system."""
    from trading.models import RiskEvent as _RE

    day_start = dt.datetime.now(dt.UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        rows = (
            db.execute(
                select(_RE)
                .where(_RE.decision == "veto", _RE.created_at >= day_start)
                .order_by(_RE.id.desc())
                .limit(100)
            )
            .scalars()
            .all()
        )
        return [
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
        return []

@router.get("/signals/today", response_model=TradingSignalsToday)
def signals_today(db: Session = Depends(get_trading_db)) -> dict:
    """Today's emissions including the rejected ones (UTC day, server clock —
    the same wall the vetoes tape uses). The table fills only from the kernel
    desk's recording seam; a database whose engine predates it answers empty,
    and empty is honest twice over: no engine ran, or no strategy spoke."""
    from trading.models import SignalRecord

    day_start = dt.datetime.now(dt.UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        names = set(inspect(db.bind).get_table_names())
    except SQLAlchemyError:
        names = set()
    if "signals" not in names:
        return {"date": day_start.date().isoformat(), "signals": []}
    try:
        rows = (
            db.execute(
                select(SignalRecord)
                .where(SignalRecord.created_at >= day_start)
                .order_by(SignalRecord.id.desc())
                .limit(500)
            )
            .scalars()
            .all()
        )
    except (OperationalError, SQLAlchemyError):
        rows = []
    return {
        "date": day_start.date().isoformat(),
        "signals": [
            {
                "id": r.id,
                "created_at": _as_iso(r.created_at),
                "bot": r.bot,
                "symbol": r.symbol,
                "timeframe": r.timeframe,
                "bar_time": _as_iso(r.bar_time),
                "side": r.side,
                "confidence": r.confidence,
                "outcome": r.outcome,
                "details": json.loads(r.details_json or "{}"),
            }
            for r in rows
        ],
    }


@router.get("/strategy-panels", response_model=list[TradingStrategyPanel])
def strategy_panels(db: Session = Depends(get_trading_db)) -> list[dict]:
    """Per-bot panel data for TRADING OPS: the cumulative realized net pnl
    curve per bot, derived from the desk's own closed trades — equity_points
    rows are portfolio-wide by design, so a per-bot equity figure would be an
    allocation fiction; realized pnl is not. Empty bots are simply absent."""
    if not _tables_present(db):
        return []
    try:
        rows = (
            db.execute(select(Trade).order_by(Trade.exit_time))
            .scalars()
            .all()
        )
    except (OperationalError, SQLAlchemyError):
        return []
    by_bot: dict[str, list] = {}
    for t in rows:
        by_bot.setdefault(t.bot, []).append(t)
    out = []
    for bot in sorted(by_bot):
        cumulative = 0.0
        curve = []
        for t in by_bot[bot]:
            cumulative += t.pnl
            curve.append({"t": _as_iso(t.exit_time), "equity": round(cumulative, 6)})
        out.append({"bot": bot, "curve": curve, "trades_count": len(by_bot[bot])})
    return out


@router.get("/validation-queue", response_model=TradingValidationQueue)
def validation_queue(db: Session = Depends(get_trading_db)) -> dict:
    """The RESEARCH validation queue: versions sitting in research state —
    registered, never promoted past the gate — beside the gate's failures
    with the reasons it wrote. Both empty is honest: nothing in flight,
    nothing failed."""
    if not _tables_present(db):
        return {"awaiting": [], "failures": []}
    awaiting: list[dict] = []
    failures: list[dict] = []
    try:
        versions = db.execute(select(StrategyVersion)).scalars().all()
        states = db.execute(select(StrategyState).order_by(StrategyState.id)).scalars().all()
    except (OperationalError, SQLAlchemyError):
        versions, states = [], []
    latest: dict[int, StrategyState] = {}
    for s in states:
        latest[s.version_id] = s
    from trading.models import Strategy as StrategyRow

    keys = {}
    try:
        keys = {s.id: s.key for s in db.execute(select(StrategyRow)).scalars().all()}
    except (OperationalError, SQLAlchemyError):
        keys = {}
    for v in versions:
        st = latest.get(v.id)
        if st is not None and st.state == "research":
            awaiting.append(
                {
                    "kind": "awaiting",
                    "version_id": v.id,
                    "strategy_key": keys.get(v.strategy_id),
                    "version": v.version,
                    "timeframe": v.timeframe,
                    "validation_id": None,
                    "bot": None,
                    "verdict": None,
                    "reasons": [],
                    "created_at": _as_iso(st.created_at),
                    "permutation_p": None,
                    "trades_n": None,
                    "min_trades_required": None,
                }
            )
    try:
        failed = (
            db.execute(
                select(BacktestValidation)
                .where(BacktestValidation.verdict != "validated")
                .order_by(BacktestValidation.id.desc())
                .limit(50)
            )
            .scalars()
            .all()
        )
    except (OperationalError, SQLAlchemyError):
        failed = []
    for v in failed:
        failures.append(
            {
                "kind": "failure",
                "version_id": None,
                "strategy_key": None,
                "version": None,
                "timeframe": v.timeframe,
                "validation_id": v.id,
                "bot": v.bot,
                "verdict": v.verdict,
                "reasons": json.loads(v.reasons_json or "[]"),
                "created_at": _as_iso(v.created_at),
                "permutation_p": v.permutation_p,
                "trades_n": v.trades_n,
                "min_trades_required": v.min_trades_required,
            }
        )
    return {"awaiting": awaiting, "failures": failures}


@router.get("/model-registry", response_model=TradingModelRegistry)
def model_registry(db: Session = Depends(get_trading_db)) -> dict:
    """The ML model registry: every version with its OOS evidence and its
    role — champion (the gate's live weights), challenger (the newest version
    of a name that is not the champion), retired (everything else). PSI drift
    is NOT a column today: the retrain cycle computes it and it travels in
    the supervisor insight's text — null on the wire is the documented,
    honest answer rather than a parsed-out-of-prose fiction."""
    from trading.models import ModelVersion

    psi_note = (
        "PSI drift is computed per retrain cycle and recorded inside the supervisor "
        "insight's text, never as a column — the registry answers it as null "
        "rather than parsing prose. Persisting it is a schema change, not a panel."
    )
    try:
        names = set(inspect(db.bind).get_table_names())
    except SQLAlchemyError:
        names = set()
    if "model_versions" not in names:
        return {"models": [], "psi_note": psi_note}
    try:
        rows = (
            db.execute(select(ModelVersion).order_by(ModelVersion.name, ModelVersion.version.desc()))
            .scalars()
            .all()
        )
    except (OperationalError, SQLAlchemyError):
        rows = []
    # challenger: the newest version of its name, when it is not the champion
    newest: dict[str, int] = {}
    for r in rows:
        newest.setdefault(r.name, r.version)
    out = []
    for r in rows:
        if r.is_champion:
            role = "champion"
        elif r.version == newest.get(r.name):
            role = "challenger"
        else:
            role = "retired"
        out.append(
            {
                "id": r.id,
                "name": r.name,
                "version": r.version,
                "trained_at": _as_iso(r.trained_at),
                "train_window_days": r.train_window_days,
                "oos_accuracy": r.oos_accuracy,
                "oos_precision_long": r.oos_precision_long,
                "is_champion": r.is_champion,
                "role": role,
                "psi_drift": None,
                "notes": r.notes or "",
            }
        )
    return {"models": out, "psi_note": psi_note}

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
        # nullable columns on databases migrated from before slice 5 read
        # as missing attributes on very old engines — getattr, never an
        # invented zero
        "entry_dev_ticks": getattr(row, "entry_dev_ticks", None),
        "entry_ref_price": getattr(row, "entry_ref_price", None),
        "entry_lag_bars": getattr(row, "entry_lag_bars", None),
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
    # the provenance drill-down: each trade's signal row, joined on the
    # anchor the desk writes at close time (bot + signal bar timestamp).
    # Rows written before the seam have no anchor and honestly no chain —
    # signal_time null, empty dict, never a guessed linkage.
    anchors: dict[tuple, dict] = {}
    try:
        names = set(inspect(db.bind).get_table_names())
    except SQLAlchemyError:
        names = set()
    if "signals" in names:
        try:
            from trading.models import SignalRecord

            sig_rows = (
                db.execute(
                    select(SignalRecord)
                    .where(SignalRecord.outcome == "entered")
                    .order_by(SignalRecord.id)
                )
                .scalars()
                .all()
            )
            for s in sig_rows:
                # newest write wins a same-bar collision, matching the desk's
                # restart semantics — the last decision is the one that traded
                anchors[(s.bot, _aware(s.bar_time))] = {
                    "outcome": s.outcome,
                    "confidence": s.confidence,
                    "details": json.loads(s.details_json or "{}"),
                }
        except (OperationalError, SQLAlchemyError):
            anchors = {}

    def _chain(t) -> dict:
        st = getattr(t, "signal_time", None)
        if st is None:
            return {}
        return anchors.get((t.bot, _aware(st))) or {}

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
            "entry_dev_ticks": getattr(t, "entry_dev_ticks", None),
            "exit_dev_ticks": getattr(t, "exit_dev_ticks", None),
            "entry_lag_bars": getattr(t, "entry_lag_bars", None),
            "signal_time": _as_iso(getattr(t, "signal_time", None)),
            "signal_chain": _chain(t),
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
    # The equity fan lives in the validation row's full results JSON —
    # validation_json.monte_carlo.equity_paths, written by the pipeline with
    # the percentile bands and sample paths when the simulation size kept the
    # path matrix (validation/validation.py documents the cutoff). Null means
    # exactly what it means everywhere else here: never recorded, or the
    # matrix was honestly too large to keep — never an invented fan.
    fan = None
    if validation is not None and validation.validation_json:
        try:
            full = json.loads(validation.validation_json)
            fan = (full.get("monte_carlo") or {}).get("equity_paths") or None
        except (ValueError, TypeError):
            fan = None
    payload["equity_fan"] = fan
    return payload


def _registry_bot_key(bot: str) -> str | None:
    """The catalog key a registry-booted bot name encodes: `<key>-v<N>`
    (optionally `-<symbol>` for multi-symbol universes, per the runner's
    naming). None for pre-registry residents — their trades are provenance
    of the pre-registry era and have no validation reference to compare
    against, which the endpoint reports honestly as no distribution."""
    import re

    m = re.match(r"^([a-z0-9_]+)-v(\d+)(?:-[a-z0-9]+)?$", bot)
    return m.group(1) if m else None


@router.get("/divergence", response_model=TradingDivergenceStatus)
def trading_divergence(db: Session = Depends(get_trading_db)) -> dict:
    """The slice-5 divergence surface: per bot, the declared budget, the live
    feed counters, the aggregated per-fill drift evidence, and the paper-vs-
    backtest distributional comparison when the data volume makes it
    meaningful (n≥30 on BOTH sides — the validation gate's own statistical
    bar; smaller samples are reported as insufficient, never as fake
    statistics).

    Sources, honestly separated: budgets and feed counters come from the
    desk runner's rail snapshots (kernel memory is the truth, the snapshot
    its rendering), per-fill evidence aggregates the trade rows the desk
    wrote at fill time. Bots present in neither surface simply do not
    appear — an engine that never ran has no divergence to measure, and
    empty is the first-class answer."""
    from trading.divergence import compare_distributions
    from trading.models import BacktestValidation as _BV
    from trading.models import RiskEvent, get_state

    if not _tables_present(db):
        return {"bots": [], "breach_events": []}

    # ---- snapshot-derived budgets and counters
    snaps: dict[str, dict] = {}
    try:
        names = [
            row.name
            for row in db.execute(select(BotStatus)).scalars()
            if row.name.startswith("__state_rails/")
        ]
        for name in names:
            bot = name[len("__state_rails/"):]
            snap = get_state(db, f"rails/{bot}", None)
            if isinstance(snap, dict):
                snaps[bot] = snap
    except (OperationalError, SQLAlchemyError):
        snaps = {}

    # ---- per-fill evidence over the closed-trade rows
    trades: dict[str, list] = {}
    try:
        rows = db.execute(select(Trade).order_by(Trade.exit_time)).scalars().all()
        for t in rows:
            trades.setdefault(t.bot, []).append(t)
    except OperationalError:
        rows = []

    # ---- open positions, per bot
    open_positions: dict[str, list[dict]] = {}
    try:
        now = dt.datetime.now(dt.UTC)
        for row in db.execute(select(OpenPosition)).scalars().all():
            open_positions.setdefault(row.bot, []).append(_position_payload(row, now))
    except OperationalError:
        pass

    bots: list[dict] = []
    for bot in sorted(set(snaps) | set(trades) | set(open_positions)):
        snap = snaps.get(bot, {})
        div = snap.get("divergence") if isinstance(snap.get("divergence"), dict) else {}
        rows = trades.get(bot, [])

        devs: list[float] = []
        lags: list[int] = []
        for t in rows:
            for v in (getattr(t, "entry_dev_ticks", None), getattr(t, "exit_dev_ticks", None)):
                if v is not None:
                    devs.append(abs(v))
            lag = getattr(t, "entry_lag_bars", None)
            if lag is not None:
                lags.append(lag)
        measured = len(devs)
        budget_dev = div.get("budget_dev_ticks")
        breaches = 0
        if budget_dev is not None:
            for t in rows:
                for v in (getattr(t, "entry_dev_ticks", None), getattr(t, "exit_dev_ticks", None)):
                    if v is not None and abs(v) > budget_dev:
                        breaches += 1
                lag = getattr(t, "entry_lag_bars", None)
                lag_budget = div.get("budget_entry_lag_bars")
                if lag is not None and lag_budget is not None and lag > lag_budget:
                    breaches += 1

        # the distributional comparison — registry-booted bots only, against
        # the validation run whose verdict put the version into paper. Both
        # sides need n≥30 (trading/divergence.py owns the gate); anything
        # less is reported with the reason, never as statistics.
        distribution = None
        distribution_note = "no validation reference — the bot is not registry-booted"
        key = _registry_bot_key(bot)
        if key is not None:
            validation = (
                db.execute(
                    select(_BV)
                    .where(_BV.bot == key, _BV.verdict == "validated")
                    .order_by(_BV.id.desc())
                    .limit(1)
                )
                .scalars()
                .first()
            )
            if validation is None or validation.run_id is None:
                distribution_note = "no validated backtest reference exists for this version"
            else:
                run = db.get(BacktestRun, validation.run_id)
                bt_trades = json.loads(run.trades_json) if run is not None and run.trades_json else []
                bt_pnls = [float(tr["pnl"]) for tr in bt_trades if isinstance(tr, dict) and "pnl" in tr]
                paper_pnls = [float(t.pnl) for t in rows]
                distribution = compare_distributions(bt_pnls, paper_pnls)
                if distribution is None:
                    distribution_note = (
                        f"insufficient data for a distributional comparison "
                        f"(backtest {len(bt_pnls)} trades, paper {len(paper_pnls)} — "
                        f"the statistical bar is 30 per side, the same the validation gate sets)"
                    )

        bots.append(
            {
                "bot": bot,
                "budget_dev_ticks": budget_dev,
                "budget_entry_lag_bars": div.get("budget_entry_lag_bars"),
                "budget_missed_bars": div.get("budget_missed_bars"),
                "missed_bars": div.get("missed_bars"),
                "backfilled_bars": div.get("backfilled_bars"),
                "open_positions": open_positions.get(bot, []),
                "fills": {
                    "measured_fills": measured,
                    "mean_abs_dev_ticks": (sum(devs) / len(devs)) if devs else None,
                    "max_abs_dev_ticks": max(devs) if devs else None,
                    "max_entry_lag_bars": max(lags) if lags else None,
                    "breaches": breaches,
                },
                "distribution": distribution,
                "distribution_note": distribution_note,
            }
        )

    breach_events: list[dict] = []
    try:
        rows_events = (
            db.execute(
                select(RiskEvent)
                .where(RiskEvent.rail == "divergence_budget")
                .order_by(RiskEvent.id.desc())
                .limit(25)
            )
            .scalars()
            .all()
        )
        breach_events = [
            {
                "id": r.id,
                "created_at": _as_iso(r.created_at),
                "bot": r.bot,
                "symbol": r.symbol,
                "rail": r.rail,
                "decision": r.decision,
                "inputs": json.loads(r.inputs_json or "{}"),
            }
            for r in rows_events
        ]
    except (OperationalError, SQLAlchemyError):
        breach_events = []

    return {"bots": bots, "breach_events": breach_events}


# --------------------------------------------------------------------------
# M4 — the first write paths of this router. Everything above describes the
# engine; everything below is the operator's hands on it. Two rules shape
# both endpoints: a control that cannot audit itself is not a control, and
# a refusal is an answer, never an exception the client has to guess at.


def _require_trading_tables(db: Session) -> None:
    """Write endpoints fail closed when the schema is absent — unlike the
    read endpoints, which degrade to empty, a write into a database that
    cannot hold it is not an honest offline answer but a 503."""
    if not _tables_present(db):
        raise HTTPException(
            status_code=503,
            detail="no trading tables in this database — the control surface has nowhere durable to write",
        )


@router.post("/kill-switch", response_model=KillSwitchState)
def set_kill_switch(req: KillSwitchRequest, db: Session = Depends(get_trading_db)) -> dict:
    """The manual kill-switch — write path of the row the kernel polls
    fail-closed at entry cadence (trading/risk.py `__killswitch` on
    BotStatus; the desk's manual_halt_check reads it before every entry).

    Direction is asymmetric on purpose: throwing the switch ON is always
    allowed and immediate, note optional — in that direction speed beats
    paperwork, and halting is the safe failure. Re-arming (enabled=false)
    is the dangerous direction, so it demands the operator's sentence: the
    note is mandatory, enforced here server-side, and both directions write
    a risk_events audit row — the control tape and the rail tape are one
    tape, so a veto read next to the switch's throw explains itself without
    a second panel. Entries halt immediately; protective exits always keep
    flowing, because the switch refuses entries, never safety."""
    _require_trading_tables(db)
    note = req.note.strip()
    if not req.enabled and not note:
        raise HTTPException(
            status_code=422,
            detail="re-arming the kill-switch requires a note — the audit row deserves the operator's own sentence for why",
        )
    ks_row = db.get(BotStatus, "__killswitch")
    if ks_row is None:
        ks_row = BotStatus(name="__killswitch", running=True, mode="risk", note="")
        db.add(ks_row)
    ks_row.running = not req.enabled
    ks_row.note = note or ("manual kill-switch " + ("ON" if req.enabled else "OFF"))
    # the audit seam: risk_events with rail manual_killswitch, decision
    # tripped/cleared, bot __control__ — the control surface as its own
    # actor on the same tape the rails write. Chosen over a separate
    # control_audit table because the events strip already renders this
    # table live, and the one-tape ordering is the honest provenance.
    db.add(
        RiskEvent(
            bot="__control__",
            symbol="",
            rail="manual_killswitch",
            decision="tripped" if req.enabled else "cleared",
            inputs_json=json.dumps(
                {
                    "actor": "operator-ui",
                    "note": note,
                    "direction": "on" if req.enabled else "off",
                }
            ),
        )
    )
    db.commit()
    return {"tripped": req.enabled, "note": ks_row.note}


# ---- the lifecycle registry surface --------------------------------------


def _bot_name(strategy_key: str, version: int) -> str:
    return f"{strategy_key}-v{version}"


def _track_record(db: Session, bot: str) -> dict:
    """The paper track record of one registry-booted bot: every closed
    paper trade of the `<key>-v<N>` name. Explicit nulls over an empty set —
    zero trades is a fact, zero pnl over zero trades would be a fiction."""
    try:
        rows = (
            db.execute(
                select(Trade).where(Trade.bot == bot).order_by(Trade.exit_time)
            )
            .scalars()
            .all()
        )
    except (OperationalError, SQLAlchemyError):
        rows = []
    if not rows:
        return {
            "trades_count": 0,
            "realized_pnl": None,
            "span_days": None,
            "first_exit_at": None,
            "last_exit_at": None,
            "drift_fills_measured": 0,
            "drift_breaches": 0,
        }
    measured = 0
    breaches = 0
    for t in rows:
        for v in (t.entry_dev_ticks, t.exit_dev_ticks):
            if v is not None:
                measured += 1
        # breach accounting is the budget's business; here the card counts
        # fills whose measured dev exists — the budget comparison itself is
        # the divergence surface's job, and double-counting it here would
        # invent precision the row does not carry. Drift breaches are read
        # from the events tape instead (below), the rail's own verdicts.
    try:
        breach_rows = db.execute(
            select(RiskEvent.id).where(
                RiskEvent.bot == bot, RiskEvent.rail == "divergence_budget"
            )
        ).all()
        breaches = len(breach_rows)
    except (OperationalError, SQLAlchemyError):
        breaches = 0
    first, last = rows[0].exit_time, rows[-1].exit_time
    span = (last - first).total_seconds() / 86400.0 if first and last else None
    return {
        "trades_count": len(rows),
        "realized_pnl": sum(t.pnl for t in rows),
        "span_days": span,
        "first_exit_at": first,
        "last_exit_at": last,
        "drift_fills_measured": measured,
        "drift_breaches": breaches,
    }


def _fingerprint_of(
    version_id: int,
    state: str,
    validation_id: int | None,
    record: dict,
    code_hash: str,
) -> str:
    """The staleness fingerprint: one digest over every input the approval
    card displays. ANY movement — a trade settled, a breach recorded, the
    state row advanced — changes the digest, and a confirmation carrying
    the old digest is a 409. Re-basing is impossible because the digest is
    recomputed, never stored: the card cannot be tricked into approving a
    snapshot of itself."""
    import hashlib

    payload = {
        "version_id": version_id,
        "state": state,
        "validation_id": validation_id,
        "code_hash": code_hash,
        "trades_count": record["trades_count"],
        "realized_pnl": record["realized_pnl"],
        "span_days": record["span_days"],
        "last_exit_at": record["last_exit_at"].isoformat() if record["last_exit_at"] else None,
        "drift_breaches": record["drift_breaches"],
        "drift_fills_measured": record["drift_fills_measured"],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _validation_ref(db: Session, version_id: int) -> int | None:
    """The validation row behind research→validated, parsed out of the state
    chain's evidence — the evidence string is the chain of custody, and the
    card quotes it rather than re-deriving it."""
    rows = (
        db.execute(
            select(StrategyState)
            .where(StrategyState.version_id == version_id)
            .order_by(StrategyState.id)
        )
        .scalars()
        .all()
    )
    for row in rows:
        if row.evidence.startswith("validation:"):
            try:
                return int(row.evidence.split(":", 1)[1])
            except ValueError:
                return None
    return None


def _registry_payload(db: Session) -> list[dict]:
    from trading.models import Strategy as StrategyRow

    strategies = {s.id: s for s in db.execute(select(StrategyRow)).scalars().all()}
    versions = db.execute(select(StrategyVersion)).scalars().all()
    out: list[dict] = []
    for v in sorted(versions, key=lambda x: x.id):
        strategy = strategies.get(v.strategy_id)
        if strategy is None:
            continue
        states = (
            db.execute(
                select(StrategyState)
                .where(StrategyState.version_id == v.id)
                .order_by(StrategyState.id)
            )
            .scalars()
            .all()
        )
        if not states:
            continue
        latest = states[-1]
        validation_id = _validation_ref(db, v.id)
        bot = _bot_name(strategy.key, v.version)
        record = _track_record(db, bot)
        fingerprint = _fingerprint_of(v.id, latest.state, validation_id, record, v.code_hash)
        out.append(
            {
                "version_id": v.id,
                "strategy_key": strategy.key,
                "name": strategy.name,
                "version": v.version,
                "state": latest.state,
                "params": json.loads(v.params_json or "{}"),
                "timeframe": v.timeframe,
                "universe": json.loads(v.universe_json or "[]"),
                "code_hash": v.code_hash,
                "validation_id": validation_id,
                "state_since": latest.created_at,
                "state_evidence": latest.evidence or "",
                "track_record": record,
                "fingerprint": fingerprint,
                # the only human-gated transition the design opens in this
                # milestone: paper → candidate_live. candidate_live → live is
                # structurally impossible in M3 (the mandate is M5), so no
                # card is ever offered for it — an offer the registry must
                # refuse would be a lie in chrome.
                "pending_transition": "candidate_live" if latest.state == "paper" else None,
            }
        )
    return out


@router.get("/registry", response_model=TradingRegistry)
def trading_registry(db: Session = Depends(get_trading_db)) -> dict:
    """Every registered strategy version with state, evidence chain, paper
    track record and staleness fingerprint. Empty is the first-class answer:
    with zero validated strategies the lifecycle owns nothing — the gate
    working, not a missing panel."""
    if not _tables_present(db):
        return {"versions": []}
    try:
        return {"versions": _registry_payload(db)}
    except (OperationalError, SQLAlchemyError):
        return {"versions": []}


@router.post("/registry/{version_id}/approve", response_model=TradingApprovalResult)
def approve_version(version_id: int, req: ApproveRequest, db: Session = Depends(get_trading_db)) -> dict:
    """The paper → candidate_live approval card, exactly as design §6 layer 1
    demands: human, mandatory, one click, re-basing impossible.

    The card's contract: the body carries the fingerprint GET /registry
    served beside the track record the human reviewed. The fingerprint is
    recomputed from CURRENT rows and compared — a mismatch is 409, "inputs
    moved — review the new track record", and nothing is written. On match
    the approval row is written first (the durable assent, the audit) and
    the registry's transition() applies its own guards; a refusal there is
    surfaced honestly as 409 with the guard's reason, and both writes roll
    back together — a half-written approval would be a forged card."""
    _require_trading_tables(db)
    from trading.registry import TransitionRefused, transition

    try:
        rows = _registry_payload(db)
    except (OperationalError, SQLAlchemyError):
        rows = []
    row = next((r for r in rows if r["version_id"] == version_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail=f"strategy version {version_id} is not registered")
    if row["pending_transition"] != "candidate_live":
        raise HTTPException(
            status_code=409,
            detail=(
                f"version {version_id} is in state {row['state']!r} — the only approvable card "
                f"is paper → candidate_live, offered only on paper versions"
            ),
        )
    if req.fingerprint != row["fingerprint"]:
        raise HTTPException(
            status_code=409,
            detail=(
                "inputs moved — the track record, state or drift counters changed since this "
                "card was rendered. Review the new track record; re-basing is impossible."
            ),
        )
    note = req.note.strip()
    db.add(
        Approval(
            version_id=version_id,
            transition="paper->candidate_live",
            approved_by="operator-ui",
            note=note,
        )
    )
    db.flush()
    try:
        state_row = transition(
            db, version_id, "candidate_live", note=note or "approval card confirmed"
        )
    except TransitionRefused as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"the registry refused the transition: {exc}") from exc
    db.commit()
    evidence_id = 0
    if ":" in state_row.evidence:
        try:
            evidence_id = int(state_row.evidence.split(":", 1)[1])
        except ValueError:
            evidence_id = 0
    return {
        "approval_id": evidence_id,
        "state": state_row.state,
        "evidence": state_row.evidence,
        "fingerprint": req.fingerprint,
    }


# --------------------------------------------------------------------------
# M5 — the mandate machinery, built but never armed.
#
# The endpoints below are the ONLY write paths into the mandate layer, and
# every one of them is human-shaped: the mandate's caps are echoed in full
# in the request body (the human types the numbers — a consent the machine
# prefilled is no consent), the signoff names the audit document, the card
# confirmation carries its fingerprint. There is no automation path to any
# of them: the AI rule extends to trading as "the model may never touch a
# mandate" (design §6). The honest-empty answer is first-class everywhere:
# in M5's expected end state no mandate exists and no card has ever been
# exercised, and that emptiness is the design working, not a missing panel.


def _mandate_payload(row) -> dict:
    from trading.mandate import mandate_expiry, mandate_integrity_ok

    expiry = mandate_expiry(row)
    now = dt.datetime.now(dt.UTC)
    return {
        "id": row.id,
        "version_id": row.version_id,
        "created_at": row.created_at,
        "created_by": row.created_by,
        "max_order_notional": row.max_order_notional,
        "max_exposure": row.max_exposure,
        "instruments": json.loads(row.instruments_json or "[]"),
        "max_trades_per_day": row.max_trades_per_day,
        "consent_days": row.consent_days,
        "funding_min": row.funding_min,
        "funding_max": row.funding_max,
        "note": row.note,
        "mandate_hash": row.mandate_hash,
        "expires_at": expiry,
        "active": expiry > now,
        "integrity_ok": mandate_integrity_ok(row),
    }


@router.get("/mandates", response_model=TradingMandates)
def list_mandates(db: Session = Depends(get_trading_db)) -> dict:
    """Every mandate row ever written, newest first — immutability means
    history is part of the surface: a superseded mandate is still the
    consent older decisions stood on. Empty is the honest M5 end state:
    no mandate exists, the live path is unbuilt by design."""
    if not _tables_present(db):
        return {"mandates": []}
    try:
        from trading.models import StrategyMandate

        rows = (
            db.execute(select(StrategyMandate).order_by(StrategyMandate.id.desc()))
            .scalars()
            .all()
        )
        return {"mandates": [_mandate_payload(r) for r in rows]}
    except (OperationalError, SQLAlchemyError):
        return {"mandates": []}


@router.post("/mandates", response_model=TradingMandates)
def create_mandate_endpoint(req: MandateCreateRequest, db: Session = Depends(get_trading_db)) -> dict:
    """The human confirmation flow — the ONLY write path for mandates.

    The full cap set must arrive in the body, typed by the human. Every cap
    is a required field because the mandate IS the consent: a machine that
    fills in the numbers for you manufactures permission nobody granted.
    There is no update path anywhere — a new mandate is a new row
    superseding the old by id, so the audit chain can always quote exactly
    which consent an order stood on. The write lands in the audit ledger
    (actor 'human') in the same transaction: a mandate without its audit
    row is a half-written consent, and half-written consent is nothing."""
    _require_trading_tables(db)
    from trading.mandate import append_audit, create_mandate

    version = db.get(StrategyVersion, req.version_id)
    if version is None:
        raise HTTPException(status_code=404, detail=f"strategy version {req.version_id} is not registered")
    if not req.instruments:
        raise HTTPException(status_code=422, detail="instruments must name at least one symbol — an empty list is a mandate over nothing")
    for cap, name in (
        (req.max_order_notional, "max_order_notional"),
        (req.max_exposure, "max_exposure"),
        (req.funding_max, "funding_max"),
    ):
        if cap <= 0:
            raise HTTPException(status_code=422, detail=f"{name} must be positive — a zero cap is a refusal, not a mandate")
    if req.funding_min < 0 or req.funding_min >= req.funding_max:
        raise HTTPException(status_code=422, detail="funding bounds are incoherent — funding_min must be below funding_max")
    if req.max_trades_per_day <= 0:
        raise HTTPException(status_code=422, detail="max_trades_per_day must be positive")
    row = create_mandate(
        db,
        version_id=req.version_id,
        caps={
            "max_order_notional": req.max_order_notional,
            "max_exposure": req.max_exposure,
            "instruments": req.instruments,
            "max_trades_per_day": req.max_trades_per_day,
            "consent_days": req.consent_days,
            "funding_min": req.funding_min,
            "funding_max": req.funding_max,
        },
        created_by="operator-ui",
        note=req.note.strip(),
    )
    append_audit(
        db,
        "human",
        "mandate_created",
        {
            "mandate_id": row.id,
            "version_id": req.version_id,
            "mandate_hash": row.mandate_hash,
            "caps": {
                "max_order_notional": row.max_order_notional,
                "max_exposure": row.max_exposure,
                "instruments": json.loads(row.instruments_json),
                "max_trades_per_day": row.max_trades_per_day,
                "consent_days": row.consent_days,
                "funding_min": row.funding_min,
                "funding_max": row.funding_max,
            },
            "note": row.note,
        },
    )
    db.commit()
    return {"mandates": [_mandate_payload(row)]}


def _card_fingerprint(db: Session, version_id: int, mandate_id: int | None) -> str:
    """The card's staleness fingerprint: strategy state + mandate version,
    NEVER the live price — design §6 layer 3 verbatim: a card does not
    expire because the market moves. Recomputed at confirmation, never
    trusted from the client: re-basing impossible because the digest is
    derived, not stored, exactly like the registry approval cards."""
    import hashlib

    states = (
        db.execute(
            select(StrategyState)
            .where(StrategyState.version_id == version_id)
            .order_by(StrategyState.id)
        )
        .scalars()
        .all()
    )
    latest_state = states[-1].state if states else "none"
    state_rows = len(states)
    payload = {
        "version_id": version_id,
        "lifecycle_state": latest_state,
        "state_rows": state_rows,
        "mandate_id": mandate_id,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


def _card_payload(row) -> dict:
    return {
        "id": row.id,
        "version_id": row.version_id,
        "mandate_id": row.mandate_id,
        "created_at": row.created_at,
        "symbol": row.symbol,
        "side": row.side,
        "notional": row.notional,
        "chain": json.loads(row.chain_json or "{}"),
        "fingerprint": row.fingerprint,
        "state": row.state,
        "decided_at": row.decided_at,
        "decision_note": row.decision_note,
    }


@router.get("/order-cards", response_model=TradingOrderCards)
def list_order_cards(db: Session = Depends(get_trading_db)) -> dict:
    """Every order card, newest first. Empty is first-class: in M5 cards
    exist only when exercised — the paper path never creates them, by design
    layer 3 (per-order approval would make paper worthless as a test)."""
    if not _tables_present(db):
        return {"cards": []}
    try:
        from trading.models import OrderCard

        rows = db.execute(select(OrderCard).order_by(OrderCard.id.desc())).scalars().all()
        return {"cards": [_card_payload(r) for r in rows]}
    except (OperationalError, SQLAlchemyError):
        return {"cards": []}


@router.post("/order-cards", response_model=TradingOrderCards)
def create_order_card(req: OrderCardCreateRequest, db: Session = Depends(get_trading_db)) -> dict:
    """An order intent becomes a card (design §6 layer 3). The fingerprint
    binds the card to the CURRENT strategy state and the active mandate's
    id — confirm after either moved and the answer is 409. In M5 nothing
    automatic creates cards; the endpoint exists so the flow is exercisable
    and testable, and the release terminates at the guard chain because no
    live adapter exists."""
    _require_trading_tables(db)
    from trading.mandate import active_mandate, append_audit
    from trading.models import OrderCard

    version = db.get(StrategyVersion, req.version_id)
    if version is None:
        raise HTTPException(status_code=404, detail=f"strategy version {req.version_id} is not registered")
    mandate = active_mandate(db, req.version_id)
    fingerprint = _card_fingerprint(db, req.version_id, mandate.id if mandate else None)
    row = OrderCard(
        version_id=req.version_id,
        mandate_id=mandate.id if mandate else None,
        symbol=req.symbol,
        side=req.side,
        notional=req.notional,
        chain_json=json.dumps(req.chain, sort_keys=True),
        fingerprint=fingerprint,
        state="open",
    )
    db.add(row)
    db.flush()
    append_audit(
        db,
        "system",
        "order_card_created",
        {
            "card_id": row.id,
            "version_id": req.version_id,
            "mandate_id": row.mandate_id,
            "symbol": req.symbol,
            "side": req.side,
            "notional": req.notional,
            "fingerprint": fingerprint,
        },
    )
    db.commit()
    return {"cards": [_card_payload(row)]}


@router.post("/order-cards/{card_id}/confirm", response_model=TradingOrderCards)
def confirm_order_card(card_id: int, req: OrderCardConfirmRequest, db: Session = Depends(get_trading_db)) -> dict:
    """Confirming the card releases the order — in live. In M5 the release
    terminates at the guard chain evaluation: the chain runs against the
    card's mandate with the sentinel in force, its verdict lands in the
    audit ledger (actor 'guard'), and the card's state records what the
    chain said. No venue ever sees anything — no live adapter exists.

    The 409 discipline is the registry's exactly: the fingerprint is
    recomputed from current rows, a mismatch means inputs moved, review the
    new card, re-basing impossible. A decided card is immutable — a second
    confirmation is a 409, never a re-decision."""
    _require_trading_tables(db)
    from trading.mandate import GuardState, OrderIntent, append_audit, evaluate_order
    from trading.models import OrderCard, StrategyMandate

    row = db.get(OrderCard, card_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"order card {card_id} does not exist")
    if row.state != "open":
        raise HTTPException(
            status_code=409,
            detail=f"order card {card_id} is already {row.state} — a card is decided exactly once",
        )
    # the fingerprint recomputes against the CURRENTLY active mandate, not the
    # one the card was created with — a mandate granted, superseded or lapsed
    # since is exactly the movement the 409 exists to catch.
    from trading.mandate import active_mandate as _active_mandate

    _mandate_now = _active_mandate(db, row.version_id)
    current_fp = _card_fingerprint(db, row.version_id, _mandate_now.id if _mandate_now else None)
    if req.fingerprint != row.fingerprint or current_fp != row.fingerprint:
        raise HTTPException(
            status_code=409,
            detail=(
                "inputs moved — the strategy state or the mandate changed since this card was "
                "rendered. Review the new state; re-basing is impossible."
            ),
        )
    mandate = db.get(StrategyMandate, row.mandate_id) if row.mandate_id else None
    # the chain at its real boundary: the sentinel path the desk uses, the
    # card's intent, an empty exposure book (no live positions exist in M5 —
    # the chain measures what it's given, and M5 gives it the truth).
    sentinel = str(Path(get_settings().data_dir) / "HALT")
    verdict = evaluate_order(
        mandate,
        OrderIntent(symbol=row.symbol, side=row.side, notional=row.notional),
        GuardState(),
        sentinel_path=sentinel,
        session=db,
    )
    now = dt.datetime.now(dt.UTC)
    row.decided_at = now
    row.decision_note = req.note.strip() or verdict.reason[:250]
    if verdict.allowed:
        # 'released' means the guard chain allowed it — full stop. No live
        # adapter exists; the card flow terminates here, by design.
        row.state = "released"
    elif verdict.verdict == "reauth":
        row.state = "confirmed"  # decided, but held for re-consent — not released
    else:
        row.state = "denied"
    db.flush()
    append_audit(
        db,
        "human",
        "order_card_decided",
        {
            "card_id": row.id,
            "decision": row.state,
            "guard_verdict": verdict.verdict,
            "guard_check": verdict.check,
            "note": req.note.strip(),
        },
    )
    db.commit()
    return {"cards": [_card_payload(row)]}


@router.post("/audit-signoffs")
def create_audit_signoff(req: AuditSignoffCreateRequest, db: Session = Depends(get_trading_db)) -> dict:
    """The human's recorded signoff of the written live-readiness audit —
    the second independent gate on candidate_live → live, alongside the
    mandate. The document reference is mandatory and validated non-empty:
    a signoff that names no document certifies nothing. No signoff exists
    today by design — writing one is the owner's act, AFTER the audit
    document exists; this endpoint existing is not an invitation, it is the
    seam the owner's act will use."""
    _require_trading_tables(db)
    from trading.mandate import append_audit
    from trading.models import AuditSignoff

    version = db.get(StrategyVersion, req.version_id)
    if version is None:
        raise HTTPException(status_code=404, detail=f"strategy version {req.version_id} is not registered")
    document_ref = req.document_ref.strip()
    note = req.note.strip()
    if not document_ref:
        raise HTTPException(status_code=422, detail="document_ref must name the audit document — a signoff certifying nothing certifies nothing")
    if not note:
        raise HTTPException(status_code=422, detail="the human's note is mandatory — the signoff is a human act or it is nothing")
    row = AuditSignoff(
        version_id=req.version_id,
        created_by="operator-ui",
        document_ref=document_ref,
        note=note,
    )
    db.add(row)
    db.flush()
    append_audit(
        db,
        "human",
        "audit_signoff_recorded",
        {"signoff_id": row.id, "version_id": req.version_id, "document_ref": document_ref, "note": note},
    )
    db.commit()
    return {"signoff_id": row.id, "version_id": req.version_id, "document_ref": document_ref}


@router.get("/audit/verify", response_model=AuditChainVerification)
def verify_audit_chain(db: Session = Depends(get_trading_db)) -> dict:
    """Walk the audit ledger and validate every hash link. Violations name
    the rows — a chain that cannot say WHERE it broke is a rumor, not
    evidence. An intact empty chain is the honest start state."""
    if not _tables_present(db):
        return {"rows": 0, "violations": [], "intact": True}
    try:
        from trading.mandate import verify_chain
        from trading.models import AuditLedger

        violations = verify_chain(db)
        rows = len(db.execute(select(AuditLedger.id)).all())
        return {"rows": rows, "violations": violations, "intact": not violations}
    except (OperationalError, SQLAlchemyError):
        return {"rows": 0, "violations": [], "intact": True}


def _predictions_table_present(db: Session) -> bool:
    """The predictions table is younger than every database it serves. A
    database without it is not an error — it is a scanner that has never
    run there, and the honest answer is empty."""
    try:
        return "predictions" in inspect(db.get_bind()).get_table_names()
    except SQLAlchemyError:
        return False


@router.get("/predictions/latest", response_model=MLPredictionsLatest)
def predictions_latest(db: Session = Depends(get_trading_db)) -> dict:
    """The ML track record's current state: one prediction per (symbol,
    artifact_kind), each carrying its noise scale, noise basis, training
    boundary and caveat — never a bare number. Empty when no scanner has
    ever run: absence is the answer, not an error."""
    if not _predictions_table_present(db):
        return {"predictions": []}
    try:
        from trading.predictions import latest_predictions

        return {"predictions": latest_predictions(db)}
    except (OperationalError, SQLAlchemyError):
        return {"predictions": []}


@router.get("/predictions/track-record", response_model=MLPredictionTrackRecord)
def predictions_track_record(db: Session = Depends(get_trading_db)) -> dict:
    """The scored history aggregated honestly: hit rate over decided
    outcomes only, mean predicted vs mean realized, the pending/scored
    split, and the sample size on every aggregate — a hit rate over four
    outcomes is decoration and is labelled exactly that."""
    from trading.predictions import CAVEAT, SMALL_SAMPLE_N, track_record

    if not _predictions_table_present(db):
        return {"series": [], "small_sample_threshold": SMALL_SAMPLE_N, "caveat": CAVEAT}
    try:
        return track_record(db)
    except (OperationalError, SQLAlchemyError):
        return {"series": [], "small_sample_threshold": SMALL_SAMPLE_N, "caveat": CAVEAT}
