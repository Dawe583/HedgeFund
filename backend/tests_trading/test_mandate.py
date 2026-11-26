"""M5 behavior tests — the mandate machinery, the guard chain, the halt
sentinel and the audit ledger.

The acceptance test of the milestone is here: the guard chain demonstrably
blocks a violating order even when every software layer above it is bypassed
— the test calls evaluate_order at its lowest level, with nothing between
the caller and the verdict but the sentinel file's existence.

The router is exercised on a throwaway database, exactly like
test_m4_controls.py — the owner's data.db never appears in this suite."""

import datetime as dt
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.trading import get_trading_db, router
from trading.mandate import (
    GENESIS_HASH,
    GuardState,
    OrderIntent,
    active_mandate,
    append_audit,
    create_mandate,
    evaluate_order,
    mandate_integrity_ok,
    verify_chain,
)
from trading.models import (
    AuditLedger,
    AuditSignoff,
    OrderCard,
    Strategy,
    StrategyMandate,
    StrategyState as SS,
    StrategyVersion,
    init_schema,
    make_engine,
    make_session_factory,
)
from trading.registry import TransitionRefused, transition

CAPS = {
    "max_order_notional": 500.0,
    "max_exposure": 1000.0,
    "instruments": ["BTCUSDT"],
    "max_trades_per_day": 5,
    "consent_days": 30,
    "funding_min": 100.0,
    "funding_max": 2000.0,
}


