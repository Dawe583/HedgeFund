"""Replay feeder — deterministic bars into a live TradingNode for tests.

NOT a mock of the engine: the feeder only publishes. Bars travel the real
path — msgbus endpoint `DataEngine.process`, the same one the production
binance client uses — through the live DataEngine's routing to subscribed
strategies and to the sandbox exchange's matching engine. Everything between
the publication and the fill is the unmodified kernel; the test therefore
measures the engine itself, never a reimplementation of it.

Emission is a timer on the node's own loop, which is the only thread-safe
way to feed a running node: the msgbus is single-threaded by design.

Bars and the instrument are constructor arguments, NOT config fields —
msgspec-serialized configs cannot carry kernel objects (measured: encoding
a Bar raises TypeError at actor construction). Plain attributes are not
state the kernel ever needs to persist: the replay feed is a test harness,
not a recoverable venue position.
"""

from __future__ import annotations

import datetime as dt

from nautilus_trader.common.actor import Actor
from nautilus_trader.config import ActorConfig


class ReplayFeeder(Actor):
    """Publishes the instrument once, then one prebuilt bar per timer fire.

    `bars` are kernel `Bar` objects built by `trading.kernel.build_bars` —
    ts_event at the bar open, ts_init at the close, the same convention the
    backtest uses, so the harness's bar indexing means the same thing in
    both contexts.
    """

    def __init__(self, *, bars, instrument, interval_ms: int = 5, feeder_id: str | None = None, quiescence=None):
        # component_id doubles as the actor id — two feeders on one node
        # (multi-symbol tests) collide on the class-derived default
        super().__init__(ActorConfig(component_id=feeder_id) if feeder_id else ActorConfig())
        self._bars = bars
        self._instrument = instrument
        self._interval_ms = interval_ms
        # quiescence: optional callable -> bool, True when the consumer has
        # processed every emitted bar AND every command it submitted has been
        # adjudicated (fill/accept/reject/cancel). When given, emission pauses
        # until the system is quiet — the live loop's command drain is
        # asynchronous, and a tape that outruns it fills orders bars late,
        # an artifact of time compression no production cadence can produce:
        # real intervals give the drain hours, not milliseconds.
        self._quiescence = quiescence
        self._i = 0

    @property
    def emitted(self) -> int:
        return self._i

    def on_start(self):
        # the instrument must reach the sandbox exchange before the first
        # bar does — the exchange refuses to match against an unknown book
        self.msgbus.send(endpoint="DataEngine.process", msg=self._instrument)
        if self._bars:
            self.clock.set_timer(
                name="replay-feed",
                interval=dt.timedelta(milliseconds=self._interval_ms),
                callback=self._emit,
                fire_immediately=True,
            )

    def _emit(self, event):
        if self._i >= len(self._bars):
            self.clock.cancel_timer("replay-feed")
            return
        if self._quiescence is not None and not self._quiescence():
            # the consumer has not caught up, or a command (entry/exit/
            # protective) is still traveling the async chain — feeding the
            # next bar now would reorder its execution against later bars
            return
        bar = self._bars[self._i]
        self._i += 1
        self.msgbus.send(endpoint="DataEngine.process", msg=bar)
        # Bars alone never initialize bid/ask — they produce trade ticks only,
        # and the matching engine rejects market orders with 'no market' when
        # no quote exists between bars. In the live feed this is exactly what
        # the exchange would provide; here the bar's close IS the executable
        # market (the harness's fill model), so the quote is both sides at
        # close — honest, zero-spread, and identical to what the order sees
        # in production where the market trades at the last print.
        from nautilus_trader.model.data import QuoteTick

        quote = QuoteTick(
            instrument_id=bar.bar_type.instrument_id,
            bid_price=bar.close,
            ask_price=bar.close,
            bid_size=bar.volume,
            ask_size=bar.volume,
            ts_event=bar.ts_init,
            ts_init=bar.ts_init,
        )
        self.msgbus.send(endpoint="DataEngine.process", msg=quote)

    def on_stop(self):
        # an exhausted feed already cancelled its own timer — cancelling
        # again is a KeyError in the LiveClock, not a no-op
        if self._i < len(self._bars):
            self.clock.cancel_timer("replay-feed")
