"""Create durable ticket-bound exchange commands.

Revision ID: 105
Revises: 104
Create Date: 2026-07-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "105"
down_revision: Union[str, None] = "104"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "brc_ticket_bound_exchange_commands"
COMMAND_STATES = (
    "prepared",
    "dispatching",
    "confirmed_submitted",
    "confirmed_rejected",
    "outcome_unknown",
    "reconciled_submitted",
    "reconciled_absent",
    "hard_stopped",
)
OUTCOME_CLASSES = (
    "pending",
    "exchange_accepted",
    "authoritative_rejection",
    "network_ambiguous",
    "incomplete_response",
    "reconciled_exchange_truth",
    "reconciled_absence",
    "contradictory_truth",
)


def upgrade() -> None:
    if _has_table(TABLE_NAME):
        return

    states = ", ".join(repr(value) for value in COMMAND_STATES)
    outcomes = ", ".join(repr(value) for value in OUTCOME_CLASSES)
    op.create_table(
        TABLE_NAME,
        sa.Column("exchange_command_id", sa.String(192), primary_key=True),
        sa.Column("protected_submit_attempt_id", sa.String(192), nullable=False),
        sa.Column("ticket_id", sa.String(192), nullable=False),
        sa.Column("operation_submit_command_id", sa.String(192), nullable=False),
        sa.Column("account_id", sa.String(128), nullable=False),
        sa.Column("strategy_group_id", sa.String(128), nullable=False),
        sa.Column("runtime_profile_id", sa.String(128), nullable=False),
        sa.Column("exchange_instrument_id", sa.String(192), nullable=False),
        sa.Column("order_role", sa.String(32), nullable=False),
        sa.Column("side", sa.String(32), nullable=False),
        sa.Column("gateway_side", sa.String(32), nullable=False),
        sa.Column("local_order_id", sa.String(192), nullable=False),
        sa.Column("parent_order_id", sa.String(192), nullable=True),
        sa.Column("client_order_id", sa.String(36), nullable=False),
        sa.Column("command_generation", sa.Integer(), nullable=False),
        sa.Column("request_fingerprint", sa.String(192), nullable=False),
        sa.Column("order_type", sa.String(64), nullable=False),
        sa.Column("amount", sa.Numeric(36, 18), nullable=False),
        sa.Column("price", sa.Numeric(36, 18), nullable=True),
        sa.Column("stop_price", sa.Numeric(36, 18), nullable=True),
        sa.Column("reduce_only", sa.Boolean(), nullable=False),
        sa.Column("authority_source_ref", sa.String(256), nullable=False),
        sa.Column("command_state", sa.String(64), nullable=False),
        sa.Column("outcome_class", sa.String(64), nullable=False),
        sa.Column("exchange_order_id", sa.String(192), nullable=True),
        sa.Column("exchange_error_code", sa.String(128), nullable=True),
        sa.Column("exchange_error_message", sa.String(1000), nullable=True),
        sa.Column("prepared_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("dispatch_started_at_ms", sa.BIGINT(), nullable=True),
        sa.Column("resolved_at_ms", sa.BIGINT(), nullable=True),
        sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
        sa.CheckConstraint(
            "order_role IN ('ENTRY', 'SL', 'TP1', 'RUNNER_SL')",
            name="ck_brc_exchange_command_role",
        ),
        sa.CheckConstraint(
            "side IN ('long', 'short')",
            name="ck_brc_exchange_command_side",
        ),
        sa.CheckConstraint(
            f"command_state IN ({states})",
            name="ck_brc_exchange_command_state",
        ),
        sa.CheckConstraint(
            f"outcome_class IN ({outcomes})",
            name="ck_brc_exchange_command_outcome",
        ),
        sa.CheckConstraint(
            "command_generation > 0 AND amount > 0",
            name="ck_brc_exchange_command_amounts",
        ),
        sa.CheckConstraint(
            "command_state NOT IN ('confirmed_submitted', "
            "'reconciled_submitted') OR exchange_order_id IS NOT NULL",
            name="ck_brc_exchange_command_submit_ref",
        ),
        sa.CheckConstraint(
            "command_state <> 'confirmed_rejected' OR "
            "outcome_class = 'authoritative_rejection'",
            name="ck_brc_exchange_command_rejection",
        ),
        sa.UniqueConstraint(
            "client_order_id",
            name="uq_brc_exchange_command_client_id",
        ),
        sa.UniqueConstraint(
            "local_order_id",
            name="uq_brc_exchange_command_local_order",
        ),
        sa.UniqueConstraint(
            "ticket_id",
            "order_role",
            "command_generation",
            name="uq_brc_exchange_command_ticket_role_generation",
        ),
    )
    op.create_index(
        "idx_brc_exchange_command_attempt_state",
        TABLE_NAME,
        ["protected_submit_attempt_id", "command_state"],
    )
    op.create_index(
        "idx_brc_exchange_command_scope_state",
        TABLE_NAME,
        [
            "account_id",
            "strategy_group_id",
            "exchange_instrument_id",
            "side",
            "command_state",
        ],
    )


def downgrade() -> None:
    if _has_table(TABLE_NAME):
        op.drop_table(TABLE_NAME)


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()
