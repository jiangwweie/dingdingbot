"""Create live lifecycle review ledger

Revision ID: 044
Revises: 043
Create Date: 2026-06-08
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "044"
down_revision: Union[str, None] = "043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "brc_live_lifecycle_reviews"


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _json_type() -> sa.types.TypeEngine:
    if str(op.get_bind().dialect.name) == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    if _has_table(TABLE_NAME):
        return
    op.create_table(
        TABLE_NAME,
        sa.Column("review_id", sa.String(length=128), primary_key=True),
        sa.Column("authorization_id", sa.String(length=128), nullable=False),
        sa.Column("carrier_id", sa.String(length=128), nullable=False),
        sa.Column("strategy_family_id", sa.String(length=128), nullable=True),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.String(length=64), nullable=False),
        sa.Column("max_notional", sa.String(length=64), nullable=True),
        sa.Column("leverage", sa.String(length=32), nullable=True),
        sa.Column("max_attempts", sa.Integer(), nullable=True),
        sa.Column("protection_mode", sa.String(length=64), nullable=False),
        sa.Column("review_requirement", sa.String(length=128), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=64), nullable=False),
        sa.Column("review_status", sa.String(length=64), nullable=False),
        sa.Column("final_gate_result", sa.String(length=64), nullable=True),
        sa.Column("protection_status", sa.String(length=64), nullable=True),
        sa.Column("execution_intent_id", sa.String(length=128), nullable=True),
        sa.Column("entry_order_id", sa.String(length=128), nullable=True),
        sa.Column("entry_exchange_order_id", sa.String(length=128), nullable=True),
        sa.Column("tp_order_ids", _json_type(), nullable=False, server_default="[]"),
        sa.Column("tp_exchange_order_ids", _json_type(), nullable=False, server_default="[]"),
        sa.Column("sl_order_id", sa.String(length=128), nullable=True),
        sa.Column("sl_exchange_order_id", sa.String(length=128), nullable=True),
        sa.Column("tp_price", sa.String(length=64), nullable=True),
        sa.Column("sl_trigger", sa.String(length=64), nullable=True),
        sa.Column("owner_risk_acceptance", sa.String(length=128), nullable=True),
        sa.Column("hard_gates_passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("evidence_refs", _json_type(), nullable=False, server_default="[]"),
        sa.Column("metadata", _json_type(), nullable=False, server_default="{}"),
        sa.Column("action_allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("creates_authorization", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("creates_execution_intent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("places_order", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mutates_exchange", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("grants_trading_permission", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("frontend_action_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.String(length=128), nullable=False, server_default="codex"),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
        sa.CheckConstraint("side IN ('long', 'short')", name="ck_brc_live_lifecycle_reviews_side"),
        sa.CheckConstraint(
            "lifecycle_status IN ('pending_open', 'protected_open', 'closed_reviewed', 'recovery_required')",
            name="ck_brc_live_lifecycle_reviews_lifecycle_status",
        ),
        sa.CheckConstraint(
            "review_status IN ('pending_open', 'closed_reviewed', 'recovery_required')",
            name="ck_brc_live_lifecycle_reviews_review_status",
        ),
        sa.CheckConstraint("action_allowed = false", name="ck_brc_live_lifecycle_reviews_no_action"),
        sa.CheckConstraint(
            "creates_authorization = false",
            name="ck_brc_live_lifecycle_reviews_no_authorization",
        ),
        sa.CheckConstraint(
            "creates_execution_intent = false",
            name="ck_brc_live_lifecycle_reviews_no_intent",
        ),
        sa.CheckConstraint("places_order = false", name="ck_brc_live_lifecycle_reviews_no_order"),
        sa.CheckConstraint(
            "mutates_exchange = false",
            name="ck_brc_live_lifecycle_reviews_no_exchange_write",
        ),
        sa.CheckConstraint(
            "grants_trading_permission = false",
            name="ck_brc_live_lifecycle_reviews_no_permission",
        ),
        sa.CheckConstraint(
            "frontend_action_enabled = false",
            name="ck_brc_live_lifecycle_reviews_no_frontend_action",
        ),
    )
    op.create_index(
        "idx_brc_live_lifecycle_reviews_auth_time",
        TABLE_NAME,
        ["authorization_id", "created_at_ms"],
    )
    op.create_index(
        "idx_brc_live_lifecycle_reviews_symbol_time",
        TABLE_NAME,
        ["symbol", "created_at_ms"],
    )
    op.create_index(
        "idx_brc_live_lifecycle_reviews_status_time",
        TABLE_NAME,
        ["review_status", "created_at_ms"],
    )


def downgrade() -> None:
    if not _has_table(TABLE_NAME):
        return
    op.drop_index("idx_brc_live_lifecycle_reviews_status_time", table_name=TABLE_NAME)
    op.drop_index("idx_brc_live_lifecycle_reviews_symbol_time", table_name=TABLE_NAME)
    op.drop_index("idx_brc_live_lifecycle_reviews_auth_time", table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
