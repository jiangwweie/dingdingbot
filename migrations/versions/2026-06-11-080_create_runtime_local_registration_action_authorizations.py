"""Create runtime local registration action authorization table

Revision ID: 080
Revises: 079
Create Date: 2026-06-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "080"
down_revision: Union[str, None] = "079"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "runtime_execution_local_registration_action_authorizations"


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _json_type() -> sa.types.TypeEngine:
    if str(op.get_bind().dialect.name) == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    if _has_table(TABLE):
        return
    op.create_table(
        TABLE,
        sa.Column("action_authorization_id", sa.String(360), primary_key=True),
        sa.Column("authorization_id", sa.String(220), nullable=False),
        sa.Column("execution_intent_id", sa.String(64), nullable=False),
        sa.Column("runtime_instance_id", sa.String(128), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=True),
        sa.Column("source_id", sa.String(128), nullable=True),
        sa.Column("status", sa.String(96), nullable=False),
        sa.Column("symbol", sa.String(128), nullable=False),
        sa.Column("side", sa.String(32), nullable=False),
        sa.Column("trusted_submit_fact_snapshot_id", sa.String(240), nullable=False),
        sa.Column("submit_idempotency_policy_id", sa.String(240), nullable=False),
        sa.Column("attempt_outcome_policy_id", sa.String(360), nullable=False),
        sa.Column(
            "protection_creation_failure_policy_id",
            sa.String(300),
            nullable=False,
        ),
        sa.Column("owner_real_submit_authorization_id", sa.String(220), nullable=False),
        sa.Column(
            "order_lifecycle_adapter_enablement_id",
            sa.String(220),
            nullable=False,
        ),
        sa.Column(
            "local_order_registration_enablement_id",
            sa.String(220),
            nullable=False,
        ),
        sa.Column("deployment_readiness_evidence_id", sa.String(220), nullable=True),
        sa.Column("registration_preview_id", sa.String(380), nullable=False),
        sa.Column("adapter_preview_id", sa.String(360), nullable=False),
        sa.Column("handoff_draft_id", sa.String(360), nullable=False),
        sa.Column("entry_order_draft_id", sa.String(260), nullable=True),
        sa.Column(
            "local_order_draft_ids",
            _json_type(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "protection_order_draft_ids",
            _json_type(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("registration_draft_count", sa.Integer(), nullable=False),
        sa.Column(
            "owner_confirmed_for_local_registration_action",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("owner_operator_id", sa.String(128), nullable=False),
        sa.Column("owner_confirmation_reference", sa.String(240), nullable=True),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("expires_at_ms", sa.BIGINT(), nullable=True),
        sa.Column("blockers", _json_type(), nullable=False, server_default="[]"),
        sa.Column("warnings", _json_type(), nullable=False, server_default="[]"),
        sa.Column(
            "local_order_registration_executed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "order_created",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "order_lifecycle_called",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "execution_intent_status_changed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "exchange_order_submitted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("exchange_called", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "owner_bounded_execution_called",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "withdrawal_or_transfer_created",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("metadata", _json_type(), nullable=False, server_default="{}"),
        sa.Column("payload", _json_type(), nullable=False, server_default="{}"),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.UniqueConstraint(
            "authorization_id",
            name="uq_rt_local_reg_action_auth_authorization",
        ),
        sa.CheckConstraint(
            "status IN ('blocked', 'approved_for_local_registration_action')",
            name="ck_rt_local_reg_action_auth_status",
        ),
        sa.CheckConstraint(
            "registration_draft_count >= 0",
            name="ck_rt_local_reg_action_auth_draft_count",
        ),
        sa.CheckConstraint(
            "status != 'approved_for_local_registration_action' "
            "OR owner_confirmed_for_local_registration_action = true",
            name="ck_rt_local_reg_action_auth_owner_confirmed",
        ),
        sa.CheckConstraint(
            "local_order_registration_executed = false",
            name="ck_rt_local_reg_action_auth_no_registration",
        ),
        sa.CheckConstraint(
            "order_created = false",
            name="ck_rt_local_reg_action_auth_no_order_created",
        ),
        sa.CheckConstraint(
            "order_lifecycle_called = false",
            name="ck_rt_local_reg_action_auth_no_lifecycle",
        ),
        sa.CheckConstraint(
            "execution_intent_status_changed = false",
            name="ck_rt_local_reg_action_auth_no_intent_status",
        ),
        sa.CheckConstraint(
            "exchange_order_submitted = false",
            name="ck_rt_local_reg_action_auth_no_exchange_submit",
        ),
        sa.CheckConstraint(
            "exchange_called = false",
            name="ck_rt_local_reg_action_auth_no_exchange",
        ),
        sa.CheckConstraint(
            "owner_bounded_execution_called = false",
            name="ck_rt_local_reg_action_auth_no_owner_bounded",
        ),
        sa.CheckConstraint(
            "withdrawal_or_transfer_created = false",
            name="ck_rt_local_reg_action_auth_no_withdrawal",
        ),
    )
    op.create_index(
        "idx_rt_local_reg_action_auth_auth_time",
        TABLE,
        ["authorization_id", "created_at_ms"],
    )
    op.create_index(
        "idx_rt_local_reg_action_auth_intent_time",
        TABLE,
        ["execution_intent_id", "created_at_ms"],
    )
    op.create_index(
        "idx_rt_local_reg_action_auth_status_time",
        TABLE,
        ["status", "created_at_ms"],
    )


def downgrade() -> None:
    if _has_table(TABLE):
        op.drop_index("idx_rt_local_reg_action_auth_status_time", table_name=TABLE)
        op.drop_index("idx_rt_local_reg_action_auth_intent_time", table_name=TABLE)
        op.drop_index("idx_rt_local_reg_action_auth_auth_time", table_name=TABLE)
        op.drop_table(TABLE)
