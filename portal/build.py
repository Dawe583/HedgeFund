"""Research portal builder — renders the evidence room as a static site.

The HedgeFund research program's one genuinely unique asset is its honesty
infrastructure: declarations before measurements, append-only ledger,
published negative results. This portal makes that asset visible: every
doc in docs/research/ becomes a page, the search ledger becomes a queryable
evidence table, and the front page is the program's current truth — what
lives, what died, what is being measured now.

Privacy contract, load-bearing: NOTHING from data.db (the owner's wealth
records), no positions, no API keys, no account numbers — the portal reads
only docs/research/*.md and the research.db LEDGER tables (search_ledger),
which contain strategy measurements, never personal data. The build fails
closed if the ledger file is missing rather than fabricating anything.

Output: portal/dist/ — plain static HTML, deployable anywhere (Vercel).
"""

from __future__ import annotations

import html
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs" / "research"
LEDGER_DB = REPO / "backend" / "data" / "research.db"
OUT = Path(__file__).resolve().parent / "dist"

STYLE = """
:root { --fg:#c8d3c4; --dim:#6b7a68; --bg:#0a0c0a; --panel:#101410; --accent:#7dff9a; --warn:#ffb86b; --dead:#ff6b6b; --border:#1e2a1e; }
* { box-sizing:border-box; margin:0; padding:0; }
body { background:var(--bg); color:var(--fg); font:14px/1.6 ui-monospace,Menlo,monospace; padding:2rem max(2rem,calc(50vw - 540px)); }
h1 { color:var(--accent); font-size:1.5rem; letter-spacing:0.05em; margin-bottom:0.3rem; }
h2 { color:var(--accent); font-size:1.05rem; margin:2rem 0 0.6rem; border-bottom:1px solid var(--border); padding-bottom:0.3rem; }
h3 { color:var(--fg); font-size:0.95rem; margin:1.2rem 0 0.4rem; }
p,li { margin:0.35rem 0; }
a { color:var(--accent); text-decoration:none; }
a:hover { text-decoration:underline; }
table { border-collapse:collapse; width:100%; margin:0.8rem 0; font-size:0.82rem; }
th { color:var(--dim); text-align:left; padding:0.3rem 0.5rem; border-bottom:1px solid var(--border); font-weight:normal; }
td { padding:0.3rem 0.5rem; border-bottom:1px solid var(--border); vertical-align:top; }
tr:hover td { background:var(--panel); }
.dim { color:var(--dim); }
.dead { color:var(--dead); }
.alive { color:var(--accent); }
.warn { color:var(--warn); }
.tag { display:inline-block; padding:0 0.4rem; border:1px solid var(--border); font-size:0.75rem; margin-right:0.3rem; }
.doc-nav { columns:2; margin:0.8rem 0; }
.doc-nav a { display:block; padding:0.15rem 0; font-size:0.85rem; }
pre { background:var(--panel); border:1px solid var(--border); padding:0.8rem; overflow-x:auto; font-size:0.8rem; margin:0.6rem 0; }
code { color:var(--warn); font-size:0.9em; }
blockquote { border-left:2px solid var(--accent); padding-left:0.8rem; color:var(--dim); margin:0.6rem 0; }
.meta { color:var(--dim); font-size:0.8rem; margin-bottom:2rem; }
strong { color:var(--fg); }
hr { border:none; border-top:1px solid var(--border); margin:1.5rem 0; }
ul,ol { padding-left:1.4rem; }
header { border-bottom:1px solid var(--border); padding-bottom:1rem; margin-bottom:1.5rem; }
"""


