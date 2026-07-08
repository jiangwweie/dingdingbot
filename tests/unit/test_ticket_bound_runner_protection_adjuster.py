from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from scripts import materialize_ticket_bound_exit_protection_set as exit_protection
from scripts import materialize_ticket_bound_runner_protection_adjustment as runner_adjuster
from src.application.action_time.runner_mutation_command import (
    prepare_ticket_bound_runner_mutation_command,
    record_ticket_bound_runner_mutation_result,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_exit_protection_materializer import _submitted_attempt
from tests.unit.test_ticket_bound_protected_submit_attempt import _json_value
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


def test_runner_adjuster_waits_before_tp1_fill(pg_control_connection):
    set_id = _materialized_exit_protection_set(pg_control_connection)

    payload = runner_adjuster.materialize_ticket_bound_runner_protection_adjustment(
        pg_control_connection,
        exit_protection_set_id=set_id,
        runner_sl_exchange_order_id="exchange-runner-sl-1",
        now_ms=NOW_MS + 7000,
    )

    assert payload["status"] == "waiting_for_tp1_fill"
    assert "tp1_not_filled:submitted" in payload["blockers"]
    assert _one(pg_control_connection, "brc_ticket_bound_order_lifecycle_runs")[
        "status"
    ] == "position_protected"


def test_runner_adjuster_missing_ref_before_tp1_fill_does_not_block(pg_control_connection):
    set_id = _materialized_exit_protection_set(pg_control_connection)

    payload = runner_adjuster.materialize_ticket_bound_runner_protection_adjustment(
        pg_control_connection,
        exit_protection_set_id=set_id,
        runner_sl_exchange_order_id="",
        now_ms=NOW_MS + 7000,
    )

    assert payload["status"] == "waiting_for_tp1_fill"
    assert "tp1_not_filled:submitted" in payload["blockers"]
    assert "runner_sl_exchange_order_id_required" in payload["blockers"]
    assert _one(pg_control_connection, "brc_ticket_bound_order_lifecycle_runs")[
        "status"
    ] == "position_protected"


def test_runner_adjuster_marks_runner_mutation_pending_without_runner_exchange_ref(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    _mark_tp1_filled(pg_control_connection, set_id)

    payload = runner_adjuster.materialize_ticket_bound_runner_protection_adjustment(
        pg_control_connection,
        exit_protection_set_id=set_id,
        runner_sl_exchange_order_id="",
        now_ms=NOW_MS + 7000,
    )

    assert payload["status"] == "runner_mutation_pending"
    assert "runner_sl_exchange_order_id_required" in payload["blockers"]
    assert _one(pg_control_connection, "brc_ticket_bound_order_lifecycle_runs")[
        "status"
    ] == "runner_mutation_pending"


def test_runner_adjuster_recovers_from_sl_adjust_pending(pg_control_connection):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    _mark_tp1_filled(pg_control_connection, set_id)
    pending = runner_adjuster.materialize_ticket_bound_runner_protection_adjustment(
        pg_control_connection,
        exit_protection_set_id=set_id,
        runner_sl_exchange_order_id="",
        now_ms=NOW_MS + 7000,
    )
    _record_official_runner_mutation_result(
        pg_control_connection,
        set_id,
        runner_exchange_id="exchange-runner-sl-1",
        now_ms=NOW_MS + 7500,
    )

    recovered = runner_adjuster.materialize_ticket_bound_runner_protection_adjustment(
        pg_control_connection,
        exit_protection_set_id=set_id,
        runner_sl_exchange_order_id="exchange-runner-sl-1",
        runner_sl_local_order_id="runner-sl-1",
        now_ms=NOW_MS + 8000,
    )

    assert pending["status"] == "runner_mutation_pending"
    assert recovered["status"] == "runner_protected"
    assert _one(pg_control_connection, "brc_ticket_bound_order_lifecycle_runs")[
        "status"
    ] == "runner_protected"


def test_runner_adjuster_materializes_runner_sl_after_tp1_fill(pg_control_connection):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    _mark_tp1_filled(pg_control_connection, set_id)
    _record_official_runner_mutation_result(
        pg_control_connection,
        set_id,
        runner_exchange_id="exchange-runner-sl-1",
        now_ms=NOW_MS + 6900,
    )

    payload = runner_adjuster.materialize_ticket_bound_runner_protection_adjustment(
        pg_control_connection,
        exit_protection_set_id=set_id,
        runner_sl_exchange_order_id="exchange-runner-sl-1",
        runner_sl_local_order_id="runner-sl-1",
        now_ms=NOW_MS + 7000,
    )

    assert payload["status"] == "runner_protected"
    assert payload["blockers"] == []
    assert payload["runner_order"]["role"] == "RUNNER_SL"
    assert Decimal(str(payload["runner_order"]["qty"])) == Decimal(
        str(
            _one(pg_control_connection, "brc_ticket_bound_exit_protection_sets")[
                "runner_qty"
            ]
        )
    )

    roles = {
        row["role"]: row
        for row in pg_control_connection.execute(
            text("SELECT * FROM brc_ticket_bound_exit_protection_orders")
        ).mappings()
    }
    assert roles["TP1"]["status"] == "filled"
    assert roles["SL"]["status"] == "replaced"
    assert roles["RUNNER_SL"]["status"] == "submitted"
    assert roles["RUNNER_SL"]["replaces_exit_protection_order_id"] == roles["SL"][
        "exit_protection_order_id"
    ]
    assert _one(pg_control_connection, "brc_ticket_bound_order_lifecycle_runs")[
        "status"
    ] == "runner_protected"
    assert _one(pg_control_connection, "brc_ticket_bound_exit_protection_sets")[
        "status"
    ] == "runner_protected"


def test_runner_adjuster_blocks_runner_sl_ref_without_official_mutation_result(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    _mark_tp1_filled(pg_control_connection, set_id)

    payload = runner_adjuster.materialize_ticket_bound_runner_protection_adjustment(
        pg_control_connection,
        exit_protection_set_id=set_id,
        runner_sl_exchange_order_id="exchange-runner-sl-1",
        runner_sl_local_order_id="runner-sl-1",
        now_ms=NOW_MS + 7000,
    )

    assert payload["status"] == "runner_mutation_failed"
    assert "runner_mutation_result_missing" in payload["blockers"]
    assert (
        pg_control_connection.execute(
            text(
                """
                SELECT count(*)
                FROM brc_ticket_bound_exit_protection_orders
                WHERE role = 'RUNNER_SL'
                """
            )
        ).scalar_one()
        == 0
    )
    assert _one(pg_control_connection, "brc_ticket_bound_order_lifecycle_runs")[
        "status"
    ] == "runner_mutation_failed"


def test_runner_adjuster_is_idempotent_after_runner_sl_exists(pg_control_connection):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    _mark_tp1_filled(pg_control_connection, set_id)
    _record_official_runner_mutation_result(
        pg_control_connection,
        set_id,
        runner_exchange_id="exchange-runner-sl-1",
        now_ms=NOW_MS + 6900,
    )
    first = runner_adjuster.materialize_ticket_bound_runner_protection_adjustment(
        pg_control_connection,
        exit_protection_set_id=set_id,
        runner_sl_exchange_order_id="exchange-runner-sl-1",
        runner_sl_local_order_id="runner-sl-1",
        now_ms=NOW_MS + 7000,
    )

    second = runner_adjuster.materialize_ticket_bound_runner_protection_adjustment(
        pg_control_connection,
        exit_protection_set_id=set_id,
        runner_sl_exchange_order_id="exchange-runner-sl-1",
        runner_sl_local_order_id="runner-sl-1",
        now_ms=NOW_MS + 8000,
    )

    assert first["status"] == "runner_protected"
    assert second["status"] == "runner_protected"
    assert second["idempotent_existing_runner_protection"] is True
    assert (
        pg_control_connection.execute(
            text(
                """
                SELECT count(*)
                FROM brc_ticket_bound_exit_protection_orders
                WHERE role = 'RUNNER_SL'
                """
            )
        ).scalar_one()
        == 1
    )


def _materialized_exit_protection_set(conn) -> str:
    _, prepared = _submitted_attempt(conn)
    payload = exit_protection.materialize_ticket_bound_exit_protection_set(
        conn,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )
    assert payload["status"] == "position_protected"
    return str(payload["exit_protection_set_id"])


def _record_official_runner_mutation_result(
    conn,
    set_id: str,
    *,
    runner_exchange_id: str,
    now_ms: int,
) -> None:
    command = prepare_ticket_bound_runner_mutation_command(
        conn,
        exit_protection_set_id=set_id,
        now_ms=now_ms - 100,
    )
    assert command["status"] == "prepared"
    record = record_ticket_bound_runner_mutation_result(
        conn,
        runner_mutation_command_id=command["runner_mutation_command_id"],
        result_payload={
            "runner_mutation_command_id": command["runner_mutation_command_id"],
            "exit_protection_set_id": set_id,
            "ticket_id": command["ticket_id"],
            "old_sl_exchange_order_id": command["command"]["old_sl_exchange_order_id"],
            "old_sl_cancelled": True,
            "runner_sl_submitted": True,
            "runner_sl_exchange_order_id": runner_exchange_id,
            "exchange_write_called": True,
            "withdrawal_or_transfer_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
            "blockers": [],
        },
        now_ms=now_ms,
    )
    assert record["status"] == "result_recorded"


def _mark_tp1_filled(conn, set_id: str) -> None:
    conn.execute(
        text(
            """
            UPDATE brc_ticket_bound_exit_protection_orders
            SET status = 'filled', updated_at_ms = :updated_at_ms
            WHERE exit_protection_set_id = :set_id
              AND role = 'TP1'
            """
        ),
        {"set_id": set_id, "updated_at_ms": NOW_MS + 6500},
    )


def _one(conn, table_name: str):
    row = conn.execute(text(f"SELECT * FROM {table_name}")).mappings().one()
    return {key: _maybe_json_value(value) for key, value in dict(row).items()}


def _maybe_json_value(value):
    if isinstance(value, str) and value[:1] in {"[", "{"}:
        return _json_value(value)
    return value
