from __future__ import annotations

from decimal import Decimal
from typing import Literal

import pytest

from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.cross_margin_stress import (
    AccountRiskPosition,
    AccountRiskSnapshot,
    CrossMarginStressRequest,
    MaintenanceMarginBracket,
    StressPosition,
    evaluate_cross_margin_stress,
)
from src.trading_kernel.domain.effects import (
    CancelEntryRemainder,
    CancelProtectionOrders,
    MarkCancelCommandReconciledAbsent,
    OpenIncident,
    PrepareControlledFlattenCommand,
    PrepareEntryCommand,
    PrepareExitCommand,
    PrepareInitialStopCommand,
    PrepareProtectionReplacementCommand,
    PrepareSetLeverageCommand,
    PrepareTakeProfitCommand,
    ProjectTerminalOwnerState,
    ReleaseBudget,
    ReleaseCapitalAuthorities,
    ReleaseEntryLane,
    RequestControlledFlatten,
    ResolveIncident,
    ResolveTicketIncidentsAtClosure,
)
from src.trading_kernel.domain.events import (
    BudgetSettled,
    CancelOrderAbsenceConfirmed,
    CancelOrderOutcomeUnknown,
    CancelOrderRejected,
    CancelOrderStillOpenConfirmed,
    ControlledFlattenAbsenceConfirmed,
    ControlledFlattenAccepted,
    ControlledFlattenOutcomeUnknown,
    EntryAccepted,
    EntryFilled,
    EntryOutcomeUnknown,
    EntryPartiallyFilled,
    EntryRejected,
    EntryRemainderCancelConfirmed,
    EntryRemainderCancelOutcomeUnknown,
    ExitAbsenceConfirmed,
    ExitAccepted,
    ExitOutcomeUnknown,
    ExitRejected,
    ExitRequested,
    ExternalFlatDetected,
    InitialStopAbsenceConfirmed,
    InitialStopConfirmed,
    InitialStopOutcomeUnknown,
    InitialStopRejected,
    LeverageConfirmed,
    LeverageOutcomeUnknown,
    LeverageRejected,
    OwnedOrphanOrderDetected,
    PositionFlatConfirmed,
    PostFillStressAssessed,
    ProtectionCancelAbsenceConfirmed,
    ProtectionCancelConfirmed,
    ProtectionCancelOutcomeUnknown,
    ProtectionReplacementAbsenceConfirmed,
    ProtectionReplacementConfirmed,
    ProtectionReplacementOutcomeUnknown,
    ReconciliationMatched,
    ReviewRecorded,
    ReviewRevised,
    TakeProfitAbsenceConfirmed,
    TakeProfitConfirmed,
    TakeProfitFilled,
    TakeProfitOutcomeUnknown,
    TicketIssued,
    UnownedOrderDetected,
)
from src.trading_kernel.domain.post_fill_risk import (
    PostFillRiskRequest,
    assess_post_fill_risk,
)
from src.trading_kernel.domain.reducer import InvalidLifecycleTransition, reduce_event
from tests.trading_kernel.unit.test_ticket import _ticket


def _normal_post_fill_risk(ticket, average_fill_price: Decimal):
    return assess_post_fill_risk(
        PostFillRiskRequest(
            position_side=ticket.identity.netting_domain.position_side,
            filled_quantity=ticket.quantity,
            average_fill_price=average_fill_price,
            initial_stop_price=ticket.initial_stop_price,
            planned_stop_risk_budget=ticket.planned_stop_risk_budget,
            post_fill_stop_risk_limit=ticket.post_fill_stop_risk_limit,
        )
    )


def _post_fill_stress_event(aggregate, *, passed: bool = True):
    ticket = aggregate.ticket
    assert aggregate.average_fill_price is not None
    assert aggregate.initial_stop_exchange_order_id is not None
    account = AccountRiskSnapshot.create(
        venue_id=ticket.identity.netting_domain.venue_id,
        account_id=ticket.identity.netting_domain.account_id,
        account_risk_mode="standard_usdm_single_asset",
        settlement_asset="USDT",
        position_mode="independent_sides",
        margin_mode="cross",
        exchange_instrument_id=(
            ticket.identity.netting_domain.exchange_instrument_id
        ),
        mark_price=aggregate.average_fill_price,
        configured_leverage=ticket.selected_leverage,
        total_wallet_balance=Decimal(100 if passed else 0),
        total_margin_balance=Decimal(100 if passed else 0),
        total_initial_margin=Decimal(0),
        total_maintenance_margin=Decimal(0),
        available_margin=Decimal(100 if passed else 0),
        account_positions=(
            AccountRiskPosition(
                exchange_instrument_id=(
                    ticket.identity.netting_domain.exchange_instrument_id
                ),
                position_side=ticket.identity.netting_domain.position_side,
                quantity=aggregate.position_qty,
                average_entry_price=aggregate.average_fill_price,
                current_unrealized_pnl=Decimal(0),
                current_maintenance_margin=Decimal(0),
            ),
        ),
        observed_at_ms=1_250,
        valid_until_ms=2_250,
    )
    evidence = evaluate_cross_margin_stress(
        CrossMarginStressRequest(
            account_snapshot=account,
            maintenance_margin_brackets=(
                MaintenanceMarginBracket(
                    bracket_id="test:1",
                    notional_floor=Decimal(0),
                    notional_cap=None,
                    maintenance_margin_rate=Decimal("0.004"),
                    maintenance_amount=Decimal(0),
                ),
            ),
            maintenance_margin_brackets_digest="sha256:" + "5" * 64,
            notional_coefficient=Decimal(1),
            notional_coefficient_certified=True,
            evaluated_side=ticket.identity.netting_domain.position_side,
            reference_entry_price=aggregate.average_fill_price,
            initial_stop_price=ticket.initial_stop_price,
            post_stop_stress_multiple=ticket.post_stop_stress_multiple,
            projected_instrument_positions=(
                StressPosition(
                    position_side=(
                        ticket.identity.netting_domain.position_side
                    ),
                    quantity=aggregate.position_qty,
                    average_entry_price=aggregate.average_fill_price,
                ),
            ),
        )
    )
    expected_status: Literal["passed", "failed"] = "passed" if passed else "failed"
    assert evidence.proof.status.value == expected_status
    return PostFillStressAssessed(
        event_id=f"event-stress-{aggregate.last_event_sequence + 1}",
        ticket_id=ticket.identity.ticket_id,
        sequence=aggregate.last_event_sequence + 1,
        occurred_at_ms=1_250,
        status=expected_status,
        evidence=evidence,
        owner_policy_id=ticket.owner_policy_id,
        owner_policy_version=ticket.owner_policy_version,
        filled_qty=aggregate.position_qty,
        average_fill_price=aggregate.average_fill_price,
        initial_stop_price=ticket.initial_stop_price,
        initial_stop_exchange_order_id=(
            aggregate.initial_stop_exchange_order_id
        ),
    )


def test_ticket_issue_prepares_only_set_leverage_when_change_is_required() -> None:
    ticket = _ticket(leverage_change_required=True)

    reduction = reduce_event(
        None,
        TicketIssued(
            event_id="event-1",
            ticket=ticket,
            sequence=1,
            occurred_at_ms=1_001,
        ),
    )

    assert reduction.aggregate.status is AggregateStatus.LEVERAGE_PENDING
    assert reduction.aggregate.version == 1
    assert reduction.effects == (PrepareSetLeverageCommand(ticket=ticket),)


