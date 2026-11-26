import { api } from "./client.ts";
import type { Schemas } from "./types";

/* The trading plane's read-only API — engine state, the strategies registry,
   and the research record of backtest runs with their validation verdicts.

   The shapes are the generated ones (see api/types.ts for why that matters):
   the backend's typed response models in app/routers/trading.py are canonical
   and this file is their transcription — there is no mapping layer, and a
   test that finds the client transforming anything is a bug report.

   Everything here is read-only by design: the engine never serves the UI, it
   writes rows; the UI reads rows. A control surface (the kill-switch) is a
   later milestone and a separate module. */

/** What the engine last told the database about itself. `last_tick_at` null
    means the engine has never ticked. `strategies_registered` is 0 until the
    lifecycle tables land in M3 — a constant, honestly reported. */
export type TradingStatus = Schemas["TradingStatus"];

/** One strategy in the static registry. `registered` is always false today:
    ported as code, research-only — no lifecycle tables exist to say otherwise. */
export type TradingStrategy = Schemas["TradingStrategy"];

/** The validation summary attached to a run that went through the gate.
    permutation_p: the Monte Carlo permutation test's p-value. sharpe_ci_lo/hi:
    the bootstrap confidence interval on Sharpe. wf_positive_folds /
    wf_total_folds: walk-forward consistency. */
export type ValidationSummary = Schemas["TradingValidationSummary"];

/** The analyzer's metrics for a run — win rate, profit factor, Sharpe,
    drawdown, total return. */
export type RunMetrics = Schemas["TradingRunMetrics"];

/** One row of the research record. Note `started_at` and `created_at` are the
    same instant today (the backend fills both from the run's creation); they
    are separate keys because a run's start and its recording diverge the day
    runs are queued rather than immediate. The OpenAPI type says nullable —
    the backend always sends them, the nullability is pydantic's honesty about
    datetime serialization, so display code guards with a dash rather than
    trusting the non-null case blindly. */
export type BacktestRun = Schemas["TradingRunItem"];

/** What the verdict stands on: the seed, source, rows and data window that
    make the run reproducible. Present only when validation ran; a run without
    the gate has provenance null. */
export type RunProvenance = Schemas["TradingProvenance"];

/** The detail adds what the run was made OF. `reasons` are the gate's own
    sentences — which check failed and why — empty when validation never ran,
    in which case `provenance` is null and the verdict statistics
    (prob_positive, sharpe_actual, min_trades_required) are explicit nulls. */
export type BacktestRunDetail = Schemas["TradingRunDetail"] & {
  /* The equity curve and the trade blotter the run recorded. These keys are
     NOT in the generated schema yet — the backend lane lands them in the same
     milestone; after its commit `npm run gen:types` picks them up and this
     intersection narrows back to the plain generated type. Both are
     explicitly nullable: null means the run predates the recording (or the
     recorder never ran on it), and the UI says exactly that instead of
     inventing a curve. */
  equity_curve: ApiEquityPoint[] | null;
  trades: BacktestTrade[] | null;
};

/** One point of a run's recorded equity curve: the bar timestamp as an ISO
    string and the portfolio equity at that moment. Conversion to the chart's
    unix-seconds shape lives in viz/equityData.ts — the wire format is the
    backend's, the chart format is the chart's, and the mapping is one tested
    function, not a spread of ad hoc Date parsing. */
export interface ApiEquityPoint {
  t: string;
  equity: number;
}

/** One closed trade of a run: entry/exit instants, direction, quantity,
    both prices and the realized pnl. What the blotter rows are made of —
    flat by design, because a datagrid column is exactly one flat key. */
export interface BacktestTrade {
  entry_time: string;
  exit_time: string;
  side: "long" | "short";
  qty: number;
  entry_price: number;
  exit_price: number;
  pnl: number;
}

/* The verdict as the backend writes it — lowercase, because that is what the
   validation pipeline stores. The generated type is plain `string | null`
   (OpenAPI does not carry the enum), so this union is a LOCAL NARROWING for
   the badge logic: a value outside the two literals must fail safe to the
   muted "not validated" state, which is exactly what the badge does. */
export type Verdict = "validated" | "rejected" | null;

export async function getTradingStatus(): Promise<TradingStatus> {
  return (await api.get<TradingStatus>("/api/trading/status")).data;
}

export async function getTradingStrategies(): Promise<TradingStrategy[]> {
  return (await api.get<TradingStrategy[]>("/api/trading/strategies")).data;
}

export async function getBacktestRuns(): Promise<BacktestRun[]> {
  return (await api.get<BacktestRun[]>("/api/trading/backtest-runs")).data;
}

