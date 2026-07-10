from __future__ import annotations

import json
import os

import pytest
from sqlalchemy import text

from scripts import materialize_ticket_bound_protected_submit_attempt as submit
from scripts import materialize_ticket_bound_runtime_safety_state as safety
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    _create_handoff_ready,
    pg_control_connection,
)


@pytest.fixture(autouse=True)
def runtime_submit_env(monkeypatch):
    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")
    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "order_allowed")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_EXCHANGE_SUBMIT_GATEWAY_BINDING_ENABLED", "true")


def test_protected_submit_attempt_disabled_smoke_records_ticket_bound_pg_attempt(
    pg_control_connection,
):
    ids = _create_handoff_ready(pg_control_connection)
    safety_payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_layer_handoff_id=ids["operation_layer_handoff_id"],
        now_ms=NOW_MS + 3000,
    )
    assert safety_payload["submit_allowed"] is True

    payload = submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="disabled_smoke",
        now_ms=NOW_MS + 4000,
    )

    assert payload["status"] == "disabled_smoke_passed"
    assert payload["ticket_id"] == ids["ticket_id"]
    assert payload["operation_submit_command_id"] == ids["operation_submit_command_id"]
    assert payload["runtime_safety_snapshot_id"] == safety_payload["runtime_safety_snapshot_id"]
    assert payload["submit_allowed"] is True
    assert payload["blockers"] == []
    assert payload["official_operation_layer_submit_called"] is True
    assert payload["exchange_write_called"] is False
    assert payload["order_created"] is False
    assert payload["order_lifecycle_called"] is False
    assert payload["submit_request"]["orders"][0]["order_role"] == "ENTRY"
    assert payload["submit_request"]["orders"][1]["order_role"] == "SL"
    assert payload["submit_request"]["orders"][2]["order_role"] == "TP1"

    row = _protected_submit_row(pg_control_connection)
    assert row["status"] == "disabled_smoke_passed"
    assert row["submit_mode"] == "disabled_smoke"
    assert row["submit_allowed"] in {True, 1}
    assert _json_value(row["blockers"]) == []
    assert _json_value(row["submit_result"])["status"] == (
        "exchange_submit_execution_disabled"
    )


def test_next_protected_submit_attempt_selects_unique_handoff_ready(
    pg_control_connection,
):
    ids = _create_handoff_ready(pg_control_connection)
    safety_payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_layer_handoff_id=ids["operation_layer_handoff_id"],
        now_ms=NOW_MS + 3000,
    )
    assert safety_payload["submit_allowed"] is True

    payload = submit.materialize_next_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        submit_mode="disabled_smoke",
        now_ms=NOW_MS + 4000,
    )

    assert payload["status"] == "disabled_smoke_passed"
    assert payload["ticket_id"] == ids["ticket_id"]
    assert payload["operation_submit_command_id"] == ids["operation_submit_command_id"]
    assert payload["exchange_write_called"] is False
    row = _protected_submit_row(pg_control_connection)
    assert row["operation_submit_command_id"] == ids["operation_submit_command_id"]


def test_next_protected_submit_attempt_noops_without_handoff_ready(
    pg_control_connection,
):
    payload = submit.materialize_next_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        submit_mode="disabled_smoke",
        now_ms=NOW_MS + 4000,
    )

    assert payload["status"] == "no_operation_layer_handoff_ready"
    assert payload["blockers"] == []
    assert payload["next_action"] == "continue_watcher_observation"


