"""Advance one bounded Strategy Entry Vacuum drain step from durable facts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import TypedDict

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.domain.aggregate import AggregateStatus, TradeAggregate
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandStatus,
)
from src.trading_kernel.domain.events import (
    EntryFilled,
    EntryVacuumAbsenceConfirmed,
    EntryVacuumCancelRequested,
    EntryVacuumOrderAbsenceConfirmed,
    EntryVacuumSuperseded,
    VacuumPartialFlattenRequired,
    VacuumPartialRetained,
)
from src.trading_kernel.domain.exit_policy import split_tp1_quantity
from src.trading_kernel.domain.instrument_selection import INTERVAL_MS
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.post_fill_risk import (
    PostFillDisposition,
    PostFillRiskRequest,
    assess_post_fill_risk,
)
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.domain.selection_authority import (
    AuthorityOutcome,
    ContinuitySourceKind,
    SelectionMode,
    SelectionSessionAuthority,
)
from src.trading_kernel.domain.strategy_entry_vacuum import (
    StrategyEntryVacuumState,
)


class VacuumDrainStatus(StrEnum):
    NO_VACUUM = "NO_VACUUM"
    DRAIN_STARTED = "DRAIN_STARTED"
    PREPARED_ENTRY_SUPERSEDED = "PREPARED_ENTRY_SUPERSEDED"
    POSITION_FACTS_REQUIRED = "POSITION_FACTS_REQUIRED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    ORDER_ABSENCE_RECORDED = "ORDER_ABSENCE_RECORDED"
    ZERO_FILL_CLOSED = "ZERO_FILL_CLOSED"
    FULL_FILL_PROTECTION_REQUESTED = "FULL_FILL_PROTECTION_REQUESTED"
    PARTIAL_RETAINED_PROTECTION_REQUESTED = (
        "PARTIAL_RETAINED_PROTECTION_REQUESTED"
    )
    PARTIAL_FLATTEN_REQUESTED = "PARTIAL_FLATTEN_REQUESTED"
    WAITING_COMMAND = "WAITING_COMMAND"
    WAITING_UNKNOWN_OUTCOME = "WAITING_UNKNOWN_OUTCOME"
    WAITING_LIFECYCLE = "WAITING_LIFECYCLE"
    ENTRY_DRAINED = "ENTRY_DRAINED"
    VALID_EMPTY_COMMITTED = "VALID_EMPTY_COMMITTED"
    OWNER_PAUSED = "OWNER_PAUSED"
    BLOCKED = "BLOCKED"


class DrainStrategyEntryVacuumRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_group_id: str
    selection_spec_id: str
    now_ms: int
    ticket_id: str | None = None
    position_snapshot: PositionSnapshot | None = None

    @field_validator("strategy_group_id", "selection_spec_id", mode="before")
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Vacuum drain identity must be non-blank")
        return normalized

    @field_validator("ticket_id", mode="before")
    @classmethod
    def _normalize_ticket_id(cls, value: object) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @model_validator(mode="after")
    def _validate_request(self) -> DrainStrategyEntryVacuumRequest:
        if self.now_ms <= 0:
            raise ValueError("Vacuum drain time must be positive")
        if self.position_snapshot is not None and self.ticket_id is None:
            raise ValueError("position facts require exact Ticket identity")
        return self


class DrainStrategyEntryVacuumResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: VacuumDrainStatus
    entry_vacuum_id: str | None = None
    ticket_id: str | None = None
    event_id: str | None = None
    selection_authority_id: str | None = None
    reason_code: str | None = None


class VacuumTicketDrainFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    aggregate: TradeAggregate
    entry_vacuum_id: str
    now_ms: int
    position_snapshot: PositionSnapshot | None = None
    quantity_step: Decimal | None = None
    tp1_quantity_fraction: Decimal | None = None

    @field_validator("entry_vacuum_id", mode="before")
    @classmethod
    def _require_vacuum_id(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Vacuum Ticket drain requires Vacuum identity")
        return normalized


VacuumDrainEvent = (
    EntryFilled
    | EntryVacuumAbsenceConfirmed
    | EntryVacuumCancelRequested
    | EntryVacuumOrderAbsenceConfirmed
    | EntryVacuumSuperseded
    | VacuumPartialFlattenRequired
    | VacuumPartialRetained
)


@dataclass(frozen=True)
class VacuumTicketDrainPlan:
    event: VacuumDrainEvent | None
    reason_code: str


class _TicketEventFields(TypedDict):
    event_id: str
    ticket_id: str
    sequence: int
    occurred_at_ms: int


def plan_vacuum_ticket_drain(
    facts: VacuumTicketDrainFacts,
) -> VacuumTicketDrainPlan:
    """Plan one reducer event without performing database or venue I/O."""

    aggregate = facts.aggregate
    snapshot = facts.position_snapshot
    if snapshot is not None and snapshot.netting_domain != aggregate.identity.netting_domain:
        raise ValueError("Vacuum position snapshot Netting Domain mismatch")

    if aggregate.status in {
        AggregateStatus.ENTRY_ACCEPTED,
        AggregateStatus.ENTRY_VACUUM_CANCEL_PENDING,
        AggregateStatus.ENTRY_VACUUM_CANCEL_REJECTED,
    }:
        if snapshot is None:
            return VacuumTicketDrainPlan(None, "POSITION_FACTS_REQUIRED")
        entry_order_id = aggregate.entry_exchange_order_id
        if entry_order_id is None:
            raise ValueError("Vacuum ENTRY drain lacks exchange order identity")
        open_entry = next(
            (
                order
                for order in snapshot.open_orders
                if order.exchange_order_id == entry_order_id
            ),
            None,
        )
        if open_entry is not None:
            if aggregate.status is AggregateStatus.ENTRY_VACUUM_CANCEL_PENDING:
                return VacuumTicketDrainPlan(None, "WAITING_CANCEL_ORDER_ABSENCE")
            if snapshot.quantity >= aggregate.ticket.quantity:
                return VacuumTicketDrainPlan(None, "FULL_FILL_WITH_OPEN_ENTRY_ORDER")
            return VacuumTicketDrainPlan(
                EntryVacuumCancelRequested(
                    **_event_fields(aggregate, facts.now_ms),
                    entry_vacuum_id=facts.entry_vacuum_id,
                    exchange_order_id=entry_order_id,
                    observed_qty=snapshot.quantity,
                    average_fill_price=snapshot.average_entry_price,
                ),
                "VACUUM_ENTRY_CANCEL_REQUIRED",
            )
        return VacuumTicketDrainPlan(
            EntryVacuumOrderAbsenceConfirmed(
                **_event_fields(aggregate, facts.now_ms),
                entry_vacuum_id=facts.entry_vacuum_id,
                exchange_order_id=entry_order_id,
                final_filled_qty=snapshot.quantity,
                average_fill_price=snapshot.average_entry_price,
            ),
            "VACUUM_ENTRY_ORDER_ABSENT",
        )

    if aggregate.status is not AggregateStatus.ENTRY_VACUUM_CANCELLED:
        return VacuumTicketDrainPlan(None, "WAITING_EXISTING_LIFECYCLE")
    if aggregate.position_qty == 0:
        return VacuumTicketDrainPlan(
            EntryVacuumAbsenceConfirmed(
                **_event_fields(aggregate, facts.now_ms),
                entry_vacuum_id=facts.entry_vacuum_id,
            ),
            "VACUUM_ZERO_FILL_CONFIRMED",
        )
    if aggregate.average_fill_price is None:
        raise ValueError("Vacuum filled quantity requires average fill price")
    risk = assess_post_fill_risk(
        PostFillRiskRequest(
            position_side=aggregate.identity.netting_domain.position_side,
            filled_quantity=aggregate.position_qty,
            average_fill_price=aggregate.average_fill_price,
            initial_stop_price=aggregate.ticket.initial_stop_price,
            planned_stop_risk_budget=aggregate.ticket.planned_stop_risk_budget,
            post_fill_stop_risk_limit=aggregate.ticket.post_fill_stop_risk_limit,
        )
    )
    if aggregate.position_qty == aggregate.ticket.quantity:
        return VacuumTicketDrainPlan(
            EntryFilled(
                **_event_fields(aggregate, facts.now_ms),
                filled_qty=aggregate.position_qty,
                average_fill_price=aggregate.average_fill_price,
                post_fill_risk=risk,
                venue_reported_liquidation_price=None,
                position_observed_at_ms=facts.now_ms,
            ),
            "VACUUM_FULL_FILL_MATERIALIZED",
        )
    if facts.quantity_step is None or facts.tp1_quantity_fraction is None:
        return VacuumTicketDrainPlan(None, "EXIT_POLICY_FACTS_REQUIRED")
    try:
        split = split_tp1_quantity(
            total_quantity=aggregate.position_qty,
            quantity_step=facts.quantity_step,
            quantity_fraction=facts.tp1_quantity_fraction,
        )
    except ValueError:
        split = None
    if split is not None and risk.disposition is PostFillDisposition.NORMAL:
        return VacuumTicketDrainPlan(
            VacuumPartialRetained(
                **_event_fields(aggregate, facts.now_ms),
                entry_vacuum_id=facts.entry_vacuum_id,
                selection_authority_id=aggregate.ticket.selection_authority_id,
                requested_qty=aggregate.ticket.quantity,
                final_filled_qty=aggregate.position_qty,
                average_fill_price=aggregate.average_fill_price,
                quantity_step=facts.quantity_step,
                effective_tp1_qty=split.tp1_quantity,
                effective_runner_qty=split.runner_quantity,
                post_fill_risk=risk,
            ),
            "VACUUM_PARTIAL_RETAINED",
        )
    reason = (
        "vacuum_partial_two_leg_unavailable"
        if split is None
        else f"vacuum_partial_{risk.status.value}"
    )
    return VacuumTicketDrainPlan(
        VacuumPartialFlattenRequired(
            **_event_fields(aggregate, facts.now_ms),
            entry_vacuum_id=facts.entry_vacuum_id,
            final_filled_qty=aggregate.position_qty,
            average_fill_price=aggregate.average_fill_price,
            reason=reason,
        ),
        reason,
    )


async def drain_strategy_entry_vacuum_once(
    uow: KernelUnitOfWork,
    request: DrainStrategyEntryVacuumRequest,
) -> DrainStrategyEntryVacuumResult:
    """Advance exactly one durable drain action inside the caller's transaction."""

    vacuum = await uow.instrument_selection.get_current_entry_vacuum(
        strategy_group_id=request.strategy_group_id,
        selection_spec_id=request.selection_spec_id,
        for_update=True,
    )
    if vacuum is None:
        return DrainStrategyEntryVacuumResult(status=VacuumDrainStatus.NO_VACUUM)
    if vacuum.state is StrategyEntryVacuumState.OPEN:
        draining = await uow.instrument_selection.mark_entry_vacuum_draining(
            vacuum,
            started_at_ms=request.now_ms,
        )
        return DrainStrategyEntryVacuumResult(
            status=VacuumDrainStatus.DRAIN_STARTED,
            entry_vacuum_id=draining.entry_vacuum_id,
        )
    if vacuum.state is not StrategyEntryVacuumState.DRAINING_ENTRY:
        return DrainStrategyEntryVacuumResult(
            status=VacuumDrainStatus.WAITING_LIFECYCLE,
            entry_vacuum_id=vacuum.entry_vacuum_id,
            reason_code=f"VACUUM_STATE:{vacuum.state.value}",
        )

    ticket_id = await uow.instrument_selection.get_next_entry_vacuum_ticket(
        strategy_group_id=request.strategy_group_id
    )
    if ticket_id is None:
        return await _complete_entry_drain(uow, vacuum, request)
    if request.ticket_id is not None and request.ticket_id != ticket_id:
        return DrainStrategyEntryVacuumResult(
            status=VacuumDrainStatus.BLOCKED,
            entry_vacuum_id=vacuum.entry_vacuum_id,
            ticket_id=ticket_id,
            reason_code="VACUUM_DRAIN_TICKET_DRIFT",
        )
    aggregate = await uow.aggregates.get_for_update(ticket_id)
    if aggregate is None:
        return DrainStrategyEntryVacuumResult(
            status=VacuumDrainStatus.BLOCKED,
            entry_vacuum_id=vacuum.entry_vacuum_id,
            ticket_id=ticket_id,
            reason_code="VACUUM_DRAIN_AGGREGATE_MISSING",
        )

    if aggregate.status in {
        AggregateStatus.LEVERAGE_PENDING,
        AggregateStatus.LEVERAGE_CONFIRMED,
        AggregateStatus.ENTRY_PENDING,
    }:
        return await _supersede_or_wait_pre_dispatch(
            uow=uow,
            aggregate=aggregate,
            entry_vacuum_id=vacuum.entry_vacuum_id,
            now_ms=request.now_ms,
        )
    if aggregate.status in {
        AggregateStatus.LEVERAGE_OUTCOME_UNKNOWN,
        AggregateStatus.ENTRY_OUTCOME_UNKNOWN,
        AggregateStatus.ENTRY_VACUUM_CANCEL_OUTCOME_UNKNOWN,
    }:
        return _ticket_result(
            VacuumDrainStatus.WAITING_UNKNOWN_OUTCOME,
            vacuum.entry_vacuum_id,
            aggregate,
            "VACUUM_DRAIN_UNKNOWN_OUTCOME",
        )

    commands = await uow.exchange_commands.list_for_ticket(ticket_id)
    if aggregate.status is AggregateStatus.ENTRY_VACUUM_CANCEL_PENDING:
        cancel = _latest_vacuum_cancel(commands, vacuum.entry_vacuum_id)
        if cancel is None or cancel.status in {
            ExchangeCommandStatus.PREPARED,
            ExchangeCommandStatus.CLAIMED,
        }:
            return _ticket_result(
                VacuumDrainStatus.WAITING_COMMAND,
                vacuum.entry_vacuum_id,
                aggregate,
                "VACUUM_CANCEL_NOT_DISPATCHED",
            )
        if cancel.status is ExchangeCommandStatus.OUTCOME_UNKNOWN:
            return _ticket_result(
                VacuumDrainStatus.WAITING_UNKNOWN_OUTCOME,
                vacuum.entry_vacuum_id,
                aggregate,
                "VACUUM_CANCEL_OUTCOME_UNKNOWN",
            )

    quantity_step: Decimal | None = None
    tp1_fraction: Decimal | None = None
    if aggregate.status is AggregateStatus.ENTRY_VACUUM_CANCELLED:
        rules = await uow.signals.get_instrument_rules(
            aggregate.identity.netting_domain.venue_id,
            aggregate.identity.netting_domain.exchange_instrument_id,
        )
        policy = await uow.strategy_registry.get_exit_policy(
            exit_policy_id=aggregate.ticket.exit_policy_id,
            semantic_hash=aggregate.ticket.exit_policy_semantic_hash,
        )
        if aggregate.position_qty not in {Decimal(0), aggregate.ticket.quantity}:
            if rules is None or policy is None:
                return _ticket_result(
                    VacuumDrainStatus.BLOCKED,
                    vacuum.entry_vacuum_id,
                    aggregate,
                    "VACUUM_PARTIAL_EXIT_POLICY_FACTS_MISSING",
                )
            quantity_step = rules.quantity_step
            tp1_fraction = policy.tp1.quantity_fraction

    snapshot = request.position_snapshot
    if snapshot is not None:
        await uow.positions.upsert(ticket_id=ticket_id, snapshot=snapshot)
    planned = plan_vacuum_ticket_drain(
        VacuumTicketDrainFacts(
            aggregate=aggregate,
            entry_vacuum_id=vacuum.entry_vacuum_id,
            now_ms=request.now_ms,
            position_snapshot=snapshot,
            quantity_step=quantity_step,
            tp1_quantity_fraction=tp1_fraction,
        )
    )
    if planned.event is None:
        status = (
            VacuumDrainStatus.POSITION_FACTS_REQUIRED
            if planned.reason_code == "POSITION_FACTS_REQUIRED"
            else VacuumDrainStatus.WAITING_LIFECYCLE
        )
        return _ticket_result(
            status,
            vacuum.entry_vacuum_id,
            aggregate,
            planned.reason_code,
        )
    await uow.commit_reduction(
        event=planned.event,
        reduction=reduce_event(aggregate, planned.event),
        expected_version=aggregate.version,
    )
    return _event_result(vacuum.entry_vacuum_id, planned.event)


