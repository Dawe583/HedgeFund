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


class TradingRailExposure(BaseModel):
    instrument_notional: float
    gross_notional: float
    symbol_cap: float
    gross_cap: float


class TradingRailDivergence(BaseModel):
    """The divergence budget as the version declared it, plus the feed
    counters the live process measures against it. None on the wire means
    the snapshot predates slice 5 — never zeros, because zero is a claim."""

    budget_dev_ticks: float
    budget_entry_lag_bars: int
    budget_missed_bars: int
    missed_bars: int
    backfilled_bars: int


class TradingBotRails(BaseModel):
    """One bot's rail state as the desk's snapshot last wrote it — every
    number the rails themselves computed, plus the exposure book's slice.
    `asof` is the snapshot's write time: the UI says when this was true,
    because a rail state without a clock is a rumor."""

    bot: str
    asof: str | None
    equity: float
    peak_equity: float
    drawdown_pct: float
    killswitch_dd_pct: float
    kill_tripped: bool
    daily_loss: float
    daily_loss_limit: float
    daily_loss_consumed: float
    daily_breached: bool
    loss_streak: int
    max_losses: int
    cooldown_remaining_s: float
    vetoes_total: int
    exposure: TradingRailExposure | None
    divergence: "TradingRailDivergence | None" = None




class TradingRiskEvent(BaseModel):
    id: int
    created_at: dt.datetime | None
    bot: str
    symbol: str
    rail: str
    decision: str
    inputs: dict[str, Any]


class TradingRailsStatus(BaseModel):
    """The desk's rail state at a glance. `bots` empty is the honest answer
    for an engine that never ran — and for the M3 end state of a registry
    with zero validated strategies: rails exist, nothing trades beneath
    them, and the strip says so."""

    manual_killswitch: bool
    manual_killswitch_note: str
    halt_sentinel: bool
    halt_sentinel_path: str
    bots: list[TradingBotRails]
    recent_events: list[TradingRiskEvent]
    # today's refused entries (UTC day, server clock) — the slice-5 veto tape:
    # every entry the caps or the rails said no to, with the inputs the
    # refusal stood on. Empty is the honest answer — a day with no vetoes
    # is a day the rails were never tested, which is information too.
    vetoes_today: list[TradingRiskEvent]


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
    engine_version: str | None


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
    equity_fan: "TradingEquityFan | None" = None


class TradingPosition(BaseModel):
    """One open position, exactly what the OpenPosition row carries.

    age_seconds is server-computed at read time so the UI never re-derives
    age from clock-synchronized arithmetic — one measurement, one clock.
    signal_time is nullable because rows from before the kernel migration
    never carried it (the model's own comment); null is the honest answer.
    There is no rearmed state on the wire: rearm is kernel memory, never
    persisted — a position a restart re-armed IS the same position.
    """

    id: int
    bot: str
    symbol: str
    side: str
    qty: float
    entry_price: float
    stop_loss: float
    take_profit: float
    opened_at: dt.datetime
    age_seconds: float
    confidence: float
    signal_time: dt.datetime | None
    gate_source: str
    # slice-5 per-fill divergence evidence: deviation in ticks from the
    # role-implied reference (the filling bar's close for the market entry),
    # and timing lag against the signal(k-1)→close(k) contract. Null means
    # unmeasured — the row predates slice 5, or the reference bar was
    # honestly unknowable
    entry_dev_ticks: float | None
    entry_ref_price: float | None
    entry_lag_bars: int | None


class TradingClosedTrade(BaseModel):
    """One settled round-trip the desk wrote — the recent evidence strip."""

    id: int
    bot: str
    symbol: str
    side: str
    qty: float
    entry_price: float
    exit_price: float
    entry_time: dt.datetime
    exit_time: dt.datetime
    pnl: float
    fees: float
    confidence: float
    mode: str
    gate_source: str
    entry_dev_ticks: float | None
    exit_dev_ticks: float | None
    entry_lag_bars: int | None
    # the provenance drill-down anchor: the signal bar's own timestamp, null
    # on rows written before the recording seam. `signal_chain` is the joined
    # emission's outcome and sizing chain — empty dict when the chain is
    # honestly unwalkable (pre-seam rows, or a restarted desk whose memory
    # of the emission died with the process that recorded it).
    signal_time: dt.datetime | None = None
    signal_chain: dict[str, Any] = {}


