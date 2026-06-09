"""Create Owner capital adjustment review table

Revision ID: 059
Revises: 058
Create Date: 2026-06-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "059"
down_revision: Union[str, None] = "058"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "owner_capital_adjustments"


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
        sa.Column("adjustment_id", sa.String(length=128), primary_key=True),
        sa.Column("adjustment_type", sa.String(length=64), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False, server_default="USDT"),
        sa.Column("amount", sa.Numeric(36, 18), nullable=True),
        sa.Column("capital_base_delta", sa.Numeric(36, 18), nullable=True),
        sa.Column("target_capital_base", sa.Numeric(36, 18), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("occurred_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("recorded_by", sa.String(length=128), nullable=False, server_default="owner"),
        sa.Column("evidence_refs", _json_type(), nullable=False, server_default="[]"),
        sa.Column("metadata", _json_type(), nullable=False, server_default="{}"),
        sa.Column("records_external_owner_action", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("withdrawal_instruction_created", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("transfer_instruction_created", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("order_instruction_created", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("exchange_called", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mutates_runtime_budget", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mutates_strategy_pnl", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("creates_risk_event", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
        sa.CheckConstraint(
            "adjustment_type IN ('owner_manual_withdrawal', 'manual_profit_extraction', "
            "'owner_capital_injection', 'capital_base_reset')",
            name="ck_owner_capital_adjustments_type",
        ),
        sa.CheckConstraint(
            "amount IS NULL OR amount > 0",
            name="ck_owner_capital_adjustments_positive_amount",
        ),
        sa.CheckConstraint(
            "target_capital_base IS NULL OR target_capital_base >= 0",
            name="ck_owner_capital_adjustments_nonnegative_target",
        ),
        sa.CheckConstraint(
            "records_external_owner_action = true",
            name="ck_owner_capital_adjustments_external_owner_action",
        ),
        sa.CheckConstraint(
            "withdrawal_instruction_created = false",
            name="ck_owner_capital_adjustments_no_withdrawal_instruction",
        ),
        sa.CheckConstraint(
            "transfer_instruction_created = false",
            name="ck_owner_capital_adjustments_no_transfer_instruction",
        ),
        sa.CheckConstraint(
            "order_instruction_created = false",
            name="ck_owner_capital_adjustments_no_order_instruction",
        ),
        sa.CheckConstraint(
            "exchange_called = false",
            name="ck_owner_capital_adjustments_no_exchange_call",
        ),
        sa.CheckConstraint(
            "mutates_runtime_budget = false",
            name="ck_owner_capital_adjustments_no_runtime_budget_mutation",
        ),
        sa.CheckConstraint(
            "mutates_strategy_pnl = false",
            name="ck_owner_capital_adjustments_no_strategy_pnl_mutation",
        ),
        sa.CheckConstraint(
            "creates_risk_event = false",
            name="ck_owner_capital_adjustments_no_risk_event",
        ),
    )
    op.create_index(
        "idx_owner_capital_adjustments_currency_time",
        TABLE,
        ["currency", "occurred_at_ms"],
    )
    op.create_index(
        "idx_owner_capital_adjustments_type_time",
        TABLE,
        ["adjustment_type", "occurred_at_ms"],
    )
    op.create_index(
        "idx_owner_capital_adjustments_recorded_by_time",
        TABLE,
        ["recorded_by", "occurred_at_ms"],
    )


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    op.drop_index("idx_owner_capital_adjustments_recorded_by_time", table_name=TABLE)
    op.drop_index("idx_owner_capital_adjustments_type_time", table_name=TABLE)
    op.drop_index("idx_owner_capital_adjustments_currency_time", table_name=TABLE)
    op.drop_table(TABLE)
