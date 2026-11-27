"""The negative control — random entries as an INSTRUMENTATION control for
the paper plane, never alpha.

Why this exists: the operational plane (veto tape, divergence measurement,
reconciliation, lifecycle transitions) cannot be calibrated against zero
strategies — an empty roster produces zero evidence, and a measurement
system that has never run under load is an unproven measurement system.
This bot fixes that by construction: its entries depend on NOTHING in the
tape, so its expectations are known before it trades a single bar — zero
edge before costs, slightly negative after fees and slippage. Every
operational measurement taken against it is therefore calibrated: if the
veto tape, divergence accounting or reconciliation "discovers" edge in the
control, the measurement is broken, not the market.

It is registered through `trading.registry.register_control`, which carries
the declaration that this is instrumentation into every provenance surface.
It must never be promoted past paper: there is no alpha to approve.

Statelessness doctrine, resolved for a random control:

A stateful random bot would reboot with amnesia and contradict its own
book, the failure trend_bot.py's docstring names. But a random control has
an option trend does not: randomness needs no market memory, so each bar's
draw can be a pure function of (seed, bar-open timestamp) instead of
evaluation order. The uniforms come from uint64 mixing arithmetic done IN
NUMPY — the seeded numpy RNG contract — keyed to the timestamp, never to a
position in any frame: reproducible by construction, identical in backtest,
paper, and across restarts regardless of how much history the frame was
seeded with. The mixing is vectorized over whole frames, so the per-bar
cost is a scan, not a stream construction.

The entry/exit schedule is a renewal process: a hit (u1 < p_entry) becomes
an effective entry only while flat; the position is held exactly hold_bars
bars unless the protective stop/take-profit closes it first (the kernel
owns those brackets); at the expiry bar the bot emits flat, and expiry
takes precedence over a hit on the same bar. Because the strategy cannot
see the kernel's position state, it reconstructs the schedule by scanning
the frame forward from its first row on every call — O(frame length) cheap
comparisons per bar, bounded in practice by worker restarts.

Two honesty caveats, documented rather than hidden:

1. Frame-start boundary: entries that fired before the frame's first row
   are invisible to the reconstruction, so after a restart a hit that the
   pre-restart schedule would have blocked can fire one position early.
   The common case is absorbed by the kernel itself — a re-armed open
   position dedupes the entry to the recorded `in_position` outcome. The
   residual case (the pre-restart position was stopped out, and the scan
   cannot know) produces at most one slightly-early re-entry per restart.
   For an instrumentation control this is noise; for an alpha candidate it
   would be a defect, which is one more reason this pattern is control-only.

2. Protective exits interact with the renewal clock: when the wide stop or
   take-profit closes a position early, the strategy does not know, and at
   the next hit it re-enters — and if that hit lands inside the original
   hold window, the flat emission at the original expiry bar will close
   THAT position early too. Holds are therefore hold_bars-or-shorter when
   stops intervene. The defaults (stop_atr 3.0, tp_rr 3.0 — wide) make the
   timeout shape most exits, as intended; the corruption is bounded, random
   in sign, and part of the control's known-by-construction expectation.

Every number in the signal path is causal by construction — trivially,
because the draws depend on nothing but the clock and the seed.
"""

from __future__ import annotations

import numpy as np

from trading.backtest.engine import Signal
from trading.bots.base import BaseStrategy

#: The declaration every provenance surface carries. Registration writes it
#: into transition notes and the version's params; the class source (and
#: therefore its code_hash) carries it too.
CONTROL_DECLARATION = (
    "instrumentation control — expectations known by construction, never alpha; "
    "the validated state is a lifecycle formality for roster plumbing, not a verdict"
)

# uint64 mixing constants — the splitmix64 finalizer, fixed by specification,
# never tuned: the draws must be reproducible for the lifetime of the ledger.
_MASK = np.uint64(0xFFFFFFFFFFFFFFFF)
_M1 = np.uint64(0xBF58476D1CE4E5B9)
_M2 = np.uint64(0x94D049BB133111EB)
_U64SCALE = float(1 << 64)


