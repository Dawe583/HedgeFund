"""Research ledger endpoints — the append-only evidence stream, in-app.

The ledger (data/research.db: search_ledger) is the program's diary:
every sweep row, verdicts included, plus the power label and the tape
venue since 2026-11-27. The evidence room renders it publicly; these
endpoints are the same evidence inside the app — read-only like every
trading API surface, and honest by construction: a row carries what the
cell measured, never an interpretation layered after the fact.

The db file is SQLite in WAL mode and opened read-only here — the sweep
can write while the API reads, and an absent file is an empty ledger,
not an error (a fresh checkout has no research yet).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/ledger", tags=["ledger"])

_BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER = _BACKEND_DIR / "data" / "research.db"


def _connect_readonly(db_path: Path | None = None) -> sqlite3.Connection | None:
    path = db_path or DEFAULT_LEDGER
    if not path.exists():
        return None
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(conn: sqlite3.Connection, q: str, args: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(q, args).fetchall()]


@router.get("/verdicts")
def ledger_verdicts(
    family: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
) -> dict:
    """Newest-first sweep rows — one row per measured cell with verdict,
    sharpe, trades, power label and venue. The app's answer to 'what has
    the program tried lately'."""
    conn = _connect_readonly()
    if conn is None:
        return {"rows": [], "note": "no ledger yet — nothing has been measured"}
    try:
        cols = (
            "id, ts, family, candidate, symbol, timeframe, params_json, phase, verdict,"
            " trades_n, min_trades, sharpe, sharpe_ci_lo, sharpe_ci_hi, permutation_p,"
            " power_label, min_detectable_sharpe, venue, seed, elapsed_s"
        )
        if family:
            rows = _rows(conn, f"SELECT {cols} FROM search_ledger WHERE family = ? ORDER BY id DESC LIMIT ?", (family, limit))
        else:
            rows = _rows(conn, f"SELECT {cols} FROM search_ledger ORDER BY id DESC LIMIT ?", (limit,))
        return {"rows": rows}
    except sqlite3.OperationalError as exc:
        # schema drift (old ledger without the new columns) is reported, not hidden
        return {"rows": [], "note": f"ledger schema mismatch: {exc}"}
    finally:
        conn.close()


@router.get("/summary")
def ledger_summary() -> dict:
    """Counts by family/phase/verdict — the same shape the evidence room
    renders, so the app and the public page never disagree about what the
    ledger says."""
    conn = _connect_readonly()
    if conn is None:
        return {"rows": [], "note": "no ledger yet"}
    try:
        rows = _rows(
            conn,
            "SELECT family, phase, verdict, COUNT(*) AS n FROM search_ledger GROUP BY family, phase, verdict",
        )
        return {"rows": rows}
    except sqlite3.OperationalError as exc:
        return {"rows": [], "note": f"ledger schema mismatch: {exc}"}
    finally:
        conn.close()
