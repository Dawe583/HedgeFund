"""ML pipeline v1 — dependency-light (numpy only).

Flow:
1. dataset from engineered features + triple-barrier labels
2. walk-forward training of a logistic model per fold (strictly causal)
3. probability calibration (10-bin isotonic-style on OOS data)
4. champion/challenger promotion gates -> ModelVersion registry
5. feature drift monitor (Population Stability Index)

The trained gate is used upstream: trade only if calibrated p >= threshold.
"""

from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd
from sqlalchemy import select

from trading.features import make_labels
from trading.models import ModelVersion

log = logging.getLogger(__name__)

FEATURES = [
    "ret_1",
    "ret_8",
    "ret_32",
    "ema_sep",
    "rsi",
    "atr_pct",
    "rvol",
    "vol_z",
    "trend_strength",
    "body_pct",
    "range_pos",
]


# --------------------------------------------------------------------- model


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


class LogitModel:
    """Plain logistic regression, full-batch Adam, deterministic."""

    def __init__(self, l2: float = 1e-3, lr: float = 0.05, epochs: int = 400):
        self.l2, self.lr, self.epochs = l2, lr, epochs
        self.w: np.ndarray | None = None
        self.mean = np.zeros(0)
        self.std = np.ones(0)
        self.calib_edges = np.linspace(0, 1, 11)
        self.calib_map = np.linspace(0, 1, 11)

    def _prep(self, X: np.ndarray, fit: bool) -> np.ndarray:
        Xf = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        if fit:
            self.mean = Xf.mean(axis=0)
            self.std = Xf.std(axis=0) + 1e-9
        return (Xf - self.mean) / self.std

    def fit(self, X: np.ndarray, y: np.ndarray):
        Xs = self._prep(X, fit=True)
        n, d = Xs.shape
        Xb = np.hstack([Xs, np.ones((n, 1))])
        rng = np.random.default_rng(7)
        self.w = rng.normal(0, 0.01, d + 1)
        m = v = np.zeros_like(self.w)
        for t in range(1, self.epochs + 1):
            p = _sigmoid(Xb @ self.w)
            grad = Xb.T @ (p - y) / n + self.l2 * self.w
            m = 0.9 * m + 0.1 * grad
            v = 0.999 * v + 0.001 * grad**2
            self.w -= self.lr * m / (np.sqrt(v / (1 - 0.999**t)) + 1e-8)
        return self

    def predict_proba_raw(self, X: np.ndarray) -> np.ndarray:
        assert self.w is not None
        Xs = self._prep(X, fit=False)
        return _sigmoid(np.hstack([Xs, np.ones((len(Xs), 1))]) @ self.w)

    # ---------------------------------------------------------- calibration
    def fit_calibration(self, probs: np.ndarray, y: np.ndarray, bins: int = 10):
        edges = np.quantile(probs, np.linspace(0, 1, bins + 1))
        edges[0], edges[-1] = 0.0, 1.0
        idx = np.clip(np.digitize(probs, edges[1:-1]), 0, bins - 1)
        mapping = np.zeros(bins)
        for b in range(bins):
            mask = idx == b
            mapping[b] = (
                y[mask].mean() if mask.sum() >= 5 else probs[mask].mean() if mask.sum() else 0.5
            )
        self.calib_edges = edges
        self.calib_map = np.clip(mapping, 0.01, 0.99)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        raw = self.predict_proba_raw(X)
        idx = np.clip(np.digitize(raw, self.calib_edges[1:-1]), 0, len(self.calib_map) - 1)
        return self.calib_map[idx]


def build_dataset(feats: pd.DataFrame, horizon: int = 6, rr: float = 1.5):
    labels = make_labels(feats, horizon=horizon, rr=rr)
    X = feats[FEATURES].to_numpy(dtype=float)
    y_long = (labels == 1).to_numpy(dtype=float)[96:]
    X = X[96:]
    # learn "long wins" as primary target; short setups are the mirrored case
    return X[:-horizon], y_long[:-horizon]


