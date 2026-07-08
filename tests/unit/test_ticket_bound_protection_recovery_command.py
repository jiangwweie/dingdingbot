from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import text

from scripts import materialize_ticket_bound_exit_protection_set as exit_protection
from scripts import materialize_ticket_bound_protected_submit_attempt as submit
from src.application.action_time.protection_recovery_command import (
    execute_ticket_bound_protection_recovery_command,
    prepare_ticket_bound_protection_recovery_command,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_protected_submit_attempt import (
    _create_ready_protected_submit,
    _json_value,
    _submitted_orders,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


@pytest.mark.asyncio
async def test_protection_recovery_submits_missing_sl_and_tp1_then_materializes_proof(
    pg_control_connection,
):
    prepared = _failed_attempt_after_sl_submit_failure(pg_control_connection)
    command = prepare_ticket_bound_protection_recovery_command(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )
    gateway = _FakeRecoveryGateway()

    executed = await execute_ticket_bound_protection_recovery_command(
        pg_control_connection,
        protection_recovery_command_id=command["protection_recovery_command_id"],
        gateway=gateway,
        now_ms=NOW_MS + 7000,
    )
    proof = exit_protection.materialize_ticket_bound_exit_protection_set(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 8000,
    )

    assert command["status"] == "prepared"
    assert [
        order["order_role"]
        for order in command["command"]["command_plan"]["submit_missing_orders"]
    ] == ["SL", "TP1"]
    assert executed["status"] == "result_recorded"
    assert [call["reduce_only"] for call in gateway.place_calls] == [True, True]
    assert [call["order_type"] for call in gateway.place_calls] == [
        "stop_market",
        "limit",
    ]
    assert proof["status"] == "position_protected"
    assert proof["protection_complete"] is True
    assert _attempt_status(pg_control_connection) == "submitted"
    assert _lifecycle_status(pg_control_connection) == "position_protected"
    assert _protection_order_roles(pg_control_connection) == {"SL", "TP1"}


@pytest.mark.asyncio
async def test_protection_recovery_submits_missing_tp1_then_materializes_proof(
    pg_control_connection,
):
    prepared = _failed_attempt_after_tp1_submit_failure(pg_control_connection)
    command = prepare_ticket_bound_protection_recovery_command(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )
    gateway = _FakeRecoveryGateway()

    executed = await execute_ticket_bound_protection_recovery_command(
        pg_control_connection,
        protection_recovery_command_id=command["protection_recovery_command_id"],
        gateway=gateway,
        now_ms=NOW_MS + 7000,
    )
    proof = exit_protection.materialize_ticket_bound_exit_protection_set(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 8000,
    )

    assert command["status"] == "prepared"
    assert [
        order["order_role"]
        for order in command["command"]["command_plan"]["submit_missing_orders"]
    ] == ["TP1"]
    assert executed["status"] == "result_recorded"
    assert len(gateway.place_calls) == 1
    assert gateway.place_calls[0]["order_type"] == "limit"
    assert proof["status"] == "position_protected"
    assert _attempt_status(pg_control_connection) == "submitted"
    assert _lifecycle_status(pg_control_connection) == "position_protected"


@pytest.mark.asyncio
async def test_protection_recovery_submit_failure_stays_hard_stopped(
    pg_control_connection,
):
    prepared = _failed_attempt_after_tp1_submit_failure(pg_control_connection)
    command = prepare_ticket_bound_protection_recovery_command(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )
    gateway = _FakeRecoveryGateway(place_success=False)

    executed = await execute_ticket_bound_protection_recovery_command(
        pg_control_connection,
        protection_recovery_command_id=command["protection_recovery_command_id"],
        gateway=gateway,
        now_ms=NOW_MS + 7000,
    )

    assert executed["status"] == "failed"
    assert executed["blockers"] == ["recovery rejected by test gateway"]
    assert _attempt_status(pg_control_connection) == "submit_failed"
    assert _lifecycle_status(pg_control_connection) == "protection_submit_failed"
    assert _attempt_blockers(pg_control_connection) == [
        "recovery rejected by test gateway"
    ]
    assert _lifecycle_blockers(pg_control_connection) == [
        "recovery rejected by test gateway"
    ]
    assert _recovery_command_status(pg_control_connection) == "failed"


@pytest.mark.asyncio
async def test_protection_recovery_sl_failure_updates_latest_lifecycle_blocker(
    pg_control_connection,
):
    prepared = _failed_attempt_after_sl_submit_failure(pg_control_connection)
    command = prepare_ticket_bound_protection_recovery_command(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )
    gateway = _FakeRecoveryGateway(place_success=False)

    executed = await execute_ticket_bound_protection_recovery_command(
        pg_control_connection,
        protection_recovery_command_id=command["protection_recovery_command_id"],
        gateway=gateway,
        now_ms=NOW_MS + 7000,
    )

    assert executed["status"] == "failed"
    assert _attempt_status(pg_control_connection) == "submit_failed"
    assert _lifecycle_status(pg_control_connection) == "protection_missing"
    assert _attempt_blockers(pg_control_connection) == [
        "recovery rejected by test gateway"
    ]
    assert _lifecycle_blockers(pg_control_connection) == [
        "recovery rejected by test gateway"
    ]


@pytest.mark.asyncio
async def test_partial_protection_recovery_updates_lifecycle_to_narrower_blocker(
    pg_control_connection,
):
    prepared = _failed_attempt_after_sl_submit_failure(pg_control_connection)
    command = prepare_ticket_bound_protection_recovery_command(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )
    gateway = _FakeRecoveryGateway(fail_on_call=2)

    executed = await execute_ticket_bound_protection_recovery_command(
        pg_control_connection,
        protection_recovery_command_id=command["protection_recovery_command_id"],
        gateway=gateway,
        now_ms=NOW_MS + 7000,
    )

    assert executed["status"] == "failed"
    assert len(gateway.place_calls) == 2
    assert _attempt_status(pg_control_connection) == "submit_failed"
    assert _lifecycle_status(pg_control_connection) == "protection_submit_failed"
    assert _submit_result_roles(pg_control_connection) == {"ENTRY", "SL"}
    assert _recovery_command_status(pg_control_connection) == "failed"


def _failed_attempt_after_sl_submit_failure(conn) -> dict:
    ids, prepared, submitted_orders = _prepared_real_submit(conn)
    entry_order = submitted_orders[0]
    result = submit.record_ticket_bound_protected_submit_result(
        conn,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        submit_result=_submit_result(
            ids=ids,
            status="protection_submit_failed",
            blockers=["exchange_submit_failed:sl"],
            submitted_orders=[entry_order],
        ),
        now_ms=NOW_MS + 5000,
    )
    assert result["next_action"] == "run_official_recovery_submit_sl_or_flatten"
    assert _lifecycle_status(conn) == "protection_missing"
    return prepared


def _failed_attempt_after_tp1_submit_failure(conn) -> dict:
    ids, prepared, submitted_orders = _prepared_real_submit(conn)
    entry_order, sl_order, _tp1_order = submitted_orders
    result = submit.record_ticket_bound_protected_submit_result(
        conn,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        submit_result=_submit_result(
            ids=ids,
            status="protection_submit_failed",
            blockers=["exchange_submit_failed:tp1"],
            submitted_orders=[entry_order, sl_order],
        ),
        now_ms=NOW_MS + 5000,
    )
    assert result["next_action"] == (
        "run_official_recovery_submit_missing_protection_or_flatten"
    )
    assert _lifecycle_status(conn) == "protection_submit_failed"
    return prepared


def _prepared_real_submit(conn):
    ids = _create_ready_protected_submit(conn)
    prepared = submit.prepare_ticket_bound_protected_submit_attempt(
        conn,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="real_gateway_action",
        now_ms=NOW_MS + 4000,
    )
    return ids, prepared, _submitted_orders(prepared)


def _submit_result(
    *,
    ids: dict[str, str],
    status: str,
    blockers: list[str],
    submitted_orders: list[dict],
) -> dict:
    return {
        "status": status,
        "ticket_id": ids["ticket_id"],
        "operation_submit_command_id": ids["operation_submit_command_id"],
        "strategy_group_id": "SOR-001",
        "symbol": "ETHUSDT",
        "side": "long",
        "blockers": blockers,
        "exchange_write_called": True,
        "order_created": True,
        "order_lifecycle_called": True,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "submitted_orders": submitted_orders,
    }


def _attempt_status(conn) -> str:
    return str(
        conn.execute(
            text("SELECT status FROM brc_ticket_bound_protected_submit_attempts")
        ).scalar_one()
    )


def _lifecycle_status(conn) -> str:
    return str(
        conn.execute(
            text("SELECT status FROM brc_ticket_bound_order_lifecycle_runs")
        ).scalar_one()
    )


def _recovery_command_status(conn) -> str:
    return str(
        conn.execute(
            text("SELECT status FROM brc_ticket_bound_protection_recovery_commands")
        ).scalar_one()
    )


def _attempt_blockers(conn) -> list[str]:
    value = conn.execute(
        text("SELECT blockers FROM brc_ticket_bound_protected_submit_attempts")
    ).scalar_one()
    return _json_value(value)


def _lifecycle_blockers(conn) -> list[str]:
    value = conn.execute(
        text("SELECT blockers FROM brc_ticket_bound_order_lifecycle_runs")
    ).scalar_one()
    return _json_value(value)


def _protection_order_roles(conn) -> set[str]:
    return {
        str(row["role"])
        for row in conn.execute(
            text("SELECT role FROM brc_ticket_bound_exit_protection_orders")
        ).mappings()
    }


def _submit_result_roles(conn) -> set[str]:
    value = conn.execute(
        text("SELECT submit_result FROM brc_ticket_bound_protected_submit_attempts")
    ).scalar_one()
    return {
        str(order["order_role"])
        for order in _json_value(value)["submitted_orders"]
    }


class _FakeRecoveryGateway:
    def __init__(
        self,
        *,
        place_success: bool = True,
        fail_on_call: int | None = None,
    ) -> None:
        self.place_success = place_success
        self.fail_on_call = fail_on_call
        self.place_calls: list[dict] = []

    async def place_order(self, **kwargs):
        self.place_calls.append(dict(kwargs))
        if not self.place_success or self.fail_on_call == len(self.place_calls):
            return SimpleNamespace(
                is_success=False,
                error_message="recovery rejected by test gateway",
            )
        return SimpleNamespace(
            is_success=True,
            exchange_order_id=f"exchange-recovered-{kwargs['client_order_id']}",
            status="OPEN",
        )
