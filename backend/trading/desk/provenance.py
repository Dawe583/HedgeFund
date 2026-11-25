"""Desk provenance — the DB is the record, kernel state is derived.

Two rules the whole desk obeys:

1. Kernel state (positions, orders) is IN-MEMORY and dies with the process.
   SQLite rows written synchronously inside the fill event itself — never
   batched, never end-of-run. A crash loses at most the in-flight event,
   and the restart logic treats kernel truth as nonexistent anyway.

2. Rows are written in the node loop's thread (the hook fires inside the
   kernel's event dispatch). SQLite writes at bar cadence are microseconds;
   blocking risk is nil, and correctness demands no queue in between.

Timestamps: entry/exit times come from the FILL's ts_event (kernel fact),
converted with the bar-interval convention — a fill stamped at a bar close
belongs to that bar's open key. `signal_time` is the frame timestamp of the
signal bar; it is what restart rebuilds the timeout counting from, because
bar indices are meaningless across processes.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import delete, select

from trading.models import EquityPoint, OpenPosition, Trade


def _utc_from_ns(ts_ns: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(ts_ns / 1e9, tz=dt.UTC)


def frame_time_at(df, pos: int) -> dt.datetime:
    """Frame-index timestamp as a tz-aware datetime — the signal bar's own
    clock, immune to arrival-time drift."""
    ts = df.index[pos]
    if getattr(ts, "tzinfo", None) is None:
        ts = ts.tz_localize("UTC")
    return ts.to_pydatetime()


class DeskLedger:
    """Writes position lifecycle events into the shared trading tables.
    One instance per desk (not per strategy) — SQLite serializes anyway."""

    def __init__(self, session_factory, interval_ns: int):
        self._sf = session_factory
        self._interval_ns = interval_ns

    def fill_time(self, ts_event_ns: int) -> dt.datetime:
        # kernel fills are stamped at the CLOSE of the filling bar; the
        # bar-open key is the frame's indexing convention everywhere else
        return _utc_from_ns(ts_event_ns - self._interval_ns)

    def entry_opened(self, bot: str, spec: dict, pos: dict) -> int:
        """INSERT the open position the moment its entry fills. Returns the
        row id so the close path updates instead of searching."""
        fill = pos["entry_fill"]
        session = self._sf()
        try:
            row = OpenPosition(
                bot=bot,
                symbol=spec["symbol"],
                side=pos["side"],
                qty=pos["qty"],
                entry_price=fill["price"],
                stop_loss=pos["stop_loss"],
                take_profit=pos["take_profit"],
                opened_at=self.fill_time(fill["ts_event"]),
                signal_time=pos.get("signal_time"),
                confidence=pos["confidence"],
                gate_source="kernel",
            )
            session.add(row)
            session.commit()
            return row.id
        finally:
            session.close()

    def position_closed(self, bot: str, spec: dict, pos: dict) -> None:
        """Write the completed trade and remove the open row — atomically in
        one transaction, so the DB never shows a position that is both open
        and traded."""
        entry = pos["entry_fill"]
        exit_ = pos["exit_fill"]
        session = self._sf()
        try:
            trade = Trade(
                bot=bot,
                symbol=spec["symbol"],
                side=pos["side"],
                qty=pos["qty"],
                entry_price=pos["entry_price_net"],
                exit_price=pos["exit_price_net"],
                entry_time=self.fill_time(entry["ts_event"]),
                exit_time=self.fill_time(exit_["ts_event"]),
                pnl=pos["pnl"],
                fees=pos["fees"],
                confidence=pos["confidence"],
                mode="paper",
                gate_source="kernel",
            )
            session.add(trade)
            row_id = pos.get("ledger_row_id")
            if row_id is not None:
                session.execute(delete(OpenPosition).where(OpenPosition.id == row_id))
            session.commit()
        finally:
            session.close()

    def equity_point(self, equity: float, bot: str = "portfolio") -> None:
        session = self._sf()
        try:
            session.add(EquityPoint(bot=bot, equity=equity))
            session.commit()
        finally:
            session.close()

    def open_positions(self, bot: str) -> list[OpenPosition]:
        session = self._sf()
        try:
            return list(
                session.execute(
                    select(OpenPosition).where(OpenPosition.bot == bot)
                ).scalars()
            )
        finally:
            session.close()