def render_markdown(text: str) -> str:
    """Minimal honest markdown: headers, tables, lists, code, bold, links.
    Not a library — the docs use a small dialect and this covers it."""
    out = []
    in_table = False
    in_code = False
    in_list = False
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            if in_code:
                out.append("</pre>")
                in_code = False
            else:
                out.append("<pre>")
                in_code = True
            continue
        if in_code:
            out.append(html.escape(line))
            continue
        if line.strip().startswith("|") and line.strip().endswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c or "---") for c in cells):
                continue
            tag = "th" if not in_table else "td"
            if not in_table:
                out.append("<table>")
                in_table = True
            out.append("<tr>" + "".join(f"<{tag}>{html.escape(c)}</{tag}>" for c in cells) + "</tr>")
            continue
        elif in_table:
            out.append("</table>")
            in_table = False
        if re.match(r"^[-*] ", line.strip()):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{inline(line.strip()[2:])}</li>")
            continue
        elif in_list:
            out.append("</ul>")
            in_list = False
        if line.startswith("###"):
            out.append(f"<h3>{inline(line.lstrip('#').strip())}</h3>")
        elif line.startswith("##"):
            out.append(f"<h2>{inline(line.lstrip('#').strip())}</h2>")
        elif line.startswith("#"):
            out.append(f"<h2>{inline(line.lstrip('#').strip())}</h2>")
        elif line.strip() == "---":
            out.append("<hr>")
        elif line.strip():
            out.append(f"<p>{inline(line)}</p>")
    if in_table:
        out.append("</table>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def inline(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def page(title: str, body: str, nav: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{html.escape(title)} — HedgeFund Evidence Room</title>
<style>{STYLE}</style></head><body>
<header><a href="index.html">← evidence room</a></header>
{body}
<footer class="meta" style="margin-top:3rem">generated from the repository's own documents — nothing here is investment advice; most of it is measured evidence that things do NOT work</footer>
</body></html>"""


SNAPSHOT = REPO / "backend" / "data" / "ledger_snapshot.json"


# Rows measured before an engine defect was found are VOID, documented in
# the incident docs. The ledger keeps them (append-only honesty, doctrine
# of devz-scaling-incident-2026-11-26.md); the portal renders them as void,
# not as evidence. Ordered list of (cutoff ledger id, incident doc slug):
# every row with id <= cutoff in the affected families rode the defect.
VOIDED_CUTOFFS = [
    # devz-scaling-incident-2026-11-26.md: dev_z scaling bug voided every
    # F7 measurement before the corrected rerun the same evening. Ledger
    # ids 242-261 are the six false "validated" rows; corrected re-runs
    # follow at higher ids and are all rejected.
    (261, "devz-scaling-incident-2026-11-26"),
]


def voided_ids(rows: list[dict]) -> set[int]:
    out = set()
    for cutoff, _doc in VOIDED_CUTOFFS:
        out |= {r.get("id", 0) for r in rows if r.get("id", 0) <= cutoff and str(r.get("family", "")).startswith("F7")}
    return out


def ledger_rows() -> list[dict]:
    if SNAPSHOT.exists():
        payload = json.loads(SNAPSHOT.read_text())
        return payload["rows"]
    if not LEDGER_DB.exists():
        print("ledger missing — failing closed rather than fabricating", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(f"file:{LEDGER_DB}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "select id, family, candidate, symbol, phase, verdict, trades_n, sharpe, permutation_p, sharpe_ci_lo, wf_positive, wf_total, ts "
            "from search_ledger order by id"
        ).fetchall()
    finally:
        conn.close()
    cols = ["id", "family", "candidate", "symbol", "phase", "verdict", "trades_n", "sharpe", "permutation_p", "sharpe_ci_lo", "wf_positive", "wf_total", "ts"]
    return [dict(zip(cols, r)) for r in rows]


def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    docs = sorted(DOCS.glob("*.md"))
    pages = []
    for doc in docs:
        slug = doc.stem
        body = render_markdown(doc.read_text())
        (OUT / f"{slug}.html").write_text(page(slug, body))
        pages.append((slug, doc.name))

    rows = ledger_rows()
    families = {}
    for r in rows:
        families.setdefault(r["family"], []).append(r)

    # evidence table page
    ev = ["<h1>search ledger — every measured cell, nothing hidden</h1>"]
    ev.append(f'<p class="meta">{len(rows)} rows across {len(families)} families — the append-only diary of the research program. validated means the cell passed every gate: permutation, bootstrap CI, walk-forward, minimum trades. <span class="warn">VOID*</span> rows were measured on a defective engine and are published as voided, never deleted — see devz-scaling-incident.</p>')
    ev.append("<table><tr><th>family</th><th>candidate</th><th>symbol</th><th>phase</th><th>verdict</th><th>trades</th><th>sharpe</th><th>perm p</th><th>wf</th></tr>")
    for r in rows[-500:]:
        if r.get("id") in voided_ids(rows):
            cls = "warn"
            verdict_txt = "VOID*"
        else:
            cls = "alive" if r["verdict"] == "validated" else "dead"
            verdict_txt = r["verdict"]
        sharpe = f"{r['sharpe']:+.2f}" if r["sharpe"] is not None else "—"
        p = f"{r['permutation_p']:.2f}" if r["permutation_p"] is not None else "—"
        wf = f"{r['wf_positive']}/{r['wf_total']}" if r["wf_total"] else "—"
        sym = (r["symbol"] or "")[:24]
        ev.append(
            f"<tr><td>{html.escape(str(r['family']))}</td><td>{html.escape(str(r['candidate']))}</td>"
            f"<td class='dim'>{html.escape(sym)}</td><td>{r['phase']}</td>"
            f"<td class='{cls}'>{verdict_txt}</td><td>{r['trades_n']}</td><td>{sharpe}</td><td>{p}</td><td>{wf}</td></tr>"
        )
    ev.append("</table>")
    (OUT / "ledger.html").write_text(page("search ledger", "\n".join(ev)))

    # family summary + index
    voids = voided_ids(rows)
    fam_summary = []
    for fam, rs in sorted(families.items()):
        val = sum(1 for r in rs if r["verdict"] == "validated" and r.get("id") not in voids)
        fam_summary.append((fam, len(rs), val))

    idx = ["<h1>HEDGEFUND — the evidence room</h1>"]
    idx.append(
        '<p class="meta">a one-person hedge fund being built in public measurement. the program\'s rule: '
        "a strategy cannot reach capital without evidence, and every claim is measured, never argued. "
        "most of what is measured dies — those deaths are published here in full, because a measured negative "
        "is worth more than a hoped positive.</p>"
    )
    idx.append(f'<p class="dim">generated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")} UTC — rebuilt on every push to main</p>')
    idx.append("<h2>the research program — family scoreboard</h2>")
    idx.append("<table><tr><th>family</th><th>cells measured</th><th>validated</th><th>verdict</th></tr>")
    verdict_doc = {}
    for fam, n, val in fam_summary:
        status = '<span class="alive">SURVIVOR</span>' if val else '<span class="dead">closed — no survivors</span>'
        idx.append(f"<tr><td>{html.escape(fam)}</td><td>{n}</td><td>{val}</td><td>{status}</td></tr>")
    idx.append("</table>")
    total_val = sum(v for _, _, v in fam_summary)
    total_cells = sum(n for _, n, _ in fam_summary)
    if total_val:
        idx.append(f'<p class="dim">{total_val} validated cells across {total_cells} measured — '
                   'each survivor earned lifecycle state "paper" and the right to be distrusted further. '
                   'everything else is published dead.</p>')
    else:
        idx.append(f'<p class="dim">zero validated cells across {total_cells} measured so far — honest, and exactly what the '
                   'base rates of this game predict. the infrastructure that measures this honestly is the asset.</p>')
    idx.append("<h2>documents</h2><div class='doc-nav'>")
    idx.append('<a href="ledger.html"><strong>→ search ledger (the raw evidence)</strong></a>')
    for slug, name in pages:
        idx.append(f'<a href="{slug}.html">{html.escape(slug)}</a>')
    idx.append("</div>")
    (OUT / "index.html").write_text(page("evidence room", "\n".join(idx)))
    print(json.dumps({"pages": len(pages) + 2, "ledger_rows": len(rows), "families": len(families)}))


if __name__ == "__main__":
    build()
