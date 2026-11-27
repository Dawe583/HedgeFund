import { useEffect, useMemo, useState, type KeyboardEvent } from "react";
import {
  getAlerts,
  getIntelligenceBudget,
  getIntelligenceFeed,
  getIntelligenceMemory,
  type AlertItem,
  type AlertsStream,
  type IntelligenceBudget,
  type IntelligenceFeed,
  type IntelligenceFeedItem,
  type IntelligenceMemory,
  type MemoryEntry,
} from "../api/intelligence";
import { cardClass, Section, statLabelClass } from "./ui";
import { apiError } from "./apiError";
import { EmptyState } from "./Emblem";
import {
  alertsBySeverity,
  filterFeed,
  fmtClock,
  severityMark,
  severityTone,
  sourceOptions,
  tierGloss,
  TIER_ORDER,
  TONE_MARK,
  TONE_TEXT,
} from "./intelFormat";

/* INTEL — the intelligence and alerts surfaces (design §8): one stream of
   what the agents said across both planes, the learning loop's memory as it
   is persisted, the day's request budget against its caps, and the alert
   stream, in-app only.

   The panels are honest-empty by construction: an engine that never ran,
   a memory that was never written, a budget never claimed — each renders as
   a sentence saying exactly that, never as a table of nothing and never as
   an error. The data path is read-only end to end: nothing on this page can
   write, because nothing here is a control surface. */

// The stream's poll cadence. Alerts are the desk's smoke detector — a minute
// is the slowest that is still a detector — and everything else rides the
// same tick because nothing here is expensive: four small reads, one per
// minute, on one person's machine.
const POLL_MS = 60_000;

function useIntelData() {
  const [feed, setFeed] = useState<IntelligenceFeed | null>(null);
  const [alerts, setAlerts] = useState<AlertsStream | null>(null);
  const [memory, setMemory] = useState<IntelligenceMemory | null>(null);
  const [budget, setBudget] = useState<IntelligenceBudget | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () => {
      // Promise.allSettled rather than four independent chains: the panels
      // answer different questions, but they answer them on the same tick,
      // and a tick that lands all four together never paints half the page
      // newer than the other half.
      Promise.allSettled([
        getIntelligenceFeed(),
        getAlerts(),
        getIntelligenceMemory(),
        getIntelligenceBudget(),
      ]).then(([f, a, m, b]) => {
        if (!alive) return;
        if (f.status === "fulfilled") setFeed(f.value);
        if (a.status === "fulfilled") setAlerts(a.value);
        if (m.status === "fulfilled") setMemory(m.value);
        if (b.status === "fulfilled") setBudget(b.value);
        const failed = [f, a, m, b].find((r) => r.status === "rejected");
        if (failed && failed.status === "rejected") {
          setError(apiError(failed.reason, "The intelligence surfaces could not be loaded."));
        }
      });
    };
    load();
    const t = setInterval(load, POLL_MS);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  return { feed, alerts, memory, budget, error };
}

/* ------------------------------------------------------------------ rows */

function FeedRow({
  item,
  selected,
  onSelect,
}: {
  item: IntelligenceFeedItem;
  selected: boolean;
  onSelect: () => void;
}) {
  const tone = severityTone(item.severity);
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={
        "flex w-full items-baseline gap-3 px-2 py-1 text-left font-mono text-xs leading-5 transition " +
        (selected ? "bg-olive-tint" : "hover:bg-tint")
      }
    >
      <span className="shrink-0 tabular-nums text-ink-faint">{fmtClock(item.ts)}</span>
      <span className={"shrink-0 " + TONE_MARK[tone]}>{severityMark(item.severity)}</span>
      <span className="shrink-0 rounded-none border border-hair px-1 text-[10px] uppercase tracking-wide text-ink-soft">
        {item.source}
      </span>
      <span className="min-w-0 flex-1 truncate text-ink">
        <span className={TONE_TEXT[tone] === "text-ink-soft" ? "text-ink" : TONE_TEXT[tone]}>
          {item.title}
        </span>
        {item.summary && <span className="text-ink-soft"> — {item.summary}</span>}
      </span>
    </button>
  );
}