@pytest.fixture
def sf(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/trading.db")
    init_schema(engine)
    factory = make_session_factory(engine)
    yield factory
    engine.dispose()


@pytest.fixture
def client(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/trading.db")
    init_schema(engine)
    factory = make_session_factory(engine)

    def override():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_trading_db] = override
    yield TestClient(app, raise_server_exceptions=False), factory
    app.dependency_overrides.clear()
    engine.dispose()


def _version(sf, state: str = "candidate_live") -> int:
    """A registered version walked to the requested lifecycle state by hand —
    the states paper→candidate_live normally needs an approval row for, but
    the transition guards are tested separately; here the fixture only needs
    a version IN the state."""
    with sf() as session:
        strategy = Strategy(key="scalp", name="Scalp Trend")
        session.add(strategy)
        session.flush()
        version = StrategyVersion(
            strategy_id=strategy.id, version=1, params_json="{}",
            code_hash="deadbeefcafe0001", timeframe="4h", universe_json='["BTCUSDT"]',
        )
        session.add(version)
        session.flush()
        chain = ["research", "validated", "paper", "candidate_live", "live"]
        for s in chain[: chain.index(state) + 1]:
            session.add(SS(version_id=version.id, state=s, note="fixture"))
        session.commit()
        return version.id


def _mandate(session, version_id: int, **over) -> StrategyMandate:
    caps = dict(CAPS, **over)
    return create_mandate(session, version_id=version_id, caps=caps, created_by="test")


# ---- the guard chain, unit by unit ----------------------------------------


def test_chain_allows_within_all_caps(sf, tmp_path):
    with sf() as session:
        vid = _version(sf)
        m = _mandate(session, vid)
        session.commit()
        verdict = evaluate_order(
            m, OrderIntent("BTCUSDT", "long", 100.0), GuardState(),
            sentinel_path=str(tmp_path / "HALT"), session=session,
        )
    assert verdict.verdict == "allow"
    assert verdict.check == "passed"


def test_chain_denies_instrument_not_allowed(sf, tmp_path):
    with sf() as session:
        vid = _version(sf)
        m = _mandate(session, vid)
        session.commit()
        verdict = evaluate_order(
            m, OrderIntent("ETHUSDT", "long", 100.0), GuardState(),
            sentinel_path=str(tmp_path / "HALT"),
        )
    assert verdict.verdict == "deny"
    assert verdict.check == "instrument"
    assert "ETHUSDT" in verdict.reason


def test_chain_denies_notional_over_cap(sf, tmp_path):
    with sf() as session:
        vid = _version(sf)
        m = _mandate(session, vid)
        session.commit()
        verdict = evaluate_order(
            m, OrderIntent("BTCUSDT", "long", 501.0), GuardState(),
            sentinel_path=str(tmp_path / "HALT"),
        )
    assert verdict.verdict == "deny"
    assert verdict.check == "notional_cap"
    assert "501" in verdict.reason


def test_chain_denies_exposure_over_cap(sf, tmp_path):
    """Exposure is measured WITH the order added — a 400 order on 700 open
    exceeds a 1000 cap even though the order alone is within its own cap."""
    with sf() as session:
        vid = _version(sf)
        m = _mandate(session, vid)
        session.commit()
        verdict = evaluate_order(
            m, OrderIntent("BTCUSDT", "long", 400.0), GuardState(current_exposure=700.0),
            sentinel_path=str(tmp_path / "HALT"),
        )
    assert verdict.verdict == "deny"
    assert verdict.check == "exposure_cap"


def test_chain_denies_daily_count_at_cap(sf, tmp_path):
    with sf() as session:
        vid = _version(sf)
        m = _mandate(session, vid)
        session.commit()
        verdict = evaluate_order(
            m, OrderIntent("BTCUSDT", "long", 100.0), GuardState(trades_today=5),
            sentinel_path=str(tmp_path / "HALT"),
        )
    assert verdict.verdict == "deny"
    assert verdict.check == "daily_count_cap"


def test_chain_no_mandate_is_deny_not_crash(sf, tmp_path):
    verdict = evaluate_order(
        None, OrderIntent("BTCUSDT", "long", 100.0), GuardState(),
        sentinel_path=str(tmp_path / "HALT"),
    )
    assert verdict.verdict == "deny"
    assert verdict.check == "no_mandate"


def test_chain_expired_mandate_is_reauth(sf, tmp_path):
    with sf() as session:
        vid = _version(sf)
        m = _mandate(session, vid, consent_days=30)
        # age the consent past its window
        m.created_at = dt.datetime.now(dt.UTC).replace(tzinfo=None) - dt.timedelta(days=31)
        session.commit()
        verdict = evaluate_order(
            m, OrderIntent("BTCUSDT", "long", 100.0), GuardState(),
            sentinel_path=str(tmp_path / "HALT"),
        )
    assert verdict.verdict == "reauth"
    assert verdict.check == "mandate_expired"


def test_chain_consent_expiring_soon_pauses_for_reauth(sf, tmp_path):
    with sf() as session:
        vid = _version(sf)
        m = _mandate(session, vid, consent_days=30)
        m.created_at = dt.datetime.now(dt.UTC).replace(tzinfo=None) - dt.timedelta(days=28)
        session.commit()
        verdict = evaluate_order(
            m, OrderIntent("BTCUSDT", "long", 100.0), GuardState(),
            sentinel_path=str(tmp_path / "HALT"),
        )
    assert verdict.verdict == "reauth"
    assert verdict.check == "consent_expiring"


def test_chain_fail_closed_on_internal_error(sf, tmp_path):
    """A mandate whose instruments_json is garbage crashes the instrument
    check — the chain must answer deny, never propagate, never allow."""
    with sf() as session:
        vid = _version(sf)
        m = _mandate(session, vid)
        m.instruments_json = "{not json"
        # force the integrity check to pass so the failure lands mid-chain
        m.mandate_hash = __import__("trading.mandate", fromlist=["mandate_payload_hash"]).mandate_payload_hash(
            version_id=vid, max_order_notional=m.max_order_notional, max_exposure=m.max_exposure,
            instruments=[], max_trades_per_day=m.max_trades_per_day, consent_days=m.consent_days,
            funding_min=m.funding_min, funding_max=m.funding_max,
        )
        # tamper back AFTER fixing the hash: json.loads will raise mid-chain
        object.__setattr__(m, "instruments_json", "{not json")
        import trading.mandate as mm
        real = mm.mandate_integrity_ok
        mm.mandate_integrity_ok = lambda row: True
        try:
            verdict = evaluate_order(
                m, OrderIntent("BTCUSDT", "long", 100.0), GuardState(),
                sentinel_path=str(tmp_path / "HALT"),
            )
        finally:
            mm.mandate_integrity_ok = real
    assert verdict.verdict == "deny"
    assert verdict.check == "internal_error"
    assert "fail-closed" in verdict.reason


def test_chain_tampered_mandate_hash_denies(sf, tmp_path):
    with sf() as session:
        vid = _version(sf)
        m = _mandate(session, vid)
        session.commit()
        # tamper: raise the notional cap outside every write path
        m.max_order_notional = 99999.0
        assert mandate_integrity_ok(m) is False
        verdict = evaluate_order(
            m, OrderIntent("BTCUSDT", "long", 100.0), GuardState(),
            sentinel_path=str(tmp_path / "HALT"),
        )
    assert verdict.verdict == "deny"
    assert verdict.check == "mandate_integrity"


def test_every_evaluation_lands_in_audit_ledger(sf, tmp_path):
    with sf() as session:
        vid = _version(sf)
        m = _mandate(session, vid)
        session.commit()
        evaluate_order(
            m, OrderIntent("BTCUSDT", "long", 100.0), GuardState(),
            sentinel_path=str(tmp_path / "HALT"), session=session,
        )
        evaluate_order(
            m, OrderIntent("ETHUSDT", "long", 100.0), GuardState(),
            sentinel_path=str(tmp_path / "HALT"), session=session,
        )
        session.commit()
        rows = session.execute(AuditLedger.__table__.select()).all()
    guard_rows = [r for r in rows if r.action == "order_evaluation"]
    assert len(guard_rows) == 2
    verdicts = [json.loads(r.payload_json)["verdict"] for r in guard_rows]
    assert verdicts == ["allow", "deny"]


# ---- THE ACCEPTANCE TEST — layer 4, everything above bypassed --------------


def test_sentinel_halts_order_with_every_layer_above_bypassed(tmp_path):
    """M5 acceptance, verbatim: the mandate machinery demonstrably blocks a
    violating order in tests even when every software layer above it is
    bypassed. No router, no registry, no kernel, no desk — the test creates
    the sentinel file and calls the guard chain at its lowest level. The
    order is otherwise perfectly legal: right instrument, within every cap,
    fresh consent. The sentinel alone must answer deny."""
    sentinel = tmp_path / "HALT"
    engine = make_engine(f"sqlite:///{tmp_path}/trading.db")
    init_schema(engine)
    sf = make_session_factory(engine)
    with sf() as session:
        vid = _version(sf)
        m = _mandate(session, vid)
        session.commit()

        # control: sentinel absent, the same order passes the sentinel check
        # and proceeds to the remaining caps — which it satisfies.
        verdict_clear = evaluate_order(
            m, OrderIntent("BTCUSDT", "long", 100.0), GuardState(),
            sentinel_path=str(sentinel),
        )
        assert verdict_clear.verdict == "allow"
        assert verdict_clear.check == "passed"

        # the sentinel appears — the ONLY change. Software layers above are
        # not bypassed in the metaphorical sense: they are absent entirely.
        sentinel.write_bytes(b"halt")
        verdict_halted = evaluate_order(
            m, OrderIntent("BTCUSDT", "long", 100.0), GuardState(),
            sentinel_path=str(sentinel),
        )
        assert verdict_halted.verdict == "deny"
        assert verdict_halted.check == "halt_sentinel"
        assert "halt sentinel" in verdict_halted.reason
    engine.dispose()


def test_corrupt_sentinel_still_halts(tmp_path):
    """The file's content is never parsed — garbage bytes halt exactly like
    a well-formed file. Content-agnosticism is the design: the day the
    sentinel matters is the day everything else is wrong, including whatever
    writes files."""
    sentinel = tmp_path / "HALT"
    sentinel.write_bytes(b"\x00\xff\xfe random garbage \x80\x81 not even utf-8 \x00")
    verdict = evaluate_order(
        None, {"symbol": "BTCUSDT", "side": "long", "notional": 1.0}, None,
        sentinel_path=str(sentinel),
    )
    assert verdict.verdict == "deny"
    assert verdict.check == "halt_sentinel"


def test_sentinel_outranks_every_other_check(tmp_path):
    """A violating order AND the sentinel: the sentinel's denial is the one
    reported — it is the first check in the chain, before consent, before
    caps."""
    sentinel = tmp_path / "HALT"
    sentinel.write_bytes(b"")
    engine = make_engine(f"sqlite:///{tmp_path}/trading.db")
    init_schema(engine)
    sf = make_session_factory(engine)
    with sf() as session:
        vid = _version(sf)
        session.expire_all()  # the ORM identity map must not shadow the tamper
        m = _mandate(session, vid)
        session.commit()
        verdict = evaluate_order(
            m, OrderIntent("WRONG", "long", 999999.0), GuardState(trades_today=99),
            sentinel_path=str(sentinel),
        )
    assert verdict.check == "halt_sentinel"
    engine.dispose()


# ---- the audit ledger — append-only, hash-chained --------------------------


def test_chain_links_and_verifies_clean(sf):
    with sf() as session:
        append_audit(session, "human", "first", {"n": 1})
        append_audit(session, "system", "second", {"n": 2})
        append_audit(session, "guard", "third", {"n": 3})
        session.commit()
        assert verify_chain(session) == []
        rows = session.execute(AuditLedger.__table__.select().order_by(AuditLedger.id)).all()
    assert rows[0].prev_hash == GENESIS_HASH
    assert rows[1].prev_hash == rows[0].hash
    assert rows[2].prev_hash == rows[1].hash
    assert len({r.hash for r in rows}) == 3


def test_tampered_payload_breaks_chain_naming_the_row(sf):
    """Flip a payload in a scratch database — verification must fail and
    name exactly the row that no longer matches its hash."""
    with sf() as session:
        append_audit(session, "human", "one", {"n": 1})
        row2 = append_audit(session, "human", "two", {"n": 2})
        append_audit(session, "human", "three", {"n": 3})
        session.commit()
        # tamper directly, bypassing every application path — the attack the
        # chain exists to detect.
        session.execute(
            AuditLedger.__table__.update()
            .where(AuditLedger.id == row2.id)
            .values(payload_json='{"n":999}')
        )
        session.commit()
        session.expire_all()  # the ORM identity map must not shadow the tamper
        violations = verify_chain(session)
    assert violations, "a tampered payload must not verify"
    assert any(f"row {row2.id}" in v for v in violations), violations


def test_no_update_or_delete_paths_exist():
    """The append-only contract is structural: trading.mandate exports no
    update or delete for the ledger — the audit's integrity is a property
    of what does not exist, not of what is merely unlikely."""
    import trading.mandate as mm

    exported = [n for n in dir(mm) if not n.startswith("_")]
    assert not any("update" in n.lower() or "delete" in n.lower() for n in exported), exported
    # and the model layer exposes nothing either — grep-level enforcement
    import inspect as _inspect

    src = _inspect.getsource(mm)
    assert ".delete()" not in src
    assert "update(" not in src.replace("__table__.update", "TABLEUPDATE_TEST_OK")


# ---- the mandate rows — immutable, human-only write path --------------------


def test_mandate_creation_roundtrip_and_supersede(sf):
    with sf() as session:
        vid = _version(sf)
        m1 = _mandate(session, vid)
        session.commit()
        assert mandate_integrity_ok(m1)
        assert active_mandate(session, vid).id == m1.id
        # a second mandate supersedes by id — the old row is untouched,
        # immutable history of what consent used to be.
        m2 = _mandate(session, vid, max_order_notional=250.0)
        session.commit()
        assert active_mandate(session, vid).id == m2.id
        rows = session.execute(StrategyMandate.__table__.select()).all()
    assert len(rows) == 2


def test_mandate_expired_is_not_active(sf):
    with sf() as session:
        vid = _version(sf)
        m = _mandate(session, vid)
        m.created_at = dt.datetime.now(dt.UTC).replace(tzinfo=None) - dt.timedelta(days=31)
        session.commit()
        assert active_mandate(session, vid) is None


def test_mandate_endpoint_requires_full_caps(client):
    """The echo discipline: a body missing any cap is 422 — the human types
    the numbers or nothing is written. pydantic's required fields enforce it."""
    c, sf = client
    vid = _version(sf)
    for missing in ["max_order_notional", "max_exposure", "instruments", "max_trades_per_day", "funding_min", "funding_max"]:
        body = {"version_id": vid, **CAPS}
        body.pop(missing)
        res = c.post("/api/trading/mandates", json=body)
        assert res.status_code == 422, f"{missing} missing must refuse"
    with sf() as session:
        assert session.execute(StrategyMandate.__table__.select()).all() == []


def test_mandate_endpoint_happy_path_writes_row_and_audit(client):
    c, sf = client
    vid = _version(sf)
    res = c.post("/api/trading/mandates", json={"version_id": vid, **CAPS, "note": "initial consent, small pilot"})
    assert res.status_code == 200
    body = res.json()["mandates"][0]
    assert body["max_order_notional"] == 500.0
    assert body["active"] is True
    assert body["integrity_ok"] is True
    with sf() as session:
        audits = [r for r in session.execute(AuditLedger.__table__.select()).all() if r.action == "mandate_created"]
    assert len(audits) == 1
    assert json.loads(audits[0].payload_json)["caps"]["max_exposure"] == 1000.0


def test_mandates_empty_is_first_class(client):
    body = client[0].get("/api/trading/mandates").json()
    assert body == {"mandates": []}


def test_mandate_unknown_version_404(client):
    res = client[0].post("/api/trading/mandates", json={"version_id": 999, **CAPS})
    assert res.status_code == 404


# ---- candidate_live → live: the two independent gates -----------------------


def test_live_refused_without_mandate_and_signoff(sf):
    with sf() as session:
        vid = _version(sf, state="candidate_live")
        session.commit()
        with pytest.raises(TransitionRefused) as exc:
            transition(session, vid, "live")
    msg = str(exc.value)
    assert "no active mandate" in msg
    assert "no audit signoff" in msg


def test_live_refused_with_mandate_but_no_signoff(sf):
    """The two gates are independent: consent alone is not readiness."""
    with sf() as session:
        vid = _version(sf, state="candidate_live")
        _mandate(session, vid)
        session.commit()
        with pytest.raises(TransitionRefused) as exc:
            transition(session, vid, "live")
    msg = str(exc.value)
    assert "no active mandate" not in msg
    assert "no audit signoff" in msg


def test_live_refused_with_signoff_but_no_mandate(sf):
    """And an audit without consent is not permission — the mirror image."""
    with sf() as session:
        vid = _version(sf, state="candidate_live")
        session.add(AuditSignoff(version_id=vid, created_by="test", document_ref="docs/audit.md", note="reviewed"))
        session.commit()
        with pytest.raises(TransitionRefused) as exc:
            transition(session, vid, "live")
    assert "no active mandate" in str(exc.value)


def test_live_transition_with_both_gates_names_evidence(sf):
    with sf() as session:
        vid = _version(sf, state="candidate_live")
        m = _mandate(session, vid)
        session.flush()
        s = AuditSignoff(version_id=vid, created_by="test", document_ref="docs/audit.md#sha", note="reviewed")
        session.add(s)
        session.commit()
        row = transition(session, vid, "live", note="audit signed, pilot consent granted")
        session.commit()
        assert row.state == "live"
        assert row.evidence == f"mandate:{m.id}+signoff:{s.id}"
        # the transition wrote its own audit row
        audits = [r for r in session.execute(AuditLedger.__table__.select()).all() if r.action == "lifecycle_transition_live"]
        assert len(audits) == 1
        assert verify_chain(session) == []


def test_expired_mandate_blocks_live_even_with_signoff(sf):
    with sf() as session:
        vid = _version(sf, state="candidate_live")
        m = _mandate(session, vid)
        m.created_at = dt.datetime.now(dt.UTC).replace(tzinfo=None) - dt.timedelta(days=31)
        session.add(AuditSignoff(version_id=vid, created_by="test", document_ref="x", note="reviewed"))
        session.commit()
        with pytest.raises(TransitionRefused) as exc:
            transition(session, vid, "live")
    assert "no active mandate" in str(exc.value)


# ---- order cards — lifecycle, fingerprint, 409 ------------------------------


def test_card_create_and_confirm_denied_without_mandate(client):
    """In M5 the release terminates at the guard chain: with no mandate the
    chain denies and the card is decided 'denied' — the machinery working,
    not an error."""
    c, sf = client
    vid = _version(sf)
    res = c.post(
        "/api/trading/order-cards",
        json={"version_id": vid, "symbol": "BTCUSDT", "side": "long", "notional": 100.0, "chain": {"signal": "x"}},
    )
    assert res.status_code == 200
    card = res.json()["cards"][0]
    assert card["state"] == "open"
    assert len(card["fingerprint"]) == 16
    res = c.post(f"/api/trading/order-cards/{card['id']}/confirm", json={"fingerprint": card["fingerprint"]})
    assert res.status_code == 200
    assert res.json()["cards"][0]["state"] == "denied"


def test_card_confirm_with_mandate_releases(client):
    c, sf = client
    vid = _version(sf)
    with sf() as session:
        _mandate(session, vid)
        session.commit()
    res = c.post(
        "/api/trading/order-cards",
        json={"version_id": vid, "symbol": "BTCUSDT", "side": "long", "notional": 100.0},
    )
    card = res.json()["cards"][0]
    res = c.post(f"/api/trading/order-cards/{card['id']}/confirm", json={"fingerprint": card["fingerprint"], "note": "sizes checked"})
    assert res.status_code == 200
    decided = res.json()["cards"][0]
    # 'released' means the guard chain allowed it — full stop, no venue
    assert decided["state"] == "released"
    assert "sizes checked" in decided["decision_note"]
    with sf() as session:
        actions = [r.action for r in session.execute(AuditLedger.__table__.select()).all()]
        assert verify_chain(session) == []
    assert "order_card_created" in actions
    assert "order_evaluation" in actions
    assert "order_card_decided" in actions


def test_card_confirm_stale_fingerprint_is_409(client):
    c, sf = client
    vid = _version(sf)
    res = c.post("/api/trading/order-cards", json={"version_id": vid, "symbol": "BTCUSDT", "side": "long", "notional": 100.0})
    card = res.json()["cards"][0]
    res = c.post(f"/api/trading/order-cards/{card['id']}/confirm", json={"fingerprint": "0000000000000000"})
    assert res.status_code == 409
    assert "re-basing is impossible" in res.json()["detail"]
    # nothing was decided
    body = c.get("/api/trading/order-cards").json()
    assert body["cards"][0]["state"] == "open"


def test_card_confirm_twice_is_409(client):
    c, sf = client
    vid = _version(sf)
    res = c.post("/api/trading/order-cards", json={"version_id": vid, "symbol": "BTCUSDT", "side": "long", "notional": 100.0})
    card = res.json()["cards"][0]
    res = c.post(f"/api/trading/order-cards/{card['id']}/confirm", json={"fingerprint": card["fingerprint"]})
    assert res.status_code == 200
    res = c.post(f"/api/trading/order-cards/{card['id']}/confirm", json={"fingerprint": card["fingerprint"]})
    assert res.status_code == 409
    assert "decided exactly once" in res.json()["detail"]


def test_card_fingerprint_moves_with_mandate(client):
    """The fingerprint binds strategy state + mandate version: grant a
    mandate after the card is created and the stale card's confirmation is
    a 409 — review the new state."""
    c, sf = client
    vid = _version(sf)
    res = c.post("/api/trading/order-cards", json={"version_id": vid, "symbol": "BTCUSDT", "side": "long", "notional": 100.0})
    card = res.json()["cards"][0]
    c.post("/api/trading/mandates", json={"version_id": vid, **CAPS})
    res = c.post(f"/api/trading/order-cards/{card['id']}/confirm", json={"fingerprint": card["fingerprint"]})
    assert res.status_code == 409


def test_order_cards_empty_is_first_class(client):
    assert client[0].get("/api/trading/order-cards").json() == {"cards": []}


# ---- signoff endpoint -------------------------------------------------------


def test_signoff_requires_document_and_note(client):
    c, sf = client
    vid = _version(sf)
    res = c.post("/api/trading/audit-signoffs", json={"version_id": vid, "document_ref": "", "note": "x"})
    assert res.status_code == 422
    res = c.post("/api/trading/audit-signoffs", json={"version_id": vid, "document_ref": "docs/audit.md", "note": ""})
    assert res.status_code == 422
    res = c.post("/api/trading/audit-signoffs", json={"version_id": vid, "document_ref": "docs/audit.md#abc123", "note": "read in full, pilot agreed"})
    assert res.status_code == 200
    with sf() as session:
        rows = session.execute(AuditSignoff.__table__.select()).all()
    assert len(rows) == 1


# ---- audit verify endpoint --------------------------------------------------


def test_audit_verify_endpoint(client):
    c, sf = client
    assert c.get("/api/trading/audit/verify").json() == {"rows": 0, "violations": [], "intact": True}
    vid = _version(sf)
    c.post("/api/trading/mandates", json={"version_id": vid, **CAPS})
    body = c.get("/api/trading/audit/verify").json()
    assert body["rows"] == 1
    assert body["intact"] is True
