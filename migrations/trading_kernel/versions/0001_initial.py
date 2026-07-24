"""Create the clean trading-kernel PostgreSQL baseline.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-22

This migration is intentionally self-contained.  Production schema history must
remain executable even when the application package is unavailable or later
refactored.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001_initial"
down_revision: str | None = None
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
    op.create_table(
        "brc_strategy_groups",
        _id("strategy_group_id", primary_key=True),
        sa.Column("display_name", LONG_TEXT, nullable=False),
        _id("active_version_id", nullable=True),
        sa.Column("status", SHORT_TEXT, nullable=False),
        _time("updated_at_ms"),
    )
    op.create_table(
        "brc_strategy_versions",
        _id("strategy_version_id", primary_key=True),
        _id("strategy_group_id"),
        sa.Column("version", sa.Integer, nullable=False),
        _json("semantics"),
        sa.Column("status", SHORT_TEXT, nullable=False),
        _time("created_at_ms"),
        sa.UniqueConstraint(
            "strategy_group_id",
            "version",
            name="uq_brc_strategy_versions_strategy_group_id_version",
        ),
    )
    op.create_table(
        "brc_event_specs",
        _id("event_spec_id", primary_key=True),
        _id("strategy_version_id"),
        sa.Column("event_id", SHORT_TEXT, nullable=False, unique=True),
        sa.Column("position_side", SHORT_TEXT, nullable=False),
        sa.Column("timeframe", SHORT_TEXT, nullable=False),
        sa.Column("freshness_window_ms", sa.BigInteger, nullable=False),
        sa.Column("event_time_authority", SHORT_TEXT, nullable=False),
        sa.Column("entry_order_type", SHORT_TEXT, nullable=False),
        _id("protection_reference_fact_definition_id"),
        _id("exit_policy_id"),
        _json("execution_semantics"),
        sa.Column("status", SHORT_TEXT, nullable=False),
        _time("created_at_ms"),
    )
    op.create_table(
        "brc_exit_policies",
        _id("exit_policy_id", primary_key=True),
        sa.Column("exit_policy_version", SHORT_TEXT, nullable=False),
        _id("event_spec_id"),
        sa.Column("position_side", SHORT_TEXT, nullable=False),
        _json("policy"),
        sa.Column("semantic_hash", LONG_TEXT, nullable=False),
        sa.Column("status", SHORT_TEXT, nullable=False),
        _time("created_at_ms"),
        sa.UniqueConstraint(
            "event_spec_id",
            name="uq_brc_exit_policies_event_spec_id",
        ),
        sa.UniqueConstraint(
            "semantic_hash",
            name="uq_brc_exit_policies_semantic_hash",
        ),
        sa.CheckConstraint(
            "position_side IN ('long', 'short')",
            name="ck_brc_exit_policies_position_side_valid",
        ),
    )
    op.create_table(
        "brc_fact_definitions",
        _id("fact_definition_id", primary_key=True),
        sa.Column("fact_name", SHORT_TEXT, nullable=False, unique=True),
        sa.Column("value_type", SHORT_TEXT, nullable=False),
        sa.Column("freshness_ms", sa.BigInteger, nullable=False),
        _json("validation"),
    )
    op.create_table(
        "brc_event_required_facts",
        _id("event_spec_id"),
        _id("fact_definition_id"),
        sa.Column("role", SHORT_TEXT, nullable=False),
        sa.Column("required", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint(
            "event_spec_id",
            "fact_definition_id",
            name="pk_brc_event_required_facts",
        ),
    )
    op.create_table(
        "brc_instruments",
        _id("exchange_instrument_id", primary_key=True),
        sa.Column("venue_id", SHORT_TEXT, nullable=False),
        sa.Column("asset_class", SHORT_TEXT, nullable=False),
        sa.Column("venue_symbol", SHORT_TEXT, nullable=False),
        sa.Column("contract_kind", SHORT_TEXT, nullable=False),
        sa.Column("status", SHORT_TEXT, nullable=False),
        sa.UniqueConstraint(
            "venue_id",
            "venue_symbol",
            name="uq_brc_instruments_venue_id_venue_symbol",
        ),
    )
    op.create_table(
        "brc_strategy_candidate_scopes",
        _id("candidate_scope_id", primary_key=True),
        _id("strategy_group_id"),
        _id("event_spec_id"),
        _id("exchange_instrument_id"),
        sa.Column("position_side", SHORT_TEXT, nullable=False),
        sa.Column("priority_rank", sa.Integer, nullable=False),
        sa.Column("status", SHORT_TEXT, nullable=False),
        _time("created_at_ms"),
        sa.UniqueConstraint(
            "event_spec_id",
            "exchange_instrument_id",
            name="uq_brc_strategy_candidate_scopes_event_instrument",
        ),
        sa.CheckConstraint(
            "position_side IN ('long', 'short')",
            name="ck_brc_strategy_candidate_scopes_position_side_valid",
        ),
        sa.CheckConstraint(
            "priority_rank > 0",
            name="ck_brc_strategy_candidate_scopes_priority_positive",
        ),
    )
    op.create_table(
        "brc_instrument_rules_current",
        sa.Column("venue_id", SHORT_TEXT, primary_key=True),
        _id("exchange_instrument_id", primary_key=True),
        sa.Column("quantity_step", MONEY, nullable=False),
        sa.Column("price_tick", MONEY, nullable=False),
        sa.Column("min_quantity", MONEY, nullable=False),
        sa.Column("min_notional", MONEY, nullable=False),
        sa.Column("exchange_max_leverage", sa.Integer, nullable=False),
        _json("maintenance_margin_brackets"),
        sa.Column("maintenance_margin_brackets_digest", LONG_TEXT, nullable=False),
        _json("session_and_settlement"),
        _time("observed_at_ms"),
        _time("valid_until_ms"),
        sa.Column("projection_version", sa.BigInteger, nullable=False),
        sa.CheckConstraint(
            "exchange_max_leverage > 0",
            name="ck_brc_instrument_rules_current_exchange_max_leverage_positive",
        ),
        sa.CheckConstraint(
            "maintenance_margin_brackets_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_brc_instrument_rules_current_brackets_digest_valid",
        ),
    )
    op.create_table(
        "brc_owner_policy_events",
        _id("owner_policy_event_id", primary_key=True),
        _id("owner_policy_id"),
        sa.Column("policy_version", sa.Integer, nullable=False),
        sa.Column("operation", SHORT_TEXT, nullable=False),
        _json("payload"),
        _time("created_at_ms"),
        sa.UniqueConstraint(
            "owner_policy_id",
            "policy_version",
            name="uq_brc_owner_policy_events_owner_policy_id_policy_version",
        ),
    )
    op.create_table(
        "brc_owner_policy_current",
        _id("owner_policy_id", primary_key=True),
        sa.Column("policy_version", sa.Integer, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("new_entry_submit_enabled", sa.Boolean, nullable=False),
        sa.Column(
            "priority_rank",
            sa.Integer,
            nullable=False,
            server_default=sa.text("100"),
        ),
        sa.Column("max_concurrent_tickets", sa.Integer, nullable=False),
        sa.Column("planned_stop_risk_fraction", MONEY, nullable=False),
        sa.Column("max_initial_margin_utilization", MONEY, nullable=False),
        sa.Column("max_leverage", sa.Integer, nullable=False),
        sa.Column("supported_margin_mode", SHORT_TEXT, nullable=False),
        sa.Column(
            "min_liquidation_distance_to_stop_distance_ratio",
            MONEY,
            nullable=False,
        ),
        sa.Column(
            "max_post_fill_stop_risk_overrun_fraction",
            MONEY,
            nullable=False,
        ),
        _json("scope"),
        _time("updated_at_ms"),
        sa.CheckConstraint(
            "priority_rank > 0",
            name="ck_brc_owner_policy_current_priority_positive",
        ),
        sa.CheckConstraint(
            "max_concurrent_tickets > 0",
            name="ck_brc_owner_policy_current_max_concurrent_tickets_positive",
        ),
        sa.CheckConstraint(
            "planned_stop_risk_fraction > 0 AND planned_stop_risk_fraction < 1",
            name="ck_brc_owner_policy_current_planned_stop_risk_fraction_valid",
        ),
        sa.CheckConstraint(
            "max_initial_margin_utilization > 0 "
            "AND max_initial_margin_utilization <= 1",
            name="ck_brc_owner_policy_current_margin_utilization_valid",
        ),
        sa.CheckConstraint(
            "max_leverage >= 1 AND max_leverage <= 10",
            name="ck_brc_owner_policy_current_max_leverage_valid",
        ),
        sa.CheckConstraint(
            "supported_margin_mode = 'cross'",
            name="ck_brc_owner_policy_current_supported_margin_mode_cross_only",
        ),
        sa.CheckConstraint(
            "min_liquidation_distance_to_stop_distance_ratio > 0",
            name="ck_brc_owner_policy_current_liq_ratio_positive",
        ),
        sa.CheckConstraint(
            "max_post_fill_stop_risk_overrun_fraction >= 0 "
            "AND max_post_fill_stop_risk_overrun_fraction < 1",
            name="ck_brc_owner_policy_current_post_fill_overrun_valid",
        ),
    )
    op.create_table(
        "brc_runtime_profiles",
        _id("runtime_profile_id", primary_key=True),
        sa.Column("venue_id", SHORT_TEXT, nullable=False),
        _id("account_id"),
        sa.Column("environment", SHORT_TEXT, nullable=False),
        sa.Column("position_mode", SHORT_TEXT, nullable=False),
        sa.Column("status", SHORT_TEXT, nullable=False),
        _time("updated_at_ms"),
    )
    op.create_table(
        "brc_runtime_scopes_current",
        _id("runtime_scope_id", primary_key=True),
        _id("strategy_group_id"),
        _id("strategy_version_id"),
        _id("event_spec_id"),
        _id("runtime_profile_id"),
        _id("owner_policy_id"),
        _id("exchange_instrument_id"),
        sa.Column("position_side", SHORT_TEXT, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("scope_version", sa.Integer, nullable=False),
        _time("observation_due_at_ms", nullable=True),
        _time("observation_lease_until_ms", nullable=True),
        _id("observation_claim_owner", nullable=True),
        _time("updated_at_ms"),
        sa.UniqueConstraint(
            "strategy_group_id",
            "event_spec_id",
            "runtime_profile_id",
            "exchange_instrument_id",
            "position_side",
            name="uq_brc_runtime_scopes_current_identity",
        ),
    )
    op.create_index(
        "ix_brc_runtime_scopes_current_observation_due",
        "brc_runtime_scopes_current",
        ["enabled", "observation_due_at_ms", "observation_lease_until_ms"],
    )
    op.create_table(
        "brc_facts_current",
        _id("fact_current_id", primary_key=True),
        _id("runtime_scope_id"),
        _id("fact_definition_id"),
        _json("value"),
        sa.Column("satisfied", sa.Boolean, nullable=False),
        _time("observed_at_ms"),
        _time("valid_until_ms"),
        sa.Column("projection_version", sa.BigInteger, nullable=False),
        sa.UniqueConstraint(
            "runtime_scope_id",
            "fact_definition_id",
            name="uq_brc_facts_current_runtime_scope_id_fact_definition_id",
        ),
    )
    op.create_table(
        "brc_signal_events",
        _id("signal_event_id", primary_key=True),
        _id("runtime_scope_id"),
        sa.Column("runtime_scope_version", sa.Integer, nullable=False),
        _id("strategy_group_id"),
        _id("strategy_version_id"),
        _id("event_spec_id"),
        _id("exchange_instrument_id"),
        sa.Column("position_side", SHORT_TEXT, nullable=False),
        sa.Column("fact_digest", LONG_TEXT, nullable=False),
        _time("occurred_at_ms"),
        _time("observed_at_ms"),
        _time("expires_at_ms"),
        sa.CheckConstraint(
            "position_side IN ('long', 'short')",
            name="ck_brc_signal_events_position_side_valid",
        ),
        sa.CheckConstraint(
            "expires_at_ms > occurred_at_ms",
            name="ck_brc_signal_events_time_window_valid",
        ),
        sa.CheckConstraint(
            "observed_at_ms >= occurred_at_ms AND expires_at_ms > observed_at_ms",
            name="ck_brc_signal_events_observation_window_valid",
        ),
        sa.CheckConstraint(
            "fact_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_brc_signal_events_fact_digest_valid",
        ),
    )
    op.create_table(
        "brc_signal_fact_snapshots",
        _id("signal_event_id"),
        _id("fact_definition_id"),
        sa.Column("role", SHORT_TEXT, nullable=False),
        _json("value"),
        sa.Column("satisfied", sa.Boolean, nullable=False),
        _time("observed_at_ms"),
        _time("valid_until_ms"),
        sa.Column("projection_version", sa.BigInteger, nullable=False),
        sa.PrimaryKeyConstraint(
            "signal_event_id",
            "fact_definition_id",
            name="pk_brc_signal_fact_snapshots",
        ),
        sa.CheckConstraint(
            "role IN ('condition', 'protection_reference', 'disable')",
            name="ck_brc_signal_fact_snapshots_role_valid",
        ),
        sa.CheckConstraint(
            "valid_until_ms > observed_at_ms",
            name="ck_brc_signal_fact_snapshots_time_window_valid",
        ),
        sa.CheckConstraint(
            "projection_version > 0",
            name="ck_brc_signal_fact_snapshots_projection_version_positive",
        ),
    )
    op.create_table(
        "brc_readiness_current",
        _id("runtime_scope_id", primary_key=True),
        sa.Column("readiness_state", SHORT_TEXT, nullable=False),
        sa.Column("first_blocker", LONG_TEXT, nullable=True),
        _id("signal_event_id", nullable=True),
        _json("fact_summary"),
        _time("updated_at_ms"),
        sa.Column("projection_version", sa.BigInteger, nullable=False),
    )
    op.create_index(
        "ix_brc_readiness_current_readiness_state_signal_event_id",
        "brc_readiness_current",
        ["readiness_state", "signal_event_id"],
    )
    op.create_index(
        "ix_brc_signal_events_candidate_order",
        "brc_signal_events",
        [
            "expires_at_ms",
            "occurred_at_ms",
            "observed_at_ms",
            "signal_event_id",
        ],
    )
    op.create_table(
        "brc_entry_lane_current",
        sa.Column("lane_id", SHORT_TEXT, primary_key=True),
        _id("ticket_id", nullable=True),
        _id("signal_event_id", nullable=True),
        sa.Column("status", SHORT_TEXT, nullable=False),
        _time("claimed_at_ms", nullable=True),
        _time("lease_until_ms", nullable=True),
        sa.Column("claim_owner", SHORT_TEXT, nullable=True),
        sa.Column("version", sa.BigInteger, nullable=False),
    )
    op.create_table(
        "brc_runtime_capabilities_current",
        sa.Column("capability_key", SHORT_TEXT, primary_key=True),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("certified_commit", SHORT_TEXT, nullable=False),
        sa.Column("schema_revision", SHORT_TEXT, nullable=False),
        _json("certification"),
        _time("updated_at_ms"),
    )
    op.create_table(
        "brc_capacity_claims",
        _id("capacity_claim_id", primary_key=True),
        _id("ticket_id"),
        _id("signal_event_id"),
        _id("exposure_episode_id"),
        _id("strategy_group_id"),
        _id("strategy_version_id"),
        _id("event_spec_id"),
        _id("runtime_profile_id"),
        _id("owner_policy_id"),
        sa.Column("owner_policy_version", sa.Integer, nullable=False),
        _id("runtime_scope_id"),
        sa.Column("runtime_scope_version", sa.Integer, nullable=False),
        _id("account_id"),
        sa.Column("venue_id", SHORT_TEXT, nullable=False),
        _id("exchange_instrument_id"),
        sa.Column("position_side", SHORT_TEXT, nullable=False),
        sa.Column("netting_domain_key", LONG_TEXT, nullable=False),
        sa.Column("fact_digest", LONG_TEXT, nullable=False),
        sa.Column("entry_admission_snapshot_digest", LONG_TEXT, nullable=False),
        sa.Column("account_entry_health_digest", LONG_TEXT, nullable=False),
        sa.Column("instrument_entry_health_digest", LONG_TEXT, nullable=False),
        sa.Column(
            "instrument_rules_projection_version",
            sa.BigInteger,
            nullable=False,
        ),
        sa.Column("account_capacity_domain_key", LONG_TEXT, nullable=False),
        sa.Column("leverage_domain_key", LONG_TEXT, nullable=False),
        sa.Column("total_wallet_balance_at_claim", MONEY, nullable=False),
        sa.Column("total_margin_balance_at_claim", MONEY, nullable=False),
        sa.Column("total_initial_margin_at_claim", MONEY, nullable=False),
        sa.Column("total_maintenance_margin_at_claim", MONEY, nullable=False),
        sa.Column("available_margin_at_claim", MONEY, nullable=False),
        sa.Column("mark_price_at_claim", MONEY, nullable=False),
        sa.Column("position_mode_at_claim", SHORT_TEXT, nullable=False),
        sa.Column("margin_mode_at_claim", SHORT_TEXT, nullable=False),
        sa.Column("active_ticket_count_at_claim", sa.Integer, nullable=False),
        sa.Column("remaining_slots_at_claim", sa.Integer, nullable=False),
        sa.Column("planned_stop_risk_fraction", MONEY, nullable=False),
        sa.Column("planned_stop_risk_budget", MONEY, nullable=False),
        sa.Column("max_post_fill_stop_risk_overrun_fraction", MONEY, nullable=False),
        sa.Column("post_fill_stop_risk_limit", MONEY, nullable=False),
        sa.Column("max_initial_margin_utilization", MONEY, nullable=False),
        sa.Column("min_liquidation_distance_to_stop_distance_ratio", MONEY, nullable=False),
        sa.Column("ticket_margin_budget", MONEY, nullable=False),
        sa.Column("required_leverage", sa.Integer, nullable=False),
        sa.Column("selected_leverage", sa.Integer, nullable=False),
        sa.Column("configured_leverage_at_claim", sa.Integer, nullable=False),
        sa.Column("leverage_change_required", sa.Boolean, nullable=False),
        sa.Column("exchange_max_leverage", sa.Integer, nullable=False),
        sa.Column("reserved_margin", MONEY, nullable=False),
        sa.Column("maintenance_margin_bracket_id", LONG_TEXT, nullable=False),
        sa.Column("projected_liquidation_price", MONEY, nullable=False),
        sa.Column("projected_liquidation_distance", MONEY, nullable=False),
        sa.Column("projected_liquidation_distance_to_stop_distance_ratio", MONEY, nullable=False),
        sa.Column("entry_reference_price", MONEY, nullable=False),
        sa.Column("quantity", MONEY, nullable=False),
        sa.Column("notional", MONEY, nullable=False),
        sa.Column("risk_at_stop", MONEY, nullable=False),
        sa.Column("entry_order_type", SHORT_TEXT, nullable=False),
        sa.Column("entry_limit_price", MONEY, nullable=True),
        sa.Column("initial_stop_price", MONEY, nullable=False),
        _json("take_profit_prices"),
        _json("take_profit_quantities"),
        sa.Column("decision_digest", LONG_TEXT, nullable=False),
        _time("created_at_ms"),
        _time("expires_at_ms"),
        sa.UniqueConstraint(
            "ticket_id",
            name="uq_brc_capacity_claims_ticket_id",
        ),
        sa.UniqueConstraint(
            "signal_event_id",
            name="uq_brc_capacity_claims_signal_event_id",
        ),
        sa.UniqueConstraint(
            "decision_digest",
            name="uq_brc_capacity_claims_decision_digest",
        ),
        sa.CheckConstraint(
            "quantity > 0",
            name="ck_brc_capacity_claims_quantity_positive",
        ),
        sa.CheckConstraint(
            "notional > 0",
            name="ck_brc_capacity_claims_notional_positive",
        ),
        sa.CheckConstraint(
            "selected_leverage > 0",
            name="ck_brc_capacity_claims_selected_leverage_positive",
        ),
        sa.CheckConstraint(
            "selected_leverage <= exchange_max_leverage",
            name="ck_brc_claim_lev_le_exchange_max",
        ),
        sa.CheckConstraint(
            "risk_at_stop >= 0",
            name="ck_brc_capacity_claims_risk_nonnegative",
        ),
        sa.CheckConstraint(
            "risk_at_stop <= planned_stop_risk_budget",
            name="ck_brc_claim_risk_le_planned",
        ),
        sa.CheckConstraint(
            "post_fill_stop_risk_limit >= planned_stop_risk_budget",
            name="ck_brc_claim_postfill_ge_planned",
        ),
        sa.CheckConstraint(
            "expires_at_ms > created_at_ms",
            name="ck_brc_capacity_claims_time_window_valid",
        ),
    )
    op.create_table(
        "brc_trade_tickets",
        _id("ticket_id", primary_key=True),
        _id("exposure_episode_id"),
        _id("signal_event_id"),
        _id("strategy_group_id"),
        _id("strategy_version_id"),
        _id("event_spec_id"),
        _id("runtime_profile_id"),
        _id("owner_policy_id"),
        sa.Column("owner_policy_version", sa.Integer, nullable=False),
        _id("runtime_scope_id"),
        sa.Column("runtime_scope_version", sa.Integer, nullable=False),
        _id("account_id"),
        sa.Column("venue_id", SHORT_TEXT, nullable=False),
        _id("exchange_instrument_id"),
        sa.Column("position_side", SHORT_TEXT, nullable=False),
        sa.Column("netting_domain_key", LONG_TEXT, nullable=False),
        sa.Column("active_netting_domain_key", LONG_TEXT, nullable=True),
        sa.Column("entry_reference_price", MONEY, nullable=False),
        sa.Column("quantity", MONEY, nullable=False),
        sa.Column("notional", MONEY, nullable=False),
        _id("capacity_claim_id"),
        sa.Column("planned_stop_risk_budget", MONEY, nullable=False),
        sa.Column("post_fill_stop_risk_limit", MONEY, nullable=False),
        sa.Column("selected_leverage", sa.Integer, nullable=False),
        sa.Column("leverage_change_required", sa.Boolean, nullable=False),
        sa.Column("reserved_margin", MONEY, nullable=False),
        sa.Column("risk_reservation_basis", SHORT_TEXT, nullable=False),
        sa.Column("margin_mode", SHORT_TEXT, nullable=False),
        sa.Column("min_liquidation_distance_to_stop_distance_ratio", MONEY, nullable=False),
        sa.Column("projected_liquidation_price", MONEY, nullable=False),
        sa.Column("projected_liquidation_distance_to_stop_distance_ratio", MONEY, nullable=False),
        sa.Column("risk_at_stop", MONEY, nullable=False),
        sa.Column("entry_order_type", SHORT_TEXT, nullable=False),
        sa.Column("entry_limit_price", MONEY, nullable=True),
        sa.Column("initial_stop_price", MONEY, nullable=False),
        _json("take_profit_prices"),
        _json("take_profit_quantities"),
        sa.Column("fact_digest", LONG_TEXT, nullable=False),
        sa.Column("decision_digest", LONG_TEXT, nullable=False),
        sa.Column("status", SHORT_TEXT, nullable=False),
        _time("created_at_ms"),
        _time("expires_at_ms"),
        _time("terminal_at_ms", nullable=True),
        sa.UniqueConstraint(
            "signal_event_id",
            name="uq_brc_trade_tickets_signal_event_id",
        ),
        sa.UniqueConstraint(
            "active_netting_domain_key",
            name="uq_brc_trade_tickets_active_netting_domain_key",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_brc_trade_tickets_quantity_positive"),
        sa.CheckConstraint("notional > 0", name="ck_brc_trade_tickets_notional_positive"),
        sa.CheckConstraint("selected_leverage > 0", name="ck_brc_trade_tickets_selected_leverage_positive"),
        sa.CheckConstraint("risk_at_stop >= 0", name="ck_brc_trade_tickets_risk_nonnegative"),
    )
    op.create_index(
        "ix_brc_trade_tickets_instrument_window",
        "brc_trade_tickets",
        [
            "venue_id",
            "account_id",
            "exchange_instrument_id",
            "created_at_ms",
            "terminal_at_ms",
        ],
    )
    op.create_table(
        "brc_trade_aggregates",
        _id("ticket_id", primary_key=True),
        sa.Column("status", SHORT_TEXT, nullable=False),
        sa.Column("version", sa.BigInteger, nullable=False),
        sa.Column("last_event_sequence", sa.BigInteger, nullable=False),
        sa.Column("entry_lane_held", sa.Boolean, nullable=False),
        sa.Column("position_qty", MONEY, nullable=False),
        sa.Column("average_fill_price", MONEY, nullable=True),
        sa.Column("actual_stop_risk", MONEY, nullable=True),
        sa.Column("actual_liquidation_price", MONEY, nullable=True),
        sa.Column("actual_liquidation_distance", MONEY, nullable=True),
        sa.Column(
            "actual_liquidation_distance_to_stop_distance_ratio",
            MONEY,
            nullable=True,
        ),
        sa.Column("post_fill_risk_status", SHORT_TEXT, nullable=True),
        sa.Column("post_fill_disposition", SHORT_TEXT, nullable=True),
        sa.Column("protected_qty", MONEY, nullable=False),
        _id("entry_exchange_order_id", nullable=True),
        _id("initial_stop_exchange_order_id", nullable=True),
        _id("active_stop_exchange_order_id", nullable=True),
        sa.Column("active_stop_price", MONEY, nullable=True),
        _id("tp1_exchange_order_id", nullable=True),
        sa.Column("tp1_target_qty", MONEY, nullable=False),
        sa.Column("tp1_filled_qty", MONEY, nullable=False),
        sa.Column("break_even_floor_price", MONEY, nullable=True),
        _id("pending_replaced_stop_exchange_order_id", nullable=True),
        sa.Column("pending_stop_price", MONEY, nullable=True),
        _time("pending_stop_watermark_ms", nullable=True),
        _time("runner_stop_watermark_ms", nullable=True),
        _id("pending_cancel_exchange_order_id", nullable=True),
        _id("exit_exchange_order_id", nullable=True),
        _id("review_id", nullable=True),
        _time("lifecycle_due_at_ms", nullable=True),
        _time("reconciliation_due_at_ms", nullable=True),
        _time("updated_at_ms"),
        sa.CheckConstraint("version > 0", name="ck_brc_trade_aggregates_version_positive"),
        sa.CheckConstraint(
            "last_event_sequence > 0",
            name="ck_brc_trade_aggregates_sequence_positive",
        ),
        sa.CheckConstraint(
            "position_qty >= 0",
            name="ck_brc_trade_aggregates_position_nonnegative",
        ),
        sa.CheckConstraint(
            "protected_qty >= 0",
            name="ck_brc_trade_aggregates_protection_nonnegative",
        ),
        sa.CheckConstraint(
            "tp1_target_qty >= 0",
            name="ck_brc_trade_aggregates_tp1_target_nonnegative",
        ),
        sa.CheckConstraint(
            "tp1_filled_qty >= 0",
            name="ck_brc_trade_aggregates_tp1_filled_nonnegative",
        ),
    )
    op.create_index(
        "ix_brc_trade_aggregates_lifecycle_due",
        "brc_trade_aggregates",
        ["status", "lifecycle_due_at_ms"],
    )
    op.create_index(
        "ix_brc_trade_aggregates_reconciliation_due",
        "brc_trade_aggregates",
        ["status", "reconciliation_due_at_ms"],
    )
    op.create_table(
        "brc_trade_events",
        _id("event_id", primary_key=True),
        _id("ticket_id"),
        sa.Column("sequence", sa.BigInteger, nullable=False),
        sa.Column("event_type", SHORT_TEXT, nullable=False),
        _json("payload"),
        _time("occurred_at_ms"),
        sa.UniqueConstraint(
            "ticket_id",
            "sequence",
            name="uq_brc_trade_events_ticket_id_sequence",
        ),
    )
    op.create_table(
        "brc_exchange_commands",
        _id("command_id", primary_key=True),
        _id("ticket_id"),
        sa.Column("command_kind", SHORT_TEXT, nullable=False),
        sa.Column("generation", sa.Integer, nullable=False),
        sa.Column("idempotency_key", LONG_TEXT, nullable=False),
        sa.Column("venue_client_order_id", SHORT_TEXT, nullable=True),
        sa.Column("status", SHORT_TEXT, nullable=False),
        sa.Column("quantity", MONEY, nullable=True),
        _json("request_payload"),
        _json("result_payload", nullable=True),
        sa.Column("claim_owner", SHORT_TEXT, nullable=True),
        _time("lease_until_ms", nullable=True),
        _time("created_at_ms"),
        _time("deadline_at_ms"),
        _time("completed_at_ms", nullable=True),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_brc_exchange_commands_idempotency_key",
        ),
        sa.UniqueConstraint(
            "venue_client_order_id",
            name="uq_brc_exchange_commands_venue_client_order_id",
        ),
        sa.UniqueConstraint(
            "ticket_id",
            "command_kind",
            "generation",
            name="uq_brc_exchange_commands_ticket_kind_generation",
        ),
        sa.CheckConstraint(
            "(command_kind = 'set_leverage' AND venue_client_order_id IS NULL) "
            "OR (command_kind <> 'set_leverage' AND venue_client_order_id IS NOT NULL)",
            name="ck_brc_exchange_commands_command_order_identity_shape",
        ),
        sa.CheckConstraint(
            "generation > 0",
            name="ck_brc_exchange_commands_generation_positive",
        ),
        sa.CheckConstraint(
            "quantity IS NULL OR quantity > 0",
            name="ck_brc_exchange_commands_quantity_positive",
        ),
    )
    op.create_table(
        "brc_positions_current",
        sa.Column("netting_domain_key", LONG_TEXT, primary_key=True),
        _id("ticket_id", nullable=True),
        sa.Column("venue_id", SHORT_TEXT, nullable=False),
        _id("account_id"),
        _id("exchange_instrument_id"),
        sa.Column("position_side", SHORT_TEXT, nullable=False),
        sa.Column("quantity", MONEY, nullable=False),
        sa.Column("average_entry_price", MONEY, nullable=True),
        _time("observed_at_ms"),
        sa.Column("projection_version", sa.BigInteger, nullable=False),
        sa.CheckConstraint(
            "quantity >= 0",
            name="ck_brc_positions_current_quantity_nonnegative",
        ),
    )
    op.create_table(
        "brc_budget_reservations",
        _id("budget_reservation_id", primary_key=True),
        _id("ticket_id"),
        _id("owner_policy_id"),
        sa.Column("venue_id", SHORT_TEXT, nullable=False),
        _id("account_id"),
        sa.Column("reserved_notional", MONEY, nullable=False),
        sa.Column("reserved_risk", MONEY, nullable=False),
        sa.Column("reserved_margin", MONEY, nullable=False),
        sa.Column("planned_stop_risk_budget", MONEY, nullable=False),
        sa.Column("risk_reservation_basis", SHORT_TEXT, nullable=False),
        sa.Column("status", SHORT_TEXT, nullable=False),
        _time("created_at_ms"),
        _time("released_at_ms", nullable=True),
        sa.UniqueConstraint(
            "ticket_id",
            name="uq_brc_budget_reservations_ticket_id",
        ),
        sa.CheckConstraint(
            "reserved_notional > 0",
            name="ck_brc_budget_reservations_notional_positive",
        ),
        sa.CheckConstraint(
            "reserved_risk >= 0",
            name="ck_brc_budget_reservations_risk_nonnegative",
        ),
        sa.CheckConstraint(
            "reserved_margin > 0",
            name="ck_brc_budget_reservations_margin_positive",
        ),
    )
    op.create_table(
        "brc_account_exposure_current",
        sa.Column("venue_id", SHORT_TEXT, primary_key=True),
        _id("account_id", primary_key=True),
        sa.Column("gross_notional", MONEY, nullable=False),
        sa.Column("gross_risk_at_stop", MONEY, nullable=False),
        sa.Column("active_ticket_count", sa.Integer, nullable=False),
        sa.Column("projection_version", sa.BigInteger, nullable=False),
        _time("updated_at_ms"),
        sa.CheckConstraint(
            "gross_notional >= 0",
            name="ck_brc_account_exposure_current_notional_nonnegative",
        ),
        sa.CheckConstraint(
            "gross_risk_at_stop >= 0",
            name="ck_brc_account_exposure_current_risk_nonnegative",
        ),
        sa.CheckConstraint(
            "active_ticket_count >= 0",
            name="ck_brc_account_exposure_current_ticket_count_nonnegative",
        ),
    )
    op.create_table(
        "brc_runtime_incidents",
        _id("incident_id", primary_key=True),
        _id("ticket_id", nullable=True),
        sa.Column("incident_kind", SHORT_TEXT, nullable=False),
        sa.Column("status", SHORT_TEXT, nullable=False),
        sa.Column("first_blocker", LONG_TEXT, nullable=False),
        sa.Column("entry_block_scope", SHORT_TEXT, nullable=False),
        sa.Column("entry_block_key", LONG_TEXT, nullable=True),
        _json("details"),
        _time("opened_at_ms"),
        _time("resolved_at_ms", nullable=True),
        sa.CheckConstraint(
            "entry_block_scope IN ('runtime', 'account_capacity', 'leverage_domain', 'none')",
            name="ck_brc_runtime_incidents_entry_block_scope_valid",
        ),
        sa.CheckConstraint(
            "(entry_block_scope = 'runtime' AND entry_block_key = 'global') OR "
            "(entry_block_scope = 'account_capacity' AND entry_block_key ~ '^[^:]+:[^:]+$') OR "
            "(entry_block_scope = 'leverage_domain' AND entry_block_key ~ '^[^:]+:[^:]+:[^:]+$') OR "
            "(entry_block_scope = 'none' AND entry_block_key IS NULL)",
            name="ck_brc_runtime_incidents_entry_block_key_canonical",
        ),
    )
    op.create_table(
        "brc_trade_reviews",
        _id("review_id", primary_key=True),
        _id("ticket_id"),
        sa.Column("outcome", SHORT_TEXT, nullable=False),
        _json("metrics"),
        _json("decision_impact"),
        _time("created_at_ms"),
        sa.UniqueConstraint("ticket_id", name="uq_brc_trade_reviews_ticket_id"),
    )
    op.create_table(
        "brc_monitor_current",
        sa.Column("monitor_key", SHORT_TEXT, primary_key=True),
        sa.Column("owner_status", SHORT_TEXT, nullable=False),
        sa.Column("summary", LONG_TEXT, nullable=False),
        sa.Column("intervention", LONG_TEXT, nullable=False),
        _id("ticket_id", nullable=True),
        _id("incident_id", nullable=True),
        _time("updated_at_ms"),
        sa.Column("projection_version", sa.BigInteger, nullable=False),
    )
    op.create_table(
        "brc_monitor_events",
        _id("monitor_event_id", primary_key=True),
        sa.Column("monitor_key", SHORT_TEXT, nullable=False),
        sa.Column("event_type", SHORT_TEXT, nullable=False),
        _json("payload"),
        _time("created_at_ms"),
    )
    op.create_table(
        "brc_retention_runs",
        _id("retention_run_id", primary_key=True),
        sa.Column("scope", SHORT_TEXT, nullable=False),
        sa.Column("deleted_rows", sa.BigInteger, nullable=False),
        _time("started_at_ms"),
        _time("completed_at_ms"),
    )
    op.create_table(
        "brc_schema_metadata",
        sa.Column("metadata_key", SHORT_TEXT, primary_key=True),
        sa.Column("metadata_value", LONG_TEXT, nullable=False),
        _time("updated_at_ms"),
    )


def downgrade() -> None:
    for table_name in (
        "brc_schema_metadata",
        "brc_retention_runs",
        "brc_monitor_events",
        "brc_monitor_current",
        "brc_trade_reviews",
        "brc_runtime_incidents",
        "brc_account_exposure_current",
        "brc_budget_reservations",
        "brc_positions_current",
        "brc_exchange_commands",
        "brc_trade_events",
        "brc_trade_aggregates",
        "brc_trade_tickets",
        "brc_capacity_claims",
        "brc_runtime_capabilities_current",
        "brc_entry_lane_current",
        "brc_readiness_current",
        "brc_signal_fact_snapshots",
        "brc_signal_events",
        "brc_facts_current",
        "brc_runtime_scopes_current",
        "brc_runtime_profiles",
        "brc_owner_policy_current",
        "brc_owner_policy_events",
        "brc_instrument_rules_current",
        "brc_strategy_candidate_scopes",
        "brc_instruments",
        "brc_event_required_facts",
        "brc_fact_definitions",
        "brc_exit_policies",
        "brc_event_specs",
        "brc_strategy_versions",
        "brc_strategy_groups",
    ):
        op.drop_table(table_name)
