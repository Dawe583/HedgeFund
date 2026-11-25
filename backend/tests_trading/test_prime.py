"""Tests for the Prime migration (backend slice).

Covers: PrimeOrchestrator local veto/pass paths, maybe_analyst throttling,
TF_CONFIG + retrain_all_timeframes skip guards, gate_source schema, vetoes
in the bots snapshot, heuristic-only immediate lessons, prime agent status.
All hermetic (offline OpenRouter client, in-memory SQLite).
"""

import pytest

from trading.agents.memory import LearningLoop
from trading.agents.openrouter import OpenRouterClient
from trading.agents.prime import PrimeOrchestrator
from trading.backtest.engine import Signal
from trading.ml.pipeline import TF_CONFIG, retrain_all_timeframes
from trading.models import make_engine, make_session_factory


def _offline_client() -> OpenRouterClient:
    c = OpenRouterClient(api_key=None)
    c.api_key = None
    return c


@pytest.fixture
def session_factory():
    return make_session_factory(make_engine("sqlite://"))


@pytest.fixture
def prime(session_factory, monkeypatch):
    """Prime with hermetic agents (offline client even if .env has a key)."""
    from trading.agents import build_agents as _orig

    offline = _offline_client()
    monkeypatch.setattr(
        "trading.agents.build_agents",
        lambda bot_stats=None: _orig(client=offline, bot_stats=bot_stats),
    )
    return PrimeOrchestrator(
        session_factory,
        client=offline,
        bot_stats={"scalp": {"wr": 0.55, "avg_pnl_pct": 0.001, "n": 50}},
    )


def _feats(**kw):
    row = {
        "vol_z": 1.5,
        "atr_pct": 1.0,
        "trend_strength": 2.0,
        "rsi": 55.0,
        "rvol": 1.0,
        "tf": "4h",
    }
    row.update(kw)
    return row


# ------------------------------------------------------------ decide_signal
@pytest.mark.asyncio
async def test_prime_local_veto_no_llm(prime):
    sig = Signal(side="long", confidence=0.7, tp_rr=2.0)
    d = await prime.decide_signal("scalp", sig, _feats(vol_z=0.1), {"price": 77_000.0})
    assert d.approved is False
    assert d.llm_used is False
    assert d.veto_reason
    assert d.insight is not None
    assert d.insight.meta.get("source") == "prime_local"
    assert prime._agents is None  # veto path builds no agents


@pytest.mark.asyncio
async def test_prime_local_pass_offline_quant_approves(prime):
    sig = Signal(side="long", confidence=0.7, tp_rr=2.0)
    d = await prime.decide_signal("scalp", sig, _feats(), {"price": 77_000.0})
    assert d.approved is True
    assert d.size_mult > 0
    adj = d.adjusted_signal(sig)
    assert adj.side == sig.side
    assert adj.confidence == pytest.approx(d.confidence)


# ------------------------------------------------------------ maybe_analyst
@pytest.mark.asyncio
async def test_prime_maybe_analyst_throttles_on_regime(prime):
    first = await prime.maybe_analyst({"regime": 0.5})
    assert first is not None  # first call always runs
    assert await prime.maybe_analyst({"regime": 0.5}) is None  # same regime: throttled
    assert await prime.maybe_analyst({"regime": 2.0}) is not None  # regime jump: runs


# ------------------------------------------------------------ pipeline TF config
def test_tf_config_shapes():
    assert set(TF_CONFIG) == {"1m", "1h", "4h"}
    assert TF_CONFIG["1m"] == {"horizon": 3, "folds": 4, "min_bars": 5000, "threshold": 0.58}
    assert TF_CONFIG["1h"]["min_bars"] == 1200
    assert TF_CONFIG["4h"] == {"horizon": 6, "folds": 4, "min_bars": 800, "threshold": 0.55}


@pytest.mark.asyncio
async def test_retrain_all_timeframes_skips_without_data(session_factory):
    out = await retrain_all_timeframes(session_factory, None)
    assert set(out) == {"1m", "1h", "4h"}
    assert all("skipped" in v for v in out.values())