class TradingDivergenceFillStats(BaseModel):
    """Per-fill drift evidence aggregated over the bot's closed trades —
    the mechanical divergence measurement, meaningful at n=1 because each
    fill is one kernel fact compared against its own bar."""

    measured_fills: int
    mean_abs_dev_ticks: float | None
    max_abs_dev_ticks: float | None
    max_entry_lag_bars: int | None
    breaches: int


class TradingDivergenceDistribution(BaseModel):
    """Paper-vs-backtest per-trade pnl positioning — present ONLY when both
    sides have ≥30 trades (the same statistical bar the validation gate
    sets). Descriptive, never inferential: no p-values over small
    autocorrelated samples."""

    bt_trades: int
    paper_trades: int
    bt_mean_pnl: float
    paper_mean_pnl: float
    bt_median_pnl: float
    paper_mean_within_bt_p5_p95: bool
    bt_p5: float
    bt_p95: float


class TradingBotDivergence(BaseModel):
    """One bot's divergence picture: the declared budget, the live feed
    counters, the aggregated per-fill evidence, and the distributional
    comparison when — and only when — the data volume makes it meaningful."""

    bot: str
    budget_dev_ticks: float | None
    budget_entry_lag_bars: int | None
    budget_missed_bars: int | None
    missed_bars: int | None
    backfilled_bars: int | None
    open_positions: list[TradingPosition]
    fills: TradingDivergenceFillStats
    distribution: TradingDivergenceDistribution | None
    distribution_note: str


class TradingDivergenceStatus(BaseModel):
    """/api/trading/divergence — the slice-5 surface. Bots come from two
    sources unioned: the rail snapshots (live processes) and the trade
    rows (evidence). Empty bots is the honest first-class answer."""

    bots: list[TradingBotDivergence]
    breach_events: list[TradingRiskEvent]


# --------------------------------------------------------------------------
# M4 control surfaces — the FIRST write endpoints of the trading router.
# The read endpoints above describe the engine; the models below describe
# the operator's hands on it. A control model that cannot audit itself is
# not a control.


class KillSwitchRequest(BaseModel):
    """POST /api/trading/kill-switch body. `enabled` is the direction of the
    throw: true halts entries desk-wide immediately (protective exits keep
    flowing — the switch refuses entries, never safety), false re-arms.
    `note` is optional going ON — speed beats paperwork in that direction —
    and MANDATORY coming OFF: re-arming a halted desk is the dangerous
    direction, and the audit row deserves the operator's own sentence for
    why, enforced server-side as a 422, never by browser chrome alone."""

    enabled: bool
    note: str = ""


class KillSwitchState(BaseModel):
    """The switch as persisted — the same truth GET /rails reads live."""

    tripped: bool
    note: str


class TradingApprovalResult(BaseModel):
    """What one POST …/approve produced: the approval row the human's assent
    became, the new state row when the registry's guards let it through,
    and the fingerprint the confirmation stood on."""

    approval_id: int
    state: str
    evidence: str
    fingerprint: str


class ApproveRequest(BaseModel):
    """POST /api/trading/registry/<id>/approve body. `fingerprint` is the
    exact digest GET /api/trading/registry served with the track record the
    human reviewed — the card's staleness check. If ANY input moved since
    (a trade settled, drift counters ticked, a validation landed) the digest
    no longer matches and the write is refused 409: re-basing is impossible,
    the human reviews the NEW track record. `note` is the operator's sentence
    on the approval row itself."""

    fingerprint: str
    note: str = ""


class TradingTrackRecord(BaseModel):
    """The paper track record summary the approval card carries (design §6):
    duration, trades, realized pnl — plus the drift counters, the live
    evidence of whether paper execution drifts from the contract. Explicit
    nulls when nothing has settled yet, never zeros: zero trades is a fact,
    zero pnl over zero trades would be a fiction."""

    trades_count: int
    realized_pnl: float | None
    span_days: float | None
    first_exit_at: dt.datetime | None
    last_exit_at: dt.datetime | None
    drift_fills_measured: int
    drift_breaches: int


class TradingRegistryVersion(BaseModel):
    """One strategy version with its lifecycle state, the evidence chain
    behind it, the paper track record, and the staleness fingerprint the
    approval flow consumes. `fingerprint` digests the inputs the approval
    card displays; a card confirmed after they moved answers 409."""

    version_id: int
    strategy_key: str
    name: str
    version: int
    state: str
    params: dict[str, Any]
    timeframe: str
    universe: list[str]
    code_hash: str
    validation_id: int | None
    state_since: dt.datetime | None
    state_evidence: str
    track_record: TradingTrackRecord
    fingerprint: str
    # the approval card this version is eligible for — "candidate_live" on a
    # paper version, null everywhere else. Null is the UI's cue to render a
    # row, never a card.
    pending_transition: str | None