def walk_forward_train(
    X: np.ndarray,
    y: np.ndarray,
    n_folds: int = 4,
    embargo: int = 24,
) -> dict:
    """Causal WF: train on [0, k), test on [k+embargo, k+embargo+step)."""
    size = len(X) // (n_folds + 1)
    fold_metrics = []
    models = []
    for k in range(1, n_folds + 1):
        cut = size * k
        test_lo, test_hi = cut + embargo, min(cut + embargo + size, len(X))
        if test_hi - test_lo < 50:
            continue
        m = LogitModel()
        m.fit(X[:cut], y[:cut])
        # calibration on the last 20% of the train window (still causal)
        raw = m.predict_proba_raw(X[max(0, cut - size // 5) : cut])
        m.fit_calibration(raw, y[max(0, cut - size // 5) : cut])
        p = m.predict_proba(X[test_lo:test_hi])
        preds = (p >= 0.5).astype(float)
        acc = float((preds == y[test_lo:test_hi]).mean())
        long_mask = preds == 1
        prec = float(y[test_lo:test_hi][long_mask].mean()) if long_mask.any() else 0.0
        fold_metrics.append(
            {"fold": k - 1, "accuracy": round(acc, 4), "precision_long": round(prec, 4)}
        )
        models.append(m)
    return {"folds": fold_metrics, "models": models}


def psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index — >0.25 signals material drift."""
    edges = np.quantile(expected, np.linspace(0, 1, bins + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    e = np.histogram(expected, bins=edges)[0] / max(len(expected), 1)
    a = np.histogram(actual, bins=edges)[0] / max(len(actual), 1)
    e, a = np.clip(e, 1e-6, None), np.clip(a, 1e-6, None)
    return float(((a - e) * np.log(a / e)).sum())


# ------------------------------------------------------------------ registry


def promote(session_factory, name: str, wf: dict, train_window_days: int, notes: str = "") -> bool:
    """Champion/challenger gate: challenger must beat champion accuracy.

    The final fold's model weights are serialized into the ModelVersion row so
    a restarted worker can load the champion without retraining.
    """
    acc = float(np.mean([f["accuracy"] for f in wf["folds"]]))
    prec = float(np.mean([f["precision_long"] for f in wf["folds"]]))
    weights_blob = serialize(wf["models"][-1]) if wf.get("models") else None

    session = session_factory()
    try:
        champ = (
            session.execute(
                select(ModelVersion)
                .where(ModelVersion.is_champion.is_(True))
                .order_by(ModelVersion.version.desc())
            )
            .scalars()
            .first()
        )

        if champ is not None and acc <= champ.oos_accuracy:
            session.add(
                ModelVersion(
                    name=champ.name,
                    version=champ.version + 1,
                    train_window_days=train_window_days,
                    oos_accuracy=acc,
                    oos_precision_long=prec,
                    is_champion=False,
                    notes=f"rejected {notes} — below champion {champ.oos_accuracy:.4f}",
                    weights_blob=weights_blob,
                )
            )
            session.commit()
            log.info(
                "challenger v%d rejected (%.4f <= %.4f)", champ.version + 1, acc, champ.oos_accuracy
            )
            return False

        version = (champ.version + 1) if champ else 1
        if champ:
            champ.is_champion = False
        session.add(
            ModelVersion(
                name=name,
                version=version,
                train_window_days=train_window_days,
                oos_accuracy=acc,
                oos_precision_long=prec,
                is_champion=True,
                notes=f"promoted {notes}",
                weights_blob=weights_blob,
            )
        )
        session.commit()
        log.info("model %s v%d PROMOTED acc=%.4f prec=%.4f", name, version, acc, prec)
        return True
    finally:
        session.close()


def serialize(m: LogitModel) -> str:
    return json.dumps(
        {
            "w": m.w.tolist(),
            "mean": m.mean.tolist(),
            "std": m.std.tolist(),
            "calib_edges": m.calib_edges.tolist(),
            "calib_map": m.calib_map.tolist(),
            "features": FEATURES,
        }
    )


def deserialize(blob: str) -> LogitModel:
    """Rebuild a LogitModel from a ModelVersion.weights_blob payload."""
    data = json.loads(blob)
    m = LogitModel()
    m.w = np.asarray(data["w"], dtype=float)
    m.mean = np.asarray(data["mean"], dtype=float)
    m.std = np.asarray(data["std"], dtype=float)
    m.calib_edges = np.asarray(data["calib_edges"], dtype=float)
    m.calib_map = np.asarray(data["calib_map"], dtype=float)
    return m
