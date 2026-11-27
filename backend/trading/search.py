"""The strategy search machinery — governed candidate evaluation.

Companion to docs/research/program-2026-11-26.md, which is binding: the
count of everything tried is first-class provenance, selection and
confirmation never share a bar, and a candidate that fails out-of-sample
is dead permanently. This module is the machinery those rules compile to.

What lives here:

1. The search ledger — one append-only sqlite table in the research db.
   Every candidate evaluated lands in it: family, parameters, phase,
   verdict, the four statistics, the data window. Failures are recorded
   with the same care as passes — the count is the evidence. Nothing is
   ever updated or deleted; a candidate re-run is a new row.

2. Phase A — in-sample screening. Candidates are evaluated on in-sample
   data with the full gate. Rails-off BTConfig: the kill-switch truncates
   losing strategies before 30 trades and the gate cannot tell a bad
   strategy from a censored sample — screening needs the uncensored
   evidence. Rails-on is phase B's job, because production truth includes
   the rails.

3. Phase B — out-of-sample confirmation, one shot, rails ON. Pass → the
   candidate is eligible for the normal validate+register path (which
   re-runs the whole thing through the CLI a human can read). Fail → dead.

The in/out split is fixed by the program document at 2025-11-01 and lives
here as a constant, not a flag: a split that moves with the results is not
a split.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

# The split fixed by docs/research/program-2026-11-26.md §2 before the first
# candidate ran. Never a CLI argument.
OOS_SPLIT = pd.Timestamp("2025-11-01", tz="UTC")

LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS search_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    family TEXT NOT NULL,
    candidate TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    params_json TEXT NOT NULL,
    phase TEXT NOT NULL,
    verdict TEXT NOT NULL,
    trades_n INTEGER,
    permutation_p REAL,
    sharpe_ci_lo REAL,
    wf_positive INTEGER,
    wf_total INTEGER,
    sharpe REAL,
    profit_factor REAL,
    max_dd_pct REAL,
    rails TEXT NOT NULL,
    data_start TEXT,
    data_end TEXT,
    data_rows INTEGER,
    seed INTEGER NOT NULL,
    reasons_json TEXT NOT NULL,
    elapsed_s REAL,
    legs_json TEXT,
    wf_windows_json TEXT
)
"""


def open_ledger(db_path: str) -> sqlite3.Connection:
    """Append-only ledger over plain sqlite3 — it is a research artifact in
    the replaceable market-data store, deliberately outside the Alembic
    lineage of the application schema: verdicts are app data, the search's
    diary is not."""
    conn = sqlite3.connect(db_path)
    conn.execute(LEDGER_DDL)
    # additive migration for ledgers written before legs existed — sqlite
    # errors on duplicate-column ALTER, so the check is the catalog read
    cols = {r[1] for r in conn.execute("PRAGMA table_info(search_ledger)")}
    if "legs_json" not in cols:
        conn.execute("ALTER TABLE search_ledger ADD COLUMN legs_json TEXT")
    if "wf_windows_json" not in cols:
        # the walk-forward window series — edge decay is the program's
        # regime question (regime-architecture-2026-11-26) and a series
        # that is computed but never persisted cannot be mined afterwards
        conn.execute("ALTER TABLE search_ledger ADD COLUMN wf_windows_json TEXT")
    conn.commit()
    return conn


def ledger_append(conn: sqlite3.Connection, row: dict) -> int:
    cols = (
        "ts, family, candidate, symbol, timeframe, params_json, phase, verdict,"
        " trades_n, permutation_p, sharpe_ci_lo, wf_positive, wf_total, sharpe,"
        " profit_factor, max_dd_pct, rails, data_start, data_end, data_rows,"
        " seed, reasons_json, elapsed_s, legs_json, wf_windows_json"
    )
    placeholders = ", ".join("?" for _ in cols.split(","))
    cur = conn.execute(
        f"INSERT INTO search_ledger ({cols}) VALUES ({placeholders})",
        [row.get(c.strip()) for c in cols.split(",")],
    )
    conn.commit()
    return cur.lastrowid


def ledger_counts(conn: sqlite3.Connection, family: str | None = None) -> list[tuple]:
    """(family, phase, verdict, count) — the multiple-testing evidence."""
    q = "SELECT family, phase, verdict, COUNT(*) FROM search_ledger"
    args = []
    if family:
        q += " WHERE family = ?"
        args.append(family)
    q += " GROUP BY family, phase, verdict ORDER BY family, phase, verdict"
    return conn.execute(q, args).fetchall()


