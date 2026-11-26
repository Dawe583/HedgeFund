/* The M4 INTEL surfaces rendered against their contract — the unified
   stream (filterable, arrow-key scannable), the alerts panel (severity-first,
   honest-empty), the memory browser and the budget panel (both omitted
   entirely when their stores do not exist, per the honesty rule).

   Same jsdom pattern as tradingOps.test.ts: the behaviour under test IS the
   render, so the components mount for real. */

import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";
import type { AlertsStream } from "../src/api/intelligence.ts";

const dom = new JSDOM("<!doctype html><html><body></body></html>", {
  url: "http://localhost/",
  pretendToBeVisual: true,
});
for (const key of ["window", "document", "navigator", "HTMLElement", "CustomEvent", "getComputedStyle", "location", "requestAnimationFrame", "cancelAnimationFrame", "ResizeObserver"]) {
  const v = (dom.window as unknown as Record<string, unknown>)[key];
  if (v === undefined) continue;
  Object.defineProperty(globalThis, key, { value: v, configurable: true, writable: true });
}

const React = await import("react");
const { createRoot } = await import("react-dom/client");
const { act } = React;
const {
  FeedPanelForTest,
  AlertsPanelForTest,
  MemoryPanelForTest,
  BudgetPanelForTest,
} = await import("../src/components/Intel.tsx");
const intelFormat = await import("../src/components/intelFormat.ts");

(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;

const cleanups: (() => void)[] = [];
process.on("exit", () => {
  for (const c of cleanups) c();
});

async function render(node: React.ReactElement): Promise<[HTMLElement, () => void]> {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(node);
  });
  const cleanup = () => {
    act(() => root.unmount());
    host.remove();
  };
  cleanups.push(cleanup);
  return [host, cleanup];
}

/* ---------------------------------------------------------------- helpers */

test("the clock column is a fixed five characters, today or not", () => {
  const now = new Date("2026-11-26T12:00:00Z");
  assert.equal(intelFormat.fmtClock("2026-11-26T08:30:00Z", now), "08:30");
  assert.equal(intelFormat.fmtClock("2026-11-20T08:30:00Z", now), "NOV-20");
  assert.equal(intelFormat.fmtClock("not a date", now), "-----");
});

test("severity ordering puts critical above warning above information", () => {
  const items = [
    { severity: "info" },
    { severity: "critical" },
    { severity: "warning" },
  ] as never[];
  const sorted = intelFormat.alertsBySeverity(items);
  assert.deepEqual(sorted.map((i: { severity: string }) => i.severity), ["critical", "warning", "info"]);
});

test("wealth sources order before trading ones", () => {
  const opts = intelFormat.sourceOptions(["trading:supervisor", "wealth-chain", "trading:analyst"]);
  assert.deepEqual(opts, ["wealth-chain", "trading:analyst", "trading:supervisor"]);
});

test("the trading prefix filter catches every trading agent", () => {
  const items = [
    { source: "wealth-chain" },
    { source: "trading:supervisor" },
    { source: "trading:analyst" },
  ] as never[];
  const filtered = intelFormat.filterFeed(items, "trading");
  assert.equal(filtered.length, 2);
  assert.equal(intelFormat.filterFeed(items, null).length, 3);
});

/* ------------------------------------------------------------------- feed */

const FEED = {
  available: true,
  sources: ["wealth-chain", "trading:supervisor"],
  items: [
    {
      ts: new Date().toISOString(),
      source: "trading:supervisor",
      kind: "insight",
      title: "Desk kernel halted",
      summary: "drawdown beyond the rail",
      severity: "warning",
      ref: null,
    },
    {
      ts: "2026-11-20T10:00:00Z",
      source: "wealth-chain",
      kind: "chain-run",
      title: "Analysis run",
      summary: "4 steps, 1 revisions — contested. Hold the course.",
      severity: "info",
      ref: "/api/advisor/chain/7",
    },
  ],
};

test("the feed renders both planes' rows with their source badges", async () => {
  const [host] = await render(
    React.createElement(FeedPanelForTest, { feed: FEED, selected: 0, onSelected: () => {} }),
  );
  const text = host.textContent ?? "";
  assert.match(text, /trading:supervisor/);
  assert.match(text, /wealth-chain/);
  assert.match(text, /Desk kernel halted/);
  assert.match(text, /Analysis run/);
});

test("the empty stream is an honest sentence, never a blank table", async () => {
  const [host] = await render(
    React.createElement(FeedPanelForTest, {
      feed: { available: true, items: [], sources: [] },
      selected: 0,
      onSelected: () => {},
    }),
  );
  assert.match(host.textContent ?? "", /Nothing has been said yet/);
});

