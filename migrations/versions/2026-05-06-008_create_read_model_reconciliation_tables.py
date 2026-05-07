"""创建 periodic reconciliation read model 持久化表

Revision ID: 008
Revises: 007
Create Date: 2026-05-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    """创建 LS-003d read-only reconciliation read model 报告表。"""

    op.create_table(
        "reconciliation_read_model_reports",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("report_id", sa.String(128), nullable=False),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("checked_at_ms", sa.BIGINT(), nullable=False),
        sa.Column(
            "is_consistent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "total_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "severe_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "warning_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "is_fetch_failure",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("fetch_failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.BIGINT(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "report_id",
            name="uq_reconciliation_read_model_reports_report_id",
        ),
    )
    op.create_index(
        "idx_reconciliation_read_model_reports_symbol_time",
        "reconciliation_read_model_reports",
        ["symbol", "checked_at_ms"],
        unique=False,
    )
    op.create_index(
        "idx_reconciliation_read_model_reports_consistent",
        "reconciliation_read_model_reports",
        ["is_consistent"],
        unique=False,
    )
    op.create_index(
        "idx_reconciliation_read_model_reports_time",
        "reconciliation_read_model_reports",
        ["checked_at_ms"],
        unique=False,
    )

    op.create_table(
        "reconciliation_read_model_mismatches",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("report_id", sa.String(128), nullable=False),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("mismatch_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("local_ref", sa.String(128), nullable=True),
        sa.Column("exchange_ref", sa.String(128), nullable=True),
        sa.Column("metadata", _jsonb_type(), nullable=True),
        sa.Column("created_at", sa.BIGINT(), nullable=False),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["reconciliation_read_model_reports.report_id"],
            name="fk_reconciliation_read_model_mismatches_report_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_reconciliation_read_model_mismatches_report",
        "reconciliation_read_model_mismatches",
        ["report_id"],
        unique=False,
    )
    op.create_index(
        "idx_reconciliation_read_model_mismatches_type",
        "reconciliation_read_model_mismatches",
        ["mismatch_type"],
        unique=False,
    )
    op.create_index(
        "idx_reconciliation_read_model_mismatches_severity",
        "reconciliation_read_model_mismatches",
        ["severity"],
        unique=False,
    )


def downgrade() -> None:
    """删除 LS-003d read-only reconciliation read model 报告表。"""

    op.drop_index(
        "idx_reconciliation_read_model_mismatches_severity",
        table_name="reconciliation_read_model_mismatches",
    )
    op.drop_index(
        "idx_reconciliation_read_model_mismatches_type",
        table_name="reconciliation_read_model_mismatches",
    )
    op.drop_index(
        "idx_reconciliation_read_model_mismatches_report",
        table_name="reconciliation_read_model_mismatches",
    )
    op.drop_table("reconciliation_read_model_mismatches")

    op.drop_index(
        "idx_reconciliation_read_model_reports_time",
        table_name="reconciliation_read_model_reports",
    )
    op.drop_index(
        "idx_reconciliation_read_model_reports_consistent",
        table_name="reconciliation_read_model_reports",
    )
    op.drop_index(
        "idx_reconciliation_read_model_reports_symbol_time",
        table_name="reconciliation_read_model_reports",
    )
    op.drop_table("reconciliation_read_model_reports")