class TradingRegistry(BaseModel):
    """GET /api/trading/registry — every registered version. Empty is the
    first-class answer: with zero validated strategies the lifecycle owns
    nothing, and the registry that shows nothing is the gate working."""

    versions: list[TradingRegistryVersion]

# --------------------------------------------------------------------------
# M4 dashboard additions: signals, per-strategy panels, validation queue,
# model registry — the §8 TRADING OPS + RESEARCH surfaces.


class TradingSignalItem(BaseModel):
    """One recorded emission — side, confidence, the signal bar's own time,
    and the outcome it met (entered / veto:* / below_confidence / no_atr /
    in_position / exited / flat_noop). `details` carries the sizing chain
    for entered and vetoed emissions: risk amount, stop distance, raw and
    rounded quantity, notional, the caps. Empty dict elsewhere, never
    invented numbers."""

    id: int
    created_at: dt.datetime | None
    bot: str
    symbol: str
    timeframe: str
    bar_time: dt.datetime | None
    side: str
    confidence: float
    outcome: str
    details: dict[str, Any]


class TradingSignalsToday(BaseModel):
    """GET /api/trading/signals/today — today's emissions per bot with the
    outcome counts. Empty rows is the first-class answer twice over: an
    engine that never ran has no emissions, and an engine whose strategies
    stayed silent has none either — the two read apart on the engine lamp,
    which is exactly why the lamp exists."""

    date: str
    signals: list[TradingSignalItem]


class TradingStrategyPanel(BaseModel):
    """One bot's per-strategy panel data: the cumulative realized net pnl
    curve derived from the desk's own closed trades (never estimated —
    equity_points rows are portfolio-wide, so a per-bot equity would be an
    allocation fiction), plus the count the panel captions with."""

    bot: str
    curve: list[TradingEquityPoint]
    trades_count: int


class TradingValidationQueueItem(BaseModel):
    """One version waiting at a gate, or a validation verdict with its
    reasons. `kind` distinguishes the two sentences: "awaiting" is a version
    in research state; "failure" is a validation row whose verdict is not
    validated, carrying the gate's own sentences. Awaiting versions carry no
    verdict numbers because none exist — explicit nulls, never zeros."""

    kind: str  # awaiting | failure
    version_id: int | None
    strategy_key: str | None
    version: int | None
    timeframe: str | None
    validation_id: int | None
    bot: str | None
    verdict: str | None
    reasons: list[str]
    created_at: dt.datetime | None
    permutation_p: float | None
    trades_n: int | None
    min_trades_required: int | None


class TradingValidationQueue(BaseModel):
    """GET /api/trading/validation-queue — versions awaiting the gates and
    the gate's failures with their reasons. Both lists empty is the honest
    answer for a pipeline with nothing in flight and nothing failed."""

    awaiting: list[TradingValidationQueueItem]
    failures: list[TradingValidationQueueItem]


class TradingModelVersionItem(BaseModel):
    """One ML model registry row: champion/challenger role, the OOS metrics
    the promotion gate measured, and the PSI drift when — and only when —
    it is honestly knowable. PSI is computed per retrain cycle and today
    travels inside the supervisor insight's text, never a column: null here
    is the documented answer, and the registry panel says where it lives."""

    id: int
    name: str
    version: int
    trained_at: dt.datetime | None
    train_window_days: int
    oos_accuracy: float
    oos_precision_long: float
    is_champion: bool
    role: str  # champion | challenger | retired
    psi_drift: float | None
    notes: str


class TradingModelRegistry(BaseModel):
    """GET /api/trading/model-registry — every ML model version with its
    promotion role and OOS evidence. Empty is the first-class answer: no
    retrain cycle has ever written a row."""

    models: list[TradingModelVersionItem]
    psi_note: str


class TradingEquityFan(BaseModel):
    """The bootstrap/permutation equity fan: percentile bands and sample
    paths over the trade steps of the validation's Monte Carlo. X is a step
    index (trade count along the path), not a clock — the fan answers
    "where could this path have gone", not "when"."""

    steps: list[int]
    initial_capital: float
    actual: list[float]
    band_p5: list[float]
    band_p25: list[float]
    band_p50: list[float]
    band_p75: list[float]
    band_p95: list[float]
    samples: list[list[float]]


