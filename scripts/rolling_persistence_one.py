import sys
import numpy as np
from trading.search import load_frame
from trading.ml_rolling import rolling_predictions_cached

DB = "sqlite:////Users/dawe/Developer/HedgeFund/backend/data/research.db"
H = 6
w, c = int(sys.argv[1]), int(sys.argv[2])

for sym in ["BTCUSDT", "ETHUSDT"]:
    df = load_frame(DB, sym, "1h")
    fwd = df["close"].shift(-H) / df["close"] - 1.0
    preds = rolling_predictions_cached(df, sym, "1h", horizon=H, window=w, cadence=c)
    both = preds.rename("p").to_frame().join(fwd.rename("f")).dropna()
    segs = [both.iloc[s] for s in np.array_split(np.arange(len(both)), 5)]
    corrs = [float(np.corrcoef(seg["p"], seg["f"])[0, 1]) for seg in segs]
    seg_str = " ".join(f"{x:+.3f}" for x in corrs)
    print(f"{sym} | w{w}-c{c} | seg1..5: {seg_str} | n {len(both)}", flush=True)
print(f"DONE-w{w}-c{c}", flush=True)
