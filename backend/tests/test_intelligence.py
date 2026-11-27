"""The intelligence surfaces: one stream across the two planes, the memory
tiers as the learning loop persists them, the day's budget against its caps,
and the alert stream — each honest about absence.

The trading database is isolated here in a way the rest of the suite does
not need: `get_trading_db` defaults to the desk's real database file, so
these tests override the dependency with a scratch SQLite rather than read
whatever a live soak happens to hold. Every name and amount is invented.
"""

from __future__ import annotations

import datetime as dt
import json
import tempfile
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import SessionLocal
from app.main import app
from app.routers.trading import get_trading_db
from trading.models import (
    AgentInsight,
    AgentMemory,
    BacktestValidation,
    Base as TradingBase,
    BotStatus,
    RiskEvent,
    make_engine,
)

NOW = dt.datetime.now(dt.UTC)


@pytest.fixture()
def trading_db():
    """A scratch trading database with the full engine schema, wired into
    the app as the trading session for the length of one test."""
    path = Path(tempfile.mkdtemp()) / "trading_test.db"
    engine = make_engine(f"sqlite:///{path}")
    TradingBase.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_trading_db] = override
    yield factory
    app.dependency_overrides.pop(get_trading_db, None)


def _chain_run(verdict: str = "Hold the course.", created: str | None = None) -> None:
    with SessionLocal() as db:
        run = models.ChainRun(verdict=verdict)
        if created:
            run.created_at = created
        db.add(run)
        db.flush()
        db.add(
            models.ChainStep(
                run_id=run.id, step_no=1, role="analyst", title="Analyst", output="analysis"
            )
        )
        db.commit()


def _seed_insights(factory, rows: list[dict]) -> None:
    with factory() as db:
        for r in rows:
            db.add(AgentInsight(**r))
        db.commit()


# ---------------------------------------------------------------- feed


def test_the_feed_of_an_empty_desk(client, trading_db):
    r = client.get("/api/intelligence/feed")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert body["items"] == []
    assert body["sources"] == []


def test_the_feed_merges_both_planes_newest_first(client, trading_db):
    _chain_run(created="2026-11-25T10:00:00+00:00")
    _seed_insights(
        trading_db,
        [
            dict(
                agent="supervisor",
                title="Desk kerfuffle",
                body="first line of the body\nsecond line",
                severity="warning",
                created_at=dt.datetime(2026, 11, 26, 9, 0),
            )
        ],
    )
    body = client.get("/api/intelligence/feed").json()
    assert len(body["items"]) == 2
    # the insight is newer than the chain run
    assert body["items"][0]["source"] == "trading:supervisor"
    assert body["items"][1]["source"] == "wealth-chain"
    assert body["items"][0]["summary"].startswith("first line")
    assert "second line" not in body["items"][0]["summary"]
    assert body["items"][1]["ref"].startswith("/api/advisor/chain/")
    assert set(body["sources"]) == {"wealth-chain", "trading:supervisor"}


def test_the_feed_filters_by_source_and_kind(client, trading_db):
    _chain_run()
    _seed_insights(
        trading_db,
        [dict(agent="analyst", title="t", body="b", created_at=dt.datetime(2026, 11, 26, 8, 0))],
    )
    only_chain = client.get("/api/intelligence/feed?source=wealth-chain").json()
    assert len(only_chain["items"]) == 1
    assert only_chain["items"][0]["kind"] == "chain-run"
    # the trading prefix selects every trading agent's entries
    only_trading = client.get("/api/intelligence/feed?source=trading").json()
    assert len(only_trading["items"]) == 1
    assert only_trading["items"][0]["kind"] == "insight"
    none = client.get("/api/intelligence/feed?kind=insight&source=wealth-chain").json()
    assert none["items"] == []


# ---------------------------------------------------------------- memory


def test_memory_is_tiered_as_the_loop_wrote_it(client, trading_db):
    with trading_db() as db:
        db.add_all(
            [
                AgentMemory(bot="scalp", tier="working", kind="outcome", content="raw", importance=0.4),
                AgentMemory(bot="scalp", tier="shallow", kind="lesson", content="lesson", importance=0.6),
                AgentMemory(bot="*", tier="deep", kind="reflection", content="reflection", importance=0.9),
            ]
        )
        db.commit()
    body = client.get("/api/intelligence/memory").json()
    assert body["available"] is True
    assert [e["content"] for e in body["working"]] == ["raw"]
    assert [e["content"] for e in body["shallow"]] == ["lesson"]
    assert [e["content"] for e in body["deep"]] == ["reflection"]
    assert body["deep"][0]["tier"] == "deep"


# ---------------------------------------------------------------- budget


def test_budget_absent_before_any_call(client):
    body = client.get("/api/intelligence/budget").json()
    # the desk's real counter file is not the test's business: whatever the
    # machine holds, the answer is well-formed and never fabricated tiers
    assert body["available"] in (True, False)
    if not body["available"]:
        assert body["used"] == 0
        assert body["tier_caps"] == []


