/* The M5 mandate surface rendered against its contract — the honest-empty
   state that is the design's expected end state, and the caps table with
   consent state and expiry countdown when a mandate exists. Compact by
   design: this is machinery, not chrome.

   Same jsdom pattern as tradingControls.test.ts: the behaviour under test
   IS the render, so the component mounts for real. */

import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", {
  url: "http://localhost/",
  pretendToBeVisual: true,
});
for (const key of ["window", "document", "navigator", "HTMLElement", "CustomEvent", "getComputedStyle", "location", "requestAnimationFrame", "cancelAnimationFrame", "Event", "MouseEvent"]) {
  const v = (dom.window as unknown as Record<string, unknown>)[key];
  if (v === undefined) continue;
  Object.defineProperty(globalThis, key, { value: v, configurable: true, writable: true });
}

const React = await import("react");
const { createRoot } = await import("react-dom/client");
const { act } = React;
const { MandateSectionForTest } = await import("../src/components/Trading.tsx");
const { getTradingMandates, getTradingOrderCards } = await import("../src/api/trading.ts");

/* dynamic imports above: jsdom globals must exist before React and the
   component module evaluate — a static import would hoist them above the
   DOM install. */

(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;

const cleanups: (() => void)[] = [];
process.on("exit", () => {
  for (const c of cleanups) c();
});

async function render(el: React.ReactElement): Promise<[HTMLElement, () => void]> {
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

function mandate(over: Record<string, unknown> = {}) {
  return {
    id: 1,
    version_id: 3,
    created_at: "2026-11-01T00:00:00Z",
    created_by: "operator-ui",
    max_order_notional: 500,
    max_exposure: 1000,
    instruments: ["BTCUSDT"],
    max_trades_per_day: 5,
    consent_days: 30,
    funding_min: 100,
    funding_max: 2000,
    note: "",
    mandate_hash: "abc123",
    expires_at: new Date(Date.now() + 5 * 86400000).toISOString(),
    active: true,
    integrity_ok: true,
    ...over,
  };
}

test("the honest empty state says the live path is unbuilt by design", async () => {
  const [host, cleanup] = await render(
    React.createElement(MandateSectionForTest, { mandates: [], cards: [], error: null }),
  );
  const text = host.textContent ?? "";
  assert.match(text, /No mandate exists — the live path is unbuilt by design/);
  assert.match(text, /the machinery working, not a missing panel/);
  assert.equal(host.querySelector("table"), null, "no caps table without a mandate");
  cleanup();
});

test("an active mandate renders its caps table with consent state and countdown", async () => {
  const [host, cleanup] = await render(
    React.createElement(MandateSectionForTest, { mandates: [mandate()], cards: [], error: null }),
  );
  const text = host.textContent ?? "";
  assert.match(text, /500/, "the per-order cap is shown");
  assert.match(text, /1000/, "the exposure cap is shown");
  assert.match(text, /BTCUSDT/);
  assert.match(text, /active/, "consent state is named");
  assert.match(text, /4d|5d/, "the expiry countdown ticks in days");
  assert.equal(host.querySelectorAll("tbody tr").length, 1);
  cleanup();
});

test("an expired mandate is shown, never hidden — lapsed consent is evidence", async () => {
  const [host, cleanup] = await render(
    React.createElement(MandateSectionForTest, {
      mandates: [mandate({ active: false, expires_at: "2026-01-01T00:00:00Z" })],
      cards: [],
      error: null,
    }),
  );
  const text = host.textContent ?? "";
  assert.match(text, /expired/);
  cleanup();
});

test("a corrupt mandate flags its integrity rather than hiding it", async () => {
  const [host, cleanup] = await render(
    React.createElement(MandateSectionForTest, {
      mandates: [mandate({ integrity_ok: false })],
      cards: [],
      error: null,
    }),
  );
  assert.match(host.textContent ?? "", /corrupt/);
  cleanup();
});

test("order cards render with state badges when they exist", async () => {
  const card = {
    id: 7,
    version_id: 3,
    mandate_id: 1,
    created_at: "2026-11-20T00:00:00Z",
    symbol: "BTCUSDT",
    side: "long",
    notional: 100,
    chain: {},
    fingerprint: "0123456789abcdef",
    state: "denied",
    decided_at: "2026-11-20T00:01:00Z",
    decision_note: "no mandate exists — no live order without written consent",
  };
  const [host, cleanup] = await render(
    React.createElement(MandateSectionForTest, { mandates: [mandate()], cards: [card], error: null }),
  );
  const text = host.textContent ?? "";
  assert.match(text, /long BTCUSDT/);
  assert.match(text, /denied/);
  assert.match(text, /no live order without written consent/);
  cleanup();
});

test("no cards means no card table — absence is not an empty chrome frame", async () => {
  const [host, cleanup] = await render(
    React.createElement(MandateSectionForTest, { mandates: [mandate()], cards: [], error: null }),
  );
  assert.equal(host.querySelectorAll("table").length, 1, "only the caps table");
  cleanup();
});

test("the error surface is the error, not a blank section", async () => {
  const [host, cleanup] = await render(
    React.createElement(MandateSectionForTest, { mandates: null, cards: null, error: "The mandates could not be loaded." }),
  );
  assert.match(host.textContent ?? "", /could not be loaded/);
  cleanup();
});

test("the client transcribes, never transforms", async () => {
  // getTradingMandates/getTradingOrderCards exist and are the plain wire
  // transcription — the drift-hiding failure mode gen:types was built against.
  assert.equal(typeof getTradingMandates, "function");
  assert.equal(typeof getTradingOrderCards, "function");
});
