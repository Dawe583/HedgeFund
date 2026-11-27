"""Tests for the 24/7 hardening: upsert races, kv state, exposure caps,
stale-signal guard, ML gate veto path, killswitch resume."""

import datetime as dt

import pytest
from sqlalchemy import select

from trading.config import Settings
from trading.models import Candle, make_session_factory
from trading.risk import RiskManager


@pytest.fixture
def session_factory(tmp_path):
    from trading.models import init_schema, make_engine

    engine = make_engine(f"sqlite:///{tmp_path}/test.db")
    init_schema(engine)
    return make_session_factory(engine)


# ------------------------------------------------------------------ upsert
def test_upsert_conflict_safe(session_factory):
    from trading.storage import upsert_candles

    row = {
        "open_time": dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
        "open": 1,
        "high": 2,
        "low": 0.5,
        "close": 1.5,
        "volume": 10,
    }
    n1 = upsert_candles(session_factory(), "BTCUSDT", "1m", [row], venue="binance-usdm", instrument_type="perp")
    n2 = upsert_candles(session_factory(), "BTCUSDT", "1m", [row, dict(row, close=1.6)], venue="binance-usdm", instrument_type="perp")
    assert n1 == 1
    assert n2 == 0  # duplicate must never raise nor double-insert
    with session_factory() as s:
        assert s.execute(select(Candle)).scalars().all().__len__() == 1


def test_upsert_large_batch_chunks_below_sqlite_var_limit(session_factory):
    """720+ rows in one multi-row INSERT hit SQLite's ~999 bound-variable
    limit (OperationalError) — upsert must chunk below it."""
    from trading.storage import upsert_candles

    base = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    rows = [
        {
            "open_time": base + dt.timedelta(hours=4 * i),
            "open": 1,
            "high": 2,
            "low": 0.5,
            "close": 1.5,
            "volume": 10,
        }
        for i in range(800)  # 800 × 8 cols = 6400 vars > 999 if unchunked
    ]
    n = upsert_candles(session_factory(), "BTCUSDT", "4h", rows, venue="binance-usdm", instrument_type="perp")
    assert n == 800
    # re-running the same batch must stay idempotent
    assert upsert_candles(session_factory(), "BTCUSDT", "4h", rows, venue="binance-usdm", instrument_type="perp") == 0


# ------------------------------------------------------------------ kv state
def test_state_roundtrip(session_factory):
    from trading.models import get_state, set_state

    with session_factory() as s:
        set_state(s, "peak_equity", 1234.5)
    with session_factory() as s:
        assert get_state(s, "peak_equity") == 1234.5
        assert get_state(s, "missing", "dflt") == "dflt"


# ------------------------------------------------------------------ risk
def test_gross_exposure_cap():
    assert RiskManager.gross_exposure_ok(1500, 1000)
    assert not RiskManager.gross_exposure_ok(2500, 1000)
    assert not RiskManager.gross_exposure_ok(100, 0)  # zero equity -> no trade


def test_daily_loss_resets_per_day(session_factory):
    rm = RiskManager(Settings(risk_max_daily_loss_pct=0.02))
    # day 1: breach at -3%
    assert rm.daily_loss_breached(1000, 970)
    # day 2 re-baselines: same equity but day-start = current -> no breach
    assert not rm.daily_loss_breached(970, 969)


def test_killswitch_resume(session_factory):
    from trading.risk import killswitch_state, set_killswitch

    set_killswitch(session_factory, True, note="test")
    assert killswitch_state(session_factory)["tripped"] is True
    set_killswitch(session_factory, False)
    st = killswitch_state(session_factory)
    assert st["tripped"] is False


# ------------------------------------------------------------------ ML gate
def test_ml_gate_veto_path(session_factory):
    import json

    import numpy as np

    from trading.ml.train import FEATURES, LogitModel, deserialize, serialize

    m = LogitModel()
    m.w = np.random.default_rng(0).normal(size=len(FEATURES) + 1)  # +1 bias term
    m.mean = np.zeros(len(FEATURES))
    m.std = np.ones(len(FEATURES))
    m.calib_edges = np.linspace(0, 1, 11)
    m.calib_map = np.full(10, 0.2)  # always-low calibrated prob
    blob = serialize(m)
    json.loads(blob)  # blob is valid JSON
    m2 = deserialize(blob)
    x = np.zeros((1, len(FEATURES)))
    p = float(m2.predict_proba(x)[0])
    assert p < 0.55  # below threshold -> worker must veto


# ------------------------------------------------------------------ worker bits
def test_stale_signal_guard_constant():
    from trading import paper

    assert paper.SIGNAL_MAX_AGE_BARS <= 2
    assert paper.STALE_CANDLE_S >= 120


def test_exit_price_gap_through():
    from trading.config import Settings
    from trading.paper import PaperEngine

    class _Dummy(PaperEngine):
        def __init__(self):  # no engine boot — just the pricing rule
            self.s = Settings(slippage_bps=2.0)

    eng = _Dummy()
    candle = {"open": 100.0, "high": 101.0, "low": 94.0, "close": 95.0}
    # long SL at 98, candle gapped down through it: fill <= min(open, sl)
    px = eng._exit_price("long", 98.0, candle, take=110.0, hit_sl=True)
    assert px <= 100.0
    # short SL at 97, candle gapped up: fill >= max(open, sl)
    candle2 = {"open": 104.0, "high": 108.0, "low": 103.0, "close": 107.0}
    px2 = eng._exit_price("short", 97.0, candle2, take=90.0, hit_sl=True)
    assert px2 >= 104.0


def test_worker_lock_single_instance(tmp_path, session_factory, monkeypatch):
    import fcntl

    import trading.paper as paper_mod
    from trading.config import Settings

    lock_path = tmp_path / "worker.lock"
    with open(lock_path, "w") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        monkeypatch.setattr(paper_mod, "get_settings", lambda: Settings(data_dir=str(tmp_path)))
        assert paper_mod._acquire_worker_lock() is False  # held by the outer flock
