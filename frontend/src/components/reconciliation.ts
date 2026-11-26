/* The fund overview's sentences, out of the markup so they can be pinned
   without a DOM.

   Every empty state here is first-class per the design: an engine that never
   ran is a fact about the desk, a dollar figure no rate converts is a fact
   about the feed, and neither is an error. What is missing is said in words,
   never pretended away. */

import type { OverviewReconciliation } from "../api/overview";

/** What the equity cell says when the engine never wrote a row: a state of
    the desk, in the words the design gives the empty state. */
export const NO_DESK_EQUITY = "no desk equity recorded — the engine is offline or never ran";

/** What the reconciliation row can say, in one reading. */
export type ReconciliationReading =
  | { kind: "measured" } // the gap exists and is the figure it carries
  | { kind: "absent"; line: string }; // what stands between the reader and a gap

const MISSING_LINES: Record<string, string> = {
  "no-mapping":
    "no ledger account is declared as the trading account — the broker statement cannot be read",
  "institution-gone": "the account declared as the trading account no longer exists",
  "no-statement": "the trading account has no situation and no balance yet",
  "no-engine-equity": NO_DESK_EQUITY,
  "equity-unconvertible": "no rate converts the engine's dollars into the base",
};

/** The reconciliation as one sentence, or the measured state.
    Every missing piece is named; several missing pieces read as one list,
    because a reader fixing the first deserves to know the rest. */
export function reconciliationReading(recon: OverviewReconciliation): ReconciliationReading {
  if (!recon.missing.length) return { kind: "measured" };
  const lines = recon.missing.map((code) => MISSING_LINES[code] ?? `the gap cannot be measured (${code})`);
  return {
    kind: "absent",
    line: lines.length === 1 ? lines[0] : lines.slice(0, -1).join("; ") + "; and " + lines[lines.length - 1],
  };
}

/** An ISO datetime as the terminal prints it: the UTC day and minute,
    because a timestamp from the engine is UTC and printing it in local time
    would move it without saying so. */
export function engineStamp(iso: string): string {
  const t = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  if (Number.isNaN(t.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${t.getUTCFullYear()}-${pad(t.getUTCMonth() + 1)}-${pad(t.getUTCDate())} ${pad(t.getUTCHours())}:${pad(t.getUTCMinutes())}Z`;
}

/** The gap's sign as the desk reads it: positive means the ledger reads
    MORE than the engine believes it holds. */
export function gapDirection(gap: number): "ledger-ahead" | "engine-ahead" | "even" {
  if (Math.abs(gap) < 0.005) return "even";
  return gap > 0 ? "ledger-ahead" : "engine-ahead";
}
