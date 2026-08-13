from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Self

import pytest
from pydantic import ValidationError

from src.trading_kernel.application.owner_control import (
    advance_flatten_operation_once,
    preview_flatten_all,
    set_global_entry_state,
    strategy_entry_is_enabled,
)
from src.trading_kernel.application.ports import OwnerPolicySnapshot
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


@pytest.mark.asyncio
async def test_flatten_preview_is_account_wide_across_runtime_profiles() -> None:
    policy = OwnerPolicySnapshot(
        owner_policy_id="policy-main",
        policy_version=9,
        enabled=True,
        new_entry_submit_enabled=True,
        priority_rank=1,
        max_concurrent_tickets=3,
        family_ticket_limits={
            "long_continuation": 1,
            "opening_range": 2,
            "rally_failure_short": 1,
        },
        max_ticket_stop_risk_fraction=Decimal("0.02"),
        max_gross_stop_risk_fraction=Decimal("0.06"),
        max_ticket_initial_margin_fraction=Decimal("0.30"),
        max_gross_initial_margin_utilization=Decimal("0.90"),
        directional_stop_risk_limit_fraction=Decimal("0.04"),
        min_materialization_ratio=Decimal("0.50"),
        max_leverage=10,
        supported_margin_mode="cross",
        post_stop_stress_multiple=Decimal(2),
        max_post_fill_stop_risk_overrun_fraction=Decimal("0.10"),
    )
    aggregates = {
        "ticket:crypto": SimpleNamespace(status=AggregateStatus.POSITION_PROTECTED),
        "ticket:tradfi": SimpleNamespace(status=AggregateStatus.POSITION_PROTECTED),
    }

    class UnitOfWork:
        entry_admission = SimpleNamespace(
            get_owner_policy=lambda _policy_id: _async_value(policy)
        )
        aggregates = SimpleNamespace(
            list_active_ticket_ids=lambda **scope: _active_account_tickets(scope),
            get=lambda ticket_id: _async_value(aggregates[ticket_id]),
        )

    preview = await preview_flatten_all(
        UnitOfWork(),
        owner_policy_id="policy-main",
        venue_id="binance-usdm",
        account_id="owner-account",
    )

    assert preview.ticket_ids == ("ticket:crypto", "ticket:tradfi")
    assert preview.runtime_profile_id == "account-wide"


@pytest.mark.asyncio
async def test_global_resume_checks_the_whole_policy_scope() -> None:
    policy = _policy(new_entry_submit_enabled=False)

    class OwnerControls:
        blocker_policy_id: str | None = None

        async def get_authorization_by_idempotency_key(self, _key: str):
            return None

        async def get_global_entry_resume_blocker(
            self,
            *,
            owner_policy_id: str,
        ) -> None:
            self.blocker_policy_id = owner_policy_id

        async def add_authorization(self, _authorization) -> None:
            return None

        async def set_global_entry_enabled(self, **_kwargs):
            return policy.model_copy(
                update={
                    "policy_version": policy.policy_version + 1,
                    "new_entry_submit_enabled": True,
                }
            )

    owner_controls = OwnerControls()
    uow = SimpleNamespace(
        entry_admission=SimpleNamespace(
            get_owner_policy=lambda _policy_id: _async_value(policy)
        ),
        owner_controls=owner_controls,
    )

    updated = await set_global_entry_state(
        uow,
        owner_policy_id="policy-main",
        enabled=True,
        request=SimpleNamespace(
            expected_version=policy.policy_version,
            reason="owner_resume",
            idempotency_key="owner-request:resume",
            owner_identity="owner",
            now_ms=300,
        ),
        authentication_strength="totp_step_up",
    )

    assert owner_controls.blocker_policy_id == "policy-main"
    assert updated.new_entry_submit_enabled


async def _active_account_tickets(scope: dict[str, object]) -> tuple[str, ...]:
    assert scope == {
        "venue_id": "binance-usdm",
        "account_id": "owner-account",
        "limit": 3,
    }
    return ("ticket:crypto", "ticket:tradfi")


def _policy(*, new_entry_submit_enabled: bool) -> OwnerPolicySnapshot:
    return OwnerPolicySnapshot(
        owner_policy_id="policy-main",
        policy_version=9,
        enabled=True,
        new_entry_submit_enabled=new_entry_submit_enabled,
        priority_rank=1,
        max_concurrent_tickets=3,
        family_ticket_limits={
            "long_continuation": 1,
            "opening_range": 2,
            "rally_failure_short": 1,
        },
        max_ticket_stop_risk_fraction=Decimal("0.02"),
        max_gross_stop_risk_fraction=Decimal("0.06"),
        max_ticket_initial_margin_fraction=Decimal("0.30"),
        max_gross_initial_margin_utilization=Decimal("0.90"),
        directional_stop_risk_limit_fraction=Decimal("0.04"),
        min_materialization_ratio=Decimal("0.50"),
        max_leverage=10,
        supported_margin_mode="cross",
        post_stop_stress_multiple=Decimal(2),
        max_post_fill_stop_risk_overrun_fraction=Decimal("0.10"),
    )


async def _async_value(value: object) -> object:
    return value
