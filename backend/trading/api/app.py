"""FastAPI gateway — REST + WebSocket for the dashboard."""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select

from trading.backtest.engine import BTConfig, run_backtest, walk_forward
from trading.config import get_settings
from trading.features import build_features, candles_to_df
from trading.models import (
    AgentPrediction,
    BacktestRun,
    BotStatus,
    Candle,
    EquityPoint,
    ModelVersion,
    OpenPosition,
    Trade,
    get_state,
    make_session_factory,
)
from trading import risk_guard
from trading.risk import RiskManager, killswitch_state, set_killswitch
from trading.storage import load_candles_df

log = logging.getLogger(__name__)

app = FastAPI(title="ScalpFX API", version="0.1.0")

from trading.api.audit import router as audit_router
from trading.api.perf import router as perf_router

app.include_router(audit_router)
app.include_router(perf_router)

_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    *[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    # LAN origins (dashboard served from the Pi itself) — IP may change, so regex
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?$",
    allow_methods=["*"],
    allow_headers=["*"],
)

session_factory = make_session_factory()


def _overview_snapshot() -> dict:
    session = session_factory()
    try:
        trades = (
            session.execute(select(Trade).order_by(Trade.exit_time.desc()).limit(500))
            .scalars()
            .all()
        )
        trades = list(reversed(trades))
        equity_pts = (
            session.execute(select(EquityPoint).order_by(EquityPoint.ts.desc()).limit(500))
            .scalars()
            .all()
        )
        eq_now = (
            equity_pts[0].equity
            if equity_pts
            else get_settings().paper_equity_start + sum(t.pnl for t in trades)
        )
        start = get_settings().paper_equity_start
        # DB may return naive (SQLite) or aware (Postgres) UTC datetimes —
        # normalize everything to naive UTC before comparing
        today = dt.datetime.now(dt.UTC).replace(
            tzinfo=None, hour=0, minute=0, second=0, microsecond=0
        )

        def naive_utc(x):
            return x.replace(tzinfo=None) if x and x.tzinfo else x

        pnl_today = sum(
            t.pnl for t in trades if naive_utc(t.exit_time) and naive_utc(t.exit_time) >= today
        )
        wins = [t for t in trades if t.pnl > 0]
        open_pos = session.execute(select(OpenPosition)).scalars().all()
        bots = {
            b.name: {
                "running": b.running,
                "mode": b.mode,
                "note": b.note,
                "heartbeat": str(b.last_heartbeat) if b.last_heartbeat else None,
            }
            for b in session.execute(select(BotStatus)).scalars()
            if not b.name.startswith("__")
        }
        peak = max([p.equity for p in equity_pts], default=start)
        return {
            "equity": round(eq_now, 2),
            "equity_start": start,
            "total_pnl": round(eq_now - start, 2),
            "pnl_today": round(pnl_today, 2),
            "trades_n": len(trades),
            "win_rate": round(len(wins) / len(trades), 4) if trades else 0.0,
            "max_dd_pct": round((eq_now - peak) / peak * 100, 3) if peak > 0 else 0.0,
            "equity_curve": [
                {"ts": str(p.ts), "equity": p.equity}
                for p in sorted(equity_pts, key=lambda p: p.ts)
            ],
            "open_positions": [
                {
                    "bot": p.bot,
                    "symbol": p.symbol,
                    "side": p.side,
                    "qty": p.qty,
                    "notional_usd": round(p.qty * p.entry_price, 2),
                    "margin_usd": round(p.qty * p.entry_price / get_settings().default_leverage, 2),
                    "leverage": get_settings().default_leverage,
                    "entry_price": p.entry_price,
                    "stop_loss": p.stop_loss,
                    "take_profit": p.take_profit,
                    "risk_usd": round(abs(p.entry_price - p.stop_loss) * p.qty, 2),
                    "reward_usd": round(abs(p.take_profit - p.entry_price) * p.qty, 2),
                    "confidence": p.confidence,
                    "opened_at": str(p.opened_at),
                }
                for p in open_pos
            ],
            "bots": bots,
        }
    finally:
        session.close()


class BacktestRequest(BaseModel):
    symbol: str = "BTCUSDT"
    timeframe: str = "4h"
    bot: str = "scalp"
    folds: int = 0  # >0 => walk-forward


