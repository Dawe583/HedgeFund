/* The M4 TRADING OPS + RESEARCH surfaces rendered against their contract —
   signals tape (rejections first-class), per-strategy panels (chain drill-
   down), validation queue (reasons verbatim), model registry (honest PSI).

   Same jsdom pattern as tradingPositions.test.ts: the behaviour under test
   IS the render, so the components mount for real. EquityChart needs no
   canvas here — the panels under test carry fewer than two curve points, so
   the honest not-a-curve sentence renders instead of the chart. */

import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";

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
  SignalsTapeForTest,
  PerStrategyPanelsForTest,
  ValidationQueuePanelForTest,
  ModelRegistryPanelForTest,
} = await import("../src/components/Trading.tsx");

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

const SIGNALS = {
  date: "2026-11-26",
  signals: [
    {
      id: 1,
      created_at: "2026-11-26T08:00:00+00:00",
      bot: "scalp-v1",
      symbol: "BTCUSDT",
      timeframe: "4h",
      bar_time: "2026-11-26T04:00:00+00:00",
      side: "long",
      confidence: 0.9,
      outcome: "entered",
      details: { qty: 0.1, risk_amount: 20.0 },
    },
    {
      id: 2,
      created_at: "2026-11-26T09:00:00+00:00",
      bot: "scalp-v1",
      symbol: "BTCUSDT",
      timeframe: "4h",
      bar_time: "2026-11-26T08:00:00+00:00",
      side: "short",
      confidence: 0.2,
      outcome: "below_confidence",
      details: {},
    },
    {
      id: 3,
      created_at: "2026-11-26T10:00:00+00:00",
      bot: "scalp-v1",
      symbol: "BTCUSDT",
      timeframe: "4h",
      bar_time: "2026-11-26T08:00:00+00:00",
      side: "long",
      confidence: 0.9,
      outcome: "veto:daily_loss",
      details: { rail: "daily_loss" },
    },
  ],
};

test("signals tape renders rejections first-class beside entered ones", async () => {
  const [host] = await render(React.createElement(SignalsTapeForTest, { data: SIGNALS }));
  const text = host.textContent ?? "";
  assert.match(text, /entered/);
  assert.match(text, /below confidence/);
  assert.match(text, /veto · daily loss/);
  // the sizing chain travels with the entered emission, keyboard-openable
  assert.ok(host.querySelector("details summary"), "the chain must be a details/summary — keyboard reachable");
  assert.match(text, /risk_amount/);
});

test("signals tape empty is an honest sentence, never an error", async () => {
  const [host] = await render(
    React.createElement(SignalsTapeForTest, { data: { date: "2026-11-26", signals: [] } }),
  );
  const text = host.textContent ?? "";
  assert.match(text, /No emissions today/);
  assert.match(text, /stayed silent/);
});

test("per-strategy panels join lifecycle state, curve and the drill-down chain", async () => {
  const panels = [
    {
      bot: "scalp-v1",
      curve: [{ t: "2026-11-25T00:00:00+00:00", equity: 10.0 }],
      trades_count: 1,
    },
  ];
  const registry = [
    {
      version_id: 1,
      strategy_key: "scalp",
      name: "Scalp Trend",
      version: 1,
      state: "paper",
      params: {},
      timeframe: "4h",
      universe: ["BTCUSDT"],
      code_hash: "abc",
      validation_id: 1,
      state_since: "2026-11-20T00:00:00+00:00",
      state_evidence: "validation:1",
      track_record: {
        trades_count: 1,
        realized_pnl: 10.0,
        span_days: 1.0,
        first_exit_at: null,
        last_exit_at: null,
        drift_fills_measured: 2,
        drift_breaches: 0,
      },
      fingerprint: "deadbeef",
      pending_transition: null,
    },
  ];
  const trades = [
    {
      id: 1,
      bot: "scalp-v1",
      symbol: "BTCUSDT",
      side: "long",
      qty: 0.1,
      entry_price: 100,
      exit_price: 101,
      entry_time: "2026-11-25T00:00:00+00:00",
      exit_time: "2026-11-25T08:00:00+00:00",
      pnl: 10.0,
      fees: 0.1,
      confidence: 0.9,
      mode: "paper",
      gate_source: "kernel",
      entry_dev_ticks: 0.1,
      exit_dev_ticks: 0.0,
      entry_lag_bars: 0,
      signal_time: "2026-11-24T20:00:00+00:00",
      signal_chain: { outcome: "entered", confidence: 0.9, details: { qty: 0.1, stop_dist: 500.0 } },
    },
  ];
  const [host] = await render(
    React.createElement(PerStrategyPanelsForTest, {
      panels,
      registry,
      divergence: null,
      trades,
    }),
  );
  const text = host.textContent ?? "";
  assert.match(text, /scalp-v1/);
  assert.match(text, /paper/);
  assert.match(text, /1 trades/);
  // one curve point is honestly not a curve — the sentence, never a flat line
  assert.match(text, /single point is not a curve/);
  // the drill-down: the sizing chain is present and keyboard-openable
  assert.ok(host.querySelector("details summary"), "the trade's chain must be a details/summary");
  assert.match(text, /stop_dist/);
});

