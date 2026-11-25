"""AI Quant Analyst — mathematical validator between signal and execution.

Unlike the reviewer (which judges context/structure), the quant agent runs
NUMBERS first: expected value vs breakeven win-rate, volume-z significance,
ATR sanity, Kelly-consistent sizing. LLM (ScalpFX Alpha) does the final math
review when a key is present; a deterministic statistical fallback keeps the
gate honest without any API.

Returns (approved, size_multiplier, insight):
- approved          — signal passes the math
- size_multiplier   — 0.5..1.75 × base notional (conviction-scaled sizing)
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from trading.agents.base import BaseAgent, Insight
from trading.backtest.engine import Signal
from trading.models import Trade

log = logging.getLogger(__name__)


def breakeven_wr(rr: float) -> float:
    """Win-rate needed to break even at reward:rr."""
    return 1.0 / (1.0 + rr) if rr > 0 else 1.0


class QuantAnalyst(BaseAgent):
    name = "quant"
    priority = "high"  # gates a real position — funded before commentary
    system = (
        "You are ScalpFX Alpha in QUANT VALIDATOR mode. You receive a candidate trade with "
        "full mathematics: R:R, breakeven win-rate, the bot's realized win-rate over "
        "recent trades, volume z-score, ATR%, trend strength. Do the arithmetic, judge "
        "expected value, and size the position by conviction. Be strict: reject when "
        "edge is unproven by the MATH (R:R too thin, vol-z insignificant, ATR out of "
        "range). A missing trade history is NOT a rejection reason — new bots start "
        "with a neutral 45% prior. "
        'Reply ONLY as JSON: {"approved": bool, "confidence": float 0-1, '
        '"expected_win_rate": float, "size_multiplier": float 0.5-1.75, '
        '"title": str, "body": str (<=50 words), "severity": "info"|"warn"|"alert", "tags": [str]}'
    )

    def __init__(self, client=None, bot_stats: dict | None = None):
        super().__init__(client)
        self.bot_stats = bot_stats or {}

    # ------------------------------------------------------------- prompt
    def build_prompt(self, context: dict) -> str:
        m = context["math"]
        hist = context.get("history", {})
        return (
            f"Candidate: {context.get('bot')} {context.get('side')} {context.get('symbol')}\n"
            f"R:R = {m['rr']:.2f} | breakeven WR = {m['breakeven_wr'] * 100:.1f}%\n"
            f"bot realized WR (last {hist.get('n', 0)} trades) = "
            + (
                f"{hist.get('wr', 0) * 100:.1f}%\n"
                if hist.get("n", 0) > 0
                else "no closed trades yet — assume a neutral 45% prior, do NOT reject solely for missing history\n"
            )
            + f"signal confidence = {m['confidence']:.2f} | volume z = {m['vol_z']:.2f}\n"
            f"ATR% = {m['atr_pct']:.3f} | trend strength = {m['trend_strength']:+.2f}\n"
            f"recent memory lessons:\n{context.get('lessons', '(none)')[:400]}\n\n"
            "Compute expected value ((WR*RR) - (1-WR)), decide, size it. JSON only."
        )

    def fallback(self, context: dict) -> Insight:
        m = self.math(context)
        return Insight(
            agent=self.name,
            title=f"EV {'+' if m['approved'] else '-'} | size ×{m['size_multiplier']:.2f}",
            body=(
                f"[heuristic] RR {m['rr']:.2f} needs WR {m['breakeven_wr'] * 100:.0f}%; "
                f"realized WR {m['realized_wr'] * 100:.0f}% → EV {m['ev']:+.2f}R; "
                f"vol_z {m['vol_z']:.2f}. {'PASS' if m['approved'] else 'REJECT'}."
            ),
            severity="info" if m["approved"] else "warn",
            tags=["quant", "fallback"],
            meta={"source": "fallback"},
        )

    # --------------------------------------------------------------- math
    def math(self, context: dict) -> dict:
        sig: Signal = context["signal"]
        rr = sig.tp_rr
        bwr = breakeven_wr(rr)
        bot = str(context.get("bot") or "")
        stats = self.bot_stats.get(bot) if bot and bot in self.bot_stats else None
        if stats is None:
            stats = self.bot_stats.get("*") or {}
        realized = float(stats.get("wr", 0.45))
        n = int(stats.get("n", 0))
        ev = (realized * rr) - (1 - realized)
        vol_z = float(context.get("vol_z") or 0)
        atr_pct = float(context.get("atr_pct") or 0)
        conf = float(sig.confidence)
        trend_strength = float(context.get("trend_strength") or 0.0)

        # Per-bot RR floor: context may carry "min_rr" (default 1.5, the
        # long-standing floor). Approval logic otherwise unchanged.
        min_rr = float(context.get("min_rr") or 1.5)
        approved = (
            rr >= min_rr
            and realized >= bwr * 0.95  # allow thin edge while sample builds
            and abs(vol_z) >= 1.3
            and 0.02 <= atr_pct <= 3.0
            and conf >= 0.5
        )
        size_mult = 0.75 + max(0.0, (conf - 0.5)) * 1.6 + (0.15 if abs(vol_z) >= 2.0 else 0)
        if not approved:
            size_mult = min(size_mult, 0.75)
        return {
            "rr": rr,
            "breakeven_wr": bwr,
            "realized_wr": realized,
            "n": n,
            "ev": ev,
            "vol_z": vol_z,
            "atr_pct": atr_pct,
            "trend_strength": trend_strength,
            "confidence": conf,
            "approved": approved,
            "size_multiplier": round(max(0.5, min(1.75, size_mult)), 2),
        }

    # -------------------------------------------------------------- public
    async def validate(self, context: dict) -> tuple[bool, float, Insight]:
        """Returns (approved, size_multiplier, insight). Never raises."""
        try:
            m = self.math(context)
            context["math"] = m
            parsed, fb = await self.run_parsed(context)
            if parsed is None:
                ins = fb if fb is not None else self.fallback(context)
                return m["approved"], m["size_multiplier"], ins
            approved = bool(parsed.get("approved", False))
            try:
                mult = float(parsed.get("size_multiplier", m["size_multiplier"]))
            except (TypeError, ValueError):
                mult = m["size_multiplier"]
            mult = round(max(0.5, min(1.75, mult)), 2)
            insight = Insight(
                agent=self.name,
                title=str(parsed.get("title", "quant check"))[:120],
                body=str(parsed.get("body", ""))[:4000],
                severity=str(parsed.get("severity", "info")),
                tags=[str(t) for t in parsed.get("tags", ["quant"])][:6],
                meta={"source": "llm", "model": self.client.model, "size_multiplier": mult},
            )
            return approved, mult, insight
        except Exception:
            log.exception("quant validator failed — approving with base size")
            return (
                True,
                1.0,
                Insight(
                    agent=self.name,
                    title="quant bypass",
                    body="validator error — base size",
                    severity="warn",
                    tags=["quant"],
                    meta={"source": "fallback"},
                ),
            )


def bot_history(session_factory, bot: str, lookback: int = 50) -> dict:
    """Realized win-rate for a bot over its last `lookback` closed trades."""
    session = session_factory()
    try:
        rows = (
            session.execute(
                select(Trade.pnl)
                .where(Trade.bot == bot)
                .order_by(Trade.exit_time.desc())
                .limit(lookback)
            )
            .scalars()
            .all()
        )
        if not rows:
            return {"wr": 0.45, "n": 0}  # neutral prior while sample builds
        wins = sum(1 for p in rows if p > 0)
        return {"wr": wins / len(rows), "n": len(rows)}
    finally:
        session.close()
