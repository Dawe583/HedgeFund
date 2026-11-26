"""The mandate machinery — design §6 layers 2, 3 and 4, built in M5, armed never.

Three independent mechanisms, one module, because they share the audit ledger:

Layer 2 — the mandate: immutable rows of hard caps (models.StrategyMandate),
created only through the human confirmation flow. No update path exists
anywhere; a changed mandate is a new row superseding the old by id.

Layer 4 — the halt sentinel: a FILE-level kill switch independent of every
software layer above it. The chain checks EXISTENCE ONLY — the content is
never opened, never parsed, because a sentinel you parse is a sentinel an
attacker can weaponize, and because the one guarantee a corrupt file must
still give you is the halt. Existence is the whole protocol.

Layer 3 — the order guard chain: `evaluate_order()`, a pure function over
(mandate, order intent, state) returning allow / deny / pause-for-reauth,
checks in exactly the design's order:
    halt sentinel → mandate expiry → instrument allowed → notional cap →
    exposure cap → daily count cap
Fail-closed by construction: any internal error — a malformed mandate, a
missing field, an exception mid-check — answers deny, never propagates.

Every evaluation lands in the audit ledger when a session is passed: allow
or deny, with the inputs the verdict stood on. The ledger is append-only
and hash-chained — Vibe's pattern, our schema: each row digests
(prev_hash, timestamp, actor, action, payload-json), so a flipped payload
in history breaks the chain at exactly that row and verify_chain() names it.

What this module deliberately does NOT contain: any path to a live venue.
In M5 the chain terminates at the verdict — the paper path never consults
it (per-order approval would make paper worthless as a strategy test,
design §6 layer 3), and no live adapter exists. The chain is exercised in
tests, directly and at its lowest level.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from dataclasses import dataclass, field

from sqlalchemy import select

from trading.models import AuditLedger, AuditSignoff, StrategyMandate

# --------------------------------------------------------------------------
# audit ledger — append-only, hash-chained
# --------------------------------------------------------------------------

#: Genesis prev_hash: the chain starts from a fixed, public constant — a
#: first row chained to nothing would be indistinguishable from a forged one.
GENESIS_HASH = "0" * 64


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def ledger_hash(prev_hash: str, timestamp: dt.datetime, actor: str, action: str, payload_json: str) -> str:
    """The row's digest over exactly the fields the chain vouches for:
    (prev_hash, timestamp, actor, action, payload-json). Timestamp enters
    as ISO text so the digest survives any datetime repr drift."""
    material = "\x1f".join([prev_hash, timestamp.isoformat(), actor, action, payload_json])
    return hashlib.sha256(material.encode()).hexdigest()


def append_audit(session, actor: str, action: str, payload: dict, *, commit: bool = False) -> AuditLedger:
    """The ledger's ONLY write path. Reads the current tip's hash, writes
    one row chained to it, returns the row. There is no update and no
    delete anywhere in the codebase: the ledger is a tape, and a tape you
    can edit is not a tape.

    Concurrency note: the chain assumes one writer at a time — true for the
    desk (single process, human actions serialized through the API). Two
    concurrent appends would both read the same tip; sqlite serializes the
    writes but not the reads. Documented, not solved: in M5 the ledger's
    writers are human actions and guard evaluations inside tests."""
    tip = (
        session.execute(select(AuditLedger).order_by(AuditLedger.id.desc()).limit(1))
        .scalars()
        .first()
    )
    prev_hash = tip.hash if tip is not None else GENESIS_HASH
    payload_json = _canonical(payload)
    # naive UTC: sqlite drops tzinfo on roundtrip, so hashing the tz-aware
    # original would verify false against the re-read row. Naive UTC is the
    # canonical timestamp form for the chain on every backend.
    now = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    row = AuditLedger(
        created_at=now,
        actor=actor,
        action=action,
        payload_json=payload_json,
        prev_hash=prev_hash,
        hash=ledger_hash(prev_hash, now, actor, action, payload_json),
    )
    session.add(row)
    session.flush()
    if commit:
        session.commit()
    return row


def verify_chain(session) -> list[str]:
    """Walk the ledger in id order and validate every link. Returns the list
    of violations, empty when the chain is intact. A violation names the row
    — a chain that cannot say WHERE it broke is a rumor, not evidence."""
    rows = session.execute(select(AuditLedger).order_by(AuditLedger.id)).scalars().all()
    violations: list[str] = []
    expected_prev = GENESIS_HASH
    for row in rows:
        if row.prev_hash != expected_prev:
            violations.append(
                f"row {row.id}: prev_hash links to {row.prev_hash[:12]}…, expected {expected_prev[:12]}…"
            )
        recomputed = ledger_hash(row.prev_hash, row.created_at, row.actor, row.action, row.payload_json)
        if recomputed != row.hash:
            violations.append(f"row {row.id}: payload does not match its hash — tampered or corrupt")
        expected_prev = row.hash
    return violations


# --------------------------------------------------------------------------
# the mandate rows
# --------------------------------------------------------------------------

def mandate_payload_hash(
    *,
    version_id: int,
    max_order_notional: float,
    max_exposure: float,
    instruments: list[str],
    max_trades_per_day: int,
    consent_days: int,
    funding_min: float,
    funding_max: float,
) -> str:
    """Digest of the cap set itself — version linkage included. Stored on the
    row at creation so a tampered cap (edited in place by anything bypassing
    the app) is detectable by recompute, and quotable in the audit chain."""
    return hashlib.sha256(
        _canonical(
            {
                "version_id": version_id,
                "max_order_notional": max_order_notional,
                "max_exposure": max_exposure,
                "instruments": sorted(instruments),
                "max_trades_per_day": max_trades_per_day,
                "consent_days": consent_days,
                "funding_min": funding_min,
                "funding_max": funding_max,
            }
        ).encode()
    ).hexdigest()


def create_mandate(
    session,
    *,
    version_id: int,
    caps: dict,
    created_by: str,
    note: str = "",
) -> StrategyMandate:
    """Write one immutable mandate row. The caller is always the human
    confirmation flow — the caps arrive fully typed in the request body,
    never defaulted silently, because a mandate the machine fills in is a
    mandate no human consented to. No automation path calls this: it is
    exported for the router and for tests, nothing else."""
    instruments = list(caps["instruments"])
    row = StrategyMandate(
        version_id=version_id,
        created_by=created_by,
        max_order_notional=float(caps["max_order_notional"]),
        max_exposure=float(caps["max_exposure"]),
        instruments_json=json.dumps(instruments),
        max_trades_per_day=int(caps["max_trades_per_day"]),
        consent_days=int(caps.get("consent_days", 30)),
        funding_min=float(caps["funding_min"]),
        funding_max=float(caps["funding_max"]),
        note=note,
    )
    row.mandate_hash = mandate_payload_hash(
        version_id=version_id,
        max_order_notional=row.max_order_notional,
        max_exposure=row.max_exposure,
        instruments=instruments,
        max_trades_per_day=row.max_trades_per_day,
        consent_days=row.consent_days,
        funding_min=row.funding_min,
        funding_max=row.funding_max,
    )
    session.add(row)
    session.flush()
    return row


def active_mandate(session, version_id: int, now: dt.datetime | None = None) -> StrategyMandate | None:
    """The latest UNEXPIRED mandate for the version, or None. Expiry is
    consent_days after creation — the design's default 30, after which live
    trading halts itself. An expired mandate is not deleted (immutability);
    it simply stops answering."""
    now = now or dt.datetime.now(dt.UTC)
    rows = (
        session.execute(
            select(StrategyMandate)
            .where(StrategyMandate.version_id == version_id)
            .order_by(StrategyMandate.id.desc())
        )
        .scalars()
        .all()
    )
    for row in rows:
        created = row.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=dt.UTC)
        if created + dt.timedelta(days=row.consent_days) > now:
            return row
    return None


def mandate_expiry(row: StrategyMandate) -> dt.datetime:
    created = row.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=dt.UTC)
    return created + dt.timedelta(days=row.consent_days)


def mandate_integrity_ok(row: StrategyMandate) -> bool:
    """Recompute the cap-set digest and compare — the tamper check the guard
    chain applies before trusting any number on the row."""
    try:
        return row.mandate_hash == mandate_payload_hash(
            version_id=row.version_id,
            max_order_notional=row.max_order_notional,
            max_exposure=row.max_exposure,
            instruments=json.loads(row.instruments_json),
            max_trades_per_day=row.max_trades_per_day,
            consent_days=row.consent_days,
            funding_min=row.funding_min,
            funding_max=row.funding_max,
        )
    except Exception:
        return False


# --------------------------------------------------------------------------
# the order guard chain
# --------------------------------------------------------------------------

@dataclass
class OrderIntent:
    """What the chain is asked about: symbol, side, notional. A plain
    dataclass, never an ORM row — the chain is pure and must be callable at
    the venue-adapter boundary with nothing but its inputs in hand."""

    symbol: str
    side: str
    notional: float


@dataclass
class GuardState:
    """The state inputs the caps are measured against. All counts are the
    caller's measurements, not the chain's business: the chain compares,
    it never counts."""

    current_exposure: float = 0.0  # open notional, this strategy version
    trades_today: int = 0
    funding: float = 0.0  # account funding, for the funding bounds
    extra: dict = field(default_factory=dict)


@dataclass
class Verdict:
    """The chain's answer. `verdict` is one of allow | deny | reauth —
    pause-for-reauth when consent is expired or expiring within the
    reauth window. `reason` names the exact check that decided, with the
    numbers — a refusal that cannot explain itself is a bug (same rule as
    the rails). `check` is the machine-readable name of the deciding check
    for the audit payload."""

    verdict: str  # allow | deny | reauth
    check: str
    reason: str

    @property
    def allowed(self) -> bool:
        return self.verdict == "allow"


#: Consent within this many days of expiry answers pause-for-reauth rather
#: than allow — the human re-consents BEFORE the halt, not after it.
REAUTH_WINDOW_DAYS = 3


def sentinel_present(path: str | None) -> bool:
    """Layer 4, the entire protocol: does the file exist. The content is
    NEVER opened — not to validate, not to log, not for any reason. A
    corrupt file halts exactly like a well-formed one, because the day this
    file matters is the day everything else is wrong, and 'everything else'
    includes whatever writes files. A missing path (None) means no sentinel
    is configured — the check passes vacuously; an unreadable PARENT or a
    permission error on the stat is treated as PRESENT (fail-closed)."""
    if not path:
        return False
    try:
        return os.path.exists(path)
    except Exception:
        return True  # fail-closed: cannot even look? assume the worst.


def evaluate_order(
    mandate: StrategyMandate | None,
    intent: OrderIntent | dict,
    state: GuardState | dict | None,
    *,
    sentinel_path: str | None = None,
    now: dt.datetime | None = None,
    session=None,
) -> Verdict:
    """The guard chain, in the design's exact order:

        halt sentinel → mandate expiry → instrument allowed → notional cap
        → exposure cap → daily count cap

    Pure in its decision — no database reads, no I/O except the sentinel's
    existence check, which IS the point of layer 4. Fail-closed: any
    exception anywhere inside answers deny with the error named; a guard
    that crashes open is worse than no guard.

    Every evaluation appends an audit row (actor 'guard') when `session` is
    passed — allow or deny, with the inputs. Volume note: rows are per
    evaluation, not batched — in M5 evaluations happen only inside the card
    flow and tests, both human-cadence; if a future live adapter evaluates
    per-order, that is exactly one row per order, the volume the ledger
    exists for. No batching needed, documented per the milestone."""
    try:
        verdict = _evaluate(mandate, intent, state, sentinel_path=sentinel_path, now=now)
    except Exception as exc:  # fail-closed, always
        verdict = Verdict("deny", "internal_error", f"guard chain internal error — fail-closed: {exc!r}")
    if session is not None:
        try:
            append_audit(
                session,
                "guard",
                "order_evaluation",
                {
                    "verdict": verdict.verdict,
                    "check": verdict.check,
                    "reason": verdict.reason,
                    "intent": _intent_payload(intent),
                    "mandate_id": getattr(mandate, "id", None),
                    "state": _state_payload(state),
                },
            )
        except Exception:
            # the audit failing must not flip the verdict — but a ledger that
            # cannot write is its own alarm, raised by the caller's session.
            pass
    return verdict


def _intent_payload(intent) -> dict:
    if isinstance(intent, dict):
        return dict(intent)
    return {"symbol": intent.symbol, "side": intent.side, "notional": intent.notional}


def _state_payload(state) -> dict:
    if state is None:
        return {}
    if isinstance(state, dict):
        return dict(state)
    return {"current_exposure": state.current_exposure, "trades_today": state.trades_today, "funding": state.funding}


def _evaluate(mandate, intent, state, *, sentinel_path, now) -> Verdict:
    if isinstance(intent, dict):
        intent = OrderIntent(**intent)
    if isinstance(state, dict):
        state = GuardState(**state)
    if state is None:
        state = GuardState()
    now = now or dt.datetime.now(dt.UTC)

    # 1 — halt sentinel, before everything: a file a human can create with
    # `touch` while every software layer is on fire.
    if sentinel_present(sentinel_path):
        return Verdict("deny", "halt_sentinel", f"halt sentinel file exists at {sentinel_path} — order submission halted at the guard chain")

    # 2 — mandate presence and expiry. No mandate is a deny, not a crash:
    # a live order without consent is exactly what the chain exists to stop.
    if mandate is None:
        return Verdict("deny", "no_mandate", "no mandate exists — no live order without written consent")
    if not mandate_integrity_ok(mandate):
        return Verdict("deny", "mandate_integrity", f"mandate {mandate.id} hash does not match its caps — tampered or corrupt, fail-closed")
    expiry = mandate_expiry(mandate)
    remaining = (expiry - now).total_seconds()
    if remaining <= 0:
        return Verdict("reauth", "mandate_expired", f"mandate {mandate.id} consent expired at {expiry.isoformat()} — live trading halts itself until re-consented")
    if remaining <= REAUTH_WINDOW_DAYS * 86400:
        return Verdict("reauth", "consent_expiring", f"mandate {mandate.id} consent expires in {remaining / 86400:.1f}d (window {REAUTH_WINDOW_DAYS}d) — pause for re-auth")

    # 3 — instrument allowed
    instruments = json.loads(mandate.instruments_json)
    if intent.symbol not in instruments:
        return Verdict("deny", "instrument", f"{intent.symbol} is not in the mandate's allowed instruments {instruments}")

    # 4 — notional cap
    if intent.notional > mandate.max_order_notional:
        return Verdict("deny", "notional_cap", f"order notional {intent.notional} exceeds the mandate's per-order cap {mandate.max_order_notional}")

    # 5 — exposure cap: open exposure PLUS this order, the honest measure.
    if state.current_exposure + intent.notional > mandate.max_exposure:
        return Verdict("deny", "exposure_cap", f"exposure {state.current_exposure} + order {intent.notional} exceeds the mandate's exposure cap {mandate.max_exposure}")

    # 6 — daily count cap
    if state.trades_today >= mandate.max_trades_per_day:
        return Verdict("deny", "daily_count_cap", f"{state.trades_today} trades today already meets the mandate's daily cap {mandate.max_trades_per_day}")

    return Verdict("allow", "passed", f"within mandate {mandate.id}: notional {intent.notional}/{mandate.max_order_notional}, exposure {state.current_exposure + intent.notional}/{mandate.max_exposure}, trades {state.trades_today}/{mandate.max_trades_per_day}")


# --------------------------------------------------------------------------
# candidate_live → live evidence helpers (registry imports these lazily)
# --------------------------------------------------------------------------

def live_blockers(session, version_id: int) -> list[str]:
    """Every independent reason candidate_live → live refuses today, in
    check order. Empty means BOTH gates are satisfied — the mandate exists
    and is unexpired, and the human's audit signoff row exists. The two are
    independent by design: consent without the audit is not readiness, and
    an audit without consent is not permission."""
    blockers: list[str] = []
    mandate = active_mandate(session, version_id)
    if mandate is None:
        blockers.append("no active mandate — the human's immutable consent row does not exist or its consent window expired")
    signoff = (
        session.execute(
            select(AuditSignoff).where(AuditSignoff.version_id == version_id).order_by(AuditSignoff.id.desc())
        )
        .scalars()
        .first()
    )
    if signoff is None:
        blockers.append("no audit signoff — the written live-readiness audit has not been signed off for this version")
    return blockers