def test_ticket_issue_prepares_entry_when_leverage_already_matches() -> None:
    ticket = _ticket(leverage_change_required=False)

    reduction = reduce_event(
        None,
        TicketIssued(
            event_id="event-1",
            ticket=ticket,
            sequence=1,
            occurred_at_ms=1_001,
        ),
    )

    assert reduction.aggregate.status is AggregateStatus.ENTRY_PENDING
    assert reduction.effects == (PrepareEntryCommand(ticket=ticket),)


def test_leverage_terminal_and_unknown_states_are_explicit() -> None:
    issued = reduce_event(
        None,
        TicketIssued(
            event_id="event-1",
            ticket=_ticket(leverage_change_required=True),
            sequence=1,
            occurred_at_ms=1_001,
        ),
    ).aggregate

    confirmed = reduce_event(
        issued,
        LeverageConfirmed(
            event_id="event-2",
            ticket_id=issued.identity.ticket_id,
            sequence=2,
            occurred_at_ms=1_002,
            exchange_configured_leverage=issued.ticket.selected_leverage,
            leverage_verified_at_ms=1_002,
            leverage_verification_digest="sha256:" + "3" * 64,
        ),
    )
    assert confirmed.aggregate.status is AggregateStatus.LEVERAGE_CONFIRMED
    assert confirmed.effects == (
        PrepareEntryCommand(
            ticket=issued.ticket,
            leverage_verification_digest="sha256:" + "3" * 64,
        ),
    )

    rejected = reduce_event(
        issued,
        LeverageRejected(
            event_id="event-3",
            ticket_id=issued.identity.ticket_id,
            sequence=2,
            occurred_at_ms=1_003,
            reason="venue_rejected",
        ),
    )
    assert rejected.aggregate.status is AggregateStatus.LEVERAGE_REJECTED
    assert rejected.aggregate.entry_lane_held is False
    assert rejected.effects == (
        ReleaseBudget(ticket_id=issued.identity.ticket_id),
        ReleaseEntryLane(ticket_id=issued.identity.ticket_id),
        ProjectTerminalOwnerState(ticket_id=issued.identity.ticket_id),
    )

    unknown = reduce_event(
        issued,
        LeverageOutcomeUnknown(
            event_id="event-4",
            ticket_id=issued.identity.ticket_id,
            sequence=2,
            occurred_at_ms=1_004,
            reason="timeout",
        ),
    )
    assert unknown.aggregate.status is AggregateStatus.LEVERAGE_OUTCOME_UNKNOWN
    assert unknown.effects == (
        OpenIncident(
            ticket_id=issued.identity.ticket_id,
            incident_kind="leverage_outcome_unknown",
        ),
    )


def test_authoritative_entry_rejection_is_terminal_and_never_retries() -> None:
    issued = reduce_event(
        None,
        TicketIssued(
            event_id="event-1",
            ticket=_ticket(),
            sequence=1,
            occurred_at_ms=1_001,
        ),
    ).aggregate

    rejected = reduce_event(
        issued,
        EntryRejected(
            event_id="event-2",
            ticket_id=issued.identity.ticket_id,
            sequence=2,
            occurred_at_ms=1_100,
            reason="venue_rejected",
        ),
    )

    assert rejected.aggregate.status is AggregateStatus.ENTRY_REJECTED
    assert rejected.effects == (
        ReleaseBudget(ticket_id=issued.identity.ticket_id),
        ReleaseEntryLane(ticket_id=issued.identity.ticket_id),
        ProjectTerminalOwnerState(ticket_id=issued.identity.ticket_id),
    )

    with pytest.raises(InvalidLifecycleTransition):
        reduce_event(
            rejected.aggregate,
            EntryFilled(
                event_id="event-3",
                ticket_id=issued.identity.ticket_id,
                sequence=3,
                occurred_at_ms=1_200,
                filled_qty=Decimal("0.001"),
                average_fill_price=Decimal(60000),
                venue_reported_liquidation_price=None,
                position_observed_at_ms=1_100,
                post_fill_risk=_normal_post_fill_risk(
                    issued.ticket, Decimal(60000)
                ),
            ),
        )


def test_entry_acceptance_is_conserved_before_fill() -> None:
    issued = reduce_event(
        None,
        TicketIssued(
            event_id="event-1",
            ticket=_ticket(),
            sequence=1,
            occurred_at_ms=1_001,
        ),
    ).aggregate

    accepted = reduce_event(
        issued,
        EntryAccepted(
            event_id="event-2",
            ticket_id=issued.identity.ticket_id,
            sequence=2,
            occurred_at_ms=1_050,
            exchange_order_id="entry-order-1",
        ),
    )

    assert accepted.aggregate.status is AggregateStatus.ENTRY_ACCEPTED
    assert accepted.aggregate.entry_exchange_order_id == "entry-order-1"
    assert accepted.effects == ()


def test_unknown_entry_outcome_opens_incident_and_blocks_progression() -> None:
    issued = reduce_event(
        None,
        TicketIssued(
            event_id="event-1",
            ticket=_ticket(),
            sequence=1,
            occurred_at_ms=1_001,
        ),
    ).aggregate

    unknown = reduce_event(
        issued,
        EntryOutcomeUnknown(
            event_id="event-2",
            ticket_id=issued.identity.ticket_id,
            sequence=2,
            occurred_at_ms=1_050,
            reason="venue_timeout",
        ),
    )

    assert unknown.aggregate.status is AggregateStatus.ENTRY_OUTCOME_UNKNOWN
    assert unknown.effects == (
        OpenIncident(
            ticket_id=issued.identity.ticket_id,
            incident_kind="entry_outcome_unknown",
        ),
    )


def test_full_entry_fill_requires_initial_stop_before_releasing_entry_lane() -> None:
    ticket = _ticket()
    issued = reduce_event(
        None,
        TicketIssued(
            event_id="event-1",
            ticket=ticket,
            sequence=1,
            occurred_at_ms=1_001,
        ),
    ).aggregate

    filled = reduce_event(
        issued,
        EntryFilled(
            event_id="event-2",
            ticket_id=ticket.identity.ticket_id,
            sequence=2,
            occurred_at_ms=1_100,
            filled_qty=ticket.quantity,
            average_fill_price=Decimal(60000),
            venue_reported_liquidation_price=None,
            position_observed_at_ms=1_100,
            post_fill_risk=_normal_post_fill_risk(ticket, Decimal(60000)),
        ),
    )

    assert filled.aggregate.status is AggregateStatus.PROTECTION_PENDING
    assert filled.aggregate.position_qty == ticket.quantity
    assert filled.effects == (
        PrepareInitialStopCommand(
            ticket_id=ticket.identity.ticket_id,
            quantity=ticket.quantity,
            stop_price=ticket.initial_stop_price,
        ),
    )

    protected = reduce_event(
        filled.aggregate,
        InitialStopConfirmed(
            event_id="event-3",
            ticket_id=ticket.identity.ticket_id,
            sequence=3,
            occurred_at_ms=1_200,
            exchange_order_id="stop-1",
            protected_qty=ticket.quantity,
        ),
    )

    assert protected.aggregate.status is AggregateStatus.POST_FILL_RISK_PENDING
    assert protected.aggregate.initial_stop_exchange_order_id == "stop-1"
    assert protected.aggregate.entry_lane_held is True
    assert protected.effects == ()

    assessed = reduce_event(
        protected.aggregate,
        _post_fill_stress_event(protected.aggregate),
    )
    assert assessed.aggregate.status is AggregateStatus.TP1_PENDING
    assert assessed.effects == (
        ReleaseEntryLane(ticket_id=ticket.identity.ticket_id),
        PrepareTakeProfitCommand(
            ticket_id=ticket.identity.ticket_id,
            quantity=ticket.take_profit_quantities[0],
            limit_price=ticket.take_profit_prices[0],
        ),
    )