async def _supersede_or_wait_pre_dispatch(
    *,
    uow: KernelUnitOfWork,
    aggregate: TradeAggregate,
    entry_vacuum_id: str,
    now_ms: int,
) -> DrainStrategyEntryVacuumResult:
    commands = await uow.exchange_commands.list_for_ticket(
        aggregate.identity.ticket_id
    )
    command = _current_entry_mutation(commands)
    if command is None:
        return _ticket_result(
            VacuumDrainStatus.BLOCKED,
            entry_vacuum_id,
            aggregate,
            "VACUUM_PRE_DISPATCH_COMMAND_MISSING",
        )
    if command.status is ExchangeCommandStatus.PREPARED:
        await uow.exchange_commands.mark_prepared_superseded(
            command_id=command.command_id,
            observed_at_ms=now_ms,
            reason=f"selection_entry_vacuum:{entry_vacuum_id}",
        )
        event = EntryVacuumSuperseded(
            **_event_fields(aggregate, now_ms),
            entry_vacuum_id=entry_vacuum_id,
            command_id=command.command_id,
        )
        await uow.commit_reduction(
            event=event,
            reduction=reduce_event(aggregate, event),
            expected_version=aggregate.version,
        )
        return _event_result(entry_vacuum_id, event)
    status = (
        VacuumDrainStatus.WAITING_UNKNOWN_OUTCOME
        if command.status is ExchangeCommandStatus.OUTCOME_UNKNOWN
        else VacuumDrainStatus.WAITING_COMMAND
    )
    return _ticket_result(
        status,
        entry_vacuum_id,
        aggregate,
        f"VACUUM_PRE_DISPATCH_COMMAND:{command.status.value}",
    )


