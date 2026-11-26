"""Behavior tests for the M4 control surfaces: the kill-switch write path
with its audit tape, and the lifecycle approval cards with the staleness
fingerprint's 409 contract.

The router is exercised on a throwaway database, exactly like
test_trading_router.py — the owner's data.db never appears in this suite."""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.trading import get_trading_db, router
from trading.models import (
    Approval,
    BacktestRun,
    BacktestValidation,
    RiskEvent,
    Strategy,
    StrategyVersion,
    Trade,
    init_schema,
    make_engine,
    make_session_factory,
)
from trading.registry import validate_and_promote
from trading.risk import killswitch_state


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
    yield TestClient(app, raise_server_exceptions=False), sf
    app.dependency_overrides.clear()
    engine.dispose()


def _paper_version(sf):
    """A fully-chained paper version: registration, a validated validation
    row whose params match, and the automatic research→validated→paper
    chain — the exact path production takes, shortened to one helper."""
    with sf() as session:
        strategy = Strategy(key="scalp", name="Scalp Trend")
        session.add(strategy)
        session.flush()
        version = StrategyVersion(
            strategy_id=strategy.id, version=1, params_json='{"stop_atr": 2.2}',
            code_hash="deadbeefcafe0001", timeframe="4h", universe_json='["BTCUSDT"]',
        )
        session.add(version)
        session.flush()
        from trading.models import StrategyState as SS
        session.add(SS(version_id=version.id, state="research", note="registered"))
        run = BacktestRun(
            bot="scalp", symbol="BTCUSDT", timeframe="4h", strategy="ScalpTrend",
            params_json='{"stop_atr": 2.2}', trades_n=40, win_rate=0.6,
            profit_factor=1.8, sharpe=1.2, max_dd_pct=-4.0, total_return_pct=9.0,
        )
        session.add(run)
        session.flush()
        validation = BacktestValidation(
            bot="scalp", symbol="BTCUSDT", timeframe="4h", strategy="ScalpTrend",
            params_json='{"stop_atr": 2.2}', seed=42, data_source="binance",
            data_rows=2000, data_start="2025-01-01", data_end="2025-11-01",
            trades_n=40, min_trades_required=30, permutation_p=0.01,
            sharpe_actual=1.2, sharpe_ci_lo=0.4, sharpe_ci_hi=2.0,
            prob_positive=0.9, wf_positive_folds=5, wf_total_folds=5,
            verdict="validated", reasons_json="[]", validation_json="{}", run_id=run.id,
        )
        session.add(validation)
        session.flush()
        validate_and_promote(session, version.id, validation.id)
        session.commit()
        return version.id


def _write_trades(sf, bot: str, n: int = 3, pnl: float = 12.5):
    import datetime as dt

    with sf() as session:
        for i in range(n):
            session.add(
                Trade(
                    bot=bot, symbol="BTCUSDT", side="long", qty=0.1,
                    entry_price=40000.0 + i, exit_price=40100.0 + i,
                    entry_time=dt.datetime(2025, 11, 1, 12, 0) + dt.timedelta(days=i),
                    exit_time=dt.datetime(2025, 11, 2, 12, 0) + dt.timedelta(days=i),
                    pnl=pnl, mode="paper",
                )
            )
        session.commit()


# ---- kill-switch ----------------------------------------------------------


def test_kill_switch_enable_writes_row_and_audit(client):
    c, sf = client
    res = c.post("/api/trading/kill-switch", json={"enabled": True})
    assert res.status_code == 200
    assert res.json()["tripped"] is True
    # the row the kernel polls is set — the engine-side seam working
    assert killswitch_state(sf)["tripped"] is True
    with sf() as session:
        events = session.execute(
            RiskEvent.__table__.select().where(RiskEvent.rail == "manual_killswitch")
        ).all()
    assert len(events) == 1
    assert events[0].decision == "tripped"
    inputs = json.loads(events[0].inputs_json)
    assert inputs["direction"] == "on"


def test_kill_switch_disable_requires_note(client):
    c, sf = client
    c.post("/api/trading/kill-switch", json={"enabled": True})
    res = c.post("/api/trading/kill-switch", json={"enabled": False, "note": ""})
    assert res.status_code == 422
    assert "note" in res.json()["detail"]
    # nothing moved: the switch stays thrown — friction must never re-arm
    assert killswitch_state(sf)["tripped"] is True
    with sf() as session:
        events = session.execute(
            RiskEvent.__table__.select().where(RiskEvent.rail == "manual_killswitch")
        ).all()
    assert len(events) == 1, "a refused re-arm writes no audit row"


def test_kill_switch_disable_with_note(client):
    c, sf = client
    c.post("/api/trading/kill-switch", json={"enabled": True, "note": "vol spike"})
    res = c.post(
        "/api/trading/kill-switch",
        json={"enabled": False, "note": "spike passed, desk flat, re-arming"},
    )
    assert res.status_code == 200
    assert res.json()["tripped"] is False
    assert killswitch_state(sf)["tripped"] is False
    with sf() as session:
        events = session.execute(
            RiskEvent.__table__.select()
            .where(RiskEvent.rail == "manual_killswitch")
            .order_by(RiskEvent.id)
        ).all()
    assert [e.decision for e in events] == ["tripped", "cleared"]
    inputs = json.loads(events[1].inputs_json)
    assert inputs["note"] == "spike passed, desk flat, re-arming"


