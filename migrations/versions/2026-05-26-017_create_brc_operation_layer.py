"""Create BRC Operation Layer ledgers

Revision ID: 017
Revises: 016
Create Date: 2026-05-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_index(table_name: str, index_name: str) -> bool:
    return any(
        index["name"] == index_name
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    )


def _create_index_if_missing(
    index_name: str,
    table_name: str,
    columns: list[str],
    *,
    unique: bool = False,
) -> None:
    if _has_table(table_name) and not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    if _has_table(table_name) and _has_index(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    if not _has_table("brc_operations"):
        op.create_table(
            "brc_operations",
            sa.Column("operation_id", sa.String(length=128), nullable=False),
            sa.Column("operation_type", sa.String(length=128), nullable=False),
            sa.Column("requested_by", sa.String(length=128), nullable=False),
            sa.Column("requested_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("source_type", sa.String(length=64), nullable=False),
            sa.Column("source_ref", sa.String(length=256), nullable=True),
            sa.Column("input_params", _jsonb_type(), nullable=False),
            sa.Column("environment", sa.String(length=64), nullable=False),
            sa.Column("risk_level", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("current_preflight_id", sa.String(length=128), nullable=True),
            sa.Column("confirmed_by", sa.String(length=128), nullable=True),
            sa.Column("confirmed_at_ms", sa.BIGINT(), nullable=True),
            sa.Column("executed_at_ms", sa.BIGINT(), nullable=True),
            sa.Column("result_status", sa.String(length=32), nullable=True),
            sa.Column("result_summary", _jsonb_type(), nullable=False),
            sa.Column("created_audit_refs", _jsonb_type(), nullable=False),
            sa.CheckConstraint(
                "status IN ('draft', 'awaiting_confirmation', 'executing', 'executed', "
                "'blocked', 'failed', 'cancelled', 'expired', 'noop')",
                name="ck_brc_operations_status",
            ),
            sa.CheckConstraint(
                "result_status IS NULL OR result_status IN "
                "('executed', 'blocked', 'failed', 'cancelled', 'expired', 'noop')",
                name="ck_brc_operations_result_status",
            ),
            sa.CheckConstraint(
                "operation_type NOT IN ('withdrawal', 'transfer')",
                name="ck_brc_operations_no_withdrawal_transfer",
            ),
            sa.PrimaryKeyConstraint("operation_id"),
        )
    _create_index_if_missing(
        "idx_brc_operations_type_time",
        "brc_operations",
        ["operation_type", "requested_at_ms"],
    )
    _create_index_if_missing(
        "idx_brc_operations_status_time",
        "brc_operations",
        ["status", "requested_at_ms"],
    )

    if not _has_table("brc_preflight_snapshots"):
        op.create_table(
            "brc_preflight_snapshots",
            sa.Column("preflight_id", sa.String(length=128), nullable=False),
            sa.Column("operation_id", sa.String(length=128), nullable=False),
            sa.Column("operation_type", sa.String(length=128), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("expires_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("current_state_snapshot", _jsonb_type(), nullable=False),
            sa.Column("target_state", _jsonb_type(), nullable=False),
            sa.Column("account_snapshot", _jsonb_type(), nullable=False),
            sa.Column("order_snapshot", _jsonb_type(), nullable=False),
            sa.Column("runtime_snapshot", _jsonb_type(), nullable=False),
            sa.Column("campaign_snapshot", _jsonb_type(), nullable=False),
            sa.Column("playbook_snapshot", _jsonb_type(), nullable=False),
            sa.Column("risk_result", _jsonb_type(), nullable=False),
            sa.Column("decision", sa.String(length=32), nullable=False),
            sa.Column("warnings", _jsonb_type(), nullable=False),
            sa.Column("blockers", _jsonb_type(), nullable=False),
            sa.Column("confirmation_requirement", _jsonb_type(), nullable=False),
            sa.Column("snapshot_hash", sa.String(length=128), nullable=False),
            sa.Column("idempotency_key", sa.String(length=128), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("before", _jsonb_type(), nullable=False),
            sa.Column("after", _jsonb_type(), nullable=False),
            sa.CheckConstraint(
                "decision IN ('allow', 'warn', 'block', 'unavailable', 'expired')",
                name="ck_brc_preflight_snapshots_decision",
            ),
            sa.PrimaryKeyConstraint("preflight_id"),
        )
    _create_index_if_missing(
        "idx_brc_preflight_operation_time",
        "brc_preflight_snapshots",
        ["operation_id", "created_at_ms"],
    )
    _create_index_if_missing("idx_brc_preflight_expires", "brc_preflight_snapshots", ["expires_at_ms"])
    _create_index_if_missing(
        "uq_brc_preflight_idempotency",
        "brc_preflight_snapshots",
        ["operation_id", "idempotency_key"],
        unique=True,
    )

    if not _has_table("brc_execution_results"):
        op.create_table(
            "brc_execution_results",
            sa.Column("operation_id", sa.String(length=128), nullable=False),
            sa.Column("preflight_id", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("rechecked", sa.Boolean(), nullable=False),
            sa.Column("recheck_result", _jsonb_type(), nullable=False),
            sa.Column("adapter_result", _jsonb_type(), nullable=False),
            sa.Column("blocked_reason", sa.Text(), nullable=True),
            sa.Column("failed_reason", sa.Text(), nullable=True),
            sa.Column("result_summary", _jsonb_type(), nullable=False),
            sa.Column("audit_refs", _jsonb_type(), nullable=False),
            sa.Column("campaign_refs", _jsonb_type(), nullable=False),
            sa.Column("review_refs", _jsonb_type(), nullable=False),
            sa.Column("final_state_snapshot", _jsonb_type(), nullable=False),
            sa.Column("occurred_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "status IN ('executed', 'blocked', 'failed', 'cancelled', 'expired', 'noop')",
                name="ck_brc_execution_results_status",
            ),
            sa.PrimaryKeyConstraint("operation_id"),
        )
    _create_index_if_missing(
        "idx_brc_execution_results_status_time",
        "brc_execution_results",
        ["status", "occurred_at_ms"],
    )


def downgrade() -> None:
    if _has_table("brc_execution_results"):
        _drop_index_if_exists(
            "idx_brc_execution_results_status_time",
            "brc_execution_results",
        )
        op.drop_table("brc_execution_results")
    if _has_table("brc_preflight_snapshots"):
        _drop_index_if_exists("uq_brc_preflight_idempotency", "brc_preflight_snapshots")
        _drop_index_if_exists("idx_brc_preflight_expires", "brc_preflight_snapshots")
        _drop_index_if_exists(
            "idx_brc_preflight_operation_time",
            "brc_preflight_snapshots",
        )
        op.drop_table("brc_preflight_snapshots")
    if _has_table("brc_operations"):
        _drop_index_if_exists("idx_brc_operations_status_time", "brc_operations")
        _drop_index_if_exists("idx_brc_operations_type_time", "brc_operations")
        op.drop_table("brc_operations")
