from __future__ import annotations

from sqlalchemy import text

from scripts import materialize_ticket_bound_post_submit_closure as closure
from scripts import materialize_ticket_bound_protected_submit_attempt as submit
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_protected_submit_attempt import (
    _create_ready_protected_submit,
    _json_value,
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
    assert len(_json_value(row["submitted_order_refs"])) == 2


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


def _submitted_attempt(conn):
    ids = _create_ready_protected_submit(conn)
    prepared = submit.prepare_ticket_bound_protected_submit_attempt(
        conn,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="real_gateway_action",
        now_ms=NOW_MS + 4000,
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
    return ids, prepared


def _closure_row(conn):
    return conn.execute(
        text("SELECT * FROM brc_ticket_bound_post_submit_closures")
    ).mappings().one()
