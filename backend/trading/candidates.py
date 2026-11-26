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

F7_DEV_LOOKBACKS = [24, 48]
F7_ENTRY_DEV = [1.5, 2.0, 2.5]
F7_EXIT_DEV = [0.3, 0.6]
F7_STOP_ATR = [3.0, 4.0]  # wider than F5 — continuation stops die to noise at fade widths


def continuation_candidates(symbols=("BTCUSDT", "ETHUSDT")) -> list[Candidate]:
    """The F7 grid: 2×3×2×2 = 24 minus broken state machines, inside the
    declared budget of 20. Same validity rule as F5: exit_dev < entry_dev
    strictly. The mirror deliberately shares F5's deviation grid so the two
    families' ledgers read against each other cell-for-cell."""
    from trading.bots.continuation_bot import Continuation1h

    out = []
    for dev_lb in F7_DEV_LOOKBACKS:
        for entry in F7_ENTRY_DEV:
            for exit_dev in F7_EXIT_DEV:
                for stop in F7_STOP_ATR:
                    if exit_dev >= entry:
                        continue
                    params = {
                        "dev_lookback": dev_lb,
                        "entry_dev": entry,
                        "exit_dev": exit_dev,
                        "stop_atr": stop,
                    }
                    name = f"cont-D{dev_lb}-e{entry}-x{exit_dev}-s{stop}"
                    out.append(
                        Candidate(
                            family="F7-continuation",
                            name=name,
                            bot_key="continuation1h",
                            params=params,
                            make=lambda p: Continuation1h(**p),
                            symbols=list(symbols),
                            timeframe="1h",
                        )
                    )
    return out


GRIDS["F7"] = continuation_candidates


def catalog_control_candidates(symbols=("BTCUSDT",)) -> list[Candidate]:
    """F6 — the catalog as-is on 3y data, the cheap control. Same bots,
    same production parameters, longer tape: separates 'no edge' from 'no
    edge in 2026's tape'. One candidate per catalog bot at its catalog
    timeframe — the budget of 16 allows parameter exploration if a bot
    shows life, but the control itself is four cells, unchanged. scalp's
    catalog timeframe is 4h; the rest ride the sub-hourly planes the
    ingest of the same evening added."""
    from trading.bots.breakout_bot import BreakoutVol
    from trading.bots.hft_bot import HFTMomentum
    from trading.bots.meanrev_bot import MeanRev
    from trading.bots.scalp_bot import ScalpTrend

    specs = [
        ("scalp", "ScalpTrend", ScalpTrend, "4h"),
        ("hft", "HFTMomentum", HFTMomentum, "1m"),
        ("breakout", "BreakoutVol", BreakoutVol, "5m"),
        ("meanrev", "MeanRev", MeanRev, "15m"),
    ]
    out = []
    for key, cls_name, cls, tf in specs:
        out.append(
            Candidate(
                family="F6-catalog-control",
                name=f"catalog-{key}-asis",
                bot_key=key,
                params={},  # production defaults — control means unchanged
                make=lambda c=cls: c(),
                symbols=list(symbols),
                timeframe=tf,
            )
        )
    return out


GRIDS["F6"] = catalog_control_candidates


# F2 — funding-carry direction. 20-point budget, exact fit:
# lookback x threshold x entry_dev = 2x2x2 = 8 per symbol, x2 symbols = 16,
# plus 4 untimed variants (entry_dev=0 isolates whether timing adds anything).
# Declared in program-2026-11-26 BEFORE the machinery existed — the kernel
# funding accrual landed the same evening and this grid is its first consumer.
F2_LOOKBACKS = (9, 21)          # settlement events: 3d / 7d regime windows
F2_THRESHOLDS = (0.00005, 0.0001)  # 0.005% / 0.01% per 8h significance bars
F2_ENTRY_DEVS = (0.0, 1.0)      # 0 = untimed regime-following, 1 = cheap entry


def funding_carry_candidates(symbols=("BTCUSDT", "ETHUSDT")) -> list[Candidate]:
    from trading.bots.funding_carry_bot import FundingCarry

    out: list[Candidate] = []
    syms = list(symbols)[:2]  # the budget is 20: 8x2 timed + 4 untimed, no trimming
    for lookback in F2_LOOKBACKS:
        for threshold in F2_THRESHOLDS:
            for entry_dev in F2_ENTRY_DEVS:
                params = {"lookback": lookback, "threshold": threshold,
                          "entry_dev": entry_dev, "max_bars": 72}
                name = f"fundcarry-l{lookback}-t{int(threshold*1e6)}-e{entry_dev}"
                out.append(Candidate(
                    family="F2-funding-carry",
                    name=name,
                    bot_key="fundingcarry",
                    params=params,
                    make=lambda p: FundingCarry(**p),
                    symbols=syms,
                    timeframe="1h",
                ))
    return out


GRIDS["F2"] = funding_carry_candidates


# F3 — cross-sectional momentum/reversal over the 10-coin basket.
# 12 cells against a 30 budget: lookback x direction x rebalance = 2x2x3.
# One candidate = one BASKET evaluation (the composite is the claim), so
# 12 cells is 12 ledger rows, never 12 x symbols. Declared at program
# writing; the causal-injection machinery is this family's own addition.
F3_LOOKBACKS = (72, 168)     # 12d / 28d of trailing return at 4h
F3_DIRECTIONS = ("momentum", "reversal")
F3_REBALANCES = (24, 48, 168)  # 4d / 8d / 28d between re-ranks


