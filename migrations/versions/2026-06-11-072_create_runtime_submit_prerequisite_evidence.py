"""Create runtime submit prerequisite evidence tables

Revision ID: 072
Revises: 071
Create Date: 2026-06-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "072"
down_revision: Union[str, None] = "071"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TRUSTED_FACTS_TABLE = "runtime_execution_trusted_submit_fact_snapshots"
IDEMPOTENCY_TABLE = "runtime_execution_submit_idempotency_snapshots"
PROTECTION_POLICY_TABLE = "runtime_execution_protection_failure_policies"


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _json_type() -> sa.types.TypeEngine:
    if str(op.get_bind().dialect.name) == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    _create_trusted_facts_table()
    _create_idempotency_table()
    _create_protection_policy_table()


def downgrade() -> None:
    if _has_table(PROTECTION_POLICY_TABLE):
        op.drop_index(
            "idx_rt_protection_failure_policy_status_time",
            table_name=PROTECTION_POLICY_TABLE,
        )
        op.drop_index(
            "idx_rt_protection_failure_policy_intent_time",
            table_name=PROTECTION_POLICY_TABLE,
        )
        op.drop_table(PROTECTION_POLICY_TABLE)
    if _has_table(IDEMPOTENCY_TABLE):
        op.drop_index(
            "idx_rt_submit_idempotency_status_time",
            table_name=IDEMPOTENCY_TABLE,
        )
        op.drop_index(
            "idx_rt_submit_idempotency_intent_time",
            table_name=IDEMPOTENCY_TABLE,
        )
        op.drop_table(IDEMPOTENCY_TABLE)
    if _has_table(TRUSTED_FACTS_TABLE):
        op.drop_index(
            "idx_rt_trusted_submit_facts_status_time",
            table_name=TRUSTED_FACTS_TABLE,
        )
        op.drop_index(
            "idx_rt_trusted_submit_facts_intent_time",
            table_name=TRUSTED_FACTS_TABLE,
        )
        op.drop_table(TRUSTED_FACTS_TABLE)


def _create_trusted_facts_table() -> None:
    if _has_table(TRUSTED_FACTS_TABLE):
        return
    op.create_table(
        TRUSTED_FACTS_TABLE,
        sa.Column("trusted_submit_fact_snapshot_id", sa.String(240), primary_key=True),
        sa.Column("execution_intent_id", sa.String(64), nullable=False),
        sa.Column("runtime_instance_id", sa.String(128), nullable=True),
        sa.Column("order_candidate_id", sa.String(128), nullable=True),
        sa.Column("status", sa.String(96), nullable=False),
        sa.Column("symbol", sa.String(128), nullable=False),
        sa.Column("side", sa.String(32), nullable=True),
        sa.Column("facts_fresh_enough", sa.Boolean(), nullable=False),
        sa.Column(
            "missing_or_stale_facts_block",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "owner_supplied_allow_facts_rejected",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "read_only_sources_only",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        *(_common_no_execution_columns()),
        sa.Column("blockers", _json_type(), nullable=False, server_default="[]"),
        sa.Column("warnings", _json_type(), nullable=False, server_default="[]"),
        sa.Column("payload", _json_type(), nullable=False, server_default="{}"),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.CheckConstraint(
            "status IN ('blocked', 'ready_for_first_real_submit_confirmation')",
            name="ck_rt_trusted_submit_facts_status",
        ),
        *(_common_no_execution_constraints("ck_rt_trusted_submit_facts")),
    )
    op.create_index(
        "idx_rt_trusted_submit_facts_intent_time",
        TRUSTED_FACTS_TABLE,
        ["execution_intent_id", "created_at_ms"],
    )
    op.create_index(
        "idx_rt_trusted_submit_facts_status_time",
        TRUSTED_FACTS_TABLE,
        ["status", "created_at_ms"],
    )


def _create_idempotency_table() -> None:
    if _has_table(IDEMPOTENCY_TABLE):
        return
    op.create_table(
        IDEMPOTENCY_TABLE,
        sa.Column("submit_idempotency_policy_id", sa.String(240), primary_key=True),
        sa.Column("authorization_id", sa.String(220), nullable=False),
        sa.Column("execution_intent_id", sa.String(64), nullable=False),
        sa.Column("runtime_execution_intent_draft_id", sa.String(180), nullable=True),
        sa.Column("runtime_instance_id", sa.String(128), nullable=True),
        sa.Column("source_type", sa.String(64), nullable=True),
        sa.Column("source_id", sa.String(128), nullable=True),
        sa.Column("status", sa.String(96), nullable=False),
        sa.Column("symbol", sa.String(128), nullable=False),
        sa.Column("side", sa.String(32), nullable=True),
        sa.Column("stable_submit_key", sa.String(260), nullable=False),
        sa.Column("replay_lock_key", sa.String(260), nullable=False),
        sa.Column(
            "adapter_result_store_implemented",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "real_adapter_boundary_implemented",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        *(_common_no_execution_columns()),
        sa.Column("blockers", _json_type(), nullable=False, server_default="[]"),
        sa.Column("warnings", _json_type(), nullable=False, server_default="[]"),
        sa.Column("payload", _json_type(), nullable=False, server_default="{}"),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.UniqueConstraint(
            "authorization_id",
            name="uq_rt_submit_idempotency_authorization",
        ),
        sa.CheckConstraint(
            "status IN ('blocked', 'ready_for_non_executing_policy_confirmation')",
            name="ck_rt_submit_idempotency_status",
        ),
        *(_common_no_execution_constraints("ck_rt_submit_idempotency")),
    )
    op.create_index(
        "idx_rt_submit_idempotency_intent_time",
        IDEMPOTENCY_TABLE,
        ["execution_intent_id", "created_at_ms"],
    )
    op.create_index(
        "idx_rt_submit_idempotency_status_time",
        IDEMPOTENCY_TABLE,
        ["status", "created_at_ms"],
    )


def _create_protection_policy_table() -> None:
    if _has_table(PROTECTION_POLICY_TABLE):
        return
    op.create_table(
        PROTECTION_POLICY_TABLE,
        sa.Column("policy_id", sa.String(300), primary_key=True),
        sa.Column("protection_plan_id", sa.String(260), nullable=False),
        sa.Column("execution_intent_id", sa.String(64), nullable=False),
        sa.Column("runtime_instance_id", sa.String(128), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=True),
        sa.Column("source_id", sa.String(128), nullable=True),
        sa.Column("status", sa.String(96), nullable=False),
        sa.Column("symbol", sa.String(128), nullable=False),
        sa.Column("side", sa.String(32), nullable=True),
        sa.Column(
            "block_new_entries_until_resolved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "mark_position_unprotected_until_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "require_owner_recovery_review",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "require_reduce_only_recovery_mode",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "require_reconciliation_before_retry",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "consume_attempt_on_any_fill",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "hold_or_reconcile_budget_until_position_resolved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "must_not_mark_unprotected_position_as_protected",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("order_created", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "order_lifecycle_called",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("exchange_called", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "exchange_order_submitted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "owner_bounded_execution_called",
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
            "runtime_state_mutated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "withdrawal_instruction_created",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "transfer_instruction_created",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("blockers", _json_type(), nullable=False, server_default="[]"),
        sa.Column("warnings", _json_type(), nullable=False, server_default="[]"),
        sa.Column("payload", _json_type(), nullable=False, server_default="{}"),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.CheckConstraint(
            "status IN ('blocked', 'ready_for_first_real_submit_confirmation')",
            name="ck_rt_protection_failure_policy_status",
        ),
        sa.CheckConstraint(
            "order_created = false",
            name="ck_rt_protection_failure_policy_no_order",
        ),
        sa.CheckConstraint(
            "order_lifecycle_called = false",
            name="ck_rt_protection_failure_policy_no_lifecycle",
        ),
        sa.CheckConstraint(
            "exchange_called = false",
            name="ck_rt_protection_failure_policy_no_exchange",
        ),
        sa.CheckConstraint(
            "exchange_order_submitted = false",
            name="ck_rt_protection_failure_policy_no_exchange_order",
        ),
        sa.CheckConstraint(
            "owner_bounded_execution_called = false",
            name="ck_rt_protection_failure_policy_no_owner_bounded",
        ),
        sa.CheckConstraint(
            "execution_intent_status_changed = false",
            name="ck_rt_protection_failure_policy_no_intent_status",
        ),
        sa.CheckConstraint(
            "runtime_state_mutated = false",
            name="ck_rt_protection_failure_policy_no_runtime_mutation",
        ),
        sa.CheckConstraint(
            "withdrawal_instruction_created = false",
            name="ck_rt_protection_failure_policy_no_withdrawal",
        ),
        sa.CheckConstraint(
            "transfer_instruction_created = false",
            name="ck_rt_protection_failure_policy_no_transfer",
        ),
    )
    op.create_index(
        "idx_rt_protection_failure_policy_intent_time",
        PROTECTION_POLICY_TABLE,
        ["execution_intent_id", "created_at_ms"],
    )
    op.create_index(
        "idx_rt_protection_failure_policy_status_time",
        PROTECTION_POLICY_TABLE,
        ["status", "created_at_ms"],
    )


def _common_no_execution_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column(
            "execution_intent_status_changed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "runtime_state_mutated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("order_created", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("exchange_called", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "owner_bounded_execution_called",
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
            "withdrawal_instruction_created",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "transfer_instruction_created",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def _common_no_execution_constraints(prefix: str) -> tuple[sa.CheckConstraint, ...]:
    return (
        sa.CheckConstraint(
            "execution_intent_status_changed = false",
            name=f"{prefix}_no_intent_status",
        ),
        sa.CheckConstraint(
            "runtime_state_mutated = false",
            name=f"{prefix}_no_runtime_mutation",
        ),
        sa.CheckConstraint("order_created = false", name=f"{prefix}_no_order"),
        sa.CheckConstraint("exchange_called = false", name=f"{prefix}_no_exchange"),
        sa.CheckConstraint(
            "owner_bounded_execution_called = false",
            name=f"{prefix}_no_owner_bounded",
        ),
        sa.CheckConstraint(
            "order_lifecycle_called = false",
            name=f"{prefix}_no_lifecycle",
        ),
        sa.CheckConstraint(
            "withdrawal_instruction_created = false",
            name=f"{prefix}_no_withdrawal",
        ),
        sa.CheckConstraint(
            "transfer_instruction_created = false",
            name=f"{prefix}_no_transfer",
        ),
    )
