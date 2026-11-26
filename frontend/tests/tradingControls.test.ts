/* The M4 control surfaces rendered against their contract — the kill-switch
   control's asymmetric directions and the lifecycle registry's honest states,
   including the approval card and its fingerprint display.

   Same jsdom pattern as tradingPositions.test.ts: the behaviour under test
   IS the render, so the components mount for real. The writes are mocked at
   the axios adapter — the one seam axios itself offers — so an interaction
   test pins what the control SENDS, never a fake backend. */

import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";
import { AxiosError, AxiosHeaders, type InternalAxiosRequestConfig } from "axios";

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
const { KillSwitchControlForTest, RegistrySectionForTest, ApprovalCardForTest } =
  await import("../src/components/Trading.tsx");
const { api } = await import("../src/api/client.ts");
const { setKillSwitch, approveVersion, isConflict, getTradingRegistry } = await import("../src/api/trading.ts");

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

function mockAdapter(handler: (config: { url?: string; data?: string }) => unknown) {
  api.defaults.adapter = async (config: InternalAxiosRequestConfig) => {
    const result = handler(config);
    if (result instanceof Error) throw result;
    return { data: result, status: 200, statusText: "OK", headers: {}, config };
  };
}

/* ---- the kill-switch control -------------------------------------------- */

test("clear state offers HALT ENTRIES and says entries flow", async () => {
  const [host, cleanup] = await render(
    React.createElement(KillSwitchControlForTest, { tripped: false, note: "", onChanged: () => {} }),
  );
  assert.match(host.textContent ?? "", /clear — entries flow/);
  const halt = host.querySelector("button");
  assert.equal(halt?.textContent, "HALT ENTRIES");
  assert.match(halt?.getAttribute("title") ?? "", /Protective exits are never refused/);
  cleanup();
});

