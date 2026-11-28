#!/usr/bin/env python3
"""Deep synthetic-path measurement, owner-invoked.

The survivor tier inside validate_core runs 16 paths — a distribution floor.
This probe owns the deep ensembles: what does a family do across 100+ price
paths that never happened, at the cost the kernel honestly charges (measured
5.9 s per 3000-bar backtest on 2026-11-28 — budget before launching).

Usage:
    uv run python ../scripts/synthetic_mc_probe.py --bot trend --symbol BTCUSDT \
        --timeframe 1h --bars 3000 --sims 64

Writes nothing to the ledger: this is a measurement instrument, not a
validation — a probe's output informs the operator, the ledger's rows inform
the program.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading.search import in_sample, load_frame
from trading.validation.synthetic_paths import synthetic_path_mc

BOTS = {
    "trend": ("trading.bots.trend_bot", "TrendMomentum"),
    "meanrev": ("trading.bots.meanrev_bot", "MeanRev"),
    "breakout": ("trading.bots.breakout_bot", "BreakoutVol"),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bot", required=True, choices=sorted(BOTS) or ["trend"])
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--timeframe", default="1h")
    ap.add_argument("--bars", type=int, default=3000)
    ap.add_argument("--sims", type=int, default=64)
    ap.add_argument("--mean-block", type=int, default=20)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--db", default="sqlite:///data/research.db")
    args = ap.parse_args()

    import importlib

    mod_name, cls_name = BOTS.get(args.bot, BOTS["trend"])
    cls = getattr(importlib.import_module(mod_name), cls_name)

    df = in_sample(load_frame(args.db, args.symbol, args.timeframe)).iloc[: args.bars].copy()
    print(f"frame: {len(df)} bars | {args.sims} synthetic paths + baseline", flush=True)

    t0 = time.time()
    out = synthetic_path_mc(
        df, lambda: cls(), None, args.timeframe,
        n_simulations=args.sims, seed=args.seed, mean_block=args.mean_block,
    )
    el = time.time() - t0
    out["elapsed_seconds"] = round(el, 1)
    out["per_sim_seconds"] = round(el / (args.sims + 1), 2)
    out["bot"] = args.bot
    out["symbol"] = args.symbol
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
