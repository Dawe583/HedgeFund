"""Basket composition tests — the composite's honesty is the whole claim.

A basket verdict is only as good as the composition rules: capital at rest
before a slot's first bar, trades pooled in time order, the composite never
inventing PnL a slot did not make. These tests pin those rules on
constructed slots, because a wrong composite silently fabricates edges.
"""

import numpy as np
import pandas as pd
import pytest

from trading.basket import compose_basket


class FakeResult:
    def __init__(self, trades, equity):
        self.trades = trades
        self.equity = equity


def _eq(values, start="2025-01-01", freq="4h"):
    idx = pd.date_range(start, periods=len(values), freq=freq, tz="UTC")
    return pd.Series(values, index=idx)


def test_trades_pool_in_time_order():
    idx = pd.date_range("2025-01-01", periods=10, freq="4h", tz="UTC")
    a = FakeResult(
        [{"entry_time": idx[0], "exit_time": idx[8], "pnl": 1.0, "side": "long", "qty": 1,
          "entry_price": 1, "exit_price": 1, "fees": 0, "confidence": 0.7, "bars_held": 8,
          "reason": "signal_exit", "signal_bar": 0, "entry_bar": 0, "exit_bar": 8,
          "entry_fill_raw": 1, "exit_fill_raw": 1}],
        _eq([100.0] * 10),
    )
    b = FakeResult(
        [{"entry_time": idx[1], "exit_time": idx[3], "pnl": 2.0, "side": "long", "qty": 1,
          "entry_price": 1, "exit_price": 1, "fees": 0, "confidence": 0.7, "bars_held": 2,
          "reason": "signal_exit", "signal_bar": 1, "entry_bar": 1, "exit_bar": 3,
          "entry_fill_raw": 1, "exit_fill_raw": 1}],
        _eq([100.0] * 10),
    )
    records, composite = compose_basket({"AAA": a, "BBB": b}, 100.0)
    assert len(records) == 2
    exits = [r.exit_time for r in records]
    assert exits == sorted(exits)
    # the BBB trade closes at idx[3], before AAA's idx[8]
    assert records[0].exit_time == idx[3]
    assert records[0].symbol == "BBB"


def test_late_starting_slot_is_capital_at_rest_not_zero():
    early = FakeResult([], _eq([100.0, 110.0, 120.0], start="2025-01-01"))
    late = FakeResult([], _eq([100.0, 105.0], start="2025-01-01 08:00"))
    records, composite = compose_basket({"AAA": early, "BBB": late}, 100.0)
    # union grid: 00:00, 04:00, 08:00, 12:00 — before 08:00 the late slot
    # contributes its starting cash (100), not zero: unborn capital is at rest
    first = composite.iloc[0]
    assert first == pytest.approx(200.0), f"composite at t0 {first} — late slot must count as resting cash"
    # after both slots exist the composite is their sum
    assert composite.iloc[-1] == pytest.approx(120.0 + 105.0)


def test_composite_never_invents_pnl():
    a = FakeResult([], _eq([100.0, 100.0, 100.0]))
    b = FakeResult([], _eq([100.0, 100.0, 100.0]))
    records, composite = compose_basket({"AAA": a, "BBB": b}, 100.0)
    assert (composite.values == 200.0).all()
    assert records == []


def test_compose_uses_union_grid_not_intersection():
    a = FakeResult([], _eq([100.0, 110.0], start="2025-01-01"))  # ends 04:00
    b = FakeResult([], _eq([100.0, 100.0, 130.0], start="2025-01-01 04:00"))  # ends 12:00
    records, composite = compose_basket({"AAA": a, "BBB": b}, 100.0)
    # union has 4 stamps (00,04,08,12); a forward-fills its last equity 110
    assert len(composite) == 4
    assert composite.iloc[-1] == pytest.approx(110.0 + 130.0)
