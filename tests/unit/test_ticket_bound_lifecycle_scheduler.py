from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.application.action_time.exchange_snapshot_provider import (
    fetch_ticket_bound_exchange_snapshot,
)
from src.application.action_time.lifecycle_maintenance_scheduler import (
    run_ticket_bound_lifecycle_maintenance_scheduler,
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
async def test_scheduler_noops_without_maintainable_lifecycle(pg_control_connection):
    gateway = _SchedulerGateway()

    payload = await run_ticket_bound_lifecycle_maintenance_scheduler(
        pg_control_connection,
        gateway=gateway,
        allow_exchange_mutation=True,
        fetch_exchange_snapshot=True,
        now_ms=NOW_MS + 10_000,
    )

    assert payload["status"] == "no_maintainable_lifecycle"
    assert payload["selected_scope_count"] == 0
    assert payload["exchange_read_called"] is False
    assert payload["exchange_write_called"] is False
    assert gateway.events == []


@pytest.mark.asyncio
async def test_exchange_snapshot_provider_normalizes_readonly_gateway_facts(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    gateway = _SchedulerGateway()

    payload = await fetch_ticket_bound_exchange_snapshot(
        pg_control_connection,
        exit_protection_set_id=set_id,
        gateway=gateway,
        now_ms=NOW_MS + 10_000,
    )

    snapshot = payload["snapshot"]
    assert payload["status"] == "snapshot_ready"
    assert payload["exchange_read_called"] is True
    assert payload["exchange_write_called"] is False
    assert [event for event in gateway.events] == [
        "fetch_open_orders",
        "fetch_my_trades",
        "fetch_positions",
    ]
    assert snapshot["open_orders"][0]["exchange_order_id"] == "exchange-sl-1"
    assert snapshot["open_orders"][0]["reduce_only"] is True
    assert snapshot["recent_fills"][0]["exchange_order_id"] == "exchange-tp1-1"
    assert snapshot["position"]["qty"] == "0.25"


@pytest.mark.asyncio
async def test_scheduler_fetches_snapshot_and_runs_runner_mutation(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    _mark_tp1_filled(pg_control_connection, set_id)
    gateway = _SchedulerGateway()

    payload = await run_ticket_bound_lifecycle_maintenance_scheduler(
        pg_control_connection,
        gateway=gateway,
        allow_exchange_mutation=True,
        fetch_exchange_snapshot=True,
        now_ms=NOW_MS + 10_000,
    )

    actions = [
        action["action_type"]
        for run in payload["runs"]
        for action in run["actions"]
    ]
    assert payload["status"] == "scheduler_complete"
    assert payload["exchange_read_called"] is True
    assert payload["exchange_write_called"] is True
    assert "exit_protection_reconciled" in actions
    assert actions[-3:] == [
        "runner_mutation_prepared",
        "runner_mutation_executed",
        "runner_protection_materialized",
    ]
    assert gateway.events == [
        "fetch_open_orders",
        "fetch_my_trades",
        "fetch_positions",
        "place_order",
        "cancel_order",
    ]


class _SchedulerGateway:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def fetch_open_orders(self, symbol: str, params=None):
        self.events.append("fetch_open_orders")
        return [
            {
                "id": "exchange-sl-1",
                "clientOrderId": "sl-client-1",
                "symbol": symbol,
                "side": "sell",
                "reduceOnly": True,
                "amount": "0.5",
                "price": "",
                "stopPrice": "1900",
                "status": "open",
            }
        ]

    async def fetch_my_trades(self, symbol: str, limit: int = 50, params=None):
        self.events.append("fetch_my_trades")
        return [
            {
                "order": "exchange-tp1-1",
                "symbol": symbol,
                "side": "sell",
                "amount": "0.25",
                "price": "2100",
                "timestamp": NOW_MS + 9000,
            }
        ]

    async def fetch_positions(self, symbol: str | None = None):
        self.events.append("fetch_positions")
        return [
            {
                "symbol": symbol or "ETHUSDT",
                "side": "long",
                "size": "0.25",
                "entry_price": "2000",
                "mark_price": "2050",
                "unrealized_pnl": "12.5",
                "liquidation_price": "1200",
            }
        ]

    async def place_order(self, **kwargs):
        self.events.append("place_order")
        return SimpleNamespace(
            is_success=True,
            exchange_order_id=f"exchange-{kwargs['client_order_id']}",
            status="OPEN",
        )

    async def cancel_order(self, **kwargs):
        self.events.append("cancel_order")
        return SimpleNamespace(
            is_success=True,
            exchange_order_id=kwargs["exchange_order_id"],
            status="CANCELED",
        )
