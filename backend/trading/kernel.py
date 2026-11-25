"""Nautilus kernel adapter — backtests on the kernel, the economics of the
ported engine reconstructed on its fills.

Why the adapter exists (measured, not assumed — probes in
`docs/research/probes/probe_execution.py` / `probe2_brackets.py`, 2026-11-25):

1.  Bar-only data in nautilus 1.231.0 cannot fill an order at the next bar's
    OPEN. Synthetic OHLC updates for bar k all land at ts_init(k) — the close
    of the interval — and any order submitted from on_bar(k) settles against
    the book state at close(k). Aggressive limits already crossing the market
    fill immediately like market orders; resting ones fill at their own limit
    price, not the open. The upstream docs say it plainly: there is no native
    next-bar-open fill mode. The harness therefore runs on the model that IS
    executable live and is unambiguous on bars: the signal for bar k-1 is
    computed when bar k completes and the order fills at close(k). Every fill
    is strictly after every bar the strategy saw — the acceptance test
    asserts exactly that. The divergence from the ported engine's open(i)
    fills is documented in docs/research/kernel-diff-*.md.

2.  The ported engine's economics (slippage-adjusted fills, percentage fees,
    realized-only equity curve, risk-budget sizing) are validation semantics,
    not kernel semantics. The kernel venue is configured zero-fee and
    near-zero-margin so nothing in the kernel distorts them; this module
    reconstructs trades, pnl and the equity curve from kernel fills following
    `backtest/engine.py`'s arithmetic — one economics definition, two
    engines, and the reference diff quantifies what changed.

3.  pandas 3 copy-on-write makes frame.values read-only, which kills the
    BarDataWrangler memoryview path. Bars are constructed object by object;
    the documented timestamp convention is kept: ts_event at the bar open,
    ts_init at the close, so no bar is visible before it formed.

Anti-lookahead is structural, exactly as in `trading/harness.py`: the frame
the strategy receives is truncated at the bar it is asked about, so indexing
past it raises inside the strategy's own guard. The kernel additionally
guarantees only closed bars reach on_bar at all.
"""

from __future__ import annotations

import math
from decimal import Decimal

import pandas as pd

from trading.backtest.engine import BTConfig, BTResult, BarsPerYear, _metrics
from trading.harness import wrap as harness_wrap

# pandas 3 keeps datetime64 in its creation unit (µs for date_range) instead
# of coercing everything to ns — every timestamp this module hands the kernel
# is nanoseconds, so conversions multiply, never assume.
_UNIT_TO_NS = {"ns": 1, "us": 1_000, "ms": 1_000_000, "s": 1_000_000_000}

TIMEFRAME_NS = {
    "1m": 60_000_000_000,
    "5m": 300_000_000_000,
    "15m": 900_000_000_000,
    "1h": 3_600_000_000_000,
    "4h": 14_400_000_000_000,
    "1d": 86_400_000_000_000,
}

TIMEFRAME_BAR_SPEC = {
    "1m": "1-MINUTE",
    "5m": "5-MINUTE",
    "15m": "15-MINUTE",
    "1h": "1-HOUR",
    "4h": "4-HOUR",
    "1d": "1-DAY",
}


def make_sim_instrument(symbol: str = "BTCUSDT", venue: str = "SIM"):
    """Zero-fee perpetual on the SIM venue, margins near zero.

    Fees and slippage live in the reconstruction — a kernel that also charged
    them would double-count. Near-zero margin means the validation sizing
    (risk budget / stop distance) is never silently rejected for leverage,
    exactly as the ported engine assumes; leverage realism is a mandate
    property, not a validation parameter (design §2).
    """
    from nautilus_trader.model.currencies import BTC, USDT
    from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
    from nautilus_trader.model.instruments import CryptoPerpetual
    from nautilus_trader.model.objects import Money, Price, Quantity

    return CryptoPerpetual(
        instrument_id=InstrumentId(symbol=Symbol(f"{symbol}-PERP"), venue=Venue(venue)),
        raw_symbol=Symbol(symbol),
        base_currency=BTC,
        quote_currency=USDT,
        settlement_currency=USDT,
        is_inverse=False,
        price_precision=1,
        price_increment=Price.from_str("0.1"),
        size_precision=3,
        size_increment=Quantity.from_str("0.001"),
        max_quantity=Quantity.from_str("10000.000"),
        min_quantity=Quantity.from_str("0.001"),
        max_notional=None,
        min_notional=Money(1.00, USDT),
        max_price=Price.from_str("10000000.0"),
        min_price=Price.from_str("1.0"),
        margin_init=Decimal("0.0001"),
        margin_maint=Decimal("0.00005"),
        maker_fee=Decimal(0),
        taker_fee=Decimal(0),
        ts_event=0,
        ts_init=0,
    )


