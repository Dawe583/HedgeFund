/* What the equity chart can draw and what it must refuse.

   The empty state is first-class: fewer than two distinct timestamps is not a
   curve, and drawing one point as a flat line invents a stability the data
   never measured. Duplicates resolve to the newest write, because a chart
   silently dropping one is the untraceable-number failure in miniature. */

import assert from "node:assert/strict";
import { test } from "node:test";
import { change, drawable, sortedUnique } from "../src/viz/equityData.ts";

test("empty data is not drawable — the empty state is the answer", () => {
  assert.equal(drawable([]), false);
});

test("a single point is not a curve", () => {
  assert.equal(drawable([{ time: 1700000000, value: 100_000 }]), false);
});

test("two points are a curve", () => {
  assert.equal(
    drawable([
      { time: 1700000000, value: 100_000 },
      { time: 1700086400, value: 101_000 },
    ]),
    true,
  );
});

test("a duplicated timestamp is one point — never two vertices on one day", () => {
  assert.equal(
    drawable([
      { time: 1700000000, value: 100_000 },
      { time: 1700000000, value: 100_500 },
    ]),
    false,
  );
});

test("unsorted input comes out ascending, duplicates resolved to the newest write", () => {
  const out = sortedUnique([
    { time: 1700086400, value: 101_000 },
    { time: 1700000000, value: 100_000 },
    { time: 1700000000, value: 100_500 },
  ]);
  assert.deepEqual(out, [
    { time: 1700000000, value: 100_500 },
    { time: 1700086400, value: 101_000 },
  ]);
});

test("sorting never mutates the caller's array", () => {
  const input = [
    { time: 1700086400, value: 101_000 },
    { time: 1700000000, value: 100_000 },
  ];
  sortedUnique(input);
  assert.equal(input[0].time, 1700086400);
});

test("the change figure is first-to-last, as a ratio — null against a zero start", () => {
  const c = change([
    { time: 1700000000, value: 100_000 },
    { time: 1700086400, value: 110_000 },
  ]);
  assert.equal(c.from, 100_000);
  assert.equal(c.to, 110_000);
  assert.ok(c.pct !== null && Math.abs(c.pct - 0.1) < 1e-12);

  const zero = change([
    { time: 1700000000, value: 0 },
    { time: 1700086400, value: 500 },
  ]);
  assert.equal(zero.pct, null);
});
