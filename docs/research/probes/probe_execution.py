"""Probe: exact fill mechanics of nautilus 1.231.0 bar execution on a
controlled price series — the facts the kernel adapter is designed against.

Run from the backend venv:
    cd backend && uv run python ../.spikes/nautilus/probe_execution.py

Controlled series, 1h bars, BTCUSDT-style prices. Every bar is hand-built so
each fill price answers exactly one question:

P1  market order submitted in on_bar(i) — fills at close(i) or open(i+1)?
P2  aggressive LIMIT (price far beyond market) — fills at open(i+1) at the
    open price, or elsewhere?
P3  resting STOP_MARKET — exact stop fill intrabar; gap-through fill at open
P4  resting LIMIT take-profit — exact limit fill intrabar
P5  closing MARKET order (the timeout exit) — fills at close(i)?
P6  zero-fee instrument — cash accounting exact to the tick
P7  fill timestamps vs bar timestamps
"""

from decimal import Decimal

import pandas as pd

from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.currencies import BTC, USDT
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import AccountType, OmsType, OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId, Symbol, TraderId, Venue
from nautilus_trader.model.instruments import CryptoPerpetual
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.persistence.wranglers import BarDataWrangler
from nautilus_trader.trading.strategy import Strategy, StrategyConfig

VENUE = Venue("SIM")
SYMBOL = "BTCUSDT-PERP"


def make_instrument() -> CryptoPerpetual:
    """Zero-fee BTCUSDT perp on SIM: kernel accounting is then gross, and every
    cost lives in the adapter's reconstruction where the ported model is defined."""
    return CryptoPerpetual(
        instrument_id=InstrumentId(symbol=Symbol(SYMBOL), venue=VENUE),
        raw_symbol=Symbol("BTCUSDT"),
        base_currency=BTC,
        quote_currency=USDT,
        settlement_currency=USDT,
        is_inverse=False,
        price_precision=1,
        price_increment=Price.from_str("0.1"),
        size_precision=3,
        size_increment=Quantity.from_str("0.001"),
        max_quantity=Quantity.from_str("1000.000"),
        min_quantity=Quantity.from_str("0.001"),
        max_notional=None,
        min_notional=Money(1.00, USDT),
        max_price=Price.from_str("1000000.0"),
        min_price=Price.from_str("100.0"),
        margin_init=Decimal("0.0001"),  # validation sizing knows no leverage cap
        margin_maint=Decimal("0.00005"),
        maker_fee=Decimal("0"),
        taker_fee=Decimal("0"),
        ts_event=0,
        ts_init=0,
    )


# ---- controlled series -------------------------------------------------
# bar:   0       1       2       3       4       5       6       7
# designed events:
#  on_bar(1): strategy submits its entry orders
#  bar 2: where do they fill?
#  bar 3: high 101000 touches TP limit at 100900?; low dips toward stop
#  bar 4: gap-down open through stop
#  etc. Each probe scenario runs in its own engine instance.

ROWS = [
    #  open      high      low       close     — one question per bar
    (100000.0, 100100.0, 99900.0, 100000.0),  # 0 warmup
    (100000.0, 100400.0, 99900.0, 100300.0),  # 1 orders submitted in on_bar(1)
    (100600.0, 100700.0, 100500.0, 100650.0),  # 2 entry fills here? open=100600
    (100650.0, 101200.0, 100550.0, 101000.0),  # 3 high touches TP(100900)/low toward stop
    (98000.0, 98100.0, 97500.0, 97800.0),  # 4 gap-through open for stops at 99500
    (97800.0, 98000.0, 97600.0, 97900.0),  # 5
    (97900.0, 98050.0, 97750.0, 98000.0),  # 6
    (98000.0, 98100.0, 97900.0, 98050.0),  # 7
]


def make_bars(instrument, rows=ROWS):
    """Build Bar objects directly — the BarDataWrangler path dies on pandas 3:
    copy-on-write makes frame.values read-only and Cython's typed memoryview
    refuses the buffer. Direct construction is also the documented custom-data
    path in upstream bar-execution.md: ts_event at the bar open, ts_init at the
    close so no bar is visible before it formed."""
    import numpy as np

    from nautilus_trader.model.data import Bar

    idx = pd.date_range("2025-01-01", periods=len(rows), freq="1h", tz="UTC")
    interval_ns = 3_600_000_000_000
    bar_type = BarType.from_str(f"{instrument.id}-1-HOUR-LAST-EXTERNAL")
    bars = []
    for ts, (o, h, lo, c) in zip(idx, rows):
        ts_event = int(ts.timestamp() * 1e9)
        bars.append(
            Bar(
                bar_type=bar_type,
                open=Price(o, instrument.price_precision),
                high=Price(h, instrument.price_precision),
                low=Price(lo, instrument.price_precision),
                close=Price(c, instrument.price_precision),
                volume=Quantity(100.0, instrument.size_precision),
                ts_event=ts_event,
                ts_init=ts_event + interval_ns,
            )
        )
    return bars, bar_type


