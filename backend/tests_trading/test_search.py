"""Search machinery tests — the governance is the product.

The machinery exists so that a validated strategy means something: every
candidate counted, selection and confirmation never sharing a bar, rails-off
screening vs rails-on truth. These tests pin those invariants, not trading
outcomes — verdicts on synthetic noise are whatever they are; the ledger's
honesty is what must not move.
"""

import json

import numpy as np
import pandas as pd
import pytest

from trading.features import build_features
from trading.search import (
    OOS_SPLIT,
    Candidate,
    evaluate_candidate,
    in_sample,
    ledger_counts,
    open_ledger,
    out_of_sample,
    rails_off_config,
)


def _tape(n=1300, seed=7, start="2025-05-01", freq="4h"):
    """Synthetic OHLCV spanning the OOS split: ~7 months at 4h, so both
    windows carry real bar counts."""
    rng = np.random.default_rng(seed)
    steps = np.cumsum(rng.normal(2.0, 60, n)) + 40_000
    close = steps
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) * 1.002
    low = np.minimum(open_, close) * 0.998
    vol = np.abs(rng.normal(1000, 100, n))
    idx = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    )


def _candidate(name="c0", params=None):
    from trading.research import STRATEGIES

    catalog = STRATEGIES["scalp"]

    def make(p):
        return catalog["cls"](**p)

    return Candidate(
        family="test-family",
        name=name,
        bot_key="scalp",
        params=params or {},
        make=make,
        symbols=["BTCUSDT"],
        timeframe="4h",
    )


def test_split_is_fixed_not_a_flag():
    """The split date is a constant — the program document says a split that
    moves with results is not a split."""
    assert OOS_SPLIT == pd.Timestamp("2025-11-01", tz="UTC")


def test_windows_partition_the_tape():
    df = build_features(_tape())
    ins = in_sample(df)
    oos = out_of_sample(df)
    assert len(ins) > 0 and len(oos) > 0
    assert len(ins) + len(oos) == len(df)
    assert ins.index.max() < OOS_SPLIT <= oos.index.min()


def test_rails_off_config_disables_censoring():
    cfg = rails_off_config()
    assert cfg.killswitch_dd_pct >= 99.0
    assert cfg.daily_loss_pct >= 99.0
    assert cfg.max_symbol_exposure > 1000
    assert cfg.loss_streak_max > 1000
    # fees and slippage stay production-real — cost honesty is the measurement
    from trading.config import get_settings

    assert cfg.fee_pct == get_settings().taker_fee_pct


def test_ledger_is_append_only_and_counts(sqlite_path):
    conn = open_ledger(sqlite_path)
    df = build_features(_tape())
    ins = in_sample(df)

    r1 = evaluate_candidate(
        conn, _candidate("c0"), phase="A", df=ins,
        research_db="sqlite:///:memory:", seed=42, cfg=rails_off_config(), symbol="BTCUSDT",
    )
    r2 = evaluate_candidate(
        conn, _candidate("c1", {"regime_min": 0.001}), phase="A", df=ins,
        research_db="sqlite:///:memory:", seed=42, cfg=rails_off_config(), symbol="BTCUSDT",
    )
    assert r2["id"] > r1["id"]

    counts = ledger_counts(conn)
    families = {row[0] for row in counts}
    assert families == {"test-family"}
    total = sum(row[3] for row in counts)
    assert total == 2, "every evaluation lands exactly once — the count is the evidence"

    rows = conn.execute("SELECT phase, rails, verdict, reasons_json FROM search_ledger ORDER BY id").fetchall()
    assert all(r[0] == "A" for r in rows)
    assert all(r[1] == "off" for r in rows)
    # reasons_json is present even when empty — the row explains itself
    for r in rows:
        json.loads(r[3])
    conn.close()


def test_phase_b_marks_rails_on(sqlite_path):
    from trading.backtest.engine import BTConfig

    conn = open_ledger(sqlite_path)
    df = build_features(_tape())
    oos = out_of_sample(df)
    r = evaluate_candidate(
        conn, _candidate(), phase="B", df=oos,
        research_db="sqlite:///:memory:", seed=42, cfg=BTConfig(), symbol="BTCUSDT",
    )
    assert r["rails"] == "on"
    assert r["phase"] == "B"
    conn.close()


def test_windows_report_their_own_range(sqlite_path):
    """The ledger row's data_start/data_end are the window's truth, so a row
    can never claim evidence it did not see."""
    conn = open_ledger(sqlite_path)
    df = build_features(_tape())
    ins = in_sample(df)
    r = evaluate_candidate(
        conn, _candidate(), phase="A", df=ins,
        research_db="sqlite:///:memory:", seed=42, cfg=rails_off_config(), symbol="BTCUSDT",
    )
    assert pd.Timestamp(r["data_end"]) < OOS_SPLIT
    assert r["data_rows"] == len(ins)
    conn.close()


def test_empty_window_dies_loudly(sqlite_path):
    """A window with no bars validates nothing — the core refuses rather than
    writing a verdict row over an empty tape."""
    from trading.research import validate_core

    conn = open_ledger(sqlite_path)
    df = build_features(_tape())
    empty = df[df.index < pd.Timestamp("2000-01-01", tz="UTC")]
    assert len(df) > 0 and len(empty) == 0
    with pytest.raises(SystemExit):
        validate_core(
            _candidate().instance(), "scalp", "BTCUSDT", "4h",
            "sqlite:///:memory:", seed=42, df=empty,
        )
    # and nothing was ledgered — a refused evaluation is not a candidate
    assert conn.execute("SELECT COUNT(*) FROM search_ledger").fetchone()[0] == 0
    conn.close()


@pytest.fixture
def sqlite_path(tmp_path):
    return str(tmp_path / "research.db")
