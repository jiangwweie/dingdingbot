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
    PrepareSetLeverageCommand,
    PrepareControlledFlattenCommand,
    PrepareExitCommand,
    PrepareInitialStopCommand,
    PrepareProtectionReplacementCommand,
    PrepareTakeProfitCommand,
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
    LeverageConfirmed,
    LeverageOutcomeUnknown,
    LeverageRejected,
    OwnedOrphanOrderDetected,
    OwnedOrderAbsenceConfirmed,
    OwnedOrphanCancelConfirmed,
    PositionFlatConfirmed,
    ProtectionCancelConfirmed,
    ProtectionCancelAbsenceConfirmed,
    ProtectionCancelOutcomeUnknown,
    ProtectionCancelRejected,
    ProtectionReplacementAbsenceConfirmed,
    ProtectionReplacementConfirmed,
    ProtectionReplacementOutcomeUnknown,
    ProtectionReplacementRejected,
    ReconciliationMatched,
    ReviewRecorded,
    RunnerStopRequested,
    TakeProfitConfirmed,
    TakeProfitAbsenceConfirmed,
    TakeProfitFilled,
    TakeProfitOutcomeUnknown,
    TakeProfitRejected,
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

    if isinstance(event, LeverageConfirmed):
        _require_status_in(
            current,
            {
                AggregateStatus.LEVERAGE_PENDING,
                AggregateStatus.LEVERAGE_OUTCOME_UNKNOWN,
            },
        )
        if event.exchange_configured_leverage != current.ticket.selected_leverage:
            raise InvalidLifecycleTransition(
                "confirmed leverage differs from immutable Ticket"
            )
        if event.leverage_verified_at_ms <= 0:
            raise InvalidLifecycleTransition("leverage confirmation time must be positive")
        if not str(event.leverage_verification_digest or "").startswith("sha256:"):
            raise InvalidLifecycleTransition("leverage confirmation requires a digest")
        effects: list[KernelEffect] = [
            PrepareEntryCommand(
                ticket=current.ticket,
                leverage_verification_digest=event.leverage_verification_digest,
            ),
        ]
        if current.status is AggregateStatus.LEVERAGE_OUTCOME_UNKNOWN:
            effects.insert(
                0,
                ResolveIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="leverage_outcome_unknown",
                ),
            )
        return _transition(
            current,
            event,
            status=AggregateStatus.LEVERAGE_CONFIRMED,
            effects=tuple(effects),
        )

    if isinstance(event, LeverageRejected):
        _require_status_in(
            current,
            {
                AggregateStatus.LEVERAGE_PENDING,
                AggregateStatus.LEVERAGE_OUTCOME_UNKNOWN,
            },
        )
        if not str(event.reason or "").strip():
            raise InvalidLifecycleTransition("leverage rejection requires reason")
        effects: list[KernelEffect] = []
        if current.status is AggregateStatus.LEVERAGE_OUTCOME_UNKNOWN:
            effects.append(
                ResolveIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="leverage_outcome_unknown",
                )
            )
        effects.extend(
            (
                ReleaseBudget(ticket_id=current.identity.ticket_id),
                ReleaseEntryLane(ticket_id=current.identity.ticket_id),
            )
        )
        return _transition(
            current,
            event,
            status=AggregateStatus.LEVERAGE_REJECTED,
            updates={"entry_lane_held": False},
            effects=tuple(effects),
        )

    if isinstance(event, LeverageOutcomeUnknown):
        _require_status(current, AggregateStatus.LEVERAGE_PENDING)
        if not str(event.reason or "").strip():
            raise InvalidLifecycleTransition("unknown leverage outcome requires reason")
        return _transition(
            current,
            event,
            status=AggregateStatus.LEVERAGE_OUTCOME_UNKNOWN,
            effects=(
                OpenIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="leverage_outcome_unknown",
                ),
            ),
        )

    if isinstance(event, EntryAccepted):
        _require_status_in(
            current,
            {
                AggregateStatus.ENTRY_PENDING,
                AggregateStatus.LEVERAGE_CONFIRMED,
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
        _require_status_in(
            current,
            {AggregateStatus.ENTRY_PENDING, AggregateStatus.LEVERAGE_CONFIRMED},
        )
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
        _require_status_in(
            current,
            {AggregateStatus.ENTRY_PENDING, AggregateStatus.LEVERAGE_CONFIRMED},
        )
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
            {
                AggregateStatus.ENTRY_PENDING,
                AggregateStatus.LEVERAGE_CONFIRMED,
                AggregateStatus.ENTRY_ACCEPTED,
            },
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
            {
                AggregateStatus.ENTRY_PENDING,
                AggregateStatus.LEVERAGE_CONFIRMED,
                AggregateStatus.ENTRY_ACCEPTED,
            },
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
        tp_prices = current.ticket.take_profit_prices
        tp_quantities = current.ticket.take_profit_quantities
        if len(tp_prices) != 1 or len(tp_quantities) != 1:
            raise InvalidLifecycleTransition(
                "registered exit policy requires exactly one TP1 leg"
            )
        tp1_quantity = tp_quantities[0]
        if tp1_quantity >= current.position_qty:
            raise InvalidLifecycleTransition("TP1 must preserve a runner quantity")
        initial_stop_effects.extend(
            (
                ReleaseEntryLane(ticket_id=current.identity.ticket_id),
                PrepareTakeProfitCommand(
                    ticket_id=current.identity.ticket_id,
                    quantity=tp1_quantity,
                    limit_price=tp_prices[0],
                ),
            )
        )
        return _transition(
            current,
            event,
            status=AggregateStatus.TP1_PENDING,
            updates={
                "entry_lane_held": False,
                "protected_qty": event.protected_qty,
                "initial_stop_exchange_order_id": event.exchange_order_id.strip(),
                "active_stop_exchange_order_id": event.exchange_order_id.strip(),
                "active_stop_price": current.ticket.initial_stop_price,
                "tp1_target_qty": tp1_quantity,
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

    if isinstance(event, TakeProfitConfirmed):
        _require_status_in(
            current,
            {
                AggregateStatus.TP1_PENDING,
                AggregateStatus.TP1_OUTCOME_UNKNOWN,
            },
        )
        exchange_order_id = str(event.exchange_order_id or "").strip()
        if not exchange_order_id:
            raise InvalidLifecycleTransition("TP1 acceptance requires order identity")
        if event.target_qty != current.tp1_target_qty:
            raise InvalidLifecycleTransition("TP1 accepted quantity differs from Ticket")
        tp1_confirm_effects: tuple[KernelEffect, ...] = ()
        if current.status is AggregateStatus.TP1_OUTCOME_UNKNOWN:
            tp1_confirm_effects = (
                ResolveIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="take_profit_outcome_unknown",
                ),
            )
        return _transition(
            current,
            event,
            status=AggregateStatus.POSITION_PROTECTED,
            updates={"tp1_exchange_order_id": exchange_order_id},
            effects=tp1_confirm_effects,
        )

    if isinstance(event, TakeProfitRejected):
        _require_status(current, AggregateStatus.TP1_PENDING)
        if not str(event.reason or "").strip():
            raise InvalidLifecycleTransition("TP1 rejection requires reason")
        return _transition(
            current,
            event,
            status=AggregateStatus.TP1_REJECTED,
            effects=(
                OpenIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="take_profit_rejected",
                ),
            ),
        )

    if isinstance(event, TakeProfitOutcomeUnknown):
        _require_status(current, AggregateStatus.TP1_PENDING)
        if not str(event.reason or "").strip():
            raise InvalidLifecycleTransition("TP1 unknown outcome requires reason")
        return _transition(
            current,
            event,
            status=AggregateStatus.TP1_OUTCOME_UNKNOWN,
            effects=(
                OpenIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="take_profit_outcome_unknown",
                ),
            ),
        )

    if isinstance(event, TakeProfitAbsenceConfirmed):
        _require_status(current, AggregateStatus.TP1_OUTCOME_UNKNOWN)
        if not str(event.command_id or "").strip():
            raise InvalidLifecycleTransition(
                "reconciled TP1 absence requires command identity"
            )
        if len(current.ticket.take_profit_prices) != 1:
            raise InvalidLifecycleTransition("TP1 retry requires one frozen price")
        return _transition(
            current,
            event,
            status=AggregateStatus.TP1_PENDING,
            effects=(
                ResolveIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="take_profit_outcome_unknown",
                ),
                PrepareTakeProfitCommand(
                    ticket_id=current.identity.ticket_id,
                    quantity=current.tp1_target_qty,
                    limit_price=current.ticket.take_profit_prices[0],
                ),
            ),
        )

    if isinstance(event, TakeProfitFilled):
        _require_status(current, AggregateStatus.POSITION_PROTECTED)
        if event.filled_qty != current.tp1_target_qty:
            raise InvalidLifecycleTransition("TP1 fill must equal the frozen target")
        if event.average_fill_price <= 0 or event.runner_floor_price <= 0:
            raise InvalidLifecycleTransition("TP1 fill and runner floor must be positive")
        if current.active_stop_exchange_order_id is None:
            raise InvalidLifecycleTransition("TP1 fill has no active stop to replace")
        runner_qty = current.position_qty - event.filled_qty
        if runner_qty <= 0:
            raise InvalidLifecycleTransition("TP1 fill must preserve runner exposure")
        return _transition(
            current,
            event,
            status=AggregateStatus.RUNNER_REPLACEMENT_PENDING,
            updates={
                "position_qty": runner_qty,
                "tp1_filled_qty": event.filled_qty,
                "tp1_exchange_order_id": None,
                "break_even_floor_price": event.runner_floor_price,
                "pending_stop_price": event.runner_floor_price,
                "pending_stop_watermark_ms": event.occurred_at_ms,
            },
            effects=(
                PrepareProtectionReplacementCommand(
                    ticket_id=current.identity.ticket_id,
                    quantity=runner_qty,
                    stop_price=event.runner_floor_price,
                    replaces_exchange_order_id=(
                        current.active_stop_exchange_order_id
                    ),
                    source_watermark_ms=event.occurred_at_ms,
                ),
            ),
        )

    if isinstance(event, RunnerStopRequested):
        _require_status(current, AggregateStatus.RUNNER_PROTECTED)
        if current.active_stop_exchange_order_id is None:
            raise InvalidLifecycleTransition("runner move requires active stop identity")
        if current.active_stop_price is None:
            raise InvalidLifecycleTransition("runner move requires active stop price")
        if event.stop_price <= 0 or event.source_watermark_ms <= 0:
            raise InvalidLifecycleTransition("runner move requires price and watermark")
        if current.identity.netting_domain.position_side == "long":
            improved = event.stop_price > current.active_stop_price
        else:
            improved = event.stop_price < current.active_stop_price
        if not improved:
            raise InvalidLifecycleTransition("runner stop must improve monotonically")
        return _transition(
            current,
            event,
            status=AggregateStatus.RUNNER_REPLACEMENT_PENDING,
            updates={
                "pending_stop_price": event.stop_price,
                "pending_stop_watermark_ms": event.source_watermark_ms,
            },
            effects=(
                PrepareProtectionReplacementCommand(
                    ticket_id=current.identity.ticket_id,
                    quantity=current.position_qty,
                    stop_price=event.stop_price,
                    replaces_exchange_order_id=(
                        current.active_stop_exchange_order_id
                    ),
                    source_watermark_ms=event.source_watermark_ms,
                ),
            ),
        )

    if isinstance(event, ProtectionReplacementConfirmed):
        _require_status_in(
            current,
            {
                AggregateStatus.RUNNER_REPLACEMENT_PENDING,
                AggregateStatus.RUNNER_REPLACEMENT_OUTCOME_UNKNOWN,
            },
        )
        exchange_order_id = str(event.exchange_order_id or "").strip()
        if not exchange_order_id:
            raise InvalidLifecycleTransition(
                "protection replacement requires order identity"
            )
        if event.protected_qty != current.position_qty:
            raise InvalidLifecycleTransition(
                "protection replacement must cover exact runner quantity"
            )
        if event.replaces_exchange_order_id != current.active_stop_exchange_order_id:
            raise InvalidLifecycleTransition("replaced stop identity mismatch")
        if (
            event.stop_price != current.pending_stop_price
            or event.source_watermark_ms != current.pending_stop_watermark_ms
        ):
            raise InvalidLifecycleTransition("replacement terms differ from request")
        replacement_confirm_effects: list[KernelEffect] = []
        if current.status is AggregateStatus.RUNNER_REPLACEMENT_OUTCOME_UNKNOWN:
            replacement_confirm_effects.append(
                ResolveIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="protection_replacement_outcome_unknown",
                )
            )
        replacement_confirm_effects.append(
            CancelProtectionOrders(
                ticket_id=current.identity.ticket_id,
                exchange_order_id=event.replaces_exchange_order_id,
            )
        )
        return _transition(
            current,
            event,
            status=AggregateStatus.RUNNER_OLD_STOP_CANCEL_PENDING,
            updates={
                "protected_qty": event.protected_qty,
                "active_stop_exchange_order_id": exchange_order_id,
                "active_stop_price": event.stop_price,
                "pending_replaced_stop_exchange_order_id": (
                    event.replaces_exchange_order_id
                ),
                "pending_stop_price": None,
                "pending_stop_watermark_ms": None,
                "runner_stop_watermark_ms": event.source_watermark_ms,
            },
            effects=tuple(replacement_confirm_effects),
        )

    if isinstance(event, ProtectionReplacementRejected):
        _require_status(current, AggregateStatus.RUNNER_REPLACEMENT_PENDING)
        if not str(event.reason or "").strip():
            raise InvalidLifecycleTransition(
                "protection replacement rejection requires reason"
            )
        return _transition(
            current,
            event,
            status=AggregateStatus.RUNNER_REPLACEMENT_REJECTED,
            effects=(
                OpenIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="protection_replacement_rejected",
                ),
            ),
        )

    if isinstance(event, ProtectionReplacementOutcomeUnknown):
        _require_status(current, AggregateStatus.RUNNER_REPLACEMENT_PENDING)
        if not str(event.reason or "").strip():
            raise InvalidLifecycleTransition(
                "protection replacement unknown outcome requires reason"
            )
        return _transition(
            current,
            event,
            status=AggregateStatus.RUNNER_REPLACEMENT_OUTCOME_UNKNOWN,
            effects=(
                OpenIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="protection_replacement_outcome_unknown",
                ),
            ),
        )

    if isinstance(event, ProtectionReplacementAbsenceConfirmed):
        _require_status(
            current,
            AggregateStatus.RUNNER_REPLACEMENT_OUTCOME_UNKNOWN,
        )
        if not str(event.command_id or "").strip():
            raise InvalidLifecycleTransition(
                "reconciled replacement absence requires command identity"
            )
        if (
            current.active_stop_exchange_order_id is None
            or current.pending_stop_price is None
            or current.pending_stop_watermark_ms is None
        ):
            raise InvalidLifecycleTransition(
                "replacement retry requires exact pending terms"
            )
        return _transition(
            current,
            event,
            status=AggregateStatus.RUNNER_REPLACEMENT_PENDING,
            effects=(
                ResolveIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="protection_replacement_outcome_unknown",
                ),
                PrepareProtectionReplacementCommand(
                    ticket_id=current.identity.ticket_id,
                    quantity=current.position_qty,
                    stop_price=current.pending_stop_price,
                    replaces_exchange_order_id=(
                        current.active_stop_exchange_order_id
                    ),
                    source_watermark_ms=current.pending_stop_watermark_ms,
                ),
            ),
        )

    if isinstance(event, ExitRequested):
        _require_status_in(
            current,
            {
                AggregateStatus.POSITION_PROTECTED,
                AggregateStatus.RUNNER_PROTECTED,
                AggregateStatus.EXIT_REJECTED,
            },
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
        cleanup_order_id = _next_cleanup_order_id(current)
        if cleanup_order_id is not None:
            updates["pending_cancel_exchange_order_id"] = cleanup_order_id
            flat_effects.append(
                CancelProtectionOrders(
                    ticket_id=current.identity.ticket_id,
                    exchange_order_id=cleanup_order_id,
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
        _require_status_in(
            current,
            {
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
            },
        )
        cleanup_order_id = _next_cleanup_order_id(current)
        if cleanup_order_id is None:
            raise InvalidLifecycleTransition("external flat has no owned order identity")
        return _transition(
            current,
            event,
            status=AggregateStatus.RECONCILIATION_PENDING,
            updates={
                "position_qty": Decimal("0"),
                "pending_cancel_exchange_order_id": cleanup_order_id,
            },
            effects=(
                OpenIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="external_flat",
                ),
                CancelProtectionOrders(
                    ticket_id=current.identity.ticket_id,
                    exchange_order_id=cleanup_order_id,
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

    if isinstance(event, OwnedOrderAbsenceConfirmed):
        _require_status(current, AggregateStatus.RECONCILIATION_PENDING)
        if not str(event.exchange_order_id or "").strip():
            raise InvalidLifecycleTransition("owned order absence requires identity")
        if event.exchange_order_id not in _known_cleanup_order_ids(current):
            raise InvalidLifecycleTransition("absent order is not owned by Ticket")
        return _transition(
            current,
            event,
            status=AggregateStatus.RECONCILIATION_PENDING,
            updates=_clear_cleanup_order(current, event.exchange_order_id),
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
        if current.status is AggregateStatus.RUNNER_OLD_STOP_CANCEL_PENDING:
            if event.exchange_order_id != current.pending_replaced_stop_exchange_order_id:
                raise InvalidLifecycleTransition(
                    "runner replaced-stop cancel identity mismatch"
                )
            runner_cancel_updates: dict[str, object] = {
                "pending_replaced_stop_exchange_order_id": None,
            }
            if event.exchange_order_id == current.initial_stop_exchange_order_id:
                runner_cancel_updates["initial_stop_exchange_order_id"] = None
            return _transition(
                current,
                event,
                status=AggregateStatus.RUNNER_PROTECTED,
                updates=runner_cancel_updates,
            )
        _require_status(current, AggregateStatus.RECONCILIATION_PENDING)
        if event.exchange_order_id != current.pending_cancel_exchange_order_id:
            raise InvalidLifecycleTransition("pending cancel identity mismatch")
        if event.exchange_order_id not in _known_cleanup_order_ids(current):
            raise InvalidLifecycleTransition("cancelled order is not owned by Ticket")
        return _transition(
            current,
            event,
            status=AggregateStatus.RECONCILIATION_PENDING,
            updates=_clear_cleanup_order(current, event.exchange_order_id),
        )

    if isinstance(event, ProtectionCancelRejected):
        _require_status(current, AggregateStatus.RUNNER_OLD_STOP_CANCEL_PENDING)
        if event.exchange_order_id != current.pending_replaced_stop_exchange_order_id:
            raise InvalidLifecycleTransition("rejected replaced-stop identity mismatch")
        if not str(event.reason or "").strip():
            raise InvalidLifecycleTransition("replaced-stop rejection requires reason")
        return _transition(
            current,
            event,
            status=AggregateStatus.RUNNER_OLD_STOP_CANCEL_REJECTED,
            effects=(
                OpenIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="runner_old_stop_cancel_rejected",
                ),
            ),
        )

    if isinstance(event, ProtectionCancelOutcomeUnknown):
        _require_status(current, AggregateStatus.RUNNER_OLD_STOP_CANCEL_PENDING)
        if event.exchange_order_id != current.pending_replaced_stop_exchange_order_id:
            raise InvalidLifecycleTransition("unknown replaced-stop identity mismatch")
        if not str(event.reason or "").strip():
            raise InvalidLifecycleTransition("unknown replaced-stop cancel requires reason")
        return _transition(
            current,
            event,
            status=AggregateStatus.RUNNER_OLD_STOP_CANCEL_OUTCOME_UNKNOWN,
            effects=(
                OpenIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="runner_old_stop_cancel_outcome_unknown",
                ),
            ),
        )

    if isinstance(event, ProtectionCancelAbsenceConfirmed):
        _require_status(
            current,
            AggregateStatus.RUNNER_OLD_STOP_CANCEL_OUTCOME_UNKNOWN,
        )
        if event.exchange_order_id != current.pending_replaced_stop_exchange_order_id:
            raise InvalidLifecycleTransition("absent replaced-stop identity mismatch")
        absence_updates: dict[str, object] = {
            "pending_replaced_stop_exchange_order_id": None,
        }
        if event.exchange_order_id == current.initial_stop_exchange_order_id:
            absence_updates["initial_stop_exchange_order_id"] = None
        return _transition(
            current,
            event,
            status=AggregateStatus.RUNNER_PROTECTED,
            updates=absence_updates,
            effects=(
                MarkCancelCommandReconciledAbsent(
                    ticket_id=current.identity.ticket_id,
                    exchange_order_id=event.exchange_order_id,
                ),
                ResolveIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="runner_old_stop_cancel_outcome_unknown",
                ),
            ),
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
            updates=_clear_cleanup_order(current, event.exchange_order_id),
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
        absence_updates = _clear_cleanup_order(current, event.exchange_order_id)
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
        if _known_cleanup_order_ids(current):
            raise InvalidLifecycleTransition("owned order identity residue remains")
        if current.protected_qty != 0:
            raise InvalidLifecycleTransition("protected quantity remains")
        if current.pending_cancel_exchange_order_id is not None:
            raise InvalidLifecycleTransition("cancel outcome remains unresolved")
        matched_effects: list[KernelEffect] = [
            SettleBudget(ticket_id=current.identity.ticket_id)
        ]
        if event.resolved_incident_kind is not None:
            matched_effects.append(
                ResolveIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind=event.resolved_incident_kind,
                )
            )
        return _transition(
            current,
            event,
            status=AggregateStatus.SETTLEMENT_PENDING,
            effects=tuple(matched_effects),
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
    requires_leverage_change = event.ticket.leverage_change_required
    aggregate = TradeAggregate(
        identity=event.ticket.identity,
        ticket=event.ticket,
        status=(
            AggregateStatus.LEVERAGE_PENDING
            if requires_leverage_change
            else AggregateStatus.ENTRY_PENDING
        ),
        version=1,
        last_event_sequence=event.sequence,
    )
    return Reduction(
        aggregate=aggregate,
        effects=(
            (
                PrepareSetLeverageCommand(ticket=event.ticket)
                if requires_leverage_change
                else PrepareEntryCommand(ticket=event.ticket)
            ),
        ),
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


def _known_cleanup_order_ids(current: TradeAggregate) -> tuple[str, ...]:
    identities: list[str] = []
    for identity in (
        current.tp1_exchange_order_id,
        current.active_stop_exchange_order_id,
        current.initial_stop_exchange_order_id,
    ):
        if identity is not None and identity not in identities:
            identities.append(identity)
    return tuple(identities)


def _next_cleanup_order_id(current: TradeAggregate) -> str | None:
    identities = _known_cleanup_order_ids(current)
    return None if not identities else identities[0]


def _clear_cleanup_order(
    current: TradeAggregate,
    exchange_order_id: str,
) -> dict[str, object]:
    updates: dict[str, object] = {"pending_cancel_exchange_order_id": None}
    if exchange_order_id == current.tp1_exchange_order_id:
        updates["tp1_exchange_order_id"] = None
    if exchange_order_id == current.active_stop_exchange_order_id:
        updates["active_stop_exchange_order_id"] = None
        updates["active_stop_price"] = None
        updates["protected_qty"] = Decimal("0")
    if exchange_order_id == current.initial_stop_exchange_order_id:
        updates["initial_stop_exchange_order_id"] = None
    return updates
