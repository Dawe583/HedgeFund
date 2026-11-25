"""Pydantic contracts for the trading API (app/routers/trading.py).

A separate module from schemas.py on purpose: schemas.py is the wealth
plane's contract monolith (~150 classes), and the trading plane has its own
lifecycle, its own database tables and its own consumers. Merging them would
couple two planes that the architecture keeps apart; the wire contract is
what they share, and that contract lives here, once — the frontend's
schema.d.ts is generated from these models, so there is exactly one source
of truth and no hand-written types anywhere downstream.

Wire notes: datetimes are ISO strings (pydantic serializes datetime to
isoformat, identical to what the pre-model payloads carried); nullable
branches are explicit null, never omitted keys; the verdict is lowercase
"validated" | "rejected" | "insufficient_data".
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel


class TradingStatus(BaseModel):
    engine_state: Literal["offline", "running"]
    last_tick_at: dt.datetime | None
    db_ok: bool
    strategies_registered: int
    validations_total: int


class TradingStrategy(BaseModel):
    key: str
    name: str
    timeframe: str
    symbols: list[str]
    description: str
    registered: bool


class TradingRunMetrics(BaseModel):
    win_rate: float
    profit_factor: float
    sharpe: float
    max_dd_pct: float
    total_return_pct: float


class TradingValidationSummary(BaseModel):
    permutation_p: float | None
    sharpe_ci_lo: float | None
    sharpe_ci_hi: float | None
    wf_positive_folds: int
    wf_total_folds: int


class TradingRunItem(BaseModel):
    id: int
    bot: str
    symbol: str
    timeframe: str
    started_at: dt.datetime | None
    trades_count: int
    metrics: TradingRunMetrics
    verdict: str | None
    validation: TradingValidationSummary | None
    created_at: dt.datetime | None


class TradingProvenance(BaseModel):
    seed: int
    data_source: str
    data_rows: int
    data_start: str
    data_end: str


class TradingEquityPoint(BaseModel):
    t: str
    equity: float


class TradingTradeEvidence(BaseModel):
    entry_time: str
    exit_time: str
    side: str
    qty: float
    entry_price: float
    exit_price: float
    pnl: float


class TradingRunDetail(TradingRunItem):
    params: dict[str, Any]
    provenance: TradingProvenance | None
    reasons: list[str]
    prob_positive: float | None
    sharpe_actual: float | None
    min_trades_required: int | None
    equity_curve: list[TradingEquityPoint] | None
    trades: list[TradingTradeEvidence] | None
