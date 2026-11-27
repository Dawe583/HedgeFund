"""The prediction track record — analysis F-7's instrument.

cmd_predict's forward-return measurement used to die on a terminal: scored
once, printed, forgotten — a measurement with no memory cannot ever be
checked against what happened, so the program's only forward-looking
instrument had no track record by construction. This module is the memory.

Two passes, each idempotent, each honest about what it cannot know:

- scan_predictions(): for every ML artifact on disk (frozen F9 pickles and
  rolling F12 series), score the artifact's latest state and commit one row
  per (symbol, timeframe, artifact_kind, bar_close_time) into the platform
  database's predictions table. PRECOMPUTED READS ONLY: an artifact is a
  file the offline research pipeline wrote; this module never trains, never
  retrains, never recomputes a rolling series — if the artifact is absent
  or not finite the series is skipped and the report says so.

- score_predictions(): for rows whose horizon has elapsed — the candle
  store already holds the bar the forward return resolves on — backfill
  outcome_return and correct_direction. A realized return of exactly zero
  is a tie: correct_direction stays NULL rather than tossing a coin.

Timing vocabulary, inherited from the feature frame: bar_close_time is the
anchor bar's OPEN time in the candle store's convention (the frame index is
open_time) — it names the bar the prediction stands ON. The outcome is the
close-to-close forward return over horizon_bars bars of that series,
exactly the label the models were trained on (close.shift(-h)/close - 1).

Where things live: candles come from the research database (bulky,
replaceable market data); predictions are written to the platform database
beside the rest of the trading state, because they are what the API serves.
The artifact dir is trading/ml_forecast.py's CACHE_DIR — same files, never
a copy.
"""

from __future__ import annotations

import datetime as dt
import logging
import math
import pickle
from pathlib import Path

import pandas as pd
from sqlalchemy import select

from trading.ml_forecast import CACHE_DIR as FROZEN_CACHE_DIR

log = logging.getLogger(__name__)

# The frozen artifacts predate the content-keyed naming and carry no digest;
# the rolling ones do. Both are matched by stem prefix, newest file first —
# the cache eviction discipline (cacheutil.write_artifact) guarantees the
# newest same-stem file is the one the freshest computation wrote, and a
# frozen artifact's staleness is a fact provenance reports (trained_through),
# never something the serving path hides or repairs.
FROZEN_STEM = "mlforecast-{sym}-{tf}-h{h}"
ROLLING_STEM = "rollpred-{sym}-{tf}-h{h}-w{w}-c{c}"

HORIZON = 6
ROLLING_WINDOW = 2000
ROLLING_CADENCE = 24

CAVEAT = (
    "a prediction is a measurement, not advice — the noise scale beside it "
    "is the artifact's own out-of-fold error, and trained_through is the "
    "last bar the model has ever seen"
)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


# ------------------------------------------------------------------ discovery


def discover_artifacts(cache_dir: Path | None = None) -> list[dict]:
    """Every ML artifact on disk, newest file per stem.

    Returns descriptor dicts: kind ('frozen'|'rolling'), symbol, timeframe,
    horizon, path. Symbols and timeframes are recovered from the filenames —
    the artifacts themselves are the registry; a file that does not match
    either naming scheme is not an artifact this module can vouch for."""
    cache_dir = cache_dir or FROZEN_CACHE_DIR
    out: list[dict] = []
    if not cache_dir.exists():
        return out
    import re

    frozen_re = re.compile(r"^mlforecast-([a-z0-9]+)-([a-z0-9]+)-h(\d+)(?:-[0-9a-f]{16})?\.pkl$")
    # the digest suffix is the content key cacheutil writes (16 hex today);
    # legacy artifacts on disk carry shorter digests from before the key
    # length was fixed — 8 to 16 hex chars are all accepted as a digest,
    # because the alternative is pretending a written artifact does not exist
    rolling_re = re.compile(r"^rollpred-([a-z0-9]+)-([a-z0-9]+)-h(\d+)-w(\d+)-c(\d+)(?:-[0-9a-f]{8,16})?\.pkl$")
    best: dict[tuple, tuple[float, dict]] = {}
    for path in sorted(cache_dir.iterdir()):
        m = frozen_re.match(path.name)
        kind = None
        if m:
            kind = "frozen"
            sym, tf, h = m.group(1).upper(), m.group(2), int(m.group(3))
        else:
            m = rolling_re.match(path.name)
            if m:
                kind = "rolling"
                sym, tf, h = m.group(1).upper(), m.group(2), int(m.group(3))
        if kind is None:
            continue
        key = (kind, sym, tf)
        mtime = path.stat().st_mtime
        desc = {
            "kind": kind,
            "symbol": sym,
            "timeframe": tf,
            "horizon": h,
            "path": path,
        }
        if key not in best or mtime > best[key][0]:
            best[key] = (mtime, desc)
    for _mtime, desc in sorted(best.values(), key=lambda t: (t[1]["symbol"], t[1]["kind"])):
        out.append(desc)
    return out


