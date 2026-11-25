import numpy as np

from trading.backtest.monte_carlo import monte_carlo_trades, summarize_edge


def _returns(n=120, wr=0.45, seed=3):
    rng = np.random.default_rng(seed)
    return [1.8 if rng.random() < wr else -1.0 for _ in range(n)]


def test_rejects_too_few_trades():
    out = monte_carlo_trades([1.0, 2.0])
    assert "error" in out


def test_bands_are_monotonic():
    mc = monte_carlo_trades(_returns(), n_sims=200, horizon=80)
    for t in range(len(mc["bands"]["50"])):
        assert mc["bands"]["5"][t] <= mc["bands"]["25"][t] <= mc["bands"]["50"][t]
        assert mc["bands"]["50"][t] <= mc["bands"]["75"][t] <= mc["bands"]["95"][t]


def test_band_lengths_match_horizon():
    horizon = 60
    mc = monte_carlo_trades(_returns(), n_sims=100, horizon=horizon)
    assert all(len(v) == horizon + 1 for v in mc["bands"].values())


def test_probabilities_in_range():
    mc = monte_carlo_trades(_returns(wr=0.55), n_sims=300, horizon=100)
    assert 0 <= mc["prob_profit"] <= 1
    assert 0 <= mc["prob_ruin_20"] <= 1


def test_positive_edge_gives_median_growth():
    mc = monte_carlo_trades(_returns(wr=0.6), n_sims=400, horizon=150)
    assert mc["final_equity"]["median"] > 100.0
    assert mc["prob_profit"] > 0.5


def test_deterministic_with_seed():
    a = monte_carlo_trades(_returns(), seed=42)
    b = monte_carlo_trades(_returns(), seed=42)
    assert a["final_equity"] == b["final_equity"]


def test_summarize_edge():
    s = summarize_edge(_returns(wr=0.5))
    assert s["trades_n"] == 120
    assert 0 < s["win_rate"] < 1
    assert s["expectancy_pct"] != 0
    assert summarize_edge([1.0]) == {}
