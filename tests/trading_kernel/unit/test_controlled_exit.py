from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import src.trading_kernel.application.controlled_exit as controlled_exit_module
from src.trading_kernel.application.controlled_exit import (
    ControlledExitAuthorization,
    ControlledExitClassification,
    ControlledExitRequest,
    classify_controlled_exit_status,
    request_controlled_exits,
)
from src.trading_kernel.domain.aggregate import AggregateStatus

TARGET_COMMIT = "a" * 40


def test_deployment_drain_authorization_builds_canonical_reason() -> None:
    authorization = ControlledExitAuthorization(
        purpose="deployment_drain",
        authorization_id="deploy-20260804-01",
        target_commit=TARGET_COMMIT,
    )

    assert authorization.reason == (
        f"deployment_drain:deploy-20260804-01:{TARGET_COMMIT}"
    )


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("purpose", "operator_close", "deployment_drain"),
        ("authorization_id", "", "authorization identity"),
        ("authorization_id", "has:colon", "authorization identity"),
        ("target_commit", "A" * 40, "target commit"),
        ("target_commit", "a" * 39, "target commit"),
    ],
)
def test_controlled_exit_authorization_rejects_invalid_identity(
    field: str,
    value: str,
    expected: str,
) -> None:
    payload = {
        "purpose": "deployment_drain",
        "authorization_id": "deploy-20260804-01",
        "target_commit": TARGET_COMMIT,
    }
    payload[field] = value

    with pytest.raises(ValidationError, match=expected):
        ControlledExitAuthorization.model_validate(payload)


@pytest.mark.parametrize(
    "status",
    [AggregateStatus.POSITION_PROTECTED, AggregateStatus.RUNNER_PROTECTED],
)
def test_protected_ticket_is_eligible_for_controlled_exit(
    status: AggregateStatus,
) -> None:
    assert (
        classify_controlled_exit_status(status)
        is ControlledExitClassification.ELIGIBLE
    )


@pytest.mark.parametrize(
    "status",
    [
        AggregateStatus.EXIT_PENDING,
        AggregateStatus.EXIT_ACCEPTED,
        AggregateStatus.EXIT_OUTCOME_UNKNOWN,
        AggregateStatus.RECONCILIATION_PENDING,
        AggregateStatus.SETTLEMENT_PENDING,
        AggregateStatus.REVIEW_PENDING,
    ],
)
def test_existing_exit_progress_is_resume_only(status: AggregateStatus) -> None:
    assert (
        classify_controlled_exit_status(status)
        is ControlledExitClassification.IN_PROGRESS
    )


@pytest.mark.parametrize(
    "status",
    [
        AggregateStatus.TERMINAL,
        AggregateStatus.LEVERAGE_REJECTED,
        AggregateStatus.ENTRY_REJECTED,
        AggregateStatus.ENTRY_RECONCILED_ABSENT,
    ],
)
def test_terminal_or_no_exposure_rejection_needs_no_exit(
    status: AggregateStatus,
) -> None:
    assert (
        classify_controlled_exit_status(status)
        is ControlledExitClassification.TERMINAL
    )


@pytest.mark.parametrize(
    "status",
    [
        AggregateStatus.ENTRY_PENDING,
        AggregateStatus.PROTECTION_PENDING,
        AggregateStatus.EXIT_REJECTED,
        AggregateStatus.CANCEL_REJECTED,
        AggregateStatus.CANCEL_OUTCOME_UNKNOWN,
    ],
)
def test_unsafe_or_unsupported_state_blocks_controlled_exit(
    status: AggregateStatus,
) -> None:
    assert (
        classify_controlled_exit_status(status)
        is ControlledExitClassification.BLOCKED
    )


@pytest.mark.asyncio
async def test_controlled_exit_requests_eligible_tickets_in_stable_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = _FakeUnitOfWorkFactory(
        {
            "ticket:b": AggregateStatus.POSITION_PROTECTED,
            "ticket:a": AggregateStatus.RUNNER_PROTECTED,
        }
    )
    calls: list[tuple[str, str, int]] = []

    async def record_request(_uow, request) -> None:
        calls.append((request.ticket_id, request.reason, request.requested_at_ms))

    monkeypatch.setattr(controlled_exit_module, "request_exit", record_request)

    result = await request_controlled_exits(factory, _controlled_exit_request())

    assert result.requested_ticket_ids == ("ticket:a", "ticket:b")
    assert result.in_progress_ticket_ids == ()
    assert result.blocked_ticket_ids == ()
    assert calls == [
        (
            "ticket:a",
            f"deployment_drain:deploy-20260804-01:{TARGET_COMMIT}",
            2_000,
        ),
        (
            "ticket:b",
            f"deployment_drain:deploy-20260804-01:{TARGET_COMMIT}",
            2_000,
        ),
    ]


