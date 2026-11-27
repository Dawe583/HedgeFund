import sys
import numpy as np
from trading.search import load_frame
from trading.ml_rolling import rolling_predictions_cached

DB = "sqlite:////Users/dawe/Developer/HedgeFund/backend/data/research.db"
H = 6
w, c = 2000, 24  # the lead config only — equities have 5078 hourly bars, marginal depth

for sym in ["GLD", "AAPL", "NFLX", "SLV"]:
    try:
        df = load_frame(DB, sym, "1h")
        fwd = df["close"].shift(-H) / df["close"] - 1.0
        preds = rolling_predictions_cached(df, sym, "1h", horizon=H, window=w, cadence=c)
        both = preds.rename("p").to_frame().join(fwd.rename("f")).dropna()
        if len(both) < 300:
            print(f"{sym}: insufficient overlap {len(both)}", flush=True)
            continue
        segs = [both.iloc[s] for s in np.array_split(np.arange(len(both)), 4)]
        corrs = [float(np.corrcoef(seg["p"], seg["f"])[0, 1]) for seg in segs]
        seg_str = " ".join(f"{x:+.3f}" for x in corrs)
        print(f"{sym} | w{w}-c{c} | seg1..4: {seg_str} | n {len(both)}", flush=True)
    except Exception as e:
        print(f"{sym}: ERROR {str(e)[:80]}", flush=True)
print("EQUITY-PERSISTENCE-DONE", flush=True)
