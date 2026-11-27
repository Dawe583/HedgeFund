"""The lifecycle registry — what the engine may trade, and how it got there
(design §6 layer 1, §7 registration).

The static STRATEGIES dict in research.py stays the CATALOG of available
code; this module is the act of registration. Nothing trades for existing in
the catalog — a version reaches the desk's roster only by walking the state
machine:

    research → validated → paper → candidate_live → live

Transition guards (the only write paths in this module):
- research → validated: ONLY with a backtest_validations row for this exact
  version — verdict "validated", matching bot/strategy key and parameter
  set. No evidence, no transition. ONE structural exception: verdict
  "control" on versions whose code hash matches a registered
  instrumentation-control class (see register_control) — the control never
  passed validation and its rows say so in every provenance surface.
- validated → paper: unconditional, automatic — paper is free. (The CLI
  chains it the moment validation lands.)
- paper → candidate_live: REFUSES without an approvals row for this version
  and transition. The approval-card flow that writes those rows is M4; the
  approvals table exists now as the honest stub, so the guard is real code
  against a real table, not a TODO.
- candidate_live → live: refuses unless BOTH independent M5 gates hold —
  an active (unexpired) mandate row for the version AND the human's audit
  signoff row. Neither exists by default, so live stays structurally
  unreachable until the written audit is signed off and consent is granted.
- everything else — backward, equal, skipped states: refused.

The AI rule (design §6): the model may never transition a state. These
functions are deterministic code called by humans and the validation CLI;
there is no agent path into this module.

The roster: versions whose latest state is `paper`. With zero validated
strategies the roster is empty, the desk boots empty, and that emptiness IS
the gate working — the honest M3 end state.
"""

from __future__ import annotations

import hashlib
import inspect
import json

from sqlalchemy import select
from trading.divergence import DivergenceBudget

from trading.models import (
    Approval,
    BacktestValidation,
    Strategy,
    StrategyState,
    StrategyVersion,
)

STATES = ("research", "validated", "paper", "candidate_live", "live")

# Instrumentation controls (trading/bots/random_control_bot.py): strategies
# whose expectations are known by construction — never alpha. The registry
# binds this claim STRUCTURALLY: a version may walk the control path only
# when its code_hash matches the control class's own hash, so the honesty
# of the ledger does not depend on anyone's notes being truthful. Controls
# are hard-frozen at paper: the human-gated edges beyond it refuse them
# outright, because there is no alpha an approval could approve.
def _control_code_hashes() -> set[str]:
    """Content hashes of every class the registry accepts as an
    instrumentation control. Lazy import: bots must never become a registry
    dependency at module load."""
    from trading.bots.random_control_bot import RandomControl

    return {code_hash_of(RandomControl)}

# forward edges and what each demands: the guard table the design's prose
# compiles to. candidate_live→live lists the approval it needs AND refuses
# outright in M3 — the mandate (M5) is a mandatory companion that cannot
# exist yet.
_FORWARD = {
    ("research", "validated"),
    ("validated", "paper"),
    ("paper", "candidate_live"),
    ("candidate_live", "live"),
}


class TransitionRefused(Exception):
    """The guard's only answer besides the row. Carries the reason — a
    refusal that cannot explain itself is a bug, same rule as the rails."""


def code_hash_of(cls) -> str:
    """Content hash of the strategy class's source — the version's claim
    about WHAT code it is. Two versions sharing logic but not parameters
    share the hash; an edit to the class makes every pre-edit version's hash
    honest evidence of a different experiment."""
    try:
        src = inspect.getsource(cls)
    except (OSError, TypeError):
        src = repr(cls)
    return hashlib.sha256(src.encode()).hexdigest()[:16]


