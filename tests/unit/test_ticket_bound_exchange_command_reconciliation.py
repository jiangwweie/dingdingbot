from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import text

from src.application.action_time.exchange_command import (
    mark_exchange_command_dispatching,
    record_exchange_command_outcome,
)
from src.application.action_time.exchange_command_reconciliation import (
    reconcile_unknown_exchange_commands,
    run_one_unknown_exchange_command_reconciliation,
)
from src.domain.ticket_bound_exchange_command import (
    ExchangeCommandOutcomeClass,
    ExchangeCommandState,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_protected_submit_attempt import (
    _create_ready_protected_submit,
    _prepare_real_submit,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


@pytest.mark.asyncio
async def test_unknown_command_reconciles_submitted_by_client_order_id(
    pg_control_connection,
):
    command = _unknown_entry_command(pg_control_connection)
    gateway = _LookupGateway(
        SimpleNamespace(
            exchange_order_id="exchange-123",
            client_order_id=command["client_order_id"],
            symbol=command["gateway_symbol"],
        )
    )

    report = await reconcile_unknown_exchange_commands(
        pg_control_connection,
        gateway=gateway,
        now_ms=NOW_MS + 5000,
        max_commands=10,
    )

    assert report["reconciled_submitted"] == 1
    assert _command_state(pg_control_connection) == "reconciled_submitted"
    assert gateway.calls == [
        (command["client_order_id"], command["gateway_symbol"])
    ]
    assert gateway.place_order_calls == 0


@pytest.mark.asyncio
async def test_unknown_command_reconciles_absent_after_visibility_window(
    pg_control_connection,
):
    _unknown_entry_command(pg_control_connection)
    gateway = _LookupGateway(None)

    report = await reconcile_unknown_exchange_commands(
        pg_control_connection,
        gateway=gateway,
        now_ms=NOW_MS + 40_000,
        max_commands=10,
    )

    assert report["reconciled_absent"] == 1
    assert _command_state(pg_control_connection) == "reconciled_absent"
    assert report["automatic_resubmit_called"] is False
    assert gateway.place_order_calls == 0


@pytest.mark.asyncio
async def test_unknown_command_stays_pending_inside_visibility_window(
    pg_control_connection,
):
    _unknown_entry_command(pg_control_connection)

    report = await reconcile_unknown_exchange_commands(
        pg_control_connection,
        gateway=_LookupGateway(None),
        now_ms=NOW_MS + 10_000,
        max_commands=10,
    )

    assert report["pending_visibility"] == 1
    assert _command_state(pg_control_connection) == "outcome_unknown"


@pytest.mark.asyncio
async def test_contradictory_client_identity_hard_stops_command(
    pg_control_connection,
):
    command = _unknown_entry_command(pg_control_connection)
    gateway = _LookupGateway(
        SimpleNamespace(
            exchange_order_id="exchange-wrong",
            client_order_id="different-client-id",
            symbol=command["gateway_symbol"],
        )
    )

    report = await reconcile_unknown_exchange_commands(
        pg_control_connection,
        gateway=gateway,
        now_ms=NOW_MS + 5000,
        max_commands=10,
    )

    assert report["hard_stopped"] == 1
    assert _command_state(pg_control_connection) == "hard_stopped"


@pytest.mark.asyncio
async def test_production_reconciliation_worker_commits_around_lookup(
    pg_control_connection,
):
    command = _unknown_entry_command(pg_control_connection)
    pg_control_connection.commit()
    gateway = _LookupGateway(
        SimpleNamespace(
            exchange_order_id="exchange-safe-worker",
            client_order_id=command["client_order_id"],
            symbol=command["gateway_symbol"],
        )
    )

    report = await run_one_unknown_exchange_command_reconciliation(
        pg_control_connection.engine,
        gateway=gateway,
        now_ms=NOW_MS + 5000,
    )

    assert report["status"] == "reconciled_submitted"
    assert report["exchange_read_called"] is True
    assert report["exchange_write_called"] is False
    assert _command_state(pg_control_connection) == "reconciled_submitted"


def _unknown_entry_command(conn) -> dict:
    ids = _create_ready_protected_submit(conn)
    _prepare_real_submit(conn, ids)
    command = dict(
        conn.execute(
            text(
                "SELECT * FROM brc_ticket_bound_exchange_commands "
                "WHERE order_role = 'ENTRY'"
            )
        ).mappings().one()
    )
    mark_exchange_command_dispatching(
        conn,
        exchange_command_id=command["exchange_command_id"],
        now_ms=NOW_MS + 1000,
    )
    record_exchange_command_outcome(
        conn,
        exchange_command_id=command["exchange_command_id"],
        target_state=ExchangeCommandState.OUTCOME_UNKNOWN,
        outcome_class=ExchangeCommandOutcomeClass.NETWORK_AMBIGUOUS,
        exchange_result={"error_code": "C-001", "error_message": "timeout"},
        now_ms=NOW_MS + 2000,
    )
    return command


def _command_state(conn) -> str:
    return str(
        conn.execute(
            text(
                "SELECT command_state FROM brc_ticket_bound_exchange_commands "
                "WHERE order_role = 'ENTRY'"
            )
        ).scalar_one()
    )


class _LookupGateway:
    def __init__(self, result) -> None:
        self.runtime_account_id = "owner-subaccount-runtime-v0"
        self.runtime_exchange_id = "binance_usdm"
        self.result = result
        self.calls: list[tuple[str, str]] = []
        self.place_order_calls = 0

    async def find_order_by_client_id(self, client_order_id: str, symbol: str):
        self.calls.append((client_order_id, symbol))
        return self.result

    async def place_order(self, **_kwargs):
        self.place_order_calls += 1
        raise AssertionError("unknown reconciliation must never resubmit")
