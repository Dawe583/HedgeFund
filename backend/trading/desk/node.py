"""Desk node — a live TradingNode running the harness strategies against
the kernel's sandbox venue.

Wiring, in one picture:

    feed (replay in tests / binance WS in production)
        -> msgbus endpoint DataEngine.process      (the kernel's own data path)
        -> live DataEngine routes bars to subscribers
            -> KernelHarnessStrategy.on_bar        (the M2 class, unmodified)
            -> SandboxExecutionClient.on_data      (SimulatedExchange matching)
        -> orders flow back through the same sandbox venue

The sandbox exchange IS the backtest matching engine (nautilus implements
`SandboxExecutionClient` over `SimulatedExchange`), so paper fills are the
same code that validation measured — parity by construction, not by audit.

State discipline: kernel state is in-memory and dies with the process; the
DB (via DeskLedger) is the record. On boot the node re-arms every open
position found there — market re-entry tagged "rearm" (excluded from trade
economics) plus the ORIGINAL stop/take-profit levels, so a restart never
flattens a book it doesn't understand.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from trading.backtest.engine import BTConfig
from trading.harness import wrap as harness_wrap
from trading.desk.worker import FeedHealth
from trading.kernel import (
    TIMEFRAME_BAR_SPEC,
    TIMEFRAME_NS,
    HarnessRunState,
    _strategy_class,
    make_sim_instrument,
)

from .frame import IncrementalFrame
from .provenance import DeskLedger, frame_time_at

log = logging.getLogger(__name__)

PAPER_VENUE = "PAPER"


@dataclass
class DeskSpec:
    """One strategy-instrument pair the desk trades. The roster is static in
    slice 1 by design — the lifecycle registry that will eventually own it
    is slice 4's seam, and nothing here presumes its shape beyond a list."""

    bot: str
    symbol: str
    timeframe: str
    strategy_cls: type
    bt_config: BTConfig = field(default_factory=BTConfig)


def make_harness_config():
    """The frozen StrategyConfig shape — one per process, same trick as
    kernel.py: msgspec config classes must be built once."""
    from nautilus_trader.config import StrategyConfig

    class DeskStrategyConfig(StrategyConfig, frozen=True):
        instrument_id: str
        bar_spec: str
        harness_state: object
        frame_source: object
        pure_strategy: object
        bt_config: object

    return DeskStrategyConfig


