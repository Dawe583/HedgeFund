"""Tests for the loss-streak cool-down guard (risk_guard.py)."""

from trading import risk_guard


def _kv():
    store = {}
    return (lambda k: store.get(k)), (lambda k, v: store.__setitem__(k, v))


def test_three_losses_trigger_cooldown():
    get, put = _kv()
    t0 = 1_000_000.0
    assert risk_guard.is_paused(get, "hft", t0)[0] is False
    risk_guard.record_close(get, put, "hft", -1.0, t0)
    risk_guard.record_close(get, put, "hft", -1.0, t0)
    r = risk_guard.record_close(get, put, "hft", -1.0, t0)
    assert r["cooldown_until"] == t0 + 4 * 3600
    paused, reason = risk_guard.is_paused(get, "hft", t0 + 60)
    assert paused is True and "min left" in reason
    assert risk_guard.is_paused(get, "hft", t0 + 5 * 3600)[0] is False


def test_win_resets_streak():
    get, put = _kv()
    t0 = 2_000_000.0
    risk_guard.record_close(get, put, "scalp", -1.0, t0)
    risk_guard.record_close(get, put, "scalp", 3.0, t0)
    assert risk_guard.status(get, "scalp", t0)["loss_streak"] == 0


def test_breakeven_counts_as_loss():
    get, put = _kv()
    t0 = 3_000_000.0
    r = risk_guard.record_close(get, put, "hft", 0.0, t0)
    assert r["streak"] == 1
