import { api } from "./client.ts";
import type { Schemas } from "./types";

/* The intelligence and alerts surfaces (backend app/routers/intelligence.py,
   design §8). Same transcription rule as every client here: the backend's
   pydantic models are canonical, these types are their generated shapes, and
   there is no mapping layer — a test that finds this file transforming
   anything is a bug report.

   Everything is read-only: the feed merges wealth chain runs and trading
   agent insights; the memory browser reads the learning loop's tiers as they
   are persisted; the budget panel reads the desk's own request counter; the
   alerts stream is in-app by design — nothing here pages anyone. */

/** One row of the unified intelligence stream: a wealth chain run or a
    trading agent insight. `ref` is the API path of the full document where
    one exists — null means the row itself is all there is. */
export type IntelligenceFeedItem = Schemas["IntelligenceFeedItem"];
export type IntelligenceFeed = Schemas["IntelligenceFeed"];

export async function getIntelligenceFeed(params?: {
  source?: string;
  kind?: string;
  limit?: number;
}): Promise<IntelligenceFeed> {
  const qs = new URLSearchParams();
  if (params?.source) qs.set("source", params.source);
  if (params?.kind) qs.set("kind", params.kind);
  if (params?.limit) qs.set("limit", String(params.limit));
  const suffix = qs.size > 0 ? `?${qs.toString()}` : "";
  return (await api.get<IntelligenceFeed>(`/api/intelligence/feed${suffix}`)).data;
}

/** The layered memory browser's answer. `available` false means the agent
    memory table is not there to read — a state of the desk, not an empty
    memory. */
export type IntelligenceMemory = Schemas["IntelligenceMemory"];
export type MemoryEntry = Schemas["MemoryEntry"];

export async function getIntelligenceMemory(): Promise<IntelligenceMemory> {
  return (await api.get<IntelligenceMemory>("/api/intelligence/memory")).data;
}

/** The day's request spend against the free-tier caps. `available` false
    means no counter file exists — no LLM call ever claimed on this machine. */
export type IntelligenceBudget = Schemas["IntelligenceBudget"];

export async function getIntelligenceBudget(): Promise<IntelligenceBudget> {
  return (await api.get<IntelligenceBudget>("/api/intelligence/budget")).data;
}

/** The in-app alert stream: rail events, validation failures, stale
    heartbeats, reconciliation gaps — severity-typed, newest first. An empty
    `items` with `available` true is the desk in good health. */
export type AlertItem = Schemas["AlertItem"];
export type AlertsStream = Schemas["AlertsStream"];

export async function getAlerts(): Promise<AlertsStream> {
  return (await api.get<AlertsStream>("/api/alerts")).data;
}
