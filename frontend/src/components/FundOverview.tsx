import { useEffect, useState } from "react";
import type { OverviewFund } from "../api/overview";
import { getFundOverview, putTradingAccount } from "../api/overview";
import { getInstitutions } from "../api/institutions";
import { money } from "./money";
import { NO_DESK_EQUITY, engineStamp, gapDirection, reconciliationReading } from "./reconciliation";

/* The consolidated fund overview (design §8, rule D13): the trading desk's
   own figure BESIDE the ledger's, never summed into net worth — the broker
   statement already contains the money, so adding the engine's reading would
   count it twice. The reconciliation line is the gap between the two
   statements about that money, with its dates, because a gap against last
   month's statement is time plus divergence and never divergence alone.

   Every absence is first-class: an engine that never ran, a mapping never
   declared, a dollar no rate converts. The row says what is missing rather
   than printing a fabricated zero. */

function Cell({ label, value, title, first, wide }: {
  label: string;
  value: React.ReactNode;
  title?: string;
  first?: boolean;
  wide?: boolean;
}) {
  return (
    <div
      title={title}
      className={"px-3 py-2 " + (first ? "" : "border-l border-hair ") + (wide ? "col-span-2 sm:col-span-2" : "")}
    >
      <dt className="font-mono text-[0.6rem] uppercase tracking-[0.14em] text-ink-faint">{label}</dt>
      <dd className="mt-0.5 font-mono text-sm tabular-nums">{value}</dd>
    </div>
  );
}

/** The rows themselves, given the payload — the component the page composes
    and the one the render tests pin, so the fetch never enters a test.

    `institutions` + `onDeclare` arm the one repair the empty state can offer:
    a reconciliation that cannot start for want of a declared trading account
    gets the declaration control inline, because a state that says what is
    missing and offers no way to fix it is a dead end wearing an explanation. */
export function FundOverviewRows({ overview, institutions, onDeclare }: {
  overview: OverviewFund;
  institutions?: { id: number; name: string }[];
  onDeclare?: (institutionId: number) => Promise<void> | void;
}) {
  const base = overview.total_wealth.base_currency;
  const inBase = money(base);
  const equity = overview.trading_equity;
  const recon = overview.reconciliation;
  const reading = reconciliationReading(recon);
  // The engine counts in its own unit; the converted figure beside it only
  // when a rate made one, and never a pass-through of dollars as euro.
  const inEngineUnit = equity.currency ? money(equity.currency) : null;

  return (
    <section aria-label="Trading desk">
      <p className="font-mono text-[0.65rem] font-medium uppercase tracking-[0.14em] text-ink-soft">
        Trading desk
        <span className="ml-3 normal-case tracking-normal text-ink-faint">
          engine-reported — beside the ledger, never part of net worth
        </span>
      </p>

      <dl className="mt-2 grid grid-cols-2 border-y border-hair sm:grid-cols-4">
        {equity.available && equity.value != null ? (
          <>
            <Cell
              first
              label="Engine equity"
              value={
                <>
                  {inEngineUnit?.format(equity.value)}
                  {equity.value_base != null && base !== equity.currency && (
                    <span className="ml-1.5 text-ink-soft">≈ {inBase.format(equity.value_base)}</span>
                  )}
                </>
              }
              title={`The engine's own reading of the desk, from ${equity.source}`}
            />
            <Cell
              label="As of"
              value={<span className="text-ink-soft">{equity.as_of ? engineStamp(equity.as_of) : "—"}</span>}
              title="The timestamp of the latest equity row the engine wrote (UTC)"
            />
          </>
        ) : (
          <Cell
            first
            wide
            label="Engine equity"
            value={<span className="text-ink-faint">{NO_DESK_EQUITY}</span>}
            title="An engine that never wrote an equity row is a state of the desk, not an error"
          />
        )}

        {reading.kind === "measured" && recon.gap != null ? (
          <>
            <Cell
              label="Reconciliation"
              value={
                <span title={`Ledger statement ${inBase.format(recon.statement_total ?? 0)} − engine ${inBase.format(recon.engine_equity_base ?? 0)}`}>
                  {recon.gap >= 0 ? "+" : "−"}
                  {inBase.format(Math.abs(recon.gap))}
                </span>
              }
            />
            <Cell
              label="Statement vs engine"
              value={
                <span className="text-ink-soft text-xs">
                  {gapDirection(recon.gap) === "even"
                    ? "the two statements agree"
                    : gapDirection(recon.gap) === "ledger-ahead"
                      ? "the ledger reads more than the engine"
                      : "the engine reads more than the ledger"}
                </span>
              }
              title={`${recon.institution_name ?? "The trading account"}: statement of ${recon.statement_date ?? "unknown date"}, engine row of ${recon.engine_as_of ? engineStamp(recon.engine_as_of) : "unknown time"}`}
            />
          </>
        ) : (
          <Cell
            wide
            label="Reconciliation"
            value={<span className="text-ink-faint text-xs">{reading.kind === "absent" ? reading.line : "—"}</span>}
            title="What stands between the reader and a measured gap, said rather than pretended"
          />
        )}
      </dl>

      {reading.kind === "measured" && recon.gap != null && (
        <p className="mt-1.5 font-mono text-[0.65rem] text-ink-faint">
          {recon.institution_name ?? "the trading account"}: ledger {inBase.format(recon.statement_total ?? 0)}
          {" "}({recon.statement_date ?? "no statement date"}) − engine {inBase.format(recon.engine_equity_base ?? 0)}
          {" "}({recon.engine_as_of ? engineStamp(recon.engine_as_of) : "no engine date"})
        </p>
      )}

      {onDeclare && institutions && institutions.length > 0 &&
        (recon.missing.includes("no-mapping") || recon.missing.includes("institution-gone")) && (
        <MappingControl institutions={institutions} onDeclare={onDeclare} />
      )}
    </section>
  );
}