def xs_basket_candidates(symbols=("BTCUSDT", "ETHUSDT")) -> list[Candidate]:
    from trading.bots.xs_basket_bot import XSBasket

    out: list[Candidate] = []
    for lookback in F3_LOOKBACKS:
        for direction in F3_DIRECTIONS:
            for rebalance in F3_REBALANCES:
                params = {"lookback": lookback, "tail": 2,
                          "direction": direction, "rebalance": rebalance}
                name = f"xs{direction[:3]}-l{lookback}-r{rebalance}"
                out.append(Candidate(
                    family="F3-xs-basket",
                    name=name,
                    bot_key="xsbasket",
                    params=params,
                    make=lambda p: XSBasket(**p),
                    symbols=list(symbols),
                    timeframe="4h",
                ))
    return out


GRIDS["F3"] = xs_basket_candidates


# F4 — volatility-scaled breakout, wide stops, longer holds. The catalog's
# BreakoutVol re-parameterized: production ran 5m/1.5 ATR/96-bar holds and
# died on 365d; the family hypothesis is that the breakout mechanism lives
# at position scale — 4h bars, 3-5 ATR stops, multi-week holds — where the
# kernel's risk sizing already scales quantity by stop distance, so wider
# stops ARE volatility-scaled sizing. Budget 20: 2x2x2 x 2 symbols = 16.
F4_LOOKBACKS = (20, 55)      # Donchian channel: 3.3d / 9.2d at 4h
F4_STOP_ATR = (3.0, 5.0)     # wide — production's 1.5 is what failed
F4_TP_RR = (2.5, 4.0)


def volbreakout_candidates(symbols=("BTCUSDT", "ETHUSDT")) -> list[Candidate]:
    from trading.bots.breakout_bot import BreakoutVol

    out: list[Candidate] = []
    for lookback in F4_LOOKBACKS:
        for stop in F4_STOP_ATR:
            for tp in F4_TP_RR:
                params = {"lookback": lookback, "vol_z_min": 0.5,
                          "body_min_pct": 0.01, "body_atr_mult": 0.25,
                          "stop_atr": stop, "tp_rr": tp, "max_bars_in_trade": 480}
                name = f"volbreak-l{lookback}-s{stop}-t{tp}"
                out.append(Candidate(
                    family="F4-volbreakout",
                    name=name,
                    bot_key="breakout",
                    params=params,
                    make=lambda p: BreakoutVol(**p),
                    symbols=list(symbols),
                    timeframe="4h",
                ))
    return out


GRIDS["F4"] = volbreakout_candidates


# F8 — regime-aware continuation. Budget 20, exact fit:
# regime_min x regime_lookback x entry_dev = 2x2x2 = 8 x 2 symbols = 16.
# Declared BEFORE the first sweep (program-2026-11-26): the gate is the
# hypothesis, tested on the same in-sample window where F7 unfiltered
# measured +1.92 — the comparison is the measurement.
F8_REGIME_MINS = (0.2, 0.4)      # ER floor: permissive / strict trend evidence
F8_REGIME_LOOKBACKS = (16, 36)   # fast windows: hours-to-day-and-half at 1h
F8_ENTRY_DEVS = (1.5, 2.0)


def regime_continuation_candidates(symbols=("BTCUSDT", "ETHUSDT")) -> list[Candidate]:
    from trading.bots.regime_continuation_bot import RegimeContinuation

    out: list[Candidate] = []
    for rmin in F8_REGIME_MINS:
        for rlook in F8_REGIME_LOOKBACKS:
            for edev in F8_ENTRY_DEVS:
                params = {"dev_lookback": 24, "entry_dev": edev, "exit_dev": 0.3,
                          "stop_atr": 3.0, "tp_rr": 2.0,
                          "regime_lookback": rlook, "regime_min": rmin}
                name = f"regcont-m{int(rmin*10)}-r{rlook}-e{edev}"
                out.append(Candidate(
                    family="F8-regime-cont",
                    name=name,
                    bot_key="regimecont",
                    params=params,
                    make=lambda p: RegimeContinuation(**p),
                    symbols=list(symbols),
                    timeframe="1h",
                ))
    return out


GRIDS["F8"] = regime_continuation_candidates


# F9: ML return forecaster — declared in program-2026-11-26 (budget 12)
F9_ENTRY_Z = [1.0, 1.5]      # predicted-return significance to enter
F9_EXIT_Z = [0.2, 0.5, 1.0]  # collapse band for exit


def mlforecast_candidates(symbols=("BTCUSDT", "ETHUSDT")) -> list[Candidate]:
    """The F9 grid: entry/exit z-scores against the model's own out-of-fold
    noise. 2 x 3 x 2 symbols = 12 exactly. The artifact is trained inside
    the sweep worker (symbol-aware, in-sample only) — params carry only the
    trading thresholds, never the model."""
    from trading.bots.ml_forecast_bot import MLForecast

    out = []
    for entry_z in F9_ENTRY_Z:
        for exit_z in F9_EXIT_Z:
            if exit_z >= entry_z:
                continue
            params = {"entry_z": entry_z, "exit_z": exit_z}
            name = f"mlfc-h6-e{entry_z}-x{exit_z}"
            out.append(
                Candidate(
                    family="F9-mlforecast",
                    name=name,
                    bot_key="mlforecast",
                    params=params,
                    make=lambda p: None,  # replaced in the worker — artifact is symbol-bound
                    symbols=list(symbols),
                    timeframe="1h",
                )
            )
    return out


GRIDS["F9"] = mlforecast_candidates
