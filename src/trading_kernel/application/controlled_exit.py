"""Owner-authorized source-runtime Controlled Exit semantics."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.application.ports import UnitOfWorkFactory
from src.trading_kernel.application.reconcile_ticket import (
    ExitTicketRequest,
    request_exit,
)
from src.trading_kernel.domain.aggregate import AggregateStatus

_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_AUTHORIZATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ControlledExitClassification(StrEnum):
    ELIGIBLE = "eligible"
    IN_PROGRESS = "in_progress"
    TERMINAL = "terminal"
    BLOCKED = "blocked"


class ControlledExitAuthorization(BaseModel):
    """Immutable authority for one bounded Controlled Exit purpose."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    purpose: Literal["deployment_drain"]
    authorization_id: str
    target_commit: str

    @field_validator("authorization_id", mode="before")
    @classmethod
    def _require_authorization_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if _AUTHORIZATION_ID.fullmatch(normalized) is None:
            raise ValueError("authorization identity must be canonical")
        return normalized

    @field_validator("target_commit", mode="before")
    @classmethod
    def _require_target_commit(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if _COMMIT.fullmatch(normalized) is None:
            raise ValueError("target commit must be an exact lowercase 40-hex SHA")
        return normalized

    @property
    def reason(self) -> str:
        return f"{self.purpose}:{self.authorization_id}:{self.target_commit}"


class ControlledExitRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    authorization: ControlledExitAuthorization
    runtime_profile_id: str
    venue_id: str
    account_id: str
    max_active_tickets: int
    requested_at_ms: int

    @field_validator("runtime_profile_id", "venue_id", "account_id", mode="before")
    @classmethod
    def _require_scope_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Controlled Exit scope identities must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_bounds(self) -> ControlledExitRequest:
        if self.max_active_tickets <= 0 or self.max_active_tickets > 3:
            raise ValueError("Controlled Exit active Ticket bound must be 1 through 3")
        if self.requested_at_ms <= 0:
            raise ValueError("Controlled Exit request time must be positive")
        return self


class ControlledExitResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    requested_ticket_ids: tuple[str, ...] = ()
    in_progress_ticket_ids: tuple[str, ...] = ()
    terminal_ticket_ids: tuple[str, ...] = ()
    blocked_ticket_ids: tuple[str, ...] = ()


_ELIGIBLE_STATUSES = frozenset(
    {
        AggregateStatus.POSITION_PROTECTED,
        AggregateStatus.RUNNER_PROTECTED,
    }
)
_IN_PROGRESS_STATUSES = frozenset(
    {
        AggregateStatus.EXIT_PENDING,
        AggregateStatus.EXIT_ACCEPTED,
        AggregateStatus.EXIT_OUTCOME_UNKNOWN,
        AggregateStatus.RECONCILIATION_PENDING,
        AggregateStatus.SETTLEMENT_PENDING,
        AggregateStatus.REVIEW_PENDING,
    }
)
_TERMINAL_STATUSES = frozenset(
    {
        AggregateStatus.TERMINAL,
        AggregateStatus.LEVERAGE_REJECTED,
        AggregateStatus.ENTRY_REJECTED,
        AggregateStatus.ENTRY_RECONCILED_ABSENT,
    }
)


def classify_controlled_exit_status(
    status: AggregateStatus,
) -> ControlledExitClassification:
    """Classify current Aggregate state without performing any mutation."""

    if status in _ELIGIBLE_STATUSES:
        return ControlledExitClassification.ELIGIBLE
    if status in _IN_PROGRESS_STATUSES:
        return ControlledExitClassification.IN_PROGRESS
    if status in _TERMINAL_STATUSES:
        return ControlledExitClassification.TERMINAL
    return ControlledExitClassification.BLOCKED


async def request_controlled_exits(
    uow_factory: UnitOfWorkFactory,
    request: ControlledExitRequest,
) -> ControlledExitResult:
    """Request source-owned exits after one complete write-free classification."""

    async with uow_factory() as uow:
        ticket_ids = await uow.aggregates.list_active_ticket_ids(
            runtime_profile_id=request.runtime_profile_id,
            venue_id=request.venue_id,
            account_id=request.account_id,
            limit=request.max_active_tickets,
        )
        initial = {
            ticket_id: await _classification_for_ticket(uow, ticket_id)
            for ticket_id in ticket_ids
        }

    initially_blocked = tuple(
        ticket_id
        for ticket_id in ticket_ids
        if initial[ticket_id] is ControlledExitClassification.BLOCKED
    )
    if initially_blocked:
        return ControlledExitResult(blocked_ticket_ids=initially_blocked)

    requested: list[str] = []
    in_progress: list[str] = []
    terminal: list[str] = []
    blocked: list[str] = []
    for ticket_id in ticket_ids:
        async with uow_factory() as uow:
            classification = await _classification_for_ticket(uow, ticket_id)
            if classification is ControlledExitClassification.ELIGIBLE:
                await request_exit(
                    uow,
                    ExitTicketRequest(
                        ticket_id=ticket_id,
                        reason=request.authorization.reason,
                        requested_at_ms=request.requested_at_ms,
                    ),
                )
                requested.append(ticket_id)
                continue
            if classification is ControlledExitClassification.IN_PROGRESS:
                in_progress.append(ticket_id)
                continue
            if classification is ControlledExitClassification.TERMINAL:
                terminal.append(ticket_id)
                continue
            blocked.append(ticket_id)
            break

    return ControlledExitResult(
        requested_ticket_ids=tuple(requested),
        in_progress_ticket_ids=tuple(in_progress),
        terminal_ticket_ids=tuple(terminal),
        blocked_ticket_ids=tuple(blocked),
    )


async def _classification_for_ticket(uow, ticket_id: str) -> ControlledExitClassification:
    aggregate = await uow.aggregates.get(ticket_id)
    if aggregate is None:
        return ControlledExitClassification.TERMINAL
    return classify_controlled_exit_status(aggregate.status)
