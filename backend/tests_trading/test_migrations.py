"""Tests for SQLite schema migration (weights_blob) and WS kline parsing
(spot lowercase h/l vs futures H/L, invalid payload skip)."""

import datetime as dt

from sqlalchemy import inspect, select, text

from trading.feeds.binance import _kline_from_ws
from trading.models import ModelVersion, make_engine, make_session_factory

# --------------------------------------------------------------- migrations
OLD_SCHEMA = """
CREATE TABLE model_versions (
    id INTEGER NOT NULL PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    "version" INTEGER NOT NULL,
    trained_at DATETIME,
    train_window_days INTEGER,
    oos_accuracy FLOAT,
    oos_precision_long FLOAT,
    is_champion BOOLEAN,
    notes VARCHAR(256)
)
"""


def _column_count(engine, table: str, column: str) -> int:
    with engine.connect() as conn:
        cols = [row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))]
    return cols.count(column)


def test_make_engine_migrates_old_schema(tmp_path):
    # 1) create an old-schema DB by hand, without weights_blob
    db = tmp_path / "old.db"
    old = make_engine(f"sqlite:///{db}")
    with old.begin() as conn:
        conn.execute(text("DROP TABLE model_versions"))
        conn.execute(text(OLD_SCHEMA))
    old.dispose()  # simulate process restart

    # 2) make_engine on the old DB must migrate + work
    engine = make_engine(f"sqlite:///{db}")
    assert _column_count(engine, "model_versions", "weights_blob") == 1

    sf = make_session_factory(engine)
    with sf() as s:
        row = ModelVersion(
            name="logit",
            version=1,
            trained_at=dt.datetime.now(dt.UTC),
            train_window_days=30,
            oos_accuracy=0.6,
            oos_precision_long=0.55,
            is_champion=True,
            notes="migrated",
            weights_blob='{"w": [0.1]}',
        )
        s.add(row)
        s.commit()
        back = s.execute(select(ModelVersion)).scalars().one()
        assert back.weights_blob == '{"w": [0.1]}'

    # 3) idempotent: second make_engine must not duplicate the column
    engine2 = make_engine(f"sqlite:///{db}")
    assert _column_count(engine2, "model_versions", "weights_blob") == 1
    sf2 = make_session_factory(engine2)
    with sf2() as s:
        assert s.execute(select(ModelVersion)).scalars().all().__len__() == 1
    engine.dispose()
    engine2.dispose()


def test_make_engine_fresh_schema_untouched(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/fresh.db")
    assert _column_count(engine, "model_versions", "weights_blob") == 1
    # create_all made all model tables — sanity that nothing else got mangled
    assert inspect(engine).has_table("model_versions")
    engine.dispose()


# ------------------------------------------------------------ ws kline parse
def test_stream_klines_parses_spot_payload():
    spot = {"t": 1, "o": "1", "h": "2", "l": "0.5", "c": "1.5", "v": "10", "T": 2, "x": True}
    fut = {"t": 1, "o": "1", "H": "2", "L": "0.5", "c": "1.5", "v": "10", "T": 2, "x": True}
    for k in (spot, fut):
        candle = _kline_from_ws(k)
        assert candle is not None
        assert candle["high"] == 2.0
        assert candle["low"] == 0.5
        assert candle["close"] == 1.5
        assert candle["volume"] == 10


def test_stream_klines_skips_invalid_payload():
    # neither h nor H present -> parser must skip, not crash
    bad = {"t": 1, "o": "1", "c": "1.5", "v": "10", "T": 2, "x": True}
    assert _kline_from_ws(bad) is None
    # non-dict k -> skipped safely
    assert _kline_from_ws("junk") is None  # type: ignore[arg-type]


# ------------------------------------------------------- ohlc sanity filter
def test_parse_kline_drops_corrupt_ohlc():
    from trading.feeds.binance import _parse_kline

    # the real-world garbage seen on the Pi: low = 6.6e9 on a ~78k candle
    assert _parse_kline([1, "78758.0", "78760.0", "6642154076.0", "78733.71", "5.8", 2]) is None
    # high below open/close is impossible — drop
    assert _parse_kline([1, "100", "90", "80", "95", "1", 2]) is None
    # valid candle still parses
    ok = _parse_kline([1, "100", "110", "95", "105", "10", 2])
    assert ok is not None and ok["high"] == 110 and ok["low"] == 95
