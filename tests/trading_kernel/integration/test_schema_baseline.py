from __future__ import annotations

import sqlalchemy as sa

from src.trading_kernel.infrastructure.pg_models import metadata


EXPECTED_TABLES = {
    "brc_account_exposure_current",
    "brc_budget_reservations",
    "brc_capacity_claims",
    "brc_entry_lane_current",
    "brc_exit_policies",
    "brc_event_required_facts",
    "brc_event_specs",
    "brc_exchange_commands",
    "brc_fact_definitions",
    "brc_facts_current",
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
    "brc_strategy_candidate_scopes",
    "brc_strategy_versions",
    "brc_trade_aggregates",
    "brc_trade_events",
    "brc_trade_reviews",
    "brc_trade_tickets",
}


def test_kernel_metadata_has_exact_clean_table_allowlist() -> None:
    assert set(metadata.tables) == EXPECTED_TABLES


def test_kernel_schema_has_core_uniqueness_constraints() -> None:
    tickets = metadata.tables["brc_trade_tickets"]
    claims = metadata.tables["brc_capacity_claims"]
    commands = metadata.tables["brc_exchange_commands"]
    events = metadata.tables["brc_trade_events"]

    ticket_uniques = _unique_column_sets(tickets)
    claim_uniques = _unique_column_sets(claims)
    command_uniques = _unique_column_sets(commands)
    event_uniques = _unique_column_sets(events)

    assert ("signal_event_id",) in ticket_uniques
    assert ("active_netting_domain_key",) in ticket_uniques
    assert ("signal_event_id",) in claim_uniques
    assert ("ticket_id",) in claim_uniques
    assert ("decision_digest",) in claim_uniques
    assert ("idempotency_key",) in command_uniques
    assert ("venue_client_order_id",) in command_uniques
    assert ("ticket_id", "command_kind", "generation") in command_uniques
    assert ("ticket_id", "sequence") in event_uniques


def test_financial_columns_use_fixed_precision_numeric() -> None:
    required = {
        ("brc_trade_tickets", "quantity"),
        ("brc_trade_tickets", "entry_reference_price"),
        ("brc_capacity_claims", "quantity"),
        ("brc_capacity_claims", "notional"),
        ("brc_trade_tickets", "notional"),
        ("brc_trade_aggregates", "position_qty"),
        ("brc_exchange_commands", "quantity"),
        ("brc_positions_current", "quantity"),
        ("brc_budget_reservations", "reserved_notional"),
        ("brc_account_exposure_current", "gross_notional"),
    }

    for table_name, column_name in required:
        column = metadata.tables[table_name].c[column_name]
        assert isinstance(column.type, sa.Numeric)
        assert column.type.precision == 38
        assert column.type.scale == 18


def test_signal_schema_contains_observation_identity_without_capital_or_order_terms() -> None:
    signals = metadata.tables["brc_signal_events"]
    check_sql = {
        str(constraint.sqltext)
        for constraint in signals.constraints
        if isinstance(constraint, sa.CheckConstraint)
    }
    forbidden_columns = {
        "signal_grade",
        "quantity",
        "notional",
        "leverage",
        "risk_at_stop",
        "entry_order_type",
        "entry_limit_price",
        "initial_stop_price",
        "take_profit_prices",
    }

    assert "position_side IN ('long', 'short')" in check_sql
    assert "expires_at_ms > occurred_at_ms" in check_sql
    assert (
        "observed_at_ms >= occurred_at_ms AND expires_at_ms > observed_at_ms"
        in check_sql
    )
    assert "fact_digest ~ '^sha256:[0-9a-f]{64}$'" in check_sql
    assert forbidden_columns.isdisjoint(signals.c.keys())


def test_candidate_selector_has_bounded_ordering_indexes() -> None:
    readiness = metadata.tables["brc_readiness_current"]
    signals = metadata.tables["brc_signal_events"]

    assert ("readiness_state", "signal_event_id") in _index_column_sets(readiness)
    assert (
        "expires_at_ms",
        "occurred_at_ms",
        "observed_at_ms",
        "signal_event_id",
    ) in _index_column_sets(signals)


def test_review_funding_attribution_has_bounded_instrument_window_index() -> None:
    tickets = metadata.tables["brc_trade_tickets"]

    assert (
        "venue_id",
        "account_id",
        "exchange_instrument_id",
        "created_at_ms",
        "terminal_at_ms",
    ) in _index_column_sets(tickets)


