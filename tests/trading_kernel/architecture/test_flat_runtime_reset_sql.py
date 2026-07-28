from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RESET_SQL = REPO_ROOT / "scripts" / "trading_kernel" / "reset_flat_runtime.sql"

RUNTIME_TABLES = {
    "brc_instrument_rules_current",
    "brc_facts_current",
    "brc_signal_events",
    "brc_signal_fact_snapshots",
    "brc_readiness_current",
    "brc_capacity_claims",
    "brc_trade_tickets",
    "brc_trade_aggregates",
    "brc_trade_events",
    "brc_exchange_commands",
    "brc_positions_current",
    "brc_budget_reservations",
    "brc_runtime_incidents",
    "brc_trade_reviews",
    "brc_monitor_current",
    "brc_monitor_events",
}

AUTHORITY_TABLES = {
    "brc_strategy_groups",
    "brc_strategy_versions",
    "brc_event_specs",
    "brc_exit_policies",
    "brc_fact_definitions",
    "brc_event_required_facts",
    "brc_instruments",
    "brc_strategy_candidate_scopes",
    "brc_owner_policy_events",
    "brc_owner_policy_current",
    "brc_runtime_profiles",
    "brc_runtime_scopes_current",
    "brc_runtime_capabilities_current",
    "brc_schema_metadata",
}


def test_flat_runtime_reset_sql_is_guarded_and_preserves_authority() -> None:
    sql = RESET_SQL.read_text(encoding="utf-8")

    assert "\\set ON_ERROR_STOP on" in sql
    assert "RESET_BRC_FLAT_RUNTIME" in sql
    assert "current_database()" in sql
    assert "expected_schema_revision" in sql
    assert "expected_runtime_commit" in sql
    assert "expected_ticket_id" in sql
    assert "expected_ticket_count" in sql
    assert "expected_unresolved_command_count" in sql
    assert "outcome_unknown" in sql
    assert "pg_advisory_xact_lock" in sql

    truncate = re.search(
        r"TRUNCATE TABLE(?P<body>.*?);",
        sql,
        flags=re.DOTALL,
    )
    assert truncate is not None
    truncated_tables = set(re.findall(r"\bbrc_[a-z0-9_]+\b", truncate["body"]))
    assert truncated_tables == RUNTIME_TABLES
    assert truncated_tables.isdisjoint(AUTHORITY_TABLES)

    assert "UPDATE brc_entry_lane_current" in sql
    assert "status = 'idle'" in sql
    assert "UPDATE brc_account_exposure_current" in sql
    assert "gross_notional = 0" in sql
    assert "gross_risk_at_stop = 0" in sql
    assert "active_ticket_count = 0" in sql
    assert "UPDATE brc_runtime_scopes_current" in sql
    assert "observation_lease_until_ms = NULL" in sql
    assert "observation_claim_owner = NULL" in sql

    lowered = sql.lower()
    assert "update brc_trade_tickets" not in lowered
    assert "update brc_owner_policy_current" not in lowered
    assert "delete from brc_owner_policy" not in lowered
