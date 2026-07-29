"""Replace liquidation-price authority with Cross Margin Stop stress evidence.

Revision ID: 0003_cross_margin_stop_stress
Revises: 0002_crypto_strategy_universe
Create Date: 2026-07-29

The upgrade is intentionally flat-only and forward-only. The final migration
shape is completed alongside the application model in this release.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_cross_margin_stop_stress"
down_revision: str | None = "0002_crypto_strategy_universe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(38, 18)

_FLAT_ONLY_TABLES = tuple(
    sorted(
        (
            "brc_account_exposure_current",
            "brc_budget_reservations",
            "brc_capacity_claims",
            "brc_comparative_projection_current",
            "brc_entry_lane_current",
            "brc_event_required_facts",
            "brc_event_specs",
            "brc_exchange_commands",
            "brc_exit_policies",
            "brc_fact_definitions",
            "brc_facts_current",
            "brc_instrument_certification_current",
            "brc_instrument_rules_current",
            "brc_instruments",
            "brc_monitor_current",
            "brc_monitor_events",
            "brc_owner_policy_current",
            "brc_owner_policy_events",
            "brc_positions_current",
            "brc_readiness_current",
            "brc_retention_runs",
            "brc_runtime_capabilities_current",
            "brc_runtime_incidents",
            "brc_runtime_profiles",
            "brc_runtime_scopes_current",
            "brc_schema_metadata",
            "brc_signal_events",
            "brc_signal_fact_snapshots",
            "brc_strategy_groups",
            "brc_strategy_universe_current",
            "brc_strategy_universe_members",
            "brc_strategy_universe_versions",
            "brc_strategy_versions",
            "brc_trade_aggregates",
            "brc_trade_events",
            "brc_trade_reviews",
            "brc_trade_tickets",
        )
    )
)


def upgrade() -> None:
    _assert_flat_runtime_before_ddl()

    op.drop_constraint(
        "ck_brc_owner_policy_current_liq_ratio_positive",
        "brc_owner_policy_current",
        type_="check",
    )
    op.alter_column(
        "brc_owner_policy_current",
        "min_liquidation_distance_to_stop_distance_ratio",
        new_column_name="post_stop_stress_multiple",
        existing_type=MONEY,
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_brc_owner_policy_current_post_stop_stress_multiple_positive",
        "brc_owner_policy_current",
        "post_stop_stress_multiple > 0",
    )

    op.add_column(
        "brc_instrument_rules_current",
        sa.Column("notional_coefficient", MONEY, nullable=False),
    )
    op.add_column(
        "brc_instrument_rules_current",
        sa.Column(
            "notional_coefficient_certified",
            sa.Boolean,
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_brc_instrument_rules_current_notional_coefficient_positive",
        "brc_instrument_rules_current",
        "notional_coefficient > 0",
    )

    op.alter_column(
        "brc_capacity_claims",
        "min_liquidation_distance_to_stop_distance_ratio",
        new_column_name="post_stop_stress_multiple",
        existing_type=MONEY,
        existing_nullable=False,
    )
    for column_name in (
        "maintenance_margin_bracket_id",
        "projected_liquidation_price",
        "projected_liquidation_distance",
        "projected_liquidation_distance_to_stop_distance_ratio",
    ):
        op.drop_column("brc_capacity_claims", column_name)
    op.add_column(
        "brc_capacity_claims",
        sa.Column(
            "cross_margin_stress_evidence",
            postgresql.JSONB,
            nullable=False,
        ),
    )

    for column_name in (
        "min_liquidation_distance_to_stop_distance_ratio",
        "projected_liquidation_price",
        "projected_liquidation_distance_to_stop_distance_ratio",
    ):
        op.drop_column("brc_trade_tickets", column_name)
    op.add_column(
        "brc_trade_tickets",
        sa.Column("cross_margin_stress_model_id", sa.String(96), nullable=False),
    )
    op.add_column(
        "brc_trade_tickets",
        sa.Column("post_stop_stress_multiple", MONEY, nullable=False),
    )
    op.add_column(
        "brc_trade_tickets",
        sa.Column("claim_stress_proof_digest", sa.String(512), nullable=False),
    )

    for column_name in (
        "actual_liquidation_price",
        "actual_liquidation_distance",
        "actual_liquidation_distance_to_stop_distance_ratio",
    ):
        op.drop_column("brc_trade_aggregates", column_name)
    op.add_column(
        "brc_trade_aggregates",
        sa.Column("venue_reported_liquidation_price", MONEY, nullable=True),
    )
    op.add_column(
        "brc_trade_aggregates",
        sa.Column("post_fill_stress_status", sa.String(96), nullable=True),
    )
    op.add_column(
        "brc_trade_aggregates",
        sa.Column("post_fill_stress_proof_digest", sa.String(512), nullable=True),
    )

    op.add_column(
        "brc_positions_current",
        sa.Column("venue_reported_liquidation_price", MONEY, nullable=True),
    )
    op.add_column(
        "brc_positions_current",
        sa.Column(
            "venue_reported_liquidation_observation_status",
            sa.String(96),
            nullable=False,
        ),
    )


def downgrade() -> None:
    raise RuntimeError("0003_cross_margin_stop_stress is forward-only")


def _assert_flat_runtime_before_ddl() -> None:
    locked_tables = ", ".join(f'"{table_name}"' for table_name in _FLAT_ONLY_TABLES)
    op.execute(sa.text(f"LOCK TABLE {locked_tables} IN ACCESS EXCLUSIVE MODE"))
    predicates = " OR ".join(
        f'EXISTS (SELECT 1 FROM "{table_name}" LIMIT 1)'
        for table_name in _FLAT_ONLY_TABLES
    )
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF {predicates} THEN
                    RAISE EXCEPTION
                        'runtime/trade tables must be empty before '
                        '0003_cross_margin_stop_stress'
                        USING ERRCODE = '55000';
                END IF;
            END
            $$;
            """
        )
    )
