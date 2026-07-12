from __future__ import annotations

from sqlalchemy import text

from scripts.verify_ticket_lifecycle_phase_two_readiness import (
    evaluate_phase_two_readiness,
)
from tests.unit.test_capital_safety_scope_freeze_gate import _insert_scope_freeze
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


def test_phase_two_requires_disabled_capability_and_one_fresh_safe_account_mode(
    pg_control_connection,
):
    pg_control_connection.execute(
        text(
            "UPDATE brc_runtime_capabilities_current "
            "SET status = 'disabled', certification_ref = 'unit:phase-one' "
            "WHERE capability_id = 'ticket_lifecycle_durable_mutation'"
        )
    )
    pg_control_connection.execute(
        text(
            "INSERT INTO brc_exchange_account_modes_current ("
            "account_mode_current_id, account_id, exchange_id, runtime_profile_id, "
            "position_mode, dual_side_position, position_mode_safe, status, "
            "fact_snapshot_id, source_kind, source_ref, observed_at_ms, "
            "valid_until_ms, updated_at_ms) VALUES ("
            "'mode-current-1', 'account-1', 'binance_usdm', 'profile-1', "
            "'one_way', 0, 1, 'current', 'fact-1', 'signed_get', "
            "'unit:/positionSide/dual', :now_ms, :valid_until_ms, :now_ms)"
        ),
        {"now_ms": NOW_MS, "valid_until_ms": NOW_MS + 60_000},
    )

    payload = evaluate_phase_two_readiness(
        pg_control_connection,
        now_ms=NOW_MS + 1_000,
    )

    assert payload["status"] == "phase_two_ready"
    assert payload["blockers"] == []
    assert payload["counts"] == {
        "safe_account_mode_count": 1,
        "critical_exchange_commands": 0,
        "active_domain_holds": 0,
        "active_real_lifecycles": 0,
        "unprotected_real_attempts": 0,
    }


def test_phase_two_rejects_enabled_capability_or_missing_account_truth(
    pg_control_connection,
):
    payload = evaluate_phase_two_readiness(
        pg_control_connection,
        now_ms=NOW_MS + 1_000,
    )

    assert payload["status"] == "blocked"
    assert "phase_two_capability_already_enabled" in payload["blockers"]
    assert "phase_two_safe_account_mode_count:0" in payload["blockers"]


def test_pre_switch_readiness_accepts_existing_enabled_capability_only_when_explicit(
    pg_control_connection,
):
    pg_control_connection.execute(
        text(
            "INSERT INTO brc_exchange_account_modes_current ("
            "account_mode_current_id, account_id, exchange_id, runtime_profile_id, "
            "position_mode, dual_side_position, position_mode_safe, status, "
            "fact_snapshot_id, source_kind, source_ref, observed_at_ms, "
            "valid_until_ms, updated_at_ms) VALUES ("
            "'mode-current-pre-switch', 'account-1', 'binance_usdm', 'profile-1', "
            "'one_way', 0, 1, 'current', 'fact-pre-switch', 'signed_get', "
            "'unit:/positionSide/dual', :now_ms, :valid_until_ms, :now_ms)"
        ),
        {"now_ms": NOW_MS, "valid_until_ms": NOW_MS + 60_000},
    )

    payload = evaluate_phase_two_readiness(
        pg_control_connection,
        now_ms=NOW_MS + 1_000,
        allow_capability_enabled=True,
    )

    assert payload["status"] == "phase_two_ready"
    assert payload["blockers"] == []
    assert payload["exchange_read_called"] is False
    assert payload["exchange_write_called"] is False
    assert payload["runtime_state_mutated"] is False


def test_pre_switch_mode_still_rejects_active_lifecycle_risk(pg_control_connection):
    pg_control_connection.execute(
        text(
            "INSERT INTO brc_exchange_account_modes_current ("
            "account_mode_current_id, account_id, exchange_id, runtime_profile_id, "
            "position_mode, dual_side_position, position_mode_safe, status, "
            "fact_snapshot_id, source_kind, source_ref, observed_at_ms, "
            "valid_until_ms, updated_at_ms) VALUES ("
            "'mode-current-risk', 'account-1', 'binance_usdm', 'profile-1', "
            "'one_way', 0, 1, 'current', 'fact-risk', 'signed_get', "
            "'unit:/positionSide/dual', :now_ms, :valid_until_ms, :now_ms)"
        ),
        {"now_ms": NOW_MS, "valid_until_ms": NOW_MS + 60_000},
    )
    _insert_scope_freeze(
        pg_control_connection,
        first_blocker="position_closed_protection_live",
    )

    payload = evaluate_phase_two_readiness(
        pg_control_connection,
        now_ms=NOW_MS + 1_000,
        allow_capability_enabled=True,
    )

    assert payload["status"] == "blocked"
    assert payload["first_blocker"] == "phase_two_active_domain_holds:1"
    assert payload["counts"]["active_domain_holds"] == 1
