import { useEffect, useState } from "react";
import {
  getLedgerSummary,
  getLedgerVerdicts,
  type LedgerSummaryRow,
  type LedgerVerdictRow,
} from "../api/tradingLedger";
import { EmptyState } from "./Emblem";
import { apiError, cardClass, Section } from "./ui";
import { fmtCi, fmtP } from "./tradingStatus";

/* LEDGER BROWSER — the research ledger in-app: every measured cell with its
   verdict, power label and tape venue. This is the same append-only stream
   the public evidence room renders; the app showing a different shape than
   the page would be two accounts of one evidence, and the system is built
   to have exactly one.

   Reading discipline (doctrine, in the UI because it is the point):
   `validated` is rare and green on purpose, `rejected` is the gate working,
   and `untestable` — since the power wiring — is the instrument admitting
   the cell was blind, rendered muted because blindness is neither success
   nor failure. Rows predating the venue column carry venue null and the UI
   says 'unknown', never guesses. */

function verdictPill(verdict: string): { text: string; cls: string } {
  if (verdict === "validated") return { text: "validated", cls: "text-gain" };
  if (verdict === "rejected") return { text: "rejected", cls: "text-loss" };
  if (verdict === "untestable") return { text: "untestable", cls: "text-ink-soft" };
  if (verdict === "error") return { text: "error", cls: "text-ink-soft italic" };
  return { text: verdict, cls: "text-ink-soft" };
}

function powerPill(row: LedgerVerdictRow): string | null {
  if (!row.power_label) return null;
  if (row.power_label === "unresolvable") return "blind cell";
  if (!row.power_label.startsWith("resolvable")) return row.power_label;
  /* "resolvable ±0.66 @ 16 trades" — the resolution the verdict could see */
  return row.power_label.replace("resolvable ", "±");
}

function SummaryStrip({ rows }: { rows: LedgerSummaryRow[] }) {
  /* family × verdict counts, flattened into one honest line per family —
     the ledger's own accounting, never an editorial summary */
  const byFamily = new Map<string, Map<string, number>>();
  for (const r of rows) {
    if (!byFamily.has(r.family)) byFamily.set(r.family, new Map());
    const m = byFamily.get(r.family)!;
    m.set(r.verdict, (m.get(r.verdict) ?? 0) + r.n);
  }
  const families = [...byFamily.keys()].sort();
  if (families.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-soft">
      {families.map((fam) => {
        const m = byFamily.get(fam)!;
        const parts = [...m.entries()]
          .sort()
          .map(([v, n]) => `${n} ${v}`)
          .join(" · ");
        return (
          <span key={fam}>
            <span className="font-medium text-ink">{fam}</span> {parts}
          </span>
        );
      })}
    </div>
  );
}

export default function LedgerBrowser() {
  const [rows, setRows] = useState<LedgerVerdictRow[] | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<LedgerSummaryRow[]>([]);
  const [family, setFamily] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getLedgerVerdicts(family ?? undefined)
      .then((r) => {
        if (!alive) return;
        setRows(r.rows);
        setNote(r.note ?? null);
      })
      .catch((e) => alive && setError(apiError(e, "The research ledger could not be loaded.")));
    getLedgerSummary()
      .then((s) => alive && setSummary(s.rows))
      .catch(() => {
        /* the strip is supplementary; its failure renders as no strip */
      });
    return () => {
      alive = false;
    };
  }, [family]);

  if (error) {
    return <p className="text-sm text-loss">{error}</p>;
  }
  if (rows === null) {
    return <p className="text-sm text-ink-soft">Reading the ledger…</p>;
  }
  if (rows.length === 0) {
    return (
      <EmptyState title="Nothing measured yet">
        {note ?? "The ledger is empty — the program's diary starts with the first sweep row."}
      </EmptyState>
    );
  }

  const families = [...new Set(summary.map((s) => s.family))].sort();

  return (
    <div className="space-y-3">
      <SummaryStrip rows={summary} />
      {families.length > 1 && (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <button
            className={family === null ? "font-medium text-ink underline" : "text-ink-soft hover:text-ink"}
            onClick={() => setFamily(null)}
          >
            all families
          </button>
          {families.map((fam) => (
            <button
              key={fam}
              className={family === fam ? "font-medium text-ink underline" : "text-ink-soft hover:text-ink"}
              onClick={() => setFamily(fam)}
            >
              {fam}
            </button>
          ))}
        </div>
      )}
      <div className={`${cardClass} overflow-x-auto`}>
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-line text-left text-ink-soft">
              <th className="px-3 py-1.5 font-medium">When</th>
              <th className="px-3 py-1.5 font-medium">Cell</th>
              <th className="px-3 py-1.5 font-medium">Phase</th>
              <th className="px-3 py-1.5 text-right font-medium">Trades</th>
              <th className="px-3 py-1.5 text-right font-medium">Sharpe</th>
              <th className="px-3 py-1.5 text-right font-medium">CI</th>
              <th className="px-3 py-1.5 text-right font-medium">p</th>
              <th className="px-3 py-1.5 font-medium">Venue</th>
              <th className="px-3 py-1.5 font-medium">Power</th>
              <th className="px-3 py-1.5 text-left font-medium">Verdict</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const pill = verdictPill(r.verdict);
              const power = powerPill(r);
              return (
                <tr key={r.id} className="border-b border-line/50 last:border-0">
                  <td className="px-3 py-1.5 whitespace-nowrap text-ink-soft">{r.ts.slice(0, 16)}</td>
                  <td className="px-3 py-1.5">
                    <span className="font-medium text-ink">{r.candidate}</span>{" "}
                    <span className="text-ink-soft">
                      {r.symbol} {r.timeframe}
                    </span>
                  </td>
                  <td className="px-3 py-1.5 text-ink-soft">{r.phase}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {r.trades_n}
                    <span className="text-ink-soft">/{r.min_trades}</span>
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {r.sharpe === null ? "—" : r.sharpe.toFixed(2)}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums text-ink-soft">{fmtCi(r.sharpe_ci_lo, r.sharpe_ci_hi)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums text-ink-soft">{fmtP(r.permutation_p)}</td>
                  <td className="px-3 py-1.5 text-ink-soft">{r.venue ?? "unknown"}</td>
                  <td className="px-3 py-1.5 text-ink-soft">{power ?? "—"}</td>
                  <td className={`px-3 py-1.5 ${pill.cls}`}>{pill.text}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
