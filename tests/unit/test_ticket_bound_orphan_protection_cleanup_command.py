from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import text

from src.application.action_time.orphan_protection_cleanup_command import (
    execute_ticket_bound_orphan_protection_cleanup_command,
    prepare_ticket_bound_orphan_protection_cleanup_command,
)
from src.application.action_time.capital_safety_guard import current_scope_blockers
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


@pytest.mark.asyncio
async def test_orphan_protection_cleanup_cancels_linked_live_protection_orders(
    pg_control_connection,
):
    set_id = _flat_position_live_protection(pg_control_connection)
    _insert_scope_freeze(pg_control_connection, first_blocker="position_closed_protection_live")
    command = prepare_ticket_bound_orphan_protection_cleanup_command(
        pg_control_connection,
        exit_protection_set_id=set_id,
        now_ms=NOW_MS + 10_000,
    )
    gateway = _FakeCleanupGateway()

    executed = await execute_ticket_bound_orphan_protection_cleanup_command(
        pg_control_connection,
        orphan_protection_cleanup_command_id=command[
            "orphan_protection_cleanup_command_id"
        ],
        gateway=gateway,
        now_ms=NOW_MS + 11_000,
    )

    assert command["status"] == "prepared"
    assert [order["role"] for order in command["command"]["command_plan"]["cancel_orders"]] == [
        "SL",
        "TP1",
    ]
    assert executed["status"] == "result_recorded"
    assert [call["exchange_order_id"] for call in gateway.cancel_calls] == [
        "exchange-sl-1",
        "exchange-tp1-1",
    ]
    assert _lifecycle_row(pg_control_connection)["status"] == "reconciliation_matched"
    assert _lifecycle_row(pg_control_connection)["first_blocker"] is None
    assert _protection_set_row(pg_control_connection)["status"] == "closed"
    assert _protection_order_statuses(pg_control_connection) == {
        "SL": "cancelled",
        "TP1": "cancelled",
    }
    freeze = dict(
        pg_control_connection.execute(
            text("SELECT * FROM brc_ticket_bound_scope_freezes")
        ).mappings().one()
    )
    assert freeze["status"] == "resolved"
    assert freeze["first_blocker"] == "scope_cleanup_pending_no_current_risk"
    assert (
        current_scope_blockers(
            {"ticket_bound_scope_freezes": [freeze]},
            strategy_group_id="SOR-001",
            symbol="ETHUSDT",
            side="long",
        )
        == []
    )


