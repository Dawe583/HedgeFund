"""The divergence budget is declared, and fills carry their drift evidence.

M3 slice 5 (docs/design/m3-paper-plan.md, hedge-fund-os.md §7 gate item 6):
the per-version divergence budget columns on strategy_versions — how far
paper may drift from the fill-at-close parity contract before the lifecycle
flags it — plus the measured per-fill evidence on trades and open_positions:
the deviation in ticks from the role-implied reference price, and the entry
timing lag in bars against the signal(k-1) → close(k) contract.

All nullable on purpose: rows written before the measurement existed carry
nothing, and a null drift column is the honest answer — a rearmed position's
original entry can predate the restart's frame, and inventing a reference
price for it would be exactly the lie the budget exists to catch.

Same additive-and-tolerant pattern as the lineage: no-op when the column
already exists, because init_schema's create_all may have produced it on
fresh databases.

Revision ID: c6d7e8f9a0b1
Revises: b4c5d6e7f8a9
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

log = logging.getLogger("alembic.trading")

revision = "c6d7e8f9a0b1"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None

_COLUMNS = {
    "trades": [
        ("entry_dev_ticks", sa.Float()),
        ("exit_dev_ticks", sa.Float()),
        ("entry_lag_bars", sa.Integer()),
    ],
    "open_positions": [
        ("entry_dev_ticks", sa.Float()),
        ("entry_ref_price", sa.Float()),
        ("entry_lag_bars", sa.Integer()),
    ],
    "strategy_versions": [
        ("budget_dev_ticks", sa.Float()),
        ("budget_entry_lag_bars", sa.Integer()),
        ("budget_missed_bars", sa.Integer()),
    ],
}


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    for table, columns in _COLUMNS.items():
        if table not in tables:
            continue
        existing = {c["name"] for c in sa.inspect(bind).get_columns(table)}
        for name, ddl in columns:
            if name not in existing:
                op.add_column(table, sa.Column(name, ddl, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    for table, columns in _COLUMNS.items():
        if table not in set(sa.inspect(bind).get_table_names()):
            continue
        existing = {c["name"] for c in sa.inspect(bind).get_columns(table)}
        for name, _ in columns:
            if name in existing:
                op.drop_column(table, name)