def test_kill_switch_state_surfaces_in_rails(client):
    """The GET seam the design asked to verify: /rails already reads the
    __killswitch row live — the write path and the surface close the loop."""
    c, sf = client
    body = c.get("/api/trading/rails").json()
    assert body["manual_killswitch"] is False
    c.post("/api/trading/kill-switch", json={"enabled": True, "note": "drill"})
    body = c.get("/api/trading/rails").json()
    assert body["manual_killswitch"] is True
    assert "drill" in body["manual_killswitch_note"]


# ---- registry -------------------------------------------------------------


def test_registry_empty_is_first_class(client):
    res = client[0].get("/api/trading/registry")
    assert res.status_code == 200
    assert res.json() == {"versions": []}


def test_registry_lists_paper_version_with_card(client):
    c, sf = client
    vid = _paper_version(sf)
    body = c.get("/api/trading/registry").json()
    assert len(body["versions"]) == 1
    row = body["versions"][0]
    assert row["version_id"] == vid
    assert row["state"] == "paper"
    assert row["pending_transition"] == "candidate_live"
    assert row["validation_id"] is not None
    assert row["track_record"]["trades_count"] == 0
    assert row["track_record"]["realized_pnl"] is None
    assert len(row["fingerprint"]) == 16


def test_track_record_counts_paper_trades(client):
    c, sf = client
    vid = _paper_version(sf)
    _write_trades(sf, "scalp-v1", n=3, pnl=12.5)
    row = c.get("/api/trading/registry").json()["versions"][0]
    rec = row["track_record"]
    assert rec["trades_count"] == 3
    assert rec["realized_pnl"] == pytest.approx(37.5)
    assert rec["span_days"] == pytest.approx(2.0)


def test_approve_happy_path_transitions_to_candidate_live(client):
    c, sf = client
    vid = _paper_version(sf)
    fp = c.get("/api/trading/registry").json()["versions"][0]["fingerprint"]
    res = c.post(
        f"/api/trading/registry/{vid}/approve",
        json={"fingerprint": fp, "note": "track record reviewed"},
    )
    assert res.status_code == 200
    assert res.json()["state"] == "candidate_live"
    assert res.json()["evidence"].startswith("approval:")
    with sf() as session:
        approvals = session.execute(Approval.__table__.select()).all()
    assert len(approvals) == 1
    assert approvals[0].transition == "paper->candidate_live"
    # the registry now shows the advanced state and offers no further card —
    # candidate_live → live is structurally impossible in this milestone
    row = c.get("/api/trading/registry").json()["versions"][0]
    assert row["state"] == "candidate_live"
    assert row["pending_transition"] is None


def test_approve_stale_fingerprint_is_409(client):
    c, sf = client
    vid = _paper_version(sf)
    fp = c.get("/api/trading/registry").json()["versions"][0]["fingerprint"]
    # inputs move: a paper trade settles after the card was rendered
    _write_trades(sf, "scalp-v1", n=1)
    res = c.post(f"/api/trading/registry/{vid}/approve", json={"fingerprint": fp})
    assert res.status_code == 409
    assert "inputs moved" in res.json()["detail"]
    with sf() as session:
        assert session.execute(Approval.__table__.select()).all() == []
    # and the state never advanced
    assert c.get("/api/trading/registry").json()["versions"][0]["state"] == "paper"


def test_approve_fresh_fingerprint_after_movement_passes(client):
    """The 409 is not a dead end: reviewing the NEW record yields a new
    fingerprint that confirms — re-basing impossible, re-reviewing trivial."""
    c, sf = client
    vid = _paper_version(sf)
    c.get("/api/trading/registry").json()
    _write_trades(sf, "scalp-v1", n=2)
    fp2 = c.get("/api/trading/registry").json()["versions"][0]["fingerprint"]
    res = c.post(f"/api/trading/registry/{vid}/approve", json={"fingerprint": fp2})
    assert res.status_code == 200


def test_approve_research_state_refused(client):
    """A version still in research offers no card; posting one anyway is a
    409 naming the state, and nothing is written."""
    c, sf = client
    with sf() as session:
        strategy = Strategy(key="hft", name="HFT")
        session.add(strategy)
        session.flush()
        version = StrategyVersion(
            strategy_id=strategy.id, version=1, params_json="{}",
            code_hash="0000deadbeef0001", timeframe="1m", universe_json='["BTCUSDT"]',
        )
        session.add(version)
        session.flush()
        from trading.models import StrategyState as SS
        session.add(SS(version_id=version.id, state="research", note="registered"))
        session.commit()
        vid = version.id
    res = c.post(f"/api/trading/registry/{vid}/approve", json={"fingerprint": "whatever00000000"})
    assert res.status_code == 409
    assert "research" in res.json()["detail"]


def test_approve_unknown_version_404(client):
    res = client[0].post("/api/trading/registry/999/approve", json={"fingerprint": "x"})
    assert res.status_code == 404


def test_candidate_live_to_live_never_offered(client):
    """Design §6: live needs a mandate that does not exist. After approval
    the registry must offer NO card for the live transition — an offer the
    guards must refuse would be a lie in chrome."""
    c, sf = client
    vid = _paper_version(sf)
    fp = c.get("/api/trading/registry").json()["versions"][0]["fingerprint"]
    c.post(f"/api/trading/registry/{vid}/approve", json={"fingerprint": fp})
    row = c.get("/api/trading/registry").json()["versions"][0]
    assert row["state"] == "candidate_live"
    assert row["pending_transition"] is None
    res = c.post(f"/api/trading/registry/{vid}/approve", json={"fingerprint": row["fingerprint"]})
    assert res.status_code == 409
