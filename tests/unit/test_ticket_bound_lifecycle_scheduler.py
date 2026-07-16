from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from scripts import materialize_ticket_bound_exit_protection_set as exit_protection
from scripts import materialize_ticket_bound_runner_protection_adjustment as runner_adjuster
from src.application.action_time.exchange_snapshot_provider import (
    fetch_ticket_bound_exchange_snapshot,
)
from src.application.action_time.lifecycle_maintenance_scheduler import (
    MAINTAINABLE_LIFECYCLE_STATUSES,
    SNAPSHOT_STATUSES,
    lifecycle_maintenance_scopes_require_exchange_gateway,
    run_ticket_bound_lifecycle_maintenance_scheduler,
    select_ticket_bound_lifecycle_maintenance_scopes,
)
from src.application.action_time.post_submit_reconciliation_tick import (
    materialize_ticket_bound_first_reconciliation_tick,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_exit_protection_materializer import (
    _submitted_attempt,
)
from tests.unit.test_ticket_bound_post_submit_reconciliation_tick import (
    _attempt_snapshot,
)
from tests.unit.test_ticket_bound_runner_protection_adjuster import (
    _mark_tp1_filled,
    _materialized_exit_protection_set,
    _record_official_runner_mutation_result,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)
from tests.unit.test_ticket_exit_execution_binding import (
    _restart_recovery_snapshot,
)
from tests.unit.test_ticket_exit_policy_service import _versioned_exit_fixture


def test_runner_protected_is_maintainable_and_snapshot_eligible():
    assert "runner_protected" in MAINTAINABLE_LIFECYCLE_STATUSES
    assert "runner_protected" in SNAPSHOT_STATUSES


@pytest.mark.asyncio
async def test_scheduler_selects_healthy_runner_without_exchange_write(
    pg_control_connection,
):
    _, prepared = _submitted_attempt(pg_control_connection)
    protection = exit_protection.materialize_ticket_bound_exit_protection_set(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )
    set_id = protection["exit_protection_set_id"]
    first_tick = materialize_ticket_bound_first_reconciliation_tick(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        exchange_snapshot=_attempt_snapshot(prepared),
        now_ms=NOW_MS + 6500,
    )
    assert first_tick["status"] == "matched"
    _mark_tp1_filled(pg_control_connection, set_id)
    _record_official_runner_mutation_result(
        pg_control_connection,
        set_id,
        runner_exchange_id="exchange-runner-sl-1",
        now_ms=NOW_MS + 7000,
    )
    runner = runner_adjuster.materialize_ticket_bound_runner_protection_adjustment(
        pg_control_connection,
        exit_protection_set_id=set_id,
        runner_sl_exchange_order_id="exchange-runner-sl-1",
        runner_sl_local_order_id="runner-sl-1",
        now_ms=NOW_MS + 7500,
    )
    assert runner["status"] == "runner_protected"
    gateway = _HealthyRunnerGateway()

    payload = await run_ticket_bound_lifecycle_maintenance_scheduler(
        pg_control_connection,
        gateway=gateway,
        allow_exchange_mutation=True,
        fetch_exchange_snapshot=True,
        now_ms=NOW_MS + 10_000,
    )

    assert payload["selected_scope_count"] == 1
    assert payload["exchange_read_called"] is True
    assert payload["exchange_write_called"] is False
    assert payload["runs"][0]["exit_policy"]["status"] == (
        "exit_policy_capability_disabled"
    )
    assert "place_order" not in gateway.events
    assert "cancel_order" not in gateway.events


@pytest.mark.asyncio
async def test_scheduler_recovers_missing_execution_truth_before_exit_policy(
    pg_control_connection,
):
    ticket_id = _versioned_exit_fixture(pg_control_connection)
    protection_set = dict(
        pg_control_connection.execute(
            text(
                "SELECT * FROM brc_ticket_bound_exit_protection_sets "
                "WHERE ticket_id = :ticket_id"
            ),
            {"ticket_id": ticket_id},
        ).mappings().one()
    )
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_exit_policy_current SET "
            "exit_execution_snapshot = NULL, exit_execution_hash = NULL, "
            "actual_r_per_unit = NULL, resolved_tp1_price = NULL, "
            "resolved_tp1_target_qty = NULL, remaining_position_qty = NULL, "
            "state = 'bound' WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ticket_id},
    )
    snapshot = _restart_recovery_snapshot(pg_control_connection, ticket_id)
    orders = list(
        pg_control_connection.execute(
            text(
                "SELECT * FROM brc_ticket_bound_exit_protection_orders "
                "WHERE ticket_id = :ticket_id AND status IN ('submitted', 'open')"
            ),
            {"ticket_id": ticket_id},
        ).mappings()
    )
    snapshot["open_orders"] = [
        {
            "exchange_order_id": row["exchange_order_id"],
            "side": row["side"],
            "reduce_only": bool(row["reduce_only"]),
            "qty": str(row["qty"]),
            "price": str(row["price"] or ""),
            "trigger_price": str(row["trigger_price"] or ""),
            "status": "open",
        }
        for row in orders
    ]
    snapshot["position"] = {
        "qty": str(protection_set["entry_filled_qty"]),
        "position_flat": False,
        "complete": True,
    }

    payload = await run_ticket_bound_lifecycle_maintenance_scheduler(
        pg_control_connection,
        gateway=None,
        allow_exchange_mutation=False,
        fetch_exchange_snapshot=False,
        provided_exchange_snapshots={
            key: {
                "status": "snapshot_ready",
                "snapshot": snapshot,
                "exchange_read_called": True,
                "exchange_write_called": False,
            }
            for key in (
                str(protection_set["exit_protection_set_id"]),
                str(protection_set["protected_submit_attempt_id"]),
            )
        },
        now_ms=NOW_MS + 30_000,
    )

    assert payload["runs"][0]["execution_binding"]["status"] == "execution_bound", (
        payload["runs"][0]["execution_binding"]
    )
    assert payload["runs"][0]["execution_binding"]["exchange_write_called"] is False
    assert payload["runs"][0]["exit_policy"]["status"] != (
        "ticket_exit_policy_snapshot_invalid:ValidationError"
    )
    assert pg_control_connection.execute(
        text(
            "SELECT exit_execution_hash FROM brc_ticket_exit_policy_current "
            "WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ticket_id},
    ).scalar_one()


@pytest.mark.asyncio
async def test_scheduler_noops_without_maintainable_lifecycle(pg_control_connection):
    gateway = _SchedulerGateway()
    scopes = select_ticket_bound_lifecycle_maintenance_scopes(
        pg_control_connection,
        max_lifecycle_scopes=4,
    )
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
    assert scopes == []
    assert (
        lifecycle_maintenance_scopes_require_exchange_gateway(
            scopes,
            allow_exchange_mutation=True,
            fetch_exchange_snapshot=True,
        )
        is False
    )


def test_unknown_command_scope_requires_read_gateway_even_without_snapshot():
    scopes = [
        {
            "scheduler_scope_kind": "first_post_submit",
            "attempt_status": "submit_outcome_unknown",
        }
    ]

    assert lifecycle_maintenance_scopes_require_exchange_gateway(
        scopes,
        allow_exchange_mutation=False,
        fetch_exchange_snapshot=False,
    ) is True


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
        "fetch_all_open_orders",
        "fetch_my_trades",
        "fetch_positions",
    ]
    assert gateway.read_symbols == [
        "ETH/USDT:USDT",
        "ETH/USDT:USDT",
        "ETH/USDT:USDT",
    ]
    assert snapshot["symbol"] == "ETHUSDT"
    assert snapshot["exchange_symbol"] == "ETH/USDT:USDT"
    assert snapshot["open_orders"][0]["exchange_order_id"] == "exchange-sl-1"
    assert snapshot["open_orders"][0]["reduce_only"] is True
    assert snapshot["recent_fills"][0]["exchange_order_id"] == "exchange-tp1-1"
    assert snapshot["position"]["qty"] == "0.25"


