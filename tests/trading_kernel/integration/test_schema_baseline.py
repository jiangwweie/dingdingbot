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
    "brc_instrument_certification_batch_members",
    "brc_instrument_certification_batches",
    "brc_instrument_certification_current",
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
    "brc_comparative_projection_current",
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
}


def test_kernel_metadata_has_exact_clean_table_allowlist() -> None:
    assert set(metadata.tables) == EXPECTED_TABLES


def test_strategy_universe_metadata_has_forward_only_authority_shape() -> None:
    versions = metadata.tables["brc_strategy_universe_versions"]
    members = metadata.tables["brc_strategy_universe_members"]
    current = metadata.tables["brc_strategy_universe_current"]
    certifications = metadata.tables["brc_instrument_certification_current"]
    batches = metadata.tables["brc_instrument_certification_batches"]
    batch_members = metadata.tables[
        "brc_instrument_certification_batch_members"
    ]
    comparative = metadata.tables["brc_comparative_projection_current"]
    instruments = metadata.tables["brc_instruments"]
    scopes = metadata.tables["brc_runtime_scopes_current"]

    assert "brc_strategy_candidate_scopes" not in metadata.tables
    assert ("event_spec_id", "universe_version") in _unique_column_sets(versions)
    assert (
        "universe_version_id",
        "event_spec_id",
        "semantic_digest",
    ) in _unique_column_sets(versions)
    assert (
        "universe_version_id",
        "event_spec_id",
        "semantic_digest",
        "lifecycle_state",
    ) in _unique_column_sets(versions)
    assert tuple(column.name for column in members.primary_key.columns) == (
        "universe_version_id",
        "exchange_instrument_id",
    )
    assert tuple(column.name for column in current.primary_key.columns) == (
        "event_spec_id",
    )
    assert current.c.lifecycle_state.server_default is not None
    assert (
        "universe_version_id",
        "event_spec_id",
        "semantic_digest",
        "lifecycle_state",
    ) in _foreign_key_column_sets(current)
    assert tuple(column.name for column in certifications.primary_key.columns) == (
        "runtime_profile_id",
        "exchange_instrument_id",
    )
    assert tuple(column.name for column in batches.primary_key.columns) == (
        "certification_batch_id",
    )
    assert tuple(column.name for column in batch_members.primary_key.columns) == (
        "certification_batch_id",
        "exchange_instrument_id",
    )
    assert {
        "target_commit",
        "target_schema_revision",
        "target_seed_identity",
        "owner_policy_id",
        "owner_policy_version",
        "manifest_digest",
        "status",
        "minimum_valid_until_ms",
        "completed_at_ms",
        "valid_until_ms",
        "blocker_code",
    }.issubset(batches.c.keys())
    assert {
        "status",
        "blocker_code",
        "facts_digest",
        "product_rules_digest",
        "observed_at_ms",
        "valid_until_ms",
    }.issubset(batch_members.c.keys())
    assert tuple(column.name for column in comparative.primary_key.columns) == (
        "event_spec_id",
        "universe_version_id",
    )
    assert {
        "projection_status",
        "failure_reason",
        "projection",
        "observed_at_ms",
        "valid_until_ms",
        "projection_version",
    }.issubset(comparative.c.keys())
    assert {
        "pending_certification",
        "active",
    } == _allowed_values(instruments, "status")
    assert {
        "lifecycle_state",
        "observation_enabled",
        "entry_enabled",
        "universe_version_id",
        "universe_semantic_digest",
        "warm_closed_bar_time_ms",
        "warm_completed_at_ms",
        "warm_readiness_digest",
        "warm_valid_until_ms",
    }.issubset(scopes.c.keys())
    assert {
        "abandoned_at_ms",
        "abandon_reason_code",
    }.issubset(versions.c.keys())
    assert (
        "universe_version_id",
        "event_spec_id",
        "universe_semantic_digest",
        "lifecycle_state",
    ) in _foreign_key_column_sets(scopes)
    assert "enabled" not in scopes.c
    assert (
        "observation_enabled",
        "next_observation_due_at_ms",
        "lease_expires_at_ms",
    ) in _index_column_sets(scopes)
    assert (
        "status",
        "next_check_at_ms",
        "lease_expires_at_ms",
    ) in _index_column_sets(certifications)
    assert (
        "event_spec_id",
        "universe_version_id",
        "closed_bar_time_ms",
    ) in _index_column_sets(comparative)


