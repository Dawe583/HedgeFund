"""Process-level supervision for the paper desk — ported from the legacy
`trading/paper.py` worker, small and correct as it was.

Two mechanisms, both honest about what they protect:

1. The flock guard keeps exactly one desk process alive against the database.
   Two desks trading the same book is not redundancy, it is double sizing.
2. The stale-feed predicate measures how long the desk has gone without a
   bar against the wall clock. Bars are the only execution-relevant data the
   desk consumes; a feed that stops delivering them is a dead venue, and
   trading against it is trading blind. Detection only — the reaction
   (flatten, alert, restart) is the supervisor's decision, not the guard's.
"""

from __future__ import annotations

import fcntl
import time
from pathlib import Path

from trading.config import get_settings

LOCK_NAME = "desk-worker.lock"


def acquire_worker_lock(lock_dir: Path | None = None):
    """Single-worker guard: flock on <data_dir>/desk-worker.lock.

    Returns the open file object on success — the lock lives exactly as long
    as the file object does, so the caller must keep it referenced for the
    process lifetime. Returns None when another worker holds the lock.
    """
    path = lock_dir or Path(get_settings().data_dir)
    path.mkdir(parents=True, exist_ok=True)
    lock_path = path / LOCK_NAME
    fh = open(lock_path, "w")  # noqa: SIM115 — held for the process lifetime
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    return fh


class FeedHealth:
    """Wall-clock staleness tracking for the desk's bar stream.

    `beat()` is called by the desk on every bar close. `stale()` answers the
    only question that matters operationally: has the feed been silent longer
    than the timeout allows? The timeout is a multiple of the bar interval —
    anything shorter is noise, anything much longer is a corpse.
    """

    def __init__(self, timeout_s: float, clock=time.monotonic):
        self._timeout_s = timeout_s
        self._clock = clock
        self._last_beat: float | None = None

    def beat(self) -> None:
        self._last_beat = self._clock()

    def stale(self) -> bool:
        if self._last_beat is None:
            return True  # a feed that never delivered is stale by definition
        return (self._clock() - self._last_beat) > self._timeout_s
