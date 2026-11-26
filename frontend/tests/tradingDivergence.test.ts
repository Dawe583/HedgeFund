/* The slice-5 divergence surfaces rendered against their contract — the
   DivergenceStrip's honest states, the blotter's dev column coloring only
   on budget breach, and the veto tape's presence in the rails strip.

   Same jsdom pattern as tradingPositions.test.ts: the behaviour under test
   IS the render, so the components mount for real. */

import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", {
  url: "http://localhost/",
  pretendToBeVisual: true,
});
for (const key of ["window", "document", "navigator", "HTMLElement", "CustomEvent", "getComputedStyle", "location", "requestAnimationFrame", "cancelAnimationFrame"]) {
  const v = (dom.window as unknown as Record<string, unknown>)[key];
  if (v === undefined) continue;
  Object.defineProperty(globalThis, key, { value: v, configurable: true, writable: true });
}

const React = await import("react");
const { createRoot } = await import("react-dom/client");
const { act } = React;
const { DivergenceStripForTest, PositionsBlotterForTest, RailsStripForTest } =
  await import("../src/components/Trading.tsx");
const { fmtTicks, divergenceBudgetsOf } = await import("../src/components/tradingStatus.ts");

(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;

const cleanups: (() => void)[] = [];
process.on("exit", () => {
  for (const c of cleanups) c();
});

async function render(
  el: React.ReactElement,
): Promise<[HTMLElement, () => void]> {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(el);
  });
  let released = false;
  const cleanup = () => {
    if (released) return;
    released = true;
    root.unmount();
    host.remove();
  };
  cleanups.push(cleanup);
  return [host, cleanup];
}

/* ---- fmtTicks, the pure readout ----------------------------------------- */

test("fmtTicks: sign kept, null is a dash never a zero", () => {
  assert.equal(fmtTicks(null), "—");
  assert.equal(fmtTicks(undefined), "—");
  assert.equal(fmtTicks(0), "0.0");
  assert.equal(fmtTicks(0.04), "0.0"); // sub-quantization noise rounds to zero
  assert.equal(fmtTicks(1.5), "+1.5");
  assert.equal(fmtTicks(-2.3), "-2.3");
});

test("divergenceBudgetsOf: only bots with a declared budget enter the map", () => {
  const div = {
    bots: [
      { bot: "a", budget_dev_ticks: 2.0 },
      { bot: "b", budget_dev_ticks: null },
    ],
    breach_events: [],
  } as never;
  const map = divergenceBudgetsOf(div);
  assert.equal(map.get("a"), 2.0);
  assert.equal(map.has("b"), false, "an unknown budget is never a zero budget");
  assert.equal(divergenceBudgetsOf(null).size, 0);
});

/* ---- the divergence strip ------------------------------------------------ */

const BOT_ROW = {
  bot: "scalp",
  budget_dev_ticks: 2.0,
  budget_entry_lag_bars: 0,
  budget_missed_bars: 0,
  missed_bars: 0,
  backfilled_bars: 3,
  open_positions: [],
  fills: {
    measured_fills: 12,
    mean_abs_dev_ticks: 0.2,
    max_abs_dev_ticks: 0.5,
    max_entry_lag_bars: 0,
    breaches: 0,
  },
  distribution: null,
  distribution_note: "insufficient data for a distributional comparison (backtest 0 trades, paper 6 — the statistical bar is 30 per side, the same the validation gate sets)",
};

test("DivergenceStrip: null render when nothing exists", async () => {
  const [host, cleanup] = await render(
    React.createElement(DivergenceStripForTest, {
      divergence: { bots: [], breach_events: [] },
    }),
  );
  assert.equal(host.textContent, "");
  cleanup();
});

test("DivergenceStrip: in-budget bot reads mono, distribution honestly insufficient", async () => {
  const [host, cleanup] = await render(
    React.createElement(DivergenceStripForTest, {
      divergence: { bots: [BOT_ROW], breach_events: [] },
    }),
  );
  const text = host.textContent ?? "";
  assert.ok(text.includes("scalp"), "bot row renders");
  assert.ok(text.includes("+0.5"), "max dev in ticks");
  assert.ok(text.includes("±2"), "budget beside it");
  assert.ok(text.includes("n<30"), "distributional insufficiency reads as text, never fake stats");
  assert.ok(!text.includes("OUTSIDE"), "no distribution means no positioning claim");
  // in-budget: nothing may carry the breach color
  assert.equal(host.querySelectorAll(".text-down").length, 0, "in-budget figures are mono ink");
  cleanup();
});

