"""Expand nullable asset-neutral account-risk identity structure.

Revision ID: 131
Revises: 130
Create Date: 2026-07-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "131"
down_revision: Union[str, None] = "130"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    _create_snapshot_tables()

    _add_column(
        "brc_exchange_instruments",
        "instrument_type",
        sa.String(64),
    )
    _add_column(
        "brc_exchange_instruments",
        "settlement_asset",
        sa.String(64),
    )
    _add_column(
        "brc_exchange_instruments",
        "margin_asset",
        sa.String(64),
    )
    _add_column(
        "brc_exchange_instruments",
        "instrument_identity_schema_version",
        sa.String(32),
    )

    _add_column(
        "brc_strategy_group_candidate_scope",
        "exchange_instrument_id",
        sa.String(192),
    )
    _add_column(
        "brc_live_signal_events",
        "exchange_instrument_id",
        sa.String(192),
    )
    _add_column(
        "brc_action_time_invocations",
        "exchange_instrument_id",
        sa.String(192),
    )
    _add_column(
        "brc_runtime_process_outcomes",
        "exchange_instrument_id",
        sa.String(192),
    )
    _add_column(
        "brc_watcher_runtime_coverage",
        "exchange_instrument_id",
        sa.String(192),
    )

    _add_column(
        "brc_risk_cluster_memberships",
        "cluster_membership_snapshot_id",
        sa.String(192),
    )
    _add_column("brc_risk_cluster_memberships", "membership_role", sa.String(32))
    _add_column("brc_risk_cluster_memberships", "status", sa.String(32))

    for column_name, column_type in (
        ("exposure_episode_id", sa.String(192)),
        ("action_time_invocation_id", sa.String(192)),
        ("asset_class", sa.String(64)),
        ("instrument_type", sa.String(64)),
        ("settlement_asset", sa.String(64)),
        ("margin_asset", sa.String(64)),
        ("instrument_rule_snapshot_id", sa.String(192)),
        ("instrument_rule_schema_version", sa.String(32)),
        ("pricing_source_fact_snapshot_id", sa.String(192)),
        ("account_source_fact_snapshot_id", sa.String(192)),
        ("account_fact_schema_version", sa.String(32)),
        ("primary_risk_cluster_id", sa.String(192)),
        ("cluster_membership_snapshot_id", sa.String(192)),
        ("capacity_claim_schema_version", sa.String(32)),
        ("capacity_claim_hash", sa.String(64)),
        ("reservation_idempotency_key", sa.String(192)),
        ("reconciliation_state", sa.String(64)),
        ("released_at_ms", sa.BIGINT()),
        ("invalidated_at_ms", sa.BIGINT()),
        ("current_first_blocker", sa.String(256)),
    ):
        _add_column("brc_budget_reservations", column_name, column_type)

    for column_name, column_type in (
        ("exposure_episode_id", sa.String(192)),
        ("asset_class", sa.String(64)),
        ("instrument_type", sa.String(64)),
        ("capacity_claim_hash", sa.String(64)),
    ):
        _add_column("brc_action_time_tickets", column_name, column_type)

    for column_name, column_type in (
        ("asset_class", sa.String(64)),
        ("instrument_type", sa.String(64)),
        ("current_exposure_episode_id", sa.String(192)),
        ("primary_risk_cluster_id", sa.String(192)),
        ("cluster_membership_snapshot_id", sa.String(192)),
        ("account_source_fact_snapshot_id", sa.String(192)),
        ("account_fact_schema_version", sa.String(32)),
    ):
        _add_column("brc_account_exposure_current", column_name, column_type)

    _add_column(
        "brc_ticket_bound_exchange_commands",
        "exposure_episode_id",
        sa.String(192),
    )
    _add_column(
        "brc_ticket_bound_reconciliation_ticks",
        "exposure_episode_id",
        sa.String(192),
    )
    _add_column(
        "brc_live_outcome_ledger",
        "exposure_episode_id",
        sa.String(192),
    )


def downgrade() -> None:
    for table_name, columns in (
        (
            "brc_live_outcome_ledger",
            ("exposure_episode_id",),
        ),
        (
            "brc_ticket_bound_reconciliation_ticks",
            ("exposure_episode_id",),
        ),
        (
            "brc_ticket_bound_exchange_commands",
            ("exposure_episode_id",),
        ),
        (
            "brc_account_exposure_current",
            (
                "account_fact_schema_version",
                "account_source_fact_snapshot_id",
                "cluster_membership_snapshot_id",
                "primary_risk_cluster_id",
                "current_exposure_episode_id",
                "instrument_type",
                "asset_class",
            ),
        ),
        (
            "brc_action_time_tickets",
            (
                "capacity_claim_hash",
                "instrument_type",
                "asset_class",
                "exposure_episode_id",
            ),
        ),
        (
            "brc_budget_reservations",
            (
                "current_first_blocker",
                "invalidated_at_ms",
                "released_at_ms",
                "reconciliation_state",
                "reservation_idempotency_key",
                "capacity_claim_hash",
                "capacity_claim_schema_version",
                "cluster_membership_snapshot_id",
                "primary_risk_cluster_id",
                "account_fact_schema_version",
                "account_source_fact_snapshot_id",
                "pricing_source_fact_snapshot_id",
                "instrument_rule_schema_version",
                "instrument_rule_snapshot_id",
                "margin_asset",
                "settlement_asset",
                "instrument_type",
                "asset_class",
                "action_time_invocation_id",
                "exposure_episode_id",
            ),
        ),
        (
            "brc_risk_cluster_memberships",
            ("status", "membership_role", "cluster_membership_snapshot_id"),
        ),
        (
            "brc_strategy_group_candidate_scope",
            ("exchange_instrument_id",),
        ),
        (
            "brc_live_signal_events",
            ("exchange_instrument_id",),
        ),
        (
            "brc_action_time_invocations",
            ("exchange_instrument_id",),
        ),
        (
            "brc_runtime_process_outcomes",
            ("exchange_instrument_id",),
        ),
        (
            "brc_watcher_runtime_coverage",
            ("exchange_instrument_id",),
        ),
        (
            "brc_exchange_instruments",
            (
                "instrument_identity_schema_version",
                "margin_asset",
                "settlement_asset",
                "instrument_type",
            ),
        ),
    ):
        for column_name in columns:
            if _has_column(table_name, column_name):
                op.drop_column(table_name, column_name)
    for table_name in (
        "brc_risk_cluster_membership_snapshots",
        "brc_instrument_rule_snapshots",
    ):
        if _has_table(table_name):
            op.drop_table(table_name)


def _create_snapshot_tables() -> None:
    if not _has_table("brc_instrument_rule_snapshots"):
        op.create_table(
            "brc_instrument_rule_snapshots",
            sa.Column("instrument_rule_snapshot_id", sa.String(192), primary_key=True),
            sa.Column("exchange_instrument_id", sa.String(192), nullable=False),
            sa.Column("rule_schema_version", sa.String(32), nullable=False),
            sa.Column("price_tick", sa.Numeric(36, 18), nullable=False),
            sa.Column("quantity_step", sa.Numeric(36, 18), nullable=False),
            sa.Column("min_qty", sa.Numeric(36, 18), nullable=False),
            sa.Column("min_notional", sa.Numeric(36, 18), nullable=False),
            sa.Column("contract_multiplier", sa.Numeric(36, 18), nullable=False),
            sa.Column("exchange_max_leverage_for_claim_notional", sa.Integer(), nullable=False),
            sa.Column("source_fact_snapshot_id", sa.String(192), nullable=False),
            sa.Column("valid_until_ms", sa.BIGINT(), nullable=False),
            sa.Column("semantic_hash", sa.String(64), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "status IN ('current', 'superseded', 'invalid')",
                name="ck_brc_instrument_rule_snapshot_status",
            ),
        )
    if not _has_table("brc_risk_cluster_membership_snapshots"):
        op.create_table(
            "brc_risk_cluster_membership_snapshots",
            sa.Column("cluster_membership_snapshot_id", sa.String(192), primary_key=True),
            sa.Column("risk_policy_version", sa.String(96), nullable=False),
            sa.Column("primary_risk_cluster_id", sa.String(192), nullable=False),
            sa.Column("semantic_hash", sa.String(64), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "status IN ('current', 'superseded', 'invalid')",
                name="ck_brc_cluster_membership_snapshot_status",
            ),
        )


def _add_column(
    table_name: str,
    column_name: str,
    column_type: sa.types.TypeEngine,
) -> None:
    if _has_table(table_name) and not _has_column(table_name, column_name):
        op.add_column(table_name, sa.Column(column_name, column_type, nullable=True))


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    return any(
        column["name"] == column_name
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    )