def rails_off_config():
    """BTConfig with layer-0 rails and exposure caps pushed out of reach —
    screening needs uncensored evidence. A kill-switch that truncates a
    losing strategy at 12 trades makes the gate confuse 'bad strategy' with
    'truncated sample'; in phase A we want the strategy's own truth. Fees,
    slippage and risk sizing stay production-real — cost honesty is not a
    rail, it is the measurement."""
    from trading.backtest.engine import BTConfig

    return BTConfig(
        leverage=1.0,
        max_symbol_exposure=1e9,
        max_gross_exposure=1e9,
        killswitch_dd_pct=99.9,
        daily_loss_pct=99.9,
        loss_streak_max=1_000_000,
    )

@dataclass
class Candidate:
    """One point in a family's parameter space — the unit the ledger counts."""

    family: str
    name: str
    bot_key: str
    params: dict
    make: object  # callable(params) -> strategy instance
    symbols: list[str] = field(default_factory=lambda: ["BTCUSDT"])
    timeframe: str = "4h"

    def instance(self):
        return self.make(self.params)


def _window(df: pd.DataFrame, start=None, end=None) -> pd.DataFrame:
    idx = df.index
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
        df = df.copy()
        df.index = idx
    out = df
    if start is not None:
        out = out[out.index >= start]
    if end is not None:
        out = out[out.index < end]
    return out


def in_sample(df: pd.DataFrame) -> pd.DataFrame:
    return _window(df, end=OOS_SPLIT)


def out_of_sample(df: pd.DataFrame) -> pd.DataFrame:
    return _window(df, start=OOS_SPLIT)

def load_frame(research_db: str, symbol: str, timeframe: str) -> pd.DataFrame:
    """The full feature frame for one symbol-timeframe — loaded once per
    caller, then sliced per phase. Windows lose warm-up history by slicing:
    the first lookback-worth of in-sample bars can never signal, which is
    the honest price of the split — recorded in every row's data_start."""
    from trading.features import build_features
    from trading.models import make_engine, make_session_factory
    from trading.research import load_candles_df

    engine = make_engine(research_db)
    sf = make_session_factory(engine)
    with sf() as session:
        raw = load_candles_df(session, symbol.upper(), timeframe)
    engine.dispose()
    if raw.empty:
        raise SystemExit(f"no candles for {symbol} {timeframe} in {research_db} — run ingest first")
    return build_features(raw)



