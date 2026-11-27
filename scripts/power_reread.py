"""Ledger re-read under corrected power — the boundary question, mined.

Whole-system analysis F-1 (2026-11-27): phase-B deaths at 13-16 trades
cannot distinguish regime decay from statistical invisibility. This script
pairs every phase-B row with its phase-A counterpart, computes the power
of the B-cell against the A-edge, adds the deflated Sharpe ratio per
family (Bailey/Lopez de Prado trial-count correction), and emits the
corrected verdict table: which deaths were measured deaths, which were
underpowered tests, and which in-sample edges survive multiple-testing
accounting at all.

Pure mining — zero sweep compute. Read-only against research.db.

Usage: python3 scripts/power_reread.py [--db PATH] [--out docs/research/power-reread.json]
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path

Z_ONE_SIDED_95 = 1.645
Z_POWER_80 = 0.842


def min_detectable_sharpe(n: int) -> float:
    return (Z_ONE_SIDED_95 + Z_POWER_80) / math.sqrt(n) if n else float("inf")


def norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def deflated_sharpe(sharpe: float, n_trials: int, T: int, skew: float = 0.0, kurt: float = 3.0) -> float:
    """Bailey/Lopez de Prado DSR: probability the true Sharpe exceeds zero
    after correcting for n_trials selection. Approximation with the standard
    expected-maximum-of-normals trial penalty; skew/kurt default to normal
    when the ledger doesn't carry per-trade returns."""
    if T < 2 or sharpe <= 0:
        return 0.0
    # expected max sharpe under the null across n independent trials
    var_sr = (1 - skew * sharpe + (kurt - 1) / 4 * sharpe * sharpe) / max(T - 1, 1)
    if var_sr <= 0:
        return 0.0
    eul = 0.5772156649
    e_max = math.sqrt(var_sr) * ((1 - eul) * norm_cdf_inverse(1 - 1 / max(n_trials, 2)) + eul * norm_cdf_inverse(1 - 1 / (max(n_trials, 2) * math.e)))
    return norm_cdf((sharpe - e_max) / math.sqrt(var_sr))


def norm_cdf_inverse(p: float) -> float:
    """Acklam's rational approximation, sufficient for the trial counts here."""
    if p <= 0 or p >= 1:
        return 0.0
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02, 1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02, 6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00, -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/Users/dawe/Developer/HedgeFund/backend/data/research.db")
    ap.add_argument("--out", default="docs/research/power-reread.json")
    args = ap.parse_args()

    db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    rows = db.execute(
        "select id, family, candidate, symbol, phase, verdict, trades_n, sharpe, wf_positive, wf_total, sharpe_ci_lo, data_start, data_end from search_ledger order by id"
    ).fetchall()
    db.close()

    cols = ["id", "family", "candidate", "symbol", "phase", "verdict", "trades_n", "sharpe", "wf_pos", "wf_total", "ci_lo", "data_start", "data_end"]
    recs = [dict(zip(cols, r)) for r in rows]

    # voided ids mirror the portal overlay: pre-fix F7 measurements
    voids = {r["id"] for r in recs if r["family"].startswith("F7") and r["id"] <= 261}

    by_key = defaultdict(dict)
    trials_by_family = defaultdict(int)
    for r in recs:
        if r["verdict"] == "error":
            continue
        trials_by_family[r["family"]] += 1
        if r["id"] in voids:
            continue
        by_key[(r["candidate"], r["symbol"])][r["phase"]] = r

    out = []
    for (cand, sym), phases in sorted(by_key.items()):
        a = phases.get("A")
        b = phases.get("B")
        if not a or not b or a["verdict"] == "error" or b["verdict"] == "error":
            continue
        n_b = b["trades_n"] or 0
        is_sharpe = a["sharpe"] or 0.0
        mds = min_detectable_sharpe(n_b)
        confirmable = is_sharpe > 0 and mds <= is_sharpe
        trials = trials_by_family[a["family"]]
        T = max(a["trades_n"] or 2, 2)
        # unit conversion: the ledger carries annualized Sharpe. For
        # independent per-trade returns r, annualized = per-trade ratio x
        # sqrt(trades_per_year). The span comes from the row itself; trades
        # assumed uniformly spaced — optimistic approximation, declared.
        try:
            from datetime import datetime
            d0 = datetime.fromisoformat(str(a["data_start"]).replace("Z", "+00:00"))
            d1 = datetime.fromisoformat(str(a["data_end"]).replace("Z", "+00:00"))
            span_years = max((d1 - d0).total_seconds() / (365.25 * 86400), 0.05)
        except Exception:
            span_years = 1.0
        trades_per_year = T / span_years
        per_trade_sharpe = is_sharpe / math.sqrt(max(trades_per_year, 1.0))
        dsr = deflated_sharpe(per_trade_sharpe, trials, T)
        verdict = {
            "candidate": cand,
            "symbol": sym,
            "family": a["family"],
            "is_sharpe": round(is_sharpe, 2),
            "oos_sharpe": round(b["sharpe"] or 0.0, 2),
            "phase_b_trades": n_b,
            "min_detectable_sharpe": round(mds, 2),
            "power": "confirmable" if confirmable else "underpowered",
            "family_trials": trials,
            "dsr": round(dsr, 3),
            "per_trade_sharpe": round(per_trade_sharpe, 3),
            "dsr_significant": dsr >= 0.95,
            "death_meaning": (
                "measured-death" if confirmable and (b["sharpe"] or 0) <= 0
                else "invisible-or-dead" if not confirmable
                else "alive-oos"
            ),
        }
        out.append(verdict)

    summary = {
        "pairs": len(out),
        "confirmable_deaths": sum(1 for r in out if r["death_meaning"] == "measured-death"),
        "underpowered": sum(1 for r in out if r["death_meaning"] == "invisible-or-dead"),
        "dsr_significant_is_edges": sum(1 for r in out if r["dsr_significant"]),
        "model": "power: SE=1/sqrt(n) normal approx, optimistic. DSR: per-trade Sharpe deannualized by measured trades/year, normal skew/kurt, uniform spacing assumed — approximate in every direction, read as a ranking instrument not a verdict.",
    }
    payload = {"summary": summary, "cells": out}
    Path(args.out).write_text(json.dumps(payload, indent=1))
    print(json.dumps(summary))
    # print the interesting rows
    for r in sorted(out, key=lambda x: -x["dsr"])[:8]:
        print(f"  {r['candidate']:26s} {r['symbol']:10s} IS {r['is_sharpe']:+.2f} OOS {r['oos_sharpe']:+.2f} "
              f"nB {r['phase_b_trades']:3d} MDS {r['min_detectable_sharpe']:.2f} {r['power']:12s} dsr {r['dsr']:.2f} → {r['death_meaning']}")


if __name__ == "__main__":
    main()
