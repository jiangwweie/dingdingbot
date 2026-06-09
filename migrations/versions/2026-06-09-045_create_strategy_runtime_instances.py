"""Create strategy runtime shadow backbone tables

Revision ID: 045
Revises: 044
Create Date: 2026-06-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "045"
down_revision: Union[str, None] = "044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RUNTIME_TABLE = "strategy_runtime_instances"
EVENT_TABLE = "strategy_runtime_events"


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _json_type() -> sa.types.TypeEngine:
    if str(op.get_bind().dialect.name) == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    if not _has_table(RUNTIME_TABLE):
        op.create_table(
            RUNTIME_TABLE,
            sa.Column("runtime_instance_id", sa.String(length=128), primary_key=True),
            sa.Column("trial_binding_id", sa.String(length=128), nullable=False),
            sa.Column("admission_decision_id", sa.String(length=128), nullable=False),
            sa.Column("strategy_family_id", sa.String(length=128), nullable=False),
            sa.Column("strategy_family_version_id", sa.String(length=128), nullable=False),
            sa.Column("owner_risk_acceptance_id", sa.String(length=128), nullable=True),
            sa.Column("carrier_id", sa.String(length=128), nullable=True),
            sa.Column("symbol", sa.String(length=128), nullable=False),
            sa.Column("side", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("boundary", _json_type(), nullable=False, server_default="{}"),
            sa.Column("policy_snapshot", _json_type(), nullable=False, server_default="{}"),
            sa.Column("review_requirement", sa.String(length=32), nullable=False),
            sa.Column("execution_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("shadow_mode", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("activated_at_ms", sa.BIGINT(), nullable=True),
            sa.Column("expires_at_ms", sa.BIGINT(), nullable=True),
            sa.Column("revoked_at_ms", sa.BIGINT(), nullable=True),
            sa.Column("closed_at_ms", sa.BIGINT(), nullable=True),
            sa.Column("metadata", _json_type(), nullable=False, server_default="{}"),
            sa.CheckConstraint(
                "status IN ('draft', 'active', 'paused', 'exhausted', 'expired', "
                "'revoked', 'closed', 'reviewed')",
                name="ck_strategy_runtime_instances_status",
            ),
            sa.CheckConstraint(
                "review_requirement IN ('required', 'optional', 'not_required')",
                name="ck_strategy_runtime_instances_review_requirement",
            ),
            sa.CheckConstraint(
                "execution_enabled = false",
                name="ck_strategy_runtime_instances_execution_disabled",
            ),
            sa.CheckConstraint(
                "shadow_mode = true",
                name="ck_strategy_runtime_instances_shadow_mode",
            ),
            sa.UniqueConstraint(
                "trial_binding_id",
                name="uq_strategy_runtime_instances_trial_binding",
            ),
        )
        op.create_index(
            "idx_strategy_runtime_instances_status_time",
            RUNTIME_TABLE,
            ["status", "updated_at_ms"],
        )
        op.create_index(
            "idx_strategy_runtime_instances_family_version",
            RUNTIME_TABLE,
            ["strategy_family_version_id", "updated_at_ms"],
        )
        op.create_index(
            "idx_strategy_runtime_instances_symbol_status",
            RUNTIME_TABLE,
            ["symbol", "status"],
        )

    if not _has_table(EVENT_TABLE):
        op.create_table(
            EVENT_TABLE,
            sa.Column("event_id", sa.String(length=128), primary_key=True),
            sa.Column("runtime_instance_id", sa.String(length=128), nullable=False),
            sa.Column("event_type", sa.String(length=128), nullable=False),
            sa.Column("previous_status", sa.String(length=32), nullable=True),
            sa.Column("next_status", sa.String(length=32), nullable=False),
            sa.Column("actor", sa.String(length=128), nullable=False, server_default="system"),
            sa.Column("reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("metadata", _json_type(), nullable=False, server_default="{}"),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "previous_status IS NULL OR previous_status IN "
                "('draft', 'active', 'paused', 'exhausted', 'expired', 'revoked', "
                "'closed', 'reviewed')",
                name="ck_strategy_runtime_events_previous_status",
            ),
            sa.CheckConstraint(
                "next_status IN ('draft', 'active', 'paused', 'exhausted', "
                "'expired', 'revoked', 'closed', 'reviewed')",
                name="ck_strategy_runtime_events_next_status",
            ),
        )
        op.create_index(
            "idx_strategy_runtime_events_runtime_time",
            EVENT_TABLE,
            ["runtime_instance_id", "created_at_ms"],
        )
        op.create_index(
            "idx_strategy_runtime_events_type_time",
            EVENT_TABLE,
            ["event_type", "created_at_ms"],
        )


def downgrade() -> None:
    if _has_table(EVENT_TABLE):
        op.drop_index("idx_strategy_runtime_events_type_time", table_name=EVENT_TABLE)
        op.drop_index("idx_strategy_runtime_events_runtime_time", table_name=EVENT_TABLE)
        op.drop_table(EVENT_TABLE)
    if _has_table(RUNTIME_TABLE):
        op.drop_index("idx_strategy_runtime_instances_symbol_status", table_name=RUNTIME_TABLE)
        op.drop_index("idx_strategy_runtime_instances_family_version", table_name=RUNTIME_TABLE)
        op.drop_index("idx_strategy_runtime_instances_status_time", table_name=RUNTIME_TABLE)
        op.drop_table(RUNTIME_TABLE)