/* The feed panel, exported for the render tests: dense terminal rows,
   filterable by source, arrow-key navigable — one keystroke per row, because
   a stream is scanned, not clicked. */
export function FeedPanel({
  feed,
  selected,
  onSelected,
}: {
  feed: IntelligenceFeed | null;
  selected: number;
  onSelected: (index: number) => void;
}) {
  const [sourceFilter, setSourceFilter] = useState<string | null>(null);

  const items = useMemo(
    () => filterFeed(feed?.items ?? [], sourceFilter),
    [feed, sourceFilter],
  );
  const options = useMemo(() => sourceOptions(feed?.sources ?? []), [feed]);

  function onKey(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === "ArrowDown" && items.length > 0) {
      e.preventDefault();
      onSelected(Math.min(selected + 1, items.length - 1));
    } else if (e.key === "ArrowUp" && items.length > 0) {
      e.preventDefault();
      onSelected(Math.max(selected - 1, 0));
    }
  }

  if (feed === null) {
    return <p className="text-sm text-ink-soft">Reading the stream…</p>;
  }
  if (feed.items.length === 0 && feed.sources.length === 0) {
    return (
      <EmptyState title="Nothing has been said yet">
        No analysis run has finished and no agent has written an insight. The stream fills itself
        the first time either plane speaks.
      </EmptyState>
    );
  }

  return (
    <div>
      {options.length > 1 && (
        <div className="mb-2 flex flex-wrap items-baseline gap-x-3 gap-y-1 font-mono text-xs">
          <button
            type="button"
            onClick={() => setSourceFilter(null)}
            aria-pressed={sourceFilter === null}
            className={
              "uppercase tracking-wide " +
              (sourceFilter === null ? "font-medium text-ink underline underline-offset-4" : "text-ink-soft hover:text-ink")
            }
          >
            all
          </button>
          {options.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setSourceFilter(sourceFilter === s ? null : s)}
              aria-pressed={sourceFilter === s}
              className={
                "uppercase tracking-wide " +
                (sourceFilter === s ? "font-medium text-ink underline underline-offset-4" : "text-ink-soft hover:text-ink")
              }
            >
              {s}
            </button>
          ))}
        </div>
      )}
      {/* role=listbox/option rather than a table: the rows are selectable for
          keyboard scanning, not data cells. The listbox owns the arrows — the
          shell's digit hotkeys never fire while it has focus, per hotkeys.ts's
          guard. */}
      <div
        role="listbox"
        aria-label="Intelligence stream"
        tabIndex={0}
        onKeyDown={onKey}
        className={"divide-y divide-hair outline-none focus:border-olive " + cardClass}
      >
        {items.length === 0 ? (
          <p className="px-2 py-3 text-sm text-ink-soft">
            Nothing from that source in the stream. The filter is a lens, not a deletion —{" "}
            {feed.items.length} {feed.items.length === 1 ? "entry" : "entries"} across the other
            sources.
          </p>
        ) : (
          items.map((item, i) => (
            <FeedRow key={`${item.source}-${item.ts}-${i}`} item={item} selected={i === selected} onSelect={() => onSelected(i)} />
          ))
        )}
      </div>
    </div>
  );
}

export const FeedPanelForTest = FeedPanel;

/* ---------------------------------------------------------------- alerts */