def test_partial_entry_fill_is_incident_and_controlled_flatten_not_normal_position() -> None:
    ticket = _ticket()
    issued = reduce_event(
        None,
        TicketIssued(
            event_id="event-1",
            ticket=ticket,
            sequence=1,
            occurred_at_ms=1_001,
        ),
    ).aggregate

    reduction = reduce_event(
        issued,
        EntryPartiallyFilled(
            event_id="event-2",
            ticket_id=ticket.identity.ticket_id,
            sequence=2,
            occurred_at_ms=1_100,
            filled_qty=Decimal("0.0004"),
            requested_qty=ticket.quantity,
            average_fill_price=Decimal(60000),
        ),
    )

    assert reduction.aggregate.status is AggregateStatus.PARTIAL_FILL_INCIDENT
    assert reduction.effects == (
        OpenIncident(
            ticket_id=ticket.identity.ticket_id,
            incident_kind="unsupported_partial_entry_fill",
        ),
        CancelEntryRemainder(ticket_id=ticket.identity.ticket_id),
        RequestControlledFlatten(
            ticket_id=ticket.identity.ticket_id,
            quantity=Decimal("0.0004"),
        ),
    )


def test_initial_stop_rejection_opens_hard_incident_and_requests_flatten() -> None:
    ticket = _ticket()
    aggregate = reduce_event(
        None,
        TicketIssued(
            event_id="event-1",
            ticket=ticket,
            sequence=1,
            occurred_at_ms=1_001,
        ),
    ).aggregate
    aggregate = reduce_event(
        aggregate,
        EntryFilled(
            event_id="event-2",
            ticket_id=ticket.identity.ticket_id,
            sequence=2,
            occurred_at_ms=1_100,
            filled_qty=ticket.quantity,
            average_fill_price=Decimal(60000),
            venue_reported_liquidation_price=None,
            position_observed_at_ms=1_100,
            post_fill_risk=_normal_post_fill_risk(ticket, Decimal(60000)),
        ),
    ).aggregate

    failed = reduce_event(
        aggregate,
        InitialStopRejected(
            event_id="event-3",
            ticket_id=ticket.identity.ticket_id,
            sequence=3,
            occurred_at_ms=1_200,
            reason="venue_rejected",
        ),
    )

    assert failed.aggregate.status is AggregateStatus.EXIT_PENDING
    assert failed.aggregate.entry_lane_held is True
    assert failed.effects == (
        OpenIncident(
            ticket_id=ticket.identity.ticket_id,
            incident_kind="initial_stop_rejected",
        ),
        PrepareExitCommand(
            ticket_id=ticket.identity.ticket_id,
            quantity=ticket.quantity,
            reason="initial_stop_rejected",
        ),
    )

    flat = reduce_event(
        failed.aggregate,
        PositionFlatConfirmed(
            event_id="event-4",
            ticket_id=ticket.identity.ticket_id,
            sequence=4,
            occurred_at_ms=1_300,
        ),
    )
    assert flat.aggregate.status is AggregateStatus.RECONCILIATION_PENDING
    assert flat.aggregate.entry_lane_held is False
    assert flat.effects == (
        ReleaseEntryLane(ticket_id=ticket.identity.ticket_id),
    )


def test_unknown_initial_stop_outcome_waits_for_venue_truth_without_exit() -> None:
    ticket = _ticket()
    aggregate = reduce_event(
        None,
        TicketIssued(
            event_id="event-1",
            ticket=ticket,
            sequence=1,
            occurred_at_ms=1_001,
        ),
    ).aggregate
    aggregate = reduce_event(
        aggregate,
        EntryFilled(
            event_id="event-2",
            ticket_id=ticket.identity.ticket_id,
            sequence=2,
            occurred_at_ms=1_100,
            filled_qty=ticket.quantity,
            average_fill_price=Decimal(60000),
            venue_reported_liquidation_price=None,
            position_observed_at_ms=1_100,
            post_fill_risk=_normal_post_fill_risk(ticket, Decimal(60000)),
        ),
    ).aggregate

    failed = reduce_event(
        aggregate,
        InitialStopOutcomeUnknown(
            event_id="event-3",
            ticket_id=ticket.identity.ticket_id,
            sequence=3,
            occurred_at_ms=1_200,
            reason="venue_timeout",
        ),
    )

    assert failed.aggregate.status is AggregateStatus.INITIAL_STOP_OUTCOME_UNKNOWN
    assert failed.aggregate.entry_lane_held is True
    assert failed.effects == (
        OpenIncident(
            ticket_id=ticket.identity.ticket_id,
            incident_kind="initial_stop_outcome_unknown",
        ),
    )


def test_reconciled_initial_stop_submission_protects_position_and_resolves_unknown() -> None:
    ticket = _ticket()
    aggregate = reduce_event(
        None,
        TicketIssued(
            event_id="event-1",
            ticket=ticket,
            sequence=1,
            occurred_at_ms=1_001,
        ),
    ).aggregate
    aggregate = reduce_event(
        aggregate,
        EntryFilled(
            event_id="event-2",
            ticket_id=ticket.identity.ticket_id,
            sequence=2,
            occurred_at_ms=1_100,
            filled_qty=ticket.quantity,
            average_fill_price=Decimal(60000),
            venue_reported_liquidation_price=None,
            position_observed_at_ms=1_100,
            post_fill_risk=_normal_post_fill_risk(ticket, Decimal(60000)),
        ),
    ).aggregate
    aggregate = reduce_event(
        aggregate,
        InitialStopOutcomeUnknown(
            event_id="event-3",
            ticket_id=ticket.identity.ticket_id,
            sequence=3,
            occurred_at_ms=1_200,
            reason="venue_timeout",
        ),
    ).aggregate

    recovered = reduce_event(
        aggregate,
        InitialStopConfirmed(
            event_id="event-4",
            ticket_id=ticket.identity.ticket_id,
            sequence=4,
            occurred_at_ms=1_300,
            exchange_order_id="stop-recovered-1",
            protected_qty=ticket.quantity,
        ),
    )

    assert recovered.aggregate.status is AggregateStatus.POST_FILL_RISK_PENDING
    assert recovered.aggregate.initial_stop_exchange_order_id == "stop-recovered-1"
    assert recovered.aggregate.entry_lane_held is True
    assert recovered.effects == (
        ResolveIncident(
            ticket_id=ticket.identity.ticket_id,
            incident_kind="initial_stop_outcome_unknown",
        ),
    )


def test_reconciled_initial_stop_absence_enters_controlled_exit() -> None:
    ticket = _ticket()
    aggregate = reduce_event(
        None,
        TicketIssued(
            event_id="event-1",
            ticket=ticket,
            sequence=1,
            occurred_at_ms=1_001,
        ),
    ).aggregate
    aggregate = reduce_event(
        aggregate,
        EntryFilled(
            event_id="event-2",
            ticket_id=ticket.identity.ticket_id,
            sequence=2,
            occurred_at_ms=1_100,
            filled_qty=ticket.quantity,
            average_fill_price=Decimal(60000),
            venue_reported_liquidation_price=None,
            position_observed_at_ms=1_100,
            post_fill_risk=_normal_post_fill_risk(ticket, Decimal(60000)),
        ),
    ).aggregate
    aggregate = reduce_event(
        aggregate,
        InitialStopOutcomeUnknown(
            event_id="event-3",
            ticket_id=ticket.identity.ticket_id,
            sequence=3,
            occurred_at_ms=1_200,
            reason="venue_timeout",
        ),
    ).aggregate

    recovered = reduce_event(
        aggregate,
        InitialStopAbsenceConfirmed(
            event_id="event-4",
            ticket_id=ticket.identity.ticket_id,
            sequence=4,
            occurred_at_ms=1_300,
            command_id="command:initial-stop-1",
        ),
    )

    assert recovered.aggregate.status is AggregateStatus.EXIT_PENDING
    assert recovered.aggregate.entry_lane_held is True
    assert recovered.effects == (
        ResolveIncident(
            ticket_id=ticket.identity.ticket_id,
            incident_kind="initial_stop_outcome_unknown",
        ),
        OpenIncident(
            ticket_id=ticket.identity.ticket_id,
            incident_kind="initial_stop_absent",
        ),
        PrepareExitCommand(
            ticket_id=ticket.identity.ticket_id,
            quantity=ticket.quantity,
            reason="initial_stop_absent",
        ),
    )


