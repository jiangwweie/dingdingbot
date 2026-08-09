from __future__ import annotations

from types import SimpleNamespace
from typing import Self

import pytest
from pydantic import ValidationError

from src.trading_kernel.application.owner_control import (
    advance_flatten_operation_once,
    strategy_entry_is_enabled,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.owner_control import (
    ControlOperationState,
    OwnerAuthorization,
    OwnerControlOperation,
    StrategyEntryControl,
    StrategyEntryState,
    advance_control_operation,
    transition_strategy_entry_control,
)


def test_strategy_pause_is_monotonic_and_idempotent() -> None:
    current = StrategyEntryControl(
        strategy_group_id="SOR-001",
        entry_state=StrategyEntryState.ENABLED,
        control_version=1,
        last_event_id="control-event:1",
        reason="seed",
        updated_at_ms=100,
    )

    paused = transition_strategy_entry_control(
        current,
        target_state=StrategyEntryState.PAUSED,
        event_id="control-event:2",
        reason="owner_manual_pause",
        now_ms=200,
    )

    assert paused.entry_state is StrategyEntryState.PAUSED
    assert paused.control_version == 2
    assert transition_strategy_entry_control(
        paused,
        target_state=StrategyEntryState.PAUSED,
        event_id="control-event:ignored",
        reason="duplicate",
        now_ms=300,
    ) is paused


def test_owner_authorization_never_accepts_secret_factors() -> None:
    with pytest.raises(ValidationError):
        OwnerAuthorization.model_validate(
            {
                "authorization_id": "owner-authorization:1",
                "purpose": "owner_flatten_all",
                "owner_identity": "owner",
                "authentication_strength": "totp_step_up",
                "request_digest": "sha256:" + "a" * 64,
                "target_scope": {"runtime_profile_id": "tokyo"},
                "idempotency_key": "owner-request:1",
                "authorized_at_ms": 100,
                "totp": "123456",
            }
        )


def test_control_operation_rejects_invalid_state_jump() -> None:
    with pytest.raises(ValueError, match="invalid control operation transition"):
        advance_control_operation(
            ControlOperationState.VALIDATING,
            ControlOperationState.REVIEW_PENDING,
        )

    assert (
        advance_control_operation(
            ControlOperationState.VALIDATING,
            ControlOperationState.PENDING,
        )
        is ControlOperationState.PENDING
    )


def test_missing_strategy_control_fails_closed() -> None:
    assert not strategy_entry_is_enabled(None)


@pytest.mark.asyncio
async def test_reconciled_intervention_operation_completes() -> None:
    operation = OwnerControlOperation(
        authorization_id="owner-authorization:1",
        state=ControlOperationState.NEEDS_INTERVENTION,
        version=6,
        runtime_profile_id="tiny-live-v1",
        venue_id="binance-usdm",
        account_id="owner-account",
        target_ticket_ids=("ticket:1",),
        snapshot_digest="sha256:" + "a" * 64,
        first_blocker="ticket_incident:ticket:1:cancel_order_outcome_unknown",
        created_at_ms=100,
        updated_at_ms=200,
    )

    class OwnerControls:
        saved: OwnerControlOperation | None = None

        async def get_progressable_operation(
            self, *, for_update: bool = False
        ) -> OwnerControlOperation:
            assert for_update
            return operation

        async def save_operation(
            self,
            updated: OwnerControlOperation,
            *,
            event_payload: dict[str, object],
        ) -> None:
            assert event_payload == {"target_ticket_ids": ["ticket:1"]}
            self.saved = updated

    owner_controls = OwnerControls()

    class UnitOfWork:
        aggregates = SimpleNamespace(
            get=lambda _ticket_id: _async_value(
                SimpleNamespace(status=AggregateStatus.TERMINAL)
            )
        )
        incidents = SimpleNamespace(
            get_open_for_ticket=lambda _ticket_id: _async_value(None)
        )
        budgets = SimpleNamespace(
            get_for_ticket=lambda _ticket_id: _async_value(
                SimpleNamespace(status="released")
            )
        )
        reviews = SimpleNamespace(
            get_for_ticket=lambda _ticket_id: _async_value(object())
        )

        def __init__(self) -> None:
            self.owner_controls = owner_controls

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

    completed = await advance_flatten_operation_once(
        lambda: UnitOfWork(),
        now_ms=300,
    )

    assert completed is not None
    assert completed.state is ControlOperationState.COMPLETED
    assert completed.first_blocker is None
    assert owner_controls.saved == completed


async def _async_value(value: object) -> object:
    return value