@app.post("/api/backtest")
async def run_bt(req: BacktestRequest):
    from trading.bots import HFTMomentum, ScalpTrend

    strat_cls = {"hft": HFTMomentum, "scalp": ScalpTrend}.get(req.bot)
    if strat_cls is None:
        raise HTTPException(400, f"unknown bot {req.bot}")
    session = session_factory()
    try:
        df = load_candles_df(session, req.symbol.upper(), req.timeframe)
    finally:
        session.close()
    if len(df) < 600:
        raise HTTPException(409, f"not enough data ({len(df)} bars) — run `make backfill` first")
    feats = build_features(candles_to_df(candles_to_rows(df)))

    cfg = BTConfig()
    if req.folds and req.folds > 1:
        folds = walk_forward(feats, strat_cls, n_folds=req.folds, cfg=cfg, timeframe=req.timeframe)
        result = None
        metrics = aggregate_folds(folds)
        payload = {"mode": "walk_forward", "folds": folds, "metrics": metrics}
    else:
        result = run_backtest(feats, strat_cls(), cfg, req.timeframe)
        payload = {"mode": "single", "metrics": result.metrics}

    session = session_factory()
    try:
        m = payload["metrics"]
        session.add(
            BacktestRun(
                bot=req.bot,
                symbol=req.symbol.upper(),
                timeframe=req.timeframe,
                strategy=strat_cls().name,
                trades_n=m.get("trades_n", 0),
                win_rate=m.get("win_rate", 0),
                profit_factor=(m["profit_factor"] if m["profit_factor"] != float("inf") else 999.0),
                sharpe=m.get("sharpe", 0),
                max_dd_pct=m.get("max_dd_pct", 0),
                total_return_pct=m.get("total_return_pct", 0),
            )
        )
        session.commit()
    finally:
        session.close()

    if result is not None:
        payload["trades"] = [
            {k: (str(v) if hasattr(v, "isoformat") else v) for k, v in t.items()}
            for t in result.trades[-200:]
        ]
    return payload


def candles_to_rows(df):
    return [
        {
            "open_time": idx,
            "open": r["open"],
            "high": r["high"],
            "low": r["low"],
            "close": r["close"],
            "volume": r["volume"],
        }
        for idx, r in df.iterrows()
    ]


def aggregate_folds(folds: list[dict]) -> dict:
    import statistics as st

    valid = [f for f in folds if f.get("trades_n")]
    if not valid:
        return {}
    wr = st.mean(f["win_rate"] for f in valid)
    pf = st.mean(min(f["profit_factor"], 10.0) for f in valid)
    return {
        "trades_n": sum(f["trades_n"] for f in valid),
        "win_rate": round(wr, 4),
        "profit_factor": round(pf, 3),
        "sharpe": round(st.mean(f["sharpe"] for f in valid), 3),
        "max_dd_pct": min(f["max_dd_pct"] for f in valid),
        "total_return_pct": sum(f["total_return_pct"] for f in valid),
    }


@app.get("/api/backtest/history")
async def backtest_history(limit: int = 30):
    session = session_factory()
    try:
        rows = (
            session.execute(
                select(BacktestRun).order_by(BacktestRun.created_at.desc()).limit(limit)
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": r.id,
                "created_at": str(r.created_at),
                "bot": r.bot,
                "symbol": r.symbol,
                "timeframe": r.timeframe,
                "strategy": r.strategy,
                "trades_n": r.trades_n,
                "win_rate": r.win_rate,
                "profit_factor": r.profit_factor,
                "sharpe": r.sharpe,
                "max_dd_pct": r.max_dd_pct,
                "total_return_pct": r.total_return_pct,
            }
            for r in rows
        ]
    finally:
        session.close()


@app.get("/api/insights")
async def insights(limit: int = 50):
    from trading.agents.base import load_insights

    return await asyncio.to_thread(load_insights, session_factory, limit=limit)


@app.get("/api/agents")
async def agents_status():
    from trading.agents import agent_status

    return await asyncio.to_thread(agent_status)


@app.get("/api/predictions")
async def predictions(symbol: str = "BTCUSDT", limit: int = 120):
    """Per-bot market forecasts — chart markers + 'how agents think' panel."""
    return await asyncio.to_thread(_predictions_snapshot, symbol, limit)


