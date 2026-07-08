from __future__ import annotations

from types import SimpleNamespace

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


@pytest.mark.asyncio
async def test_runner_mutation_executor_cancels_old_sl_and_submits_runner_sl(
    pg_control_connection,
):
    prepared = _prepared_command(pg_control_connection)
    gateway = _FakeRunnerMutationGateway()

    payload = await execute_ticket_bound_runner_mutation_command(
        pg_control_connection,
        runner_mutation_command_id=prepared["runner_mutation_command_id"],
        gateway=gateway,
        now_ms=NOW_MS + 8000,
    )

    assert payload["status"] == "result_recorded"
    assert payload["blockers"] == []
    assert payload["next_action"] == (
        "materialize_ticket_bound_runner_protection_adjustment"
    )
    assert gateway.cancel_calls == [
        {
            "exchange_order_id": prepared["command"]["old_sl_exchange_order_id"],
            "symbol": prepared["command"]["symbol"],
        }
    ]
    assert len(gateway.place_calls) == 1
    place_call = gateway.place_calls[0]
    assert place_call["symbol"] == prepared["command"]["symbol"]
    assert place_call["order_type"] == "stop_market"
    assert place_call["side"] == prepared["command"]["command_plan"]["submit_runner_sl"][
        "side"
    ]
    assert str(place_call["amount"]) == str(prepared["command"]["runner_qty"])
    assert place_call["trigger_price"] > 0
    assert place_call["reduce_only"] is True
    assert payload["result_payload"]["exchange_write_called"] is True
    assert payload["result_payload"]["withdrawal_or_transfer_created"] is False
    assert payload["result_payload"]["live_profile_changed"] is False
    assert payload["result_payload"]["order_sizing_changed"] is False
    assert _command_status(pg_control_connection) == "result_recorded"


@pytest.mark.asyncio
async def test_runner_mutation_executor_cancel_failure_records_failed_result(
    pg_control_connection,
):
    prepared = _prepared_command(pg_control_connection)
    gateway = _FakeRunnerMutationGateway(cancel_success=False)

    payload = await execute_ticket_bound_runner_mutation_command(
        pg_control_connection,
        runner_mutation_command_id=prepared["runner_mutation_command_id"],
        gateway=gateway,
        now_ms=NOW_MS + 8000,
    )

    assert payload["status"] == "failed"
    assert payload["blockers"] == ["cancel rejected by test gateway"]
    assert payload["result_payload"]["old_sl_cancelled"] is False
    assert payload["result_payload"]["runner_sl_submitted"] is False
    assert payload["result_payload"]["exchange_write_called"] is True
    assert gateway.place_calls == []
    assert _command_status(pg_control_connection) == "failed"
    assert _command_blockers(pg_control_connection)[0] == (
        "cancel rejected by test gateway"
    )


@pytest.mark.asyncio
async def test_runner_mutation_executor_runner_submit_failure_records_failed_result(
    pg_control_connection,
):
    prepared = _prepared_command(pg_control_connection)
    gateway = _FakeRunnerMutationGateway(place_success=False)

    payload = await execute_ticket_bound_runner_mutation_command(
        pg_control_connection,
        runner_mutation_command_id=prepared["runner_mutation_command_id"],
        gateway=gateway,
        now_ms=NOW_MS + 8000,
    )

    assert payload["status"] == "failed"
    assert payload["blockers"] == ["runner submit rejected by test gateway"]
    assert payload["result_payload"]["old_sl_cancelled"] is True
    assert payload["result_payload"]["runner_sl_submitted"] is False
    assert payload["result_payload"]["exchange_write_called"] is True
    assert len(gateway.cancel_calls) == 1
    assert len(gateway.place_calls) == 1
    assert _command_status(pg_control_connection) == "failed"
    assert _command_blockers(pg_control_connection)[0] == (
        "runner submit rejected by test gateway"
    )


@pytest.mark.asyncio
async def test_runner_mutation_executor_missing_command_does_not_call_exchange(
    pg_control_connection,
):
    gateway = _FakeRunnerMutationGateway()

    payload = await execute_ticket_bound_runner_mutation_command(
        pg_control_connection,
        runner_mutation_command_id="missing-command",
        gateway=gateway,
        now_ms=NOW_MS + 8000,
    )

    assert payload["status"] == "blocked"
    assert payload["blockers"] == ["runner_mutation_command_missing"]
    assert gateway.cancel_calls == []
    assert gateway.place_calls == []


@pytest.mark.asyncio
async def test_runner_mutation_executor_non_prepared_command_does_not_call_exchange(
    pg_control_connection,
):
    prepared = _prepared_command(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_ticket_bound_runner_mutation_commands
            SET status = 'failed', first_blocker = 'manual_test_failure'
            WHERE runner_mutation_command_id = :command_id
            """
        ),
        {"command_id": prepared["runner_mutation_command_id"]},
    )
    gateway = _FakeRunnerMutationGateway()

    payload = await execute_ticket_bound_runner_mutation_command(
        pg_control_connection,
        runner_mutation_command_id=prepared["runner_mutation_command_id"],
        gateway=gateway,
        now_ms=NOW_MS + 8000,
    )

    assert payload["status"] == "blocked"
    assert payload["blockers"] == ["runner_mutation_command_not_prepared:failed"]
    assert gateway.cancel_calls == []
    assert gateway.place_calls == []


def _prepared_command(conn) -> dict:
    set_id = _materialized_exit_protection_set(conn)
    _mark_tp1_filled(conn, set_id)
    payload = prepare_ticket_bound_runner_mutation_command(
        conn,
        exit_protection_set_id=set_id,
        now_ms=NOW_MS + 7000,
    )
    assert payload["status"] == "prepared"
    return payload


def _command_status(conn) -> str:
    return str(
        conn.execute(
            text("SELECT status FROM brc_ticket_bound_runner_mutation_commands")
        ).scalar_one()
    )


def _command_blockers(conn) -> list[str]:
    value = conn.execute(
        text("SELECT blockers FROM brc_ticket_bound_runner_mutation_commands")
    ).scalar_one()
    if isinstance(value, list):
        return value
    import json

    return list(json.loads(value))


class _FakeRunnerMutationGateway:
    def __init__(
        self,
        *,
        cancel_success: bool = True,
        place_success: bool = True,
    ) -> None:
        self.cancel_success = cancel_success
        self.place_success = place_success
        self.cancel_calls: list[dict] = []
        self.place_calls: list[dict] = []

    async def cancel_order(self, **kwargs):
        self.cancel_calls.append(dict(kwargs))
        if not self.cancel_success:
            return SimpleNamespace(
                is_success=False,
                error_message="cancel rejected by test gateway",
            )
        return SimpleNamespace(
            is_success=True,
            exchange_order_id=kwargs["exchange_order_id"],
            status="CANCELED",
        )

    async def place_order(self, **kwargs):
        self.place_calls.append(dict(kwargs))
        if not self.place_success:
            return SimpleNamespace(
                is_success=False,
                error_message="runner submit rejected by test gateway",
            )
        return SimpleNamespace(
            is_success=True,
            exchange_order_id=f"exchange-{kwargs['client_order_id']}",
            status="OPEN",
        )