def test_external_flat_enters_reconciliation_and_cancels_owned_protection() -> None:
    ticket = _ticket()
    aggregate = reduce_event(
        None,
        TicketIssued(
            event_id="event-1",
            ticket=ticket,
            sequence=1,
            occurred_at_ms=1_001,
        ),
    ).aggregate
    aggregate = reduce_event(
        aggregate,
        EntryFilled(
            event_id="event-2",
            ticket_id=ticket.identity.ticket_id,
            sequence=2,
            occurred_at_ms=1_100,
            filled_qty=ticket.quantity,
            average_fill_price=Decimal(60000),
            venue_reported_liquidation_price=None,
            position_observed_at_ms=1_100,
            post_fill_risk=_normal_post_fill_risk(ticket, Decimal(60000)),
        ),
    ).aggregate
    aggregate = reduce_event(
        aggregate,
        InitialStopConfirmed(
            event_id="event-3",
            ticket_id=ticket.identity.ticket_id,
            sequence=3,
            occurred_at_ms=1_200,
            exchange_order_id="stop-1",
            protected_qty=ticket.quantity,
        ),
    ).aggregate
    aggregate = reduce_event(
        aggregate,
        _post_fill_stress_event(aggregate),
    ).aggregate

    external_flat = reduce_event(
        aggregate,
        ExternalFlatDetected(
            event_id="event-4",
            ticket_id=ticket.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_000,
        ),
    )

    assert external_flat.aggregate.status is AggregateStatus.RECONCILIATION_PENDING
    assert external_flat.aggregate.position_qty == Decimal(0)
    assert external_flat.aggregate.pending_cancel_exchange_order_id == "stop-1"
    assert external_flat.effects == (
        OpenIncident(
            ticket_id=ticket.identity.ticket_id,
            incident_kind="external_flat",
        ),
        CancelProtectionOrders(
            ticket_id=ticket.identity.ticket_id,
            exchange_order_id="stop-1",
            order_namespace="conditional",
            purpose="reconciliation_cleanup",
        ),
    )


def test_unknown_exit_outcome_opens_incident_without_creating_retry() -> None:
    aggregate = _position_protected_aggregate()
    ticket = aggregate.ticket
    aggregate = reduce_event(
        aggregate,
        ExitRequested(
            event_id="event-4",
            ticket_id=ticket.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_000,
            reason="strategy_exit",
        ),
    ).aggregate

    unknown = reduce_event(
        aggregate,
        ExitOutcomeUnknown(
            event_id="event-5",
            ticket_id=ticket.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_100,
            reason="venue_timeout",
        ),
    )

    assert unknown.aggregate.status is AggregateStatus.EXIT_OUTCOME_UNKNOWN
    assert unknown.effects == (
        OpenIncident(
            ticket_id=ticket.identity.ticket_id,
            incident_kind="exit_outcome_unknown",
        ),
    )


def test_reconciled_exit_submission_resumes_accepted_state() -> None:
    aggregate = _exit_outcome_unknown_aggregate()

    recovered = reduce_event(
        aggregate,
        ExitAccepted(
            event_id="event-6",
            ticket_id=aggregate.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_200,
            exchange_order_id="exit-recovered-1",
        ),
    )

    assert recovered.aggregate.status is AggregateStatus.EXIT_ACCEPTED
    assert recovered.aggregate.exit_exchange_order_id == "exit-recovered-1"
    assert recovered.effects == (
        ResolveIncident(
            ticket_id=aggregate.identity.ticket_id,
            incident_kind="exit_outcome_unknown",
        ),
    )


def test_reconciled_exit_absence_remains_nonflat_recovery_state() -> None:
    aggregate = _exit_outcome_unknown_aggregate()

    recovered = reduce_event(
        aggregate,
        ExitAbsenceConfirmed(
            event_id="event-6",
            ticket_id=aggregate.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_200,
            command_id="command:exit-1",
        ),
    )

    assert recovered.aggregate.status is AggregateStatus.EXIT_REJECTED
    assert recovered.aggregate.position_qty == aggregate.position_qty
    assert recovered.effects == (
        ResolveIncident(
            ticket_id=aggregate.identity.ticket_id,
            incident_kind="exit_outcome_unknown",
        ),
    )


def test_reconciled_controlled_flatten_submission_resumes_accepted_state() -> None:
    aggregate = _controlled_flatten_outcome_unknown_aggregate()

    recovered = reduce_event(
        aggregate,
        ControlledFlattenAccepted(
            event_id="event-6",
            ticket_id=aggregate.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_200,
            exchange_order_id="flatten-recovered-1",
        ),
    )

    assert recovered.aggregate.status is AggregateStatus.CONTROLLED_FLATTEN_ACCEPTED
    assert recovered.aggregate.exit_exchange_order_id == "flatten-recovered-1"
    assert recovered.effects == (
        ResolveIncident(
            ticket_id=aggregate.identity.ticket_id,
            incident_kind="controlled_flatten_outcome_unknown",
        ),
    )


def test_reconciled_controlled_flatten_absence_stays_incident_and_nonflat() -> None:
    aggregate = _controlled_flatten_outcome_unknown_aggregate()

    recovered = reduce_event(
        aggregate,
        ControlledFlattenAbsenceConfirmed(
            event_id="event-6",
            ticket_id=aggregate.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_200,
            command_id="command:flatten-1",
        ),
    )

    assert recovered.aggregate.status is AggregateStatus.CONTROLLED_FLATTEN_REJECTED
    assert recovered.aggregate.position_qty == aggregate.position_qty
    assert recovered.effects == (
        ResolveIncident(
            ticket_id=aggregate.identity.ticket_id,
            incident_kind="controlled_flatten_outcome_unknown",
        ),
        OpenIncident(
            ticket_id=aggregate.identity.ticket_id,
            incident_kind="controlled_flatten_absent",
        ),
    )


def test_exit_rejection_enters_explicit_recovery_and_allows_new_request() -> None:
    aggregate = _position_protected_aggregate()
    ticket = aggregate.ticket
    aggregate = reduce_event(
        aggregate,
        ExitRequested(
            event_id="event-4",
            ticket_id=ticket.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_000,
            reason="strategy_exit",
        ),
    ).aggregate

    rejected = reduce_event(
        aggregate,
        ExitRejected(
            event_id="event-5",
            ticket_id=ticket.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_100,
            reason="venue_rejected",
        ),
    )

    assert rejected.aggregate.status is AggregateStatus.EXIT_REJECTED
    assert rejected.effects == (
        OpenIncident(
            ticket_id=ticket.identity.ticket_id,
            incident_kind="exit_rejected",
        ),
    )

    externally_flat = reduce_event(
        rejected.aggregate,
        PositionFlatConfirmed(
            event_id="event-6-flat",
            ticket_id=ticket.identity.ticket_id,
            sequence=rejected.aggregate.last_event_sequence + 1,
            occurred_at_ms=2_150,
        ),
    )
    assert externally_flat.aggregate.status is AggregateStatus.RECONCILIATION_PENDING

    retried = reduce_event(
        rejected.aggregate,
        ExitRequested(
            event_id="event-6",
            ticket_id=ticket.identity.ticket_id,
            sequence=rejected.aggregate.last_event_sequence + 1,
            occurred_at_ms=2_200,
            reason="recover_exit_rejection",
        ),
    )
    assert retried.aggregate.status is AggregateStatus.EXIT_PENDING
    assert retried.effects == (
        PrepareExitCommand(
            ticket_id=ticket.identity.ticket_id,
            quantity=ticket.quantity,
            reason="recover_exit_rejection",
        ),
    )