export async function getBacktestRun(id: number): Promise<BacktestRunDetail> {
  return (await api.get<BacktestRunDetail>(`/api/trading/backtest-runs/${id}`)).data;
}

/** One open position, exactly the backend's row: the protective levels it
    carries, the signal-time provenance (null for rows predating the kernel
    migration), and `age_seconds` measured on the SERVER'S clock at read time
    — the client ticks forward from it rather than trusting its own clock
    against opened_at. There is no rearmed state: rearm is kernel memory,
    never persisted, and a re-armed position IS the same position. */
export type TradingPosition = Schemas["TradingPosition"];

/** One settled round-trip — the recent-trades strip's evidence row. */
export type TradingClosedTrade = Schemas["TradingClosedTrade"];

export async function getTradingPositions(): Promise<TradingPosition[]> {
  return (await api.get<TradingPosition[]>("/api/trading/positions")).data;
}

/** The desk's rail state: per-bot kill-switch/drawdown, daily loss consumed,
    loss-streak cooldown and exposure against the caps, plus the desk-wide
    external halts (manual kill-switch, halt sentinel) and the recent
    risk_events the rails wrote to explain themselves. `bots` empty is the
    honest answer both for an engine that never ran and for the ready-and-
    empty end state of a registry with zero validated strategies. */
export type TradingRailsStatus = Schemas["TradingRailsStatus"];
export type TradingBotRails = Schemas["TradingBotRails"];
export type TradingRiskEvent = Schemas["TradingRiskEvent"];

export async function getTradingRails(): Promise<TradingRailsStatus> {
  return (await api.get<TradingRailsStatus>("/api/trading/rails")).data;
}

export async function getRecentTrades(): Promise<TradingClosedTrade[]> {
  return (await api.get<TradingClosedTrade[]>("/api/trading/positions/recent-trades")).data;
}

/** The slice-5 divergence surface: per bot, the declared drift budget, the
    feed counters the live process measures, the aggregated per-fill drift
    evidence, and the distributional paper-vs-backtest comparison — null
    with an explanatory note whenever the data volume is below the same
    statistical bar the validation gate sets (30 trades per side). Never
    fake statistics over two trades. */
export type TradingDivergenceStatus = Schemas["TradingDivergenceStatus"];
export type TradingBotDivergence = Schemas["TradingBotDivergence"];

export async function getTradingDivergence(): Promise<TradingDivergenceStatus> {
  return (await api.get<TradingDivergenceStatus>("/api/trading/divergence")).data;
}

/* ---- M4 control surfaces: the first write paths of this client.

   The read endpoints above describe the engine; the functions below are the
   operator's hands on it. Both write paths carry the same honesty contract
   as the backend: the kill-switch audit tape is server-side and unconditional
   (this client cannot forget it), and the approval card's fingerprint is the
   exact digest GET /registry served — never recomputed client-side, because
   a client that recomputes inputs is a client that can drift from what was
   on the screen. */

/** The kill-switch as persisted. `tripped` true means entries are halted
    desk-wide RIGHT NOW — protective exits always keep flowing, the switch
    refuses entries, never safety. */
export type KillSwitchState = Schemas["KillSwitchState"];

/** Throw the manual kill-switch. `enabled: true` halts entries immediately
    and needs no note — in that direction speed beats paperwork. Re-arming
    (`enabled: false`) is the dangerous direction and the backend refuses
    (422) without a non-empty note: the audit row deserves the operator's
    own sentence for why. */
export async function setKillSwitch(enabled: boolean, note: string): Promise<KillSwitchState> {
  return (await api.post<KillSwitchState>("/api/trading/kill-switch", { enabled, note })).data;
}

/** One registry version: state, evidence chain, paper track record, and the
    staleness fingerprint the approval flow consumes. */
export type TradingRegistryVersion = Schemas["TradingRegistryVersion"];
export type TradingTrackRecord = Schemas["TradingTrackRecord"];
export type TradingApprovalResult = Schemas["TradingApprovalResult"];

export async function getTradingRegistry(): Promise<TradingRegistryVersion[]> {
  return (await api.get<Schemas["TradingRegistry"]>("/api/trading/registry")).data.versions;
}

/** Confirm the paper → candidate_live approval card. `fingerprint` must be
    the digest the registry served WITH the track record the human reviewed:
    if any input moved since, the backend answers 409 ("inputs moved") and
    nothing is written — re-basing is impossible, the human reviews the new
    track record. Callers distinguish the 409 by `axios` status, not by
    parsing the sentence. */
