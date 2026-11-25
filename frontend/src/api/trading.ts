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
export type BacktestRunDetail = Schemas["TradingRunDetail"];

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