def test_owned_orphan_order_requests_exact_durable_cancel() -> None:
    aggregate = _reconciliation_pending_aggregate()

    detected = reduce_event(
        aggregate,
        OwnedOrphanOrderDetected(
            event_id="event-8",
            ticket_id=aggregate.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_200,
            exchange_order_id="owned-orphan-1",
            order_namespace="conditional",
        ),
    )
    assert detected.aggregate.status is AggregateStatus.RECONCILIATION_PENDING
    assert detected.effects == (
        CancelProtectionOrders(
            ticket_id=aggregate.identity.ticket_id,
            exchange_order_id="owned-orphan-1",
            order_namespace="conditional",
            purpose="reconciliation_cleanup",
        ),
    )


def test_reconciliation_match_closes_every_open_ticket_incident_before_release() -> None:
    aggregate = _reconciliation_pending_aggregate()

    matched = reduce_event(
        aggregate,
        ReconciliationMatched(
            event_id="event:reconciliation-matched",
            ticket_id=aggregate.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_500,
        ),
    )

    assert matched.effects[0] == ResolveTicketIncidentsAtClosure(
        ticket_id=aggregate.identity.ticket_id,
    )
    assert isinstance(matched.effects[1], ReleaseCapitalAuthorities)

def test_cancel_rejection_is_persisted_as_blocking_recovery_state() -> None:
    aggregate = _cancel_pending_aggregate()
    assert aggregate.pending_cancel_exchange_order_id == "tp-1"

    rejected = reduce_event(
        aggregate,
        CancelOrderRejected(
            event_id="event-6",
            ticket_id=aggregate.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_150,
            exchange_order_id="tp-1",
            reason="venue_rejected",
        ),
    )

    assert rejected.aggregate.status is AggregateStatus.CANCEL_REJECTED
    assert rejected.aggregate.pending_cancel_exchange_order_id == "tp-1"
    assert rejected.effects == (
        OpenIncident(
            ticket_id=aggregate.identity.ticket_id,
            incident_kind="cancel_order_rejected",
        ),
    )
    with pytest.raises(InvalidLifecycleTransition):
        reduce_event(
            rejected.aggregate,
            ReconciliationMatched(
                event_id="event-7",
                ticket_id=aggregate.identity.ticket_id,
                sequence=rejected.aggregate.last_event_sequence + 1,
                occurred_at_ms=2_200,
            ),
        )


def test_unknown_cancel_outcome_is_conserved_and_blocks_reconciliation() -> None:
    aggregate = _cancel_pending_aggregate()

    unknown = reduce_event(
        aggregate,
        CancelOrderOutcomeUnknown(
            event_id="event-6",
            ticket_id=aggregate.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_150,
            exchange_order_id="tp-1",
            reason="venue_timeout",
        ),
    )

    assert unknown.aggregate.status is AggregateStatus.CANCEL_OUTCOME_UNKNOWN
    assert unknown.aggregate.pending_cancel_exchange_order_id == "tp-1"
    assert unknown.effects == (
        OpenIncident(
            ticket_id=aggregate.identity.ticket_id,
            incident_kind="cancel_order_outcome_unknown",
        ),
    )
    with pytest.raises(InvalidLifecycleTransition):
        reduce_event(
            unknown.aggregate,
            ReconciliationMatched(
                event_id="event-7",
                ticket_id=aggregate.identity.ticket_id,
                sequence=unknown.aggregate.last_event_sequence + 1,
                occurred_at_ms=2_200,
            ),
        )


def test_reconciled_cancel_absence_resolves_only_cancel_unknown_incident() -> None:
    aggregate = _cancel_pending_aggregate()
    aggregate = reduce_event(
        aggregate,
        CancelOrderOutcomeUnknown(
            event_id="event-6",
            ticket_id=aggregate.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_150,
            exchange_order_id="tp-1",
            reason="venue_timeout",
        ),
    ).aggregate

    recovered = reduce_event(
        aggregate,
        CancelOrderAbsenceConfirmed(
            event_id="event-7",
            ticket_id=aggregate.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_200,
            exchange_order_id="tp-1",
        ),
    )

    assert recovered.aggregate.status is AggregateStatus.RECONCILIATION_PENDING
    assert recovered.aggregate.pending_cancel_exchange_order_id is None
    assert recovered.effects == (
        MarkCancelCommandReconciledAbsent(
            ticket_id=aggregate.identity.ticket_id,
            exchange_order_id="tp-1",
        ),
        ResolveIncident(
            ticket_id=aggregate.identity.ticket_id,
            incident_kind="cancel_order_outcome_unknown",
        ),
    )


def test_cancel_target_still_open_resolves_unknown_and_allows_exact_retry() -> None:
    aggregate = _cancel_pending_aggregate()
    aggregate = reduce_event(
        aggregate,
        CancelOrderOutcomeUnknown(
            event_id="event-6",
            ticket_id=aggregate.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_150,
            exchange_order_id="tp-1",
            reason="venue_timeout",
        ),
    ).aggregate

    recovered = reduce_event(
        aggregate,
        CancelOrderStillOpenConfirmed(
            event_id="event-7",
            ticket_id=aggregate.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_200,
            exchange_order_id="tp-1",
        ),
    )

    assert recovered.aggregate.status is AggregateStatus.CANCEL_REJECTED
    assert recovered.aggregate.pending_cancel_exchange_order_id == "tp-1"
    assert recovered.effects == (
        ResolveIncident(
            ticket_id=aggregate.identity.ticket_id,
            incident_kind="cancel_order_outcome_unknown",
        ),
    )


def test_reconciled_partial_fill_cancel_absence_starts_controlled_flatten() -> None:
    ticket = _ticket()
    aggregate = reduce_event(
        None,
        TicketIssued(
            event_id="event-1",
            ticket=ticket,
            sequence=1,
            occurred_at_ms=1_001,
        ),
    ).aggregate
    aggregate = reduce_event(
        aggregate,
        EntryAccepted(
            event_id="event-2",
            ticket_id=ticket.identity.ticket_id,
            sequence=2,
            occurred_at_ms=1_100,
            exchange_order_id="entry-1",
        ),
    ).aggregate
    aggregate = reduce_event(
        aggregate,
        EntryPartiallyFilled(
            event_id="event-3",
            ticket_id=ticket.identity.ticket_id,
            sequence=3,
            occurred_at_ms=1_200,
            filled_qty=Decimal("0.0004"),
            requested_qty=ticket.quantity,
            average_fill_price=Decimal(60000),
        ),
    ).aggregate
    aggregate = reduce_event(
        aggregate,
        EntryRemainderCancelOutcomeUnknown(
            event_id="event-4",
            ticket_id=ticket.identity.ticket_id,
            sequence=4,
            occurred_at_ms=1_300,
            exchange_order_id="entry-1",
            reason="venue_timeout",
        ),
    ).aggregate

    recovered = reduce_event(
        aggregate,
        EntryRemainderCancelConfirmed(
            event_id="event-5",
            ticket_id=ticket.identity.ticket_id,
            sequence=5,
            occurred_at_ms=1_400,
            exchange_order_id="entry-1",
        ),
    )

    assert recovered.aggregate.status is AggregateStatus.CONTROLLED_FLATTEN_PENDING
    assert recovered.effects == (
        MarkCancelCommandReconciledAbsent(
            ticket_id=ticket.identity.ticket_id,
            exchange_order_id="entry-1",
        ),
        ResolveIncident(
            ticket_id=ticket.identity.ticket_id,
            incident_kind="entry_remainder_cancel_outcome_unknown",
        ),
        PrepareControlledFlattenCommand(
            ticket_id=ticket.identity.ticket_id,
            quantity=Decimal("0.0004"),
        ),
    )


