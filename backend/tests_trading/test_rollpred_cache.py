"""The rolling-prediction cache's prefix-resume contract, written before
the implementation: an extended frame must produce BIT-IDENTICAL predictions
to a full recompute, because every feature is backward-looking and the
retrain schedule keys on absolute position. The artifact carries the final
model and the schedule cursor, so resuming from the artifact's length is
the same computation, not an approximation of it."""

import numpy as np
import pandas as pd

from trading.features import build_features
from trading.ml_rolling import rolling_predictions, rolling_predictions_cached


def _frame(n: int, seed: int = 42) -> pd.DataFrame:
    """n rows of synthetic OHLCV — CRITICALLY, the first k rows are invariant
    in n: a longer frame is a strict extension of a shorter one, the way a
    candle tape grows. Drawing every column at full length first and slicing
    afterwards is what makes that true; an rng consumed column-by-column at
    length n produces different prefixes at different n, which is a fixture
    bug that reads exactly like a lookahead in the code under test."""
    total = _FRAME_MAX_ROWS
    rng = np.random.default_rng(seed)
    close = np.cumsum(rng.normal(0, 30, total)) + 50_000
    high = close * (1 + np.abs(rng.normal(0, 0.002, total)))
    low = close * (1 - np.abs(rng.normal(0, 0.002, total)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    vol = np.abs(rng.normal(1000, 200, total))
    idx = pd.date_range("2026-01-01", periods=total, freq="1h", tz="UTC")
    raw = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    ).iloc[:n]
    return build_features(raw)


_FRAME_MAX_ROWS = 400


# small shapes keep the test in seconds — the contract is scale-free
W, C, H = 120, 24, 6


def test_extended_frame_yields_identical_predictions(tmp_path, monkeypatch):
    """The prefix-resume contract: cache on n, extend by k, recompute —
    every prediction the length of the frame must match the full-run
    predictions exactly, and the overlap must match the cached prefix."""
    monkeypatch.setattr("trading.ml_rolling.CACHE_DIR", tmp_path)
    base = _frame(W + H + 96)
    preds_base = rolling_predictions_cached(
        base, "TESTUSDT", "1h", horizon=H, window=W, cadence=C
    )
    assert preds_base.notna().any(), "fixture must produce some predictions"

    extended = _frame(W + H + 96 + 48)  # same seed: the first rows coincide
    resumed = rolling_predictions_cached(
        extended, "TESTUSDT", "1h", horizon=H, window=W, cadence=C
    )
    full = rolling_predictions(extended, horizon=H, window=W, cadence=C)

    # bit-identity against the full recompute — the resume is the same
    # computation, not a faster approximation of one
    pd.testing.assert_series_equal(resumed, full)
    # and the cached prefix survives unchanged inside the extended series
    overlap = resumed.iloc[: len(base)].dropna()
    pd.testing.assert_series_equal(overlap, preds_base.dropna())


def test_repair_breaks_the_prefix_and_recomputes(tmp_path, monkeypatch):
    """A repaired candle inside the overlap invalidates the prefix: the
    resume must NOT fire and the artifact family must not serve the stale
    computation. Measured as different predictions, not as a cache miss
    implementation detail."""
    monkeypatch.setattr("trading.ml_rolling.CACHE_DIR", tmp_path)
    base = _frame(W + H + 96)
    preds_base = rolling_predictions_cached(
        base, "TESTUSDT", "1h", horizon=H, window=W, cadence=C
    )

    repaired = base.copy()
    # the repair must land inside a training window: row 10 precedes the first
    # window entirely, so a repair there honestly changes nothing — the model
    # never sees it. Row 130 sits inside the windows the retrains fit on.
    repair_row = 130
    repaired.iloc[repair_row, repaired.columns.get_loc("close")] *= 1.05
    preds_repaired = rolling_predictions_cached(
        repaired, "TESTUSDT", "1h", horizon=H, window=W, cadence=C
    )
    # downstream predictions must move — a silent reuse would be the F-8
    # failure all over again, one layer down
    assert not preds_repaired.dropna().equals(preds_base.dropna())


def test_small_extension_and_chained_resume_stay_bit_exact(tmp_path, monkeypatch):
    """Extensions smaller than the cadence, and resumes chained off resumed
    artifacts, are the same computation: the walker state travels with the
    artifact, so nothing about the schedule is ever reconstructed."""
    monkeypatch.setattr("trading.ml_rolling.CACHE_DIR", tmp_path)
    base = _frame(W + H + 96)
    rolling_predictions_cached(base, "TESTUSDT", "1h", horizon=H, window=W, cadence=C)

    small = _frame(W + H + 96 + 5)
    resumed_small = rolling_predictions_cached(small, "TESTUSDT", "1h", horizon=H, window=W, cadence=C)
    pd.testing.assert_series_equal(
        resumed_small, rolling_predictions(small, horizon=H, window=W, cadence=C)
    )

    larger = _frame(W + H + 96 + 40)
    resumed_large = rolling_predictions_cached(larger, "TESTUSDT", "1h", horizon=H, window=W, cadence=C)
    pd.testing.assert_series_equal(
        resumed_large, rolling_predictions(larger, horizon=H, window=W, cadence=C)
    )
    # eviction keeps exactly one family member regardless of the resume chain
    assert len(list(tmp_path.iterdir())) == 1
