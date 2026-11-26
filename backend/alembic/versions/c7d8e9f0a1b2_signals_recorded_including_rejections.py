"""Every signal is recorded, including the rejected ones.

M3 acceptance (hedge-fund-os.md, M3 line: "every signal recorded including
rejections") and design §4 line 433 — the signals table every emission the
kernel strategy produces writes: side, confidence, the signal bar's own
timestamp, and the outcome vocabulary (entered / veto:<rail> / qty_zero /
below_confidence / no_atr / in_position / exited / flat_noop). The sizing
chain travels in details_json so the dashboard can walk
trade → order intent → sizing → signal → version (§8 TRADING OPS).

Same additive-and-tolerant pattern as the lineage: databases built by a
pre-lineage create_all may already carry a byte-identical table from the
same model; a present table is adopted, never recreated.

Revision ID: c7d8e9f0a1b2
Revises: c6d7e8f9a0b1
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

log = logging.getLogger("alembic.trading")

revision = "c7d8e9f0a1b2"
down_revision = "c6d7e8f9a0b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "signals" in existing:
        log.warning(
            "trading migration: table signals already present (pre-lineage create_all) — adopting, not recreating",
        )
    else:
        op.create_table(
            "signals",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("bot", sa.String(length=32), nullable=False),
            sa.Column("symbol", sa.String(length=32), nullable=False),
            sa.Column("timeframe", sa.String(length=8), nullable=False),
            sa.Column("bar_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("side", sa.String(length=5), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("outcome", sa.String(length=64), nullable=False),
            sa.Column("details_json", sa.Text(), nullable=False),
        )
        op.create_index("ix_signals_created_at", "signals", ["created_at"])
        op.create_index("ix_signals_bot", "signals", ["bot"])
        op.create_index("ix_signals_bot_bar", "signals", ["bot", "bar_time"])
    # the provenance chain's anchor: trades point at the signal bar they came
    # from — nullable, because rows predate the recording seam. Applies whether
    # or not the signals table was adopted: the chain is independent of it.
    if "trades" in existing:
        cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("trades")}
        if "signal_time" not in cols:
            op.add_column("trades", sa.Column("signal_time", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "signals" not in existing:
        return
    for index in sa.inspect(op.get_bind()).get_indexes("signals"):
        op.drop_index(index["name"], table_name="signals")
    op.drop_table("signals")
