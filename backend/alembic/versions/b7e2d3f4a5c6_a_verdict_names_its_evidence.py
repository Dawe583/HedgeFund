"""A verdict names its evidence.

The validation gate (design §7) is worthless as a printout: a strategy that
"passed" without the numbers it passed on is a promise nobody can check.
Every research verdict therefore lands in `backtest_validations` with the
seed that makes it reproducible, the data range and source it ran on, the
three statistical checks (permutation p, bootstrap Sharpe CI, walk-forward
folds) and the thresholds they were held to — so the difference between
VALIDATED and REJECTED is arithmetic anyone can recompute, never taste.

Revision ID: b7e2d3f4a5c6
Revises: a3f1c2d4e5b6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b7e2d3f4a5c6"
down_revision = "a3f1c2d4e5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Same adoption tolerance as the parent revision a3f1c2d4e5b6: the buggy
    # read-path create_all created every trading table at once, including this
    # one, and the schema is identical either way — adopt, never strand.
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "backtest_validations" in existing:
        return
    op.create_table(
        "backtest_validations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bot", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("strategy", sa.String(length=64), nullable=False),
        sa.Column("params_json", sa.String(length=2048), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("data_source", sa.String(length=32), nullable=False),
        sa.Column("data_rows", sa.Integer(), nullable=False),
        sa.Column("data_start", sa.String(length=40), nullable=False),
        sa.Column("data_end", sa.String(length=40), nullable=False),
        sa.Column("trades_n", sa.Integer(), nullable=False),
        sa.Column("min_trades_required", sa.Integer(), nullable=False),
        sa.Column("permutation_p", sa.Float(), nullable=True),
        sa.Column("sharpe_actual", sa.Float(), nullable=True),
        sa.Column("sharpe_ci_lo", sa.Float(), nullable=True),
        sa.Column("sharpe_ci_hi", sa.Float(), nullable=True),
        sa.Column("prob_positive", sa.Float(), nullable=True),
        sa.Column("wf_positive_folds", sa.Integer(), nullable=False),
        sa.Column("wf_total_folds", sa.Integer(), nullable=False),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column("reasons_json", sa.String(length=2048), nullable=False),
        sa.Column("validation_json", sa.Text(), nullable=False),
        sa.Column(
            "run_id", sa.Integer(), sa.ForeignKey("backtest_runs.id"), nullable=True
        ),
    )


def downgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "backtest_validations" in existing:
        op.drop_table("backtest_validations")
