"""Create strategy runtime promotion confirmation records

Revision ID: 063
Revises: 062
Create Date: 2026-06-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "063"
down_revision: Union[str, None] = "062"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "strategy_runtime_promotion_confirmations"


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
        sa.Column("confirmation_id", sa.String(length=180), primary_key=True),
        sa.Column("runtime_instance_id", sa.String(length=128), nullable=True),
        sa.Column("strategy_family_id", sa.String(length=128), nullable=False),
        sa.Column("strategy_family_version_id", sa.String(length=128), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("semantic_confirmations", _json_type(), nullable=False, server_default="{}"),
        sa.Column("runtime_confirmations", _json_type(), nullable=False, server_default="{}"),
        sa.Column(
            "first_real_submit_confirmations",
            _json_type(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("promotion_gate_result_snapshot", _json_type(), nullable=True),
        sa.Column("recorded_by", sa.String(length=128), nullable=False, server_default="owner"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_refs", _json_type(), nullable=False, server_default="[]"),
        sa.Column("metadata", _json_type(), nullable=False, server_default="{}"),
        sa.Column(
            "records_promotion_gate_confirmation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "not_execution_authority",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "execution_intent_created",
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
            "runtime_mutation_created",
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
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
        sa.CheckConstraint(
            "scope IN ('controlled_runtime_execution', 'first_real_submit_gate_review')",
            name="ck_srpc_scope",
        ),
        sa.CheckConstraint(
            "records_promotion_gate_confirmation = true",
            name="ck_srpc_records_confirmation",
        ),
        sa.CheckConstraint(
            "not_execution_authority = true",
            name="ck_srpc_not_authority",
        ),
        sa.CheckConstraint(
            "execution_intent_created = false",
            name="ck_srpc_no_intent",
        ),
        sa.CheckConstraint(
            "order_created = false",
            name="ck_srpc_no_order",
        ),
        sa.CheckConstraint(
            "exchange_called = false",
            name="ck_srpc_no_exchange",
        ),
        sa.CheckConstraint(
            "owner_bounded_execution_called = false",
            name="ck_srpc_no_one_shot",
        ),
        sa.CheckConstraint(
            "order_lifecycle_called = false",
            name="ck_srpc_no_lifecycle",
        ),
        sa.CheckConstraint(
            "runtime_mutation_created = false",
            name="ck_srpc_no_runtime_mutation",
        ),
        sa.CheckConstraint(
            "withdrawal_instruction_created = false",
            name="ck_srpc_no_withdrawal",
        ),
        sa.CheckConstraint(
            "transfer_instruction_created = false",
            name="ck_srpc_no_transfer",
        ),
    )
    op.create_index(
        "idx_strategy_runtime_promotion_confirmations_runtime_time",
        TABLE,
        ["runtime_instance_id", "created_at_ms"],
    )
    op.create_index(
        "idx_strategy_runtime_promotion_confirmations_strategy_time",
        TABLE,
        ["strategy_family_id", "strategy_family_version_id", "created_at_ms"],
    )
    op.create_index(
        "idx_strategy_runtime_promotion_confirmations_scope_time",
        TABLE,
        ["scope", "created_at_ms"],
    )


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    op.drop_index("idx_strategy_runtime_promotion_confirmations_scope_time", table_name=TABLE)
    op.drop_index("idx_strategy_runtime_promotion_confirmations_strategy_time", table_name=TABLE)
    op.drop_index("idx_strategy_runtime_promotion_confirmations_runtime_time", table_name=TABLE)
    op.drop_table(TABLE)
