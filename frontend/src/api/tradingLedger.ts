import { api } from "./client.ts";

/* The research ledger's in-app surface — sweep verdicts with power labels
   and venues. Separate module from trading.ts because the data plane is
   separate: these rows live in research.db (the program's diary), not the
   app database the desk writes. Hand-written types, same discipline as the
   generated ones: the backend payload is canonical, there is no mapping
   layer, and a null means what the backend says it means. */

/** One measured cell: verdict plus what the verdict stands on — sharpe with
    its bootstrap interval, trades against the minimum, the power resolution
    label (resolvable | untestable) and the tape venue since the schema
    landed (null = written before venue existed, honestly unknown). */
export interface LedgerVerdictRow {
  id: number;
  ts: string;
  family: string;
  candidate: string;
  symbol: string;
  timeframe: string;
  params_json: string;
  phase: string;
  verdict: string;
  trades_n: number;
  min_trades: number;
  sharpe: number | null;
  sharpe_ci_lo: number | null;
  sharpe_ci_hi: number | null;
  permutation_p: number | null;
  power_label: string | null;
  min_detectable_sharpe: number | null;
  venue: string | null;
  seed: number;
  elapsed_s: number | null;
}

export interface LedgerVerdictsResponse {
  rows: LedgerVerdictRow[];
  note?: string;
}

/** The by-family/phase/verdict counts — the same shape the public evidence
    room renders, so the app and the page can never disagree. */
export interface LedgerSummaryRow {
  family: string;
  phase: string;
  verdict: string;
  n: number;
}

export interface LedgerSummaryResponse {
  rows: LedgerSummaryRow[];
  note?: string;
}

export function getLedgerVerdicts(family?: string, limit = 100): Promise<LedgerVerdictsResponse> {
  const q = new URLSearchParams();
  if (family) q.set("family", family);
  q.set("limit", String(limit));
  return api(`/api/ledger/verdicts?${q.toString()}`);
}

export function getLedgerSummary(): Promise<LedgerSummaryResponse> {
  return api("/api/ledger/summary");
}
