"""Layer-0 hard rails — evaluated inside the kernel harness, before any entry
order exists (design §6: the closer to execution, the dumber and more
independent the rail).

Four rails, all deterministic arithmetic over the run's own realized truth:

1. KILL-SWITCH — drawdown from peak realized equity. The peak is tracked
   inside the run from realized_net (the validation equity the harness
   settles into), so backtest and paper measure the identical quantity.
   Tripping is a one-way latch for the run's lifetime: entries vetoed until
   the process ends. A restart rebuilds the book from initial equity — the
   trip memory dying with the process is documented provenance, and the
   persisted MANUAL kill-switch (below) is the rail that survives restarts.
   flatten-on-trip is configurable and defaults off: in paper the trip is
   detected at a settle — the position that caused it has already closed —
   and in the harness's realized-only accounting an open position never
   moves equity, so there is nothing additional to flatten. The flag exists
   for the day mark-to-market rails land; today it is honestly vacuous.

2. DAILY LOSS LIMIT — net realized loss within the UTC day vs the equity the
   day started with. A breach latches for the REST of the UTC day (design:
   "breach vetoes entries for the rest of the UTC day"), even if later wins
   would net it back — the day is forfeit, not the moment.

3. LOSS-STREAK COOLDOWN — risk_guard.py's exact semantics (3 consecutive
   losing closes -> 4h pause, wins reset the streak, breakeven counts as a
   loss) with the kv-state callables replaced by in-run state. The constants
   are imported, never copied: one definition, two storage backends.

4. EXTERNAL HALTS, fail-closed and entry-blocking:
   - the persisted manual kill-switch row (risk.py's `__killswitch` — the
     existing mechanism, reused; nothing invented). In the desk the check
     reads the database at entry-evaluation cadence — rare enough that a
     microsecond SQLite read is nothing, and the alternative (polling) would
     lag the switch by design. A check that ERRORS reads as tripped: a rail
     that cannot see its state is a rail that says no.
   - the Layer-4 halt sentinel file. Existence is the halt — content is
     never read, so a corrupt file halts exactly like a sound one. The check
     runs at every entry AND at rearm submission. Protective stops,
     take-profits and position CLOSES are never blocked: a halt that
     strands open risk is a halt that creates the damage it exists to
     prevent. In paper the harness submission path IS the venue boundary —
     the sandbox is kernel-internal — so the harness is where this rail
     lives; the design's venue-adapter boundary is the live adapter's, and
     that adapter does not exist in M3.

Every firing produces an event with its inputs — "a rail that cannot
explain itself is removed, not trusted" (design §6). Entry-blocking firings
additionally land in the veto tape slice 3 built, so sizing vetoes and rail
vetoes share one evidence stream.
"""

from __future__ import annotations

import datetime as dt

from trading.risk_guard import COOLDOWN_HOURS, MAX_LOSSES

# rail names — the vocabulary risk_events rows and the dashboard speak
RAIL_KILL_SWITCH = "kill_switch_drawdown"
RAIL_DAILY_LOSS = "daily_loss_limit"
RAIL_LOSS_STREAK = "loss_streak_cooldown"
RAIL_MANUAL_KILL = "manual_killswitch"
RAIL_HALT_SENTINEL = "halt_sentinel"


def _utc_day(epoch_s: float) -> str:
    return dt.datetime.fromtimestamp(epoch_s, tz=dt.UTC).strftime("%Y-%m-%d")


