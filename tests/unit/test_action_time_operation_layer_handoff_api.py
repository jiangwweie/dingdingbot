from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException

from src.interfaces import api_trading_console


@pytest.mark.asyncio
async def test_ticket_bound_operation_layer_handoff_api_returns_ready_body(
    monkeypatch,
):
    monkeypatch.setattr(
        api_trading_console,
        "_run_ticket_bound_operation_layer_handoff",
        lambda *, ticket_id, finalgate_pass_id: {
            "status": "operation_layer_handoff_ready",
            "ticket_id": ticket_id,
            "finalgate_pass_id": finalgate_pass_id,
            "operation_layer_handoff_id": "handoff-1",
            "operation_submit_command_id": "operation-submit-1",
            "action_time_lane_input_id": "lane-1",
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
            "blockers": [],
            "command_plan": {
                "ticket_id": ticket_id,
                "finalgate_pass_id": finalgate_pass_id,
                "operation_submit_command_id": "operation-submit-1",
                "requires_ticket_bound_protected_submit": True,
            },
            "next_action": "prepare_ticket_bound_protected_submit",
            "authority_boundary": "ticket_id_finalgate_pass_operation_layer_handoff",
        },
    )

    response = await api_trading_console.runtime_operation_layer_handoff_for_ticket(
        "ticket-1",
        "finalgate-pass-1",
    )
    payload = response.model_dump()

    assert payload["status"] == "operation_layer_handoff_ready"
    assert payload["operation_layer_verdict"] == "ready"
    assert payload["ticket_id"] == "ticket-1"
    assert payload["finalgate_pass_id"] == "finalgate-pass-1"
    assert payload["operation_submit_command_id"] == "operation-submit-1"
    assert payload["command_plan"]["requires_ticket_bound_protected_submit"] is True
    assert "authorization_id" not in payload["command_plan"]
    assert payload["submit_executed"] is False
    assert payload["operation_layer_submit_called"] is False
    assert payload["order_created"] is False
    assert payload["exchange_called"] is False
    assert payload["exchange_write_called"] is False
    assert payload["owner_bounded_execution_called"] is False
    assert payload["order_lifecycle_called"] is False


@pytest.mark.asyncio
async def test_ticket_bound_operation_layer_handoff_api_returns_blocked_body(
    monkeypatch,
):
    monkeypatch.setattr(
        api_trading_console,
        "_run_ticket_bound_operation_layer_handoff",
        lambda *, ticket_id, finalgate_pass_id: {
            "status": "blocked",
            "ticket_id": ticket_id,
            "finalgate_pass_id": finalgate_pass_id,
            "blockers": ["finalgate_pass_id_mismatch:expected=a:actual=b"],
            "command_plan": {},
            "next_action": "repair_ticket_bound_operation_layer_handoff_inputs",
            "authority_boundary": "ticket_id_finalgate_pass_operation_layer_handoff",
        },
    )

    response = await api_trading_console.runtime_operation_layer_handoff_for_ticket(
        "ticket-1",
        "finalgate-pass-1",
    )
    payload = response.model_dump()

    assert payload["status"] == "blocked"
    assert payload["operation_layer_verdict"] == "block"
    assert payload["blockers"] == ["finalgate_pass_id_mismatch:expected=a:actual=b"]
    assert payload["exchange_write_called"] is False


@pytest.mark.asyncio
async def test_ticket_bound_operation_layer_handoff_api_fails_closed_without_pg(
    monkeypatch,
):
    def _raise(*, ticket_id: str, finalgate_pass_id: str):
        raise RuntimeError(
            "PG_DATABASE_URL is required for ticket-bound Operation Layer handoff"
        )

    monkeypatch.setattr(
        api_trading_console,
        "_run_ticket_bound_operation_layer_handoff",
        _raise,
    )

    with pytest.raises(HTTPException) as exc:
        await api_trading_console.runtime_operation_layer_handoff_for_ticket(
            "ticket-1",
            "finalgate-pass-1",
        )

    assert exc.value.status_code == 503
    assert "PG_DATABASE_URL is required" in exc.value.detail


def test_ticket_bound_operation_layer_handoff_api_signature_has_no_legacy_inputs():
    signature = inspect.signature(
        api_trading_console.runtime_operation_layer_handoff_for_ticket
    )

    assert list(signature.parameters) == ["ticket_id", "finalgate_pass_id"]
    assert "authorization_id" not in signature.parameters
    assert "signal_input_json" not in signature.parameters
    assert "prepared_authorization_id" not in signature.parameters
