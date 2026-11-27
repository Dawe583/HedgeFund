"""Paper trading worker — live data in, simulated executions out.

Single asyncio process:
1. streams live BTCUSDT candles (WS) and persists them
2. every tick evaluates each bot against the latest CLOSED candle
3. simulates fills (fees + slippage), manages SL/TP, records trades/equity
"""

import asyncio
import contextlib
import datetime as dt
import logging
import signal as os_signal
from pathlib import Path

import numpy as np
from sqlalchemy import delete, select

from trading.agents import build_agents
from trading.agents.base import Insight, save_insight
from trading.agents.memory import LearningLoop
from trading.config import get_settings
from trading.features import build_features, candles_to_df
from trading.feeds.binance import stream_klines
from trading.feeds.fallback import fetch_candles_any
from trading.models import (
    init_schema,
    make_engine,
    AgentInsight,
    AgentPrediction,
    BotStatus,
    Candle,
    EquityPoint,
    ModelVersion,
    OpenPosition,
    Trade,
    get_state,
    make_session_factory,
    set_state,
)
from trading.risk import RiskManager, killswitch_state
from trading import risk_guard
from trading.trailing import time_stop_bars, trailing_level
from trading.storage import upsert_candles

log = logging.getLogger(__name__)

SYMBOL = "BTCUSDT"
RETRAIN_INTERVAL_DAYS = 7
BACKFILL_MIN_DAYS = 28  # every agent gets >= 4 weeks of candle history
FORECAST_INTERVAL_S = 900  # per-bot forecast cadence (CI cycles are 30 min)
STALE_CANDLE_S = 300  # 1m feed older than 5 min => stale
SIGNAL_MAX_AGE_BARS = 2  # rescans may only act on the last N closed bars
_TF_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240}
_TIME_STOP_BARS = 24  # exit any position open >= 24 bars of its bot timeframe
EQUITY_POINT_EVERY_TICKS = 60  # ~10 min at the 10s cadence
EQUITY_POINT_DELTA_PCT = 0.001  # ...unless equity moved > 0.1%
PRUNE_INTERVAL_S = 3600
PRUNE_KEEP_EQUITY = 5000
PRUNE_KEEP_INSIGHTS = 3000
PRUNE_KEEP_PREDICTIONS = 500
PRUNE_CANDLE_1M_DAYS = 90

BOT_SPECS = {
    # Turbo 24/7 desk: 5 bots across 1m → 4h so at least ~5 entries/day land
    # on BTC. Confidence floors lowered (HFT 0.45, scalp 0.52); each bot may
    # hold up to max_positions concurrent positions; leverage is picked
    # dynamically per-signal in [leverage_min, leverage_max] (default 2–25x).
    # ml_gate_threshold None = bypass the 4h long-only champion on intraday TFs.
    "hft": {
        "timeframe": "1m", "strategy": "hft", "confidence_min": 0.45,
        "mode": "active", "size_mult": 3.0, "leverage": 25,
        "ml_gate_threshold": None, "max_positions": 3,
    },
    "hft_5m": {
        "timeframe": "5m", "strategy": "hft", "confidence_min": 0.45,
        "mode": "active", "size_mult": 2.5, "leverage": 20,
        "ml_gate_threshold": None, "max_positions": 2,
    },
    "scalp_15m": {
        "timeframe": "15m", "strategy": "scalp", "confidence_min": 0.52,
        "mode": "active", "size_mult": 2.0, "leverage": 15,
        "ml_gate_threshold": None, "max_positions": 2,
    },
    "scalp_1h": {
        "timeframe": "1h", "strategy": "scalp", "confidence_min": 0.52,
        "mode": "active", "size_mult": 1.5, "leverage": 10,
        "ml_gate_threshold": 0.50, "max_positions": 2,
    },
    "scalp": {
        "timeframe": "4h", "strategy": "scalp", "confidence_min": 0.52,
        "mode": "active", "size_mult": 1.5, "leverage": 10,
        "ml_gate_threshold": 0.50, "max_positions": 2,
    },
}


def _acquire_worker_lock() -> bool:
    """Single-worker guard: flock on <data_dir>/worker.lock. False if held."""
    import fcntl

    path = Path(get_settings().data_dir)
    path.mkdir(parents=True, exist_ok=True)
    lock_path = path / "worker.lock"
    fh = open(lock_path, "w")  # noqa: SIM115 — held for the process lifetime
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log.error("another paper worker holds %s — exiting", lock_path)
        fh.close()
        return False
    return True



def _engine_with_schema():
    """The paper worker is a writer and owns its startup schema init."""
    engine = make_engine()
    init_schema(engine)
    return engine

