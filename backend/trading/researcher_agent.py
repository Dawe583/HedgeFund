"""The researcher agent — the first trading agent, wired into the program's
one honest loop: agents propose, the machinery disposes
(docs/design/trading-agents-2026-11-26.md).

The agent reads the search ledger, the family verdicts and the research
notes — everything local, nothing invented — and drafts ONE family
declaration: mechanism hypothesis, falsifiable claim, parameter grid,
budget. Its output is TEXT. A human or a policy gate reviews it before the
first sweep; the declaration-before-measurement discipline applies to the
agent exactly as it applied to the human all week, because the alternative
is a selection-bias machine wearing a lab coat.

Provider: OpenRouter through the app's own advisor wiring — no new key
infrastructure, no new vendor. The model slug is configurable; the prompt
is in this file because a prompt you cannot read in one screen is a prompt
you cannot audit.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RESEARCH_NOTES = REPO_ROOT / "docs" / "research"

PROMPT = """You are the researcher agent of a systematic trading program whose one rule
is: a strategy cannot reach capital without evidence, and every claim is
measured, never argued. The program runs families (F1..F9 so far), each with
a declared budget of parameter cells, measured through one kernel with
permutation tests, out-of-sample gates and a walk-forward window series.

Below is the program's full measurement state: the search ledger rows, the
verdict documents, and the program document. Read all of it. Then draft
EXACTLY ONE new family declaration in the program's own format:

## F<N>. <name> | budget <count>

Mechanism hypothesis: what structural or behavioral effect should exist and
WHY — not 'the model learns patterns', a reason a market participant or
constraint creates the edge. Then the grid, countable in one line, and what
would falsify the hypothesis.

Rules you do not get to break:
- The budget is total cells across the family (params x symbols x phases).
- Declared budgets so far ran 10-50 cells. Propose in that range.
- Do not re-propose a closed family. Do not invert a dead family — F5's
  inversion already exists as F7/F8 and is measured.
- You may use anything in the integrated tooling: the vendored alpha zoo
  (Kakushadze 101 / GTJA 191, bench results below if present), the funding
  feed, multi-asset data (SPY/QQQ/IWM/DIA/GLD/SLV + crypto 10), the ML
  forecaster machinery, cross-sectional basket machinery.
- If you believe no honest family remains within the budget discipline,
  say so in one paragraph instead. That is a valid output.

Write the declaration in English, in the program document's voice. Under it,
add one section 'Agent reasoning' — at most ten lines — naming the evidence
rows that motivated the choice. That section is auditable input, not part
of the declaration.
"""


def ledger_summary(db_path: str, limit: int = 400) -> str:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "select family, candidate, symbol, phase, verdict, trades_n, sharpe, permutation_p, sharpe_ci_lo "
            "from search_ledger order by id desc limit ?", (limit,)
        ).fetchall()
    finally:
        conn.close()
    lines = ["family | candidate | symbol | phase | verdict | trades | sharpe | perm_p | ci_lo"]
    for r in rows:
        sharpe = f"{r[6]:+.2f}" if r[6] is not None else "n/a"
        p = f"{r[7]:.3f}" if r[7] is not None else "n/a"
        ci = f"{r[8]:+.2f}" if r[8] is not None else "n/a"
        lines.append(f"{r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {sharpe} | {p} | {ci}")
    return "\n".join(lines)


def research_docs() -> str:
    parts = []
    for name in ("program-2026-11-26.md", "program-day2-plan-2026-11-26.md", "program-verdict-day1-2026-11-26.md"):
        p = RESEARCH_NOTES / name
        if p.exists():
            parts.append(f"--- {name} ---\n{p.read_text()[:6000]}")
    return "\n\n".join(parts)


def bench_results() -> str:
    for path in ("/tmp/alpha-bench-crypto-4h.json", "/tmp/alpha-bench-equity-1d.json"):
        p = Path(path)
        if not p.exists():
            continue
        rows = json.loads(p.read_text())
        alive = [r for r in rows if r.get("verdict") in ("alive", "reversed")]
        lines = [f"--- alpha bench {p.name}: {len(rows)} alphas measured, {len(alive)} significant ---"]
        for r in sorted(alive, key=lambda x: -abs(x.get("mean_ic", 0)))[:30]:
            lines.append(
                f"{r['alpha']} | {r['verdict']} | mean_ic {r.get('mean_ic')} | tstat {r.get('tstat')} | pos {r.get('positive_share')} | {r.get('theme', '')}"
            )
        return "\n".join(lines)
    return "(alpha bench results not yet available)"


def propose(db_path: str, *, model: str | None = None) -> str:
    """One researcher pass: read everything, draft one declaration."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY is not set — the researcher cannot call a model without it.")
    from openai import OpenAI

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    slug = model or os.environ.get("OPENROUTER_MODEL") or "anthropic/claude-sonnet-4.5"
    evidence = "\n\n".join(
        [
            "# SEARCH LEDGER (newest first)",
            ledger_summary(db_path),
            "# PROGRAM DOCUMENTS",
            research_docs(),
            "# ALPHA BENCH",
            bench_results(),
        ]
    )
    resp = client.chat.completions.create(
        model=slug,
        messages=[
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": evidence},
        ],
        temperature=0.3,
    )
    return resp.choices[0].message.content or ""


def main() -> int:
    ap = argparse.ArgumentParser(description="researcher agent — proposes one family declaration")
    ap.add_argument("--db", default=str(REPO_ROOT / "backend" / "data" / "research.db"))
    ap.add_argument("--model", default=None)
    args = ap.parse_args()
    print(propose(args.db, model=args.model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
