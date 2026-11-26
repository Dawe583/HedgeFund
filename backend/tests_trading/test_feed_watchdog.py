"""Feed watchdog verdict tests — the restart decision's truth table.

The watchdog exists because the 2026-11-26 soak measured a desk blind for
hours behind healthy-looking websocket reconnects: quotes flowing, klines
never closing, nothing acting. These tests pin the distinction the verdict
must hold: quotes alive + bars silent = restart (subscription death, local
and remediable); quotes silent + bars silent = no restart (partition,
unremediable); boot grace and timeout multipliers keep the honest windows
honest. Pure logic, no kernel — the kernel-side integration is the
QuoteBridge beat write, exercised wherever the live wiring boots.
"""

from types import SimpleNamespace

from trading.desk.runner import QUOTE_ALIVE_S, feed_watchdog_verdict
from trading.desk.worker import FeedHealth


def _spec(bot="scalp"):
    return SimpleNamespace(bot=bot)


def _desk(
    *,
    stale_after=180.0,
    feed_health=None,
    quote_beats=None,
    instrument_ids=None,
):
    specs = [_spec()]
    return SimpleNamespace(
        specs=specs,
        feed_stale_after_s=stale_after,
        feed_health=feed_health or {"scalp": FeedHealth(timeout_s=stale_after)},
        instrument_ids=instrument_ids or {"scalp": "BTCUSDT-PERP.BINANCE"},
        quote_beats=quote_beats,
    )


def test_no_quote_beats_no_verdict():
    """Replay/test wiring has no quotes at all — the watchdog must stay out
    of the way rather than read absence as death."""
    desk = _desk(quote_beats=None)
    assert feed_watchdog_verdict(desk, started_monotonic=0.0) is None
    desk2 = _desk(quote_beats={})
    assert feed_watchdog_verdict(desk2, started_monotonic=0.0) is None


def test_boot_grace_suppresses_verdict():
    """A fresh feed is legitimately stale until the first close; within one
    staleness timeout of boot the watchdog never fires, whatever it sees."""
    import time

    now = time.monotonic()
    desk = _desk(
        stale_after=180.0,
        quote_beats={"BTCUSDT-PERP.BINANCE": now},
    )
    # booted 60s ago — inside the 180s grace
    assert feed_watchdog_verdict(desk, started_monotonic=now - 60) is None


def test_partition_never_restarts():
    """Quotes silent with everything else: the wire is dead, restarting
    re-seeds into the same partition. The verdict must stay None even when
    bars have been silent far past the restart threshold."""
    import time

    now = time.monotonic()
    health = FeedHealth(timeout_s=180.0)
    health.beat()  # one bar long ago, then silence
    health._last_beat = now - 7200  # two hours of bar silence
    desk = _desk(
        feed_health={"scalp": health},
        quote_beats={"BTCUSDT-PERP.BINANCE": now - 600},  # quotes dead too
    )
    assert feed_watchdog_verdict(desk, started_monotonic=now - 7300) is None


def test_subscription_death_shape_restarts():
    """The soak's failure: bars silent for hours, quotes flowing seconds ago.
    The verdict names the bot and carries the evidence."""
    import time

    now = time.monotonic()
    health = FeedHealth(timeout_s=180.0)
    health.beat()
    health._last_beat = now - 7200
    desk = _desk(
        feed_health={"scalp": health},
        quote_beats={"BTCUSDT-PERP.BINANCE": now - 2},
    )
    verdict = feed_watchdog_verdict(desk, started_monotonic=now - 7300)
    assert verdict is not None
    assert verdict["bot"] == "scalp"
    assert verdict["bars_silent_s"] > 7000
    assert verdict["last_quote_s"] < 5


def test_threshold_not_tripped_inside_double_timeout():
    """Silence shorter than 2x the staleness timeout is the honest recovery
    window — reconnects and backfills legitimately cost minutes on fast
    tapes, hours on slow ones."""
    import time

    now = time.monotonic()
    health = FeedHealth(timeout_s=180.0)
    health.beat()
    health._last_beat = now - 300  # 300s < 2x180s
    desk = _desk(
        feed_health={"scalp": health},
        quote_beats={"BTCUSDT-PERP.BINANCE": now - 1},
    )
    assert feed_watchdog_verdict(desk, started_monotonic=now - 400) is None


def test_never_delivered_feed_measured_from_boot():
    """A feed that never closed a bar reads silence from boot, not infinity —
    infinity would fire the instant the boot grace ends."""
    import time

    now = time.monotonic()
    health = FeedHealth(timeout_s=180.0)  # never beaten
    desk = _desk(
        feed_health={"scalp": health},
        quote_beats={"BTCUSDT-PERP.BINANCE": now - 1},
    )
    # 200s after boot: past grace, but silence measured from boot is
    # 200s < 360s (2x timeout) — no verdict
    assert feed_watchdog_verdict(desk, started_monotonic=now - 200) is None
    # 400s after boot: silence 400s > 360s — the never-delivered kline
    # subscription IS the vendor failure shape; verdict fires
    verdict = feed_watchdog_verdict(desk, started_monotonic=now - 400)
    assert verdict is not None


def test_quote_liveness_window_boundary():
    """A quote beat older than QUOTE_ALIVE_S reads as a dead wire — the
    liveness evidence must be fresh, stale evidence is no evidence."""
    import time

    now = time.monotonic()
    health = FeedHealth(timeout_s=180.0)
    health.beat()
    health._last_beat = now - 7200
    desk = _desk(
        feed_health={"scalp": health},
        quote_beats={"BTCUSDT-PERP.BINANCE": now - QUOTE_ALIVE_S - 1},
    )
    assert feed_watchdog_verdict(desk, started_monotonic=now - 7300) is None


def test_stale_for_semantics():
    """The duration primitive the verdict consumes: never-beaten is inf,
    beaten is elapsed wall time."""
    health = FeedHealth(timeout_s=10.0)
    assert health.stale_for() == float("inf")
    assert health.stale() is True
    health.beat()
    assert health.stale_for() < 1.0
    assert health.stale() is False
