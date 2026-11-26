/* The Intel page's pure decisions — how a severity colours a row, how a
   timestamp renders in terminal voice, which source filter a stream supports.
   No React in here so node --test can argue with all of it directly. */

import type { AlertItem, IntelligenceFeedItem } from "../api/intelligence";

/* Severity is deliberately quiet: the phosphor terminal idiom reserves loud
   colour for things that are genuinely on fire. `critical` alone gets the
   down-red; warnings wear the amber of the warn token; information is ink at
   the softened weight — a stream where everything shouts is a stream nobody
   reads. */
export type SeverityTone = "critical" | "warning" | "info";

export function severityTone(severity: string | undefined | null): SeverityTone {
  if (severity === "critical") return "critical";
  if (severity === "warning") return "warning";
  return "info";
}

export const TONE_TEXT: Record<SeverityTone, string> = {
  critical: "text-down",
  warning: "text-warn",
  info: "text-ink-soft",
};

export const TONE_MARK: Record<SeverityTone, string> = {
  critical: "text-down",
  warning: "text-warn",
  info: "text-ink-faint",
};

/** The single glyph at the row's left edge: a terminal marks severity with a
    character, not a badge — the scan pattern is a column. */
export function severityMark(severity: string | undefined | null): string {
  const tone = severityTone(severity);
  if (tone === "critical") return "✕";
  if (tone === "warning") return "▲";
  return "·";
}

/* The clock column. Terminal rows align in a fixed-width prefix: HH:MM for
   today, MMM-DD for anything older — both exactly 5 characters, so the eye's
   column never shifts. UTC throughout: every backend clock is UTC, and a
   desk that runs through the night has no use for a date that flips at a
   local midnight. */
export function fmtClock(iso: string, now: Date = new Date()): string {
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return "-----";
  const sameDay =
    t.getUTCFullYear() === now.getUTCFullYear() &&
    t.getUTCMonth() === now.getUTCMonth() &&
    t.getUTCDate() === now.getUTCDate();
  if (sameDay) {
    const hh = String(t.getUTCHours()).padStart(2, "0");
    const mm = String(t.getUTCMinutes()).padStart(2, "0");
    return `${hh}:${mm}`;
  }
  const months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];
  return `${months[t.getUTCMonth()]}-${String(t.getUTCDate()).padStart(2, "0")}`;
}

/** The distinct sources a feed can be filtered by, in stable order: wealth
    first (it is the slower, rarer voice), then trading agents alphabetically.
    Derived from the feed's own `sources` list, never hardcoded — an agent
    that starts writing tomorrow appears without a code change. */
export function sourceOptions(sources: string[]): string[] {
  return [...sources].sort((a, b) => {
    const wa = a.startsWith("wealth") ? 0 : 1;
    const wb = b.startsWith("wealth") ? 0 : 1;
    return wa !== wb ? wa - wb : a.localeCompare(b);
  });
}

/** Client-side narrowing for a stream already fetched. The backend filters
    too — this exists because re-fetching on every filter click would make
    the panel blink; the stream is small enough to hold, and the filter is a
    lens over what is in hand, not a new question to the server. */
export function filterFeed(
  items: IntelligenceFeedItem[],
  source: string | null,
): IntelligenceFeedItem[] {
  if (source === null) return items;
  return items.filter((i) => i.source === source || i.source.startsWith(source + ":"));
}

/** Alerts grouped the way the panel scans them: critical first, then
    warnings, then information — severity outranks recency inside a stream
    that is already roughly newest-first. Stable within a severity. */
export function severityRank(severity: string): number {
  const tone = severityTone(severity);
  return tone === "critical" ? 0 : tone === "warning" ? 1 : 2;
}

export function alertsBySeverity(items: AlertItem[]): AlertItem[] {
  return [...items].sort((a, b) => severityRank(a.severity) - severityRank(b.severity));
}

/** The memory tier's display order and its one-word gloss: the loop's own
    vocabulary, explained once in the panel hint, abbreviated in the column
    because the rows are dense. */
export const TIER_ORDER = ["working", "shallow", "deep"] as const;

export function tierGloss(tier: string): string {
  if (tier === "working") return "raw outcomes — decay in days";
  if (tier === "shallow") return "distilled lessons — decay in weeks";
  if (tier === "deep") return "consolidated reflections — durable";
  return tier;
}
