"""Add versioned strategy universes and U.S.-equity admission facts.

Revision ID: 0002_strategy_universe_us_equity
Revises: 0001_initial
Create Date: 2026-07-27

The migration is structural and forward-only at runtime.  It does not seed
business membership, mutate current Tickets, or call an external provider.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0002_strategy_universe_us_equity"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ID = sa.String(160)
SHORT_TEXT = sa.String(96)
LONG_TEXT = sa.String(512)
MONEY = sa.Numeric(38, 18)


def _id(name: str, *, primary_key: bool = False, nullable: bool = False) -> sa.Column:
    return sa.Column(name, ID, primary_key=primary_key, nullable=nullable)


def _time(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.BigInteger, nullable=nullable)


def _json(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, postgresql.JSONB, nullable=nullable)


def upgrade() -> None:
    _create_universe_tables()
    _create_product_and_calendar_tables()
    _extend_current_tables()


def downgrade() -> None:
    _remove_current_table_extensions()
    for table_name in (
        "brc_product_admission_policies",
        "brc_corporate_event_coverage",
        "brc_corporate_event_versions",
        "brc_market_calendar_sessions",
        "brc_market_calendar_versions",
        "brc_instrument_product_current",
        "brc_instrument_product_profiles",
        "brc_armed_structures",
        "brc_universe_projection_members",
        "brc_universe_projection_runs",
        "brc_universe_projection_leases",
        "brc_scope_warm_readiness",
        "brc_strategy_universe_cutovers",
        "brc_strategy_universe_activations",
        "brc_strategy_universe_current",
        "brc_strategy_universe_members",
        "brc_strategy_universe_versions",
    ):
        op.drop_table(table_name)


def _create_universe_tables() -> None:
    op.create_table(
        "brc_strategy_universe_versions",
        _id("universe_version_id", primary_key=True),
        sa.Column("universe_version", sa.Integer, nullable=False),
        _id("strategy_group_id"),
        _id("event_spec_id"),
        sa.Column("asset_class", SHORT_TEXT, nullable=False),
        sa.Column("semantic_digest", LONG_TEXT, nullable=False),
        sa.Column("lifecycle_state", SHORT_TEXT, nullable=False),
        _time("installed_at_ms"),
        _time("activated_at_ms", nullable=True),
        sa.UniqueConstraint(
            "event_spec_id",
            "universe_version",
            name="uq_brc_strategy_universe_versions_event_version",
        ),
        sa.UniqueConstraint(
            "semantic_digest",
            name="uq_brc_strategy_universe_versions_semantic_digest",
        ),
        sa.CheckConstraint(
            "universe_version > 0",
            name="ck_brc_strategy_universe_versions_universe_version_positive",
        ),
        sa.CheckConstraint(
            "asset_class IN ('crypto', 'us_equity')",
            name="ck_brc_strategy_universe_versions_asset_class_valid",
        ),
        sa.CheckConstraint(
            "lifecycle_state IN "
            "('draft', 'installed', 'warming', 'active', 'retiring', 'retired')",
            name="ck_brc_strategy_universe_versions_lifecycle_state_valid",
        ),
        sa.CheckConstraint(
            "semantic_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_brc_strategy_universe_versions_semantic_digest_valid",
        ),
    )
    op.create_table(
        "brc_strategy_universe_members",
        _id("universe_version_id"),
        _id("exchange_instrument_id"),
        sa.Column("venue_symbol", SHORT_TEXT, nullable=False),
        sa.Column("member_role", SHORT_TEXT, nullable=False),
        sa.Column("priority_rank", sa.Integer, nullable=False),
        sa.PrimaryKeyConstraint(
            "universe_version_id",
            "exchange_instrument_id",
            name="pk_brc_strategy_universe_members",
        ),
        sa.UniqueConstraint(
            "universe_version_id",
            "member_role",
            "priority_rank",
            name="uq_brc_strategy_universe_members_role_priority",
        ),
        sa.CheckConstraint(
            "member_role IN ('candidate', 'reference')",
            name="ck_brc_strategy_universe_members_member_role_valid",
        ),
        sa.CheckConstraint(
            "priority_rank > 0",
            name="ck_brc_strategy_universe_members_priority_positive",
        ),
    )
    op.create_table(
        "brc_strategy_universe_current",
        _id("event_spec_id", primary_key=True),
        _id("universe_version_id"),
        sa.Column("activation_generation", sa.BigInteger, nullable=False),
        _time("activated_at_ms"),
        sa.UniqueConstraint(
            "universe_version_id",
            name="uq_brc_strategy_universe_current_universe_version_id",
        ),
        sa.CheckConstraint(
            "activation_generation > 0",
            name="ck_brc_strategy_universe_current_activation_generation_positive",
        ),
    )
    op.create_table(
        "brc_strategy_universe_activations",
        _id("activation_id", primary_key=True),
        _id("event_spec_id"),
        _id("old_universe_version_id", nullable=True),
        _id("new_universe_version_id"),
        sa.Column("activation_generation", sa.BigInteger, nullable=False),
        sa.Column("operation", SHORT_TEXT, nullable=False),
        sa.Column("activation_digest", LONG_TEXT, nullable=False),
        _time("activated_at_ms"),
        sa.UniqueConstraint(
            "event_spec_id",
            "activation_generation",
            name="uq_brc_strategy_universe_activations_event_generation",
        ),
        sa.UniqueConstraint(
            "activation_digest",
            name="uq_brc_strategy_universe_activations_activation_digest",
        ),
        sa.CheckConstraint(
            "activation_generation > 0",
            name="ck_brc_universe_activations_generation_positive",
        ),
    )
    op.create_table(
        "brc_universe_projection_runs",
        _id("projection_run_id", primary_key=True),
        _id("event_spec_id"),
        _id("universe_version_id"),
        sa.Column("universe_digest", LONG_TEXT, nullable=False),
        _time("as_of_close_time_ms"),
        sa.Column("input_digest", LONG_TEXT, nullable=False),
        sa.Column("reference_digest", LONG_TEXT, nullable=False),
        sa.Column("regime_eligible", sa.Boolean, nullable=False),
        sa.Column("projection_status", SHORT_TEXT, nullable=False),
        sa.Column("failure_reason", LONG_TEXT, nullable=True),
        _time("created_at_ms"),
        _time("completed_at_ms", nullable=True),
        sa.UniqueConstraint(
            "event_spec_id",
            "universe_version_id",
            "as_of_close_time_ms",
            "input_digest",
            name="uq_brc_universe_projection_runs_input",
        ),
    )
    op.create_table(
        "brc_universe_projection_leases",
        _id("projection_claim_id", primary_key=True),
        _id("event_spec_id"),
        _id("universe_version_id"),
        _time("as_of_close_time_ms"),
        sa.Column("claim_status", SHORT_TEXT, nullable=False),
        _id("claim_owner", nullable=True),
        _time("lease_until_ms", nullable=True),
        sa.Column("failure_reason", LONG_TEXT, nullable=True),
        _time("updated_at_ms"),
        sa.UniqueConstraint(
            "event_spec_id",
            "universe_version_id",
            "as_of_close_time_ms",
            name="uq_brc_universe_projection_leases_scope_close",
        ),
        sa.CheckConstraint(
            "claim_status IN ('running', 'completed', 'failed')",
            name="ck_brc_universe_projection_leases_status_valid",
        ),
    )
    op.create_table(
        "brc_scope_warm_readiness",
        _id("runtime_scope_id", primary_key=True),
        _id("universe_version_id"),
        sa.Column("observation_fact_digest", LONG_TEXT, nullable=False),
        _id("product_profile_id", nullable=True),
        sa.Column("product_profile_digest", LONG_TEXT, nullable=True),
        _id("projection_run_id", nullable=True),
        sa.Column(
            "instrument_rules_projection_version",
            sa.BigInteger,
            nullable=True,
        ),
        sa.Column("readiness_digest", LONG_TEXT, nullable=False),
        _time("ready_at_ms"),
        sa.UniqueConstraint(
            "universe_version_id",
            "runtime_scope_id",
            name="uq_brc_scope_warm_readiness_universe_scope",
        ),
    )
    op.create_table(
        "brc_strategy_universe_cutovers",
        _id("cutover_id", primary_key=True),
        sa.Column("target_runtime_commit", SHORT_TEXT, nullable=False),
        sa.Column("target_schema_revision", SHORT_TEXT, nullable=False),
        sa.Column("target_seed_identity", LONG_TEXT, nullable=False),
        sa.Column(
            "external_flat_verification_digest",
            LONG_TEXT,
            nullable=False,
        ),
        _json("terminal_ticket_ids"),
        _json("resolved_incident_ids"),
        _json("before_counts"),
        _json("after_counts"),
        sa.Column("status", SHORT_TEXT, nullable=False),
        _time("applied_at_ms"),
        sa.CheckConstraint(
            "status = 'applied'",
            name="ck_brc_strategy_universe_cutovers_status_applied",
        ),
    )
    op.create_table(
        "brc_universe_projection_members",
        _id("projection_run_id"),
        _id("exchange_instrument_id"),
        sa.Column("eligible", sa.Boolean, nullable=False),
        sa.Column("rank", sa.Integer, nullable=True),
        sa.Column("return_24h", MONEY, nullable=False),
        sa.Column("return_72h", MONEY, nullable=False),
        sa.Column("relative_strength_24h", MONEY, nullable=False),
        sa.Column("relative_strength_72h", MONEY, nullable=False),
        sa.Column("volume_ratio_24h", MONEY, nullable=False),
        sa.Column("trend_eligible", sa.Boolean, nullable=False),
        sa.Column("metrics_digest", LONG_TEXT, nullable=False),
        sa.PrimaryKeyConstraint(
            "projection_run_id",
            "exchange_instrument_id",
            name="pk_brc_universe_projection_members",
        ),
        sa.CheckConstraint(
            "rank IS NULL OR rank > 0",
            name="ck_brc_universe_projection_members_rank_positive",
        ),
    )
    op.create_table(
        "brc_armed_structures",
        _id("armed_structure_id", primary_key=True),
        _id("event_spec_id"),
        _id("universe_version_id"),
        _id("projection_run_id"),
        _id("exchange_instrument_id"),
        sa.Column("armed_generation", sa.BigInteger, nullable=False),
        sa.Column("breakout_boundary", MONEY, nullable=False),
        sa.Column("compression_ratio", MONEY, nullable=False),
        sa.Column("input_digest", LONG_TEXT, nullable=False),
        sa.Column("status", SHORT_TEXT, nullable=False),
        _time("armed_at_ms"),
        _time("expires_at_ms"),
        sa.UniqueConstraint(
            "event_spec_id",
            "exchange_instrument_id",
            "armed_generation",
            name="uq_brc_armed_structures_event_instrument_generation",
        ),
        sa.CheckConstraint(
            "armed_generation > 0",
            name="ck_brc_armed_structures_armed_generation_positive",
        ),
        sa.CheckConstraint(
            "breakout_boundary > 0 AND compression_ratio >= 0",
            name="ck_brc_armed_structures_values_valid",
        ),
        sa.CheckConstraint(
            "expires_at_ms > armed_at_ms",
            name="ck_brc_armed_structures_time_window_valid",
        ),
    )


def _create_product_and_calendar_tables() -> None:
    op.create_table(
        "brc_instrument_product_profiles",
        _id("product_profile_id", primary_key=True),
        _id("exchange_instrument_id"),
        sa.Column("profile_version", sa.Integer, nullable=False),
        sa.Column("venue_id", SHORT_TEXT, nullable=False),
        sa.Column("contract_type", SHORT_TEXT, nullable=False),
        sa.Column("underlying_type", SHORT_TEXT, nullable=False),
        sa.Column("margin_asset", SHORT_TEXT, nullable=False),
        sa.Column("product_status", SHORT_TEXT, nullable=False),
        sa.Column("configured_leverage", sa.Integer, nullable=False),
        sa.Column("margin_mode", SHORT_TEXT, nullable=False),
        _json("source_payload"),
        sa.Column("semantic_digest", LONG_TEXT, nullable=False),
        _time("observed_at_ms"),
        _time("valid_until_ms"),
        _time("created_at_ms"),
        sa.UniqueConstraint(
            "exchange_instrument_id",
            "profile_version",
            name="uq_brc_instrument_product_profiles_instrument_version",
        ),
        sa.UniqueConstraint(
            "semantic_digest",
            name="uq_brc_instrument_product_profiles_semantic_digest",
        ),
        sa.CheckConstraint(
            "profile_version > 0",
            name="ck_brc_instrument_product_profiles_profile_version_positive",
        ),
        sa.CheckConstraint(
            "configured_leverage = 5",
            name="ck_brc_product_profiles_leverage_fixed_five",
        ),
        sa.CheckConstraint(
            "margin_mode = 'cross'",
            name="ck_brc_instrument_product_profiles_margin_mode_cross",
        ),
        sa.CheckConstraint(
            "valid_until_ms > observed_at_ms",
            name="ck_brc_instrument_product_profiles_time_window_valid",
        ),
    )
    op.create_table(
        "brc_instrument_product_current",
        _id("exchange_instrument_id", primary_key=True),
        _id("product_profile_id"),
        _time("updated_at_ms"),
        sa.UniqueConstraint(
            "product_profile_id",
            name="uq_brc_instrument_product_current_product_profile_id",
        ),
    )
    op.create_table(
        "brc_market_calendar_versions",
        _id("calendar_version_id", primary_key=True),
        sa.Column("calendar_version", sa.Integer, nullable=False),
        sa.Column("source_name", LONG_TEXT, nullable=False),
        sa.Column("timezone_name", SHORT_TEXT, nullable=False),
        sa.Column("horizon_start_date", sa.Date, nullable=False),
        sa.Column("horizon_end_date", sa.Date, nullable=False),
        sa.Column("semantic_digest", LONG_TEXT, nullable=False),
        sa.Column("status", SHORT_TEXT, nullable=False),
        _time("created_at_ms"),
        sa.UniqueConstraint(
            "semantic_digest",
            name="uq_brc_market_calendar_versions_semantic_digest",
        ),
        sa.CheckConstraint(
            "calendar_version > 0",
            name="ck_brc_market_calendar_versions_calendar_version_positive",
        ),
        sa.CheckConstraint(
            "horizon_end_date >= horizon_start_date",
            name="ck_brc_market_calendar_versions_horizon_valid",
        ),
    )
    op.create_table(
        "brc_market_calendar_sessions",
        _id("calendar_version_id"),
        sa.Column("session_date", sa.Date, nullable=False),
        _time("regular_open_at_ms", nullable=True),
        _time("regular_close_at_ms", nullable=True),
        sa.Column("holiday", sa.Boolean, nullable=False),
        sa.Column("early_close", sa.Boolean, nullable=False),
        sa.Column("source_ref", LONG_TEXT, nullable=False),
        sa.PrimaryKeyConstraint(
            "calendar_version_id",
            "session_date",
            name="pk_brc_market_calendar_sessions",
        ),
        sa.CheckConstraint(
            "(holiday AND regular_open_at_ms IS NULL "
            "AND regular_close_at_ms IS NULL) "
            "OR (NOT holiday AND regular_open_at_ms IS NOT NULL "
            "AND regular_close_at_ms > regular_open_at_ms)",
            name="ck_brc_market_calendar_sessions_session_shape_valid",
        ),
    )
    op.create_table(
        "brc_corporate_event_versions",
        _id("corporate_event_version_id", primary_key=True),
        _id("exchange_instrument_id"),
        sa.Column("source_event_id", LONG_TEXT, nullable=False),
        sa.Column("event_kind", SHORT_TEXT, nullable=False),
        sa.Column("certainty", SHORT_TEXT, nullable=False),
        sa.Column("event_date", sa.Date, nullable=False),
        _time("effective_at_ms", nullable=True),
        sa.Column("payload_digest", LONG_TEXT, nullable=False),
        sa.Column("status", SHORT_TEXT, nullable=False),
        _time("observed_at_ms"),
        _time("valid_until_ms"),
        sa.UniqueConstraint(
            "exchange_instrument_id",
            "source_event_id",
            name="uq_brc_corporate_event_versions_instrument_source",
        ),
        sa.CheckConstraint(
            "event_kind IN ('earnings', 'split', 'contract_adjustment')",
            name="ck_brc_corporate_event_versions_event_kind_valid",
        ),
        sa.CheckConstraint(
            "certainty IN ('exact_time', 'date_only')",
            name="ck_brc_corporate_event_versions_certainty_valid",
        ),
    )
    op.create_table(
        "brc_corporate_event_coverage",
        _id("coverage_id", primary_key=True),
        _id("exchange_instrument_id"),
        sa.Column("source_name", LONG_TEXT, nullable=False),
        _time("coverage_start_ms"),
        _time("coverage_end_ms"),
        sa.Column("coverage_status", SHORT_TEXT, nullable=False),
        sa.Column("coverage_digest", LONG_TEXT, nullable=False),
        _time("observed_at_ms"),
        _time("valid_until_ms"),
        sa.UniqueConstraint(
            "coverage_digest",
            name="uq_brc_corporate_event_coverage_coverage_digest",
        ),
        sa.CheckConstraint(
            "coverage_end_ms > coverage_start_ms",
            name="ck_brc_corporate_event_coverage_coverage_window_valid",
        ),
    )
    op.create_table(
        "brc_product_admission_policies",
        _id("product_policy_version_id", primary_key=True),
        sa.Column("policy_version", sa.Integer, nullable=False),
        sa.Column("asset_class", SHORT_TEXT, nullable=False),
        _json("session_thresholds"),
        _json("earnings_policy"),
        sa.Column("configured_leverage", sa.Integer, nullable=False),
        sa.Column("semantic_digest", LONG_TEXT, nullable=False),
        sa.Column("status", SHORT_TEXT, nullable=False),
        _time("created_at_ms"),
        sa.UniqueConstraint(
            "asset_class",
            "policy_version",
            name="uq_brc_product_admission_policies_asset_version",
        ),
        sa.UniqueConstraint(
            "semantic_digest",
            name="uq_brc_product_admission_policies_semantic_digest",
        ),
        sa.CheckConstraint(
            "policy_version > 0",
            name="ck_brc_product_admission_policies_policy_version_positive",
        ),
        sa.CheckConstraint(
            "configured_leverage = 5",
            name="ck_brc_product_policies_leverage_fixed_five",
        ),
    )


def _extend_current_tables() -> None:
    op.drop_constraint(
        "uq_brc_strategy_candidate_scopes_event_instrument",
        "brc_strategy_candidate_scopes",
        type_="unique",
    )
    op.add_column(
        "brc_strategy_candidate_scopes",
        _id("universe_version_id", nullable=True),
    )
    op.create_unique_constraint(
        "uq_brc_candidate_scopes_universe_event_instrument",
        "brc_strategy_candidate_scopes",
        ("universe_version_id", "event_spec_id", "exchange_instrument_id"),
    )
    op.add_column(
        "brc_owner_policy_current",
        sa.Column(
            "max_portfolio_stop_risk_fraction",
            MONEY,
            nullable=False,
            server_default=sa.text("0.09"),
        ),
    )
    op.create_check_constraint(
        "ck_brc_owner_policy_portfolio_stop_risk_valid",
        "brc_owner_policy_current",
        "max_portfolio_stop_risk_fraction > 0 "
        "AND max_portfolio_stop_risk_fraction < 1",
    )
    op.add_column(
        "brc_runtime_scopes_current",
        _id("universe_version_id", nullable=True),
    )
    op.drop_constraint(
        "uq_brc_runtime_scopes_current_identity",
        "brc_runtime_scopes_current",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_brc_runtime_scopes_current_universe_identity",
        "brc_runtime_scopes_current",
        (
            "strategy_group_id",
            "event_spec_id",
            "runtime_profile_id",
            "universe_version_id",
            "exchange_instrument_id",
            "position_side",
        ),
    )
    op.add_column(
        "brc_runtime_scopes_current",
        sa.Column(
            "observation_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "brc_runtime_scopes_current",
        sa.Column(
            "entry_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "brc_runtime_scopes_current",
        sa.Column(
            "scope_state",
            SHORT_TEXT,
            nullable=False,
            server_default=sa.text("'legacy'"),
        ),
    )
    op.add_column(
        "brc_runtime_scopes_current",
        _time("warm_ready_at_ms", nullable=True),
    )
    op.add_column(
        "brc_runtime_scopes_current",
        _time("reprofile_required_at_ms", nullable=True),
    )
    for column in (
        _id("universe_version_id", nullable=True),
        sa.Column("universe_digest", LONG_TEXT, nullable=True),
        _id("projection_run_id", nullable=True),
        _id("armed_structure_id", nullable=True),
        sa.Column("session_code", SHORT_TEXT, nullable=True),
        sa.Column("session_multiplier", MONEY, nullable=True),
        _id("product_policy_version_id", nullable=True),
    ):
        op.add_column("brc_signal_events", column)
    op.create_index(
        "ix_brc_signal_events_event_instrument_occurred",
        "brc_signal_events",
        ("event_spec_id", "exchange_instrument_id", "occurred_at_ms"),
    )
    for column in (
        _id("universe_version_id", nullable=True),
        sa.Column("universe_digest", LONG_TEXT, nullable=True),
        _id("projection_run_id", nullable=True),
        _id("armed_structure_id", nullable=True),
        _id("product_policy_version_id", nullable=True),
        _id("exit_policy_id", nullable=True),
        sa.Column("exit_policy_version", SHORT_TEXT, nullable=True),
        sa.Column("exit_policy_digest", LONG_TEXT, nullable=True),
        _json("exit_policy_payload", nullable=True),
        sa.Column("portfolio_stop_risk_before", MONEY, nullable=True),
        sa.Column("portfolio_stop_risk_after", MONEY, nullable=True),
        sa.Column("session_code", SHORT_TEXT, nullable=True),
        sa.Column("session_multiplier", MONEY, nullable=True),
        sa.Column("product_admission_digest", LONG_TEXT, nullable=True),
    ):
        op.add_column("brc_capacity_claims", column)
    for column in (
        _id("universe_version_id", nullable=True),
        sa.Column("universe_digest", LONG_TEXT, nullable=True),
        _id("projection_run_id", nullable=True),
        _id("armed_structure_id", nullable=True),
        _id("product_policy_version_id", nullable=True),
        sa.Column("session_code", SHORT_TEXT, nullable=True),
        sa.Column("session_multiplier", MONEY, nullable=True),
        sa.Column("product_admission_digest", LONG_TEXT, nullable=True),
        _id("exit_policy_id", nullable=True),
        sa.Column("exit_policy_version", SHORT_TEXT, nullable=True),
        sa.Column("exit_policy_digest", LONG_TEXT, nullable=True),
        _json("exit_policy_payload", nullable=True),
    ):
        op.add_column("brc_trade_tickets", column)


def _remove_current_table_extensions() -> None:
    for column_name in (
        "exit_policy_payload",
        "exit_policy_digest",
        "exit_policy_version",
        "exit_policy_id",
        "product_admission_digest",
        "session_multiplier",
        "session_code",
        "product_policy_version_id",
        "armed_structure_id",
        "projection_run_id",
        "universe_digest",
        "universe_version_id",
    ):
        op.drop_column("brc_trade_tickets", column_name)
    for column_name in (
        "exit_policy_payload",
        "exit_policy_digest",
        "exit_policy_version",
        "exit_policy_id",
        "product_policy_version_id",
        "armed_structure_id",
        "projection_run_id",
        "universe_digest",
        "universe_version_id",
        "product_admission_digest",
        "session_multiplier",
        "session_code",
        "portfolio_stop_risk_after",
        "portfolio_stop_risk_before",
    ):
        op.drop_column("brc_capacity_claims", column_name)
    for column_name in (
        "product_policy_version_id",
        "session_multiplier",
        "session_code",
        "armed_structure_id",
        "projection_run_id",
        "universe_digest",
        "universe_version_id",
    ):
        op.drop_column("brc_signal_events", column_name)
    op.drop_index(
        "ix_brc_signal_events_event_instrument_occurred",
        table_name="brc_signal_events",
    )
    op.drop_constraint(
        "uq_brc_runtime_scopes_current_universe_identity",
        "brc_runtime_scopes_current",
        type_="unique",
    )
    for column_name in (
        "reprofile_required_at_ms",
        "warm_ready_at_ms",
        "scope_state",
        "entry_enabled",
        "observation_enabled",
        "universe_version_id",
    ):
        op.drop_column("brc_runtime_scopes_current", column_name)
    op.create_unique_constraint(
        "uq_brc_runtime_scopes_current_identity",
        "brc_runtime_scopes_current",
        (
            "strategy_group_id",
            "event_spec_id",
            "runtime_profile_id",
            "exchange_instrument_id",
            "position_side",
        ),
    )
    op.drop_constraint(
        "ck_brc_owner_policy_portfolio_stop_risk_valid",
        "brc_owner_policy_current",
        type_="check",
    )
    op.drop_column(
        "brc_owner_policy_current",
        "max_portfolio_stop_risk_fraction",
    )
    op.drop_constraint(
        "uq_brc_candidate_scopes_universe_event_instrument",
        "brc_strategy_candidate_scopes",
        type_="unique",
    )
    op.drop_column("brc_strategy_candidate_scopes", "universe_version_id")
    op.create_unique_constraint(
        "uq_brc_strategy_candidate_scopes_event_instrument",
        "brc_strategy_candidate_scopes",
        ("event_spec_id", "exchange_instrument_id"),
    )
