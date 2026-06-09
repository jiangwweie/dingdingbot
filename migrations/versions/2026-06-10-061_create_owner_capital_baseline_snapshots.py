"""Create Owner capital baseline snapshot review table

Revision ID: 061
Revises: 060
Create Date: 2026-06-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "061"
down_revision: Union[str, None] = "060"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "owner_capital_baseline_snapshots"


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
        sa.Column("snapshot_id", sa.String(length=128), primary_key=True),
        sa.Column("currency", sa.String(length=16), nullable=False, server_default="USDT"),
        sa.Column("account_equity", sa.Numeric(36, 18), nullable=False),
        sa.Column("capital_base", sa.Numeric(36, 18), nullable=False),
        sa.Column("available_balance", sa.Numeric(36, 18), nullable=True),
        sa.Column("unrealized_pnl", sa.Numeric(36, 18), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("occurred_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("recorded_by", sa.String(length=128), nullable=False, server_default="owner"),
        sa.Column("evidence_refs", _json_type(), nullable=False, server_default="[]"),
        sa.Column("metadata", _json_type(), nullable=False, server_default="{}"),
        sa.Column("records_account_equity_fact", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("creates_withdrawal_instruction", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("creates_transfer_instruction", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("creates_order_instruction", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("calls_exchange", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mutates_runtime_budget", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mutates_strategy_pnl", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("creates_risk_event", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
        sa.CheckConstraint(
            "source IN ('owner_recorded', 'trading_console_read_model', "
            "'startup_account_fact', 'read_only_account_fact', 'manual_review')",
            name="ck_owner_capital_baseline_snapshots_source",
        ),
        sa.CheckConstraint(
            "account_equity >= 0",
            name="ck_owner_capital_baseline_snapshots_nonnegative_equity",
        ),
        sa.CheckConstraint(
            "capital_base >= 0",
            name="ck_owner_capital_baseline_snapshots_nonnegative_base",
        ),
        sa.CheckConstraint(
            "available_balance IS NULL OR available_balance >= 0",
            name="ck_owner_capital_baseline_snapshots_nonnegative_available",
        ),
        sa.CheckConstraint(
            "records_account_equity_fact = true",
            name="ck_owner_capital_baseline_snapshots_records_fact",
        ),
        sa.CheckConstraint(
            "creates_withdrawal_instruction = false",
            name="ck_owner_capital_baseline_snapshots_no_withdrawal_instruction",
        ),
        sa.CheckConstraint(
            "creates_transfer_instruction = false",
            name="ck_owner_capital_baseline_snapshots_no_transfer_instruction",
        ),
        sa.CheckConstraint(
            "creates_order_instruction = false",
            name="ck_owner_capital_baseline_snapshots_no_order_instruction",
        ),
        sa.CheckConstraint(
            "calls_exchange = false",
            name="ck_owner_capital_baseline_snapshots_no_exchange_call",
        ),
        sa.CheckConstraint(
            "mutates_runtime_budget = false",
            name="ck_owner_capital_baseline_snapshots_no_runtime_budget_mutation",
        ),
        sa.CheckConstraint(
            "mutates_strategy_pnl = false",
            name="ck_owner_capital_baseline_snapshots_no_strategy_pnl_mutation",
        ),
        sa.CheckConstraint(
            "creates_risk_event = false",
            name="ck_owner_capital_baseline_snapshots_no_risk_event",
        ),
    )
    op.create_index(
        "idx_owner_capital_baseline_snapshots_currency_time",
        TABLE,
        ["currency", "occurred_at_ms"],
    )
    op.create_index(
        "idx_owner_capital_baseline_snapshots_source_time",
        TABLE,
        ["source", "occurred_at_ms"],
    )
    op.create_index(
        "idx_owner_capital_baseline_snapshots_recorded_by_time",
        TABLE,
        ["recorded_by", "occurred_at_ms"],
    )


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    op.drop_index("idx_owner_capital_baseline_snapshots_recorded_by_time", table_name=TABLE)
    op.drop_index("idx_owner_capital_baseline_snapshots_source_time", table_name=TABLE)
    op.drop_index("idx_owner_capital_baseline_snapshots_currency_time", table_name=TABLE)
    op.drop_table(TABLE)
