from __future__ import annotations

import json

from sqlalchemy import text

from scripts import materialize_ticket_bound_protected_submit_attempt as submit
from scripts import materialize_ticket_bound_runtime_safety_state as safety
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    _create_handoff_ready,
    pg_control_connection,
)


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


def test_protected_submit_real_result_marks_ticket_and_handoff_submitted(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)

    prepared = submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="real_gateway_action",
        now_ms=NOW_MS + 4000,
    )
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
            "submitted_orders": [
                {
                    "local_order_id": prepared["submit_request"]["orders"][0][
                        "local_order_id"
                    ],
                    "exchange_order_id": "exchange-entry-1",
                    "order_role": "ENTRY",
                    "reduce_only": False,
                },
                {
                    "local_order_id": prepared["submit_request"]["orders"][1][
                        "local_order_id"
                    ],
                    "exchange_order_id": "exchange-sl-1",
                    "order_role": "SL",
                    "reduce_only": True,
                },
            ],
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
    prepared = submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="real_gateway_action",
        now_ms=NOW_MS + 4000,
    )

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
    prepared = submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="real_gateway_action",
        now_ms=NOW_MS + 4000,
    )
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
    prepared = submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="real_gateway_action",
        now_ms=NOW_MS + 4000,
    )

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
    prepared = submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="real_gateway_action",
        now_ms=NOW_MS + 4000,
    )

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
            "submitted_orders": [
                {
                    "local_order_id": prepared["submit_request"]["orders"][0][
                        "local_order_id"
                    ],
                    "exchange_order_id": "exchange-entry-1",
                    "order_role": "ENTRY",
                    "reduce_only": False,
                },
                {
                    "local_order_id": prepared["submit_request"]["orders"][1][
                        "local_order_id"
                    ],
                    "exchange_order_id": "exchange-sl-1",
                    "order_role": "SL",
                    "reduce_only": True,
                },
            ],
        },
        now_ms=NOW_MS + 5000,
    )

    assert result["status"] == "hard_stopped"
    assert "submit_result_identity_missing:strategy_group_id" in result["blockers"]
    assert "submit_result_identity_missing:symbol" in result["blockers"]
    assert "submit_result_identity_missing:side" in result["blockers"]


def test_protected_submit_result_preserves_gateway_failure_blockers(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="real_gateway_action",
        now_ms=NOW_MS + 4000,
    )

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
    assert _status(pg_control_connection, "brc_action_time_tickets", "ticket_id", ids["ticket_id"]) == "finalgate_ready"


def test_protected_submit_result_forbidden_effect_hard_stops_without_breaking_db(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="real_gateway_action",
        now_ms=NOW_MS + 4000,
    )

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
            "submitted_orders": [
                {
                    "local_order_id": prepared["submit_request"]["orders"][0][
                        "local_order_id"
                    ],
                    "exchange_order_id": "exchange-entry-1",
                    "order_role": "ENTRY",
                    "reduce_only": False,
                },
                {
                    "local_order_id": prepared["submit_request"]["orders"][1][
                        "local_order_id"
                    ],
                    "exchange_order_id": "exchange-sl-1",
                    "order_role": "SL",
                    "reduce_only": True,
                },
            ],
        },
        now_ms=NOW_MS + 5000,
    )

    assert result["status"] == "hard_stopped"
    assert "submit_result_forbidden_effect:live_profile_changed" in result["blockers"]
    row = _protected_submit_row(pg_control_connection)
    assert row["live_profile_changed"] in {False, 0}
    assert _json_value(row["submit_result"])["live_profile_changed"] is True


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


def _protected_submit_row(conn):
    return conn.execute(
        text("SELECT * FROM brc_ticket_bound_protected_submit_attempts")
    ).mappings().one()


def _status(conn, table: str, id_column: str, id_value: str) -> str:
    return str(
        conn.execute(
            text(f"SELECT status FROM {table} WHERE {id_column} = :id_value"),
            {"id_value": id_value},
        ).scalar_one()
    )


def _json_value(value):
    if isinstance(value, str):
        return json.loads(value)
    return value
