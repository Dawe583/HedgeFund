"""Register the negative control into paper (90-day plan, weeks 7-8).

The desk's operational plane — veto tape, divergence measurement,
reconciliation, lifecycle transitions — has never run under its intended
load: zero validated strategies means an empty roster means zero evidence
flowing. A random-entry control fixes that because its expectations are
known BY CONSTRUCTION (zero edge before costs, slightly negative after),
so every operational measurement against it is calibrated: a measurement
system that reports edge in the control is broken, not insightful.

What this script does, exactly:

1. Reads the roster. If a 'randomctl' version already sits in paper, the
   registration is not repeated — registration is an act, re-running it is
   not a second act — and the roster is printed as-is.
2. Otherwise calls trading.registry.register_control, which writes the
   strategy/version rows and walks research → validated → paper with the
   instrumentation declaration in every note and in the version's params.
   The control NEVER passed validation; the ledger rows say so. See
   registry.register_control's docstring for the honesty design.
3. Prints the roster JSON — the desk's boot contract — after committing.

Usage:
    python3 scripts/register_negative_control.py [--db sqlite:////path/to/data.db]

Default db is the configured app database (backend/data.db). Run it when
you choose — nothing else in the system calls this.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from trading.config import get_settings  # noqa: E402
from trading.models import init_schema, make_engine, make_session_factory  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="register_negative_control")
    p.add_argument(
        "--db",
        default=None,
        help="SQLAlchemy url of the app database (default: configured database_url, i.e. backend/data.db)",
    )
    p.add_argument("--seed", type=int, default=42, help="control RNG seed (default 42 — reproducibility is doctrine)")
    p.add_argument("--symbol", default="BTCUSDT", help="universe symbol (default BTCUSDT)")
    args = p.parse_args(argv)

    from trading.bots.random_control_bot import CONTROL_DECLARATION, RandomControl
    from trading.registry import register_control, roster

    db_url = args.db or get_settings().database_url
    engine = make_engine(db_url)
    init_schema(engine)
    session_factory = make_session_factory(engine)

    session = session_factory()
    try:
        existing = [r for r in roster(session) if r["key"] == "randomctl"]
        if existing:
            print("randomctl already in paper — registration is an act, not repeated.")
        else:
            result = register_control(
                session,
                "randomctl",
                "RandomControl — instrumentation control, never alpha",
                RandomControl,
                timeframe="1h",
                universe=[args.symbol],
                params={"seed": args.seed},
            )
            session.commit()
            print(f"registered control version {result['version_id']} (designation row {result['validation_id']}):")
            for state, note in result["states"]:
                print(f"  -> {state}: {note}")
            print(f"declaration: {CONTROL_DECLARATION}")
        entries = roster(session)
        print("\nROSTER " + json.dumps(entries, indent=2, default=str))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
