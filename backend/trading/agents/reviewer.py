"""Signal Reviewer agent — second opinion before the engine commits capital.

Returns (approved, adjusted_confidence, insight). LLM verdict via ScalpFX Alpha;
deterministic heuristic fallback keeps paper trading working without a key.
"""

from __future__ import annotations

import logging

from trading.agents.base import BaseAgent, Insight
from trading.backtest.engine import Signal

log = logging.getLogger(__name__)


class SignalReviewer(BaseAgent):
    name = "reviewer"
    priority = "high"  # gates a real position — funded before commentary
    system = (
        "You are ScalpFX Alpha, risk reviewer at ScalpFX desk. You receive a candidate "
        "trade signal with market context. Approve only if the setup is coherent "
        "(regime alignment, sane volatility, no news-risk window). "
        "For bot=hft (1m mean-reversion) do NOT veto solely on trend misalignment "
        "when volatility is calm. "
        'Reply ONLY as JSON: {"approved": bool, "confidence": float 0-1, '
        '"title": str, "body": str (<=60 words), "severity": "info"|"warn"|"alert", "tags": [str]}'
    )

    def __init__(self, client=None, veto_floor: float = 0.55):
        super().__init__(client)
        self.veto_floor = veto_floor

    def build_prompt(self, context: dict) -> str:
        sig: Signal = context["signal"]
        prompt = (
            f"Candidate signal:\n"
            f"bot: {context.get('bot')} side: {sig.side} confidence: {sig.confidence}\n"
            f"stop_atr: {sig.stop_atr} tp_rr: {sig.tp_rr}\n"
            f"symbol: {context.get('symbol')} price: {context.get('price')}\n"
            f"trend_strength(ATR): {context.get('trend_strength')} rsi: {context.get('rsi')}\n"
            f"atr_pct: {context.get('atr_pct')} news_blackout_active: {context.get('news_blackout')}\n"
        )
        lessons = str(context.get("lessons") or "").strip()
        if lessons:
            prompt += (
                f"\nLessons from your own memory (Hermes-style learning loop — apply them "
                f"when this setup matches a known losing pattern):\n{lessons}\n"
            )
        return prompt + "\nReview and return JSON verdict."

    def fallback(self, context: dict) -> Insight:
        approved, _, ins = self._heuristic(context)
        return ins if ins is not None else Insight(agent=self.name, title="n/a", body="")

    async def review(self, context: dict) -> tuple[bool, float, Insight]:
        parsed, fb = await self.run_parsed(context)
        sig: Signal = context["signal"]

        if parsed is None:
            approved, conf, ins = self._heuristic(context)
            if fb is not None and not ins.body:
                ins = fb
            return approved, conf, ins

        approved = bool(parsed.get("approved", False))
        try:
            conf = float(parsed.get("confidence", sig.confidence))
        except (TypeError, ValueError):
            conf = sig.confidence
        conf = round(min(0.95, max(self.veto_floor if approved else 0.0, conf)), 3)

        insight = Insight(
            agent=self.name,
            title=str(parsed.get("title", "review"))[:120],
            body=str(parsed.get("body", ""))[:4000],
            severity=str(parsed.get("severity", "info")),
            tags=[str(t) for t in parsed.get("tags", ["review"])][:6],
            meta={"source": "llm", "model": self.client.model},
        )
        return approved, conf, insight

    # ------------------------------------------------------------- heuristic
    def _heuristic(self, context: dict) -> tuple[bool, float, Insight]:
        sig: Signal = context["signal"]
        ts = float(context.get("trend_strength") or 0)
        # Per-bot tolerance: HFT fade is mean-reversion by construction, so the
        # narrow +/-0.5 band systematically vetoes its counter-trend entries.
        # Widen to +/-1.5 for bot=hft; all other bots keep the strict band.
        tol = 1.5 if context.get("bot") == "hft" else 0.5
        aligned = (sig.side == "long" and ts >= -tol) or (sig.side == "short" and ts <= tol)
        calm = float(context.get("atr_pct") or 1) < 4.0
        blackout = bool(context.get("news_blackout"))
        approved = aligned and calm and not blackout
        conf = round(
            min(0.95, max(self.veto_floor if approved else 0.0, sig.confidence * (1.05 if aligned else 0.85))),
            3,
        )
        body = (
            f"[heuristic] side={sig.side} vs trend {ts:+.2f} ATR → "
            f"{'aligned' if aligned else 'counter-trend'}; vol {'ok' if calm else 'elevated'}; "
            f"blackout={blackout}. {'APPROVED.' if approved else 'VETO.'}"
        )
        insight = Insight(
            agent=self.name,
            title="Signal approved" if approved else "Signal vetoed",
            body=body,
            severity="info" if approved else "warn",
            tags=["review", "approve" if approved else "veto"],
            meta={"source": "fallback"},
        )
        return approved, conf, insight