def _current_state(session, version_id: int) -> str | None:
    row = (
        session.execute(
            select(StrategyState)
            .where(StrategyState.version_id == version_id)
            .order_by(StrategyState.id.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    return row.state if row else None


def register_strategy(session, key: str, name: str) -> Strategy:
    """Idempotent by key — registration is an act, re-running it is not a
    second act."""
    row = session.execute(select(Strategy).where(Strategy.key == key)).scalars().first()
    if row is not None:
        return row
    row = Strategy(key=key, name=name)
    session.add(row)
    session.flush()
    return row


def register_version(
    session,
    key: str,
    name: str,
    cls,
    *,
    timeframe: str,
    universe: list[str],
    params: dict,
    budget: "DivergenceBudget | None" = None,
) -> StrategyVersion:
    """A new version row in state research. The constructor is validated
    HERE, not at roster time: a version whose params its own class cannot
    accept is a registration error, and registration is the cheap place to
    say so.

    budget: the divergence budget declaration (design §7 gate item 6) — how
    far paper may drift from the fill-at-close parity contract before the
    lifecycle flags it. None means never declared: the columns stay null
    and the desk measures against the zero-drift defaults, honestly
    reported as defaults rather than invented precision."""
    try:
        cls(**params)
    except TypeError as exc:
        raise TransitionRefused(
            f"params {sorted(params)} do not construct {cls.__name__}: {exc}"
        ) from exc
    strategy = register_strategy(session, key, name)
    latest = (
        session.execute(
            select(StrategyVersion)
            .where(StrategyVersion.strategy_id == strategy.id)
            .order_by(StrategyVersion.version.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    version = StrategyVersion(
        strategy_id=strategy.id,
        version=(latest.version + 1) if latest else 1,
        params_json=json.dumps(params, sort_keys=True),
        code_hash=code_hash_of(cls),
        timeframe=timeframe,
        universe_json=json.dumps(list(universe)),
        budget_dev_ticks=budget.dev_ticks if budget is not None else None,
        budget_entry_lag_bars=budget.entry_lag_bars if budget is not None else None,
        budget_missed_bars=budget.missed_bars if budget is not None else None,
    )
    session.add(version)
    session.flush()
    session.add(StrategyState(version_id=version.id, state="research", note="registered"))
    session.flush()
    return version


def transition(session, version_id: int, to_state: str, *, validation_id: int | None = None, note: str = "") -> StrategyState:
    """The state machine's only write path. Refuses loudly — TransitionRefused
    with the reason — and never writes anything on a refusal."""
    if to_state not in STATES:
        raise TransitionRefused(f"unknown state {to_state!r}")
    version = session.get(StrategyVersion, version_id)
    if version is None:
        raise TransitionRefused(f"strategy version {version_id} does not exist")
    current = _current_state(session, version_id)
    if current is None:
        raise TransitionRefused(f"strategy version {version_id} has no initial state row")
    edge = (current, to_state)
    if edge not in _FORWARD:
        raise TransitionRefused(
            f"{current} → {to_state} is not a forward single-step transition "
            f"(state is the latest row; re-basing is impossible)"
        )

    evidence = ""
    if edge == ("research", "validated"):
        if validation_id is None:
            raise TransitionRefused(
                "research → validated requires a validation row — no evidence, no transition"
            )
        row = session.get(BacktestValidation, validation_id)
        if row is None:
            raise TransitionRefused(f"validation row {validation_id} does not exist")
        if row.verdict == "control":
            # the instrumentation-control path (see register_control): the
            # row is NOT a verdict on alpha — it is the designation itself,
            # and the guard accepts it only when the version's code hash
            # provably IS a control class. An alpha candidate cannot reach
            # validated through this door without literally becoming the
            # control's source code.
            if version.code_hash not in _control_code_hashes():
                raise TransitionRefused(
                    "validation row verdict 'control' applies only to versions whose "
                    "code hash matches a registered instrumentation-control class — "
                    "this version is not one, so the row is no evidence at all"
                )
        elif row.verdict != "validated":
            raise TransitionRefused(
                f"validation row {validation_id} says {row.verdict!r}, not 'validated'"
            )
        strategy = session.get(Strategy, version.strategy_id)
        if row.bot != strategy.key:
            raise TransitionRefused(
                f"validation row {validation_id} is for bot {row.bot!r}, not {strategy.key!r}"
            )
        if json.loads(row.params_json or "{}") != json.loads(version.params_json or "{}"):
            raise TransitionRefused(
                "validation row params do not match this version's params — "
                "the evidence belongs to a different experiment"
            )
        evidence = f"validation:{validation_id}"
    elif edge == ("paper", "candidate_live"):
        if version.code_hash in _control_code_hashes():
            # instrumentation controls are hard-frozen at paper: there is no
            # alpha an approval card could approve, and a control in
            # candidate_live would be the ledger lying about what it holds.
            raise TransitionRefused(
                "instrumentation controls never leave paper — there is no alpha "
                "to approve; the control's expectations are known by construction"
            )
        approval = (
            session.execute(
                select(Approval).where(
                    Approval.version_id == version_id,
                    Approval.transition == "paper->candidate_live",
                )
            )
            .scalars()
            .first()
        )
        if approval is None:
            raise TransitionRefused(
                "paper → candidate_live requires a human approval card — the approvals "
                "table is the stub M4 fills, and it holds no row for this version"
            )
        evidence = f"approval:{approval.id}"
    elif edge == ("candidate_live", "live"):
        # the design's 'approval card PLUS a mandate' — M5 builds both halves
        # as independent refusals: the mandate (layer 2, the human's immutable
        # consent) AND the audit signoff (the written live-readiness audit,
        # signed off by the owner). Neither exists today, so live stays
        # correctly unreachable; when both exist the transition proceeds and
        # its evidence names both rows. Each refusal names its missing half —
        # consent without the audit is not readiness, and an audit without
        # consent is not permission.
        from trading.mandate import active_mandate, live_blockers
        from trading.models import AuditSignoff

        blockers = live_blockers(session, version_id)
        if blockers:
            raise TransitionRefused(
                "candidate_live → live refused: " + "; ".join(blockers)
            )
        mandate = active_mandate(session, version_id)
        signoff = (
            session.execute(
                select(AuditSignoff).where(AuditSignoff.version_id == version_id).order_by(AuditSignoff.id.desc())
            )
            .scalars()
            .first()
        )
        evidence = f"mandate:{mandate.id}+signoff:{signoff.id}"

    row = StrategyState(version_id=version_id, state=to_state, evidence=evidence, note=note)
    session.add(row)
    session.flush()
    if to_state in ("candidate_live", "live"):
        # the lifecycle's human-gated edges write to the audit ledger (M5 §D):
        # actor 'human' because both transitions exist only behind a human's
        # card — the approval row for paper → candidate_live, the mandate +
        # signoff for candidate_live → live.
        from trading.mandate import append_audit

        append_audit(
            session,
            "human",
            f"lifecycle_transition_{to_state}",
            {"version_id": version_id, "state_row_id": row.id, "evidence": evidence, "note": note},
        )
    session.flush()
    return row


def validate_and_promote(session, version_id: int, validation_id: int) -> list[StrategyState]:
    """The automatic chain: research → validated on the validation row's
    evidence, then validated → paper because paper is free. Both rows in one
    call because neither is a human decision — the human decisions are
    exactly the ones this function does not make."""
    out = [transition(session, version_id, "validated", validation_id=validation_id)]
    out.append(transition(session, version_id, "paper", note="automatic — paper is free"))
    return out


def register_control(
    session,
    key: str,
    name: str,
    cls,
    *,
    timeframe: str,
    universe: list[str],
    params: dict,
    budget: "DivergenceBudget | None" = None,
) -> dict:
    """Register an INSTRUMENTATION CONTROL into paper — the negative control
    whose expectations are known by construction (trading/bots/
    random_control_bot.py). The desk's operational plane has never run under
    load with an empty roster; the control exists so veto tape, divergence
    measurement, reconciliation and lifecycle transitions finally run
    against a flow whose truth is known in advance.

    Honesty design — read before copying this pattern:

    1. The control NEVER passed validation, and nothing here pretends it
       did. The validation row written below carries verdict 'control' —
       a designation, not a verdict on evidence. Its numeric fields are
       zeros and empty strings because no backtest exists; inventing
       numbers would be the lie this function exists to avoid.
    2. validate_and_promote is deliberately NOT used: its chain implies the
       validation gate's machinery ran and passed. Here each transition's
       note states precisely what the row means — the validated state is a
       lifecycle formality for roster plumbing, not a verdict.
    3. The binding is structural, not clerical: transition() accepts the
       'control' verdict only for versions whose code_hash matches the
       control class's own source hash, and refuses controls past paper
       outright. The honesty of the ledger therefore survives careless
       callers of this function. NOT idempotent: every call writes a new
       version row (same params, next version number) — registration is an
       act, and the driving script checks the roster before calling.
    4. The declaration travels in the version's params (declared_role) and
       in every transition note — roster dumps, divergence records and
       signal tapes all restate what this is."""
    from trading.bots.random_control_bot import CONTROL_DECLARATION

    if cls.__name__ != "RandomControl" or code_hash_of(cls) not in _control_code_hashes():
        raise TransitionRefused(
            "register_control registers instrumentation controls only — "
            f"{cls.__name__} is not a control class the registry recognizes"
        )
    # declared_role is not a degree of freedom: a registration that does not
    # carry the declaration is precisely the lie the ledger cannot afford.
    params = {**params, "declared_role": CONTROL_DECLARATION}
    version = register_version(
        session, key, name, cls, timeframe=timeframe, universe=universe, params=params, budget=budget
    )
    if _current_state(session, version.id) != "research":
        raise TransitionRefused(
            f"version {version.id} is not in research after registration — refusing to guess"
        )

    # the designation row: verdict 'control', honest emptiness everywhere a
    # backtest would have written numbers. params_json MUST equal the
    # version's exactly — transition() enforces it on this edge too.
    designation = BacktestValidation(
        bot=key,
        symbol="",
        timeframe=timeframe,
        strategy=name,
        params_json=json.dumps(params, sort_keys=True),
        seed=int(params.get("seed", 0)),
        data_source="none",
        data_rows=0,
        data_start="",
        data_end="",
        trades_n=0,
        min_trades_required=0,
        permutation_p=None,
        sharpe_actual=None,
        sharpe_ci_lo=None,
        sharpe_ci_hi=None,
        prob_positive=None,
        wf_positive_folds=0,
        wf_total_folds=0,
        verdict="control",
        reasons_json=json.dumps([CONTROL_DECLARATION]),
        validation_json=json.dumps({"designation": CONTROL_DECLARATION, "no_backtest_exists": True}),
        run_id=None,
        engine_version=None,
    )
    session.add(designation)
    session.flush()

    states = [
        transition(
            session,
            version.id,
            "validated",
            validation_id=designation.id,
            note=CONTROL_DECLARATION,
        ),
        transition(
            session,
            version.id,
            "paper",
            note="paper is free — " + CONTROL_DECLARATION,
        ),
    ]
    return {
        "version_id": version.id,
        "validation_id": designation.id,
        "states": [(s.state, s.note) for s in states],
    }


def roster(session) -> list[dict]:
    """The desk's roster: every version whose LATEST state row is `paper`,
    with what the desk needs to boot it. Empty is the honest answer — with
    zero validated strategies the lifecycle owns nothing, and the desk that
    boots from this roster trades nothing."""
    versions = session.execute(select(StrategyVersion)).scalars().all()
    strategies = {s.id: s for s in session.execute(select(Strategy)).scalars().all()}
    out = []
    for v in versions:
        if _current_state(session, v.id) != "paper":
            continue
        strategy = strategies[v.strategy_id]
        out.append(
            {
                "version_id": v.id,
                "key": strategy.key,
                "name": strategy.name,
                "bot": f"{strategy.key}-v{v.version}",
                "version": v.version,
                "params": json.loads(v.params_json or "{}"),
                "timeframe": v.timeframe,
                "universe": json.loads(v.universe_json or "[]"),
                "code_hash": v.code_hash,
                "budget": DivergenceBudget.from_row(v),
            }
        )
    return sorted(out, key=lambda r: r["bot"])
