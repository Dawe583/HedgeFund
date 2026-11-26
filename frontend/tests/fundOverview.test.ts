/* The fund overview rendered against its contract: engine equity BESIDE the
   ledger and never summed, the reconciliation gap with its dates, and every
   empty state first-class — no engine, no mapping, no statement, no rate.

   Same jsdom pattern as tradingControls.test.ts: the behaviour under test IS
   the render, so the component mounts for real on a given payload, and the
   fetch never enters the test. */

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

/* Dynamic imports, deliberately: react-dom binds to whatever `document` exists
   at the moment it is first evaluated, so the jsdom globals above must be in
   place before the module loads — the load ORDER is the point, which a static
   import cannot express (the same seam tradingControls.test.ts uses). */
const React = await import("react");
const { createRoot } = await import("react-dom/client");
const { act } = React;
const { FundOverviewRows } = await import("../src/components/FundOverview.tsx");
const { reconciliationReading, engineStamp, gapDirection, NO_DESK_EQUITY } = await import("../src/components/reconciliation.ts");
import type { OverviewFund, OverviewReconciliation } from "../src/api/overview.ts";

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

function recon(over: Partial<OverviewReconciliation> = {}): OverviewReconciliation {
  return {
    institution_id: null,
    institution_name: null,
    statement_positions: null,
    statement_cash: null,
    statement_total: null,
    statement_date: null,
    engine_equity_base: null,
    engine_as_of: null,
    gap: null,
    missing: [],
    ...over,
  };
}

function overview(over: {
  equity?: Partial<OverviewFund["trading_equity"]>;
  reconciliation?: Partial<OverviewReconciliation>;
} = {}): OverviewFund {
  return {
    total_wealth: { base_currency: "EUR" } as OverviewFund["total_wealth"],
    trading_equity: {
      available: false,
      value: null,
      value_base: null,
      currency: "USD",
      as_of: null,
      source: "equity_points",
      ...over.equity,
    },
    reconciliation: recon(over.reconciliation),
  };
}

/* ---- the component, per state -------------------------------------------- */

test("a measured gap renders with its dates and its sign", async () => {
  const [host, cleanup] = await render(
    React.createElement(FundOverviewRows, {
      overview: overview({
        equity: { available: true, value: 1200, value_base: 600, as_of: "2026-11-26T00:19:00" },
        reconciliation: recon({
          institution_id: 1,
          institution_name: "BitDesk",
          statement_positions: 1000,
          statement_cash: 500,
          statement_total: 1500,
          statement_date: "2026-11-20",
          engine_equity_base: 600,
          engine_as_of: "2026-11-26T00:19:00",
          gap: 900,
        }),
      }),
    }),
  );
  const text = host.textContent ?? "";
  assert.match(text, /never part of net worth/, "the never-summed rule is stated beside the figures");
  assert.match(text, /engine-reported/i);
  assert.match(text, /Reconciliation/);
  assert.match(text, /BitDesk/);
  assert.match(text, /2026-11-20/, "the statement's own date renders with the gap");
  assert.match(text, /the ledger reads more than the engine/);
  cleanup();
});

test("no engine equity is a first-class sentence, not a zero", async () => {
  const [host, cleanup] = await render(
    React.createElement(FundOverviewRows, { overview: overview() }),
  );
  const text = host.textContent ?? "";
  assert.match(text, /no desk equity recorded — the engine is offline or never ran/);
  assert.doesNotMatch(text, /\$0|0\.00\s*USD/, "nothing invents a zero equity");
  cleanup();
});

test("no mapping explains what the reconciliation cannot read", async () => {
  const [host, cleanup] = await render(
    React.createElement(FundOverviewRows, {
      overview: overview({
        equity: { available: true, value: 100, value_base: 50, as_of: "2026-11-26T00:19:00" },
        reconciliation: recon({ missing: ["no-mapping"] }),
      }),
    }),
  );
  assert.match(host.textContent ?? "", /no ledger account is declared as the trading account/);
  cleanup();
});

test("several missing pieces read as one list", async () => {
  const [host, cleanup] = await render(
    React.createElement(FundOverviewRows, {
      overview: overview({
        reconciliation: recon({ missing: ["no-mapping", "no-engine-equity"] }),
      }),
    }),
  );
  const text = host.textContent ?? "";
  assert.match(text, /no ledger account is declared/);
  assert.match(text, /; and /);
  assert.match(text, /engine is offline or never ran/);
  cleanup();
});

