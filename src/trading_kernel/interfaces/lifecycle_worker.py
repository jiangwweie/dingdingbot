"""Own protection, TP1, runner, EXIT, and cleanup progression."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.application.dispatch_exchange_command import (
    DispatchCommandRequest,
    DispatchCommandStatus,
    dispatch_one_command,
)
from src.trading_kernel.application.maintain_ticket_lifecycle import (
    LifecycleMaintenanceRequest,
    LifecycleMaintenanceStatus,
    maintain_ticket_lifecycle,
)
from src.trading_kernel.application.ports import UnitOfWorkFactory, VenuePort
from src.trading_kernel.application.runtime_fence import runtime_writer_is_certified
from src.trading_kernel.application.runtime_facts import (
    LifecycleFactsRequest,
    LifecycleFactsSource,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import ExchangeCommandKind
from src.trading_kernel.domain.events import EntryFilled


_LIFECYCLE_COMMAND_KINDS = (
    ExchangeCommandKind.INITIAL_STOP,
    ExchangeCommandKind.TAKE_PROFIT,
    ExchangeCommandKind.REPLACE_PROTECTION,
    ExchangeCommandKind.EXIT,
    ExchangeCommandKind.CANCEL_ORDER,
    ExchangeCommandKind.CONTROLLED_FLATTEN,
)


class LifecycleWorkerStatus(StrEnum):
    NO_WORK = "no_work"
    RUNTIME_FENCED = "runtime_fenced"
    DISPATCHED = "dispatched"
    SUPERSEDED = "superseded"
    FACTS_UNAVAILABLE = "facts_unavailable"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    NO_CHANGE = "no_change"


class LifecycleWorkerRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    worker_id: str
    runtime_commit: str
    schema_revision: str
    now_ms: int
    lease_until_ms: int
    timeout_seconds: float
    idle_poll_interval_ms: int

    @field_validator("worker_id", "runtime_commit", "schema_revision", mode="before")
    @classmethod
    def _require_worker_id(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("lifecycle worker identities must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_window(self) -> "LifecycleWorkerRequest":
        if self.now_ms <= 0 or self.lease_until_ms <= self.now_ms:
            raise ValueError("lifecycle worker lease must end after its tick")
        if self.timeout_seconds <= 0 or self.idle_poll_interval_ms <= 0:
            raise ValueError("lifecycle worker timeout and cadence must be positive")
        return self


class LifecycleWorkerResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: LifecycleWorkerStatus
    ticket_id: str | None = None
    command_id: str | None = None
    dispatch_status: DispatchCommandStatus | None = None
    maintenance_status: LifecycleMaintenanceStatus | None = None
    detail: str | None = None


async def run_lifecycle_worker_once(
    uow_factory: UnitOfWorkFactory,
    venue: VenuePort,
    facts_source: LifecycleFactsSource,
    request: LifecycleWorkerRequest,
) -> LifecycleWorkerResult:
    if not await runtime_writer_is_certified(
        uow_factory,
        worker_id=request.worker_id,
        runtime_commit=request.runtime_commit,
        schema_revision=request.schema_revision,
        observed_at_ms=request.now_ms,
    ):
        return LifecycleWorkerResult(
            status=LifecycleWorkerStatus.RUNTIME_FENCED,
            detail="runtime_identity_mismatch",
        )

    dispatched = await _dispatch_lifecycle(
        uow_factory,
        venue,
        request,
        ticket_id=None,
    )
    if dispatched.status is not DispatchCommandStatus.NO_COMMAND:
        return LifecycleWorkerResult(
            status=(
                LifecycleWorkerStatus.SUPERSEDED
                if dispatched.status is DispatchCommandStatus.SUPERSEDED
                else LifecycleWorkerStatus.DISPATCHED
            ),
            command_id=dispatched.command_id,
            dispatch_status=dispatched.status,
        )

    async with uow_factory() as uow:
        aggregate = await uow.aggregates.get_next_for_statuses(
            (
                AggregateStatus.POSITION_PROTECTED,
                AggregateStatus.RUNNER_PROTECTED,
            ),
            work_kind="lifecycle",
            now_ms=request.now_ms,
        )
        if aggregate is None:
            return LifecycleWorkerResult(status=LifecycleWorkerStatus.NO_WORK)
        policy = await uow.strategy_registry.get_exit_policy(
            aggregate.identity.runtime.event_spec_id
        )
        rules = await uow.signals.get_instrument_rules(
            aggregate.identity.netting_domain.venue_id,
            aggregate.identity.netting_domain.exchange_instrument_id
        )
        commands = await uow.exchange_commands.list_for_ticket(
            aggregate.identity.ticket_id
        )
        events = await uow.events.list_for_ticket(aggregate.identity.ticket_id)
    if policy is None or rules is None:
        async with uow_factory() as uow:
            await uow.aggregates.schedule_next_check(
                aggregate.identity.ticket_id,
                work_kind="lifecycle",
                due_at_ms=request.now_ms + request.idle_poll_interval_ms,
            )
        return LifecycleWorkerResult(
            status=LifecycleWorkerStatus.FACTS_UNAVAILABLE,
            ticket_id=aggregate.identity.ticket_id,
            detail="exit_policy_or_instrument_rules_missing",
        )
    entry_command = next(
        (
            command
            for command in commands
            if command.kind is ExchangeCommandKind.ENTRY
        ),
        None,
    )
    tp1_command = next(
        (
            command
            for command in reversed(commands)
            if command.kind is ExchangeCommandKind.TAKE_PROFIT
        ),
        None,
    )
    entry_fill = next(
        (event for event in events if isinstance(event, EntryFilled)),
        None,
    )
    if entry_command is None or entry_fill is None:
        async with uow_factory() as uow:
            await uow.aggregates.schedule_next_check(
                aggregate.identity.ticket_id,
                work_kind="lifecycle",
                due_at_ms=request.now_ms + request.idle_poll_interval_ms,
            )
        return LifecycleWorkerResult(
            status=LifecycleWorkerStatus.FACTS_UNAVAILABLE,
            ticket_id=aggregate.identity.ticket_id,
            detail="entry_command_or_fill_missing",
        )
    facts_request = LifecycleFactsRequest(
        ticket_id=aggregate.identity.ticket_id,
        netting_domain=aggregate.identity.netting_domain,
        event_spec_id=aggregate.identity.runtime.event_spec_id,
        timeframe=policy.runner.timeframe,
        entry_quantity=aggregate.ticket.quantity,
        expected_position_quantity=aggregate.position_qty,
        entry_venue_client_order_id=entry_command.venue_client_order_id,
        tp1_venue_client_order_id=(
            None if tp1_command is None else tp1_command.venue_client_order_id
        ),
        entered_at_ms=entry_fill.occurred_at_ms,
        price_tick=rules.price_tick,
        structure_window_bars=policy.runner.structure_window_bars,
        atr_period=policy.runner.atr_period,
        runner_market_required=(
            aggregate.status is AggregateStatus.RUNNER_PROTECTED
        ),
        observed_at_ms=request.now_ms,
    )
    try:
        facts = await asyncio.wait_for(
            facts_source.read_lifecycle_facts(facts_request),
            timeout=request.timeout_seconds,
        )
    except Exception as exc:
        async with uow_factory() as uow:
            await uow.aggregates.schedule_next_check(
                aggregate.identity.ticket_id,
                work_kind="lifecycle",
                due_at_ms=request.now_ms + request.idle_poll_interval_ms,
            )
        return LifecycleWorkerResult(
            status=LifecycleWorkerStatus.FACTS_UNAVAILABLE,
            ticket_id=aggregate.identity.ticket_id,
            detail=f"lifecycle_facts:{type(exc).__name__}",
        )

    expected_position_quantity: Decimal | None = aggregate.position_qty
    if aggregate.status is AggregateStatus.POSITION_PROTECTED:
        if facts.tp1_filled_quantity == aggregate.tp1_target_qty:
            expected_position_quantity = (
                aggregate.position_qty - aggregate.tp1_target_qty
            )
        elif facts.tp1_filled_quantity != 0:
            expected_position_quantity = None
    if facts.position_quantity != expected_position_quantity:
        async with uow_factory() as uow:
            await uow.aggregates.schedule_next_check(
                aggregate.identity.ticket_id,
                work_kind="reconciliation",
                due_at_ms=request.now_ms,
            )
            await uow.aggregates.schedule_next_check(
                aggregate.identity.ticket_id,
                work_kind="lifecycle",
                due_at_ms=request.now_ms + request.idle_poll_interval_ms,
            )
        return LifecycleWorkerResult(
            status=LifecycleWorkerStatus.RECONCILIATION_REQUIRED,
            ticket_id=aggregate.identity.ticket_id,
            detail="venue_position_differs_from_ticket_projection",
        )

    async with uow_factory() as uow:
        maintenance = await maintain_ticket_lifecycle(
            uow,
            LifecycleMaintenanceRequest(
                ticket_id=aggregate.identity.ticket_id,
                facts=facts,
                now_ms=request.now_ms,
            ),
        )
    if maintenance.status is LifecycleMaintenanceStatus.NO_CHANGE:
        async with uow_factory() as uow:
            await uow.aggregates.schedule_next_check(
                aggregate.identity.ticket_id,
                work_kind="lifecycle",
                due_at_ms=request.now_ms + request.idle_poll_interval_ms,
            )
        return LifecycleWorkerResult(
            status=LifecycleWorkerStatus.NO_CHANGE,
            ticket_id=aggregate.identity.ticket_id,
            maintenance_status=maintenance.status,
        )

    dispatched = await _dispatch_lifecycle(
        uow_factory,
        venue,
        request,
        ticket_id=aggregate.identity.ticket_id,
    )
    return LifecycleWorkerResult(
        status=(
            LifecycleWorkerStatus.SUPERSEDED
            if dispatched.status is DispatchCommandStatus.SUPERSEDED
            else LifecycleWorkerStatus.DISPATCHED
        ),
        ticket_id=aggregate.identity.ticket_id,
        command_id=dispatched.command_id,
        dispatch_status=dispatched.status,
        maintenance_status=maintenance.status,
    )


async def _dispatch_lifecycle(
    uow_factory: UnitOfWorkFactory,
    venue: VenuePort,
    request: LifecycleWorkerRequest,
    *,
    ticket_id: str | None,
):
    return await dispatch_one_command(
        uow_factory,
        venue,
        DispatchCommandRequest(
            worker_id=request.worker_id,
            ticket_id=ticket_id,
            command_kinds=_LIFECYCLE_COMMAND_KINDS,
            now_ms=request.now_ms,
            lease_until_ms=request.lease_until_ms,
            timeout_seconds=request.timeout_seconds,
        ),
    )
