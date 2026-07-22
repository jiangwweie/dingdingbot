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
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandResult,
    ExchangeCommandStatus,
    OrderCommandPayload,
)
from src.trading_kernel.domain.events import (
    CancelOrderOutcomeUnknown,
    CancelOrderRejected,
    ControlledFlattenAccepted,
    ControlledFlattenOutcomeUnknown,
    ControlledFlattenRejected,
    EntryAccepted,
    EntryOutcomeUnknown,
    EntryRejected,
    EntryRemainderCancelConfirmed,
    EntryRemainderCancelOutcomeUnknown,
    EntryRemainderCancelRejected,
    ExitAccepted,
    ExitOutcomeUnknown,
    ExitRejected,
    InitialStopConfirmed,
    InitialStopOutcomeUnknown,
    InitialStopRejected,
    OwnedOrphanCancelConfirmed,
    ProtectionCancelConfirmed,
    ProtectionCancelOutcomeUnknown,
    ProtectionCancelRejected,
    ProtectionReplacementConfirmed,
    ProtectionReplacementOutcomeUnknown,
    ProtectionReplacementRejected,
    TakeProfitConfirmed,
    TakeProfitOutcomeUnknown,
    TakeProfitRejected,
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
    ticket_id: str | None = None
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

    @field_validator("ticket_id", mode="before")
    @classmethod
    def _normalize_optional_ticket(cls, value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("dispatcher ticket identity must be non-blank")
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
            now_ms=request.now_ms,
            ticket_id=request.ticket_id,
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
            event = _command_result_event(
                command=expired,
                aggregate=aggregate,
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
            ticket_id=request.ticket_id,
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
        event = _command_result_event(
            command=command,
            aggregate=aggregate,
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


def _command_result_event(
    *,
    command: ExchangeCommand,
    aggregate,
    result: ExchangeCommandResult,
):
    kind = command.kind
    ticket_id = aggregate.identity.ticket_id
    next_sequence = aggregate.last_event_sequence + 1
    common = {
        "event_id": f"event:{ticket_id}:{next_sequence}",
        "ticket_id": ticket_id,
        "sequence": next_sequence,
        "occurred_at_ms": result.observed_at_ms,
    }
    if kind is ExchangeCommandKind.ENTRY and result.status is ExchangeCommandStatus.ACCEPTED:
        return EntryAccepted(
            **common,
            exchange_order_id=str(result.exchange_order_id),
        )
    if kind is ExchangeCommandKind.ENTRY and result.status is ExchangeCommandStatus.REJECTED:
        return EntryRejected(**common, reason=str(result.reason))
    if kind is ExchangeCommandKind.ENTRY and result.status is ExchangeCommandStatus.OUTCOME_UNKNOWN:
        return EntryOutcomeUnknown(**common, reason=str(result.reason))
    if kind is ExchangeCommandKind.EXIT and result.status is ExchangeCommandStatus.OUTCOME_UNKNOWN:
        return ExitOutcomeUnknown(**common, reason=str(result.reason))
    if kind is ExchangeCommandKind.TAKE_PROFIT:
        if not isinstance(command.payload, OrderCommandPayload):
            raise RuntimeError("TP1 command payload is invalid")
        if result.status is ExchangeCommandStatus.ACCEPTED:
            return TakeProfitConfirmed(
                **common,
                exchange_order_id=str(result.exchange_order_id),
                target_qty=command.payload.quantity,
            )
        if result.status is ExchangeCommandStatus.REJECTED:
            return TakeProfitRejected(**common, reason=str(result.reason))
        if result.status is ExchangeCommandStatus.OUTCOME_UNKNOWN:
            return TakeProfitOutcomeUnknown(**common, reason=str(result.reason))
    if kind is ExchangeCommandKind.REPLACE_PROTECTION:
        payload = command.payload
        if not isinstance(payload, OrderCommandPayload):
            raise RuntimeError("protection replacement payload is invalid")
        if payload.stop_price is None:
            raise RuntimeError("protection replacement stop price is missing")
        if payload.replaces_exchange_order_id is None:
            raise RuntimeError("protection replacement prior order is missing")
        if payload.source_watermark_ms is None:
            raise RuntimeError("protection replacement watermark is missing")
        if result.status is ExchangeCommandStatus.ACCEPTED:
            return ProtectionReplacementConfirmed(
                **common,
                exchange_order_id=str(result.exchange_order_id),
                protected_qty=payload.quantity,
                stop_price=payload.stop_price,
                replaces_exchange_order_id=payload.replaces_exchange_order_id,
                source_watermark_ms=payload.source_watermark_ms,
            )
        if result.status is ExchangeCommandStatus.REJECTED:
            return ProtectionReplacementRejected(
                **common,
                reason=str(result.reason),
            )
        if result.status is ExchangeCommandStatus.OUTCOME_UNKNOWN:
            return ProtectionReplacementOutcomeUnknown(
                **common,
                reason=str(result.reason),
            )
    if kind is ExchangeCommandKind.INITIAL_STOP and result.status is ExchangeCommandStatus.REJECTED:
        return InitialStopRejected(**common, reason=str(result.reason))
    if kind is ExchangeCommandKind.INITIAL_STOP and result.status is ExchangeCommandStatus.OUTCOME_UNKNOWN:
        return InitialStopOutcomeUnknown(**common, reason=str(result.reason))
    if kind is ExchangeCommandKind.EXIT and result.status is ExchangeCommandStatus.REJECTED:
        return ExitRejected(**common, reason=str(result.reason))
    if kind is ExchangeCommandKind.CANCEL_ORDER:
        if not isinstance(command.payload, CancelCommandPayload):
            raise RuntimeError("cancel command payload is invalid")
        if aggregate.status is AggregateStatus.PARTIAL_FILL_INCIDENT:
            if result.status is ExchangeCommandStatus.ACCEPTED:
                return EntryRemainderCancelConfirmed(
                    **common,
                    exchange_order_id=command.payload.exchange_order_id,
                )
            if result.status is ExchangeCommandStatus.REJECTED:
                return EntryRemainderCancelRejected(
                    **common,
                    exchange_order_id=command.payload.exchange_order_id,
                    reason=str(result.reason),
                )
            if result.status is ExchangeCommandStatus.OUTCOME_UNKNOWN:
                return EntryRemainderCancelOutcomeUnknown(
                    **common,
                    exchange_order_id=command.payload.exchange_order_id,
                    reason=str(result.reason),
                )
        if (
            aggregate.status is AggregateStatus.RUNNER_OLD_STOP_CANCEL_PENDING
        ):
            if result.status is ExchangeCommandStatus.ACCEPTED:
                return ProtectionCancelConfirmed(
                    **common,
                    exchange_order_id=command.payload.exchange_order_id,
                )
            if result.status is ExchangeCommandStatus.REJECTED:
                return ProtectionCancelRejected(
                    **common,
                    exchange_order_id=command.payload.exchange_order_id,
                    reason=str(result.reason),
                )
            if result.status is ExchangeCommandStatus.OUTCOME_UNKNOWN:
                return ProtectionCancelOutcomeUnknown(
                    **common,
                    exchange_order_id=command.payload.exchange_order_id,
                    reason=str(result.reason),
                )
        if result.status is ExchangeCommandStatus.REJECTED:
            return CancelOrderRejected(
                **common,
                exchange_order_id=command.payload.exchange_order_id,
                reason=str(result.reason),
            )
        if result.status is ExchangeCommandStatus.OUTCOME_UNKNOWN:
            return CancelOrderOutcomeUnknown(
                **common,
                exchange_order_id=command.payload.exchange_order_id,
                reason=str(result.reason),
            )
    if kind is ExchangeCommandKind.CONTROLLED_FLATTEN:
        if result.status is ExchangeCommandStatus.ACCEPTED:
            return ControlledFlattenAccepted(
                **common,
                exchange_order_id=str(result.exchange_order_id),
            )
        if result.status is ExchangeCommandStatus.REJECTED:
            return ControlledFlattenRejected(**common, reason=str(result.reason))
        if result.status is ExchangeCommandStatus.OUTCOME_UNKNOWN:
            return ControlledFlattenOutcomeUnknown(
                **common,
                reason=str(result.reason),
            )
    if result.status is not ExchangeCommandStatus.ACCEPTED:
        raise RuntimeError(
            f"unsupported {kind.value} result status: {result.status.value}"
        )
    if kind is ExchangeCommandKind.INITIAL_STOP:
        return InitialStopConfirmed(
            **common,
            exchange_order_id=str(result.exchange_order_id),
            protected_qty=aggregate.position_qty,
        )
    if kind is ExchangeCommandKind.EXIT:
        return ExitAccepted(
            **common,
            exchange_order_id=str(result.exchange_order_id),
        )
    if kind is ExchangeCommandKind.CANCEL_ORDER:
        if not isinstance(command.payload, CancelCommandPayload):
            raise RuntimeError("cancel command payload is invalid")
        cancel_payload = command.payload
        known_order_ids = {
            aggregate.initial_stop_exchange_order_id,
            aggregate.active_stop_exchange_order_id,
            aggregate.tp1_exchange_order_id,
            aggregate.pending_replaced_stop_exchange_order_id,
        }
        if cancel_payload.exchange_order_id not in known_order_ids:
            return OwnedOrphanCancelConfirmed(
                **common,
                exchange_order_id=cancel_payload.exchange_order_id,
            )
        return ProtectionCancelConfirmed(
            **common,
            exchange_order_id=str(result.exchange_order_id),
        )
    raise RuntimeError(f"unsupported command kind: {kind.value}")
