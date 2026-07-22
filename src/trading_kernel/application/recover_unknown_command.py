"""Resolve one unknown exchange command through timeout-bounded venue truth."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import TypedDict

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.application.ports import (
    RuntimeIncidentRecord,
    UnitOfWorkFactory,
    VenueTruthPort,
    VenueTruthRequest,
)
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandStatus,
    OrderCommandPayload,
)
from src.trading_kernel.domain.aggregate import AggregateStatus, TradeAggregate
from src.trading_kernel.domain.events import (
    CancelOrderAbsenceConfirmed,
    ControlledFlattenAbsenceConfirmed,
    ControlledFlattenAccepted,
    EntryAbsenceConfirmed,
    EntryAccepted,
    EntryRemainderCancelConfirmed,
    ExitAbsenceConfirmed,
    ExitAccepted,
    InitialStopAbsenceConfirmed,
    InitialStopConfirmed,
    ProtectionCancelAbsenceConfirmed,
    ProtectionReplacementAbsenceConfirmed,
    ProtectionReplacementConfirmed,
    TakeProfitAbsenceConfirmed,
    TakeProfitConfirmed,
    TradeEvent,
)
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.domain.venue_truth import (
    UnknownRecoveryDecision,
    UnknownRecoveryStatus,
    VenueLookupStatus,
    VenueTruthSnapshot,
    decide_unknown_recovery,
)


class RecoverUnknownCommandRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: str
    now_ms: int
    visibility_deadline_ms: int
    timeout_seconds: float

    @field_validator("command_id", mode="before")
    @classmethod
    def _require_command_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("unknown recovery command identity must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_window(self) -> "RecoverUnknownCommandRequest":
        if (
            self.now_ms <= 0
            or self.visibility_deadline_ms <= 0
            or self.timeout_seconds <= 0
        ):
            raise ValueError("unknown recovery time and timeout must be positive")
        return self


async def recover_unknown_command(
    uow_factory: UnitOfWorkFactory,
    venue_truth: VenueTruthPort,
    request: RecoverUnknownCommandRequest,
) -> UnknownRecoveryDecision:
    async with uow_factory() as uow:
        command = await uow.exchange_commands.get(request.command_id)
        if command is None:
            raise ValueError("unknown recovery command does not exist")
        if command.status is not ExchangeCommandStatus.OUTCOME_UNKNOWN:
            raise ValueError("command is not in unknown-outcome state")

    truth_request = VenueTruthRequest(
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
        observed_at_ms=request.now_ms,
    )
    try:
        truth = await asyncio.wait_for(
            venue_truth.lookup_command_truth(truth_request),
            timeout=request.timeout_seconds,
        )
    except TimeoutError:
        truth = VenueTruthSnapshot(
            lookup_status=VenueLookupStatus.LOOKUP_FAILED,
            position_quantity=Decimal("0"),
            matching_fill_quantity=Decimal("0"),
            regular_open_client_order_ids=(),
            conditional_open_client_order_ids=(),
            observed_at_ms=request.now_ms,
            reason="venue_truth_timeout",
        )
    except Exception as exc:
        truth = VenueTruthSnapshot(
            lookup_status=VenueLookupStatus.LOOKUP_FAILED,
            position_quantity=Decimal("0"),
            matching_fill_quantity=Decimal("0"),
            regular_open_client_order_ids=(),
            conditional_open_client_order_ids=(),
            observed_at_ms=request.now_ms,
            reason=f"venue_truth_error:{type(exc).__name__}",
        )
    decision = decide_unknown_recovery(
        command,
        truth,
        visibility_deadline_ms=request.visibility_deadline_ms,
    )
    if decision.status in {
        UnknownRecoveryStatus.PENDING_VISIBILITY,
        UnknownRecoveryStatus.LOOKUP_FAILED,
    }:
        return decision

    async with uow_factory() as uow:
        current_command = await uow.exchange_commands.get(request.command_id)
        if (
            current_command is None
            or current_command.status is not ExchangeCommandStatus.OUTCOME_UNKNOWN
        ):
            raise RuntimeError("unknown command changed during venue lookup")
        aggregate = await uow.aggregates.get(
            current_command.ticket_identity.ticket_id
        )
        if aggregate is None:
            raise RuntimeError("unknown command has no Ticket aggregate")

        if decision.status is UnknownRecoveryStatus.IDENTITY_CONTRADICTION:
            await uow.incidents.add(
                RuntimeIncidentRecord(
                    incident_id=(
                        f"incident:{aggregate.identity.ticket_id}:"
                        f"venue-identity:{decision.observed_at_ms}"
                    ),
                    ticket_id=aggregate.identity.ticket_id,
                    incident_kind="venue_identity_contradiction",
                    status="open",
                    first_blocker="hard_safety_stop",
                    details={
                        "command_id": current_command.command_id,
                        "reason": str(decision.reason),
                    },
                    opened_at_ms=decision.observed_at_ms,
                )
            )
            return decision

        event = _recovery_event(
            aggregate=aggregate,
            command=current_command,
            decision=decision,
        )
        if decision.status is UnknownRecoveryStatus.RECONCILED_SUBMITTED:
            await uow.exchange_commands.reconcile_unknown_submitted(
                command_id=current_command.command_id,
                exchange_order_id=str(decision.exchange_order_id),
                observed_at_ms=decision.observed_at_ms,
            )
        elif current_command.kind is not ExchangeCommandKind.CANCEL_ORDER:
            await uow.exchange_commands.reconcile_unknown_absent(
                command_id=current_command.command_id,
                observed_at_ms=decision.observed_at_ms,
                reason=str(decision.reason),
            )
        await uow.commit_reduction(
            event=event,
            reduction=reduce_event(aggregate, event),
            expected_version=aggregate.version,
        )
    return decision


def _recovery_event(
    *,
    aggregate: TradeAggregate,
    command: ExchangeCommand,
    decision: UnknownRecoveryDecision,
) -> TradeEvent:
    sequence = aggregate.last_event_sequence + 1
    common: _EventFields = {
        "event_id": f"event:{aggregate.identity.ticket_id}:{sequence}",
        "ticket_id": aggregate.identity.ticket_id,
        "sequence": sequence,
        "occurred_at_ms": decision.observed_at_ms,
    }
    if decision.status is UnknownRecoveryStatus.RECONCILED_SUBMITTED:
        exchange_order_id = str(decision.exchange_order_id or "").strip()
        if command.kind is ExchangeCommandKind.ENTRY:
            return EntryAccepted(
                **common,
                exchange_order_id=exchange_order_id,
            )
        if command.kind is ExchangeCommandKind.INITIAL_STOP:
            return InitialStopConfirmed(
                **common,
                exchange_order_id=exchange_order_id,
                protected_qty=aggregate.position_qty,
            )
        if command.kind is ExchangeCommandKind.TAKE_PROFIT:
            payload = command.payload
            if not isinstance(payload, OrderCommandPayload):
                raise RuntimeError("TP1 recovery payload is invalid")
            return TakeProfitConfirmed(
                **common,
                exchange_order_id=exchange_order_id,
                target_qty=payload.quantity,
            )
        if command.kind is ExchangeCommandKind.REPLACE_PROTECTION:
            payload = command.payload
            if not isinstance(payload, OrderCommandPayload) or payload.stop_price is None:
                raise RuntimeError("replacement recovery payload is invalid")
            if payload.replaces_exchange_order_id is None:
                raise RuntimeError("replacement recovery prior order is missing")
            if payload.source_watermark_ms is None:
                raise RuntimeError("replacement recovery watermark is missing")
            return ProtectionReplacementConfirmed(
                **common,
                exchange_order_id=exchange_order_id,
                protected_qty=payload.quantity,
                stop_price=payload.stop_price,
                replaces_exchange_order_id=payload.replaces_exchange_order_id,
                source_watermark_ms=payload.source_watermark_ms,
            )
        if command.kind is ExchangeCommandKind.EXIT:
            return ExitAccepted(
                **common,
                exchange_order_id=exchange_order_id,
            )
        if command.kind is ExchangeCommandKind.CONTROLLED_FLATTEN:
            return ControlledFlattenAccepted(
                **common,
                exchange_order_id=exchange_order_id,
            )
        raise RuntimeError(
            f"submitted recovery is not mapped for {command.kind.value}"
        )

    if decision.status is not UnknownRecoveryStatus.RECONCILED_ABSENT:
        raise RuntimeError("non-terminal recovery decision cannot create an event")
    if command.kind is ExchangeCommandKind.ENTRY:
        return EntryAbsenceConfirmed(
            **common,
            command_id=command.command_id,
        )
    if command.kind is ExchangeCommandKind.INITIAL_STOP:
        return InitialStopAbsenceConfirmed(
            **common,
            command_id=command.command_id,
        )
    if command.kind is ExchangeCommandKind.TAKE_PROFIT:
        return TakeProfitAbsenceConfirmed(
            **common,
            command_id=command.command_id,
        )
    if command.kind is ExchangeCommandKind.REPLACE_PROTECTION:
        return ProtectionReplacementAbsenceConfirmed(
            **common,
            command_id=command.command_id,
        )
    if command.kind is ExchangeCommandKind.EXIT:
        return ExitAbsenceConfirmed(
            **common,
            command_id=command.command_id,
        )
    if command.kind is ExchangeCommandKind.CONTROLLED_FLATTEN:
        return ControlledFlattenAbsenceConfirmed(
            **common,
            command_id=command.command_id,
        )
    if command.kind is ExchangeCommandKind.CANCEL_ORDER:
        if not isinstance(command.payload, CancelCommandPayload):
            raise RuntimeError("cancel recovery payload is invalid")
        target_order_id = command.payload.exchange_order_id
        if aggregate.status is AggregateStatus.PARTIAL_FILL_CANCEL_OUTCOME_UNKNOWN:
            return EntryRemainderCancelConfirmed(
                **common,
                exchange_order_id=target_order_id,
            )
        if aggregate.status is AggregateStatus.CANCEL_OUTCOME_UNKNOWN:
            return CancelOrderAbsenceConfirmed(
                **common,
                exchange_order_id=target_order_id,
            )
        if (
            aggregate.status
            is AggregateStatus.RUNNER_OLD_STOP_CANCEL_OUTCOME_UNKNOWN
        ):
            return ProtectionCancelAbsenceConfirmed(
                **common,
                exchange_order_id=target_order_id,
            )
        raise RuntimeError("cancel recovery aggregate state is not supported")
    raise RuntimeError(f"absence recovery is not mapped for {command.kind.value}")


class _EventFields(TypedDict):
    event_id: str
    ticket_id: str
    sequence: int
    occurred_at_ms: int