class ProbeStrategy(Strategy):
    """Submits exactly what each probe needs, records what on_bar sees."""

    def __init__(self, config):
        super().__init__(config)
        self.scenario = config.scenario
        self.bar_count = 0
        self.instrument_id = InstrumentId.from_str(config.instrument_id)

    def on_start(self):
        self.subscribe_bars(BarType.from_str(f"{self.instrument_id}-1-HOUR-LAST-EXTERNAL"))

    def on_bar(self, bar):
        self.bar_count += 1
        i = self.bar_count - 1
        qty = Quantity.from_str("0.010")
        if i == 1:
            if self.scenario == "market_entry":
                order = self.order_factory.market(
                    self.instrument_id, OrderSide.BUY, qty, time_in_force=TimeInForce.GTC
                )
                self.submit_order(order)
            elif self.scenario == "aggressive_limit_entry":
                order = self.order_factory.limit(
                    self.instrument_id, OrderSide.BUY, qty,
                    Price.from_str("130000.0"), time_in_force=TimeInForce.GTC,
                )
                self.submit_order(order)
            elif self.scenario == "bracket":
                entry = self.order_factory.limit(
                    self.instrument_id, OrderSide.BUY, qty,
                    Price.from_str("130000.0"), time_in_force=TimeInForce.GTC,
                )
                self.submit_order(entry)
                # resting exits placed immediately after entry — as the adapter
                # will: stop at 99500, tp at 100900
                stop = self.order_factory.stop_market(
                    self.instrument_id, OrderSide.SELL, qty,
                    Price.from_str("99500.0"), time_in_force=TimeInForce.GTC,
                    reduce_only=True,
                )
                tp = self.order_factory.limit(
                    self.instrument_id, OrderSide.SELL, qty,
                    Price.from_str("100900.0"), time_in_force=TimeInForce.GTC,
                    reduce_only=True,
                )
                self.submit_order(stop)
                self.submit_order(tp)
        if i == 3 and self.scenario == "market_close":
            order = self.order_factory.market(
                self.instrument_id, OrderSide.BUY, qty, time_in_force=TimeInForce.GTC
            )
            self.submit_order(order)
        if i == 6 and self.scenario == "market_close":
            close = self.order_factory.market(
                self.instrument_id, OrderSide.SELL, qty, time_in_force=TimeInForce.GTC,
                reduce_only=True,
            )
            self.submit_order(close)


class ProbeConfig(StrategyConfig, frozen=True):
    scenario: str = "market_entry"
    instrument_id: str = f"{SYMBOL}.{VENUE}"


def run_scenario(scenario: str):
    config = BacktestEngineConfig(
        trader_id=TraderId("PROBE-001"),
        logging=LoggingConfig(log_level="ERROR"),
    )
    engine = BacktestEngine(config)
    instrument = make_instrument()
    engine.add_venue(
        venue=VENUE,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        starting_balances=[Money.from_str("100000 USDT")],
        bar_execution=True,
    )
    engine.add_instrument(instrument)
    bars, bar_type = make_bars(instrument)
    engine.add_data(bars)
    engine.add_strategy(ProbeStrategy(ProbeConfig(scenario=scenario)))
    engine.run()

    fills = engine.trader.generate_order_fills_report()
    account = engine.trader.generate_account_report(VENUE)
    orders = engine.trader.generate_orders_report()
    engine.dispose()
    return fills, account, orders


def show(scenario: str):
    fills, account, orders = run_scenario(scenario)
    print(f"\n================ {scenario} ================")
    if fills.empty:
        print("no fills")
    else:
        cols = [c for c in ["client_order_id", "type", "side", "last_px", "last_qty", "ts_event", "ts_init"] if c in fills.columns]
        print(fills[cols].to_string())
    if not account.empty:
        last = account.iloc[-1]
        print(f"final account total: {last['total']}")


if __name__ == "__main__":
    for s in ["market_entry", "aggressive_limit_entry", "bracket", "market_close"]:
        show(s)
