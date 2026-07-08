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
async def test_runner_mutation_executor_submits_runner_sl_before_canceling_old_sl(
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
    assert gateway.events == [
        "place_order",
        "cancel_order",
    ]
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
    assert payload["result_payload"]["runner_sl_submitted"] is True
    assert payload["result_payload"]["old_sl_cleanup_required"] is True
    assert payload["result_payload"]["exchange_write_called"] is True
    assert gateway.events == [
        "place_order",
        "cancel_order",
    ]
    assert len(gateway.place_calls) == 1
    assert _command_status(pg_control_connection) == "failed"
    assert _command_blockers(pg_control_connection)[0] == (
        "cancel rejected by test gateway"
    )
    assert "old_sl_cancel_not_confirmed" in _command_blockers(pg_control_connection)
    assert _lifecycle_status(pg_control_connection) == "runner_mutation_failed"
    assert _protection_set_status(pg_control_connection) == "runner_mutation_failed"


@pytest.mark.asyncio
async def test_runner_mutation_executor_runner_submit_failure_keeps_old_sl_live(
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
    assert payload["result_payload"]["old_sl_cancelled"] is False
    assert payload["result_payload"]["runner_sl_submitted"] is False
    assert (
        payload["result_payload"]["old_sl_remained_live_until_runner_sl_confirmed"]
        is True
    )
    assert payload["result_payload"]["exchange_write_called"] is True
    assert gateway.cancel_calls == []
    assert len(gateway.place_calls) == 1
    assert _command_status(pg_control_connection) == "failed"
    command_blockers = _command_blockers(pg_control_connection)
    assert command_blockers[0] == "runner submit rejected by test gateway"
    assert "runner_unprotected_after_old_sl_cancelled" not in command_blockers
    assert _lifecycle_status(pg_control_connection) == "runner_mutation_failed"
    assert _protection_set_status(pg_control_connection) == "runner_mutation_failed"
    assert _lifecycle_blockers(pg_control_connection) == command_blockers


@pytest.mark.asyncio
async def test_runner_mutation_executor_rejects_canceled_runner_place_result(
    pg_control_connection,
):
    prepared = _prepared_command(pg_control_connection)
    gateway = _FakeRunnerMutationGateway(place_status="CANCELED")

    payload = await execute_ticket_bound_runner_mutation_command(
        pg_control_connection,
        runner_mutation_command_id=prepared["runner_mutation_command_id"],
        gateway=gateway,
        now_ms=NOW_MS + 8000,
    )

    assert payload["status"] == "failed"
    assert payload["blockers"] == ["runner_sl_submit_not_confirmed"]
    assert payload["result_payload"]["old_sl_cancelled"] is False
    assert payload["result_payload"]["runner_sl_submitted"] is False
    assert gateway.cancel_calls == []
    assert len(gateway.place_calls) == 1
    command_blockers = _command_blockers(pg_control_connection)
    assert command_blockers[0] == "runner_sl_submit_not_confirmed"
    assert "runner_unprotected_after_old_sl_cancelled" not in command_blockers
    assert _lifecycle_status(pg_control_connection) == "runner_mutation_failed"
    assert _protection_set_status(pg_control_connection) == "runner_mutation_failed"


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


@pytest.mark.asyncio
async def test_runner_mutation_executor_blocks_stale_closed_lifecycle_without_exchange(
    pg_control_connection,
):
    prepared = _prepared_command(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_ticket_bound_order_lifecycle_runs
            SET status = 'lifecycle_closed', updated_at_ms = :updated_at_ms
            """
        ),
        {"updated_at_ms": NOW_MS + 7500},
    )
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_ticket_bound_exit_protection_sets
            SET status = 'closed', updated_at_ms = :updated_at_ms
            """
        ),
        {"updated_at_ms": NOW_MS + 7500},
    )
    gateway = _FakeRunnerMutationGateway()

    payload = await execute_ticket_bound_runner_mutation_command(
        pg_control_connection,
        runner_mutation_command_id=prepared["runner_mutation_command_id"],
        gateway=gateway,
        now_ms=NOW_MS + 8000,
    )

    assert payload["status"] == "blocked"
    assert gateway.cancel_calls == []
    assert gateway.place_calls == []
    assert "runner_mutation_stale_lifecycle_status:lifecycle_closed" in payload["blockers"]
    assert "runner_mutation_stale_protection_set_status:closed" in payload["blockers"]
    assert _command_status(pg_control_connection) == "failed"
    assert _lifecycle_status(pg_control_connection) == "lifecycle_closed"
    assert _protection_set_status(pg_control_connection) == "closed"


@pytest.mark.asyncio
async def test_runner_mutation_executor_blocks_when_runner_sl_already_exists(
    pg_control_connection,
):
    prepared = _prepared_command(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_ticket_bound_exit_protection_orders (
                exit_protection_order_id,
                exit_protection_set_id,
                ticket_id,
                role,
                local_order_id,
                exchange_order_id,
                status,
                order_type,
                side,
                qty,
                price,
                trigger_price,
                reduce_only,
                replaces_exit_protection_order_id,
                created_at_ms,
                updated_at_ms
            )
            VALUES (
                'runner-order-existing',
                :set_id,
                :ticket_id,
                'RUNNER_SL',
                'runner-local-existing',
                'runner-exchange-existing',
                'submitted',
                'STOP_MARKET',
                'sell',
                '0.5',
                NULL,
                '100.0',
                1,
                :old_sl_order_id,
                :created_at_ms,
                :updated_at_ms
            )
            """
        ),
        {
            "set_id": prepared["command"]["exit_protection_set_id"],
            "ticket_id": prepared["command"]["ticket_id"],
            "old_sl_order_id": prepared["command"]["old_sl_order_id"],
            "created_at_ms": NOW_MS + 7500,
            "updated_at_ms": NOW_MS + 7500,
        },
    )
    gateway = _FakeRunnerMutationGateway()

    payload = await execute_ticket_bound_runner_mutation_command(
        pg_control_connection,
        runner_mutation_command_id=prepared["runner_mutation_command_id"],
        gateway=gateway,
        now_ms=NOW_MS + 8000,
    )

    assert payload["status"] == "blocked"
    assert payload["blockers"] == ["runner_mutation_stale_runner_sl_already_present"]
    assert gateway.cancel_calls == []
    assert gateway.place_calls == []
    assert _command_status(pg_control_connection) == "failed"


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


def _lifecycle_status(conn) -> str:
    return str(
        conn.execute(
            text("SELECT status FROM brc_ticket_bound_order_lifecycle_runs")
        ).scalar_one()
    )


def _protection_set_status(conn) -> str:
    return str(
        conn.execute(
            text("SELECT status FROM brc_ticket_bound_exit_protection_sets")
        ).scalar_one()
    )


def _lifecycle_blockers(conn) -> list[str]:
    value = conn.execute(
        text("SELECT blockers FROM brc_ticket_bound_order_lifecycle_runs")
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
        place_status: str = "OPEN",
    ) -> None:
        self.cancel_success = cancel_success
        self.place_success = place_success
        self.place_status = place_status
        self.cancel_calls: list[dict] = []
        self.place_calls: list[dict] = []
        self.events: list[str] = []

    async def cancel_order(self, **kwargs):
        self.events.append("cancel_order")
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
        self.events.append("place_order")
        self.place_calls.append(dict(kwargs))
        if not self.place_success:
            return SimpleNamespace(
                is_success=False,
                error_message="runner submit rejected by test gateway",
            )
        return SimpleNamespace(
            is_success=True,
            exchange_order_id=f"exchange-{kwargs['client_order_id']}",
            status=self.place_status,
        )
