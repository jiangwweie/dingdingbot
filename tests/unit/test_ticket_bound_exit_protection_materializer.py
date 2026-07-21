from __future__ import annotations

# ruff: noqa: F401, F811

from sqlalchemy import text

from scripts import materialize_ticket_bound_exit_protection_set as exit_protection
from scripts import materialize_ticket_bound_protected_submit_attempt as submit
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_protected_submit_attempt import (
    _create_ready_protected_submit,
    _prepare_real_submit,
    _json_value,
    _submitted_orders,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


def test_exit_protection_materializes_sl_and_tp1_after_entry_fill(
    pg_control_connection,
):
    ids, prepared = _submitted_attempt(pg_control_connection)

    payload = exit_protection.materialize_ticket_bound_exit_protection_set(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )

    assert payload["status"] == "position_protected"
    assert payload["protection_complete"] is True
    assert payload["blockers"] == []

    lifecycle = _one(pg_control_connection, "brc_ticket_bound_order_lifecycle_runs")
    assert lifecycle["status"] == "position_protected"
    assert lifecycle["entry_fill_confirmed"] in {True, 1}
    assert lifecycle["exit_protection_set_id"] == payload["exit_protection_set_id"]

    protection_set = _one(pg_control_connection, "brc_ticket_bound_exit_protection_sets")
    assert protection_set["status"] == "submitted"
    assert protection_set["protection_complete"] in {True, 1}
    assert protection_set["sl_order_id"]
    assert protection_set["tp1_order_id"]

    roles = {
        row["role"]
        for row in pg_control_connection.execute(
            text("SELECT role FROM brc_ticket_bound_exit_protection_orders")
        ).mappings()
    }
    assert roles == {"SL", "TP1"}


def test_exit_protection_blocks_before_entry_fill(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _submitted_attempt_with_orders(
        pg_control_connection,
        ids,
        submitted_orders_mutator=lambda orders: [
            {
                **order,
                "status": "NEW" if order["order_role"] == "ENTRY" else order.get("status", ""),
                "filled_qty": "" if order["order_role"] == "ENTRY" else order.get("filled_qty", ""),
                "average_exec_price": ""
                if order["order_role"] == "ENTRY"
                else order.get("average_exec_price", ""),
            }
            for order in orders
        ],
    )

    payload = exit_protection.materialize_ticket_bound_exit_protection_set(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )

    assert payload["status"] == "entry_fill_pending"
    assert "entry_status_not_filled:new" in payload["blockers"]
    assert "entry_filled_qty_missing" in payload["blockers"]
    assert payload["exit_protection_set_id"] is None
    assert _one(pg_control_connection, "brc_ticket_bound_order_lifecycle_runs")[
        "status"
    ] == "entry_fill_pending"


def test_exit_protection_blocks_unresized_partial_entry_protection(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _submitted_attempt_with_orders(
        pg_control_connection,
        ids,
        submitted_orders_mutator=lambda orders: [
            {
                **order,
                "filled_qty": str(float(order["amount"]) / 2)
                if order["order_role"] == "ENTRY"
                else order.get("filled_qty", ""),
            }
            for order in orders
        ],
    )

    payload = exit_protection.materialize_ticket_bound_exit_protection_set(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )

    assert payload["status"] == "protection_reconciliation_mismatch"
    assert "partial_entry_sl_qty_not_actual_fill" in payload["blockers"]
    assert _one(pg_control_connection, "brc_ticket_bound_order_lifecycle_runs")[
        "status"
    ] == "protection_reconciliation_mismatch"


def test_exit_protection_blocks_without_tp1(
    pg_control_connection,
):
    _, prepared = _submitted_attempt(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_ticket_bound_exchange_commands
            SET command_state = 'reconciled_absent',
                outcome_class = 'reconciled_absence', exchange_order_id = NULL
            WHERE protected_submit_attempt_id = :attempt_id AND order_role = 'TP1'
            """
        ),
        {"attempt_id": prepared["protected_submit_attempt_id"]},
    )

    payload = exit_protection.materialize_ticket_bound_exit_protection_set(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )

    assert payload["status"] == "protection_degraded"
    assert "tp1_exchange_order_missing" in payload["blockers"]
    lifecycle = _one(pg_control_connection, "brc_ticket_bound_order_lifecycle_runs")
    assert lifecycle["status"] == "protection_degraded"
    assert lifecycle["entry_fill_confirmed"] in {True, 1}


def test_exit_protection_classifies_missing_sl_as_protection_missing(
    pg_control_connection,
):
    _, prepared = _submitted_attempt(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_ticket_bound_exchange_commands
            SET command_state = 'reconciled_absent',
                outcome_class = 'reconciled_absence', exchange_order_id = NULL
            WHERE protected_submit_attempt_id = :attempt_id AND order_role = 'SL'
            """
        ),
        {"attempt_id": prepared["protected_submit_attempt_id"]},
    )

    payload = exit_protection.materialize_ticket_bound_exit_protection_set(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )

    assert payload["status"] == "protection_missing"
    assert "sl_exchange_order_missing" in payload["blockers"]
    assert _one(pg_control_connection, "brc_ticket_bound_order_lifecycle_runs")[
        "status"
    ] == "protection_missing"


def _submitted_attempt(conn):
    ids = _create_ready_protected_submit(conn)
    prepared = _submitted_attempt_with_orders(conn, ids)
    return ids, prepared


def _submitted_attempt_with_orders(
    conn,
    ids: dict[str, str],
    *,
    submitted_orders_mutator=None,
) -> dict:
    prepared = _prepare_real_submit(conn, ids)
    submitted_orders = _submitted_orders(prepared)
    if submitted_orders_mutator:
        submitted_orders = submitted_orders_mutator(submitted_orders)
    result = submit.record_ticket_bound_protected_submit_result(
        conn,
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
    assert result["status"] == "submitted"
    return prepared


def _one(conn, table_name: str):
    row = conn.execute(text(f"SELECT * FROM {table_name}")).mappings().one()
    return {key: _maybe_json_value(value) for key, value in dict(row).items()}


def _maybe_json_value(value):
    if isinstance(value, str) and value[:1] in {"[", "{"}:
        return _json_value(value)
    return value


def _json_dumps(value) -> str:
    import json

    return json.dumps(value, sort_keys=True)
