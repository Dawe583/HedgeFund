"""The fund overview: ledger wealth beside the engine's figure, never summed,
and the reconciliation between the two statements about the same money.

Each state the design calls first-class is measured here: no engine ever
ran, a dollar figure no rate converts, an account with nothing on record,
a mapping pointed at air. Every name and amount is invented.
"""

from __future__ import annotations

import datetime

import pytest

from app import models
from app.database import SessionLocal, engine

TODAY = datetime.date.today().isoformat()


def _institution(client, name="BitDesk") -> int:
    return client.post("/api/institutions", json={"name": name, "type": "broker"}).json()["id"]


def _snapshot_with_holding(client, institution_id: int, value: float, date: str = TODAY) -> None:
    sid = client.post(
        f"/api/institutions/{institution_id}/snapshots", json={"date": date}
    ).json()["id"]
    r = client.post(
        f"/api/snapshots/{sid}/holdings",
        json={"asset_name": "Desk basket", "asset_class": "equity", "value": value, "currency": "EUR"},
    )
    assert r.status_code in (200, 201), r.text


def _anchor(client, institution_id: int, amount: float, date: str = TODAY) -> None:
    r = client.post(
        f"/api/institutions/{institution_id}/cash-anchors",
        json={"date": date, "amount": amount, "currency": "EUR"},
    )
    assert r.status_code in (200, 201), r.text


@pytest.fixture
def engine_tables():
    """The equity table, as Alembic would have migrated it, with nothing in it
    after the test — the wealth schema sweep does not know the trading tables,
    so this fixture sweeps its own."""
    from trading.models import Base as TradingBase

    TradingBase.metadata.create_all(bind=engine)
    yield
    with engine.begin() as conn:
        conn.execute(TradingBase.metadata.tables["equity_points"].delete())


def _equity_point(value: float, ts: str = "2026-11-26 00:19:00") -> None:
    from trading.models import EquityPoint

    with SessionLocal() as db:
        db.add(EquityPoint(bot="portfolio", ts=datetime.datetime.fromisoformat(ts), equity=value))
        db.commit()


def _seed_usd(rate: float = 2.0) -> None:
    """The ECB said two dollars to the euro on the day in force: a dollar
    figure converts at half, and the tests below count on exactly that."""
    with SessionLocal() as db:
        db.add(models.FxRate(base="EUR", currency="USD", rate=rate, as_of=TODAY,
                             fetched_at=datetime.datetime.now(datetime.timezone.utc).isoformat()))
        db.commit()


def _overview(client) -> dict:
    r = client.get("/api/overview/fund")
    assert r.status_code == 200, r.text
    return r.json()


# --- total wealth: the ledger's own figure, never reimplemented -------------


def test_the_total_is_the_dashboards_own_figure(client):
    iid = _institution(client)
    _snapshot_with_holding(client, iid, 1000)
    overview = _overview(client)
    summary = client.get("/api/dashboard/summary").json()
    assert overview["total_wealth"]["net_worth"] == summary["net_worth"] == 1000


def test_engine_equity_never_enters_net_worth(client, engine_tables):
    """D13: the broker statement already contains the money; an engine row
    beside it is a comparison, not an addition."""
    iid = _institution(client)
    _snapshot_with_holding(client, iid, 1000)
    before = _overview(client)["total_wealth"]["net_worth"]
    _equity_point(9_999_999)
    after = _overview(client)["total_wealth"]["net_worth"]
    assert before == after == 1000


# --- the engine's figure, honestly absent or honestly present ---------------


def test_an_engine_that_never_ran_is_a_state_not_an_error(client):
    equity = _overview(client)["trading_equity"]
    assert equity["available"] is False
    assert equity["value"] is None
    assert equity["as_of"] is None


def test_the_latest_portfolio_equity_is_reported_with_its_time(client, engine_tables):
    _equity_point(1100.5)
    equity = _overview(client)["trading_equity"]
    assert equity["available"] is True
    assert equity["value"] == 1100.5
    assert equity["as_of"].startswith("2026-11-26")
    assert equity["source"] == "equity_points"


