"""Tests for the Hermes-style self-learning loop (agents/memory.py)."""

import datetime as dt

import pytest

from trading.agents.memory import (
    BIG_MOVE_PCT,
    EXTENDED_EVERY,
    SHALLOW_TTL_DAYS,
    WORKING_TTL_DAYS,
    LearningLoop,
)
from trading.agents.openrouter import OpenRouterClient
from trading.agents.reviewer import SignalReviewer
from trading.backtest.engine import Signal
from trading.models import AgentMemory, Trade, make_engine, make_session_factory

NOTIONAL = 0.01 * 77_000.0  # qty * entry_price used in _trade below


def _offline_client() -> OpenRouterClient:
    """Force-offline client: .env may carry a real key, tests must stay hermetic."""
    c = OpenRouterClient(api_key=None)
    c.api_key = None
    return c


@pytest.fixture
def session_factory():
    return make_session_factory(make_engine("sqlite://"))


@pytest.fixture
def loop(session_factory):
    return LearningLoop(session_factory, _offline_client())


def _trade(bot="scalp", side="long", conf=0.65, pnl_pct=0.004):
    return Trade(
        bot=bot,
        symbol="BTCUSDT",
        side=side,
        qty=0.01,
        entry_price=77_000.0,
        exit_price=77_000.0,
        entry_time=dt.datetime.now(dt.UTC),
        exit_time=dt.datetime.now(dt.UTC),
        pnl=pnl_pct * NOTIONAL,
        fees=1.0,
        confidence=conf,
        mode="paper",
    )


def _rows(session_factory, **kw):
    s = session_factory()
    try:
        return list(s.query(AgentMemory).filter_by(**kw).all())
    finally:
        s.close()


@pytest.mark.asyncio
async def test_record_outcome_stores_working_and_lesson(loop):
    await loop.record_outcome(_trade())
    working = _rows(loop.session_factory, tier="working", kind="outcome")
    lessons = _rows(loop.session_factory, tier="shallow", kind="lesson")
    assert len(working) == 1
    assert "+0.40%" in working[0].content
    assert len(lessons) == 1
    assert lessons[0].content.startswith("[heuristic]")


@pytest.mark.asyncio
async def test_big_loss_with_high_confidence_is_memorable(loop):
    await loop.record_outcome(_trade(conf=0.85, pnl_pct=-BIG_MOVE_PCT))
    memorable = [r for r in _rows(loop.session_factory, tier="shallow") if "LOSS" in r.content]
    assert len(memorable) == 1


@pytest.mark.asyncio
async def test_small_lowconf_loss_not_promoted(loop):
    await loop.record_outcome(_trade(conf=0.55, pnl_pct=-0.002))
    assert not [r for r in _rows(loop.session_factory, tier="shallow") if r.kind == "outcome"]


def test_context_block_ranks_deep_first(loop):
    loop._add("working", "outcome", "recent outcome", 0.3)
    loop._add("shallow", "lesson", "mid lesson", 0.6)
    loop._add("deep", "reflection", "durable lesson", 0.95)
    block = loop.context_block()
    lines = block.splitlines()
    db_lines = [l for l in lines if l.startswith("- [")]
    assert db_lines[0].startswith("- [deep/")
    assert db_lines[-1].startswith("- [working/")
    assert "durable lesson" in db_lines[0]
    # prime-agent layer is appended AFTER the ranked DB memories
    if "[prime-agent lessons]" in block:
        assert block.index("[prime-agent lessons]") > block.index("- [working/")


@pytest.mark.asyncio
async def test_no_reflection_below_threshold(loop):
    for i in range(EXTENDED_EVERY - 1):
        await loop.record_outcome(_trade(pnl_pct=0.001 if i % 2 else -0.001))
    assert await loop.maybe_extended_reflect() is None
    assert _rows(loop.session_factory, tier="deep") == []


@pytest.mark.asyncio
async def test_extended_reflection_consolidates_and_persists(loop):
    for i in range(EXTENDED_EVERY):
        await loop.record_outcome(_trade(pnl_pct=0.01 if i % 2 else -0.005))
    insight = await loop.maybe_extended_reflect()
    assert insight is not None
    assert insight.agent == "learner"
    deep = _rows(loop.session_factory, tier="deep", kind="reflection")
    assert len(deep) == 1
    assert "1W/0L" not in insight.body or "[heuristic]" in insight.body

    # counter resets: immediate second call must not duplicate the reflection
    assert await loop.maybe_extended_reflect() is None
    assert len(_rows(loop.session_factory, tier="deep")) == 1


def test_prune_decays_working_but_keeps_deep(session_factory, loop):
    old = dt.datetime.now(dt.UTC) - dt.timedelta(days=WORKING_TTL_DAYS + 2)
    old_shal = dt.datetime.now(dt.UTC) - dt.timedelta(days=SHALLOW_TTL_DAYS + 5)
    loop._add("deep", "reflection", "keep me forever", 0.95)
    loop._add("shallow", "lesson", "old weak lesson", 0.5)
    loop._add("working", "outcome", "stale outcome", 0.3)
    s = session_factory()
    try:
        for r in s.query(AgentMemory).all():
            if r.tier == "working":
                r.created_at = old
            elif r.tier == "shallow":
                r.created_at = old_shal
        s.commit()
    finally:
        s.close()
    loop._prune()
    tiers = {r.tier for r in _rows(session_factory)}
    assert tiers == {"deep"}


@pytest.mark.asyncio
async def test_reviewer_prompt_includes_lessons():
    sf = make_session_factory(make_engine("sqlite://"))
    loop = LearningLoop(sf, _offline_client())
    await loop.record_outcome(_trade())
    reviewer = SignalReviewer(_offline_client())
    ctx = {
        "bot": "scalp",
        "signal": Signal(side="long", confidence=0.7),
        "symbol": "BTCUSDT",
        "price": 77_000,
        "trend_strength": 1.5,
        "rsi": 55,
        "atr_pct": 1.2,
        "news_blackout": False,
        "lessons": loop.context_block(bot="scalp"),
    }
    prompt = reviewer.build_prompt(ctx)
    assert "Lessons from your own memory" in prompt
    assert "[heuristic]" in prompt or "- [" in prompt
