/* The positions blotter rendered against its contract — the three honest
   states (no engine / engine flat / positions open) and the ticking age.

   Same jsdom pattern as tradingDetail.test.ts: the behaviour under test IS
   the render, so the component mounts for real. The blotter has no heavy
   children (no Perspective, no chart) — it's a plain dense table — so this
   test reads exactly what a reader sees. */

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
const { PositionsSectionForTest, fmtAge } = await import("../src/components/Trading.tsx");

(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;

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
  entry_dev_ticks: 0.1,
  entry_ref_price: 90999.9,
  entry_lag_bars: 0,
};

const TRADE = {
  id: 3,
  bot: "scalp",
  symbol: "BTCUSDT",
  side: "short",
  qty: 0.05,
  entry_price: 93000,
  exit_price: 92000,
  entry_time: "2026-11-25T20:00:00+00:00",
  exit_time: "2026-11-26T02:00:00+00:00",
  pnl: 50.0,
  fees: 1.5,
  confidence: 0.4,
  mode: "paper",
  gate_source: "kernel",
  entry_dev_ticks: 0.0,
  exit_dev_ticks: -0.2,
  entry_lag_bars: 0,
};

const cleanups: (() => void)[] = [];
process.on("exit", () => {
  for (const c of cleanups) c();
});

async function renderSection(
  props: Parameters<typeof PositionsSectionForTest>[0],
): Promise<[HTMLElement, () => void]> {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(React.createElement(PositionsSectionForTest, props));
  });
  // The blotter ticks on an interval — a component left mounted keeps the
  // event loop (and the test process) alive forever, so the caller unmounts
  // the moment its assertions are done. cleanup-at-exit stays as backstop.
  let released = false;
  const release = () => {
    if (released) return;
    released = true;
    act(() => root.unmount());
    host.remove();
  };
  cleanups.push(release);
  return [host, release];
}

test("fmtAge reads mm:ss under the hour, hh:mm under the day, days after", () => {
  assert.equal(fmtAge(305), "5:05");
  assert.equal(fmtAge(0), "0:00");
  assert.equal(fmtAge(3661), "1:01h");
  assert.equal(fmtAge(90000), "1d 1h");
});

test("no engine, no positions: the empty state is a sentence, not a blank table", async () => {
  const [host, release] = await renderSection({
    positions: [], trades: [], fetchedAt: Date.now(), engineState: "offline", error: null,
  });
  const text = host.textContent ?? "";
  assert.match(text, /No positions — the engine has not run/);
  assert.match(text, /nothing shown is better than something invented/);
  assert.equal(host.querySelector("table"), null);
  release();
});

test("engine running and flat: flat is the zero position, said in words", async () => {
  const [host, release] = await renderSection({
    positions: [], trades: [], fetchedAt: Date.now(), engineState: "running", error: null,
  });
  const text = host.textContent ?? "";
  assert.match(text, /Flat — no open positions/);
  assert.match(text, /The engine is running and holds nothing/);
  release();
});

test("an open position renders its row: side direction, levels, ticking age, confidence", async () => {
  const [host, release] = await renderSection({
    positions: [POSITION], trades: [], fetchedAt: Date.now(), engineState: "running", error: null,
  });
  const text = host.textContent ?? "";
  assert.match(text, /BTCUSDT/);
  assert.match(text, /▲ long/);
  assert.match(text, /91000/);
  assert.match(text, /89500/);
  assert.match(text, /93500/);
  assert.match(text, /0\.62/);
  // the age at mount: 305s ticks forward by the render's own seconds — 5:xx
  assert.match(text, /5:0\d/);
  // the row is keyboard-focusable (the global css reverse-video focus hooks tr:focus)
  const row = host.querySelector("tbody tr");
  assert.ok(row !== null);
  assert.equal((row as HTMLElement).tabIndex, 0);
  release();
});

test("settled round-trips render as the evidence strip beneath", async () => {
  const [host, release] = await renderSection({
    positions: [POSITION], trades: [TRADE], fetchedAt: Date.now(), engineState: "running", error: null,
  });
  const text = host.textContent ?? "";
  assert.match(text, /Recently settled/);
  assert.match(text, /\+50\.00/);
  assert.match(text, /93000 → 92000/);
  release();
});

test("the error state is the error, never a silent empty", async () => {
  const [host, release] = await renderSection({
    positions: null, trades: null, fetchedAt: 0, engineState: null, error: "The positions could not be loaded.",
  });
  assert.match(host.textContent ?? "", /could not be loaded/);
  release();
});
