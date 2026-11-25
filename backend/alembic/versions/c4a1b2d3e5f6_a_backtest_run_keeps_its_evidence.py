"""A backtest run keeps its evidence: the equity curve and the trade list.

A run reduced to six summary metrics is a number nobody can draw. The
dashboard's chart needs the equity path, and the fill-model audit (design
§7, M2) needs the individual trades with entry/exit times and prices. Both
are stored as JSON text columns on `backtest_runs` — bulky per-row evidence
that belongs to exactly one run and is never queried relationally, so
normalized tables would buy nothing here.

Additive and tolerant in the same spirit as a3f1c2d4e5b6: databases created
by a pre-lineage create_all may already carry these columns (identical DDL
either way); a present column is adopted, never recreated, and a genuinely
diverging one still fails loudly at the first write.

Revision ID: c4a1b2d3e5f6
Revises: b7e2d3f4a5c6
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

log = logging.getLogger("alembic.trading")

revision = "c4a1b2d3e5f6"
down_revision = "b7e2d3f4a5c6"
branch_labels = None
depends_on = None

_COLUMNS = ("equity_curve_json", "trades_json")


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "backtest_runs" not in existing:
        return
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("backtest_runs")}
    for name in _COLUMNS:
        if name in cols:
            log.warning(
                "trading migration: backtest_runs.%s already present — adopting, not re-adding",
                name,
            )
            continue
        op.add_column("backtest_runs", sa.Column(name, sa.Text(), nullable=True))


def downgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "backtest_runs" not in existing:
        return
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("backtest_runs")}
    for name in reversed(_COLUMNS):
        if name in cols:
            op.drop_column("backtest_runs", name)