async def _complete_entry_drain(
    uow: KernelUnitOfWork,
    vacuum,
    request: DrainStrategyEntryVacuumRequest,
) -> DrainStrategyEntryVacuumResult:
    if vacuum.first_blocker == "OWNER_PAUSED":
        owner_control = await uow.owner_controls.get_strategy_control(
            request.strategy_group_id,
            for_update=True,
        )
        if (
            owner_control is None
            or owner_control.entry_state.value != "paused"
        ):
            return DrainStrategyEntryVacuumResult(
                status=VacuumDrainStatus.BLOCKED,
                entry_vacuum_id=vacuum.entry_vacuum_id,
                reason_code="OWNER_PAUSE_VACUUM_FACTS_INVALID",
            )
        paused = await uow.instrument_selection.mark_owner_pause_vacuum_drained(
            vacuum,
            drained_at_ms=request.now_ms,
        )
        return DrainStrategyEntryVacuumResult(
            status=VacuumDrainStatus.OWNER_PAUSED,
            entry_vacuum_id=paused.entry_vacuum_id,
            reason_code="OWNER_PAUSE_ENTRY_DRAINED",
        )
    if vacuum.source_generation_id is not None:
        drained = await uow.instrument_selection.mark_entry_vacuum_drained(
            vacuum,
            target_state="RECONFIGURING",
            drained_at_ms=request.now_ms,
        )
        return DrainStrategyEntryVacuumResult(
            status=VacuumDrainStatus.ENTRY_DRAINED,
            entry_vacuum_id=drained.entry_vacuum_id,
            reason_code="GENERATION_READY_FOR_MATERIALIZATION",
        )

    if vacuum.first_blocker != "NO_SELECTION_READY_MEMBERS":
        return DrainStrategyEntryVacuumResult(
            status=VacuumDrainStatus.BLOCKED,
            entry_vacuum_id=vacuum.entry_vacuum_id,
            reason_code="VALID_EMPTY_VACUUM_INTENT_INVALID",
        )

    snapshot = await uow.instrument_selection.get_snapshot_disposition(
        selection_spec_id=request.selection_spec_id,
        session_start_ms=vacuum.session_start_ms,
        for_update=True,
    )
    control = await uow.instrument_selection.get_selection_control(
        request.strategy_group_id,
        for_update=True,
    )
    owner_control = await uow.owner_controls.get_strategy_control(
        request.strategy_group_id,
        for_update=True,
    )
    current = await uow.instrument_selection.get_current_authority_projection(
        request.selection_spec_id
    )
    if (
        snapshot is None
        or snapshot.snapshot.selected_count != 0
        or control is None
        or owner_control is None
        or owner_control.entry_state.value != "enabled"
    ):
        return DrainStrategyEntryVacuumResult(
            status=VacuumDrainStatus.BLOCKED,
            entry_vacuum_id=vacuum.entry_vacuum_id,
            reason_code="VALID_EMPTY_FINALIZATION_FACTS_INVALID",
        )
    sequence = (
        1
        if current is None
        or current.authority.session_start_ms != vacuum.session_start_ms
        else current.authority.authority_sequence + 1
    )
    authority = SelectionSessionAuthority(
        selection_authority_id=(
            f"selection-authority:{request.selection_spec_id}:"
            f"{vacuum.session_start_ms}:{sequence}"
        ),
        selection_spec_id=request.selection_spec_id,
        session_start_ms=vacuum.session_start_ms,
        decision_boundary_ms=vacuum.session_start_ms + 4 * INTERVAL_MS,
        authority_sequence=sequence,
        selection_mode=SelectionMode.DYNAMIC_SELECTION,
        selection_snapshot_id=snapshot.snapshot.selection_snapshot_id,
        continued_from_selection_authority_id=(
            None if current is None else current.authority.selection_authority_id
        ),
        continuity_source_kind=ContinuitySourceKind.NONE,
        authority_gap_audit_id=None,
        materialization_generation_id=None,
        owner_control_version=owner_control.control_version,
        authority_outcome=AuthorityOutcome.VALID_EMPTY,
        authorized_pair=None,
        grant_proof=None,
        effective_from_ms=request.now_ms,
        first_eligible_close_time_ms=None,
        expires_at_ms=vacuum.session_start_ms + 100 * INTERVAL_MS,
        reason_code="NO_SELECTION_READY_MEMBERS",
        created_at_ms=request.now_ms,
    )
    await uow.instrument_selection.mark_entry_vacuum_drained(
        vacuum,
        target_state="VALID_EMPTY",
        drained_at_ms=request.now_ms,
    )
    await uow.instrument_selection.add_authority_and_set_current(
        authority,
        expected_current_version=(
            None if current is None else current.projection_version
        ),
    )
    if (
        control.selection_mode is SelectionMode.STATIC_BASELINE
        and control.pending_selection_mode is SelectionMode.DYNAMIC_SELECTION
        and control.pending_effective_session_start_ms == vacuum.session_start_ms
    ):
        await uow.instrument_selection.activate_pending_selection_mode(
            strategy_group_id=request.strategy_group_id,
            expected_control_version=control.control_version,
            expected_pending_mode=SelectionMode.DYNAMIC_SELECTION,
            activated_at_ms=request.now_ms,
        )
    elif control.selection_mode is not SelectionMode.DYNAMIC_SELECTION:
        raise ValueError("VALID_EMPTY requires current or pending Dynamic mode")
    return DrainStrategyEntryVacuumResult(
        status=VacuumDrainStatus.VALID_EMPTY_COMMITTED,
        entry_vacuum_id=vacuum.entry_vacuum_id,
        selection_authority_id=authority.selection_authority_id,
        reason_code=authority.reason_code,
    )


