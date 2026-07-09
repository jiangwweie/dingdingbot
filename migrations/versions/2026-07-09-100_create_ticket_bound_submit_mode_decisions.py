"""Create ticket-bound submit mode decision projection.

Revision ID: 100
Revises: 099
Create Date: 2026-07-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "100"
down_revision: Union[str, None] = "099"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json_type() -> sa.types.TypeEngine:
    if str(op.get_bind().dialect.name) == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(
        column["name"] == column_name
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    )


def upgrade() -> None:
    json_t = _json_type()
    if not _has_table("brc_ticket_bound_submit_mode_decisions"):
        op.create_table(
            "brc_ticket_bound_submit_mode_decisions",
            sa.Column("submit_mode_decision_id", sa.String(192), primary_key=True),
            sa.Column("ticket_id", sa.String(192), nullable=False),
            sa.Column("operation_layer_handoff_id", sa.String(192), nullable=False),
            sa.Column("operation_submit_command_id", sa.String(192), nullable=False),
            sa.Column("runtime_safety_snapshot_id", sa.String(192), nullable=False),
            sa.Column("action_time_lane_input_id", sa.String(192), nullable=False),
            sa.Column("runtime_scope_binding_id", sa.String(160), nullable=False),
            sa.Column("policy_current_id", sa.String(160), nullable=False),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("symbol", sa.String(128), nullable=False),
            sa.Column("side", sa.String(32), nullable=False),
            sa.Column("runtime_profile_id", sa.String(128), nullable=False),
            sa.Column("decision", sa.String(64), nullable=False),
            sa.Column("decision_reason", sa.Text(), nullable=False),
            sa.Column("first_blocker", sa.Text(), nullable=True),
            sa.Column("blockers", json_t, nullable=False, server_default="[]"),
            sa.Column("warnings", json_t, nullable=False, server_default="[]"),
            sa.Column("evidence_refs", json_t, nullable=False, server_default="{}"),
            sa.Column("production_submit_execution_policy", sa.String(64), nullable=False),
            sa.Column("gateway_binding_ready", sa.Boolean(), nullable=False),
            sa.Column("authority_boundary", sa.Text(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("expires_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "side IN ('long', 'short')",
                name="ck_brc_submit_mode_decision_side",
            ),
            sa.CheckConstraint(
                "decision IN ('blocked', 'disabled_smoke', 'real_gateway_action')",
                name="ck_brc_submit_mode_decision_value",
            ),
            sa.CheckConstraint(
                "production_submit_execution_policy IN ('disabled', 'armed')",
                name="ck_brc_submit_mode_decision_deploy_policy",
            ),
            sa.CheckConstraint(
                "decision <> 'real_gateway_action' OR "
                "(gateway_binding_ready = true "
                "AND production_submit_execution_policy = 'armed' "
                "AND (first_blocker IS NULL OR first_blocker = ''))",
                name="ck_brc_submit_mode_decision_real_ready",
            ),
            sa.UniqueConstraint(
                "operation_submit_command_id",
                name="uq_brc_submit_mode_decision_command",
            ),
        )
        op.create_index(
            "idx_brc_submit_mode_decision_ticket",
            "brc_ticket_bound_submit_mode_decisions",
            ["ticket_id", "decision", "created_at_ms"],
        )
    if not _has_column(
        "brc_ticket_bound_protected_submit_attempts",
        "submit_mode_decision_id",
    ):
        op.add_column(
            "brc_ticket_bound_protected_submit_attempts",
            sa.Column("submit_mode_decision_id", sa.String(192), nullable=True),
        )


def downgrade() -> None:
    if _has_column(
        "brc_ticket_bound_protected_submit_attempts",
        "submit_mode_decision_id",
    ):
        op.drop_column(
            "brc_ticket_bound_protected_submit_attempts",
            "submit_mode_decision_id",
        )
    if _has_table("brc_ticket_bound_submit_mode_decisions"):
        op.drop_index(
            "idx_brc_submit_mode_decision_ticket",
            table_name="brc_ticket_bound_submit_mode_decisions",
        )
        op.drop_table("brc_ticket_bound_submit_mode_decisions")
