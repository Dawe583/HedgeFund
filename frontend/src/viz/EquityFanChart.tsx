import { useEffect, useRef } from "react";
import { createChart, LineSeries, type IChartApi, type UTCTimestamp } from "lightweight-charts";
import type { TradingEquityFan } from "../api/trading";

/* The validation equity fan — Vibe's percentile bands over the Monte Carlo
   permuted paths, with the run's actual path drawn over them.

   What it shows, exactly: every permutation of the SAME trades, plotted by
   trade step. The x axis is a step index, not a clock — the fan answers
   "where could this path have ended up", never "when". lightweight-charts
   speaks only timestamps, so steps are cast into the time slot and the time
   scale is hidden: the axis is never read as a date because it never draws
   one. The caption beside the chart names the axis in words.

   The bands: p5/p95 outer, p25/p75 inner, p50 the median path — plus a
   handful of individual sample paths in hairline ink, because a band alone
   reads as a boundary and the paths ARE the distribution. The actual path
   is the one line in the accent colour: it is the experiment, everything
   else is the null. */

function cssToken(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

/** The fan is drawable when the bands and steps agree in length and there
    are at least two steps — one step is a point, not a path. */
function fanDrawable(fan: TradingEquityFan): boolean {
  const n = fan.steps.length;
  return (
    n >= 2 &&
    fan.band_p5.length === n &&
    fan.band_p95.length === n &&
    fan.band_p50.length === n &&
    fan.actual.length === n
  );
}

export function EquityFanChart({ fan, height = 220 }: { fan: TradingEquityFan; height?: number }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const canDraw = fanDrawable(fan);

  useEffect(() => {
    if (!canDraw || !hostRef.current) return;
    const chart: IChartApi = createChart(hostRef.current, {
      width: hostRef.current.clientWidth,
      height,
      layout: {
        background: { color: "transparent" },
        textColor: cssToken("--color-ink-soft", "#6f6a5f"),
        fontSize: 10,
        fontFamily: "'IBM Plex Mono', ui-monospace, Menlo, monospace",
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: cssToken("--color-hair", "#e5e0d4") },
      },
      rightPriceScale: { borderColor: cssToken("--color-rule", "#cfc8b8") },
      // the x axis is trade steps, not time — hidden, and the caption says
      // what it is. A date axis over step data would be the lie this chart
      // exists to not tell.
      timeScale: { visible: false },
    });

    const hairline = cssToken("--color-ink-faint", "#a39d8f");
    const ink = cssToken("--color-ink-soft", "#6f6a5f");
    const accent = cssToken("--color-olive", "#5a6247");

    const line = (color: string, width: 1 | 2, title: string) => {
      const series = chart.addSeries(LineSeries, {
        color,
        lineWidth: width,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
        title,
      });
      return series;
    };

    const points = (values: number[]) =>
      fan.steps.map((step, i) => ({ time: step as UTCTimestamp, value: values[i] }));

    // sample paths first, beneath everything — they are texture, not data ink
    for (const path of fan.samples.slice(0, 30)) {
      if (path.length !== fan.steps.length) continue;
      line(hairline + "55", 1, "").setData(points(path));
    }
    line(hairline, 1, "p5/p95").setData(points(fan.band_p5));
    line(hairline, 1, "p5/p95").setData(points(fan.band_p95));
    line(ink, 1, "p25/p75").setData(points(fan.band_p25));
    line(ink, 1, "p25/p75").setData(points(fan.band_p75));
    line(ink, 2, "p50").setData(points(fan.band_p50));
    line(accent, 2, "actual").setData(points(fan.actual));

    chart.timeScale().fitContent();

    const observer = new ResizeObserver(() => {
      if (hostRef.current) chart.applyOptions({ width: hostRef.current.clientWidth });
    });
    observer.observe(hostRef.current);
    return () => {
      observer.disconnect();
      chart.remove();
    };
  }, [fan, canDraw, height]);

  if (!canDraw) {
    return (
      <div className="flex items-center justify-center text-sm text-ink-soft" style={{ height }}>
        The fan cannot be drawn — the bands and the step axis disagree, which means the recorded
        fan is incomplete, not that there is nothing to say.
      </div>
    );
  }
  return <div ref={hostRef} style={{ height }} />;
}
