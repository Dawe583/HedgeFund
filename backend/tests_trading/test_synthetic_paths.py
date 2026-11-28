"""Contract tests for the synthetic-path Monte Carlo tier. Written before
wiring: the resample must be continuous, causal, structurally faithful,
and reproducible — and the OHLC envelope must never lie to the kernel."""

import numpy as np
import pandas as pd

from trading.validation.synthetic_paths import (
    make_synthetic_ohlcv,
    stationary_bootstrap_indices,
    synthetic_path_mc,
)


def _tape(n: int = 400, seed: int = 7) -> pd.DataFrame:
    """A geometric random walk with vol clustering — enough structure that
    a broken resample has something to destroy."""
    rng = np.random.default_rng(seed)
    vol = 1.0 + np.sin(np.arange(n) / 30.0)  # slow vol cycle
    rets = rng.normal(0, 0.01, n) * vol
    close = 100.0 * np.exp(np.cumsum(rets))
    open_ = close / (1.0 + rng.normal(0, 0.002, n))
    span = np.abs(rng.normal(0.004, 0.002, n))
    high = np.maximum(open_, close) * (1 + span)
    low = np.minimum(open_, close) * (1 - span)
    idx = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close,
         "volume": rng.uniform(100, 900, n)},
        index=idx,
    )


class TestIndices:
    def test_positions_in_range_and_length(self):
        rng = np.random.default_rng(0)
        idx = stationary_bootstrap_indices(100, 100, 20, rng)
        assert len(idx) == 100
        assert idx.min() >= 0 and idx.max() < 100

    def test_reproducible_under_seed(self):
        a = stationary_bootstrap_indices(100, 100, 20, np.random.default_rng(5))
        b = stationary_bootstrap_indices(100, 100, 20, np.random.default_rng(5))
        assert (a == b).all()

    def test_block_structure_visible(self):
        # with a long mean block consecutive positions should often be
        # consecutive integers — the serial structure the tier exists for
        idx = stationary_bootstrap_indices(500, 200, 50, np.random.default_rng(3))
        runs = (np.diff(idx) == 1).mean()
        assert runs > 0.5, f"expected blocky resample, got {runs:.2f} consecutive share"


class TestSyntheticFrame:
    def test_envelope_never_violated(self):
        df = _tape()
        for seed in range(5):
            synth = make_synthetic_ohlcv(df, seed=seed)
            assert (synth["high"] >= synth["close"]).all()
            assert (synth["high"] >= synth["open"]).all()
            assert (synth["low"] <= synth["close"]).all()
            assert (synth["low"] <= synth["open"]).all()

    def test_close_chain_continuous(self):
        df = _tape()
        synth = make_synthetic_ohlcv(df, seed=1)
        # every close derives multiplicatively from the seed: log of the
        # ratio chain must be finite and the series strictly positive
        assert (synth["close"] > 0).all()
        assert np.isfinite(synth["close"]).all()

    def test_positive_levels(self):
        df = _tape()
        synth = make_synthetic_ohlcv(df, seed=2)
        for col in ("open", "high", "low", "close"):
            assert (synth[col] > 0).all(), col

    def test_reproducible_per_seed_distinct_across_seeds(self):
        df = _tape()
        a = make_synthetic_ohlcv(df, seed=9)
        b = make_synthetic_ohlcv(df, seed=9)
        c = make_synthetic_ohlcv(df, seed=10)
        pd.testing.assert_frame_equal(a, b)
        assert not a["close"].equals(c["close"])

    def test_volume_travels_with_source_bar(self):
        df = _tape()
        synth = make_synthetic_ohlcv(df, seed=4)
        # every synthetic volume value must exist somewhere in the real tape
        real_vals = set(np.round(df["volume"].to_numpy(), 8))
        assert set(np.round(synth["volume"].to_numpy(), 8)) <= real_vals

    def test_attrs_and_provenance(self):
        df = _tape()
        df.attrs["instrument_type"] = "perp"
        synth = make_synthetic_ohlcv(df, seed=1)
        assert synth.attrs["instrument_type"] == "perp"
        assert synth.attrs["synthetic"] is True

    def test_funding_column_bootstrapped_when_present(self):
        df = _tape()
        df["_funding_rate"] = np.linspace(-0.001, 0.001, len(df))
        synth = make_synthetic_ohlcv(df, seed=1)
        assert "_funding_rate" in synth.columns
        assert synth["_funding_rate"].abs().max() <= 0.001 + 1e-12


class TestMcContract:
    def test_error_on_missing_ohlcv(self):
        df = pd.DataFrame({"close": [1.0] * 50, "ret_1": [0.0] * 50})
        out = synthetic_path_mc(df, lambda: object(), None, "1h", n_simulations=2)
        assert "error" in out

    def test_input_validation(self):
        df = _tape()
        assert "error" in synthetic_path_mc(df, lambda: object(), None, "1h", n_simulations=1)
        assert "error" in synthetic_path_mc(df, lambda: object(), None, "1h", n_simulations=True)
