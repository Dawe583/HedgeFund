"""OpenRouter LLM client — powers all ScalpFX agents.

Runs exclusively on OpenRouter's free tier (`:free` model slugs, $0/token).
The desk asks for short structured verdicts, not long-form generation, so a
free model is sufficient; paid models are never required to run ScalpFX.

`agent_model` is the primary; `agent_model_fallbacks` is handed to OpenRouter
as a routing chain, so a free model that is rate-limited or briefly down rolls
over to the next free model instead of dropping the call.

Key: OPENROUTER_API_KEY / TRADING_OPENROUTER_API_KEY. Without a key — or once
the free daily quota is spent — every agent degrades gracefully to heuristic
fallbacks; the trading system never hard-depends on the LLM.
"""

from __future__ import annotations

import contextlib
import logging
import re
from pathlib import Path
from typing import Any

import httpx

from trading.agents.budget import RequestBudget
from trading.config import get_settings

log = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterClient:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        s = get_settings()
        self.api_key = api_key or s.openrouter_api_key
        self.model = model or s.agent_model
        # Routing chain: primary first, then each configured free fallback.
        self.models = [self.model] + [
            m.strip()
            for m in s.agent_model_fallbacks.split(",")
            if m.strip() and m.strip() != self.model
        ]
        self.timeout = s.agent_timeout_s
        self.budget = RequestBudget(
            budget_path(s.database_url, s.data_dir), s.agent_daily_budget, s.agent_rpm_budget
        )

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    async def chat(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
        max_tokens: int = 600,
        temperature: float = 0.3,
        priority: str = "normal",
    ) -> str | None:
        """Single completion; returns None when unavailable/failed (never raises).

        None is the caller's cue to use its deterministic fallback — it covers
        "no key", "out of free budget" and "the call failed" alike, so no
        caller has to know which.
        """
        if not self.available:
            return None
        if not self.budget.take(priority):
            return None
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            # Both free models the desk routes to have reasoning ON by default
            # (nemotron-3-super at "medium", glm-5.2 at "high"), and reasoning
            # tokens are billed against max_tokens. At the 120-600 the agents
            # ask for, the whole allowance goes on thinking and `content` comes
            # back empty. Every configured model has reasoning.mandatory=false,
            # so turn it off and spend the allowance on the answer.
            "reasoning": {"enabled": False},
        }
        if len(self.models) > 1:
            payload["models"] = self.models
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            # OpenRouter attribution headers
            "HTTP-Referer": "https://trading.local",
            "X-Title": "ScalpFX",
        }
        for attempt in range(2):
            # The retry is a second real request against the account quota, so
            # it claims its own slot rather than riding the first one.
            if attempt and not self.budget.take(priority):
                break
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(OPENROUTER_URL, json=payload, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    content = data["choices"][0]["message"].get("content")
                    served = data.get("model") or self.model
                    if not content:
                        # A length cut is deterministic — the identical payload
                        # returns identical empty content, so retrying only
                        # spends a second free-tier slot for the same nothing.
                        log.warning("empty LLM content from %s — using the fallback", served)
                        return None
                    log.debug("llm ok (%s, %d chars)", served, len(content))
                    return content
            except Exception as exc:  # noqa: BLE001 — LLM must never kill the engine
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
                    # OpenRouter answers 429 for three different things: the
                    # daily account cap, the 20/min account cap, and upstream
                    # throttling of a shared `:free` endpoint. Only the first
                    # justifies giving up on the day — the other two clear in
                    # under a minute, and standing down for 23 hours over one
                    # of them is how the desk ends up silently on heuristics.
                    body = ""
                    with contextlib.suppress(Exception):
                        body = exc.response.text[:500].lower()
                    if "per-day" in body or "per day" in body or "daily" in body:
                        self.budget.exhaust_day()
                    else:
                        self.budget.exhaust_minute()
                    log.warning("openrouter rate-limited: %s", exc)
                    return None
                if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
                    # Never reached OpenRouter, so the account quota never saw
                    # it. On a home line that drops out this is the difference
                    # between a counter that tracks reality and one that drifts
                    # up all day and sheds the agents early.
                    self.budget.refund()
                log.warning("openrouter attempt %d failed: %s", attempt + 1, exc)
        return None


def budget_path(database_url: str | None = None, data_dir: str | None = None) -> Path:
    """Park the counter beside the database so every process shares one budget.

    sqlite URL → DB's parent dir; anything else (postgres etc.) → TRADING_DATA_DIR.
    """
    from trading.config import get_settings

    s = get_settings()
    url = database_url or s.database_url
    m = re.match(r"sqlite:///(.+)", url or "")
    if m and m.group(1):
        return Path(m.group(1)).parent / "llm_budget.json"
    return Path(data_dir or s.data_dir) / "llm_budget.json"
