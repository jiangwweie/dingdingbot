"""Create PG multi-carrier budget authorization foundation

Revision ID: 032
Revises: 031
Create Date: 2026-06-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "032"
down_revision: Union[str, None] = "031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in sa.inspect(op.get_bind()).get_indexes(table_name))


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if _has_table(table_name) and not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, columns)


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    if _has_table(table_name) and _has_index(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    if not _has_table("brc_multi_carrier_budget_authorizations"):
        op.create_table(
            "brc_multi_carrier_budget_authorizations",
            sa.Column("budget_authorization_id", sa.String(length=128), nullable=False),
            sa.Column("allowed_carriers", _jsonb_type(), nullable=False),
            sa.Column("global_budget", sa.Numeric(36, 18), nullable=False),
            sa.Column("max_attempts", sa.Integer(), nullable=False),
            sa.Column("daily_loss_limit", sa.Numeric(36, 18), nullable=False),
            sa.Column("max_concurrent_positions", sa.Integer(), nullable=False),
            sa.Column("cooldown_seconds", sa.Integer(), nullable=False),
            sa.Column("valid_from_ms", sa.BIGINT(), nullable=True),
            sa.Column("valid_until_ms", sa.BIGINT(), nullable=True),
            sa.Column("status", sa.String(length=96), nullable=False),
            sa.Column("linked_acknowledgement_id", sa.String(length=128), nullable=True),
            sa.Column("linked_authorization_id", sa.String(length=128), nullable=True),
            sa.Column("live_ready", sa.Boolean(), nullable=False),
            sa.Column("auto_execution_enabled", sa.Boolean(), nullable=False),
            sa.Column("order_permission_granted", sa.Boolean(), nullable=False),
            sa.Column("execution_permission_granted", sa.Boolean(), nullable=False),
            sa.Column("execution_intent_created", sa.Boolean(), nullable=False),
            sa.Column("order_created", sa.Boolean(), nullable=False),
            sa.Column("source", sa.String(length=64), nullable=False),
            sa.Column("metadata_only", sa.Boolean(), nullable=False),
            sa.Column("metadata", _jsonb_type(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint("global_budget > 0", name="ck_brc_budget_auth_global_budget_positive"),
            sa.CheckConstraint("max_attempts > 0", name="ck_brc_budget_auth_max_attempts_positive"),
            sa.CheckConstraint("daily_loss_limit > 0", name="ck_brc_budget_auth_daily_loss_positive"),
            sa.CheckConstraint(
                "max_concurrent_positions > 0",
                name="ck_brc_budget_auth_max_concurrent_positive",
            ),
            sa.CheckConstraint("cooldown_seconds >= 0", name="ck_brc_budget_auth_cooldown_nonnegative"),
            sa.CheckConstraint(
                "valid_until_ms IS NULL OR valid_from_ms IS NULL OR valid_until_ms > valid_from_ms",
                name="ck_brc_budget_auth_validity_window",
            ),
            sa.CheckConstraint(
                "status IN ('draft_disabled_pending_owner_authorization')",
                name="ck_brc_budget_auth_status",
            ),
            sa.CheckConstraint("live_ready IS FALSE", name="ck_brc_budget_auth_live_not_ready"),
            sa.CheckConstraint(
                "auto_execution_enabled IS FALSE",
                name="ck_brc_budget_auth_no_auto_execution",
            ),
            sa.CheckConstraint(
                "order_permission_granted IS FALSE",
                name="ck_brc_budget_auth_no_order_permission",
            ),
            sa.CheckConstraint(
                "execution_permission_granted IS FALSE",
                name="ck_brc_budget_auth_no_execution_permission",
            ),
            sa.CheckConstraint(
                "execution_intent_created IS FALSE",
                name="ck_brc_budget_auth_no_execution_intent",
            ),
            sa.CheckConstraint("order_created IS FALSE", name="ck_brc_budget_auth_no_order"),
            sa.CheckConstraint("source = 'owner_console'", name="ck_brc_budget_auth_source"),
            sa.CheckConstraint("metadata_only IS TRUE", name="ck_brc_budget_auth_metadata_only"),
            sa.ForeignKeyConstraint(
                ["linked_acknowledgement_id"],
                ["brc_owner_risk_acknowledgements.acknowledgement_id"],
                deferrable=True,
                initially="DEFERRED",
            ),
            sa.ForeignKeyConstraint(
                ["linked_authorization_id"],
                ["brc_bounded_live_trial_authorizations.authorization_id"],
                deferrable=True,
                initially="DEFERRED",
            ),
            sa.PrimaryKeyConstraint("budget_authorization_id"),
        )
    _create_index_if_missing(
        "idx_brc_budget_auth_status_time",
        "brc_multi_carrier_budget_authorizations",
        ["status", "updated_at_ms"],
    )
    _create_index_if_missing(
        "idx_brc_budget_auth_ack",
        "brc_multi_carrier_budget_authorizations",
        ["linked_acknowledgement_id"],
    )
    _create_index_if_missing(
        "idx_brc_budget_auth_live_auth",
        "brc_multi_carrier_budget_authorizations",
        ["linked_authorization_id"],
    )


def downgrade() -> None:
    for index_name in [
        "idx_brc_budget_auth_live_auth",
        "idx_brc_budget_auth_ack",
        "idx_brc_budget_auth_status_time",
    ]:
        _drop_index_if_exists(index_name, "brc_multi_carrier_budget_authorizations")
    if _has_table("brc_multi_carrier_budget_authorizations"):
        op.drop_table("brc_multi_carrier_budget_authorizations")
