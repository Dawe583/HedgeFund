"""Anti-lookahead harness — the discipline the engine alone does not enforce.

`run_backtest` hands the strategy the full dataframe and calls
`strategy.signal(i - 1, df)`; nothing stops a strategy from reading row i+5.
That is a promise made of discipline, and discipline is exactly what a
validation pipeline exists to replace (design §7).

The harness wrapper makes the guarantee structural instead: the frame the
strategy receives is truncated at the just-closed bar, so indexing past it
raises instead of answering — inside the strategy's own try/except that
means "no signal", which is the correct outcome for a strategy that cannot
exist without cheating. A test in tests_trading proves a deliberately
cheating strategy gets no future data and that an honest strategy produces
identical trades with and without the wrapper.
"""

from __future__ import annotations

from trading.backtest.engine import Signal


class HarnessStrategy:
    """Wrap a pure strategy so signal(i, df) can only see bars <= i."""

    def __init__(self, inner):
        self.inner = inner

    def signal(self, i: int, df) -> Signal | None:
        if i < 0:
            return None
        return self.inner.signal(i, df.iloc[: i + 1])

    def __getattr__(self, name):
        # Parameters stay visible for provenance (research.py reads them off
        # the strategy object); everything else belongs to the inner object.
        return getattr(self.inner, name)


def wrap(strategy) -> HarnessStrategy:
    return HarnessStrategy(strategy)
