"""Create runtime retention run audit table.

Revision ID: 090
Revises: 089
Create Date: 2026-07-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "090"
down_revision: Union[str, None] = "089"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "brc_runtime_retention_runs"


def _json_type() -> sa.types.TypeEngine:
    if str(op.get_bind().dialect.name) == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def _has_table() -> bool:
    return sa.inspect(op.get_bind()).has_table(TABLE_NAME)


def upgrade() -> None:
    if _has_table():
        return
    json_t = _json_type()
    op.create_table(
        TABLE_NAME,
        sa.Column("retention_run_id", sa.String(192), primary_key=True),
        sa.Column("started_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("finished_at_ms", sa.BIGINT(), nullable=True),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("apply_mode", sa.Boolean(), nullable=False),
        sa.Column("eligible_total", sa.Integer(), nullable=False),
        sa.Column("deleted_total", sa.Integer(), nullable=False),
        sa.Column("details", json_t, nullable=False, server_default="{}"),
        sa.Column("authority_boundary", sa.Text(), nullable=False),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.CheckConstraint(
            "status IN ('retention_dry_run', 'retention_applied', 'blocked', 'failed')",
            name="ck_brc_runtime_retention_status",
        ),
        sa.CheckConstraint(
            "deleted_total >= 0 AND eligible_total >= 0",
            name="ck_brc_runtime_retention_counts",
        ),
    )
    op.create_index(
        "idx_brc_runtime_retention_status_time",
        TABLE_NAME,
        ["status", "started_at_ms"],
    )


def downgrade() -> None:
    if _has_table():
        op.drop_table(TABLE_NAME)
