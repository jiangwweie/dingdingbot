"""Create signal evaluation and order candidate shadow tables

Revision ID: 047
Revises: 046
Create Date: 2026-06-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "047"
down_revision: Union[str, None] = "046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SIGNAL_EVALUATION_TABLE = "signal_evaluations"
ORDER_CANDIDATE_TABLE = "order_candidates"


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _json_type() -> sa.types.TypeEngine:
    if str(op.get_bind().dialect.name) == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    if not _has_table(SIGNAL_EVALUATION_TABLE):
        op.create_table(
            SIGNAL_EVALUATION_TABLE,
            sa.Column("signal_evaluation_id", sa.String(length=128), primary_key=True),
            sa.Column("runtime_instance_id", sa.String(length=128), nullable=True),
            sa.Column("trial_binding_id", sa.String(length=128), nullable=True),
            sa.Column("strategy_family_id", sa.String(length=128), nullable=True),
            sa.Column("strategy_family_version_id", sa.String(length=128), nullable=True),
            sa.Column("source_signal_id", sa.String(length=128), nullable=True),
            sa.Column("symbol", sa.String(length=128), nullable=False),
            sa.Column("side", sa.String(length=16), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("decision", sa.String(length=32), nullable=False),
            sa.Column("reason_codes", _json_type(), nullable=False, server_default="[]"),
            sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
            sa.Column("evidence_snapshot", _json_type(), nullable=False, server_default="{}"),
            sa.Column("policy_snapshot", _json_type(), nullable=False, server_default="{}"),
            sa.Column("evaluated_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("expires_at_ms", sa.BIGINT(), nullable=True),
            sa.Column("shadow_mode", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("execution_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("not_order", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("not_execution_intent", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("metadata", _json_type(), nullable=False, server_default="{}"),
            sa.CheckConstraint(
                "status IN ('evaluated', 'invalidated', 'expired', 'parked')",
                name="ck_signal_evaluations_status",
            ),
            sa.CheckConstraint(
                "decision IN ('candidate', 'no_action', 'invalid', 'park')",
                name="ck_signal_evaluations_decision",
            ),
            sa.CheckConstraint(
                "side IN ('long', 'short', 'none')",
                name="ck_signal_evaluations_side",
            ),
            sa.CheckConstraint(
                "execution_enabled = false",
                name="ck_signal_evaluations_execution_disabled",
            ),
            sa.CheckConstraint(
                "shadow_mode = true",
                name="ck_signal_evaluations_shadow_mode",
            ),
            sa.CheckConstraint(
                "not_order = true",
                name="ck_signal_evaluations_not_order",
            ),
            sa.CheckConstraint(
                "not_execution_intent = true",
                name="ck_signal_evaluations_not_execution_intent",
            ),
        )
        op.create_index(
            "idx_signal_evaluations_runtime_time",
            SIGNAL_EVALUATION_TABLE,
            ["runtime_instance_id", "evaluated_at_ms"],
        )
        op.create_index(
            "idx_signal_evaluations_trial_binding",
            SIGNAL_EVALUATION_TABLE,
            ["trial_binding_id"],
        )
        op.create_index(
            "idx_signal_evaluations_family_version",
            SIGNAL_EVALUATION_TABLE,
            ["strategy_family_version_id"],
        )
        op.create_index(
            "idx_signal_evaluations_symbol_status",
            SIGNAL_EVALUATION_TABLE,
            ["symbol", "status"],
        )
        op.create_index(
            "idx_signal_evaluations_status_time",
            SIGNAL_EVALUATION_TABLE,
            ["status", "updated_at_ms"],
        )

    if not _has_table(ORDER_CANDIDATE_TABLE):
        op.create_table(
            ORDER_CANDIDATE_TABLE,
            sa.Column("order_candidate_id", sa.String(length=128), primary_key=True),
            sa.Column("signal_evaluation_id", sa.String(length=128), nullable=False),
            sa.Column("runtime_instance_id", sa.String(length=128), nullable=True),
            sa.Column("trial_binding_id", sa.String(length=128), nullable=True),
            sa.Column("strategy_family_id", sa.String(length=128), nullable=True),
            sa.Column("strategy_family_version_id", sa.String(length=128), nullable=True),
            sa.Column("symbol", sa.String(length=128), nullable=False),
            sa.Column("side", sa.String(length=16), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("candidate_order_type", sa.String(length=64), nullable=False),
            sa.Column("proposed_quantity", sa.Numeric(36, 18), nullable=True),
            sa.Column("intended_notional", sa.Numeric(36, 18), nullable=True),
            sa.Column("entry_price_reference", sa.Numeric(36, 18), nullable=True),
            sa.Column("risk_preview", _json_type(), nullable=False, server_default="{}"),
            sa.Column("protection_preview", _json_type(), nullable=False, server_default="{}"),
            sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
            sa.Column("evidence_refs", _json_type(), nullable=False, server_default="[]"),
            sa.Column("shadow_mode", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("execution_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("candidate_executable", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("not_order", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("not_execution_intent", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("expires_at_ms", sa.BIGINT(), nullable=True),
            sa.Column("metadata", _json_type(), nullable=False, server_default="{}"),
            sa.CheckConstraint(
                "status IN ('proposed', 'under_review', 'expired', 'parked')",
                name="ck_order_candidates_status",
            ),
            sa.CheckConstraint(
                "side IN ('long', 'short')",
                name="ck_order_candidates_side",
            ),
            sa.CheckConstraint(
                "proposed_quantity IS NULL OR proposed_quantity >= 0",
                name="ck_order_candidates_proposed_quantity_nonnegative",
            ),
            sa.CheckConstraint(
                "intended_notional IS NULL OR intended_notional >= 0",
                name="ck_order_candidates_intended_notional_nonnegative",
            ),
            sa.CheckConstraint(
                "execution_enabled = false",
                name="ck_order_candidates_execution_disabled",
            ),
            sa.CheckConstraint(
                "shadow_mode = true",
                name="ck_order_candidates_shadow_mode",
            ),
            sa.CheckConstraint(
                "candidate_executable = false",
                name="ck_order_candidates_not_executable",
            ),
            sa.CheckConstraint(
                "not_order = true",
                name="ck_order_candidates_not_order",
            ),
            sa.CheckConstraint(
                "not_execution_intent = true",
                name="ck_order_candidates_not_execution_intent",
            ),
        )
        op.create_index(
            "idx_order_candidates_signal_evaluation",
            ORDER_CANDIDATE_TABLE,
            ["signal_evaluation_id"],
        )
        op.create_index(
            "idx_order_candidates_runtime_time",
            ORDER_CANDIDATE_TABLE,
            ["runtime_instance_id", "updated_at_ms"],
        )
        op.create_index(
            "idx_order_candidates_trial_binding",
            ORDER_CANDIDATE_TABLE,
            ["trial_binding_id"],
        )
        op.create_index(
            "idx_order_candidates_family_version",
            ORDER_CANDIDATE_TABLE,
            ["strategy_family_version_id"],
        )
        op.create_index(
            "idx_order_candidates_symbol_status",
            ORDER_CANDIDATE_TABLE,
            ["symbol", "status"],
        )
        op.create_index(
            "idx_order_candidates_status_time",
            ORDER_CANDIDATE_TABLE,
            ["status", "updated_at_ms"],
        )


def downgrade() -> None:
    if _has_table(ORDER_CANDIDATE_TABLE):
        op.drop_index("idx_order_candidates_status_time", table_name=ORDER_CANDIDATE_TABLE)
        op.drop_index("idx_order_candidates_symbol_status", table_name=ORDER_CANDIDATE_TABLE)
        op.drop_index("idx_order_candidates_family_version", table_name=ORDER_CANDIDATE_TABLE)
        op.drop_index("idx_order_candidates_trial_binding", table_name=ORDER_CANDIDATE_TABLE)
        op.drop_index("idx_order_candidates_runtime_time", table_name=ORDER_CANDIDATE_TABLE)
        op.drop_index("idx_order_candidates_signal_evaluation", table_name=ORDER_CANDIDATE_TABLE)
        op.drop_table(ORDER_CANDIDATE_TABLE)
    if _has_table(SIGNAL_EVALUATION_TABLE):
        op.drop_index("idx_signal_evaluations_status_time", table_name=SIGNAL_EVALUATION_TABLE)
        op.drop_index("idx_signal_evaluations_symbol_status", table_name=SIGNAL_EVALUATION_TABLE)
        op.drop_index("idx_signal_evaluations_family_version", table_name=SIGNAL_EVALUATION_TABLE)
        op.drop_index("idx_signal_evaluations_trial_binding", table_name=SIGNAL_EVALUATION_TABLE)
        op.drop_index("idx_signal_evaluations_runtime_time", table_name=SIGNAL_EVALUATION_TABLE)
        op.drop_table(SIGNAL_EVALUATION_TABLE)
