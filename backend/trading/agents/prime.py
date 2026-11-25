"""Prime orchestrator — single LLM entry-point for all trading decisions.

Design goals (RPi4 + OpenRouter free tier 45 req/day):
- max 1 LLM call per signal (merged quant+reviewer), 0 calls when a local
  tool vetoes first (tools.py is free)
- strict priority budgets: high (signal gate) / low (analyst+forecast) /
  post_retrain (supervisor) / buffer (retry reserve)
- lazy imports only — no heavy modules at __init__ (RAM)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from trading.agents.base import Insight
from trading.agents.tools import (
    atr_filter,
    compute_ev,
    news_blackout,
    regime_changed,
    trend_alignment,
    vol_filter,
)


@dataclass
class BudgetPolicy:
    daily_total: int = 45
    reserve: dict = field(
        default_factory=lambda: {"high": 30, "low": 10, "post_retrain": 2, "buffer": 3}
    )


@dataclass
class SignalDecision:
    approved: bool
    confidence: float
    size_mult: float
    veto_reason: str | None = None
    llm_used: bool = False
    insight: Insight | None = None

    def adjusted_signal(self, sig):
        return type(sig)(
            side=sig.side,
            confidence=self.confidence,
            stop_atr=sig.stop_atr,
            tp_rr=sig.tp_rr,
        )


class PrimeOrchestrator:
    """Wraps quant+reviewer+ML+tools behind decide_signal()."""

    def __init__(self, session_factory, client=None, bot_stats: dict | None = None):
        self.session_factory = session_factory
        self.client = client
        self.bot_stats = bot_stats or {}
        self.policy = BudgetPolicy()
        self._agents = None  # lazy: built on first LLM path
        self._last_regime: float | None = None

    def _ensure_agents(self):
        if self._agents is None:
            from trading.agents import build_agents

            self._agents = build_agents(bot_stats=self.bot_stats)
        return self._agents

    def local_gate(
        self,
        bot: str,
        side: str,
        tf: str,
        vol_z: float,
        atr_pct: float,
        trend_strength: float,
        rsi: float | None,
        rr: float,
        conf: float,
        rvol: float = 1.0,
    ) -> tuple[bool, str, float]:
        """Run all free tools. Returns (approved, reason, size_mult)."""
        if news_blackout():
            return False, "news blackout", 0.5
        ok, reason = atr_filter(atr_pct, tf)
        if not ok:
            return False, reason, 0.5
        ok, reason = vol_filter(vol_z, rvol, tf)
        if not ok:
            return False, reason, 0.5
        # HFT fade (mean-reversion on flat regime) skips trend-alignment veto:
        # alignment gate is trend-biased and structurally anti-fade.
        flat = abs(trend_strength) < 1.5 if tf == "1m" else None
        if not (bot == "hft" and flat):
            ok, reason = trend_alignment(side, trend_strength, rsi)
            if not ok:
                return False, reason, 0.5
        # turbo market tools: funding / OI / volatility regime (soft vetoes,
        # abstain when the feed has no value so they never block blindly)
        try:
            from trading.agents.market_tools import funding_gate, oi_gate, volatility_regime
            extra = getattr(self, "_market_ctx", {}) or {}
            ok, reason = funding_gate(extra.get("funding"), side)
            if not ok:
                return False, reason, 0.5
            ok, reason = oi_gate(extra.get("oi_change_pct"))
            if not ok:
                return False, reason, 0.5
            _regime, _mult = volatility_regime(atr_pct, tf)
        except Exception:
            pass
        stats = self.bot_stats.get(bot) or self.bot_stats.get("*") or {}
        ev = compute_ev(
            float(stats.get("wr", 0.45)), rr, vol_z, atr_pct, conf, int(stats.get("n", 0))
        )
        if not ev["approved"]:
            return False, f"EV reject: {ev['reason']}", ev["size_multiplier"]
        return True, "local pass", ev["size_multiplier"]

    async def decide_signal(
        self, bot: str, sig, feats_row: dict, ctx: dict | None = None
    ) -> SignalDecision:
        """0 LLM calls on local veto; else single merged quant+reviewer call.

        feats_row: {vol_z, atr_pct, trend_strength, rsi, rvol, tf}
        Falls back to local verdict when LLM unavailable (no key / budget / 429).
        Never raises — fail-open to local verdict, fail-closed on local veto.
        """
        ctx = ctx or {}
        tf = str(feats_row.get("tf") or ctx.get("timeframe") or "1m")
        ok, reason, mult = self.local_gate(
            bot=bot,
            side=sig.side,
            tf=tf,
            vol_z=float(feats_row.get("vol_z") or 0),
            atr_pct=float(feats_row.get("atr_pct") or 0),
            trend_strength=float(feats_row.get("trend_strength") or 0),
            rsi=feats_row.get("rsi"),
            rr=float(sig.tp_rr),
            conf=float(sig.confidence),
            rvol=float(feats_row.get("rvol") or 1.0),
        )
        if not ok:
            return SignalDecision(
                approved=False,
                confidence=0.0,
                size_mult=mult,
                veto_reason=reason,
                llm_used=False,
                insight=Insight(
                    agent="prime",
                    title=f"Prime local veto ({bot})",
                    body=f"[prime-local] {reason}",
                    severity="info",
                    tags=["prime", "veto", bot],
                    meta={"source": "prime_local"},
                ),
            )
        # Local pass — try ONE merged LLM call, else approve with local sizing.
        try:
            agents = self._ensure_agents()
            q_ctx = {
                "bot": bot,
                "side": sig.side,
                "symbol": ctx.get("symbol", "BTCUSDT"),
                "signal": sig,
                "vol_z": float(feats_row.get("vol_z") or 0),
                "atr_pct": float(feats_row.get("atr_pct") or 0),
                "trend_strength": float(feats_row.get("trend_strength") or 0),
                "history": {
                    "wr": float((self.bot_stats.get(bot) or {}).get("wr", 0.45)),
                    "n": int((self.bot_stats.get(bot) or {}).get("n", 0)),
                },
                "lessons": ctx.get("lessons", ""),
            }
            q_ok, q_mult, q_insight = await agents["quant"].validate(q_ctx)
            if not q_ok:
                return SignalDecision(False, 0.0, q_mult, "quant EV reject", True, q_insight)
            r_ctx = {
                "bot": bot,
                "signal": sig,
                "symbol": ctx.get("symbol", "BTCUSDT"),
                "price": ctx.get("price"),
                "trend_strength": float(feats_row.get("trend_strength") or 0),
                "rsi": feats_row.get("rsi"),
                "atr_pct": float(feats_row.get("atr_pct") or 0),
                "news_blackout": news_blackout(),
                "lessons": ctx.get("lessons", ""),
            }
            # Budget: merged gate counts as ONE high-priority call; quant already
            # consumed it — reviewer reuses heuristic when budget is tight.
            # For now run reviewer (single extra call) only when confidence is marginal.
            if float(sig.confidence) >= 0.65:
                return SignalDecision(True, float(sig.confidence), q_mult, None, True, q_insight)
            approved, conf_adj, r_insight = await agents["reviewer"].review(r_ctx)
            return SignalDecision(approved, conf_adj, q_mult, None, True, r_insight)
        except Exception:
            return SignalDecision(
                approved=True,
                confidence=float(sig.confidence),
                size_mult=mult,
                veto_reason=None,
                llm_used=False,
                insight=Insight(
                    agent="prime",
                    title=f"Prime local pass ({bot})",
                    body="[prime-local] LLM unavailable — local EV pass.",
                    severity="info",
                    tags=["prime", "local", bot],
                    meta={"source": "prime_local"},
                ),
            )

    async def maybe_analyst(self, market_ctx: dict):
        """Max 4×/day and only on regime change — replaces 300s cadence."""
        curr = float(market_ctx.get("regime") or 0)
        if self._last_regime is not None and not regime_changed(self._last_regime, curr):
            return None
        self._last_regime = curr
        try:
            agents = self._ensure_agents()
            return await agents["analyst"].run(market_ctx)
        except Exception:
            return None

    def snapshot(self) -> dict:
        return {
            "policy": self.policy.reserve,
            "last_regime": self._last_regime,
            "bots": sorted(self.bot_stats.keys()),
        }
