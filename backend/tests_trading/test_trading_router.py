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