def build_bars(df: pd.DataFrame, instrument, timeframe: str) -> list:
    """One Bar per frame row, direct construction (pandas 3 kills the wrangler,
    see module docstring). ts_event at the open, ts_init at the close."""
    import numpy as np
    from nautilus_trader.model.data import Bar, BarType
    from nautilus_trader.model.objects import Price, Quantity

    interval_ns = TIMEFRAME_NS[timeframe]
    spec = TIMEFRAME_BAR_SPEC[timeframe]
    bar_type = BarType.from_str(f"{instrument.id}-{spec}-LAST-EXTERNAL")
    idx_ns = df.index.asi8 * _UNIT_TO_NS[df.index.unit]  # UTC by the ingestion contract; pandas 3 resolves datetime64 in µs — asi8 is NOT nanoseconds there
    opens = df["open"].to_numpy(dtype=np.float64, copy=True)
    highs = df["high"].to_numpy(dtype=np.float64, copy=True)
    lows = df["low"].to_numpy(dtype=np.float64, copy=True)
    closes = df["close"].to_numpy(dtype=np.float64, copy=True)
    volumes = (
        df["volume"].to_numpy(dtype=np.float64, copy=True)
        if "volume" in df
        else np.ones(len(df))
    )
    pp = instrument.price_precision
    sp = instrument.size_precision
    bars = []
    for j in range(len(df)):
        ts_event = int(idx_ns[j])
        bars.append(
            Bar(
                bar_type=bar_type,
                open=Price(float(opens[j]), pp),
                high=Price(float(highs[j]), pp),
                low=Price(float(lows[j]), pp),
                close=Price(float(closes[j]), pp),
                volume=Quantity(float(max(volumes[j], 1e-9)), sp),
                ts_event=ts_event,
                ts_init=ts_event + interval_ns,
            )
        )
    return bars


class HarnessRunState:
    """Everything the run records for reconstruction. One instance per run —
    two engines never share it. `realized_net` is the validation's own
    accounting: it starts at initial equity and moves by the reconstructed
    net pnl of each close, so sizing inside the kernel run uses exactly the
    equity the ported engine would have used at that moment."""

    def __init__(self, initial_equity: float, on_position_event=None):
        self.fills: list[dict] = []
        self.order_meta: dict[str, dict] = {}
        self.positions: list[dict] = []
        self.realized_net = float(initial_equity)
        # desk provenance hook: fn(event, pos_dict) called synchronously when
        # a position's entry fills ("entry") and when it settles ("close").
        # Backtests pass nothing — the reconstruction reads state wholesale.
        self.on_position_event = on_position_event
        # feed-health hook: fn() called once per bar close, before any
        # evaluation. The desk uses it for wall-clock staleness detection;
        # backtests pass nothing — every bar arrives by construction.
        self.on_bar_processed = None
        # command-execution evidence for replay pacing: every order the
        # harness submits has its client id in order_meta before submission;
        # the event hooks (fill, accept, reject, cancel, expire) move each id
        # to adjudicated. Cancels target orders whose ids are ALREADY
        # adjudicated (resting protective brackets), so they are tracked
        # separately in pending_cancel_ids from submission until the
        # canceled/rejected event lands — otherwise the cancel traveling the
        # async chain is invisible to the gate and the resting order can
        # still fill intrabar while its cancel is in flight.
        self.adjudicated_order_ids: set[str] = set()
        self.pending_cancel_ids: set[str] = set()

    def order_chain_drained(self) -> bool:
        """Every submitted order has reached a terminal-ish state — fill,
        acceptance, rejection or cancel — and no cancel command is still
        traveling the async chain."""
        return not self.pending_cancel_ids and all(oid in self.adjudicated_order_ids for oid in self.order_meta)


