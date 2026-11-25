"""open_positions know their signal_time

The kernel desk's restart logic re-derives a position's age from the SIGNAL
bar's own timestamp, never from frame positions — those die with the process.
Nullable on purpose: rows written before the kernel migration simply don't
carry it, and the rearm logic treats a missing signal_time as unrecoverable
age (honest immediate close) rather than inventing one.

Same additive-DDL pattern as d5e6f7a8b9c0: no-op when the column already
exists, because init_schema's create_all may have produced it on fresh DBs.

Revision ID: a1b2c3d4e5f7
Revises: d5e6f7a8b9c0
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

log = logging.getLogger("alembic.trading")

revision = "a1b2c3d4e5f7"
down_revision = "d5e6f7a8b9c0"


def upgrade() -> None:
    cols = [c["name"] for c in sa.inspect(op.get_bind()).get_columns("open_positions")]
    if "open_positions" not in sa.inspect(op.get_bind()).get_table_names():
        return
    if "signal_time" in cols:
        return
    op.add_column("open_positions", sa.Column("signal_time", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    cols = [c["name"] for c in sa.inspect(op.get_bind()).get_columns("open_positions")]
    if "signal_time" in cols:
        op.drop_column("open_positions", "signal_time")
