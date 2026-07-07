from __future__ import annotations

import json

from sqlalchemy import text

from scripts import materialize_ticket_bound_exit_protection_set as exit_protection
from scripts import materialize_ticket_bound_post_submit_closure as closure
from scripts import materialize_ticket_bound_protected_submit_attempt as submit
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_protected_submit_attempt import (
    _create_ready_protected_submit,
    _json_value,
    _submitted_orders,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


def test_post_submit_closure_records_reconciliation_pending_after_submitted_attempt(
    pg_control_connection,
):
    ids, prepared = _submitted_attempt(pg_control_connection)

    payload = closure.materialize_ticket_bound_post_submit_closure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )

    assert payload["status"] == "reconciliation_pending"
    assert payload["ticket_id"] == ids["ticket_id"]
    assert payload["operation_submit_command_id"] == ids["operation_submit_command_id"]
    assert payload["protection_state"] == "submitted"
    assert payload["reconciliation_state"] == "not_checked"
    assert payload["settlement_state"] == "blocked"
    assert payload["review_state"] == "blocked"
    assert payload["first_blocker"] == "post_submit_reconciliation_fact_missing"
    assert payload["exchange_write_called"] is False
    assert payload["order_created"] is False
    assert payload["order_lifecycle_called"] is False

    row = _closure_row(pg_control_connection)
    assert row["status"] == "reconciliation_pending"
    assert row["protected_submit_attempt_id"] == prepared["protected_submit_attempt_id"]
    assert _json_value(row["blockers"]) == ["post_submit_reconciliation_fact_missing"]
    assert len(_json_value(row["submitted_order_refs"])) == 3


def test_post_submit_closure_blocks_when_attempt_not_submitted(
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

    payload = closure.materialize_ticket_bound_post_submit_closure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )

    assert payload["status"] == "blocked"
    assert "protected_submit_attempt_not_submitted:submit_prepared" in payload["blockers"]
    assert payload["reconciliation_state"] == "blocked"
    assert payload["settlement_state"] == "blocked"
    assert payload["review_state"] == "blocked"


def test_post_submit_closure_blocks_without_exit_protection_set(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _record_submitted_attempt(pg_control_connection, ids)

    payload = closure.materialize_ticket_bound_post_submit_closure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )

    assert payload["status"] == "blocked"
    assert payload["protection_state"] == "missing"
    assert "ticket_bound_exit_protection_set_missing" in payload["blockers"]


def test_post_submit_closure_is_idempotent(
    pg_control_connection,
):
    _, prepared = _submitted_attempt(pg_control_connection)
    first = closure.materialize_ticket_bound_post_submit_closure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )
    second = closure.materialize_ticket_bound_post_submit_closure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 7000,
    )

    assert second["status"] == first["status"]
    assert second["idempotent_existing_closure"] is True
    assert second["post_submit_closure_id"] == first["post_submit_closure_id"]


def test_latest_post_submit_closure_noops_without_submitted_attempt(
    pg_control_connection,
):
    payload = closure.materialize_latest_ticket_bound_post_submit_closure(
        pg_control_connection,
        now_ms=NOW_MS + 6000,
    )

    assert payload["status"] == "not_applicable_no_submitted_attempt"
    assert payload["blockers"] == []
    assert payload["next_action"] == "wait_for_ticket_bound_protected_submit"
    assert pg_control_connection.execute(
        text("SELECT COUNT(*) FROM brc_ticket_bound_post_submit_closures")
    ).scalar_one() == 0