class StaticFrame:
    """Frame source for backtests — behaves incrementally, exactly like the
    desk's IncrementalFrame: each closed bar uncovers one more row of the
    precomputed feature frame, never the whole thing. A backtest is therefore
    a fast-forward of the live tape, not a different data shape, and the
    strategy's evaluation logic is identical in both contexts by construction
    (design: same wrapper, both contexts).

    Rows arrive keyed by the bar's ts_event (bar-open stamp, the harness
    convention from build_bars) so position i of the visible frame is global
    bar i — the contract the harness slicing relies on.
    """

    def __init__(self, df: pd.DataFrame):
        self._full = df
        self._open_ns = list(df.index.asi8 * _UNIT_TO_NS[df.index.unit])
        self._n = 0

    def on_bar_close(self, bar) -> None:
        if self._n < len(self._full) and int(bar.ts_event) == self._open_ns[self._n]:
            self._n += 1
        # a bar that doesn't match the next expected open is not ours to
        # reveal — silently skipping is correct for the backtest's single,
        # ordered stream and never masks a live-feed gap, which is the
        # desk's concern, not this class's

    def frame(self) -> pd.DataFrame:
        return self._full.iloc[: self._n]

def _make_strategy_class():
    """The nautilus Strategy subclass — built once per process because the
    kernel imports cost 1-2 s, never per bar."""
    from nautilus_trader.trading.strategy import Strategy

    class KernelHarnessStrategy(Strategy):
        """Evaluates the wrapped pure strategy one bar behind the just-closed
        bar and executes the reconstruction's model:

        - on_bar for bar k evaluates signal(k-1) on the frame truncated at
          k-1 — structural anti-lookahead, the same guarantee the pandas
          harness gives the ported engine
        - entries and flat/timeout exits are market orders filling at
          close(k) — the kernel's only unambiguous bar fill, strictly after
          every bar the strategy saw
        - protective stop/tp are an OCO bracket resting from the entry's
          submission, filled intrabar by the kernel at exact stop/tp prices,
          or at the open when a bar gaps through (measured in probe2)
        - the timeout mirrors the ported engine's counting: a position
          signaled at bar k is force-closed at close of bar k + max_bars
        - sizing uses the reconstruction's net realized equity, tracked
          inside the run, not kernel cash — the kernel is zero-fee, the
          validation's equity is not
        """

        def __init__(self, config):
            super().__init__(config)
            from nautilus_trader.model.identifiers import InstrumentId

            self.instrument_id = InstrumentId.from_str(config.instrument_id)
            self._k = -1
            self._state: HarnessRunState = config.harness_state
            self._frame_source = config.frame_source
            self._strategy = config.pure_strategy
            self._cfg: BTConfig = config.bt_config
            self._open_pos: dict | None = None
            self._last_close = 0.0

        def on_start(self):
            from nautilus_trader.model.data import BarType

            spec = self.config.bar_spec
            self.subscribe_bars(BarType.from_str(f"{self.instrument_id}-{spec}-LAST-EXTERNAL"))

        def on_bar(self, bar):
            # _k counts COMPLETED bars, never started ones: the replay gate
            # reads _k to decide emission, and incrementing at the top here
            # opens the gate while the signal evaluation below is still
            # running — the next bar's quote then reaches the book before the
            # orders this bar submits clear the async command chain, filling
            # them one bar late (measured 2026-11-25 in the live-node parity
            # runs: entry fills at close(k+1) instead of close(k)).
            try:
                self._on_bar(bar)
            finally:
                self._k += 1

        def _on_bar(self, bar):
            # a rearm left unsubmitted at boot goes out now: the market exists
            # (a bar closed), so the order is no longer rejected on sight
            pending_rearm = getattr(self, "_pending_rearm", None)
            if pending_rearm is not None:
                from nautilus_trader.model.enums import TimeInForce

                instrument = self.cache.instrument(self.instrument_id)
                order = self.order_factory.market(
                    self.instrument_id,
                    pending_rearm["order_side"],
                    instrument.make_qty(pending_rearm["qty"]),
                    time_in_force=TimeInForce.GTC,
                )
                self._state.order_meta[str(order.client_order_id)] = pending_rearm["meta"]
                pending_rearm["pos"]["entry_order_id"] = str(order.client_order_id)
                self._pending_rearm = None
                self.submit_order(order)
            # the bar that closed is pushed into the frame source BEFORE any
            # evaluation — ordering is structural, never subscription luck
            self._frame_source.on_bar_close(bar)
            if self._state.on_bar_processed is not None:
                self._state.on_bar_processed()
            # close of the just-closed bar, kept for bracket anchoring — in
            # the backtest this equals the frame row's close because bars
            # derive from the frame; in paper it is the live close. One
            # definition, both contexts.
            self._last_close = float(bar.close)
            df = self._frame_source.frame()
            cfg = self._cfg
            # the universal bar index: the just-closed bar's POSITION in the
            # visible frame. Identical arithmetic in both contexts — in the
            # backtest the frame grows one row per bar exactly like the live
            # tape, so k is the same number here and in production.
            k = len(df) - 1
            if k < 1:
                return  # nothing precedes the first bar; no signal can exist

            sig_bar = k - 1
            sig = self._strategy.signal(sig_bar, df.iloc[: sig_bar + 1])

            atr_abs = 0.0
            if sig is not None:
                row = df.iloc[sig_bar]
                atr_pct = row["atr_pct"]
                if not (isinstance(atr_pct, float) and math.isnan(atr_pct)) and atr_pct > 0:
                    atr_abs = float(atr_pct) * float(row["close"])

            # exits beat entries, as in the ported loop: flat signal first,
            # then timeout, never both in one bar
            if self._open_pos is not None and not self._open_pos.get("pending"):
                if sig is not None and sig.side == "flat":
                    self._close_market("signal_exit")
                elif (
                    cfg.max_bars_in_trade
                    and k - self._open_pos["signal_bar"] >= cfg.max_bars_in_trade
                ):
                    self._close_market("timeout")

            if (
                sig is not None
                and sig.side in ("long", "short")
                and self._open_pos is None
                and sig.confidence >= cfg.confidence_min
                and atr_abs > 0
            ):
                self._enter(sig.side, sig.confidence, sig.stop_atr, sig.tp_rr, sig_bar, atr_abs)

        def rearm(
            self,
            *,
            side: str,
            qty: float,
            stop_loss: float,
            take_profit: float,
            confidence: float,
            signal_time,
            ledger_row_id: int,
            entry_price: float = 0.0,
        ) -> None:
            """Re-arm an open position the DB says survived a restart. The
            kernel starts flat, so this is a market re-entry tagged 'rearm' —
            excluded from trade economics, which keep the ORIGINAL entry —
            followed by the original protective levels as a fresh OCO pair.

            signal_bar is re-derived from the frame: the bar whose timestamp
            is the signal bar's own. If the seeded history doesn't reach back
            that far, the position times out at the first opportunity — an
            honestly unknowable age, never a silently reset clock.
            """
            from nautilus_trader.model.enums import OrderSide, TimeInForce

            instrument = self.cache.instrument(self.instrument_id)
            order_side = OrderSide.BUY if side == "long" else OrderSide.SELL
            meta = {
                "side": side,
                "signal_bar": -1,  # resolved when the rearm fills
                "qty": qty,
                "confidence": confidence,
                "role": "rearm",
            }
            pos = {
                **{k: meta[k] for k in ("side", "qty", "confidence")},
                "signal_bar": -1,
                "signal_time": signal_time,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "ledger_row_id": ledger_row_id,
                "pending": True,
                "rearmed": True,
                "child_order_ids": [],
                # economics anchor: the ORIGINAL entry, not the rearm print —
                # written when the rearm fills, from the DB row the worker kept
                "original_entry_price": entry_price,
            }
            # the rearm order is NOT submitted here: rearm runs at boot,
            # before the first quote exists, and every venue rejects a market
            # order into a marketless book. The order goes out on the first
            # bar close, when the market measurably exists — same entry class
            # as every other market order this harness ever submits.
            self._pending_rearm = {
                "order_side": order_side,
                "qty": qty,
                "meta": meta,
                "pos": pos,
            }
            self._open_pos = pos

        # -- execution ------------------------------------------------------

        def _enter(
            self,
            side_str: str,
            confidence: float,
            stop_atr: float,
            tp_rr: float,
            sig_bar: int,
            atr_abs: float,
        ):
            from nautilus_trader.model.enums import ContingencyType, OrderSide, TimeInForce

            close_k = self._last_close
            stop_dist = stop_atr * atr_abs
            risk_amount = self._state.realized_net * self._cfg.risk_per_trade
            qty_raw = risk_amount / stop_dist
            instrument = self.cache.instrument(self.instrument_id)
            qty = float(instrument.make_qty(qty_raw).as_decimal())
            if qty <= 0:
                return

            if side_str == "long":
                stop_price = close_k - stop_dist
                tp_price = close_k + stop_dist * tp_rr
                side = OrderSide.BUY
            else:
                stop_price = close_k + stop_dist
                tp_price = close_k - stop_dist * tp_rr
                side = OrderSide.SELL

            q = instrument.make_qty(qty)
            # The entry goes alone; the stop/take-profit pair is submitted in
            # on_order_filled once the venue position exists. Three reasons,
            # all measured:
            #  1. order_factory.bracket hardcodes reduce_only=True on the
            #     children — on a live execution path the children process
            #     BEFORE the entry fill is applied to the cache, see no
            #     position, and reject (the backtest's synchronous cascade
            #     hides this entirely).
            #  2. Submitting protective orders after the entry fill is what
            #     the production venue flow does anyway — the backtest/live
            #     parity this file exists for demands one behavior, and the
            #     live one is the honest reference.
            #  3. The OCO sibling discipline is manual in
            #     _cancel_sibling_protective either way.
            entry_order = self.order_factory.market(
                self.instrument_id,
                side,
                q,
                time_in_force=TimeInForce.GTC,
            )
            meta = {
                "side": side_str,
                "signal_bar": sig_bar,
                "qty": qty,
                "confidence": confidence,
            }
            pos = {
                **meta,
                "pending": True,
                # the signal bar's own timestamp — restart bookkeeping re-
                # derives bar indices from it across processes, never from
                # frame positions, which are meaningless once the process dies
                "signal_time": self._frame_source.frame().index[sig_bar].to_pydatetime()
                if len(self._frame_source.frame()) > sig_bar >= 0
                else None,
                "stop_loss": stop_price,
                "take_profit": tp_price,
                "entry_order_id": str(entry_order.client_order_id),
                "child_order_ids": [],
            }
            self._state.order_meta[str(entry_order.client_order_id)] = {**meta, "role": "entry"}
            self.submit_order(entry_order)
            self._open_pos = pos

        def _close_market(self, reason: str):
            from nautilus_trader.model.enums import OrderSide, TimeInForce

            pos = self._open_pos
            if pos is None:
                return
            instrument = self.cache.instrument(self.instrument_id)
            qty = instrument.make_qty(pos["qty"])
            side = OrderSide.SELL if pos["side"] == "long" else OrderSide.BUY
            order = self.order_factory.market(
                self.instrument_id,
                side,
                qty,
                time_in_force=TimeInForce.GTC,
                reduce_only=True,
            )
            self._state.order_meta[str(order.client_order_id)] = {
                "side": pos["side"],
                "signal_bar": pos["signal_bar"],
                "qty": pos["qty"],
                "confidence": pos["confidence"],
                "role": reason,
            }
            self.submit_order(order)
            pos["exit_order_id"] = str(order.client_order_id)
            # the resting protective orders must not survive the close —
            # tracked cancels, see _cancel_resting
            for oid in pos["child_order_ids"]:
                cached = self.cache.order(self.client_order_id_of(oid))
                if cached is not None and cached.is_open:
                    self._cancel_resting(cached)

        def _cancel_resting(self, order) -> None:
            """Cancel a resting order with quiescence evidence: the id is
            already adjudicated (it was accepted), so order_meta alone can
            never see this command — track it in pending_cancel_ids until the
            canceled/rejected event lands. A tape that ignores in-flight
            cancels feeds the next bar while the order is still live, and a
            protective leg can then fill intrabar against a position the
            harness already believes closed. A cancel already traveling is
            not re-sent: PENDING_CANCEL reads as is_open in the kernel, so
            the close path and the sibling-cancel path would otherwise
            double-cancel every bracket exit (measured 2026-11-25)."""
            oid = str(order.client_order_id)
            if oid in self._state.pending_cancel_ids:
                return
            self._state.pending_cancel_ids.add(oid)
            self.cancel_order(order)

        def client_order_id_of(self, oid_str: str):
            from nautilus_trader.model.identifiers import ClientOrderId

            return ClientOrderId(oid_str)

        # -- bookkeeping ----------------------------------------------------

        def on_order_filled(self, event):
            oid = str(event.client_order_id)
            self._state.adjudicated_order_ids.add(oid)
            # a filled order is terminal — any cancel still traveling the
            # chain is dead on arrival whether or not the rejection is seen
            self._state.pending_cancel_ids.discard(oid)
            meta = self._state.order_meta.get(oid)
            if meta is None:
                return
            fill = {
                "order_id": oid,
                "role": meta["role"],
                "price": float(event.last_px.as_decimal()),
                "qty": float(event.last_qty.as_decimal()),
                "ts_event": int(event.ts_event),
                "side": meta["side"],
                "signal_bar": meta["signal_bar"],
                "confidence": meta.get("confidence", 0.0),
            }
            self._state.fills.append(fill)
            pos = self._open_pos
            if pos is None:
                return
            if meta["role"] == "rearm" and oid == pos.get("entry_order_id"):
                self._on_rearm_filled(pos, fill)
            elif meta["role"] == "entry" and oid == pos["entry_order_id"]:
                pos["pending"] = False
                pos["entry_fill"] = fill
                self._place_protective(pos)
                if self._state.on_position_event is not None:
                    self._state.on_position_event("entry", pos)
            elif meta["role"] in ("stop", "take_profit", "signal_exit", "timeout", "restart_unrecoverable"):
                if pos.get("entry_fill") is not None and not pos.get("closed"):
                    pos["exit_fill"] = fill
                    pos["closed"] = True
                    self._settle(pos)
                    self._state.positions.append(pos)
                    if self._state.on_position_event is not None:
                        self._state.on_position_event("close", pos)
                    self._cancel_sibling_protective(pos, meta["role"])
                    self._open_pos = None

        def _on_rearm_filled(self, pos: dict, fill: dict) -> None:
            """Rearm entry filled — reconstruct the position bookkeeping and
            place the original protective levels. The economics anchor to the
            original entry (the rearm print never enters pnl); the rearm fill
            itself is kept as the kernel fact so the audit sees the restart
            cost."""
            df = self._frame_source.frame()
            signal_bar = -1
            st = pos.get("signal_time")
            if st is not None and len(df):
                target = pd.Timestamp(st)
                if target.tzinfo is None:
                    target = target.tz_localize("UTC")
                matches = [i for i, ts in enumerate(df.index) if ts == target]
                if matches:
                    signal_bar = matches[0]
            pos["signal_bar"] = signal_bar
            # entry_fill carries the ORIGINAL economics; the rearm print is
            # audit-only in pos["rearm_fill"]
            pos["entry_fill"] = {
                **fill,
                "price": pos.get("original_entry_price") or fill["price"],
            }
            pos["rearm_fill"] = fill
            pos["pending"] = False
            if signal_bar < 0:
                # the seeded history doesn't reach the signal bar — the
                # position's age is unknowable. Honest fallback: close at
                # market right away, never a silently reset clock.
                self._close_market("restart_unrecoverable")
                return
            self._place_protective(pos)

        def _place_protective(self, pos: dict) -> None:
            """Standalone stop/take-profit pair for a rearmed position —
            reduce-only GTC orders, sibling-cancelled manually on fill (the
            verified kernel behaviour for bracket children applies here too)."""
            from nautilus_trader.model.enums import OrderSide, TimeInForce

            instrument = self.cache.instrument(self.instrument_id)
            qty = instrument.make_qty(pos["qty"])
            close_side = OrderSide.SELL if pos["side"] == "long" else OrderSide.BUY
            meta_base = {
                "side": pos["side"],
                "signal_bar": pos["signal_bar"],
                "qty": pos["qty"],
                "confidence": pos["confidence"],
            }
            child_ids = []
            for role, price, is_stop in (
                ("stop", pos["stop_loss"], True),
                ("take_profit", pos["take_profit"], False),
            ):
                if is_stop:
                    # TriggerType.LAST_PRICE, never the DEFAULT bid/ask: the
                    # harness's stop is defined against what the market
                    # TRADES, and the bar auction produces trade ticks in
                    # every context — backtest, replay, live. A bid/ask
                    # trigger would fire on the replay's close-quote only,
                    # making the stop blind to intra-bar lows that the
                    # backtest fill model does see.
                    from nautilus_trader.model.enums import TriggerType

                    order = self.order_factory.stop_market(
                        self.instrument_id,
                        close_side,
                        qty,
                        instrument.make_price(price),
                        trigger_type=TriggerType.LAST_PRICE,
                        time_in_force=TimeInForce.GTC,
                        reduce_only=True,
                    )
                else:
                    order = self.order_factory.limit(
                        self.instrument_id,
                        close_side,
                        qty,
                        instrument.make_price(price),
                        time_in_force=TimeInForce.GTC,
                        reduce_only=True,
                    )
                self._state.order_meta[str(order.client_order_id)] = {**meta_base, "role": role}
                self.submit_order(order)
                child_ids.append(str(order.client_order_id))
            pos["child_order_ids"] = child_ids

        def _cancel_sibling_protective(self, pos: dict, filled_role: str) -> None:
            """After a protective leg fills, its sibling must not survive —
            kernel brackets do this via OCO; standalone rearm pairs do it
            here. Same discipline as _close_market's cancel path."""
            if filled_role not in ("stop", "take_profit"):
                return
            for oid in pos.get("child_order_ids", []):
                cached = self.cache.order(self.client_order_id_of(oid))
                if cached is not None and cached.is_open:
                    self._cancel_resting(cached)

        def _settle(self, pos: dict):
            """Net realized pnl in the ported arithmetic, credited to the
            run's validation equity the moment the close fills — later sizing
            decisions in the same run see exactly what the ported engine
            would have seen."""
            cfg = self._cfg
            fee = cfg.fee_pct / 100
            slip = cfg.slippage_bps / 10_000
            side = pos["side"]
            entry_raw = pos["entry_fill"]["price"]
            exit_raw = pos["exit_fill"]["price"]
            qty = pos["qty"]
            entry_px = entry_raw * (1 + slip) if side == "long" else entry_raw * (1 - slip)
            exit_px = exit_raw * (1 - slip) if side == "long" else exit_raw * (1 + slip)
            gross = (exit_px - entry_px) * qty * (1 if side == "long" else -1)
            fees = (entry_px + exit_px) * qty * fee
            pnl = gross - fees
            self._state.realized_net += pnl
            pos["pnl"] = pnl
            pos["fees"] = fees
            pos["entry_price_net"] = entry_px
            pos["exit_price_net"] = exit_px

        def on_order_accepted(self, event):
            # quiescence evidence for replay pacing: an accepted order is
            # adjudicated — the venue has it resting or is done with it
            self._state.adjudicated_order_ids.add(str(event.client_order_id))

        def on_order_rejected(self, event):
            self._state.adjudicated_order_ids.add(str(event.client_order_id))

        def on_order_canceled(self, event):
            oid = str(event.client_order_id)
            self._state.adjudicated_order_ids.add(oid)
            self._state.pending_cancel_ids.discard(oid)

        def on_order_cancel_rejected(self, event):
            # the venue refused the cancel (the order filled or expired
            # first) — the cancel is dead either way, and the terminal event
            # that caused the refusal carries the adjudication
            self._state.pending_cancel_ids.discard(str(event.client_order_id))

        def on_order_expired(self, event):
            self._state.adjudicated_order_ids.add(str(event.client_order_id))

        def on_stop(self):
            # a position still open when the data ends never becomes a trade —
            # same as the ported engine, whose open position simply never
            # closes. Recorded as-is so the audit sees it existed.
            if self._open_pos is not None and self._open_pos.get("entry_fill") is not None:
                self._open_pos["closed"] = False
                self._state.positions.append(self._open_pos)
                self._open_pos = None

    return KernelHarnessStrategy