def test_universe_lineage_is_required_on_signal_claim_and_ticket_metadata() -> None:
    for table_name in (
        "brc_signal_events",
        "brc_capacity_claims",
        "brc_trade_tickets",
    ):
        table = metadata.tables[table_name]
        assert table.c.universe_version_id.nullable is False
        assert table.c.universe_semantic_digest.nullable is False
        assert (
            "universe_version_id",
            "event_spec_id",
            "universe_semantic_digest",
        ) in _foreign_key_column_sets(table)


def test_kernel_schema_has_core_uniqueness_constraints() -> None:
    tickets = metadata.tables["brc_trade_tickets"]
    claims = metadata.tables["brc_capacity_claims"]
    commands = metadata.tables["brc_exchange_commands"]
    events = metadata.tables["brc_trade_events"]
    reviews = metadata.tables["brc_trade_reviews"]

    ticket_uniques = _unique_column_sets(tickets)
    claim_uniques = _unique_column_sets(claims)
    command_uniques = _unique_column_sets(commands)
    event_uniques = _unique_column_sets(events)
    review_uniques = _unique_column_sets(reviews)

    assert ("signal_event_id",) in ticket_uniques
    assert ("active_netting_domain_key",) in ticket_uniques
    assert ("signal_event_id",) in claim_uniques
    assert ("ticket_id",) in claim_uniques
    assert ("decision_digest",) in claim_uniques
    assert ("idempotency_key",) in command_uniques
    assert ("venue_client_order_id",) in command_uniques
    assert ("ticket_id", "command_kind", "generation") in command_uniques
    assert ("ticket_id", "sequence") in event_uniques
    assert ("ticket_id",) not in review_uniques
    assert ("ticket_id", "revision") in review_uniques
    assert ("supersedes_review_id",) in review_uniques


def test_trade_review_schema_is_append_only_revision_authority() -> None:
    reviews = metadata.tables["brc_trade_reviews"]
    check_sql = {
        str(constraint.sqltext)
        for constraint in reviews.constraints
        if isinstance(constraint, sa.CheckConstraint)
    }

    assert reviews.c.revision.nullable is False
    assert reviews.c.supersedes_review_id.nullable is True
    assert len(reviews.c.supersedes_review_id.foreign_keys) == 1
    assert (
        "ticket_id",
        "supersedes_review_id",
    ) in _foreign_key_column_sets(reviews)
    assert "revision > 0" in check_sql
    assert (
        "(revision = 1 AND supersedes_review_id IS NULL) OR "
        "(revision > 1 AND supersedes_review_id IS NOT NULL)"
    ) in check_sql


def test_leverage_commands_are_the_only_commands_without_order_identity() -> None:
    commands = metadata.tables["brc_exchange_commands"]
    check_sql = {
        str(constraint.sqltext)
        for constraint in commands.constraints
        if isinstance(constraint, sa.CheckConstraint)
    }

    assert commands.c.venue_client_order_id.nullable is True
    assert (
        "(command_kind = 'set_leverage' AND venue_client_order_id IS NULL) "
        "OR (command_kind <> 'set_leverage' AND venue_client_order_id IS NOT NULL)"
    ) in check_sql


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
    assert (
        "venue_id",
        "account_id",
        "strategy_group_id",
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
        "max_strategy_group_concurrent_tickets",
        "max_ticket_stop_risk_fraction",
        "max_gross_stop_risk_fraction",
        "max_ticket_initial_margin_fraction",
        "max_gross_initial_margin_utilization",
        "max_leverage",
        "supported_margin_mode",
        "post_stop_stress_multiple",
        "max_post_fill_stop_risk_overrun_fraction",
    }.issubset(policies.c.keys())
    assert {
        "planned_stop_risk_fraction",
        "max_initial_margin_utilization",
        "real_submit_enabled",
        "max_gross_notional",
        "max_gross_risk_at_stop",
        "max_ticket_risk_at_stop",
        "target_leverage",
    }.isdisjoint(policies.c.keys())
    assert "priority_rank > 0" in check_sql
    assert "max_concurrent_tickets > 0" in check_sql
    assert "max_strategy_group_concurrent_tickets > 0" in check_sql
    assert (
        "max_ticket_stop_risk_fraction > 0 "
        "AND max_ticket_stop_risk_fraction < 1"
        in check_sql
    )
    assert (
        "max_gross_stop_risk_fraction > 0 "
        "AND max_gross_stop_risk_fraction <= 1 "
        "AND max_ticket_stop_risk_fraction <= max_gross_stop_risk_fraction"
    ) in check_sql
    assert (
        "max_ticket_initial_margin_fraction > 0 "
        "AND max_ticket_initial_margin_fraction <= 1"
    ) in check_sql
    assert (
        "max_gross_initial_margin_utilization > 0 "
        "AND max_gross_initial_margin_utilization <= 1 "
        "AND max_ticket_initial_margin_fraction "
        "<= max_gross_initial_margin_utilization"
    ) in check_sql
    assert "max_leverage >= 1 AND max_leverage <= 10" in check_sql
    assert "supported_margin_mode = 'cross'" in check_sql
    assert "post_stop_stress_multiple > 0" in check_sql
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
        "notional_coefficient",
        "notional_coefficient_certified",
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


