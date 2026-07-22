"""Advance one exact protected Ticket from current venue and market facts."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import TypedDict

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.domain.aggregate import AggregateStatus, TradeAggregate
from src.trading_kernel.domain.events import (
    ExitRequested,
    RunnerStopRequested,
    TakeProfitFilled,
    TradeEvent,
)
from src.trading_kernel.domain.exit_policy import (
    ExitDecisionKind,
    LifecycleMarketFacts,
    calculate_cost_adjusted_break_even,
    evaluate_exit_policy,
)
from src.trading_kernel.domain.reducer import reduce_event


class LifecycleMaintenanceStatus(StrEnum):
    NO_CHANGE = "no_change"
    BREAK_EVEN_REQUESTED = "break_even_requested"
    RUNNER_MOVE_REQUESTED = "runner_move_requested"
    EXIT_REQUESTED = "exit_requested"


class TicketLifecycleFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    position_quantity: Decimal
    tp1_filled_quantity: Decimal
    tp1_average_fill_price: Decimal | None
    allocated_entry_fee_quote: Decimal
    exit_taker_fee_rate: Decimal
    price_tick: Decimal
    market_facts: LifecycleMarketFacts | None
    observed_at_ms: int

    @field_validator(
        "position_quantity",
        "tp1_filled_quantity",
        "allocated_entry_fee_quote",
    )
    @classmethod
    def _require_nonnegative(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("lifecycle quantities and fees cannot be negative")
        return value

    @field_validator("price_tick")
    @classmethod
    def _require_positive_tick(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("lifecycle price tick must be positive")
        return value

    @model_validator(mode="after")
    def _validate_facts(self) -> "TicketLifecycleFacts":
        if self.observed_at_ms <= 0:
            raise ValueError("lifecycle observation time must be positive")
        if not Decimal("0") <= self.exit_taker_fee_rate < Decimal("1"):
            raise ValueError("exit taker fee rate must be in [0, 1)")
        if self.tp1_filled_quantity > 0:
            if self.tp1_average_fill_price is None or self.tp1_average_fill_price <= 0:
                raise ValueError("TP1 fill requires a positive average price")
        elif self.tp1_average_fill_price is not None:
            raise ValueError("zero TP1 fill forbids an average price")
        return self


class LifecycleMaintenanceRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    facts: TicketLifecycleFacts
    now_ms: int

    @field_validator("ticket_id", mode="before")
    @classmethod
    def _require_ticket_id(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("lifecycle maintenance requires Ticket identity")
        return normalized

    @model_validator(mode="after")
    def _validate_time(self) -> "LifecycleMaintenanceRequest":
        if self.now_ms < self.facts.observed_at_ms:
            raise ValueError("lifecycle maintenance cannot precede its facts")
        return self


class LifecycleMaintenanceResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: LifecycleMaintenanceStatus
    event_id: str | None = None


class _EventFields(TypedDict):
    event_id: str
    ticket_id: str
    sequence: int
    occurred_at_ms: int


async def maintain_ticket_lifecycle(
    uow: KernelUnitOfWork,
    request: LifecycleMaintenanceRequest,
) -> LifecycleMaintenanceResult:
    aggregate = await uow.aggregates.get(request.ticket_id)
    if aggregate is None:
        raise ValueError("lifecycle Ticket does not exist")
    policy = await uow.strategy_registry.get_exit_policy(
        aggregate.ticket.identity.runtime.event_spec_id
    )
    if policy is None:
        raise ValueError("Ticket Event has no active exit policy")
    if policy.position_side != aggregate.identity.netting_domain.position_side:
        raise ValueError("exit-policy side differs from Ticket Netting Domain")

    if aggregate.status is AggregateStatus.POSITION_PROTECTED:
        target = aggregate.tp1_target_qty
        if request.facts.tp1_filled_quantity == 0:
            return LifecycleMaintenanceResult(
                status=LifecycleMaintenanceStatus.NO_CHANGE
            )
        if request.facts.tp1_filled_quantity != target:
            raise ValueError("partial TP1 fill is outside the registered exit policy")
        runner_quantity = aggregate.position_qty - target
        if (
            runner_quantity <= 0
            or request.facts.position_quantity != runner_quantity
            or aggregate.average_fill_price is None
            or request.facts.tp1_average_fill_price is None
        ):
            raise ValueError("TP1 venue facts contradict the frozen Ticket")
        floor = calculate_cost_adjusted_break_even(
            side=policy.position_side,
            entry_average_price=aggregate.average_fill_price,
            runner_quantity=runner_quantity,
            allocated_entry_fee_quote=request.facts.allocated_entry_fee_quote,
            exit_taker_fee_rate=request.facts.exit_taker_fee_rate,
            price_tick=request.facts.price_tick,
            slippage_buffer_ticks=policy.break_even_floor.slippage_buffer_ticks,
        )
        tp1_event = TakeProfitFilled(
            **_event_fields(aggregate, request.now_ms),
            filled_qty=target,
            average_fill_price=request.facts.tp1_average_fill_price,
            runner_floor_price=floor,
        )
        await uow.commit_reduction(
            event=tp1_event,
            reduction=reduce_event(aggregate, tp1_event),
            expected_version=aggregate.version,
        )
        return LifecycleMaintenanceResult(
            status=LifecycleMaintenanceStatus.BREAK_EVEN_REQUESTED,
            event_id=tp1_event.event_id,
        )

    if aggregate.status is AggregateStatus.RUNNER_PROTECTED:
        if request.facts.position_quantity != aggregate.position_qty:
            raise ValueError("runner venue quantity differs from Ticket projection")
        if request.facts.market_facts is None:
            return LifecycleMaintenanceResult(
                status=LifecycleMaintenanceStatus.NO_CHANGE
            )
        if (
            aggregate.active_stop_price is None
            or aggregate.break_even_floor_price is None
        ):
            raise ValueError("runner protection lacks its active and floor prices")
        decision = evaluate_exit_policy(
            policy=policy,
            current_stop=aggregate.active_stop_price,
            break_even_floor=aggregate.break_even_floor_price,
            price_tick=request.facts.price_tick,
            last_runner_watermark_ms=aggregate.runner_stop_watermark_ms or 0,
            market_facts=request.facts.market_facts,
        )
        if decision.kind is ExitDecisionKind.NO_CHANGE:
            return LifecycleMaintenanceResult(
                status=LifecycleMaintenanceStatus.NO_CHANGE
            )
        if decision.kind is ExitDecisionKind.MOVE_STOP:
            if decision.proposed_stop is None:
                raise RuntimeError("runner move decision lacks a stop price")
            event: TradeEvent = RunnerStopRequested(
                **_event_fields(aggregate, request.now_ms),
                stop_price=decision.proposed_stop,
                source_watermark_ms=decision.source_watermark_ms,
            )
            status = LifecycleMaintenanceStatus.RUNNER_MOVE_REQUESTED
        else:
            event = ExitRequested(
                **_event_fields(aggregate, request.now_ms),
                reason=decision.reason,
            )
            status = LifecycleMaintenanceStatus.EXIT_REQUESTED
        await uow.commit_reduction(
            event=event,
            reduction=reduce_event(aggregate, event),
            expected_version=aggregate.version,
        )
        return LifecycleMaintenanceResult(status=status, event_id=event.event_id)

    return LifecycleMaintenanceResult(status=LifecycleMaintenanceStatus.NO_CHANGE)


def _event_fields(
    aggregate: TradeAggregate,
    occurred_at_ms: int,
) -> _EventFields:
    sequence = aggregate.last_event_sequence + 1
    return {
        "event_id": f"event:{aggregate.identity.ticket_id}:{sequence}",
        "ticket_id": aggregate.identity.ticket_id,
        "sequence": sequence,
        "occurred_at_ms": occurred_at_ms,
    }
