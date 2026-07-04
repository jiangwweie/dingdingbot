"""Create ticket-bound protected submit attempts.

Revision ID: 088
Revises: 087
Create Date: 2026-07-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "088"
down_revision: Union[str, None] = "087"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "brc_ticket_bound_protected_submit_attempts"


def _json_type() -> sa.types.TypeEngine:
    if str(op.get_bind().dialect.name) == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def _has_table() -> bool:
    return sa.inspect(op.get_bind()).has_table(TABLE_NAME)


def upgrade() -> None:
    if _has_table():
        return
    json_t = _json_type()
    op.create_table(
        TABLE_NAME,
        sa.Column("protected_submit_attempt_id", sa.String(192), primary_key=True),
        sa.Column("ticket_id", sa.String(192), nullable=False),
        sa.Column("finalgate_pass_id", sa.String(256), nullable=False),
        sa.Column("operation_layer_handoff_id", sa.String(192), nullable=False),
        sa.Column("operation_submit_command_id", sa.String(192), nullable=False),
        sa.Column("runtime_safety_snapshot_id", sa.String(192), nullable=False),
        sa.Column("action_time_lane_input_id", sa.String(192), nullable=False),
        sa.Column("strategy_group_id", sa.String(128), nullable=False),
        sa.Column("symbol", sa.String(128), nullable=False),
        sa.Column("side", sa.String(32), nullable=False),
        sa.Column("runtime_profile_id", sa.String(128), nullable=False),
        sa.Column("submit_mode", sa.String(64), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("submit_allowed", sa.Boolean(), nullable=False),
        sa.Column("blockers", json_t, nullable=False, server_default="[]"),
        sa.Column("warnings", json_t, nullable=False, server_default="[]"),
        sa.Column("trusted_fact_refs", json_t, nullable=False, server_default="{}"),
        sa.Column("submit_request", json_t, nullable=False, server_default="{}"),
        sa.Column("submit_result", json_t, nullable=False, server_default="{}"),
        sa.Column("identity_evidence", json_t, nullable=False, server_default="{}"),
        sa.Column("official_operation_layer_submit_called", sa.Boolean(), nullable=False),
        sa.Column("exchange_write_called", sa.Boolean(), nullable=False),
        sa.Column("order_created", sa.Boolean(), nullable=False),
        sa.Column("order_lifecycle_called", sa.Boolean(), nullable=False),
        sa.Column("withdrawal_or_transfer_created", sa.Boolean(), nullable=False),
        sa.Column("live_profile_changed", sa.Boolean(), nullable=False),
        sa.Column("order_sizing_changed", sa.Boolean(), nullable=False),
        sa.Column("authority_boundary", sa.Text(), nullable=False),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
        sa.CheckConstraint("side IN ('long', 'short')", name="ck_brc_ticket_submit_side"),
        sa.CheckConstraint(
            "submit_mode IN ('disabled_smoke', 'real_gateway_action')",
            name="ck_brc_ticket_submit_mode",
        ),
        sa.CheckConstraint(
            "status IN ('blocked', 'submit_prepared', 'disabled_smoke_passed', "
            "'submitted', 'submit_failed', 'hard_stopped')",
            name="ck_brc_ticket_submit_status",
        ),
        sa.CheckConstraint(
            "withdrawal_or_transfer_created = false "
            "AND live_profile_changed = false "
            "AND order_sizing_changed = false",
            name="ck_brc_ticket_submit_no_forbidden_effects",
        ),
        sa.CheckConstraint(
            "submit_mode <> 'disabled_smoke' OR "
            "(exchange_write_called = false "
            "AND order_created = false "
            "AND order_lifecycle_called = false "
            "AND status IN ('blocked', 'disabled_smoke_passed'))",
            name="ck_brc_ticket_submit_disabled_no_effects",
        ),
        sa.CheckConstraint(
            "status <> 'submitted' OR "
            "(submit_mode = 'real_gateway_action' "
            "AND submit_allowed = true "
            "AND official_operation_layer_submit_called = true "
            "AND exchange_write_called = true "
            "AND order_lifecycle_called = true)",
            name="ck_brc_ticket_submit_submitted_effects",
        ),
        sa.UniqueConstraint(
            "operation_submit_command_id",
            name="uq_brc_ticket_submit_command",
        ),
    )
    op.create_index(
        "idx_brc_ticket_submit_ticket_status",
        TABLE_NAME,
        ["ticket_id", "status", "created_at_ms"],
    )
    op.create_index(
        "idx_brc_ticket_submit_safety",
        TABLE_NAME,
        ["runtime_safety_snapshot_id", "status"],
    )


def downgrade() -> None:
    if _has_table():
        op.drop_table(TABLE_NAME)
