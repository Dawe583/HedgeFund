import datetime as dt
import json
import logging

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    event,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from trading.config import get_settings

log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Candle(Base):
    __tablename__ = "candles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32))
    timeframe: Mapped[str] = mapped_column(String(8))
    open_time: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)

    __table_args__ = (
        Index("ix_candles_sym_tf_time", "symbol", "timeframe", "open_time", unique=True),
    )


class Trade(Base):
    """A completed (closed) round-trip trade executed by a bot."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot: Mapped[str] = mapped_column(String(32))  # hft | scalp
    symbol: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(4))  # long | short
    qty: Mapped[float] = mapped_column(Float)
    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float] = mapped_column(Float)
    entry_time: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    exit_time: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    pnl: Mapped[float] = mapped_column(Float)  # net of fees
    fees: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    mode: Mapped[str] = mapped_column(String(16), default="paper")  # paper|testnet|live
    gate_source: Mapped[str] = mapped_column(String(16), default="legacy")

    @property
    def pnl_pct(self) -> float:
        notional = self.qty * self.entry_price
        return self.pnl / notional if notional else 0.0


class OpenPosition(Base):
    __tablename__ = "open_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot: Mapped[str] = mapped_column(String(32))
    symbol: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(4))
    qty: Mapped[float] = mapped_column(Float)
    entry_price: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float)
    take_profit: Mapped[float] = mapped_column(Float)
    opened_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    gate_source: Mapped[str] = mapped_column(String(16), default="legacy")


class EquityPoint(Base):
    __tablename__ = "equity_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot: Mapped[str] = mapped_column(String(32))  # or "portfolio"
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    equity: Mapped[float] = mapped_column(Float)


class BotStatus(Base):
    __tablename__ = "bot_status"

    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    running: Mapped[bool] = mapped_column(default=False)
    mode: Mapped[str] = mapped_column(String(16), default="paper")
    last_heartbeat: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    note: Mapped[str] = mapped_column(String(256), default="")


class AgentInsight(Base):
    __tablename__ = "agent_insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent: Mapped[str] = mapped_column(String(32), index=True)  # analyst|reviewer|supervisor
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(String(4096))
    severity: Mapped[str] = mapped_column(String(8), default="info")
    tags: Mapped[str] = mapped_column(String(256), default="")
    meta: Mapped[str] = mapped_column(String(2048), default="{}")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_now, index=True
    )


class AgentMemory(Base):
    """Layered memory event for the self-learning agent loop (Hermes/FinMem style).

    Tiers: working (raw outcomes, decays) → shallow (lessons, slow decay)
    → deep (extended reflections, durable). Deep lessons are injected into
    analyst/reviewer prompts so verdicts improve as experience accumulates.
    """

    __tablename__ = "agent_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot: Mapped[str] = mapped_column(String(32), default="*")  # bot name or "*" for all
    tier: Mapped[str] = mapped_column(String(8))  # working | shallow | deep
    kind: Mapped[str] = mapped_column(String(16))  # outcome | lesson | reflection
    content: Mapped[str] = mapped_column(String(1024))
    importance: Mapped[float] = mapped_column(Float, default=0.5)  # 0..1
    pnl_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_now, index=True
    )

    __table_args__ = (Index("ix_memory_tier_bot", "tier", "bot", "created_at"),)


class AgentPrediction(Base):
    """Per-cycle directional forecast by one bot — rendered on the dashboard chart.

    Produced every engine cycle per active bot (HFT-BOT, SCALP-BOT) so the
    user can see how each agent thinks, where it expects price to go and
    with what confidence.
    """

    __tablename__ = "agent_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    bot: Mapped[str] = mapped_column(String(32))  # hft | scalp
    symbol: Mapped[str] = mapped_column(String(32), default="BTCUSDT")
    timeframe: Mapped[str] = mapped_column(String(8))
    direction: Mapped[str] = mapped_column(String(8))  # up | down | flat
    confidence: Mapped[float] = mapped_column(Float)  # 0..1
    expected_move_pct: Mapped[float] = mapped_column(Float, default=0.0)
    horizon_bars: Mapped[int] = mapped_column(Integer, default=6)
    price_at_ts: Mapped[float] = mapped_column(Float)
    reasoning: Mapped[str] = mapped_column(String(512), default="")
    signal_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String(16), default="heuristic")  # llm | heuristic

    __table_args__ = (Index("ix_pred_bot_ts", "bot", "ts"),)


class ModelVersion(Base):
    """ML model registry row — champion/challenger promotion tracking."""

    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    trained_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    train_window_days: Mapped[int] = mapped_column(Integer)
    oos_accuracy: Mapped[float] = mapped_column(Float)
    oos_precision_long: Mapped[float] = mapped_column(Float)
    is_champion: Mapped[bool] = mapped_column(default=False)
    notes: Mapped[str] = mapped_column(String(256), default="")
    weights_blob: Mapped[str | None] = mapped_column(Text, nullable=True)

    runs: Mapped[list["BacktestRun"]] = relationship(back_populates="model")


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    bot: Mapped[str] = mapped_column(String(32))
    symbol: Mapped[str] = mapped_column(String(32))
    timeframe: Mapped[str] = mapped_column(String(8))
    strategy: Mapped[str] = mapped_column(String(64))
    params_json: Mapped[str] = mapped_column(String(1024), default="{}")
    trades_n: Mapped[int] = mapped_column(Integer)
    win_rate: Mapped[float] = mapped_column(Float)
    profit_factor: Mapped[float] = mapped_column(Float)
    sharpe: Mapped[float] = mapped_column(Float)
    max_dd_pct: Mapped[float] = mapped_column(Float)
    total_return_pct: Mapped[float] = mapped_column(Float)
    model_id: Mapped[int | None] = mapped_column(ForeignKey("model_versions.id"), nullable=True)
    equity_curve_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    trades_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    model: Mapped[ModelVersion | None] = relationship(back_populates="runs")

class BacktestValidation(Base):
    """Provenance row for one validation-gate verdict on one backtest.

    Written by the research CLI (trading/research.py) — every number the
    verdict stands on travels with it: seed, data range and source, the
    three statistical checks and the gate thresholds they were held to.
    """

    __tablename__ = "backtest_validations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    bot: Mapped[str] = mapped_column(String(32))
    symbol: Mapped[str] = mapped_column(String(32))
    timeframe: Mapped[str] = mapped_column(String(8))
    strategy: Mapped[str] = mapped_column(String(64))
    params_json: Mapped[str] = mapped_column(String(2048), default="{}")
    seed: Mapped[int] = mapped_column(Integer)
    data_source: Mapped[str] = mapped_column(String(32))  # binance | synthetic | ...
    data_rows: Mapped[int] = mapped_column(Integer)
    data_start: Mapped[str] = mapped_column(String(40))
    data_end: Mapped[str] = mapped_column(String(40))
    trades_n: Mapped[int] = mapped_column(Integer)
    min_trades_required: Mapped[int] = mapped_column(Integer, default=30)
    permutation_p: Mapped[float | None] = mapped_column(Float, nullable=True)
    sharpe_actual: Mapped[float | None] = mapped_column(Float, nullable=True)
    sharpe_ci_lo: Mapped[float | None] = mapped_column(Float, nullable=True)
    sharpe_ci_hi: Mapped[float | None] = mapped_column(Float, nullable=True)
    prob_positive: Mapped[float | None] = mapped_column(Float, nullable=True)
    wf_positive_folds: Mapped[int] = mapped_column(Integer, default=0)
    wf_total_folds: Mapped[int] = mapped_column(Integer, default=0)
    verdict: Mapped[str] = mapped_column(String(16))  # validated | rejected | insufficient_data
    reasons_json: Mapped[str] = mapped_column(String(2048), default="[]")
    validation_json: Mapped[str] = mapped_column(Text, default="{}")
    run_id: Mapped[int | None] = mapped_column(ForeignKey("backtest_runs.id"), nullable=True)


def make_engine(url: str | None = None):
    """A connection engine. Never DDL.

    Schema creation is Alembic's job in the platform database (design D3:
    one migration lineage) and `init_schema`'s everywhere else — a function
    that merely opens a database must not decide what the database contains,
    because a read path that creates tables silently forks the migration
    lineage (this once made `alembic upgrade` fail on the owner's database
    copy with `table candles already exists`).
    """
    settings = get_settings()
    url = url or settings.database_url
    kwargs: dict = {"echo": False}
    if url.startswith("postgresql"):
        # managed Postgres (Supabase pooler): detect dead conns, recycle often
        kwargs.update(
            pool_pre_ping=True,
            pool_recycle=120,
            pool_size=3,
            max_overflow=2,
            # sslmode=require: pooler resets connections during "prefer" negotiation
            connect_args={
                "connect_timeout": 15,
                "sslmode": "require",
                "application_name": "trading",
            },
        )
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        _tune_sqlite(engine)
    return engine


def init_schema(engine) -> None:
    """Create the trading tables and apply the legacy column guard.

    Called by writers and owners of their own database files: the research
    CLI (ingest and validate), the paper engine at startup, and every test
    fixture working against a throwaway database. Never called from a read
    path. On the platform database this is a no-op in practice — Alembic
    creates the same tables from the same models first — and the guard below
    only ever adds a column that is missing, so the two cannot disagree.
    """
    Base.metadata.create_all(engine)
    _migrate_sqlite(engine)


# Columns added after initial schema; applied idempotently on every startup.
# Postgres databases should use migrations instead — this is SQLite-only.
_SQLITE_MIGRATIONS: list[tuple[str, str, str]] = [
    # (table, column, DDL fragment)
    ("model_versions", "weights_blob", "TEXT"),
    ("trades", "gate_source", "TEXT"),
    ("open_positions", "gate_source", "TEXT"),
]


def _migrate_sqlite(engine) -> None:
    if not engine.url.drivername.startswith("sqlite"):
        return
    with engine.begin() as conn:
        for table, column, ddl in _SQLITE_MIGRATIONS:
            cols = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            if cols and column not in cols:
                log.warning("sqlite migrate: adding %s.%s", table, column)
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def _tune_sqlite(engine) -> None:
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()


def make_session_factory(engine=None):
    if engine is None:
        engine = make_engine()
    return sessionmaker(bind=engine, expire_on_commit=False)


# ------------------------------------------------------------------- kv state
# Persistent key-value state on BotStatus rows with `__` prefix names
# (same pattern as the `__killswitch` row); JSON payloads live in `note`.


def get_state(session, key: str, default=None):
    row = session.get(BotStatus, f"__state_{key}")
    if row is None or not row.note:
        return default
    try:
        return json.loads(row.note)
    except (ValueError, TypeError):
        return default


def set_state(session, key: str, value) -> None:
    name = f"__state_{key}"
    row = session.get(BotStatus, name)
    if row is None:
        row = BotStatus(name=name, running=True, mode="state", note="")
        session.add(row)
    row.note = json.dumps(value)
    session.commit()
