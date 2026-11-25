"""ATR trailing-stop + time-stop helpers — pure functions, stdlib only.

Never raises: every function catches all exceptions internally and returns
a safe default. No I/O, no DB, no globals.
"""

import datetime as dt


def _to_epoch_seconds(v):
    """Best-effort timestamp -> float seconds. Returns None if unparseable."""
    try:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, dt.datetime):
            t = v
            if t.tzinfo is None:
                t = t.replace(tzinfo=dt.timezone.utc)
            return t.timestamp()
        if isinstance(v, dt.date):
            t = dt.datetime(v.year, v.month, v.day, tzinfo=dt.timezone.utc)
            return t.timestamp()
        # numeric string?
        return float(v)
    except Exception:
        return None


def time_stop_bars(close_time, open_time, tf_minutes, max_bars) -> bool:
    """True when a position has been open for >= max_bars bars (time to exit).

    bars_elapsed = (close_time - open_time) / (tf_minutes * 60).
    Returns False on ANY invalid input (None, bad types, tf_minutes <= 0,
    max_bars <= 0, close before open). Never raises.
    """
    try:
        ct = _to_epoch_seconds(close_time)
        ot = _to_epoch_seconds(open_time)
        tf = float(tf_minutes)
        mb = float(max_bars)
        if ct is None or ot is None:
            return False
        if not (tf > 0) or not (mb > 0):
            return False
        elapsed_bars = (ct - ot) / (tf * 60.0)
        if elapsed_bars != elapsed_bars:  # NaN guard
            return False
        return elapsed_bars >= mb
    except Exception:
        return False


def trailing_level(side, entry, atr, mult) -> float:
    """ATR stop price anchored at a reference price (entry, or favourable extreme).

    long  -> entry - atr * mult  (stop sits below the reference)
    short -> entry + atr * mult  (stop sits above the reference)

    Ratcheting: re-call with the best favourable price seen so far as
    ``entry`` (highest high for longs, lowest low for shorts) and only
    ever move the stored stop towards profit.

    Invalid side/entry returns entry when numeric else 0.0; non-positive
    atr or mult returns entry unchanged. Never raises.
    """
    try:
        px = float(entry)
    except Exception:
        return 0.0
    try:
        if px != px:  # NaN entry
            return 0.0
        a = float(atr)
        m = float(mult)
        if not (a > 0) or not (m > 0):
            return px
        s = str(side).strip().lower() if side is not None else ""
        if s in ("long", "l", "buy"):
            return px - a * m
        if s in ("short", "s", "sell"):
            return px + a * m
        return px
    except Exception:
        try:
            return float(entry)
        except Exception:
            return 0.0
