"""Agent framework — every agent returns an Insight, persisted for the dashboard."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import logging
from typing import Any

from sqlalchemy import select

from trading.agents.openrouter import OpenRouterClient
from trading.models import AgentInsight

log = logging.getLogger(__name__)


@dataclasses.dataclass
class Insight:
    agent: str
    title: str
    body: str
    severity: str = "info"  # info | warn | alert
    tags: list[str] = dataclasses.field(default_factory=list)
    meta: dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_row(self) -> AgentInsight:
        return AgentInsight(
            agent=self.agent,
            title=self.title[:120],
            body=self.body[:4000],
            severity=self.severity,
            tags=",".join(self.tags),
            meta=json.dumps(self.meta)[:2000],
        )


def save_insight(session_factory, insight: Insight) -> None:
    session = session_factory()
    try:
        session.add(insight.to_row())
        session.commit()
    finally:
        session.close()


def load_insights(session_factory, limit: int = 50) -> list[dict]:
    session = session_factory()
    try:
        rows = (
            session.execute(
                select(AgentInsight).order_by(AgentInsight.created_at.desc()).limit(limit)
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": r.id,
                "agent": r.agent,
                "title": r.title,
                "body": r.body,
                "severity": r.severity,
                "tags": r.tags.split(",") if r.tags else [],
                "created_at": str(r.created_at),
            }
            for r in rows
        ]
    finally:
        session.close()


class BaseAgent:
    """Subclasses implement `build_prompt()` and `fallback()` (no-key path)."""

    name: str = "base"
    system: str = ""

    def __init__(self, client: OpenRouterClient | None = None):
        self.client = client or OpenRouterClient()

    async def run(self, context: dict) -> Insight:
        parsed, insight = await self.run_parsed(context)
        if insight is not None:
            return insight
        assert parsed is not None
        return Insight(
            agent=self.name,
            title=str(parsed.get("title", "insight"))[:120],
            body=str(parsed.get("body", ""))[:4000],
            severity=str(parsed.get("severity", "info")),
            tags=[str(t) for t in parsed.get("tags", [])][:6],
            meta={"source": "llm", "model": self.client.model},
        )

    # Where this agent sits in the free-tier request budget. Agents that gate a
    # real position override this to "high"; commentary stays cheap.
    priority: str = "normal"

    async def run_parsed(self, context: dict) -> tuple[dict | None, Insight | None]:
        """Returns (parsed_llm_json, None) on success or (None, fallback_insight)."""
        prompt = self.build_prompt(context)
        raw = await self.client.chat(
            system=self.system, user=prompt, json_mode=True, priority=self.priority
        )
        if raw is None:
            return None, self.fallback(context)
        try:
            return json.loads(raw), None
        except json.JSONDecodeError:
            log.warning("%s: non-JSON LLM output, using fallback", self.name)
            return None, self.fallback(context)

    def build_prompt(self, context: dict) -> str:
        raise NotImplementedError

    def fallback(self, context: dict) -> Insight:
        raise NotImplementedError


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