def _load_frame(research_db: str, symbol: str, timeframe: str) -> pd.DataFrame:
    """The causal feature frame for one series — trading.search.load_frame,
    the same loader cmd_predict uses, so scanner and terminal measure the
    same row."""
    from trading.search import load_frame

    return load_frame(research_db, symbol, timeframe)


def _naive(ts) -> dt.datetime:
    """SQLite returns naive UTC datetimes; pandas frames here are naive UTC
    too. Normalize to naive-UTC for storage and comparisons — the candle
    store's own convention, never a tz guess."""
    t = pd.Timestamp(ts)
    if t.tzinfo is not None:
        t = t.tz_convert("UTC").tz_localize(None)
    return t.to_pydatetime()


# ------------------------------------------------------------------ scanning


def scan_one(desc: dict, df: pd.DataFrame) -> dict | None:
    """Score one artifact against the frame's latest state. Returns the row
    payload, or None with the reason logged when the artifact honestly
    cannot speak (non-finite features on the last bar, warm-up incomplete).

    Frozen: the artifact dict's model scores the LAST feature row — the
    artifact is frozen, scoring is what it exists for. Rolling: the LAST
    non-NaN entry of the precomputed series — never a recompute. The rolling
    noise scale is the prediction series' own std (pred_series_std): the
    series is all the artifact carries, and inventing an out-of-fold RMSE
    it never recorded would be a worse lie than reporting the scale the
    evidence actually has. z_score denominates in that noise either way."""
    kind = desc["kind"]
    if df.empty:
        log.warning("scan: %s %s — empty frame, skipped", desc["symbol"], desc["timeframe"])
        return None

    if kind == "frozen":
        with open(desc["path"], "rb") as fh:
            art = pickle.load(fh)
        row = df.iloc[-1]
        x = []
        missing = []
        for f in art["features"]:
            v = float(row[f]) if f in row else float("nan")
            if not math.isfinite(v):
                missing.append(f)
            x.append(v)
        if missing:
            log.warning(
                "scan: %s %s frozen — features not finite on the last bar: %s",
                desc["symbol"], desc["timeframe"], missing,
            )
            return None
        pred = float(art["model"].predict([x])[0])
        noise = float(art["noise"])
        return {
            "symbol": desc["symbol"],
            "timeframe": desc["timeframe"],
            "artifact_kind": "frozen",
            "horizon_bars": int(art.get("horizon", desc["horizon"])),
            "predicted_return": pred,
            "noise": noise,
            "noise_basis": "oof_rmse",
            "z_score": pred / (noise + 1e-12),
            "oof_corr": float(art.get("oof_corr", 0.0)),
            "bar_close_time": _naive(df.index[-1]),
            "trained_through": str(art.get("trained_through", "")),
            "artifact_file": desc["path"].name,
        }

    # rolling — the precomputed series, its last finite entry
    with open(desc["path"], "rb") as fh:
        preds = pickle.load(fh)
    hist = preds.dropna()
    if hist.empty:
        log.warning("scan: %s %s rolling — warm-up incomplete, no prediction yet", desc["symbol"], desc["timeframe"])
        return None
    pred = float(hist.iloc[-1])
    noise = float(hist.std())
    if not math.isfinite(pred) or not math.isfinite(noise) or noise <= 0:
        log.warning("scan: %s %s rolling — non-finite prediction or degenerate noise", desc["symbol"], desc["timeframe"])
        return None
    return {
        "symbol": desc["symbol"],
        "timeframe": desc["timeframe"],
        "artifact_kind": "rolling",
        "horizon_bars": desc["horizon"],
        "predicted_return": pred,
        "noise": noise,
        "noise_basis": "pred_series_std",
        "z_score": pred / (noise + 1e-12),
        "oof_corr": None,
        "bar_close_time": _naive(hist.index[-1]),
        # the series carries no trained_through — the structural embargo
        # bound: training data ends at latest horizon_bars before the bar
        # being scored, by construction of the rolling fit
        "trained_through": f"embargoed: train end >= {desc['horizon']} bars before {hist.index[-1]}",
        "artifact_file": desc["path"].name,
    }