test("DivergenceStrip: breaching max dev colors red", async () => {
  const breaching = {
    ...BOT_ROW,
    fills: { ...BOT_ROW.fills, max_abs_dev_ticks: 3.5, breaches: 2 },
  };
  const [host, cleanup] = await render(
    React.createElement(DivergenceStripForTest, {
      divergence: {
        bots: [breaching],
        breach_events: [
          {
            id: 9,
            created_at: "2026-11-26T10:00:00+00:00",
            bot: "scalp",
            symbol: "BTCUSDT",
            rail: "divergence_budget",
            decision: "breached",
            inputs: { dimensions: ["dev_ticks"], fill_kind: "entry", dev_ticks: 3.5 },
          },
        ],
      },
    }),
  );
  assert.ok(host.querySelectorAll(".text-down").length > 0, "a breach colors red — visible, never silent");
  const text = host.textContent ?? "";
  assert.ok(text.includes("Budget breaches"), "the breach tape renders");
  assert.ok(text.includes("dev_ticks"), "the breached dimension is named");
  cleanup();
});

test("DivergenceStrip: distribution present shows the positioning", async () => {
  const withDist = {
    ...BOT_ROW,
    distribution: {
      bt_trades: 40,
      paper_trades: 32,
      bt_mean_pnl: 12.5,
      paper_mean_pnl: -4.0,
      bt_median_pnl: 10.0,
      paper_mean_within_bt_p5_p95: false,
      bt_p5: -20.0,
      bt_p95: 60.0,
    },
    distribution_note: "",
  };
  const [host, cleanup] = await render(
    React.createElement(DivergenceStripForTest, {
      divergence: { bots: [withDist], breach_events: [] },
    }),
  );
  const text = host.textContent ?? "";
  assert.ok(text.includes("OUTSIDE"), "paper mean outside the backtest band reads as what it is");
  assert.ok(text.includes("12.50"), "both means render side by side");
  cleanup();
});

/* ---- the blotter's dev column -------------------------------------------- */

const POSITION = {
  id: 7,
  bot: "scalp",
  symbol: "BTCUSDT",
  side: "long",
  qty: 0.05,
  entry_price: 91000,
  stop_loss: 89500,
  take_profit: 93500,
  opened_at: "2026-11-26T08:00:00+00:00",
  age_seconds: 305,
  confidence: 0.62,
  signal_time: "2026-11-26T07:55:00+00:00",
  gate_source: "kernel",
  entry_dev_ticks: 0.3,
  entry_ref_price: 90999.9,
  entry_lag_bars: 0,
};

test("blotter dev column: in-budget mono, breaching red, unmeasured a dash", async () => {
  const budgets = new Map([["scalp", 2.0]]);
  // in budget: no red anywhere
  const [host1, cleanup1] = await render(
    React.createElement(PositionsBlotterForTest, {
      positions: [POSITION],
      fetchedAt: Date.now(),
      budgets,
    }),
  );
  assert.ok((host1.textContent ?? "").includes("+0.3"), "the entry drift renders in ticks");
  assert.equal(host1.querySelectorAll(".text-down").length, 1, "only the stop column reads red — drift does not");
  cleanup1();

  // breaching: the dev cell goes red
  const [host2, cleanup2] = await render(
    React.createElement(PositionsBlotterForTest, {
      positions: [{ ...POSITION, entry_dev_ticks: 4.5 }],
      fetchedAt: Date.now(),
      budgets,
    }),
  );
  assert.equal(host2.querySelectorAll(".text-down").length, 2, "the breaching dev joins the stop column in red");
  cleanup2();

  // unmeasured: a dash, never a zero
  const [host3, cleanup3] = await render(
    React.createElement(PositionsBlotterForTest, {
      positions: [{ ...POSITION, entry_dev_ticks: null, entry_ref_price: null, entry_lag_bars: null }],
      fetchedAt: Date.now(),
      budgets,
    }),
  );
  assert.ok((host3.textContent ?? "").includes("—"), "unmeasured reads as a dash");
  assert.equal(host3.querySelectorAll(".text-down").length, 1, "a dash never colors");
  cleanup3();
});

/* ---- today's vetoes in the rails strip ------------------------------------ */

const RAILS = {
  manual_killswitch: false,
  manual_killswitch_note: "",
  halt_sentinel: false,
  halt_sentinel_path: "/tmp/x/HALT",
  bots: [],
  recent_events: [],
  vetoes_today: [
    {
      id: 4,
      created_at: "2026-11-26T09:30:00+00:00",
      bot: "scalp",
      symbol: "BTCUSDT",
      rail: "symbol_exposure_cap",
      decision: "veto",
      inputs: { notional: 1200, reason: "symbol cap" },
    },
  ],
};

test("rails strip: today's veto tape renders time, rail and reason", async () => {
  const [host, cleanup] = await render(React.createElement(RailsStripForTest, { rails: RAILS }));
  const text = host.textContent ?? "";
  assert.ok(text.includes("Today's vetoes"), "the tape is labeled");
  assert.ok(text.includes("symbol_exposure_cap"), "the refusing rail is named");
  assert.ok(text.includes("symbol cap"), "the reason renders");
  cleanup();
});

test("rails strip: a day without vetoes says so rather than disappearing", async () => {
  const [host, cleanup] = await render(
    React.createElement(RailsStripForTest, { rails: { ...RAILS, vetoes_today: [] } }),
  );
  const text = host.textContent ?? "";
  assert.ok(text.includes("never tested today"), "the empty tape is information too");
  cleanup();
});
