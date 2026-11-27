import { Fragment, useEffect, useState } from "react";
import {
  approveVersion,
  getBacktestRun,
  getBacktestRuns,
  getModelRegistry,
  getStrategyPanels,
  getTradingRegistry,
  getTradingSignalsToday,
  getValidationQueue,
  isConflict,
  setKillSwitch,
  getTradingDivergence,
  getRecentTrades,
  getTradingPositions,
  getTradingRails,
  getTradingStatus,
  getTradingStrategies,
  type BacktestRun,
  type BacktestRunDetail,
  type RunMetrics,
  type TradingDivergenceStatus,
  type RunProvenance,
  type TradingClosedTrade,
  type TradingModelRegistry,
  type TradingPosition,
  type TradingRailsStatus,
  type TradingSignalsToday,
  type TradingStatus,
  type TradingStrategy,
  type TradingStrategyPanel,
  type TradingValidationQueue,
  type TradingMandate,
  type TradingOrderCard,
  type TradingRegistryVersion,
  getTradingMandates,
  getTradingOrderCards,
} from "../api/trading";
import { Blotter } from "../viz/Blotter";
import { EquityFanChart } from "../viz/EquityFanChart";
import { EquityChart } from "../viz/EquityChart";
import { fromApiCurve } from "../viz/equityData";
import { EmptyState } from "./Emblem";
import LedgerBrowser from "./LedgerBrowser";
import { apiError, btnClass, cardClass, inputClass, Section, statLabelClass } from "./ui";
import {
  divergenceBudgetsOf,
  engineReading,
  engineTone,
  fmtCi,
  fmtFolds,
  fmtP,
  fmtTicks,
  runsNewestFirst,
  verdictBadge,
  type BadgeTone,
  type DivergenceBudgets,
} from "./tradingStatus";

/* TRADING — the trading plane's page, structured as the design's information
   architecture (hedge-fund-os.md §8) lays it out: the positions blotter first,
   because what the desk holds IS the desk; the research record below it.
   Empty is an answer, never an error — a page pretending otherwise would be
   a demo, not a dashboard.

   The page's design law, inherited from the whole app: no number without
   provenance — the validation figures name the run and date they come from,
   the engine's state says when it was last true, and a missing verdict is
   "not validated", never a colour borrowed from either outcome. Numbers in
   columns are tabular (index.css does that for every td); standalone figures
   stay proportional. */

function fmtDay(iso: string | null): string {
  if (iso === null) return "—";
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

const TONE_CLASS: Record<BadgeTone, string> = {
  up: "bg-up-tint text-up",
  down: "bg-down-tint text-down",
  muted: "bg-olive-tint text-ink-soft",
};

function Badge({ tone, children, title }: { tone: BadgeTone; children: string; title?: string }) {
  return (
    <span
      title={title}
      className={
        "inline-block rounded-sm px-1.5 py-0.5 text-[0.65rem] font-medium uppercase tracking-[0.1em] " +
        TONE_CLASS[tone]
      }
    >
      {children}
    </span>
  );
}

/* ---- Engine status strip ------------------------------------------------

   The terminal's instrument strip, not a banner: one hairline-framed row
   that reads like a panel header — the status LAMP first (a terminal's
   lights are small and square, not round jewels), then the state readout in
   the mono voice, then the counters it can vouch for. The strip is flush
   with the page: full-bleed instrument furniture, no card rounding. */

function EngineHeader({ status, error }: { status: TradingStatus | null; error: string | null }) {
  // The backend failing to answer is read as unreachable, not offline — the
  // distinction tradingStatus.engineReading exists to keep.
  const reading = engineReading(error !== null ? null : status);
  const tone = engineTone(reading);
  const surface =
    tone === "up"
      ? "border-rule bg-up-tint"
      : tone === "warn"
        ? "border-rule bg-warn-tint"
        : "border-rule bg-surface";
  const lamp = tone === "up" ? "bg-up" : tone === "warn" ? "bg-warn" : "bg-ink-faint";
  return (
    <div className={"border-l-2 border-y border-r px-3 py-2 " + surface}>
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 font-mono">
        <span className="flex items-center gap-2">
          <span className={"inline-block h-2.5 w-2.5 " + lamp} aria-hidden="true" />
          <span className="text-[0.7rem] uppercase tracking-[0.14em] text-ink-faint">Engine</span>
        </span>
        <span className="text-xs text-ink">{reading.line}</span>
        {status && error === null && (
          <span className="ml-auto flex flex-wrap gap-x-4 text-[0.7rem] uppercase tracking-[0.12em] text-ink-soft">
            <span>
              Strategies <span className="tabular-nums text-ink">{status.strategies_registered}</span>
            </span>
            <span>
              Validations <span className="tabular-nums text-ink">{status.validations_total}</span>
            </span>
          </span>
        )}
      </div>
    </div>
  );
}

/* ---- The research record ------------------------------------------------ */

function MetricFigure({ k, v }: { k: string; v: number | null }) {
  return (
    <span className="inline-flex items-baseline gap-1">
      <span className="text-[0.65rem] uppercase tracking-wider text-ink-faint">{k}</span>
      {/* null is a fact too: too few trades for the statistic — a dash, never a zero */}
      <span className={v === null ? "text-ink-faint" : "tabular-nums text-ink"}>
        {v === null ? "—" : +v.toFixed(2)}
      </span>
    </span>
  );
}

const PROVENANCE_LABELS: [keyof RunProvenance, string][] = [
  ["seed", "seed"],
  ["data_source", "source"],
  ["data_rows", "rows"],
  ["data_start", "window start"],
  ["data_end", "window end"],
];


/** The expanding row body. Exported (as RunDetailForTest) because the render
    tests mount it standalone, without the table row that normally owns it —
    same component, no test-only behaviour. */
export function RunDetail({ id }: { id: number }) {
  const [detail, setDetail] = useState<BacktestRunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    getBacktestRun(id)
      .then((d) => {
        if (alive) setDetail(d);
      })
      .catch((e) => {
        if (alive) setError(apiError(e, "The run's detail could not be loaded."));
      });
    return () => {
      alive = false;
    };
  }, [id]);

  if (error) return <p className="py-2 text-sm text-down">{error}</p>;
  if (!detail) return <p className="py-2 text-sm text-ink-soft">Loading the run…</p>;

  return (
    <div className="py-3">
      {/* engine_version is the execution layer's fingerprint: rows written
          before the kernel migration (null) and after it are two different
          measurements of the world, and the detail says which it is looking
          at rather than letting them read as the same experiment */}
      <p className="mb-3 text-xs text-ink-faint">
        engine: {detail.engine_version ?? "not recorded — predates the kernel migration"}
      </p>
      {detail.reasons && detail.reasons.length > 0 && (
        <div className="mb-3">
          <h4 className={statLabelClass}>The gate's reasons</h4>
          <ul className="mt-1 space-y-0.5 text-sm text-ink-soft">
            {detail.reasons.map((r) => (
              <li key={r}>· {r}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
      <div>
        <h4 className={statLabelClass}>Parameters</h4>
        {Object.keys(detail.params).length === 0 ? (
          <p className="mt-1 text-sm text-ink-soft">No parameters recorded.</p>
        ) : (
          <dl className="mt-1 space-y-0.5 font-mono text-xs">
            {Object.entries(detail.params).map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3">
                <dt className="text-ink-soft">{k}</dt>
                <dd className="tabular-nums text-ink">{String(v)}</dd>
              </div>
            ))}
          </dl>
        )}
        <p className="mt-2 text-xs text-ink-faint">
          A verdict that cannot be re-run is an opinion — the seed and the data
          window beside the metrics are what makes it a measurement.
        </p>
      </div>
      <div>
        <h4 className={statLabelClass}>Data provenance</h4>
        {!detail.provenance ? (
          <p className="mt-1 text-sm text-ink-soft">No provenance — the validation gate never ran on this backtest.</p>
        ) : (
          <dl className="mt-1 space-y-0.5 font-mono text-xs">
            {PROVENANCE_LABELS.map(([key, label]) => {
              const provenance = detail.provenance;
              const value = provenance ? provenance[key] : null;
              return (
              <div key={key} className="flex justify-between gap-3">
                <dt className="text-ink-soft">{label}</dt>
                <dd className={typeof value === "number" ? "tabular-nums text-ink" : "text-ink"}>
                  {value ?? "not recorded"}
                </dd>
              </div>
              );
            })}
            {detail.prob_positive != null && (
              <div className="flex justify-between gap-3">
                <dt className="text-ink-soft">prob. positive</dt>
                <dd className="tabular-nums text-ink">{detail.prob_positive.toFixed(3)}</dd>
              </div>
            )}
            {detail.sharpe_actual != null && (
              <div className="flex justify-between gap-3">
                <dt className="text-ink-soft">sharpe actual</dt>
                <dd className="tabular-nums text-ink">{detail.sharpe_actual.toFixed(2)}</dd>
              </div>
            )}
          </dl>
        )}
        <h4 className={statLabelClass + " mt-4"}>Metrics</h4>
        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs">
          {(Object.keys(detail.metrics) as (keyof RunMetrics)[]).map((k) => (
            <MetricFigure key={k} k={k} v={detail.metrics[k]} />
          ))}
        </div>
      </div>
      </div>
      {/* The equity curve and the blotter below the figures — the numbers
          say what happened, these show HOW it happened. Both carry the same
          honesty rule as the rest of the detail: null means the run predates
          the recording, and the sentence says so instead of drawing nothing
          or inventing points. The blotter is Perspective behind a lazy import,
          so it costs nothing for a detail nobody opens. */}
      <div className="mt-4">
        <h4 className={statLabelClass}>Equity curve</h4>
        <div className="mt-1">
          {detail.equity_curve === null ? (
            <p className="py-6 text-center text-sm text-ink-soft">
              Equity curve not recorded for this run — it predates the recording.
            </p>
          ) : (
            <EquityChart
              data={fromApiCurve(detail.equity_curve)}
              emptyText="The recorded curve has fewer than two distinct points — not enough to draw."
            />
          )}
        </div>
      </div>
      <div className="mt-4">
        <h4 className={statLabelClass}>Equity fan — the permutation null</h4>
        <div className="mt-1">
          {detail.equity_fan == null ? (
            <p className="py-6 text-center text-sm text-ink-soft">
              No fan recorded — the validation never ran on this run, or the permutation matrix was
              honestly too large to keep. The verdict stands without it; the fan is the shape of the
              null, not the verdict itself.
            </p>
          ) : (
            <>
              <EquityFanChart fan={detail.equity_fan} height={220} />
              <p className="mt-1 font-mono text-[0.7rem] text-ink-faint">
                x is the trade step, not a clock — every permutation of the same {detail.trades_count} trades,
                percentile bands p5/p25/p50/p75/p95 over {detail.equity_fan.initial_capital.toFixed(0)} initial
                capital, the run&apos;s actual path in the accent. The fan answers where the path could
                have ended up, never when.
              </p>
            </>
          )}
        </div>
      </div>
      <div className="mt-4">
        <h4 className={statLabelClass}>Trades</h4>
        <div className="mt-1">
          {detail.trades === null ? (
            <p className="py-6 text-center text-sm text-ink-soft">
              Trades not recorded for this run — it predates the recording.
            </p>
          ) : (
            <Blotter
              rows={detail.trades.map((t) => ({ ...t }))}
              columns={["entry_time", "exit_time", "side", "qty", "entry_price", "exit_price", "pnl"]}
              empty="No trades — the run never opened a position, which is what zero trades means."
            />
          )}
        </div>
      </div>
    </div>
  );
}

export const RunDetailForTest = RunDetail;

function ResearchSection({ runs, error }: { runs: BacktestRun[] | null; error: string | null }) {
  const [openId, setOpenId] = useState<number | null>(null);

  if (error) return <p className="text-down">{error}</p>;
  if (runs === null) return <p className="text-ink-soft">Loading…</p>;
  if (runs.length === 0) {
    return (
      <EmptyState title="No backtest runs yet">
        The research pipeline writes a row here for every run it finishes — metrics, validation
        verdict and the provenance to reproduce it. Nothing has run through it so far.
      </EmptyState>
    );
  }

  const sorted = runsNewestFirst(runs);
  /* The table and the detail are separate surfaces: the table scrolls
     horizontally inside its card on narrow windows (that is what the card's
     overflow is FOR), and a detail nested inside it would inherit the
     scrollport's column width — measured at 390px, where the run's evidence
     was clipped to the label column with every value scrolled out of reach.
     So the open detail renders BELOW the card, full-width, visually docked
     to the table it expands by the row's hairline and the shared tint. */
  return (
    <>
      <div className={cardClass + " overflow-x-auto"}>
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr className="border-b border-rule text-[0.65rem] uppercase tracking-[0.1em] text-ink-soft">
            <th className="px-3 py-1.5 text-left font-medium">Strategy</th>
            <th className="px-3 py-1.5 text-left font-medium">Symbol</th>
            <th className="px-3 py-1.5 text-left font-medium">TF</th>
            <th className="px-3 py-1.5 text-left font-medium">Started</th>
            <th className="px-3 py-1.5 text-right font-medium">Trades</th>
            <th className="px-3 py-1.5 text-right font-medium">Permutation p</th>
            <th className="px-3 py-1.5 text-right font-medium">Sharpe CI</th>
            <th className="px-3 py-1.5 text-right font-medium">WF folds</th>
            <th className="px-3 py-1.5 text-left font-medium">Verdict</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => {
            const badge = verdictBadge(r.verdict);
            const provenance = `run #${r.id} · ${r.bot} on ${r.symbol} · started ${fmtDay(r.started_at)}`;
            return (
              <Fragment key={r.id}>
                <tr
                  data-run-row
                  tabIndex={0}
                  aria-expanded={openId === r.id}
                  onClick={() => setOpenId(openId === r.id ? null : r.id)}
                  onKeyDown={(e) => {
                    /* The research record is a blotter, and a blotter is
                       operated by keys: ↑/↓ walk the rows (the DOM holds
                       them, expansion rows included — querySelector's list
                       is the truth), Enter opens the detail the click
                       would. Space does NOT toggle: on a tr it scrolls,
                       and a scroll that looks like nothing happened is the
                       worst keyboard trap. */
                    if (e.key === "Enter") {
                      e.preventDefault();
                      setOpenId(openId === r.id ? null : r.id);
                    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                      e.preventDefault();
                      const rows = Array.from(
                        e.currentTarget.closest("tbody")?.querySelectorAll("[data-run-row]") ?? [],
                      );
                      const at = rows.indexOf(e.currentTarget);
                      const next = rows[at + (e.key === "ArrowDown" ? 1 : -1)];
                      if (next instanceof HTMLElement) next.focus();
                    }
                  }}
                  className="cursor-pointer border-b border-hair last:border-b-0 hover:bg-olive-tint/40 focus:bg-olive-tint/40"
                >
                  <td className="px-3 py-1 text-ink">{r.bot}</td>
                  <td className="px-3 py-1 text-ink">{r.symbol}</td>
                  <td className="px-3 py-1 text-ink-soft">{r.timeframe}</td>
                  <td className="px-3 py-1 text-ink-soft">{fmtDay(r.started_at)}</td>
                  <td className="px-3 py-1 text-right tabular-nums text-ink" title={provenance}>
                    {r.trades_count}
                  </td>
                  {r.validation ? (
                    <>
                      <td className="px-3 py-1 text-right tabular-nums text-ink" title={provenance}>
                        {fmtP(r.validation.permutation_p)}
                      </td>
                      <td className="px-3 py-1 text-right tabular-nums text-ink" title={provenance}>
                        {fmtCi(r.validation.sharpe_ci_lo, r.validation.sharpe_ci_hi)}
                      </td>
                      <td className="px-3 py-1 text-right tabular-nums text-ink" title={provenance}>
                        {fmtFolds(r.validation.wf_positive_folds, r.validation.wf_total_folds)}
                      </td>
                    </>
                  ) : (
                    <td
                      colSpan={3}
                      className="px-3 py-1 text-right text-ink-faint"
                      title={`${provenance} · the validation gate never ran on this backtest`}
                    >
                      —
                    </td>
                  )}
                  <td className="px-3 py-1">
                    <Badge tone={badge.tone} title={provenance}>
                      {badge.label}
                    </Badge>
                  </td>
                </tr>
              </Fragment>
            );
          })}
        </tbody>
      </table>
      </div>
      {openId !== null && (
        <div className="border border-t-0 border-rule bg-ground/60 px-4">
          <RunDetail id={openId} />
        </div>
      )}
    </>
  );
}


