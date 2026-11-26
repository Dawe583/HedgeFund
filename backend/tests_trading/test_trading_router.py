"""Behavior tests for the read-only trading API router.

The router is exercised on its own small FastAPI app against a throwaway
database — the owner's data.db never appears in this suite.
"""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.trading import get_trading_db, router
from trading.models import (
    BacktestRun,
    BacktestValidation,
    init_schema,
    make_engine,
    make_session_factory,
)


@pytest.fixture
def client(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/trading.db")
    init_schema(engine)
    sf = make_session_factory(engine)

    def override():
        db = sf()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_trading_db] = override
    yield TestClient(app), sf
    app.dependency_overrides.clear()
    engine.dispose()


def _write_verdict(sf, verdict="rejected", seed=42):
    with sf() as session:
        run = BacktestRun(
            bot="scalp", symbol="BTCUSDT", timeframe="4h", strategy="ScalpTrend",
            params_json='{"stop_atr": 2.2}', trades_n=12, win_rate=0.4,
            profit_factor=0.8, sharpe=-0.3, max_dd_pct=-5.0, total_return_pct=-2.0,
            equity_curve_json=json.dumps(
                [{"t": "2025-01-01T00:00:00+00:00", "equity": 10000.0},
                 {"t": "2025-01-02T00:00:00+00:00", "equity": 9950.0}]
            ),
            trades_json=json.dumps(
                [{"entry_time": "2025-01-01T00:00:00+00:00",
                  "exit_time": "2025-01-02T00:00:00+00:00", "side": "long",
                  "qty": 0.1, "entry_price": 40000.0, "exit_price": 39500.0,
                  "pnl": -50.0}]
            ),
        )
        session.add(run)
        session.flush()
        row = BacktestValidation(
            bot="scalp", symbol="BTCUSDT", timeframe="4h", strategy="ScalpTrend",
            params_json='{"stop_atr": 2.2}', seed=seed, data_source="binance",
            data_rows=2000, data_start="2025-01-01", data_end="2025-11-01",
            trades_n=12, min_trades_required=30, permutation_p=0.4,
            sharpe_actual=-0.3, sharpe_ci_lo=-1.2, sharpe_ci_hi=0.5,
            prob_positive=0.2, wf_positive_folds=1, wf_total_folds=5,
            verdict=verdict, reasons_json='["trades 12 < minimum 30"]',
            validation_json="{}", run_id=run.id,
        )
        session.add(row)
        session.commit()
        return run.id


def test_status_is_first_class_offline(client):
    c, sf = client
    res = c.get("/api/trading/status")
    assert res.status_code == 200
    body = res.json()
    assert body["engine_state"] == "offline"
    assert body["last_tick_at"] is None
    assert body["db_ok"] is True
    assert body["strategies_registered"] == 0
    assert body["validations_total"] == 0


def test_strategies_lists_four_ported_bots(client):
    c, sf = client
    res = c.get("/api/trading/strategies")
    assert res.status_code == 200
    keys = {s["key"] for s in res.json()}
    assert keys == {"scalp", "hft", "breakout", "meanrev"}
    assert all(s["registered"] is False for s in res.json())
    assert all(s["description"] for s in res.json())


def test_backtest_runs_empty_without_rows(client):
    c, sf = client
    res = c.get("/api/trading/backtest-runs")
    assert res.status_code == 200
    assert res.json() == []


def test_backtest_runs_carry_their_verdict(client):
    c, sf = client
    run_id = _write_verdict(sf)
    res = c.get("/api/trading/backtest-runs")
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == run_id
    assert row["verdict"] == "rejected"
    assert row["trades_count"] == 12
    assert row["validation"]["permutation_p"] == 0.4
    assert row["validation"]["wf_positive_folds"] == 1
    assert row["validation"]["wf_total_folds"] == 5
    assert row["metrics"]["sharpe"] == -0.3