test("tripped state reads TRIPPED with the note, and the re-arm is behind a confirm strip", async () => {
  const [host, cleanup] = await render(
    React.createElement(KillSwitchControlForTest, { tripped: true, note: "vol spike", onChanged: () => {} }),
  );
  assert.match(host.textContent ?? "", /TRIPPED — entries halted desk-wide/);
  assert.match(host.textContent ?? "", /protective exits keep flowing/);
  assert.match(host.textContent ?? "", /vol spike/);
  // no note input until the operator opens the strip
  assert.equal(host.querySelector("input"), null);
  const rearm = [...host.querySelectorAll("button")].find((b) => b.textContent === "Re-arm…");
  assert.ok(rearm);
  await act(async () => {
    rearm!.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  const input = host.querySelector("input") as HTMLInputElement;
  assert.ok(input, "the confirm strip opens with the note input");
  const confirm = [...host.querySelectorAll("button")].find((b) => b.textContent === "Confirm re-arm") as HTMLButtonElement;
  assert.equal(confirm.disabled, true, "an empty note never confirms — the server would 422 it anyway");
  cleanup();
});

test("client: throwing the switch posts enabled true; re-arming carries the note", async () => {
  const posts: { enabled: boolean; note: string }[] = [];
  mockAdapter((config) => {
    posts.push(JSON.parse(config.data ?? "{}"));
    return { tripped: true, note: "" };
  });
  await setKillSwitch(true, "");
  await setKillSwitch(false, "spike passed, re-arming");
  assert.deepEqual(posts, [
    { enabled: true, note: "" },
    { enabled: false, note: "spike passed, re-arming" },
  ]);
});

/* ---- the lifecycle registry --------------------------------------------- */

const PAPER_VERSION = {
  version_id: 7,
  strategy_key: "scalp",
  name: "Scalp Trend",
  version: 1,
  state: "paper",
  params: { stop_atr: 2.2 },
  timeframe: "4h",
  universe: ["BTCUSDT"],
  code_hash: "deadbeefcafe0001",
  validation_id: 3,
  state_since: "2025-11-20T00:00:00Z",
  state_evidence: "",
  track_record: {
    trades_count: 12,
    realized_pnl: 140.5,
    span_days: 9.5,
    first_exit_at: "2025-11-10T12:00:00Z",
    last_exit_at: "2025-11-20T12:00:00Z",
    drift_fills_measured: 24,
    drift_breaches: 0,
  },
  fingerprint: "0123456789abcdef",
  pending_transition: "candidate_live",
};

test("empty registry is the honest first-class state", async () => {
  const [host, cleanup] = await render(
    React.createElement(RegistrySectionForTest, { versions: [], error: null, onChanged: () => {} }),
  );
  assert.match(host.textContent ?? "", /The lifecycle owns nothing yet/);
  assert.match(host.textContent ?? "", /the gate working, not a missing panel/);
  cleanup();
});

test("a paper version renders its row and the approval card with the fingerprint", async () => {
  const [host, cleanup] = await render(
    React.createElement(RegistrySectionForTest, { versions: [PAPER_VERSION], error: null, onChanged: () => {} }),
  );
  const text = host.textContent ?? "";
  assert.match(text, /scalp-v1/);
  assert.match(text, /paper/);
  assert.match(text, /Approval card — paper → candidate_live/);
  assert.match(text, /12 trades/);
  assert.match(text, /\+140\.50/);
  assert.match(text, /0123456789abcdef/);
  assert.match(text, /re-basing is impossible|the confirmation is refused/);
  cleanup();
});

test("a candidate_live version renders no further card — live is never offered", async () => {
  const advanced = { ...PAPER_VERSION, state: "candidate_live", pending_transition: null };
  const [host, cleanup] = await render(
    React.createElement(RegistrySectionForTest, { versions: [advanced], error: null, onChanged: () => {} }),
  );
  assert.match(host.textContent ?? "", /candidate_live/);
  assert.equal(host.querySelector("form"), null, "no approval form — the mandate is M5");
  cleanup();
});

test("confirming the card posts the fingerprint it was rendered with", async () => {
  const posts: { fingerprint: string; note: string }[] = [];
  mockAdapter((config) => {
    if ((config.url ?? "").includes("/approve")) {
      posts.push(JSON.parse(config.data ?? "{}"));
      return { approval_id: 1, state: "candidate_live", evidence: "approval:1", fingerprint: "x" };
    }
    return {};
  });
  const [host, cleanup] = await render(
    React.createElement(ApprovalCardForTest, { version: PAPER_VERSION, onChanged: () => {} }),
  );
  const confirm = [...host.querySelectorAll("button")].find((b) => b.textContent === "Confirm approval");
  assert.ok(confirm);
  await act(async () => {
    confirm!.closest("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
  assert.equal(posts.length, 1);
  assert.equal(posts[0].fingerprint, "0123456789abcdef");
  await act(async () => {});
  assert.match(host.textContent ?? "", /approved — state is now candidate_live/);
  cleanup();
});

test("the 409 renders as the honest inputs-moved state, never a silent retry", async () => {
  mockAdapter(() => {
    const err = new AxiosError("Request failed with status code 409", "ERR_BAD_REQUEST", undefined, undefined, {
      status: 409,
      statusText: "Conflict",
      headers: {},
      config: { headers: new AxiosHeaders() },
      data: { detail: "inputs moved — the track record, state or drift counters changed since this card was rendered. Review the new track record; re-basing is impossible." },
    } as never);
    return err;
  });
  const [host, cleanup] = await render(
    React.createElement(ApprovalCardForTest, { version: PAPER_VERSION, onChanged: () => {} }),
  );
  const confirm = [...host.querySelectorAll("button")].find((b) => b.textContent === "Confirm approval");
  await act(async () => {
    confirm!.closest("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
  await act(async () => {});
  assert.match(host.textContent ?? "", /inputs moved — review the new track record/);
  assert.match(host.textContent ?? "", /re-basing is impossible/);
  cleanup();
});

test("client: isConflict separates the staleness refusal from every other failure", () => {
  const conflict = { response: { status: 409 } };
  const other = { response: { status: 422 } };
  assert.equal(isConflict(conflict), true);
  assert.equal(isConflict(other), false);
  assert.equal(isConflict(new Error("network")), false);
});

test("client: the registry endpoint reads /api/trading/registry versions", async () => {
  mockAdapter(() => ({ versions: [PAPER_VERSION] }));
  const got = await getTradingRegistry();
  assert.equal(got.length, 1);
  assert.equal(got[0].fingerprint, "0123456789abcdef");
});

test("client: approveVersion posts to the version's own path", async () => {
  const urls: string[] = [];
  mockAdapter((config) => {
    urls.push(config.url ?? "");
    return { approval_id: 1, state: "candidate_live", evidence: "approval:1", fingerprint: "x" };
  });
  await approveVersion(7, "0123456789abcdef", "reviewed");
  assert.deepEqual(urls, ["/api/trading/registry/7/approve"]);
});
