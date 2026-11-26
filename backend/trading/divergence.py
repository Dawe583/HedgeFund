"""Divergence budget — the declared paper-vs-backtest drift contract (design §7).

What "drift" can honestly mean for THIS engine, and no more. The parity
contract is fill-at-close: a market order submitted when bar k closes fills
against bar k's auction. Both sides of the comparison run the same sandbox
matching code (parity by construction), so the drift dimensions are the
places where paper's live-clock reality can pull away from the backtest's
compressed tape:

1. **fill price deviation** — per entry/exit fill, the deviation in ticks
   from the reference price the role implies:
   - market roles (entry, signal_exit, timeout, restart_unrecoverable): the
     filling bar's close. In the sandbox this is structurally zero — any
     nonzero reading is evidence the venue model broke, and it becomes the
     paper → candidate_live execution evidence the moment a real venue
     adapter exists, where fills measurably land away from the close.
   - protective roles (stop, take_profit): the order's own level. Deviation
     here is gap-through slippage — the bar auction fills a gapped stop at
     the open, worse for the trader. Same model both engines, so a large
     reading is NOT paper-vs-backtest drift; it is execution cost both
     engines share. Measured anyway because the budget is declared per role
     class and the number is the honest one.
2. **entry timing lag** — the fill's bar position minus the signal bar's
   position minus one. The harness contract is signal(k-1) → fill at
   close(k): lag zero. The measured live-only divergence class (async
   command execution, kernel-diff-2026-11-25 §6) is exactly lag 1: the
   command chain clears after the next bar's quote. A sustained nonzero lag
   in production means the chain latency is approaching the bar interval —
   the desk is failing its parity contract.
3. **missed bars** — bars the stream never delivered and REST could not
   recover (the frame's counter). The soak acceptance criterion is zero;
   the budget declares how many the lifecycle tolerates before flagging.

What is explicitly NOT drift: veto-vs-backtest divergence (vetoes are the
rails working, a rail firing in paper that the backtest never saw is risk
discipline, not execution drift), rearm cost (restart semantics are their
own documented divergence class, audit-visible in the rearm fill, and a
budget cannot capture "the process died"), and distributional pnl drift at
small n (compare_distributions refuses below 30 trades per side — the same
statistical bar the validation gate sets; fake statistics over two trades
are worse than no statistics).

The budget is declared on the strategy version (registry.py): the design's
validation gate item 6 makes it part of the validated promise, one parameter
set on one universe — not a strategy constructor parameter, because the
constructor is what the STRATEGY is and the budget is what the LIFECYCLE
tolerates.
"""

from __future__ import annotations

from dataclasses import dataclass

# roles whose reference price is the filling bar's close; everything else
# protective references the order's own level
MARKET_ROLES = frozenset({"entry", "rearm", "signal_exit", "timeout", "restart_unrecoverable"})

# the statistical bar — same number the validation gate demands (design §7:
# "we set the bar at 30 for the CI to mean anything")
DISTRIBUTION_MIN_TRADES = 30


@dataclass(frozen=True)
class DivergenceBudget:
    """One version's declared tolerances. Defaults are the paper engine's
    honest zero-parity contract: the sandbox is the same matching code as
    the backtest, so nonzero readings are always evidence."""

    # dev default 2.0 ticks, not 0: fills quantize to the instrument's
    # price increment while the frame's close is the raw float, so the
    # measurement carries up to half a tick of rounding noise by
    # construction. 2.0 absorbs the quantization and nothing else — a real
    # venue divergence is tens of ticks.
    dev_ticks: float = 2.0
    entry_lag_bars: int = 0
    missed_bars: int = 0

    @classmethod
    def from_row(cls, version) -> "DivergenceBudget":
        """Read the declared budget off a strategy_versions row; nullable
        columns mean 'never declared' and fall back to the defaults — a
        version registered before slice 5 has the paper engine's zero-drift
        contract, honestly reported as defaults, not invented precision."""
        return cls(
            dev_ticks=version.budget_dev_ticks if version.budget_dev_ticks is not None else cls.dev_ticks,
            entry_lag_bars=(
                version.budget_entry_lag_bars if version.budget_entry_lag_bars is not None else cls.entry_lag_bars
            ),
            missed_bars=version.budget_missed_bars if version.budget_missed_bars is not None else cls.missed_bars,
        )


def reference_price(role: str, bar_close: float, stop_loss: float, take_profit: float) -> float:
    """The price the role INTENDED. Market roles intend the filling bar's
    close (fill-at-close parity); protective roles intend their own level,
    so the deviation reads gap-through slippage instead of the protective
    distance, which is design, not drift."""
    if role == "stop":
        return stop_loss
    if role == "take_profit":
        return take_profit
    return bar_close


def dev_ticks(fill_price: float, ref_price: float, tick_size: float) -> float:
    """Signed deviation in ticks — sign kept because systematic sign IS the
    signal (consistently negative entry deviation on a real venue reads as
    adverse selection; magnitude alone hides it)."""
    if tick_size <= 0 or ref_price <= 0:
        return 0.0
    return (fill_price - ref_price) / tick_size


def budget_breaches(budget: DivergenceBudget, *, dev: float | None = None, lag_bars: int | None = None) -> list[str]:
    """Which dimensions a single fill's measurement violates. Pure — the
    caller decides what a breach means (a risk_events row in the desk)."""
    out = []
    if dev is not None and abs(dev) > budget.dev_ticks:
        out.append("dev_ticks")
    if lag_bars is not None and lag_bars > budget.entry_lag_bars:
        out.append("entry_lag_bars")
    return out


def compare_distributions(bt_pnls: list[float], paper_pnls: list[float]) -> dict | None:
    """Paper-vs-backtest per-trade pnl comparison, gated on the statistical
    bar. None means the comparison is not meaningful yet — the honest answer
    at small n, and the only answer M3's empty registry can produce in
    production today.

    Descriptive, never inferential: both means/medians, and whether the
    paper mean lies inside the backtest distribution's central 90% — a
    positioning statement, not a test statistic with a p-value. A formal
    two-sample test over 30 autocorrelated trades would be its own fake
    precision; the lifecycle reads this as evidence texture beside the
    per-fill mechanical drift, which is meaningful at n=1.
    """
    if len(bt_pnls) < DISTRIBUTION_MIN_TRADES or len(paper_pnls) < DISTRIBUTION_MIN_TRADES:
        return None
    bt = sorted(bt_pnls)
    n = len(bt)
    lo = bt[int(0.05 * n)]
    hi = bt[min(n - 1, int(0.95 * n))]
    paper_mean = sum(paper_pnls) / len(paper_pnls)
    bt_mean = sum(bt_pnls) / n
    return {
        "bt_trades": n,
        "paper_trades": len(paper_pnls),
        "bt_mean_pnl": bt_mean,
        "paper_mean_pnl": paper_mean,
        "bt_median_pnl": bt[n // 2],
        "paper_mean_within_bt_p5_p95": lo <= paper_mean <= hi,
        "bt_p5": lo,
        "bt_p95": hi,
    }
