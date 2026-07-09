from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from scripts import materialize_ticket_bound_exit_protection_set as exit_protection
from scripts import materialize_ticket_bound_protected_submit_attempt as submit
from src.application.action_time.lifecycle_maintenance_scheduler import (
    lifecycle_maintenance_scopes_require_exchange_gateway,
    run_ticket_bound_lifecycle_maintenance_scheduler,
    select_ticket_bound_lifecycle_maintenance_scopes,
)
from src.application.action_time.post_submit_reconciliation_tick import (
    materialize_ticket_bound_first_reconciliation_tick,
    select_ticket_bound_first_reconciliation_tick_scopes,
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


@pytest.fixture(autouse=True)
def runtime_submit_env(monkeypatch):
    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")
    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "order_allowed")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_EXCHANGE_SUBMIT_GATEWAY_BINDING_ENABLED", "true")


def test_first_tick_skips_disabled_smoke_without_pg_tick(pg_control_connection):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="disabled_smoke",
        now_ms=NOW_MS + 4000,
    )

    payload = materialize_ticket_bound_first_reconciliation_tick(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 5000,
    )

    assert payload["status"] == "not_applicable_disabled_smoke"
    assert _count(pg_control_connection, "brc_ticket_bound_reconciliation_ticks") == 0


def test_first_tick_marks_tp1_missing_as_recovery_required(pg_control_connection):
    prepared = _submitted_real_attempt(pg_control_connection)
    snapshot = _attempt_snapshot(prepared, omit_roles={"TP1"})

    payload = materialize_ticket_bound_first_reconciliation_tick(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 6000,
    )

    assert payload["status"] == "recovery_required"
    assert payload["first_blocker"] == "tp1_exchange_order_missing"
    assert payload["next_action"] == "submit_missing_tp1"
    row = _one(pg_control_connection, "brc_ticket_bound_reconciliation_ticks")
    assert row["status"] == "recovery_required"
    assert row["tp1_state"] == "missing"
    assert row["sl_state"] == "open"


def test_first_tick_freezes_scope_for_unknown_exchange_only_order(pg_control_connection):
    prepared = _submitted_real_attempt(pg_control_connection)
    snapshot = _attempt_snapshot(prepared)
    snapshot["open_orders"].append(
        {
            "exchange_order_id": "exchange-unknown-reduce-only",
            "side": "sell",
            "reduce_only": True,
            "qty": "0.25",
            "status": "open",
        }
    )

    payload = materialize_ticket_bound_first_reconciliation_tick(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 6000,
    )

    assert payload["status"] == "hard_stopped"
    assert payload["first_blocker"] == "exchange_only_unknown_order"
    freeze = _one(pg_control_connection, "brc_ticket_bound_scope_freezes")
    assert freeze["status"] == "active"
    assert freeze["strategy_group_id"] == "SOR-001"
    assert freeze["symbol"] == "ETHUSDT"
    assert freeze["side"] == "long"


def test_first_tick_rechecks_pending_visibility_after_deadline(pg_control_connection):
    prepared = _submitted_real_attempt(pg_control_connection)
    _mark_entry_visibility_pending(
        pg_control_connection,
        prepared["protected_submit_attempt_id"],
    )
    pending = materialize_ticket_bound_first_reconciliation_tick(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        exchange_snapshot={
            "snapshot_id": "snapshot:first-tick-pending",
            "symbol": "ETHUSDT",
            "open_orders": [],
            "recent_fills": [],
            "position": {"qty": "0", "position_flat": True},
        },
        now_ms=NOW_MS + 5001,
    )
    assert pending["status"] == "pending_visibility"
    assert select_ticket_bound_first_reconciliation_tick_scopes(
        pg_control_connection,
        max_scopes=4,
        now_ms=NOW_MS + 5002,
    ) == []

    due = select_ticket_bound_first_reconciliation_tick_scopes(
        pg_control_connection,
        max_scopes=4,
        now_ms=NOW_MS + 36_000,
    )
    assert due[0]["protected_submit_attempt_id"] == prepared["protected_submit_attempt_id"]
    assert due[0]["existing_tick_status"] == "pending_visibility"

    refreshed = materialize_ticket_bound_first_reconciliation_tick(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        exchange_snapshot=_attempt_snapshot(prepared),
        now_ms=NOW_MS + 36_000,
    )
    assert refreshed["status"] == "matched"
    assert _count(pg_control_connection, "brc_ticket_bound_reconciliation_ticks") == 1
    row = _one(pg_control_connection, "brc_ticket_bound_reconciliation_ticks")
    assert row["status"] == "matched"


@pytest.mark.asyncio
async def test_scheduler_runs_first_tick_and_prepares_tp1_recovery(pg_control_connection):
    prepared = _submitted_real_attempt(pg_control_connection)
    gateway = _FirstTickGateway(prepared, omit_roles={"TP1"})

    payload = await run_ticket_bound_lifecycle_maintenance_scheduler(
        pg_control_connection,
        gateway=gateway,
        allow_exchange_mutation=False,
        fetch_exchange_snapshot=True,
        now_ms=NOW_MS + 7000,
    )

    actions = [
        action["action_type"]
        for run in payload["runs"]
        for action in run["actions"]
    ]
    assert payload["status"] == "scheduler_blocked"
    assert payload["exchange_read_called"] is True
    assert payload["exchange_write_called"] is False
    assert gateway.place_calls == []
    assert "exit_protection_materialized" in actions
    assert "exit_protection_reconciled" in actions
    assert "protection_recovery_prepared" in actions
    assert _lifecycle_status(pg_control_connection) == "protection_degraded"
    command = _one(pg_control_connection, "brc_ticket_bound_protection_recovery_commands")
    assert command["status"] == "prepared"
    assert command["execution_attempt_count"] == 0
    assert command["scope_frozen"] in {False, 0}
    assert (
        lifecycle_maintenance_scopes_require_exchange_gateway(
            [{"scheduler_scope_kind": "first_post_submit"}],
            allow_exchange_mutation=False,
            fetch_exchange_snapshot=True,
        )
        is True
    )
    assert select_ticket_bound_first_reconciliation_tick_scopes(
        pg_control_connection,
        max_scopes=4,
    ) == []
    assert select_ticket_bound_lifecycle_maintenance_scopes(
        pg_control_connection,
        max_lifecycle_scopes=4,
    )[0]["lifecycle_status"] == "protection_degraded"