def test_unowned_order_opens_incident_without_cancel_authority() -> None:
    aggregate = _reconciliation_pending_aggregate()

    detected = reduce_event(
        aggregate,
        UnownedOrderDetected(
            event_id="event-8",
            ticket_id=aggregate.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_200,
            exchange_order_id="manual-order-1",
        ),
    )

    assert detected.aggregate.status is AggregateStatus.RECONCILIATION_PENDING
    assert detected.effects == (
        OpenIncident(
            ticket_id=aggregate.identity.ticket_id,
            incident_kind="unowned_open_order",
        ),
    )


@pytest.mark.parametrize(
    ("field_name", "exchange_order_id"),
    (
        ("active_stop_exchange_order_id", "active-stop-residue"),
        ("tp1_exchange_order_id", "tp1-residue"),
    ),
)
def test_reconciliation_rejects_any_owned_order_identity_residue(
    field_name: str,
    exchange_order_id: str,
) -> None:
    aggregate = _reconciliation_pending_aggregate().model_copy(
        update={field_name: exchange_order_id}
    )

    with pytest.raises(InvalidLifecycleTransition, match="order identity residue"):
        reduce_event(
            aggregate,
            ReconciliationMatched(
                event_id="event-reconciliation-residue",
                ticket_id=aggregate.identity.ticket_id,
                sequence=aggregate.last_event_sequence + 1,
                occurred_at_ms=2_250,
            ),
        )


def _position_protected_aggregate():
    ticket = _ticket()
    aggregate = reduce_event(
        None,
        TicketIssued(
            event_id="event-1",
            ticket=ticket,
            sequence=1,
            occurred_at_ms=1_001,
        ),
    ).aggregate
    aggregate = reduce_event(
        aggregate,
        EntryFilled(
            event_id="event-2",
            ticket_id=ticket.identity.ticket_id,
            sequence=2,
            occurred_at_ms=1_100,
            filled_qty=ticket.quantity,
            average_fill_price=Decimal(60000),
            venue_reported_liquidation_price=None,
            position_observed_at_ms=1_100,
            post_fill_risk=_normal_post_fill_risk(ticket, Decimal(60000)),
        ),
    ).aggregate
    aggregate = reduce_event(
        aggregate,
        InitialStopConfirmed(
            event_id="event-3",
            ticket_id=ticket.identity.ticket_id,
            sequence=3,
            occurred_at_ms=1_200,
            exchange_order_id="stop-1",
            protected_qty=ticket.quantity,
        ),
    ).aggregate
    aggregate = reduce_event(
        aggregate,
        _post_fill_stress_event(aggregate),
    ).aggregate
    return reduce_event(
        aggregate,
        TakeProfitConfirmed(
            event_id="event-5",
            ticket_id=ticket.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=1_300,
            exchange_order_id="tp-1",
            target_qty=ticket.take_profit_quantities[0],
        ),
    ).aggregate


def _exit_outcome_unknown_aggregate():
    aggregate = _position_protected_aggregate()
    ticket = aggregate.ticket
    aggregate = reduce_event(
        aggregate,
        ExitRequested(
            event_id="event-4",
            ticket_id=ticket.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_000,
            reason="strategy_exit",
        ),
    ).aggregate
    return reduce_event(
        aggregate,
        ExitOutcomeUnknown(
            event_id="event-5",
            ticket_id=ticket.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_100,
            reason="venue_timeout",
        ),
    ).aggregate


def _controlled_flatten_outcome_unknown_aggregate():
    ticket = _ticket()
    aggregate = reduce_event(
        None,
        TicketIssued(
            event_id="event-1",
            ticket=ticket,
            sequence=1,
            occurred_at_ms=1_001,
        ),
    ).aggregate
    aggregate = reduce_event(
        aggregate,
        EntryAccepted(
            event_id="event-2",
            ticket_id=ticket.identity.ticket_id,
            sequence=2,
            occurred_at_ms=1_100,
            exchange_order_id="entry-1",
        ),
    ).aggregate
    aggregate = reduce_event(
        aggregate,
        EntryPartiallyFilled(
            event_id="event-3",
            ticket_id=ticket.identity.ticket_id,
            sequence=3,
            occurred_at_ms=1_200,
            filled_qty=Decimal("0.0004"),
            requested_qty=ticket.quantity,
            average_fill_price=Decimal(60000),
        ),
    ).aggregate
    cancel_confirmed = reduce_event(
        aggregate,
        EntryRemainderCancelConfirmed(
            event_id="event-4",
            ticket_id=ticket.identity.ticket_id,
            sequence=4,
            occurred_at_ms=1_300,
            exchange_order_id="entry-1",
        ),
    )
    assert cancel_confirmed.effects == (
        PrepareControlledFlattenCommand(
            ticket_id=ticket.identity.ticket_id,
            quantity=Decimal("0.0004"),
        ),
    )
    return reduce_event(
        cancel_confirmed.aggregate,
        ControlledFlattenOutcomeUnknown(
            event_id="event-5",
            ticket_id=ticket.identity.ticket_id,
            sequence=5,
            occurred_at_ms=2_100,
            reason="venue_timeout",
        ),
    ).aggregate

