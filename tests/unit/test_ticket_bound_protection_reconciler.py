from __future__ import annotations

from sqlalchemy import text

from scripts import materialize_ticket_bound_runner_protection_adjustment as runner_adjuster
from src.application.action_time.protection_reconciler import (
    reconcile_ticket_bound_exit_protection_set,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_runner_protection_adjuster import (
    _mark_tp1_filled,
    _materialized_exit_protection_set,
    _record_official_runner_mutation_result,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


def test_protection_reconciler_marks_complete_set_reconciled(pg_control_connection):
    set_id = _materialized_exit_protection_set(pg_control_connection)

    payload = reconcile_ticket_bound_exit_protection_set(
        pg_control_connection,
        exit_protection_set_id=set_id,
        exchange_snapshot=_snapshot(pg_control_connection, set_id),
        now_ms=NOW_MS + 9000,
    )

    assert payload["status"] == "reconciled"
    assert payload["blockers"] == []
    protection_set = _one(
        pg_control_connection,
        "brc_ticket_bound_exit_protection_sets",
        "exit_protection_set_id",
        set_id,
    )
    assert protection_set["status"] == "reconciled"
    assert protection_set["reconciled_with_exchange"] in {True, 1}
    assert _lifecycle_status(pg_control_connection) == "position_protected"


def test_protection_reconciler_flags_missing_exchange_sl(pg_control_connection):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    snapshot = _snapshot(pg_control_connection, set_id, omit_roles={"SL"})

    payload = reconcile_ticket_bound_exit_protection_set(
        pg_control_connection,
        exit_protection_set_id=set_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 9000,
    )

    assert payload["status"] == "protection_reconciliation_mismatch"
    assert "sl_exchange_order_missing" in payload["blockers"]
    assert _lifecycle_status(pg_control_connection) == "protection_reconciliation_mismatch"


def test_protection_reconciler_ignores_unrelated_non_reduce_only_open_order(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    snapshot = _snapshot(pg_control_connection, set_id)
    snapshot["open_orders"].append(
        {
            "exchange_order_id": "exchange-unrelated-entry",
            "qty": "0.5",
            "side": "buy",
            "reduce_only": False,
            "status": "open",
        }
    )

    payload = reconcile_ticket_bound_exit_protection_set(
        pg_control_connection,
        exit_protection_set_id=set_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 9000,
    )

    assert payload["status"] == "reconciled"
    assert payload["blockers"] == []
    assert _lifecycle_status(pg_control_connection) == "position_protected"


def test_protection_reconciler_flags_linked_protection_side_mismatch(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    snapshot = _snapshot(pg_control_connection, set_id)
    for order in snapshot["open_orders"]:
        if order["exchange_order_id"] == "exchange-sl-1":
            order["side"] = "buy"

    payload = reconcile_ticket_bound_exit_protection_set(
        pg_control_connection,
        exit_protection_set_id=set_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 9000,
    )

    assert payload["status"] == "protection_reconciliation_mismatch"
    assert "sl_side_mismatch" in payload["blockers"]
    assert _lifecycle_status(pg_control_connection) == "protection_reconciliation_mismatch"


def test_protection_reconciler_flags_linked_protection_qty_exceeds_position(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    snapshot = _snapshot(pg_control_connection, set_id)
    for order in snapshot["open_orders"]:
        if order["exchange_order_id"] == "exchange-sl-1":
            order["qty"] = "9"
    snapshot["position"]["qty"] = "0.5"

    payload = reconcile_ticket_bound_exit_protection_set(
        pg_control_connection,
        exit_protection_set_id=set_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 9000,
    )

    assert payload["status"] == "protection_reconciliation_mismatch"
    assert "sl_qty_exceeds_position" in payload["blockers"]
    assert _lifecycle_status(pg_control_connection) == "protection_reconciliation_mismatch"


def test_protection_reconciler_flags_tp1_fill_without_runner_sl(pg_control_connection):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    _mark_tp1_filled(pg_control_connection, set_id)
    snapshot = _snapshot(pg_control_connection, set_id, omit_roles={"TP1"})
    snapshot["recent_fills"] = [{"exchange_order_id": "exchange-tp1-1"}]
    snapshot["position"]["qty"] = "0.25"

    payload = reconcile_ticket_bound_exit_protection_set(
        pg_control_connection,
        exit_protection_set_id=set_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 9000,
    )

    assert payload["status"] == "runner_mutation_pending"
    assert "tp1_filled_without_runner_sl" in payload["blockers"]
    assert _lifecycle_status(pg_control_connection) == "runner_mutation_pending"


def test_protection_reconciler_accepts_runner_sl_after_old_sl_cancelled(
    pg_control_connection,
):
    set_id = _materialized_runner_protection(pg_control_connection)
    snapshot = _snapshot(pg_control_connection, set_id, omit_roles={"SL", "TP1"})
    snapshot["recent_fills"] = [{"exchange_order_id": "exchange-tp1-1"}]
    snapshot["position"]["qty"] = "0.25"

    payload = reconcile_ticket_bound_exit_protection_set(
        pg_control_connection,
        exit_protection_set_id=set_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 9000,
    )

    assert payload["status"] == "runner_protected"
    assert payload["blockers"] == []
    assert _lifecycle_status(pg_control_connection) == "runner_protected"
    protection_set = _one(
        pg_control_connection,
        "brc_ticket_bound_exit_protection_sets",
        "exit_protection_set_id",
        set_id,
    )
    assert protection_set["status"] == "runner_protected"
    assert protection_set["reconciled_with_exchange"] in {True, 1}


def test_protection_reconciler_flags_old_sl_still_live_after_runner_mutation(
    pg_control_connection,
):
    set_id = _materialized_runner_protection(pg_control_connection)
    snapshot = _snapshot(pg_control_connection, set_id, omit_roles={"TP1"})
    snapshot["recent_fills"] = [{"exchange_order_id": "exchange-tp1-1"}]
    snapshot["position"]["qty"] = "0.25"

    payload = reconcile_ticket_bound_exit_protection_set(
        pg_control_connection,
        exit_protection_set_id=set_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 9000,
    )

    assert payload["status"] == "runner_reconciliation_mismatch"
    assert "old_sl_still_live_after_runner_mutation" in payload["blockers"]
    assert _lifecycle_status(pg_control_connection) == "runner_reconciliation_mismatch"


def test_protection_reconciler_flags_flat_position_with_live_protection(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    snapshot = _snapshot(pg_control_connection, set_id)
    snapshot["position"] = {"qty": "0", "position_flat": True}

    payload = reconcile_ticket_bound_exit_protection_set(
        pg_control_connection,
        exit_protection_set_id=set_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 9000,
    )

    assert payload["status"] == "position_closed_protection_live"
    assert "position_flat_with_live_protection_orders" in payload["blockers"]
    assert _lifecycle_status(pg_control_connection) == "position_closed_protection_live"


def _materialized_runner_protection(conn) -> str:
    set_id = _materialized_exit_protection_set(conn)
    _mark_tp1_filled(conn, set_id)
    _record_official_runner_mutation_result(
        conn,
        set_id,
        runner_exchange_id="exchange-runner-sl-1",
        now_ms=NOW_MS + 7500,
    )
    payload = runner_adjuster.materialize_ticket_bound_runner_protection_adjustment(
        conn,
        exit_protection_set_id=set_id,
        runner_sl_exchange_order_id="exchange-runner-sl-1",
        runner_sl_local_order_id="runner-sl-1",
        now_ms=NOW_MS + 8000,
    )
    assert payload["status"] == "runner_protected"
    return set_id


def _snapshot(conn, set_id: str, *, omit_roles: set[str] | None = None) -> dict:
    omit_roles = omit_roles or set()
    orders = [
        dict(row)
        for row in conn.execute(
            text(
                """
                SELECT role, exchange_order_id, qty, side, reduce_only
                FROM brc_ticket_bound_exit_protection_orders
                WHERE exit_protection_set_id = :set_id
                ORDER BY role
                """
            ),
            {"set_id": set_id},
        ).mappings()
        if row["role"] not in omit_roles
    ]
    return {
        "snapshot_id": f"snapshot:{set_id}",
        "open_orders": [
            {
                "exchange_order_id": row["exchange_order_id"],
                "qty": str(row["qty"]),
                "side": row["side"],
                "reduce_only": row["reduce_only"] in {True, 1},
                "status": "open",
            }
            for row in orders
        ],
        "recent_fills": [],
        "position": {"qty": "0.5", "position_flat": False},
    }


def _one(conn, table_name: str, id_column: str, id_value: str):
    row = conn.execute(
        text(f"SELECT * FROM {table_name} WHERE {id_column} = :id_value"),
        {"id_value": id_value},
    ).mappings().one()
    return dict(row)


def _lifecycle_status(conn) -> str:
    return str(
        conn.execute(
            text("SELECT status FROM brc_ticket_bound_order_lifecycle_runs")
        ).scalar_one()
    )
