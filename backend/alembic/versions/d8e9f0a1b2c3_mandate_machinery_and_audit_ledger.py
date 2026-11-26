"""The mandate machinery and the audit ledger.

M5 (hedge-fund-os.md, milestone M5): build — but do not arm — the mandate
and order-guard layer. Four tables:

- strategy_mandates: immutable rows of hard caps (design §6 layer 2) — max
  order notional, max exposure, allowed instruments, max trades per day,
  consent expiry window, funding bounds, plus a digest of the cap set.
  No update path exists in code; a changed mandate is a new row.
- order_cards: layer-3 per-order approval cards — the order intent with its
  full decision chain and a fingerprint over strategy state + mandate
  version, never the live price.
- audit_ledger: the append-only hash-chained tape — Vibe's pattern, our
  schema: each row digests (prev_hash, timestamp, actor, action, payload).
- audit_signoffs: the human's recorded signoff of the written live-readiness
  audit — the second independent gate on candidate_live → live.

Same additive-and-tolerant pattern as the lineage: databases built by a
pre-lineage create_all may already carry byte-identical tables from the
same models; a present table is adopted, never recreated.

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

log = logging.getLogger("alembic.trading")

revision = "d8e9f0a1b2c3"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def _create_strategy_mandates() -> None:
    op.create_table(
        "strategy_mandates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version_id", sa.Integer(), sa.ForeignKey("strategy_versions.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("max_order_notional", sa.Float(), nullable=False),
        sa.Column("max_exposure", sa.Float(), nullable=False),
        sa.Column("instruments_json", sa.Text(), nullable=False),
        sa.Column("max_trades_per_day", sa.Integer(), nullable=False),
        sa.Column("consent_days", sa.Integer(), nullable=False),
        sa.Column("funding_min", sa.Float(), nullable=False),
        sa.Column("funding_max", sa.Float(), nullable=False),
        sa.Column("note", sa.String(length=256), nullable=False),
        sa.Column("mandate_hash", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_strategy_mandates_version_id", "strategy_mandates", ["version_id"])


def _create_order_cards() -> None:
    op.create_table(
        "order_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version_id", sa.Integer(), sa.ForeignKey("strategy_versions.id"), nullable=False),
        sa.Column("mandate_id", sa.Integer(), sa.ForeignKey("strategy_mandates.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("notional", sa.Float(), nullable=False),
        sa.Column("chain_json", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.String(length=256), nullable=False),
    )
    op.create_index("ix_order_cards_version_id", "order_cards", ["version_id"])


def _create_audit_ledger() -> None:
    op.create_table(
        "audit_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(length=16), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("hash", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_audit_ledger_action", "audit_ledger", ["action"])
    op.create_index("ix_audit_ledger_hash", "audit_ledger", ["hash"])


def _create_audit_signoffs() -> None:
    op.create_table(
        "audit_signoffs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version_id", sa.Integer(), sa.ForeignKey("strategy_versions.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("document_ref", sa.String(length=256), nullable=False),
        sa.Column("note", sa.String(length=256), nullable=False),
    )
    op.create_index("ix_audit_signoffs_version_id", "audit_signoffs", ["version_id"])


_TABLES = {
    "strategy_mandates": _create_strategy_mandates,
    "order_cards": _create_order_cards,
    "audit_ledger": _create_audit_ledger,
    "audit_signoffs": _create_audit_signoffs,
}


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for table, create in _TABLES.items():
        if table in existing:
            log.warning(
                "trading migration: table %s already present (pre-lineage create_all) — adopting, not recreating",
                table,
            )
        else:
            create()


def downgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for table in reversed(list(_TABLES)):
        if table not in existing:
            continue
        for index in sa.inspect(op.get_bind()).get_indexes(table):
            op.drop_index(index["name"], table_name=table)
        op.drop_table(table)
