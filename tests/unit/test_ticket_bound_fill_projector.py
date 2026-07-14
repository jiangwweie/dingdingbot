import json

from sqlalchemy import text

from scripts import materialize_ticket_bound_exit_protection_set as exit_protection
from scripts import materialize_ticket_bound_protected_submit_attempt as submit
from src.application.action_time.ticket_bound_fill_projector import (
    project_ticket_bound_exchange_fills,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_protected_submit_attempt import (
    _create_ready_protected_submit,
    _prepare_real_submit,
    _submitted_orders,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


def test_projector_backfills_missing_tp1_event_for_order_already_marked_filled(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _prepare_real_submit(pg_control_connection, ids)
    orders = _submitted_orders(prepared)
    submit.record_ticket_bound_protected_submit_result(
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
            "submitted_orders": orders,
        },
        now_ms=NOW_MS + 5_000,
    )
    exit_protection.materialize_ticket_bound_exit_protection_set(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6_000,
    )
    tp1 = pg_control_connection.execute(
        text(
            "SELECT exit_protection_order_id, exchange_order_id, qty, price "
            "FROM brc_ticket_bound_exit_protection_orders "
            "WHERE ticket_id = :ticket_id AND role = 'TP1'"
        ),
        {"ticket_id": ids["ticket_id"]},
    ).mappings().one()
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_exit_protection_orders "
            "SET status = 'filled' WHERE exit_protection_order_id = :order_id"
        ),
        {"order_id": tp1["exit_protection_order_id"]},
    )

    result = project_ticket_bound_exchange_fills(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        exchange_snapshot={
            "recent_fills": [
                {
                    "exchange_order_id": tp1["exchange_order_id"],
                    "qty": str(tp1["qty"]),
                    "price": str(tp1["price"]),
                    "fee": {"cost": "0.0059432", "currency": "USDT"},
                    "timestamp_ms": NOW_MS + 7_000,
                }
            ]
        },
        now_ms=NOW_MS + 7_000,
    )

    assert result["status"] == "fills_projected"
    assert result["projected_roles"] == ["TP1"]
    event = pg_control_connection.execute(
        text(
            "SELECT event_payload FROM brc_ticket_bound_lifecycle_events "
            "WHERE ticket_id = :ticket_id AND event_type = 'tp1_filled'"
        ),
        {"ticket_id": ids["ticket_id"]},
    ).mappings().one()
    payload = event["event_payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    assert payload["fill"]["fee"] == {
        "cost": "0.0059432",
        "currency": "USDT",
    }
