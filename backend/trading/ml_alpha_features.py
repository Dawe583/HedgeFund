"""F13 machinery — alpha-augmented feature frames for the rolling forecaster.

The vendored zoo's survivors join the F12 feature set as causal columns.
Built but deliberately idle: the family sweeps only if F12's persistence
measurement says the ML premise lives (program-2026-11-26, F13 section).

The honesty chain is F10's and F12's composed: alpha values are causal by
the zoo's operator discipline, rolling predictions are embargoed by
construction, and injection joins everything onto the frame before the
kernel ever sees it.
"""

from __future__ import annotations

import importlib

import pandas as pd

from trading.ml_forecast import FEATURES as BASE_FEATURES

# the five decorrelated survivors from the 2026-11-26 bench — inversion
# does not matter for features: the model learns the sign itself
F13_ALPHAS = ["gtja191_093", "gtja191_159", "gtja191_126", "gtja191_097", "gtja191_081"]
F13_FEATURES = list(BASE_FEATURES) + [f"alpha_{a.split('_')[1]}" for a in F13_ALPHAS]

F13_UNIVERSE = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT", "AVAXUSDT", "LTCUSDT"]


def augment_frame(df: pd.DataFrame, symbol: str, research_db: str, timeframe: str) -> pd.DataFrame:
    """Join the five survivor alphas onto a feature frame as causal columns.
    Each alpha is z-scored against its expanding history exactly as in the
    F10 adapter — expanding, never centered."""
    from trading.bots.alpha_signal_bot import _alpha_wide_cached, align_alpha_series

    out = df.copy()
    for alpha_id in F13_ALPHAS:
        zoo, num = alpha_id.split("_")
        compute_fn = importlib.import_module(f"trading.factors.zoo.{zoo}.alpha_{num}").compute
        wide = _alpha_wide_cached(compute_fn, research_db, F13_UNIVERSE, timeframe)
        if symbol not in wide.columns:
            continue
        z = align_alpha_series(wide, symbol)
        col = z["alpha_z"]
        if out.index.tz is not None and col.index.tz is None:
            col = col.copy()
            col.index = col.index.tz_localize(out.index.tz)
        out[f"alpha_{num}"] = col.reindex(out.index)
    return out
