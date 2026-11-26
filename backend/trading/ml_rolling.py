"""F12 — rolling-regime ML forecaster: the precompute half.

At bar t the model is retrained on the trailing window of W bars ending at
t - h (h = label horizon): no forward-looking label ever overlaps the
prediction boundary, the embargo is structural rather than procedural.
Between retrains (cadence C) the last-fitted model scores. Everything is
computed causally and written into one prediction series per (symbol,
timeframe, horizon, W, C) — cached as a parquet research artifact, keyed
by content, deleted to invalidate.

The series joins onto the kernel's frame through the same inject_frame
discipline F10 established: the bot reads `_ml_pred` and `_ml_pred_z` at
the current bar, nothing else, so backtest and paper can never diverge
in what the model saw.
"""

from __future__ import annotations

import hashlib
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from trading.ml_forecast import FEATURES


def rolling_predictions(
    df: pd.DataFrame,
    *,
    horizon: int = 6,
    window: int = 2000,
    cadence: int = 24,
) -> pd.Series:
    """Causal rolling-retrained predictions for one symbol's feature frame.

    Returns a series aligned to df.index; rows before the first full
    training window carry NaN — the model honestly does not exist yet.
    Training labels are forward returns computed INSIDE the training
    window only: the window's last h rows are unusable as labels (their
    forward returns reach past the boundary) and are excluded from fitting
    — the embargo is in the data, not in a promise."""
    from sklearn.ensemble import HistGradientBoostingRegressor

    d = df.dropna(subset=FEATURES)
    close = df["close"]
    n = len(df)
    preds = pd.Series(np.nan, index=df.index, dtype=float)

    model = None
    trained_through = -1
    fwd_all = close.shift(-horizon) / close - 1.0

    for pos in range(window + horizon, n):
        if model is None or pos - trained_through >= cadence:
            # fit on rows [pos-window-horizon, pos-horizon): labels for these
            # rows resolve strictly before pos — the embargo, structurally
            lo = max(0, pos - window - horizon)
            hi = pos - horizon
            train_slice = d.loc[(d.index >= df.index[lo]) & (d.index < df.index[hi])]
            if len(train_slice) < window // 2:
                continue
            X = train_slice[FEATURES].values
            y = fwd_all.reindex(train_slice.index).values
            valid = np.isfinite(y)
            if valid.sum() < len(y) * 0.8:
                continue
            model = HistGradientBoostingRegressor(max_iter=200, max_depth=3, learning_rate=0.06)
            model.fit(X[valid], y[valid])
            trained_through = pos
        row = df.iloc[pos]
        try:
            x = [float(row[f]) for f in FEATURES]
        except (KeyError, TypeError, ValueError):
            continue
        if not all(np.isfinite(x)):
            continue
        preds.iloc[pos] = float(model.predict([x])[0])
    return preds


CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "ml_artifacts"


def rolling_predictions_cached(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    *,
    horizon: int = 6,
    window: int = 2000,
    cadence: int = 24,
) -> pd.Series:
    """File-cached rolling predictions — a deterministic function of
    (candles, config), so the cache is a research artifact: delete to
    invalidate, never a module global. The key covers the config and the
    frame's own hash, so new candles produce a new artifact rather than a
    stale hit."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    frame_hash = hashlib.sha256(
        (str(df.index[0]) + str(df.index[-1]) + str(len(df))).encode()
    ).hexdigest()[:10]
    key = f"rollpred-{symbol.lower()}-{timeframe}-h{horizon}-w{window}-c{cadence}-{frame_hash}.pkl"
    path = CACHE_DIR / key
    if path.exists():
        with open(path, "rb") as fh:
            return pickle.load(fh)
    preds = rolling_predictions(df, horizon=horizon, window=window, cadence=cadence)
    with open(path, "wb") as fh:
        pickle.dump(preds, fh)
    return preds
