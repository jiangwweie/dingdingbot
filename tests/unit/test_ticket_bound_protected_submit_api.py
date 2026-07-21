from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.interfaces import api_trading_console


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


def test_direct_real_gateway_submit_branch_is_retired_from_console_api():
    runner_source = inspect.getsource(
        api_trading_console._run_ticket_bound_protected_submit
    )

    assert "durable_action_time_dispatch_command" in runner_source
    for legacy_symbol in (
        "_execute_ticket_bound_real_gateway_submit",
        "_execute_one_ticket_bound_exchange_command",
        "_submit_ticket_bound_orders",
    ):
        assert not hasattr(api_trading_console, legacy_symbol)


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