# --------------------------------------------------------------------------
# M5 — the mandate machinery, built but never armed (design §6 layers 2-4).
# The models below describe consent, cards and the audit tape — surfaces
# whose honest-empty state is the design's expected M5 end state.


class MandateCreateRequest(BaseModel):
    """POST /api/trading/mandates body. The full cap set is echoed by the
    human in the request — every cap is a REQUIRED field, never defaulted
    server-side (consent_days is the single exception the design itself
    defaults, to 30 days). The reason is the mandate's nature: it is the
    human's written consent, and a consent the machine filled in for you is
    no consent at all. A form that forgets a number is refused at the door
    with 422, not guessed at — the same discipline the kill-switch's re-arm
    note follows. There is deliberately no automation path to this endpoint:
    the AI rule extends to trading as 'the model may never touch a mandate'."""

    version_id: int
    max_order_notional: float
    max_exposure: float
    instruments: list[str]
    max_trades_per_day: int
    consent_days: int = 30
    funding_min: float
    funding_max: float
    note: str = ""


class TradingMandate(BaseModel):
    """One immutable mandate row as the surface renders it: the cap set,
    the consent window with its expiry, and the integrity digest. `active`
    is the server's own verdict at render time — an expired mandate is
    shown, not hidden, because consent that lapsed is evidence too."""

    id: int
    version_id: int
    created_at: dt.datetime | None
    created_by: str
    max_order_notional: float
    max_exposure: float
    instruments: list[str]
    max_trades_per_day: int
    consent_days: int
    funding_min: float
    funding_max: float
    note: str
    mandate_hash: str
    expires_at: dt.datetime | None
    active: bool
    integrity_ok: bool


class TradingMandates(BaseModel):
    """GET /api/trading/mandates — every mandate row ever written, newest
    first. Empty is the first-class answer and the honest M5 end state:
    no mandate exists, the live path is unbuilt by design."""

    mandates: list[TradingMandate]


class OrderCardCreateRequest(BaseModel):
    """POST /api/trading/order-cards body. `chain` is the full decision
    chain the card carries — signal, sizing stages, rails state — exactly
    as design §6 layer 3 demands. The fingerprint is computed server-side
    from strategy state + mandate version and returned on the card; the
    client never supplies it (a client-supplied fingerprint would be a
    self-forged staleness check)."""

    version_id: int
    symbol: str
    side: str
    notional: float
    chain: dict[str, Any] = {}


class TradingOrderCard(BaseModel):
    """One order card: the intent, the decision chain, the fingerprint over
    strategy state + mandate version (never the live price — a card does
    not expire because the market moves), and the lifecycle state. In M5
    `verdict` on confirmation is the guard chain's answer, and the release
    terminates there: no live adapter exists, so 'released' means the guard
    chain allowed it, not that any venue saw it."""

    id: int
    version_id: int
    mandate_id: int | None
    created_at: dt.datetime | None
    symbol: str
    side: str
    notional: float
    chain: dict[str, Any]
    fingerprint: str
    state: str  # open | confirmed | released | denied
    decided_at: dt.datetime | None
    decision_note: str


class TradingOrderCards(BaseModel):
    """GET /api/trading/order-cards — every card, newest first. Empty is
    first-class: in M5 cards exist only when exercised."""

    cards: list[TradingOrderCard]


class OrderCardConfirmRequest(BaseModel):
    """POST /api/trading/order-cards/<id>/confirm body. The fingerprint the
    card rendered with — recomputed server-side from current rows; a
    mismatch is 409, re-basing impossible. `note` is the human's sentence
    on the decision."""

    fingerprint: str
    note: str = ""


class AuditSignoffCreateRequest(BaseModel):
    """POST /api/trading/audit-signoffs body. `document_ref` is the audit
    document's path or content hash — the signoff is meaningless unless it
    names WHAT was audited — and `note` is the human's own sentence. No
    signoff exists today by design: writing one is the owner's act, after
    the audit document exists."""

    version_id: int
    document_ref: str
    note: str = ""


class AuditChainVerification(BaseModel):
    """POST/GET verification of the audit ledger: violations name the rows,
    empty means the chain is intact."""

    rows: int
    violations: list[str]
    intact: bool
