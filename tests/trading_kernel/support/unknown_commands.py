"""Reusable command fixtures for unknown-outcome tests."""

from __future__ import annotations

from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandStatus,
    build_command_id,
    build_venue_client_order_id,
)
from tests.trading_kernel.support.capacity_claims import make_issue_request
from tests.trading_kernel.support.tickets import make_ticket


def cancel_command() -> ExchangeCommand:
    ticket = make_issue_request(
        ticket=make_ticket(), now_ms=1_001, claim_owner="unit-test"
    ).capacity_claim.to_ticket()
    command_id = build_command_id(
        ticket_id=ticket.identity.ticket_id,
        kind=ExchangeCommandKind.CANCEL_ORDER,
        generation=1,
    )
    return ExchangeCommand(
        command_id=command_id,
        ticket_identity=ticket.identity,
        kind=ExchangeCommandKind.CANCEL_ORDER,
        generation=1,
        idempotency_key=command_id,
        venue_client_order_id=build_venue_client_order_id(command_id),
        payload=CancelCommandPayload(
            exchange_order_id="venue-stop-1",
            order_namespace="regular",
            purpose="runner_old_stop",
        ),
        status=ExchangeCommandStatus.OUTCOME_UNKNOWN,
        created_at_ms=1_001,
        deadline_at_ms=31_000,
    )
