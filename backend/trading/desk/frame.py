"""Incremental feature frame for the paper desk — the live twin of the
backtest's precomputed frame.

Parity contract: features come from `trading.features.build_features`, the
one implementation, recomputed over the whole retained window whenever a bar
closes. Never an incremental approximation of it — a second feature
computation is a second truth, and parity dies there first.

Bars are never dropped within a run: the harness contract hands the strategy
`frame.iloc[:i+1]` keyed by *global* bar index, so pruning history would
shift positions and silently misalign signal bars. Memory is bounded in
practice by worker restarts; the numbers (a 1m bar row ≈ 200 B, ~1 MB per
instrument-day-year) make this a non-issue at desk cadences.
"""

from __future__ import annotations

import pandas as pd

from trading.features import build_features


class IncrementalFrame:
    """Frame source for the kernel harness strategy in a live node.

    Seeded with historical candles (feature warm-up needs ~130 bars before
    vol_z and the EMAs converge — a cold node must never trade on noise),
    then extended one row per closed bar by the strategy itself, before any
    evaluation, inside `on_bar`.
    """

    def __init__(self):
        self._rows: list[dict] = []
        self._index: list[pd.Timestamp] = []
        self._frame: pd.DataFrame = build_features(self._empty())
        self._last_open_ns: int | None = None

    @staticmethod
    def _empty() -> pd.DataFrame:
        return pd.DataFrame(
            {"open": [], "high": [], "low": [], "close": [], "volume": []},
            index=pd.DatetimeIndex([], tz="UTC"),
        )

    def seed(self, rows: list[dict]) -> None:
        """Bulk-load history before the node starts. Rows carry open_time,
        open, high, low, close, volume — the candle shape `build_features`
        already eats. Duplicates of bars already present are dropped."""
        existing = set(self._index)
        for r in rows:
            ts = pd.Timestamp(r["open_time"])
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            if ts in existing:
                continue
            self._index.append(ts)
            self._rows.append(
                {
                    "open": float(r["open"]),
                    "high": float(r["high"]),
                    "low": float(r["low"]),
                    "close": float(r["close"]),
                    "volume": float(r.get("volume", 0.0)),
                }
            )
            existing.add(ts)
        self._rebuild()

    def on_bar_close(self, bar) -> None:
        """Append the kernel bar that just closed — the strategy calls this
        before evaluating, so the frame and the bar stream can never drift
        apart. ts_event is the bar OPEN (the kernel/harness convention from
        `kernel.build_bars`), which is the frame index's key."""
        open_ns = int(bar.ts_event)
        if self._last_open_ns is not None and open_ns <= self._last_open_ns:
            return  # duplicate or out-of-order delivery — never append twice
        self._last_open_ns = open_ns
        ts = pd.Timestamp(open_ns, unit="ns", tz="UTC")
        self._index.append(ts)
        self._rows.append(
            {
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": float(bar.volume),
            }
        )
        self._rebuild()

    def frame(self) -> pd.DataFrame:
        return self._frame

    def __len__(self) -> int:
        return len(self._frame)

    def _rebuild(self) -> None:
        if not self._rows:
            return
        df = pd.DataFrame(self._rows, index=pd.DatetimeIndex(self._index, tz="UTC"))
        self._frame = build_features(df)
