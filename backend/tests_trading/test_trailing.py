"""Tests for trailing.py (time_stop_bars, trailing_level) + vol_scaled_size."""

import datetime as dt
import math

from trading.trailing import time_stop_bars, trailing_level
from trading.risk import vol_scaled_size

T = dt.datetime(2026, 1, 1, 12, 0, 0, tzinfo=dt.timezone.utc)


def _add_minutes(t, m):
    return t + dt.timedelta(minutes=m)


# --- time_stop_bars ---

def test_time_stop_not_expired():
    assert time_stop_bars(_add_minutes(T, 5), T, 1, 10) is False


def test_time_stop_expired_exact():
    assert time_stop_bars(_add_minutes(T, 10), T, 1, 10) is True


def test_time_stop_expired_over():
    assert time_stop_bars(_add_minutes(T, 61), T, 15, 4) is True  # 4.06 bars


def test_time_stop_multi_timeframe():
    # 2h hold on 1h tf with max 3 bars -> not expired
    assert time_stop_bars(_add_minutes(T, 120), T, 60, 3) is False
    assert time_stop_bars(_add_minutes(T, 180), T, 60, 3) is True


def test_time_stop_close_before_open():
    assert time_stop_bars(T, _add_minutes(T, 5), 1, 10) is False


def test_time_stop_invalid_never_raises():
    assert time_stop_bars(None, T, 1, 10) is False
    assert time_stop_bars(T, None, 1, 10) is False
    assert time_stop_bars("junk", T, 1, 10) is False
    assert time_stop_bars(T, T, 0, 10) is False
    assert time_stop_bars(T, T, -5, 10) is False
    assert time_stop_bars(T, T, 1, 0) is False
    assert time_stop_bars(T, T, 1, -2) is False
    assert time_stop_bars(T, T, "x", "y") is False


def test_time_stop_epoch_numbers():
    assert time_stop_bars(600.0, 0.0, 1, 10) is True
    assert time_stop_bars(599.0, 0.0, 1, 10) is False


# --- trailing_level ---

def test_trailing_long():
    assert trailing_level("long", 100.0, 2.0, 3.0) == 94.0


def test_trailing_short():
    assert trailing_level("short", 100.0, 2.0, 3.0) == 106.0


def test_trailing_side_aliases():
    assert trailing_level("BUY", 100.0, 1.0, 1.0) == 99.0
    assert trailing_level("sell", 100.0, 1.0, 1.0) == 101.0


def test_trailing_ratchet_semantics():
    # re-anchor at favourable extreme: stop only moves toward profit
    first = trailing_level("long", 100.0, 2.0, 1.0)   # 98
    moved = trailing_level("long", 105.0, 2.0, 1.0)   # 103 > 98 -> ratchet up
    assert moved > first


def test_trailing_invalid_never_raises():
    assert trailing_level("long", 100.0, 0.0, 3.0) == 100.0
    assert trailing_level("long", 100.0, -1.0, 3.0) == 100.0
    assert trailing_level("long", 100.0, 2.0, 0.0) == 100.0
    assert trailing_level("???", 100.0, 2.0, 3.0) == 100.0
    assert trailing_level(None, 100.0, 2.0, 3.0) == 100.0
    assert trailing_level("long", "junk", 2.0, 3.0) == 0.0
    assert trailing_level("long", float("nan"), 2.0, 3.0) == 0.0


# --- vol_scaled_size ---

def test_vol_scaled_parity():
    assert vol_scaled_size(10_000, 3_000, 0.01, 0.01) == 3_000


def test_vol_scaled_high_vol_scales_down():
    assert vol_scaled_size(10_000, 3_000, 0.02, 0.01) == 1_500


def test_vol_scaled_low_vol_capped_at_2x_and_equity():
    assert vol_scaled_size(10_000, 3_000, 0.002, 0.01) == 6_000  # 5x -> clamp 2x
    assert vol_scaled_size(5_000, 4_000, 0.001, 0.01) == 5_000   # 2x=8000 -> equity cap


def test_vol_scaled_invalid_never_raises():
    for args in [(0, 100, 0.01, 0.01), (100, 0, 0.01, 0.01),
                 (100, 100, 0, 0.01), (100, 100, 0.01, 0),
                 (100, 100, -1, 0.01), (None, 1, 1, 1),
                 ("x", "y", "z", "w"), (float("nan"), 1, 1, 1)]:
        r = vol_scaled_size(*args)
        assert r == 0.0 and not math.isnan(r)