def test_a_dollar_figure_no_rate_converts_is_not_passed_through(client, engine_tables):
    """Without a stored rate, `value_base` is None — a dollar figure read as
    euro would be the wrong answer wearing the right one's clothes."""
    _equity_point(1100)
    equity = _overview(client)["trading_equity"]
    assert equity["available"] is True
    assert equity["value_base"] is None


def test_engine_equity_converts_at_the_day_in_force(client, engine_tables):
    _equity_point(1100)
    _seed_usd(2.0)
    assert _overview(client)["trading_equity"]["value_base"] == 550.0


# --- the reconciliation: what is missing is said, never pretended ------------


def test_no_mapping_and_no_engine_are_both_said(client):
    recon = _overview(client)["reconciliation"]
    assert "no-mapping" in recon["missing"]
    assert "no-engine-equity" in recon["missing"]
    assert recon["gap"] is None
    assert recon["statement_total"] is None


def test_the_gap_is_the_statement_minus_the_engine(client, engine_tables):
    iid = _institution(client)
    client.put("/api/overview/trading-account", json={"institution_id": iid})
    _snapshot_with_holding(client, iid, 1000)
    _anchor(client, iid, 500)
    _equity_point(1200)
    _seed_usd(2.0)  # the engine's 1,200 dollars are 600 euro

    recon = _overview(client)["reconciliation"]
    assert recon["missing"] == []
    assert recon["institution_name"] == "BitDesk"
    assert recon["statement_positions"] == 1000
    assert recon["statement_cash"] == 500
    assert recon["statement_total"] == 1500
    assert recon["statement_date"] == TODAY
    assert recon["engine_equity_base"] == 600
    # Positive: the ledger reads more than the engine believes it holds.
    assert recon["gap"] == pytest.approx(900)


def test_an_account_with_nothing_on_record_says_no_statement(client):
    iid = _institution(client)
    client.put("/api/overview/trading-account", json={"institution_id": iid})
    recon = _overview(client)["reconciliation"]
    assert "no-statement" in recon["missing"]
    assert recon["gap"] is None


def test_a_mapping_pointed_at_air_is_said(client, engine_tables):
    iid = _institution(client)
    client.put("/api/overview/trading-account", json={"institution_id": iid})
    client.delete(f"/api/institutions/{iid}")
    recon = _overview(client)["reconciliation"]
    assert "institution-gone" in recon["missing"]
    assert "no-mapping" not in recon["missing"]


def test_an_unconvertible_engine_figure_blocks_the_gap_honestly(client, engine_tables):
    iid = _institution(client)
    client.put("/api/overview/trading-account", json={"institution_id": iid})
    _anchor(client, iid, 500)
    _equity_point(1200)  # no USD rate seeded: nothing converts the dollars

    recon = _overview(client)["reconciliation"]
    assert "equity-unconvertible" in recon["missing"]
    assert recon["gap"] is None
    assert recon["statement_total"] == 500


def test_a_cash_only_statement_is_a_statement(client, engine_tables):
    iid = _institution(client)
    client.put("/api/overview/trading-account", json={"institution_id": iid})
    _anchor(client, iid, 800)
    _equity_point(1600)
    _seed_usd(2.0)

    recon = _overview(client)["reconciliation"]
    assert recon["missing"] == []
    assert recon["statement_positions"] is None or recon["statement_positions"] == 0
    assert recon["statement_total"] == 800
    assert recon["gap"] == pytest.approx(0)


# --- the mapping itself ------------------------------------------------------


def test_the_mapping_refuses_an_institution_that_is_not_there(client):
    r = client.put("/api/overview/trading-account", json={"institution_id": 999})
    assert r.status_code == 404


def test_the_mapping_can_be_changed(client):
    first, second = _institution(client, "Desk One"), _institution(client, "Desk Two")
    r = client.put("/api/overview/trading-account", json={"institution_id": first})
    assert r.status_code == 200, r.text
    assert r.json()["institution_id"] == first
    r = client.put("/api/overview/trading-account", json={"institution_id": second})
    assert r.json()["institution_id"] == second
    assert "no-mapping" not in r.json()["missing"]
