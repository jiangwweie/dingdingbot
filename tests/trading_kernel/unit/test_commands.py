from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    CommandGenerationError,
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandResult,
    ExchangeCommandStatus,
    OrderCommandPayload,
    build_command_id,
    build_venue_client_order_id,
    require_next_generation_allowed,
)
from tests.trading_kernel.unit.test_ticket import _identity


def _payload(*, reduce_only: bool = False) -> OrderCommandPayload:
    return OrderCommandPayload(
        side="sell" if reduce_only else "buy",
        quantity=Decimal("0.001"),
        order_type="market",
        reduce_only=reduce_only,
    )


def test_exchange_command_identity_is_deterministic_and_venue_safe() -> None:
    identity = _identity()
    command_id = build_command_id(
        ticket_id=identity.ticket_id,
        kind=ExchangeCommandKind.ENTRY,
        generation=1,
    )
    same = build_command_id(
        ticket_id=identity.ticket_id,
        kind=ExchangeCommandKind.ENTRY,
        generation=1,
    )
    client_order_id = build_venue_client_order_id(command_id)

    assert command_id == same
    assert command_id.startswith("command:")
    assert client_order_id.startswith("brc-")
    assert len(client_order_id) <= 36


def test_exchange_command_is_immutable_and_exact() -> None:
    identity = _identity()
    command = ExchangeCommand(
        command_id=build_command_id(
            ticket_id=identity.ticket_id,
            kind=ExchangeCommandKind.ENTRY,
            generation=1,
        ),
        ticket_identity=identity,
        kind=ExchangeCommandKind.ENTRY,
        generation=1,
        idempotency_key="entry-idempotency-1",
        venue_client_order_id="brc-entry-1",
        payload=_payload(),
        status=ExchangeCommandStatus.PREPARED,
        created_at_ms=1_000,
        deadline_at_ms=10_000,
    )

    with pytest.raises(ValidationError):
        command.status = ExchangeCommandStatus.CLAIMED  # type: ignore[misc]

    with pytest.raises(ValidationError):
        ExchangeCommand.model_validate(
            {
                **command.model_dump(),
                "unexpected": True,
            }
        )


def test_exchange_command_result_requires_authoritative_outcome_shape() -> None:
    accepted = ExchangeCommandResult(
        status=ExchangeCommandStatus.ACCEPTED,
        observed_at_ms=2_000,
        exchange_order_id="venue-order-1",
    )
    rejected = ExchangeCommandResult(
        status=ExchangeCommandStatus.REJECTED,
        observed_at_ms=2_001,
        reason="insufficient_margin",
    )
    unknown = ExchangeCommandResult(
        status=ExchangeCommandStatus.OUTCOME_UNKNOWN,
        observed_at_ms=2_002,
        reason="timeout",
    )

    assert accepted.exchange_order_id == "venue-order-1"
    assert rejected.reason == "insufficient_margin"
    assert unknown.status is ExchangeCommandStatus.OUTCOME_UNKNOWN

    with pytest.raises(ValidationError):
        ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=2_000,
        )


def test_cancel_command_requires_exact_exchange_order_identity() -> None:
    identity = _identity()
    command = ExchangeCommand(
        command_id=build_command_id(
            ticket_id=identity.ticket_id,
            kind=ExchangeCommandKind.CANCEL_ORDER,
            generation=1,
        ),
        ticket_identity=identity,
        kind=ExchangeCommandKind.CANCEL_ORDER,
        generation=1,
        idempotency_key="cancel-stop-1",
        venue_client_order_id="brc-cancel-stop-1",
        payload=CancelCommandPayload(exchange_order_id="stop-order-1"),
        status=ExchangeCommandStatus.PREPARED,
        created_at_ms=2_000,
        deadline_at_ms=12_000,
    )

    assert command.payload.exchange_order_id == "stop-order-1"

    with pytest.raises(ValidationError):
        ExchangeCommand(
            **{
                **command.model_dump(),
                "kind": ExchangeCommandKind.EXIT,
            }
        )

    with pytest.raises(ValidationError):
        CancelCommandPayload(exchange_order_id=" ")

    with pytest.raises(ValidationError):
        ExchangeCommandResult(
            status=ExchangeCommandStatus.REJECTED,
            observed_at_ms=2_000,
        )


def test_entry_command_cannot_have_retry_generation() -> None:
    with pytest.raises(ValidationError):
        ExchangeCommand(
            command_id="command:entry-2",
            ticket_identity=_identity(),
            kind=ExchangeCommandKind.ENTRY,
            generation=2,
            idempotency_key="entry-idempotency-2",
            venue_client_order_id="brc-entry-2",
            payload=_payload(),
            status=ExchangeCommandStatus.PREPARED,
            created_at_ms=1_000,
            deadline_at_ms=10_000,
        )


@pytest.mark.parametrize(
    "kind",
    [
        ExchangeCommandKind.ENTRY,
        ExchangeCommandKind.INITIAL_STOP,
        ExchangeCommandKind.EXIT,
    ],
)
def test_unknown_outcome_blocks_new_generation(kind: ExchangeCommandKind) -> None:
    with pytest.raises(CommandGenerationError):
        require_next_generation_allowed(
            kind=kind,
            prior_status=ExchangeCommandStatus.OUTCOME_UNKNOWN,
            next_generation=2,
        )


def test_protection_and_exit_may_retry_after_authoritative_rejection() -> None:
    require_next_generation_allowed(
        kind=ExchangeCommandKind.INITIAL_STOP,
        prior_status=ExchangeCommandStatus.REJECTED,
        next_generation=2,
    )
    require_next_generation_allowed(
        kind=ExchangeCommandKind.EXIT,
        prior_status=ExchangeCommandStatus.REJECTED,
        next_generation=2,
    )

    with pytest.raises(CommandGenerationError):
        require_next_generation_allowed(
            kind=ExchangeCommandKind.ENTRY,
            prior_status=ExchangeCommandStatus.REJECTED,
            next_generation=2,
        )
