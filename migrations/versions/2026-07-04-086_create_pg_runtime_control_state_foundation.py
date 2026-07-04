"""Create PG runtime control-state foundation tables.

Revision ID: 086
Revises: 085
Create Date: 2026-07-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "086"
down_revision: Union[str, None] = "085"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = (
    "brc_strategy_groups",
    "brc_strategy_group_versions",
    "brc_required_fact_contracts",
    "brc_strategy_side_event_specs",
    "brc_strategy_event_required_facts",
    "brc_strategy_group_candidate_scope",
    "brc_candidate_scope_event_bindings",
    "brc_owner_policy_events",
    "brc_owner_policy_current",
    "brc_runtime_scope_bindings",
    "brc_symbols",
    "brc_exchange_instruments",
    "brc_symbol_instrument_mappings",
    "brc_market_data_sources",
    "brc_candle_snapshots",
    "brc_market_data_quality_events",
    "brc_watcher_runtime_coverage",
    "brc_runtime_fact_snapshots",
    "brc_live_signal_events",
    "brc_pretrade_readiness_rows",
    "brc_promotion_candidates",
    "brc_action_time_lane_inputs",
    "brc_budget_reservations",
    "brc_protection_references",
    "brc_execution_policies",
    "brc_action_time_tickets",
    "brc_action_time_ticket_events",
    "brc_operation_layer_handoffs",
    "brc_state_transition_events",
    "brc_runtime_safety_state_snapshots",
    "brc_projection_runs",
    "brc_current_projection_ownership",
    "brc_legacy_diagnostics",
    "brc_goal_status_current",
    "brc_control_read_model_snapshots",
    "brc_server_monitor_runs",
    "brc_server_monitor_notifications",
    "brc_runtime_incidents",
    "brc_recovery_runs",
    "brc_strategy_intake_cases",
    "brc_strategy_intake_stage_events",
    "brc_strategy_review_outcomes",
    "brc_strategy_governance_decisions",
    "brc_strategy_policy_change_requests",
)


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _json_type() -> sa.types.TypeEngine:
    if str(op.get_bind().dialect.name) == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def _partial_index_kwargs(where_sql: str) -> dict[str, sa.sql.elements.TextClause]:
    return {
        "postgresql_where": sa.text(where_sql),
        "sqlite_where": sa.text(where_sql),
    }


def _create_index(
    name: str,
    table: str,
    columns: list[str],
    *,
    unique: bool = False,
    where: str | None = None,
) -> None:
    kwargs = _partial_index_kwargs(where) if where else {}
    op.create_index(name, table, columns, unique=unique, **kwargs)


def upgrade() -> None:
    json_t = _json_type()

    if not _has_table("brc_strategy_groups"):
        op.create_table(
            "brc_strategy_groups",
            sa.Column("strategy_group_id", sa.String(128), primary_key=True),
            sa.Column("strategy_family_id", sa.String(128), nullable=True),
            sa.Column("current_version_id", sa.String(160), nullable=True),
            sa.Column("owner_label", sa.String(256), nullable=False),
            sa.Column("status", sa.String(64), nullable=False),
            sa.Column("active_wip_slot", sa.String(32), nullable=True),
            sa.Column("default_tier", sa.String(16), nullable=False),
            sa.Column("tradeability_stage", sa.String(64), nullable=False),
            sa.Column("owner_visible", sa.Boolean(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("metadata", json_t, nullable=False, server_default="{}"),
            sa.CheckConstraint(
                "status IN ('intake', 'active', 'paused', 'parked', 'killed', 'retired')",
                name="ck_brc_strategy_groups_status",
            ),
            sa.CheckConstraint(
                "default_tier IN ('L0', 'L1', 'L2', 'L3', 'L4')",
                name="ck_brc_strategy_groups_tier",
            ),
            sa.CheckConstraint(
                "active_wip_slot IS NULL OR active_wip_slot IN "
                "('P0-A', 'P0-B', 'P1-A', 'P1-B', 'P2-A')",
                name="ck_brc_strategy_groups_wip",
            ),
        )
        _create_index(
            "idx_brc_strategy_groups_status",
            "brc_strategy_groups",
            ["status", "updated_at_ms"],
        )
        _create_index(
            "idx_brc_strategy_groups_wip",
            "brc_strategy_groups",
            ["active_wip_slot"],
        )

    if not _has_table("brc_strategy_group_versions"):
        op.create_table(
            "brc_strategy_group_versions",
            sa.Column("strategy_group_version_id", sa.String(160), primary_key=True),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(64), nullable=False),
            sa.Column("edge_thesis", sa.Text(), nullable=False),
            sa.Column("trade_logic", sa.Text(), nullable=False),
            sa.Column("regime_fit", sa.Text(), nullable=False),
            sa.Column("supported_sides", json_t, nullable=False, server_default="[]"),
            sa.Column("supported_timeframes", json_t, nullable=False, server_default="[]"),
            sa.Column("risk_envelope", json_t, nullable=False, server_default="{}"),
            sa.Column("promotion_rules", json_t, nullable=False, server_default="{}"),
            sa.Column("evidence_refs", json_t, nullable=False, server_default="[]"),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("created_by", sa.String(128), nullable=False),
            sa.CheckConstraint(
                "status IN ('draft', 'current', 'superseded', 'retired')",
                name="ck_brc_strategy_group_versions_status",
            ),
            sa.CheckConstraint("version > 0", name="ck_brc_strategy_group_versions_ver"),
            sa.UniqueConstraint(
                "strategy_group_id",
                "version",
                name="uq_brc_strategy_group_versions_group_ver",
            ),
        )
        _create_index(
            "uq_brc_strategy_group_versions_current",
            "brc_strategy_group_versions",
            ["strategy_group_id"],
            unique=True,
            where="status = 'current'",
        )
        _create_index(
            "idx_brc_strategy_group_versions_group",
            "brc_strategy_group_versions",
            ["strategy_group_id", "status"],
        )

    if not _has_table("brc_required_fact_contracts"):
        op.create_table(
            "brc_required_fact_contracts",
            sa.Column("fact_contract_id", sa.String(160), primary_key=True),
            sa.Column("strategy_group_version_id", sa.String(160), nullable=False),
            sa.Column("fact_key", sa.String(128), nullable=False),
            sa.Column("fact_group", sa.String(64), nullable=False),
            sa.Column("required_surface", sa.String(64), nullable=False),
            sa.Column("source_kind", sa.String(64), nullable=False),
            sa.Column("freshness_ms", sa.BIGINT(), nullable=True),
            sa.Column("missing_blocker_class", sa.String(128), nullable=False),
            sa.Column("failed_blocker_class", sa.String(128), nullable=False),
            sa.Column("required_for_live_submit", sa.Boolean(), nullable=False),
            sa.Column("definition_payload", json_t, nullable=False, server_default="{}"),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "fact_group IN ('market', 'strategy', 'derivatives', 'risk', "
                "'account', 'exchange', 'protection')",
                name="ck_brc_required_fact_contracts_group",
            ),
            sa.CheckConstraint(
                "required_surface IN ('pretrade', 'action_time', 'finalgate', "
                "'operation_layer', 'review')",
                name="ck_brc_required_fact_contracts_surface",
            ),
            sa.CheckConstraint(
                "source_kind IN ('public_market', 'account_safe', 'watcher', "
                "'exchange_metadata', 'derived')",
                name="ck_brc_required_fact_contracts_source",
            ),
            sa.CheckConstraint(
                "fact_key NOT LIKE '%explicit_not_required_for_v0%'",
                name="ck_brc_required_fact_contracts_no_v0_text",
            ),
            sa.UniqueConstraint(
                "strategy_group_version_id",
                "fact_key",
                "required_surface",
                name="uq_brc_required_fact_contracts_ver_key_surface",
            ),
        )
        _create_index(
            "idx_brc_required_fact_contracts_surface",
            "brc_required_fact_contracts",
            ["required_surface", "fact_group"],
        )

    if not _has_table("brc_strategy_side_event_specs"):
        op.create_table(
            "brc_strategy_side_event_specs",
            sa.Column("event_spec_id", sa.String(160), primary_key=True),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("strategy_group_version_id", sa.String(160), nullable=False),
            sa.Column("event_id", sa.String(128), nullable=False),
            sa.Column("side", sa.String(32), nullable=False),
            sa.Column("timeframe", sa.String(32), nullable=False),
            sa.Column("event_spec_version", sa.String(64), nullable=False),
            sa.Column("status", sa.String(64), nullable=False),
            sa.Column("freshness_window_ms", sa.BIGINT(), nullable=False),
            sa.Column("time_authority", sa.String(96), nullable=False),
            sa.Column("protection_ref_type", sa.String(96), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("created_by", sa.String(128), nullable=False),
            sa.CheckConstraint("side IN ('long', 'short')", name="ck_brc_event_specs_side"),
            sa.CheckConstraint(
                "status IN ('current', 'retired', 'disabled')",
                name="ck_brc_event_specs_status",
            ),
            sa.CheckConstraint(
                "freshness_window_ms > 0",
                name="ck_brc_event_specs_freshness_pos",
            ),
            sa.UniqueConstraint(
                "strategy_group_id",
                "side",
                "event_id",
                "event_spec_version",
                name="uq_brc_event_specs_group_side_event_ver",
            ),
        )
        _create_index(
            "idx_brc_event_specs_group_status",
            "brc_strategy_side_event_specs",
            ["strategy_group_id", "status"],
        )
        _create_index(
            "uq_brc_event_specs_current",
            "brc_strategy_side_event_specs",
            ["strategy_group_id", "side", "event_id"],
            unique=True,
            where="status = 'current'",
        )

    if not _has_table("brc_strategy_event_required_facts"):
        op.create_table(
            "brc_strategy_event_required_facts",
            sa.Column("event_required_fact_id", sa.String(192), primary_key=True),
            sa.Column("event_spec_id", sa.String(160), nullable=False),
            sa.Column("required_facts_version_id", sa.String(160), nullable=False),
            sa.Column("fact_key", sa.String(128), nullable=False),
            sa.Column("fact_role", sa.String(64), nullable=False),
            sa.Column("fact_surface", sa.String(64), nullable=False),
            sa.Column("operator", sa.String(32), nullable=False),
            sa.Column("expected_value", json_t, nullable=True),
            sa.Column("value_source", sa.String(128), nullable=False),
            sa.Column("disable_on_match", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("missing_blocker_class", sa.String(128), nullable=False),
            sa.Column("failed_blocker_class", sa.String(128), nullable=False),
            sa.Column("freshness_ms", sa.BIGINT(), nullable=True),
            sa.Column("required_for_promotion", sa.Boolean(), nullable=False),
            sa.Column("required_for_ticket", sa.Boolean(), nullable=False),
            sa.Column("required_for_finalgate", sa.Boolean(), nullable=False),
            sa.Column("status", sa.String(64), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "operator IN ('eq', 'neq', 'gte', 'lte', 'gt', 'lt', 'in', "
                "'not_in', 'exists', 'not_exists', 'expr_ref')",
                name="ck_brc_event_req_facts_operator",
            ),
            sa.CheckConstraint(
                "status IN ('current', 'retired', 'disabled')",
                name="ck_brc_event_req_facts_status",
            ),
            sa.CheckConstraint(
                "disable_on_match = false OR failed_blocker_class <> ''",
                name="ck_brc_event_req_facts_disable_shape",
            ),
            sa.CheckConstraint(
                "fact_key NOT LIKE '%explicit_not_required_for_v0%' "
                "AND value_source NOT LIKE '%explicit_not_required_for_v0%'",
                name="ck_brc_event_req_facts_no_v0_text",
            ),
            sa.UniqueConstraint(
                "event_spec_id",
                "required_facts_version_id",
                "fact_key",
                "fact_surface",
                name="uq_brc_event_req_facts_ver_key_surface",
            ),
        )
        _create_index(
            "idx_brc_event_req_facts_spec",
            "brc_strategy_event_required_facts",
            ["event_spec_id", "status"],
        )

    if not _has_table("brc_strategy_group_candidate_scope"):
        op.create_table(
            "brc_strategy_group_candidate_scope",
            sa.Column("candidate_scope_id", sa.String(160), primary_key=True),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("symbol", sa.String(128), nullable=False),
            sa.Column("exchange_symbol", sa.String(128), nullable=True),
            sa.Column("asset_class", sa.String(64), nullable=False),
            sa.Column("side", sa.String(32), nullable=False),
            sa.Column("timeframe", sa.String(32), nullable=True),
            sa.Column("candidate_role", sa.String(32), nullable=False),
            sa.Column("observation_scope", sa.String(32), nullable=False),
            sa.Column("scope_state", sa.String(64), nullable=False),
            sa.Column("priority_rank", sa.Integer(), nullable=False),
            sa.Column("policy_current_id", sa.String(160), nullable=True),
            sa.Column("status", sa.String(64), nullable=False),
            sa.Column("valid_from_ms", sa.BIGINT(), nullable=False),
            sa.Column("valid_until_ms", sa.BIGINT(), nullable=True),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("metadata", json_t, nullable=False, server_default="{}"),
            sa.CheckConstraint("side IN ('long', 'short')", name="ck_brc_candidate_scope_side"),
            sa.CheckConstraint(
                "status IN ('active', 'paused', 'parked', 'revoked')",
                name="ck_brc_candidate_scope_status",
            ),
        )
        _create_index(
            "uq_brc_candidate_scope_active",
            "brc_strategy_group_candidate_scope",
            ["strategy_group_id", "symbol", "side"],
            unique=True,
            where="status = 'active'",
        )
        _create_index(
            "idx_brc_candidate_scope_group_rank",
            "brc_strategy_group_candidate_scope",
            ["strategy_group_id", "priority_rank"],
        )

    if not _has_table("brc_candidate_scope_event_bindings"):
        op.create_table(
            "brc_candidate_scope_event_bindings",
            sa.Column("binding_id", sa.String(192), primary_key=True),
            sa.Column("candidate_scope_id", sa.String(160), nullable=False),
            sa.Column("event_spec_id", sa.String(160), nullable=False),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("symbol", sa.String(128), nullable=False),
            sa.Column("side", sa.String(32), nullable=False),
            sa.Column("status", sa.String(64), nullable=False),
            sa.Column("valid_from_ms", sa.BIGINT(), nullable=False),
            sa.Column("valid_until_ms", sa.BIGINT(), nullable=True),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint("side IN ('long', 'short')", name="ck_brc_scope_event_side"),
            sa.CheckConstraint(
                "status IN ('active', 'paused', 'revoked')",
                name="ck_brc_scope_event_status",
            ),
        )
        _create_index(
            "uq_brc_scope_event_active",
            "brc_candidate_scope_event_bindings",
            ["candidate_scope_id", "event_spec_id"],
            unique=True,
            where="status = 'active'",
        )

    if not _has_table("brc_owner_policy_events"):
        op.create_table(
            "brc_owner_policy_events",
            sa.Column("policy_event_id", sa.String(192), primary_key=True),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("symbol", sa.String(128), nullable=True),
            sa.Column("side", sa.String(32), nullable=True),
            sa.Column("event_type", sa.String(96), nullable=False),
            sa.Column("policy_version", sa.String(96), nullable=False),
            sa.Column("payload", json_t, nullable=False, server_default="{}"),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("created_by", sa.String(128), nullable=False),
            sa.CheckConstraint(
                "side IS NULL OR side IN ('long', 'short')",
                name="ck_brc_owner_policy_events_side",
            ),
        )
        _create_index(
            "idx_brc_owner_policy_events_scope_time",
            "brc_owner_policy_events",
            ["strategy_group_id", "symbol", "side", "created_at_ms"],
        )

    if not _has_table("brc_owner_policy_current"):
        op.create_table(
            "brc_owner_policy_current",
            sa.Column("policy_current_id", sa.String(160), primary_key=True),
            sa.Column("scope_key", sa.String(256), nullable=False),
            sa.Column("scope_level", sa.String(32), nullable=False),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("symbol", sa.String(128), nullable=True),
            sa.Column("side", sa.String(32), nullable=True),
            sa.Column("enabled_state", sa.String(64), nullable=False),
            sa.Column("tier", sa.String(16), nullable=False),
            sa.Column("runtime_profile_id", sa.String(128), nullable=True),
            sa.Column("pretrade_candidate_allowed", sa.Boolean(), nullable=False),
            sa.Column("action_time_rehearsal_allowed", sa.Boolean(), nullable=False),
            sa.Column("live_submit_allowed", sa.String(64), nullable=False),
            sa.Column("max_notional", sa.Numeric(36, 18), nullable=True),
            sa.Column("leverage", sa.Numeric(18, 8), nullable=True),
            sa.Column("attempt_cap", sa.Integer(), nullable=True),
            sa.Column("loss_unit", sa.Numeric(36, 18), nullable=True),
            sa.Column("policy_event_ids", json_t, nullable=False, server_default="[]"),
            sa.Column("valid_from_ms", sa.BIGINT(), nullable=False),
            sa.Column("valid_until_ms", sa.BIGINT(), nullable=True),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "scope_level IN ('group', 'symbol', 'side')",
                name="ck_brc_owner_policy_current_scope",
            ),
            sa.CheckConstraint(
                "live_submit_allowed IN ('none', 'scoped', 'conditional_hard_gated')",
                name="ck_brc_owner_policy_current_submit",
            ),
            sa.CheckConstraint(
                "enabled_state IN ('not_enabled', 'enabled', 'paused', 'parked', 'killed')",
                name="ck_brc_owner_policy_current_enabled",
            ),
            sa.CheckConstraint(
                "tier IN ('L0', 'L1', 'L2', 'L3', 'L4')",
                name="ck_brc_owner_policy_current_tier",
            ),
            sa.CheckConstraint(
                "(scope_level = 'group' AND symbol IS NULL AND side IS NULL) OR "
                "(scope_level = 'symbol' AND symbol IS NOT NULL AND side IS NULL) OR "
                "(scope_level = 'side' AND symbol IS NOT NULL AND side IS NOT NULL)",
                name="ck_brc_owner_policy_current_shape",
            ),
            sa.UniqueConstraint("scope_key", name="uq_brc_owner_policy_scope_key"),
        )
        _create_index(
            "idx_brc_owner_policy_current_enabled",
            "brc_owner_policy_current",
            ["enabled_state", "tier"],
        )

    if not _has_table("brc_runtime_scope_bindings"):
        op.create_table(
            "brc_runtime_scope_bindings",
            sa.Column("runtime_scope_binding_id", sa.String(160), primary_key=True),
            sa.Column("candidate_scope_id", sa.String(160), nullable=False),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("symbol", sa.String(128), nullable=False),
            sa.Column("side", sa.String(32), nullable=False),
            sa.Column("runtime_profile_id", sa.String(128), nullable=False),
            sa.Column("selected_strategygroup_scope", sa.Boolean(), nullable=False),
            sa.Column("symbol_side_scope_closed", sa.Boolean(), nullable=False),
            sa.Column("notional_leverage_scope_closed", sa.Boolean(), nullable=False),
            sa.Column("server_runtime_coverage_required", sa.Boolean(), nullable=False),
            sa.Column("live_submit_allowed", sa.Boolean(), nullable=False),
            sa.Column("conditional_hard_gates", json_t, nullable=False, server_default="[]"),
            sa.Column("policy_current_id", sa.String(160), nullable=False),
            sa.Column("status", sa.String(64), nullable=False),
            sa.Column("valid_from_ms", sa.BIGINT(), nullable=False),
            sa.Column("valid_until_ms", sa.BIGINT(), nullable=True),
            sa.Column("authority_boundary", sa.Text(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint("side IN ('long', 'short')", name="ck_brc_runtime_scope_side"),
            sa.CheckConstraint(
                "status IN ('active', 'paused', 'revoked', 'expired')",
                name="ck_brc_runtime_scope_status",
            ),
            sa.CheckConstraint(
                "live_submit_allowed = false OR "
                "(selected_strategygroup_scope = true "
                "AND symbol_side_scope_closed = true "
                "AND notional_leverage_scope_closed = true)",
                name="ck_brc_runtime_scope_live_submit_scope",
            ),
        )
        _create_index(
            "uq_brc_runtime_scope_active",
            "brc_runtime_scope_bindings",
            ["strategy_group_id", "symbol", "side", "runtime_profile_id"],
            unique=True,
            where="status = 'active'",
        )

    if not _has_table("brc_symbols"):
        op.create_table(
            "brc_symbols",
            sa.Column("symbol", sa.String(128), primary_key=True),
            sa.Column("asset_class", sa.String(64), nullable=False),
            sa.Column("status", sa.String(64), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "status IN ('active', 'disabled', 'retired')",
                name="ck_brc_symbols_status",
            ),
        )

    if not _has_table("brc_exchange_instruments"):
        op.create_table(
            "brc_exchange_instruments",
            sa.Column("exchange_instrument_id", sa.String(192), primary_key=True),
            sa.Column("exchange_id", sa.String(64), nullable=False),
            sa.Column("exchange_symbol", sa.String(128), nullable=False),
            sa.Column("asset_class", sa.String(64), nullable=False),
            sa.Column("price_tick", sa.Numeric(36, 18), nullable=True),
            sa.Column("quantity_step", sa.Numeric(36, 18), nullable=True),
            sa.Column("min_notional", sa.Numeric(36, 18), nullable=True),
            sa.Column("status", sa.String(64), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.UniqueConstraint(
                "exchange_id",
                "exchange_symbol",
                name="uq_brc_exchange_instruments_symbol",
            ),
        )

    if not _has_table("brc_symbol_instrument_mappings"):
        op.create_table(
            "brc_symbol_instrument_mappings",
            sa.Column("mapping_id", sa.String(192), primary_key=True),
            sa.Column("symbol", sa.String(128), nullable=False),
            sa.Column("exchange_instrument_id", sa.String(192), nullable=False),
            sa.Column("status", sa.String(64), nullable=False),
            sa.Column("valid_from_ms", sa.BIGINT(), nullable=False),
            sa.Column("valid_until_ms", sa.BIGINT(), nullable=True),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "status IN ('active', 'disabled', 'retired')",
                name="ck_brc_symbol_mapping_status",
            ),
        )
        _create_index(
            "uq_brc_symbol_mapping_active",
            "brc_symbol_instrument_mappings",
            ["symbol"],
            unique=True,
            where="status = 'active'",
        )

    if not _has_table("brc_market_data_sources"):
        op.create_table(
            "brc_market_data_sources",
            sa.Column("market_data_source_id", sa.String(128), primary_key=True),
            sa.Column("source_kind", sa.String(64), nullable=False),
            sa.Column("exchange_id", sa.String(64), nullable=False),
            sa.Column("status", sa.String(64), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        )

    if not _has_table("brc_candle_snapshots"):
        op.create_table(
            "brc_candle_snapshots",
            sa.Column("candle_snapshot_id", sa.String(192), primary_key=True),
            sa.Column("exchange_instrument_id", sa.String(192), nullable=False),
            sa.Column("timeframe", sa.String(32), nullable=False),
            sa.Column("trigger_candle_open_time_ms", sa.BIGINT(), nullable=False),
            sa.Column("trigger_candle_close_time_ms", sa.BIGINT(), nullable=False),
            sa.Column("market_data_source_id", sa.String(128), nullable=False),
            sa.Column("ohlcv", json_t, nullable=False, server_default="{}"),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "trigger_candle_close_time_ms > trigger_candle_open_time_ms",
                name="ck_brc_candle_times_ordered",
            ),
            sa.UniqueConstraint(
                "exchange_instrument_id",
                "timeframe",
                "trigger_candle_open_time_ms",
                "market_data_source_id",
                name="uq_brc_candle_identity",
            ),
        )

    if not _has_table("brc_market_data_quality_events"):
        op.create_table(
            "brc_market_data_quality_events",
            sa.Column("quality_event_id", sa.String(192), primary_key=True),
            sa.Column("market_data_source_id", sa.String(128), nullable=False),
            sa.Column("exchange_instrument_id", sa.String(192), nullable=True),
            sa.Column("symbol", sa.String(128), nullable=True),
            sa.Column("timeframe", sa.String(32), nullable=True),
            sa.Column("quality_event_type", sa.String(96), nullable=False),
            sa.Column("severity", sa.String(32), nullable=False),
            sa.Column("observed_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("valid_until_ms", sa.BIGINT(), nullable=True),
            sa.Column("details", json_t, nullable=False, server_default="{}"),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "quality_event_type IN ('data_gap', 'stale', 'clock_skew', "
                "'source_conflict', 'precision_mismatch')",
                name="ck_brc_market_quality_type",
            ),
            sa.CheckConstraint(
                "severity IN ('info', 'warning', 'blocking')",
                name="ck_brc_market_quality_severity",
            ),
        )
        _create_index(
            "idx_brc_market_quality_scope_time",
            "brc_market_data_quality_events",
            ["symbol", "timeframe", "observed_at_ms"],
        )

    if not _has_table("brc_watcher_runtime_coverage"):
        op.create_table(
            "brc_watcher_runtime_coverage",
            sa.Column("runtime_coverage_id", sa.String(192), primary_key=True),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("symbol", sa.String(128), nullable=False),
            sa.Column("side", sa.String(32), nullable=False),
            sa.Column("detector_key", sa.String(128), nullable=False),
            sa.Column("runtime_profile_id", sa.String(128), nullable=True),
            sa.Column("coverage_state", sa.String(64), nullable=False),
            sa.Column("liveness_state", sa.String(64), nullable=False),
            sa.Column("last_tick_at_ms", sa.BIGINT(), nullable=True),
            sa.Column("valid_until_ms", sa.BIGINT(), nullable=True),
            sa.Column("is_current", sa.Boolean(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint("side IN ('long', 'short')", name="ck_brc_coverage_side"),
            sa.CheckConstraint(
                "coverage_state IN ('covered', 'not_covered', 'stale', 'missing', 'disabled')",
                name="ck_brc_coverage_state",
            ),
        )
        _create_index(
            "uq_brc_coverage_current",
            "brc_watcher_runtime_coverage",
            ["strategy_group_id", "symbol", "side", "detector_key"],
            unique=True,
            where="is_current = true",
        )

    if not _has_table("brc_runtime_fact_snapshots"):
        op.create_table(
            "brc_runtime_fact_snapshots",
            sa.Column("fact_snapshot_id", sa.String(192), primary_key=True),
            sa.Column("strategy_group_id", sa.String(128), nullable=True),
            sa.Column("symbol", sa.String(128), nullable=True),
            sa.Column("side", sa.String(32), nullable=True),
            sa.Column("runtime_profile_id", sa.String(128), nullable=True),
            sa.Column("fact_surface", sa.String(64), nullable=False),
            sa.Column("source_kind", sa.String(64), nullable=False),
            sa.Column("source_ref", sa.String(512), nullable=True),
            sa.Column("computed", sa.Boolean(), nullable=False),
            sa.Column("satisfied", sa.Boolean(), nullable=True),
            sa.Column("freshness_state", sa.String(64), nullable=False),
            sa.Column("failed_facts", json_t, nullable=False, server_default="[]"),
            sa.Column("fact_values", json_t, nullable=False, server_default="{}"),
            sa.Column("blocker_class", sa.String(128), nullable=True),
            sa.Column("observed_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("valid_until_ms", sa.BIGINT(), nullable=True),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "freshness_state IN ('fresh', 'stale', 'missing', 'unknown')",
                name="ck_brc_fact_snapshots_freshness",
            ),
        )

    if not _has_table("brc_live_signal_events"):
        op.create_table(
            "brc_live_signal_events",
            sa.Column("signal_event_id", sa.String(192), primary_key=True),
            sa.Column("candidate_scope_id", sa.String(160), nullable=True),
            sa.Column("event_spec_id", sa.String(160), nullable=False),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("symbol", sa.String(128), nullable=False),
            sa.Column("side", sa.String(32), nullable=False),
            sa.Column("detector_key", sa.String(128), nullable=False),
            sa.Column("signal_type", sa.String(64), nullable=False),
            sa.Column("status", sa.String(64), nullable=False),
            sa.Column("freshness_state", sa.String(64), nullable=False),
            sa.Column("confidence", sa.Numeric(18, 8), nullable=True),
            sa.Column("fact_snapshot_id", sa.String(192), nullable=True),
            sa.Column("reason_codes", json_t, nullable=False, server_default="[]"),
            sa.Column("signal_payload", json_t, nullable=False, server_default="{}"),
            sa.Column("observed_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("expires_at_ms", sa.BIGINT(), nullable=True),
            sa.Column("invalidated_at_ms", sa.BIGINT(), nullable=True),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint("side IN ('long', 'short')", name="ck_brc_live_signal_side"),
            sa.CheckConstraint(
                "status IN ('detected', 'facts_validated', 'stale', 'rejected', 'superseded')",
                name="ck_brc_live_signal_status",
            ),
            sa.CheckConstraint(
                "freshness_state IN ('fresh', 'stale', 'expired', 'unknown')",
                name="ck_brc_live_signal_freshness",
            ),
            sa.CheckConstraint(
                "freshness_state <> 'fresh' OR (status = 'facts_validated' AND expires_at_ms IS NOT NULL)",
                name="ck_brc_live_signal_fresh_valid",
            ),
            sa.UniqueConstraint(
                "strategy_group_id",
                "symbol",
                "side",
                "detector_key",
                "signal_type",
                "observed_at_ms",
                name="uq_brc_live_signal_identity",
            ),
        )

    if not _has_table("brc_pretrade_readiness_rows"):
        op.create_table(
            "brc_pretrade_readiness_rows",
            sa.Column("readiness_row_id", sa.String(192), primary_key=True),
            sa.Column("candidate_scope_id", sa.String(160), nullable=True),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("symbol", sa.String(128), nullable=False),
            sa.Column("side", sa.String(32), nullable=False),
            sa.Column("readiness_state", sa.String(64), nullable=False),
            sa.Column("detector_state", sa.String(64), nullable=False),
            sa.Column("watcher_state", sa.String(64), nullable=False),
            sa.Column("public_facts_state", sa.String(64), nullable=False),
            sa.Column("signal_lifecycle_status", sa.String(64), nullable=False),
            sa.Column("signal_freshness_state", sa.String(64), nullable=False),
            sa.Column("risk_state", sa.String(64), nullable=False),
            sa.Column("scope_state", sa.String(64), nullable=False),
            sa.Column("promotion_state", sa.String(64), nullable=False),
            sa.Column("first_blocker_class", sa.String(128), nullable=False),
            sa.Column("first_blocker_detail", sa.Text(), nullable=False),
            sa.Column("next_action", sa.Text(), nullable=False),
            sa.Column("stop_condition", sa.Text(), nullable=False),
            sa.Column("evidence_ref", sa.String(512), nullable=True),
            sa.Column("source_watermark", sa.String(256), nullable=True),
            sa.Column("computed_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("valid_until_ms", sa.BIGINT(), nullable=True),
            sa.CheckConstraint("side IN ('long', 'short')", name="ck_brc_readiness_side"),
            sa.UniqueConstraint(
                "strategy_group_id",
                "symbol",
                "side",
                name="uq_brc_readiness_current_scope",
            ),
        )

    if not _has_table("brc_promotion_candidates"):
        op.create_table(
            "brc_promotion_candidates",
            sa.Column("promotion_candidate_id", sa.String(192), primary_key=True),
            sa.Column("signal_event_id", sa.String(192), nullable=False),
            sa.Column("readiness_row_id", sa.String(192), nullable=False),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("symbol", sa.String(128), nullable=False),
            sa.Column("side", sa.String(32), nullable=False),
            sa.Column("promotion_scope", sa.String(64), nullable=False),
            sa.Column("status", sa.String(64), nullable=False),
            sa.Column("scope_state", sa.String(64), nullable=False),
            sa.Column("risk_state", sa.String(64), nullable=False),
            sa.Column("facts_snapshot_id", sa.String(192), nullable=True),
            sa.Column("blockers", json_t, nullable=False, server_default="[]"),
            sa.Column("arbitration_rank", sa.Integer(), nullable=True),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("expires_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("closed_at_ms", sa.BIGINT(), nullable=True),
            sa.Column("authority_boundary", sa.Text(), nullable=False),
            sa.CheckConstraint("side IN ('long', 'short')", name="ck_brc_promotion_side"),
            sa.CheckConstraint(
                "status IN ('eligible', 'blocked', 'arbitration_pending', "
                "'arbitration_won', 'arbitration_lost', 'expired')",
                name="ck_brc_promotion_status",
            ),
        )

    if not _has_table("brc_action_time_lane_inputs"):
        op.create_table(
            "brc_action_time_lane_inputs",
            sa.Column("action_time_lane_input_id", sa.String(192), primary_key=True),
            sa.Column("promotion_candidate_id", sa.String(192), nullable=False),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("symbol", sa.String(128), nullable=False),
            sa.Column("side", sa.String(32), nullable=False),
            sa.Column("runtime_profile_id", sa.String(128), nullable=False),
            sa.Column("lane_scope", sa.String(64), nullable=False),
            sa.Column("status", sa.String(64), nullable=False),
            sa.Column("signal_event_id", sa.String(192), nullable=True),
            sa.Column("public_fact_snapshot_id", sa.String(192), nullable=True),
            sa.Column("action_time_fact_snapshot_id", sa.String(192), nullable=True),
            sa.Column("runtime_scope_binding_id", sa.String(160), nullable=False),
            sa.Column("candidate_authorization_ref", sa.String(256), nullable=True),
            sa.Column("runtime_safety_snapshot_id", sa.String(192), nullable=True),
            sa.Column("first_blocker_class", sa.String(128), nullable=True),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("expires_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("closed_at_ms", sa.BIGINT(), nullable=True),
            sa.Column("authority_boundary", sa.Text(), nullable=False),
            sa.CheckConstraint("side IN ('long', 'short')", name="ck_brc_lane_side"),
            sa.CheckConstraint(
                "lane_scope IN ('rehearsal', 'paper', 'conditional_rehearsal', 'real_submit_candidate')",
                name="ck_brc_lane_scope",
            ),
            sa.CheckConstraint(
                "status IN ('opened', 'facts_refreshing', 'ticket_pending', "
                "'ticket_created', 'closed', 'expired', 'invalidated')",
                name="ck_brc_lane_status",
            ),
        )
        _create_index(
            "uq_brc_lane_single_open_real",
            "brc_action_time_lane_inputs",
            ["lane_scope"],
            unique=True,
            where=(
                "lane_scope = 'real_submit_candidate' AND status IN "
                "('opened', 'facts_refreshing', 'ticket_pending', 'ticket_created')"
            ),
        )

    if not _has_table("brc_budget_reservations"):
        op.create_table(
            "brc_budget_reservations",
            sa.Column("budget_reservation_id", sa.String(192), primary_key=True),
            sa.Column("promotion_candidate_id", sa.String(192), nullable=False),
            sa.Column("action_time_lane_input_id", sa.String(192), nullable=False),
            sa.Column("ticket_id", sa.String(192), nullable=True),
            sa.Column("signal_event_id", sa.String(192), nullable=False),
            sa.Column("event_spec_id", sa.String(160), nullable=False),
            sa.Column("runtime_profile_id", sa.String(128), nullable=False),
            sa.Column("account_id", sa.String(128), nullable=False),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("symbol", sa.String(128), nullable=False),
            sa.Column("side", sa.String(32), nullable=False),
            sa.Column("target_notional", sa.Numeric(36, 18), nullable=False),
            sa.Column("leverage", sa.Numeric(18, 8), nullable=False),
            sa.Column("reserved_margin", sa.Numeric(36, 18), nullable=False),
            sa.Column("reserved_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("expires_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("status", sa.String(64), nullable=False),
            sa.Column("release_reason", sa.Text(), nullable=True),
            sa.Column("policy_version", sa.String(96), nullable=False),
            sa.CheckConstraint("side IN ('long', 'short')", name="ck_brc_budget_res_side"),
            sa.CheckConstraint(
                "status IN ('active', 'consumed', 'released', 'expired', 'invalidated')",
                name="ck_brc_budget_res_status",
            ),
            sa.CheckConstraint(
                "expires_at_ms > reserved_at_ms",
                name="ck_brc_budget_res_expiry",
            ),
            sa.CheckConstraint(
                "target_notional > 0 AND leverage > 0 AND reserved_margin >= 0",
                name="ck_brc_budget_res_amounts",
            ),
        )
        _create_index(
            "uq_brc_budget_res_active_lane",
            "brc_budget_reservations",
            ["action_time_lane_input_id"],
            unique=True,
            where="status = 'active'",
        )
        _create_index(
            "uq_brc_budget_res_ticket",
            "brc_budget_reservations",
            ["ticket_id"],
            unique=True,
            where="ticket_id IS NOT NULL",
        )

    if not _has_table("brc_protection_references"):
        op.create_table(
            "brc_protection_references",
            sa.Column("protection_ref_id", sa.String(192), primary_key=True),
            sa.Column("event_spec_id", sa.String(160), nullable=False),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("symbol", sa.String(128), nullable=False),
            sa.Column("side", sa.String(32), nullable=False),
            sa.Column("reference_type", sa.String(96), nullable=False),
            sa.Column("reference_price", sa.Numeric(36, 18), nullable=False),
            sa.Column("invalidation_condition", sa.Text(), nullable=False),
            sa.Column("stop_order_type", sa.String(64), nullable=False),
            sa.Column("stop_time_in_force", sa.String(64), nullable=False),
            sa.Column("protection_policy_version", sa.String(96), nullable=False),
            sa.Column("source_fact_snapshot_id", sa.String(192), nullable=False),
            sa.Column("expires_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint("side IN ('long', 'short')", name="ck_brc_protection_side"),
        )

    if not _has_table("brc_execution_policies"):
        op.create_table(
            "brc_execution_policies",
            sa.Column("execution_policy_id", sa.String(192), primary_key=True),
            sa.Column("execution_policy_version", sa.String(96), nullable=False),
            sa.Column("runtime_profile_id", sa.String(128), nullable=False),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("event_spec_id", sa.String(160), nullable=False),
            sa.Column("side", sa.String(32), nullable=False),
            sa.Column("order_type", sa.String(64), nullable=False),
            sa.Column("time_in_force", sa.String(64), nullable=False),
            sa.Column("reduce_only", sa.Boolean(), nullable=False),
            sa.Column("post_only", sa.Boolean(), nullable=False),
            sa.Column("close_position", sa.Boolean(), nullable=False),
            sa.Column("allowed_slippage_bps", sa.Numeric(18, 8), nullable=False),
            sa.Column("price_protection_mode", sa.String(64), nullable=False),
            sa.Column("submit_deadline_ms", sa.BIGINT(), nullable=False),
            sa.Column("cancel_if_not_filled_policy", json_t, nullable=False, server_default="{}"),
            sa.Column("status", sa.String(64), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("created_by", sa.String(128), nullable=False),
            sa.CheckConstraint("side IN ('long', 'short')", name="ck_brc_exec_policy_side"),
            sa.CheckConstraint(
                "order_type IN ('market', 'limit', 'post_only_limit')",
                name="ck_brc_exec_policy_order_type",
            ),
            sa.CheckConstraint(
                "time_in_force IN ('GTC', 'IOC', 'FOK', 'GTX')",
                name="ck_brc_exec_policy_tif",
            ),
            sa.CheckConstraint(
                "status IN ('current', 'retired', 'disabled')",
                name="ck_brc_exec_policy_status",
            ),
            sa.CheckConstraint(
                "allowed_slippage_bps >= 0 AND submit_deadline_ms > 0",
                name="ck_brc_exec_policy_bounds",
            ),
        )
        _create_index(
            "uq_brc_exec_policy_current",
            "brc_execution_policies",
            ["runtime_profile_id", "strategy_group_id", "event_spec_id", "side"],
            unique=True,
            where="status = 'current'",
        )
        _create_index(
            "idx_brc_exec_policy_profile",
            "brc_execution_policies",
            ["runtime_profile_id", "status"],
        )

    if not _has_table("brc_action_time_tickets"):
        op.create_table(
            "brc_action_time_tickets",
            sa.Column("ticket_id", sa.String(192), primary_key=True),
            sa.Column("action_time_lane_input_id", sa.String(192), nullable=False),
            sa.Column("promotion_candidate_id", sa.String(192), nullable=False),
            sa.Column("signal_event_id", sa.String(192), nullable=False),
            sa.Column("event_spec_id", sa.String(160), nullable=False),
            sa.Column("event_spec_version_id", sa.String(160), nullable=False),
            sa.Column("candidate_scope_id", sa.String(160), nullable=False),
            sa.Column("runtime_scope_binding_id", sa.String(160), nullable=False),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("strategy_group_version_id", sa.String(160), nullable=False),
            sa.Column("symbol", sa.String(128), nullable=False),
            sa.Column("exchange_instrument_id", sa.String(192), nullable=False),
            sa.Column("side", sa.String(32), nullable=False),
            sa.Column("event_id", sa.String(128), nullable=False),
            sa.Column("event_time_ms", sa.BIGINT(), nullable=False),
            sa.Column("trigger_candle_close_time_ms", sa.BIGINT(), nullable=False),
            sa.Column("runtime_profile_id", sa.String(128), nullable=False),
            sa.Column("public_fact_snapshot_id", sa.String(192), nullable=False),
            sa.Column("action_time_fact_snapshot_id", sa.String(192), nullable=False),
            sa.Column("account_safe_fact_snapshot_id", sa.String(192), nullable=False),
            sa.Column("account_mode_snapshot_id", sa.String(192), nullable=False),
            sa.Column("budget_reservation_id", sa.String(192), nullable=False),
            sa.Column("protection_ref_id", sa.String(192), nullable=False),
            sa.Column("execution_policy_id", sa.String(192), nullable=False),
            sa.Column("execution_policy_version", sa.String(96), nullable=False),
            sa.Column("owner_policy_version", sa.String(96), nullable=False),
            sa.Column("sizing_policy_version", sa.String(96), nullable=False),
            sa.Column("protection_policy_version", sa.String(96), nullable=False),
            sa.Column("target_notional", sa.Numeric(36, 18), nullable=False),
            sa.Column("leverage", sa.Numeric(18, 8), nullable=False),
            sa.Column("expires_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("status", sa.String(64), nullable=False),
            sa.Column("authority_boundary", sa.Text(), nullable=False),
            sa.Column("ticket_hash", sa.String(192), nullable=False),
            sa.Column("created_under_versions_hash", sa.String(192), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint("side IN ('long', 'short')", name="ck_brc_ticket_side"),
            sa.CheckConstraint(
                "event_time_ms = trigger_candle_close_time_ms",
                name="ck_brc_ticket_event_time",
            ),
            sa.CheckConstraint(
                "status IN ('created', 'preflight_pending', 'finalgate_ready', "
                "'finalgate_rejected', 'expired', 'superseded', 'submitted', "
                "'closed', 'invalidated')",
                name="ck_brc_ticket_status",
            ),
            sa.CheckConstraint(
                "target_notional > 0 AND leverage > 0",
                name="ck_brc_ticket_amounts",
            ),
            sa.UniqueConstraint("ticket_hash", name="uq_brc_ticket_hash"),
        )
        _create_index(
            "uq_brc_ticket_active_lane",
            "brc_action_time_tickets",
            ["action_time_lane_input_id"],
            unique=True,
            where=(
                "status IN ('created', 'preflight_pending', 'finalgate_ready')"
            ),
        )

    if not _has_table("brc_action_time_ticket_events"):
        op.create_table(
            "brc_action_time_ticket_events",
            sa.Column("ticket_event_id", sa.String(192), primary_key=True),
            sa.Column("ticket_id", sa.String(192), nullable=False),
            sa.Column("action_time_lane_input_id", sa.String(192), nullable=False),
            sa.Column("from_status", sa.String(64), nullable=True),
            sa.Column("to_status", sa.String(64), nullable=False),
            sa.Column("transition_reason", sa.Text(), nullable=False),
            sa.Column("trigger_ref", sa.String(256), nullable=True),
            sa.Column("writer", sa.String(128), nullable=False),
            sa.Column("event_payload", json_t, nullable=False, server_default="{}"),
            sa.Column("occurred_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "to_status IN ('created', 'preflight_pending', 'finalgate_ready', "
                "'finalgate_rejected', 'expired', 'superseded', 'submitted', "
                "'closed', 'invalidated')",
                name="ck_brc_ticket_event_to_status",
            ),
            sa.CheckConstraint(
                "from_status IS NULL OR from_status IN ('created', "
                "'preflight_pending', 'finalgate_ready', 'finalgate_rejected', "
                "'expired', 'superseded', 'submitted', 'closed', 'invalidated')",
                name="ck_brc_ticket_event_from_status",
            ),
            sa.CheckConstraint(
                "(from_status IS NULL AND to_status = 'created') OR "
                "(from_status = 'created' AND to_status IN "
                "('preflight_pending', 'expired', 'superseded', 'invalidated')) OR "
                "(from_status = 'preflight_pending' AND to_status IN "
                "('finalgate_ready', 'finalgate_rejected', 'expired', "
                "'superseded', 'invalidated')) OR "
                "(from_status = 'finalgate_ready' AND to_status IN "
                "('submitted', 'expired', 'superseded', 'invalidated')) OR "
                "(from_status = 'submitted' AND to_status = 'closed')",
                name="ck_brc_ticket_event_transition",
            ),
        )
        _create_index(
            "idx_brc_ticket_events_ticket_time",
            "brc_action_time_ticket_events",
            ["ticket_id", "occurred_at_ms"],
        )

    if not _has_table("brc_operation_layer_handoffs"):
        op.create_table(
            "brc_operation_layer_handoffs",
            sa.Column("operation_layer_handoff_id", sa.String(192), primary_key=True),
            sa.Column("ticket_id", sa.String(192), nullable=False),
            sa.Column("finalgate_pass_id", sa.String(256), nullable=False),
            sa.Column("operation_submit_command_id", sa.String(192), nullable=False),
            sa.Column("action_time_lane_input_id", sa.String(192), nullable=False),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("symbol", sa.String(128), nullable=False),
            sa.Column("side", sa.String(32), nullable=False),
            sa.Column("runtime_profile_id", sa.String(128), nullable=False),
            sa.Column("status", sa.String(64), nullable=False),
            sa.Column("blockers", json_t, nullable=False, server_default="[]"),
            sa.Column("command_plan", json_t, nullable=False, server_default="{}"),
            sa.Column("authority_boundary", sa.Text(), nullable=False),
            sa.Column("operation_layer_called", sa.Boolean(), nullable=False),
            sa.Column("exchange_write_called", sa.Boolean(), nullable=False),
            sa.Column("order_created", sa.Boolean(), nullable=False),
            sa.Column("order_lifecycle_called", sa.Boolean(), nullable=False),
            sa.Column("withdrawal_or_transfer_created", sa.Boolean(), nullable=False),
            sa.Column("live_profile_changed", sa.Boolean(), nullable=False),
            sa.Column("order_sizing_changed", sa.Boolean(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "side IN ('long', 'short')",
                name="ck_brc_op_handoff_side",
            ),
            sa.CheckConstraint(
                "status IN ('handoff_ready', 'handoff_blocked', 'submitted', "
                "'expired', 'invalidated')",
                name="ck_brc_op_handoff_status",
            ),
            sa.CheckConstraint(
                "operation_layer_called = false AND exchange_write_called = false "
                "AND order_created = false AND order_lifecycle_called = false "
                "AND withdrawal_or_transfer_created = false "
                "AND live_profile_changed = false AND order_sizing_changed = false",
                name="ck_brc_op_handoff_no_effects",
            ),
            sa.UniqueConstraint(
                "ticket_id",
                "finalgate_pass_id",
                name="uq_brc_op_handoff_ticket_finalgate",
            ),
            sa.UniqueConstraint(
                "operation_submit_command_id",
                name="uq_brc_op_handoff_submit_command",
            ),
        )
        _create_index(
            "idx_brc_op_handoff_status_time",
            "brc_operation_layer_handoffs",
            ["status", "created_at_ms"],
        )

    if not _has_table("brc_state_transition_events"):
        op.create_table(
            "brc_state_transition_events",
            sa.Column("transition_event_id", sa.String(192), primary_key=True),
            sa.Column("state_table", sa.String(128), nullable=False),
            sa.Column("entity_id", sa.String(192), nullable=False),
            sa.Column("from_status", sa.String(96), nullable=True),
            sa.Column("to_status", sa.String(96), nullable=False),
            sa.Column("transition_reason", sa.Text(), nullable=False),
            sa.Column("trigger_ref", sa.String(256), nullable=True),
            sa.Column("writer", sa.String(128), nullable=False),
            sa.Column("occurred_at_ms", sa.BIGINT(), nullable=False),
        )
        _create_index(
            "idx_brc_transition_entity_time",
            "brc_state_transition_events",
            ["state_table", "entity_id", "occurred_at_ms"],
        )

    if not _has_table("brc_runtime_safety_state_snapshots"):
        op.create_table(
            "brc_runtime_safety_state_snapshots",
            sa.Column("runtime_safety_snapshot_id", sa.String(192), primary_key=True),
            sa.Column("action_time_lane_input_id", sa.String(192), nullable=True),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("symbol", sa.String(128), nullable=True),
            sa.Column("side", sa.String(32), nullable=True),
            sa.Column("runtime_profile_id", sa.String(128), nullable=True),
            sa.Column("safety_state", sa.String(64), nullable=False),
            sa.Column("submit_allowed", sa.Boolean(), nullable=False),
            sa.Column("finalgate_ready", sa.Boolean(), nullable=False),
            sa.Column("operation_layer_ready", sa.Boolean(), nullable=False),
            sa.Column("protection_ready", sa.Boolean(), nullable=False),
            sa.Column("active_position_conflict", sa.Boolean(), nullable=False),
            sa.Column("facts_fresh", sa.Boolean(), nullable=False),
            sa.Column("trusted_fact_refs_complete", sa.Boolean(), nullable=False),
            sa.Column("blockers", json_t, nullable=False, server_default="[]"),
            sa.Column("trusted_fact_refs", json_t, nullable=False, server_default="{}"),
            sa.Column("observed_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("valid_until_ms", sa.BIGINT(), nullable=True),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("authority_boundary", sa.Text(), nullable=False),
            sa.CheckConstraint(
                "safety_state IN ('not_ready', 'ready_for_finalgate', "
                "'live_submit_ready', 'blocked_safety', 'market_wait_validated')",
                name="ck_brc_runtime_safety_state",
            ),
            sa.CheckConstraint(
                "submit_allowed = false OR (safety_state = 'live_submit_ready' "
                "AND finalgate_ready = true AND operation_layer_ready = true "
                "AND protection_ready = true AND active_position_conflict = false "
                "AND facts_fresh = true AND trusted_fact_refs_complete = true)",
                name="ck_brc_runtime_safety_submit",
            ),
        )

    if not _has_table("brc_projection_runs"):
        op.create_table(
            "brc_projection_runs",
            sa.Column("projection_run_id", sa.String(192), primary_key=True),
            sa.Column("model_type", sa.String(96), nullable=False),
            sa.Column("owner_projector", sa.String(128), nullable=False),
            sa.Column("code_version", sa.String(128), nullable=True),
            sa.Column("source_mode", sa.String(32), nullable=False),
            sa.Column("projection_target", sa.String(64), nullable=False),
            sa.Column("input_watermark", json_t, nullable=False, server_default="{}"),
            sa.Column("source_priority", json_t, nullable=False, server_default="[]"),
            sa.Column("legacy_diagnostics_read", sa.Boolean(), nullable=False),
            sa.Column("legacy_diagnostics_affected_current", sa.Boolean(), nullable=False),
            sa.Column("started_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("finished_at_ms", sa.BIGINT(), nullable=True),
            sa.Column("status", sa.String(64), nullable=False),
            sa.Column("error_detail", sa.Text(), nullable=True),
            sa.CheckConstraint(
                "source_mode IN ('db_backed', 'local_file_inventory', 'local_migration_comparison')",
                name="ck_brc_projection_source_mode",
            ),
            sa.CheckConstraint(
                "projection_target IN ('production_current', 'diagnostic', 'export')",
                name="ck_brc_projection_target",
            ),
            sa.CheckConstraint(
                "projection_target <> 'production_current' OR source_mode = 'db_backed'",
                name="ck_brc_projection_prod_db",
            ),
            sa.CheckConstraint(
                "NOT (source_mode = 'db_backed' "
                "AND projection_target = 'production_current' "
                "AND status = 'succeeded' "
                "AND legacy_diagnostics_affected_current = true)",
                name="ck_brc_projection_legacy_current",
            ),
        )

    if not _has_table("brc_current_projection_ownership"):
        op.create_table(
            "brc_current_projection_ownership",
            sa.Column("projection_key", sa.String(160), primary_key=True),
            sa.Column("model_type", sa.String(96), nullable=False),
            sa.Column("projection_scope_key", sa.String(256), nullable=False),
            sa.Column("owner_projector", sa.String(128), nullable=False),
            sa.Column("export_paths", json_t, nullable=False, server_default="[]"),
            sa.Column("legacy_writer_allowed", sa.Boolean(), nullable=False),
            sa.Column("current_source_mode", sa.String(32), nullable=False),
            sa.Column("sunset_condition", sa.Text(), nullable=True),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "legacy_writer_allowed = false",
                name="ck_brc_projection_owner_no_legacy",
            ),
            sa.CheckConstraint(
                "current_source_mode = 'db_backed'",
                name="ck_brc_projection_owner_db",
            ),
            sa.CheckConstraint(
                "projection_scope_key <> ''",
                name="ck_brc_projection_owner_scope_nonempty",
            ),
            sa.UniqueConstraint(
                "model_type",
                "projection_scope_key",
                name="uq_brc_projection_owner_scope",
            ),
        )

    if not _has_table("brc_legacy_diagnostics"):
        op.create_table(
            "brc_legacy_diagnostics",
            sa.Column("legacy_diagnostic_id", sa.String(192), primary_key=True),
            sa.Column("source_name", sa.String(128), nullable=False),
            sa.Column("diagnostic_type", sa.String(96), nullable=False),
            sa.Column("strategy_group_id", sa.String(128), nullable=True),
            sa.Column("symbol", sa.String(128), nullable=True),
            sa.Column("side", sa.String(32), nullable=True),
            sa.Column("diagnostic_payload", json_t, nullable=False, server_default="{}"),
            sa.Column("may_set_current_blocker", sa.Boolean(), nullable=False),
            sa.Column("observed_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("created_by_projection_run_id", sa.String(192), nullable=True),
            sa.CheckConstraint(
                "side IS NULL OR side IN ('long', 'short')",
                name="ck_brc_legacy_diagnostics_side",
            ),
            sa.CheckConstraint(
                "may_set_current_blocker = false",
                name="ck_brc_legacy_diag_no_current_blocker",
            ),
        )
        _create_index(
            "idx_brc_legacy_diag_scope_time",
            "brc_legacy_diagnostics",
            ["strategy_group_id", "symbol", "side", "observed_at_ms"],
        )

    if not _has_table("brc_goal_status_current"):
        op.create_table(
            "brc_goal_status_current",
            sa.Column("goal_status_current_id", sa.String(128), primary_key=True),
            sa.Column("status", sa.String(96), nullable=False),
            sa.Column("fresh_signal_present", sa.Boolean(), nullable=False),
            sa.Column("ready_for_real_order_action", sa.Boolean(), nullable=False),
            sa.Column("owner_action_required", sa.Boolean(), nullable=False),
            sa.Column("blockers", json_t, nullable=False, server_default="[]"),
            sa.Column("input_watermark", json_t, nullable=False, server_default="{}"),
            sa.Column("projection_run_id", sa.String(192), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.UniqueConstraint("goal_status_current_id", name="uq_brc_goal_status_single"),
        )

    if not _has_table("brc_control_read_model_snapshots"):
        op.create_table(
            "brc_control_read_model_snapshots",
            sa.Column("snapshot_id", sa.String(192), primary_key=True),
            sa.Column("model_type", sa.String(96), nullable=False),
            sa.Column("payload", json_t, nullable=False, server_default="{}"),
            sa.Column("source_watermark", json_t, nullable=False, server_default="{}"),
            sa.Column("owner_projector", sa.String(128), nullable=False),
            sa.Column("input_watermark", json_t, nullable=False, server_default="{}"),
            sa.Column("output_path", sa.String(512), nullable=True),
            sa.Column("is_current", sa.Boolean(), nullable=False),
            sa.Column("generated_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("generated_by", sa.String(128), nullable=False),
        )
        _create_index(
            "uq_brc_read_model_current",
            "brc_control_read_model_snapshots",
            ["model_type"],
            unique=True,
            where="is_current = true",
        )

    if not _has_table("brc_server_monitor_runs"):
        op.create_table(
            "brc_server_monitor_runs",
            sa.Column("monitor_run_id", sa.String(192), primary_key=True),
            sa.Column("automation_id", sa.String(128), nullable=False),
            sa.Column("runtime_head", sa.String(128), nullable=True),
            sa.Column("started_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("finished_at_ms", sa.BIGINT(), nullable=True),
            sa.Column("status", sa.String(64), nullable=False),
            sa.Column("quiet_reason", sa.Text(), nullable=True),
            sa.Column("notify_reason", sa.Text(), nullable=True),
            sa.Column("blocker_classes", json_t, nullable=False, server_default="[]"),
            sa.Column("systemd_status", json_t, nullable=False, server_default="{}"),
            sa.Column("source_refs", json_t, nullable=False, server_default="{}"),
            sa.Column("forbidden_effects", json_t, nullable=False, server_default="{}"),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "status IN ('quiet', 'notify', 'failed', 'degraded')",
                name="ck_brc_server_monitor_status",
            ),
        )

    if not _has_table("brc_server_monitor_notifications"):
        op.create_table(
            "brc_server_monitor_notifications",
            sa.Column("notification_id", sa.String(192), primary_key=True),
            sa.Column("dedupe_key", sa.String(256), nullable=False),
            sa.Column("automation_id", sa.String(128), nullable=False),
            sa.Column("strategy_group_id", sa.String(128), nullable=True),
            sa.Column("symbol", sa.String(128), nullable=True),
            sa.Column("blocker_class", sa.String(128), nullable=True),
            sa.Column("checkpoint", sa.String(128), nullable=False),
            sa.Column("notification_state", sa.String(64), nullable=False),
            sa.Column("first_seen_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("last_notified_at_ms", sa.BIGINT(), nullable=True),
            sa.Column("last_seen_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("send_attempts", sa.Integer(), nullable=False),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("feishu_response", json_t, nullable=False, server_default="{}"),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "notification_state IN ('pending', 'sent', 'failed', 'suppressed', 'retrying')",
                name="ck_brc_monitor_notify_state",
            ),
            sa.UniqueConstraint("dedupe_key", name="uq_brc_monitor_notify_dedupe"),
        )

    if not _has_table("brc_runtime_incidents"):
        op.create_table(
            "brc_runtime_incidents",
            sa.Column("incident_id", sa.String(192), primary_key=True),
            sa.Column("incident_type", sa.String(96), nullable=False),
            sa.Column("severity", sa.String(32), nullable=False),
            sa.Column("status", sa.String(64), nullable=False),
            sa.Column("strategy_group_id", sa.String(128), nullable=True),
            sa.Column("symbol", sa.String(128), nullable=True),
            sa.Column("side", sa.String(32), nullable=True),
            sa.Column("blocker_class", sa.String(128), nullable=True),
            sa.Column("trigger_ref", sa.String(256), nullable=True),
            sa.Column("details", json_t, nullable=False, server_default="{}"),
            sa.Column("opened_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("closed_at_ms", sa.BIGINT(), nullable=True),
            sa.CheckConstraint(
                "side IS NULL OR side IN ('long', 'short')",
                name="ck_brc_runtime_incidents_side",
            ),
            sa.CheckConstraint(
                "severity IN ('info', 'warning', 'blocking', 'critical')",
                name="ck_brc_runtime_incidents_severity",
            ),
            sa.CheckConstraint(
                "status IN ('open', 'investigating', 'recovering', 'closed', 'invalidated')",
                name="ck_brc_runtime_incidents_status",
            ),
        )
        _create_index(
            "idx_brc_runtime_incidents_scope_time",
            "brc_runtime_incidents",
            ["strategy_group_id", "symbol", "opened_at_ms"],
        )

    if not _has_table("brc_recovery_runs"):
        op.create_table(
            "brc_recovery_runs",
            sa.Column("recovery_run_id", sa.String(192), primary_key=True),
            sa.Column("incident_id", sa.String(192), nullable=True),
            sa.Column("recovery_action", sa.String(128), nullable=False),
            sa.Column("status", sa.String(64), nullable=False),
            sa.Column("operator", sa.String(128), nullable=False),
            sa.Column("effects", json_t, nullable=False, server_default="{}"),
            sa.Column("forbidden_effects", json_t, nullable=False, server_default="{}"),
            sa.Column("started_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("finished_at_ms", sa.BIGINT(), nullable=True),
            sa.CheckConstraint(
                "status IN ('planned', 'running', 'succeeded', 'failed', 'aborted')",
                name="ck_brc_recovery_runs_status",
            ),
        )
        _create_index(
            "idx_brc_recovery_runs_incident",
            "brc_recovery_runs",
            ["incident_id", "started_at_ms"],
        )

    if not _has_table("brc_strategy_intake_cases"):
        op.create_table(
            "brc_strategy_intake_cases",
            sa.Column("intake_case_id", sa.String(192), primary_key=True),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("source_ref", sa.String(512), nullable=True),
            sa.Column("status", sa.String(64), nullable=False),
            sa.Column("stage", sa.String(96), nullable=False),
            sa.Column("owner_action_required", sa.Boolean(), nullable=False),
            sa.Column("payload", json_t, nullable=False, server_default="{}"),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "status IN ('research', 'candidate', 'admitted', 'rejected', 'parked')",
                name="ck_brc_strategy_intake_status",
            ),
        )
        _create_index(
            "idx_brc_strategy_intake_group",
            "brc_strategy_intake_cases",
            ["strategy_group_id", "status"],
        )

    if not _has_table("brc_strategy_intake_stage_events"):
        op.create_table(
            "brc_strategy_intake_stage_events",
            sa.Column("stage_event_id", sa.String(192), primary_key=True),
            sa.Column("intake_case_id", sa.String(192), nullable=False),
            sa.Column("from_stage", sa.String(96), nullable=True),
            sa.Column("to_stage", sa.String(96), nullable=False),
            sa.Column("transition_reason", sa.Text(), nullable=False),
            sa.Column("writer", sa.String(128), nullable=False),
            sa.Column("event_payload", json_t, nullable=False, server_default="{}"),
            sa.Column("occurred_at_ms", sa.BIGINT(), nullable=False),
        )
        _create_index(
            "idx_brc_strategy_intake_events_case",
            "brc_strategy_intake_stage_events",
            ["intake_case_id", "occurred_at_ms"],
        )

    if not _has_table("brc_strategy_review_outcomes"):
        op.create_table(
            "brc_strategy_review_outcomes",
            sa.Column("review_outcome_id", sa.String(192), primary_key=True),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("symbol", sa.String(128), nullable=True),
            sa.Column("side", sa.String(32), nullable=True),
            sa.Column("signal_event_id", sa.String(192), nullable=True),
            sa.Column("promotion_candidate_id", sa.String(192), nullable=True),
            sa.Column("action_time_lane_input_id", sa.String(192), nullable=True),
            sa.Column("ticket_id", sa.String(192), nullable=True),
            sa.Column("order_id", sa.String(192), nullable=True),
            sa.Column("stage_reached", sa.String(96), nullable=False),
            sa.Column("first_blocker", sa.String(128), nullable=True),
            sa.Column("market_after_event", json_t, nullable=False, server_default="{}"),
            sa.Column("execution_outcome", json_t, nullable=False, server_default="{}"),
            sa.Column("strategy_learning", sa.Text(), nullable=False),
            sa.Column("governance_recommendation", sa.String(128), nullable=False),
            sa.Column("owner_action_required", sa.Boolean(), nullable=False),
            sa.Column("created_under_versions_hash", sa.String(192), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "side IS NULL OR side IN ('long', 'short')",
                name="ck_brc_strategy_review_side",
            ),
        )
        _create_index(
            "idx_brc_strategy_review_scope_time",
            "brc_strategy_review_outcomes",
            ["strategy_group_id", "symbol", "created_at_ms"],
        )

    if not _has_table("brc_strategy_governance_decisions"):
        op.create_table(
            "brc_strategy_governance_decisions",
            sa.Column("governance_decision_id", sa.String(192), primary_key=True),
            sa.Column("review_outcome_id", sa.String(192), nullable=True),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("decision_type", sa.String(96), nullable=False),
            sa.Column("decision_state", sa.String(64), nullable=False),
            sa.Column("owner_action_required", sa.Boolean(), nullable=False),
            sa.Column("current_authority_effect", sa.String(64), nullable=False),
            sa.Column("decision_payload", json_t, nullable=False, server_default="{}"),
            sa.Column("created_under_versions_hash", sa.String(192), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "decision_state IN ('proposed', 'accepted', 'rejected', 'superseded')",
                name="ck_brc_strategy_gov_decision_state",
            ),
            sa.CheckConstraint(
                "current_authority_effect IN ('none', 'policy_event_required')",
                name="ck_brc_strategy_gov_no_direct_authority",
            ),
        )
        _create_index(
            "idx_brc_strategy_gov_group",
            "brc_strategy_governance_decisions",
            ["strategy_group_id", "created_at_ms"],
        )

    if not _has_table("brc_strategy_policy_change_requests"):
        op.create_table(
            "brc_strategy_policy_change_requests",
            sa.Column("policy_change_request_id", sa.String(192), primary_key=True),
            sa.Column("governance_decision_id", sa.String(192), nullable=True),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("request_type", sa.String(96), nullable=False),
            sa.Column("request_state", sa.String(64), nullable=False),
            sa.Column("requested_scope_key", sa.String(256), nullable=False),
            sa.Column("proposed_policy_event_payload", json_t, nullable=False, server_default="{}"),
            sa.Column("validates_against_current_versions", sa.Boolean(), nullable=False),
            sa.Column("owner_approved_at_ms", sa.BIGINT(), nullable=True),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "request_state IN ('draft', 'validated', 'owner_approved', "
                "'applied', 'rejected', 'superseded')",
                name="ck_brc_strategy_policy_req_state",
            ),
            sa.CheckConstraint(
                "request_type IN ('enable_strategy', 'pause_strategy', "
                "'resume_strategy', 'retire_strategy', 'narrow_scope', "
                "'expand_scope', 'enable_ticket_eligibility', "
                "'disable_ticket_eligibility', 'enable_real_submit', "
                "'disable_real_submit', 'set_budget', 'set_runtime_profile', "
                "'set_notification_policy')",
                name="ck_brc_strategy_policy_req_type",
            ),
        )
        _create_index(
            "idx_brc_strategy_policy_req_group",
            "brc_strategy_policy_change_requests",
            ["strategy_group_id", "request_state"],
        )


def downgrade() -> None:
    for table_name in reversed(TABLES):
        if _has_table(table_name):
            op.drop_table(table_name)