def test_backtest_run_detail_carries_provenance(client):
    c, sf = client
    run_id = _write_verdict(sf)
    res = c.get(f"/api/trading/backtest-runs/{run_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["provenance"]["seed"] == 42
    assert body["provenance"]["data_source"] == "binance"
    assert body["provenance"]["data_rows"] == 2000
    assert body["params"] == {"stop_atr": 2.2}
    assert body["reasons"] == ["trades 12 < minimum 30"]
    assert len(body["equity_curve"]) == 2
    assert body["equity_curve"][0]["t"] == "2025-01-01T00:00:00+00:00"
    assert body["equity_curve"][1]["equity"] == 9950.0
    assert len(body["trades"]) == 1
    trade = body["trades"][0]
    assert trade["side"] == "long"
    assert trade["qty"] == 0.1
    assert trade["entry_price"] == 40000.0
    assert trade["exit_price"] == 39500.0
    assert trade["pnl"] == -50.0


def test_backtest_run_detail_null_evidence_for_legacy_rows(client):
    """Runs written before migration c4a1b2d3e5f6 have no evidence columns —
    the keys must be present and explicitly null, never omitted."""
    c, sf = client
    with sf() as session:
        run = BacktestRun(
            bot="scalp", symbol="BTCUSDT", timeframe="4h", strategy="ScalpTrend",
            params_json="{}", trades_n=0, win_rate=0.0,
            profit_factor=0.0, sharpe=0.0, max_dd_pct=0.0, total_return_pct=0.0,
        )
        session.add(run)
        session.commit()
        run_id = run.id
    res = c.get(f"/api/trading/backtest-runs/{run_id}")
    assert res.status_code == 200
    body = res.json()
    assert "equity_curve" in body and body["equity_curve"] is None
    assert "trades" in body and body["trades"] is None


def test_backtest_run_detail_404_for_missing(client):
    c, sf = client
    res = c.get("/api/trading/backtest-runs/999")
    assert res.status_code == 404


def test_status_counts_validations(client):
    c, sf = client
    _write_verdict(sf)
    res = c.get("/api/trading/status")
    assert res.json()["validations_total"] == 1


def test_read_endpoints_create_nothing(tmp_path):
    """Schema authority: GET endpoints are reads, and reads never write.

    Against a database without the trading tables, every endpoint degrades
    to the offline answer — and the database file comes out of it with
    exactly the tables it went in with (none). Alembic is the only authority
    that may ever put them there.
    """
    from sqlalchemy import inspect as sa_inspect

    engine = make_engine(f"sqlite:///{tmp_path}/virgin.db")
    sf = make_session_factory(engine)

    def override():
        db = sf()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_trading_db] = override
    c = TestClient(app)

    before = sa_inspect(engine).get_table_names()
    res = c.get("/api/trading/status")
    assert res.status_code == 200
    body = res.json()
    assert body["engine_state"] == "offline"
    assert body["db_ok"] is False  # trading tables absent: said, never fixed behind the user's back
    assert c.get("/api/trading/backtest-runs").json() == []
    assert c.get("/api/trading/strategies").status_code == 200  # pure code registry, no db
    assert c.get("/api/trading/backtest-runs/1").status_code == 404
    after = sa_inspect(engine).get_table_names()
    assert after == before
    engine.dispose()


# ------------------------------------------------------------- wire shape
# The contract is canonical for the frontend: keys, casing and explicit nulls
# are the API, pinned here so a refactor cannot drift them silently.

RUN_ITEM_KEYS = {
    "id", "bot", "symbol", "timeframe", "started_at", "trades_count",
    "metrics", "verdict", "validation", "created_at", "engine_version",
}
METRICS_KEYS = {"win_rate", "profit_factor", "sharpe", "max_dd_pct", "total_return_pct"}
VALIDATION_KEYS = {"permutation_p", "sharpe_ci_lo", "sharpe_ci_hi", "wf_positive_folds", "wf_total_folds"}
DETAIL_EXTRA_KEYS = {"params", "provenance", "reasons", "prob_positive", "sharpe_actual", "min_trades_required", "equity_curve", "trades"}
PROVENANCE_KEYS = {"seed", "data_source", "data_rows", "data_start", "data_end"}


def test_run_list_wire_shape_is_canonical(client):
    c, sf = client
    _write_verdict(sf)
    row = c.get("/api/trading/backtest-runs").json()[0]
    assert set(row.keys()) == RUN_ITEM_KEYS
    assert set(row["metrics"].keys()) == METRICS_KEYS
    assert set(row["validation"].keys()) == VALIDATION_KEYS
    assert row["verdict"] == "rejected"  # lowercase, never capitalized


def test_run_detail_wire_shape_is_canonical(client):
    c, sf = client
    run_id = _write_verdict(sf)
    body = c.get(f"/api/trading/backtest-runs/{run_id}").json()
    assert set(body.keys()) == RUN_ITEM_KEYS | DETAIL_EXTRA_KEYS
    assert set(body["provenance"].keys()) == PROVENANCE_KEYS
    assert isinstance(body["reasons"], list)
    assert isinstance(body["started_at"], str)  # ISO string on the wire


def test_run_detail_nullable_branches_are_explicit_nulls(client):
    """A run without a validation row still carries the keys — as null."""
    c, sf = client
    with sf() as session:
        run = BacktestRun(
            bot="hft", symbol="BTCUSDT", timeframe="1m", strategy="HFTMomentum",
            params_json="{}", trades_n=0, win_rate=0.0, profit_factor=0.0,
            sharpe=0.0, max_dd_pct=0.0, total_return_pct=0.0,
        )
        session.add(run)
        session.commit()
        run_id = run.id
    body = c.get(f"/api/trading/backtest-runs/{run_id}").json()
    assert set(body.keys()) == RUN_ITEM_KEYS | DETAIL_EXTRA_KEYS
    assert body["verdict"] is None
    assert body["validation"] is None
    assert body["provenance"] is None
    assert body["prob_positive"] is None
    assert body["sharpe_actual"] is None
    assert body["min_trades_required"] is None
    assert body["reasons"] == []