def evaluate_candidate(
    conn: sqlite3.Connection,
    candidate: Candidate,
    *,
    phase: str,
    df: pd.DataFrame,
    research_db: str,
    seed: int,
    cfg,
    symbol: str,
) -> dict:
    """One candidate, one phase, one symbol — validated through the same
    validate_core the CLI uses, then ledgered. The ledger write is not
    optional: an evaluation that does not land in the ledger is exactly the
    selection bias this machinery exists to prevent, so the write happens
    inside the same call, before the verdict is returned."""
    from trading.research import validate_core

    if phase not in ("A", "B"):
        raise ValueError(f"phase must be A or B, got {phase!r}")

    started = time.monotonic()
    instance = candidate.instance()
    # cross-sectional injection hook (F10, 2026-11-26): same contract as the
    # basket path — the instance may reshape the frame causally before
    # validation. `df` here is the FULL frame (phase slicing happens inside
    # validate_core), so alpha warm-up reaches back through in-sample
    # history even in phase B — legitimate causal use, never lookahead:
    # alpha values at bar t depend only on bars <= t by the zoo's own
    # operator discipline.
    injector = getattr(instance, "inject_frame", None)
    if callable(injector):
        df = injector(df, symbol)
    # the worker passes the full frame so injected causal columns can warm
    # up across the boundary; the backtest itself never crosses it — slice
    # unconditionally, after injection if there was one
    df = in_sample(df) if phase == "A" else out_of_sample(df)
    core = validate_core(
        instance,
        candidate.bot_key,
        symbol,
        candidate.timeframe,
        research_db,
        seed=seed,
        cfg=cfg,
        df=df,
    )
    elapsed = round(time.monotonic() - started, 2)
    metrics = core["metrics"]
    # Power resolution label (stats repair 2026-11-27): could a test of
    # this size see the edge it measured? The observed sharpe is its own
    # reference — degenerate for phase A (the cell is the measurement) but
    # honest about resolution: a cell that cannot see its own result was
    # noise before it ran. Phase-B interpretation against the in-sample
    # edge lives in scripts/power_reread.py pairing.
    from trading.research import min_detectable_sharpe

    power_label = {
        "min_detectable_sharpe": round(min_detectable_sharpe(core["n_trades"]), 3),
        "resolvable": bool(
            core["n_trades"] >= 1
            and abs(core["metrics"].get("sharpe") or 0.0) >= min_detectable_sharpe(core["n_trades"])
        ),
    }
    # budget enforcement (analysis F-6, now code): the family's declared
    # budget is counted against spent ledger rows — phase A cells only,
    # phase B confirmations are the protocol's own continuation, not new
    # spend. Overflow never blocks (the ledger is append-only and honest)
    # but it is always flagged, verbatim, in the row itself.
    from trading.candidates import FAMILY_BUDGETS

    budget_flag = None
    if phase == "A":
        budget = FAMILY_BUDGETS.get(candidate.family)
        if budget is not None:
            spent = conn.execute(
                "select count(*) from search_ledger where family = ? and phase = 'A' and verdict != 'error'",
                (candidate.family,),
            ).fetchone()[0]
            if spent >= budget:
                budget_flag = (
                    f"budget_exceeded: family {candidate.family} budget {budget} phase-A cells, "
                    f"this is cell {spent + 1} — declared budgets are the program's multiple-testing accounting"
                )
    # the power line rides inside the reasons list as a machine-prefixed
    # entry — the list shape every consumer already parses stays intact,
    # and the resolution label is visible verbatim wherever reasons render.
    reasons_with_power = list(core["reasons"]) + ([budget_flag] if budget_flag else []) + [
        f"power: min-detectable-sharpe {power_label['min_detectable_sharpe']} at {core['n_trades']} trades"
        + (" (resolvable)" if power_label["resolvable"] else " (UNRESOLVABLE - the cell cannot see its own edge)")
    ]
    row = {
        "ts": pd.Timestamp.now(tz="UTC").isoformat(),
        "family": candidate.family,
        "candidate": candidate.name,
        "symbol": symbol.upper(),
        "timeframe": candidate.timeframe,
        "params_json": json.dumps(candidate.params, sort_keys=True),
        "phase": phase,
        "verdict": core["verdict"],
        "trades_n": core["n_trades"],
        "permutation_p": core["p_sharpe"],
        "sharpe_ci_lo": core["bs"].get("ci_lower"),
        "wf_positive": core["wf_pos"],
        "wf_total": core["wf_total"],
        "sharpe": metrics.get("sharpe"),
        "profit_factor": metrics.get("profit_factor"),
        "max_dd_pct": metrics.get("max_dd_pct"),
        "rails": "off" if phase == "A" else "on",
        "data_start": str(df.index[0]),
        "data_end": str(df.index[-1]),
        "data_rows": len(df),
        "seed": seed,
        "reasons_json": json.dumps(reasons_with_power),
        "elapsed_s": elapsed,
        "wf_windows_json": json.dumps(
            core.get("validation_payload", {}).get("walk_forward", {}).get("windows", [])
        ),
    }
    row_id = ledger_append(conn, row)
    return {"id": row_id, **row, "core": core}


def export_ledger_snapshot(db_path: str, out_path: str | None = None) -> str:
    """Write the full search ledger as JSON for the public research portal.

    The portal deploys from CI where research.db (460MB, gitignored market
    data) cannot exist; the ledger itself is half a megabyte of pure
    evidence. The snapshot is a research artifact committed to the repo —
    privacy-safe by construction: it contains strategy measurements, never
    positions, wealth records, or anything from data.db."""
    if out_path is None:
        out_path = str(Path(db_path).parent / "ledger_snapshot.json")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cols = [d[1] for d in conn.execute("PRAGMA table_info(search_ledger)").fetchall()]
        rows = conn.execute("select * from search_ledger order by id").fetchall()
    finally:
        conn.close()
    payload = {
        "exported_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "rows": [dict(zip(cols, r)) for r in rows],
    }
    Path(out_path).write_text(json.dumps(payload))
    return out_path
