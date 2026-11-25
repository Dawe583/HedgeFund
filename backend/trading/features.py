"""Feature engineering — pure pandas/numpy, shared by backtest, paper and ML."""

import numpy as np
import pandas as pd

TF_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}


def candles_to_df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df = df.set_index("open_time").sort_index()
    return df[["open", "high", "low", "close", "volume"]]


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50.0)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def realized_vol(close: pd.Series, n: int = 48) -> pd.Series:
    rets = np.log(close / close.shift(1))
    return rets.rolling(n).std() * np.sqrt(n)


def regime_score(close: pd.Series) -> pd.Series:
    """+1 strong trend up .. -1 strong trend down, via EMA separation."""
    fast, slow = ema(close, 21), ema(close, 89)
    sep = (fast - slow) / slow.replace(0, np.nan)
    return sep.fillna(0).clip(-1, 1)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Attach all model features to an OHLCV frame."""
    out = df.copy()
    c = out["close"]
    out["ret_1"] = c.pct_change()
    out["ret_8"] = c.pct_change(8)
    out["ret_32"] = c.pct_change(32)
    out["ema_fast"] = ema(c, 21)
    out["ema_slow"] = ema(c, 89)
    out["ema_sep"] = (out["ema_fast"] - out["ema_slow"]) / out["ema_slow"]
    out["rsi"] = rsi(c, 14)
    out["atr_pct"] = atr(out, 14) / c
    out["rvol"] = realized_vol(c, 48)
    out["vol_z"] = (
        (out["volume"] - out["volume"].rolling(96).mean()) / out["volume"].rolling(96).std()
    )
    out["regime"] = regime_score(c)
    out["trend_strength"] = (
        out["regime"] / out["atr_pct"].replace(0, np.nan)
    ).clip(-5, 5)
    out["body_pct"] = (c - out["open"]) / out["open"]
    out["range_pos"] = (c - out["low"]) / (out["high"] - out["low"]).replace(0, np.nan)
    return out


def make_labels(df: pd.DataFrame, horizon: int = 6, rr: float = 1.5) -> pd.Series:
    """Triple-barrier style label using ATR bands over `horizon` bars.

    1 = long wins first, -1 = short wins first, 0 = neither hit (timeout).
    """
    a = atr(df, 14)
    hi, lo, c = df["high"], df["low"], df["close"]
    labels = pd.Series(0, index=df.index, dtype=int)
    values = c.to_numpy()
    highs, lows = hi.to_numpy(), lo.to_numpy()
    atrs, n = a.to_numpy(), len(c)
    h = int(horizon)
    for i in range(n - h):
        entry = values[i]
        up, dn = entry + rr * atrs[i], entry - rr * atrs[i]
        win_h = highs[i + 1 : i + 1 + h]
        win_l = lows[i + 1 : i + 1 + h]
        hit_up = win_h >= up
        hit_dn = win_l <= dn
        if hit_up.any():
            labels.iloc[i] = 1
        elif hit_dn.any():
            labels.iloc[i] = -1
    return labels
