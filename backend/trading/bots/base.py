"""Strategy contract shared by backtest + paper engines."""

from trading.backtest.engine import Signal


class BaseStrategy:
    """Subclasses implement `signal(i, df)` using ONLY rows <= i."""

    name: str = "base"
    timeframe: str = "1h"

    def signal(self, i: int, df) -> Signal | None:
        raise NotImplementedError
