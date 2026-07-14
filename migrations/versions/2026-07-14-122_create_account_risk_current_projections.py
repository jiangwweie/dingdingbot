"""Create account exposure and budget current projections.

Revision ID: 122
Revises: 121
Create Date: 2026-07-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "122"
down_revision: Union[str, None] = "121"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not _has_table("brc_account_exposure_current"):
        op.create_table(
            "brc_account_exposure_current",
            sa.Column("account_exposure_current_id", sa.String(192), primary_key=True),
            sa.Column("account_id", sa.String(192), nullable=False),
            sa.Column("exchange_id", sa.String(96), nullable=False),
            sa.Column("exchange_instrument_id", sa.String(192), nullable=False),
            sa.Column("exchange_symbol", sa.String(128), nullable=False),
            sa.Column("position_mode", sa.String(32), nullable=False),
            sa.Column("position_bucket", sa.String(32), nullable=False),
            sa.Column("netting_domain_key", sa.String(256), nullable=False),
            sa.Column("owner_ticket_id", sa.String(192), nullable=True),
            sa.Column("ownership_state", sa.String(64), nullable=False),
            sa.Column("position_slot_claimed", sa.Boolean(), nullable=False),
            sa.Column("exposure_state", sa.String(64), nullable=False),
            sa.Column("position_qty", sa.Numeric(36, 18), nullable=False),
            sa.Column("entry_price", sa.Numeric(36, 18), nullable=True),
            sa.Column("confirmed_stop_price", sa.Numeric(36, 18), nullable=True),
            sa.Column("working_entry_qty", sa.Numeric(36, 18), nullable=False),
            sa.Column("planned_reserved_risk", sa.Numeric(36, 18), nullable=False),
            sa.Column("actual_directional_risk", sa.Numeric(36, 18), nullable=False),
            sa.Column("held_risk", sa.Numeric(36, 18), nullable=False),
            sa.Column("exchange_initial_margin", sa.Numeric(36, 18), nullable=False),
            sa.Column("unreflected_pending_margin", sa.Numeric(36, 18), nullable=False),
            sa.Column("protection_state", sa.String(64), nullable=False),
            sa.Column("stop_covered_qty", sa.Numeric(36, 18), nullable=False),
            sa.Column("tp1_open_qty", sa.Numeric(36, 18), nullable=False),
            sa.Column("runner_stop_open_qty", sa.Numeric(36, 18), nullable=False),
            sa.Column("reconciliation_state", sa.String(64), nullable=False),
            sa.Column("first_blocker", sa.String(256), nullable=True),
            sa.Column("source_snapshot_id", sa.String(192), nullable=False),
            sa.Column("observed_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("valid_until_ms", sa.BIGINT(), nullable=False),
            sa.Column("projection_version", sa.BIGINT(), nullable=False),
            sa.Column("semantic_fingerprint", sa.String(64), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "position_mode IN ('one_way', 'hedge')",
                name="ck_brc_account_exposure_current_position_mode",
            ),
            sa.CheckConstraint("position_qty >= 0", name="ck_brc_account_exposure_current_qty"),
            sa.CheckConstraint("held_risk >= 0", name="ck_brc_account_exposure_current_held_risk"),
            sa.UniqueConstraint(
                "account_id", "exchange_instrument_id", "position_mode", "position_bucket",
                name="uq_brc_account_exposure_current_domain",
            ),
        )

    if not _has_table("brc_account_budget_current"):
        op.create_table(
            "brc_account_budget_current",
            sa.Column("account_budget_current_id", sa.String(192), primary_key=True),
            sa.Column("account_id", sa.String(192), nullable=False),
            sa.Column("runtime_profile_id", sa.String(128), nullable=False),
            sa.Column("risk_policy_version", sa.String(96), nullable=False),
            sa.Column("total_wallet_balance", sa.Numeric(36, 18), nullable=False),
            sa.Column("available_balance", sa.Numeric(36, 18), nullable=False),
            sa.Column("exchange_total_initial_margin", sa.Numeric(36, 18), nullable=False),
            sa.Column("reserved_risk", sa.Numeric(36, 18), nullable=False),
            sa.Column("working_entry_risk", sa.Numeric(36, 18), nullable=False),
            sa.Column("open_directional_risk", sa.Numeric(36, 18), nullable=False),
            sa.Column("unknown_held_risk", sa.Numeric(36, 18), nullable=False),
            sa.Column("portfolio_held_risk", sa.Numeric(36, 18), nullable=False),
            sa.Column("unreflected_pending_margin", sa.Numeric(36, 18), nullable=False),
            sa.Column("portfolio_margin_used", sa.Numeric(36, 18), nullable=False),
            sa.Column("ticket_risk_limit", sa.Numeric(36, 18), nullable=False),
            sa.Column("portfolio_risk_limit", sa.Numeric(36, 18), nullable=False),
            sa.Column("portfolio_risk_remaining", sa.Numeric(36, 18), nullable=False),
            sa.Column("portfolio_margin_limit", sa.Numeric(36, 18), nullable=False),
            sa.Column("portfolio_margin_remaining", sa.Numeric(36, 18), nullable=False),
            sa.Column("claimed_position_slots", sa.Integer(), nullable=False),
            sa.Column("pending_ticket_claims", sa.Integer(), nullable=False),
            sa.Column("max_concurrent_positions", sa.Integer(), nullable=False),
            sa.Column("reconciliation_state", sa.String(64), nullable=False),
            sa.Column("new_entry_allowed", sa.Boolean(), nullable=False),
            sa.Column("first_blocker", sa.String(256), nullable=True),
            sa.Column("source_snapshot_id", sa.String(192), nullable=False),
            sa.Column("source_watermark", sa.String(256), nullable=False),
            sa.Column("valid_until_ms", sa.BIGINT(), nullable=False),
            sa.Column("projection_version", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.UniqueConstraint(
                "account_id", "runtime_profile_id", "risk_policy_version",
                name="uq_brc_account_budget_current_scope",
            ),
        )

    if not _has_table("brc_account_risk_projection_events"):
        op.create_table(
            "brc_account_risk_projection_events",
            sa.Column("account_risk_projection_event_id", sa.String(192), primary_key=True),
            sa.Column("account_exposure_current_id", sa.String(192), nullable=False),
            sa.Column("semantic_fingerprint", sa.String(64), nullable=False),
            sa.Column("event_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.UniqueConstraint(
                "account_exposure_current_id", "semantic_fingerprint",
                name="uq_brc_account_risk_projection_semantic_event",
            ),
        )

    if not _has_table("brc_budget_reservation_events"):
        op.create_table(
            "brc_budget_reservation_events",
            sa.Column("budget_reservation_event_id", sa.String(192), primary_key=True),
            sa.Column("budget_reservation_id", sa.String(192), nullable=False),
            sa.Column("from_status", sa.String(64), nullable=True),
            sa.Column("to_status", sa.String(64), nullable=False),
            sa.Column("reason", sa.String(256), nullable=False),
            sa.Column("evidence_ref", sa.String(256), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        )


def downgrade() -> None:
    for table_name in (
        "brc_budget_reservation_events",
        "brc_account_risk_projection_events",
        "brc_account_budget_current",
        "brc_account_exposure_current",
    ):
        if _has_table(table_name):
            op.drop_table(table_name)


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()
