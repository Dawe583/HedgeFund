"""Backtest provenance records which engine produced the run.

The M2 kernel migration moved validation onto nautilus behind the harness;
rows written before it came from the ported engine. Both engines are honest
— and different: the fill-timing and intrabar divergences are documented in
docs/research/kernel-diff-2026-11-25.md. A verdict row that cannot say which
execution model it stands on is provenance with a hole in it, and design §5
makes a run invalid without complete provenance. `engine_version` is a short
string — "nautilus-1.231.0+delayed-close" today — recorded on both
backtest_runs and backtest_validations. Rows predating the column stay NULL,
which reads correctly: their engine was never recorded, and the diff
document says what they were.

Additive and adoption-tolerant, same spirit as c4a1b2d3e5f6.

Revision ID: d5e6f7a8b9c0
Revises: c4a1b2d3e5f6
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

log = logging.getLogger("alembic.trading")

revision = "d5e6f7a8b9c0"
down_revision = "c4a1b2d3e5f6"
branch_labels = None
depends_on = None

_TABLES = ("backtest_runs", "backtest_validations")


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for table in _TABLES:
        if table not in existing:
            continue
        cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
        if "engine_version" in cols:
            log.warning(
                "trading migration: %s.engine_version already present — adopting, not re-adding",
                table,
            )
            continue
        op.add_column(table, sa.Column("engine_version", sa.String(64), nullable=True))


def downgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for table in _TABLES:
        if table not in existing:
            continue
        cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
        if "engine_version" in cols:
            op.drop_column(table, "engine_version")
