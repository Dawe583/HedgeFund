import pytest

pytest.importorskip("trading.feeds.hyperliquid")

from trading.feeds.hyperliquid import OrderFlowTracker, book_features, parse_l2


def _msg(bids, asks):
    return {
        "channel": "l2Book",
        "data": {
            "coin": "BTC",
            "time": 1_700_000_000_000,
            "levels": [[{"px": str(p), "sz": str(s)} for p, s in bids],
                       [{"px": str(p), "sz": str(s)} for p, s in asks]],
        },
    }


def test_parse_l2_normalizes_and_sorts():
    book = parse_l2(_msg([(100.0, 1.0), (99.5, 2.0)], [(101.0, 1.5), (100.5, 3.0)]))
    assert book is not None
    assert book["bids"][0] == (100.0, 1.0)  # best bid first
    assert book["asks"][0] == (100.5, 3.0)  # best ask first


def test_book_features_math():
    feats = book_features(parse_l2(_msg([(100.0, 2.0), (99.0, 2.0)], [(100.1, 2.0), (101.0, 2.0)])))
    assert feats["mid"] == pytest.approx(100.05)
    assert feats["spread_bps"] == pytest.approx(0.1 / 100.05 * 10_000)  # 9.995
    assert feats["imbalance"] == 0.0  # symmetric book
    # microprice: weighted by opposite size -> closer to ask when ask size > bid size
    assert 0 <= feats["micro_skew_bps"] <= feats["spread_bps"]


def test_imbalance_sign():
    bid_heavy = book_features(parse_l2(_msg([(100.0, 8.0)], [(100.1, 2.0)])))
    ask_heavy = book_features(parse_l2(_msg([(100.0, 2.0)], [(100.1, 8.0)])))
    assert bid_heavy["imbalance"] == pytest.approx(0.6)
    assert ask_heavy["imbalance"] == pytest.approx(-0.6)


def test_tracker_pressure_direction():
    t = OrderFlowTracker(window=6)
    out = None
    for _ in range(6):
        f = book_features(parse_l2(_msg([(100.0, 9.0)], [(100.1, 1.0)])))
        out = t.update(f)
    assert out is not None
    assert out["ofi_mean"] > 0
    assert out["pressure"] > 0
