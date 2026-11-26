import { Fragment, useEffect, useState } from "react";
import {
  getBacktestRun,
  getBacktestRuns,
  getRecentTrades,
  getTradingPositions,
  getTradingStatus,
  getTradingStrategies,
  type BacktestRun,
  type BacktestRunDetail,
  type RunMetrics,
  type RunProvenance,
  type TradingClosedTrade,
  type TradingPosition,
  type TradingStatus,
  type TradingStrategy,
} from "../api/trading";
import { Blotter } from "../viz/Blotter";
import { EquityChart } from "../viz/EquityChart";
import { fromApiCurve } from "../viz/equityData";
import { EmptyState } from "./Emblem";
import { apiError, cardClass, Section, statLabelClass } from "./ui";
import {
  engineReading,
  engineTone,
  fmtCi,
  fmtFolds,
  fmtP,
  runsNewestFirst,
  verdictBadge,
  type BadgeTone,
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
}: {
  positions: TradingPosition[];
  fetchedAt: number;
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
function RecentTradesStrip({ trades }: { trades: TradingClosedTrade[] }) {
  if (trades.length === 0) return null;
  return (
    <div className="mt-3">
      <h4 className={statLabelClass}>Recently settled</h4>
      <div className={cardClass + " mt-1 overflow-x-auto"}>
        <table className="w-full border-collapse text-xs">
          <tbody>
            {trades.map((t) => {
              const won = t.pnl >= 0;
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

function PositionsSection({
  positions,
  trades,
  fetchedAt,
  engineState,
  error,
}: {
  positions: TradingPosition[] | null;
  trades: TradingClosedTrade[] | null;
  fetchedAt: number;
  engineState: "offline" | "running" | null;
  error: string | null;
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
          {trades && trades.length > 0 && <RecentTradesStrip trades={trades} />}
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
        {trades && trades.length > 0 && <RecentTradesStrip trades={trades} />}
      </>
    );
  }
  return (
    <>
      <PositionsBlotter positions={positions} fetchedAt={fetchedAt} />
      {trades && trades.length > 0 && <RecentTradesStrip trades={trades} />}
    </>
  );
}

export const PositionsSectionForTest = PositionsSection;


/* ---- The page ------------------------------------------------------------ */

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
    getRecentTrades()
      .then((t) => alive && setTrades(t))
      .catch(() => {
        /* the strip is supplementary evidence; its failure must not blank
           the positions blotter beside it — absence renders as no strip */
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="space-y-8">
      <EngineHeader status={status} error={statusError} />

      <Section
        title="Positions & risk"
        hint="Open positions as the desk wrote them at the fill — the protective levels each row carries, ages ticking. Settled round-trips below as the desk's recent evidence."
      >
        <PositionsSection
          positions={positions}
          trades={trades}
          fetchedAt={positionsAt}
          engineState={status?.engine_state ?? null}
          error={positionsError}
        />
      </Section>

      <Section
        title="Research"
        hint="Every backtest the research pipeline finished, with the validation gate's verdict: the permutation test, the bootstrap Sharpe interval and walk-forward consistency."
        note="Figures come from the run row itself — hover any number for its run and date. A run without validation shows dashes, not zeros."
      >
        <ResearchSection runs={runs} error={runsError} />
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
