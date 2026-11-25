"""Probe 2: bracket mechanics the kernel adapter depends on.

S1  stop-exact — intrabar touch fills exactly at the stop price
S2  stop-gap   — bar opens through the stop: fills at the open, not the stop
S3  tp-exact   — limit TP fills exact; OCO cancels the stop
S4  resting reduce-only orders submitted together with the entry — accepted?
S5  market order submitted at on_bar fills at that bar's close (control)

Each scenario gets its own hand-built bar series so every number answers
exactly one question. Entry is always a market buy of 0.010 submitted in
on_bar(1); it fills at close(1)=100300 (control fact from probe 1).
"""

import sys

sys.path.insert(0, ".")  # probe_execution lives beside this file

import pandas as pd

from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import (
    AccountType,
    ContingencyType,
    OmsType,
    OrderSide,
    TimeInForce,
)
from nautilus_trader.model.identifiers import InstrumentId, TraderId
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.trading.strategy import Strategy

from probe_execution import VENUE, ProbeConfig, make_bars, make_instrument

pd.set_option("display.width", 250)

# bar layout per scenario — bar 0 warmup, bar 1 entry decision (close 100300),
# bar 2+ is where the question is answered
WARM = [
    (100000.0, 100100.0, 99900.0, 100000.0),
    (100000.0, 100400.0, 99900.0, 100300.0),
]

SCENARIOS = {
    # stop 100100; bar3 low 99950 dips through intrabar, opens above
    "stop_exact": WARM + [
        (100650.0, 100700.0, 100500.0, 100650.0),
        (100650.0, 100660.0, 99950.0, 100100.0),
        (100100.0, 100200.0, 100000.0, 100150.0),
    ],
    # stop 100100; bar3 OPENS at 99500, straight through the stop
    "stop_gap": WARM + [
        (100650.0, 100700.0, 100500.0, 100650.0),
        (99500.0, 99600.0, 99400.0, 99550.0),
        (99550.0, 99600.0, 99450.0, 99580.0),
    ],
    # tp 100900 hit at bar3 high 101200; stop 100100 never threatened
    "tp_exact": WARM + [
        (100650.0, 100700.0, 100500.0, 100650.0),
        (100650.0, 101200.0, 100550.0, 101000.0),
        (101000.0, 101100.0, 100900.0, 101050.0),
    ],
    # same as tp_exact — the question is order states, not fills
    "reduce_only": WARM + [
        (100650.0, 100700.0, 100500.0, 100650.0),
        (100650.0, 101200.0, 100550.0, 101000.0),
        (101000.0, 101100.0, 100900.0, 101050.0),
    ],
    "market_control": WARM + [
        (100650.0, 100700.0, 100500.0, 100650.0),
        (100650.0, 100660.0, 100550.0, 100640.0),
    ],
}

STOP_PX = 100100.0
TP_PX = 100900.0


class BracketStrategy(Strategy):
    def __init__(self, config):
        super().__init__(config)
        self.instrument_id = InstrumentId.from_str(config.instrument_id)
        self.n = 0

    def on_start(self):
        self.subscribe_bars(BarType.from_str(f"{self.instrument_id}-1-HOUR-LAST-EXTERNAL"))

    def on_bar(self, bar):
        self.n += 1
        if self.n - 1 != 1:
            return
        qty = Quantity.from_str("0.010")
        bracket = self.order_factory.bracket(
            instrument_id=self.instrument_id,
            order_side=OrderSide.BUY,
            quantity=qty,
            contingency_type=ContingencyType.OCO,
            sl_trigger_price=Price.from_str(str(STOP_PX)),
            tp_price=Price.from_str(str(TP_PX)),
            time_in_force=TimeInForce.GTC,
        )
        self.submit_order_list(bracket)


def run(scenario: str, strategy_cls=BracketStrategy):
    config = BacktestEngineConfig(
        trader_id=TraderId("PROBE-001"), logging=LoggingConfig(log_level="ERROR")
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
    bars, _ = make_bars(instrument, SCENARIOS[scenario])
    engine.add_data(bars)
    engine.add_strategy(strategy_cls(ProbeConfig()))
    engine.run()
    fills = engine.trader.generate_order_fills_report()
    orders = engine.trader.generate_orders_report()
    positions = engine.trader.generate_positions_report()
    engine.dispose()
    return fills, orders, positions


def show(scenario: str):
    fills, orders, positions = run(scenario)
    print(f"\n================ {scenario} ================")
    cols = ["type", "side", "filled_qty", "liquidity_side", "avg_px", "ts_init", "ts_last"]
    print(fills[[c for c in cols if c in fills.columns]].to_string() if not fills.empty else "no fills")
    if not positions.empty:
        pc = [c for c in ["side", "quantity", "avg_px_open", "avg_px_close", "realized_pnl", "ts_opened", "ts_closed"] if c in positions.columns]
        print(positions[pc].to_string())
    if scenario == "tp_exact":
        oc = [c for c in ["type", "side", "price", "trigger_price", "status"] if c in orders.columns]
        print("-- order states --")
        print(orders[oc].to_string())


if __name__ == "__main__":
    for s in ["stop_exact", "stop_gap", "tp_exact", "market_control"]:
        show(s)
