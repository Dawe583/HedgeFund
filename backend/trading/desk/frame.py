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

import logging

import pandas as pd

from trading.features import build_features

log = logging.getLogger(__name__)


class IncrementalFrame:
    """Frame source for the kernel harness strategy in a live node.

    Seeded with historical candles (feature warm-up needs ~130 bars before
    vol_z and the EMAs converge — a cold node must never trade on noise),
    then extended one row per closed bar by the strategy itself, before any
    evaluation, inside `on_bar`.
    """

    def __init__(self, interval_ns: int | None = None, backfill=None):
        """
        interval_ns: the bar interval in nanoseconds. When given, incoming
        bar timestamps are normalized to the bar-open key and missing bars
        are counted. The desk always passes it; plain construction keeps the
        raw pass-through behavior for isolated users of the class.

        backfill: optional callable (after_open_ns, before_open_ns) ->
        list of candle dicts covering the open times strictly between the
        two keys. Wired in production to the binance REST fetcher; the bars
        a live stream can never deliver are the ones that closed while the
        socket was still connecting — recovering them before first use is
        what makes "no missed tick" an achievable acceptance rather than a
        boot-time lottery.
        """
        self._rows: list[dict] = []
        self._index: list[pd.Timestamp] = []
        self._frame: pd.DataFrame = build_features(self._empty())
        self._last_open_ns: int | None = None
        self._interval_ns = interval_ns
        self._backfill = backfill
        self.missed_bars = 0  # closed bars never recovered — the soak's failure metric
        self.backfilled_bars = 0  # closed bars the stream missed but REST recovered

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
        if self._index:
            self._last_open_ns = int(self._index[-1].value)
        self._rebuild()

    @staticmethod
    def _key_ns(open_time) -> int:
        """Bar-open key in nanoseconds from a seed/backfill row timestamp —
        the same key space the normalized bar stream uses."""
        ts = pd.Timestamp(open_time)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        return int(ts.value)

    def _check_gap(self, open_ns: int, prev_ns: int) -> int:
        """Count bars skipped between consecutive keys and try to recover
        them. The arithmetic is the honest sequence check a closed-bar
        stream offers: the kline WS publishes no sequence id, and bar k's
        absence is knowable only when bar k+1 (or later) arrives — detection
        is one bar late by construction. Recovery runs BEFORE the triggering
        bar's append so insertion stays order-safe; whatever REST cannot
        recover is what `missed_bars` counts."""
        if self._interval_ns is None:
            return 0
        gap = (open_ns - prev_ns) // self._interval_ns - 1
        if gap <= 0:
            return 0
        unrecovered = self._recover_gap(prev_ns, open_ns)
        if unrecovered > 0:
            self.missed_bars += unrecovered
            log.error(
                "bar stream gap: %d closed bar(s) unrecovered before open %s",
                unrecovered,
                pd.Timestamp(open_ns, unit="ns", tz="UTC"),
            )
        return unrecovered

    def _insert_backfilled(self, rows: list[dict]) -> int:
        """Insert recovered bars BEFORE the live append. Order-safe by
        construction: every backfilled key is strictly greater than the last
        key already present (the window starts after it) and strictly less
        than the incoming bar's key, so appending them now keeps both arrays
        sorted ascending without any positional arithmetic."""
        existing = set(self._index)
        n = 0
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
            n += 1
        return n

    def _recover_gap(self, after_open_ns: int, before_open_ns: int) -> int:
        """Attempt REST backfill of the gap between two consecutive keys.
        Returns the number of unrecovered bars. Failure modes are loud, not
        silent: a fetch exception leaves the gap counted as missed and is
        logged — a desk that cannot recover history must know it."""
        missing = (before_open_ns - after_open_ns) // self._interval_ns - 1
        if self._backfill is None:
            return missing
        try:
            rows = self._backfill(after_open_ns, before_open_ns) or []
        except Exception:
            log.exception("backfill fetch failed — gap stays missed")
            return missing
        # strictly-inside filter: REST windows are inclusive and the source
        # cannot be trusted to exclude the boundary bars — the left one
        # already sits in the frame, the right one is the live bar whose own
        # append follows this insertion. Anything outside the open interval
        # (after, before) is not this gap's to insert.
        rows = [
            r for r in rows
            if after_open_ns < self._key_ns(r["open_time"]) < before_open_ns
        ]
        recovered = self._insert_backfilled(rows)
        self.backfilled_bars += recovered
        if recovered:
            log.warning(
                "backfilled %d bar(s) the stream missed before open %s",
                recovered,
                pd.Timestamp(before_open_ns, unit="ns", tz="UTC"),
            )
        return missing - recovered

    def on_bar_close(self, bar) -> None:
        """Append the kernel bar that just closed — the strategy calls this
        before evaluating, so the frame and the bar stream can never drift
        apart. The frame's key is the bar OPEN.

        Timestamp normalization: the kernel/harness convention (replay,
        `kernel.build_bars`) stamps ts_event AT the open; the Binance
        adapter stamps it at the close (kline.T — see the adapter's
        `parse_to_binance_bar`). Flooring to the interval boundary is the
        identity for open-stamped feeds and maps close-stamped feeds onto
        the open for every T strictly inside the interval — Binance's T is
        the interval's last millisecond, never the boundary. A close-stamped
        feed whose T landed exactly on the boundary would key one bar ahead;
        that failure mode is documented, not silently absent."""
        open_ns = int(bar.ts_event)
        if self._interval_ns is not None:
            open_ns = (open_ns // self._interval_ns) * self._interval_ns
        if self._last_open_ns is not None:
            if open_ns <= self._last_open_ns:
                return  # duplicate or out-of-order delivery — never append twice
            self._check_gap(open_ns, self._last_open_ns)
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
