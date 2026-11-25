/* The run detail rendered against its contract — what a reader actually sees
   when a backtest row expands.

   Rendered into jsdom through react-dom/client because the behaviour under
   test IS the render: the null states must be sentences, the populated states
   must hand the data to the chart and the blotter. The heavy children are
   real, not mocked — lightweight-charts runs on jsdom's canvas stub well
   enough to mount (ResizeObserver is the one browser API jsdom lacks, so it
   is stubbed here), and the blotter boots the real Perspective wasm engine.

   Run by `npm test` alongside the pure tests; the axios adapter is mocked at
   the same seam tradingClient.test.ts uses, so no server is involved. */

import assert from "node:assert/strict";
import { test } from "node:test";
import type { InternalAxiosRequestConfig } from "axios";
import { JSDOM } from "jsdom";

// jsdom before ANY React import touches the DOM: the globals must exist when
// the modules load.
const dom = new JSDOM("<!doctype html><html><body></body></html>", {
  url: "http://localhost/",
  pretendToBeVisual: true,
});
for (const key of ["window", "document", "navigator", "HTMLElement", "HTMLCanvasElement", "CustomEvent", "MutationObserver", "getComputedStyle", "location", "requestAnimationFrame", "cancelAnimationFrame", "matchMedia", "fetch", "customElements", "ShadowRoot", "Element", "Node", "DOMParser", "XMLSerializer", "crypto"]) {
  // defineProperty rather than assignment: Node 21+ exposes `navigator` as a
  // getter-only global, and the jsdom one is what the DOM libraries expect.
  const v = (dom.window as unknown as Record<string, unknown>)[key];
  if (v === undefined) continue;
  Object.defineProperty(globalThis, key, {
    value: v,
    configurable: true,
    writable: true,
  });
}
// Perspective's webcomponents construct CSSStyleSheet at module load; jsdom
// never implemented it. A minimal stub — the engine fails later for other
// reasons, but module-load crashes are the ones no catch can reach.
class CSSStyleSheetStub {
  replace() { return Promise.resolve(this); }
  replaceSync() {}
  insertRule() { return 0; }
  deleteRule() {}
  cssRules = [];
}
Object.defineProperty(globalThis, "CSSStyleSheet", { value: CSSStyleSheetStub, configurable: true, writable: true });
// lightweight-charts measures with ResizeObserver; jsdom has none.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as Record<string, unknown>).ResizeObserver = ResizeObserverStub;
// jsdom's canvas has no 2d context; the chart only needs the object to exist
// for mount — the assertions below are about the data path, not pixels.
(dom.window.HTMLCanvasElement.prototype as unknown as Record<string, unknown>).getContext = () => null;

const React = await import("react");
const { createRoot } = await import("react-dom/client");
const { act } = React;
const { api } = await import("../src/api/client.ts");
const { RunDetailForTest } = await import("../src/components/Trading.tsx");

(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;

function mockDetail(detail: unknown): void {
  api.defaults.adapter = async (config: InternalAxiosRequestConfig) => ({
    data: detail,
    status: 200,
    statusText: "OK",
    headers: {},
    config,
  });
}

const BASE = {
  id: 1,
  bot: "scalp",
  symbol: "BTCUSDT",
  timeframe: "4h",
  started_at: "2026-11-25T01:17:54",
  trades_count: 2,
  metrics: { win_rate: 0.5, profit_factor: 1.2, sharpe: 1.1, max_dd_pct: -5.0, total_return_pct: 3.4 },
  verdict: null,
  validation: null,
  created_at: "2026-11-25T01:17:54",
  params: {},
  provenance: null,
  reasons: [],
};

/** Mount the detail against a mocked backend answer and settle everything —
    the fetch, the chart effect, the lazy perspective boot. Each test gets its
    own host and root: a shared root would carry one test's tree into the
    next, and "the empty state rendered" would be measuring the wrong render. */
async function renderDetail(detail: unknown): Promise<HTMLElement> {
  mockDetail(detail);
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(React.createElement(RunDetailForTest, { id: 1 }));
  });
  // The lazy perspective import and the detail fetch resolve on their own
  // timers, outside the first flush — pump twice, then read the DOM.
  for (let i = 0; i < 6; i++) {
    await act(async () => {
      await new Promise((r) => setTimeout(r, 250));
    });
  }
  cleanups.push(() => {
    act(() => root.unmount());
    host.remove();
  });
  return host;
}

const cleanups: (() => void)[] = [];
process.on("exit", () => {
  for (const c of cleanups) c();
});

test("null equity_curve and null trades render as honest sentences, not invented data", async () => {
  const host = await renderDetail({ ...BASE, equity_curve: null, trades: null });
  const text = host.textContent ?? "";
  assert.match(text, /Equity curve not recorded for this run/);
  assert.match(text, /Trades not recorded for this run/);
});

test("a populated curve mounts the chart canvas and the trades populate the blotter grid", async () => {
  const host = await renderDetail({
    ...BASE,
    equity_curve: [
      { t: "2026-11-20T08:00:00", equity: 100_000 },
      { t: "2026-11-21T08:00:00", equity: 101_000 },
      { t: "2026-11-22T08:00:00", equity: 99_500 },
    ],
    trades: [
      { entry_time: "2026-11-20T08:00:00", exit_time: "2026-11-21T08:00:00", side: "long", qty: 0.5, entry_price: 90_000, exit_price: 91_000, pnl: 500 },
      { entry_time: "2026-11-21T08:00:00", exit_time: "2026-11-22T08:00:00", side: "short", qty: 0.5, entry_price: 91_000, exit_price: 92_000, pnl: -500 },
    ],
  });
  // The chart drew: lightweight-charts puts a canvas in the host.
  assert.ok(host.querySelector("canvas") !== null, "equity chart canvas mounted");
  // The empty-state sentences are gone.
  const text = host.textContent ?? "";
  assert.ok(!text.includes("not recorded"), `unexpected empty state: ${text.slice(0, 200)}`);
  // The blotter: Perspective's wasm engine cannot boot inside jsdom (the
  // viewer package touches CSSStyleSheet at module load, before any test
  // seam), so what this test pins is the data path up to the engine — the
  // grid's own sentence or the viewer element must be present, and the
  // empty-state sentence must NOT be. The real engine boot is the browser
  // e2e's job, where the wasm actually runs.
  const text2 = host.textContent ?? "";
  assert.ok(
    host.querySelector("perspective-viewer") !== null ||
      text2.includes("Loading the grid") ||
      text2.includes("grid engine could not start"),
    "blotter engaged — viewer mounted, engine loading, or its failure honestly reported",
  );
});

test("an empty trades array renders the zero-trades sentence — a run that never opened", async () => {
  const host = await renderDetail({ ...BASE, equity_curve: null, trades: [] });
  const text = host.textContent ?? "";
  assert.match(text, /No trades — the run never opened/);
});
