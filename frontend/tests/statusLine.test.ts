/* The status line's engine lamp, rendered against the backend's answers.

   The furniture's one rule is honesty: unreachable is never read as offline.
   These tests mount the real StatusLine in jsdom with the axios adapter
   mocked at the same seam tradingClient.test.ts uses — the success case, the
   failure case, and the running case, each read off the DOM the way a desk
   would read it. */

import assert from "node:assert/strict";
import { test } from "node:test";
import type { InternalAxiosRequestConfig } from "axios";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", {
  url: "http://localhost/",
  pretendToBeVisual: true,
});
for (const key of ["window", "document", "navigator", "HTMLElement", "CustomEvent", "MutationObserver", "getComputedStyle", "location", "requestAnimationFrame", "cancelAnimationFrame", "matchMedia", "Element", "Node"]) {
  const v = (dom.window as unknown as Record<string, unknown>)[key];
  if (v === undefined) continue;
  Object.defineProperty(globalThis, key, {
    value: v,
    configurable: true,
    writable: true,
  });
}

/* Dynamic imports, not static: the jsdom globals above must exist BEFORE
   React and the component modules load, and a static import is hoisted
   ahead of everything in the file — the one ordering static cannot express. */
const React = await import("react");
const { createRoot } = await import("react-dom/client");
const { act } = React;
const { api } = await import("../src/api/client.ts");
const { StatusLine } = await import("../src/components/StatusLine.tsx");

(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;

function mockBackend(answer: object | "fail"): void {
  api.defaults.adapter = async (config: InternalAxiosRequestConfig) => {
    if (answer === "fail") {
      // No response at all — the backend process is down, which is the case
      // the unreachable state exists for.
      throw Object.assign(new Error("Network Error"), { config });
    }
    return { data: answer, status: 200, statusText: "OK", headers: {}, config };
  };
}

async function renderLine(answer: object | "fail"): Promise<{ host: HTMLElement; done: () => void }> {
  mockBackend(answer);
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(React.createElement(StatusLine, { section: "Trading", onOpenSheet: () => {} }));
  });
  // The status poll resolves outside the first flush — pump, then read.
  for (let i = 0; i < 3; i++) {
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100));
    });
  }
  return {
    host,
    // The line ticks (a one-second clock) and polls the engine: two live
    // intervals. Unmounting at the END of each test — not at process exit,
    // which those very intervals would keep from ever arriving — is what
    // lets the test process finish. React's unmount tears the effects down.
    done: () => {
      act(() => root.unmount());
      host.remove();
    },
  };
}

test("the lamp reads offline when the engine is offline — a state, not an error", async () => {
  const { host, done } = await renderLine({
    engine_state: "offline",
    last_tick_at: null,
    db_ok: true,
    strategies_registered: 0,
    validations_total: 18,
  });
  const text = host.textContent ?? "";
  assert.match(text, /offline/i);
  assert.doesNotMatch(text, /unreachable/i);
  // The full honest sentence rides on the lamp as its title.
  const lamp = host.querySelector("[title]");
  assert.match(lamp?.getAttribute("title") ?? "", /offline/i);
  done();
});

test("the lamp reads unreachable when the backend does not answer — never offline", async () => {
  const { host, done } = await renderLine("fail");
  const text = host.textContent ?? "";
  assert.match(text, /unreachable/i);
  assert.doesNotMatch(text, /offline/i);
  done();
});

test("the lamp reads running when the engine runs", async () => {
  const { host, done } = await renderLine({
    engine_state: "running",
    last_tick_at: "2026-11-26T09:30:00",
    db_ok: true,
    strategies_registered: 2,
    validations_total: 18,
  });
  assert.match(host.textContent ?? "", /running/i);
  done();
});

test("the frame furniture is all there: section, clock, and the key-sheet hint", async () => {
  const { host, done } = await renderLine({
    engine_state: "offline",
    last_tick_at: null,
    db_ok: true,
    strategies_registered: 0,
    validations_total: 0,
  });
  const text = host.textContent ?? "";
  assert.ok(text.includes("Trading"), "the section is named");
  assert.match(text, /\d{1,2}:\d{2}/, "the clock ticks in the line");
  assert.ok(host.querySelector("button") !== null, "the key sheet has a way in");
  done();
});
