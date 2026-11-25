"""Agent registry — one place to construct and describe all agents."""

from __future__ import annotations

from dataclasses import dataclass

from trading.agents.analyst import MarketAnalyst
from trading.agents.openrouter import OpenRouterClient
from trading.agents.quant import QuantAnalyst
from trading.agents.reviewer import SignalReviewer
from trading.agents.supervisor import TrainingSupervisor


@dataclass
class AgentInfo:
    name: str
    role: str
    enabled: bool


def build_agents(client: OpenRouterClient | None = None, bot_stats: dict | None = None) -> dict:
    c = client or OpenRouterClient()
    return {
        "analyst": MarketAnalyst(c),
        "reviewer": SignalReviewer(c),
        "supervisor": TrainingSupervisor(c),
        "quant": QuantAnalyst(c, bot_stats=bot_stats),
    }


def agent_status(client: OpenRouterClient | None = None) -> dict:
    c = client or OpenRouterClient()
    s = c.available
    return {
        "llm_available": s,
        "model": c.model,
        "fallback_models": c.models[1:],
        "provider": "openrouter",
        "free_tier": True,
        "budget": c.budget.snapshot(),
        "agents": [
            {"name": a.name, "role": a.role, "enabled": a.enabled}
            for a in (
                AgentInfo("analyst", "market regime commentary", s),
                AgentInfo("reviewer", "pre-entry signal veto", s),
                AgentInfo("quant", "mathematical EV validator + sizing", s),
                AgentInfo("supervisor", "retraining oversight", s),
                AgentInfo("learner", "self-learning memory loop", s),
                AgentInfo("prime", "single LLM entry-point: merged quant+reviewer gate", s),
            )
        ],
    }