class DeskNode:
    """Builds, owns and supervises the TradingNode. Everything restart-
    sensitive is decided in `boot`, before the node starts: seed the frames
    from candle history, re-arm open positions, then subscribe bars."""

    def __init__(
        self,
        specs: list[DeskSpec],
        session_factory,
        seed_history,
        trader_id: str = "DESK-001",
        initial_equity: float | None = None,
        feed_stale_after_s: float = 900.0,
    ):
        """
        seed_history: fn(symbol, timeframe) -> list of candle dicts, newest-last,
        covering at least the feature warm-up (~130 bars) plus whatever the
        restart logic needs to re-derive signal bars of open positions.
        """
        self.specs = specs
        self.session_factory = session_factory
        self.seed_history = seed_history
        self.trader_id = trader_id
        if initial_equity is None:
            # the paper desk's equity is the validation equity: sizing parity
            # between backtest and paper is meaningless otherwise
            from trading.config import get_settings

            initial_equity = get_settings().paper_equity_start
        self.initial_equity = initial_equity
        self.feed_stale_after_s = feed_stale_after_s
        self.feed_health: dict[str, FeedHealth] = {}
        self.instruments = {}
        self.frames: dict[str, IncrementalFrame] = {}
        self.states: dict[str, HarnessRunState] = {}
        self.ledger = None
        self.node = None

    def _make_hook(self, spec: DeskSpec):
        ledger = self.ledger

        def hook(event: str, pos: dict) -> None:
            try:
                if event == "entry":
                    pos["ledger_row_id"] = ledger.entry_opened(spec.bot, {"symbol": spec.symbol}, pos)
                elif event == "close":
                    ledger.position_closed(spec.bot, {"symbol": spec.symbol}, pos)
                    ledger.equity_point(self._realized_total())
            except Exception:
                log.exception("provenance write failed for %s — desk state and DB now diverge", spec.bot)

        return hook

    def _realized_total(self) -> float:
        return sum(s.realized_net for s in self.states.values()) - self.initial_equity * (
            len(self.states) - 1
        )

    def build(self, exec_config=None, data_config=None):
        """Assemble the node. `exec_config`/`data_config` are the venue
        client configs; tests pass none and drive the sandbox alone."""
        from nautilus_trader.adapters.sandbox.config import SandboxExecutionClientConfig
        from nautilus_trader.adapters.sandbox.factory import SandboxLiveExecClientFactory
        from nautilus_trader.config import LoggingConfig, TradingNodeConfig
        from nautilus_trader.live.node import TradingNode

        # one ledger per desk; interval comes from the specs (single-TF desks
        # dominate slice 1; mixed TFs key the conversion per spec at write time)
        self.ledger = DeskLedger(self.session_factory, TIMEFRAME_NS[self.specs[0].timeframe])

        exec_clients = {
            PAPER_VENUE: SandboxExecutionClientConfig(
                venue=PAPER_VENUE,
                starting_balances=[f"{self.initial_equity:.2f} USDT"],
                base_currency="USDT",
                oms_type="NETTING",
                account_type="MARGIN",
            )
        }
        cfg = TradingNodeConfig(
            trader_id=self.trader_id,
            logging=LoggingConfig(log_level="WARNING"),
            exec_clients=exec_clients,
            data_clients=data_config or {},
        )
        node = TradingNode(cfg)
        node.add_exec_client_factory(PAPER_VENUE, SandboxLiveExecClientFactory)
        node.build()

        # The vendor sandbox subscribes `data.*.{venue}.*`, which matches tick
        # topics (data.quotes.PAPER.BTCUSDT-PERP) but never bar topics
        # (data.bars.BTCUSDT-PERP.PAPER-4-HOUR-LAST-EXTERNAL) — the wildcard
        # would need the venue in position 2. The sandbox is a tick-era
        # design; for bar-driven venues the execution side simply never sees
        # the market. Bridging here is integration work, not a fork: the
        # sandbox's own on_data does the processing, we only repair the
        # delivery route.
        exec_engine = node.kernel.exec_engine
        for client in exec_engine._clients.values():
            if hasattr(client, "on_data") and type(client).__name__ == "SandboxExecutionClient":
                node.kernel.msgbus.subscribe(
                    f"data.bars.*.{PAPER_VENUE}*",
                    handler=client.on_data,
                )
        for spec in self.specs:
            instrument = make_sim_instrument(spec.symbol, venue=PAPER_VENUE)
            self.instruments[spec.bot] = instrument
            node.cache.add_instrument(instrument)

            frame = IncrementalFrame()
            history = self.seed_history(spec.symbol, spec.timeframe)
            if history:
                frame.seed(history)
            self.frames[spec.bot] = frame

            state = HarnessRunState(self.initial_equity, on_position_event=self._make_hook(spec))
            health = FeedHealth(timeout_s=self.feed_stale_after_s)
            state.on_bar_processed = health.beat
            self.feed_health[spec.bot] = health
            self.states[spec.bot] = state

            cfg_cls = make_harness_config()
            strat = _strategy_class()(
                cfg_cls(
                    instrument_id=str(instrument.id),
                    bar_spec=TIMEFRAME_BAR_SPEC[spec.timeframe],
                    harness_state=state,
                    frame_source=frame,
                    pure_strategy=harness_wrap(spec.strategy_cls()),
                    bt_config=spec.bt_config,
                )
            )
            node.trader.add_strategy(strat)

        self.node = node
        return node

    # ------------------------------------------------------------------ restart
    def rearm_open_positions(self) -> None:
        """Re-arm every open position found in the DB. Runs BEFORE bars flow:
        the kernel starts flat, so each re-arm is a market re-entry tagged
        'rearm' — invisible to trade economics — followed by the original
        protective levels as a fresh OCO bracket. The alternative (flatten on
        restart) would make every deploy a forced liquidation; this class of
        divergence is documented in docs/design/m3-paper-plan.md."""
        for spec in self.specs:
            rows = self.ledger.open_positions(spec.bot)
            if not rows:
                continue
            strat = self._strategy_for(spec.bot)
            for row in rows:
                log.warning(
                    "re-arming %s %s %.6f %s from DB after restart",
                    spec.bot, row.side, row.qty, spec.symbol,
                )
                strat.rearm(
                    side=row.side,
                    qty=row.qty,
                    stop_loss=row.stop_loss,
                    take_profit=row.take_profit,
                    confidence=row.confidence,
                    signal_time=row.opened_at,
                    ledger_row_id=row.id,
                    entry_price=row.entry_price,
                )

    def _strategy_for(self, bot: str):
        # strategies are added in spec order in build(); trader.strategies
        # preserves it
        idx = [s.bot for s in self.specs].index(bot)
        return self.node.trader.strategies()[idx]
