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


def make_sim_instrument(symbol: str = "BTCUSDT"):
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
        instrument_id=InstrumentId(symbol=Symbol(f"{symbol}-PERP"), venue=Venue("SIM")),
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
    idx_ns = df.index.asi8  # UTC by the ingestion contract, already ns
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

    def __init__(self, initial_equity: float):
        self.fills: list[dict] = []
        self.order_meta: dict[str, dict] = {}
        self.positions: list[dict] = []
        self.realized_net = float(initial_equity)


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
            self._df = config.frame
            self._strategy = config.pure_strategy
            self._cfg: BTConfig = config.bt_config
            self._open_pos: dict | None = None

        def on_start(self):
            from nautilus_trader.model.data import BarType

            spec = self.config.bar_spec
            self.subscribe_bars(BarType.from_str(f"{self.instrument_id}-{spec}-LAST-EXTERNAL"))

        def on_bar(self, bar):
            self._k += 1
            k = self._k
            df = self._df
            cfg = self._cfg
            if k >= len(df):
                return

            sig_bar = k - 1
            sig = None
            if sig_bar >= 0:
                sig = self._strategy.signal(sig_bar, df.iloc[: sig_bar + 1])

            atr_abs = 0.0
            if sig is not None:
                row = df.iloc[sig_bar]
                atr_pct = row["atr_pct"]
                if not (isinstance(atr_pct, float) and math.isnan(atr_pct)) and atr_pct > 0:
                    atr_abs = float(atr_pct) * float(row["close"])

            # exits beat entries, as in the ported loop: flat signal first,
            # then timeout, never both in one bar
            if self._open_pos is not None:
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

            k = self._k
            close_k = float(self._df.iloc[k]["close"])
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
            bracket = self.order_factory.bracket(
                instrument_id=self.instrument_id,
                order_side=side,
                quantity=q,
                contingency_type=ContingencyType.OCO,
                sl_trigger_price=instrument.make_price(stop_price),
                tp_price=instrument.make_price(tp_price),
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
                "entry_order_id": str(bracket.orders[0].client_order_id),
                "child_order_ids": [str(o.client_order_id) for o in bracket.orders[1:]],
            }
            # role assignment: bracket orders are entry, stop, tp in the
            # factory's documented order — verified by order type at runtime
            for order in bracket.orders:
                otype = order.order_type.name
                role = "entry" if otype == "MARKET" else "stop" if otype == "STOP_MARKET" else "take_profit"
                self._state.order_meta[str(order.client_order_id)] = {**meta, "role": role}
            self.submit_order_list(bracket)
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
            # the resting protective orders must not survive the close
            for oid in pos["child_order_ids"]:
                cached = self.cache.order(self.client_order_id_of(oid))
                if cached is not None and cached.is_open:
                    self.cancel_order(cached)

        def client_order_id_of(self, oid_str: str):
            from nautilus_trader.model.identifiers import ClientOrderId

            return ClientOrderId(oid_str)

        # -- bookkeeping ----------------------------------------------------

        def on_order_filled(self, event):
            oid = str(event.client_order_id)
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
            if meta["role"] == "entry" and oid == pos["entry_order_id"]:
                pos["pending"] = False
                pos["entry_fill"] = fill
            elif meta["role"] in ("stop", "take_profit", "signal_exit", "timeout"):
                if pos.get("entry_fill") is not None and not pos.get("closed"):
                    pos["exit_fill"] = fill
                    pos["closed"] = True
                    self._settle(pos)
                    self._state.positions.append(pos)
                    self._open_pos = None

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
        frame: object
        pure_strategy: object
        bt_config: object

    strat = _strategy_class()(
        HarnessConfig(
            instrument_id=str(instrument.id),
            bar_spec=TIMEFRAME_BAR_SPEC[timeframe],
            harness_state=state,
            frame=df,
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
    idx_ns = list(df.index.asi8)

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