def _current_entry_mutation(
    commands: list[ExchangeCommand],
) -> ExchangeCommand | None:
    candidates = [
        command
        for command in commands
        if command.kind in {
            ExchangeCommandKind.SET_LEVERAGE,
            ExchangeCommandKind.ENTRY,
        }
        and command.status
        in {
            ExchangeCommandStatus.PREPARED,
            ExchangeCommandStatus.CLAIMED,
            ExchangeCommandStatus.OUTCOME_UNKNOWN,
        }
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item.created_at_ms, item.generation))


def _latest_vacuum_cancel(
    commands: list[ExchangeCommand],
    entry_vacuum_id: str,
) -> ExchangeCommand | None:
    candidates = [
        command
        for command in commands
        if command.kind is ExchangeCommandKind.CANCEL_ORDER
        and isinstance(command.payload, CancelCommandPayload)
        and command.payload.purpose == "selection_vacuum_entry"
        and command.payload.entry_vacuum_id == entry_vacuum_id
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.generation)


def _event_fields(
    aggregate: TradeAggregate,
    occurred_at_ms: int,
) -> _TicketEventFields:
    sequence = aggregate.last_event_sequence + 1
    return {
        "event_id": f"event:{aggregate.identity.ticket_id}:{sequence}",
        "ticket_id": aggregate.identity.ticket_id,
        "sequence": sequence,
        "occurred_at_ms": occurred_at_ms,
    }


