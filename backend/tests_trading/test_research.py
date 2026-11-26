"""Behavior tests for the research pipeline: anti-lookahead harness, the
validation trio on known inputs, and the CLI end-to-end verdict row."""

import asyncio
import json

import numpy as np
import pandas as pd
import pytest

from trading.backtest.engine import BTConfig, run_backtest
from trading.bots import ScalpTrend
from trading.features import build_features
from trading.harness import wrap as harness_wrap
from trading.models import (
    BacktestRun,
    BacktestValidation,
    init_schema,
    make_engine,
    make_session_factory,
)
from trading.research import validate_strategy
from trading.storage import upsert_candles
from trading.validation import bootstrap_sharpe_ci, monte_carlo_test, walk_forward_analysis
from trading.validation.models import TradeRecord


def _synthetic_ohlcv(n=700, seed=11, freq="4h"):
    # high/low must enclose BOTH open and close: the kernel validates OHLC
    # consistency per bar and refuses a frame whose wicks don't cover the body
    rng = np.random.default_rng(seed)
    steps = np.cumsum(rng.normal(2.0, 60, n)) + 40_000
    close = steps
    open_ = np.concatenate([[close[0]], close[:-1]])
    body_hi = np.maximum(open_, close)
    body_lo = np.minimum(open_, close)
    high = body_hi * (1 + np.abs(rng.normal(0, 0.002, n)))
    low = body_lo * (1 - np.abs(rng.normal(0, 0.002, n)))
    vol = np.abs(rng.normal(1000, 100, n))
    idx = pd.date_range("2025-01-01", periods=n, freq=freq, tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    )


def _candle_rows(df):
    return [
        {
            "open_time": ts.to_pydatetime(),
            "open": float(r.open),
            "high": float(r.high),
            "low": float(r.low),
            "close": float(r.close),
            "volume": float(r.volume),
        }
        for ts, r in df.iterrows()
    ]


def _mktrades(pnls):
    out = []
    t = pd.Timestamp("2025-01-01", tz="UTC")
    for i, p in enumerate(pnls):
        out.append(
            TradeRecord(
                symbol="X", direction=1, entry_price=100, exit_price=101,
                entry_time=t + pd.Timedelta(hours=i * 2),
                exit_time=t + pd.Timedelta(hours=i * 2 + 1),
                size=1.0, leverage=1.0, pnl=p, pnl_pct=p / 10000,
                exit_reason="x", holding_bars=1, commission=1.0, entry_margin=10000,
            )
        )
    return out


# ------------------------------------------------------------- anti-lookahead


class CheatingStrategy:
    """Reads the future on purpose: signals long whenever the bar 5 ahead is higher."""

    def signal(self, i, df):
        try:
            future_close = df["close"].iloc[i + 5]
            now_close = df["close"].iloc[i]
        except Exception:
            return None
        if future_close > now_close * 1.001:
            from trading.backtest.engine import Signal

            return Signal(side="long", confidence=0.9)
        return None


def test_cheating_strategy_gets_no_future_data():
    df = build_features(_synthetic_ohlcv())
    cfg = BTConfig(fee_pct=0.0, slippage_bps=0.0, confidence_min=0.0)

    bare = run_backtest(df, CheatingStrategy(), cfg, "4h")
    wrapped = run_backtest(df, harness_wrap(CheatingStrategy()), cfg, "4h")

    # Unwrapped, the cheater sees the future and trades constantly; wrapped,
    # every lookahead read explodes inside its own guard and it never trades.
    # The bare-run count is the test's sensitivity witness: if the cheater
    # barely traded unwrapped, zero trades wrapped would prove nothing. The
    # exact count is fixture noise — the discrimination (many vs zero) is not.
    assert len(bare.trades) >= 5
    assert wrapped.trades == []


def test_harness_is_transparent_for_honest_strategies():
    df = build_features(_synthetic_ohlcv())
    cfg = BTConfig(fee_pct=0.0, slippage_bps=0.0, confidence_min=0.0)
    bare = run_backtest(df, ScalpTrend(), cfg, "4h")
    wrapped = run_backtest(df, harness_wrap(ScalpTrend()), cfg, "4h")
    assert len(bare.trades) == len(wrapped.trades)
    for a, b in zip(bare.trades, wrapped.trades):
        assert a["entry_price"] == b["entry_price"]
        assert a["exit_price"] == b["exit_price"]
        assert a["pnl"] == b["pnl"]


# ------------------------------------------------------------ validation trio


def test_permutation_test_separates_ordering_from_luck():
    # Wins clustered first: compounding makes this ordering measurably better
    # than shuffles of the same trades — p must be small.
    ordered = [40.0] * 40 + [-30.0] * 10
    res = monte_carlo_test(_mktrades(ordered), 1000.0, n_simulations=500, seed=42, bars_per_year=2190)
    assert res["p_value_sharpe"] < 0.05
    # The same trades randomly interleaved are indistinguishable from luck.
    # (seed 2 picked so the ordering is a typical shuffle, not a lucky one)
    rng = np.random.default_rng(2)
    shuffled = list(rng.permutation(np.array(ordered)))
    res2 = monte_carlo_test(_mktrades(list(shuffled)), 1000.0, n_simulations=500, seed=42, bars_per_year=2190)
    assert res2["p_value_sharpe"] > 0.2


def test_permutation_test_is_seeded_reproducible():
    pnls = [40.0] * 20 + [-25.0] * 15
    a = monte_carlo_test(_mktrades(pnls), 1000.0, n_simulations=200, seed=7)
    b = monte_carlo_test(_mktrades(pnls), 1000.0, n_simulations=200, seed=7)
    assert a["p_value_sharpe"] == b["p_value_sharpe"]
    assert a["sharpe_samples"] == b["sharpe_samples"]