class RailBook:
    """Per-run rail state — one instance per strategy run, in-memory by
    design (paper). Everything the rails know is here or in the inputs they
    are handed; there is no hidden state to restart-diverge beyond what the
    module docstring documents."""

    def __init__(
        self,
        initial_equity: float,
        *,
        killswitch_dd_pct: float,
        daily_loss_pct: float,
        loss_streak_max: int = MAX_LOSSES,
        cooldown_hours: float = COOLDOWN_HOURS,
        flatten_on_kill: bool = False,
    ):
        self.killswitch_dd_pct = float(killswitch_dd_pct)
        self.daily_loss_pct = float(daily_loss_pct)
        self.loss_streak_max = int(loss_streak_max)
        self.cooldown_hours = float(cooldown_hours)
        # documented as vacuous in the harness's realized-only accounting —
        # see the module docstring
        self.flatten_on_kill = bool(flatten_on_kill)

        self.peak_equity = float(initial_equity)
        self.kill_tripped = False
        self._day: str | None = None
        self.day_start_equity = float(initial_equity)
        self.daily_breached = False
        self.loss_streak = 0
        self.cooldown_until = 0.0

    # ------------------------------------------------------------- internals
    def _roll_day(self, now_s: float, realized_net: float) -> None:
        """The daily-loss window is the UTC day, rolling forward lazily at
        the next observation — a day nobody observed never existed."""
        day = _utc_day(now_s)
        if day != self._day:
            self._day = day
            self.day_start_equity = realized_net
            self.daily_breached = False

    def _daily_loss_inputs(self, realized_net: float) -> dict:
        loss = self.day_start_equity - realized_net
        limit = self.day_start_equity * self.daily_loss_pct if self.day_start_equity > 0 else 0.0
        return {
            "day": self._day,
            "day_start_equity": round(self.day_start_equity, 6),
            "realized_net": round(realized_net, 6),
            "loss": round(loss, 6),
            "limit": round(limit, 6),
            "daily_loss_pct": self.daily_loss_pct,
        }

    def _daily_breach_now(self, realized_net: float) -> bool:
        if self.day_start_equity <= 0:
            return False
        return (self.day_start_equity - realized_net) >= self.day_start_equity * self.daily_loss_pct

    # ---------------------------------------------------------------- settle
    def settle(self, pnl: float, now_s: float, realized_net: float) -> list[dict]:
        """Feed one closed trade. Returns the rail events this settle caused —
        the harness emits them into the run's evidence stream. Called AFTER
        realized_net has been incremented by pnl (the harness's order)."""
        events: list[dict] = []
        # the day roll must see the equity the day STARTED with: on the first
        # observation of a new day that is the pre-settle equity — using the
        # post-loss figure would hide the very loss the rail exists to catch
        self._roll_day(now_s, realized_net - pnl)

        # loss streak — risk_guard.record_close verbatim in arithmetic:
        # losses and breakevens increment, wins reset; hitting the max arms
        # the cooldown and zeroes the streak
        self.loss_streak = self.loss_streak + 1 if pnl <= 0 else 0
        if self.loss_streak >= self.loss_streak_max:
            self.cooldown_until = now_s + self.cooldown_hours * 3600
            streak = self.loss_streak
            self.loss_streak = 0
            events.append(
                {
                    "rail": RAIL_LOSS_STREAK,
                    "decision": "cooldown_started",
                    "inputs": {
                        "streak": streak,
                        "max_losses": self.loss_streak_max,
                        "cooldown_hours": self.cooldown_hours,
                        "cooldown_until": self.cooldown_until,
                        "pnl": round(pnl, 6),
                    },
                    "ts": now_s,
                }
            )

        # daily loss — latch the day forfeit on first breach
        if not self.daily_breached and self._daily_breach_now(realized_net):
            self.daily_breached = True
            events.append(
                {
                    "rail": RAIL_DAILY_LOSS,
                    "decision": "breached",
                    "inputs": self._daily_loss_inputs(realized_net),
                    "ts": now_s,
                }
            )

        # kill-switch — peak moves only up; the drawdown is measured against
        # it from the run's realized truth
        if realized_net > self.peak_equity:
            self.peak_equity = realized_net
        elif (
            not self.kill_tripped
            and self.peak_equity > 0
            and (self.peak_equity - realized_net) / self.peak_equity >= self.killswitch_dd_pct
        ):
            self.kill_tripped = True
            events.append(
                {
                    "rail": RAIL_KILL_SWITCH,
                    "decision": "tripped",
                    "inputs": {
                        "peak_equity": round(self.peak_equity, 6),
                        "realized_net": round(realized_net, 6),
                        "drawdown_pct": round((self.peak_equity - realized_net) / self.peak_equity, 6),
                        "killswitch_dd_pct": self.killswitch_dd_pct,
                        "pnl": round(pnl, 6),
                        # the honest flatten answer: nothing was open to flatten
                        # (the trip is detected at a close) — recorded so the
                        # row explains itself
                        "flattened": False,
                    },
                    "ts": now_s,
                }
            )
        return events

    # ----------------------------------------------------------------- entry
    def entry_verdict(self, now_s: float, realized_net: float) -> dict | None:
        """None when the entries may flow, else the veto with rail, reason and
        every input number the decision stands on. Ordering: the kill-switch
        outranks the daily limit outranks the cooldown — the most terminal
        rail explains itself first."""
        self._roll_day(now_s, realized_net)
        if self.kill_tripped:
            return {
                "rail": RAIL_KILL_SWITCH,
                "reason": RAIL_KILL_SWITCH,
                "inputs": {
                    "peak_equity": round(self.peak_equity, 6),
                    "realized_net": round(realized_net, 6),
                    "drawdown_pct": round(
                        (self.peak_equity - realized_net) / self.peak_equity, 6
                    )
                    if self.peak_equity > 0
                    else 0.0,
                    "killswitch_dd_pct": self.killswitch_dd_pct,
                },
            }
        if self.daily_breached or self._daily_breach_now(realized_net):
            self.daily_breached = True  # breach discovered at entry time latches too
            return {
                "rail": RAIL_DAILY_LOSS,
                "reason": RAIL_DAILY_LOSS,
                "inputs": self._daily_loss_inputs(realized_net),
            }
        if self.cooldown_until and now_s < self.cooldown_until:
            return {
                "rail": RAIL_LOSS_STREAK,
                "reason": RAIL_LOSS_STREAK,
                "inputs": {
                    "cooldown_until": self.cooldown_until,
                    "remaining_s": round(self.cooldown_until - now_s, 1),
                    "loss_streak": self.loss_streak,
                    "max_losses": self.loss_streak_max,
                },
            }
        return None

    # -------------------------------------------------------------- snapshot
    def snapshot(self, now_s: float, realized_net: float) -> dict:
        """Dashboard-friendly rail state — the same numbers the verdicts are
        made of, read-only."""
        self._roll_day(now_s, realized_net)
        drawdown = (
            (self.peak_equity - realized_net) / self.peak_equity if self.peak_equity > 0 else 0.0
        )
        loss = self.day_start_equity - realized_net
        limit = self.day_start_equity * self.daily_loss_pct if self.day_start_equity > 0 else 0.0
        return {
            "equity": round(realized_net, 6),
            "peak_equity": round(self.peak_equity, 6),
            "drawdown_pct": round(max(drawdown, 0.0), 6),
            "killswitch_dd_pct": self.killswitch_dd_pct,
            "kill_tripped": self.kill_tripped,
            "day": self._day,
            "daily_loss": round(max(loss, 0.0), 6),
            "daily_loss_limit": round(limit, 6),
            "daily_loss_consumed": round(loss / limit, 4) if limit > 0 and loss > 0 else 0.0,
            "daily_breached": self.daily_breached,
            "loss_streak": self.loss_streak,
            "max_losses": self.loss_streak_max,
            "cooldown_remaining_s": round(max(self.cooldown_until - now_s, 0.0), 1),
        }
