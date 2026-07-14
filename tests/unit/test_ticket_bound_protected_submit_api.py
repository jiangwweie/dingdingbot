from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from src.domain.exceptions import ConnectionLostError
from src.interfaces import api_trading_console
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_protected_submit_attempt import (
    _create_ready_protected_submit,
    _prepare_real_submit,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


@pytest.mark.asyncio
async def test_ticket_bound_protected_submit_api_returns_disabled_smoke_body(
    monkeypatch,
):
    async def _run(*, ticket_id: str, operation_submit_command_id: str, submit_mode: str):
        return {
            "status": "disabled_smoke_passed",
            "protected_submit_attempt_id": "protected-submit-1",
            "ticket_id": ticket_id,
            "finalgate_pass_id": "finalgate-pass-1",
            "operation_layer_handoff_id": "handoff-1",
            "operation_submit_command_id": operation_submit_command_id,
            "runtime_safety_snapshot_id": "runtime-safety-1",
            "action_time_lane_input_id": "lane-1",
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
            "submit_mode": submit_mode,
            "submit_allowed": True,
            "blockers": [],
            "warnings": ["disabled_smoke_no_exchange_write"],
            "submit_request": {},
            "submit_result": {"status": "exchange_submit_execution_disabled"},
            "identity_evidence": {},
            "next_action": "continue_without_exchange_write",
            "authority_boundary": "ticket_bound_protected_submit",
            "official_operation_layer_submit_called": True,
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "withdrawal_or_transfer_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
        }

    monkeypatch.setattr(api_trading_console, "_run_ticket_bound_protected_submit", _run)

    response = await api_trading_console.runtime_ticket_bound_protected_submit_for_ticket(
        "ticket-1",
        "operation-submit-1",
        submit_mode="disabled_smoke",
    )
    payload = response.model_dump()

    assert payload["status"] == "disabled_smoke_passed"
    assert payload["ticket_id"] == "ticket-1"
    assert payload["operation_submit_command_id"] == "operation-submit-1"
    assert payload["runtime_safety_snapshot_id"] == "runtime-safety-1"
    assert payload["submit_allowed"] is True
    assert payload["official_operation_layer_submit_called"] is True
    assert payload["exchange_write_called"] is False
    assert payload["order_created"] is False
    assert payload["order_lifecycle_called"] is False


@pytest.mark.asyncio
async def test_ticket_bound_protected_submit_api_fails_closed_without_pg(
    monkeypatch,
):
    async def _raise(
        *,
        ticket_id: str,
        operation_submit_command_id: str,
        submit_mode: str,
    ):
        raise RuntimeError("PG_DATABASE_URL is required for ticket-bound protected submit")

    monkeypatch.setattr(api_trading_console, "_run_ticket_bound_protected_submit", _raise)

    with pytest.raises(HTTPException) as exc:
        await api_trading_console.runtime_ticket_bound_protected_submit_for_ticket(
            "ticket-1",
            "operation-submit-1",
        )

    assert exc.value.status_code == 503
    assert "PG_DATABASE_URL is required" in exc.value.detail


def test_ticket_bound_protected_submit_api_signature_has_no_legacy_inputs():
    signature = inspect.signature(
        api_trading_console.runtime_ticket_bound_protected_submit_for_ticket
    )

    assert list(signature.parameters) == [
        "ticket_id",
        "operation_submit_command_id",
        "submit_mode",
    ]
    assert "authorization_id" not in signature.parameters
    assert "signal_input_json" not in signature.parameters
    assert "prepared_authorization_id" not in signature.parameters


def test_runtime_exchange_submit_gateway_status_requires_lifecycle_methods():
    gateway = SimpleNamespace(
        place_order=lambda **_kwargs: None,
        fetch_ticker_price=lambda *_args, **_kwargs: None,
        get_market_info=lambda *_args, **_kwargs: None,
    )

    status = api_trading_console._runtime_exchange_submit_gateway_status(gateway)

    assert status["status"] == "blocked_methods_missing"
    assert status["gateway"] is None
    assert "runtime_gateway_missing_cancel_order" in status["blockers"]
    assert "runtime_gateway_missing_fetch_open_orders" in status["blockers"]
    assert "runtime_gateway_missing_fetch_order" in status["blockers"]
    assert "runtime_gateway_missing_fetch_positions" in status["blockers"]
    assert "runtime_gateway_missing_fetch_my_trades" in status["blockers"]


@pytest.mark.asyncio
async def test_ticket_bound_post_submit_closure_api_returns_pg_closure_body(
    monkeypatch,
):
    def _run(*, protected_submit_attempt_id: str):
        return {
            "status": "reconciliation_pending",
            "post_submit_closure_id": "post-submit-closure-1",
            "protected_submit_attempt_id": protected_submit_attempt_id,
            "ticket_id": "ticket-1",
            "operation_submit_command_id": "operation-submit-1",
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
            "protection_state": "submitted",
            "reconciliation_state": "not_checked",
            "settlement_state": "blocked",
            "review_state": "blocked",
            "first_blocker": "post_submit_reconciliation_fact_missing",
            "blockers": ["post_submit_reconciliation_fact_missing"],
            "submitted_order_refs": [{"local_order_id": "entry-1"}],
            "next_action": "run_ticket_bound_post_submit_reconciliation",
            "authority_boundary": "ticket_bound_post_submit_closure",
            "finalgate_called": False,
            "operation_layer_called": False,
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "withdrawal_or_transfer_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
            "runtime_budget_mutated": False,
        }

    monkeypatch.setattr(api_trading_console, "_run_ticket_bound_post_submit_closure", _run)

    response = (
        await api_trading_console.runtime_ticket_bound_post_submit_closure_for_attempt(
            "protected-submit-1"
        )
    )
    payload = response.model_dump()

    assert payload["status"] == "reconciliation_pending"
    assert payload["post_submit_closure_id"] == "post-submit-closure-1"
    assert payload["protected_submit_attempt_id"] == "protected-submit-1"
    assert payload["ticket_id"] == "ticket-1"
    assert payload["first_blocker"] == "post_submit_reconciliation_fact_missing"
    assert payload["exchange_write_called"] is False
    assert payload["order_created"] is False
    assert payload["order_lifecycle_called"] is False
    assert payload["runtime_budget_mutated"] is False


@pytest.mark.asyncio
async def test_ticket_bound_post_submit_closure_api_fails_closed_without_pg(
    monkeypatch,
):
    def _raise(*, protected_submit_attempt_id: str):
        raise RuntimeError("PG_DATABASE_URL is required for ticket-bound post-submit closure")

    monkeypatch.setattr(api_trading_console, "_run_ticket_bound_post_submit_closure", _raise)

    with pytest.raises(HTTPException) as exc:
        await api_trading_console.runtime_ticket_bound_post_submit_closure_for_attempt(
            "protected-submit-1"
        )

    assert exc.value.status_code == 503
    assert "PG_DATABASE_URL is required" in exc.value.detail


def test_ticket_bound_post_submit_closure_api_signature_has_no_legacy_inputs():
    signature = inspect.signature(
        api_trading_console.runtime_ticket_bound_post_submit_closure_for_attempt
    )

    assert list(signature.parameters) == ["protected_submit_attempt_id"]
    assert "authorization_id" not in signature.parameters
    assert "prepared_authorization_id" not in signature.parameters
    assert "signal_input_json" not in signature.parameters


@pytest.mark.asyncio
async def test_ticket_bound_real_submit_helper_uses_gateway_and_order_lifecycle():
    gateway = _FakeGateway()
    lifecycle = _FakeOrderLifecycle()
    report = {
        "ticket_id": "ticket-1",
        "operation_submit_command_id": "operation-submit-1",
        "runtime_safety_snapshot_id": "runtime-safety-1",
        "strategy_group_id": "SOR-001",
        "symbol": "ETHUSDT",
        "side": "long",
        "submit_request": {
            "ticket_id": "ticket-1",
            "operation_submit_command_id": "operation-submit-1",
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
            "direction": "LONG",
            "exchange_symbol": "ETH/USDT:USDT",
            "orders": [
                {
                    "local_order_id": "entry-1",
                    "order_role": "ENTRY",
                    "symbol": "ETH/USDT:USDT",
                    "gateway_order_type": "market",
                    "gateway_side": "buy",
                    "amount": "0.01",
                    "price": None,
                    "trigger_price": None,
                    "reduce_only": False,
                    "client_order_id": "entry-1",
                },
                {
                    "local_order_id": "sl-1",
                    "parent_order_id": "entry-1",
                    "order_role": "SL",
                    "symbol": "ETH/USDT:USDT",
                    "gateway_order_type": "stop_market",
                    "gateway_side": "sell",
                    "amount": "0.01",
                    "price": None,
                    "trigger_price": "1800",
                    "reduce_only": True,
                    "client_order_id": "sl-1",
                },
            ],
        },
    }

    result = await api_trading_console._submit_ticket_bound_orders(
        report,
        gateway=gateway,
        order_lifecycle_service=lifecycle,
    )

    assert result["status"] == "exchange_submit_orders_submitted"
    assert result["ticket_id"] == "ticket-1"
    assert result["operation_submit_command_id"] == "operation-submit-1"
    assert result["exchange_write_called"] is True
    assert result["order_created"] is True
    assert result["order_lifecycle_called"] is True
    assert [call["client_order_id"] for call in gateway.calls] == ["entry-1", "sl-1"]
    assert lifecycle.registered_order_ids == ["entry-1", "sl-1"]
    assert lifecycle.submitted_order_ids == ["entry-1", "sl-1"]
    assert lifecycle.confirmed_order_ids == ["entry-1", "sl-1"]
    assert [order["local_order_id"] for order in result["submitted_orders"]] == [
        "entry-1",
        "sl-1",
    ]


@pytest.mark.asyncio
async def test_ticket_bound_real_submit_helper_ignores_unparseable_filled_qty():
    gateway = _UnparseableFilledQtyGateway()
    lifecycle = _FakeOrderLifecycle()
    report = {
        "ticket_id": "ticket-1",
        "operation_submit_command_id": "operation-submit-1",
        "runtime_safety_snapshot_id": "runtime-safety-1",
        "strategy_group_id": "SOR-001",
        "symbol": "ETHUSDT",
        "side": "long",
        "submit_request": {
            "ticket_id": "ticket-1",
            "operation_submit_command_id": "operation-submit-1",
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
            "direction": "LONG",
            "exchange_symbol": "ETH/USDT:USDT",
            "orders": [
                {
                    "local_order_id": "entry-1",
                    "order_role": "ENTRY",
                    "symbol": "ETH/USDT:USDT",
                    "gateway_order_type": "market",
                    "gateway_side": "buy",
                    "amount": "0.01",
                    "price": None,
                    "trigger_price": None,
                    "reduce_only": False,
                    "client_order_id": "entry-1",
                }
            ],
        },
    }

    result = await api_trading_console._submit_ticket_bound_orders(
        report,
        gateway=gateway,
        order_lifecycle_service=lifecycle,
    )

    assert result["status"] == "exchange_submit_orders_submitted"
    assert lifecycle.confirmed_order_ids == ["entry-1"]
    assert lifecycle.filled_order_ids == []
    assert result["submitted_orders"][0]["filled_qty"] == "not-a-number"


@pytest.mark.asyncio
async def test_ticket_bound_real_submit_helper_marks_gateway_failure_as_exchange_called():
    gateway = _FailingGateway()
    lifecycle = _FakeOrderLifecycle()
    report = {
        "ticket_id": "ticket-1",
        "operation_submit_command_id": "operation-submit-1",
        "runtime_safety_snapshot_id": "runtime-safety-1",
        "strategy_group_id": "SOR-001",
        "symbol": "ETHUSDT",
        "side": "long",
        "submit_request": {
            "ticket_id": "ticket-1",
            "operation_submit_command_id": "operation-submit-1",
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
            "direction": "LONG",
            "exchange_symbol": "ETH/USDT:USDT",
            "orders": [
                {
                    "local_order_id": "entry-1",
                    "order_role": "ENTRY",
                    "symbol": "ETH/USDT:USDT",
                    "gateway_order_type": "market",
                    "gateway_side": "buy",
                    "amount": "0.01",
                    "price": None,
                    "trigger_price": None,
                    "reduce_only": False,
                    "client_order_id": "entry-1",
                }
            ],
        },
    }

    result = await api_trading_console._submit_ticket_bound_orders(
        report,
        gateway=gateway,
        order_lifecycle_service=lifecycle,
    )

    assert result["status"] == "entry_submit_failed"
    assert result["exchange_write_called"] is True
    assert result["order_created"] is True
    assert result["order_lifecycle_called"] is True
    assert result["submitted_orders"] == []


@pytest.mark.asyncio
async def test_ticket_bound_real_submit_helper_blocks_identity_mismatch_before_gateway():
    gateway = _FakeGateway()
    lifecycle = _FakeOrderLifecycle()
    report = {
        "ticket_id": "ticket-1",
        "operation_submit_command_id": "operation-submit-1",
        "runtime_safety_snapshot_id": "runtime-safety-1",
        "strategy_group_id": "SOR-001",
        "symbol": "ETHUSDT",
        "side": "long",
        "submit_request": {
            "ticket_id": "ticket-1",
            "operation_submit_command_id": "operation-submit-1",
            "strategy_group_id": "SOR-001",
            "symbol": "SOLUSDT",
            "side": "long",
            "direction": "LONG",
            "exchange_symbol": "SOL/USDT:USDT",
            "orders": [
                {
                    "local_order_id": "entry-1",
                    "order_role": "ENTRY",
                    "symbol": "SOL/USDT:USDT",
                    "gateway_order_type": "market",
                    "gateway_side": "buy",
                    "amount": "0.01",
                    "price": None,
                    "trigger_price": None,
                    "reduce_only": False,
                    "client_order_id": "entry-1",
                }
            ],
        },
    }

    result = await api_trading_console._submit_ticket_bound_orders(
        report,
        gateway=gateway,
        order_lifecycle_service=lifecycle,
    )

    assert result["status"] == "submit_request_identity_mismatch"
    assert result["exchange_write_called"] is False
    assert result["order_created"] is False
    assert result["order_lifecycle_called"] is False
    assert "submit_request_identity_mismatch:symbol:expected=ETHUSDT:actual=SOLUSDT" in (
        result["blockers"]
    )
    assert gateway.calls == []
    assert lifecycle.registered_order_ids == []


class _FakeGateway:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def place_order(self, **kwargs):
        self.calls.append(dict(kwargs))
        return SimpleNamespace(
            is_success=True,
            exchange_order_id=f"exchange-{kwargs['client_order_id']}",
        )


class _FailingGateway:
    async def place_order(self, **kwargs):
        return SimpleNamespace(
            is_success=False,
            error_message="exchange rejected test order",
            error_code="TEST_REJECTED",
        )


class _UnparseableFilledQtyGateway:
    async def place_order(self, **kwargs):
        return SimpleNamespace(
            is_success=True,
            exchange_order_id=f"exchange-{kwargs['client_order_id']}",
            filled_qty="not-a-number",
            average_exec_price="bad-price",
        )


class _FilledWithoutExecutionFactsGateway:
    runtime_account_id = "owner-subaccount-runtime-v0"
    runtime_exchange_id = "binance_usdm"

    async def place_order(self, **kwargs):
        return SimpleNamespace(
            is_success=True,
            exchange_order_id=f"exchange-{kwargs['client_order_id']}",
            status="FILLED",
            filled_qty=None,
            average_exec_price=None,
        )


class _FakeOrderLifecycle:
    def __init__(self) -> None:
        self.registered_order_ids: list[str] = []
        self.submitted_order_ids: list[str] = []
        self.confirmed_order_ids: list[str] = []
        self.filled_order_ids: list[str] = []

    async def register_created_order(self, order, *, metadata=None):
        self.registered_order_ids.append(order.id)
        return order

    async def submit_order(self, order_id: str, exchange_order_id: str | None = None):
        self.submitted_order_ids.append(order_id)
        return SimpleNamespace(id=order_id, exchange_order_id=exchange_order_id)

    async def confirm_order(self, order_id: str, exchange_order_id: str | None = None):
        self.confirmed_order_ids.append(order_id)
        return SimpleNamespace(id=order_id, exchange_order_id=exchange_order_id)

    async def update_order_filled(self, order_id: str, *, filled_qty, average_exec_price):
        self.filled_order_ids.append(order_id)
        return SimpleNamespace(
            id=order_id,
            filled_qty=filled_qty,
            average_exec_price=average_exec_price,
        )


@pytest.mark.asyncio
async def test_network_timeout_records_outcome_unknown_without_retry(
    pg_control_connection,
):
    command_id = _prepared_entry_command_id(pg_control_connection)
    gateway = _TimeoutGateway()
    lifecycle = _FakeOrderLifecycle()

    result = await api_trading_console._execute_one_ticket_bound_exchange_command(
        engine=pg_control_connection.engine,
        exchange_command_id=command_id,
        gateway=gateway,
        order_lifecycle_service=lifecycle,
        now_ms=NOW_MS + 5000,
    )

    assert result["status"] == "exchange_command_outcome_unknown"
    assert _command_state(pg_control_connection, command_id) == "outcome_unknown"
    assert gateway.call_count == 1


@pytest.mark.asyncio
async def test_gateway_call_occurs_without_open_command_transaction(
    pg_control_connection,
):
    command_id = _prepared_entry_command_id(pg_control_connection)
    gateway = _NoTransactionGateway(pg_control_connection.engine)

    result = await api_trading_console._execute_one_ticket_bound_exchange_command(
        engine=pg_control_connection.engine,
        exchange_command_id=command_id,
        gateway=gateway,
        order_lifecycle_service=_FakeOrderLifecycle(),
        now_ms=NOW_MS + 5000,
    )

    assert result["status"] == "exchange_command_confirmed_submitted"
    assert gateway.saw_open_transaction is False
    assert _command_state(pg_control_connection, command_id) == "confirmed_submitted"


@pytest.mark.asyncio
async def test_filled_response_without_execution_facts_is_confirmed_for_reconciliation(
    pg_control_connection,
):
    command_id = _prepared_entry_command_id(pg_control_connection)
    lifecycle = _FakeOrderLifecycle()

    result = await api_trading_console._execute_one_ticket_bound_exchange_command(
        engine=pg_control_connection.engine,
        exchange_command_id=command_id,
        gateway=_FilledWithoutExecutionFactsGateway(),
        order_lifecycle_service=lifecycle,
        now_ms=NOW_MS + 5000,
    )

    assert result["status"] == "exchange_command_confirmed_submitted"
    assert lifecycle.filled_order_ids == []
    assert len(lifecycle.confirmed_order_ids) == 1
    assert _command_state(pg_control_connection, command_id) == "confirmed_submitted"


@pytest.mark.asyncio
async def test_authoritative_gateway_rejection_is_confirmed_rejected(
    pg_control_connection,
):
    command_id = _prepared_entry_command_id(pg_control_connection)

    result = await api_trading_console._execute_one_ticket_bound_exchange_command(
        engine=pg_control_connection.engine,
        exchange_command_id=command_id,
        gateway=_AuthoritativeRejectGateway(),
        order_lifecycle_service=_FakeOrderLifecycle(),
        now_ms=NOW_MS + 5000,
    )

    assert result["status"] == "exchange_command_confirmed_rejected"
    assert _command_state(pg_control_connection, command_id) == "confirmed_rejected"


@pytest.mark.asyncio
async def test_success_response_without_exchange_order_id_is_outcome_unknown(
    pg_control_connection,
):
    command_id = _prepared_entry_command_id(pg_control_connection)

    result = await api_trading_console._execute_one_ticket_bound_exchange_command(
        engine=pg_control_connection.engine,
        exchange_command_id=command_id,
        gateway=_MissingExchangeIdGateway(),
        order_lifecycle_service=_FakeOrderLifecycle(),
        now_ms=NOW_MS + 5000,
    )

    assert result["status"] == "exchange_command_outcome_unknown"
    assert _command_state(pg_control_connection, command_id) == "outcome_unknown"


def _prepared_entry_command_id(conn) -> str:
    ids = _create_ready_protected_submit(conn)
    _prepare_real_submit(conn, ids)
    command_id = str(
        conn.execute(
            text(
                "SELECT exchange_command_id "
                "FROM brc_ticket_bound_exchange_commands "
                "WHERE order_role = 'ENTRY'"
            )
        ).scalar_one()
    )
    conn.commit()
    return command_id


def _command_state(conn, command_id: str) -> str:
    return str(
        conn.execute(
            text(
                "SELECT command_state FROM brc_ticket_bound_exchange_commands "
                "WHERE exchange_command_id = :command_id"
            ),
            {"command_id": command_id},
        ).scalar_one()
    )


class _TimeoutGateway:
    runtime_account_id = "owner-subaccount-runtime-v0"
    runtime_exchange_id = "binance_usdm"

    def __init__(self) -> None:
        self.call_count = 0

    async def place_order(self, **_kwargs):
        self.call_count += 1
        raise ConnectionLostError("timeout", "C-001")


class _NoTransactionGateway:
    runtime_account_id = "owner-subaccount-runtime-v0"
    runtime_exchange_id = "binance_usdm"

    def __init__(self, engine) -> None:
        self.engine = engine
        self.saw_open_transaction = None

    async def place_order(self, **kwargs):
        with self.engine.connect() as conn:
            self.saw_open_transaction = conn.in_transaction()
        return SimpleNamespace(
            is_success=True,
            exchange_order_id=f"exchange-{kwargs['client_order_id']}",
        )


class _AuthoritativeRejectGateway:
    runtime_account_id = "owner-subaccount-runtime-v0"
    runtime_exchange_id = "binance_usdm"

    async def place_order(self, **_kwargs):
        return SimpleNamespace(
            is_success=False,
            error_code="F-011",
            error_message="invalid order",
        )


class _MissingExchangeIdGateway:
    runtime_account_id = "owner-subaccount-runtime-v0"
    runtime_exchange_id = "binance_usdm"

    async def place_order(self, **_kwargs):
        return SimpleNamespace(is_success=True, exchange_order_id=None)
