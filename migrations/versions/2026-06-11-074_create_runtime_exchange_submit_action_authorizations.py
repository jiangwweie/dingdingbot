"""Create runtime exchange submit action authorization table

Revision ID: 074
Revises: 073
Create Date: 2026-06-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "074"
down_revision: Union[str, None] = "073"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "runtime_execution_exchange_submit_action_authorizations"
ADAPTER_RESULT_TABLE = "runtime_execution_exchange_submit_adapter_results"


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(
        column["name"] == column_name
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    )


def _json_type() -> sa.types.TypeEngine:
    if str(op.get_bind().dialect.name) == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    if (
        _has_table(ADAPTER_RESULT_TABLE)
        and not _has_column(
            ADAPTER_RESULT_TABLE,
            "exchange_submit_action_authorization_id",
        )
    ):
        op.add_column(
            ADAPTER_RESULT_TABLE,
            sa.Column(
                "exchange_submit_action_authorization_id",
                sa.String(360),
                nullable=True,
            ),
        )
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
        sa.Column("side", sa.String(32), nullable=True),
        sa.Column(
            "local_registration_enablement_decision_id",
            sa.String(300),
            nullable=False,
        ),
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
            "order_lifecycle_submit_enablement_id",
            sa.String(220),
            nullable=False,
        ),
        sa.Column(
            "exchange_submit_adapter_enablement_id",
            sa.String(220),
            nullable=False,
        ),
        sa.Column("deployment_readiness_evidence_id", sa.String(220), nullable=True),
        sa.Column("packet_preview_id", sa.String(460), nullable=False),
        sa.Column("binding_id", sa.String(460), nullable=False),
        sa.Column(
            "local_registration_adapter_result_id",
            sa.String(420),
            nullable=False,
        ),
        sa.Column("entry_order_id", sa.String(260), nullable=True),
        sa.Column("local_order_ids", _json_type(), nullable=False, server_default="[]"),
        sa.Column(
            "protection_order_ids",
            _json_type(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("submit_request_count", sa.Integer(), nullable=False),
        sa.Column("entry_submit_request_count", sa.Integer(), nullable=False),
        sa.Column("protection_submit_request_count", sa.Integer(), nullable=False),
        sa.Column(
            "owner_confirmed_for_exchange_submit_action",
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
            "order_lifecycle_submit_called",
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
            name="uq_rt_exchange_action_auth_authorization",
        ),
        sa.CheckConstraint(
            "status IN ('blocked', 'approved_for_exchange_submit_action')",
            name="ck_rt_exchange_action_auth_status",
        ),
        sa.CheckConstraint(
            "submit_request_count >= 0",
            name="ck_rt_exchange_action_auth_request_count",
        ),
        sa.CheckConstraint(
            "entry_submit_request_count >= 0",
            name="ck_rt_exchange_action_auth_entry_count",
        ),
        sa.CheckConstraint(
            "protection_submit_request_count >= 0",
            name="ck_rt_exchange_action_auth_protection_count",
        ),
        sa.CheckConstraint(
            "status != 'approved_for_exchange_submit_action' "
            "OR owner_confirmed_for_exchange_submit_action = true",
            name="ck_rt_exchange_action_auth_owner_confirmed",
        ),
        sa.CheckConstraint(
            "order_lifecycle_submit_called = false",
            name="ck_rt_exchange_action_auth_no_lifecycle_submit",
        ),
        sa.CheckConstraint(
            "execution_intent_status_changed = false",
            name="ck_rt_exchange_action_auth_no_intent_status",
        ),
        sa.CheckConstraint(
            "exchange_order_submitted = false",
            name="ck_rt_exchange_action_auth_no_exchange_submit",
        ),
        sa.CheckConstraint(
            "exchange_called = false",
            name="ck_rt_exchange_action_auth_no_exchange",
        ),
        sa.CheckConstraint(
            "owner_bounded_execution_called = false",
            name="ck_rt_exchange_action_auth_no_owner_bounded",
        ),
        sa.CheckConstraint(
            "withdrawal_or_transfer_created = false",
            name="ck_rt_exchange_action_auth_no_withdrawal",
        ),
    )
    op.create_index(
        "idx_rt_exchange_action_auth_auth_time",
        TABLE,
        ["authorization_id", "created_at_ms"],
    )
    op.create_index(
        "idx_rt_exchange_action_auth_intent_time",
        TABLE,
        ["execution_intent_id", "created_at_ms"],
    )
    op.create_index(
        "idx_rt_exchange_action_auth_status_time",
        TABLE,
        ["status", "created_at_ms"],
    )


def downgrade() -> None:
    if _has_table(TABLE):
        op.drop_index("idx_rt_exchange_action_auth_status_time", table_name=TABLE)
        op.drop_index("idx_rt_exchange_action_auth_intent_time", table_name=TABLE)
        op.drop_index("idx_rt_exchange_action_auth_auth_time", table_name=TABLE)
        op.drop_table(TABLE)
    if _has_column(
        ADAPTER_RESULT_TABLE,
        "exchange_submit_action_authorization_id",
    ):
        op.drop_column(
            ADAPTER_RESULT_TABLE,
            "exchange_submit_action_authorization_id",
        )
