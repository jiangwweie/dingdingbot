"""Create ticket-bound live outcome ledger.

Revision ID: 102
Revises: 101
Create Date: 2026-07-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "102"
down_revision: Union[str, None] = "101"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "brc_live_outcome_ledger"


def upgrade() -> None:
    if _has_table(TABLE_NAME):
        return
    json_t = _json_type()
    op.create_table(
        TABLE_NAME,
        sa.Column("live_outcome_id", sa.String(192), primary_key=True),
        sa.Column("ticket_id", sa.String(192), nullable=False),
        sa.Column("protected_submit_attempt_id", sa.String(192), nullable=False),
        sa.Column("lifecycle_run_id", sa.String(192), nullable=True),
        sa.Column("exit_protection_set_id", sa.String(192), nullable=True),
        sa.Column("strategy_group_id", sa.String(128), nullable=False),
        sa.Column("symbol", sa.String(128), nullable=False),
        sa.Column("side", sa.String(32), nullable=False),
        sa.Column("runtime_profile_id", sa.String(128), nullable=False),
        sa.Column("policy_version_id", sa.String(128), nullable=True),
        sa.Column("strategy_version_id", sa.String(160), nullable=True),
        sa.Column("signal_event_id", sa.String(192), nullable=True),
        sa.Column("signal_time_ms", sa.BIGINT(), nullable=True),
        sa.Column("ticket_created_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("entry_time_ms", sa.BIGINT(), nullable=True),
        sa.Column("entry_price", sa.Numeric(36, 18), nullable=True),
        sa.Column("entry_qty", sa.Numeric(36, 18), nullable=True),
        sa.Column("stop_price", sa.Numeric(36, 18), nullable=True),
        sa.Column("tp1_price", sa.Numeric(36, 18), nullable=True),
        sa.Column("tp1_qty", sa.Numeric(36, 18), nullable=True),
        sa.Column("risk_at_stop", sa.Numeric(36, 18), nullable=True),
        sa.Column("initial_notional", sa.Numeric(36, 18), nullable=True),
        sa.Column("leverage", sa.Numeric(18, 8), nullable=True),
        sa.Column("sl_exchange_order_id", sa.String(192), nullable=True),
        sa.Column("tp1_exchange_order_id", sa.String(192), nullable=True),
        sa.Column("tp1_fill_time_ms", sa.BIGINT(), nullable=True),
        sa.Column("tp1_fill_price", sa.Numeric(36, 18), nullable=True),
        sa.Column("runner_qty", sa.Numeric(36, 18), nullable=True),
        sa.Column("runner_sl_price", sa.Numeric(36, 18), nullable=True),
        sa.Column("runner_sl_exchange_order_id", sa.String(192), nullable=True),
        sa.Column("final_exit_time_ms", sa.BIGINT(), nullable=True),
        sa.Column("final_exit_price", sa.Numeric(36, 18), nullable=True),
        sa.Column("flat_reconciled_at_ms", sa.BIGINT(), nullable=True),
        sa.Column("fees", sa.Numeric(36, 18), nullable=True),
        sa.Column("funding", sa.Numeric(36, 18), nullable=True),
        sa.Column("realized_pnl", sa.Numeric(36, 18), nullable=True),
        sa.Column("unrealized_pnl", sa.Numeric(36, 18), nullable=True),
        sa.Column("mae", sa.Numeric(36, 18), nullable=True),
        sa.Column("mfe", sa.Numeric(36, 18), nullable=True),
        sa.Column("r_multiple", sa.Numeric(36, 18), nullable=True),
        sa.Column("stage_reached", sa.String(96), nullable=False),
        sa.Column("outcome_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("first_blocker", sa.String(160), nullable=True),
        sa.Column("lifecycle_defects", json_t, nullable=False, server_default="[]"),
        sa.Column("review_decision", sa.String(64), nullable=True),
        sa.Column("review_reason_code", sa.String(128), nullable=True),
        sa.Column("reviewed_at_ms", sa.BIGINT(), nullable=True),
        sa.Column("review_source", sa.String(64), nullable=True),
        sa.Column("source_refs", json_t, nullable=False, server_default="{}"),
        sa.Column("authority_boundary", sa.Text(), nullable=False),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
        sa.CheckConstraint("side IN ('long', 'short')", name="ck_brc_live_outcome_side"),
        sa.CheckConstraint(
            "outcome_type IN ('lifecycle_closed', 'hard_blocked_outcome', "
            "'recovered_outcome')",
            name="ck_brc_live_outcome_type",
        ),
        sa.CheckConstraint(
            "status IN ('recorded', 'reviewed')",
            name="ck_brc_live_outcome_status",
        ),
        sa.CheckConstraint(
            "review_decision IS NULL OR review_decision IN ("
            "'continue_same', 'promote_observe', 'revise', 'park', 'kill', "
            "'needs_more_samples')",
            name="ck_brc_live_outcome_review_decision",
        ),
        sa.UniqueConstraint("ticket_id", name="uq_brc_live_outcome_ticket"),
    )
    op.create_index(
        "idx_brc_live_outcome_scope_time",
        TABLE_NAME,
        ["strategy_group_id", "symbol", "side", "created_at_ms"],
    )
    op.create_index(
        "idx_brc_live_outcome_type_time",
        TABLE_NAME,
        ["outcome_type", "created_at_ms"],
    )


def downgrade() -> None:
    if _has_table(TABLE_NAME):
        op.drop_table(TABLE_NAME)


def _json_type() -> sa.types.TypeEngine:
    if str(op.get_bind().dialect.name) == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)