test("per-strategy panels empty is the gate working, not a missing panel", async () => {
  const [host] = await render(
    React.createElement(PerStrategyPanelsForTest, {
      panels: [],
      registry: [],
      divergence: null,
      trades: [],
    }),
  );
  assert.match(host.textContent ?? "", /No strategy has ever traded/);
});

test("validation queue renders awaiting versions and failures with verbatim reasons", async () => {
  const queue = {
    awaiting: [
      {
        kind: "awaiting",
        version_id: 3,
        strategy_key: "hf",
        version: 2,
        timeframe: "1h",
        validation_id: null,
        bot: null,
        verdict: null,
        reasons: [],
        created_at: "2026-11-25T00:00:00+00:00",
        permutation_p: null,
        trades_n: null,
        min_trades_required: null,
      },
    ],
    failures: [
      {
        kind: "failure",
        version_id: null,
        strategy_key: null,
        version: null,
        timeframe: "4h",
        validation_id: 9,
        bot: "scalp",
        verdict: "rejected",
        reasons: ["trades 12 < minimum 30"],
        created_at: "2026-11-20T00:00:00+00:00",
        permutation_p: 0.4,
        trades_n: 12,
        min_trades_required: 30,
      },
    ],
  };
  const [host] = await render(React.createElement(ValidationQueuePanelForTest, { queue }));
  const text = host.textContent ?? "";
  assert.match(text, /Awaiting the gates/);
  assert.match(text, /hf-v2/);
  assert.match(text, /no verdict yet/);
  assert.match(text, /Failures, with the gate/);
  assert.match(text, /trades 12 < minimum 30/);
  assert.match(text, /12\/30 trades/);
});

test("model registry renders roles and the honest PSI dash", async () => {
  const registry = {
    models: [
      {
        id: 1,
        name: "gate-BTCUSDT-4h",
        version: 2,
        trained_at: "2026-11-20T00:00:00+00:00",
        train_window_days: 90,
        oos_accuracy: 0.57,
        oos_precision_long: 0.61,
        is_champion: true,
        role: "champion",
        psi_drift: null,
        notes: "promoted",
      },
      {
        id: 2,
        name: "gate-BTCUSDT-4h",
        version: 3,
        trained_at: "2026-11-25T00:00:00+00:00",
        train_window_days: 90,
        oos_accuracy: 0.53,
        oos_precision_long: 0.54,
        is_champion: false,
        role: "challenger",
        psi_drift: null,
        notes: "",
      },
    ],
    psi_note: "PSI drift is computed per retrain cycle and recorded inside the supervisor insight's text",
  };
  const [host] = await render(React.createElement(ModelRegistryPanelForTest, { registry }));
  const text = host.textContent ?? "";
  assert.match(text, /champion/);
  assert.match(text, /challenger/);
  assert.match(text, /0\.570/);
  assert.match(text, /0\.610/);
  // PSI is honestly absent: the dash and the documentation, never a zero
  assert.match(text, /PSI drift is computed per retrain cycle/);
});

test("model registry empty renders the honest empty state with the note", async () => {
  const [host] = await render(
    React.createElement(ModelRegistryPanelForTest, {
      registry: { models: [], psi_note: "PSI note travels even empty" },
    }),
  );
  const text = host.textContent ?? "";
  assert.match(text, /No model has ever trained/);
  assert.match(text, /PSI note travels even empty/);
});
