"""Rails keep their evidence, and the lifecycle owns what may trade.

M3 slice 4 (docs/design/m3-paper-plan.md, hedge-fund-os.md §6): the risk_events
table every Layer-0 rail firing writes — rail name, bot, decision and the
inputs the decision stood on, because a rail that cannot explain itself is
removed, not trusted — plus the lifecycle registry tables: strategies,
strategy_versions, the append-only strategy_states transition log, and the
approvals stub the human-gated transitions will read (the card flow is M4;
the table exists now so the guard is real code against a real table).

Same additive-and-tolerant pattern as a3f1c2d4e5b6: databases built by a
pre-lineage create_all may already carry byte-identical tables from the same
models; a present table is adopted, never recreated, and a genuinely
diverging shape still fails loudly at the first write.

Revision ID: b4c5d6e7f8a9
Revises: a1b2c3d4e5f7
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

log = logging.getLogger("alembic.trading")

revision = "b4c5d6e7f8a9"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def _tables() -> dict[str, list]:
    return {
        "risk_events": [
            lambda: op.create_table(
                "risk_events",
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
                sa.Column("bot", sa.String(length=64), nullable=False),
                sa.Column("symbol", sa.String(length=32), nullable=False),
                sa.Column("rail", sa.String(length=48), nullable=False),
                sa.Column("decision", sa.String(length=24), nullable=False),
                sa.Column("inputs_json", sa.Text(), nullable=False),
                sa.Column("tape_ts", sa.Float(), nullable=False),
            ),
            lambda: op.create_index("ix_risk_events_created_at", "risk_events", ["created_at"]),
            lambda: op.create_index("ix_risk_events_bot", "risk_events", ["bot"]),
        ],
        "strategies": [
            lambda: op.create_table(
                "strategies",
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column("key", sa.String(length=32), nullable=False),
                sa.Column("name", sa.String(length=64), nullable=False),
                sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
                sa.UniqueConstraint("key", name="uq_strategies_key"),
            ),
        ],
        "strategy_versions": [
            lambda: op.create_table(
                "strategy_versions",
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column("strategy_id", sa.Integer(), sa.ForeignKey("strategies.id"), nullable=False),
                sa.Column("version", sa.Integer(), nullable=False),
                sa.Column("params_json", sa.Text(), nullable=False),
                sa.Column("code_hash", sa.String(length=64), nullable=False),
                sa.Column("timeframe", sa.String(length=8), nullable=False),
                sa.Column("universe_json", sa.String(length=256), nullable=False),
                sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            ),
            lambda: op.create_index(
                "ix_version_unique", "strategy_versions", ["strategy_id", "version"], unique=True
            ),
        ],
        "strategy_states": [
            lambda: op.create_table(
                "strategy_states",
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column("version_id", sa.Integer(), sa.ForeignKey("strategy_versions.id"), nullable=False),
                sa.Column("state", sa.String(length=16), nullable=False),
                sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
                sa.Column("evidence", sa.String(length=128), nullable=False),
                sa.Column("note", sa.String(length=256), nullable=False),
            ),
            lambda: op.create_index("ix_strategy_states_version_id", "strategy_states", ["version_id"]),
        ],
        "approvals": [
            lambda: op.create_table(
                "approvals",
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column("version_id", sa.Integer(), sa.ForeignKey("strategy_versions.id"), nullable=False),
                sa.Column("transition", sa.String(length=32), nullable=False),
                sa.Column("approved_by", sa.String(length=64), nullable=False),
                sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
                sa.Column("note", sa.String(length=256), nullable=False),
            ),
            lambda: op.create_index("ix_approvals_version_id", "approvals", ["version_id"]),
        ],
    }


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for table, statements in _tables().items():
        if table in existing:
            log.warning(
                "trading migration: table %s already present (pre-lineage create_all) — adopting, not recreating",
                table,
            )
            continue
        for statement in statements:
            statement()


def downgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for table in reversed(list(_tables())):
        if table not in existing:
            continue
        for index in sa.inspect(op.get_bind()).get_indexes(table):
            op.drop_index(index["name"], table_name=table)
        op.drop_table(table)