export async function approveVersion(
  versionId: number,
  fingerprint: string,
  note: string,
): Promise<TradingApprovalResult> {
  return (
    await api.post<TradingApprovalResult>(`/api/trading/registry/${versionId}/approve`, {
      fingerprint,
      note,
    })
  ).data;
}

/** True when a failure is the approval flow's staleness refusal — the 409
    the design mandates, distinct from a network or validation failure. */
export function isConflict(e: unknown): boolean {
  return (
    typeof e === "object" &&
    e !== null &&
    "response" in e &&
    typeof (e as { response?: { status?: number } }).response?.status === "number" &&
    (e as { response: { status: number } }).response.status === 409
  );
}

/* ---- M4 §8 additions: signals, per-strategy panels, validation queue,
   model registry — the TRADING OPS + RESEARCH surfaces. Same transcription
   rule as everything above: the backend's pydantic models are canonical,
   this file adds no mapping layer. */

/** One recorded emission, rejections included — the M3 acceptance surface.
    `outcome` is the closed vocabulary the backend documents on the model:
    entered / veto:<rail> / qty_zero / below_confidence / no_atr /
    in_position / exited / flat_noop. `details` carries the sizing chain for
    entered and vetoed emissions — empty elsewhere, never invented. */
export type TradingSignalItem = Schemas["TradingSignalItem"];
export type TradingSignalsToday = Schemas["TradingSignalsToday"];

export async function getTradingSignalsToday(): Promise<TradingSignalsToday> {
  return (await api.get<TradingSignalsToday>("/api/trading/signals/today")).data;
}

/** One bot's per-strategy panel: the cumulative realized net pnl curve
    derived from the desk's own closed trades (never an allocation of the
    portfolio equity rows — those are desk-wide by design) and the count. */
export type TradingStrategyPanel = Schemas["TradingStrategyPanel"];

export async function getStrategyPanels(): Promise<TradingStrategyPanel[]> {
  return (await api.get<TradingStrategyPanel[]>("/api/trading/strategy-panels")).data;
}

/** The validation queue: versions awaiting the gates (research state, no
    verdict numbers — explicit nulls, never zeros) and the gate's failures
    carrying the reasons it wrote. */
export type TradingValidationQueue = Schemas["TradingValidationQueue"];
export type TradingValidationQueueItem = Schemas["TradingValidationQueueItem"];

export async function getValidationQueue(): Promise<TradingValidationQueue> {
  return (await api.get<TradingValidationQueue>("/api/trading/validation-queue")).data;
}

/** The ML model registry: champion/challenger/retired role per version and
    the OOS evidence the promotion gate measured. PSI drift is null on the
    wire by design — the retrain cycle records it in the supervisor insight's
    text, never a column — and `psi_note` is the panel's documentation of
    exactly that. */
export type TradingModelRegistry = Schemas["TradingModelRegistry"];
export type TradingModelVersionItem = Schemas["TradingModelVersionItem"];

export async function getModelRegistry(): Promise<TradingModelRegistry> {
  return (await api.get<TradingModelRegistry>("/api/trading/model-registry")).data;
}

/** The equity fan: the Monte Carlo permutation percentile bands and sample
    paths over the validation's trade steps. X is a step index, not a clock —
    the fan answers where the path could have gone, not when. Null on the
    detail means never recorded (or the path matrix honestly too large to
    keep), and the UI says so instead of inventing bands. */
export type TradingEquityFan = Schemas["TradingEquityFan"];

/* ---- M5 mandate machinery — built, never armed. Same transcription rule:
   the backend's pydantic models are canonical. The honest-empty answer is
   the design's expected end state: no mandate exists, no card exercised. */

/** One immutable mandate row: the hard caps a human consented to, the
    consent window with its expiry, and the integrity digest. `active` is the
    server's verdict at render time — an expired mandate is shown, never
    hidden, because lapsed consent is evidence too. */
export type TradingMandate = Schemas["TradingMandate"];

/** One order card: the intent, the decision chain, the fingerprint over
    strategy state + mandate version (never the live price), and the
    lifecycle state. 'released' means the guard chain allowed it — in M5 no
    venue exists, the flow terminates at the chain. */
export type TradingOrderCard = Schemas["TradingOrderCard"];

export async function getTradingMandates(): Promise<TradingMandate[]> {
  return (await api.get<Schemas["TradingMandates"]>("/api/trading/mandates")).data.mandates;
}

export async function getTradingOrderCards(): Promise<TradingOrderCard[]> {
  return (await api.get<Schemas["TradingOrderCards"]>("/api/trading/order-cards")).data.cards;
}