def _ticket_result(
    status: VacuumDrainStatus,
    entry_vacuum_id: str,
    aggregate: TradeAggregate,
    reason_code: str,
) -> DrainStrategyEntryVacuumResult:
    return DrainStrategyEntryVacuumResult(
        status=status,
        entry_vacuum_id=entry_vacuum_id,
        ticket_id=aggregate.identity.ticket_id,
        reason_code=reason_code,
    )


def _event_result(
    entry_vacuum_id: str,
    event: VacuumDrainEvent,
) -> DrainStrategyEntryVacuumResult:
    status = {
        EntryVacuumSuperseded: VacuumDrainStatus.PREPARED_ENTRY_SUPERSEDED,
        EntryVacuumCancelRequested: VacuumDrainStatus.CANCEL_REQUESTED,
        EntryVacuumOrderAbsenceConfirmed: VacuumDrainStatus.ORDER_ABSENCE_RECORDED,
        EntryVacuumAbsenceConfirmed: VacuumDrainStatus.ZERO_FILL_CLOSED,
        EntryFilled: VacuumDrainStatus.FULL_FILL_PROTECTION_REQUESTED,
        VacuumPartialRetained: VacuumDrainStatus.PARTIAL_RETAINED_PROTECTION_REQUESTED,
        VacuumPartialFlattenRequired: VacuumDrainStatus.PARTIAL_FLATTEN_REQUESTED,
    }[type(event)]
    return DrainStrategyEntryVacuumResult(
        status=status,
        entry_vacuum_id=entry_vacuum_id,
        ticket_id=event.ticket_id,
        event_id=event.event_id,
    )
