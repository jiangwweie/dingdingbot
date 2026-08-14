from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.trading_kernel.application.dispatch_exchange_command import (
    _command_result_event,
)
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    CommandGenerationError,
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandResult,
    ExchangeCommandStatus,
    OrderCommandPayload,
    SetLeverageCommandPayload,
    SetLeverageCommandResult,
    build_command_id,
    build_venue_client_order_id,
    require_next_generation_allowed,
)
from tests.trading_kernel.support.tickets import make_ticket_identity as _identity
from tests.trading_kernel.unit.test_reducer import _reconciliation_pending_aggregate


def _payload(*, reduce_only: bool = False) -> OrderCommandPayload:
    return OrderCommandPayload(
        side="sell" if reduce_only else "buy",
        quantity=Decimal("0.001"),
        order_type="market",
        reduce_only=reduce_only,
        required_configured_leverage=5,
        leverage_verification_digest="sha256:" + "1" * 64,
    )


def test_limit_order_requires_explicit_time_in_force() -> None:
    with pytest.raises(ValidationError, match="time_in_force"):
        OrderCommandPayload(
            side="sell",
            quantity=Decimal("0.001"),
            order_type="limit",
            reduce_only=True,
            limit_price=Decimal(101),
        )


def test_stop_market_forbids_time_in_force() -> None:
    with pytest.raises(ValidationError, match="time_in_force"):
        OrderCommandPayload(
            side="sell",
            quantity=Decimal("0.001"),
            order_type="stop_market",
            reduce_only=True,
            stop_price=Decimal(99),
            time_in_force="GTX",
        )


def test_limit_gtx_payload_is_immutable_and_serializable() -> None:
    payload = OrderCommandPayload(
        side="sell",
        quantity=Decimal("0.001"),
        order_type="limit",
        reduce_only=True,
        limit_price=Decimal(101),
        time_in_force="GTX",
    )

    assert payload.time_in_force == "GTX"
    assert OrderCommandPayload.model_validate(payload.model_dump()) == payload


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
        payload=CancelCommandPayload(
            exchange_order_id="stop-order-1",
            order_namespace="conditional",
            purpose="runner_old_stop",
        ),
        status=ExchangeCommandStatus.PREPARED,
        created_at_ms=2_000,
        deadline_at_ms=12_000,
    )

    assert isinstance(command.payload, CancelCommandPayload)
    assert command.payload.exchange_order_id == "stop-order-1"
    assert command.payload.order_namespace == "conditional"
    assert command.payload.purpose == "runner_old_stop"

    with pytest.raises(ValidationError):
        ExchangeCommand(
            **{
                **command.model_dump(),
                "kind": ExchangeCommandKind.EXIT,
            }
        )

    with pytest.raises(ValidationError):
        CancelCommandPayload(
            exchange_order_id=" ",
            order_namespace="regular",
            purpose="reconciliation_cleanup",
        )

    with pytest.raises(ValidationError):
        CancelCommandPayload.model_validate(
            {
                "exchange_order_id": "stop-order-1",
                "order_namespace": "conditional",
            }
        )

    with pytest.raises(ValidationError):
        ExchangeCommandResult(
            status=ExchangeCommandStatus.REJECTED,
            observed_at_ms=2_000,
        )


def test_cancel_result_refuses_a_frozen_purpose_that_contradicts_state() -> None:
    aggregate = _reconciliation_pending_aggregate()
    command = ExchangeCommand(
        command_id="command:cancel-runner-stop",
        ticket_identity=aggregate.identity,
        kind=ExchangeCommandKind.CANCEL_ORDER,
        generation=1,
        idempotency_key="cancel-runner-stop",
        venue_client_order_id="brc-cancel-runner-stop",
        payload=CancelCommandPayload(
            exchange_order_id="stop-order-1",
            order_namespace="conditional",
            purpose="runner_old_stop",
        ),
        status=ExchangeCommandStatus.CLAIMED,
        created_at_ms=2_000,
        deadline_at_ms=12_000,
    )

    with pytest.raises(RuntimeError, match="cancel purpose is incompatible"):
        _command_result_event(
            command=command,
            aggregate=aggregate,
            result=ExchangeCommandResult(
                status=ExchangeCommandStatus.ACCEPTED,
                observed_at_ms=2_100,
                exchange_order_id="stop-order-1",
            ),
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


def test_set_leverage_generation_is_exactly_one_and_has_no_order_identity() -> None:
    identity = _identity()
    command = ExchangeCommand(
        command_id=build_command_id(
            ticket_id=identity.ticket_id,
            kind=ExchangeCommandKind.SET_LEVERAGE,
            generation=1,
        ),
        ticket_identity=identity,
        kind=ExchangeCommandKind.SET_LEVERAGE,
        generation=1,
        idempotency_key="set-leverage-idempotency-1",
        venue_client_order_id=None,
        payload=SetLeverageCommandPayload(
            desired_leverage=5,
            owner_policy_version=7,
            entry_admission_snapshot_digest="sha256:" + "1" * 64,
            leverage_fact_digest="sha256:" + "2" * 64,
        ),
        status=ExchangeCommandStatus.PREPARED,
        created_at_ms=1_000,
        deadline_at_ms=10_000,
    )

    assert command.kind is ExchangeCommandKind.SET_LEVERAGE
    assert command.venue_client_order_id is None
    assert isinstance(command.payload, SetLeverageCommandPayload)
    assert command.payload.desired_leverage == 5

    with pytest.raises(
        ValidationError,
        match="SET_LEVERAGE command cannot have a retry generation",
    ):
        ExchangeCommand.model_validate(
            {
                **command.model_dump(),
                "generation": 2,
            }
        )

    with pytest.raises(ValidationError, match="forbids venue_client_order_id"):
        ExchangeCommand.model_validate(
            {
                **command.model_dump(),
                "venue_client_order_id": "brc-not-an-order",
            }
        )


def test_set_leverage_result_is_distinct_from_order_result() -> None:
    result = SetLeverageCommandResult(
        exchange_configured_leverage=5,
        leverage_verified_at_ms=2_000,
        leverage_verification_digest="sha256:" + "3" * 64,
    )

    assert result.exchange_configured_leverage == 5

    with pytest.raises(ValidationError):
        SetLeverageCommandResult(
            exchange_configured_leverage=0,
            leverage_verified_at_ms=2_000,
            leverage_verification_digest="sha256:" + "3" * 64,
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