/** The declaration the reconciliation is waiting for: which of the ledger's
    accounts is the trading desk. One select, one button — the mapping is a
    fact only the reader knows, so nothing here proposes. */
function MappingControl({
  institutions,
  onDeclare,
}: {
  institutions: { id: number; name: string }[];
  onDeclare: (institutionId: number) => Promise<void> | void;
}) {
  const [chosen, setChosen] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-xs">
      <span className="text-ink-faint">which account is the trading desk?</span>
      <select
        aria-label="Trading account"
        className="max-w-full rounded-sm border border-rule bg-surface px-2 py-1 font-mono text-xs outline-none focus:border-olive"
        value={chosen ?? ""}
        onChange={(e) => setChosen(e.target.value ? Number(e.target.value) : null)}
      >
        <option value="">—</option>
        {institutions.map((i) => (
          <option key={i.id} value={i.id}>
            {i.name}
          </option>
        ))}
      </select>
      <button
        type="button"
        disabled={chosen == null || busy}
        className="rounded-sm bg-olive px-2 py-1 font-mono text-xs font-medium text-on-accent transition hover:bg-olive-deep disabled:opacity-50"
        onClick={() => {
          if (chosen == null) return;
          setBusy(true);
          void Promise.resolve(onDeclare(chosen)).finally(() => setBusy(false));
        }}
      >
        Declare
      </button>
    </div>
  );
}

/** The block as the Dashboard mounts it: fetched on its own, so a backend
    that cannot answer this one endpoint never blanks the wealth figures
    around it. */
export default function FundOverview() {
  const [overview, setOverview] = useState<OverviewFund | null>(null);
  const [accounts, setAccounts] = useState<{ id: number; name: string }[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    getFundOverview()
      .then(async (o) => {
        if (!live) return;
        setOverview(o);
        // The institution list costs a request, so it is only asked for when
        // the reconciliation would actually offer the declaration control.
        const missing = o.reconciliation.missing;
        if (missing.includes("no-mapping") || missing.includes("institution-gone")) {
          try {
            const list = await getInstitutions();
            if (live) setAccounts(list.map((i) => ({ id: i.id, name: i.name })));
          } catch {
            // Without the list the control simply does not render: the empty
            // state's sentence already says what is missing.
          }
        }
      })
      .catch(() => {
        if (live) setFailed(true);
      });
    return () => {
      live = false;
    };
  }, []);

  if (failed) {
    return (
      <p className="font-mono text-xs text-warn" role="status">
        The fund overview did not answer — the desk's figures are unknown, not absent.
      </p>
    );
  }
  if (!overview) return null;
  return (
    <FundOverviewRows
      overview={overview}
      institutions={accounts ?? undefined}
      onDeclare={async (institutionId) => {
        await putTradingAccount(institutionId);
        setOverview(await getFundOverview());
      }}
    />
  );
}
