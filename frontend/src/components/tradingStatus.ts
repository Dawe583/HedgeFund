import type { BacktestRun, TradingDivergenceStatus, TradingStatus } from "../api/trading";

/* The Trading page's logic, pure and testable: every decision the page makes
   about what to show — what the verdict badge says, what colour it wears, how
   the engine's state reads, which run sorts first — lives here, in plain
   functions over plain data. Trading.tsx maps these onto pixels and makes no
   decisions of its own, so node --test can argue with all of it without a
   DOM. The repo's pattern (followStream, explain, watchItem), applied. */

/* ---- Verdict badges ---------------------------------------------------- */

export type BadgeTone = "up" | "down" | "muted";

/** What a run's verdict wears. `validated` is the pipeline saying the evidence
    holds (the gain colour); `rejected` is the gate doing its job (the loss
    colour — a rejection is the system working, not failing); null is a run
    that never went through validation, and it must NOT borrow either colour:
    "no verdict yet" is a fact, not an outcome. */
export function verdictBadge(verdict: string | null): { label: string; tone: BadgeTone } {
  if (verdict === "validated") return { label: "Validated", tone: "up" };
  if (verdict === "rejected") return { label: "Rejected", tone: "down" };
  return { label: "Not validated", tone: "muted" };
}

/* ---- Engine state ------------------------------------------------------ */

/* The engine being offline is a first-class state, NOT an error: the design
   (hedge-fund-os.md §8) says the engine-offline state is a visual state of
   its own, never an empty dashboard pretending precision. What changes with
   the state is what the page can claim: running means the numbers are being
   written now; offline means everything shown is the last thing the engine
   said, dated. */

export type EngineReading =
  | { state: "running"; line: string }
  | { state: "offline"; line: string }
  | { state: "unreachable"; line: string };

function fmtDateTime(iso: string): string {
  // The reader's locale, resolved through the runtime — the same convention
  // money.ts documents: never a hardcoded country format.
  return new Date(iso).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** The status header's one sentence, in the state's own words.
    `status` null means the backend itself did not answer — a different fact
    from "the engine is offline", and never merged into it: the database may
    be perfectly fine while the web process is down, and confusing the two is
    how "offline" came to mean "something is wrong somewhere". */
export function engineReading(status: TradingStatus | null): EngineReading {
  if (status === null) {
    return {
      state: "unreachable",
      line: "The backend did not answer — nothing below is current.",
    };
  }
  if (status.engine_state === "running") {
    return {
      state: "running",
      line: status.last_tick_at
        ? `Engine running — last tick ${fmtDateTime(status.last_tick_at)}.`
        : "Engine running — no tick recorded yet.",
    };
  }
  return {
    state: "offline",
    line: status.last_tick_at
      ? `Engine offline — showing what it last wrote, ${fmtDateTime(status.last_tick_at)}.`
      : "Engine offline — it has never ticked, so there is nothing it wrote.",
  };
}

/** The header's tint: green for running, quiet grey for offline (a state,
    not a failure), the warn tint only for unreachable — the one state where
    even the "offline" claim cannot be made honestly. */
export function engineTone(reading: EngineReading): "up" | "muted" | "warn" {
  if (reading.state === "running") return "up";
  if (reading.state === "offline") return "muted";
  return "warn";
}

/* ---- The research record ----------------------------------------------- */

/** Newest first: the research record is read as a log, and a log's present
    is at the top. `started_at` is the run's own time, not `created_at` — the
    row's insertion order is a database accident, the run's start is the fact.
    A null start (the type allows it, the backend never sends it) sorts below
    everything dated — unknown is never "newest". */
export function runsNewestFirst(runs: BacktestRun[]): BacktestRun[] {
  return [...runs].sort((a, b) => (b.started_at ?? "").localeCompare(a.started_at ?? ""));
}

/** The permutation test's p-value, printed as a statistician reads it: small
    values precise, the rest to two decimals — and never rounded into
    significance it did not reach ("0.00" would claim exactly zero). null is a
    fact too — the validation row exists but the statistic does not — and it
    prints as a dash, never a zero. */
export function fmtP(p: number | null): string {
  if (p === null) return "—";
  if (p <= 0) return "0";
  if (p < 0.01) return p.toFixed(4);
  return p.toFixed(2);
}

/** The bootstrap Sharpe confidence interval as one interval, both ends
    signed. This is the figure the verdict stands on, so it is printed in
    full — never collapsed to the point estimate, which is precisely the
    number the validation pipeline exists to distrust. */
export function fmtCi(lo: number | null, hi: number | null): string {
  if (lo === null || hi === null) return "—";
  const end = (x: number) => (x >= 0 ? "+" : "") + x.toFixed(2);
  return `${end(lo)} … ${end(hi)}`;
}

/** Walk-forward consistency as the fraction it is: positive folds over all
    folds. */
export function fmtFolds(positive: number, total: number): string {
  return `${positive}/${total}`;
}

/** Ticks of drift as the blotter/terminal readout — one decimal, sign kept
    because systematic sign IS the signal (consistently negative entry
    deviation reads as adverse selection; magnitude alone hides it). Null
    renders as a dash, never a zero: unmeasured is a different fact than
    zero deviation. */
export function fmtTicks(dev: number | null | undefined): string {
  if (dev === null || dev === undefined) return "—";
  const v = Math.abs(dev) < 0.05 ? 0 : dev;
  return (v > 0 ? "+" : "") + v.toFixed(1);
}

/** Per-bot divergence budget lookup the blotter/trades strips color against.
    Maps bot -> max dev ticks the version declared; absent means no snapshot
    exists and nothing colors — an unknown budget is never a zero budget. */
export type DivergenceBudgets = Map<string, number>;

export function divergenceBudgetsOf(
  divergence: TradingDivergenceStatus | null,
): DivergenceBudgets {
  const out: DivergenceBudgets = new Map();
  if (!divergence) return out;
  for (const b of divergence.bots) {
    if (b.budget_dev_ticks !== null && b.budget_dev_ticks !== undefined) {
      out.set(b.bot, b.budget_dev_ticks);
    }
  }
  return out;
}
