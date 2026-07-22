"""Reconcile one exact Ticket against one typed venue snapshot."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator

from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommandStatus,
)
from src.trading_kernel.domain.events import (
    CancelOrderAbsenceConfirmed,
    EntryFilled,
    EntryPartiallyFilled,
    ExternalFlatDetected,
    ExitRequested,
    OwnedOrphanOrderDetected,
    OwnedOrderAbsenceConfirmed,
    PositionFlatConfirmed,
    ReconciliationMatched,
    TradeEvent,
    UnownedOrderDetected,
)
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.reducer import reduce_event


class ReconcileTicketStatus(StrEnum):
    NO_CHANGE = "no_change"
    ENTRY_FILL_RECORDED = "entry_fill_recorded"
    PARTIAL_FILL_INCIDENT = "partial_fill_incident"
    EXTERNAL_FLAT_INCIDENT = "external_flat_incident"
    POSITION_FLAT_RECORDED = "position_flat_recorded"
    PROTECTION_RESIDUE = "protection_residue"
    CANCEL_ABSENCE_RECORDED = "cancel_absence_recorded"
    OWNED_ORPHAN_CANCEL_REQUESTED = "owned_orphan_cancel_requested"
    UNOWNED_ORDER_INCIDENT = "unowned_order_incident"
    MATCHED = "matched"


class ExitTicketStatus(StrEnum):
    REQUESTED = "requested"


class ReconcileTicketRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    snapshot: PositionSnapshot


class ExitTicketRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    reason: str
    requested_at_ms: int

    @field_validator("reason", mode="before")
    @classmethod
    def _require_reason(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("exit reason must be non-blank")
        return normalized


class ReconcileTicketResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ReconcileTicketStatus


class ExitTicketResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ExitTicketStatus


async def reconcile_ticket(
    uow: KernelUnitOfWork,
    request: ReconcileTicketRequest,
) -> ReconcileTicketResult:
    aggregate = await uow.aggregates.get(request.ticket_id)
    if aggregate is None:
        raise ValueError("Ticket aggregate does not exist")
    snapshot = request.snapshot
    if snapshot.netting_domain != aggregate.identity.netting_domain:
        raise ValueError("position snapshot Netting Domain mismatch")
    await uow.positions.upsert(ticket_id=request.ticket_id, snapshot=snapshot)

    event: TradeEvent | None = None
    status = ReconcileTicketStatus.NO_CHANGE
    if aggregate.status is AggregateStatus.ENTRY_ACCEPTED:
        if snapshot.quantity == aggregate.ticket.quantity:
            event = EntryFilled(
                event_id=_event_id(aggregate),
                ticket_id=request.ticket_id,
                sequence=aggregate.last_event_sequence + 1,
                occurred_at_ms=snapshot.observed_at_ms,
                filled_qty=snapshot.quantity,
                average_fill_price=_required_average_entry_price(snapshot),
            )
            status = ReconcileTicketStatus.ENTRY_FILL_RECORDED
        elif 0 < snapshot.quantity < aggregate.ticket.quantity:
            event = EntryPartiallyFilled(
                event_id=_event_id(aggregate),
                ticket_id=request.ticket_id,
                sequence=aggregate.last_event_sequence + 1,
                occurred_at_ms=snapshot.observed_at_ms,
                filled_qty=snapshot.quantity,
                requested_qty=aggregate.ticket.quantity,
                average_fill_price=_required_average_entry_price(snapshot),
            )
            status = ReconcileTicketStatus.PARTIAL_FILL_INCIDENT
    elif aggregate.status in {
        AggregateStatus.EXIT_PENDING,
        AggregateStatus.EXIT_ACCEPTED,
        AggregateStatus.EXIT_REJECTED,
        AggregateStatus.EXIT_OUTCOME_UNKNOWN,
        AggregateStatus.CONTROLLED_FLATTEN_PENDING,
        AggregateStatus.CONTROLLED_FLATTEN_ACCEPTED,
        AggregateStatus.CONTROLLED_FLATTEN_REJECTED,
        AggregateStatus.CONTROLLED_FLATTEN_OUTCOME_UNKNOWN,
    } and snapshot.quantity == 0:
        event = PositionFlatConfirmed(
            event_id=_event_id(aggregate),
            ticket_id=request.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=snapshot.observed_at_ms,
        )
        status = ReconcileTicketStatus.POSITION_FLAT_RECORDED
    elif aggregate.status in {
        AggregateStatus.TP1_PENDING,
        AggregateStatus.TP1_REJECTED,
        AggregateStatus.TP1_OUTCOME_UNKNOWN,
        AggregateStatus.POSITION_PROTECTED,
        AggregateStatus.RUNNER_REPLACEMENT_PENDING,
        AggregateStatus.RUNNER_REPLACEMENT_REJECTED,
        AggregateStatus.RUNNER_REPLACEMENT_OUTCOME_UNKNOWN,
        AggregateStatus.RUNNER_OLD_STOP_CANCEL_PENDING,
        AggregateStatus.RUNNER_OLD_STOP_CANCEL_REJECTED,
        AggregateStatus.RUNNER_OLD_STOP_CANCEL_OUTCOME_UNKNOWN,
        AggregateStatus.RUNNER_PROTECTED,
    } and snapshot.quantity == 0:
        event = ExternalFlatDetected(
            event_id=_event_id(aggregate),
            ticket_id=request.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=snapshot.observed_at_ms,
        )
        status = ReconcileTicketStatus.EXTERNAL_FLAT_INCIDENT
    elif aggregate.status is AggregateStatus.RECONCILIATION_PENDING:
        if aggregate.pending_cancel_exchange_order_id is not None:
            return ReconcileTicketResult(
                status=ReconcileTicketStatus.PROTECTION_RESIDUE
            )
        unowned_order = next(
            (
                order
                for order in snapshot.open_orders
                if not _is_kernel_owned_order(order.venue_client_order_id)
            ),
            None,
        )
        if unowned_order is not None:
            existing_incident = await uow.incidents.get_open_for_ticket(
                request.ticket_id
            )
            if (
                existing_incident is not None
                and existing_incident.incident_kind == "unowned_open_order"
            ):
                return ReconcileTicketResult(
                    status=ReconcileTicketStatus.UNOWNED_ORDER_INCIDENT
                )
            event = UnownedOrderDetected(
                event_id=_event_id(aggregate),
                ticket_id=request.ticket_id,
                sequence=aggregate.last_event_sequence + 1,
                occurred_at_ms=snapshot.observed_at_ms,
                exchange_order_id=unowned_order.exchange_order_id,
            )
            status = ReconcileTicketStatus.UNOWNED_ORDER_INCIDENT
        else:
            known_order_id = _next_known_cleanup_order_id(aggregate)
            if known_order_id is not None:
                known_still_open = any(
                    order.exchange_order_id == known_order_id
                    for order in snapshot.open_orders
                )
                if not known_still_open:
                    event = OwnedOrderAbsenceConfirmed(
                        event_id=_event_id(aggregate),
                        ticket_id=request.ticket_id,
                        sequence=aggregate.last_event_sequence + 1,
                        occurred_at_ms=snapshot.observed_at_ms,
                        exchange_order_id=known_order_id,
                    )
                    status = ReconcileTicketStatus.CANCEL_ABSENCE_RECORDED
                else:
                    commands = await uow.exchange_commands.list_for_ticket(
                        request.ticket_id
                    )
                    if _has_cancel_attempt(commands, known_order_id):
                        return ReconcileTicketResult(
                            status=ReconcileTicketStatus.PROTECTION_RESIDUE
                        )
                    event = OwnedOrphanOrderDetected(
                        event_id=_event_id(aggregate),
                        ticket_id=request.ticket_id,
                        sequence=aggregate.last_event_sequence + 1,
                        occurred_at_ms=snapshot.observed_at_ms,
                        exchange_order_id=known_order_id,
                    )
                    status = ReconcileTicketStatus.OWNED_ORPHAN_CANCEL_REQUESTED
            elif snapshot.open_orders:
                owned_order = snapshot.open_orders[0]
                commands = await uow.exchange_commands.list_for_ticket(request.ticket_id)
                if _has_cancel_attempt(commands, owned_order.exchange_order_id):
                    return ReconcileTicketResult(
                        status=ReconcileTicketStatus.PROTECTION_RESIDUE
                    )
                event = OwnedOrphanOrderDetected(
                    event_id=_event_id(aggregate),
                    ticket_id=request.ticket_id,
                    sequence=aggregate.last_event_sequence + 1,
                    occurred_at_ms=snapshot.observed_at_ms,
                    exchange_order_id=owned_order.exchange_order_id,
                )
                status = ReconcileTicketStatus.OWNED_ORPHAN_CANCEL_REQUESTED
            elif snapshot.quantity == 0:
                event = ReconciliationMatched(
                    event_id=_event_id(aggregate),
                    ticket_id=request.ticket_id,
                    sequence=aggregate.last_event_sequence + 1,
                    occurred_at_ms=snapshot.observed_at_ms,
                )
                status = ReconcileTicketStatus.MATCHED
    elif aggregate.status in {
        AggregateStatus.CANCEL_REJECTED,
        AggregateStatus.CANCEL_OUTCOME_UNKNOWN,
    }:
        target_order_id = aggregate.pending_cancel_exchange_order_id
        if target_order_id is None:
            raise RuntimeError("cancel recovery state has no exact order identity")
        target_still_open = any(
            order.exchange_order_id == target_order_id
            for order in snapshot.open_orders
        )
        if target_still_open:
            if aggregate.status is AggregateStatus.CANCEL_OUTCOME_UNKNOWN:
                return ReconcileTicketResult(
                    status=ReconcileTicketStatus.PROTECTION_RESIDUE
                )
            event = OwnedOrphanOrderDetected(
                event_id=_event_id(aggregate),
                ticket_id=request.ticket_id,
                sequence=aggregate.last_event_sequence + 1,
                occurred_at_ms=snapshot.observed_at_ms,
                exchange_order_id=target_order_id,
            )
            status = ReconcileTicketStatus.OWNED_ORPHAN_CANCEL_REQUESTED
        else:
            event = CancelOrderAbsenceConfirmed(
                event_id=_event_id(aggregate),
                ticket_id=request.ticket_id,
                sequence=aggregate.last_event_sequence + 1,
                occurred_at_ms=snapshot.observed_at_ms,
                exchange_order_id=target_order_id,
            )
            status = ReconcileTicketStatus.CANCEL_ABSENCE_RECORDED

    if event is not None:
        await uow.commit_reduction(
            event=event,
            reduction=reduce_event(aggregate, event),
            expected_version=aggregate.version,
        )
    return ReconcileTicketResult(status=status)


def _required_average_entry_price(snapshot: PositionSnapshot) -> Decimal:
    price = snapshot.average_entry_price
    if price is None:
        raise RuntimeError("open position snapshot lacks average entry price")
    return price


async def request_exit(
    uow: KernelUnitOfWork,
    request: ExitTicketRequest,
) -> ExitTicketResult:
    aggregate = await uow.aggregates.get(request.ticket_id)
    if aggregate is None:
        raise ValueError("Ticket aggregate does not exist")
    event = ExitRequested(
        event_id=_event_id(aggregate),
        ticket_id=request.ticket_id,
        sequence=aggregate.last_event_sequence + 1,
        occurred_at_ms=request.requested_at_ms,
        reason=request.reason,
    )
    await uow.commit_reduction(
        event=event,
        reduction=reduce_event(aggregate, event),
        expected_version=aggregate.version,
    )
    return ExitTicketResult(status=ExitTicketStatus.REQUESTED)


def _event_id(aggregate) -> str:
    return (
        f"event:{aggregate.identity.ticket_id}:"
        f"{aggregate.last_event_sequence + 1}"
    )


def _is_kernel_owned_order(venue_client_order_id: str | None) -> bool:
    return str(venue_client_order_id or "").startswith("brc-")


def _has_cancel_attempt(commands, exchange_order_id: str) -> bool:
    non_repeatable = {
        ExchangeCommandStatus.PREPARED,
        ExchangeCommandStatus.CLAIMED,
        ExchangeCommandStatus.ACCEPTED,
        ExchangeCommandStatus.OUTCOME_UNKNOWN,
    }
    return any(
        command.status in non_repeatable
        and isinstance(command.payload, CancelCommandPayload)
        and command.payload.exchange_order_id == exchange_order_id
        for command in commands
    )


def _next_known_cleanup_order_id(aggregate) -> str | None:
    identities: list[str] = []
    for identity in (
        aggregate.tp1_exchange_order_id,
        aggregate.active_stop_exchange_order_id,
        aggregate.initial_stop_exchange_order_id,
    ):
        if identity is not None and identity not in identities:
            identities.append(identity)
    return None if not identities else identities[0]
