from __future__ import annotations

import sqlalchemy as sa

from src.trading_kernel.infrastructure.pg_models import metadata


EXPECTED_TABLES = {
    "brc_account_exposure_current",
    "brc_budget_reservations",
    "brc_entry_lane_current",
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
    "brc_strategy_groups",
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
    commands = metadata.tables["brc_exchange_commands"]
    events = metadata.tables["brc_trade_events"]

    ticket_uniques = _unique_column_sets(tickets)
    command_uniques = _unique_column_sets(commands)
    event_uniques = _unique_column_sets(events)

    assert ("signal_event_id",) in ticket_uniques
    assert ("active_netting_domain_key",) in ticket_uniques
    assert ("idempotency_key",) in command_uniques
    assert ("venue_client_order_id",) in command_uniques
    assert ("ticket_id", "command_kind", "generation") in command_uniques
    assert ("ticket_id", "sequence") in event_uniques


def test_financial_columns_use_fixed_precision_numeric() -> None:
    required = {
        ("brc_trade_tickets", "quantity"),
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


def test_ticket_schema_freezes_runtime_scope_identity_and_version() -> None:
    tickets = metadata.tables["brc_trade_tickets"]

    assert "runtime_scope_id" in tickets.c
    assert "runtime_scope_version" in tickets.c


def _unique_column_sets(table: sa.Table) -> set[tuple[str, ...]]:
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, sa.UniqueConstraint)
    }