function AlertRow({ item }: { item: AlertItem }) {
  const tone = severityTone(item.severity);
  return (
    <div className="flex items-baseline gap-3 px-2 py-1 font-mono text-xs leading-5">
      <span className="shrink-0 tabular-nums text-ink-faint">{fmtClock(item.ts)}</span>
      <span className={"shrink-0 " + TONE_MARK[tone]}>{severityMark(item.severity)}</span>
      <span className={"shrink-0 text-[10px] uppercase tracking-wide " + TONE_TEXT[tone]}>
        {item.kind}
      </span>
      <span className="min-w-0 flex-1 truncate">
        <span className={tone === "info" ? "text-ink" : TONE_TEXT[tone]}>{item.title}</span>
        {item.detail && <span className="text-ink-soft"> — {item.detail}</span>}
      </span>
    </div>
  );
}

/* The alerts panel, exported for the render tests. Sorted severity-first on
   the client: a stream scanned top-down must put the fire above the noise,
   and the backend's newest-first order is recency, not urgency. */
export function AlertsPanel({ alerts }: { alerts: AlertsStream | null }) {
  if (alerts === null) {
    return <p className="text-sm text-ink-soft">Reading the alert stream…</p>;
  }
  if (alerts.items.length === 0) {
    return (
      <EmptyState title="Nothing is wrong">
        No rail has fired, no validation has failed, no heartbeat is silent, and the ledger and the
        engine agree within measurement noise — as far as either plane can measure.
      </EmptyState>
    );
  }
  const sorted = alertsBySeverity(alerts.items);
  const criticals = sorted.filter((i) => severityTone(i.severity) === "critical").length;
  return (
    <div>
      {criticals > 0 && (
        <p className="mb-2 font-mono text-xs uppercase tracking-wide text-down">
          {criticals} critical — read those first
        </p>
      )}
      <div className={"divide-y divide-hair " + cardClass}>
        {sorted.map((item, i) => (
          <AlertRow key={`${item.kind}-${item.ts}-${i}`} item={item} />
        ))}
      </div>
    </div>
  );
}

export const AlertsPanelForTest = AlertsPanel;

/* ---------------------------------------------------------------- memory */

