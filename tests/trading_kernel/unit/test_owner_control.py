from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.trading_kernel.application.owner_control import strategy_entry_is_enabled
from src.trading_kernel.domain.owner_control import (
    ControlOperationState,
    OwnerAuthorization,
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
