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
DETAIL_EXTRA_KEYS = {"params", "provenance", "reasons", "prob_positive", "sharpe_actual", "min_trades_required", "equity_curve", "trades", "equity_fan"}
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
    # slice 5: per-fill divergence evidence, nullable
    "entry_dev_ticks", "entry_ref_price", "entry_lag_bars",
}
CLOSED_TRADE_KEYS = {
    "id", "bot", "symbol", "side", "qty", "entry_price", "exit_price",
    "entry_time", "exit_time", "pnl", "fees", "confidence", "mode",
    "gate_source",
    # slice 5: per-fill divergence evidence, nullable
    "entry_dev_ticks", "exit_dev_ticks", "entry_lag_bars",
    # M4 §8: the provenance drill-down anchor and the joined sizing chain
    "signal_time", "signal_chain",
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


# --------------------------------------------------------------------------
# M4 §8 additions: signals today, strategy panels, validation queue,
# model registry, the equity fan.


def _write_signal(sf, bot="scalp", outcome="entered", details='{"qty": 0.1}'):
    import datetime as dt

    from trading.models import SignalRecord

    with sf() as session:
        row = SignalRecord(
            bot=bot, symbol="BTCUSDT", timeframe="4h",
            bar_time=dt.datetime.now(dt.UTC), side="long", confidence=0.9,
            outcome=outcome, details_json=details,
        )
        session.add(row)
        session.commit()
        return row.id


def test_signals_today_empty_is_the_honest_answer(client):
    c, sf = client
    res = c.get("/api/trading/signals/today")
    assert res.status_code == 200
    body = res.json()
    assert body["signals"] == []
    assert "date" in body


def test_signals_today_carry_outcome_and_sizing_chain(client):
    c, sf = client
    row_id = _write_signal(sf)
    res = c.get("/api/trading/signals/today")
    assert res.status_code == 200
    rows = res.json()["signals"]
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == row_id
    assert row["outcome"] == "entered"
    assert row["details"] == {"qty": 0.1}
    assert row["side"] == "long"
    assert row["confidence"] == 0.9
    assert row["bar_time"] is not None


def test_signals_today_surfaces_rejected_outcomes(client):
    """The acceptance line: rejected emissions must be exactly as visible as
    the entered ones — the endpoint does not filter, sort or soften them."""
    c, sf = client
    _write_signal(sf, outcome="below_confidence", details="{}")
    _write_signal(sf, outcome="veto:daily_loss", details='{"rail": "daily_loss"}')
    res = c.get("/api/trading/signals/today")
    outcomes = {r["outcome"] for r in res.json()["signals"]}
    assert outcomes == {"below_confidence", "veto:daily_loss"}


def test_strategy_panels_curve_is_cumulative_realized_pnl(client):
    """Per-bot equity curves are derived from the desk's own closed trades —
    cumulative realized net pnl, never an allocation of the portfolio rows."""
    import datetime as dt

    from trading.models import Trade

    c, sf = client
    with sf() as session:
        for i, pnl in enumerate([10.0, -4.0, 6.0]):
            session.add(
                Trade(
                    bot="scalp", symbol="BTCUSDT", side="long", qty=0.1,
                    entry_price=100.0, exit_price=101.0,
                    entry_time=dt.datetime(2025, 1, 1, tzinfo=dt.UTC),
                    exit_time=dt.datetime(2025, 1, 2 + i, tzinfo=dt.UTC),
                    pnl=pnl, fees=0.1, confidence=0.9, mode="paper", gate_source="kernel",
                )
            )
        session.commit()
    res = c.get("/api/trading/strategy-panels")
    assert res.status_code == 200
    panels = res.json()
    assert len(panels) == 1
    panel = panels[0]
    assert panel["bot"] == "scalp"
    assert panel["trades_count"] == 3
    equities = [p["equity"] for p in panel["curve"]]
    assert equities == [pytest.approx(10.0), pytest.approx(6.0), pytest.approx(12.0)]


def test_strategy_panels_empty_is_the_honest_answer(client):
    c, sf = client
    res = c.get("/api/trading/strategy-panels")
    assert res.status_code == 200
    assert res.json() == []


def _write_registry_version(sf, state="research"):
    from trading.models import Strategy, StrategyState, StrategyVersion

    with sf() as session:
        strat = Strategy(key="scalp", name="Scalp Trend")
        session.add(strat)
        session.flush()
        v = StrategyVersion(
            strategy_id=strat.id, version=1, params_json="{}",
            code_hash="abc", timeframe="4h", universe_json='["BTCUSDT"]',
        )
        session.add(v)
        session.flush()
        session.add(StrategyState(version_id=v.id, state=state, evidence="", note="registered"))
        session.commit()
        return v.id


def test_validation_queue_surfaces_awaiting_versions(client):
    c, sf = client
    vid = _write_registry_version(sf, state="research")
    res = c.get("/api/trading/validation-queue")
    assert res.status_code == 200
    body = res.json()
    assert len(body["awaiting"]) == 1
    awaiting = body["awaiting"][0]
    assert awaiting["version_id"] == vid
    assert awaiting["strategy_key"] == "scalp"
    assert awaiting["kind"] == "awaiting"
    # awaiting versions carry no verdict numbers — explicit nulls, never zeros
    assert awaiting["permutation_p"] is None
    assert awaiting["trades_n"] is None


def test_validation_queue_excludes_promoted_versions(client):
    c, sf = client
    _write_registry_version(sf, state="paper")
    res = c.get("/api/trading/validation-queue")
    assert res.json()["awaiting"] == []


def test_validation_queue_failures_carry_the_gates_reasons(client):
    c, sf = client
    _write_verdict(sf, verdict="rejected")
    res = c.get("/api/trading/validation-queue")
    failures = res.json()["failures"]
    assert len(failures) == 1
    failure = failures[0]
    assert failure["kind"] == "failure"
    assert failure["verdict"] == "rejected"
    assert failure["reasons"] == ["trades 12 < minimum 30"]
    assert failure["permutation_p"] == 0.4
    assert failure["trades_n"] == 12
    assert failure["min_trades_required"] == 30


def test_model_registry_empty_is_the_honest_answer(client):
    c, sf = client
    res = c.get("/api/trading/model-registry")
    assert res.status_code == 200
    body = res.json()
    assert body["models"] == []
    # the PSI honesty note travels even on the empty answer — the panel's
    # documentation is part of the contract, not a footnote
    assert "psi" in body["psi_note"].lower()


def test_model_registry_roles_and_oos_metrics(client):
    from trading.models import ModelVersion

    c, sf = client
    with sf() as session:
        session.add(
            ModelVersion(
                name="gate-BTCUSDT-4h", version=1, train_window_days=90,
                oos_accuracy=0.51, oos_precision_long=0.52, is_champion=False,
                notes="rejected by the gate",
            )
        )
        session.add(
            ModelVersion(
                name="gate-BTCUSDT-4h", version=2, train_window_days=90,
                oos_accuracy=0.57, oos_precision_long=0.61, is_champion=True,
                notes="promoted",
            )
        )
        session.commit()
    res = c.get("/api/trading/model-registry")
    assert res.status_code == 200
    models = res.json()["models"]
    assert len(models) == 2
    champion = next(m for m in models if m["is_champion"])
    assert champion["role"] == "champion"
    assert champion["oos_accuracy"] == 0.57
    other = next(m for m in models if not m["is_champion"])
    # v1 is not the newest of its name — retired, never a silent absence
    assert other["role"] == "retired"
    # PSI is not a column today: null on the wire is the documented answer
    for m in models:
        assert m["psi_drift"] is None


def test_model_registry_newest_nonchampion_is_the_challenger(client):
    from trading.models import ModelVersion

    c, sf = client
    with sf() as session:
        session.add(
            ModelVersion(
                name="gate-BTCUSDT-4h", version=1, train_window_days=90,
                oos_accuracy=0.55, oos_precision_long=0.56, is_champion=True,
            )
        )
        session.add(
            ModelVersion(
                name="gate-BTCUSDT-4h", version=2, train_window_days=90,
                oos_accuracy=0.53, oos_precision_long=0.54, is_champion=False,
            )
        )
        session.commit()
    models = c.get("/api/trading/model-registry").json()["models"]
    challenger = next(m for m in models if m["version"] == 2)
    assert challenger["role"] == "challenger"


def test_run_detail_carries_the_equity_fan(client):
    """The fan lives in validation_json.monte_carlo.equity_paths — the detail
    endpoint surfaces it verbatim, null when never recorded."""
    c, sf = client
    fan = {
        "steps": [1, 2], "initial_capital": 1000.0,
        "actual": [1010.0, 1020.0],
        "band_p5": [990.0, 980.0], "band_p25": [995.0, 990.0],
        "band_p50": [1000.0, 1000.0], "band_p75": [1005.0, 1010.0],
        "band_p95": [1010.0, 1020.0],
        "samples": [[1001.0, 1002.0]],
    }
    with sf() as session:
        run = BacktestRun(
            bot="scalp", symbol="BTCUSDT", timeframe="4h", strategy="ScalpTrend",
            params_json="{}", trades_n=30, win_rate=0.5,
            profit_factor=1.2, sharpe=0.8, max_dd_pct=-3.0, total_return_pct=5.0,
        )
        session.add(run)
        session.flush()
        session.add(
            BacktestValidation(
                bot="scalp", symbol="BTCUSDT", timeframe="4h", strategy="ScalpTrend",
                params_json="{}", seed=42, data_source="binance",
                data_rows=2000, data_start="2025-01-01", data_end="2025-11-01",
                trades_n=30, min_trades_required=30, permutation_p=0.02,
                sharpe_actual=0.8, sharpe_ci_lo=0.1, sharpe_ci_hi=1.4,
                prob_positive=0.9, wf_positive_folds=4, wf_total_folds=5,
                verdict="validated", reasons_json="[]",
                validation_json=json.dumps({"monte_carlo": {"equity_paths": fan}}),
                run_id=run.id,
            )
        )
        session.commit()
        run_id = run.id
    res = c.get(f"/api/trading/backtest-runs/{run_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["equity_fan"]["actual"] == [1010.0, 1020.0]
    assert body["equity_fan"]["band_p95"] == [1010.0, 1020.0]
    assert len(body["equity_fan"]["samples"]) == 1


def test_run_detail_fan_is_null_when_never_recorded(client):
    c, sf = client
    run_id = _write_verdict(sf)  # validation_json = "{}"
    res = c.get(f"/api/trading/backtest-runs/{run_id}")
    assert res.status_code == 200
    assert res.json()["equity_fan"] is None


def test_new_endpoints_create_nothing(tmp_path):
    """The schema-authority rule holds for the M4 additions: virgin databases
    answer empty and gain no tables for being asked."""
    from sqlalchemy import inspect as sa_inspect

    engine = make_engine(f"sqlite:///{tmp_path}/virgin3.db")
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
    assert c.get("/api/trading/signals/today").json()["signals"] == []
    assert c.get("/api/trading/strategy-panels").json() == []
    vq = c.get("/api/trading/validation-queue").json()
    assert vq["awaiting"] == [] and vq["failures"] == []
    assert c.get("/api/trading/model-registry").json()["models"] == []
    assert sa_inspect(engine).get_table_names() == before
    engine.dispose()


def test_recent_trades_carry_the_provenance_chain(client):
    """The drill-down: a trade anchored to its signal bar surfaces the
    emission's sizing chain — trade → signal → sizing, walkable in one row."""
    import datetime as dt

    from trading.models import SignalRecord, Trade

    c, sf = client
    bar = dt.datetime(2025, 6, 1, 12, tzinfo=dt.UTC)
    with sf() as session:
        session.add(
            SignalRecord(
                bot="scalp", symbol="BTCUSDT", timeframe="4h", bar_time=bar,
                side="long", confidence=0.9, outcome="entered",
                details_json=json.dumps({"qty": 0.1, "risk_amount": 20.0}),
            )
        )
        session.add(
            Trade(
                bot="scalp", symbol="BTCUSDT", side="long", qty=0.1,
                entry_price=100.0, exit_price=101.0,
                entry_time=dt.datetime(2025, 6, 1, 16, tzinfo=dt.UTC),
                exit_time=dt.datetime(2025, 6, 2, tzinfo=dt.UTC),
                pnl=10.0, fees=0.1, confidence=0.9, mode="paper",
                gate_source="kernel", signal_time=bar,
            )
        )
        session.commit()
    res = c.get("/api/trading/positions/recent-trades")
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["signal_time"] is not None
    assert row["signal_chain"]["outcome"] == "entered"
    assert row["signal_chain"]["details"] == {"qty": 0.1, "risk_amount": 20.0}


def test_recent_trades_pre_seam_have_no_chain_and_say_so(client):
    """A trade without the anchor answers null and empty — the honest shape,
    never a guessed linkage."""
    import datetime as dt

    from trading.models import Trade

    c, sf = client
    with sf() as session:
        session.add(
            Trade(
                bot="scalp", symbol="BTCUSDT", side="long", qty=0.1,
                entry_price=100.0, exit_price=101.0,
                entry_time=dt.datetime(2025, 1, 1, tzinfo=dt.UTC),
                exit_time=dt.datetime(2025, 1, 2, tzinfo=dt.UTC),
                pnl=10.0, fees=0.1, confidence=0.9, mode="paper",
                gate_source="legacy",
            )
        )
        session.commit()
    row = c.get("/api/trading/positions/recent-trades").json()[0]
    assert row["signal_time"] is None
    assert row["signal_chain"] == {}