@pytest.mark.asyncio
async def test_scheduler_fetches_snapshot_and_prepares_durable_runner_commands(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    scopes = select_ticket_bound_lifecycle_maintenance_scopes(
        pg_control_connection,
        max_lifecycle_scopes=4,
    )
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
    assert payload["status"] == "scheduler_complete", payload["blockers"]
    assert payload["exchange_read_called"] is True
    assert payload["exchange_write_called"] is False
    assert (
        lifecycle_maintenance_scopes_require_exchange_gateway(
            scopes,
            allow_exchange_mutation=True,
            fetch_exchange_snapshot=True,
        )
        is True
    )
    assert "exit_protection_reconciled" in actions
    assert actions[-2:] == [
        "runner_mutation_prepared",
        "runner_mutation_exchange_commands_prepared",
    ]
    assert gateway.events == [
        "fetch_all_open_orders",
        "fetch_my_trades",
        "fetch_positions",
    ]
    assert pg_control_connection.execute(
        text(
            "SELECT status FROM brc_ticket_bound_exit_protection_orders "
            "WHERE role = 'TP1'"
        )
    ).scalar_one() == "filled"


@pytest.mark.asyncio
async def test_snapshot_blocks_gateway_identity_mismatch_before_exchange_io(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    gateway = _SchedulerGateway()
    gateway.runtime_account_id = "another-account"

    payload = await fetch_ticket_bound_exchange_snapshot(
        pg_control_connection,
        exit_protection_set_id=set_id,
        gateway=gateway,
        now_ms=NOW_MS + 10_000,
    )

    assert payload["status"] == "blocked"
    assert payload["first_blocker"] == (
        "ticket_exchange_scope_gateway_account_mismatch"
    )
    assert payload["exchange_read_called"] is False
    assert gateway.events == []


@pytest.mark.asyncio
@pytest.mark.parametrize("reverse", [False, True])
async def test_snapshot_selects_exact_hedge_position_bucket_independent_of_order(
    pg_control_connection,
    reverse: bool,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_runtime_fact_snapshots
            SET fact_values = :fact_values
            WHERE fact_snapshot_id = (
              SELECT account_mode_snapshot_id
              FROM brc_action_time_tickets
              LIMIT 1
            )
            """
        ),
        {
            "fact_values": json.dumps(
                {
                    "account_id": "owner-subaccount-runtime-v0",
                    "exchange_id": "binance_usdm",
                    "account_mode": "hedge",
                    "dual_side_position": True,
                    "position_mode_safe": True,
                }
            )
        },
    )
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_exchange_account_modes_current
            SET position_mode = 'hedge',
                dual_side_position = true,
                position_mode_safe = true,
                status = 'current'
            WHERE account_id = 'owner-subaccount-runtime-v0'
              AND exchange_id = 'binance_usdm'
            """
        )
    )
    gateway = _SchedulerGateway()
    rows = [
        {
            "symbol": "ETH/USDT:USDT",
            "side": "long",
            "size": "0.25",
            "position_side": "LONG",
        },
        {
            "symbol": "ETH/USDT:USDT",
            "side": "short",
            "size": "0.75",
            "position_side": "SHORT",
        },
    ]
    gateway.position_rows = list(reversed(rows)) if reverse else rows

    payload = await fetch_ticket_bound_exchange_snapshot(
        pg_control_connection,
        exit_protection_set_id=set_id,
        gateway=gateway,
        now_ms=NOW_MS + 10_000,
    )

    assert payload["status"] == "snapshot_ready"
    assert payload["snapshot"]["position_mode"] == "hedge"
    assert payload["snapshot"]["position_side"] == "LONG"
    assert payload["snapshot"]["position"]["qty"] == "0.25"


@pytest.mark.asyncio
async def test_snapshot_complete_empty_position_rows_prove_flat(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    gateway = _SchedulerGateway()
    gateway.position_rows = []

    payload = await fetch_ticket_bound_exchange_snapshot(
        pg_control_connection,
        exit_protection_set_id=set_id,
        gateway=gateway,
        now_ms=NOW_MS + 10_000,
    )

    assert payload["status"] == "snapshot_ready"
    assert payload["snapshot"]["position"]["truth_state"] == "flat"
    assert payload["snapshot"]["position"]["position_flat"] is True


class _SchedulerGateway:
    def __init__(self) -> None:
        self.runtime_account_id = "owner-subaccount-runtime-v0"
        self.runtime_exchange_id = "binance_usdm"
        self.events: list[str] = []
        self.read_symbols: list[str] = []
        self.position_rows = None

    async def fetch_open_orders(self, symbol: str, params=None):
        self.events.append("fetch_open_orders")
        self.read_symbols.append(symbol)
        return self._open_orders(symbol)

    async def fetch_all_open_orders(self, symbol: str):
        self.events.append("fetch_all_open_orders")
        self.read_symbols.append(symbol)
        return self._open_orders(symbol)

    @staticmethod
    def _open_orders(symbol: str):
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
        self.read_symbols.append(symbol)
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
        self.read_symbols.append(str(symbol or ""))
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

    async def fetch_position_rows(self, symbol: str):
        if self.position_rows is not None:
            self.events.append("fetch_positions")
            self.read_symbols.append(symbol)
            return list(self.position_rows)
        return await self.fetch_positions(symbol)

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


class _HealthyRunnerGateway(_SchedulerGateway):
    @staticmethod
    def _open_orders(symbol: str):
        return [
            {
                "id": "exchange-runner-sl-1",
                "clientOrderId": "runner-sl-1",
                "symbol": symbol,
                "side": "sell",
                "reduceOnly": True,
                "amount": "0.25",
                "price": "",
                "stopPrice": "2000",
                "status": "open",
            }
        ]
