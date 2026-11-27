"""The prediction track record's table.

Analysis F-7: cmd_predict's forward-return measurement died on a terminal —
scored once, printed, forgotten, so the program's only forward-looking
instrument had no track record by construction. One table:

- predictions: one row per (symbol, timeframe, artifact_kind,
  bar_close_time), written by the scanner process (trading/predictions.py),
  never by the API. The prediction half is written at scan time with its
  noise scale and training boundary; the outcome half (outcome_return,
  scored_at, correct_direction) is NULL until the horizon-close scoring
  pass measures it against the candle store.

Same additive-and-tolerant pattern as the lineage: a present table is
adopted, never recreated. The scanner is a writer and calls init_schema
on its own database as well, so databases the scanner touched before this
migration ran may already carry a byte-identical table.

Revision ID: e5f6a7b8c9d0
Revises: d8e9f0a1b2c3
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

log = logging.getLogger("alembic.trading")

revision = "e5f6a7b8c9d0"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None


def _create_predictions() -> None:
    op.create_table(
        "predictions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("artifact_kind", sa.String(length=16), nullable=False),
        sa.Column("horizon_bars", sa.Integer(), nullable=False),
        sa.Column("predicted_return", sa.Float(), nullable=False),
        sa.Column("noise", sa.Float(), nullable=False),
        sa.Column("noise_basis", sa.String(length=32), nullable=False),
        sa.Column("z_score", sa.Float(), nullable=False),
        sa.Column("oof_corr", sa.Float(), nullable=True),
        sa.Column("bar_close_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trained_through", sa.String(length=64), nullable=False),
        sa.Column("artifact_file", sa.String(length=256), nullable=False),
        sa.Column("outcome_return", sa.Float(), nullable=True),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correct_direction", sa.Boolean(), nullable=True),
    )
    op.create_index(
        "ix_predictions_series_bar",
        "predictions",
        ["symbol", "timeframe", "artifact_kind", "bar_close_time"],
        unique=True,
    )
    op.create_index("ix_predictions_unscored", "predictions", ["artifact_kind", "scored_at"])
    op.create_index("ix_predictions_ts", "predictions", ["ts"])


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "predictions" in existing:
        log.warning(
            "trading migration: table predictions already present (pre-lineage create_all) — adopting, not recreating",
        )
    else:
        _create_predictions()


def downgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "predictions" not in existing:
        return
    for index in sa.inspect(op.get_bind()).get_indexes("predictions"):
        op.drop_index(index["name"], table_name="predictions")
    op.drop_table("predictions")
