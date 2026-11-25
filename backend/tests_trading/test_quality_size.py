"""Curve-shape + clamp tests for risk.quality_size_mult (pure, never raises)."""

import math

from trading.risk import quality_size_mult


def test_low_confidence_halved():
    for c in (0.0, 0.30, 0.45, 0.52, 0.59, -1.0, 2.0 - 1.5):
        assert quality_size_mult(c) == 0.5


def test_mid_band_ramps_075_to_100():
    assert quality_size_mult(0.60) == 0.75
    assert quality_size_mult(0.75) == 1.0
    mid = quality_size_mult(0.675)
    assert 0.75 < mid < 1.0
    # monotone inside band
    assert quality_size_mult(0.60) < quality_size_mult(0.68) < quality_size_mult(0.75)


def test_high_band_up_to_125():
    assert quality_size_mult(0.85) == 1.25
    assert quality_size_mult(0.90) == 1.25
    assert quality_size_mult(0.99) == 1.25
    at_08 = quality_size_mult(0.80)
    assert 1.0 < at_08 < 1.25
    # convex: upper-band slope (2.5) steeper than mid-band slope (~1.667)
    mid_slope = (quality_size_mult(0.75) - quality_size_mult(0.60)) / 0.15
    hi_slope = (quality_size_mult(0.85) - quality_size_mult(0.75)) / 0.10
    assert hi_slope > mid_slope > 0


def test_monotone_non_decreasing():
    confs = [0.0, 0.4, 0.59, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 1.0, 5.0]
    vals = [quality_size_mult(c) for c in confs]
    assert vals == sorted(vals)


def test_clamp_bounds():
    for c in (-100.0, 0.0, 0.6, 0.75, 0.9, 100.0):
        assert 0.4 <= quality_size_mult(c) <= 1.3


def test_never_raises_on_garbage():
    for bad in (None, "abc", float("nan"), float("inf"), float("-inf"), object()):
        assert quality_size_mult(bad) == 0.5
    # numeric strings still map
    assert quality_size_mult("0.7") == quality_size_mult(0.7)
    assert math.isfinite(quality_size_mult(True))
