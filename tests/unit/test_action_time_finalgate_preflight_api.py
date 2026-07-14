from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException

from src.interfaces import api_trading_console


@pytest.mark.asyncio
async def test_ticket_bound_finalgate_api_returns_dispatcher_ready_body(monkeypatch):
    monkeypatch.setattr(
        api_trading_console,
        "_run_ticket_bound_action_time_finalgate_preflight",
        lambda ticket_id: {
            "status": "finalgate_ready",
            "ticket_id": ticket_id,
            "finalgate_pass_id": "finalgate-pass-1",
            "action_time_lane_input_id": "lane-1",
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
            "blockers": [],
            "next_action": "prepare_official_operation_layer_handoff",
            "authority_boundary": "ticket_id_only_finalgate_preflight",
        },
    )

    response = await (
        api_trading_console.runtime_action_time_finalgate_preflight_for_ticket(
            "ticket-1"
        )
    )
    payload = response.model_dump()

    assert payload["status"] == "ready_for_controlled_submit_adapter"
    assert payload["controlled_submit_plan_status"] == (
        "ready_for_controlled_submit_adapter"
    )
    assert payload["final_gate_verdict"] == "pass"
    assert payload["ticket_id"] == "ticket-1"
    assert payload["finalgate_pass_id"] == "finalgate-pass-1"
    assert payload["blockers"] == []
    assert payload["submit_executed"] is False
    assert payload["order_created"] is False
    assert payload["exchange_called"] is False
    assert payload["owner_bounded_execution_called"] is False
    assert payload["order_lifecycle_called"] is False
    assert payload["operation_layer_called"] is False
    assert payload["exchange_write_called"] is False


@pytest.mark.asyncio
async def test_ticket_bound_finalgate_api_returns_blocked_body(monkeypatch):
    monkeypatch.setattr(
        api_trading_console,
        "_run_ticket_bound_action_time_finalgate_preflight",
        lambda ticket_id: {
            "status": "blocked",
            "ticket_id": ticket_id,
            "finalgate_pass_id": None,
            "blockers": ["active_position_or_open_order_conflict"],
            "next_action": "repair_ticket_bound_finalgate_inputs",
            "authority_boundary": "ticket_id_only_finalgate_preflight",
        },
    )

    response = await (
        api_trading_console.runtime_action_time_finalgate_preflight_for_ticket(
            "ticket-1"
        )
    )
    payload = response.model_dump()

    assert payload["status"] == "blocked"
    assert payload["final_gate_verdict"] == "block"
    assert payload["blockers"] == ["active_position_or_open_order_conflict"]
    assert payload["exchange_write_called"] is False


@pytest.mark.asyncio
async def test_ticket_bound_finalgate_api_fails_closed_without_pg(monkeypatch):
    def _raise(_ticket_id: str):
        raise RuntimeError("PG_DATABASE_URL is required for ticket-bound FinalGate")

    monkeypatch.setattr(
        api_trading_console,
        "_run_ticket_bound_action_time_finalgate_preflight",
        _raise,
    )

    with pytest.raises(HTTPException) as exc:
        await api_trading_console.runtime_action_time_finalgate_preflight_for_ticket(
            "ticket-1"
        )

    assert exc.value.status_code == 503
    assert "PG_DATABASE_URL is required" in exc.value.detail


def test_ticket_bound_finalgate_api_signature_has_no_legacy_authorization_inputs():
    signature = inspect.signature(
        api_trading_console.runtime_action_time_finalgate_preflight_for_ticket
    )

    assert list(signature.parameters) == ["ticket_id"]
    assert "authorization_id" not in signature.parameters
    assert "signal_input_json" not in signature.parameters
    assert "prepared_authorization_id" not in signature.parameters
