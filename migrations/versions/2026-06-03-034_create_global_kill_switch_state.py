"""Create global kill switch state table

Revision ID: 034
Revises: 033
Create Date: 2026-06-03
"""

from __future__ import annotations

import time
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "034"
down_revision: Union[str, None] = "033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(
        index["name"] == index_name
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    )


def upgrade() -> None:
    if not _has_table("global_kill_switch_state"):
        op.create_table(
            "global_kill_switch_state",
            sa.Column("state_key", sa.String(length=64), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("updated_by", sa.String(length=128), nullable=False, server_default="system"),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "state_key = 'global'",
                name="ck_global_kill_switch_state_key",
            ),
            sa.PrimaryKeyConstraint("state_key"),
        )
    if not _has_index("global_kill_switch_state", "idx_global_kill_switch_updated_at"):
        op.create_index(
            "idx_global_kill_switch_updated_at",
            "global_kill_switch_state",
            ["updated_at_ms"],
        )
    _seed_fail_closed_row()


def downgrade() -> None:
    if _has_index("global_kill_switch_state", "idx_global_kill_switch_updated_at"):
        op.drop_index(
            "idx_global_kill_switch_updated_at",
            table_name="global_kill_switch_state",
        )
    if _has_table("global_kill_switch_state"):
        op.drop_table("global_kill_switch_state")


def _seed_fail_closed_row() -> None:
    bind = op.get_bind()
    now_ms = int(time.time() * 1000)
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                INSERT INTO global_kill_switch_state
                    (state_key, active, reason, updated_by, updated_at_ms)
                VALUES
                    ('global', TRUE, 'GKS_STATE_INITIALIZED_FAIL_CLOSED', 'migration_034', :now_ms)
                ON CONFLICT (state_key) DO NOTHING
                """
            ).bindparams(now_ms=now_ms)
        )
        return
    op.execute(
        sa.text(
            """
            INSERT OR IGNORE INTO global_kill_switch_state
                (state_key, active, reason, updated_by, updated_at_ms)
            VALUES
                ('global', 1, 'GKS_STATE_INITIALIZED_FAIL_CLOSED', 'migration_034', :now_ms)
            """
        ).bindparams(now_ms=now_ms)
    )