_STRATEGY_CLASS = None


def _strategy_class():
    global _STRATEGY_CLASS
    if _STRATEGY_CLASS is None:
        _STRATEGY_CLASS = _make_strategy_class()
    return _STRATEGY_CLASS


def run_kernel_backtest(
    df: pd.DataFrame,
    strategy,
    cfg: BTConfig | None = None,
    timeframe: str = "1h",
    symbol: str = "BTCUSDT",
) -> BTResult:
    """Backtest on the nautilus kernel with the ported engine's economics
    reconstructed from its fills. Same contract as `run_backtest` — df is the
    feature frame, BTResult carries reconstructed trades, the realized-only
    equity curve and the same metrics — except the strategy is passed bare:
    harness wrapping happens here, once, so the truncation logic exists in
    exactly one place.
    """
    cfg = cfg or BTConfig()

    from nautilus_trader.backtest.config import BacktestEngineConfig
    from nautilus_trader.backtest.engine import BacktestEngine
    from nautilus_trader.config import LoggingConfig, StrategyConfig
    from nautilus_trader.model.enums import AccountType, OmsType
    from nautilus_trader.model.identifiers import TraderId, Venue
    from nautilus_trader.model.objects import Money

    instrument = make_sim_instrument(symbol)
    state = HarnessRunState(cfg.initial_equity)

    config = BacktestEngineConfig(
        trader_id=TraderId("KERNEL-BT-001"),
        logging=LoggingConfig(log_level="ERROR"),
    )
    engine = BacktestEngine(config)
    engine.add_venue(
        venue=Venue("SIM"),
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        starting_balances=[Money.from_str(f"{cfg.initial_equity} USDT")],
        bar_execution=True,
    )
    engine.add_instrument(instrument)
    engine.add_data(build_bars(df, instrument, timeframe))

    class HarnessConfig(StrategyConfig, frozen=True):
        instrument_id: str
        bar_spec: str
        harness_state: object
        frame_source: object
        pure_strategy: object
        bt_config: object

    strat = _strategy_class()(
        HarnessConfig(
            instrument_id=str(instrument.id),
            bar_spec=TIMEFRAME_BAR_SPEC[timeframe],
            harness_state=state,
            frame_source=StaticFrame(df),
            pure_strategy=harness_wrap(strategy),
            bt_config=cfg,
        )
    )
    engine.add_strategy(strat)
    engine.run()

    trades, equity = _reconstruct(df, state, cfg, timeframe)
    metrics = _metrics(trades, equity, BarsPerYear.get(timeframe, 8_760))
    engine.dispose()
    return BTResult(trades, equity, metrics)


