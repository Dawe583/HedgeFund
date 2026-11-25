import { useEffect, useRef } from "react";
import {
  createChart,
  AreaSeries,
  type IChartApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { drawable, sortedUnique, type EquityPoint } from "./equityData";

/* An equity curve, drawn with lightweight-charts (v5 API, per the viz spike:
   chart.addSeries(AreaSeries, …), series typed ISeriesApi<"Area"> — and
   cleanup is chart.remove(), which makes StrictMode's double-mount harmless).

   The data discipline lives in ./equityData.ts: fewer than two distinct
   timestamps is NOT a curve, so the empty state is first-class — rendered
   here, worded by the caller, never filled with invented points. The caller
   owns what the emptiness means (an engine that never ran, a run with one
   snapshot); this component owns only "we cannot draw that".

   Colours: canvas 2d cannot read var(--color-…) strings, so the chart reads
   the resolved token values once at creation. A theme switch while the chart
   is mounted is not re-read — the spike's own constraint, acceptable because
   the chart re-creates whenever its data identity changes anyway. */

function cssToken(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

export function EquityChart({
  data,
  height = 240,
  emptyText = "No equity data — nothing to draw yet.",
}: {
  data: EquityPoint[];
  height?: number;
  emptyText?: string;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  // The series the chart draws, decided once per data identity: sorted,
  // deduped, or nothing.
  const points = sortedUnique(data);
  const canDraw = drawable(data);

  useEffect(() => {
    if (!canDraw || !hostRef.current) return;
    const chart: IChartApi = createChart(hostRef.current, {
      width: hostRef.current.clientWidth,
      height,
      layout: {
        background: { color: "transparent" },
        textColor: cssToken("--color-ink-soft", "#6f6a5f"),
        fontSize: 10,
        // The axis numbers are data, and data speaks mono: a price scale in
        // a proportional face is a newspaper's chart, not a terminal's.
        fontFamily: "'IBM Plex Mono', ui-monospace, Menlo, monospace",
      },
      grid: {
        vertLines: { color: cssToken("--color-hair", "#e5e0d4") },
        horzLines: { color: cssToken("--color-hair", "#e5e0d4") },
      },
      rightPriceScale: { borderColor: cssToken("--color-rule", "#cfc8b8") },
      timeScale: { borderColor: cssToken("--color-rule", "#cfc8b8") },
      crosshair: {
        horzLine: { labelVisible: true },
      },
    });
    // One series, the olive accent — the dataviz rule for single-series
    // charts, the same hue the net-worth chart wears.
    const series = chart.addSeries(AreaSeries, {
      lineColor: cssToken("--color-olive", "#5a6247"),
      topColor: cssToken("--color-olive", "#5a6247") + "33",
      bottomColor: cssToken("--color-olive", "#5a6247") + "05",
      lineWidth: 2,
      priceLineVisible: false,
    });
    series.setData(
      points.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })),
    );
    chart.timeScale().fitContent();

    const observer = new ResizeObserver(() => {
      if (hostRef.current) chart.applyOptions({ width: hostRef.current.clientWidth });
    });
    observer.observe(hostRef.current);
    return () => {
      observer.disconnect();
      chart.remove();
    };
    // points identity changes with data; height rarely. Re-creating the chart
    // on new data is deliberate — an equity curve is a document of a finished
    // thing, not a streaming tape, and setData+fitContent on the same chart
    // keeps a scale memory of the old range.
  }, [points, canDraw, height]);

  if (!canDraw) {
    return (
      <div
        className="flex items-center justify-center text-sm text-ink-soft"
        style={{ height }}
      >
        {emptyText}
      </div>
    );
  }
  return <div ref={hostRef} style={{ height }} />;
}
