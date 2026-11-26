"""Pydantic contracts for the intelligence and alerts surfaces
(app/routers/intelligence.py) — design §8's INTELLIGENCE and ALERTS panels.

A separate module for the same reason schemas_trading.py is: this surface
reads across BOTH planes (wealth chain runs beside trading agent insights),
and neither plane's schema file is its home. The frontend's schema.d.ts is
generated from these models, so there is one source of truth and no
hand-written types downstream.

Honesty rules carried on the wire: a panel whose underlying store does not
exist (engine never ran, budget file never written) answers `available:
false` with empty lists — never fabricated rows, never an error page.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel


# ---------------------------------------------------------------- feed


class IntelligenceFeedItem(BaseModel):
    """One row of the unified stream: a wealth chain run or a trading agent
    insight, in the shape both share — when, who said it, what kind of thing
    it is, and one line of it. `ref` is the API path of the full document
    when one exists; null means the row itself is all there is."""

    ts: dt.datetime
    source: str  # wealth-chain | trading:<agent>
    kind: str  # chain-run | insight
    title: str
    summary: str
    severity: str = "info"  # info | warning | critical, as the writer declared
    ref: str | None = None


class IntelligenceFeed(BaseModel):
    """The stream, newest first. `sources` lists the sources present in the
    underlying stores BEFORE filtering, so the filter control can name real
    choices instead of guessing."""

    available: bool
    items: list[IntelligenceFeedItem]
    sources: list[str]


# ---------------------------------------------------------------- memory


class MemoryEntry(BaseModel):
    """One memory event as the learning loop wrote it. Tier and kind are the
    loop's own vocabulary (working/shallow/deep; outcome/lesson/reflection);
    importance is its 0..1 salience, pnl_pct the outcome's result when the
    event came from a trade."""

    id: int
    bot: str
    tier: str
    kind: str
    content: str
    importance: float
    pnl_pct: float | None
    created_at: dt.datetime


class IntelligenceMemory(BaseModel):
    """The memory browser's answer. `available` false means the agent memory
    table is not there to read (engine never ran, unmigrated database) — the
    panel says so instead of showing an empty browser that implies memory
    was empty."""

    available: bool
    working: list[MemoryEntry]
    shallow: list[MemoryEntry]
    deep: list[MemoryEntry]


# ---------------------------------------------------------------- budget


class BudgetTierCap(BaseModel):
    """One priority tier's effective daily cap: the RESERVE fraction of the
    day's budget above which the tier stops spending (agents/budget.py)."""

    tier: str  # high | normal | low
    cap: int


class IntelligenceBudget(BaseModel):
    """The day's request spend against the free-tier ceiling. `available`
    false means no counter file exists — no LLM call has ever been claimed
    on this machine — which is a state of the desk, not a failure.

    The counter is a single shared tally (agents/budget.py by design): the
    per-tier CAPS are policy, but there is no per-tier SPEND to report, and
    none is fabricated."""

    available: bool
    day: str | None = None
    used: int = 0
    daily_budget: int = 0
    remaining: int = 0
    rpm_budget: int = 0
    tier_caps: list[BudgetTierCap] = []


# ---------------------------------------------------------------- alerts


class AlertItem(BaseModel):
    """One alert in the unified stream, severity-typed. `kind` names what
    fired (rail-veto, validation-rejected, engine-stale, reconciliation-gap);
    `ts` is when it happened for events, when it was measured for states."""

    ts: dt.datetime
    severity: Literal["info", "warning", "critical"]
    kind: str
    source: str  # trading | wealth
    title: str
    detail: str


class AlertsStream(BaseModel):
    """The alerts stream, newest first. `available` false means nothing
    behind it could be read at all; an empty `items` with available true is
    the desk in good health, which is a first-class answer and not a missing
    page."""

    available: bool
    items: list[AlertItem]
