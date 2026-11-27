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


def upsert_candles(
    session: Session,
    symbol: str,
    timeframe: str,
    rows: list[dict],
    *,
    venue: str,
    instrument_type: str,
) -> int:
    """Idempotent candle write; returns number of new rows inserted.

    Conflict-safe: concurrent writers (WS stream + periodic backfill + API
    one-shots) insert with ON CONFLICT DO NOTHING, so duplicates can never
    raise. Falls back to per-row skip on dialects without upsert support.

    `venue` and `instrument_type` are required keywords (analysis F-3): the
    writer is the only place that knows which tape the rows came from — a
    default would be exactly the silent identity loss this schema exists to
    end. Rows may also carry per-row 'venue'/'instrument_type' keys, which
    win — a mixed batch keeps its own provenance.
    """
    if not rows:
        return 0
    fresh = [
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "venue": r.get("venue") or venue,
            "instrument_type": r.get("instrument_type") or instrument_type,
            "open_time": r["open_time"],
            "open": r["open"],
            "high": r["high"],
            "low": r["low"],
            "close": r["close"],
            "volume": r["volume"],
        }
        for r in rows
    ]
    # SQLite caps a statement at ~999 bound variables — 10 columns per row,
    # so chunk multi-row inserts well below the limit.
    chunk_size = 90
    inserted = 0
    for i in range(0, len(fresh), chunk_size):
        chunk = fresh[i : i + chunk_size]
        try:
            stmt = (
                _insert_stmt(session)
                .values(chunk)
                .on_conflict_do_nothing(index_elements=["symbol", "timeframe", "venue", "open_time"])
            )
            result = session.execute(stmt)
            session.commit()
            inserted += int(result.rowcount or 0)
        except (IntegrityError, NotImplementedError):
            session.rollback()
            inserted += _upsert_fallback(session, symbol, timeframe, chunk, venue=venue)
    return inserted


def _upsert_fallback(session: Session, symbol: str, timeframe: str, rows: list[dict], *, venue: str) -> int:
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
                Candle.venue == venue,
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


# The tape the desk actually trades (design: USD-M perpetuals on Binance).
# Resolution order when a read does not name its venue: an explicit venue
# wins; a sole stored venue is unambiguous; otherwise perp beats spot beats
# the legacy unlabelled rows — and the choice is recorded on the frame's
# attrs so provenance travels with the data instead of hiding in the call.
TRADING_VENUE = "binance-usdm"
VENUE_PREFERENCE = ("binance-usdm", "hyperliquid", "ccxt:binanceusdm", "binance", "yahoo", "")


def load_candles_df(
    session,
    symbol: str,
    timeframe: str,
    chunk: int = 5000,
    *,
    venue: str | None = None,
) -> pd.DataFrame:
    """Load candles ordered by time. Reads in keyset pages — large tables
    (40k+ rows of 1m) would otherwise die on managed-Postgres poolers that
    reset long-running single-result transfers.

    Venue resolution: explicit `venue` selects exactly that tape. Without it,
    one stored venue is used unambiguously; several resolve by VENUE_PREFERENCE
    (perp truth first — the desk trades perps). The chosen venue and
    instrument type land in `frame.attrs['venue']`/`['instrument_type']` and
    a warning is logged whenever a choice had to be made — silent venue
    mixing is the failure mode this schema exists to end (analysis F-3).
    """
    q0 = select(Candle.venue).where(Candle.symbol == symbol, Candle.timeframe == timeframe).distinct()
    venues = [r[0] for r in session.execute(q0).all() if r[0] is not None]
    chosen = venue
    if chosen is None:
        if len(venues) == 1:
            chosen = venues[0]
        elif venues:
            chosen = min(venues, key=lambda v: VENUE_PREFERENCE.index(v) if v in VENUE_PREFERENCE else len(VENUE_PREFERENCE))
            log.warning(
                "load_candles_df: %s %s stored under %d venues %s — resolved to %r by preference order",
                symbol, timeframe, len(venues), sorted(venues), chosen,
            )
        else:
            chosen = venue  # None — no rows at all, the empty frame below is the answer
    frames: list[pd.DataFrame] = []
    last_ts: dt.datetime | None = None
    instrument_type = ""
    while True:
        q = (
            select(Candle)
            .where(Candle.symbol == symbol, Candle.timeframe == timeframe)
            .order_by(Candle.open_time)
        )
        if chosen is not None:
            q = q.where(Candle.venue == chosen)
        if last_ts is not None:
            q = q.where(Candle.open_time > last_ts)
        rows = session.execute(q.limit(chunk)).scalars().all()
        if not rows:
            break
        instrument_type = rows[-1].instrument_type or instrument_type
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
    out = pd.concat(frames, ignore_index=True).set_index("open_time")
    out.attrs["venue"] = chosen or ""
    out.attrs["instrument_type"] = instrument_type
    return out


def clear_candles(session, symbol: str, timeframe: str, venue: str | None = None):
    q = delete(Candle).where(Candle.symbol == symbol, Candle.timeframe == timeframe)
    if venue is not None:
        q = q.where(Candle.venue == venue)
    session.execute(q)
    session.commit()



__all__ = [
    "TRADING_VENUE",
    "VENUE_PREFERENCE",
    "clear_candles",
    "load_candles_df",
    "make_engine",
    "make_session_factory",
    "upsert_candles",
]


def upsert_funding_rates(session: Session, symbol: str, rows: list[dict]) -> int:
    """Idempotent funding-event write, same conflict discipline as candles."""
    if not rows:
        return 0
    from trading.models import FundingRate

    fresh = [
        {"symbol": symbol, "funding_time": r["funding_time"], "rate": r["rate"], "mark_price": r["mark_price"]}
        for r in rows
    ]
    before = session.query(FundingRate).filter_by(symbol=symbol).count()
    for row in fresh:
        exists = (
            session.query(FundingRate)
            .filter_by(symbol=row["symbol"], funding_time=row["funding_time"])
            .first()
        )
        if not exists:
            session.add(FundingRate(**row))
    session.commit()
    after = session.query(FundingRate).filter_by(symbol=symbol).count()
    return after - before