def test_next_protected_submit_attempt_ignores_expired_handoff_ticket(
    pg_control_connection,
):
    ids = _create_handoff_ready(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_action_time_tickets
            SET expires_at_ms = :expires_at_ms
            WHERE ticket_id = :ticket_id
            """
        ),
        {
            "expires_at_ms": NOW_MS - 1,
            "ticket_id": ids["ticket_id"],
        },
    )

    payload = submit.materialize_next_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        submit_mode="disabled_smoke",
        now_ms=NOW_MS + 4000,
    )

    assert payload["status"] == "no_operation_layer_handoff_ready"
    assert payload["blockers"] == []


def test_protected_submit_attempt_blocks_without_runtime_safety_snapshot(
    pg_control_connection,
):
    ids = _create_handoff_ready(pg_control_connection)

    payload = submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="disabled_smoke",
        now_ms=NOW_MS + 4000,
    )

    assert payload["status"] == "blocked"
    assert payload["submit_allowed"] is False
    assert "runtime_safety_snapshot_missing" in payload["blockers"]
    row = _protected_submit_row(pg_control_connection)
    assert row["status"] == "blocked"
    assert row["submit_allowed"] in {False, 0}


def test_protected_submit_attempt_rechecks_execution_eligibility(
    pg_control_connection,
):
    ids = _create_handoff_ready(pg_control_connection)
    safety_payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_layer_handoff_id=ids["operation_layer_handoff_id"],
        now_ms=NOW_MS + 3000,
    )
    assert safety_payload["submit_allowed"] is True
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_action_time_tickets
            SET execution_eligible = false
            WHERE ticket_id = :ticket_id
            """
        ),
        {"ticket_id": ids["ticket_id"]},
    )

    payload = submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="disabled_smoke",
        now_ms=NOW_MS + 4000,
    )

    assert payload["status"] == "blocked"
    assert "execution_eligibility_missing_or_false" in payload["blockers"]
    assert payload["submit_allowed"] is False


def test_protected_submit_attempt_rechecks_stop_risk_reservation(
    pg_control_connection,
):
    ids = _create_handoff_ready(pg_control_connection)
    safety_payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_layer_handoff_id=ids["operation_layer_handoff_id"],
        now_ms=NOW_MS + 3000,
    )
    assert safety_payload["submit_allowed"] is True
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_budget_reservations
            SET risk_reservation_basis = 'wrong'
            WHERE ticket_id = :ticket_id
            """
        ),
        {"ticket_id": ids["ticket_id"]},
    )

    payload = submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="disabled_smoke",
        now_ms=NOW_MS + 4000,
    )

    assert payload["status"] == "blocked"
    assert "risk_reservation_basis_missing_or_invalid" in payload["blockers"]
    assert payload["submit_allowed"] is False


def test_protected_submit_attempt_rechecks_stop_risk_protective_side(
    pg_control_connection,
):
    ids = _create_handoff_ready(pg_control_connection)
    safety_payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_layer_handoff_id=ids["operation_layer_handoff_id"],
        now_ms=NOW_MS + 3000,
    )
    assert safety_payload["submit_allowed"] is True
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_budget_reservations
            SET stop_price = 2200,
                risk_at_stop = 2
            WHERE ticket_id = :ticket_id
            """
        ),
        {"ticket_id": ids["ticket_id"]},
    )

    payload = submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="disabled_smoke",
        now_ms=NOW_MS + 4000,
    )

    assert payload["status"] == "blocked"
    assert "risk_reservation_stop_side_not_protective" in payload["blockers"]
    assert payload["submit_allowed"] is False


def test_protected_submit_attempt_refreshes_blocked_after_safety_ready(
    pg_control_connection,
):
    ids = _create_handoff_ready(pg_control_connection)

    blocked = submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="disabled_smoke",
        now_ms=NOW_MS + 4000,
    )
    assert blocked["status"] == "blocked"
    assert blocked["exchange_write_called"] is False
    assert "runtime_safety_snapshot_missing" in blocked["blockers"]

    safety_payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_layer_handoff_id=ids["operation_layer_handoff_id"],
        now_ms=NOW_MS + 5000,
    )
    assert safety_payload["submit_allowed"] is True

    refreshed = submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="disabled_smoke",
        now_ms=NOW_MS + 6000,
    )

    assert refreshed["status"] == "disabled_smoke_passed"
    assert refreshed.get("idempotent_existing_attempt") is None
    assert refreshed["runtime_safety_snapshot_id"] == safety_payload["runtime_safety_snapshot_id"]
    assert refreshed["submit_allowed"] is True
    assert refreshed["blockers"] == []
    row = _protected_submit_row(pg_control_connection)
    assert row["status"] == "disabled_smoke_passed"
    assert row["runtime_safety_snapshot_id"] == safety_payload["runtime_safety_snapshot_id"]
    assert row["created_at_ms"] == NOW_MS + 4000
    assert row["updated_at_ms"] == NOW_MS + 6000


