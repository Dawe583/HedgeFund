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
from pathlib import Path

from trading.backtest.engine import BTConfig
from trading.harness import wrap as harness_wrap
from trading.desk.worker import FeedHealth
from trading.divergence import DivergenceBudget, budget_breaches, dev_ticks, reference_price
from trading.kernel import (
    TIMEFRAME_BAR_SPEC,
    TIMEFRAME_NS,
    ExposureBook,
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
    """One strategy-instrument pair the desk trades. Since slice 4 the roster
    comes from the lifecycle registry (trading/registry.py: versions in state
    `paper`); the node itself only ever sees a list of these. `strategy_params`
    is the registered version's parameter set — applied to the constructor,
    which register_version already proved accepts them."""

    bot: str
    symbol: str
    timeframe: str
    strategy_cls: type
    bt_config: BTConfig = field(default_factory=BTConfig)
    strategy_params: dict = field(default_factory=dict)
    # the declared divergence budget (design §7 gate item 6) — the registered
    # version's declaration for registry-driven desks, the zero-drift defaults
    # for everything else (tests, pre-registry soak bots). Never None: an
    # undeclared budget IS the default contract, honestly reported.
    budget: "DivergenceBudget" = field(default_factory=lambda: DivergenceBudget())


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
        venue: str = PAPER_VENUE,
        instrument_ids: dict[str, str] | None = None,
        frame_backfills: dict[str, object] | None = None,
    ):
        """
        seed_history: fn(symbol, timeframe) -> list of candle dicts, newest-last,
        covering at least the feature warm-up (~130 bars) plus whatever the
        restart logic needs to re-derive signal bars of open positions.

        venue: the sandbox exchange's venue label — PAPER in tests, BINANCE
        in production wiring (live.py documents why the label follows the
        data source). instrument_ids: per-bot real instrument id strings,
        used INSTEAD of synthesizing zero-margin sim instruments — the
        production path passes them and the actual instrument definitions
        arrive from the data client's provider at connect time; tests pass
        nothing and get the sim instrument on `venue`.
        """
        self.specs = specs
        self.session_factory = session_factory
        self.seed_history = seed_history
        self.trader_id = trader_id
        self.venue = venue
        self.instrument_ids = instrument_ids or {}
        self.frame_backfills = frame_backfills or {}
        if initial_equity is None:
            # the paper desk's equity is the validation equity: sizing parity
            # between backtest and paper is meaningless otherwise
            from trading.config import get_settings

            initial_equity = get_settings().paper_equity_start
        self.initial_equity = initial_equity
        self.feed_stale_after_s = feed_stale_after_s
        self.feed_health: dict[str, FeedHealth] = {}
        # one shared book — the gross exposure cap reads desk-wide truth
        self._exposure_book = ExposureBook()
        self.instruments = {}
        self._instrument_id_strs: dict[str, str] = {}
        # missed-bars breach latching: the counter is monotone within a boot,
        # so one risk_events row per boot per crossing is the honest tape —
        # a breach re-reports across restarts because the frame counter resets
        self._missed_breach_count: dict[str, int] = {}
        self.frames: dict[str, IncrementalFrame] = {}
        self.states: dict[str, HarnessRunState] = {}
        self.ledger = None
        self.node = None
        # Layer-4 halt sentinel (design §6): existence of this file halts
        # every entry and defers every re-arm, fail-closed, content never
        # read. Lives in the scratch data dir next to the worker lock —
        # an operator creates it when everything else is wrong.
        from trading.config import get_settings as _gs

        self.halt_sentinel_path = str(Path(_gs().data_dir) / "HALT")

        def _manual_halt_check() -> bool:
            from trading.risk import killswitch_state

            return bool(killswitch_state(self.session_factory)["tripped"])

        self._manual_halt_check = _manual_halt_check

    def _tick_size(self, instrument_id_str: str):
        """The instrument's price increment out of the node cache — lazy at
        fill time because production instruments arrive from the data client
        at connect, after build() wires the hooks. None means unknowable,
        and an unknowable tick size means no measurement, never an assumed
        one."""
        if self.node is None:
            return None
        try:
            from nautilus_trader.model.identifiers import InstrumentId

            instrument = self.node.cache.instrument(InstrumentId.from_str(instrument_id_str))
        except Exception:
            return None
        if instrument is None:
            return None
        return float(instrument.price_increment.as_decimal())

    def _measure_fill(self, spec: DeskSpec, pos: dict, fill: dict, kind: str) -> dict:
        """One fill's drift measurement against the role-implied reference
        (trading/divergence.py owns the semantics). Returns the evidence
        keys for the pos dict — values None when the reference is honestly
        unknowable: the filling bar missing from the frame means the fill
        cannot be tied to the tape it claims to belong to, and inventing a
        reference price would be exactly the lie the budget exists to catch."""
        import pandas as pd

        frame = self.frames[spec.bot].frame()
        interval_ns = TIMEFRAME_NS[spec.timeframe]
        open_ns = (int(fill["ts_event"]) - interval_ns) // interval_ns * interval_ns
        key = pd.Timestamp(open_ns, unit="ns", tz="UTC")
        out = {f"{kind}_dev_ticks": None, f"{kind}_ref_price": None}
        if kind == "entry":
            out["entry_lag_bars"] = None
        try:
            bar_pos = frame.index.get_loc(key)
        except KeyError:
            log.warning(
                "%s %s fill at %s keys no frame bar (fill %.2f) — drift unmeasurable, not assumed",
                spec.bot, kind, key.isoformat(), fill["price"],
            )
            return out
        tick = self._tick_size(self._instrument_id_strs.get(spec.bot, ""))
        if tick is None or tick <= 0:
            return out
        bar_close = float(frame.iloc[bar_pos]["close"])
        ref = reference_price(fill["role"], bar_close, pos.get("stop_loss") or 0.0, pos.get("take_profit") or 0.0)
        dev = dev_ticks(fill["price"], ref, tick)
        out[f"{kind}_dev_ticks"] = dev
        out[f"{kind}_ref_price"] = ref
        lag = None
        if kind == "entry" and pos.get("signal_bar") is not None and pos["signal_bar"] >= 0:
            # signal(k-1) → close(k) is lag zero; every bar beyond that is the
            # async-chain divergence class made visible
            lag = int(bar_pos) - int(pos["signal_bar"]) - 1
            out["entry_lag_bars"] = lag
        breaches = budget_breaches(spec.budget, dev=dev, lag_bars=lag if kind == "entry" else None)
        if breaches:
            self._write_risk_event(
                spec,
                "divergence_budget",
                "breached",
                {
                    "dimensions": breaches,
                    "fill_kind": kind,
                    "role": fill["role"],
                    "dev_ticks": round(dev, 4),
                    "budget_dev_ticks": spec.budget.dev_ticks,
                    "lag_bars": lag,
                    "budget_entry_lag_bars": spec.budget.entry_lag_bars,
                    "fill_price": fill["price"],
                    "ref_price": ref,
                    "bar_open": key.isoformat(),
                },
                int(fill["ts_event"]) / 1e9,
            )
        return out

    def _make_bar_watch(self, spec: DeskSpec, health: FeedHealth):
        """Chained on_bar_processed: the feed-health beat plus the missed-bar
        budget check. Missed bars are the soak acceptance dimension — bars the
        stream never delivered and REST could not recover — and the budget is
        the version's declared tolerance for them. The check runs at bar
        cadence inside the kernel thread: the frame counters are written
        there, so no lock and no staleness window exists. A crossing writes
        one risk_events row per new maximum: the tape shows every worsening,
        never a flood."""

        def watch() -> None:
            health.beat()
            frame = self.frames[spec.bot]
            missed = frame.missed_bars
            if missed > spec.budget.missed_bars and missed > self._missed_breach_count.get(spec.bot, -1):
                self._missed_breach_count[spec.bot] = missed
                log.error("%s missed-bars budget breached: %d missed of %d tolerated", spec.bot, missed, spec.budget.missed_bars)
                self._write_risk_event(
                    spec,
                    "divergence_budget",
                    "breached",
                    {
                        "dimensions": ["missed_bars"],
                        "missed_bars": missed,
                        "budget_missed_bars": spec.budget.missed_bars,
                        "backfilled_bars": frame.backfilled_bars,
                    },
                    0.0,
                )

        return watch

    def _make_hook(self, spec: DeskSpec):
        ledger = self.ledger

        def hook(event: str, pos: dict) -> None:
            try:
                if event == "entry":
                    pos.update(self._measure_fill(spec, pos, pos["entry_fill"], "entry"))
                    pos["ledger_row_id"] = ledger.entry_opened(spec.bot, {"symbol": spec.symbol}, pos)
                elif event == "close":
                    pos.update(self._measure_fill(spec, pos, pos["exit_fill"], "exit"))
                    ledger.position_closed(spec.bot, {"symbol": spec.symbol}, pos)
                    ledger.equity_point(self._realized_total())
            except Exception:
                log.exception("provenance write failed for %s — desk state and DB now diverge", spec.bot)

        return hook

    def _write_risk_event(self, spec: DeskSpec, rail: str, decision: str, inputs: dict, tape_ts: float) -> None:
        """One risk_events row per firing, written synchronously inside the
        event — the same provenance discipline as the position ledger (the
        DB is the record; kernel state is derived). A failed write must not
        kill the node loop: the firing already vetoed or tripped in memory,
        which is the rail's job; the row is its explanation."""
        import json as _json

        from trading.models import RiskEvent

        session = self.session_factory()
        try:
            session.add(
                RiskEvent(
                    bot=spec.bot,
                    symbol=spec.symbol,
                    rail=rail,
                    decision=decision,
                    inputs_json=_json.dumps(inputs, default=str),
                    tape_ts=float(tape_ts or 0.0),
                )
            )
            session.commit()
        except Exception:
            session.rollback()
            log.exception("risk_events write failed for %s — the firing stands, its explanation is missing", spec.bot)
        finally:
            session.close()

    def _make_veto_hook(self, spec: DeskSpec):
        """Every refused entry — sizing caps and Layer-0 rails share the veto
        tape — becomes a risk_events row with the inputs the refusal stands
        on: a rail that cannot explain itself is removed, not trusted
        (design §6)."""

        def hook(veto: dict) -> None:
            log.warning("entry vetoed [%s/%s]: %s", spec.bot, spec.symbol, veto)
            rail = veto.get("rail") or veto.get("reason", "unknown")
            inputs = {k: v for k, v in veto.items() if k not in ("rail", "reason")}
            merged = dict(veto.get("inputs") or {})
            merged.update(inputs)
            self._write_risk_event(spec, rail, "veto", merged, float(veto.get("tape_ts") or 0.0))

        return hook

    def _make_rail_hook(self, spec: DeskSpec):
        """Non-veto firings — kill-switch trips, daily-loss breaches, cooldown
        starts, halt observations — the risk_events rows that explain how the
        rails GOT to a veto."""

        def hook(event: dict) -> None:
            self._write_risk_event(
                spec, event["rail"], event["decision"], event.get("inputs") or {}, float(event.get("ts") or 0.0)
            )

        return hook


    def _make_signal_hook(self, spec: DeskSpec):
        """Every non-None emission the strategy produced — including every
        rejection — becomes a `signals` row (M3 acceptance). Same failure
        discipline as the position ledger: a failed write must not kill the
        bar loop; the kernel already decided, the row is its explanation."""
        ledger = self.ledger

        def hook(record: dict) -> None:
            try:
                ledger.signal_observed(
                    spec.bot,
                    {"symbol": spec.symbol, "timeframe": spec.timeframe},
                    record,
                )
            except Exception:
                log.exception("signal provenance write failed for %s — emission recorded in kernel memory only", spec.bot)

        return hook

    def _realized_total(self) -> float:
        if not self.states:
            # an empty roster has no desk equity beyond the initial stake —
            # and nothing ever calls this on one, but the honest answer must
            # exist anyway
            return self.initial_equity
        return sum(s.realized_net for s in self.states.values()) - self.initial_equity * (
            len(self.states) - 1
        )

    def build(self, exec_config=None, data_config=None, data_factories: dict | None = None):
        """Assemble the node. `exec_config`/`data_config` are the venue
        client configs; `data_factories` registers adapter factories BEFORE
        node.build (the live wiring passes the binance data factory here).
        Tests pass none of these and drive the sandbox alone."""
        from nautilus_trader.adapters.sandbox.config import SandboxExecutionClientConfig
        from nautilus_trader.adapters.sandbox.factory import SandboxLiveExecClientFactory
        from nautilus_trader.config import LoggingConfig, TradingNodeConfig
        from nautilus_trader.live.node import TradingNode

        # one ledger per desk; interval comes from the specs (single-TF desks
        # dominate slice 1; mixed TFs key the conversion per spec at write time)
        # empty rosters are first-class (slice 4: zero validated strategies is
        # the gate working, and the desk that boots empty must boot); the
        # interval default only matters to fill-time conversion, which no
        # strategyless desk ever performs
        interval_ns = TIMEFRAME_NS[self.specs[0].timeframe] if self.specs else TIMEFRAME_NS["4h"]
        self.ledger = DeskLedger(self.session_factory, interval_ns)

        exec_clients = exec_config or {
            self.venue: SandboxExecutionClientConfig(
                venue=self.venue,
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
        node.add_exec_client_factory(self.venue, SandboxLiveExecClientFactory)
        for name, factory in (data_factories or {}).items():
            node.add_data_client_factory(name, factory)
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
                    f"data.bars.*.{self.venue}*",
                    handler=client.on_data,
                )
        for spec in self.specs:
            if spec.bot in self.instrument_ids:
                # production wiring: the real adapter-provided instrument
                # arrives from the data client's provider at connect time —
                # correct tick/step sizes by construction, never the sim
                # zero-margin shape. Nothing to register into the cache here.
                instrument = None
                instrument_id_str = self.instrument_ids[spec.bot]
            else:
                instrument = make_sim_instrument(spec.symbol, venue=self.venue)
                instrument_id_str = str(instrument.id)
                node.cache.add_instrument(instrument)
            self.instruments[spec.bot] = instrument
            self._instrument_id_strs[spec.bot] = instrument_id_str

            frame = IncrementalFrame(
                interval_ns=TIMEFRAME_NS[spec.timeframe],
                backfill=self.frame_backfills.get(spec.bot),
            )
            history = self.seed_history(spec.symbol, spec.timeframe)
            if history:
                frame.seed(history)
            self.frames[spec.bot] = frame

            # ONE book per desk, handed to every strategy: the gross
            # exposure cap is desk-wide by construction (design §10,
            # multi-symbol), not a sum of per-bot blind spots.
            state = HarnessRunState(
                self.initial_equity,
                on_position_event=self._make_hook(spec),
                exposure_book=self._exposure_book,
                manual_halt_check=self._manual_halt_check,
                halt_sentinel_path=self.halt_sentinel_path,
            )
            state.on_veto = self._make_veto_hook(spec)
            state.on_rail_event = self._make_rail_hook(spec)
            state.on_signal = self._make_signal_hook(spec)
            health = FeedHealth(timeout_s=self.feed_stale_after_s)
            state.on_bar_processed = self._make_bar_watch(spec, health)
            self.feed_health[spec.bot] = health
            self.states[spec.bot] = state

            cfg_cls = make_harness_config()
            strat = _strategy_class()(
                cfg_cls(
                    instrument_id=instrument_id_str,
                    bar_spec=TIMEFRAME_BAR_SPEC[spec.timeframe],
                    harness_state=state,
                    frame_source=frame,
                    # the registered version's parameter set, proven to
                    # construct at registration time — params are part of what
                    # the lifecycle validated, never a runtime opinion
                    pure_strategy=harness_wrap(spec.strategy_cls(**spec.strategy_params)),
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
