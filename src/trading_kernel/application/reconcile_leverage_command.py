"""Resolve one unknown durable leverage mutation from exact venue truth."""

from __future__ import annotations

import asyncio
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator

from src.trading_kernel.application.ports import (
    LeverageTruthRequest,
    UnitOfWorkFactory,
    VenueTruthPort,
)
from src.trading_kernel.domain.commands import (
    ExchangeCommandKind,
    ExchangeCommandStatus,
    SetLeverageCommandPayload,
    SetLeverageCommandResult,
)
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.events import LeverageConfirmed, LeverageRejected
from src.trading_kernel.domain.reducer import reduce_event


class ReconcileLeverageStatus(StrEnum):
    CONFIRMED = "confirmed"
    REJECTED_MISMATCH = "rejected_mismatch"
    BLOCKED_CONTRADICTION = "blocked_contradiction"
    TRUTH_UNAVAILABLE = "truth_unavailable"


class ReconcileLeverageCommandRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: str
    now_ms: int
    timeout_seconds: float

    @field_validator("command_id", mode="before")
    @classmethod
    def _require_command_id(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("leverage reconciliation command identity must be non-blank")
        return normalized

    @field_validator("now_ms")
    @classmethod
    def _require_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("leverage reconciliation time must be positive")
        return value

    @field_validator("timeout_seconds")
    @classmethod
    def _require_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("leverage reconciliation timeout must be positive")
        return value


class ReconcileLeverageCommandResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ReconcileLeverageStatus
    command_id: str
    reason: str | None = None


async def reconcile_leverage_command(
    uow_factory: UnitOfWorkFactory,
    truth_port: VenueTruthPort,
    request: ReconcileLeverageCommandRequest,
) -> ReconcileLeverageCommandResult:
    """Never resend: only exact readonly truth may advance or reject mutation."""

    async with uow_factory() as uow:
        command = await uow.exchange_commands.get(request.command_id)
        if command is None:
            raise ValueError("leverage command does not exist")
        if command.kind is not ExchangeCommandKind.SET_LEVERAGE:
            raise ValueError("command is not SET_LEVERAGE")
        if command.status is not ExchangeCommandStatus.OUTCOME_UNKNOWN:
            raise ValueError("leverage command is not in unknown-outcome state")
        if not isinstance(command.payload, SetLeverageCommandPayload):
            raise RuntimeError("SET_LEVERAGE command payload is invalid")

    truth_request = LeverageTruthRequest(
        command_id=command.command_id,
        venue_id=command.ticket_identity.netting_domain.venue_id,
        account_id=command.ticket_identity.netting_domain.account_id,
        exchange_instrument_id=(
            command.ticket_identity.netting_domain.exchange_instrument_id
        ),
        desired_leverage=command.payload.desired_leverage,
        observed_at_ms=request.now_ms,
    )
    try:
        truth = await asyncio.wait_for(
            truth_port.read_configured_leverage(truth_request),
            timeout=request.timeout_seconds,
        )
    except Exception as exc:
        return ReconcileLeverageCommandResult(
            status=ReconcileLeverageStatus.TRUTH_UNAVAILABLE,
            command_id=command.command_id,
            reason=f"leverage_truth:{type(exc).__name__}",
        )

    has_external_exposure = (
        truth.long_position_quantity != 0
        or truth.short_position_quantity != 0
        or bool(truth.regular_open_order_ids)
        or bool(truth.conditional_open_order_ids)
    )
    if has_external_exposure:
        return ReconcileLeverageCommandResult(
            status=ReconcileLeverageStatus.BLOCKED_CONTRADICTION,
            command_id=command.command_id,
            reason="leverage_truth_contains_position_or_order",
        )

    async with uow_factory() as uow:
        current_command = await uow.exchange_commands.get(request.command_id)
        if (
            current_command is None
            or current_command.kind is not ExchangeCommandKind.SET_LEVERAGE
            or current_command.status is not ExchangeCommandStatus.OUTCOME_UNKNOWN
            or not isinstance(current_command.payload, SetLeverageCommandPayload)
        ):
            raise RuntimeError("leverage command changed during truth lookup")
        aggregate = await uow.aggregates.get(
            current_command.ticket_identity.ticket_id
        )
        if aggregate is None:
            raise RuntimeError("leverage command has no Ticket aggregate")
        common = {
            "event_id": (
                f"event:{aggregate.identity.ticket_id}:"
                f"{aggregate.last_event_sequence + 1}"
            ),
            "ticket_id": aggregate.identity.ticket_id,
            "sequence": aggregate.last_event_sequence + 1,
            "occurred_at_ms": truth.observed_at_ms,
        }
        if truth.exchange_configured_leverage == current_command.payload.desired_leverage:
            result = SetLeverageCommandResult(
                exchange_configured_leverage=truth.exchange_configured_leverage,
                leverage_verified_at_ms=truth.observed_at_ms,
                leverage_verification_digest=canonical_digest(
                    {
                        "command_id": current_command.command_id,
                        "desired_leverage": current_command.payload.desired_leverage,
                        "exchange_configured_leverage": truth.exchange_configured_leverage,
                        "observed_at_ms": truth.observed_at_ms,
                    }
                ),
            )
            event = LeverageConfirmed(
                **common,
                exchange_configured_leverage=result.exchange_configured_leverage,
                leverage_verified_at_ms=result.leverage_verified_at_ms,
                leverage_verification_digest=result.leverage_verification_digest,
            )
            await uow.exchange_commands.reconcile_unknown_leverage_confirmed(
                command_id=current_command.command_id,
                result=result,
            )
            await uow.commit_reduction(
                event=event,
                reduction=reduce_event(aggregate, event),
                expected_version=aggregate.version,
            )
            return ReconcileLeverageCommandResult(
                status=ReconcileLeverageStatus.CONFIRMED,
                command_id=current_command.command_id,
            )

        event = LeverageRejected(
            **common,
            reason="configured_leverage_mismatch",
        )
        await uow.exchange_commands.reconcile_unknown_absent(
            command_id=current_command.command_id,
            observed_at_ms=truth.observed_at_ms,
            reason="configured_leverage_mismatch",
        )
        await uow.commit_reduction(
            event=event,
            reduction=reduce_event(aggregate, event),
            expected_version=aggregate.version,
        )
        return ReconcileLeverageCommandResult(
            status=ReconcileLeverageStatus.REJECTED_MISMATCH,
            command_id=current_command.command_id,
        )
