"""Alpha bench — the vendored factor zoos measured on OUR universes.

Methodology follows the Vibe-Trading CSI 300 study (MIT, wiki/research-lab):
each alpha is scored by its cross-sectional rank IC against forward returns,
then classified:

    alive    — mean IC > 0.02, t-stat > 2, 55%+ of periods positive
    reversed — same significance with negative mean IC (contrarian signal)
    dead     — everything else

The honest differences from their study, declared: our universes are small
(10 crypto / 6 equity-index-metals vs CSI 300), so cross-sectional ranks
carry less information per bar and the power is correspondingly lower —
the bench measures what the alpha does on OUR tape, not theirs, which is
the only question this program ever asks. Alphas needing factor extras
(mkt_ret/smb/hml) get cross-sectionally constructed proxies: mkt_ret is
the equal-weight universe return, smb/hml are decomposition proxies
documented in the panel builder — a step below Fama-French construction
and the honest ceiling for a 6-16 asset universe.
"""

from __future__ import annotations

import importlib
import json
import pkgutil

import numpy as np
import pandas as pd

import trading.factors.zoo.alpha101 as alpha101_pkg
import trading.factors.zoo.gtja191 as gtja191_pkg


def load_panel(research_db: str, symbols: list[str], timeframe: str) -> dict[str, pd.DataFrame]:
    """Wide OHLCV panel: column per symbol, aligned on the union index,
    forward-filled — the zoo's input contract. Rows where fewer than half
    the universe has data are dropped rather than filled into fiction."""
    from trading.models import make_engine, make_session_factory
    from trading.storage import load_candles_df

    engine = make_engine(research_db)
    sf = make_session_factory(engine)
    frames = {}
    with sf() as session:
        for sym in symbols:
            df = load_candles_df(session, sym, timeframe)
            if not df.empty:
                frames[sym] = df
    engine.dispose()
    if len(frames) < 2:
        raise SystemExit(f"panel needs >= 2 symbols with data, got {list(frames)}")

    union = pd.DatetimeIndex(sorted(set().union(*[f.index for f in frames.values()])))
    panel: dict[str, pd.DataFrame] = {}
    for col in ("open", "high", "low", "close", "volume"):
        wide = pd.DataFrame({s: f[col].reindex(union, method="ffill") for s, f in frames.items()})
        panel[col] = wide
    # rows where less than half the universe trades: crypto trades 24/7,
    # equities don't — the intersection rows are the honest shared tape
    coverage = panel["close"].notna().mean(axis=1)
    keep = coverage >= 0.5
    panel = {c: w.loc[keep] for c, w in panel.items()}
    # drop still-empty columns (asset never overlaps)
    alive_cols = panel["close"].notna().any()
    live = list(alive_cols[alive_cols].index)
    panel = {c: w[live] for c, w in panel.items()}

    # cross-sectional extras: equal-weight market return + smb/hml proxies
    rets = panel["close"].pct_change(fill_method=None)
    mkt = rets.mean(axis=1)
    spread = rets.std(axis=1)
    for name, series in (("mkt_ret", mkt), ("smb", spread), ("hml", mkt.rolling(20).mean() - mkt)):
        panel[name] = pd.DataFrame({s: series for s in live}, index=panel["close"].index)
    return panel


def iter_zoo():
    """(alpha_id, compute_fn, meta) for every alpha in both vendored zoos."""
    for pkg, prefix in ((alpha101_pkg, "alpha101"), (gtja191_pkg, "gtja191")):
        for m in pkgutil.iter_modules(pkg.__path__):
            if not m.name.startswith("alpha"):
                continue
            mod = importlib.import_module(f"{pkg.__name__}.{m.name}")
            compute = getattr(mod, "compute", None)
            if compute is not None:
                yield f"{prefix}_{m.name.split('_')[-1]}", compute, getattr(mod, "__alpha_meta__", {})


def rank_ic_series(alpha_out: pd.DataFrame, fwd: pd.DataFrame) -> pd.Series:
    """Per-bar Spearman rank correlation between alpha values and forward
    returns across the universe — the information coefficient series."""
    common = alpha_out.index.intersection(fwd.index)
    a = alpha_out.loc[common]
    f = fwd.loc[common]
    ics = []
    idx = []
    for i in range(len(common)):
        ar = a.iloc[i].rank()
        fr = f.iloc[i].rank()
        valid = ar.notna() & fr.notna()
        if valid.sum() < 4:
            continue
        ic = ar[valid].corr(fr[valid])
        if np.isfinite(ic):
            ics.append(ic)
            idx.append(common[i])
    return pd.Series(ics, index=idx)


def classify(ic: pd.Series, horizon: int) -> dict:
    """alive / reversed / dead from the IC series, Vibe's filter exactly."""
    n = len(ic)
    if n < 30:
        return {"verdict": "untestable", "n_periods": n, "reason": "fewer than 30 measured periods"}
    mean_ic = float(ic.mean())
    tstat = float(mean_ic / (ic.std() + 1e-12) * np.sqrt(n))
    pos_share = float((ic > 0).mean())
    out = {
        "mean_ic": round(mean_ic, 4), "tstat": round(tstat, 2),
        "positive_share": round(pos_share, 3), "n_periods": n, "horizon": horizon,
    }
    if abs(tstat) > 2 and pos_share >= 0.55 and mean_ic > 0.02:
        out["verdict"] = "alive"
    elif abs(tstat) > 2 and (1 - pos_share) >= 0.55 and mean_ic < -0.02:
        out["verdict"] = "reversed"
    else:
        out["verdict"] = "dead"
    return out


def run_bench(
    research_db: str,
    symbols: list[str],
    timeframe: str,
    *,
    horizon: int = 1,
    alpha_ids: list[str] | None = None,
) -> list[dict]:
    """The full bench: every zoo alpha against forward `horizon`-bar returns."""
    panel = load_panel(research_db, symbols, timeframe)
    fwd = panel["close"].shift(-horizon) / panel["close"] - 1.0
    rows = []
    wanted = set(alpha_ids) if alpha_ids else None
    for alpha_id, compute, meta in iter_zoo():
        if wanted and alpha_id not in wanted:
            continue
        try:
            out = compute(panel)
            if not isinstance(out, pd.DataFrame):
                rows.append({"alpha": alpha_id, "verdict": "untestable", "reason": "non-frame output"})
                continue
            finite_share = float(np.isfinite(out.values).mean())
            if finite_share < 0.1:
                rows.append({"alpha": alpha_id, "verdict": "untestable", "reason": f"finite share {finite_share:.2f}"})
                continue
            ic = rank_ic_series(out, fwd)
            verdict = classify(ic, horizon)
            verdict["alpha"] = alpha_id
            verdict["theme"] = ",".join(meta.get("theme", [])[:2]) if isinstance(meta.get("theme"), list) else ""
            rows.append(verdict)
        except Exception as exc:
            rows.append({"alpha": alpha_id, "verdict": "untestable", "reason": f"{type(exc).__name__}: {str(exc)[:80]}"})
    return rows
