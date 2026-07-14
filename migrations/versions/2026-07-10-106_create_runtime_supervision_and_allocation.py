"""Create runtime supervision, semantic admission, and allocation V0.

Revision ID: 106
Revises: 105
Create Date: 2026-07-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "106"
down_revision: Union[str, None] = "105"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not _has_table("brc_runtime_process_outcomes"):
        op.create_table(
            "brc_runtime_process_outcomes",
            sa.Column("process_outcome_id", sa.String(192), primary_key=True),
            sa.Column("process_name", sa.String(128), nullable=False),
            sa.Column("scope_key", sa.String(256), nullable=False),
            sa.Column("run_id", sa.String(192), nullable=False),
            sa.Column("process_state", sa.String(64), nullable=False),
            sa.Column("business_state", sa.String(64), nullable=False),
            sa.Column("first_blocker", sa.String(256), nullable=True),
            sa.Column("started_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("completed_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("runtime_head", sa.String(128), nullable=False),
            sa.Column("source_watermark", sa.String(256), nullable=False),
            sa.Column("projector_owner", sa.String(128), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "process_state IN ('succeeded', 'noop', 'business_blocked', "
                "'retryable_failure', 'hard_failure')",
                name="ck_brc_process_outcome_state",
            ),
            sa.UniqueConstraint(
                "process_name",
                "scope_key",
                name="uq_brc_process_outcome_scope",
            ),
        )

    if not _has_table("brc_strategy_semantic_admissions"):
        op.create_table(
            "brc_strategy_semantic_admissions",
            sa.Column("semantic_admission_id", sa.String(192), primary_key=True),
            sa.Column("candidate_scope_id", sa.String(160), nullable=False),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("strategy_group_version_id", sa.String(160), nullable=False),
            sa.Column("event_spec_id", sa.String(160), nullable=False),
            sa.Column("event_spec_version_id", sa.String(160), nullable=False),
            sa.Column("symbol", sa.String(128), nullable=False),
            sa.Column("exchange_instrument_id", sa.String(192), nullable=False),
            sa.Column("asset_class", sa.String(64), nullable=False),
            sa.Column("side", sa.String(32), nullable=False),
            sa.Column("conclusion", sa.String(64), nullable=False),
            sa.Column("first_blocker", sa.String(256), nullable=True),
            sa.Column("authority_source_ref", sa.String(256), nullable=False),
            sa.Column("evaluated_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "conclusion IN ('trial_grade_capable', 'observe_only_by_design', "
                "'semantics_incomplete', 'facts_incomplete', "
                "'strategy_quality_blocked', 'safety_blocked')",
                name="ck_brc_semantic_admission_conclusion",
            ),
            sa.UniqueConstraint(
                "candidate_scope_id",
                name="uq_brc_semantic_admission_candidate",
            ),
        )

    if not _has_table("brc_allocation_decisions"):
        op.create_table(
            "brc_allocation_decisions",
            sa.Column("allocation_decision_id", sa.String(192), primary_key=True),
            sa.Column("allocation_policy_version", sa.String(96), nullable=False),
            sa.Column("arbitration_cycle_ref", sa.String(192), nullable=False),
            sa.Column("max_new_action_time_lanes", sa.Integer(), nullable=False),
            sa.Column("eligible_candidate_count", sa.Integer(), nullable=False),
            sa.Column("selected_candidate_count", sa.Integer(), nullable=False),
            sa.Column("capital_scope_ref", sa.String(192), nullable=False),
            sa.Column("selected_promotion_candidate_id", sa.String(192), nullable=True),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "max_new_action_time_lanes > 0 AND selected_candidate_count >= 0 "
                "AND selected_candidate_count <= max_new_action_time_lanes",
                name="ck_brc_allocation_decision_limits",
            ),
            sa.UniqueConstraint(
                "arbitration_cycle_ref",
                name="uq_brc_allocation_cycle",
            ),
        )

    additions = (
        sa.Column("allocation_decision_id", sa.String(192), nullable=True),
        sa.Column("allocation_rank", sa.Integer(), nullable=True),
        sa.Column("requested_risk_at_stop", sa.Numeric(36, 18), nullable=True),
        sa.Column("allocated_risk_at_stop", sa.Numeric(36, 18), nullable=True),
        sa.Column("allocation_state", sa.String(64), nullable=True),
    )
    for column in additions:
        if not _has_column("brc_promotion_candidates", str(column.name)):
            op.add_column("brc_promotion_candidates", column)


def downgrade() -> None:
    for name in (
        "allocation_state",
        "allocated_risk_at_stop",
        "requested_risk_at_stop",
        "allocation_rank",
        "allocation_decision_id",
    ):
        if _has_column("brc_promotion_candidates", name):
            op.drop_column("brc_promotion_candidates", name)
    for table_name in (
        "brc_allocation_decisions",
        "brc_strategy_semantic_admissions",
        "brc_runtime_process_outcomes",
    ):
        if _has_table(table_name):
            op.drop_table(table_name)


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(
        column["name"] == column_name
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    )
