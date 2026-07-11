from __future__ import annotations

import pytest
from sqlalchemy import text

from src.application.action_time.runner_mutation_command import (
    prepare_ticket_bound_runner_mutation_command,
)
from src.application.action_time.runner_mutation_executor import (
    execute_ticket_bound_runner_mutation_command,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_runner_protection_adjuster import (
    _mark_tp1_filled,
    _materialized_exit_protection_set,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


class _NoCallGateway:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def place_order(self, **kwargs):
        self.calls.append(dict(kwargs))
        raise AssertionError("legacy runner executor must not call exchange")

    async def cancel_order(self, **kwargs):
        self.calls.append(dict(kwargs))
        raise AssertionError("legacy runner executor must not call exchange")


@pytest.mark.asyncio
async def test_legacy_runner_executor_is_hard_interlocked_before_gateway_io(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    _mark_tp1_filled(pg_control_connection, set_id)
    prepared = prepare_ticket_bound_runner_mutation_command(
        pg_control_connection,
        exit_protection_set_id=set_id,
        now_ms=NOW_MS + 7000,
    )
    gateway = _NoCallGateway()

    payload = await execute_ticket_bound_runner_mutation_command(
        pg_control_connection,
        runner_mutation_command_id=prepared["runner_mutation_command_id"],
        gateway=gateway,
        now_ms=NOW_MS + 8000,
    )

    assert payload["status"] == "blocked"
    assert payload["blockers"] == ["legacy_direct_runner_executor_retired"]
    assert payload["exchange_write_called"] is False
    assert gateway.calls == []
    assert pg_control_connection.execute(
        text(
            "SELECT status FROM brc_ticket_bound_runner_mutation_commands "
            "WHERE runner_mutation_command_id = :command_id"
        ),
        {"command_id": prepared["runner_mutation_command_id"]},
    ).scalar_one() == "prepared"