# ------------------------------------------------------------ gate_source schema
def test_gate_source_columns_and_default(tmp_path):
    from sqlalchemy import inspect

    engine = make_engine(f"sqlite:///{tmp_path}/g.db")
    cols_t = {c["name"] for c in inspect(engine).get_columns("trades")}
    cols_p = {c["name"] for c in inspect(engine).get_columns("open_positions")}
    assert "gate_source" in cols_t and "gate_source" in cols_p

    import datetime as dt

    from trading.models import OpenPosition, Trade

    sf = make_session_factory(engine)
    with sf() as s:
        s.add(
            Trade(
                bot="scalp",
                symbol="BTCUSDT",
                side="long",
                qty=0.01,
                entry_price=77_000.0,
                exit_price=77_100.0,
                entry_time=dt.datetime.now(dt.UTC),
                exit_time=dt.datetime.now(dt.UTC),
                pnl=1.0,
                fees=0.1,
                confidence=0.7,
            )
        )
        s.add(
            OpenPosition(
                bot="scalp",
                symbol="BTCUSDT",
                side="long",
                qty=0.01,
                entry_price=77_000.0,
                stop_loss=76_000.0,
                take_profit=79_000.0,
                confidence=0.7,
                gate_source="prime_local",
            )
        )
        s.commit()
    with sf() as s:
        from sqlalchemy import select

        t = s.execute(select(Trade)).scalars().one()
        assert t.gate_source == "legacy"
        p = s.execute(select(OpenPosition)).scalars().one()
        assert p.gate_source == "prime_local"
    # idempotent second boot
    engine2 = make_engine(f"sqlite:///{tmp_path}/g.db")
    assert "gate_source" in {c["name"] for c in inspect(engine2).get_columns("trades")}
    engine.dispose()
    engine2.dispose()


# ------------------------------------------------------------ bots snapshot vetoes
def test_bots_snapshot_vetoes(session_factory, monkeypatch):
    import trading.api.app as app_mod
    from trading.models import BotStatus, set_state

    monkeypatch.setattr(app_mod, "session_factory", session_factory)
    with session_factory() as s:
        s.add(BotStatus(name="scalp", running=True, mode="active", note="t"))
        s.commit()
        set_state(s, "veto:scalp:prime", 3)
        set_state(s, "veto:scalp:ml_gate", 1)
    rows = app_mod._bots_snapshot()
    scalp = next(r for r in rows if r["name"] == "scalp")
    assert scalp["vetoes"] == {"quant": 0, "reviewer": 0, "ml_gate": 1, "prime": 3, "cooldown": 0}


# ------------------------------------------------------------ memory: 0 LLM calls
@pytest.mark.asyncio
async def test_immediate_lesson_makes_zero_llm_calls(session_factory):
    import datetime as dt

    from trading.models import AgentMemory, Trade

    client = _offline_client()
    calls: list = []
    orig_chat = client.chat

    async def _counting(*a, **k):
        calls.append(1)
        return await orig_chat(*a, **k)

    client.chat = _counting  # type: ignore[method-assign]
    loop = LearningLoop(session_factory, client)
    trade = Trade(
        bot="scalp",
        symbol="BTCUSDT",
        side="long",
        qty=0.01,
        entry_price=77_000.0,
        exit_price=77_100.0,
        entry_time=dt.datetime.now(dt.UTC),
        exit_time=dt.datetime.now(dt.UTC),
        pnl=30.0,
        fees=1.0,
        confidence=0.65,
        mode="paper",
    )
    await loop.record_outcome(trade)
    assert calls == []
    with session_factory() as s:
        from sqlalchemy import select

        lessons = (
            s.execute(
                select(AgentMemory).where(
                    AgentMemory.tier == "shallow", AgentMemory.kind == "lesson"
                )
            )
            .scalars()
            .all()
        )
    assert len(lessons) == 1
    assert lessons[0].content.startswith("[heuristic]")


# ------------------------------------------------------------ agent status lists prime
def test_agent_status_includes_prime():
    from trading.agents import agent_status

    snap = agent_status(client=_offline_client())
    names = {a["name"]: a for a in snap["agents"]}
    assert "prime" in names
    assert "quant+reviewer" in names["prime"]["role"]
