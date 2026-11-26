"""F3 — cross-sectional momentum/reversal over a basket. Declared in
program-2026-11-26:

    rank coins by trailing return, hold tails, rebalance slow —
    diversification across idiosyncratic coins raises Sharpe mechanically.

The mechanism is cross-sectional, so the information cannot live in one
symbol's frame: the ranking needs every coin's trailing return at once.
The harness boundary stays clean by construction — ranks are computed
CAUSALLY and injected as a per-bar target column (`_xs_dir`: +1 long,
-1 short, 0 flat) before the kernel runs, so the strategy reads only past
truth at every bar and the kernel keeps owning execution, rails and
sizing exactly as it does for every other family.

Injection happens in `evaluate_basket` through the `inject_cross_section`
hook: the candidate instance transforms the window frames before any
backtest starts. Rebalance instants are a step function — targets persist
between them — and every rank uses trailing returns over data strictly
already closed, so no lookahead is possible by construction.
"""

from __future__ import annotations

import math

import pandas as pd

from trading.backtest.engine import Signal
from trading.bots.base import BaseStrategy


class XSBasket(BaseStrategy):
    name = "xsbasket"
    timeframe = "4h"

    def __init__(
        self,
        lookback: int = 72,       # bars of trailing return in the rank (72 x 4h = 12d)
        tail: int = 2,            # coins held per side
        direction: str = "reversal",  # "momentum" rides winners, "reversal" fades them
        rebalance: int = 24,      # bars between re-ranks (24 x 4h = 4d)
    ) -> None:
        self.lookback = lookback
        self.tail = tail
        self.direction = direction
        self.rebalance = rebalance

    def inject_cross_section(self, windows: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        """Add `_xs_dir` to every symbol's frame: the causal cross-sectional
        target. At each rebalance instant the trailing-return rank over the
        union panel decides the tails; targets forward-fill until the next
        re-rank. Momentum longs winners and shorts losers; reversal inverts.
        Rows before the first full lookback carry 0 — the panel honestly
        does not know yet."""
        union = pd.DatetimeIndex(sorted(set().union(*[w.index for w in windows.values()])))
        closes = pd.DataFrame({
            s: w["close"].reindex(union, method="ffill") for s, w in windows.items()
        })
        rets = closes / closes.shift(self.lookback) - 1.0
        targets = pd.DataFrame(0, index=union, columns=closes.columns)
        syms = list(closes.columns)
        current = {s: 0 for s in syms}
        for pos, ts in enumerate(union):
            if pos % self.rebalance == 0 and pos >= self.lookback:
                row = rets.iloc[pos].dropna()
                if len(row) >= 2 * self.tail:
                    ordered = row.sort_values()
                    losers = list(ordered.index[: self.tail])
                    winners = list(ordered.index[-self.tail:])
                    current = {s: 0 for s in syms}
                    if self.direction == "reversal":
                        for s in losers:
                            current[s] = 1
                        for s in winners:
                            current[s] = -1
                    else:
                        for s in winners:
                            current[s] = 1
                        for s in losers:
                            current[s] = -1
            for s in syms:
                targets.iloc[pos, targets.columns.get_loc(s)] = current[s]
        out = {}
        for s, w in windows.items():
            w2 = w.copy()
            col = targets[s].reindex(w2.index, method="ffill").fillna(0).astype(int)
            w2["_xs_dir"] = col.values
            out[s] = w2
        return out

    def signal(self, i: int, df) -> Signal | None:
        try:
            if "_xs_dir" not in df.columns:
                return None
            target = int(df["_xs_dir"].iloc[i])
            if target == 0:
                return Signal(side="flat", confidence=0.5)
            row = df.iloc[i]
            close = float(row["close"])
            if not (math.isfinite(close) and close > 0):
                return None
            # crash insurance only: the rebalance is the exit, the stop is
            # the harness's protection against the gap between them — 6 ATR
            # wide, tp effectively never (vocabulary needs a number)
            side = "long" if target > 0 else "short"
            return Signal(side=side, confidence=0.6, stop_atr=6.0, tp_rr=12.0)
        except Exception:
            return None
