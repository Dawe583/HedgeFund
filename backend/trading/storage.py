"""Storage helpers — candle persistence + queries used by API and bots."""

import datetime as dt

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from trading.models import Candle, make_engine, make_session_factory


def _ts(value) -> int:
    """Normalize any datetime (naive=UTC or aware) to epoch seconds."""
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.UTC)
        return int(value.timestamp())
    return int(pd.Timestamp(value).timestamp())


def _insert_stmt(session: Session):
    bind = session.get_bind()
    if bind is not None and hasattr(bind, "dialect") and bind.dialect.name == "postgresql":
        return pg_insert(Candle)
    return sqlite_insert(Candle)


def upsert_candles(session: Session, symbol: str, timeframe: str, rows: list[dict]) -> int:
    """Idempotent candle write; returns number of new rows inserted.

    Conflict-safe: concurrent writers (WS stream + periodic backfill + API
    one-shots) insert with ON CONFLICT DO NOTHING, so duplicates can never
    raise. Falls back to per-row skip on dialects without upsert support.
    """
    if not rows:
        return 0
    fresh = [
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "open_time": r["open_time"],
            "open": r["open"],
            "high": r["high"],
            "low": r["low"],
            "close": r["close"],
            "volume": r["volume"],
        }
        for r in rows
    ]
    # SQLite caps a statement at ~999 bound variables — 8 columns per row,
    # so chunk multi-row inserts well below the limit.
    chunk_size = 100
    inserted = 0
    for i in range(0, len(fresh), chunk_size):
        chunk = fresh[i : i + chunk_size]
        try:
            stmt = (
                _insert_stmt(session)
                .values(chunk)
                .on_conflict_do_nothing(index_elements=["symbol", "timeframe", "open_time"])
            )
            result = session.execute(stmt)
            session.commit()
            inserted += int(result.rowcount or 0)
        except (IntegrityError, NotImplementedError):
            session.rollback()
            inserted += _upsert_fallback(session, symbol, timeframe, chunk)
    return inserted


def _upsert_fallback(session: Session, symbol: str, timeframe: str, rows: list[dict]) -> int:
    """Dialects without upsert support: SELECT existing, insert only new rows."""
    # fallback: filter via SELECT then plain insert, skip duplicates
    min_ts = min(_ts(r["open_time"]) for r in rows)
    cutoff = dt.datetime.fromtimestamp(min_ts, dt.UTC)
    existing = {
        _ts(r[0])
        for r in session.execute(
            select(Candle.open_time).where(
                Candle.symbol == symbol,
                Candle.timeframe == timeframe,
                Candle.open_time >= cutoff,
            )
        ).all()
    }
    deduped = {r["open_time"]: r for r in rows}
    new_rows = [r for t, r in deduped.items() if _ts(t) not in existing]
    for r in new_rows:
        session.add(Candle(**r))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
    return len(new_rows)


def load_candles_df(session, symbol: str, timeframe: str, chunk: int = 5000) -> pd.DataFrame:
    """Load candles ordered by time. Reads in keyset pages — large tables
    (40k+ rows of 1m) would otherwise die on managed-Postgres poolers that
    reset long-running single-result transfers."""
    frames: list[pd.DataFrame] = []
    last_ts: dt.datetime | None = None
    while True:
        q = (
            select(Candle)
            .where(Candle.symbol == symbol, Candle.timeframe == timeframe)
            .order_by(Candle.open_time)
        )
        if last_ts is not None:
            q = q.where(Candle.open_time > last_ts)
        rows = session.execute(q.limit(chunk)).scalars().all()
        if not rows:
            break
        frames.append(
            pd.DataFrame(
                [
                    {
                        "open_time": r.open_time,
                        "open": r.open,
                        "high": r.high,
                        "low": r.low,
                        "close": r.close,
                        "volume": r.volume,
                    }
                    for r in rows
                ]
            )
        )
        last_ts = rows[-1].open_time
        if len(rows) < chunk:
            break
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).set_index("open_time")


def clear_candles(session, symbol: str, timeframe: str):
    session.execute(delete(Candle).where(Candle.symbol == symbol, Candle.timeframe == timeframe))
    session.commit()


__all__ = [
    "clear_candles",
    "load_candles_df",
    "make_engine",
    "make_session_factory",
    "upsert_candles",
]