def test_permutation_survives_ruin_shaped_permutations():
    # the 2026-11-26 artifact: permuted loss clusters replayed at fixed
    # dollars cross zero equity, and the first draft aborted the whole test
    # as 'inconclusive' — on 48/48 F7 cells including winning ones. Ruin is
    # absorbing, not fatal: the test must complete and the drawdown cap at -1.
    pnls = [30.0] * 30 + [-320.0] * 5  # any interleaving ruins the $1000 start
    res = monte_carlo_test(_mktrades(pnls), 1000.0, n_simulations=200, seed=42, bars_per_year=2190)
    assert "error" not in res, f"ruin-shaped permutations must not abort: {res.get('error')}"
    assert res["n_simulations"] == 200
    assert res["actual_max_dd"] >= -1.0
    assert all(isinstance(s, float) for s in res["sharpe_samples"])


def test_bootstrap_ci_sign_follows_equity_direction():
    idx = pd.date_range("2025-01-01", periods=500, freq="4h", tz="UTC")
    up = pd.Series(np.linspace(1000, 1400, 500), index=idx)
    down = pd.Series(np.linspace(1000, 700, 500), index=idx)
    b_up = bootstrap_sharpe_ci(up, bars_per_year=2190, seed=42, initial_capital=1000.0)
    b_down = bootstrap_sharpe_ci(down, bars_per_year=2190, seed=42, initial_capital=1000.0)
    assert b_up["ci_lower"] > 0 and b_up["prob_positive"] == 1.0
    assert b_down["ci_upper"] < 0 and b_down["prob_positive"] == 0.0


def test_walk_forward_counts_profitable_windows():
    idx = pd.date_range("2025-01-01", periods=500, freq="4h", tz="UTC")
    up = pd.Series(np.linspace(1000, 1400, 500), index=idx)
    wf = walk_forward_analysis(up, _mktrades([10] * 30), n_windows=5, bars_per_year=2190, initial_capital=1000.0)
    assert wf["profitable_windows"] == 5
    assert wf["n_windows"] == 5


# ------------------------------------------------------------- CLI end-to-end


def _seed_research_db(db_url: str, df) -> None:
    engine = make_engine(db_url)
    init_schema(engine)
    sf = make_session_factory(engine)
    with sf() as session:
        upsert_candles(session, "BTCUSDT", "4h", _candle_rows(df))
    engine.dispose()


def test_validate_writes_verdict_row(tmp_path):
    df = _synthetic_ohlcv()
    research_db = f"sqlite:///{tmp_path}/research.db"
    app_db = f"sqlite:///{tmp_path}/app.db"
    _seed_research_db(research_db, df)

    payload = validate_strategy(
        bot_key="scalp",
        symbol="BTCUSDT",
        timeframe="4h",
        research_db=research_db,
        app_db=app_db,
        seed=42,
    )

    assert payload["verdict"] in ("validated", "rejected")
    assert payload["seed"] == 42
    assert payload["data"]["rows"] == len(df)

    engine = make_engine(app_db)
    sf = make_session_factory(engine)
    with sf() as session:
        rows = session.query(BacktestValidation).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.verdict == payload["verdict"]
        assert row.seed == 42
        assert row.data_rows == len(df)
        assert row.data_source == "binance"
        assert row.trades_n == payload["trades"]
        # the verdict is consistent with the recorded reasons
        reasons = json.loads(row.reasons_json)
        assert (row.verdict == "validated") == (not reasons)
        # the run row carries the headline metrics
        run = session.get(BacktestRun, row.run_id)
        assert run is not None and run.bot == "scalp"
        validation = json.loads(row.validation_json)
        assert "monte_carlo" in validation and "bootstrap" in validation and "walk_forward" in validation
    engine.dispose()


def test_validate_is_reproducible_with_same_seed(tmp_path):
    df = _synthetic_ohlcv()
    research_db = f"sqlite:///{tmp_path}/research.db"
    _seed_research_db(research_db, df)

    first = validate_strategy("scalp", "BTCUSDT", "4h", research_db, f"sqlite:///{tmp_path}/a.db", seed=42)
    second = validate_strategy("scalp", "BTCUSDT", "4h", research_db, f"sqlite:///{tmp_path}/b.db", seed=42)
    assert first["verdict"] == second["verdict"]
    assert first["permutation_p"] == second["permutation_p"]
    assert first["sharpe_ci"] == second["sharpe_ci"]


def test_ingest_uses_public_feed_without_network_in_tests(tmp_path, monkeypatch):
    """ingest pulls rows from the feed and lands them in the candle store."""
    df = _synthetic_ohlcv(n=50)
    rows = _candle_rows(df)

    async def fake_fetch(symbol, interval, **kwargs):
        return rows, "binance"

    import trading.feeds.fallback as fallback_mod

    monkeypatch.setattr(fallback_mod, "fetch_candles_any", fake_fetch)

    from trading.research import _ingest

    db_url = f"sqlite:///{tmp_path}/research.db"
    inserted, venue = asyncio.run(_ingest("BTCUSDT", "4h", 30, db_url))
    assert inserted == 50
    assert venue == "binance"

    engine = make_engine(db_url)
    init_schema(engine)
    sf = make_session_factory(engine)
    from trading.storage import load_candles_df

    with sf() as session:
        back = load_candles_df(session, "BTCUSDT", "4h")
    assert len(back) == 50
    engine.dispose()