def test_latest_post_submit_closure_materializes_newest_unclosed_submitted_attempt(
    pg_control_connection,
):
    _, first = _submitted_attempt(pg_control_connection)
    second = _clone_submitted_attempt(
        pg_control_connection,
        first,
        ticket_suffix="2",
        attempt_offset_ms=1000,
    )
    existing = closure.materialize_ticket_bound_post_submit_closure(
        pg_control_connection,
        protected_submit_attempt_id=first["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )

    payload = closure.materialize_latest_ticket_bound_post_submit_closure(
        pg_control_connection,
        now_ms=NOW_MS + 7000,
    )

    assert existing["protected_submit_attempt_id"] == first["protected_submit_attempt_id"]
    assert payload["status"] == "reconciliation_pending"
    assert payload["protected_submit_attempt_id"] == second["protected_submit_attempt_id"]
    assert "idempotent_existing_closure" not in payload
    assert pg_control_connection.execute(
        text("SELECT COUNT(*) FROM brc_ticket_bound_post_submit_closures")
    ).scalar_one() == 2


def test_latest_post_submit_closure_returns_existing_when_all_submitted_closed(
    pg_control_connection,
):
    _, prepared = _submitted_attempt(pg_control_connection)
    first = closure.materialize_ticket_bound_post_submit_closure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )

    payload = closure.materialize_latest_ticket_bound_post_submit_closure(
        pg_control_connection,
        now_ms=NOW_MS + 7000,
    )

    assert payload["status"] == first["status"]
    assert payload["protected_submit_attempt_id"] == prepared["protected_submit_attempt_id"]
    assert payload["idempotent_existing_closure"] is True
    assert payload["post_submit_closure_id"] == first["post_submit_closure_id"]


def _submitted_attempt(
    conn,
    *,
    attempt_offset_ms: int = 0,
):
    ids = _create_ready_protected_submit(conn)
    prepared = _record_submitted_attempt(conn, ids, attempt_offset_ms=attempt_offset_ms)
    protection = exit_protection.materialize_ticket_bound_exit_protection_set(
        conn,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 5500 + attempt_offset_ms,
    )
    assert protection["status"] == "position_protected"
    return ids, prepared


def _record_submitted_attempt(
    conn,
    ids: dict[str, str],
    *,
    attempt_offset_ms: int = 0,
) -> dict:
    prepared = submit.prepare_ticket_bound_protected_submit_attempt(
        conn,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="real_gateway_action",
        now_ms=NOW_MS + 4000 + attempt_offset_ms,
    )
    submit.record_ticket_bound_protected_submit_result(
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
            "submitted_orders": _submitted_orders(prepared),
        },
        now_ms=NOW_MS + 5000 + attempt_offset_ms,
    )
    return prepared


def _clone_submitted_attempt(
    conn,
    prepared: dict,
    *,
    ticket_suffix: str,
    attempt_offset_ms: int,
) -> dict:
    row = conn.execute(
        text(
            """
            SELECT *
            FROM brc_ticket_bound_protected_submit_attempts
            WHERE protected_submit_attempt_id = :attempt_id
            """
        ),
        {"attempt_id": prepared["protected_submit_attempt_id"]},
    ).mappings().one()
    values = dict(row)
    values["protected_submit_attempt_id"] = (
        f"{prepared['protected_submit_attempt_id']}:{ticket_suffix}"
    )
    values["ticket_id"] = f"{values['ticket_id']}:{ticket_suffix}"
    values["operation_submit_command_id"] = (
        f"{values['operation_submit_command_id']}:{ticket_suffix}"
    )
    values["created_at_ms"] = NOW_MS + 4000 + attempt_offset_ms
    values["updated_at_ms"] = NOW_MS + 5000 + attempt_offset_ms
    submit_request = _json_value(values["submit_request"])
    submit_result = _json_value(values["submit_result"])
    submit_request["ticket_id"] = values["ticket_id"]
    submit_request["operation_submit_command_id"] = values["operation_submit_command_id"]
    submit_result["ticket_id"] = values["ticket_id"]
    submit_result["operation_submit_command_id"] = values["operation_submit_command_id"]
    for order in submit_result.get("submitted_orders", []):
        order["exchange_order_id"] = f"{order['exchange_order_id']}:{ticket_suffix}"
    values["submit_request"] = json.dumps(submit_request, sort_keys=True)
    values["submit_result"] = json.dumps(submit_result, sort_keys=True)
    columns = ", ".join(values)
    placeholders = ", ".join(f":{key}" for key in values)
    conn.execute(
        text(
            f"""
            INSERT INTO brc_ticket_bound_protected_submit_attempts ({columns})
            VALUES ({placeholders})
            """
        ),
        values,
    )
    protection = exit_protection.materialize_ticket_bound_exit_protection_set(
        conn,
        protected_submit_attempt_id=values["protected_submit_attempt_id"],
        now_ms=NOW_MS + 5500 + attempt_offset_ms,
    )
    assert protection["status"] == "position_protected"
    return values


def _closure_row(conn):
    return conn.execute(
        text("SELECT * FROM brc_ticket_bound_post_submit_closures")
    ).mappings().one()
