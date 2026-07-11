from __future__ import annotations

import pytest

from scripts import materialize_ticket_bound_protected_submit_attempt as submit
from src.application.action_time.protection_recovery_command import (
    execute_ticket_bound_protection_recovery_command,
    prepare_ticket_bound_protection_recovery_command,
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


class _NoCallGateway:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def place_order(self, **kwargs):
        self.calls.append(dict(kwargs))
        raise AssertionError("legacy recovery executor must not call exchange")


@pytest.mark.asyncio
async def test_legacy_protection_recovery_executor_is_hard_interlocked_before_gateway_io(
    pg_control_connection,
):
    prepared = _failed_attempt_after_sl_submit_failure(pg_control_connection)
    command = prepare_ticket_bound_protection_recovery_command(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )
    gateway = _NoCallGateway()

    payload = await execute_ticket_bound_protection_recovery_command(
        pg_control_connection,
        protection_recovery_command_id=command["protection_recovery_command_id"],
        gateway=gateway,
        now_ms=NOW_MS + 7000,
    )

    assert command["status"] == "prepared"
    assert payload["status"] == "blocked"
    assert payload["blockers"] == [
        "legacy_direct_protection_recovery_executor_retired"
    ]
    assert payload["exchange_write_called"] is False
    assert gateway.calls == []


def _failed_attempt_after_sl_submit_failure(conn) -> dict:
    ids = _create_ready_protected_submit(conn)
    prepared = _prepare_real_submit(conn, ids)
    entry_order = _submitted_orders(prepared)[0]
    result = submit.record_ticket_bound_protected_submit_result(
        conn,
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
    assert result["next_action"] == "run_official_recovery_submit_sl_or_flatten"
    return prepared