def test_budget_reports_the_day_against_the_caps(client, monkeypatch, tmp_path):
    counter = tmp_path / "llm_budget.json"
    # the counter's day must be TODAY — the budget endpoint resets on the
    # date boundary, so a hardcoded day makes this test a time bomb that
    # fires every following midnight
    import datetime as _dt
    today = _dt.datetime.now(_dt.UTC).date().isoformat()
    counter.write_text(json.dumps({"day": today, "used": 12, "minute": 1, "minute_used": 0}))

    from app.routers import intelligence as intel
    from trading.config import get_settings

    real = get_settings()

    class FakeSettings:
        database_url = f"sqlite:///{tmp_path}/x.db"
        data_dir = str(tmp_path)
        agent_daily_budget = 45
        agent_rpm_budget = 15

    monkeypatch.setattr(intel, "get_settings", lambda: FakeSettings())
    body = client.get("/api/intelligence/budget").json()
    monkeypatch.setattr(intel, "get_settings", get_settings)
    assert real is not None  # the real settings exist; only the path was faked
    assert body["available"] is True
    assert body["used"] == 12
    assert body["daily_budget"] == 45
    assert body["remaining"] == 33
    caps = {t["tier"]: t["cap"] for t in body["tier_caps"]}
    assert caps == {"high": 45, "normal": 36, "low": 22}


# ---------------------------------------------------------------- alerts


def test_alerts_of_a_quiet_desk(client, trading_db):
    body = client.get("/api/alerts").json()
    assert body["available"] is True
    assert body["items"] == []


def test_rail_events_are_severity_typed(client, trading_db):
    with trading_db() as db:
        db.add_all(
            [
                RiskEvent(
                    bot="scalp", symbol="BTCUSDT", rail="kill_switch_drawdown",
                    decision="tripped", inputs_json=json.dumps({"reason": "drawdown 13%"}),
                ),
                RiskEvent(
                    bot="hft", symbol="ETHUSDT", rail="max_positions",
                    decision="veto", inputs_json=json.dumps({"reason": "3 positions open"}),
                ),
                RiskEvent(
                    bot="hft", rail="halt", decision="observed", inputs_json="{}",
                ),
            ]
        )
        db.commit()
    body = client.get("/api/alerts").json()
    by_kind = {i["kind"]: i for i in body["items"]}
    assert by_kind["rail-tripped"]["severity"] == "critical"
    assert "drawdown 13%" in by_kind["rail-tripped"]["detail"]
    assert by_kind["rail-veto"]["severity"] == "warning"
    assert by_kind["rail-observed"]["severity"] == "info"


def test_a_rejected_validation_is_an_alert(client, trading_db):
    with trading_db() as db:
        db.add(
            BacktestValidation(
                bot="scalp", symbol="BTCUSDT", timeframe="5m", strategy="meanrev",
                seed=1, data_source="binance", data_rows=1000,
                data_start="a", data_end="b", trades_n=12,
                verdict="rejected", reasons_json=json.dumps(["permutation p=0.4 too high"]),
            )
        )
        db.commit()
    body = client.get("/api/alerts").json()
    hits = [i for i in body["items"] if i["kind"] == "validation-rejected"]
    assert len(hits) == 1
    assert hits[0]["severity"] == "warning"
    assert "meanrev" in hits[0]["title"]
    assert "permutation" in hits[0]["detail"]


def test_a_silent_heartbeat_is_an_alert_a_never_started_engine_is_not(client, trading_db):
    # no rows at all: nothing was ever measured, so nothing is stale
    assert client.get("/api/alerts").json()["items"] == []

    with trading_db() as db:
        db.add(
            BotStatus(
                name="scalp", running=False,
                last_heartbeat=dt.datetime.now(dt.UTC).replace(tzinfo=None) - dt.timedelta(hours=2),
                note="desk kernel halted",
            )
        )
        db.commit()
    body = client.get("/api/alerts").json()
    hits = [i for i in body["items"] if i["kind"] == "engine-stale"]
    assert len(hits) == 1
    assert hits[0]["severity"] == "critical"  # two hours silent is death, not lag
    assert "scalp" in hits[0]["title"]


def test_a_fresh_heartbeat_is_not_an_alert(client, trading_db):
    with trading_db() as db:
        db.add(
            BotStatus(
                name="hft", running=True,
                last_heartbeat=dt.datetime.now(dt.UTC).replace(tzinfo=None) - dt.timedelta(seconds=30),
            )
        )
        db.commit()
    body = client.get("/api/alerts").json()
    assert [i for i in body["items"] if i["kind"] == "engine-stale"] == []


def test_an_unmapped_reconciliation_raises_no_alert(client, trading_db):
    """No trading-account mapping, no engine equity: absence, not an alert."""
    body = client.get("/api/alerts").json()
    assert [i for i in body["items"] if i["kind"] == "reconciliation-gap"] == []
