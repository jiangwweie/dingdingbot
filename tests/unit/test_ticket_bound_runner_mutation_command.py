from __future__ import annotations

from sqlalchemy import text

from src.application.action_time.runner_mutation_command import (
    prepare_ticket_bound_runner_mutation_command,
    record_ticket_bound_runner_mutation_result,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_runner_protection_adjuster import (
    _mark_tp1_filled,
    _materialized_exit_protection_set,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


def test_runner_mutation_command_waits_for_tp1_fill(pg_control_connection):
    set_id = _materialized_exit_protection_set(pg_control_connection)

    payload = prepare_ticket_bound_runner_mutation_command(
        pg_control_connection,
        exit_protection_set_id=set_id,
        now_ms=NOW_MS + 7000,
    )

    assert payload["status"] == "blocked"
    assert "tp1_not_filled:submitted" in payload["blockers"]
    assert payload["next_action"] == "wait_for_tp1_fill"
    assert _command_count(pg_control_connection) == 0


def test_runner_mutation_command_prepares_official_command_after_tp1_fill(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    _mark_tp1_filled(pg_control_connection, set_id)

    payload = prepare_ticket_bound_runner_mutation_command(
        pg_control_connection,
        exit_protection_set_id=set_id,
        now_ms=NOW_MS + 7000,
    )

    assert payload["status"] == "prepared"
    assert payload["blockers"] == []
    assert payload["next_action"] == (
        "execute_runner_mutation_through_official_operation_path"
    )
    assert payload["command"]["command_plan"]["cancel_old_sl"]["exchange_order_id"]
    assert payload["command"]["command_plan"]["submit_runner_sl"]["reduce_only"] is True
    assert _command_count(pg_control_connection) == 1
    assert _lifecycle_status(pg_control_connection) == "runner_mutation_pending"


def test_runner_mutation_command_is_idempotent(pg_control_connection):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    _mark_tp1_filled(pg_control_connection, set_id)
    first = prepare_ticket_bound_runner_mutation_command(
        pg_control_connection,
        exit_protection_set_id=set_id,
        now_ms=NOW_MS + 7000,
    )

    second = prepare_ticket_bound_runner_mutation_command(
        pg_control_connection,
        exit_protection_set_id=set_id,
        now_ms=NOW_MS + 8000,
    )

    assert second["status"] == "prepared"
    assert second["runner_mutation_command_id"] == first["runner_mutation_command_id"]
    assert second["idempotent_existing_runner_mutation_command"] is True
    assert _command_count(pg_control_connection) == 1


def test_runner_mutation_result_records_official_exchange_refs(pg_control_connection):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    _mark_tp1_filled(pg_control_connection, set_id)
    prepared = prepare_ticket_bound_runner_mutation_command(
        pg_control_connection,
        exit_protection_set_id=set_id,
        now_ms=NOW_MS + 7000,
    )

    payload = record_ticket_bound_runner_mutation_result(
        pg_control_connection,
        runner_mutation_command_id=prepared["runner_mutation_command_id"],
        result_payload={
            "old_sl_cancelled": True,
            "runner_sl_submitted": True,
            "runner_sl_exchange_order_id": "exchange-runner-sl-1",
            "exchange_write_called": True,
            "withdrawal_or_transfer_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
        },
        now_ms=NOW_MS + 8000,
    )

    assert payload["status"] == "result_recorded"
    assert payload["blockers"] == []
    assert payload["next_action"] == (
        "materialize_ticket_bound_runner_protection_adjustment"
    )
    command = _command(pg_control_connection)
    assert command["status"] == "result_recorded"


def _command_count(conn) -> int:
    return int(
        conn.execute(
            text("SELECT count(*) FROM brc_ticket_bound_runner_mutation_commands")
        ).scalar_one()
    )


def _command(conn):
    return dict(
        conn.execute(
            text("SELECT * FROM brc_ticket_bound_runner_mutation_commands")
        ).mappings().one()
    )


def _lifecycle_status(conn) -> str:
    return str(
        conn.execute(
            text("SELECT status FROM brc_ticket_bound_order_lifecycle_runs")
        ).scalar_one()
    )