def test_protected_ticket_exits_reconciles_settles_reviews_and_terminates() -> None:
    aggregate = _position_protected_aggregate()
    ticket = aggregate.ticket

    exit_requested = reduce_event(
        aggregate,
        ExitRequested(
            event_id="event-4",
            ticket_id=ticket.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_000,
            reason="strategy_exit",
        ),
    )
    assert exit_requested.aggregate.status is AggregateStatus.EXIT_PENDING
    assert exit_requested.effects == (
        PrepareExitCommand(
            ticket_id=ticket.identity.ticket_id,
            quantity=ticket.quantity,
            reason="strategy_exit",
        ),
    )

    exit_accepted = reduce_event(
        exit_requested.aggregate,
        ExitAccepted(
            event_id="event-5",
            ticket_id=ticket.identity.ticket_id,
            sequence=exit_requested.aggregate.last_event_sequence + 1,
            occurred_at_ms=2_050,
            exchange_order_id="exit-order-1",
        ),
    )
    assert exit_accepted.aggregate.status is AggregateStatus.EXIT_ACCEPTED
    assert exit_accepted.aggregate.exit_exchange_order_id == "exit-order-1"

    flat = reduce_event(
        exit_accepted.aggregate,
        PositionFlatConfirmed(
            event_id="event-6",
            ticket_id=ticket.identity.ticket_id,
            sequence=exit_accepted.aggregate.last_event_sequence + 1,
            occurred_at_ms=2_100,
        ),
    )
    assert flat.aggregate.status is AggregateStatus.RECONCILIATION_PENDING
    assert flat.effects == (
        CancelProtectionOrders(
            ticket_id=ticket.identity.ticket_id,
            exchange_order_id="tp-1",
            order_namespace="conditional",
            purpose="reconciliation_cleanup",
        ),
    )

    tp_cancelled = reduce_event(
        flat.aggregate,
        ProtectionCancelConfirmed(
            event_id="event-7",
            ticket_id=ticket.identity.ticket_id,
            sequence=flat.aggregate.last_event_sequence + 1,
            occurred_at_ms=2_150,
            exchange_order_id="tp-1",
        ),
    )
    assert tp_cancelled.aggregate.tp1_exchange_order_id is None

    stop_cancel_requested = reduce_event(
        tp_cancelled.aggregate,
        OwnedOrphanOrderDetected(
            event_id="event-8",
            ticket_id=ticket.identity.ticket_id,
            sequence=tp_cancelled.aggregate.last_event_sequence + 1,
            occurred_at_ms=2_175,
            exchange_order_id="stop-1",
            order_namespace="conditional",
        ),
    )

    cancelled = reduce_event(
        stop_cancel_requested.aggregate,
        ProtectionCancelConfirmed(
            event_id="event-9",
            ticket_id=ticket.identity.ticket_id,
            sequence=stop_cancel_requested.aggregate.last_event_sequence + 1,
            occurred_at_ms=2_190,
            exchange_order_id="stop-1",
        ),
    )
    assert cancelled.aggregate.initial_stop_exchange_order_id is None
    assert cancelled.aggregate.active_stop_exchange_order_id is None
    assert cancelled.aggregate.protected_qty == Decimal(0)

    reconciled = reduce_event(
        cancelled.aggregate,
        ReconciliationMatched(
            event_id="event-10",
            ticket_id=ticket.identity.ticket_id,
            sequence=cancelled.aggregate.last_event_sequence + 1,
            occurred_at_ms=2_200,
        ),
    )
    assert reconciled.aggregate.status is AggregateStatus.SETTLEMENT_PENDING
    assert reconciled.effects == (
        ResolveTicketIncidentsAtClosure(
            ticket_id=ticket.identity.ticket_id,
        ),
        ReleaseCapitalAuthorities(
            ticket_id=ticket.identity.ticket_id,
            account_capacity_domain_key=(
                f"{ticket.identity.netting_domain.venue_id}:"
                f"{ticket.identity.netting_domain.account_id}"
            ),
            netting_domain_key=ticket.identity.netting_domain.key(),
            notional=ticket.notional,
            risk_at_stop=ticket.risk_at_stop,
            reserved_margin=ticket.reserved_margin,
            released_at_ms=2_200,
        ),
    )

    settled = reduce_event(
        reconciled.aggregate,
        BudgetSettled(
            event_id="event-11",
            ticket_id=ticket.identity.ticket_id,
            sequence=reconciled.aggregate.last_event_sequence + 1,
            occurred_at_ms=2_300,
        ),
    )
    assert settled.aggregate.status is AggregateStatus.REVIEW_PENDING
    assert settled.effects == ()

    terminal = reduce_event(
        settled.aggregate,
        ReviewRecorded(
            event_id="event-12",
            ticket_id=ticket.identity.ticket_id,
            sequence=settled.aggregate.last_event_sequence + 1,
            occurred_at_ms=2_400,
            review_id="review-1",
        ),
    )
    assert terminal.aggregate.status is AggregateStatus.TERMINAL
    assert terminal.aggregate.review_id == "review-1"
    assert terminal.effects == (
        ProjectTerminalOwnerState(ticket_id=ticket.identity.ticket_id),
    )

    revised = reduce_event(
        terminal.aggregate,
        ReviewRevised(
            event_id="event-13",
            ticket_id=ticket.identity.ticket_id,
            sequence=terminal.aggregate.last_event_sequence + 1,
            occurred_at_ms=2_500,
            review_id="review-2",
            supersedes_review_id="review-1",
        ),
    )
    assert revised.aggregate.status is AggregateStatus.TERMINAL
    assert revised.aggregate.review_id == "review-2"
    assert revised.effects == (
        ProjectTerminalOwnerState(ticket_id=ticket.identity.ticket_id),
    )


def test_review_revision_requires_terminal_current_pointer() -> None:
    pending = _reconciliation_pending_aggregate()
    settled = reduce_event(
        reduce_event(
            pending,
            ReconciliationMatched(
                event_id="event-review-match",
                ticket_id=pending.identity.ticket_id,
                sequence=pending.last_event_sequence + 1,
                occurred_at_ms=3_000,
            ),
        ).aggregate,
        BudgetSettled(
            event_id="event-review-settle",
            ticket_id=pending.identity.ticket_id,
            sequence=pending.last_event_sequence + 2,
            occurred_at_ms=3_100,
        ),
    ).aggregate

    with pytest.raises(InvalidLifecycleTransition, match="terminal"):
        reduce_event(
            settled,
            ReviewRevised(
                event_id="event-review-revise",
                ticket_id=pending.identity.ticket_id,
                sequence=settled.last_event_sequence + 1,
                occurred_at_ms=3_200,
                review_id="review-2",
                supersedes_review_id="review-1",
            ),
        )


def test_review_revision_requires_exact_current_review_pointer() -> None:
    pending = _reconciliation_pending_aggregate()
    matched = reduce_event(
        pending,
        ReconciliationMatched(
            event_id="event-review-pointer-match",
            ticket_id=pending.identity.ticket_id,
            sequence=pending.last_event_sequence + 1,
            occurred_at_ms=3_000,
        ),
    ).aggregate
    settled = reduce_event(
        matched,
        BudgetSettled(
            event_id="event-review-pointer-settle",
            ticket_id=pending.identity.ticket_id,
            sequence=matched.last_event_sequence + 1,
            occurred_at_ms=3_100,
        ),
    ).aggregate
    aggregate = reduce_event(
        settled,
        ReviewRecorded(
            event_id="event-review-pointer-record",
            ticket_id=pending.identity.ticket_id,
            sequence=settled.last_event_sequence + 1,
            occurred_at_ms=3_150,
            review_id="review-1",
        ),
    ).aggregate

    with pytest.raises(InvalidLifecycleTransition, match="supersedes"):
        reduce_event(
            aggregate,
            ReviewRevised(
                event_id="event-review-revise",
                ticket_id=aggregate.identity.ticket_id,
                sequence=aggregate.last_event_sequence + 1,
                occurred_at_ms=3_200,
                review_id="review-2",
                supersedes_review_id="review-wrong",
            ),
        )


def _reconciliation_pending_aggregate():
    aggregate = _position_protected_aggregate()
    ticket = aggregate.ticket
    aggregate = reduce_event(
        aggregate,
        ExitRequested(
            event_id="event-4",
            ticket_id=ticket.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_000,
            reason="strategy_exit",
        ),
    ).aggregate
    aggregate = reduce_event(
        aggregate,
        PositionFlatConfirmed(
            event_id="event-5",
            ticket_id=ticket.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_100,
        ),
    ).aggregate
    aggregate = reduce_event(
        aggregate,
        ProtectionCancelConfirmed(
            event_id="event-6",
            ticket_id=ticket.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_150,
            exchange_order_id="tp-1",
        ),
    ).aggregate
    aggregate = reduce_event(
        aggregate,
        OwnedOrphanOrderDetected(
            event_id="event-7",
            ticket_id=ticket.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_175,
            exchange_order_id="stop-1",
            order_namespace="conditional",
        ),
    ).aggregate
    return reduce_event(
        aggregate,
        ProtectionCancelConfirmed(
            event_id="event-8",
            ticket_id=ticket.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_190,
            exchange_order_id="stop-1",
        ),
    ).aggregate