def scan_predictions(research_db: str, app_engine, *, cache_dir: Path | None = None) -> dict:
    """Scan every artifact, commit new prediction rows. Idempotent: a row
    whose (symbol, timeframe, artifact_kind, bar_close_time) already exists
    is the same measurement, not a new one. Returns a small report — the
    scan's own provenance."""
    from trading.models import Prediction, make_session_factory

    artifacts = discover_artifacts(cache_dir)
    report = {
        "scanned_at": _now().isoformat(),
        "artifacts_found": len(artifacts),
        "inserted": 0,
        "already_present": 0,
        "skipped": [],
        "rows": [],
    }
    if not artifacts:
        report["skipped"].append("no artifacts on disk — the offline ML pipeline has not produced any")
        return report

    frames: dict[tuple[str, str], pd.DataFrame] = {}
    for desc in artifacts:
        key = (desc["symbol"], desc["timeframe"])
        if key in frames:
            continue
        try:
            frames[key] = _load_frame(research_db, desc["symbol"], desc["timeframe"])
        except (SystemExit, Exception) as exc:  # load_frame raises SystemExit on empty stores
            report["skipped"].append(f"{desc['symbol']} {desc['timeframe']}: frame load failed — {exc}")
            frames[key] = pd.DataFrame()

    sf = make_session_factory(app_engine)
    with sf() as session:
        for desc in artifacts:
            df = frames.get((desc["symbol"], desc["timeframe"]))
            if df is None or df.empty:
                continue
            payload = scan_one(desc, df)
            if payload is None:
                report["skipped"].append(f"{desc['symbol']} {desc['timeframe']} {desc['kind']}: not finite or warm-up incomplete")
                continue
            exists = session.execute(
                select(Prediction.id).where(
                    Prediction.symbol == payload["symbol"],
                    Prediction.timeframe == payload["timeframe"],
                    Prediction.artifact_kind == payload["artifact_kind"],
                    Prediction.bar_close_time == payload["bar_close_time"],
                )
            ).first()
            if exists:
                report["already_present"] += 1
                continue
            session.add(Prediction(**payload))
            report["inserted"] += 1
            report["rows"].append({k: (str(v) if isinstance(v, dt.datetime) else v) for k, v in payload.items()})
        session.commit()
    return report


# ------------------------------------------------------------------ scoring


def score_predictions(research_db: str, app_engine) -> dict:
    """Backfill outcomes for predictions whose horizon has elapsed.

    The outcome is positional, not clock-arithmetic: the close of the candle
    exactly horizon_bars after the anchor bar in the stored series — the
    same indexing the training labels used. Missing future bars (the series
    is short, or a hole sits exactly there) leave the row UNSCORED: a hole
    in the tape is not evidence, and a clock-computed timestamp would score
    a different bar than the model was trained to predict."""
    from trading.models import Prediction, make_engine, make_session_factory
    from trading.storage import load_candles_df

    app_sf = make_session_factory(app_engine)
    research_engine = make_engine(research_db)
    report = {"scored": 0, "pending": 0, "series_missing": []}
    try:
        research_sf = make_session_factory(research_engine)
        with app_sf() as session, research_sf() as rs:
            rows = (
                session.execute(
                    select(Prediction).where(Prediction.scored_at.is_(None))
                )
                .scalars()
                .all()
            )
            candles: dict[tuple[str, str], pd.DataFrame] = {}
            for p in rows:
                key = (p.symbol, p.timeframe)
                if key not in candles:
                    candles[key] = load_candles_df(rs, p.symbol, p.timeframe)
                frame = candles[key]
                if frame.empty:
                    if key not in report["series_missing"]:
                        report["series_missing"].append(f"{p.symbol} {p.timeframe}")
                    continue
                anchor = pd.Timestamp(p.bar_close_time)
                try:
                    pos = frame.index.get_loc(anchor)
                except KeyError:
                    # the anchor bar itself is not in the store — venue
                    # resolution may differ from scan time; nothing honest
                    # can be measured, leave the row pending
                    report["pending"] += 1
                    continue
                if isinstance(pos, slice):  # duplicate index entries — take the first, never average
                    pos = pos.start
                target = pos + p.horizon_bars
                if target >= len(frame):
                    report["pending"] += 1
                    continue
                base_close = float(frame["close"].iloc[pos])
                final_close = float(frame["close"].iloc[target])
                if base_close <= 0:
                    report["pending"] += 1
                    continue
                outcome = final_close / base_close - 1.0
                p.outcome_return = outcome
                p.scored_at = _now()
                if outcome == 0.0:
                    p.correct_direction = None  # a tie is not a coin flip
                else:
                    p.correct_direction = bool((outcome > 0) == (p.predicted_return > 0))
                report["scored"] += 1
            session.commit()
    finally:
        research_engine.dispose()
    return report