test("an unconvertible engine figure is said, never read as euro", async () => {
  const [host, cleanup] = await render(
    React.createElement(FundOverviewRows, {
      overview: overview({
        equity: { available: true, value: 1200, value_base: null, as_of: "2026-11-26T00:19:00" },
        reconciliation: recon({ missing: ["equity-unconvertible"] }),
      }),
    }),
  );
  const text = host.textContent ?? "";
  assert.match(text, /no rate converts the engine's dollars/);
  // The dollar figure still renders in dollars — the conversion failing never hides the engine's own number.
  assert.match(text, /1.*200/);
  assert.doesNotMatch(text, /≈/, "no converted figure appears when none exists");
  cleanup();
});

test("a converted figure renders beside the engine's own unit", async () => {
  const [host, cleanup] = await render(
    React.createElement(FundOverviewRows, {
      overview: overview({
        equity: { available: true, value: 1100, value_base: 550, as_of: "2026-11-26T00:19:00" },
        reconciliation: recon({ missing: ["no-mapping"] }),
      }),
    }),
  );
  assert.match(host.textContent ?? "", /≈/);
  cleanup();
});

test("an engine-ahead gap reads its own direction", async () => {
  const [host, cleanup] = await render(
    React.createElement(FundOverviewRows, {
      overview: overview({
        equity: { available: true, value: 2000, value_base: 1000, as_of: "2026-11-26T00:19:00" },
        reconciliation: recon({
          institution_name: "BitDesk",
          statement_total: 500,
          statement_date: "2026-11-20",
          engine_equity_base: 1000,
          engine_as_of: "2026-11-26T00:19:00",
          gap: -500,
        }),
      }),
    }),
  );
  assert.match(host.textContent ?? "", /the engine reads more than the ledger/);
  cleanup();
});

test("the declaration control appears exactly when the mapping is the missing piece", async () => {
  const accounts = [{ id: 7, name: "BitDesk" }];
  const [host, cleanup] = await render(
    React.createElement(FundOverviewRows, {
      overview: overview({ reconciliation: recon({ missing: ["no-mapping"] }) }),
      institutions: accounts,
      onDeclare: () => {},
    }),
  );
  assert.match(host.textContent ?? "", /which account is the trading desk\?/);
  const declare = [...host.querySelectorAll("button")].find((b) => b.textContent === "Declare") as HTMLButtonElement;
  assert.ok(declare);
  assert.equal(declare.disabled, true, "nothing is declared until an account is chosen");
  cleanup();
});

test("declaring sends the chosen account's id", async () => {
  let sent: number | null = null;
  const [host, cleanup] = await render(
    React.createElement(FundOverviewRows, {
      overview: overview({ reconciliation: recon({ missing: ["no-mapping"] }) }),
      institutions: [
        { id: 7, name: "BitDesk" },
        { id: 9, name: "Other bank" },
      ],
      onDeclare: (id: number) => {
        sent = id;
      },
    }),
  );
  const select = host.querySelector("select") as HTMLSelectElement;
  await act(async () => {
    select.value = "9";
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
  const declare = [...host.querySelectorAll("button")].find((b) => b.textContent === "Declare") as HTMLButtonElement;
  assert.equal(declare.disabled, false);
  await act(async () => {
    declare.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  assert.equal(sent, 9);
  cleanup();
});

test("a measured reconciliation offers no control — nothing is missing", async () => {
  const [host, cleanup] = await render(
    React.createElement(FundOverviewRows, {
      overview: overview({
        equity: { available: true, value: 100, value_base: 50, as_of: "2026-11-26T00:19:00" },
        reconciliation: recon({
          institution_name: "BitDesk",
          statement_total: 50,
          statement_date: "2026-11-20",
          engine_equity_base: 50,
          engine_as_of: "2026-11-26T00:19:00",
          gap: 0,
        }),
      }),
      institutions: [{ id: 7, name: "BitDesk" }],
      onDeclare: () => {},
    }),
  );
  assert.equal(host.querySelector("select"), null);
  cleanup();
});

/* ---- the logic, pinned without a DOM where it can be --------------------- */

test("an empty missing list is the measured state", () => {
  assert.equal(reconciliationReading(recon()).kind, "measured");
});

test("an unknown missing code never renders blank", () => {
  const reading = reconciliationReading(recon({ missing: ["something-new"] }));
  assert.equal(reading.kind, "absent");
  if (reading.kind === "absent") assert.match(reading.line, /something-new/);
});

test("the engine's timestamp renders in UTC and says so", () => {
  assert.equal(engineStamp("2026-11-26T00:19:00"), "2026-11-26 00:19Z");
});

test("the gap direction reads zero as even and the sign as the side", () => {
  assert.equal(gapDirection(0), "even");
  assert.equal(gapDirection(0.001), "even");
  assert.equal(gapDirection(500), "ledger-ahead");
  assert.equal(gapDirection(-500), "engine-ahead");
});

test("the no-equity sentence is the design's own words", () => {
  assert.match(NO_DESK_EQUITY, /offline or never ran/);
});
