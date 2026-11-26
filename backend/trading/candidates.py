"""Candidate enumeration — the F1 trend family's declared grid.

docs/research/program-2026-11-26.md §3 gives F1 a budget of 40 candidates.
This module is where the budget is spent in writing: the grid is fixed here,
countable, and small enough to read. A candidate never appears that is not
in this file — the ledger's count means something precisely because the
sampling frame is declared, not improvised at runtime.

Grid reasoning: lookbacks span the literature range at 4h bars (2/4/8/12
weeks), entry_z spans sign-following to selective, exit_z spans fast-death
to slow-death. 4×5×2 = 40 exactly — the budget fully allocated, no reserve.
"""

from trading.bots.trend_bot import TrendMomentum
from trading.search import Candidate

F1_LOOKBACKS = [84, 168, 336, 504]  # 2/4/8/12 weeks of 4h bars
F1_ENTRY_Z = [0.0, 0.5, 1.0, 1.5, 2.0]
F1_EXIT_Z = [0.0, 0.5, 1.0]


def trend_momentum_candidates(symbols=("BTCUSDT", "ETHUSDT")) -> list[Candidate]:
    """The F1 grid, one candidate per parameter point per symbol direction —
    symbols ride inside the candidate: the machinery evaluates per symbol
    and ledgers per symbol, because a trend that exists only on BTC is a
    different claim than a trend on the basket."""
    out = []
    for lookback in F1_LOOKBACKS:
        for entry_z in F1_ENTRY_Z:
            for exit_z in F1_EXIT_Z:
                # invalid when the exit band swallows the entry band: entry
                # fires inside the flat region and the exit never gets a
                # word — that is a broken state machine, not a candidate.
                # exit_z 0 with any entry is valid: momentum-held positions
                # managed by stops alone, the never-exit variant.
                if exit_z > 0 and entry_z <= exit_z:
                    continue
                params = {"lookback_bars": lookback, "entry_z": entry_z, "exit_z": exit_z}
                name = f"trendmom-L{lookback}-e{entry_z}-x{exit_z}"
                out.append(
                    Candidate(
                        family="F1-trend",
                        name=name,
                        bot_key="trendmom",
                        params=params,
                        make=lambda p: TrendMomentum(**p),
                        symbols=list(symbols),
                        timeframe="4h",
                    )
                )
    return out
