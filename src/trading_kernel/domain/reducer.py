"""Deterministic state reduction for one Ticket lifecycle."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from src.trading_kernel.domain.aggregate import AggregateStatus, TradeAggregate
from src.trading_kernel.domain.effects import (
    CancelEntryRemainder,
    CancelProtectionOrders,
    KernelEffect,
    MarkCancelCommandReconciledAbsent,
    OpenIncident,
    PrepareEntryCommand,
    PrepareControlledFlattenCommand,
    PrepareExitCommand,
    PrepareInitialStopCommand,
    ReleaseBudget,
    ReleaseEntryLane,
    ResolveIncident,
    RequestControlledFlatten,
    SettleBudget,
)
from src.trading_kernel.domain.events import (
    BudgetSettled,
    CancelOrderAbsenceConfirmed,
    CancelOrderOutcomeUnknown,
    CancelOrderRejected,
    ControlledFlattenAbsenceConfirmed,
    ControlledFlattenAccepted,
    ControlledFlattenOutcomeUnknown,
    ControlledFlattenRejected,
    EntryAccepted,
    EntryAbsenceConfirmed,
    EntryFilled,
    EntryOutcomeUnknown,
    EntryPartiallyFilled,
    EntryRemainderCancelConfirmed,
    EntryRemainderCancelOutcomeUnknown,
    EntryRemainderCancelRejected,
    EntryRejected,
    ExternalFlatDetected,
    ExitAccepted,
    ExitAbsenceConfirmed,
    ExitOutcomeUnknown,
    ExitRejected,
    ExitRequested,
    InitialStopConfirmed,
    InitialStopAbsenceConfirmed,
    InitialStopOutcomeUnknown,
    InitialStopRejected,
    OwnedOrphanOrderDetected,
    OwnedOrphanCancelConfirmed,
    PositionFlatConfirmed,
    ProtectionCancelConfirmed,
    ReconciliationMatched,
    ReviewRecorded,
    TicketIssued,
    TradeEvent,
    UnownedOrderDetected,
)


class InvalidLifecycleTransition(ValueError):
    """Raised when an event contradicts current Ticket lifecycle truth."""


class Reduction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    aggregate: TradeAggregate
    effects: tuple[KernelEffect, ...] = ()


def reduce_event(
    current: TradeAggregate | None,
    event: TradeEvent,
) -> Reduction:
    if current is None:
        return _issue_ticket(event)

    _require_event_identity_and_sequence(current, event)

    if isinstance(event, EntryAccepted):
        _require_status_in(
            current,
            {
                AggregateStatus.ENTRY_PENDING,
                AggregateStatus.ENTRY_OUTCOME_UNKNOWN,
            },
        )
        exchange_order_id = str(event.exchange_order_id or "").strip()
        if not exchange_order_id:
            raise InvalidLifecycleTransition("ENTRY acceptance requires order identity")
        entry_accept_effects: tuple[KernelEffect, ...] = ()
        if current.status is AggregateStatus.ENTRY_OUTCOME_UNKNOWN:
            entry_accept_effects = (
                ResolveIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="entry_outcome_unknown",
                ),
            )
        return _transition(
            current,
            event,
            status=AggregateStatus.ENTRY_ACCEPTED,
            updates={"entry_exchange_order_id": exchange_order_id},
            effects=entry_accept_effects,
        )

    if isinstance(event, EntryOutcomeUnknown):
        _require_status(current, AggregateStatus.ENTRY_PENDING)
        if not str(event.reason or "").strip():
            raise InvalidLifecycleTransition("unknown ENTRY outcome requires reason")
        return _transition(
            current,
            event,
            status=AggregateStatus.ENTRY_OUTCOME_UNKNOWN,
            effects=(
                OpenIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="entry_outcome_unknown",
                ),
            ),
        )

    if isinstance(event, EntryRejected):
        _require_status(current, AggregateStatus.ENTRY_PENDING)
        return _transition(
            current,
            event,
            status=AggregateStatus.ENTRY_REJECTED,
            updates={"entry_lane_held": False},
            effects=(
                ReleaseBudget(ticket_id=current.identity.ticket_id),
                ReleaseEntryLane(ticket_id=current.identity.ticket_id),
            ),
        )

    if isinstance(event, EntryAbsenceConfirmed):
        _require_status(current, AggregateStatus.ENTRY_OUTCOME_UNKNOWN)
        if not str(event.command_id or "").strip():
            raise InvalidLifecycleTransition(
                "reconciled ENTRY absence requires command identity"
            )
        return _transition(
            current,
            event,
            status=AggregateStatus.ENTRY_RECONCILED_ABSENT,
            updates={"entry_lane_held": False},
            effects=(
                ResolveIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="entry_outcome_unknown",
                ),
                ReleaseBudget(ticket_id=current.identity.ticket_id),
                ReleaseEntryLane(ticket_id=current.identity.ticket_id),
            ),
        )

    if isinstance(event, EntryFilled):
        _require_status_in(
            current,
            {AggregateStatus.ENTRY_PENDING, AggregateStatus.ENTRY_ACCEPTED},
        )
        if event.filled_qty != current.ticket.quantity:
            raise InvalidLifecycleTransition("full entry fill must equal Ticket quantity")
        if event.average_fill_price <= 0:
            raise InvalidLifecycleTransition("average fill price must be positive")
        return _transition(
            current,
            event,
            status=AggregateStatus.PROTECTION_PENDING,
            updates={
                "position_qty": event.filled_qty,
                "average_fill_price": event.average_fill_price,
            },
            effects=(
                PrepareInitialStopCommand(
                    ticket_id=current.identity.ticket_id,
                    quantity=event.filled_qty,
                    stop_price=current.ticket.initial_stop_price,
                ),
            ),
        )

    if isinstance(event, EntryPartiallyFilled):
        _require_status_in(
            current,
            {AggregateStatus.ENTRY_PENDING, AggregateStatus.ENTRY_ACCEPTED},
        )
        if not Decimal("0") < event.filled_qty < event.requested_qty:
            raise InvalidLifecycleTransition("partial fill quantity is contradictory")
        if event.requested_qty != current.ticket.quantity:
            raise InvalidLifecycleTransition("partial fill request differs from Ticket")
        return _transition(
            current,
            event,
            status=AggregateStatus.PARTIAL_FILL_INCIDENT,
            updates={
                "position_qty": event.filled_qty,
                "average_fill_price": event.average_fill_price,
            },
            effects=(
                OpenIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="unsupported_partial_entry_fill",
                ),
                CancelEntryRemainder(ticket_id=current.identity.ticket_id),
                RequestControlledFlatten(
                    ticket_id=current.identity.ticket_id,
                    quantity=event.filled_qty,
                ),
            ),
        )

    if isinstance(event, EntryRemainderCancelConfirmed):
        _require_status_in(
            current,
            {
                AggregateStatus.PARTIAL_FILL_INCIDENT,
                AggregateStatus.PARTIAL_FILL_CANCEL_OUTCOME_UNKNOWN,
            },
        )
        if event.exchange_order_id != current.entry_exchange_order_id:
            raise InvalidLifecycleTransition("ENTRY remainder cancel identity mismatch")
        cancel_recovery_effects: list[KernelEffect] = []
        if current.status is AggregateStatus.PARTIAL_FILL_CANCEL_OUTCOME_UNKNOWN:
            cancel_recovery_effects.extend(
                (
                    MarkCancelCommandReconciledAbsent(
                        ticket_id=current.identity.ticket_id,
                        exchange_order_id=event.exchange_order_id,
                    ),
                    ResolveIncident(
                        ticket_id=current.identity.ticket_id,
                        incident_kind="entry_remainder_cancel_outcome_unknown",
                    ),
                )
            )
        cancel_recovery_effects.append(
            PrepareControlledFlattenCommand(
                ticket_id=current.identity.ticket_id,
                quantity=current.position_qty,
            )
        )
        return _transition(
            current,
            event,
            status=AggregateStatus.CONTROLLED_FLATTEN_PENDING,
            effects=tuple(cancel_recovery_effects),
        )

    if isinstance(event, EntryRemainderCancelRejected):
        _require_status(current, AggregateStatus.PARTIAL_FILL_INCIDENT)
        if event.exchange_order_id != current.entry_exchange_order_id:
            raise InvalidLifecycleTransition("rejected ENTRY cancel identity mismatch")
        if not str(event.reason or "").strip():
            raise InvalidLifecycleTransition("ENTRY cancel rejection requires reason")
        return _transition(
            current,
            event,
            status=AggregateStatus.PARTIAL_FILL_CANCEL_REJECTED,
            effects=(
                OpenIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="entry_remainder_cancel_rejected",
                ),
            ),
        )

    if isinstance(event, EntryRemainderCancelOutcomeUnknown):
        _require_status(current, AggregateStatus.PARTIAL_FILL_INCIDENT)
        if event.exchange_order_id != current.entry_exchange_order_id:
            raise InvalidLifecycleTransition("unknown ENTRY cancel identity mismatch")
        if not str(event.reason or "").strip():
            raise InvalidLifecycleTransition("unknown ENTRY cancel requires reason")
        return _transition(
            current,
            event,
            status=AggregateStatus.PARTIAL_FILL_CANCEL_OUTCOME_UNKNOWN,
            effects=(
                OpenIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="entry_remainder_cancel_outcome_unknown",
                ),
            ),
        )
    if isinstance(event, InitialStopConfirmed):
        _require_status_in(
            current,
            {
                AggregateStatus.PROTECTION_PENDING,
                AggregateStatus.INITIAL_STOP_OUTCOME_UNKNOWN,
            },
        )
        if event.protected_qty != current.position_qty:
            raise InvalidLifecycleTransition("initial stop does not cover exact position")
        if not str(event.exchange_order_id or "").strip():
            raise InvalidLifecycleTransition("initial stop order identity is required")
        initial_stop_effects: list[KernelEffect] = []
        if current.status is AggregateStatus.INITIAL_STOP_OUTCOME_UNKNOWN:
            initial_stop_effects.append(
                ResolveIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="initial_stop_outcome_unknown",
                )
            )
        initial_stop_effects.append(
            ReleaseEntryLane(ticket_id=current.identity.ticket_id)
        )
        return _transition(
            current,
            event,
            status=AggregateStatus.POSITION_PROTECTED,
            updates={
                "entry_lane_held": False,
                "protected_qty": event.protected_qty,
                "initial_stop_exchange_order_id": event.exchange_order_id.strip(),
            },
            effects=tuple(initial_stop_effects),
        )

    if isinstance(event, InitialStopRejected):
        _require_status(current, AggregateStatus.PROTECTION_PENDING)
        reason = str(event.reason or "").strip()
        if not reason:
            raise InvalidLifecycleTransition("initial stop rejection requires reason")
        return _transition(
            current,
            event,
            status=AggregateStatus.EXIT_PENDING,
            effects=(
                OpenIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="initial_stop_rejected",
                ),
                PrepareExitCommand(
                    ticket_id=current.identity.ticket_id,
                    quantity=current.position_qty,
                    reason="initial_stop_rejected",
                ),
            ),
        )

    if isinstance(event, InitialStopOutcomeUnknown):
        _require_status(current, AggregateStatus.PROTECTION_PENDING)
        reason = str(event.reason or "").strip()
        if not reason:
            raise InvalidLifecycleTransition("unknown initial stop outcome requires reason")
        return _transition(
            current,
            event,
            status=AggregateStatus.INITIAL_STOP_OUTCOME_UNKNOWN,
            effects=(
                OpenIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="initial_stop_outcome_unknown",
                ),
            ),
        )

    if isinstance(event, InitialStopAbsenceConfirmed):
        _require_status(current, AggregateStatus.INITIAL_STOP_OUTCOME_UNKNOWN)
        if not str(event.command_id or "").strip():
            raise InvalidLifecycleTransition(
                "reconciled initial stop absence requires command identity"
            )
        return _transition(
            current,
            event,
            status=AggregateStatus.EXIT_PENDING,
            effects=(
                ResolveIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="initial_stop_outcome_unknown",
                ),
                OpenIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="initial_stop_absent",
                ),
                PrepareExitCommand(
                    ticket_id=current.identity.ticket_id,
                    quantity=current.position_qty,
                    reason="initial_stop_absent",
                ),
            ),
        )

    if isinstance(event, ExitRequested):
        _require_status_in(
            current,
            {AggregateStatus.POSITION_PROTECTED, AggregateStatus.EXIT_REJECTED},
        )
        reason = str(event.reason or "").strip()
        if not reason:
            raise InvalidLifecycleTransition("exit reason is required")
        return _transition(
            current,
            event,
            status=AggregateStatus.EXIT_PENDING,
            effects=(
                PrepareExitCommand(
                    ticket_id=current.identity.ticket_id,
                    quantity=current.position_qty,
                    reason=reason,
                ),
            ),
        )

    if isinstance(event, ExitAccepted):
        _require_status_in(
            current,
            {
                AggregateStatus.EXIT_PENDING,
                AggregateStatus.EXIT_OUTCOME_UNKNOWN,
            },
        )
        exchange_order_id = str(event.exchange_order_id or "").strip()
        if not exchange_order_id:
            raise InvalidLifecycleTransition("EXIT acceptance requires order identity")
        exit_accept_effects: tuple[KernelEffect, ...] = ()
        if current.status is AggregateStatus.EXIT_OUTCOME_UNKNOWN:
            exit_accept_effects = (
                ResolveIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="exit_outcome_unknown",
                ),
            )
        return _transition(
            current,
            event,
            status=AggregateStatus.EXIT_ACCEPTED,
            updates={"exit_exchange_order_id": exchange_order_id},
            effects=exit_accept_effects,
        )

    if isinstance(event, ExitRejected):
        _require_status(current, AggregateStatus.EXIT_PENDING)
        reason = str(event.reason or "").strip()
        if not reason:
            raise InvalidLifecycleTransition("EXIT rejection requires reason")
        return _transition(
            current,
            event,
            status=AggregateStatus.EXIT_REJECTED,
            effects=(
                OpenIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="exit_rejected",
                ),
            ),
        )

    if isinstance(event, ExitOutcomeUnknown):
        _require_status(current, AggregateStatus.EXIT_PENDING)
        reason = str(event.reason or "").strip()
        if not reason:
            raise InvalidLifecycleTransition("EXIT unknown outcome requires reason")
        return _transition(
            current,
            event,
            status=AggregateStatus.EXIT_OUTCOME_UNKNOWN,
            effects=(
                OpenIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="exit_outcome_unknown",
                ),
            ),
        )

    if isinstance(event, ExitAbsenceConfirmed):
        _require_status(current, AggregateStatus.EXIT_OUTCOME_UNKNOWN)
        if not str(event.command_id or "").strip():
            raise InvalidLifecycleTransition(
                "reconciled EXIT absence requires command identity"
            )
        return _transition(
            current,
            event,
            status=AggregateStatus.EXIT_REJECTED,
            effects=(
                ResolveIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="exit_outcome_unknown",
                ),
            ),
        )

    if isinstance(event, ControlledFlattenAccepted):
        _require_status_in(
            current,
            {
                AggregateStatus.CONTROLLED_FLATTEN_PENDING,
                AggregateStatus.CONTROLLED_FLATTEN_OUTCOME_UNKNOWN,
            },
        )
        exchange_order_id = str(event.exchange_order_id or "").strip()
        if not exchange_order_id:
            raise InvalidLifecycleTransition("controlled flatten requires order identity")
        flatten_accept_effects: tuple[KernelEffect, ...] = ()
        if current.status is AggregateStatus.CONTROLLED_FLATTEN_OUTCOME_UNKNOWN:
            flatten_accept_effects = (
                ResolveIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="controlled_flatten_outcome_unknown",
                ),
            )
        return _transition(
            current,
            event,
            status=AggregateStatus.CONTROLLED_FLATTEN_ACCEPTED,
            updates={"exit_exchange_order_id": exchange_order_id},
            effects=flatten_accept_effects,
        )

    if isinstance(event, ControlledFlattenRejected):
        _require_status(current, AggregateStatus.CONTROLLED_FLATTEN_PENDING)
        if not str(event.reason or "").strip():
            raise InvalidLifecycleTransition("controlled flatten rejection requires reason")
        return _transition(
            current,
            event,
            status=AggregateStatus.CONTROLLED_FLATTEN_REJECTED,
            effects=(
                OpenIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="controlled_flatten_rejected",
                ),
            ),
        )

    if isinstance(event, ControlledFlattenOutcomeUnknown):
        _require_status(current, AggregateStatus.CONTROLLED_FLATTEN_PENDING)
        if not str(event.reason or "").strip():
            raise InvalidLifecycleTransition("unknown controlled flatten requires reason")
        return _transition(
            current,
            event,
            status=AggregateStatus.CONTROLLED_FLATTEN_OUTCOME_UNKNOWN,
            effects=(
                OpenIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="controlled_flatten_outcome_unknown",
                ),
            ),
        )

    if isinstance(event, ControlledFlattenAbsenceConfirmed):
        _require_status(current, AggregateStatus.CONTROLLED_FLATTEN_OUTCOME_UNKNOWN)
        if not str(event.command_id or "").strip():
            raise InvalidLifecycleTransition(
                "reconciled controlled flatten absence requires command identity"
            )
        return _transition(
            current,
            event,
            status=AggregateStatus.CONTROLLED_FLATTEN_REJECTED,
            effects=(
                ResolveIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="controlled_flatten_outcome_unknown",
                ),
                OpenIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="controlled_flatten_absent",
                ),
            ),
        )

    if isinstance(event, PositionFlatConfirmed):
        _require_status_in(
            current,
            {
                AggregateStatus.EXIT_PENDING,
                AggregateStatus.EXIT_ACCEPTED,
                AggregateStatus.EXIT_REJECTED,
                AggregateStatus.EXIT_OUTCOME_UNKNOWN,
                AggregateStatus.CONTROLLED_FLATTEN_PENDING,
                AggregateStatus.CONTROLLED_FLATTEN_ACCEPTED,
                AggregateStatus.CONTROLLED_FLATTEN_REJECTED,
                AggregateStatus.CONTROLLED_FLATTEN_OUTCOME_UNKNOWN,
            },
        )
        updates: dict[str, object] = {"position_qty": Decimal("0")}
        flat_effects: list[KernelEffect] = []
        if current.initial_stop_exchange_order_id is not None:
            updates["pending_cancel_exchange_order_id"] = (
                current.initial_stop_exchange_order_id
            )
            flat_effects.append(
                CancelProtectionOrders(
                    ticket_id=current.identity.ticket_id,
                    exchange_order_id=current.initial_stop_exchange_order_id,
                )
            )
        if current.entry_lane_held:
            updates["entry_lane_held"] = False
            flat_effects.append(
                ReleaseEntryLane(ticket_id=current.identity.ticket_id)
            )
        return _transition(
            current,
            event,
            status=AggregateStatus.RECONCILIATION_PENDING,
            updates=updates,
            effects=tuple(flat_effects),
        )

    if isinstance(event, ExternalFlatDetected):
        _require_status(current, AggregateStatus.POSITION_PROTECTED)
        if current.initial_stop_exchange_order_id is None:
            raise InvalidLifecycleTransition("external flat has no owned protection identity")
        return _transition(
            current,
            event,
            status=AggregateStatus.RECONCILIATION_PENDING,
            updates={
                "position_qty": Decimal("0"),
                "pending_cancel_exchange_order_id": (
                    current.initial_stop_exchange_order_id
                ),
            },
            effects=(
                OpenIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="external_flat",
                ),
                CancelProtectionOrders(
                    ticket_id=current.identity.ticket_id,
                    exchange_order_id=current.initial_stop_exchange_order_id,
                ),
            ),
        )

    if isinstance(event, OwnedOrphanOrderDetected):
        _require_status_in(
            current,
            {AggregateStatus.RECONCILIATION_PENDING, AggregateStatus.CANCEL_REJECTED},
        )
        exchange_order_id = str(event.exchange_order_id or "").strip()
        if not exchange_order_id:
            raise InvalidLifecycleTransition("owned orphan order identity is required")
        return _transition(
            current,
            event,
            status=AggregateStatus.RECONCILIATION_PENDING,
            updates={"pending_cancel_exchange_order_id": exchange_order_id},
            effects=(
                CancelProtectionOrders(
                    ticket_id=current.identity.ticket_id,
                    exchange_order_id=exchange_order_id,
                ),
            ),
        )

    if isinstance(event, UnownedOrderDetected):
        _require_status(current, AggregateStatus.RECONCILIATION_PENDING)
        if not str(event.exchange_order_id or "").strip():
            raise InvalidLifecycleTransition("unowned order identity is required")
        return _transition(
            current,
            event,
            status=AggregateStatus.RECONCILIATION_PENDING,
            effects=(
                OpenIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="unowned_open_order",
                ),
            ),
        )

    if isinstance(event, ProtectionCancelConfirmed):
        _require_status(current, AggregateStatus.RECONCILIATION_PENDING)
        if event.exchange_order_id != current.initial_stop_exchange_order_id:
            raise InvalidLifecycleTransition("cancelled protection identity mismatch")
        if event.exchange_order_id != current.pending_cancel_exchange_order_id:
            raise InvalidLifecycleTransition("pending cancel identity mismatch")
        return _transition(
            current,
            event,
            status=AggregateStatus.RECONCILIATION_PENDING,
            updates={
                "protected_qty": Decimal("0"),
                "initial_stop_exchange_order_id": None,
                "pending_cancel_exchange_order_id": None,
            },
        )

    if isinstance(event, OwnedOrphanCancelConfirmed):
        _require_status(current, AggregateStatus.RECONCILIATION_PENDING)
        if not str(event.exchange_order_id or "").strip():
            raise InvalidLifecycleTransition("owned orphan cancel identity is required")
        if event.exchange_order_id != current.pending_cancel_exchange_order_id:
            raise InvalidLifecycleTransition("pending orphan cancel identity mismatch")
        return _transition(
            current,
            event,
            status=AggregateStatus.RECONCILIATION_PENDING,
            updates={"pending_cancel_exchange_order_id": None},
        )

    if isinstance(event, CancelOrderRejected):
        _require_status(current, AggregateStatus.RECONCILIATION_PENDING)
        if event.exchange_order_id != current.pending_cancel_exchange_order_id:
            raise InvalidLifecycleTransition("rejected cancel identity mismatch")
        if not str(event.reason or "").strip():
            raise InvalidLifecycleTransition("cancel rejection requires reason")
        return _transition(
            current,
            event,
            status=AggregateStatus.CANCEL_REJECTED,
            effects=(
                OpenIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="cancel_order_rejected",
                ),
            ),
        )

    if isinstance(event, CancelOrderOutcomeUnknown):
        _require_status(current, AggregateStatus.RECONCILIATION_PENDING)
        if event.exchange_order_id != current.pending_cancel_exchange_order_id:
            raise InvalidLifecycleTransition("unknown cancel identity mismatch")
        if not str(event.reason or "").strip():
            raise InvalidLifecycleTransition("unknown cancel outcome requires reason")
        return _transition(
            current,
            event,
            status=AggregateStatus.CANCEL_OUTCOME_UNKNOWN,
            effects=(
                OpenIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="cancel_order_outcome_unknown",
                ),
            ),
        )

    if isinstance(event, CancelOrderAbsenceConfirmed):
        _require_status_in(
            current,
            {
                AggregateStatus.CANCEL_REJECTED,
                AggregateStatus.CANCEL_OUTCOME_UNKNOWN,
            },
        )
        if event.exchange_order_id != current.pending_cancel_exchange_order_id:
            raise InvalidLifecycleTransition("absent cancel identity mismatch")
        absence_updates: dict[str, object] = {
            "pending_cancel_exchange_order_id": None,
        }
        if event.exchange_order_id == current.initial_stop_exchange_order_id:
            absence_updates.update(
                {
                    "protected_qty": Decimal("0"),
                    "initial_stop_exchange_order_id": None,
                }
            )
        absence_effects: tuple[KernelEffect, ...] = ()
        if current.status is AggregateStatus.CANCEL_OUTCOME_UNKNOWN:
            absence_effects = (
                MarkCancelCommandReconciledAbsent(
                    ticket_id=current.identity.ticket_id,
                    exchange_order_id=event.exchange_order_id,
                ),
                ResolveIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="cancel_order_outcome_unknown",
                ),
            )
        return _transition(
            current,
            event,
            status=AggregateStatus.RECONCILIATION_PENDING,
            updates=absence_updates,
            effects=absence_effects,
        )

    if isinstance(event, ReconciliationMatched):
        _require_status(current, AggregateStatus.RECONCILIATION_PENDING)
        if current.initial_stop_exchange_order_id is not None:
            raise InvalidLifecycleTransition("protection residue remains")
        if current.protected_qty != 0:
            raise InvalidLifecycleTransition("protected quantity remains")
        if current.pending_cancel_exchange_order_id is not None:
            raise InvalidLifecycleTransition("cancel outcome remains unresolved")
        return _transition(
            current,
            event,
            status=AggregateStatus.SETTLEMENT_PENDING,
            effects=(SettleBudget(ticket_id=current.identity.ticket_id),),
        )

    if isinstance(event, BudgetSettled):
        _require_status(current, AggregateStatus.SETTLEMENT_PENDING)
        return _transition(
            current,
            event,
            status=AggregateStatus.REVIEW_PENDING,
        )

    if isinstance(event, ReviewRecorded):
        _require_status(current, AggregateStatus.REVIEW_PENDING)
        review_id = str(event.review_id or "").strip()
        if not review_id:
            raise InvalidLifecycleTransition("review identity is required")
        return _transition(
            current,
            event,
            status=AggregateStatus.TERMINAL,
            updates={"review_id": review_id},
        )

    raise InvalidLifecycleTransition(f"unsupported event: {type(event).__name__}")


def _issue_ticket(event: TradeEvent) -> Reduction:
    if not isinstance(event, TicketIssued):
        raise InvalidLifecycleTransition("first event must issue a Ticket")
    if event.sequence != 1:
        raise InvalidLifecycleTransition("first event sequence must be one")
    aggregate = TradeAggregate(
        identity=event.ticket.identity,
        ticket=event.ticket,
        status=AggregateStatus.ENTRY_PENDING,
        version=1,
        last_event_sequence=event.sequence,
    )
    return Reduction(
        aggregate=aggregate,
        effects=(PrepareEntryCommand(ticket=event.ticket),),
    )


def _require_event_identity_and_sequence(
    current: TradeAggregate,
    event: TradeEvent,
) -> None:
    if isinstance(event, TicketIssued):
        raise InvalidLifecycleTransition("Ticket cannot be issued twice")
    if event.ticket_id != current.identity.ticket_id:
        raise InvalidLifecycleTransition("event Ticket identity mismatch")
    if event.sequence != current.last_event_sequence + 1:
        raise InvalidLifecycleTransition("event sequence is not monotonic")


def _require_status(current: TradeAggregate, expected: AggregateStatus) -> None:
    if current.status is not expected:
        raise InvalidLifecycleTransition(
            f"event requires {expected.value}, current is {current.status.value}"
        )


def _require_status_in(
    current: TradeAggregate,
    expected: set[AggregateStatus],
) -> None:
    if current.status not in expected:
        allowed = ", ".join(sorted(status.value for status in expected))
        raise InvalidLifecycleTransition(
            f"event requires one of {allowed}, current is {current.status.value}"
        )


def _transition(
    current: TradeAggregate,
    event: TradeEvent,
    *,
    status: AggregateStatus,
    updates: dict[str, object] | None = None,
    effects: tuple[KernelEffect, ...] = (),
) -> Reduction:
    aggregate = current.model_copy(
        update={
            "status": status,
            "version": current.version + 1,
            "last_event_sequence": event.sequence,
            **(updates or {}),
        }
    )
    return Reduction(aggregate=aggregate, effects=effects)