# ---------------------------------------------------------------- positions

POSITION_KEYS = {
    "id", "bot", "symbol", "side", "qty", "entry_price", "stop_loss",
    "take_profit", "opened_at", "age_seconds", "confidence", "signal_time",
    "gate_source",
}
CLOSED_TRADE_KEYS = {
    "id", "bot", "symbol", "side", "qty", "entry_price", "exit_price",
    "entry_time", "exit_time", "pnl", "fees", "confidence", "mode",
    "gate_source",
}


def _write_position(sf, opened_seconds_ago=300, signal_time=True):
    import datetime as dt

    from trading.models import OpenPosition

    now = dt.datetime.now(dt.UTC)
    opened = now - dt.timedelta(seconds=opened_seconds_ago)
    with sf() as session:
        row = OpenPosition(
            bot="scalp", symbol="BTCUSDT", side="long", qty=0.05,
            entry_price=91000.0, stop_loss=89500.0, take_profit=93500.0,
            opened_at=opened, confidence=0.62, gate_source="kernel",
            signal_time=opened if signal_time else None,
        )
        session.add(row)
        session.commit()
        return row.id


def _write_trade(sf):
    import datetime as dt

    from trading.models import Trade

    now = dt.datetime.now(dt.UTC)
    with sf() as session:
        row = Trade(
            bot="scalp", symbol="BTCUSDT", side="short", qty=0.05,
            entry_price=93000.0, exit_price=92000.0,
            entry_time=now - dt.timedelta(hours=8), exit_time=now - dt.timedelta(hours=2),
            pnl=50.0, fees=1.5, confidence=0.4, mode="paper", gate_source="kernel",
        )
        session.add(row)
        session.commit()
        return row.id


def test_positions_empty_is_the_honest_answer(client):
    c, sf = client
    res = c.get("/api/trading/positions")
    assert res.status_code == 200
    assert res.json() == []


def test_positions_carry_exactly_what_the_row_carries(client):
    c, sf = client
    _write_position(sf, opened_seconds_ago=300)
    res = c.get("/api/trading/positions")
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 1
    row = rows[0]
    assert set(row.keys()) == POSITION_KEYS
    assert row["bot"] == "scalp"
    assert row["side"] == "long"
    assert row["qty"] == 0.05
    assert row["entry_price"] == 91000.0
    assert row["stop_loss"] == 89500.0
    assert row["take_profit"] == 93500.0
    assert row["confidence"] == 0.62
    assert row["gate_source"] == "kernel"
    # server-computed age: ~300s, tolerant of the seconds the test itself takes
    assert 295 <= row["age_seconds"] <= 330
    assert isinstance(row["opened_at"], str)
    assert isinstance(row["signal_time"], str)


def test_positions_legacy_row_has_null_signal_time(client):
    """Rows from before the kernel migration never carried signal_time —
    explicit null, never invented."""
    c, sf = client
    _write_position(sf, signal_time=False)
    row = c.get("/api/trading/positions").json()[0]
    assert "signal_time" in row
    assert row["signal_time"] is None


def test_recent_trades_empty_is_the_honest_answer(client):
    c, sf = client
    res = c.get("/api/trading/positions/recent-trades")
    assert res.status_code == 200
    assert res.json() == []


def test_recent_trades_carry_the_settled_round_trip(client):
    c, sf = client
    _write_trade(sf)
    res = c.get("/api/trading/positions/recent-trades")
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 1
    row = rows[0]
    assert set(row.keys()) == CLOSED_TRADE_KEYS
    assert row["side"] == "short"
    assert row["pnl"] == 50.0
    assert row["fees"] == 1.5
    assert row["mode"] == "paper"
    assert row["gate_source"] == "kernel"
    assert isinstance(row["entry_time"], str)
    assert isinstance(row["exit_time"], str)


def test_positions_endpoints_create_nothing(tmp_path):
    """Same schema-authority rule as the run endpoints: a database without
    the trading tables answers empty, and gains no tables for being asked."""
    from sqlalchemy import inspect as sa_inspect

    engine = make_engine(f"sqlite:///{tmp_path}/virgin2.db")
    sf = make_session_factory(engine)

    def override():
        db = sf()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_trading_db] = override
    c = TestClient(app)

    before = sa_inspect(engine).get_table_names()
    assert c.get("/api/trading/positions").json() == []
    assert c.get("/api/trading/positions/recent-trades").json() == []
    assert sa_inspect(engine).get_table_names() == before
    engine.dispose()
