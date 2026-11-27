"""Alert egress — one webhook sender behind the risk-event stream.

A smoke detector nobody watches is not a detector (90-day plan, weeks
9-10). Every rail firing already lands in risk_events with its inputs;
what never existed is the path OUT of the database. This module is that
path: a poller that reads un-sent severe events, posts them to a webhook
the operator controls, and records the sending in the kv state so a
restart never re-alerts (and never silently drops — a failed send leaves
the cursor behind, so the event is retried with the next batch).

Deliberately small:
- severity is a whitelist, not a heuristic: kill-switch trips, daily-loss
  breaches, halt observations and feed deaths page; entry vetoes and
  cooldown starts are the system's normal voice and would drown the
  channel — they stay in the database where they belong.
- one webhook, configured by TRADING_ALERT_WEBHOOK_URL (env). No URL
  configured means egress is off BY DESIGN — the scanner exits 0 with a
  note, because an unconfigured alert channel is a configuration fact,
  not an error. Slack/Discord/ntfy/generic JSON endpoints all accept a
  JSON POST; the payload carries both a `text` rendering and the
  structured event so any of them work.
- sending failure never crashes the caller: the desk's job is trading,
  alerting is a sidecar — a dead webhook must not take the desk with it.
"""

from __future__ import annotations

import json
import logging
import os

log = logging.getLogger(__name__)

# Decisions that page — everything else is the system's normal voice.
# Whitelisted, never heuristic: the operator tunes this list in code,
# because alert fatigue is how channels die.
SEVERE_DECISIONS = {"tripped", "breached", "halt_observed", "feed_dead", "flattened"}
SEVERE_RAILS = {"kill_switch_drawdown", "manual_killswitch", "halt_sentinel"}

_CURSOR_KEY = "alert_egress_cursor"


def severe(row) -> bool:
    """Whether one RiskEvent ORM row pages the operator."""
    return row.decision in SEVERE_DECISIONS or row.rail in SEVERE_RAILS


def render_text(row) -> str:
    """The one-line human rendering — reads like a pager, carries the why."""
    try:
        inputs = json.loads(row.inputs_json or "{}")
    except Exception:  # noqa: BLE001 — a corrupt payload still pages, minus detail
        inputs = {}
    detail = ", ".join(f"{k}={v}" for k, v in list(inputs.items())[:6])
    return f"[{row.rail}] {row.decision} — {row.bot} {row.symbol} ({detail})"[:900]


def send_pending(session, webhook_url: str, *, limit: int = 20, timeout_s: float = 10.0) -> dict:
    """POST every un-sent severe risk event to the webhook, oldest first.

    The cursor (kv state, `alert_egress_cursor`) is the last risk_events id
    successfully sent — it advances only after a successful POST, so a
    failed batch is retried whole next time. Returns a small report dict;
    never raises — the desk must not die because a webhook did.
    """
    from sqlalchemy import select

    from trading.models import RiskEvent, get_state, set_state

    report = {"sent": 0, "failed": 0, "pending": 0, "skipped_url": False}
    try:
        cursor = int(get_state(session, _CURSOR_KEY) or 0)
        rows = (
            session.execute(
                select(RiskEvent).where(RiskEvent.id > cursor).order_by(RiskEvent.id).limit(200)
            )
            .scalars()
            .all()
        )
        todo = [r for r in rows if severe(r)][:limit]
        report["pending"] = len(todo)
        if not todo:
            # the cursor still advances past non-severe rows — vetoes are not
            # pages, and scanning them forever is a growing cost
            if rows:
                set_state(session, _CURSOR_KEY, rows[-1].id)
            return report

        import httpx

        for row in todo:
            payload = {
                "text": render_text(row),
                "event": {
                    "id": row.id,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "bot": row.bot,
                    "symbol": row.symbol,
                    "rail": row.rail,
                    "decision": row.decision,
                    "inputs": json.loads(row.inputs_json or "{}"),
                    "tape_ts": row.tape_ts,
                },
                "source": "hedgefund-risk-events",
            }
            try:
                resp = httpx.post(webhook_url, json=payload, timeout=timeout_s)
                if resp.status_code < 300:
                    report["sent"] += 1
                    set_state(session, _CURSOR_KEY, row.id)
                else:
                    report["failed"] += 1
                    log.warning("alert webhook answered %s — cursor holds at %s, retried next run", resp.status_code, row.id)
                    break
            except Exception as exc:  # noqa: BLE001 — a dead webhook never kills the desk
                report["failed"] += 1
                log.warning("alert webhook unreachable (%s) — cursor holds, retried next run", exc)
                break
    except Exception:  # alerting is a sidecar, never a crash cause
        log.exception("alert egress failed")
    return report


def scan_once(app_db: str | None = None) -> dict:
    """One egress pass against the app database. Exit-shaped for cron:
    a missing webhook URL is a configuration fact (reported, exit 0),
    everything else returns the send report."""
    from trading.config import get_settings
    from trading.models import make_engine, make_session_factory

    url = os.environ.get("TRADING_ALERT_WEBHOOK_URL")
    if not url:
        return {"skipped_url": True, "note": "TRADING_ALERT_WEBHOOK_URL unset — egress off by design"}
    engine = make_engine(app_db or get_settings().database_url)
    sf = make_session_factory(engine)
    with sf() as session:
        report = scan_and_report(session, url)
    engine.dispose()
    return report


def scan_and_report(session, url: str) -> dict:
    report = send_pending(session, url)
    if report["sent"] or report["failed"]:
        log.info("alert egress: %s", report)
    return report
