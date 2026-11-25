"""A trading engine keeps its ledger in the same database.

The trading engine ported from ScalpFX (design doc §3.2, decision D3) writes
its own tables — candles, paper trades, open positions, equity curve, bot
heartbeats, agent memory and predictions, model versions, backtest runs —
into the platform's one SQLite database, never a second file: one backup,
one migration lineage, one place where a number can be looked up.

Every table is additive and every name is prefixed by its purpose, so nothing
here collides with the wealth tables. The engine's own `make_engine` still
carries its idempotent `_migrate_sqlite` startup guard for databases that
were created by the standalone ScalpFX deployment before this lineage
existed; in this repository Alembic is the single authority and the guard
is a no-op on a database Alembic built, because the columns it would add are
already here.

Revision ID: a3f1c2d4e5b6
Revises: 1f24a6148f6b
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a3f1c2d4e5b6"
down_revision = "1f24a6148f6b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("open_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
    )
    op.create_index("ix_candles_open_time", "candles", ["open_time"])
    op.create_index(
        "ix_candles_sym_tf_time",
        "candles",
        ["symbol", "timeframe", "open_time"],
        unique=True,
    )

    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bot", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=4), nullable=False),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("exit_price", sa.Float(), nullable=False),
        sa.Column("entry_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pnl", sa.Float(), nullable=False),
        sa.Column("fees", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("gate_source", sa.String(length=16), nullable=False),
    )

    op.create_table(
        "open_positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bot", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=4), nullable=False),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("stop_loss", sa.Float(), nullable=False),
        sa.Column("take_profit", sa.Float(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("gate_source", sa.String(length=16), nullable=False),
    )

    op.create_table(
        "equity_points",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bot", sa.String(length=32), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("equity", sa.Float(), nullable=False),
    )
    op.create_index("ix_equity_points_ts", "equity_points", ["ts"])

    op.create_table(
        "bot_status",
        sa.Column("name", sa.String(length=32), primary_key=True),
        sa.Column("running", sa.Boolean(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(length=256), nullable=False),
    )

    op.create_table(
        "agent_insights",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agent", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("body", sa.String(length=4096), nullable=False),
        sa.Column("severity", sa.String(length=8), nullable=False),
        sa.Column("tags", sa.String(length=256), nullable=False),
        sa.Column("meta", sa.String(length=2048), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_insights_agent", "agent_insights", ["agent"])
    op.create_index("ix_agent_insights_created_at", "agent_insights", ["created_at"])

    op.create_table(
        "agent_memory",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bot", sa.String(length=32), nullable=False),
        sa.Column("tier", sa.String(length=8), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("content", sa.String(length=1024), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False),
        sa.Column("pnl_pct", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_memory_created_at", "agent_memory", ["created_at"])
    op.create_index(
        "ix_memory_tier_bot", "agent_memory", ["tier", "bot", "created_at"]
    )

    op.create_table(
        "agent_predictions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bot", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("expected_move_pct", sa.Float(), nullable=False),
        sa.Column("horizon_bars", sa.Integer(), nullable=False),
        sa.Column("price_at_ts", sa.Float(), nullable=False),
        sa.Column("reasoning", sa.String(length=512), nullable=False),
        sa.Column("signal_confidence", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
    )
    op.create_index("ix_agent_predictions_ts", "agent_predictions", ["ts"])
    op.create_index("ix_pred_bot_ts", "agent_predictions", ["bot", "ts"])

    op.create_table(
        "model_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("train_window_days", sa.Integer(), nullable=False),
        sa.Column("oos_accuracy", sa.Float(), nullable=False),
        sa.Column("oos_precision_long", sa.Float(), nullable=False),
        sa.Column("is_champion", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.String(length=256), nullable=False),
        sa.Column("weights_blob", sa.Text(), nullable=True),
    )

    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bot", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("strategy", sa.String(length=64), nullable=False),
        sa.Column("params_json", sa.String(length=1024), nullable=False),
        sa.Column("trades_n", sa.Integer(), nullable=False),
        sa.Column("win_rate", sa.Float(), nullable=False),
        sa.Column("profit_factor", sa.Float(), nullable=False),
        sa.Column("sharpe", sa.Float(), nullable=False),
        sa.Column("max_dd_pct", sa.Float(), nullable=False),
        sa.Column("total_return_pct", sa.Float(), nullable=False),
        sa.Column(
            "model_id", sa.Integer(), sa.ForeignKey("model_versions.id"), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_table("backtest_runs")
    op.drop_table("model_versions")
    op.drop_index("ix_pred_bot_ts", table_name="agent_predictions")
    op.drop_index("ix_agent_predictions_ts", table_name="agent_predictions")
    op.drop_table("agent_predictions")
    op.drop_index("ix_memory_tier_bot", table_name="agent_memory")
    op.drop_index("ix_agent_memory_created_at", table_name="agent_memory")
    op.drop_table("agent_memory")
    op.drop_index("ix_agent_insights_created_at", table_name="agent_insights")
    op.drop_index("ix_agent_insights_agent", table_name="agent_insights")
    op.drop_table("agent_insights")
    op.drop_table("bot_status")
    op.drop_index("ix_equity_points_ts", table_name="equity_points")
    op.drop_table("equity_points")
    op.drop_table("open_positions")
    op.drop_table("trades")
    op.drop_index("ix_candles_sym_tf_time", table_name="candles")
    op.drop_index("ix_candles_open_time", table_name="candles")
    op.drop_table("candles")
