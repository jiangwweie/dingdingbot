"""Create runtime execution intent draft audit table

Revision ID: 048
Revises: 047
Create Date: 2026-06-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "048"
down_revision: Union[str, None] = "047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "runtime_execution_intent_drafts"


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
        sa.Column("draft_id", sa.String(length=180), primary_key=True),
        sa.Column("plan_id", sa.String(length=160), nullable=False),
        sa.Column("runtime_instance_id", sa.String(length=128), nullable=False),
        sa.Column("order_candidate_id", sa.String(length=128), nullable=False),
        sa.Column("signal_evaluation_id", sa.String(length=128), nullable=False),
        sa.Column("trial_binding_id", sa.String(length=128), nullable=True),
        sa.Column("strategy_family_id", sa.String(length=128), nullable=True),
        sa.Column("strategy_family_version_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("side", sa.String(length=32), nullable=False),
        sa.Column("candidate_order_type", sa.String(length=64), nullable=False),
        sa.Column("proposed_quantity", sa.Numeric(36, 18), nullable=True),
        sa.Column("intended_notional", sa.Numeric(36, 18), nullable=True),
        sa.Column("owner_reviewed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "owner_confirmed_for_intent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("source_plan_status", sa.String(length=64), nullable=False),
        sa.Column("final_gate_verdict", sa.String(length=16), nullable=False),
        sa.Column("blockers", _json_type(), nullable=False, server_default="[]"),
        sa.Column("warnings", _json_type(), nullable=False, server_default="[]"),
        sa.Column(
            "owner_confirmation_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("preview_only", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("not_order", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "not_execution_intent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "execution_intent_repository_write_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "execution_intent_created",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("order_created", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("exchange_called", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("metadata", _json_type(), nullable=False, server_default="{}"),
        sa.CheckConstraint(
            "status IN ('blocked', 'owner_confirmation_required', "
            "'ready_for_intent_creation')",
            name="ck_runtime_execution_intent_drafts_status",
        ),
        sa.CheckConstraint(
            "source_plan_status IN ('blocked', 'owner_review_required', "
            "'ready_for_intent_draft')",
            name="ck_runtime_execution_intent_drafts_plan_status",
        ),
        sa.CheckConstraint(
            "final_gate_verdict IN ('PASS', 'BLOCK', 'WARN')",
            name="ck_runtime_execution_intent_drafts_final_gate_verdict",
        ),
        sa.CheckConstraint(
            "owner_confirmation_required = true",
            name="ck_runtime_execution_intent_drafts_owner_confirmation_required",
        ),
        sa.CheckConstraint("dry_run = true", name="ck_runtime_execution_intent_drafts_dry_run"),
        sa.CheckConstraint(
            "preview_only = true",
            name="ck_runtime_execution_intent_drafts_preview_only",
        ),
        sa.CheckConstraint(
            "not_order = true",
            name="ck_runtime_execution_intent_drafts_not_order",
        ),
        sa.CheckConstraint(
            "not_execution_intent = true",
            name="ck_runtime_execution_intent_drafts_not_execution_intent",
        ),
        sa.CheckConstraint(
            "execution_intent_repository_write_enabled = false",
            name="ck_runtime_execution_intent_drafts_no_intent_repo_write",
        ),
        sa.CheckConstraint(
            "execution_intent_created = false",
            name="ck_runtime_execution_intent_drafts_no_intent_created",
        ),
        sa.CheckConstraint(
            "order_created = false",
            name="ck_runtime_execution_intent_drafts_no_order_created",
        ),
        sa.CheckConstraint(
            "exchange_called = false",
            name="ck_runtime_execution_intent_drafts_no_exchange_called",
        ),
    )
    op.create_index(
        "idx_runtime_execution_intent_drafts_candidate_time",
        TABLE,
        ["order_candidate_id", "created_at_ms"],
    )
    op.create_index(
        "idx_runtime_execution_intent_drafts_runtime_time",
        TABLE,
        ["runtime_instance_id", "created_at_ms"],
    )
    op.create_index(
        "idx_runtime_execution_intent_drafts_status_time",
        TABLE,
        ["status", "created_at_ms"],
    )


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    op.drop_index("idx_runtime_execution_intent_drafts_status_time", table_name=TABLE)
    op.drop_index("idx_runtime_execution_intent_drafts_runtime_time", table_name=TABLE)
    op.drop_index("idx_runtime_execution_intent_drafts_candidate_time", table_name=TABLE)
    op.drop_table(TABLE)
