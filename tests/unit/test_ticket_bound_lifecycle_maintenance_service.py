from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from src.application.action_time.lifecycle_maintenance_service import (
    run_ticket_bound_lifecycle_maintenance,
)
from src.application.action_time.protection_reconciler import (
    reconcile_ticket_bound_exit_protection_set,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_exit_protection_materializer import (
    _submitted_attempt,
)
from tests.unit.test_ticket_bound_protection_reconciler import _snapshot
from tests.unit.test_ticket_bound_runner_protection_adjuster import (
    _mark_tp1_filled,
    _materialized_exit_protection_set,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


@pytest.mark.asyncio
async def test_lifecycle_maintenance_materializes_exit_protection_without_exchange_write(
    pg_control_connection,
):
    _, prepared = _submitted_attempt(pg_control_connection)

    payload = await run_ticket_bound_lifecycle_maintenance(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 10_000,
    )

    assert payload["status"] == "maintenance_complete"
    assert payload["exchange_write_called"] is False
    assert [action["action_type"] for action in payload["actions"]] == [
        "exit_protection_materialized"
    ]
    assert _count(pg_control_connection, "brc_ticket_bound_exit_protection_sets") == 1
    assert _lifecycle_status(pg_control_connection) == "position_protected"


@pytest.mark.asyncio
async def test_lifecycle_maintenance_recovers_missing_tp1_then_materializes_protection(
    pg_control_connection,
):
    _, prepared = _submitted_attempt(pg_control_connection)
    _remove_submitted_order_role(
        pg_control_connection,
        prepared["protected_submit_attempt_id"],
        "TP1",
    )
    gateway = _LifecycleMaintenanceGateway()

    payload = await run_ticket_bound_lifecycle_maintenance(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        gateway=gateway,
        allow_exchange_mutation=True,
        now_ms=NOW_MS + 10_000,
    )

    assert payload["status"] == "maintenance_complete"
    assert payload["exchange_write_called"] is True
    assert [action["action_type"] for action in payload["actions"]] == [
        "exit_protection_materialized",
        "protection_recovery_prepared",
        "protection_recovery_executed",
        "exit_protection_materialized_after_recovery",
    ]
    assert [call["reduce_only"] for call in gateway.place_calls] == [True]
    assert _lifecycle_status(pg_control_connection) == "position_protected"


@pytest.mark.asyncio
async def test_lifecycle_maintenance_executes_runner_mutation_and_materializes_runner(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    _mark_tp1_filled(pg_control_connection, set_id)
    gateway = _LifecycleMaintenanceGateway()

    payload = await run_ticket_bound_lifecycle_maintenance(
        pg_control_connection,
        exit_protection_set_id=set_id,
        gateway=gateway,
        allow_exchange_mutation=True,
        now_ms=NOW_MS + 10_000,
    )

    assert payload["status"] == "maintenance_complete"
    assert [action["action_type"] for action in payload["actions"]] == [
        "runner_mutation_prepared",
        "runner_mutation_executed",
        "runner_protection_materialized",
    ]
    assert gateway.events == ["place_order", "cancel_order"]
    assert _lifecycle_status(pg_control_connection) == "runner_protected"


@pytest.mark.asyncio
async def test_lifecycle_maintenance_prepares_runner_without_exchange_mutation(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    _mark_tp1_filled(pg_control_connection, set_id)
    gateway = _LifecycleMaintenanceGateway()

    payload = await run_ticket_bound_lifecycle_maintenance(
        pg_control_connection,
        exit_protection_set_id=set_id,
        gateway=gateway,
        allow_exchange_mutation=False,
        now_ms=NOW_MS + 10_000,
    )

    assert payload["status"] == "maintenance_blocked"
    assert payload["first_blocker"] == "exchange_mutation_not_allowed_for_runner_mutation"
    assert gateway.events == []
    assert _lifecycle_status(pg_control_connection) == "runner_mutation_pending"


@pytest.mark.asyncio
async def test_lifecycle_maintenance_executes_orphan_cleanup_after_flat_reconcile(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    snapshot = _snapshot(pg_control_connection, set_id)
    snapshot["position"] = {"qty": "0", "position_flat": True}
    reconciled = reconcile_ticket_bound_exit_protection_set(
        pg_control_connection,
        exit_protection_set_id=set_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 9000,
    )
    gateway = _LifecycleMaintenanceGateway()

    payload = await run_ticket_bound_lifecycle_maintenance(
        pg_control_connection,
        exit_protection_set_id=set_id,
        gateway=gateway,
        allow_exchange_mutation=True,
        now_ms=NOW_MS + 10_000,
    )

    assert reconciled["status"] == "position_closed_protection_live"
    assert payload["status"] == "maintenance_complete"
    assert [action["action_type"] for action in payload["actions"]] == [
        "orphan_protection_cleanup_prepared",
        "orphan_protection_cleanup_executed",
    ]
    assert gateway.events == ["cancel_order", "cancel_order"]
    assert _lifecycle_status(pg_control_connection) == "reconciliation_matched"


def _count(conn, table_name: str) -> int:
    return int(conn.execute(text(f"SELECT count(*) FROM {table_name}")).scalar_one())


def _lifecycle_status(conn) -> str:
    return str(
        conn.execute(
            text("SELECT status FROM brc_ticket_bound_order_lifecycle_runs")
        ).scalar_one()
    )


def _remove_submitted_order_role(conn, attempt_id: str, role: str) -> None:
    raw = conn.execute(
        text(
            """
            SELECT submit_result
            FROM brc_ticket_bound_protected_submit_attempts
            WHERE protected_submit_attempt_id = :attempt_id
            """
        ),
        {"attempt_id": attempt_id},
    ).scalar_one()
    submit_result = json.loads(raw) if isinstance(raw, str) else dict(raw)
    submit_result["submitted_orders"] = [
        order
        for order in submit_result["submitted_orders"]
        if order["order_role"] != role
    ]
    conn.execute(
        text(
            """
            UPDATE brc_ticket_bound_protected_submit_attempts
            SET submit_result = :submit_result
            WHERE protected_submit_attempt_id = :attempt_id
            """
        ),
        {
            "attempt_id": attempt_id,
            "submit_result": json.dumps(submit_result, sort_keys=True),
        },
    )


class _LifecycleMaintenanceGateway:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.place_calls: list[dict] = []
        self.cancel_calls: list[dict] = []

    async def place_order(self, **kwargs):
        self.events.append("place_order")
        self.place_calls.append(dict(kwargs))
        return SimpleNamespace(
            is_success=True,
            exchange_order_id=f"exchange-{kwargs['client_order_id']}",
            status="OPEN",
        )

    async def cancel_order(self, **kwargs):
        self.events.append("cancel_order")
        self.cancel_calls.append(dict(kwargs))
        return SimpleNamespace(
            is_success=True,
            exchange_order_id=kwargs["exchange_order_id"],
            status="CANCELED",
        )
