"""创建 daily risk stats aggregate 和 event ledger 表

Revision ID: 007
Revises: 006
Create Date: 2026-05-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 LS-002b daily risk stats 持久化表。"""

    op.create_table(
        "daily_risk_stats_aggregates",
        sa.Column("scope_key", sa.String(128), nullable=False),
        sa.Column("stats_date", sa.Date(), nullable=False),
        sa.Column(
            "realized_pnl",
            sa.Numeric(38, 18),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "trade_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("last_event_key", sa.String(256), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("scope_key", "stats_date"),
        sa.CheckConstraint(
            "trade_count >= 0",
            name="ck_daily_risk_stats_trade_count_non_negative",
        ),
    )
    op.create_index(
        "idx_daily_risk_stats_aggregates_scope_updated",
        "daily_risk_stats_aggregates",
        ["scope_key", "updated_at"],
        unique=False,
    )

    op.create_table(
        "daily_risk_stats_events",
        sa.Column("event_key", sa.String(256), nullable=False),
        sa.Column("scope_key", sa.String(128), nullable=False),
        sa.Column("stats_date", sa.Date(), nullable=False),
        sa.Column(
            "source",
            sa.String(64),
            nullable=False,
            server_default="exit_projection",
        ),
        sa.Column("position_id", sa.String(64), nullable=False),
        sa.Column("signal_id", sa.String(64), nullable=False),
        sa.Column("exit_order_id", sa.String(64), nullable=False),
        sa.Column(
            "delta_exit_qty",
            sa.Numeric(38, 18),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "delta_realized_pnl",
            sa.Numeric(38, 18),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "trade_count_delta",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("event_key"),
        sa.CheckConstraint(
            "source = 'exit_projection'",
            name="ck_daily_risk_stats_source",
        ),
        sa.CheckConstraint(
            "trade_count_delta IN (0, 1)",
            name="ck_daily_risk_stats_trade_count_delta",
        ),
        sa.CheckConstraint(
            "delta_exit_qty >= 0",
            name="ck_daily_risk_stats_delta_exit_qty_non_negative",
        ),
    )
    op.create_index(
        "idx_daily_risk_stats_events_scope_date_created",
        "daily_risk_stats_events",
        ["scope_key", "stats_date", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_daily_risk_stats_events_position_exit",
        "daily_risk_stats_events",
        ["position_id", "exit_order_id"],
        unique=False,
    )


def downgrade() -> None:
    """删除 LS-002b daily risk stats 持久化表。"""

    op.drop_index(
        "idx_daily_risk_stats_events_position_exit",
        table_name="daily_risk_stats_events",
    )
    op.drop_index(
        "idx_daily_risk_stats_events_scope_date_created",
        table_name="daily_risk_stats_events",
    )
    op.drop_table("daily_risk_stats_events")

    op.drop_index(
        "idx_daily_risk_stats_aggregates_scope_updated",
        table_name="daily_risk_stats_aggregates",
    )
    op.drop_table("daily_risk_stats_aggregates")
