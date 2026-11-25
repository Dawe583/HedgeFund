"""Market forecaster — per-cycle directional forecast for each bot.

Every engine cycle each active bot (HFT-BOT, SCALP-BOT) produces a structured
forecast: direction (up/down/flat), confidence 0-1, expected move % and a
one-line reasoning. ScalpFX Alpha via OpenRouter when a key is present, otherwise
a deterministic heuristic built from trend/volatility features. Forecasts are
persisted (AgentPrediction) and rendered on the dashboard chart so the user
can watch how both agents think over time.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from trading.agents.openrouter import OpenRouterClient
from trading.models import AgentPrediction

log = logging.getLogger(__name__)

VALID_DIRECTIONS = {"up", "down", "flat"}

SYSTEM = (
    "You are ScalpFX Alpha, forecasting BTCUSDT for the ScalpFX desk. You receive the "
    "latest features of one bot's timeframe plus lessons from its own trade memory. "
    "Forecast the NEXT {horizon_hint} bars: direction up/down/flat, your confidence "
    "0-1 (calibrated — flat is valid when signals conflict), expected absolute move "
    "%, one-line reasoning. Terse, quantitative, no advice. "
    'Reply ONLY as JSON: {"direction": "up"|"down"|"flat", "confidence": float, '
    '"expected_move_pct": float (signed %), "horizon_bars": int<=24, '
    '"reasoning": str (<=25 words)}'
)


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


class Forecaster:
    name = "forecaster"

    def __init__(self, session_factory, client: OpenRouterClient | None = None):
        self.session_factory = session_factory
        self.client = client or OpenRouterClient()

    async def run(
        self,
        bot: str,
        symbol: str,
        timeframe: str,
        feats,
        lessons: str = "",
        signal_confidence: float | None = None,
    ) -> dict:
        """Produce + persist one forecast row. Never raises."""
        try:
            return await self._run(bot, symbol, timeframe, feats, lessons, signal_confidence)
        except Exception:
            log.exception("forecaster failed (%s)", bot)
            return {}

    async def _run(self, bot, symbol, timeframe, feats, lessons, signal_confidence) -> dict:
        last = feats.iloc[-1]
        ctx = {
            "price": round(float(last["close"]), 2),
            "trend_strength": round(float(last["trend_strength"]), 3),
            "rsi": round(float(last["rsi"]), 1),
            "atr_pct": round(float(last["atr_pct"]) * 100, 3),
            "rvol": round(float(last["rvol"]), 3),
            "regime": round(float(last["regime"]), 4),
        }
        horizon_hint = "1-4 bars" if bot == "hft" else "6-24 bars"

        user = (
            f"bot: {bot} timeframe: {timeframe}\n"
            f"metrics: {json.dumps(ctx)}\n"
            f"strategy_signal_confidence: "
            f"{'none' if signal_confidence is None else round(signal_confidence, 3)}\n"
        )
        if lessons:
            user += f"\nMemory lessons:\n{lessons}\n"

        raw = await self.client.chat(
            system=SYSTEM.replace("{horizon_hint}", horizon_hint),
            user=user,
            json_mode=True,
            max_tokens=200,
            temperature=0.2,
            priority="low",
        )
        parsed: dict = {}
        if raw:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = {}

        direction = str(parsed.get("direction", "")).lower()
        source = "llm"
        if direction not in VALID_DIRECTIONS:
            direction, source = self._heuristic(ctx), "heuristic"

        conf = _f(parsed.get("confidence"), -1)
        if not (0 <= conf <= 1):
            conf = self._heuristic_conf(ctx, direction)
        move = _f(parsed.get("expected_move_pct"), self._heuristic_move(ctx, direction))
        try:
            horizon = max(1, min(24, int(parsed.get("horizon_bars") or (2 if bot == "hft" else 8))))
        except (TypeError, ValueError):
            horizon = 2 if bot == "hft" else 8
        reasoning = str(parsed.get("reasoning", "")).strip() or "[heuristic] trend/vol read"
        if len(reasoning) > 500:
            reasoning = reasoning[:497] + "..."

        row = dict(
            bot=bot,
            symbol=symbol.upper(),
            timeframe=timeframe,
            direction=direction,
            confidence=round(min(0.99, max(0.01, conf)), 3),
            expected_move_pct=round(max(-50.0, min(50.0, move)), 3),
            horizon_bars=horizon,
            price_at_ts=ctx["price"],
            reasoning=f"{reasoning} | ts={ctx['trend_strength']} rsi={ctx['rsi']} "
            f"atr%={ctx['atr_pct']}",
            signal_confidence=round(_f(signal_confidence), 3),
            source=source,
        )
        session = self.session_factory()
        try:
            session.add(AgentPrediction(**row))
            session.commit()
        finally:
            session.close()
        return row

    # ------------------------------------------------------------- heuristic
    @staticmethod
    def _heuristic(ctx: dict) -> str:
        ts = ctx["trend_strength"]
        rsi = ctx["rsi"]
        if abs(ts) < 0.5 and 40 < rsi < 60:
            return "flat"
        if ts > 0.5 and rsi < 78:
            return "up"
        if ts < -0.5 and rsi > 22:
            return "down"
        # extreme RSI overrides weak trend
        return "down" if rsi >= 78 else ("up" if rsi <= 22 else "flat")

    @staticmethod
    def _heuristic_conf(ctx: dict, direction: str) -> float:
        if direction == "flat":
            return 0.45
        strength = min(abs(ctx["trend_strength"]) / 5.0, 0.55)
        return round(min(0.9, 0.38 + strength + (0.05 if ctx["atr_pct"] < 2 else 0)), 3)

    @staticmethod
    def _heuristic_move(ctx: dict, direction: str) -> float:
        base = max(ctx["atr_pct"], 0.15) * 0.6
        return round(base if direction == "up" else (-base if direction == "down" else 0.0), 3)