@pytest.mark.asyncio
async def test_orphan_protection_cleanup_blocks_before_flat_proof_without_exchange(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    command = prepare_ticket_bound_orphan_protection_cleanup_command(
        pg_control_connection,
        exit_protection_set_id=set_id,
        now_ms=NOW_MS + 10_000,
    )
    gateway = _FakeCleanupGateway()

    executed = await execute_ticket_bound_orphan_protection_cleanup_command(
        pg_control_connection,
        orphan_protection_cleanup_command_id="missing-command",
        gateway=gateway,
        now_ms=NOW_MS + 11_000,
    )

    assert command["status"] == "blocked"
    assert command["blockers"] == [
        "lifecycle_status_not_cleanup_recoverable:position_protected",
        "exit_protection_set_status_not_cleanup_recoverable:submitted",
        "position_flat_live_protection_blocker_missing",
    ]
    assert executed["status"] == "blocked"
    assert gateway.cancel_calls == []


@pytest.mark.asyncio
async def test_orphan_protection_cleanup_cancel_failure_stays_fail_closed(
    pg_control_connection,
):
    set_id = _flat_position_live_protection(pg_control_connection)
    command = prepare_ticket_bound_orphan_protection_cleanup_command(
        pg_control_connection,
        exit_protection_set_id=set_id,
        now_ms=NOW_MS + 10_000,
    )
    gateway = _FakeCleanupGateway(cancel_success=False)

    executed = await execute_ticket_bound_orphan_protection_cleanup_command(
        pg_control_connection,
        orphan_protection_cleanup_command_id=command[
            "orphan_protection_cleanup_command_id"
        ],
        gateway=gateway,
        now_ms=NOW_MS + 11_000,
    )

    assert executed["status"] == "failed"
    assert executed["blockers"] == ["cleanup rejected by test gateway"]
    assert _cleanup_command_row(pg_control_connection)["status"] == "failed"
    assert _lifecycle_row(pg_control_connection)["status"] == "position_closed_protection_live"
    assert _lifecycle_row(pg_control_connection)["first_blocker"] == (
        "cleanup rejected by test gateway"
    )


@pytest.mark.asyncio
async def test_orphan_protection_cleanup_stale_scope_does_not_call_exchange(
    pg_control_connection,
):
    set_id = _flat_position_live_protection(pg_control_connection)
    command = prepare_ticket_bound_orphan_protection_cleanup_command(
        pg_control_connection,
        exit_protection_set_id=set_id,
        now_ms=NOW_MS + 10_000,
    )
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_ticket_bound_exit_protection_orders
            SET status = 'cancelled', updated_at_ms = :updated_at_ms
            WHERE role = 'TP1'
            """
        ),
        {"updated_at_ms": NOW_MS + 10_500},
    )
    gateway = _FakeCleanupGateway()

    executed = await execute_ticket_bound_orphan_protection_cleanup_command(
        pg_control_connection,
        orphan_protection_cleanup_command_id=command[
            "orphan_protection_cleanup_command_id"
        ],
        gateway=gateway,
        now_ms=NOW_MS + 11_000,
    )

    assert executed["status"] == "blocked"
    assert executed["blockers"] == ["orphan_cleanup_stale_cancel_scope_changed"]
    assert gateway.cancel_calls == []
    assert _cleanup_command_row(pg_control_connection)["status"] == "failed"


def _flat_position_live_protection(conn) -> str:
    set_id = _materialized_exit_protection_set(conn)
    snapshot = _snapshot(conn, set_id)
    snapshot["position"] = {"qty": "0", "position_flat": True}
    payload = reconcile_ticket_bound_exit_protection_set(
        conn,
        exit_protection_set_id=set_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 9000,
    )
    assert payload["status"] == "position_closed_protection_live"
    return set_id


def _lifecycle_row(conn) -> dict:
    return dict(
        conn.execute(
            text("SELECT * FROM brc_ticket_bound_order_lifecycle_runs")
        ).mappings().one()
    )


def _protection_set_row(conn) -> dict:
    return dict(
        conn.execute(
            text("SELECT * FROM brc_ticket_bound_exit_protection_sets")
        ).mappings().one()
    )


def _cleanup_command_row(conn) -> dict:
    return dict(
        conn.execute(
            text("SELECT * FROM brc_ticket_bound_orphan_protection_cleanup_commands")
        ).mappings().one()
    )


def _protection_order_statuses(conn) -> dict[str, str]:
    return {
        str(row["role"]): str(row["status"])
        for row in conn.execute(
            text(
                """
                SELECT role, status
                FROM brc_ticket_bound_exit_protection_orders
                ORDER BY role
                """
            )
        ).mappings()
    }


def _insert_scope_freeze(conn, *, first_blocker: str) -> None:
    conn.execute(
        text(
            """
            INSERT INTO brc_ticket_bound_scope_freezes (
              scope_freeze_id, strategy_group_id, symbol, side, status,
              source_kind, source_id, first_blocker, blockers, freeze_scope,
              next_action, authority_boundary, created_at_ms, updated_at_ms
            ) VALUES (
              'freeze:SOR-001:ETHUSDT:long', 'SOR-001', 'ETHUSDT', 'long', 'active',
              'unit_test', 'unit_test_freeze', :first_blocker, :blockers,
              :freeze_scope, 'repair_scope', 'unit_test', :now_ms, :now_ms
            )
            """
        ),
        {
            "first_blocker": first_blocker,
            "blockers": f'["{first_blocker}"]',
            "freeze_scope": (
                '{"strategy_group_id":"SOR-001","symbol":"ETHUSDT","side":"long"}'
            ),
            "now_ms": NOW_MS + 9500,
        },
    )


class _FakeCleanupGateway:
    def __init__(self, *, cancel_success: bool = True):
        self.cancel_success = cancel_success
        self.cancel_calls: list[dict[str, str]] = []

    async def cancel_order(self, *, exchange_order_id: str, symbol: str):
        self.cancel_calls.append(
            {"exchange_order_id": exchange_order_id, "symbol": symbol}
        )
        if not self.cancel_success:
            return SimpleNamespace(
                is_success=False,
                status="REJECTED",
                error_message="cleanup rejected by test gateway",
                error_code=None,
            )
        return SimpleNamespace(
            is_success=True,
            status="CANCELED",
            exchange_order_id=exchange_order_id,
            error_message=None,
            error_code=None,
        )
