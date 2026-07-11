from __future__ import annotations

import pytest

from src.application.action_time.orphan_protection_cleanup_command import (
    execute_ticket_bound_orphan_protection_cleanup_command,
    prepare_ticket_bound_orphan_protection_cleanup_command,
)
from src.application.action_time.protection_reconciler import (
    reconcile_ticket_bound_exit_protection_set,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_protection_reconciler import (
    _materialized_exit_protection_set,
    _snapshot,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


class _NoCallGateway:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def cancel_order(self, **kwargs):
        self.calls.append(dict(kwargs))
        raise AssertionError("legacy cleanup executor must not call exchange")


@pytest.mark.asyncio
async def test_legacy_orphan_cleanup_executor_is_hard_interlocked_before_gateway_io(
    pg_control_connection,
):
    set_id = _flat_position_live_protection(pg_control_connection)
    prepared = prepare_ticket_bound_orphan_protection_cleanup_command(
        pg_control_connection,
        exit_protection_set_id=set_id,
        now_ms=NOW_MS + 10_000,
    )
    gateway = _NoCallGateway()

    payload = await execute_ticket_bound_orphan_protection_cleanup_command(
        pg_control_connection,
        orphan_protection_cleanup_command_id=prepared[
            "orphan_protection_cleanup_command_id"
        ],
        gateway=gateway,
        now_ms=NOW_MS + 11_000,
    )

    assert prepared["status"] == "prepared"
    assert payload["status"] == "blocked"
    assert payload["blockers"] == ["legacy_direct_orphan_cleanup_executor_retired"]
    assert payload["exchange_write_called"] is False
    assert gateway.calls == []


def _flat_position_live_protection(conn) -> str:
    set_id = _materialized_exit_protection_set(conn)
    snapshot = _snapshot(conn, set_id)
    snapshot["position"] = {
        "qty": "0",
        "position_flat": True,
        "complete": True,
    }
    payload = reconcile_ticket_bound_exit_protection_set(
        conn,
        exit_protection_set_id=set_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 9000,
    )
    assert payload["status"] == "position_closed_protection_live"
    return set_id
