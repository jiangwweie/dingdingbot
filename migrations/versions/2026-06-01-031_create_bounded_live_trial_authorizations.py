"""Create PG bounded live trial authorization metadata table

Revision ID: 031
Revises: 030
Create Date: 2026-06-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "031"
down_revision: Union[str, None] = "030"
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
    if not _has_table("brc_bounded_live_trial_authorizations"):
        op.create_table(
            "brc_bounded_live_trial_authorizations",
            sa.Column("authorization_id", sa.String(length=128), nullable=False),
            sa.Column("draft_id", sa.String(length=128), nullable=False),
            sa.Column("carrier_id", sa.String(length=128), nullable=False),
            sa.Column("strategy_family_id", sa.String(length=128), nullable=False),
            sa.Column("symbol", sa.String(length=128), nullable=False),
            sa.Column("side", sa.String(length=32), nullable=False),
            sa.Column("max_notional", sa.Numeric(36, 18), nullable=False),
            sa.Column("quantity", sa.Numeric(36, 18), nullable=False),
            sa.Column("leverage", sa.Numeric(18, 8), nullable=False),
            sa.Column("protection_plan_type", sa.String(length=64), nullable=False),
            sa.Column("single_use", sa.Boolean(), nullable=False),
            sa.Column("status", sa.String(length=96), nullable=False),
            sa.Column("live_authorized", sa.Boolean(), nullable=False),
            sa.Column("owner_live_authorized_by", sa.String(length=128), nullable=False),
            sa.Column("owner_live_authorized_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("live_ready", sa.Boolean(), nullable=False),
            sa.Column("order_permission_granted", sa.Boolean(), nullable=False),
            sa.Column("execution_permission_granted", sa.Boolean(), nullable=False),
            sa.Column("execution_intent_created", sa.Boolean(), nullable=False),
            sa.Column("order_created", sa.Boolean(), nullable=False),
            sa.Column("auto_execution_enabled", sa.Boolean(), nullable=False),
            sa.Column("consumed", sa.Boolean(), nullable=False),
            sa.Column("expires_at_ms", sa.BIGINT(), nullable=True),
            sa.Column("linked_acknowledgement_id", sa.String(length=128), nullable=False),
            sa.Column("source_draft_id", sa.String(length=128), nullable=False),
            sa.Column("final_preflight_required", sa.Boolean(), nullable=False),
            sa.Column("hard_blockers", _jsonb_type(), nullable=False),
            sa.Column("next_executable", sa.Boolean(), nullable=False),
            sa.Column("source", sa.String(length=64), nullable=False),
            sa.Column("metadata_only", sa.Boolean(), nullable=False),
            sa.Column("metadata", _jsonb_type(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint("side IN ('long', 'short')", name="ck_brc_trial_auths_side"),
            sa.CheckConstraint(
                "protection_plan_type IN ('single_tp_plus_sl')",
                name="ck_brc_trial_auths_protection_plan",
            ),
            sa.CheckConstraint(
                "status IN ('owner_live_authorized_pending_final_preflight')",
                name="ck_brc_trial_auths_status",
            ),
            sa.CheckConstraint("max_notional > 0", name="ck_brc_trial_auths_max_notional_positive"),
            sa.CheckConstraint("quantity > 0", name="ck_brc_trial_auths_quantity_positive"),
            sa.CheckConstraint("leverage > 0", name="ck_brc_trial_auths_leverage_positive"),
            sa.CheckConstraint("single_use IS TRUE", name="ck_brc_trial_auths_single_use"),
            sa.CheckConstraint("live_authorized IS TRUE", name="ck_brc_trial_auths_live_authorized"),
            sa.CheckConstraint("live_ready IS FALSE", name="ck_brc_trial_auths_live_not_ready"),
            sa.CheckConstraint(
                "order_permission_granted IS FALSE",
                name="ck_brc_trial_auths_no_order_permission",
            ),
            sa.CheckConstraint(
                "execution_permission_granted IS FALSE",
                name="ck_brc_trial_auths_no_execution_permission",
            ),
            sa.CheckConstraint(
                "execution_intent_created IS FALSE",
                name="ck_brc_trial_auths_no_execution_intent",
            ),
            sa.CheckConstraint("order_created IS FALSE", name="ck_brc_trial_auths_no_order"),
            sa.CheckConstraint(
                "auto_execution_enabled IS FALSE",
                name="ck_brc_trial_auths_no_auto_execution",
            ),
            sa.CheckConstraint("consumed IS FALSE", name="ck_brc_trial_auths_not_consumed"),
            sa.CheckConstraint(
                "final_preflight_required IS TRUE",
                name="ck_brc_trial_auths_final_preflight_required",
            ),
            sa.CheckConstraint("next_executable IS FALSE", name="ck_brc_trial_auths_not_next_executable"),
            sa.CheckConstraint("source = 'owner_console'", name="ck_brc_trial_auths_source"),
            sa.CheckConstraint("metadata_only IS TRUE", name="ck_brc_trial_auths_metadata_only"),
            sa.ForeignKeyConstraint(
                ["draft_id"],
                ["brc_bounded_live_trial_authorization_drafts.draft_id"],
                deferrable=True,
                initially="DEFERRED",
            ),
            sa.ForeignKeyConstraint(
                ["linked_acknowledgement_id"],
                ["brc_owner_risk_acknowledgements.acknowledgement_id"],
                deferrable=True,
                initially="DEFERRED",
            ),
            sa.PrimaryKeyConstraint("authorization_id"),
            sa.UniqueConstraint("draft_id", name="uq_brc_trial_auths_draft_id"),
        )
    _create_index_if_missing(
        "idx_brc_trial_auths_carrier_time",
        "brc_bounded_live_trial_authorizations",
        ["carrier_id", "owner_live_authorized_at_ms"],
    )
    _create_index_if_missing(
        "idx_brc_trial_auths_draft",
        "brc_bounded_live_trial_authorizations",
        ["draft_id"],
    )
    _create_index_if_missing(
        "idx_brc_trial_auths_ack",
        "brc_bounded_live_trial_authorizations",
        ["linked_acknowledgement_id"],
    )
    _create_index_if_missing(
        "idx_brc_trial_auths_status_time",
        "brc_bounded_live_trial_authorizations",
        ["status", "updated_at_ms"],
    )


def downgrade() -> None:
    for index_name in [
        "idx_brc_trial_auths_status_time",
        "idx_brc_trial_auths_ack",
        "idx_brc_trial_auths_draft",
        "idx_brc_trial_auths_carrier_time",
    ]:
        _drop_index_if_exists(index_name, "brc_bounded_live_trial_authorizations")
    if _has_table("brc_bounded_live_trial_authorizations"):
        op.drop_table("brc_bounded_live_trial_authorizations")
