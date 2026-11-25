/* What a validation verdict wears, and how the figures beside it are printed.

   The badge rules exist because "no verdict" used to be a colour decision made
   ad hoc in the markup: a run that never went through the gate wearing green
   is the exact optimism-in-validation failure the pipeline exists to exclude.
   The formatting rules exist because a rounded p-value can round INTO
   significance it never reached.

   Run by `npm test` with Node's own test runner: the module under test is
   pure, so no bundler and no DOM. */

import assert from "node:assert/strict";
import { test } from "node:test";
import {
  fmtCi,
  fmtFolds,
  fmtP,
  runsNewestFirst,
  verdictBadge,
} from "../src/components/tradingStatus.ts";
import type { BacktestRun } from "../src/api/trading.ts";

test("validated wears the gain colour, in the reader's words", () => {
  assert.deepEqual(verdictBadge("validated"), { label: "Validated", tone: "up" });
});

test("rejected wears the loss colour — the gate doing its job", () => {
  assert.deepEqual(verdictBadge("rejected"), { label: "Rejected", tone: "down" });
});

test("no verdict is a fact, not an outcome: neither colour, honestly labelled", () => {
  const badge = verdictBadge(null);
  assert.equal(badge.tone, "muted");
  assert.equal(badge.label, "Not validated");
});

test("small p-values keep their precision instead of rounding into significance", () => {
  assert.equal(fmtP(0.004), "0.0040");
  assert.equal(fmtP(0.0099), "0.0099");
});

test("ordinary p-values print to two decimals", () => {
  assert.equal(fmtP(0.042), "0.04");
  assert.equal(fmtP(0.37), "0.37");
  assert.equal(fmtP(1), "1.00");
});

test("a p-value of exactly zero never claims more than zero", () => {
  assert.equal(fmtP(0), "0");
});

test("the Sharpe interval prints both ends, signed, as one interval", () => {
  assert.equal(fmtCi(0.42, 1.87), "+0.42 … +1.87");
  assert.equal(fmtCi(-0.31, 1.02), "-0.31 … +1.02");
});

test("walk-forward consistency is the fraction it is", () => {
  assert.equal(fmtFolds(3, 4), "3/4");
  assert.equal(fmtFolds(0, 4), "0/4");
});

function run(id: number, started_at: string): BacktestRun {
  return {
    id,
    bot: "scalptrend",
    symbol: "BTCUSDT",
    timeframe: "1h",
    started_at,
    trades_count: 0,
    metrics: { win_rate: 0, profit_factor: 0, sharpe: 0, max_dd_pct: 0, total_return_pct: 0 },
    verdict: null,
    validation: null,
    created_at: started_at,
  };
}

test("the research record reads newest first, by the run's own start time", () => {
  const sorted = runsNewestFirst([
    run(1, "2026-01-10T08:00:00"),
    run(2, "2026-03-01T08:00:00"),
    run(3, "2026-02-14T08:00:00"),
  ]);
  assert.deepEqual(
    sorted.map((r) => r.id),
    [2, 3, 1],
  );
});

test("sorting never mutates the array the backend handed over", () => {
  const original = [run(1, "2026-01-10T08:00:00"), run(2, "2026-03-01T08:00:00")];
  runsNewestFirst(original);
  assert.deepEqual(
    original.map((r) => r.id),
    [1, 2],
  );
});
