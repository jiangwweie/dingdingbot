"""Claim and dispatch one durable exchange command without a long DB transaction."""

from __future__ import annotations

import asyncio
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.application.ports import (
    UnitOfWorkFactory,
    VenueCommandRequest,
    VenuePort,
)
from src.trading_kernel.domain.commands import (
    ExchangeCommandKind,
    ExchangeCommandResult,
    ExchangeCommandStatus,
)
from src.trading_kernel.domain.events import (
    EntryAccepted,
    EntryOutcomeUnknown,
    EntryRejected,
)
from src.trading_kernel.domain.reducer import reduce_event


class DispatchCommandStatus(StrEnum):
    NO_COMMAND = "no_command"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    OUTCOME_UNKNOWN = "outcome_unknown"


class DispatchCommandRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    worker_id: str
    now_ms: int
    lease_until_ms: int
    timeout_seconds: float

    @field_validator("worker_id", mode="before")
    @classmethod
    def _require_worker_id(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("dispatcher worker identity must be non-blank")
        return normalized

    @field_validator("now_ms", "lease_until_ms")
    @classmethod
    def _require_positive_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("dispatcher times must be positive")
        return value

    @field_validator("timeout_seconds")
    @classmethod
    def _require_positive_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("dispatcher timeout must be positive")
        return value

    @model_validator(mode="after")
    def _validate_lease(self) -> "DispatchCommandRequest":
        if self.lease_until_ms <= self.now_ms:
            raise ValueError("command lease must end after claim time")
        return self


class DispatchCommandResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: DispatchCommandStatus
    command_id: str | None = None


async def dispatch_one_command(
    uow_factory: UnitOfWorkFactory,
    venue: VenuePort,
    request: DispatchCommandRequest,
) -> DispatchCommandResult:
    async with uow_factory() as uow:
        expired = await uow.exchange_commands.get_one_expired_claim(
            now_ms=request.now_ms
        )
        if expired is not None:
            result = ExchangeCommandResult(
                status=ExchangeCommandStatus.OUTCOME_UNKNOWN,
                observed_at_ms=request.now_ms,
                reason="stale_claim_after_restart",
            )
            aggregate = await uow.aggregates.get(expired.ticket_identity.ticket_id)
            if aggregate is None:
                raise RuntimeError("expired command has no Ticket aggregate")
            event = _entry_result_event(
                ticket_id=expired.ticket_identity.ticket_id,
                next_sequence=aggregate.last_event_sequence + 1,
                result=result,
            )
            await uow.exchange_commands.record_expired_claim_unknown(
                command_id=expired.command_id,
                result=result,
            )
            await uow.commit_reduction(
                event=event,
                reduction=reduce_event(aggregate, event),
                expected_version=aggregate.version,
            )
            return DispatchCommandResult(
                status=DispatchCommandStatus.OUTCOME_UNKNOWN,
                command_id=expired.command_id,
            )

    async with uow_factory() as uow:
        command = await uow.exchange_commands.claim_one_prepared(
            worker_id=request.worker_id,
            now_ms=request.now_ms,
            lease_until_ms=request.lease_until_ms,
        )
    if command is None:
        return DispatchCommandResult(status=DispatchCommandStatus.NO_COMMAND)

    venue_request = VenueCommandRequest(
        command_id=command.command_id,
        kind=command.kind,
        venue_id=command.ticket_identity.netting_domain.venue_id,
        account_id=command.ticket_identity.netting_domain.account_id,
        exchange_instrument_id=(
            command.ticket_identity.netting_domain.exchange_instrument_id
        ),
        position_side=command.ticket_identity.netting_domain.position_side,
        venue_client_order_id=command.venue_client_order_id,
        payload=command.payload,
        deadline_at_ms=command.deadline_at_ms,
    )
    if command.kind is not ExchangeCommandKind.ENTRY:
        raise RuntimeError("only ENTRY dispatch is implemented")
    try:
        result = await asyncio.wait_for(
            venue.execute(venue_request),
            timeout=request.timeout_seconds,
        )
    except TimeoutError:
        result = ExchangeCommandResult(
            status=ExchangeCommandStatus.OUTCOME_UNKNOWN,
            observed_at_ms=request.now_ms,
            reason="venue_timeout",
        )
    except Exception as exc:
        result = ExchangeCommandResult(
            status=ExchangeCommandStatus.OUTCOME_UNKNOWN,
            observed_at_ms=request.now_ms,
            reason=f"venue_error:{type(exc).__name__}",
        )

    async with uow_factory() as uow:
        aggregate = await uow.aggregates.get(command.ticket_identity.ticket_id)
        if aggregate is None:
            raise RuntimeError("claimed command has no Ticket aggregate")
        event = _entry_result_event(
            ticket_id=command.ticket_identity.ticket_id,
            next_sequence=aggregate.last_event_sequence + 1,
            result=result,
        )
        await uow.exchange_commands.record_result(
            command_id=command.command_id,
            worker_id=request.worker_id,
            result=result,
        )
        await uow.commit_reduction(
            event=event,
            reduction=reduce_event(aggregate, event),
            expected_version=aggregate.version,
        )

    return DispatchCommandResult(
        status=DispatchCommandStatus(result.status.value),
        command_id=command.command_id,
    )


def _entry_result_event(
    *,
    ticket_id: str,
    next_sequence: int,
    result: ExchangeCommandResult,
):
    common = {
        "event_id": f"event:{ticket_id}:{next_sequence}",
        "ticket_id": ticket_id,
        "sequence": next_sequence,
        "occurred_at_ms": result.observed_at_ms,
    }
    if result.status is ExchangeCommandStatus.ACCEPTED:
        return EntryAccepted(
            **common,
            exchange_order_id=str(result.exchange_order_id),
        )
    if result.status is ExchangeCommandStatus.REJECTED:
        return EntryRejected(**common, reason=str(result.reason))
    if result.status is ExchangeCommandStatus.OUTCOME_UNKNOWN:
        return EntryOutcomeUnknown(**common, reason=str(result.reason))
    raise RuntimeError(f"unsupported ENTRY result status: {result.status.value}")