# ------------------------------------------------------------------ reading


def prediction_to_dict(p) -> dict:
    """One prediction row as the wire contract: never a bare number. The
    noise scale, its basis, and the training boundary ride with every
    prediction because that is what a prediction IS — the rest is
    decoration."""
    return {
        "id": p.id,
        "ts": p.ts.isoformat() if p.ts else None,
        "symbol": p.symbol,
        "timeframe": p.timeframe,
        "artifact_kind": p.artifact_kind,
        "horizon_bars": p.horizon_bars,
        "predicted_return": p.predicted_return,
        "noise": p.noise,
        "noise_basis": p.noise_basis,
        "z_score": p.z_score,
        "oof_corr": p.oof_corr,
        "bar_close_time": p.bar_close_time.isoformat() if p.bar_close_time else None,
        "trained_through": p.trained_through,
        "outcome_return": p.outcome_return,
        "scored_at": p.scored_at.isoformat() if p.scored_at else None,
        "correct_direction": p.correct_direction,
        "caveat": CAVEAT,
    }


def latest_predictions(session) -> list[dict]:
    """The newest committed prediction per (symbol, artifact_kind) — one
    row per series per model family, the instrument strip's data. Empty
    when no scanner has ever run: absence is the honest answer, never a
    fabricated zero."""
    from trading.models import Prediction

    rows = session.execute(select(Prediction).order_by(Prediction.bar_close_time.desc())).scalars().all()
    seen: dict[tuple, object] = {}
    for p in rows:
        key = (p.symbol, p.artifact_kind)
        if key not in seen:
            seen[key] = p
    return [prediction_to_dict(p) for p in seen.values()]


# Below this sample size a hit rate is decoration, not evidence — the same
# honesty bar the divergence surface sets (never fake statistics over two
# trades). The label is explicit so the UI cannot mistake a coin-flip
# sample for a measurement.
SMALL_SAMPLE_N = 10


def track_record(session) -> dict:
    """The scored history, aggregated per (symbol, artifact_kind): hit rate
    over decided outcomes only, mean predicted vs mean realized, and the
    pending/scored split. Every aggregate carries its sample size — a hit
    rate without n is a horoscope."""
    from trading.models import Prediction

    rows = session.execute(select(Prediction)).scalars().all()
    groups: dict[tuple, list] = {}
    for p in rows:
        groups.setdefault((p.symbol, p.artifact_kind), []).append(p)
    out = []
    for (symbol, kind), preds in sorted(groups.items()):
        scored = [p for p in preds if p.scored_at is not None]
        decided = [p for p in scored if p.correct_direction is not None]
        hits = sum(1 for p in decided if p.correct_direction)
        hit_rate = hits / len(decided) if decided else None
        entry = {
            "symbol": symbol,
            "artifact_kind": kind,
            "timeframe": preds[0].timeframe,
            "total": len(preds),
            "pending": len(preds) - len(scored),
            "scored": len(scored),
            "decided": len(decided),
            "ties": len(scored) - len(decided),
            "hits": hits,
            "hit_rate": round(hit_rate, 4) if hit_rate is not None else None,
            "mean_predicted": round(sum(p.predicted_return for p in scored) / len(scored), 6) if scored else None,
            "mean_realized": round(sum(p.outcome_return for p in scored) / len(scored), 6) if scored else None,
            "small_sample": len(decided) < SMALL_SAMPLE_N,
            "sample_note": (
                f"{len(decided)} decided outcomes — decoration, not evidence"
                if len(decided) < SMALL_SAMPLE_N
                else f"{len(decided)} decided outcomes"
            ),
        }
        out.append(entry)
    return {
        "series": out,
        "small_sample_threshold": SMALL_SAMPLE_N,
        "caveat": CAVEAT,
    }