def _predictions_snapshot(symbol: str, limit: int) -> list[dict]:
    session = session_factory()
    try:
        rows = (
            session.execute(
                select(AgentPrediction)
                .where(AgentPrediction.symbol == symbol.upper())
                .order_by(AgentPrediction.ts.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": p.id,
                "ts": str(p.ts),
                "ts_ms": int(p.ts.timestamp() * 1000) if p.ts else None,
                "bot": p.bot,
                "symbol": p.symbol,
                "timeframe": p.timeframe,
                "direction": p.direction,
                "confidence": p.confidence,
                "expected_move_pct": p.expected_move_pct,
                "horizon_bars": p.horizon_bars,
                "price_at_ts": p.price_at_ts,
                "reasoning": p.reasoning,
                "signal_confidence": p.signal_confidence,
                "source": p.source,
            }
            for p in rows
        ]
    finally:
        session.close()


@app.post("/api/agents/tick")
async def agents_tick(authorization: str | None = Header(default=None)):
    """One analyst cycle on demand — designed for GitHub Actions cron.

    Optional bearer auth via TRADING_ENGINE_TOKEN when set.
    """
    token = get_settings().engine_token
    if token and authorization != f"Bearer {token}":
        raise HTTPException(401, "bad engine token")

    from trading.agents import build_agents
    from trading.agents.base import save_insight

    session = session_factory()
    try:
        rows = (
            session.execute(
                select(Candle)
                .where(Candle.symbol == "BTCUSDT", Candle.timeframe == "4h")
                .order_by(Candle.open_time.desc())
                .limit(400)
            )
            .scalars()
            .all()
        )
    finally:
        session.close()
    if len(rows) < 100:
        raise HTTPException(409, "not enough candles for agent context")

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
    session = session_factory()
    try:
        realized = float(sum(t.pnl for t in session.execute(select(Trade)).scalars()))
        last_px = float(last["close"])
        unrealized = 0.0
        for p in session.execute(select(OpenPosition)).scalars():
            sign = 1 if p.side == "long" else -1
            unrealized += (last_px - p.entry_price) * p.qty * sign
        equity = get_settings().paper_equity_start + realized + unrealized
    finally:
        session.close()
    ctx = {
        "symbol": "BTCUSDT",
        "price": round(float(last["close"]), 2),
        "trend_strength": round(float(last["trend_strength"]), 3),
        "rsi": round(float(last["rsi"]), 1),
        "atr_pct": round(float(last["atr_pct"]) * 100, 3),
        "rvol": round(float(last["rvol"]) * 100, 3),
        "regime": round(float(last["regime"]), 4),
        "equity": round(equity, 2),
    }
    insight = await build_agents()["analyst"].run(ctx)
    save_insight(session_factory, insight)
    return {
        "agent": insight.agent,
        "title": insight.title,
        "severity": insight.severity,
        "source": insight.meta.get("source"),
    }


@app.get("/api/models")
async def models():
    return await asyncio.to_thread(_models_snapshot)


def _models_snapshot() -> list[dict]:
    session = session_factory()
    try:
        rows = (
            session.execute(select(ModelVersion).order_by(ModelVersion.version.desc()).limit(30))
            .scalars()
            .all()
        )
        return [
            {
                "id": m.id,
                "name": m.name,
                "version": m.version,
                "trained_at": str(m.trained_at),
                "train_window_days": m.train_window_days,
                "oos_accuracy": m.oos_accuracy,
                "oos_precision_long": m.oos_precision_long,
                "is_champion": m.is_champion,
                "notes": m.notes,
            }
            for m in rows
        ]
    finally:
        session.close()


@app.get("/api/risk")
async def risk_status():
    s = get_settings()
    snap = await asyncio.to_thread(_overview_snapshot)
    eq = snap["equity"]
    start = s.paper_equity_start
    ks = await asyncio.to_thread(killswitch_state, session_factory)
    day_start = start + snap["pnl_today"]
    open_pos = snap["open_positions"]
    last_px = float(open_pos[0]["entry_price"]) if open_pos else None
    session = session_factory()
    try:
        row = (
            session.execute(
                select(Candle.close)
                .where(Candle.symbol == "BTCUSDT", Candle.timeframe == "1m")
                .order_by(Candle.open_time.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if row is not None:
            last_px = float(row)
        realized = float(sum(t.pnl for t in session.execute(select(Trade)).scalars()))
    finally:
        session.close()
    unrealized = 0.0
    if last_px is not None:
        for p in open_pos:
            sign = 1 if p["side"] == "long" else -1
            unrealized += (last_px - p["entry_price"]) * p["qty"] * sign
    daily_pnl_pct = (eq - day_start) / day_start * 100 if day_start else 0.0
    return {
        "equity": eq,
        "day_start_equity": round(day_start, 2),
        "realized_pnl": round(realized, 2),
        "unrealized_pnl": round(unrealized, 2),
        "daily_loss_limit_pct": -s.risk_max_daily_loss_pct * 100,
        "daily_pnl_pct": round(daily_pnl_pct, 3),
        "killswitch_dd_pct": -s.risk_killswitch_dd_pct * 100,
        "current_dd_pct": snap["max_dd_pct"],
        "max_exposure_pct": s.risk_max_exposure_pct * 100,
        "open_notional_usd": round(sum(p["qty"] * p["entry_price"] for p in open_pos), 2),
        "kelly_cap_fraction": s.kelly_fraction_cap,
        "news_blackout": RiskManager.is_news_blackout(),
        "manual_killswitch": ks,
    }


class KillSwitchRequest(BaseModel):
    tripped: bool
    note: str = ""


@app.post("/api/risk/killswitch")
async def killswitch(req: KillSwitchRequest, authorization: str | None = Header(default=None)):
    _require_engine_token(authorization)
    return await asyncio.to_thread(set_killswitch, session_factory, req.tripped, req.note)


# ------------------------------------------------------------------ REST


def _stale_feed(session) -> bool:
    import datetime as _dt

    row = (
        session.execute(
            select(Candle.open_time)
            .where(Candle.symbol == "BTCUSDT", Candle.timeframe == "1m")
            .order_by(Candle.open_time.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if row is None:
        return True
    ts = row.replace(tzinfo=_dt.UTC) if row.tzinfo is None else row
    return (_dt.datetime.now(_dt.UTC) - ts).total_seconds() > 300


def _health_snapshot() -> dict:
    from trading.agents.openrouter import OpenRouterClient

    session = session_factory()
    try:
        stale = _stale_feed(session)
        ks = killswitch_state(session_factory)
        budget = OpenRouterClient().budget.snapshot()
    finally:
        session.close()
    return {
        "status": "ok",
        "time": dt.datetime.now(dt.UTC).isoformat(),
        "stale_feed": stale,
        "killed": ks["tripped"],
        "budget_day_used": budget.get("used", 0),
    }


@app.get("/api/health")
async def health():
    return await asyncio.to_thread(_health_snapshot)


@app.get("/api/overview")
async def overview():
    return await asyncio.to_thread(_overview_snapshot)


@app.get("/api/trades")
async def trades(limit: int = 500):
    return await asyncio.to_thread(_trades_snapshot, limit)


def _trades_snapshot(limit: int) -> list[dict]:
    s = get_settings()
    session = session_factory()
    try:
        rows = (
            session.execute(select(Trade).order_by(Trade.exit_time.desc()).limit(limit))
            .scalars()
            .all()
        )
        return [
            {
                "id": t.id,
                "bot": t.bot,
                "symbol": t.symbol,
                "side": t.side,
                "qty": t.qty,
                "notional_usd": round(t.qty * t.entry_price, 2),
                "margin_usd": round(t.qty * t.entry_price / s.default_leverage, 2),
                "leverage": s.default_leverage,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "entry_time": str(t.entry_time),
                "exit_time": str(t.exit_time),
                "pnl": round(t.pnl, 4),
                "pnl_pct": round(t.pnl_pct * 100, 4),
                "confidence": t.confidence,
            }
            for t in rows
        ]
    finally:
        session.close()


@app.get("/api/chart/{symbol}/{timeframe}/annotations")
async def chart_annotations(symbol: str, timeframe: str = "4h"):
    """Price lines (open positions) + markers (closed trades) for the chart."""
    symbol = symbol.upper()
    s = get_settings()
    session = session_factory()
    try:
        positions = (
            session.execute(select(OpenPosition).where(OpenPosition.symbol == symbol))
            .scalars()
            .all()
        )
        closed = (
            session.execute(
                select(Trade)
                .where(Trade.symbol == symbol)
                .order_by(Trade.exit_time.desc())
                .limit(60)
            )
            .scalars()
            .all()
        )
    finally:
        session.close()

    lines = [
        {
            "kind": p.side,  # long | short
            "bot": p.bot,
            "entry": p.entry_price,
            "stop": p.stop_loss,
            "take": p.take_profit,
            "qty": p.qty,
            "margin_usd": round(p.qty * p.entry_price / s.default_leverage, 2),
            "confidence": p.confidence,
            "opened_at": str(p.opened_at),
        }
        for p in positions
    ]
    markers = []
    for t in closed:
        ts_ms = int(t.exit_time.timestamp() * 1000) if t.exit_time else None
        if ts_ms:
            markers.append(
                {
                    "time": ts_ms,
                    "position": "aboveBar" if t.pnl < 0 else "belowBar",
                    "color": "#f87171" if t.pnl < 0 else "#34d399",
                    "shape": "square",
                    "text": f"{t.bot} {'+' if t.pnl >= 0 else ''}{t.pnl:.1f}",
                }
            )
    return {"price_lines": lines, "markers": list(reversed(markers))}


@app.get("/api/analytics/{symbol}/{timeframe}")
async def analytics(symbol: str, timeframe: str = "4h", limit: int = 400):
    from trading.analytics import key_levels

    session = session_factory()
    try:
        df = load_candles_df(session, symbol.upper(), timeframe)
    finally:
        session.close()
    if len(df) < 120:
        raise HTTPException(409, f"not enough data ({len(df)} bars)")
    df = df.tail(limit)
    rows = candles_to_rows(df)
    feats = build_features(candles_to_df(rows))
    levels = key_levels(df.reset_index(names="open_time"))
    last = feats.iloc[-1]
    levels["context"] = {
        "price": round(float(last["close"]), 2),
        "trend_strength": round(float(last["trend_strength"]), 3),
        "rsi": round(float(last["rsi"]), 1),
        "atr_pct": round(float(last["atr_pct"]) * 100, 3),
        "regime": round(float(last["regime"]), 4),
    }
    return levels


@app.get("/api/intel/{symbol}")
async def intel(symbol: str = "BTCUSDT"):
    from trading.feeds.binance_futures import full_intel

    try:
        return await full_intel(symbol)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"intel feed failed: {exc}")


# ------------------------------------------------------------------ live


@app.get("/api/live/status")
async def live_status():
    """Hyperliquid live-trading status: config, gates, balance + positions."""
    from trading.venues.hyperliquid_live import get_live

    live = get_live()
    out = live.status()
    if live.configured:
        try:
            out["account_state"] = live.account_state()
        except Exception as exc:  # noqa: BLE001
            out["account_error"] = str(exc)[:200]
    return out


@app.get("/api/wallet/{address}")
async def wallet_state(address: str):
    """Read-only Hyperliquid state for ANY address (positions are on-chain)."""
    if not address.startswith("0x") or len(address) != 42:
        raise HTTPException(400, "expected 0x… address")
    from hyperliquid.info import Info
    from hyperliquid.utils import constants

    try:
        info = Info(constants.MAINNET_API_URL, skip_ws=True)
        state = info.user_state(address)
        margin = state.get("marginSummary", {})
        positions = []
        for p in state.get("assetPositions", []):
            pos = p.get("position", {})
            try:
                positions.append(
                    {
                        "coin": pos.get("coin"),
                        "szi": float(pos.get("szi", 0)),
                        "entry_px": float(pos.get("entryPx") or 0),
                        "position_value_usd": float(pos.get("positionValue", 0)),
                        "unrealized_pnl": float(pos.get("unrealizedPnl", 0)),
                    }
                )
            except (TypeError, ValueError):
                continue
        return {
            "address": address,
            "account_value_usd": float(margin.get("accountValue", 0)),
            "total_unrealized_pnl": float(margin.get("totalUnrealizedPnl", 0)),
            "withdrawable": float(state.get("withdrawable", 0)),
            "positions": positions,
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"hyperliquid query failed: {exc}")


class LiveOrderRequest(BaseModel):
    coin: str = "BTC"
    side: str = "buy"  # buy | sell
    notional_usd: float = 10.0


def _require_engine_token(authorization: str | None) -> None:
    token = get_settings().engine_token
    if token and authorization != f"Bearer {token}":
        raise HTTPException(401, "engine token required for live actions")


def _last_price(symbol: str = "BTCUSDT") -> float:
    session = session_factory()
    try:
        df = load_candles_df(session, symbol, "1m")
    finally:
        session.close()
    if df.empty:
        raise HTTPException(409, "no candles for pricing")
    return float(df["close"].iloc[-1])


@app.post("/api/live/order")
async def live_order(req: LiveOrderRequest, authorization: str | None = Header(default=None)):
    """Manual live order — hard-gated by env config + per-order/exposure caps."""
    _require_engine_token(authorization)
    from trading.venues.hyperliquid_live import get_live

    px = _last_price(f"{req.coin.upper()}USDT")
    try:
        return get_live().market_order(req.coin, req.side, req.notional_usd, px)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)[:250])


@app.post("/api/live/close/{coin}")
async def live_close(coin: str, authorization: str | None = Header(default=None)):
    _require_engine_token(authorization)
    from trading.venues.hyperliquid_live import get_live

    try:
        return get_live().close_position(coin.upper())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)[:250])


class MonteCarloRequest(BaseModel):
    bot: str = ""  # empty = all bots
    n_sims: int = 500
    horizon: int = 100
    risk_per_trade_pct: float = 1.0


@app.post("/api/montecarlo")
async def montecarlo(req: MonteCarloRequest):
    from trading.backtest.monte_carlo import monte_carlo_trades, summarize_edge

    session = session_factory()
    try:
        q = select(Trade).order_by(Trade.exit_time.desc()).limit(400)
        rows = session.execute(q).scalars().all()
    finally:
        session.close()
    rets = [t.pnl_pct * 100 for t in rows if req.bot in ("", t.bot)]
    mc = monte_carlo_trades(
        rets,
        n_sims=req.n_sims,
        horizon=req.horizon,
        risk_per_trade=req.risk_per_trade_pct,
        start_equity=get_settings().paper_equity_start,
    )
    return {"edge": summarize_edge(rets), **mc}


@app.get("/api/candles")
async def candles(symbol: str = "BTCUSDT", timeframe: str = "1h", limit: int = 500):
    return await asyncio.to_thread(_candles_snapshot, symbol, timeframe, limit)


def _candles_snapshot(symbol: str, timeframe: str, limit: int) -> list[dict]:
    session = session_factory()
    try:
        df = load_candles_df(session, symbol.upper(), timeframe)
    finally:
        session.close()
    if df.empty:
        return []
    df = df.tail(limit)
    return [
        {
            "t": int(idx.timestamp() * 1000),
            "o": float(r["open"]),
            "h": float(r["high"]),
            "l": float(r["low"]),
            "c": float(r["close"]),
            "v": float(r["volume"]),
        }
        for idx, r in df.iterrows()
    ]


@app.get("/api/bots")
async def bots():
    return await asyncio.to_thread(_bots_snapshot)


def _bots_snapshot() -> list[dict]:
    session = session_factory()
    try:
        out = []
        for b in session.execute(select(BotStatus)).scalars():
            if b.name.startswith("__"):
                continue
            out.append(
                {
                    "name": b.name,
                    "running": b.running,
                    "mode": b.mode,
                    "note": b.note,
                    "heartbeat": str(b.last_heartbeat) if b.last_heartbeat else None,
                    "vetoes": {
                        gate: int(get_state(session, f"veto:{b.name}:{gate}") or 0)
                        for gate in ("quant", "reviewer", "ml_gate", "prime", "cooldown")
                    },
                    "guard": risk_guard.status(
                        lambda k: get_state(session, k),
                        b.name,
                        dt.datetime.now(dt.UTC).timestamp(),
                    ),
                }
            )
        return out
    finally:
        session.close()


@app.post("/api/bots/{name}/toggle")
async def toggle_bot(name: str, authorization: str | None = Header(default=None)):
    _require_engine_token(authorization)
    session = session_factory()
    try:
        bot = session.get(BotStatus, name)
        if bot is None:
            raise HTTPException(404, name)
        bot.running = not bot.running
        bot.note = ("resumed" if bot.running else "paused") + " via dashboard"
        session.commit()
        return {"name": name, "running": bot.running}
    finally:
        session.close()


# ------------------------------------------------- agent tuning (autopilot)


class TuningUpdate(BaseModel):
    leverage_min: float | None = None
    leverage_max: float | None = None
    risk_per_trade_pct: float | None = None
    confidence_min_hft: float | None = None
    confidence_min_scalp: float | None = None
    max_positions_per_bot: int | None = None
    turbo_mode: bool | None = None


_TUNING_KEYS = (
    "leverage_min", "leverage_max", "risk_per_trade_pct", "confidence_min_hft",
    "confidence_min_scalp", "max_positions_per_bot", "turbo_mode",
)


def _tuning_snapshot() -> dict:
    from trading.config import get_settings
    s = get_settings()
    session = session_factory()
    try:
        out = {
            "leverage_min": s.leverage_min, "leverage_max": s.leverage_max,
            "risk_per_trade_pct": s.risk_per_trade_risk_pct,
            "confidence_min_hft": s.confidence_min_hft,
            "confidence_min_scalp": s.confidence_min_scalp,
            "max_positions_per_bot": s.max_positions_per_bot,
            "turbo_mode": s.turbo_mode,
            "target_trades_per_day": s.target_trades_per_day,
        }
        for k in _TUNING_KEYS:
            v = get_state(session, f"tuning:{k}")
            if v is not None:
                out[k] = float(v) if k != "turbo_mode" else bool(int(v))
        return out
    finally:
        session.close()


@app.get("/api/agents/tuning")
async def get_tuning():
    return await asyncio.to_thread(_tuning_snapshot)


@app.post("/api/agents/tuning")
async def set_tuning(body: TuningUpdate, authorization: str | None = Header(default=None)):
    _require_engine_token(authorization)
    from trading.models import set_state as _set
    session = session_factory()
    try:
        data = body.model_dump(exclude_none=True)
        for k, v in data.items():
            if k in _TUNING_KEYS:
                _set(session, f"tuning:{k}", int(v) if isinstance(v, bool) else v)
        session.commit()
        return await asyncio.to_thread(_tuning_snapshot)
    finally:
        session.close()


# ------------------------------------------------- opportunity scanner


def _scan_opportunities(symbol: str = "BTCUSDT") -> list[dict]:
    """Score the latest setup per bot TF: strategy signal + opportunity score.

    Read-only, never raises (per-bot try/except) — the AUTO view polls this
    to show what the desk sees RIGHT NOW across 1m → 4h.
    """
    from trading.agents.market_tools import opportunity_score, volatility_regime
    from trading.bots import HFTMomentum, ScalpTrend
    from trading.features import build_features
    from trading.storage import load_candles_df

    specs = [
        ("hft", "1m", HFTMomentum()),
        ("hft_5m", "5m", HFTMomentum()),
        ("scalp_15m", "15m", ScalpTrend()),
        ("scalp_1h", "1h", ScalpTrend()),
        ("scalp", "4h", ScalpTrend()),
    ]
    out: list[dict] = []
    session = session_factory()
    try:
        for bot, tf, strat in specs:
            try:
                df = load_candles_df(session, symbol, tf)
                if df is None or len(df) < 120:
                    out.append({"bot": bot, "timeframe": tf, "state": "warming_up"})
                    continue
                feats = build_features(df)
                sig = None
                for i in (len(feats) - 2, len(feats) - 3):
                    sig = strat.signal(i, feats)
                    if sig is not None:
                        break
                if sig is None:
                    out.append({"bot": bot, "timeframe": tf, "state": "no_setup"})
                    continue
                row = feats.iloc[-2]
                atr_pct = float(row["atr_pct"]) * 100
                regime, _ = volatility_regime(atr_pct, tf)
                out.append(
                    {
                        "bot": bot,
                        "timeframe": tf,
                        "state": "setup",
                        "side": sig.side,
                        "confidence": sig.confidence,
                        "rr": sig.tp_rr,
                        "score": opportunity_score(
                            sig.confidence, float(row["vol_z"]), sig.tp_rr, regime
                        ),
                        "regime": regime,
                    }
                )
            except Exception as exc:  # noqa: BLE001 — one bad TF must not kill the scan
                log.warning("scanner %s/%s failed: %s", bot, tf, exc)
                out.append({"bot": bot, "timeframe": tf, "state": "error"})
    finally:
        session.close()
    out.sort(key=lambda d: d.get("score", -1), reverse=True)
    return out


@app.get("/api/opportunities")
async def opportunities(symbol: str = "BTCUSDT"):
    return await asyncio.to_thread(_scan_opportunities, symbol)


# ------------------------------------------------------------------ WS


@app.websocket("/ws")
async def ws_feed(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            snap = await asyncio.to_thread(_overview_snapshot)
            await ws.send_text(json.dumps(snap, default=str))
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        return
    except Exception as exc:  # pragma: no cover
        log.debug("ws closed: %s", exc)