def test_next_protected_submit_attempt_refreshes_existing_blocked_attempt(
    pg_control_connection,
):
    ids = _create_handoff_ready(pg_control_connection)
    blocked = submit.materialize_next_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        submit_mode="disabled_smoke",
        now_ms=NOW_MS + 4000,
    )
    assert blocked["status"] == "blocked"
    assert "runtime_safety_snapshot_missing" in blocked["blockers"]

    safety_payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_layer_handoff_id=ids["operation_layer_handoff_id"],
        now_ms=NOW_MS + 5000,
    )
    assert safety_payload["submit_allowed"] is True

    refreshed = submit.materialize_next_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        submit_mode="disabled_smoke",
        now_ms=NOW_MS + 6000,
    )

    assert refreshed["status"] == "disabled_smoke_passed"
    assert refreshed.get("idempotent_existing_attempt") is None
    assert refreshed["operation_submit_command_id"] == ids["operation_submit_command_id"]
    assert refreshed["runtime_safety_snapshot_id"] == safety_payload["runtime_safety_snapshot_id"]


def test_protected_submit_real_mode_requires_submit_mode_decision(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)

    payload = submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="real_gateway_action",
        now_ms=NOW_MS + 4000,
    )

    assert payload["status"] == "blocked"
    assert "submit_mode_decision_missing_for_real_gateway_action" in payload["blockers"]
    assert payload["exchange_write_called"] is False
    assert payload["order_created"] is False
    assert payload["order_lifecycle_called"] is False


def test_protected_submit_real_result_marks_ticket_and_handoff_submitted(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)

    prepared = _prepare_real_submit(pg_control_connection, ids)
    assert prepared["status"] == "submit_prepared"

    result = submit.record_ticket_bound_protected_submit_result(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        submit_result={
            "status": "exchange_submit_orders_submitted",
            "ticket_id": ids["ticket_id"],
            "operation_submit_command_id": ids["operation_submit_command_id"],
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
            "exchange_write_called": True,
            "order_created": True,
            "order_lifecycle_called": True,
            "withdrawal_or_transfer_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
            "submitted_orders": _submitted_orders(prepared),
        },
        now_ms=NOW_MS + 5000,
    )

    assert result["status"] == "submitted"
    assert result["blockers"] == []
    assert _status(pg_control_connection, "brc_action_time_tickets", "ticket_id", ids["ticket_id"]) == "submitted"
    assert _status(
        pg_control_connection,
        "brc_operation_layer_handoffs",
        "operation_layer_handoff_id",
        ids["operation_layer_handoff_id"],
    ) == "submitted"


