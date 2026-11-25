import { Fragment, useEffect, useState } from "react";
import {
  getBacktestRun,
  getBacktestRuns,
  getTradingStatus,
  getTradingStrategies,
  type BacktestRun,
  type BacktestRunDetail,
  type RunMetrics,
  type RunProvenance,
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
   architecture (hedge-fund-os.md §8) lays it out, at the stage the system is
   actually at: the research record first, because it EXISTS; positions and
   risk as honest placeholders, because the paper engine is an M3 milestone
   and a page pretending otherwise would be a demo, not a dashboard.

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


/* ---- The page ------------------------------------------------------------ */

export default function Trading() {

  const [status, setStatus] = useState<TradingStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [runs, setRuns] = useState<BacktestRun[] | null>(null);
  const [runsError, setRunsError] = useState<string | null>(null);
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
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="space-y-8">
      <EngineHeader status={status} error={statusError} />

      <Section
        title="Positions & risk"
        hint="Open positions, order intents and the risk rails — kill-switch, daily loss, exposure caps."
      >
        <EmptyState title="No engine running">
          Paper trading starts at milestone M3. Until the engine runs there is nothing to show here
          — and nothing shown is better than something invented.
        </EmptyState>
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