def _cancel_pending_aggregate():
    aggregate = _position_protected_aggregate()
    ticket = aggregate.ticket
    aggregate = reduce_event(
        aggregate,
        ExitRequested(
            event_id="event-4",
            ticket_id=ticket.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_000,
            reason="strategy_exit",
        ),
    ).aggregate
    return reduce_event(
        aggregate,
        PositionFlatConfirmed(
            event_id="event-5",
            ticket_id=ticket.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_100,
        ),
    ).aggregate


def test_reducer_rejects_wrong_ticket_and_non_monotonic_sequence() -> None:
    aggregate = reduce_event(
        None,
        TicketIssued(
            event_id="event-1",
            ticket=_ticket(),
            sequence=1,
            occurred_at_ms=1_001,
        ),
    ).aggregate

    with pytest.raises(InvalidLifecycleTransition):
        reduce_event(
            aggregate,
            EntryRejected(
                event_id="event-2",
                ticket_id="ticket-wrong",
                sequence=2,
                occurred_at_ms=1_100,
                reason="venue_rejected",
            ),
        )

    with pytest.raises(InvalidLifecycleTransition):
        reduce_event(
            aggregate,
            EntryRejected(
                event_id="event-2",
                ticket_id=aggregate.identity.ticket_id,
                sequence=1,
                occurred_at_ms=1_100,
                reason="venue_rejected",
            ),
        )


def test_proven_absent_tp1_unknown_prepares_one_safe_new_generation() -> None:
    aggregate = _tp1_pending_aggregate()
    unknown = reduce_event(
        aggregate,
        TakeProfitOutcomeUnknown(
            event_id="event-tp-unknown",
            ticket_id=aggregate.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=1_300,
            reason="venue_timeout",
        ),
    ).aggregate

    recovered = reduce_event(
        unknown,
        TakeProfitAbsenceConfirmed(
            event_id="event-tp-absent",
            ticket_id=unknown.identity.ticket_id,
            sequence=unknown.last_event_sequence + 1,
            occurred_at_ms=1_400,
            command_id="command-tp-1",
        ),
    )

    assert recovered.aggregate.status is AggregateStatus.TP1_PENDING
    assert recovered.effects == (
        ResolveIncident(
            ticket_id=unknown.identity.ticket_id,
            incident_kind="take_profit_outcome_unknown",
        ),
        PrepareTakeProfitCommand(
            ticket_id=unknown.identity.ticket_id,
            quantity=unknown.tp1_target_qty,
            limit_price=unknown.ticket.take_profit_prices[0],
        ),
    )


def test_proven_absent_replacement_unknown_retries_exact_frozen_terms() -> None:
    aggregate = _replacement_pending_aggregate()
    unknown = reduce_event(
        aggregate,
        ProtectionReplacementOutcomeUnknown(
            event_id="event-replacement-unknown",
            ticket_id=aggregate.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=1_600,
            reason="venue_timeout",
        ),
    ).aggregate

    recovered = reduce_event(
        unknown,
        ProtectionReplacementAbsenceConfirmed(
            event_id="event-replacement-absent",
            ticket_id=unknown.identity.ticket_id,
            sequence=unknown.last_event_sequence + 1,
            occurred_at_ms=1_700,
            command_id="command-replacement-1",
        ),
    )

    assert recovered.aggregate.status is AggregateStatus.RUNNER_REPLACEMENT_PENDING
    assert recovered.effects == (
        ResolveIncident(
            ticket_id=unknown.identity.ticket_id,
            incident_kind="protection_replacement_outcome_unknown",
        ),
        PrepareProtectionReplacementCommand(
            ticket_id=unknown.identity.ticket_id,
            quantity=unknown.position_qty,
            stop_price=Decimal(60010),
            replaces_exchange_order_id="stop-1",
            source_watermark_ms=1_500,
        ),
    )


def test_proven_absent_old_stop_cancel_finishes_runner_protection() -> None:
    replacement = _replacement_pending_aggregate()
    confirmed = reduce_event(
        replacement,
        ProtectionReplacementConfirmed(
            event_id="event-replacement-confirmed",
            ticket_id=replacement.identity.ticket_id,
            sequence=replacement.last_event_sequence + 1,
            occurred_at_ms=1_600,
            exchange_order_id="stop-2",
            protected_qty=replacement.position_qty,
            stop_price=Decimal(60010),
            replaces_exchange_order_id="stop-1",
            source_watermark_ms=1_500,
        ),
    ).aggregate
    unknown = reduce_event(
        confirmed,
        ProtectionCancelOutcomeUnknown(
            event_id="event-cancel-unknown",
            ticket_id=confirmed.identity.ticket_id,
            sequence=confirmed.last_event_sequence + 1,
            occurred_at_ms=1_700,
            exchange_order_id="stop-1",
            reason="venue_timeout",
        ),
    ).aggregate

    recovered = reduce_event(
        unknown,
        ProtectionCancelAbsenceConfirmed(
            event_id="event-cancel-absent",
            ticket_id=unknown.identity.ticket_id,
            sequence=unknown.last_event_sequence + 1,
            occurred_at_ms=1_800,
            exchange_order_id="stop-1",
        ),
    )

    assert recovered.aggregate.status is AggregateStatus.RUNNER_PROTECTED
    assert recovered.aggregate.active_stop_exchange_order_id == "stop-2"
    assert recovered.aggregate.pending_replaced_stop_exchange_order_id is None
    assert recovered.effects == (
        MarkCancelCommandReconciledAbsent(
            ticket_id=unknown.identity.ticket_id,
            exchange_order_id="stop-1",
        ),
        ResolveIncident(
            ticket_id=unknown.identity.ticket_id,
            incident_kind="runner_old_stop_cancel_outcome_unknown",
        ),
    )


def _tp1_pending_aggregate():
    ticket = _ticket()
    aggregate = reduce_event(
        None,
        TicketIssued(
            event_id="event-1",
            ticket=ticket,
            sequence=1,
            occurred_at_ms=1_001,
        ),
    ).aggregate
    aggregate = reduce_event(
        aggregate,
        EntryFilled(
            event_id="event-2",
            ticket_id=ticket.identity.ticket_id,
            sequence=2,
            occurred_at_ms=1_100,
            filled_qty=ticket.quantity,
            average_fill_price=ticket.entry_reference_price,
            venue_reported_liquidation_price=None,
            position_observed_at_ms=1_100,
            post_fill_risk=_normal_post_fill_risk(
                ticket, ticket.entry_reference_price
            ),
        ),
    ).aggregate
    aggregate = reduce_event(
        aggregate,
        InitialStopConfirmed(
            event_id="event-3",
            ticket_id=ticket.identity.ticket_id,
            sequence=3,
            occurred_at_ms=1_200,
            exchange_order_id="stop-1",
            protected_qty=ticket.quantity,
        ),
    ).aggregate
    return reduce_event(
        aggregate,
        _post_fill_stress_event(aggregate),
    ).aggregate


def _replacement_pending_aggregate():
    aggregate = _tp1_pending_aggregate().model_copy(
        update={"status": AggregateStatus.POSITION_PROTECTED}
    )
    return reduce_event(
        aggregate,
        TakeProfitFilled(
            event_id="event-4",
            ticket_id=aggregate.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=1_500,
            filled_qty=aggregate.tp1_target_qty,
            average_fill_price=aggregate.ticket.take_profit_prices[0],
            runner_floor_price=Decimal(60010),
        ),
    ).aggregate
