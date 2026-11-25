"""Request budget for OpenRouter's free tier.

The free tier caps *requests*, not tokens: 20/min always, and 50/day until the
account has ever bought $10 of credit, 1000/day after that. No choice of model
changes this — the cap is per account. So the desk cannot rely on "pick a
better model" to stay inside it; it has to spend the requests deliberately.

Two rules:

1. A hard ceiling, checked before the call goes out. Hitting the cap for real
   costs a 429 and a wasted round-trip in the trade path; declining locally
   costs nothing and lands on the same heuristic fallback.
2. Priority. Not every call is worth the same. The quant and reviewer gates sit
   between a signal and a real position, so they get the budget first; analyst
   commentary and forecasts are the first thing dropped as the day fills up.

Counters persist to disk so short-lived `cli cycle` invocations share one
budget with the long-running engine instead of each starting from zero.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import time
from pathlib import Path

try:  # POSIX only; the Pi and every deploy target has it
    import fcntl
except ImportError:  # pragma: no cover — Windows dev boxes
    fcntl = None  # type: ignore[assignment]

log = logging.getLogger(__name__)

# Fraction of the daily budget above which a given priority stops spending.
# High priority runs to the ceiling; the rest stand down early so the gates
# still have requests left late in the day.
RESERVE = {"high": 1.00, "normal": 0.80, "low": 0.50}


class RequestBudget:
    def __init__(self, path: Path, daily: int, rpm: int):
        self.path = path
        self.daily = max(0, daily)
        self.rpm = max(1, rpm)

    # ---- persistence -------------------------------------------------
    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except Exception:  # noqa: BLE001 — missing/corrupt: start a fresh day
            return {}

    def _save(self, state: dict) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Per-process temp name: a shared one lets two writers clobber each
            # other's file between write and replace, and the loser's replace()
            # then fails with ENOENT — the counter silently stops persisting.
            tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
            tmp.write_text(json.dumps(state))
            tmp.replace(self.path)
        except Exception as exc:  # noqa: BLE001 — accounting must never kill a trade
            log.warning("budget: could not persist (%s)", exc)
            with contextlib.suppress(Exception):
                tmp.unlink()

    @contextlib.contextmanager
    def _locked(self):
        """Serialise the read-modify-write across processes.

        The engine runs 24/7 while one-shot `cli cycle` runs land beside it, and
        they share one counter by design. Without a lock both read the same
        `used`, both write back +1, and one claim vanishes — the local count
        drifts under the provider's and the desk earns a real 429 instead of
        standing down cleanly.
        """
        if fcntl is None:  # pragma: no cover
            yield
            return
        lock = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Held open deliberately: the lock lives until the finally below.
            lock = open(self.path.with_name(f"{self.path.name}.lock"), "a+")  # noqa: SIM115
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        except Exception as exc:  # noqa: BLE001 — accounting must never kill a trade
            log.warning("budget: could not lock (%s) — proceeding unlocked", exc)
            if lock is not None:
                with contextlib.suppress(Exception):
                    lock.close()
            lock = None
        try:
            yield
        finally:
            if lock is not None:
                with contextlib.suppress(Exception):
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
                    lock.close()

    @staticmethod
    def _now() -> tuple[str, int]:
        t = time.gmtime()
        return time.strftime("%Y-%m-%d", t), int(time.time() // 60)

    def _current(self) -> dict:
        """State with the day and minute windows rolled forward."""
        day, minute = self._now()
        st = self._load()
        if st.get("day") != day:
            st = {"day": day, "used": 0, "minute": minute, "minute_used": 0}
        if st.get("minute") != minute:
            st["minute"] = minute
            st["minute_used"] = 0
        return st

    # ---- accounting --------------------------------------------------
    def take(self, priority: str = "normal") -> bool:
        """Claim one request. False means: skip the call, use the fallback."""
        with self._locked():
            st = self._current()
            cap = int(self.daily * RESERVE.get(priority, RESERVE["normal"]))
            if st["used"] >= cap:
                log.info(
                    "budget: %s call declined — %d/%d used today (cap %d at this priority)",
                    priority, st["used"], self.daily, cap,
                )
                self._save(st)
                return False
            if st["minute_used"] >= self.rpm:
                log.info(
                    "budget: %s call declined — %d req this minute", priority, st["minute_used"]
                )
                self._save(st)
                return False
            st["used"] += 1
            st["minute_used"] += 1
            self._save(st)
            return True

    def refund(self) -> None:
        """Give back a claim the request never actually spent (local failure)."""
        with self._locked():
            st = self._current()
            st["used"] = max(0, st["used"] - 1)
            st["minute_used"] = max(0, st["minute_used"] - 1)
            self._save(st)

    def exhaust_day(self) -> None:
        """The provider says the DAILY cap is gone — believe it over our count."""
        with self._locked():
            st = self._current()
            st["used"] = self.daily
            self._save(st)
        log.warning("budget: daily cap reached — standing down until UTC midnight")

    def exhaust_minute(self) -> None:
        """A transient 429 — the per-minute cap or an upstream `:free` throttle.

        Sits out the rest of the current minute only. `_current()` already zeroes
        `minute_used` when the wall clock rolls over, so this clears itself
        within 60s without any extra state — unlike standing the whole day down
        for something that resolves in seconds.
        """
        with self._locked():
            st = self._current()
            st["minute_used"] = max(st["minute_used"], self.rpm)
            self._save(st)
        log.warning("budget: provider throttled — pausing until the minute rolls over")

    def snapshot(self) -> dict:
        st = self._current()
        return {
            "day": st["day"],
            "used": st["used"],
            "daily_budget": self.daily,
            "remaining": max(0, self.daily - st["used"]),
            "rpm_budget": self.rpm,
        }