test("the source filter narrows the rows without losing the count of the rest", async () => {
  const [host] = await render(
    React.createElement(FeedPanelForTest, { feed: FEED, selected: 0, onSelected: () => {} }),
  );
  const filter = [...host.querySelectorAll("button")].find((b) => b.textContent === "wealth-chain");
  assert.ok(filter, "the filter row names the sources");
  await act(async () => {
    filter.click();
  });
  const text = host.textContent ?? "";
  assert.match(text, /Analysis run/);
  assert.ok(!text.includes("Desk kernel halted"), "the other source's rows are out");
});

test("arrow keys move the selection through the stream", async () => {
  let selected = 0;
  const onSelected = (i: number) => {
    selected = i;
  };
  const [host] = await render(
    React.createElement(FeedPanelForTest, { feed: FEED, selected, onSelected }),
  );
  const listbox = host.querySelector("[role=listbox]");
  assert.ok(listbox, "the stream is a listbox — keyboard owned");
  const down = new dom.window.KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true });
  await act(async () => {
    listbox.dispatchEvent(down);
  });
  assert.equal(selected, 1, "one arrow down is one row further");
});

/* ----------------------------------------------------------------- alerts */

const ALERTS: AlertsStream = {
  available: true,
  items: [
    {
      ts: new Date().toISOString(),
      severity: "warning",
      kind: "rail-veto",
      source: "trading",
      title: "max_positions — scalp BTCUSDT",
      detail: "3 positions open",
    },
    {
      ts: new Date().toISOString(),
      severity: "critical",
      kind: "rail-tripped",
      source: "trading",
      title: "kill_switch_drawdown — scalp",
      detail: "drawdown 13%",
    },
  ],
};

test("alerts render severity-first: the critical row is above the warning", async () => {
  const [host] = await render(React.createElement(AlertsPanelForTest, { alerts: ALERTS }));
  const text = host.textContent ?? "";
  assert.match(text, /kill_switch_drawdown/);
  assert.match(text, /max_positions/);
  assert.ok(
    text.indexOf("kill_switch_drawdown") < text.indexOf("max_positions"),
    "critical scans before warning regardless of arrival order",
  );
  assert.match(text, /critical — read those first/);
});

test("the quiet desk is an honest sentence, not an empty table", async () => {
  const [host] = await render(
    React.createElement(AlertsPanelForTest, { alerts: { available: true, items: [] } }),
  );
  assert.match(host.textContent ?? "", /Nothing is wrong/);
});

/* ----------------------------------------------------------------- memory */

const MEMORY = {
  available: true,
  working: [
    {
      id: 1, bot: "scalp", tier: "working", kind: "outcome",
      content: "BTCUSDT long closed +2.1%", importance: 0.6, pnl_pct: 0.021,
      created_at: new Date().toISOString(),
    },
  ],
  shallow: [],
  deep: [
    {
      id: 3, bot: "*", tier: "deep", kind: "reflection",
      content: "chop punishes high conviction", importance: 0.9, pnl_pct: null,
      created_at: "2026-11-15T10:00:00Z",
    },
  ],
};

test("the memory browser shows the tiers as the loop wrote them", async () => {
  const [host] = await render(React.createElement(MemoryPanelForTest, { memory: MEMORY }));
  const text = host.textContent ?? "";
  assert.match(text, /working/);
  assert.match(text, /shallow/);
  assert.match(text, /deep/);
  assert.match(text, /BTCUSDT long closed/);
  assert.match(text, /chop punishes high conviction/);
  assert.match(text, /\+2\.1%/);
  assert.match(text, /Nothing in this tier/, "the empty shallow tier says so, honestly");
});

test("no memory store means no panel at all — omission, not fake chrome", async () => {
  const [host] = await render(
    React.createElement(MemoryPanelForTest, { memory: { available: false, working: [], shallow: [], deep: [] } }),
  );
  assert.equal((host.textContent ?? "").trim(), "");
});

/* ----------------------------------------------------------------- budget */

const BUDGET = {
  available: true,
  day: "2026-11-26",
  used: 12,
  daily_budget: 45,
  remaining: 33,
  rpm_budget: 15,
  tier_caps: [
    { tier: "high", cap: 45 },
    { tier: "normal", cap: 36 },
    { tier: "low", cap: 22 },
  ],
};

test("the budget panel reports the day against the tier caps", async () => {
  const [host] = await render(React.createElement(BudgetPanelForTest, { budget: BUDGET }));
  const text = host.textContent ?? "";
  assert.match(text, /12 \/ 45/);
  assert.match(text, /high/);
  assert.match(text, /normal/);
  assert.match(text, /low/);
  // honesty line: the spend is one shared tally, never per-tier invention
  assert.match(text, /one shared tally/);
});

test("no counter file means no panel — a zero would claim the day started", async () => {
  const [host] = await render(
    React.createElement(BudgetPanelForTest, {
      budget: { available: false, day: null, used: 0, daily_budget: 0, remaining: 0, rpm_budget: 0, tier_caps: [] },
    }),
  );
  assert.equal((host.textContent ?? "").trim(), "");
});