def _mix64(x: np.ndarray) -> np.ndarray:
    """uint64 avalanche mixing, vectorized in numpy: xor-shift/multiply rounds
    strong enough that adjacent (seed, timestamp) keys produce independent
    uniforms — the seeded numpy RNG this control's reproducibility stands on."""
    x = x ^ (x >> np.uint64(30))
    x = x * _M1
    x = x ^ (x >> np.uint64(27))
    x = x * _M2
    x = x ^ (x >> np.uint64(31))
    return x


class RandomControl(BaseStrategy):
    """Random-entry instrumentation control. See the module docstring for
    the statelessness resolution — the draws are keyed to bar-open
    timestamps, never to evaluation order, so restarts reproduce the exact
    schedule."""

    name = "randomctl"
    timeframe = "1h"

    def __init__(
        self,
        seed: int = 42,
        p_entry: float = 1.0 / 24.0,
        hold_bars: int = 24,
        stop_atr: float = 3.0,
        tp_rr: float = 3.0,
        confidence: float = 0.6,
        declared_role: str = CONTROL_DECLARATION,
    ):
        # p_entry ~1/24: one hit per day at 1h bars on average — enough flow
        # to exercise veto tape, divergence budgets and reconciliation
        # continuously without dominating the book.
        # confidence 0.6: above the harness's default confidence_min (0.55)
        # so entries are not silently filtered into below_confidence — a
        # control that never enters measures nothing.
        # declared_role is NOT a trading parameter: it is the provenance
        # declaration traveling inside the registered version's params_json,
        # so every roster dump and divergence record restates what this is.
        self.seed = seed
        self.p_entry = p_entry
        self.hold_bars = hold_bars
        self.stop_atr = stop_atr
        self.tp_rr = tp_rr
        self.confidence = confidence
        self.declared_role = declared_role

    def _uniforms(self, df, upto: int) -> tuple[np.ndarray, np.ndarray]:
        """(hit-draw, direction-draw) per frame row 0..upto — pure functions
        of (seed, bar-open timestamp), vectorized over the whole scan in one
        shot. Two independently keyed mixes per bar so hit and direction do
        not correlate by construction."""
        ns = df.index[: upto + 1].asi8.astype(np.uint64)
        # python-int modular arithmetic for the key pre-mix: exact mod 2^64,
        # no scalar-overflow warnings; the vectorized mixing stays in numpy
        s = int(self.seed) % (1 << 64)
        base = ns ^ np.uint64((s * int(_M1)) % (1 << 64))
        u1 = _mix64(base).astype(np.float64) / _U64SCALE
        u2 = _mix64(base ^ np.uint64((s * int(_M2)) % (1 << 64))).astype(np.float64) / _U64SCALE
        return u1, u2

    def signal(self, i: int, df) -> Signal | None:
        # Never raises: the paper loop calls signal() on every bar including
        # warmup. The frame is truncated at i — but the draws would be
        # identical either way, since they read nothing but the clock.
        try:
            if df is None or len(df) == 0 or i >= len(df) or i < 0:
                return None
            u1, u2 = self._uniforms(df, i)
            in_pos = False
            expiry = -1
            entered = None  # (side) when row i is an effective entry
            exit_now = False
            for j in range(i + 1):
                if in_pos and j >= expiry:
                    in_pos = False
                    # expiry takes precedence: no entry on the expiry bar
                    if j == i:
                        exit_now = True
                    continue
                if in_pos:
                    continue
                if u1[j] < self.p_entry:
                    if j == i:
                        entered = "long" if u2[j] < 0.5 else "short"
                    in_pos = True
                    expiry = j + self.hold_bars
            if exit_now:
                # time-based exit — closes whatever the kernel holds in
                # either direction; nothing held means a recorded flat_noop,
                # the honest cost of statelessness
                return Signal(side="flat", confidence=self.confidence)
            if entered is not None:
                return Signal(
                    side=entered,
                    confidence=self.confidence,
                    stop_atr=self.stop_atr,
                    tp_rr=self.tp_rr,
                )
            return None
        except Exception:
            return None
