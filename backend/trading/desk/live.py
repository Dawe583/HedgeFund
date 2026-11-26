"""Live Binance wiring for the paper desk — the production data seam.

The replay tests register ReplayFeeder actors; production registers the
adapter's data client instead. Both paths coexist on the same DeskNode
because the seam is the same in both: bars travel msgbus endpoint
`DataEngine.process` into the live DataEngine, and the sandbox exchange is
the only execution client either way.

Decision notes, all measured against the installed adapter
(nautilus_trader 1.231.0):

1. DATA IS MAINNET, EXECUTION IS ALWAYS THE LOCAL SANDBOX. Real money never
   exists in M3 — there is no Binance exec client in this process, so
   "testnet-first" has nothing to apply to on the execution side. For data,
   testnet futures klines are thin/fake (few participants, dead books); the
   honest tape is mainnet public market data. Public klines need no API key:
   BinanceDataClientConfig documents "If None, the client will work for
   public market data only", and the futures provider falls back to the
   venue fee-tier table when no key is present (measured in
   adapters/binance/futures/providers.py::load_ids_async). The desk carries
   no keys at all.

2. VENUE ALIGNMENT: production runs venue label BINANCE end-to-end —
   instrument ids are BTCUSDT-PERP.BINANCE, the sandbox exchange's venue is
   BINANCE, the bar bridge and the strategy subscriptions all key on the
   same id. The alternative (relabeling the data client config venue to
   PAPER) is technically available (the adapter threads config.venue through
   the provider) but would publish Binance tape under a venue label that
   claims it is the sandbox's own — provenance fraud for one config flag's
   convenience. Nautilus keys everything — cache, order routing, matching
   books — by the full InstrumentId including venue; there is no venue
   translation layer, so the sandbox MUST wear the data's venue label.
   Nothing about the BINANCE label triggers real-money behavior: execution
   routing resolves to the registered client for that venue, which is the
   sandbox.

3. INSTRUMENT TRUTH comes from the adapter's futures provider: real
   tick/step sizes parsed out of exchangeInfo (measured in
   futures/providers.py::_parse_instrument — tickSize/stepSize drive
   price/size increments), never the test's zero-margin make_sim_instrument.
   Delivery: client connect loads instruments and pushes them through
   `_handle_data` -> live DataEngine -> msgbus `data.instrument.BINANCE.*`,
   which the sandbox client's own `data.*.{venue}.*` subscription matches;
   SimulatedExchange.update_instrument registers the book on first sight.
   Ordering is safe by construction: exec clients connect synchronously in
   the same loop tick the data clients' async connects are scheduled in, so
   the sandbox's msgbus subscription predates any instrument publication
   (measured in system/kernel.py::_connect_clients and
   live/data_client.py::connect). The sandbox exchange is given high
   leverage because the adapter sets margin_init=1.0 on Binance perps
   ("Binance docs: ignore API values"): at the sandbox default leverage of 1
   the margin check would reject sizing the validation harness considers
   legitimate — a divergence with no economic meaning in M3, where exposure
   caps are slice 3's explicit problem. Leverage 50 keeps the margin check
   non-binding for the harness's risk-per-trade sizing while the account
   arithmetic stays real.

4. BAR TRUTH IS THE CLOSED CANDLE. The kline WS pushes the forming candle
   every second; the adapter's _handle_kline drops every update with
   x=False and publishes only closed klines — exactly the harness's feed
   contract, no filtering needed on our side. Two consequences:
   - ts_event is the kline CLOSE time (kline.T, measured in
     parse_to_binance_bar), not the open the harness convention assumes.
     IncrementalFrame normalizes keys to the open by interval flooring; see
     frame.py for why that arithmetic is exact for Binance's T.
   - "missed tick" for a closed-bar truth means a missed or late BAR. The
     kline stream carries no sequence id, so the honest integrity checks
     are: wall-clock staleness (FeedHealth — a feed silent longer than
     timeout is dead) and bar-open arithmetic (frame.missed_bars — a bar
     whose key jumps more than one interval means the intermediates never
     arrived). The arithmetic detects a gap one bar late by construction;
     nothing finer exists without consuming the raw stream, which the
     adapter does not expose.

5. QUOTES ARE THE EXECUTABLE MARKET. The replay feeder synthesizes a
   zero-spread quote at each bar close because the sandbox's matching
   engine rejects market orders when no quote exists ("no market" —
   measured in slice 1). Binance bars alone never produce quotes either, so
   production subscribes the @bookTicker stream (quote ticks) and lets them
   flow to the sandbox through its own data.*.{venue}.* subscription.
   Divergence vs the replay model: fills cross the real spread — honest,
   sub-cent at BTCUSDT depth, and documented here. Intrabar protective
   fills also gain granularity (quotes at ~1s cadence vs bar-close-only).
   The bridge below is an actor for the same reason ReplayFeeder is:
   subscription plumbing belongs on the node's own loop.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from trading.desk.node import DeskNode, DeskSpec
from trading.kernel import TIMEFRAME_NS

log = logging.getLogger(__name__)

BINANCE_VENUE = "BINANCE"

# leverage high enough that the sandbox margin check never binds against the
# harness's risk-per-trade sizing — see decision note 3
SANDBOX_LEVERAGE = Decimal(50)


def production_instrument_id(symbol: str) -> str:
    """BTCUSDT -> BTCUSDT-PERP.BINANCE — the adapter's USDT-M perpetual
    naming (BinanceSymbol.parse_as_nautilus, measured)."""
    return f"{symbol.upper()}-PERP.{BINANCE_VENUE}"


def make_data_config(symbols: list[str], proxy_url: str | None = None):
    """BinanceDataClientConfig for public USDT-M futures data: no keys,
    mainnet environment (the default), instruments pinned to the roster so
    the provider never walks the whole exchangeInfo list. proxy_url exists
    for the reconnect probe — production runs without one."""
    from nautilus_trader.adapters.binance.common.enums import BinanceAccountType
    from nautilus_trader.adapters.binance.config import (
        BinanceDataClientConfig,
        BinanceInstrumentProviderConfig,
    )
    from nautilus_trader.model.identifiers import InstrumentId

    return BinanceDataClientConfig(
        account_type=BinanceAccountType.USDT_FUTURES,
        instrument_provider=BinanceInstrumentProviderConfig(
            load_ids=frozenset(
                InstrumentId.from_str(production_instrument_id(s)) for s in symbols
            ),
        ),
        proxy_url=proxy_url,
    )


def make_exec_config(initial_equity: float):
    """The sandbox exchange wearing the BINANCE venue label — decision
    note 2. High leverage keeps the margin arithmetic non-binding against
    harness sizing — decision note 3."""
    from nautilus_trader.adapters.sandbox.config import SandboxExecutionClientConfig

    return {
        BINANCE_VENUE: SandboxExecutionClientConfig(
            venue=BINANCE_VENUE,
            starting_balances=[f"{initial_equity:.2f} USDT"],
            base_currency="USDT",
            oms_type="NETTING",
            account_type="MARGIN",
            default_leverage=SANDBOX_LEVERAGE,
        )
    }


class QuoteFeedBridge:
    """Builds the quote-subscribing actor. Deferred class construction for
    the same reason kernel.py defers the strategy class: the kernel imports
    cost seconds and the class must exist once per process."""

    @staticmethod
    def make(instrument_ids: list[str]):
        from nautilus_trader.common.actor import Actor
        from nautilus_trader.config import ActorConfig
        from nautilus_trader.model.identifiers import InstrumentId

        class QuoteBridge(Actor):
            """Subscribes quote ticks for the production instruments. The
            sandbox exchange consumes them through its own
            `data.*.{venue}.*` msgbus subscription — this actor's only job
            is to make the DataEngine request them from the venue client.
            Ticks are never transformed, so the bridge is inert in replay:
            no venue client exists there to answer the subscription."""

            def on_start(self):
                for id_str in instrument_ids:
                    self.subscribe_quote_ticks(InstrumentId.from_str(id_str))

        return QuoteBridge(ActorConfig(component_id="quote-feed-bridge"))


def make_backfill(symbol: str, timeframe: str):
    """A backfill callable for IncrementalFrame over binance REST.

    Arguments are nanosecond bar-open keys strictly bracketing the gap:
    bars in (after_open_ns, before_open_ns) are the missing ones. Returns
    seed-contract dicts. fetch_klines_range is inclusive on both ends, so
    the query covers [after_open, before_open - 1ms] — the two boundary
    bars are already in the frame (the last key present) or arrive by wire
    (the incoming bar), and the frame's dedupe drops them; only strictly
    missing keys insert."""
    import datetime as dt

    from trading.desk.binance_history import fetch_klines_range

    one_ms = dt.timedelta(milliseconds=1)

    def backfill(after_open_ns: int, before_open_ns: int) -> list[dict]:
        start = dt.datetime.fromtimestamp(after_open_ns / 1e9, tz=dt.UTC)
        end = dt.datetime.fromtimestamp(before_open_ns / 1e9, tz=dt.UTC) - one_ms
        if end <= start:
            return []
        return fetch_klines_range(symbol, timeframe, start, end)

    return backfill


def build_production_desk(
    specs: list[DeskSpec],
    session_factory,
    seed_history,
    proxy_url: str | None = None,
    **desk_kwargs,
) -> DeskNode:
    """The production twin of the test boot: same harness strategy factory,
    same SandboxExecutionClient — the data seam is the only difference.
    Returns the built (not yet started) desk."""
    from nautilus_trader.adapters.binance.factories import BinanceLiveDataClientFactory

    instrument_ids = {spec.bot: production_instrument_id(spec.symbol) for spec in specs}
    desk = DeskNode(
        specs=specs,
        session_factory=session_factory,
        seed_history=seed_history,
        venue=BINANCE_VENUE,
        instrument_ids=instrument_ids,
        frame_backfills={spec.bot: make_backfill(spec.symbol, spec.timeframe) for spec in specs},
        **desk_kwargs,
    )
    desk.build(
        exec_config=make_exec_config(desk.initial_equity),
        data_config={BINANCE_VENUE: make_data_config(sorted({s.symbol for s in specs}), proxy_url=proxy_url)},
        data_factories={BINANCE_VENUE: BinanceLiveDataClientFactory},
    )
    desk.node.trader.add_actor(QuoteFeedBridge.make(sorted(instrument_ids.values())))
    return desk


def seed_drop_forming_bar(symbol: str, timeframe: str) -> list[dict]:
    """seed_history implementation over trading.desk.binance_history.

    The REST fetch's last row may be the still-FORMING bar (documented in
    binance_history.fetch_klines). Seeding it would inject partial-bar data
    the feature frame then treats as a closed truth — a quiet parity break.
    The forming bar's open_time is within one interval of now; strictly
    older rows are closed by construction."""
    import datetime as dt

    from trading.desk.binance_history import fetch_klines

    rows = fetch_klines(symbol, timeframe, limit=1500)
    if not rows:
        return rows
    interval = dt.timedelta(microseconds=TIMEFRAME_NS[timeframe] / 1000)
    now = dt.datetime.now(dt.UTC)
    if now - rows[-1]["open_time"] < interval:
        return rows[:-1]
    return rows