class PaperEngine:
    def __init__(self):
        self.s = get_settings()
        self.session_factory = make_session_factory(_engine_with_schema())
        self.risk = RiskManager(self.s)
        from trading.bots import HFTMomentum, ScalpTrend

        self.strategies = {"hft": HFTMomentum(), "scalp": ScalpTrend()}
        self.learning = LearningLoop(self.session_factory)
        from trading.agents.forecaster import Forecaster

        self.forecaster = Forecaster(self.session_factory)
        self._last_forecast: dict[str, float] = {}
        self._last_seen_bar: dict[str, object] = {}  # bot -> last evaluated bar ts
        # auto-trip latch for the automatic drawdown kill-switch — distinct
        # from the manual __killswitch row. Persisted in the kv store
        # (kill_tripped / kill_trip_meta) because a restart must not be a
        # risk reset (F-4 hole 2); _init_state reloads it. The operator
        # un-kill is risk.reset_kill_state — clearing the manual row alone
        # would silently leave this latch set.
        self._auto_kill = False
        # the last close the evaluation loop saw — _equity_now falls back to
        # it when no close is passed, so the periodic equity/peak path marks
        # open positions too (the honest approximation: staleness is bounded
        # by the tick cadence, and the alternative — realized-only peak
        # tracking — is exactly the inconsistency F-4 named)
        self._last_close_seen = None
        self.killed = False
        self._stop = False
        self._last_analyst_run = float("-inf")  # fire on first tick
        self._last_retrain_check = float("-inf")
        self._last_prune = float("-inf")
        self._last_equity_point = None
        self._tick_count = 0
        self._tasks: dict[str, asyncio.Task] = {}
        self._champion = None  # cached deserialized champion gate
        self._champion_tf: str | None = None  # parsed from ModelVersion.name gate-<SYM>-<TF>
        self._champion_checked_at = 0.0
        bot_stats = self._build_bot_stats()
        self.agents = build_agents(bot_stats=bot_stats)
        # Lazy import: keeps worker RSS low on the RPi4 (no heavy LLM chain
        # at module import time); Prime builds its own agents lazily too.
        from trading.agents.prime import PrimeOrchestrator

        self.prime = PrimeOrchestrator(self.session_factory, bot_stats=bot_stats)
        self._agents_rebuilt_at = asyncio.get_event_loop().time()
        self._init_state()

    # ------------------------------------------------------------------ state
    def _init_state(self) -> None:
        """Load peak_equity and the auto-kill latch from the kv store so
        restarts keep both. A previously tripped engine STAYS killed across
        the restart — restarting the process is not a risk reset (F-4 hole
        2). The only way back is the deliberate operator reset,
        risk.reset_kill_state, wired into the manual killswitch endpoint."""
        session = self.session_factory()
        try:
            peak = get_state(session, "peak_equity")
            self.peak_equity = float(peak) if peak is not None else self.s.paper_equity_start
            self._auto_kill = bool(get_state(session, "kill_tripped", False))
            if self._auto_kill:
                log.error("auto kill-switch latch persisted — staying killed (meta: %s)",
                          get_state(session, "kill_trip_meta"))
        finally:
            session.close()

    def _persist_peak(self, session) -> None:
        set_state(session, "peak_equity", self.peak_equity)

    def _day_start_equity(self, session, equity: float) -> float:
        """Equity at UTC midnight; re-baselines when the UTC date rolls."""
        today = dt.datetime.now(dt.UTC).date().isoformat()
        day = get_state(session, "day")
        val = get_state(session, "day_start_equity")
        if day != today or val is None:
            set_state(session, "day", today)
            set_state(session, "day_start_equity", equity)
            return equity
        return float(val)

    # ------------------------------------------------------------------ utils
    def _ensure_bot_rows(self, session):
        for name, spec in BOT_SPECS.items():
            row = session.get(BotStatus, name)
            if row is None:
                session.add(
                    BotStatus(
                        name=name,
                        running=True,
                        mode=spec.get("mode", "active"),
                        note="boot",
                    )
                )
        session.commit()

    def _build_bot_stats(self, lookback: int = 100) -> dict:
        """Per-bot realized stats (wr, avg pnl_pct, n) from the last N trades."""
        session = self.session_factory()
        try:
            out: dict[str, dict] = {}
            for bot in BOT_SPECS:
                rows = session.execute(
                    select(Trade.pnl, Trade.qty, Trade.entry_price)
                    .where(Trade.bot == bot)
                    .order_by(Trade.exit_time.desc())
                    .limit(lookback)
                ).all()
                if not rows:
                    out[bot] = {"wr": 0.45, "avg_pnl_pct": 0.0, "n": 0}
                    continue
                wins = sum(1 for r in rows if r.pnl > 0)
                pnls_pct = [r.pnl / max(r.qty * r.entry_price, 1e-9) for r in rows]
                out[bot] = {
                    "wr": wins / len(rows),
                    "avg_pnl_pct": sum(pnls_pct) / len(pnls_pct),
                    "n": len(rows),
                }
            all_rows = session.execute(
                select(Trade.pnl, Trade.qty, Trade.entry_price)
                .order_by(Trade.exit_time.desc())
                .limit(lookback)
            ).all()
            if all_rows:
                wins = sum(1 for r in all_rows if r.pnl > 0)
                pnls_pct = [r.pnl / max(r.qty * r.entry_price, 1e-9) for r in all_rows]
                out["*"] = {
                    "wr": wins / len(all_rows),
                    "avg_pnl_pct": sum(pnls_pct) / len(pnls_pct),
                    "n": len(all_rows),
                }
            return out
        finally:
            session.close()

    def _refresh_champion(self) -> None:
        """Reload the champion ML gate at most once a minute."""
        now = asyncio.get_event_loop().time()
        if now - self._champion_checked_at < 60:
            return
        self._champion_checked_at = now
        from trading.ml.predict import load_champion, champion_timeframe

        session = self.session_factory()
        try:
            self._champion = load_champion(session)
            self._champion_tf = champion_timeframe(session)
        except Exception:
            log.exception("champion load failed")
            self._champion = None
            self._champion_tf = None
        finally:
            session.close()

    def _bump_veto(self, session, bot: str, gate: str) -> None:
        """Per-gate veto counter in kv store — dashboard can SELECT instead of guessing."""
        try:
            key = f"veto:{bot}:{gate}"
            cur = get_state(session, key)
            set_state(session, key, int(cur or 0) + 1)
            session.commit()
        except Exception:
            log.exception("veto counter write failed")
            session.rollback()

    def _maybe_rebuild_agents(self) -> None:
        """Rebuild the agent dict hourly so quant sees fresh per-bot stats."""
        now = asyncio.get_event_loop().time()
        if now - self._agents_rebuilt_at < 3600:
            return
        self._agents_rebuilt_at = now
        try:
            stats = self._build_bot_stats()
            self.agents = build_agents(bot_stats=stats)
            self.prime.bot_stats = stats
            log.info("agents rebuilt with fresh bot stats")
        except Exception:
            log.exception("agent rebuild failed — keeping previous dict")

    def _trip_auto_kill(self, session, equity: float) -> None:
        """The automatic drawdown kill-switch fires: latch in memory AND
        persist the trip with its metadata into the kv store beside
        peak_equity. A restart reloads the latch (see _init_state) — the
        trip memory must not die with the process. The operator reset is
        risk.reset_kill_state; this function has no inverse here by design."""
        self._auto_kill = True
        dd = (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0.0
        log.error("KILL SWITCH — equity %.2f vs peak %.2f (drawdown %.4f) — persisting trip",
                  equity, self.peak_equity, dd)
        try:
            set_state(session, "kill_tripped", True)
            set_state(session, "kill_trip_meta", {
                "ts": dt.datetime.now(dt.UTC).isoformat(),
                "equity_marked": round(equity, 6),
                "peak_equity": round(self.peak_equity, 6),
                "drawdown_pct": round(dd, 6),
            })
            session.commit()
        except Exception:
            # a failed persist must not un-trip the in-memory latch — the
            # log above is the evidence and the next trip attempt retries
            log.exception("kill trip persist failed — latch holds in memory only")
            session.rollback()

    def _equity_now(self, session, last_close: float | None = None) -> tuple[float, float]:
        """(equity_marked, realized_pnl). Equity includes unrealized PnL —
        consistently: when no close is passed the last close the evaluation
        loop saw is used, so the periodic equity/peak path measures the same
        marked quantity as the signal-time path. The stored close is the
        honest approximation (staleness bounded by the tick cadence); the
        pre-F-4 alternative — unrealized silently zero on that path — made
        peak tracking blind to exactly the drawdowns the kill-switch exists
        for. Kernel parity: validation's rails measure realized + unrealized
        at bar close too, and this is the same quantity."""
        if last_close is None:
            last_close = self._last_close_seen
        realized = sum(t.pnl for t in session.execute(select(Trade)).scalars())
        unrealized = 0.0
        if last_close is not None:
            for p in session.execute(select(OpenPosition)).scalars():
                sign = 1 if p.side == "long" else -1
                unrealized += (last_close - p.entry_price) * p.qty * sign
        return self.s.paper_equity_start + realized + unrealized, realized

    def _exit_price(self, side: str, stop: float, candle: dict, take: float, hit_sl: bool) -> float:
        """Backtest-aligned SL/TP fill: gap-through fills at the worse price.

        Long SL: candle low broke it -> fill at min(open, SL) minus slippage;
        long TP: candle high reached it -> fill at TP plus slippage. Mirrored
        for shorts. Keeps paper fills honest vs the backtest engine.
        """
        # cost curve v1: the filling candle's own width prices the fill —
        # gap-through exits land in exactly the bars where flat slippage lied most
        from trading.costs import bar_slippage_bps
        slip = bar_slippage_bps(candle["high"], candle["low"], candle["close"], self.s.slippage_bps) / 10_000
        if hit_sl:
            if side == "long":
                gap_fill = min(candle["open"], stop)
                return gap_fill * (1 - slip)
            gap_fill = max(candle["open"], stop)
            return gap_fill * (1 + slip)
        return take * (1 - slip) if side == "long" else take * (1 + slip)

    async def _maybe_close_positions(self, session, last_candle: dict):
        positions = session.execute(select(OpenPosition)).scalars().all()
        closed: list[Trade] = []
        trail_mult = float(getattr(self.s, "trailing_stop_atr_mult", 1.0))
        for p in positions:
            # trailing stop: once open profit exceeds trail_mult × risk distance,
            # ratchet SL to breakeven (+10% of the profit) — locks winners, rides trend.
            try:
                risk_d = abs(p.entry_price - p.stop_loss)
                cur_px = float(last_candle["close"])
                profit_d = (cur_px - p.entry_price) if p.side == "long" else (p.entry_price - cur_px)
                if risk_d > 0 and profit_d > trail_mult * risk_d:
                    new_sl = p.entry_price + (0.1 * profit_d if p.side == "long" else -0.1 * profit_d)
                    if (p.side == "long" and new_sl > p.stop_loss) or (p.side == "short" and new_sl < p.stop_loss):
                        p.stop_loss = new_sl
                        session.commit()
            except Exception:
                pass
            # ATR trailing ratchet (pure helper): re-anchor the stop at the
            # best favourable extreme; only ever move it toward profit.
            try:
                _range = float(last_candle["high"]) - float(last_candle["low"])
                _atr = _range if _range > 0 else abs(float(p.entry_price)) * 0.0005
                _ref = p.entry_price
                if p.side == "long":
                    _ref = max(_ref, float(last_candle["high"]))
                else:
                    _ref = min(_ref, float(last_candle["low"]))
                _trail = trailing_level(p.side, _ref, _atr, trail_mult)
                if p.side == "long" and _trail > p.stop_loss:
                    p.stop_loss = _trail
                    session.commit()
                elif p.side == "short" and _trail < p.stop_loss:
                    p.stop_loss = _trail
                    session.commit()
            except Exception:
                pass
            # Time stop (pure helper): stale positions exit at market even if
            # neither SL nor TP was touched. Candle open_time (not wall clock)
            # so WS gaps/backfills cannot prematurely age positions.
            try:
                _tfm = _TF_MINUTES.get((BOT_SPECS.get(p.bot) or {}).get("timeframe", "1m"), 1)
                time_expired = time_stop_bars(
                    last_candle.get("open_time"), p.opened_at, _tfm, _TIME_STOP_BARS
                )
            except Exception:
                time_expired = False
            hit_sl = (
                last_candle["low"] <= p.stop_loss
                if p.side == "long"
                else last_candle["high"] >= p.stop_loss
            )
            hit_tp = (
                last_candle["high"] >= p.take_profit
                if p.side == "long"
                else last_candle["low"] <= p.take_profit
            )
            if not (hit_sl or hit_tp or time_expired):
                continue
            hit_sl_first = hit_sl  # conservative: stop first
            if time_expired and not (hit_sl or hit_tp):
                exit_px = float(last_candle["close"])  # time exit at market
            else:
                exit_px = self._exit_price(
                    p.side, p.stop_loss, last_candle, p.take_profit, hit_sl_first
                )
            gross = (exit_px - p.entry_price) * p.qty * (1 if p.side == "long" else -1)
            fees = (p.entry_price + exit_px) * p.qty * (self.s.taker_fee_pct / 100)
            pnl = gross - fees
            trade = Trade(
                bot=p.bot,
                symbol=p.symbol,
                side=p.side,
                qty=p.qty,
                entry_price=p.entry_price,
                exit_price=exit_px,
                entry_time=p.opened_at,
                exit_time=dt.datetime.now(dt.UTC),
                pnl=pnl,
                fees=fees,
                confidence=p.confidence,
                gate_source=getattr(p, "gate_source", None) or "legacy",
            )
            session.add(trade)
            session.delete(p)
            closed.append(trade)
            log.info("%s CLOSE @ %.2f pnl=%.4f", p.bot, exit_px, pnl)
        session.commit()
        # self-learning loop: store outcomes/lessons, reflect every N trades
        now_ts = dt.datetime.now(dt.UTC).timestamp()
        for t in closed:
            await self.learning.record_outcome(t)
            try:
                risk_guard.record_close(
                    lambda k: get_state(session, k),
                    lambda k, v: set_state(session, k, v),
                    t.bot, float(t.pnl), now_ts,
                )
            except Exception:
                log.exception("loss-streak guard record failed")
        if closed:
            await self.learning.maybe_extended_reflect()

    def _tuning(self, session) -> dict:
        """Live kv overrides from the dashboard (SET/autopilot) — no restart needed."""
        try:
            out = {}
            for k in ("leverage_min", "leverage_max", "risk_per_trade_pct",
                      "confidence_min_hft", "confidence_min_scalp",
                      "max_positions_per_bot", "turbo_mode"):
                v = get_state(session, f"tuning:{k}")
                if v is not None:
                    out[k] = v
            return out
        except Exception:
            return {}

    async def _maybe_open_position(self, session, bot: str, feats, price: float):
        spec = dict(BOT_SPECS[bot])
        t = self._tuning(session)
        if "max_positions_per_bot" in t:
            spec["max_positions"] = int(t["max_positions_per_bot"])
        tf = spec.get("timeframe", "")
        if tf in ("1m", "5m") and "confidence_min_hft" in t:
            spec["confidence_min"] = float(t["confidence_min_hft"])
        if tf not in ("1m", "5m") and "confidence_min_scalp" in t:
            spec["confidence_min"] = float(t["confidence_min_scalp"])
        strat = self.strategies[spec["strategy"]]
        # scan EVERY unseen bar since the last processed one — slow ticks /
        # WS drops must never skip a signal. But only the LAST
        # SIGNAL_MAX_AGE_BARS bars are actionable: anything older is stale.
        last_seen = self._last_seen_bar.get(bot)
        sig = None
        sig_bar = None  # index into feats of the bar that produced the signal
        scan_from = max(96, len(feats) - 60)
        for i in range(scan_from, len(feats)):
            bar_ts = feats.index[i]
            if last_seen is not None and bar_ts <= last_seen:
                continue
            s = strat.signal(i, feats)
            if s and s.confidence >= spec["confidence_min"]:
                if i < len(feats) - SIGNAL_MAX_AGE_BARS:
                    log.info(
                        "%s stale signal on bar %s (conf %.2f) — skipped",
                        bot,
                        bar_ts.strftime("%H:%M"),
                        s.confidence,
                    )
                    continue
                sig = s
                sig_bar = i
                log.info(
                    "%s signal %s conf=%.2f (bar %s, gate %.2f)",
                    bot,
                    sig.side,
                    sig.confidence,
                    bar_ts.strftime("%H:%M"),
                    spec["confidence_min"],
                )
        if len(feats):
            self._last_seen_bar[bot] = feats.index[-1]
        if sig is None:
            return
        if spec.get("mode") == "shadow":
            log.info("[shadow] %s signal %s conf=%.2f (not traded)", bot, sig.side, sig.confidence)
            return
        if sig.confidence < spec["confidence_min"]:
            return
        status = session.get(BotStatus, bot)
        if status is not None and status.running is False:
            log.info("%s paused via dashboard — signal skipped", bot)
            return
        paused, why = risk_guard.is_paused(
            lambda k: get_state(session, k), bot, dt.datetime.now(dt.UTC).timestamp()
        )
        if paused:
            log.info("%s paused by loss-streak guard — %s", bot, why)
            self._bump_veto(session, bot, "cooldown")
            return
        max_pos = int(spec.get("max_positions", getattr(self.s, "max_positions_per_bot", 3)))
        n_open = len(session.execute(select(OpenPosition).where(OpenPosition.bot == bot)).scalars().all())
        if n_open >= max_pos:
            return
        total_open = len(session.execute(select(OpenPosition)).scalars().all())
        if total_open >= int(getattr(self.s, "max_total_positions", 8)):
            log.info("desk position cap hit (%d) — %s skipped", total_open, bot)
            return
        if self.risk.is_news_blackout():
            log.info("news blackout — %s signal skipped", bot)
            return
        equity, _ = self._equity_now(session, price)
        day_start = self._day_start_equity(session, equity)
        if self.risk.kill_switch(self.peak_equity, equity):
            self._trip_auto_kill(session, equity)
            return
        if self.risk.daily_loss_breached(day_start, equity):
            log.warning("daily loss limit hit — %s paused", bot)
            return
        open_notional = sum(
            p.qty * p.entry_price for p in session.execute(select(OpenPosition)).scalars()
        )
        if not self.risk.gross_exposure_ok(open_notional, equity):
            log.info(
                "gross exposure cap hit (open %.2f vs equity %.2f × 2.0) — %s skipped",
                open_notional,
                equity,
                bot,
            )
            return

        # ---- Prime gate: SINGLE LLM entry-point (merged quant+reviewer) ----
        # 0 LLM calls when a free local tool vetoes first; else one merged
        # quant+reviewer call. Gate contexts describe the bar that produced
        # the signal (sig_bar), not the newest bar. The TF-aware ML gate
        # below stays untouched as the last instance.
        quant_mult = 1.0
        sig_adj = sig
        gate_source = "legacy"
        if self.s.agents_enabled:
            try:
                feats_row = {
                    "vol_z": float(feats["vol_z"].iloc[sig_bar]),
                    "atr_pct": float(feats["atr_pct"].iloc[sig_bar]) * 100,
                    "trend_strength": float(feats["trend_strength"].iloc[sig_bar]),
                    "rsi": float(feats["rsi"].iloc[sig_bar]),
                    "rvol": (
                        float(feats["rvol"].iloc[sig_bar]) if "rvol" in feats.columns else 1.0
                    ),
                    "tf": spec.get("timeframe"),
                }
                prime_ctx = {
                    "price": price,
                    "symbol": SYMBOL,
                    "timeframe": spec.get("timeframe"),
                    "lessons": self.learning.context_block(bot=bot),
                }
                decision = await self.prime.decide_signal(bot, sig, feats_row, prime_ctx)
                gate_source = "prime_llm" if decision.llm_used else "prime_local"
                if decision.insight is not None:
                    try:
                        src = decision.insight.meta.get("source")
                    except (AttributeError, TypeError):
                        src = None
                    if src:
                        gate_source = str(src)
                    save_insight(self.session_factory, decision.insight)
                if not decision.approved:
                    log.info("%s signal REJECTED by prime: %s", bot, decision.veto_reason)
                    self._bump_veto(session, bot, "prime")
                    return
                sig_adj = decision.adjusted_signal(sig)
                quant_mult = decision.size_mult
            except Exception:
                log.exception("prime gate failed — proceeding with base size")

        # ---- ML champion gate: TF-aware, per-bot threshold, veto counters ----
        # A champion trained on 4h must NEVER gate 1m signals (distribution +
        # horizon + long-only mismatch). Bypass = log + counter, not silent.
        self._refresh_champion()
        bot_gate = spec.get("ml_gate_threshold", self.s.ml_gate_threshold)
        if self._champion is not None and bot_gate is not None:
            champ_tf = self._champion_tf
            bot_tf = spec.get("timeframe")
            if champ_tf is not None and champ_tf != bot_tf:
                log.info(
                    "ML gate bypass (%s): champ TF %s vs bot TF %s — incompatible, skipped",
                    bot,
                    champ_tf,
                    bot_tf,
                )
            elif sig.side == "short" and (champ_tf or "") == "4h":
                # 4h champion is long-only (train.py y_long); short gate is structural veto
                log.info("ML gate bypass (%s short): long-only champion cannot gate shorts", bot)
            else:
                from trading.ml.train import FEATURES

                try:
                    x = np.array(
                        [float(feats[c].iloc[sig_bar]) for c in FEATURES], dtype=float
                    ).reshape(1, -1)
                    p = float(self._champion.predict_proba(x)[0])
                    if p < bot_gate:
                        log.info("ML gate veto: %s p=%.3f < %.3f", bot, p, bot_gate)
                        self._bump_veto(session, bot, "ml_gate")
                        save_insight(
                            self.session_factory,
                            Insight(
                                agent="ml_gate",
                                title=f"ML gate veto ({bot})",
                                body=f"champion probability {p:.3f} below threshold "
                                f"{bot_gate:.2f} — entry skipped.",
                                severity="info",
                                tags=["ml", "veto", bot],
                                meta={"source": "champion", "p": round(p, 4)},
                            ),
                        )
                        return
                except Exception:
                    log.exception("ML gate failed — allowing entry")
        else:
            log.info(
                "ML gate bypass (%s): %s",
                bot,
                "no champion" if self._champion is None else "per-bot threshold None",
            )

        close = float(feats["close"].iloc[-1])
        atr_abs = float(feats["atr_pct"].iloc[-1]) * close
        if atr_abs <= 0:
            return
        stop_dist = sig_adj.stop_atr * atr_abs
        notional = self.risk.size_position(equity, sig_adj.confidence, stop_dist / close)
        # conviction sizing: per-bot multiplier (HFT demo = 3×) × quant multiplier,
        # hard-capped at 90 % of equity notional so demo aggression stays bounded
        notional = round(min(notional * spec.get("size_mult", 1.0) * quant_mult, equity * 0.9), 6)
        # dynamic leverage 2–25x by conviction: conf 0.45→lev_min, 0.9→lev_max.
        # Paper venue: leverage scales notional/equity (margin = notional/lev).
        lev_min = float(getattr(self.s, "leverage_min", 2.0))
        lev_max = float(getattr(self.s, "leverage_max", 25.0))
        bot_lev_cap = float(spec.get("leverage", lev_max))
        dyn_lev = lev_min + (min(max(sig_adj.confidence, 0.45), 0.9) - 0.45) / 0.45 * (min(lev_max, bot_lev_cap) - lev_min)
        dyn_lev = round(max(lev_min, min(min(lev_max, bot_lev_cap), dyn_lev)), 1)
        notional = round(min(notional * (dyn_lev / 5.0), equity * 2.0), 6)
        # volatility-scaled sizing (protective): shrink when ATR runs hot
        try:
            from trading.risk import vol_scaled_size
            _atr_dec = max(float(feats["atr_pct"].iloc[-1]), 1e-6)
            notional = vol_scaled_size(equity, notional, _atr_dec, 0.004)
        except Exception:
            log.exception("vol sizing failed — keeping base notional")
        # quality sizing: reward only high-confidence setups (convex 0.5x -> 1.25x)
        try:
            from trading.risk import quality_size_mult
            notional = round(min(notional * quality_size_mult(sig_adj.confidence), equity * 0.9), 6)
        except Exception:
            log.exception("quality sizing failed — keeping base notional")
        # cross-bot gross exposure cap: open notional + new <= 2.0 × equity
        if not self.risk.gross_exposure_ok(open_notional + notional, equity):
            log.info("gross exposure cap hit (+%.2f new) — %s skipped", notional, bot)
            return
        qty = notional / price
        from trading.costs import bar_slippage_bps
        # the entry fills on the signal candle's close — that candle's own
        # width prices the cost (cost curve v1); the feats frame IS the tape
        slip = bar_slippage_bps(
            float(feats["high"].iloc[-1]), float(feats["low"].iloc[-1]), close, self.s.slippage_bps
        ) / 10_000
        fill = price * (1 + slip) if sig_adj.side == "long" else price * (1 - slip)
        sl = fill - stop_dist if sig_adj.side == "long" else fill + stop_dist
        tp = (
            fill + stop_dist * sig_adj.tp_rr
            if sig_adj.side == "long"
            else fill - stop_dist * sig_adj.tp_rr
        )
        session.add(
            OpenPosition(
                bot=bot,
                symbol=SYMBOL,
                side=sig_adj.side,
                qty=qty,
                entry_price=fill,
                stop_loss=sl,
                take_profit=tp,
                confidence=sig_adj.confidence,
                gate_source=gate_source,
            )
        )
        session.commit()
        log.info(
            "%s OPEN %s qty=%.6f @%.2f conf=%.2f", bot, sig_adj.side, qty, fill, sig_adj.confidence
        )

    def _stale_feed(self, session) -> bool:
        """Newest 1m candle older than STALE_CANDLE_S => feed is stale."""
        row = session.execute(
            select(Candle.open_time)
            .where(Candle.symbol == SYMBOL, Candle.timeframe == "1m")
            .order_by(Candle.open_time.desc())
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            return True
        ts = row.replace(tzinfo=dt.UTC) if row.tzinfo is None else row
        return (dt.datetime.now(dt.UTC) - ts).total_seconds() > STALE_CANDLE_S

    async def _evaluate(self):
        session = self.session_factory()
        try:
            self._ensure_bot_rows(session)
            # kill-switch lifecycle: two independent latches OR together —
            # the manual __killswitch row (dashboard) and the automatic
            # drawdown trip, re-read from the kv store every tick so the
            # operator's reset_kill_state takes effect without a restart.
            # Nothing here CLEARS either latch on its own: un-killing is
            # deliberate or it is nothing.
            ks = killswitch_state(self.session_factory)
            self._auto_kill = bool(get_state(session, "kill_tripped", False))
            killed_now = ks["tripped"] or self._auto_kill
            if killed_now and not self.killed:
                log.error("kill-switch engaged (manual=%s auto=%s)", ks["tripped"], self._auto_kill)
            elif not killed_now and self.killed:
                log.info("kill-switch cleared — resuming")
            self.killed = killed_now
            stale = self._stale_feed(session)
            if stale:
                log.warning("stale feed: newest 1m candle older than %ds", STALE_CANDLE_S)
            for bot, spec in BOT_SPECS.items():
                # per-bot isolation: one DB/feed hiccup must not kill the
                # whole tick — other bots keep evaluating (118 dead ticks
                # during network flaps meant HFT never saw its signals)
                try:
                    rows_q = (
                        select(Candle)
                        .where(Candle.symbol == SYMBOL, Candle.timeframe == spec["timeframe"])
                        .order_by(Candle.open_time.desc())
                        .limit(1000)
                    )
                    candles = list(reversed(session.execute(rows_q).scalars().all()))
                    if len(candles) < 200:
                        continue
                    rows = [
                        {
                            "open_time": c.open_time,
                            "open": c.open,
                            "high": c.high,
                            "low": c.low,
                            "close": c.close,
                            "volume": c.volume,
                        }
                        for c in candles
                    ]
                    feats = build_features(candles_to_df(rows))
                    last = rows[-1]
                    self._last_close_seen = float(last["close"])

                    await self._maybe_close_positions(session, last)

                    status = session.get(BotStatus, bot)
                    status.last_heartbeat = dt.datetime.now(dt.UTC)
                    note = f"{len(rows)} bars | px {last['close']:.2f}"
                    if stale:
                        note = "stale feed | " + note
                    status.note = note
                    session.commit()

                    if not self.killed:
                        await self._maybe_open_position(session, bot, feats, last["close"])
                except Exception:
                    log.exception("evaluate %s failed — bot skipped this tick", bot)

            try:
                eq, _ = self._equity_now(session)
                self.peak_equity = max(self.peak_equity, eq)
                self._persist_peak(session)
                # the kill-switch is a PER-TICK rail, not a signal-time one:
                # an underwater open position must trip it even when no bot
                # is trying to enter — the equity above is marked (the last
                # close fallback in _equity_now), so this measures the same
                # quantity the kernel rails measure at bar close
                if not self._auto_kill and self.risk.kill_switch(self.peak_equity, eq):
                    self._trip_auto_kill(session, eq)
                    self.killed = True
                self._tick_count_since_point = getattr(self, "_tick_count_since_point", 0) + 1
                moved = (
                    self._last_equity_point is None
                    or abs(eq - self._last_equity_point) / max(self._last_equity_point, 1e-9)
                    > EQUITY_POINT_DELTA_PCT
                )
                if self._tick_count_since_point >= EQUITY_POINT_EVERY_TICKS or moved:
                    session.add(EquityPoint(bot="portfolio", equity=eq))
                    session.commit()
                    self._last_equity_point = eq
                    self._tick_count_since_point = 0
            except Exception:
                log.exception("equity point write failed")
                session.rollback()
        finally:
            session.close()

    # ------------------------------------------------------------------ agents
    async def _maybe_run_analyst(self):
        # No fixed cadence here: Prime throttles itself (regime-change only).
        if not self.s.agents_enabled:
            return
        session = self.session_factory()
        try:
            rows = (
                session.execute(
                    select(Candle)
                    .where(Candle.symbol == SYMBOL, Candle.timeframe == "4h")
                    .order_by(Candle.open_time.desc())
                    .limit(400)
                )
                .scalars()
                .all()
            )
            if len(rows) < 100:
                return
            feats = build_features(
                candles_to_df(
                    [
                        {
                            "open_time": c.open_time,
                            "open": c.open,
                            "high": c.high,
                            "low": c.low,
                            "close": c.close,
                            "volume": c.volume,
                        }
                        for c in reversed(rows)
                    ]
                )
            )
            last = feats.iloc[-1]
            equity, _ = self._equity_now(session, float(last["close"]))
            ctx = {
                "symbol": SYMBOL,
                "price": round(float(last["close"]), 2),
                "trend_strength": round(float(last["trend_strength"]), 3),
                "rsi": round(float(last["rsi"]), 1),
                "atr_pct": round(float(last["atr_pct"]) * 100, 3),
                "rvol": round(float(last["rvol"]) * 100, 3),
                "regime": round(float(last["regime"]), 4),
                "open_positions": len(session.execute(select(OpenPosition)).scalars().all()),
                "equity": equity,
                "lessons": self.learning.context_block(),
            }
        finally:
            session.close()
        try:
            insight = await self.prime.maybe_analyst(ctx)
            if insight is None:
                return  # throttled (no regime change) or LLM unavailable
            save_insight(self.session_factory, insight)
            log.info("analyst: %s (%s)", insight.title, insight.severity)
        except Exception:
            log.exception("analyst agent failed")

    async def _maybe_forecast(self):
        """Per-bot directional forecast (chart overlay) with a cadence cap."""
        if not self.s.agents_enabled:
            return
        now = asyncio.get_event_loop().time()
        session = self.session_factory()
        try:
            for bot, spec in BOT_SPECS.items():
                if bot not in self.strategies:
                    continue
                if now - self._last_forecast.get(bot, float("-inf")) < FORECAST_INTERVAL_S:
                    continue
                rows = (
                    session.execute(
                        select(Candle)
                        .where(Candle.symbol == SYMBOL, Candle.timeframe == spec["timeframe"])
                        .order_by(Candle.open_time.desc())
                        .limit(600)
                    )
                    .scalars()
                    .all()
                )
                if len(rows) < 200:
                    continue
                feats = build_features(
                    candles_to_df(
                        [
                            {
                                "open_time": c.open_time,
                                "open": c.open,
                                "high": c.high,
                                "low": c.low,
                                "close": c.close,
                                "volume": c.volume,
                            }
                            for c in reversed(rows)
                        ]
                    )
                )
                sig = self.strategies[spec["strategy"]].signal(len(feats) - 1, feats)
                if spec.get("timeframe") == "1m":
                    # HFT: always heuristic — skip the LLM forecast call
                    if self._heuristic_forecast(bot, spec, feats, sig):
                        self._last_forecast[bot] = now
                        log.info("forecast %s: heuristic only (1m)", bot)
                    continue
                result = await self.forecaster.run(
                    bot=bot,
                    symbol=SYMBOL,
                    timeframe=spec["timeframe"],
                    feats=feats,
                    lessons=self.learning.context_block(bot=bot),
                    signal_confidence=sig.confidence if sig else None,
                )
                if result:
                    self._last_forecast[bot] = now
                    log.info(
                        "forecast %s: %s conf=%.2f (%s)",
                        bot,
                        result["direction"],
                        result["confidence"],
                        result["source"],
                    )
        finally:
            session.close()

    def _heuristic_forecast(self, bot: str, spec: dict, feats, sig) -> bool:
        """Heuristic-only forecast for 1m bots (HFT): zero LLM calls.

        Reuses Forecaster's pure heuristic helpers and persists the same
        AgentPrediction row shape with source="heuristic".
        """
        from trading.agents.forecaster import Forecaster

        try:
            last = feats.iloc[-1]
            ctx = {
                "price": round(float(last["close"]), 2),
                "trend_strength": round(float(last["trend_strength"]), 3),
                "rsi": round(float(last["rsi"]), 1),
                "atr_pct": round(float(last["atr_pct"]) * 100, 3),
                "rvol": round(float(last["rvol"]), 3),
                "regime": round(float(last["regime"]), 4),
            }
            direction = Forecaster._heuristic(ctx)
            conf = Forecaster._heuristic_conf(ctx, direction)
            move = Forecaster._heuristic_move(ctx, direction)
            session = self.session_factory()
            try:
                session.add(
                    AgentPrediction(
                        bot=bot,
                        symbol=SYMBOL,
                        timeframe=spec.get("timeframe", "1m"),
                        direction=direction,
                        confidence=round(min(0.99, max(0.01, conf)), 3),
                        expected_move_pct=round(max(-50.0, min(50.0, move)), 3),
                        horizon_bars=2,
                        price_at_ts=ctx["price"],
                        reasoning=(
                            "[heuristic] trend/vol read "
                            f"| ts={ctx['trend_strength']} rsi={ctx['rsi']} "
                            f"atr%={ctx['atr_pct']}"
                        ),
                        signal_confidence=round(float(sig.confidence) if sig else 0.0, 3),
                        source="heuristic",
                    )
                )
                session.commit()
            finally:
                session.close()
            return True
        except Exception:
            log.exception("heuristic forecast failed (%s)", bot)
            return False

    async def _maybe_auto_retrain(self):
        """Weekly cadence: retrain ML gate when champion is stale."""
        now = asyncio.get_event_loop().time()
        if now - self._last_retrain_check < 3600:  # check hourly at most
            return
        self._last_retrain_check = now

        session = self.session_factory()
        try:
            champ = (
                session.execute(
                    select(ModelVersion)
                    .where(ModelVersion.is_champion.is_(True))
                    .order_by(ModelVersion.trained_at.desc())
                    .limit(1)
                )
                .scalars()
                .first()
            )
            stale = (
                champ is None
                or (dt.datetime.now(dt.UTC) - champ.trained_at.replace(tzinfo=dt.UTC)).days
                >= RETRAIN_INTERVAL_DAYS
            )
        finally:
            session.close()
        if not stale:
            return
        log.info("champion model stale — running scheduled retrain")
        try:
            from trading.ml.pipeline import retrain_all_timeframes

            await retrain_all_timeframes(self.session_factory, self.agents["supervisor"])
            post = getattr(self.prime, "post_retrain", None)
            if callable(post):
                try:
                    await post()
                except Exception:
                    log.exception("prime post_retrain hook failed")
        except Exception:
            log.exception("scheduled retrain failed")

    # ------------------------------------------------------------------ prune
    @staticmethod
    def _id_cutoff(session, model, keep: int):
        """id of the `keep`-th newest row; rows below it are deletable."""
        return (
            session.execute(select(model.id).order_by(model.id.desc()).offset(keep).limit(1))
            .scalars()
            .first()
        )

    def _prune(self):
        """Hourly retention: capped EquityPoints/insights/predictions, 90d of 1m candles."""
        session = self.session_factory()
        try:
            for model, keep in (
                (EquityPoint, PRUNE_KEEP_EQUITY),
                (AgentInsight, PRUNE_KEEP_INSIGHTS),
                (AgentPrediction, PRUNE_KEEP_PREDICTIONS),
            ):
                cutoff = self._id_cutoff(session, model, keep)
                if cutoff is not None:
                    session.execute(delete(model).where(model.id < cutoff))
            candle_cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=PRUNE_CANDLE_1M_DAYS)
            session.execute(
                delete(Candle).where(
                    Candle.symbol == SYMBOL,
                    Candle.timeframe == "1m",
                    Candle.open_time < candle_cutoff,
                )
            )
            session.commit()
            log.info(
                "prune done (caps: equity=%d insights=%d preds=%d)",
                PRUNE_KEEP_EQUITY,
                PRUNE_KEEP_INSIGHTS,
                PRUNE_KEEP_PREDICTIONS,
            )
        except Exception:
            session.rollback()
            log.exception("prune failed")
        finally:
            session.close()

    # ------------------------------------------------------------------- loop
    async def _warmup_incremental(self):
        """Fetch only candles missing since last DB entry (CI-friendly).

        Guarantees at least BACKFILL_MIN_DAYS (4 weeks) of history for every
        timeframe so both SCALP variants and the HFT bot always have enough
        context for forecasting.
        """
        now = dt.datetime.now(dt.UTC)
        for tf, default_days in (
            ("1m", BACKFILL_MIN_DAYS),
            ("5m", BACKFILL_MIN_DAYS),
            ("15m", BACKFILL_MIN_DAYS),
            ("1h", 60),
            ("4h", 120),
        ):
            session = self.session_factory()
            try:
                row = session.execute(
                    select(Candle.open_time)
                    .where(Candle.symbol == SYMBOL, Candle.timeframe == tf)
                    .order_by(Candle.open_time.desc())
                    .limit(1)
                ).scalar_one_or_none()
            finally:
                session.close()
            if row is None:
                start = now - dt.timedelta(days=default_days)
            else:
                start = max(
                    row.replace(tzinfo=dt.UTC) - dt.timedelta(minutes=5),
                    now - dt.timedelta(days=default_days),
                )
            rows, _venue = await fetch_candles_any(SYMBOL, tf, start=start, end=now)
            # the desk trades perps — warmup fetches the perp tape and rows
            # land under the venue that actually priced them (analysis F-3)
            _itype = "perp" if _venue in ("binance-usdm", "hyperliquid") else "spot"
            session = self.session_factory()
            try:
                n = upsert_candles(session, SYMBOL, tf, rows, venue=_venue, instrument_type=_itype)
            finally:
                session.close()
            log.info("warmup %s +%d candles", tf, n)

    async def cycle_once(self):
        """One full engine pass — designed for GitHub Actions cron."""
        log.info("engine cycle starting — symbol %s", SYMBOL)
        await self._warmup_incremental()
        try:
            await self._evaluate()
            await self._maybe_run_analyst()
            await self._maybe_forecast()
            await self._maybe_auto_retrain()
        except Exception:
            log.exception("cycle tick failed")

    # --------------------------------------------------------- task supervision
    def _spawn_tasks(self) -> None:
        if "stream" not in self._tasks or self._tasks["stream"].done():
            self._tasks["stream"] = asyncio.create_task(self._stream_writer())
        if "l2" not in self._tasks or self._tasks["l2"].done():
            self._tasks["l2"] = asyncio.create_task(self._l2_shadow_loop())

    def _supervise_tasks(self) -> None:
        for name, task in list(self._tasks.items()):
            if task.done():
                exc = task.exception()
                log.error("task %s died (%s) — restarting", name, exc or "cancelled")
                del self._tasks[name]
        self._spawn_tasks()

    async def _shutdown(self) -> None:
        self._stop = True
        for t in self._tasks.values():
            t.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()

    async def run(self):
        log.info("paper engine starting — symbol %s", SYMBOL)
        if not _acquire_worker_lock():
            raise SystemExit(1)

        loop = asyncio.get_event_loop()
        for sig in (os_signal.SIGINT, os_signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, self._request_stop)

        await self._warmup_incremental()
        self._spawn_tasks()
        try:
            while not self._stop:
                try:
                    # 1m candles stream live; higher TFs need periodic re-fetch
                    self._tick_count += 1
                    if self._tick_count % 30 == 1:  # ~every 5 min
                        await self._warmup_incremental()
                    self._supervise_tasks()
                    await self._evaluate()
                    self._maybe_rebuild_agents()
                    await self._maybe_run_analyst()
                    await self._maybe_forecast()
                    await self._maybe_auto_retrain()
                    now = loop.time()
                    if now - self._last_prune >= PRUNE_INTERVAL_S:
                        self._last_prune = now
                        self._prune()
                except Exception:  # keep the worker alive no matter what
                    log.exception("worker tick failed")
                await asyncio.sleep(10)
        finally:
            log.info("paper engine stopping — flushing and exiting")
            await self._shutdown()

    def _request_stop(self) -> None:
        log.info("shutdown signal received — finishing current tick")
        self._stop = True

    async def _stream_writer(self):
        """Persist live 1m candles; 4h aggregates are refreshed by periodic backfill."""
        try:
            async for candle in stream_klines(SYMBOL, "1m", market="perp"):
                session = self.session_factory()
                try:
                    upsert_candles(session, SYMBOL, "1m", [candle], venue="binance-usdm", instrument_type="perp")
                finally:
                    session.close()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("stream writer died — supervisor will restart it")

    async def _l2_shadow_loop(self):
        """Hyperliquid L2 order-flow shadow signals for the HFT-BOT.

        Logs OFI-pressure entries/exits as insights; never trades until the
        fill model is validated (F5).
        """
        try:
            from trading.feeds.hyperliquid import OrderFlowTracker, book_features, stream_book
        except Exception:
            log.exception("hyperliquid feed unavailable — L2 shadow disabled")
            return
        try:
            tracker = OrderFlowTracker(window=60)
            last_signal = 0.0
            async for book in stream_book("BTC"):
                feats = book_features(book)
                if not feats:
                    continue
                state = tracker.update(feats)
                if state is None:
                    continue
                now = asyncio.get_event_loop().time()
                if abs(state["pressure"]) > 0.35 and now - last_signal > 600:
                    last_signal = now
                    side = "long" if state["pressure"] > 0 else "short"
                    title = f"L2 pressure {side} ({state['pressure']:+.2f})"
                    body = (
                        f"[hft-shadow] order-flow imbalance {state['ofi_mean']:+.3f}, "
                        f"micro-skew {state['micro_skew_mean_bps']:+.1f} bps over 60 snapshots "
                        f"(spread {feats['spread_bps']:.1f} bps). Signal logged, NOT traded — "
                        "awaiting fill-model validation."
                    )
                    save_insight(
                        self.session_factory,
                        Insight(
                            agent="reviewer",
                            title=title,
                            body=body,
                            severity="info",
                            tags=["hft", "shadow", side],
                            meta={"source": "l2"},
                        ),
                    )
                    log.info("%s", title)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("l2 shadow loop died — supervisor will restart it")
