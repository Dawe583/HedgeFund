"""ML forecaster training — the offline half of F9.

Trains a gradient-boosted regressor of forward returns on the causal
feature frame with embargoed walk-forward evaluation, and pickles the
model with its noise estimate and feature list. The noise estimate is
the out-of-fold RMSE: the bot's entry threshold is denominated in it,
so the artifact carries its own honesty scale.

Purged/embargoed splits: fold boundaries skip `embargo` bars on both
sides, where embargo >= the label horizon — a forward-looking label can
never overlap a training row's features across the boundary.
"""

from __future__ import annotations

import pickle

import numpy as np
import pandas as pd

FEATURES = ["ret_1", "ret_8", "ret_32", "ema_sep", "rsi", "atr_pct", "rvol", "vol_z", "regime", "trend_strength", "body_pct", "range_pos"]


def train_forecaster(
    df: pd.DataFrame,
    *,
    horizon: int = 6,
    n_splits: int = 5,
) -> dict:
    """Train and return the artifact dict: model, features, noise (out-of-fold
    RMSE), and the evaluation summary. `df` is the causal feature frame for
    ONE symbol — cross-sectional learning is a separate, later question."""
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.model_selection import TimeSeriesSplit

    d = df.dropna(subset=FEATURES).copy()
    fwd = d["close"].shift(-horizon) / d["close"] - 1.0
    d["_fwd"] = fwd
    d = d.dropna(subset=["_fwd"])
    if len(d) < 1000:
        raise SystemExit(f"need >= 1000 rows after warm-up, got {len(d)}")

    X = d[FEATURES].values
    y = d["_fwd"].values
    embargo = horizon * 2
    tscv = TimeSeriesSplit(n_splits=n_splits, gap=embargo)

    oof = np.full(len(d), np.nan)
    for train_idx, test_idx in tscv.split(X):
        model = HistGradientBoostingRegressor(max_iter=200, max_depth=3, learning_rate=0.06)
        model.fit(X[train_idx], y[train_idx])
        oof[test_idx] = model.predict(X[test_idx])

    valid = ~np.isnan(oof)
    noise = float(np.sqrt(np.mean((y[valid] - oof[valid]) ** 2)))
    corr = float(np.corrcoef(oof[valid], y[valid])[0, 1])

    final = HistGradientBoostingRegressor(max_iter=200, max_depth=3, learning_rate=0.06)
    final.fit(X, y)
    return {
        "model": final,
        "features": FEATURES,
        "noise": noise,
        "oof_corr": corr,
        "oof_rmse": noise,
        "horizon": horizon,
        "n_rows": len(d),
    }


def save_artifact(artifact: dict, path: str) -> None:
    with open(path, "wb") as fh:
        pickle.dump({k: v for k, v in artifact.items()}, fh)


def load_artifact(path: str) -> dict:
    with open(path, "rb") as fh:
        return pickle.load(fh)


# ------------------------------------------------------------- artifact cache

CACHE_DIR = __import__("pathlib").Path(__file__).resolve().parent.parent / "data" / "ml_artifacts"


def artifact_path(symbol: str, timeframe: str, horizon: int, digest: str) -> "object":
    """Content-keyed artifact path — digest is mandatory so no caller can
    ever construct the old data-blind key."""
    from trading.cacheutil import artifact_file

    stem = f"mlforecast-{symbol.lower()}-{timeframe}-h{horizon}"
    return artifact_file(CACHE_DIR, stem, digest)


def artifact_for(symbol: str, timeframe: str, research_db: str, *, horizon: int = 6) -> dict:
    """Load or train the symbol's artifact. Training is IN-SAMPLE ONLY —
    the out-of-sample window stays virgin for phase B, which is the whole
    point of the program. The artifact is cached beside the research db:
    it is a research artifact, not application state, and deleting it just
    costs a retrain. The cache key is content-keyed on the in-sample frame
    actually consumed — the old config-only key assumed the split date
    makes staleness impossible, which is false the moment in-sample candles
    are repaired or re-ingested (F-8). The frame load therefore precedes
    the lookup; the cache saves the training, not the read. Writing evicts
    same-config predecessors."""
    import pickle

    from trading.cacheutil import frame_digest, write_artifact
    from trading.search import in_sample, load_frame

    df = in_sample(load_frame(research_db, symbol, timeframe))
    digest = frame_digest(df)
    stem = f"mlforecast-{symbol.lower()}-{timeframe}-h{horizon}"
    path = artifact_path(symbol, timeframe, horizon, digest)
    if path.exists():
        with open(path, "rb") as fh:
            return pickle.load(fh)
    art = train_forecaster(df, horizon=horizon)
    art["symbol"] = symbol
    art["trained_through"] = str(df.index[-1])
    write_artifact(CACHE_DIR, stem, digest, art)
    return art
