import pytest

from trading.risk import killswitch_state, set_killswitch


@pytest.fixture
def session_factory():
    from trading.models import init_schema, make_engine, make_session_factory

    engine = make_engine("sqlite://")
    init_schema(engine)
    return make_session_factory(engine)


def test_killswitch_persists_and_toggles(session_factory):
    set_killswitch(session_factory, True, note="test on")
    assert killswitch_state(session_factory)["tripped"] is True

    set_killswitch(session_factory, False)
    st = killswitch_state(session_factory)
    assert st["tripped"] is False
    assert "OFF" in st["note"]
