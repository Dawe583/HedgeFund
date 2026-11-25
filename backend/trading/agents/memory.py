"""Self-learning loop for the ScalpFX agent desk.

A native, dependency-free port of two MIT-licensed designs:

- **Hermes Agent** (NousResearch/hermes-agent): closed learning loop - the
  agent distills every experience into durable lessons and reuses them in
  later decisions.
- **FinMem** (pipiku915/FinMem-LLM-StockTrading, arXiv:2311.13743): layered
  memory (working -> shallow -> deep) with decay and reflection.

Loop per closed trade:
1. outcome stored as a working-tier memory event
2. ScalpFX Alpha (via OpenRouter) distills an immediate shallow lesson; a
   deterministic heuristic keeps the loop alive without an API key
3. every EXTENDED_EVERY outcomes one extended reflection consolidates
   recent lessons into a deep insight (also surfaced on the dashboard)
4. deep lessons are injected into analyst/reviewer prompts - verdicts
   improve as experience accumulates; stale events decay out

The trading engine never hard-depends on the LLM: every step has a
fallback path.
"""

from __future__ import annotations

import datetime as dt
import json
import logging

from sqlalchemy import delete, select

from trading.agents.base import Insight, save_insight
from trading.agents.openrouter import OpenRouterClient
from trading.models import AgentMemory, Trade

log = logging.getLogger(__name__)

WORKING_TTL_DAYS = 7
SHALLOW_TTL_DAYS = 30
BIG_MOVE_PCT = 0.015  # |pnl| >= 1.5% of notional is memorable by itself
HIGH_CONF = 0.70
EXTENDED_EVERY = 5  # outcomes between extended reflections (turbo: learn twice as fast)
MAX_RETRIEVE = 5


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