@pytest.mark.asyncio
async def test_scheduler_materializes_scheduled_tick_for_active_lifecycle(
    pg_control_connection,
):
    prepared = _submitted_real_attempt(pg_control_connection)
    proof = exit_protection.materialize_ticket_bound_exit_protection_set(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )
    assert proof["status"] == "position_protected"
    gateway = _FirstTickGateway(prepared)
    first_tick = materialize_ticket_bound_first_reconciliation_tick(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        exchange_snapshot=_attempt_snapshot(prepared),
        now_ms=NOW_MS + 7000,
    )
    assert first_tick["status"] == "matched"

    second = await run_ticket_bound_lifecycle_maintenance_scheduler(
        pg_control_connection,
        gateway=gateway,
        allow_exchange_mutation=False,
        fetch_exchange_snapshot=True,
        now_ms=NOW_MS + 9000,
    )

    assert second["exchange_read_called"] is True
    assert any(
        run.get("scheduled_tick", {}).get("status") == "matched"
        for run in second["runs"]
    )
    rows = list(
        pg_control_connection.execute(
            text(
                """
                SELECT tick_kind, status
                FROM brc_ticket_bound_reconciliation_ticks
                ORDER BY tick_kind
                """
            )
        ).mappings()
    )
    assert {(row["tick_kind"], row["status"]) for row in rows} >= {
        ("first_post_submit", "matched"),
        ("scheduled", "matched"),
    }


def _submitted_real_attempt(conn) -> dict:
    ids = _create_ready_protected_submit(conn)
    prepared = _prepare_real_submit(conn, ids)
    result = submit.record_ticket_bound_protected_submit_result(
        conn,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        submit_result={
            "status": "exchange_submit_orders_submitted",
            "ticket_id": ids["ticket_id"],
            "operation_submit_command_id": ids["operation_submit_command_id"],
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
            "exchange_write_called": True,
            "order_created": True,
            "order_lifecycle_called": True,
            "withdrawal_or_transfer_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
            "submitted_orders": _submitted_orders(prepared),
        },
        now_ms=NOW_MS + 5000,
    )
    assert result["status"] == "submitted"
    return prepared


def _attempt_snapshot(prepared: dict, *, omit_roles: set[str] | None = None) -> dict:
    omit_roles = omit_roles or set()
    open_orders = []
    for order in _submitted_orders(prepared):
        role = order["order_role"]
        if role == "ENTRY" or role in omit_roles:
            continue
        open_orders.append(
            {
                "exchange_order_id": order["exchange_order_id"],
                "side": "sell",
                "reduce_only": order["reduce_only"],
                "qty": order["amount"],
                "price": order.get("price") or "",
                "trigger_price": order.get("trigger_price") or "",
                "status": "open",
            }
        )
    return {
        "snapshot_id": "snapshot:first-tick",
        "symbol": "ETHUSDT",
        "open_orders": open_orders,
        "recent_fills": [
            {
                "exchange_order_id": "exchange-entry-1",
                "side": "buy",
                "qty": prepared["submit_request"]["orders"][0]["amount"],
                "price": prepared["submit_request"]["reference_price"],
                "timestamp_ms": NOW_MS + 5100,
            }
        ],
        "position": {"qty": "0.5", "position_flat": False},
        "fetched_at_ms": NOW_MS + 5500,
    }


def _count(conn, table_name: str) -> int:
    return int(conn.execute(text(f"SELECT count(*) FROM {table_name}")).scalar_one())


def _one(conn, table_name: str) -> dict:
    return dict(conn.execute(text(f"SELECT * FROM {table_name}")).mappings().one())


def _lifecycle_status(conn) -> str:
    return str(
        conn.execute(
            text("SELECT status FROM brc_ticket_bound_order_lifecycle_runs")
        ).scalar_one()
    )


def _mark_entry_visibility_pending(conn, attempt_id: str) -> None:
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
    for order in submit_result["submitted_orders"]:
        if order["order_role"] == "ENTRY":
            order["status"] = "NEW"
            order.pop("filled_qty", None)
            order.pop("average_exec_price", None)
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


class _FirstTickGateway:
    def __init__(self, prepared: dict, *, omit_roles: set[str] | None = None) -> None:
        self.snapshot = _attempt_snapshot(prepared, omit_roles=omit_roles)
        self.place_calls: list[dict] = []

    async def fetch_open_orders(self, symbol: str, params=None):
        return list(self.snapshot["open_orders"])

    async def fetch_my_trades(self, symbol: str, limit: int = 50, params=None):
        return list(self.snapshot["recent_fills"])

    async def fetch_positions(self, symbol: str | None = None):
        return [
            {
                "symbol": symbol or "ETHUSDT",
                "side": "long",
                "size": "0.5",
                "entry_price": "2000",
                "mark_price": "2010",
            }
        ]

    async def place_order(self, **kwargs):
        self.place_calls.append(dict(kwargs))
        return SimpleNamespace(
            is_success=True,
            exchange_order_id=f"exchange-{kwargs['client_order_id']}",
            status="OPEN",
        )
