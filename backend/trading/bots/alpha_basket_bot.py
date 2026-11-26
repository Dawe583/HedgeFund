"""F11 — alpha-ranked cross-sectional basket. Declared in program-2026-11-26.

F10's verdict is the founding document: cross-sectional alphas per-symbol
are noise (0/20 validated, mean Sharpe -0.23) because the edge the bench
measured is RELATIVE — the alpha ranks the universe, it does not time any
one symbol. This family trades the ranking in its own shape: long the
alpha's top tail, short the bottom tail, rebalanced on a schedule, through
the same basket harness F3 built. The kernel never learns anything new —
targets are injected causally as `_xs_dir` exactly like F3, and execution,
rails and sizing stay where they have always been.

The honesty chain, end to end:
  1. the alpha is causal by the vendored zoo's operator discipline
     (delta requires d >= 1, negative shifts are absent)
  2. ranks at rebalance instant t use alpha values at bar t only
  3. targets persist as a step function until the next re-rank
  4. the kernel fills at the next open — the one-bar delay the whole
     design already measures everywhere
"""

from __future__ import annotations

import pandas as pd

from trading.bots.xs_basket_bot import XSBasket


class AlphaBasket(XSBasket):
    name = "alphabasket"
    timeframe = "4h"

    def __init__(
        self,
        alpha_compute=None,
        alpha_symbols=None,
        alpha_research_db: str | None = None,
        invert: bool = False,
        tail: int = 2,
        rebalance: int = 24,
    ) -> None:
        super().__init__(lookback=1, tail=tail, direction="momentum", rebalance=rebalance)
        self.alpha_compute = alpha_compute
        self.alpha_symbols = alpha_symbols
        self.alpha_research_db = alpha_research_db
        self.invert = invert

    def inject_cross_section(self, windows: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        """Rank by alpha value instead of trailing return. The alpha panel
        is computed over the full candle history (file-cached) and sliced
        to each window causally: alpha at bar t uses data up to t by the
        zoo's own construction, so a longer warm-up reaching before the
        window start is legitimate causal use, identical in shape to the
        kernel's own ATR warm-up."""
        if self.alpha_compute is None:
            raise SystemExit("AlphaBasket without alpha_compute is not a candidate")
        from trading.bots.alpha_signal_bot import _alpha_wide_cached

        syms = sorted(windows.keys())
        wide = _alpha_wide_cached(self.alpha_compute, self.alpha_research_db, syms, self.timeframe)
        if self.invert:
            wide = -wide

        union = pd.DatetimeIndex(sorted(set().union(*[w.index for w in windows.values()])))
        # timezone alignment BEFORE reindexing: comparing naive with aware
        # indexes raises inside reindex, so the alpha panel adopts the
        # windows' tz up front — the same honesty rule as the F10 adapter,
        # one level earlier
        if union.tz is not None and wide.index.tz is None:
            wide = wide.copy()
            wide.index = wide.index.tz_localize(union.tz)
        elif union.tz is None and wide.index.tz is not None:
            wide = wide.copy()
            wide.index = wide.index.tz_localize(None)
        alpha = wide.reindex(union, method="ffill")

        targets = pd.DataFrame(0, index=union, columns=syms)
        current = {s: 0 for s in syms}
        for pos, ts in enumerate(union):
            if pos % self.rebalance == 0:
                row = alpha.iloc[pos].dropna()
                row = row[[s for s in row.index if s in syms]]
                if len(row) >= 2 * self.tail:
                    ordered = row.sort_values()
                    bottom = list(ordered.index[: self.tail])
                    top = list(ordered.index[-self.tail:])
                    current = {s: 0 for s in syms}
                    for s in top:
                        current[s] = 1
                    for s in bottom:
                        current[s] = -1
            for s in syms:
                targets.iloc[pos, targets.columns.get_loc(s)] = current[s]

        out = {}
        for s, w in windows.items():
            w2 = w.copy()
            col = targets[s].reindex(w2.index, method="ffill").fillna(0).astype(int)
            w2["_xs_dir"] = col
            out[s] = w2
        return out
