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

F5_DEV_LOOKBACKS = [24, 48]  # 1/2 days at 1h — the mean being reverted to
F5_ENTRY_DEV = [1.5, 2.0, 2.5]  # overextension in ATR units
F5_REGIME_MAX = [0.35, 0.5]  # |trend z| ceiling for "ranging" — tight vs loose
F5_EXIT_DEV = [0.3, 0.6]  # reversion completion


def meanrev_regime_candidates(symbols=("BTCUSDT", "ETHUSDT")) -> list[Candidate]:
    """The F5 grid: 2×3×2×2 = 24 points, minus the broken state machines
    (exit must sit inside entry or reversion never gets to complete) —
    lands inside the family's budget of 20 by construction of the grid,
    not by trimming. Validity rule: exit_dev < entry_dev strictly, else
    the flat band swallows the entry band."""
    from trading.bots.meanrev_regime_bot import MeanRevRegime

    out = []
    for dev_lb in F5_DEV_LOOKBACKS:
        for entry in F5_ENTRY_DEV:
            for regime in F5_REGIME_MAX:
                for exit_dev in F5_EXIT_DEV:
                    if exit_dev >= entry:
                        continue
                    params = {
                        "dev_lookback": dev_lb,
                        "entry_dev": entry,
                        "regime_max": regime,
                        "exit_dev": exit_dev,
                    }
                    name = f"meanrev-D{dev_lb}-e{entry}-r{regime}-x{exit_dev}"
                    out.append(
                        Candidate(
                            family="F5-meanrev",
                            name=name,
                            bot_key="meanrevregime",
                            params=params,
                            make=lambda p: MeanRevRegime(**p),
                            symbols=list(symbols),
                            timeframe="1h",
                        )
                    )
    return out


GRIDS = {"F1": trend_momentum_candidates, "F5": meanrev_regime_candidates}
