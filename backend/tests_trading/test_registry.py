"""M3 slice 4 — the lifecycle registry owns what the engine may trade.

The state machine's guards, each proven by what it refuses and what it
accepts: research → validated only with a passing validation row for THIS
version; validated → paper automatic; the human-gated edges refuse without
an approval row (the M4 seam, honestly empty today); candidate_live → live
refuses outright in M3 because the mandate cannot exist. And the roster:
empty registry, empty roster, empty desk — the gate working.
"""

from __future__ import annotations

import json

import pytest

from trading.bots import ScalpTrend
from trading.models import (
    BacktestValidation,
    StrategyState,
    init_schema,
    make_engine,
    make_session_factory,
)
from trading.registry import (
    TransitionRefused,
    register_version,
    roster,
    transition,
    validate_and_promote,
)

PARAMS = {"stop_atr": 2.2, "tp_rr": 2.0}


@pytest.fixture()
def session(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/reg.db")
    init_schema(engine)
    sf = make_session_factory(engine)
    with sf() as s:
        yield s
    engine.dispose()


def _write_validation(session, verdict="validated", params=None, bot="scalp"):
    row = BacktestValidation(
        bot=bot,
        symbol="BTCUSDT",
        timeframe="4h",
        strategy="ScalpTrend",
        params_json=json.dumps(params if params is not None else PARAMS),
        seed=42,
        data_source="binance",
        data_rows=2000,
        data_start="2025-01-01",
        data_end="2025-11-01",
        trades_n=42,
        verdict=verdict,
        reasons_json="[]" if verdict == "validated" else '["permutation p 0.4 >= 0.05"]',
        validation_json="{}",
    )
    session.add(row)
    session.flush()
    return row.id


def _register(session):
    return register_version(
        session,
        "scalp",
        "ScalpTrend",
        ScalpTrend,
        timeframe="4h",
        universe=["BTCUSDT"],
        params=PARAMS,
    )


def test_registration_lands_in_research(session):
    v = _register(session)
    states = [s.state for s in v.states]
    assert states == ["research"]
    assert roster(session) == [], "a research version is not the roster"
    assert v.code_hash, "the version names its code"


def test_research_to_validated_refuses_without_validation_row(session):
    v = _register(session)
    with pytest.raises(TransitionRefused, match="no evidence"):
        transition(session, v.id, "validated")
    # nothing written on a refusal — the log stays append-only-honest
    rows = session.execute(
        __import__("sqlalchemy").select(StrategyState).where(StrategyState.version_id == v.id)
    ).scalars().all()
    assert [r.state for r in rows] == ["research"]


def test_research_to_validated_refuses_rejected_verdict(session):
    v = _register(session)
    vid = _write_validation(session, verdict="rejected")
    with pytest.raises(TransitionRefused, match="rejected"):
        transition(session, v.id, "validated", validation_id=vid)


def test_research_to_validated_refuses_param_mismatch(session):
    v = _register(session)
    vid = _write_validation(session, params={"stop_atr": 9.9, "tp_rr": 2.0})
    with pytest.raises(TransitionRefused, match="params"):
        transition(session, v.id, "validated", validation_id=vid)


def test_research_to_validated_refuses_wrong_bot(session):
    v = _register(session)
    vid = _write_validation(session, bot="hft")
    with pytest.raises(TransitionRefused, match="bot"):
        transition(session, v.id, "validated", validation_id=vid)


def test_validate_and_promote_walks_to_paper_and_feeds_roster(session):
    v = _register(session)
    vid = _write_validation(session)
    states = validate_and_promote(session, v.id, vid)
    assert [s.state for s in states] == ["validated", "paper"]
    # the validated transition names its evidence
    assert states[0].evidence == f"validation:{vid}"
    entries = roster(session)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["bot"] == "scalp-v1"
    assert entry["params"] == PARAMS
    assert entry["timeframe"] == "4h"
    assert entry["universe"] == ["BTCUSDT"]


def test_backward_and_skipped_transitions_refuse(session):
    v = _register(session)
    vid = _write_validation(session)
    validate_and_promote(session, v.id, vid)
    for target in ("research", "validated", "live"):
        with pytest.raises(TransitionRefused):
            transition(session, v.id, target)


def test_paper_to_candidate_live_refuses_without_approval(session):
    v = _register(session)
    vid = _write_validation(session)
    validate_and_promote(session, v.id, vid)
    with pytest.raises(TransitionRefused, match="approval"):
        transition(session, v.id, "candidate_live")


def test_candidate_live_to_live_refuses_outright_in_m3(session):
    """Even WITH an approval row the live transition cannot happen: the
    mandate it requires is M5, and a mandatory companion that cannot exist
    makes the transition structurally impossible, not merely unapproved."""
    from trading.models import Approval

    v = _register(session)
    vid = _write_validation(session)
    validate_and_promote(session, v.id, vid)
    session.add(Approval(version_id=v.id, transition="paper->candidate_live", approved_by="operator"))
    session.flush()
    transition(session, v.id, "candidate_live")
    with pytest.raises(TransitionRefused, match="mandate"):
        transition(session, v.id, "live")


def test_empty_registry_empty_roster(session):
    """The honest M3 end state: zero validated strategies means the roster
    is empty — and empty is the answer, not an error."""
    assert roster(session) == []


def test_params_must_construct_at_registration(session):
    with pytest.raises(TransitionRefused, match="construct"):
        register_version(
            session,
            "scalp",
            "ScalpTrend",
            ScalpTrend,
            timeframe="4h",
            universe=["BTCUSDT"],
            params={"nonexistent_knob": 1.0},
        )


def test_runner_roster_specs_empty_on_fresh_registry(tmp_path):
    """The runner's own resolution path: a fresh registry resolves to zero
    specs, and build_desk returns None — the ready-and-empty end state at
    the seam the runner actually uses."""
    from trading.desk.runner import build_desk, resolve_roster_specs

    engine = make_engine(f"sqlite:///{tmp_path}/runner.db")
    init_schema(engine)
    sf = make_session_factory(engine)
    assert resolve_roster_specs(sf) == []

    import os

    os.environ["TRADING_DATABASE_URL"] = f"sqlite:///{tmp_path}/runner.db"
    try:
        from trading.config import get_settings

        get_settings.cache_clear()

        class Args:
            stale_after = None

        assert build_desk(Args(), seed_history=lambda s, t: []) is None
    finally:
        del os.environ["TRADING_DATABASE_URL"]
        from trading.config import get_settings

        get_settings.cache_clear()
        engine.dispose()


def test_runner_roster_specs_from_paper_version(tmp_path):
    """A version in paper state becomes one DeskSpec per universe symbol with
    the registered params — the only path by which anything ever trades."""
    from trading.desk.runner import resolve_roster_specs

    engine = make_engine(f"sqlite:///{tmp_path}/runner.db")
    init_schema(engine)
    sf = make_session_factory(engine)
    with sf() as session:
        v = register_version(
            session, "scalp", "ScalpTrend", ScalpTrend,
            timeframe="4h", universe=["BTCUSDT"], params=PARAMS,
        )
        vid = _write_validation(session)
        validate_and_promote(session, v.id, vid)
        session.commit()
    specs = resolve_roster_specs(sf)
    assert len(specs) == 1
    spec = specs[0]
    assert spec.bot == "scalp-v1"
    assert spec.symbol == "BTCUSDT"
    assert spec.timeframe == "4h"
    assert spec.strategy_cls is ScalpTrend
    assert spec.strategy_params == PARAMS
    engine.dispose()