def test_owner_capacity_policy_has_dynamic_budget_columns_and_constraints() -> None:
    policies = metadata.tables["brc_owner_policy_current"]
    check_sql = {
        str(constraint.sqltext)
        for constraint in policies.constraints
        if isinstance(constraint, sa.CheckConstraint)
    }

    assert {
        "new_entry_submit_enabled",
        "planned_stop_risk_fraction",
        "max_initial_margin_utilization",
        "max_leverage",
        "supported_margin_mode",
        "min_liquidation_distance_to_stop_distance_ratio",
        "max_post_fill_stop_risk_overrun_fraction",
    }.issubset(policies.c.keys())
    assert {
        "real_submit_enabled",
        "max_gross_notional",
        "max_gross_risk_at_stop",
        "max_ticket_risk_at_stop",
        "target_leverage",
    }.isdisjoint(policies.c.keys())
    assert "priority_rank > 0" in check_sql
    assert "max_concurrent_tickets > 0" in check_sql
    assert (
        "planned_stop_risk_fraction > 0 AND planned_stop_risk_fraction < 1"
        in check_sql
    )
    assert (
        "max_initial_margin_utilization > 0 "
        "AND max_initial_margin_utilization <= 1"
    ) in check_sql
    assert "max_leverage >= 1 AND max_leverage <= 10" in check_sql
    assert "supported_margin_mode = 'cross'" in check_sql
    assert "min_liquidation_distance_to_stop_distance_ratio > 0" in check_sql
    assert (
        "max_post_fill_stop_risk_overrun_fraction >= 0 "
        "AND max_post_fill_stop_risk_overrun_fraction < 1"
    ) in check_sql


def test_instrument_rules_are_venue_scoped_and_freeze_leverage_brackets() -> None:
    rules = metadata.tables["brc_instrument_rules_current"]

    assert tuple(column.name for column in rules.primary_key.columns) == (
        "venue_id",
        "exchange_instrument_id",
    )
    assert {
        "exchange_max_leverage",
        "maintenance_margin_brackets",
        "maintenance_margin_brackets_digest",
    }.issubset(rules.c.keys())


def test_signal_fact_snapshots_are_append_only_per_signal_and_definition() -> None:
    snapshots = metadata.tables["brc_signal_fact_snapshots"]

    assert tuple(column.name for column in snapshots.primary_key.columns) == (
        "signal_event_id",
        "fact_definition_id",
    )
    assert {
        "role",
        "value",
        "satisfied",
        "observed_at_ms",
        "valid_until_ms",
        "projection_version",
    }.issubset(snapshots.c.keys())


def test_ticket_schema_freezes_runtime_scope_identity_and_version() -> None:
    tickets = metadata.tables["brc_trade_tickets"]

    assert "runtime_scope_id" in tickets.c
    assert "runtime_scope_version" in tickets.c
    assert "take_profit_quantities" in tickets.c


def test_dynamic_claim_and_incident_storage_enforce_typed_safety_boundaries() -> None:
    claims = metadata.tables["brc_capacity_claims"]
    incidents = metadata.tables["brc_runtime_incidents"]
    claim_checks = {
        str(constraint.sqltext)
        for constraint in claims.constraints
        if isinstance(constraint, sa.CheckConstraint)
    }
    incident_checks = {
        str(constraint.sqltext)
        for constraint in incidents.constraints
        if isinstance(constraint, sa.CheckConstraint)
    }

    assert {
        "selected_leverage <= exchange_max_leverage",
        "risk_at_stop <= planned_stop_risk_budget",
        "post_fill_stop_risk_limit >= planned_stop_risk_budget",
    }.issubset(claim_checks)
    assert {"entry_block_scope", "entry_block_key"}.issubset(incidents.c.keys())
    assert any("entry_block_scope IN" in check for check in incident_checks)
    assert any("entry_block_key" in check for check in incident_checks)


def test_exit_policy_registry_and_capacity_claim_freeze_runner_split() -> None:
    policies = metadata.tables["brc_exit_policies"]
    claims = metadata.tables["brc_capacity_claims"]

    assert {
        "exit_policy_id",
        "exit_policy_version",
        "event_spec_id",
        "semantic_hash",
        "policy",
        "status",
    }.issubset(policies.c.keys())
    assert "take_profit_quantities" in claims.c


def test_aggregate_schema_conserves_authoritative_entry_order_identity() -> None:
    aggregates = metadata.tables["brc_trade_aggregates"]

    assert "entry_exchange_order_id" in aggregates.c
    assert {
        "active_stop_exchange_order_id",
        "active_stop_price",
        "tp1_exchange_order_id",
        "tp1_target_qty",
        "tp1_filled_qty",
        "break_even_floor_price",
        "pending_replaced_stop_exchange_order_id",
        "pending_stop_price",
        "pending_stop_watermark_ms",
        "runner_stop_watermark_ms",
    }.issubset(aggregates.c.keys())


def test_cancel_command_allows_null_quantity_without_weakening_order_quantity() -> None:
    commands = metadata.tables["brc_exchange_commands"]

    assert commands.c.quantity.nullable is True
    check_sql = {
        str(constraint.sqltext)
        for constraint in commands.constraints
        if isinstance(constraint, sa.CheckConstraint)
    }
    assert "quantity IS NULL OR quantity > 0" in check_sql


def _unique_column_sets(table: sa.Table) -> set[tuple[str, ...]]:
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, sa.UniqueConstraint)
    }


def _index_column_sets(table: sa.Table) -> set[tuple[str, ...]]:
    return {
        tuple(column.name for column in index.columns)
        for index in table.indexes
    }