@pytest.mark.asyncio
async def test_deployment_drain_covers_tickets_across_runtime_profiles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = _FakeUnitOfWorkFactory(
        {
            "ticket:crypto": AggregateStatus.POSITION_PROTECTED,
            "ticket:tradfi": AggregateStatus.RUNNER_PROTECTED,
        }
    )
    calls: list[str] = []

    async def record_request(_uow, request) -> None:
        calls.append(request.ticket_id)

    monkeypatch.setattr(controlled_exit_module, "request_exit", record_request)

    result = await request_controlled_exits(factory, _controlled_exit_request())

    assert factory.selection_scopes == [
        {
            "venue_id": "binance-usdm",
            "account_id": "account:tokyo",
            "limit": 3,
        }
    ]
    assert result.requested_ticket_ids == ("ticket:crypto", "ticket:tradfi")
    assert calls == ["ticket:crypto", "ticket:tradfi"]


@pytest.mark.asyncio
async def test_controlled_exit_resume_does_not_request_progressing_ticket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = _FakeUnitOfWorkFactory(
        {"ticket:a": AggregateStatus.EXIT_PENDING}
    )
    calls: list[str] = []

    async def record_request(_uow, request) -> None:
        calls.append(request.ticket_id)

    monkeypatch.setattr(controlled_exit_module, "request_exit", record_request)

    result = await request_controlled_exits(factory, _controlled_exit_request())

    assert result.requested_ticket_ids == ()
    assert result.in_progress_ticket_ids == ("ticket:a",)
    assert calls == []


@pytest.mark.asyncio
async def test_initial_blocked_ticket_prevents_every_exit_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = _FakeUnitOfWorkFactory(
        {
            "ticket:a": AggregateStatus.POSITION_PROTECTED,
            "ticket:b": AggregateStatus.EXIT_REJECTED,
        }
    )
    calls: list[str] = []

    async def record_request(_uow, request) -> None:
        calls.append(request.ticket_id)

    monkeypatch.setattr(controlled_exit_module, "request_exit", record_request)

    result = await request_controlled_exits(factory, _controlled_exit_request())

    assert result.requested_ticket_ids == ()
    assert result.blocked_ticket_ids == ("ticket:b",)
    assert calls == []


@pytest.mark.asyncio
async def test_ticket_that_terminalizes_after_selection_is_a_safe_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = _FakeUnitOfWorkFactory(
        {"ticket:a": AggregateStatus.POSITION_PROTECTED},
        terminalize_after_orientation={"ticket:a"},
    )
    calls: list[str] = []

    async def record_request(_uow, request) -> None:
        calls.append(request.ticket_id)

    monkeypatch.setattr(controlled_exit_module, "request_exit", record_request)

    result = await request_controlled_exits(factory, _controlled_exit_request())

    assert result.terminal_ticket_ids == ("ticket:a",)
    assert calls == []


def _controlled_exit_request() -> ControlledExitRequest:
    return ControlledExitRequest(
        authorization=ControlledExitAuthorization(
            purpose="deployment_drain",
            authorization_id="deploy-20260804-01",
            target_commit=TARGET_COMMIT,
        ),
        runtime_profile_id="account-wide",
        venue_id="binance-usdm",
        account_id="account:tokyo",
        max_active_tickets=3,
        requested_at_ms=2_000,
    )


class _FakeAggregateRepository:
    def __init__(
        self,
        factory: _FakeUnitOfWorkFactory,
        orientation: bool,
    ) -> None:
        self._factory = factory
        self._orientation = orientation

    async def list_active_ticket_ids(self, **scope) -> tuple[str, ...]:
        self._factory.selection_scopes.append(scope)
        return tuple(sorted(self._factory.statuses))

    async def get(self, ticket_id: str):
        if (
            not self._orientation
            and ticket_id in self._factory.terminalize_after_orientation
        ):
            return None
        return SimpleNamespace(status=self._factory.statuses[ticket_id])


class _FakeUnitOfWork:
    def __init__(
        self,
        factory: _FakeUnitOfWorkFactory,
        orientation: bool,
    ) -> None:
        self.aggregates = _FakeAggregateRepository(factory, orientation)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None


class _FakeUnitOfWorkFactory:
    def __init__(
        self,
        statuses: dict[str, AggregateStatus],
        *,
        terminalize_after_orientation: set[str] | None = None,
    ) -> None:
        self.statuses = statuses
        self.terminalize_after_orientation = terminalize_after_orientation or set()
        self.selection_scopes: list[dict[str, object]] = []
        self._calls = 0

    def __call__(self) -> _FakeUnitOfWork:
        self._calls += 1
        return _FakeUnitOfWork(self, orientation=self._calls == 1)
