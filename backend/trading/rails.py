"""Layer-0 hard rails — evaluated inside the kernel harness, before any entry
order exists (design §6: the closer to execution, the dumber and more
independent the rail).

Four rails, all deterministic arithmetic over the run's own truth — and
since 2026-11-27 (analysis F-4) that truth is MARKED, not realized-only:
every bar close marks the open position at the bar's close price and the
rails evaluate realized + unrealized. An open position deep underwater now
moves every rail, which is exactly what a gap-through-stop week requires
of them. The marked curve is a RAIL INPUT ONLY: the equity series the
backtest reports (result.equity) is and remains the realized curve — mark-
to-market changes which entries the rails veto, never what the reported
equity series means. A loss you are sitting in is a loss: the daily-loss
rail measures marked day loss too (the genuine semantic alternative —
realized-only daily loss — would let an intraday underwater position
consume the day's risk budget invisibly, the same hole F-4 found in the
kill-switch; consistency wins).

1. KILL-SWITCH — drawdown of marked equity from peak marked equity. The
   peak is tracked inside the run from the bar-close marks, so backtest
   and paper measure the identical quantity. Tripping is a one-way latch
   for the run's lifetime: entries vetoed until the process ends. In
   validation a run starts fresh by design — a backtest is one
   measurement, not a life; in paper the continuous-life plane persists
   its trip (see paper.py/risk.py) because restarting the process must
   not be a risk reset. flatten_on_kill is now REAL: when the switch
   trips with a position open, the harness force-closes it at the
   current bar close (same fill semantics as timeout exits) and the trip
   event records flattened: true with the position's marked loss.

2. DAILY LOSS LIMIT — marked loss within the UTC day vs the marked equity
   the day started with. A breach latches for the REST of the UTC day
   (design: "breach vetoes entries for the rest of the UTC day"), even if
   later wins would net it back — the day is forfeit, not the moment.

3. LOSS-STREAK COOLDOWN — risk_guard.py's exact semantics (3 consecutive
   losing closes -> 4h pause, wins reset the streak, breakeven counts as a
   loss) with the kv-state callables replaced by in-run state. The streak
   counts CLOSES, so it alone stays realized-only: a close is a fact, a
   mark is not. The constants are imported, never copied: one definition,
   two storage backends.

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
        # real since 2026-11-27 (F-4): the harness force-closes the open
        # position at the tripping bar's close — see the module docstring
        self.flatten_on_kill = bool(flatten_on_kill)

        self.peak_equity = float(initial_equity)
        # the marked curve's latest value — every verdict and the snapshot
        # measure THIS, never realized-only equity. Settles write it because
        # a closed position's marked equity IS the realized figure; bar-close
        # marks write it with unrealized included.
        self.last_marked = float(initial_equity)

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

        # kill-switch — peak moves only up; at a settle nothing is open, so
        # realized IS the marked equity at this instant
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
        # a closed position's marked truth is the realized figure
        self.last_marked = realized_net
        return events

    # ------------------------------------------------------------------ mark
    def mark(self, now_s: float, realized_net: float, unrealized: float, open_position: bool) -> list[dict]:
        """Mark-to-market at a bar close: evaluate peak/drawdown and the
        daily-loss rail against realized + unrealized, WITHOUT touching the
        close-driven state (the loss streak counts facts, not marks). This is
        the per-bar entry point distinct from settle — the harness calls it
        at every bar close so the kill-switch can trip intra-position, which
        is the whole point of F-4's repair: the week that gaps through every
        stop now moves the rails while it is still happening.

        Returns the rail events the mark caused. When the trip fires with
        flatten_on_kill set and a position open, the event records
        flattened: true with the position's marked loss, and the harness
        force-closes at the same bar close (timeout fill semantics) — the
        event's flattened is the flatten ORDER the trip caused, honest
        because the harness performs it unconditionally on seeing this
        event."""
        events: list[dict] = []
        marked = realized_net + unrealized
        self._roll_day(now_s, marked)
        self.last_marked = marked

        # daily loss — a loss you are sitting in is a loss: the marked day
        # loss latches the day forfeit exactly like a realized one
        if not self.daily_breached and self._daily_breach_now(marked):
            self.daily_breached = True
            events.append(
                {
                    "rail": RAIL_DAILY_LOSS,
                    "decision": "breached",
                    "inputs": self._daily_loss_inputs(marked),
                    "ts": now_s,
                }
            )

        # kill-switch — peak moves only up, on the marked curve; a trip with
        # a position open is the scenario flatten_on_kill exists for
        if marked > self.peak_equity:
            self.peak_equity = marked
        elif (
            not self.kill_tripped
            and self.peak_equity > 0
            and (self.peak_equity - marked) / self.peak_equity >= self.killswitch_dd_pct
        ):
            self.kill_tripped = True
            flattened = bool(self.flatten_on_kill and open_position)
            events.append(
                {
                    "rail": RAIL_KILL_SWITCH,
                    "decision": "tripped",
                    "inputs": {
                        "peak_equity": round(self.peak_equity, 6),
                        "equity_marked": round(marked, 6),
                        "realized_net": round(realized_net, 6),
                        "unrealized": round(unrealized, 6),
                        "drawdown_pct": round((self.peak_equity - marked) / self.peak_equity, 6),
                        "killswitch_dd_pct": self.killswitch_dd_pct,
                        "flattened": flattened,
                        # the position's marked loss at the trip instant —
                        # negative when underwater; 0.0 when nothing was open
                        "flatten_loss": round(unrealized, 6) if flattened else 0.0,
                    },
                    "ts": now_s,
                }
            )
        return events

    # ----------------------------------------------------------------- entry
    def entry_verdict(self, now_s: float) -> dict | None:
        """None when the entries may flow, else the veto with rail, reason and
        every input number the decision stands on. Measured against
        last_marked — the marked equity the most recent settle or bar-close
        mark established — because the entry the rails judge is about to sit
        in the same marked world. Ordering: the kill-switch outranks the
        daily limit outranks the cooldown — the most terminal rail explains
        itself first."""
        marked = self.last_marked
        self._roll_day(now_s, marked)
        if self.kill_tripped:
            return {
                "rail": RAIL_KILL_SWITCH,
                "reason": RAIL_KILL_SWITCH,
                "inputs": {
                    "peak_equity": round(self.peak_equity, 6),
                    "equity_marked": round(marked, 6),
                    "drawdown_pct": round(
                        (self.peak_equity - marked) / self.peak_equity, 6
                    )
                    if self.peak_equity > 0
                    else 0.0,
                    "killswitch_dd_pct": self.killswitch_dd_pct,
                },
            }
        if self.daily_breached or self._daily_breach_now(marked):
            self.daily_breached = True  # breach discovered at entry time latches too
            return {
                "rail": RAIL_DAILY_LOSS,
                "reason": RAIL_DAILY_LOSS,
                "inputs": self._daily_loss_inputs(marked),
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
    def snapshot(self, now_s: float) -> dict:
        """Dashboard-friendly rail state — the same numbers the verdicts are
        made of (the marked curve), read-only."""
        marked = self.last_marked
        self._roll_day(now_s, marked)
        drawdown = (
            (self.peak_equity - marked) / self.peak_equity if self.peak_equity > 0 else 0.0
        )
        loss = self.day_start_equity - marked
        limit = self.day_start_equity * self.daily_loss_pct if self.day_start_equity > 0 else 0.0
        return {
            "equity": round(marked, 6),
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
