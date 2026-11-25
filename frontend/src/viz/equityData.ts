/* The equity chart's data rules, pure and testable: what the chart can draw
   and what it must refuse. The component (EquityChart.tsx) is a thin shell
   over these — every decision is here, so node --test can argue with it
   without a DOM. */

/** One point of an equity curve: unix seconds (UTC day or tick) and the
    equity value in whatever currency the caller names. */
export interface EquityPoint {
  time: number;
  value: number;
}

/** lightweight-charts requires strictly ascending unique timestamps; the
    callers hand over database rows, which are neither guaranteed sorted nor
    guaranteed unique. Sorting here (rather than trusting the backend's
    ORDER BY) because a chart silently dropping a duplicate row is exactly
    the number-you-cannot-trace failure the rest of the system exists to
    prevent: better to dedupe with a rule than to render wrong.

    Rule for duplicates: the LAST point for a timestamp wins — the newest
    write is the correction. Returns a new array, never mutates the input. */
export function sortedUnique(points: EquityPoint[]): EquityPoint[] {
  const byTime = new Map<number, number>();
  for (const p of points) byTime.set(p.time, p.value);
  return [...byTime.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([time, value]) => ({ time, value }));
}

/** Can the chart honestly draw? Fewer than two points is not a curve — it is
    a point, and rendering one as a flat line invents a stability the data
    never measured. The chart shows its empty state instead. */
export function drawable(points: EquityPoint[]): boolean {
  return sortedUnique(points).length >= 2;
}

/** First/last equity of a drawable series, for the caption's change figure.
    Sign included by the caller's formatter, not here — a ratio, not money. */
export function change(points: EquityPoint[]): { from: number; to: number; pct: number | null } {
  const sorted = sortedUnique(points);
  const from = sorted[0].value;
  const to = sorted[sorted.length - 1].value;
  // pct null when the curve starts at zero: a ratio against zero is not
  // a number, and printing "∞%" is worse than printing nothing.
  return { from, to, pct: from !== 0 ? (to - from) / Math.abs(from) : null };
}

/* The wire-to-chart boundary. The API sends ISO timestamps; lightweight-charts
   wants unix seconds. One function, both directions of failure named: a
   timestamp that does not parse is DROPPED, not coerced — a point at the
   wrong time is a lie, a missing point is visible in the count. The caller
   compares input length to output length if the discrepancy matters; for a
   finished backtest's curve, silently re-timed points are the worse failure. */

/** Convert the API's `{t: iso, equity}` rows into chart points — unix seconds,
    unparseable timestamps dropped. Unsorted output is fine: sortedUnique is
    the chart's own gate. */
export function fromApiCurve(rows: { t: string; equity: number }[]): EquityPoint[] {
  const out: EquityPoint[] = [];
  for (const r of rows) {
    const ms = Date.parse(r.t);
    if (Number.isNaN(ms)) continue;
    out.push({ time: Math.floor(ms / 1000), value: r.equity });
  }
  return out;
}