def _reconstruct(df: pd.DataFrame, state: HarnessRunState, cfg: BTConfig, timeframe: str):
    """Rebuild the BTResult shape from the run's positions.

    Prices, fees and pnl are already net in each position (`_settle` applied
    the ported arithmetic at fill time, because sizing needed it then); what
    remains is the trade records, the realized-only equity curve with a step
    at each exit bar, and the audit extras — signal/entry/exit bar indices,
    which are the fill-timing evidence the acceptance test reads.
    """
    interval_ns = TIMEFRAME_NS[timeframe]
    idx_ns = list(df.index.asi8 * _UNIT_TO_NS[df.index.unit])

    def bar_index_of(ts_event_ns: int) -> int:
        # fills are stamped at the close of the bar that filled them; the
        # bar's index position is keyed by its open stamp
        open_ns = ts_event_ns - interval_ns
        try:
            return idx_ns.index(open_ns)
        except ValueError:
            return -1

    trades: list[dict] = []
    steps: dict[int, float] = {}
    for pos in state.positions:
        if not pos.get("closed"):
            continue  # never exited within the data — no trade exists
        entry_i = bar_index_of(pos["entry_fill"]["ts_event"])
        exit_i = bar_index_of(pos["exit_fill"]["ts_event"])
        entry_ts = df.index[entry_i] if entry_i >= 0 else df.index[0]
        exit_ts = df.index[exit_i] if exit_i >= 0 else df.index[-1]
        trades.append(
            {
                "side": pos["side"],
                "qty": pos["qty"],
                "entry_price": pos["entry_price_net"],
                "exit_price": pos["exit_price_net"],
                "entry_time": entry_ts,
                "exit_time": exit_ts,
                "pnl": pos["pnl"],
                "fees": pos["fees"],
                "confidence": pos["confidence"],
                "bars_held": exit_i - entry_i if exit_i >= 0 and entry_i >= 0 else 0,
                "reason": pos["exit_fill"]["role"],
                # fill-timing evidence for the acceptance test and the audit:
                # the kernel facts, not the adjusted economics
                "signal_bar": pos["signal_bar"],
                "entry_bar": entry_i,
                "exit_bar": exit_i,
                "entry_fill_raw": pos["entry_fill"]["price"],
                "exit_fill_raw": pos["exit_fill"]["price"],
            }
        )
        if exit_i >= 0:
            steps[exit_i] = steps.get(exit_i, 0.0) + pos["pnl"]

    eq = float(cfg.initial_equity)
    curve = []
    for i in range(len(df)):
        eq += steps.get(i, 0.0)
        curve.append(eq)
    return trades, pd.Series(curve, index=df.index, name="equity")
