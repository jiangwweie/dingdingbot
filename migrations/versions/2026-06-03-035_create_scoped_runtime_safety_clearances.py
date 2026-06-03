"""Create scoped runtime safety clearances

Revision ID: 035
Revises: 034
Create Date: 2026-06-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "035"
down_revision: Union[str, None] = "034"
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
    if not _has_table("brc_scoped_runtime_safety_clearances"):
        op.create_table(
            "brc_scoped_runtime_safety_clearances",
            sa.Column("clearance_id", sa.String(length=128), nullable=False),
            sa.Column("clearance_type", sa.String(length=32), nullable=False),
            sa.Column("authorization_id", sa.String(length=128), nullable=False),
            sa.Column("carrier_id", sa.String(length=128), nullable=False),
            sa.Column("symbol", sa.String(length=128), nullable=False),
            sa.Column("side", sa.String(length=32), nullable=False),
            sa.Column("max_notional", sa.Numeric(36, 18), nullable=False),
            sa.Column("quantity", sa.Numeric(36, 18), nullable=False),
            sa.Column("leverage", sa.Numeric(18, 8), nullable=False),
            sa.Column("protection_plan_type", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("expires_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("actor", sa.String(length=128), nullable=False),
            sa.Column("source", sa.String(length=64), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "clearance_type IN ('gks', 'startup_guard')",
                name="ck_brc_scoped_runtime_safety_clearances_type",
            ),
            sa.CheckConstraint(
                "side IN ('long', 'short')",
                name="ck_brc_scoped_runtime_safety_clearances_side",
            ),
            sa.CheckConstraint(
                "protection_plan_type IN ('single_tp_plus_sl')",
                name="ck_brc_scoped_runtime_safety_clearances_protection",
            ),
            sa.CheckConstraint(
                "status IN ('active', 'revoked', 'expired')",
                name="ck_brc_scoped_runtime_safety_clearances_status",
            ),
            sa.ForeignKeyConstraint(
                ["authorization_id"],
                ["brc_bounded_live_trial_authorizations.authorization_id"],
                deferrable=True,
                initially="DEFERRED",
            ),
            sa.PrimaryKeyConstraint("clearance_id"),
        )
    if not _has_index(
        "brc_scoped_runtime_safety_clearances",
        "idx_brc_scoped_runtime_safety_clearances_auth_type",
    ):
        op.create_index(
            "idx_brc_scoped_runtime_safety_clearances_auth_type",
            "brc_scoped_runtime_safety_clearances",
            ["authorization_id", "clearance_type", "status"],
        )
    if not _has_index(
        "brc_scoped_runtime_safety_clearances",
        "idx_brc_scoped_runtime_safety_clearances_scope",
    ):
        op.create_index(
            "idx_brc_scoped_runtime_safety_clearances_scope",
            "brc_scoped_runtime_safety_clearances",
            ["carrier_id", "symbol", "side", "clearance_type", "status", "expires_at_ms"],
        )


def downgrade() -> None:
    if _has_index(
        "brc_scoped_runtime_safety_clearances",
        "idx_brc_scoped_runtime_safety_clearances_scope",
    ):
        op.drop_index(
            "idx_brc_scoped_runtime_safety_clearances_scope",
            table_name="brc_scoped_runtime_safety_clearances",
        )
    if _has_index(
        "brc_scoped_runtime_safety_clearances",
        "idx_brc_scoped_runtime_safety_clearances_auth_type",
    ):
        op.drop_index(
            "idx_brc_scoped_runtime_safety_clearances_auth_type",
            table_name="brc_scoped_runtime_safety_clearances",
        )
    if _has_table("brc_scoped_runtime_safety_clearances"):
        op.drop_table("brc_scoped_runtime_safety_clearances")
