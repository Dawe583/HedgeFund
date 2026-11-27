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
    preds = pd.Series(np.nan, index=df.index, dtype=float)
    preds, _model, _trained = _walk(
        df, horizon=horizon, window=window, cadence=cadence,
        preds=preds, start=window + horizon, model=None, trained_through=-1,
    )
    return preds


def _walk(
    df: pd.DataFrame,
    *,
    horizon: int,
    window: int,
    cadence: int,
    preds: pd.Series,
    start: int,
    model,
    trained_through: int,
):
    """The rolling-retrain loop as a resumable walker: given the terminal
    state of a previous walk (predictions, final model, schedule cursor),
    continuing it produces bit-identical output to an uninterrupted run.
    Exactness is structural, not approximate: the retrain schedule keys on
    absolute positions, training windows reach only backwards, and every
    feature is backward-looking — state at any position is a function of
    data strictly before it, so an extended frame replays identically over
    the overlap.

    Returns (preds, model, trained_through) — the terminal state a later
    walk resumes from."""
    from sklearn.ensemble import HistGradientBoostingRegressor

    d = df.dropna(subset=FEATURES)
    close = df["close"]
    n = len(df)
    fwd_all = close.shift(-horizon) / close - 1.0

    for pos in range(start, n):
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
    return preds, model, trained_through


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
    invalidate, never a module global. The key is CONTENT-keyed: the
    digest covers every value of the frame the computation consumed, so
    repaired candles — even holes of equal length — produce a new key
    instead of a stale hit (the F-8 failure the old position-keyed hash
    structurally could not see). Writing evicts same-config predecessors:
    they are the pre-repair computation and must not survive."""
    from trading.cacheutil import artifact_file, frame_digest, write_artifact

    digest = frame_digest(df)
    stem = f"rollpred-{symbol.lower()}-{timeframe}-h{horizon}-w{window}-c{cadence}"
    path = artifact_file(CACHE_DIR, stem, digest)
    if path.exists():
        with open(path, "rb") as fh:
            payload = pickle.load(fh)
        # exact-hit artifacts are the predictions alone in every format
        return payload["preds"] if isinstance(payload, dict) else payload

    # prefix-resume: the computation is causal per position and the retrain
    # schedule keys on absolute positions, so a cached artifact whose frame
    # is a strict prefix of this one IS the first n0 rows of the answer —
    # bit-identically. The artifact carries the walk's terminal state
    # (final model, schedule cursor), so resuming replays the uninterrupted
    # run exactly. This is what makes hourly ingestion affordable: appending
    # bars stops invalidating hours of retraining.
    best = None  # (n_rows, payload)
    if CACHE_DIR.exists():
        import re as _re
        pattern = _re.compile(
            _re.escape(stem) + r"-[0-9a-f]{16}\.pkl$"
        )
        for cand in CACHE_DIR.iterdir():
            if not pattern.match(cand.name):
                continue
            try:
                with open(cand, "rb") as fh:
                    payload = pickle.load(fh)
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue  # legacy format: no terminal state, cannot resume
            n0 = int(payload["n_rows"])
            if n0 >= len(df) or n0 < window + horizon + 1:
                continue  # not a strict prefix, or too short to matter
            if best is not None and n0 <= best[0]:
                continue  # a longer prefix already won
            if frame_digest(df.iloc[:n0]) == payload["digest"]:
                best = (n0, payload)

    if best is not None:
        n0, payload = best
        preds = pd.Series(np.nan, index=df.index, dtype=float)
        preds.iloc[:n0] = payload["preds"].to_numpy()
        preds, model, trained = _walk(
            df, horizon=horizon, window=window, cadence=cadence,
            preds=preds, start=n0,
            model=payload["model"], trained_through=payload["trained_through"],
        )
    else:
        preds = pd.Series(np.nan, index=df.index, dtype=float)
        preds, model, trained = _walk(
            df, horizon=horizon, window=window, cadence=cadence,
            preds=preds, start=window + horizon, model=None, trained_through=-1,
        )

    write_artifact(
        CACHE_DIR, stem, digest,
        {
            "preds": preds,
            "n_rows": len(df),
            "digest": digest,
            "model": model,
            "trained_through": trained,
        },
    )
    return preds