def test_protected_submit_result_identity_mismatch_hard_stops(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _prepare_real_submit(pg_control_connection, ids)

    result = submit.record_ticket_bound_protected_submit_result(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        submit_result={
            "status": "exchange_submit_orders_submitted",
            "ticket_id": ids["ticket_id"],
            "operation_submit_command_id": ids["operation_submit_command_id"],
            "strategy_group_id": "SOR-001",
            "symbol": "SOLUSDT",
            "side": "long",
            "exchange_write_called": True,
            "order_created": True,
            "order_lifecycle_called": True,
            "withdrawal_or_transfer_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
            "submitted_orders": [
                {
                    "local_order_id": "not-from-ticket",
                    "exchange_order_id": "exchange-entry-1",
                }
            ],
        },
        now_ms=NOW_MS + 5000,
    )

    assert result["status"] == "hard_stopped"
    assert "submit_result_identity_mismatch:symbol" in result["blockers"]
    assert "submit_result_order_id_not_in_ticket_request" in result["blockers"]
    assert _status(pg_control_connection, "brc_action_time_tickets", "ticket_id", ids["ticket_id"]) == "finalgate_ready"


def test_protected_submit_existing_prepared_attempt_blocks_duplicate_submit(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _prepare_real_submit(pg_control_connection, ids)
    assert prepared["status"] == "submit_prepared"

    repeated = submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="real_gateway_action",
        now_ms=NOW_MS + 5000,
    )

    assert repeated["status"] == "blocked"
    assert repeated["idempotent_existing_attempt"] is True
    assert "protected_submit_attempt_already_prepared" in repeated["blockers"]
    assert "duplicate_submit_risk_requires_reconciliation" in repeated["blockers"]
    assert repeated["next_action"] == (
        "reconcile_existing_submit_prepared_attempt_before_retry"
    )


def test_protected_submit_result_requires_complete_ticket_order_set(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _prepare_real_submit(pg_control_connection, ids)

    result = submit.record_ticket_bound_protected_submit_result(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        submit_result={
            "status": "exchange_submit_orders_submitted",
            "ticket_id": ids["ticket_id"],
            "operation_submit_command_id": ids["operation_submit_command_id"],
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
            "exchange_write_called": True,
            "order_created": True,
            "order_lifecycle_called": True,
            "withdrawal_or_transfer_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
            "submitted_orders": [
                {
                    "local_order_id": prepared["submit_request"]["orders"][0][
                        "local_order_id"
                    ],
                    "exchange_order_id": "exchange-entry-1",
                    "order_role": "ENTRY",
                    "reduce_only": False,
                }
            ],
        },
        now_ms=NOW_MS + 5000,
    )

    assert result["status"] == "hard_stopped"
    assert "submit_result_order_ids_incomplete" in result["blockers"]
    assert _status(pg_control_connection, "brc_action_time_tickets", "ticket_id", ids["ticket_id"]) == "finalgate_ready"


def test_protected_submit_result_requires_identity_fields(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _prepare_real_submit(pg_control_connection, ids)

    result = submit.record_ticket_bound_protected_submit_result(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        submit_result={
            "status": "exchange_submit_orders_submitted",
            "ticket_id": ids["ticket_id"],
            "operation_submit_command_id": ids["operation_submit_command_id"],
            "exchange_write_called": True,
            "order_created": True,
            "order_lifecycle_called": True,
            "withdrawal_or_transfer_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
            "submitted_orders": _submitted_orders(prepared),
        },
        now_ms=NOW_MS + 5000,
    )

    assert result["status"] == "hard_stopped"
    assert "submit_result_identity_missing:strategy_group_id" in result["blockers"]
    assert "submit_result_identity_missing:symbol" in result["blockers"]
    assert "submit_result_identity_missing:side" in result["blockers"]


def test_protected_submit_result_rejects_terminal_entry_status(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _prepare_real_submit(pg_control_connection, ids)
    submitted_orders = _submitted_orders(prepared)
    submitted_orders[0]["status"] = "CANCELED"

    result = submit.record_ticket_bound_protected_submit_result(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        submit_result={
            "status": "exchange_submit_orders_submitted",
            "ticket_id": ids["ticket_id"],
            "operation_submit_command_id": ids["operation_submit_command_id"],
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
            "exchange_write_called": True,
            "order_created": True,
            "order_lifecycle_called": True,
            "withdrawal_or_transfer_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
            "submitted_orders": submitted_orders,
        },
        now_ms=NOW_MS + 5000,
    )

    assert result["status"] == "hard_stopped"
    assert "submit_result_entry_terminal_status" in result["blockers"]
    assert _status(pg_control_connection, "brc_action_time_tickets", "ticket_id", ids["ticket_id"]) == "finalgate_ready"


def test_protected_submit_result_rejects_terminal_protection_order_status(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _prepare_real_submit(pg_control_connection, ids)
    submitted_orders = _submitted_orders(prepared)
    submitted_orders[2]["status"] = "CANCELED"

    result = submit.record_ticket_bound_protected_submit_result(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        submit_result={
            "status": "exchange_submit_orders_submitted",
            "ticket_id": ids["ticket_id"],
            "operation_submit_command_id": ids["operation_submit_command_id"],
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
            "exchange_write_called": True,
            "order_created": True,
            "order_lifecycle_called": True,
            "withdrawal_or_transfer_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
            "submitted_orders": submitted_orders,
        },
        now_ms=NOW_MS + 5000,
    )

    assert result["status"] == "hard_stopped"
    assert "submit_result_tp1_terminal_status" in result["blockers"]
    assert _status(pg_control_connection, "brc_action_time_tickets", "ticket_id", ids["ticket_id"]) == "finalgate_ready"


def test_protected_submit_result_preserves_gateway_failure_blockers(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _prepare_real_submit(pg_control_connection, ids)

    result = submit.record_ticket_bound_protected_submit_result(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        submit_result={
            "status": "runtime_exchange_gateway_unavailable",
            "ticket_id": ids["ticket_id"],
            "operation_submit_command_id": ids["operation_submit_command_id"],
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
            "blockers": ["runtime_exchange_gateway_unavailable"],
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "withdrawal_or_transfer_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
            "submitted_orders": [],
        },
        now_ms=NOW_MS + 5000,
    )

    assert result["status"] == "submit_failed"
    assert result["blockers"] == ["runtime_exchange_gateway_unavailable"]
    assert result["next_action"] == "release_or_expire_ticket_scope_after_submit_failure"
    lifecycle = _lifecycle_row(pg_control_connection)
    assert lifecycle["status"] == "submit_failed"
    assert lifecycle["first_blocker"] == "runtime_exchange_gateway_unavailable"
    assert _status(pg_control_connection, "brc_action_time_tickets", "ticket_id", ids["ticket_id"]) == "finalgate_ready"


def test_protected_submit_result_materializes_protection_missing_after_sl_failure(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _prepare_real_submit(pg_control_connection, ids)
    entry_order = _submitted_orders(prepared)[0]

    result = submit.record_ticket_bound_protected_submit_result(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        submit_result={
            "status": "protection_submit_failed",
            "ticket_id": ids["ticket_id"],
            "operation_submit_command_id": ids["operation_submit_command_id"],
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
            "blockers": ["exchange_submit_failed:sl"],
            "exchange_write_called": True,
            "order_created": True,
            "order_lifecycle_called": True,
            "withdrawal_or_transfer_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
            "submitted_orders": [entry_order],
        },
        now_ms=NOW_MS + 5000,
    )

    assert result["status"] == "submit_failed"
    assert result["next_action"] == "run_official_recovery_submit_sl_or_flatten"
    lifecycle = _lifecycle_row(pg_control_connection)
    assert lifecycle["status"] == "protection_missing"
    assert lifecycle["entry_fill_confirmed"] in {True, 1}
    assert lifecycle["first_blocker"] == "exchange_submit_failed:sl"


def test_protected_submit_result_materializes_protection_degraded_after_tp1_failure(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _prepare_real_submit(pg_control_connection, ids)
    entry_order, sl_order, _tp1_order = _submitted_orders(prepared)

    result = submit.record_ticket_bound_protected_submit_result(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        submit_result={
            "status": "protection_submit_failed",
            "ticket_id": ids["ticket_id"],
            "operation_submit_command_id": ids["operation_submit_command_id"],
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
            "blockers": ["exchange_submit_failed:tp1"],
            "exchange_write_called": True,
            "order_created": True,
            "order_lifecycle_called": True,
            "withdrawal_or_transfer_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
            "submitted_orders": [entry_order, sl_order],
        },
        now_ms=NOW_MS + 5000,
    )

    assert result["status"] == "submit_failed"
    assert result["next_action"] == "run_official_recovery_submit_missing_tp1"
    lifecycle = _lifecycle_row(pg_control_connection)
    assert lifecycle["status"] == "protection_degraded"
    assert lifecycle["entry_fill_confirmed"] in {True, 1}
    assert lifecycle["first_blocker"] == "exchange_submit_failed:tp1"


def test_protected_submit_result_forbidden_effect_hard_stops_without_breaking_db(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _prepare_real_submit(pg_control_connection, ids)

    result = submit.record_ticket_bound_protected_submit_result(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        submit_result={
            "status": "exchange_submit_orders_submitted",
            "ticket_id": ids["ticket_id"],
            "operation_submit_command_id": ids["operation_submit_command_id"],
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
            "exchange_write_called": True,
            "order_created": True,
            "order_lifecycle_called": True,
            "withdrawal_or_transfer_created": False,
            "live_profile_changed": True,
            "order_sizing_changed": False,
            "submitted_orders": _submitted_orders(prepared),
        },
        now_ms=NOW_MS + 5000,
    )

    assert result["status"] == "hard_stopped"
    assert "submit_result_forbidden_effect:live_profile_changed" in result["blockers"]
    row = _protected_submit_row(pg_control_connection)
    assert row["live_profile_changed"] in {False, 0}
    assert _json_value(row["submit_result"])["live_profile_changed"] is True


def test_protected_submit_result_preserves_unknown_outcome_for_reconciliation(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _prepare_real_submit(pg_control_connection, ids)

    result = submit.record_ticket_bound_protected_submit_result(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        submit_result={
            "status": "exchange_submit_outcome_unknown",
            "ticket_id": ids["ticket_id"],
            "operation_submit_command_id": ids["operation_submit_command_id"],
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
            "blockers": ["exchange_command_outcome_unknown"],
            "exchange_write_called": True,
            "order_created": True,
            "order_lifecycle_called": True,
            "submitted_orders": [],
        },
        now_ms=NOW_MS + 5000,
    )

    assert result["status"] == "submit_outcome_unknown"
    assert result["next_action"] == (
        "reconcile_unknown_exchange_command_before_any_new_submit"
    )
    assert _protected_submit_row(pg_control_connection)["status"] == (
        "submit_outcome_unknown"
    )


def _create_ready_protected_submit(conn) -> dict[str, str]:
    ids = _create_handoff_ready(conn)
    safety_payload = safety.materialize_ticket_bound_runtime_safety_state(
        conn,
        ticket_id=ids["ticket_id"],
        operation_layer_handoff_id=ids["operation_layer_handoff_id"],
        now_ms=NOW_MS + 3000,
    )
    assert safety_payload["submit_allowed"] is True
    return ids


def _prepare_real_submit(conn, ids: dict[str, str]) -> dict:
    _ensure_runtime_submit_env()
    decision = submit.materialize_ticket_bound_submit_mode_decision(
        conn,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        production_submit_execution_policy="armed",
        now_ms=NOW_MS + 3500,
    )
    assert decision["decision"] == "real_gateway_action"
    prepared = submit.prepare_ticket_bound_protected_submit_attempt(
        conn,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="real_gateway_action",
        now_ms=NOW_MS + 4000,
    )
    assert prepared["submit_mode_decision_id"] == decision["submit_mode_decision_id"]
    return prepared


def _ensure_runtime_submit_env() -> None:
    os.environ["TRADING_ENV"] = "live"
    os.environ["EXCHANGE_TESTNET"] = "false"
    os.environ["BRC_EXECUTION_PERMISSION_MAX"] = "order_allowed"
    os.environ["RUNTIME_CONTROL_API_ENABLED"] = "false"
    os.environ["RUNTIME_TEST_SIGNAL_INJECTION_ENABLED"] = "false"
    os.environ["RUNTIME_EXCHANGE_SUBMIT_GATEWAY_BINDING_ENABLED"] = "true"


def _protected_submit_row(conn):
    return conn.execute(
        text("SELECT * FROM brc_ticket_bound_protected_submit_attempts")
    ).mappings().one()


def _lifecycle_row(conn):
    row = conn.execute(
        text("SELECT * FROM brc_ticket_bound_order_lifecycle_runs")
    ).mappings().one()
    return {key: _json_value(value) for key, value in dict(row).items()}


def _status(conn, table: str, id_column: str, id_value: str) -> str:
    return str(
        conn.execute(
            text(f"SELECT status FROM {table} WHERE {id_column} = :id_value"),
            {"id_value": id_value},
        ).scalar_one()
    )


def _submitted_orders(prepared: dict) -> list[dict]:
    rows: list[dict] = []
    for order in prepared["submit_request"]["orders"]:
        role = order["order_role"]
        row = {
            "local_order_id": order["local_order_id"],
            "exchange_order_id": f"exchange-{role.lower()}-1",
            "order_role": role,
            "reduce_only": order.get("reduce_only") is True,
            "amount": order["amount"],
            "price": order.get("price") or "",
            "trigger_price": order.get("trigger_price") or "",
        }
        if role == "ENTRY":
            row.update(
                {
                    "status": "FILLED",
                    "filled_qty": order["amount"],
                    "average_exec_price": prepared["submit_request"]["reference_price"],
                }
            )
        rows.append(row)
    return rows


def _json_value(value):
    if isinstance(value, str) and value[:1] in {"[", "{"}:
        return json.loads(value)
    return value
