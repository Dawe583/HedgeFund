"""Market Analyst agent — regime commentary every N minutes."""

from __future__ import annotations

from trading.agents.base import BaseAgent, Insight


def _market_summary(context: dict) -> str:
    return (
        f"symbol: {context.get('symbol')}\n"
        f"price: {context.get('price')}\n"
        f"trend_strength(ATR units): {context.get('trend_strength')}\n"
        f"rsi: {context.get('rsi')}\n"
        f"atr_pct: {context.get('atr_pct')}\n"
        f"realized_vol: {context.get('rvol')}\n"
        f"regime(ema separation): {context.get('regime')}\n"
        f"open_positions: {context.get('open_positions')}\n"
        f"equity: {context.get('equity')}"
    )


class MarketAnalyst(BaseAgent):
    name = "analyst"
    priority = "low"  # commentary; first to stand down as the day fills
    system = (
        "You are ScalpFX Alpha, the quant analyst inside the ScalpFX trading desk. "
        "Assess the current market state for a systematic trend/scalp operation. "
        "Be terse, quantitative, never give financial advice. "
        'Reply ONLY as JSON: {"title": str, "body": str (<=90 words), '
        '"severity": "info"|"warn"|"alert", "tags": [str]}'
    )

    def build_prompt(self, context: dict) -> str:
        prompt = f"Market snapshot:\n{_market_summary(context)}\n"
        lessons = str(context.get("lessons") or "").strip()
        if lessons:
            prompt += (
                f"\nLessons from your own memory (Hermes-style learning loop — "
                f"ground the assessment in what recently worked/failed):\n{lessons}\n"
            )
        return prompt + "\nProduce your assessment JSON."

    def fallback(self, context: dict) -> Insight:
        ts = float(context.get("trend_strength") or 0)
        sev = "info" if abs(ts) < 2.5 else ("warn" if abs(ts) < 4 else "alert")
        direction = "UP-trend" if ts > 0.5 else "DOWN-trend" if ts < -0.5 else "range/flat"
        body = (
            f"[heuristic] regime reads {direction} (strength {ts:.2f} ATR units). "
            f"RSI {context.get('rsi')}, ATR {context.get('atr_pct')}% of price, "
            f"realized vol {context.get('rvol')}. "
            + (
                "Trend-following setups favored; fade tactics discouraged."
                if abs(ts) >= 1.2
                else "Mean-reversion conditions; breakout chasing penalized by fees."
            )
        )
        return Insight(
            agent=self.name,
            title=f"Regime: {direction}",
            body=body,
            severity=sev,
            tags=["regime", context.get("symbol", "")],
            meta={"source": "fallback"},
        )