def test_stop_stress_schema_retires_liquidation_command_authority() -> None:
    claims = metadata.tables["brc_capacity_claims"]
    tickets = metadata.tables["brc_trade_tickets"]
    aggregates = metadata.tables["brc_trade_aggregates"]
    positions = metadata.tables["brc_positions_current"]
    retired = {
        "min_liquidation_distance_to_stop_distance_ratio",
        "maintenance_margin_bracket_id",
        "projected_liquidation_price",
        "projected_liquidation_distance",
        "projected_liquidation_distance_to_stop_distance_ratio",
        "actual_liquidation_price",
        "actual_liquidation_distance",
        "actual_liquidation_distance_to_stop_distance_ratio",
    }

    assert retired.isdisjoint(claims.c.keys())
    assert retired.isdisjoint(tickets.c.keys())
    assert retired.isdisjoint(aggregates.c.keys())
    assert {
        "post_stop_stress_multiple",
        "cross_margin_stress_evidence",
    }.issubset(claims.c.keys())
    assert {
        "cross_margin_stress_model_id",
        "post_stop_stress_multiple",
        "claim_stress_proof_digest",
    }.issubset(tickets.c.keys())
    assert "cross_margin_stress_evidence" not in tickets.c
    assert {
        "venue_reported_liquidation_price",
        "post_fill_stress_status",
        "post_fill_stress_proof_digest",
    }.issubset(aggregates.c.keys())
    assert {
        "venue_reported_liquidation_price",
        "venue_reported_liquidation_observation_status",
    }.issubset(positions.c.keys())
    assert positions.c.venue_reported_liquidation_observation_status.nullable is False


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
    assert {
        "gross_risk_at_stop_at_claim",
        "current_reserved_margin_at_claim",
        "max_ticket_stop_risk_fraction",
        "max_gross_stop_risk_fraction",
        "max_ticket_initial_margin_fraction",
        "max_gross_initial_margin_utilization",
        "ticket_margin_budget",
        "reserved_margin",
    }.issubset(claims.c.keys())
    assert {"entry_block_scope", "entry_block_key"}.issubset(incidents.c.keys())
    assert any("entry_block_scope IN" in check for check in incident_checks)
    assert any("entry_block_key" in check for check in incident_checks)


def test_account_exposure_tracks_reserved_margin_for_atomic_capacity_revalidation() -> None:
    exposure = metadata.tables["brc_account_exposure_current"]
    check_sql = {
        str(constraint.sqltext)
        for constraint in exposure.constraints
        if isinstance(constraint, sa.CheckConstraint)
    }

    assert {
        "gross_notional",
        "gross_risk_at_stop",
        "current_reserved_margin",
        "active_ticket_count",
        "projection_version",
    }.issubset(exposure.c.keys())
    assert "current_reserved_margin >= 0" in check_sql


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
    assert {
        "take_profit_quantities",
        "active_strategy_group_ticket_count_at_claim",
        "max_strategy_group_concurrent_tickets",
        "remaining_strategy_group_slots_at_claim",
    }.issubset(claims.c.keys())


def test_aggregate_schema_conserves_authoritative_entry_order_identity() -> None:
    aggregates = metadata.tables["brc_trade_aggregates"]

    assert "entry_exchange_order_id" in aggregates.c
    assert {
        "actual_stop_risk",
        "venue_reported_liquidation_price",
        "post_fill_risk_status",
        "post_fill_disposition",
        "post_fill_stress_status",
        "post_fill_stress_proof_digest",
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


def _foreign_key_column_sets(table: sa.Table) -> set[tuple[str, ...]]:
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, sa.ForeignKeyConstraint)
    }


def _allowed_values(table: sa.Table, column_name: str) -> set[str]:
    marker = f"{column_name} IN ("
    for constraint in table.constraints:
        if not isinstance(constraint, sa.CheckConstraint):
            continue
        sql = str(constraint.sqltext)
        if sql.startswith(marker):
            return {
                value.strip().strip("'")
                for value in sql.removeprefix(marker).removesuffix(")").split(",")
            }
    return set()