/* ---- The strategies registry ------------------------------------------- */

function StrategiesSection({
  strategies,
  error,
}: {
  strategies: TradingStrategy[] | null;
  error: string | null;
}) {
  if (error) return <p className="text-down">{error}</p>;
  if (strategies === null) return <p className="text-ink-soft">Loading…</p>;
  if (strategies.length === 0) {
    return (
      <EmptyState title="No strategies ported yet">
        The registry lists every strategy the research plane knows — ported as code, validated as
        evidence, registered for capital only after the gates. It is empty because nothing has been
        ported so far.
      </EmptyState>
    );
  }
  /* The registry as a terminal roster: one hairline-ruled table, not cards —
     the columns line up (name, window, symbols, state) because what a desk
     does with a registry is SCAN it for the one row that changed. */
  return (
    <div className={cardClass + " overflow-x-auto"}>
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr className="border-b border-rule text-[0.65rem] uppercase tracking-[0.1em] text-ink-soft">
            <th className="px-3 py-1.5 text-left font-medium">Key</th>
            <th className="px-3 py-1.5 text-left font-medium">Name</th>
            <th className="px-3 py-1.5 text-left font-medium">TF</th>
            <th className="px-3 py-1.5 text-left font-medium">Symbols</th>
            <th className="px-3 py-1.5 text-left font-medium">Description</th>
            <th className="px-3 py-1.5 text-left font-medium">State</th>
          </tr>
        </thead>
        <tbody>
          {strategies.map((s) => (
            <tr key={s.key} className="border-b border-hair last:border-b-0">
              <td className="px-3 py-1 text-ink-soft">{s.key}</td>
              <td className="px-3 py-1 text-ink">{s.name}</td>
              <td className="px-3 py-1 text-ink-soft">{s.timeframe}</td>
              <td className="px-3 py-1 text-ink">{s.symbols.join(", ")}</td>
              <td className="max-w-[40ch] px-3 py-1 text-ink-soft">{s.description}</td>
              <td className="px-3 py-1">
                {s.registered ? (
                  <Badge tone="up">Registered</Badge>
                ) : (
                  <Badge tone="muted" title="Ported as code for research only — no capital, no orders. Registration is a gate decision, not a default.">
                    Research only
                  </Badge>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


/* ---- The positions blotter ----------------------------------------------

   What the desk is holding right now. The table reads like a terminal
   blotter: dense mono rows, the side as a direction (▲ long / ▼ short —
   the semiotics of the tape, not decoration), the protective levels the
   row carries, and the age TICKING — the server measured age_seconds on
   its own clock at read time, the page counts forward from that one
   measurement instead of re-computing against a second clock.

   Age formatting: mm:ss under the hour, hh:mm under the day, then days —
   a position's age is scanned, never read. */

/** Seconds as the blotter's age readout. Exported (and pure) because the
    tick's arithmetic is exactly what a render test can pin. */
export function fmtAge(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  if (s >= 86400) {
    const d = Math.floor(s / 86400);
    const h = Math.floor((s % 86400) / 3600);
    return `${d}d ${h}h`;
  }
  if (s >= 3600) {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return `${h}:${String(m).padStart(2, "0")}h`;
  }
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

function useTick(intervalMs: number): number {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return tick;
}

function fmtClock(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** The open-positions table. Exported (as PositionsBlotterForTest) because
    the render tests mount it with fixture rows — the ticking age is the
    behaviour under test, and a test that cannot mount the table cannot see
    it tick. `fetchedAt` is when the payload arrived (ms epoch): ages tick
    from age_seconds plus the time since then, so a stalled page shows
    advancing ages — the honest reading of rows that keep aging whether or
    not the page refreshes. */
export function PositionsBlotter({
  positions,
  fetchedAt,
  budgets,
}: {
  positions: TradingPosition[];
  fetchedAt: number;
  budgets?: DivergenceBudgets;
}) {
  const tick = useTick(1000);
  void tick; // the tick's only job is to re-render; the clock is Date.now()
  const elapsed = (Date.now() - fetchedAt) / 1000;
  return (
    <div className={cardClass + " overflow-x-auto"}>
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr className="border-b border-rule text-[0.65rem] uppercase tracking-[0.1em] text-ink-soft">
            <th className="px-3 py-1.5 text-left font-medium">Bot</th>
            <th className="px-3 py-1.5 text-left font-medium">Symbol</th>
            <th className="px-3 py-1.5 text-left font-medium">Side</th>
            <th className="px-3 py-1.5 text-right font-medium">Qty</th>
            <th className="px-3 py-1.5 text-right font-medium">Entry</th>
            <th className="px-3 py-1.5 text-right font-medium">Stop</th>
            <th className="px-3 py-1.5 text-right font-medium">Target</th>
            <th className="px-3 py-1.5 text-right font-medium">Dev</th>
            <th className="px-3 py-1.5 text-right font-medium">Age</th>
            <th className="px-3 py-1.5 text-right font-medium">Conf</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => {
            const long = p.side === "long";
            const provenance =
              `opened ${new Date(p.opened_at).toLocaleString()}` +
              (p.signal_time
                ? ` · signal bar ${new Date(p.signal_time).toLocaleString()}`
                : " · signal time not recorded — row predates the kernel migration") +
              ` · written by ${p.gate_source}`;
            // slice-5 divergence evidence: the entry fill's deviation in
            // ticks from the filling bar's close. Colored ONLY when the
            // bot's declared budget says so — a reading inside budget is
            // mono ink because parity holding is the normal state, not a
            // badge. Unmeasured reads as a dash, never a zero.
            const budget = budgets?.get(p.bot);
            const dev = p.entry_dev_ticks;
            const breaching = dev !== null && dev !== undefined && budget !== undefined && Math.abs(dev) > budget;
            const devTitle =
              dev === null || dev === undefined
                ? "entry drift unmeasured — the row predates slice 5 or the reference bar was unknowable"
                : `entry fill ${fmtTicks(dev)} ticks from the filling bar's close` +
                  (p.entry_ref_price ? ` (reference ${p.entry_ref_price})` : "") +
                  (p.entry_lag_bars !== null && p.entry_lag_bars !== undefined
                    ? ` · timing lag ${p.entry_lag_bars} bar${p.entry_lag_bars === 1 ? "" : "s"}`
                    : "") +
                  (budget !== undefined ? ` · budget ±${budget} ticks` : "") +
                  (breaching ? " — BREACHING THE DECLARED BUDGET" : "");
            return (
              <tr
                key={p.id}
                tabIndex={0}
                className="border-b border-hair last:border-b-0 hover:bg-olive-tint/40 focus:bg-olive-tint/40"
              >
                <td className="px-3 py-1 text-ink-soft">{p.bot}</td>
                <td className="px-3 py-1 text-ink">{p.symbol}</td>
                <td
                  className={"px-3 py-1 font-medium " + (long ? "text-up" : "text-down")}
                  title={provenance}
                >
                  {long ? "▲ long" : "▼ short"}
                </td>
                <td className="px-3 py-1 text-right tabular-nums text-ink">{p.qty}</td>
                <td className="px-3 py-1 text-right tabular-nums text-ink">{p.entry_price}</td>
                <td className="px-3 py-1 text-right tabular-nums text-down">{p.stop_loss}</td>
                <td className="px-3 py-1 text-right tabular-nums text-up">{p.take_profit}</td>
                <td
                  className={
                    "px-3 py-1 text-right tabular-nums font-mono " +
                    (breaching ? "font-medium text-down" : dev === null || dev === undefined ? "text-ink-faint" : "text-ink-soft")
                  }
                  title={devTitle}
                >
                  {fmtTicks(dev)}
                </td>
                <td className="px-3 py-1 text-right tabular-nums text-ink" title={provenance}>
                  {fmtAge(p.age_seconds + elapsed)}
                </td>
                <td className="px-3 py-1 text-right tabular-nums text-ink-soft">
                  {p.confidence.toFixed(2)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export const PositionsBlotterForTest = PositionsBlotter;

/* The recent-trades strip: settled round-trips as evidence the desk actually
   traded. Dense one-line rows, pnl signed and coloured — a loss reads red
   because it IS red, never because the palette needed variety. */
function RecentTradesStrip({ trades, budgets }: { trades: TradingClosedTrade[]; budgets?: DivergenceBudgets }) {
  if (trades.length === 0) return null;
  return (
    <div className="mt-3">
      <h4 className={statLabelClass}>Recently settled</h4>
      <div className={cardClass + " mt-1 overflow-x-auto"}>
        <table className="w-full border-collapse text-xs">
          <tbody>
            {trades.map((t) => {
              const won = t.pnl >= 0;
              // entry/exit drift in ticks, compact — the trade's execution
              // evidence beside its economics. Colored only when breaching
              // the bot's declared budget; unmeasured reads as a dash.
              const budget = budgets?.get(t.bot);
              const devs: { v: number | null | undefined; kind: string }[] = [
                { v: t.entry_dev_ticks, kind: "entry" },
                { v: t.exit_dev_ticks, kind: "exit" },
              ];
              const worst = devs.reduce<number | null>((acc, d) => {
                if (d.v === null || d.v === undefined) return acc;
                return acc === null || Math.abs(d.v) > Math.abs(acc) ? d.v : acc;
              }, null);
              const breaching =
                worst !== null && budget !== undefined && Math.abs(worst) > budget;
              const devTitle = devs
                .map((d) =>
                  d.v === null || d.v === undefined
                    ? `${d.kind} unmeasured`
                    : `${d.kind} ${fmtTicks(d.v)} ticks`,
                )
                .join(" · ") + (budget !== undefined ? ` · budget ±${budget}` : "") + (breaching ? " — BREACHING" : "");
              return (
                <tr key={t.id} className="border-b border-hair last:border-b-0">
                  <td className="px-3 py-1 text-ink-soft">{fmtClock(t.exit_time)}</td>
                  <td className="px-3 py-1 text-ink-soft">{t.bot}</td>
                  <td className="px-3 py-1 text-ink">{t.symbol}</td>
                  <td className={"px-3 py-1 " + (t.side === "long" ? "text-up" : "text-down")}>
                    {t.side}
                  </td>
                  <td className="px-3 py-1 text-right tabular-nums text-ink-soft">
                    {t.entry_price} → {t.exit_price}
                  </td>
                  <td className="px-3 py-1 text-right tabular-nums font-medium">
                    <span className={won ? "text-up" : "text-down"}>
                      {won ? "+" : ""}
                      {t.pnl.toFixed(2)}
                    </span>
                  </td>
                  <td
                    className={
                      "px-3 py-1 text-right tabular-nums font-mono " +
                      (breaching ? "font-medium text-down" : "text-ink-faint")
                    }
                    title={devTitle}
                  >
                    {worst === null ? "—" : fmtTicks(worst)}
                  </td>
                  <td className="px-3 py-1 text-ink-faint">{t.mode}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ---- The rails strip -----------------------------------------------------

   Layer 0 in the terminal idiom: one hairline table, dense mono figures,
   status lamps as small squares like the engine lamp, consumed fractions
   as thin bars. Every number is the desk's own snapshot — the strip says
   when it was true (the asof), because rail state without a clock is a
   rumor. The honest empties are three different sentences again: no
   engine ever ran (no snapshots exist), the engine runs with an empty
   roster (the gate working — nothing is registered for paper), and rows
   exist (the strip itself). */

function RailLamp({ tripped, title }: { tripped: boolean; title: string }) {
  return (
    <span
      title={title}
      aria-hidden="true"
      className={"inline-block h-2 w-2 align-baseline " + (tripped ? "bg-down" : "bg-up")}
    />
  );
}

/** The consumed-fraction bar: a hairline box, the fill proportional to
    `fraction` of the rail's budget spent. Widths are clamped — a breach
    reads full, never overflowed, because over-100% IS the full bar. */
function FractionBar({ fraction, breached }: { fraction: number; breached: boolean }) {
  const pct = Math.max(0, Math.min(1, fraction)) * 100;
  return (
    <span className="inline-flex h-2.5 w-16 items-stretch border border-rule" aria-hidden="true">
      <span className={(breached ? "bg-down" : "bg-warn") + " block"} style={{ width: `${pct}%` }} />
    </span>
  );
}

function fmtCooldown(seconds: number): string {
  if (seconds <= 0) return "—";
  const m = Math.ceil(seconds / 60);
  if (m >= 60) return `${Math.floor(m / 60)}h${String(m % 60).padStart(2, "0")}m`;
  return `${m}m`;
}

export function RailsStrip({ rails }: { rails: TradingRailsStatus }) {
  const anyHalt = rails.manual_killswitch || rails.halt_sentinel;
  return (
    <div className="mb-3">
      {/* the desk-wide external halts first — they outrank every per-bot
          number below, and the strip says so before anything else */}
      {(rails.manual_killswitch || rails.halt_sentinel) && (
        <div className="mb-2 border-l-2 border-down bg-down-tint px-3 py-1.5 font-mono text-xs text-down">
          {rails.manual_killswitch && (
            <span className="mr-4">
              ■ manual kill-switch TRIPPED{rails.manual_killswitch_note ? ` — ${rails.manual_killswitch_note}` : ""}
            </span>
          )}
          {rails.halt_sentinel && (
            <span>■ halt sentinel file present — every entry halted</span>
          )}
        </div>
      )}
      {rails.bots.length === 0 ? (
        <p className="text-sm text-ink-soft">
          No rail state — the desk has written no rail snapshots yet.
          {!anyHalt &&
            " With zero strategies registered for paper, the roster is empty and the rails have nothing beneath them — the gate working, not a missing panel."}
        </p>
      ) : (
        <div className={cardClass + " overflow-x-auto"}>
          <table className="w-full border-collapse font-mono text-xs">
            <thead>
              <tr className="border-b border-rule text-[0.65rem] uppercase tracking-[0.1em] text-ink-soft">
                <th className="px-3 py-1.5 text-left font-medium">Bot</th>
                <th className="px-3 py-1.5 text-left font-medium">Kill</th>
                <th className="px-3 py-1.5 text-left font-medium">Drawdown</th>
                <th className="px-3 py-1.5 text-left font-medium">Daily loss</th>
                <th className="px-3 py-1.5 text-left font-medium">Streak</th>
                <th className="px-3 py-1.5 text-left font-medium">Cooldown</th>
                <th className="px-3 py-1.5 text-right font-medium" title="symbol / gross notional as percent of the hard caps — caps veto, never resize">Exp/cap</th>
                <th className="px-3 py-1.5 text-right font-medium">Vetoes</th>
                <th className="px-3 py-1.5 text-right font-medium">As of</th>
              </tr>
            </thead>
            <tbody>
              {rails.bots.map((b) => {
                const killTitle = b.kill_tripped
                  ? `tripped — drawdown ${(b.drawdown_pct * 100).toFixed(1)}% reached the ${(b.killswitch_dd_pct * 100).toFixed(0)}% rail; entries vetoed for the run's lifetime`
                  : `clear — drawdown ${(b.drawdown_pct * 100).toFixed(1)}% of the ${(b.killswitch_dd_pct * 100).toFixed(0)}% rail`;
                return (
                  <tr key={b.bot} className="border-b border-hair last:border-b-0">
                    <td className="px-3 py-1 text-ink">{b.bot}</td>
                    <td className="px-3 py-1">
                      <RailLamp tripped={b.kill_tripped} title={killTitle} />
                    </td>
                    <td className="px-3 py-1 tabular-nums text-ink" title={killTitle}>
                      {(b.drawdown_pct * 100).toFixed(1)}% / {(b.killswitch_dd_pct * 100).toFixed(0)}%
                    </td>
                    <td
                      className="px-3 py-1"
                      title={`${b.daily_loss.toFixed(2)} lost of the ${b.daily_loss_limit.toFixed(2)} daily budget${b.daily_breached ? " — breached, entries vetoed for the rest of the UTC day" : ""}`}
                    >
                      <span className="inline-flex items-center gap-2">
                        <FractionBar fraction={b.daily_loss_consumed} breached={b.daily_breached} />
                        <span className={"tabular-nums " + (b.daily_breached ? "text-down" : "text-ink")}>
                          {(b.daily_loss_consumed * 100).toFixed(0)}%
                        </span>
                      </span>
                    </td>
                    <td
                      className="px-3 py-1 tabular-nums text-ink"
                      title={`${b.loss_streak} consecutive losses of ${b.max_losses} that arm the cooldown`}
                    >
                      {b.loss_streak}/{b.max_losses}
                    </td>
                    <td
                      className={"px-3 py-1 tabular-nums " + (b.cooldown_remaining_s > 0 ? "text-warn" : "text-ink-faint")}
                      title={b.cooldown_remaining_s > 0 ? "cooldown after a loss streak — entries vetoed until it expires" : "no cooldown active"}
                    >
                      {fmtCooldown(b.cooldown_remaining_s)}
                    </td>
                    <td
                      className="px-3 py-1 text-right tabular-nums"
                      title={(() => {
                        if (!b.exposure || b.equity <= 0) return "exposure not snapshotted — the desk has written no rail state for this bot yet";
                        const symCap = b.equity * b.exposure.symbol_cap;
                        const grossCap = b.equity * b.exposure.gross_cap;
                        return `symbol notional ${b.exposure.instrument_notional.toFixed(0)} of the ${symCap.toFixed(0)} cap (${b.exposure.symbol_cap}× equity) · gross ${b.exposure.gross_notional.toFixed(0)} of the ${grossCap.toFixed(0)} cap (${b.exposure.gross_cap}× equity) — caps are hard: an entry breaching either is vetoed, never resized`;
                      })()}
                    >
                      {b.exposure && b.equity > 0 ? (
                        <span className="inline-flex flex-col items-end">
                          <span className={b.exposure.instrument_notional > b.equity * b.exposure.symbol_cap ? "font-medium text-down" : "text-up"}>
                            s {(b.exposure.instrument_notional / (b.equity * b.exposure.symbol_cap) * 100).toFixed(0)}%
                          </span>
                          <span className={b.exposure.gross_notional > b.equity * b.exposure.gross_cap ? "font-medium text-down" : "text-up"}>
                            g {(b.exposure.gross_notional / (b.equity * b.exposure.gross_cap) * 100).toFixed(0)}%
                          </span>
                        </span>
                      ) : (
                        <span className="text-ink-faint">—</span>
                      )}
                    </td>
                    <td className="px-3 py-1 text-right tabular-nums text-ink-soft">{b.vetoes_total}</td>
                    <td className="px-3 py-1 text-right text-ink-faint">
                      {b.asof ? fmtClock(b.asof) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {rails.recent_events.length > 0 && (
        <div className="mt-2">
          <h4 className={statLabelClass}>Rail events</h4>
          <div className="mt-1 space-y-0.5 font-mono text-[0.7rem] text-ink-soft">
            {rails.recent_events.slice(0, 8).map((e) => (
              <div key={e.id} className="flex flex-wrap gap-x-3" title={JSON.stringify(e.inputs)}>
                <span className="text-ink-faint">{e.created_at ? fmtClock(e.created_at) : "—"}</span>
                <span className="text-ink">{e.bot}</span>
                <span className={e.decision === "veto" ? "text-warn" : "text-down"}>{e.rail}</span>
                <span>{e.decision}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      {/* today's veto tape (slice 5): every entry the caps or rails refused
          since UTC midnight, densest-first. A day without vetoes is a day
          the rails were never tested — which is information too, so the
          strip says it rather than disappearing. */}
      <div className="mt-2">
        <h4 className={statLabelClass}>Today&apos;s vetoes</h4>
        {rails.vetoes_today.length === 0 ? (
          <p className="mt-1 font-mono text-[0.7rem] text-ink-faint">
            none — the rails were never tested today
          </p>
        ) : (
          <div className="mt-1 space-y-0.5 font-mono text-[0.7rem] text-ink-soft">
            {rails.vetoes_today.slice(0, 12).map((e) => {
              const reason =
                typeof e.inputs?.reason === "string"
                  ? e.inputs.reason
                  : typeof e.inputs?.detail === "string"
                    ? e.inputs.detail
                    : "";
              return (
                <div key={e.id} className="flex flex-wrap gap-x-3" title={JSON.stringify(e.inputs)}>
                  <span className="text-ink-faint">{e.created_at ? fmtClock(e.created_at) : "—"}</span>
                  <span className="text-ink">{e.bot}</span>
                  <span className="text-warn">{e.rail}</span>
                  {e.symbol && <span className="text-ink-faint">{e.symbol}</span>}
                  {reason && <span className="text-ink-soft">{reason}</span>}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

export const RailsStripForTest = RailsStrip;

/* ---- The divergence strip (slice 5) --------------------------------------

   Design §7's budget made visible: per bot, the measured fill drift against
   the declared budget, the missed-bar counters, and the distributional
   comparison's honest state. The strip exists only when bots exist — an
   engine that never ran has no divergence to measure, and the section's
   other honest-empty sentences already say why. */

export function DivergenceStrip({ divergence }: { divergence: TradingDivergenceStatus }) {
  if (divergence.bots.length === 0 && divergence.breach_events.length === 0) return null;
  return (
    <div className="mb-3">
      {divergence.bots.length > 0 && (
        <div className={cardClass + " overflow-x-auto"}>
          <table className="w-full border-collapse font-mono text-xs">
            <thead>
              <tr className="border-b border-rule text-[0.65rem] uppercase tracking-[0.1em] text-ink-soft">
                <th className="px-3 py-1.5 text-left font-medium">Bot</th>
                <th className="px-3 py-1.5 text-right font-medium">Max dev</th>
                <th className="px-3 py-1.5 text-right font-medium">Budget</th>
                <th className="px-3 py-1.5 text-right font-medium">Max lag</th>
                <th className="px-3 py-1.5 text-right font-medium">Missed</th>
                <th className="px-3 py-1.5 text-right font-medium">Fills</th>
                <th className="px-3 py-1.5 text-right font-medium">Breaches</th>
                <th className="px-3 py-1.5 text-left font-medium">Distribution</th>
              </tr>
            </thead>
            <tbody>
              {divergence.bots.map((b) => {
                const maxDev = b.fills.max_abs_dev_ticks;
                const breaching =
                  maxDev !== null &&
                  maxDev !== undefined &&
                  b.budget_dev_ticks !== null &&
                  b.budget_dev_ticks !== undefined &&
                  maxDev > b.budget_dev_ticks;
                const lagBreaching =
                  b.fills.max_entry_lag_bars !== null &&
                  b.fills.max_entry_lag_bars !== undefined &&
                  b.budget_entry_lag_bars !== null &&
                  b.budget_entry_lag_bars !== undefined &&
                  b.fills.max_entry_lag_bars > b.budget_entry_lag_bars;
                const missedBreaching =
                  b.missed_bars !== null &&
                  b.missed_bars !== undefined &&
                  b.budget_missed_bars !== null &&
                  b.budget_missed_bars !== undefined &&
                  b.missed_bars > b.budget_missed_bars;
                return (
                  <tr key={b.bot} className="border-b border-hair last:border-b-0">
                    <td className="px-3 py-1 text-ink">{b.bot}</td>
                    <td
                      className={"px-3 py-1 text-right tabular-nums " + (breaching ? "font-medium text-down" : "text-ink")}
                      title={
                        maxDev === null || maxDev === undefined
                          ? "no measured fills yet — each fill measures at write time, meaningful from n=1"
                          : `worst |deviation| over ${b.fills.measured_fills} measured fills, mean ${b.fills.mean_abs_dev_ticks?.toFixed(2) ?? "—"} ticks`
                      }
                    >
                      {maxDev === null || maxDev === undefined ? "—" : fmtTicks(maxDev)}
                    </td>
                    <td className="px-3 py-1 text-right tabular-nums text-ink-soft">
                      {b.budget_dev_ticks !== null && b.budget_dev_ticks !== undefined ? `±${b.budget_dev_ticks}` : "—"}
                    </td>
                    <td
                      className={"px-3 py-1 text-right tabular-nums " + (lagBreaching ? "font-medium text-down" : "text-ink")}
                      title="worst entry timing lag in bars against the signal(k-1)→close(k) contract — zero is parity"
                    >
                      {b.fills.max_entry_lag_bars ?? "—"}
                    </td>
                    <td
                      className={"px-3 py-1 text-right tabular-nums " + (missedBreaching ? "font-medium text-down" : "text-ink")}
                      title={
                        b.missed_bars === null || b.missed_bars === undefined
                          ? "no live snapshot — the counters die with the process"
                          : `${b.missed_bars} missed, ${b.backfilled_bars ?? 0} recovered by backfill`
                      }
                    >
                      {b.missed_bars ?? "—"}
                    </td>
                    <td className="px-3 py-1 text-right tabular-nums text-ink-soft">{b.fills.measured_fills}</td>
                    <td
                      className={
                        "px-3 py-1 text-right tabular-nums " + (b.fills.breaches > 0 ? "font-medium text-down" : "text-ink-faint")
                      }
                    >
                      {b.fills.breaches}
                    </td>
                    <td className="px-3 py-1 text-ink-soft" title={b.distribution_note}>
                      {b.distribution
                        ? `bt ${b.distribution.bt_mean_pnl.toFixed(2)} vs paper ${b.distribution.paper_mean_pnl.toFixed(2)}${
                            b.distribution.paper_mean_within_bt_p5_p95 ? " · within" : " · OUTSIDE"
                          }`
                        : b.distribution_note.includes("insufficient")
                          ? "n<30 — not meaningful yet"
                          : "no reference"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {divergence.breach_events.length > 0 && (
        <div className="mt-2">
          <h4 className={statLabelClass}>Budget breaches</h4>
          <div className="mt-1 space-y-0.5 font-mono text-[0.7rem] text-ink-soft">
            {divergence.breach_events.slice(0, 8).map((e) => {
              const inputs = e.inputs as Record<string, unknown>;
              const dims = Array.isArray(inputs.dimensions) ? (inputs.dimensions as string[]).join("+") : "";
              const detail =
                typeof inputs.dev_ticks === "number"
                  ? `${inputs.fill_kind} ${fmtTicks(inputs.dev_ticks as number)} ticks`
                  : typeof inputs.missed_bars === "number"
                    ? `${inputs.missed_bars} missed bars`
                    : "";
              return (
                <div key={e.id} className="flex flex-wrap gap-x-3" title={JSON.stringify(e.inputs)}>
                  <span className="text-ink-faint">{e.created_at ? fmtClock(e.created_at) : "—"}</span>
                  <span className="text-ink">{e.bot}</span>
                  <span className="text-down">{dims || e.rail}</span>
                  <span>{detail}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export const DivergenceStripForTest = DivergenceStrip;

function PositionsSection({
  positions,
  trades,
  fetchedAt,
  engineState,
  error,
  budgets,
}: {
  positions: TradingPosition[] | null;
  trades: TradingClosedTrade[] | null;
  fetchedAt: number;
  engineState: "offline" | "running" | null;
  error: string | null;
  budgets?: DivergenceBudgets;
}) {
  if (error) return <p className="text-down">{error}</p>;
  if (positions === null) return <p className="text-ink-soft">Loading…</p>;
  /* The three honest states, and they are three different sentences because
     they mean three different things: no engine ever ran (nothing to hold),
     the engine runs but holds nothing (flat is a position too — the zero
     position), and rows exist (the blotter itself). The engine lamp in the
     header is the same distinction at a glance; here it becomes words. */
  if (positions.length === 0) {
    if (engineState === "running") {
      return (
        <>
          <EmptyState title="Flat — no open positions">
            The engine is running and holds nothing. Flat is the zero position, not a missing
            dashboard: when a signal fills, the row appears here with its stop and target.
          </EmptyState>
          {trades && trades.length > 0 && <RecentTradesStrip trades={trades} budgets={budgets} />}
        </>
      );
    }
    return (
      <>
        <EmptyState title="No positions — the engine has not run">
          Open positions appear here the moment the desk's first entry fills — written to the
          database at the fill itself, never at end of run. Until then there is nothing to show,
          and nothing shown is better than something invented.
        </EmptyState>
        {trades && trades.length > 0 && <RecentTradesStrip trades={trades} budgets={budgets} />}
      </>
    );
  }
  return (
    <>
      <PositionsBlotter positions={positions} fetchedAt={fetchedAt} budgets={budgets} />
      {trades && trades.length > 0 && <RecentTradesStrip trades={trades} budgets={budgets} />}
    </>
  );
}

export const PositionsSectionForTest = PositionsSection;



/* ---- The kill-switch control ------------------------------------------------

   The first control surface of the terminal: not a readout but a HAND on the
   engine. It sits at instrument-panel rank — hairline frame, square lamp,
   mono voice — and its asymmetry is the design's: throwing the switch ON is
   one click, because halting entries is the safe failure and speed beats
   paperwork in that direction; re-arming is the dangerous direction, so it
   opens a confirm strip that demands the operator's sentence — the audit row
   the backend writes deserves a why, and the backend enforces it server-side
   (422) so this chrome is convenience, never the gate. */

export function KillSwitchControl({
  tripped,
  note,
  onChanged,
}: {
  tripped: boolean;
  note: string;
  onChanged: () => void;
}) {
  const [arming, setArming] = useState(false);
  const [armNote, setArmNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function throwSwitch() {
    setBusy(true);
    setError(null);
    try {
      await setKillSwitch(true, "");
      onChanged();
    } catch (e) {
      setError(apiError(e, "The kill-switch could not be thrown."));
    } finally {
      setBusy(false);
    }
  }

  async function reArm() {
    setBusy(true);
    setError(null);
    try {
      await setKillSwitch(false, armNote.trim());
      setArming(false);
      setArmNote("");
      onChanged();
    } catch (e) {
      setError(apiError(e, "The kill-switch could not be re-armed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={"border-l-2 border-y border-r px-3 py-2 " + (tripped ? "border-down bg-down-tint" : "border-rule bg-surface")}>
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 font-mono">
        <span className="flex items-center gap-2">
          <span className={"inline-block h-2.5 w-2.5 " + (tripped ? "bg-down" : "bg-up")} aria-hidden="true" />
          <span className="text-[0.7rem] uppercase tracking-[0.14em] text-ink-faint">Kill-switch</span>
        </span>
        <span className="text-xs text-ink">
          {tripped ? "TRIPPED — entries halted desk-wide; protective exits keep flowing" : "clear — entries flow"}
        </span>
        {tripped && note ? <span className="text-[0.7rem] text-ink-soft">{note}</span> : null}
        <span className="ml-auto">
          {tripped ? (
            <button
              type="button"
              className={btnClass}
              disabled={busy}
              onClick={() => {
                setArming((v) => !v);
                setError(null);
              }}
            >
              Re-arm…
            </button>
          ) : (
            <button
              type="button"
              className="rounded-sm bg-down px-3 py-1.5 font-mono text-xs font-medium tracking-wide text-on-accent transition hover:opacity-90 disabled:opacity-50"
              disabled={busy}
              title="Halts every new entry immediately, desk-wide. Protective exits are never refused — the switch stops entries, never safety."
              onClick={throwSwitch}
            >
              {busy ? "…" : "HALT ENTRIES"}
            </button>
          )}
        </span>
      </div>
      {arming && (
        <form
          className="mt-2 flex flex-wrap items-center gap-2 border-t border-hair pt-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (armNote.trim() && !busy) void reArm();
          }}
        >
          <label className="font-mono text-[0.7rem] uppercase tracking-[0.12em] text-ink-soft" htmlFor="ks-note">
            Why re-arm
          </label>
          <input
            id="ks-note"
            className={inputClass + " min-w-[24ch] flex-1"}
            value={armNote}
            onChange={(e) => setArmNote(e.target.value)}
            placeholder="the audit row carries this sentence — required"
            autoFocus
          />
          <button type="submit" className={btnClass} disabled={busy || armNote.trim().length === 0}>
            {busy ? "…" : "Confirm re-arm"}
          </button>
          <button
            type="button"
            className="rounded-sm border border-rule px-3 py-1.5 font-mono text-xs text-ink-soft transition hover:text-ink"
            onClick={() => {
              setArming(false);
              setError(null);
            }}
          >
            Cancel
          </button>
        </form>
      )}
      {error && <p className="mt-1 font-mono text-[0.7rem] text-down">{error}</p>}
    </div>
  );
}

export const KillSwitchControlForTest = KillSwitchControl;


/* ---- The lifecycle registry ----------------------------------------------

   Every version with its state, evidence chain, and paper track record. A
   version in paper carries the approval card the design mandates: human,
   one click, re-basing impossible. The card shows the exact record the human
   approves and the fingerprint that freezes it — a confirmation whose inputs
   moved answers 409, rendered here as the honest error state, never retried
   silently. candidate_live → live is never offered: the mandate is M5 and an
   offer the registry must refuse would be a lie in chrome. */

const STATE_TONE: Record<string, BadgeTone> = {
  research: "muted",
  validated: "muted",
  paper: "up",
  candidate_live: "up",
  live: "up",
};

function fmtPnl(v: number | null): string {
  if (v === null) return "—";
  return (v >= 0 ? "+" : "") + v.toFixed(2);
}

function ApprovalCard({
  version,
  onChanged,
}: {
  version: TradingRegistryVersion;
  onChanged: () => void;
}) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const rec = version.track_record;

  async function confirm() {
    setBusy(true);
    setError(null);
    setConflict(false);
    try {
      const result = await approveVersion(version.version_id, version.fingerprint, note.trim());
      setDone(result.state);
      onChanged();
    } catch (e) {
      if (isConflict(e)) {
        setConflict(true);
      }
      setError(apiError(e, "The approval could not be written."));
    } finally {
      setBusy(false);
    }
  }

  if (done !== null) {
    return (
      <div className="border-l-2 border-up bg-up-tint px-3 py-2 font-mono text-xs text-up">
        approved — state is now {done}
      </div>
    );
  }

  return (
    <div className="border-l-2 border-olive bg-surface px-3 py-2">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 font-mono text-xs">
        <span className="text-[0.7rem] uppercase tracking-[0.14em] text-ink-faint">
          Approval card — paper → candidate_live
        </span>
        <span className="tabular-nums text-ink" title="closed paper trades of this version">
          {rec.trades_count} trades
        </span>
        <span className={"tabular-nums " + ((rec.realized_pnl ?? 0) >= 0 ? "text-up" : "text-down")} title="realized pnl, net of fees">
          {fmtPnl(rec.realized_pnl)}
        </span>
        <span className="tabular-nums text-ink-soft" title="days between first and last exit">
          {rec.span_days === null ? "—" : rec.span_days.toFixed(1) + "d"} span
        </span>
        <span
          className={"tabular-nums " + (rec.drift_breaches > 0 ? "text-warn" : "text-ink-soft")}
          title="divergence-budget breaches on the events tape"
        >
          drift {rec.drift_breaches}/{rec.drift_fills_measured}
        </span>
      </div>
      <div className="mt-1 font-mono text-[0.7rem] text-ink-faint">
        fingerprint <span className="text-ink-soft">{version.fingerprint}</span> — freezes exactly this record;
        if anything moves, the confirmation is refused and the new record must be reviewed
      </div>
      <form
        className="mt-2 flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (!busy) void confirm();
        }}
      >
        <input
          className={inputClass + " min-w-[20ch] flex-1"}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="note for the approval row (optional)"
          aria-label="approval note"
        />
        <button type="submit" className={btnClass} disabled={busy}>
          {busy ? "…" : "Confirm approval"}
        </button>
      </form>
      {error && (
        <p className="mt-1 font-mono text-[0.7rem] text-down">
          {conflict ? "inputs moved — review the new track record: " : ""}
          {error}
        </p>
      )}
    </div>
  );
}

export const ApprovalCardForTest = ApprovalCard;

export function RegistrySection({
  versions,
  error,
  onChanged,
}: {
  versions: TradingRegistryVersion[] | null;
  error: string | null;
  onChanged: () => void;
}) {
  if (error) return <p className="text-down">{error}</p>;
  if (versions === null) return <p className="text-ink-soft">Loading…</p>;
  if (versions.length === 0) {
    return (
      <EmptyState title="The lifecycle owns nothing yet">
        No strategy version is registered. Versions appear here in state research the moment one is
        registered, move to paper on the validation gate&apos;s evidence alone, and reach candidate_live
        only through a human approval card — never automatically. Empty is the gate working, not a
        missing panel.
      </EmptyState>
    );
  }
  return (
    <div className="space-y-2">
      <div className={cardClass + " overflow-x-auto"}>
        <table className="w-full border-collapse font-mono text-xs">
          <thead>
            <tr className="border-b border-rule text-[0.65rem] uppercase tracking-[0.1em] text-ink-soft">
              <th className="px-3 py-1.5 text-left font-medium">Version</th>
              <th className="px-3 py-1.5 text-left font-medium">State</th>
              <th className="px-3 py-1.5 text-left font-medium">TF</th>
              <th className="px-3 py-1.5 text-left font-medium">Universe</th>
              <th className="px-3 py-1.5 text-right font-medium">Trades</th>
              <th className="px-3 py-1.5 text-right font-medium">PnL</th>
              <th className="px-3 py-1.5 text-left font-medium">Evidence</th>
              <th className="px-3 py-1.5 text-left font-medium">Since</th>
            </tr>
          </thead>
          <tbody>
            {versions.map((v) => (
              <tr key={v.version_id} className="border-b border-hair last:border-b-0">
                <td className="px-3 py-1 text-ink" title={`${v.name} — code ${v.code_hash}`}>
                  {v.strategy_key}-v{v.version}
                </td>
                <td className="px-3 py-1">
                  <Badge tone={STATE_TONE[v.state] ?? "muted"}>{v.state}</Badge>
                </td>
                <td className="px-3 py-1 text-ink-soft">{v.timeframe}</td>
                <td className="px-3 py-1 text-ink-soft">{v.universe.join(", ")}</td>
                <td className="px-3 py-1 text-right tabular-nums text-ink">{v.track_record.trades_count}</td>
                <td
                  className={
                    "px-3 py-1 text-right tabular-nums " + ((v.track_record.realized_pnl ?? 0) >= 0 ? "text-up" : "text-down")
                  }
                >
                  {fmtPnl(v.track_record.realized_pnl)}
                </td>
                <td className="px-3 py-1 text-ink-faint">{v.state_evidence || "—"}</td>
                <td className="px-3 py-1 text-ink-faint">{v.state_since ? fmtDay(v.state_since) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {versions
        .filter((v) => v.pending_transition === "candidate_live")
        .map((v) => (
          <ApprovalCard key={v.version_id} version={v} onChanged={onChanged} />
        ))}
    </div>
  );
}

export const RegistrySectionForTest = RegistrySection;


/* ---- Today's signals, including the rejected ones --------------------------

   The M3 acceptance surface: every emission the kernel recorded today,
   rejections first-class beside the entered ones. The outcome vocabulary is
   the backend's closed set; the badge colours follow the terminal's law —
   "veto:" is the rails working, which is the loss colour because a veto IS
   a refusal, never because the palette needed variety. Entered is the gain
   colour. Everything else is muted ink: a rejection by arithmetic (below
   confidence, no ATR, position already open) is information, not alarm.
   Rows carry the sizing chain in a keyboard-openable <details> — the chain
   is the drill-down, and a drill-down you cannot reach without a mouse is
   not one. */

function outcomeTone(outcome: string): BadgeTone {
  if (outcome === "entered") return "up";
  if (outcome.startsWith("veto:")) return "down";
  return "muted";
}

function outcomeLabel(outcome: string): string {
  return outcome.replace(/^veto:/, "veto · ").replace(/_/g, " ");
}

function ChainDetails({ details }: { details: Record<string, unknown> }) {
  const entries = Object.entries(details);
  if (entries.length === 0) return null;
  return (
    <details className="mt-0.5">
      <summary className="cursor-pointer text-[0.65rem] uppercase tracking-[0.1em] text-ink-faint focus:bg-olive-tint/40">
        sizing chain
      </summary>
      <dl className="mt-1 grid grid-cols-2 gap-x-4 gap-y-0.5 font-mono text-[0.7rem] sm:grid-cols-3">
        {entries.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-2">
            <dt className="text-ink-faint">{k}</dt>
            <dd className="tabular-nums text-ink">{typeof v === "number" ? v.toPrecision(6) : String(v)}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

export function SignalsTape({ data }: { data: TradingSignalsToday | null }) {
  if (data === null) return <p className="text-ink-soft">Loading…</p>;
  if (data.signals.length === 0) {
    return (
      <EmptyState title={`No emissions today (${data.date})`}>
        Nothing recorded yet — either the engine has not run today, or every strategy stayed silent.
        Both are facts the tape reports as nothing, never as an error. Rejected signals appear here
        exactly like entered ones, with the reason they were refused.
      </EmptyState>
    );
  }
  const counts = new Map<string, number>();
  for (const s of data.signals) counts.set(s.outcome, (counts.get(s.outcome) ?? 0) + 1);
  return (
    <div>
      <div className="mb-1 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[0.7rem] uppercase tracking-[0.12em] text-ink-soft">
        {Array.from(counts.entries()).map(([outcome, n]) => (
          <span key={outcome}>
            {outcomeLabel(outcome)} <span className="tabular-nums text-ink">{n}</span>
          </span>
        ))}
      </div>
      <div className={cardClass + " overflow-x-auto"}>
        <table className="w-full border-collapse font-mono text-xs">
          <thead>
            <tr className="border-b border-rule text-[0.65rem] uppercase tracking-[0.1em] text-ink-soft">
              <th className="px-3 py-1.5 text-left font-medium">Time</th>
              <th className="px-3 py-1.5 text-left font-medium">Bot</th>
              <th className="px-3 py-1.5 text-left font-medium">Side</th>
              <th className="px-3 py-1.5 text-right font-medium">Conf</th>
              <th className="px-3 py-1.5 text-left font-medium">Outcome</th>
            </tr>
          </thead>
          <tbody>
            {data.signals.map((s) => {
              const provenance = `signal bar ${s.bar_time ? new Date(s.bar_time).toLocaleString() : "not recorded"} · ${s.symbol} ${s.timeframe}`;
              return (
                <Fragment key={s.id}>
                  <tr
                    tabIndex={0}
                    className="border-b border-hair last:border-b-0 hover:bg-olive-tint/40 focus:bg-olive-tint/40"
                    title={provenance}
                  >
                    <td className="px-3 py-1 text-ink-soft">{s.created_at ? fmtClock(s.created_at) : "—"}</td>
                    <td className="px-3 py-1 text-ink">{s.bot}</td>
                    <td
                      className={
                        "px-3 py-1 " +
                        (s.side === "long" ? "text-up" : s.side === "short" ? "text-down" : "text-ink-soft")
                      }
                    >
                      {s.side}
                    </td>
                    <td className="px-3 py-1 text-right tabular-nums text-ink-soft">{s.confidence.toFixed(2)}</td>
                    <td className="px-3 py-1">
                      <Badge tone={outcomeTone(s.outcome)} title={provenance}>
                        {outcomeLabel(s.outcome)}
                      </Badge>
                    </td>
                  </tr>
                  {Object.keys(s.details).length > 0 && (
                    <tr className="border-b border-hair last:border-b-0">
                      <td colSpan={5} className="px-3 pb-1">
                        <ChainDetails details={s.details} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export const SignalsTapeForTest = SignalsTape;


/* ---- The per-strategy panels ----------------------------------------------

   One panel per bot the desk has evidence for: state in lifecycle (joined
   from the registry rows, absent honestly when the registry owns nothing),
   the cumulative realized net pnl curve, the paper-vs-backtest divergence
   reading, and the recent round-trips with the provenance drill-down —
   trade → signal → sizing chain, expandable per row. The panel union comes
   from three surfaces on purpose: a bot can have trades without being
   registered (pre-registry soak rows) and can be registered without ever
   trading, and both are facts the panel reports rather than merges away. */

function PanelTradeRow({ trade }: { trade: TradingClosedTrade }) {
  const chain = trade.signal_chain ?? {};
  const details = (chain.details ?? {}) as Record<string, unknown>;
  const hasChain = trade.signal_time !== null && trade.signal_time !== undefined;
  const provenance =
    trade.signal_time != null
      ? `signal bar ${new Date(trade.signal_time).toLocaleString()} · gate ${trade.gate_source}` +
        (Object.keys(details).length > 0 ? " · chain below" : " · emission not recorded — row predates the seam or the recording process died")
      : "no signal anchor — the row predates the recording seam";
  return (
    <div className="border-b border-hair py-1 last:border-b-0" title={provenance}>
      <div className="flex flex-wrap items-baseline gap-x-3 font-mono text-xs">
        <span className="text-ink-faint">{fmtClock(trade.exit_time)}</span>
        <span className={trade.side === "long" ? "text-up" : "text-down"}>{trade.side}</span>
        <span className="tabular-nums text-ink-soft">{trade.qty}</span>
        <span className={"tabular-nums font-medium " + (trade.pnl >= 0 ? "text-up" : "text-down")}>
          {trade.pnl >= 0 ? "+" : ""}
          {trade.pnl.toFixed(2)}
        </span>
        <span className="text-ink-faint">fees {trade.fees.toFixed(2)}</span>
        {hasChain && Object.keys(details).length === 0 && (
          <span className="text-[0.65rem] uppercase tracking-[0.1em] text-ink-faint">chain unrecorded</span>
        )}
      </div>
      {Object.keys(details).length > 0 && <ChainDetails details={details} />}
    </div>
  );
}

export function PerStrategyPanels({
  panels,
  registry,
  divergence,
  trades,
}: {
  panels: TradingStrategyPanel[] | null;
  registry: TradingRegistryVersion[] | null;
  divergence: TradingDivergenceStatus | null;
  trades: TradingClosedTrade[] | null;
}) {
  if (panels === null) return <p className="text-ink-soft">Loading…</p>;
  const bots = new Set<string>();
  for (const p of panels) bots.add(p.bot);
  for (const v of registry ?? []) bots.add(`${v.strategy_key}-v${v.version}`);
  for (const b of divergence?.bots ?? []) bots.add(b.bot);
  if (bots.size === 0) {
    return (
      <EmptyState title="No strategy has ever traded">
        The panels appear per bot the moment the desk settles its first round-trip or the registry
        registers a version — state in lifecycle, the realized pnl curve, the divergence reading and
        the trades with their provenance chain. With zero validated strategies the roster is honestly
        empty: the gate working, not a missing panel.
      </EmptyState>
    );
  }
  const registryByBot = new Map<string, TradingRegistryVersion>();
  for (const v of registry ?? []) registryByBot.set(`${v.strategy_key}-v${v.version}`, v);
  const divergenceByBot = new Map((divergence?.bots ?? []).map((b) => [b.bot, b]));
  const panelByBot = new Map(panels.map((p) => [p.bot, p]));
  const tradesByBot = new Map<string, TradingClosedTrade[]>();
  for (const t of trades ?? []) {
    const list = tradesByBot.get(t.bot) ?? [];
    list.push(t);
    tradesByBot.set(t.bot, list);
  }
  return (
    <div className="space-y-3">
      {Array.from(bots).sort().map((bot) => {
        const panel = panelByBot.get(bot);
        const reg = registryByBot.get(bot);
        const div = divergenceByBot.get(bot);
        const botTrades = tradesByBot.get(bot) ?? [];
        const curve = panel?.curve ?? [];
        return (
          <div key={bot} className="border border-rule">
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b border-hair px-3 py-1.5 font-mono text-xs">
              <span className="font-medium text-ink">{bot}</span>
              {reg ? (
                <Badge tone={STATE_TONE[reg.state] ?? "muted"} title={`in lifecycle since ${reg.state_since ?? "unrecorded"} — ${reg.state_evidence || "no evidence note"}`}>
                  {reg.state}
                </Badge>
              ) : (
                <span className="text-[0.65rem] uppercase tracking-[0.1em] text-ink-faint" title="trades exist for this bot but no registry row carries its name — pre-registry or unregistered evidence">
                  unregistered
                </span>
              )}
              {panel !== undefined && (
                <span className="tabular-nums text-ink-soft" title="settled round-trips the desk wrote">
                  {panel.trades_count} trades
                </span>
              )}
              {div !== undefined && div.fills.measured_fills > 0 && (
                <span
                  className={"tabular-nums " + (div.fills.breaches > 0 ? "text-warn" : "text-ink-soft")}
                  title={`paper-vs-backtest divergence: mean |dev| ${div.fills.mean_abs_dev_ticks?.toFixed(2) ?? "—"} ticks over ${div.fills.measured_fills} measured fills, ${div.fills.breaches} budget breaches`}
                >
                  drift {div.fills.mean_abs_dev_ticks?.toFixed(2) ?? "—"}t · {div.fills.breaches} breaches
                </span>
              )}
            </div>
            <div className="grid gap-3 px-3 py-2 lg:grid-cols-2">
              <div>
                <h4 className={statLabelClass}>Cumulative realized net pnl</h4>
                <div className="mt-1">
                  {curve.length < 2 ? (
                    <p className="py-6 text-center text-sm text-ink-soft">
                      {curve.length === 0
                        ? "No settled round-trips — a curve of zero trades is not a curve."
                        : "One settled trade — a single point is not a curve."}
                    </p>
                  ) : (
                    <EquityChart
                      data={fromApiCurve(curve)}
                      height={160}
                      emptyText="The recorded curve has fewer than two distinct points — not enough to draw."
                    />
                  )}
                </div>
              </div>
              <div>
                <h4 className={statLabelClass}>Recent round-trips</h4>
                <div className="mt-1">
                  {botTrades.length === 0 ? (
                    <p className="py-6 text-center text-sm text-ink-soft">
                      Nothing settled yet — the first close writes the first row.
                    </p>
                  ) : (
                    botTrades.slice(0, 8).map((t) => <PanelTradeRow key={t.id} trade={t} />)
                  )}
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export const PerStrategyPanelsForTest = PerStrategyPanels;


/* ---- The validation queue and the model registry ---------------------------

   RESEARCH surfaces: who waits at the gates, and what the gate said when it
   refused. The failure rows carry the reasons verbatim — the gate's own
   sentences, never paraphrased, because a paraphrase is an opinion about
   evidence. */

export function ValidationQueuePanel({ queue }: { queue: TradingValidationQueue | null }) {
  if (queue === null) return <p className="text-ink-soft">Loading…</p>;
  if (queue.awaiting.length === 0 && queue.failures.length === 0) {
    return (
      <EmptyState title="Nothing in flight, nothing failed">
        No version sits in research state and no validation has failed — a pipeline with nothing to
        answer for right now. Versions appear here the moment one is registered, and failures stay
        visible with the reasons the gate wrote.
      </EmptyState>
    );
  }
  return (
    <div className="space-y-3">
      {queue.awaiting.length > 0 && (
        <div>
          <h4 className={statLabelClass}>Awaiting the gates</h4>
          <div className="mt-1 space-y-0.5 font-mono text-xs">
            {queue.awaiting.map((item) => (
              <div
                key={`a-${item.version_id}`}
                tabIndex={0}
                className="flex flex-wrap items-baseline gap-x-3 border-b border-hair px-2 py-1 last:border-b-0 hover:bg-olive-tint/40 focus:bg-olive-tint/40"
                title={`registered ${item.created_at ? fmtDay(item.created_at) : "unrecorded"} — no validation verdict exists for this version yet`}
              >
                <span className="text-ink">
                  {item.strategy_key}-v{item.version}
                </span>
                <span className="text-ink-soft">{item.timeframe}</span>
                <Badge tone="muted">research</Badge>
                <span className="text-ink-faint">no verdict yet — the gate has not run on this version</span>
              </div>
            ))}
          </div>
        </div>
      )}
      {queue.failures.length > 0 && (
        <div>
          <h4 className={statLabelClass}>Failures, with the gate&apos;s reasons</h4>
          <div className="mt-1 space-y-1">
            {queue.failures.map((item) => (
              <div
                key={`f-${item.validation_id}`}
                tabIndex={0}
                className="border-l-2 border-down bg-down-tint/40 px-3 py-1.5 focus:bg-down-tint/60"
                title={`validation #${item.validation_id} · ${item.created_at ? fmtDay(item.created_at) : ""} · ${item.trades_n} trades of the required ${item.min_trades_required}`}
              >
                <div className="flex flex-wrap items-baseline gap-x-3 font-mono text-xs">
                  <span className="text-ink">{item.bot}</span>
                  <span className="text-ink-soft">{item.timeframe}</span>
                  <Badge tone="down">{item.verdict ?? "rejected"}</Badge>
                  {item.permutation_p !== null && (
                    <span className="tabular-nums text-ink-soft" title="permutation test p-value">
                      p {fmtP(item.permutation_p)}
                    </span>
                  )}
                  <span className="tabular-nums text-ink-faint" title="trades in the run against the gate's minimum">
                    {item.trades_n}/{item.min_trades_required} trades
                  </span>
                </div>
                {item.reasons.length > 0 && (
                  <ul className="mt-0.5 space-y-0.5 font-mono text-[0.7rem] text-ink-soft">
                    {item.reasons.map((r) => (
                      <li key={r}>· {r}</li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export const ValidationQueuePanelForTest = ValidationQueuePanel;


export function ModelRegistryPanel({ registry }: { registry: TradingModelRegistry | null }) {
  if (registry === null) return <p className="text-ink-soft">Loading…</p>;
  return (
    <div>
      {registry.models.length === 0 ? (
        <EmptyState title="No model has ever trained">
          The ML gate&apos;s registry is empty: no retrain cycle has written a champion or a rejected
          challenger. When one does, the OOS metrics the promotion gate measured appear here beside
          the role — champion, challenger or retired.
        </EmptyState>
      ) : (
        <div className={cardClass + " overflow-x-auto"}>
          <table className="w-full border-collapse font-mono text-xs">
            <thead>
              <tr className="border-b border-rule text-[0.65rem] uppercase tracking-[0.1em] text-ink-soft">
                <th className="px-3 py-1.5 text-left font-medium">Model</th>
                <th className="px-3 py-1.5 text-left font-medium">Role</th>
                <th className="px-3 py-1.5 text-right font-medium">OOS acc</th>
                <th className="px-3 py-1.5 text-right font-medium">OOS prec long</th>
                <th className="px-3 py-1.5 text-right font-medium">Window</th>
                <th className="px-3 py-1.5 text-right font-medium">PSI drift</th>
                <th className="px-3 py-1.5 text-left font-medium">Trained</th>
              </tr>
            </thead>
            <tbody>
              {registry.models.map((m) => (
                <tr
                  key={m.id}
                  tabIndex={0}
                  className="border-b border-hair last:border-b-0 hover:bg-olive-tint/40 focus:bg-olive-tint/40"
                  title={m.notes || `model ${m.id}`}
                >
                  <td className="px-3 py-1 text-ink">
                    {m.name} v{m.version}
                  </td>
                  <td className="px-3 py-1">
                    <Badge
                      tone={m.role === "champion" ? "up" : "muted"}
                      title={m.role === "champion" ? "the gate's live weights" : m.role === "challenger" ? "newest version of its name, not the champion" : "superseded"}
                    >
                      {m.role}
                    </Badge>
                  </td>
                  <td className="px-3 py-1 text-right tabular-nums text-ink">{m.oos_accuracy.toFixed(3)}</td>
                  <td className="px-3 py-1 text-right tabular-nums text-ink">{m.oos_precision_long.toFixed(3)}</td>
                  <td className="px-3 py-1 text-right tabular-nums text-ink-soft">{m.train_window_days}d</td>
                  <td className="px-3 py-1 text-right text-ink-faint" title={registry.psi_note}>
                    {m.psi_drift === null ? "—" : m.psi_drift.toFixed(3)}
                  </td>
                  <td className="px-3 py-1 text-ink-faint">{m.trained_at ? fmtDay(m.trained_at) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-1 font-mono text-[0.7rem] text-ink-faint">{registry.psi_note}</p>
    </div>
  );
}

export const ModelRegistryPanelForTest = ModelRegistryPanel;


/* ---- The page ------------------------------------------------------------ */


/* ---- The mandate machinery (M5) -------------------------------------------

   Machinery, not chrome: the mandate rows, the order cards. Compact on
   purpose — the audit document is the M5 deliverable that matters, this
   surface exists so the machinery is visible and honest. The empty state
   is the design's expected end state and says so: no mandate exists, the
   live path is unbuilt by design. */

function fmtCountdown(expiresAt: string | null): string {
  if (!expiresAt) return "—";
  const ms = new Date(expiresAt).getTime() - Date.now();
  if (ms <= 0) return "expired";
  const days = ms / 86400000;
  if (days >= 1) return `${Math.floor(days)}d ${Math.floor((days % 1) * 24)}h`;
  return `${Math.floor(ms / 3600000)}h ${Math.floor((ms % 3600000) / 60000)}m`;
}

export function MandateSection({
  mandates,
  cards,
  error,
}: {
  mandates: TradingMandate[] | null;
  cards: TradingOrderCard[] | null;
  error: string | null;
}) {
  if (error) return <p className="text-down">{error}</p>;
  if (mandates === null) return <p className="text-ink-soft">Loading…</p>;
  const empty = mandates.length === 0;
  return (
    <div className="space-y-2">
      {empty ? (
        <EmptyState title="No mandate exists — the live path is unbuilt by design">
          A mandate is the human&apos;s immutable written consent: hard caps on order size, exposure,
          instruments and daily count, inside a consent window that expires. None has ever been
          granted. Live trading is unreachable through every independent layer — no mandate, no audit
          signoff, no live adapter — and this emptiness is the machinery working, not a missing panel.
        </EmptyState>
      ) : (
        <div className={cardClass + " overflow-x-auto"}>
          <table className="w-full border-collapse font-mono text-xs">
            <thead>
              <tr className="border-b border-rule text-[0.65rem] uppercase tracking-[0.1em] text-ink-soft">
                <th className="px-3 py-1.5 text-left font-medium">Mandate</th>
                <th className="px-3 py-1.5 text-left font-medium">Version</th>
                <th className="px-3 py-1.5 text-right font-medium">Max order</th>
                <th className="px-3 py-1.5 text-right font-medium">Max exposure</th>
                <th className="px-3 py-1.5 text-left font-medium">Instruments</th>
                <th className="px-3 py-1.5 text-right font-medium">Trades/day</th>
                <th className="px-3 py-1.5 text-left font-medium">Consent</th>
                <th className="px-3 py-1.5 text-left font-medium">Expires in</th>
              </tr>
            </thead>
            <tbody>
              {mandates.map((m) => (
                <tr key={m.id} className="border-b border-hair last:border-b-0">
                  <td className="px-3 py-1 text-ink" title={`integrity digest ${m.mandate_hash}`}>
                    #{m.id}
                    {!m.integrity_ok && (
                      <span className="text-down" title="the row's caps no longer match their digest — tampered or corrupt">
                        {" "}⚠ corrupt
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-1 text-ink-soft">v{m.version_id}</td>
                  <td className="px-3 py-1 text-right tabular-nums text-ink">{m.max_order_notional}</td>
                  <td className="px-3 py-1 text-right tabular-nums text-ink">{m.max_exposure}</td>
                  <td className="px-3 py-1 text-ink-soft">{m.instruments.join(", ")}</td>
                  <td className="px-3 py-1 text-right tabular-nums text-ink">{m.max_trades_per_day}</td>
                  <td className="px-3 py-1">
                    <Badge tone={m.active ? "up" : "muted"}>{m.active ? "active" : "expired"}</Badge>
                  </td>
                  <td
                    className="px-3 py-1 text-ink-faint"
                    title={m.expires_at ? `consent expires ${m.expires_at}` : "no expiry recorded"}
                  >
                    {fmtCountdown(m.expires_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {cards !== null && cards.length > 0 && (
        <div className={cardClass + " overflow-x-auto"}>
          <table className="w-full border-collapse font-mono text-xs">
            <thead>
              <tr className="border-b border-rule text-[0.65rem] uppercase tracking-[0.1em] text-ink-soft">
                <th className="px-3 py-1.5 text-left font-medium">Card</th>
                <th className="px-3 py-1.5 text-left font-medium">Intent</th>
                <th className="px-3 py-1.5 text-right font-medium">Notional</th>
                <th className="px-3 py-1.5 text-left font-medium">Mandate</th>
                <th className="px-3 py-1.5 text-left font-medium">State</th>
                <th className="px-3 py-1.5 text-left font-medium">Decision</th>
              </tr>
            </thead>
            <tbody>
              {cards.map((c) => (
                <tr key={c.id} className="border-b border-hair last:border-b-0">
                  <td className="px-3 py-1 text-ink" title={`fingerprint ${c.fingerprint}`}>
                    #{c.id}
                  </td>
                  <td className="px-3 py-1 text-ink-soft">
                    {c.side} {c.symbol}
                  </td>
                  <td className="px-3 py-1 text-right tabular-nums text-ink">{c.notional}</td>
                  <td className="px-3 py-1 text-ink-faint">{c.mandate_id !== null ? `#${c.mandate_id}` : "none"}</td>
                  <td className="px-3 py-1">
                    <Badge tone={c.state === "released" ? "up" : c.state === "denied" ? "down" : "muted"}>{c.state}</Badge>
                  </td>
                  <td className="px-3 py-1 text-ink-faint" title={c.decision_note}>
                    {c.decision_note.length > 60 ? c.decision_note.slice(0, 57) + "…" : c.decision_note || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export const MandateSectionForTest = MandateSection;

export default function Trading() {

  const [status, setStatus] = useState<TradingStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [runs, setRuns] = useState<BacktestRun[] | null>(null);
  const [runsError, setRunsError] = useState<string | null>(null);
  const [positions, setPositions] = useState<TradingPosition[] | null>(null);
  const [trades, setTrades] = useState<TradingClosedTrade[] | null>(null);
  const [positionsAt, setPositionsAt] = useState<number>(0);
  const [positionsError, setPositionsError] = useState<string | null>(null);
  const [strategies, setStrategies] = useState<TradingStrategy[] | null>(null);
  const [strategiesError, setStrategiesError] = useState<string | null>(null);
  const [rails, setRails] = useState<TradingRailsStatus | null>(null);
  const [divergence, setDivergence] = useState<TradingDivergenceStatus | null>(null);
  const [registry, setRegistry] = useState<TradingRegistryVersion[] | null>(null);
  const [registryError, setRegistryError] = useState<string | null>(null);
  const [railsReloadKey, setRailsReloadKey] = useState(0);
  const [registryReloadKey, setRegistryReloadKey] = useState(0);
  const [signalsToday, setSignalsToday] = useState<TradingSignalsToday | null>(null);
  const [panels, setPanels] = useState<TradingStrategyPanel[] | null>(null);
  const [queue, setQueue] = useState<TradingValidationQueue | null>(null);
  const [models, setModels] = useState<TradingModelRegistry | null>(null);
  const [mandates, setMandates] = useState<TradingMandate[] | null>(null);
  const [orderCards, setOrderCards] = useState<TradingOrderCard[] | null>(null);
  const [mandatesError, setMandatesError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getTradingStatus()
      .then((s) => alive && setStatus(s))
      .catch((e) => alive && setStatusError(apiError(e, "The trading status could not be loaded.")));
    getBacktestRuns()
      .then((r) => alive && setRuns(r))
      .catch((e) => alive && setRunsError(apiError(e, "The backtest record could not be loaded.")));
    getTradingStrategies()
      .then((s) => alive && setStrategies(s))
      .catch((e) => alive && setStrategiesError(apiError(e, "The strategies registry could not be loaded.")));
    getTradingPositions()
      .then((p) => {
        if (!alive) return;
        setPositions(p);
        setPositionsAt(Date.now());
      })
      .catch((e) => alive && setPositionsError(apiError(e, "The positions could not be loaded.")));
    getTradingRails()
      .then((r) => alive && setRails(r))
      .catch(() => {
        /* the strip is rail evidence; its failure renders as no strip,
           never as a blank page over the positions beside it */
      });
    getTradingRegistry()
      .then((v) => alive && setRegistry(v))
      .catch((e) => alive && setRegistryError(apiError(e, "The lifecycle registry could not be loaded.")));
    getRecentTrades()
      .then((t) => alive && setTrades(t))
      .catch(() => {
        /* the strip is supplementary evidence; its failure must not blank
           the positions blotter beside it — absence renders as no strip */
      });
    getTradingDivergence()
      .then((d) => alive && setDivergence(d))
      .catch(() => {
        /* same discipline as the other evidence strips — its failure
           renders as no strip, never as a blank page */
      });
    getTradingSignalsToday()
      .then((s) => alive && setSignalsToday(s))
      .catch(() => {
        /* supplementary evidence — failure renders as no tape, never a blank page */
      });
    getStrategyPanels()
      .then((p) => alive && setPanels(p))
      .catch(() => {
        /* same discipline */
      });
    getValidationQueue()
      .then((q) => alive && setQueue(q))
      .catch(() => {
        /* same discipline */
      });
    getModelRegistry()
      .then((m) => alive && setModels(m))
      .catch(() => {
        /* same discipline */
      });
    getTradingMandates()
      .then((m) => alive && setMandates(m))
      .catch((e) => alive && setMandatesError(apiError(e, "The mandates could not be loaded.")));
    getTradingOrderCards()
      .then((c) => alive && setOrderCards(c))
      .catch(() => {
        /* supplementary — failure renders as no card table, never a blank section */
      });
    return () => {
      alive = false;
    };
  }, [railsReloadKey, registryReloadKey]);

  return (
    <div className="space-y-8">
      <EngineHeader status={status} error={statusError} />
      {rails !== null && (
        <KillSwitchControl
          tripped={rails.manual_killswitch}
          note={rails.manual_killswitch_note}
          onChanged={() => setRailsReloadKey((k) => k + 1)}
        />
      )}

      <Section
        title="Positions & risk"
        hint="Open positions as the desk wrote them at the fill, ages ticking. Each row's stop and target ARE the open orders — the resting protective brackets the kernel holds for the position, submitted at the entry fill. Settled round-trips below as the desk's recent evidence."
      >
        {rails !== null && <RailsStrip rails={rails} />}
        {divergence !== null && <DivergenceStrip divergence={divergence} />}
        <PositionsSection
          positions={positions}
          trades={trades}
          fetchedAt={positionsAt}
          engineState={status?.engine_state ?? null}
          error={positionsError}
          budgets={divergenceBudgetsOf(divergence)}
        />
        {signalsToday !== null && (
          <div className="mt-4">
            <h4 className={statLabelClass}>Today&apos;s signals — rejections included</h4>
            <div className="mt-1">
              <SignalsTape data={signalsToday} />
            </div>
          </div>
        )}
        <div className="mt-4">
          <h4 className={statLabelClass}>Per strategy</h4>
          <div className="mt-1">
            <PerStrategyPanels
              panels={panels}
              registry={registry}
              divergence={divergence}
              trades={trades}
            />
          </div>
        </div>
      </Section>

      <Section
        title="Lifecycle"
        hint="Every registered strategy version with its state, evidence chain and paper track record. Versions in paper carry the approval card — human, one click, re-basing impossible. A confirmation whose inputs moved is refused, and the new record must be reviewed."
      >
        <RegistrySection
          versions={registry}
          error={registryError}
          onChanged={() => setRegistryReloadKey((k) => k + 1)}
        />
      </Section>

      <Section
        title="Mandates & order cards"
        hint="The M5 mandate machinery — built, never armed. A mandate is the human's immutable consent to hard caps; an order card is a per-order human approval carrying the full decision chain. Both surfaces are honest-empty today: no mandate exists and the live path is unbuilt by design."
      >
        <MandateSection mandates={mandates} cards={orderCards} error={mandatesError} />
      </Section>

      <Section
        title="Research"
        hint="Every backtest the research pipeline finished, with the validation gate's verdict: the permutation test, the bootstrap Sharpe interval and walk-forward consistency."
        note="Figures come from the run row itself — hover any number for its run and date. A run without validation shows dashes, not zeros."
      >
        <div className="mb-4">
          <h4 className={statLabelClass}>Sweep ledger</h4>
          <div className="mt-1">
            <LedgerBrowser />
          </div>
        </div>
        <ResearchSection runs={runs} error={runsError} />
        <div className="mt-4">
          <h4 className={statLabelClass}>Validation queue</h4>
          <div className="mt-1">
            <ValidationQueuePanel queue={queue} />
          </div>
        </div>
        <div className="mt-4">
          <h4 className={statLabelClass}>Model registry</h4>
          <div className="mt-1">
            <ModelRegistryPanel registry={models} />
          </div>
        </div>
      </Section>

      <Section
        title="Strategies"
        hint="The registry of ported strategies. Research-only means exactly that: the code exists, the evidence is gathered, no capital has ever followed it."
      >
        <StrategiesSection strategies={strategies} error={strategiesError} />
      </Section>
    </div>
  );
}