function MemoryTier({ tier, entries }: { tier: string; entries: MemoryEntry[] }) {
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <h4 className={statLabelClass}>{tier}</h4>
        <span className="text-xs text-ink-faint">{tierGloss(tier)}</span>
      </div>
      {entries.length === 0 ? (
        <p className="mt-1 text-xs text-ink-faint">Nothing in this tier.</p>
      ) : (
        <ul className="mt-1 divide-y divide-hair border border-hair">
          {entries.map((e) => (
            <li key={e.id} className="flex items-baseline gap-3 px-2 py-1 text-xs">
              <span className="shrink-0 font-mono tabular-nums text-ink-faint">{fmtClock(e.created_at)}</span>
              <span className="shrink-0 font-mono text-[10px] uppercase text-ink-soft">{e.kind}</span>
              <span className="min-w-0 flex-1 text-ink">{e.content}</span>
              {e.pnl_pct !== null && (
                <span className={"shrink-0 font-mono tabular-nums " + (e.pnl_pct >= 0 ? "text-up" : "text-down")}>
                  {e.pnl_pct >= 0 ? "+" : ""}
                  {(e.pnl_pct * 100).toFixed(1)}%
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* The memory browser, exported for the render tests. Omitted entirely when
   the store does not exist — a memory browser over no memory system would be
   fake chrome, and the honest answer is the page without the panel. */
export function MemoryPanel({ memory }: { memory: IntelligenceMemory | null }) {
  if (memory === null || !memory.available) return null;
  const total = memory.working.length + memory.shallow.length + memory.deep.length;
  return (
    <div className="space-y-4">
      {total === 0 && (
        <p className="text-sm text-ink-soft">
          The memory tables exist and are empty — the learning loop has not distilled a single
          outcome yet. It writes after closed trades.
        </p>
      )}
      {TIER_ORDER.map((tier) => (
        <MemoryTier key={tier} tier={tier} entries={memory[tier]} />
      ))}
    </div>
  );
}

export const MemoryPanelForTest = MemoryPanel;

/* ---------------------------------------------------------------- budget */

/* The budget panel, exported for the render tests. Same omission rule as
   memory: no counter file means no LLM call was ever claimed, and a panel
   showing zeros would claim the day started. */
export function BudgetPanel({ budget }: { budget: IntelligenceBudget | null }) {
  if (budget === null || !budget.available) return null;
  // pydantic defaults serialize as optional in the generated types; the
  // backend always sends them, and the guards keep tsc honest either way.
  const used = budget.used ?? 0;
  const daily = budget.daily_budget ?? 0;
  const caps = budget.tier_caps ?? [];
  const pct = daily > 0 ? used / daily : 0;
  return (
    <div className="space-y-3">
      <div className="flex items-baseline gap-3 font-mono text-sm">
        <span className="tabular-nums text-ink">
          {used} / {daily}
        </span>
        <span className="text-xs text-ink-soft">requests today ({budget.day ?? "UTC day"})</span>
        <span className={"text-xs tabular-nums " + (pct > 0.8 ? "text-warn" : "text-ink-faint")}>
          {Math.round(pct * 100)}%
        </span>
      </div>
      <div className="h-1.5 w-full border border-hair bg-tint">
        <div
          className={"h-full " + (pct > 0.8 ? "bg-warn" : "bg-olive")}
          style={{ width: `${Math.min(100, pct * 100)}%` }}
        />
      </div>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left font-mono uppercase tracking-wide text-ink-faint">
            <th className="py-0.5 font-normal">priority</th>
            <th className="py-0.5 text-right font-normal">daily cap</th>
            <th className="py-0.5 text-right font-normal">share</th>
          </tr>
        </thead>
        <tbody className="font-mono tabular-nums">
          {caps.map((t) => (
            <tr key={t.tier} className="border-t border-hair">
              <td className="py-0.5 text-ink">{t.tier}</td>
              <td className="py-0.5 text-right text-ink">{t.cap}</td>
              <td className="py-0.5 text-right text-ink-soft">
                {daily > 0 && t.cap !== undefined ? `${Math.round(((t.cap ?? 0) / daily) * 100)}%` : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-ink-faint">
        Spend is one shared tally — the caps are per-priority policy, not per-priority counters.
        Per-minute ceiling {budget.rpm_budget} req/min.
      </p>
    </div>
  );
}

export const BudgetPanelForTest = BudgetPanel;

/* ------------------------------------------------------------------ page */

export default function Intel() {
  const { feed, alerts, memory, budget, error } = useIntelData();
  const [selected, setSelected] = useState(0);

  return (
    <div className="space-y-8">
      {error !== null && <p className="text-sm text-warn">{error}</p>}

      <Section
        title="Alerts"
        hint="Everything either plane is currently warning about: rails that fired, validations that failed, heartbeats that went silent, a ledger and an engine that disagree. In-app only — nothing here pages anyone."
      >
        <AlertsPanel alerts={alerts} />
      </Section>

      <Section
        title="Intelligence stream"
        hint="One stream of what the agents said: wealth analysis runs beside the trading desk's insights, newest first. Filter by source, scan with the arrow keys."
      >
        <FeedPanel feed={feed} selected={selected} onSelected={setSelected} />
      </Section>

      {/* The memory and budget panels exist only when their stores do — a
          section that cannot say anything is not rendered at all, per the
          same honesty rule the endpoints follow. */}
      {memory !== null && memory.available && (
        <Section
          title="Agent memory"
          hint="The learning loop's layered memory as it is persisted: working outcomes decay in days, shallow lessons in weeks, deep reflections endure — deep lessons are what the analyst and reviewer read back."
        >
          <MemoryPanel memory={memory} />
        </Section>
      )}

      {budget !== null && budget.available && (
        <Section
          title="Request budget"
          hint="The day's LLM requests against the free-tier ceiling, per priority tier. High priority spends to the cap; the rest stand down early so the gates still have requests late in the day."
        >
          <BudgetPanel budget={budget} />
        </Section>
      )}
    </div>
  );
}
