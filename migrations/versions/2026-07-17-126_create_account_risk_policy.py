"""Create account-scoped risk policy authority and static risk clusters.

Revision ID: 126
Revises: 125
Create Date: 2026-07-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "126"
down_revision: Union[str, None] = "125"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not _has_table("brc_account_risk_policy_events"):
        op.create_table(
            "brc_account_risk_policy_events",
            sa.Column("account_risk_policy_event_id", sa.String(192), primary_key=True),
            sa.Column("account_id", sa.String(192), nullable=False),
            sa.Column("runtime_profile_id", sa.String(128), nullable=False),
            sa.Column("event_type", sa.String(96), nullable=False),
            sa.Column("risk_policy_version", sa.String(96), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("created_by", sa.String(128), nullable=False),
            sa.UniqueConstraint(
                "account_id",
                "runtime_profile_id",
                "risk_policy_version",
                "event_type",
                name="uq_brc_account_risk_policy_event_identity",
            ),
        )
        op.create_index(
            "idx_brc_account_risk_policy_event_scope_time",
            "brc_account_risk_policy_events",
            ["account_id", "runtime_profile_id", "created_at_ms"],
        )

    if not _has_table("brc_account_risk_policy_current"):
        op.create_table(
            "brc_account_risk_policy_current",
            sa.Column("account_risk_policy_current_id", sa.String(192), primary_key=True),
            sa.Column("account_id", sa.String(192), nullable=False),
            sa.Column("runtime_profile_id", sa.String(128), nullable=False),
            sa.Column("risk_policy_version", sa.String(96), nullable=False),
            sa.Column("planned_stop_risk_fraction", sa.Numeric(8, 6), nullable=False),
            sa.Column("max_concurrent_positions", sa.Integer(), nullable=False),
            sa.Column("max_portfolio_open_risk_fraction", sa.Numeric(8, 6), nullable=False),
            sa.Column("max_cluster_open_risk_fraction", sa.Numeric(8, 6), nullable=False),
            sa.Column("max_portfolio_initial_margin_fraction", sa.Numeric(8, 6), nullable=False),
            sa.Column("max_leverage", sa.Integer(), nullable=False),
            sa.Column("max_new_action_time_lanes", sa.Integer(), nullable=False),
            sa.Column("automatic_downsize_enabled", sa.Boolean(), nullable=False),
            sa.Column("unknown_exposure_policy", sa.String(64), nullable=False),
            sa.Column("activation_state", sa.String(32), nullable=False),
            sa.Column("source_event_id", sa.String(192), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "planned_stop_risk_fraction > 0 AND planned_stop_risk_fraction <= 1",
                name="ck_brc_account_risk_policy_current_stop_risk",
            ),
            sa.CheckConstraint(
                "max_portfolio_open_risk_fraction > 0 AND max_portfolio_open_risk_fraction <= 1",
                name="ck_brc_account_risk_policy_current_portfolio_risk",
            ),
            sa.CheckConstraint(
                "max_cluster_open_risk_fraction > 0 AND max_cluster_open_risk_fraction <= 1",
                name="ck_brc_account_risk_policy_current_cluster_risk",
            ),
            sa.CheckConstraint(
                "max_portfolio_initial_margin_fraction > 0 AND max_portfolio_initial_margin_fraction <= 1",
                name="ck_brc_account_risk_policy_current_margin",
            ),
            sa.CheckConstraint(
                "max_concurrent_positions IN (1, 2)",
                name="ck_brc_account_risk_policy_current_position_limit",
            ),
            sa.CheckConstraint(
                "max_new_action_time_lanes = 1",
                name="ck_brc_account_risk_policy_current_lane_limit",
            ),
            sa.CheckConstraint(
                "max_leverage >= 1 AND max_leverage <= 125",
                name="ck_brc_account_risk_policy_current_leverage",
            ),
            sa.CheckConstraint(
                "unknown_exposure_policy = 'global_fail_closed'",
                name="ck_brc_account_risk_policy_current_unknown_policy",
            ),
            sa.CheckConstraint(
                "activation_state IN ('shadow', 'active')",
                name="ck_brc_account_risk_policy_current_activation",
            ),
            sa.UniqueConstraint(
                "account_id",
                "runtime_profile_id",
                name="uq_brc_account_risk_policy_current_scope",
            ),
        )

    if not _has_table("brc_risk_cluster_memberships"):
        op.create_table(
            "brc_risk_cluster_memberships",
            sa.Column("risk_cluster_membership_id", sa.String(192), primary_key=True),
            sa.Column("risk_policy_version", sa.String(96), nullable=False),
            sa.Column("exchange_instrument_id", sa.String(192), nullable=False),
            sa.Column("risk_cluster_id", sa.String(128), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("created_by", sa.String(128), nullable=False),
            sa.UniqueConstraint(
                "risk_policy_version",
                "exchange_instrument_id",
                name="uq_brc_risk_cluster_membership_policy_instrument",
            ),
        )


def downgrade() -> None:
    for table_name in (
        "brc_risk_cluster_memberships",
        "brc_account_risk_policy_current",
        "brc_account_risk_policy_events",
    ):
        if _has_table(table_name):
            op.drop_table(table_name)


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()
