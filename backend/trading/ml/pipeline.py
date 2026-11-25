"""Retraining pipeline — shared by CLI `train` and the weekly auto-scheduler."""

from __future__ import annotations

import logging

import numpy as np

from trading.features import build_features, candles_to_df
from trading.ml.train import (
    FEATURES,
    build_dataset,
    promote,
    psi,
    serialize,
    walk_forward_train,
)
from trading.models import ModelVersion
from trading.storage import load_candles_df

log = logging.getLogger(__name__)

TF_DAYS_PER_BAR = {"5m": 5 / 1440, "15m": 15 / 1440, "1h": 1 / 24, "4h": 4 / 24}

TF_CONFIG: dict[str, dict] = {
    "1m": {"horizon": 3, "folds": 4, "min_bars": 5000, "threshold": 0.58},
    "1h": {"horizon": 4, "folds": 4, "min_bars": 1200, "threshold": 0.55},
    "4h": {"horizon": 6, "folds": 4, "min_bars": 800, "threshold": 0.55},
}


def _load_feats(session_factory, symbol: str, timeframe: str):
    session = session_factory()
    try:
        raw = load_candles_df(session, symbol.upper(), timeframe)
    finally:
        session.close()
    if len(raw) < 800:
        raise RuntimeError(f"not enough data ({len(raw)} bars) — run backfill first")
    rows = candles_to_df(
        [
            {
                "open_time": i,
                "open": r["open"],
                "high": r["high"],
                "low": r["low"],
                "close": r["close"],
                "volume": r["volume"],
            }
            for i, r in raw.iterrows()
        ]
    )
    return build_features(rows), len(raw)


async def retrain_with_supervision(
    session_factory,
    supervisor_agent=None,
    symbol: str = "BTCUSDT",
    timeframe: str = "4h",
    horizon: int = 6,
    folds: int = 4,
) -> dict:
    """Full cycle: dataset → WF training → promotion gate → PSI drift → supervisor insight."""
    from sqlalchemy import select

    from trading.agents.base import save_insight

    feats, n_bars = _load_feats(session_factory, symbol, timeframe)
    X, y = build_dataset(feats, horizon=horizon)
    wf = walk_forward_train(X, y, n_folds=folds)
    if not wf["models"]:
        raise RuntimeError("walk-forward produced no models")

    acc = float(np.mean([f["accuracy"] for f in wf["folds"]]))
    prec = float(np.mean([f["precision_long"] for f in wf["folds"]]))

    # drift: last-quarter feature distribution vs training window (on trend_strength proxy)
    ts_col = feats[FEATURES[7]].dropna().to_numpy()  # vol_z index in FEATURES
    split = int(len(ts_col) * 0.75)
    psi_val = psi(ts_col[:split], ts_col[split:])

    name = f"gate-{symbol}-{timeframe}"
    days = max(1, int(n_bars * TF_DAYS_PER_BAR.get(timeframe, 1 / 24)))
    promoted = promote(session_factory, name, wf, train_window_days=days)

    # champion history for context
    session = session_factory()
    try:
        champs = (
            session.execute(
                select(ModelVersion).where(ModelVersion.name == name).order_by(ModelVersion.version)
            )
            .scalars()
            .all()
        )
        champions = [
            f"v{m.version}:{'champ' if m.is_champion else 'rej'}({m.oos_accuracy:.3f})"
            for m in champs
        ]
    finally:
        session.close()

    folds_table = "\n".join(
        f"fold {f['fold']}: acc={f['accuracy']:.4f} prec_long={f['precision_long']:.4f}"
        for f in wf["folds"]
    )
    ctx = {
        "folds_table": folds_table,
        "mean_accuracy": round(acc, 4),
        "mean_precision": round(prec, 4),
        "psi": round(psi_val, 4),
        "promoted": promoted,
        "champions": ", ".join(champions),
    }

    insight = None
    if supervisor_agent is not None:
        try:
            insight = await supervisor_agent.run(ctx)
        except Exception:
            log.exception("supervisor agent failed")
    if insight is None:
        from trading.agents.supervisor import TrainingSupervisor

        insight = TrainingSupervisor(None).fallback(ctx)
    save_insight(session_factory, insight)

    result = {
        "promoted": promoted,
        "accuracy": round(acc, 4),
        "precision_long": round(prec, 4),
        "psi": round(psi_val, 4),
        "insight_title": insight.title,
        "payload_bytes": len(serialize(wf["models"][-1])),
    }
    log.info("retrain done: %s", result)
    return result


async def retrain_all_timeframes(
    session_factory,
    supervisor_agent=None,
    symbol: str = "BTCUSDT",
) -> dict:
    """Retrain the champion gate for every TF in TF_CONFIG.

    Per-TF min_bars guard: a TF with too little history is skipped with a
    log line instead of failing the whole run. The supervisor insight is
    produced ONCE for all TFs — supervisor_agent is passed only to the
    last TF, earlier TFs get None (fallback insight, no extra LLM calls).
    Returns a dict mapping timeframe -> per-TF result (or {"skipped": ...}).
    """
    tfs = list(TF_CONFIG)
    out: dict = {}
    for i, tf in enumerate(tfs):
        cfg = TF_CONFIG[tf]
        try:
            session = session_factory()
            try:
                n_bars = len(load_candles_df(session, symbol.upper(), tf))
            finally:
                session.close()
        except Exception:
            log.exception("retrain %s: candle load failed — skipped", tf)
            out[tf] = {"skipped": "candle load failed"}
            continue
        if n_bars < cfg["min_bars"]:
            log.warning(
                "retrain %s: only %d bars < min_bars %d — skipped",
                tf,
                n_bars,
                cfg["min_bars"],
            )
            out[tf] = {"skipped": f"only {n_bars} bars < min_bars {cfg['min_bars']}"}
            continue
        is_last = i == len(tfs) - 1
        try:
            out[tf] = await retrain_with_supervision(
                session_factory,
                supervisor_agent if is_last else None,
                symbol=symbol,
                timeframe=tf,
                horizon=cfg["horizon"],
                folds=cfg["folds"],
            )
        except Exception:
            log.exception("retrain %s failed — continuing with other TFs", tf)
            out[tf] = {"skipped": "retrain failed"}
    log.info("retrain_all_timeframes done: %s", {k: v.get("promoted", v) for k, v in out.items()})
    return out