class LearningLoop:
    """Persists trade experience into layered memory and reflects on it."""

    name = "learner"

    def __init__(self, session_factory, client: OpenRouterClient | None = None):
        self.session_factory = session_factory
        self.client = client or OpenRouterClient()

    # ------------------------------------------------------------ recording
    async def record_outcome(self, trade: Trade) -> None:
        """Store a closed trade + distilled lesson. Never raises."""
        try:
            pnl_pct = float(trade.pnl_pct)
            importance = _clamp(0.3 + abs(pnl_pct) * 25)
            self._add("working", "outcome", self._outcome_text(trade), importance, pnl_pct)
            if abs(pnl_pct) >= BIG_MOVE_PCT or (trade.confidence >= HIGH_CONF and pnl_pct < 0):
                # significant events jump straight to the shallow layer (FinMem)
                self._add(
                    "shallow",
                    "outcome",
                    f"memorable {'WIN' if pnl_pct > 0 else 'LOSS'}: " + self._outcome_text(trade),
                    _clamp(importance + 0.2),
                    pnl_pct,
                )
            await self._immediate_lesson(trade, pnl_pct)
            self._prune()
        except Exception:
            log.exception("learning loop record failed")

    def _outcome_text(self, trade: Trade) -> str:
        return (
            f"{trade.bot} {trade.side} {trade.symbol} conf={trade.confidence:.2f} "
            f"pnl={trade.pnl_pct * 100:+.2f}%"
        )

    def _add(
        self,
        tier: str,
        kind: str,
        content: str,
        importance: float,
        pnl_pct: float | None = None,
        bot: str = "*",
    ) -> None:
        session = self.session_factory()
        try:
            session.add(
                AgentMemory(
                    bot=bot,
                    tier=tier,
                    kind=kind,
                    content=content[:1000],
                    importance=round(importance, 3),
                    pnl_pct=pnl_pct,
                )
            )
            session.commit()
        finally:
            session.close()

    # ------------------------------------------------------------- lessons
    async def _immediate_lesson(self, trade: Trade, pnl_pct: float) -> None:
        # Always-heuristic: the per-trade LLM call was the biggest budget
        # eater (1 call/trade) on the 45 req/day free tier. Extended
        # reflections keep the LLM path (low priority) for consolidation.
        lesson = self._heuristic_lesson(trade, pnl_pct)
        self._add("shallow", "lesson", lesson, _clamp(0.4 + abs(pnl_pct) * 20), pnl_pct)

    @staticmethod
    def _heuristic_lesson(trade: Trade, pnl_pct: float) -> str:
        won = pnl_pct > 0
        pct = f"{pnl_pct * 100:+.2f}%"
        if won and trade.confidence >= HIGH_CONF:
            return (
                f"[heuristic] high-confidence {trade.side} on {trade.bot} paid off ({pct}); "
                "current veto thresholds look calibrated."
            )
        if won:
            return (
                f"[heuristic] modest win ({pct}) on low confidence - consider sizing up "
                "only after repeated confirmation."
            )
        if trade.confidence >= HIGH_CONF:
            return (
                f"[heuristic] high-confidence {trade.side} LOST ({pct}) - tighten veto "
                f"for {trade.bot} when volatility is elevated."
            )
        return (
            f"[heuristic] low-confidence loss ({pct}); gate was right to allow small size "
            "- keep threshold."
        )

    # ---------------------------------------------------------- reflection
    async def maybe_extended_reflect(self) -> Insight | None:
        """Every EXTENDED_EVERY outcomes consolidate lessons into deep memory.

        Returns the reflection Insight (already persisted), or None.
        """
        try:
            n_since, wins, losses = self._outcomes_since_last_reflection()
            if n_since < EXTENDED_EVERY:
                return None
            lessons = self.context_block(k=EXTENDED_EVERY)
            if not lessons:
                return None
            return await self._extended_reflection(lessons, n_since, wins, losses)
        except Exception:
            log.exception("extended reflection failed")
            return None

    def _outcomes_since_last_reflection(self) -> tuple[int, int, int]:
        """(#working events since last deep row, #wins, #losses) in that window."""
        session = self.session_factory()
        try:
            last_deep = session.execute(
                select(AgentMemory.created_at)
                .where(AgentMemory.tier == "deep")
                .order_by(AgentMemory.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            q = select(AgentMemory.pnl_pct).where(AgentMemory.tier == "working")
            if last_deep is not None:
                q = q.where(AgentMemory.created_at > last_deep)
            pnls = [r[0] for r in session.execute(q).all() if r[0] is not None]
            wins = sum(1 for p in pnls if p > 0)
            return len(pnls), wins, len(pnls) - wins
        finally:
            session.close()

    async def _extended_reflection(
        self, lessons: str, n: int, wins: int, losses: int
    ) -> Insight | None:
        system = (
            "You are ScalpFX Alpha performing an extended reflection for the ScalpFX desk "
            "(FinMem-style consolidation). Review recent trade outcomes and lessons. "
            "Produce durable guidance: what market behaviour rewards which setups, "
            "which patterns to veto, calibration notes. Terse, quantitative. "
            'Reply ONLY as JSON: {"title": str (<=8 words), '
            '"body": str (<=90 words), "severity": "info"|"warn"|"alert"}'
        )
        raw = await self.client.chat(
            system=system,
            user=(
                f"Recent window: {n} outcomes ({wins}W/{losses}L).\n\n{lessons}\n\n"
                "Produce the consolidation JSON."
            ),
            priority="low",
            max_tokens=200,
            temperature=0.3,
        )
        title, body, severity = None, None, "info"
        if raw:
            try:
                data = json.loads(raw)
                title = str(data.get("title", "")).strip() or None
                body = str(data.get("body", "")).strip() or None
                severity = str(data.get("severity", "info"))
            except json.JSONDecodeError:
                pass
        if not body:
            body = self._heuristic_reflection(wins, losses)
            title = title or "Consolidated trade lessons"

        insight = Insight(
            agent=self.name,
            title=title or "Extended reflection",
            body=body[:4000],
            severity=severity if severity in {"info", "warn", "alert"} else "info",
            tags=["learning", "reflection"],
            meta={"source": "llm" if raw else "fallback", "model": self.client.model},
        )
        self._add("deep", "reflection", f"{insight.title}: {insight.body}", 0.95)
        save_insight(self.session_factory, insight)
        log.info("learner: extended reflection stored (%s)", insight.title)
        return insight

    @staticmethod
    def _heuristic_reflection(wins: int, losses: int) -> str:
        return (
            "[heuristic] Consolidation of recent outcomes: repeat the winning lesson "
            "class, veto the losing pattern class. Recent balance "
            f"{wins}W/{losses}L. Keep sizing within risk rails while the sample "
            "stays small."
        )

    # ----------------------------------------------------------- retrieval
    def context_block(self, bot: str | None = None, k: int = MAX_RETRIEVE) -> str:
        """Ranked memory lines for prompt injection: deep first, then recency."""
        session = self.session_factory()
        try:
            q = select(AgentMemory).order_by(
                # tier rank: deep=0, shallow=1, working=2; then importance, then age
                (AgentMemory.tier != "deep"),
                (AgentMemory.tier != "shallow"),
                AgentMemory.importance.desc(),
                AgentMemory.created_at.desc(),
            )
            if bot:
                q = q.where((AgentMemory.bot == bot) | (AgentMemory.bot == "*"))
            rows = session.execute(q.limit(k)).scalars().all()
        finally:
            session.close()
        lines = [f"- [{r.tier}/{r.kind}] {r.content}" for r in rows] if rows else []
        # prime-agent layer: hourly reviews distill cross-session lessons into
        # docs/LESSONS.md — every trading agent reads the tail of that file,
        # so the whole desk keeps learning even across restarts/retrains.
        try:
            from pathlib import Path as _P
            lp = _P(__file__).resolve().parents[3] / "docs" / "LESSONS.md"
            if lp.exists():
                from trading.agents.curator import dedup_lessons, rank_lessons
                raw = lp.read_text(encoding="utf-8").strip().splitlines()
                raw = [l.strip() for l in raw if l.strip() and not l.strip().startswith("#")]
                tail = rank_lessons(dedup_lessons(raw), max_n=12)
                if tail:
                    lines.append("[prime-agent lessons]")
                    lines.extend(f"- {l[:300]}" for l in tail)
        except Exception:
            pass
        return "\n".join(lines)

    # --------------------------------------------------------------- decay
    def _prune(self) -> None:
        """Decay: drop stale working/shallow events; deep lessons persist."""
        cutoff_work = _now() - dt.timedelta(days=WORKING_TTL_DAYS)
        cutoff_shal = _now() - dt.timedelta(days=SHALLOW_TTL_DAYS)
        session = self.session_factory()
        try:
            session.execute(
                delete(AgentMemory).where(
                    AgentMemory.tier == "working", AgentMemory.created_at < cutoff_work
                )
            )
            session.execute(
                delete(AgentMemory).where(
                    AgentMemory.tier == "shallow",
                    AgentMemory.created_at < cutoff_shal,
                    AgentMemory.importance < 0.9,
                )
            )
            session.commit()
        finally:
            session.close()

    async def run(self, context: dict) -> Insight:  # pragma: no cover - API compat shim
        raise NotImplementedError("LearningLoop is driven by record_outcome/reflection")
