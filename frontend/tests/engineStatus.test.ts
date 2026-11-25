/* The engine status header's one sentence, per state.

   These tests pin the distinction the whole trading dashboard stands on:
   the engine being offline is a STATE (first-class, dated, grey), the backend
   not answering is a different fact entirely (warn) — a page that merges them
   tells the reader "offline" when what happened is "unknown". */

import assert from "node:assert/strict";
import { test } from "node:test";
import { engineReading, engineTone } from "../src/components/tradingStatus.ts";
import type { TradingStatus } from "../src/api/trading.ts";

function status(over: Partial<TradingStatus> = {}): TradingStatus {
  return {
    engine_state: "offline",
    last_tick_at: null,
    db_ok: true,
    strategies_registered: 0,
    validations_total: 0,
    ...over,
  };
}

test("a running engine says so, with its last tick dated", () => {
  const reading = engineReading(
    status({ engine_state: "running", last_tick_at: "2026-11-25T09:30:00" }),
  );
  assert.equal(reading.state, "running");
  assert.match(reading.line, /running/i);
  assert.match(reading.line, /2026/);
});

test("a running engine that never ticked says exactly that", () => {
  const reading = engineReading(status({ engine_state: "running" }));
  assert.equal(reading.state, "running");
  assert.match(reading.line, /no tick/i);
});

test("an offline engine is a state, not an error — dated when it last wrote", () => {
  const reading = engineReading(status({ last_tick_at: "2026-11-20T22:00:00" }));
  assert.equal(reading.state, "offline");
  assert.match(reading.line, /offline/i);
  assert.match(reading.line, /last wrote/i);
  assert.doesNotMatch(reading.line, /error|fail/i);
});

test("an offline engine that never ticked claims nothing", () => {
  const reading = engineReading(status());
  assert.equal(reading.state, "offline");
  assert.match(reading.line, /never ticked/i);
});

test("the backend not answering is unreachable — never read as offline", () => {
  const reading = engineReading(null);
  assert.equal(reading.state, "unreachable");
  assert.doesNotMatch(reading.line, /offline/i);
  assert.match(reading.line, /did not answer/i);
});

test("the tone follows the state: green, grey, warn", () => {
  assert.equal(engineTone(engineReading(status({ engine_state: "running" }))), "up");
  assert.equal(engineTone(engineReading(status())), "muted");
  assert.equal(engineTone(engineReading(null)), "warn");
});
