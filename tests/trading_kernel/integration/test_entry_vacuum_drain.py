from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.application.dispatch_exchange_command import (
    DispatchCommandRequest,
    DispatchCommandStatus,
    dispatch_one_command,
)
from src.trading_kernel.application.drain_strategy_entry_vacuum import (
    DrainStrategyEntryVacuumRequest,
    VacuumDrainStatus,
    drain_strategy_entry_vacuum_once,
)
from src.trading_kernel.application.ports import (
    LeverageTruthRequest,
    LeverageTruthSnapshot,
    VenueCommandRequest,
    VenueSetLeverageRequest,
    VenueTruthRequest,
)
from src.trading_kernel.application.recover_unknown_command import (
    RecoverUnknownCommandRequest,
    recover_unknown_command,
)
from src.trading_kernel.application.runtime_facts import InstrumentRulesRequest
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommandKind,
    ExchangeCommandResult,
    ExchangeCommandStatus,
    SetLeverageCommandResult,
)
from src.trading_kernel.domain.cross_margin_stress import MaintenanceMarginBracket
from src.trading_kernel.domain.position import PositionSnapshot, VenueOrderSnapshot
from src.trading_kernel.domain.ticket import TradeTicket
from src.trading_kernel.domain.venue_truth import (
    UnknownRecoveryStatus,
    VenueLookupStatus,
    VenueOrderTruth,
    VenueTruthSnapshot,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    seed_strategy_registry,
)
from tests.trading_kernel.support.command_dispatch import (
    dispatch_for_ticket,
    issue,
    seed_policy,
)
from tests.trading_kernel.support.command_dispatch import (
    ticket as make_ticket,
)
from tests.trading_kernel.support.dispatch_venues import (
    AcceptingVenue,
    KindAwareAcceptingVenue,
    PreflightFacts,
)
from tests.trading_kernel.support.lifecycle import registered_sor_long_ticket
from tests.trading_kernel.support.selection_vacuum import (
    SELECTION_SPEC_ID,
    SESSION_START_MS,
    open_entry_vacuum,
)


class UnknownCancelVenue:
    async def execute(
        self,
        request: VenueCommandRequest,
    ) -> ExchangeCommandResult:
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.OUTCOME_UNKNOWN,
            observed_at_ms=request.deadline_at_ms - 1,
            reason="test_cancel_timeout",
        )

    async def set_leverage(
        self,
        request: VenueSetLeverageRequest,
    ) -> SetLeverageCommandResult:
        del request
        raise AssertionError("Vacuum cancel test must not set leverage")


class RejectingVenue:
    async def execute(
        self,
        request: VenueCommandRequest,
    ) -> ExchangeCommandResult:
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.REJECTED,
            observed_at_ms=request.deadline_at_ms - 1,
            reason="test_initial_stop_rejected",
        )

    async def set_leverage(
        self,
        request: VenueSetLeverageRequest,
    ) -> SetLeverageCommandResult:
        del request
        raise AssertionError("Retained partial protection test must not set leverage")


class StaticTruthPort:
    def __init__(self, truth: VenueTruthSnapshot) -> None:
        self.truth = truth
        self.requests: list[VenueTruthRequest] = []

    async def lookup_command_truth(
        self,
        request: VenueTruthRequest,
    ) -> VenueTruthSnapshot:
        self.requests.append(request)
        return self.truth

    async def read_configured_leverage(
        self,
        request: LeverageTruthRequest,
    ) -> LeverageTruthSnapshot:
        del request
        raise AssertionError("Vacuum cancel recovery must not read leverage")


@pytest.mark.asyncio
async def test_prepared_entry_is_superseded_and_releases_all_admission_authority(
    dispatch_engine,
) -> None:
    ticket = make_ticket()
    await seed_policy(dispatch_engine)
    await issue(dispatch_engine, ticket)
    vacuum = await open_entry_vacuum(dispatch_engine, ticket)

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        result = await drain_strategy_entry_vacuum_once(
            uow,
            _request(ticket, now_ms=vacuum.fenced_at_ms + 1),
        )

    assert result.status is VacuumDrainStatus.PREPARED_ENTRY_SUPERSEDED
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
        exposure = await uow.entry_admission.get_account_exposure(
            ticket.identity.netting_domain.venue_id,
            ticket.identity.netting_domain.account_id,
        )
        lane = await uow.entry_admission.get_global_lane()
        domain_active = await uow.entry_admission.has_active_ticket_in_domain(
            ticket.identity.netting_domain.key()
        )
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.ENTRY_REJECTED
    assert aggregate.entry_vacuum_id == vacuum.entry_vacuum_id
    assert [command.status for command in commands] == [
        ExchangeCommandStatus.SUPERSEDED
    ]
    assert reservation is not None and reservation.status == "released"
    assert exposure is not None and exposure.active_ticket_count == 0
    assert lane is not None and lane.ticket_id is None
    assert domain_active is False


@pytest.mark.asyncio
async def test_zero_fill_cancel_waits_for_durable_dispatch_and_order_absence(
    dispatch_engine,
) -> None:
    ticket = make_ticket()
    await seed_policy(dispatch_engine)
    await issue(dispatch_engine, ticket)
    await dispatch_for_ticket(
        dispatch_engine,
        AcceptingVenue(dispatch_engine),
        ticket.identity.ticket_id,
        now_ms=1_100,
    )
    vacuum = await open_entry_vacuum(dispatch_engine, ticket)
    open_order_snapshot = _position_snapshot(
        ticket,
        quantity=Decimal(0),
        average_entry_price=None,
        open_entry_order=True,
        observed_at_ms=vacuum.fenced_at_ms + 1,
    )

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        requested = await drain_strategy_entry_vacuum_once(
            uow,
            _request(
                ticket,
                now_ms=vacuum.fenced_at_ms + 1,
                position_snapshot=open_order_snapshot,
            ),
        )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        waiting = await drain_strategy_entry_vacuum_once(
            uow,
            _request(ticket, now_ms=vacuum.fenced_at_ms + 2),
        )
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )

    assert requested.status is VacuumDrainStatus.CANCEL_REQUESTED
    assert waiting.status is VacuumDrainStatus.WAITING_COMMAND
    cancel = next(
        command
        for command in commands
        if command.kind is ExchangeCommandKind.CANCEL_ORDER
    )
    assert cancel.status is ExchangeCommandStatus.PREPARED
    assert isinstance(cancel.payload, CancelCommandPayload)
    assert cancel.payload.purpose == "selection_vacuum_entry"
    assert cancel.payload.entry_vacuum_id == vacuum.entry_vacuum_id

    await dispatch_for_ticket(
        dispatch_engine,
        KindAwareAcceptingVenue(),
        ticket.identity.ticket_id,
        now_ms=vacuum.fenced_at_ms + 3,
    )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        still_waiting = await drain_strategy_entry_vacuum_once(
            uow,
            _request(ticket, now_ms=vacuum.fenced_at_ms + 4),
        )
        aggregate_after_cancel = await uow.aggregates.get(ticket.identity.ticket_id)

    assert still_waiting.status is VacuumDrainStatus.POSITION_FACTS_REQUIRED
    assert aggregate_after_cancel is not None
    assert aggregate_after_cancel.status is AggregateStatus.ENTRY_VACUUM_CANCEL_PENDING

    flat_snapshot = _position_snapshot(
        ticket,
        quantity=Decimal(0),
        average_entry_price=None,
        open_entry_order=False,
        observed_at_ms=vacuum.fenced_at_ms + 5,
    )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        absent = await drain_strategy_entry_vacuum_once(
            uow,
            _request(
                ticket,
                now_ms=vacuum.fenced_at_ms + 5,
                position_snapshot=flat_snapshot,
            ),
        )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        closed = await drain_strategy_entry_vacuum_once(
            uow,
            _request(ticket, now_ms=vacuum.fenced_at_ms + 6),
        )
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
        domain_active = await uow.entry_admission.has_active_ticket_in_domain(
            ticket.identity.netting_domain.key()
        )

    assert absent.status is VacuumDrainStatus.ORDER_ABSENCE_RECORDED
    assert closed.status is VacuumDrainStatus.ZERO_FILL_CLOSED
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.ENTRY_RECONCILED_ABSENT
    assert reservation is not None and reservation.status == "released"
    assert domain_active is False


@pytest.mark.asyncio
async def test_unknown_vacuum_cancel_blocks_then_reconciles_before_retry(
    dispatch_engine,
) -> None:
    ticket = make_ticket()
    await seed_policy(dispatch_engine)
    await issue(dispatch_engine, ticket)
    await dispatch_for_ticket(
        dispatch_engine,
        AcceptingVenue(dispatch_engine),
        ticket.identity.ticket_id,
        now_ms=1_100,
    )
    vacuum = await open_entry_vacuum(dispatch_engine, ticket)
    open_snapshot = _position_snapshot(
        ticket,
        quantity=Decimal(0),
        average_entry_price=None,
        open_entry_order=True,
        observed_at_ms=vacuum.fenced_at_ms + 1,
    )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        requested = await drain_strategy_entry_vacuum_once(
            uow,
            _request(
                ticket,
                now_ms=vacuum.fenced_at_ms + 1,
                position_snapshot=open_snapshot,
            ),
        )
    assert requested.status is VacuumDrainStatus.CANCEL_REQUESTED

    unknown = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        UnknownCancelVenue(),
        DispatchCommandRequest(
            worker_id="vacuum-cancel-dispatcher",
            ticket_id=ticket.identity.ticket_id,
            now_ms=vacuum.fenced_at_ms + 2,
            lease_until_ms=vacuum.fenced_at_ms + 5_002,
            timeout_seconds=1,
        ),
    )
    assert unknown.status is DispatchCommandStatus.OUTCOME_UNKNOWN
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        blocked = await drain_strategy_entry_vacuum_once(
            uow,
            _request(ticket, now_ms=vacuum.fenced_at_ms + 3),
        )
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
    assert blocked.status is VacuumDrainStatus.WAITING_UNKNOWN_OUTCOME
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.ENTRY_VACUUM_CANCEL_OUTCOME_UNKNOWN

    commands_before = await _commands(dispatch_engine, ticket)
    unknown_cancel = next(
        command
        for command in commands_before
        if command.kind is ExchangeCommandKind.CANCEL_ORDER
    )
    recovery = await recover_unknown_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        StaticTruthPort(
            VenueTruthSnapshot(
                lookup_status=VenueLookupStatus.VISIBLE,
                order=VenueOrderTruth(
                    exchange_order_id="venue-entry-1",
                    venue_client_order_id=unknown_cancel.venue_client_order_id,
                    exchange_instrument_id=(
                        ticket.identity.netting_domain.exchange_instrument_id
                    ),
                    position_side=ticket.identity.netting_domain.position_side,
                    order_side="buy",
                    quantity=ticket.quantity,
                    reduce_only=False,
                    order_namespace="regular",
                ),
                position_quantity=Decimal(0),
                matching_fill_quantity=Decimal(0),
                regular_open_client_order_ids=(
                    str(unknown_cancel.venue_client_order_id),
                ),
                conditional_open_client_order_ids=(),
                observed_at_ms=vacuum.fenced_at_ms + 4,
            )
        ),
        RecoverUnknownCommandRequest(
            command_id=unknown_cancel.command_id,
            now_ms=vacuum.fenced_at_ms + 4,
            visibility_deadline_ms=vacuum.fenced_at_ms + 3,
            timeout_seconds=1,
        ),
    )
    assert recovery.status is UnknownRecoveryStatus.CANCEL_TARGET_STILL_OPEN

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        retried = await drain_strategy_entry_vacuum_once(
            uow,
            _request(
                ticket,
                now_ms=vacuum.fenced_at_ms + 5,
                position_snapshot=open_snapshot.model_copy(
                    update={"observed_at_ms": vacuum.fenced_at_ms + 5}
                ),
            ),
        )
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands_after = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    assert retried.status is VacuumDrainStatus.CANCEL_REQUESTED
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.ENTRY_VACUUM_CANCEL_PENDING
    cancel_commands = [
        command
        for command in commands_after
        if command.kind is ExchangeCommandKind.CANCEL_ORDER
    ]
    assert [command.generation for command in cancel_commands] == [1, 2]
    assert cancel_commands[0].status is ExchangeCommandStatus.RECONCILED_ABSENT
    assert cancel_commands[1].status is ExchangeCommandStatus.PREPARED


@pytest.mark.asyncio
async def test_retained_partial_keeps_original_capacity_until_protected(
    dispatch_engine,
) -> None:
    ticket, vacuum, partial_qty = await _reach_retained_partial_pending(
        dispatch_engine
    )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
        exposure = await uow.entry_admission.get_account_exposure(
            ticket.identity.netting_domain.venue_id,
            ticket.identity.netting_domain.account_id,
        )
        lane = await uow.entry_admission.get_global_lane()
        domain_active = await uow.entry_admission.has_active_ticket_in_domain(
            ticket.identity.netting_domain.key()
        )
        drain_blocked = await uow.instrument_selection.entry_vacuum_has_drain_blockers(
            strategy_group_id=ticket.identity.runtime.strategy_group_id
        )
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.PROTECTION_PENDING
    assert aggregate.position_qty == partial_qty
    assert aggregate.tp1_target_qty == Decimal("0.001")
    assert aggregate.entry_materialization_kind == "VACUUM_PARTIAL_RETAINED"
    assert reservation is not None and reservation.status == "active"
    assert reservation.reserved_notional == ticket.notional
    assert reservation.reserved_risk == ticket.risk_at_stop
    assert exposure is not None and exposure.active_ticket_count == 1
    assert lane is not None and lane.ticket_id == ticket.identity.ticket_id
    assert domain_active is True
    assert drain_blocked is True

    await dispatch_for_ticket(
        dispatch_engine,
        KindAwareAcceptingVenue(),
        ticket.identity.ticket_id,
        now_ms=vacuum.fenced_at_ms + 5,
    )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        protected = await uow.aggregates.get(ticket.identity.ticket_id)
        reservation_after = await uow.budgets.get_for_ticket(
            ticket.identity.ticket_id
        )
        exposure_after = await uow.entry_admission.get_account_exposure(
            ticket.identity.netting_domain.venue_id,
            ticket.identity.netting_domain.account_id,
        )
        lane_after = await uow.entry_admission.get_global_lane()
        domain_after = await uow.entry_admission.has_active_ticket_in_domain(
            ticket.identity.netting_domain.key()
        )
        drain_blocked_after = (
            await uow.instrument_selection.entry_vacuum_has_drain_blockers(
                strategy_group_id=ticket.identity.runtime.strategy_group_id
            )
        )
    assert protected is not None
    assert protected.status is AggregateStatus.TP1_PENDING
    assert reservation_after is not None and reservation_after.status == "active"
    assert exposure_after is not None and exposure_after.active_ticket_count == 1
    assert lane_after is not None and lane_after.ticket_id is None
    assert domain_after is True
    assert drain_blocked_after is False


@pytest.mark.asyncio
async def test_retained_partial_initial_stop_rejection_requires_controlled_flatten(
    dispatch_engine,
) -> None:
    ticket, vacuum, partial_qty = await _reach_retained_partial_pending(
        dispatch_engine
    )

    rejected = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        RejectingVenue(),
        DispatchCommandRequest(
            worker_id="vacuum-retained-stop-dispatcher",
            ticket_id=ticket.identity.ticket_id,
            now_ms=vacuum.fenced_at_ms + 5,
            lease_until_ms=vacuum.fenced_at_ms + 5_005,
            timeout_seconds=1,
        ),
    )

    assert rejected.status is DispatchCommandStatus.REJECTED
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
        domain_active = await uow.entry_admission.has_active_ticket_in_domain(
            ticket.identity.netting_domain.key()
        )
        drain_blocked = await uow.instrument_selection.entry_vacuum_has_drain_blockers(
            strategy_group_id=ticket.identity.runtime.strategy_group_id
        )

    assert aggregate is not None
    assert aggregate.status is AggregateStatus.CONTROLLED_FLATTEN_PENDING
    assert aggregate.position_qty == partial_qty
    assert incident is not None
    assert incident.incident_kind == "vacuum_partial_initial_stop_rejected"
    assert [command.kind for command in commands] == [
        ExchangeCommandKind.ENTRY,
        ExchangeCommandKind.CANCEL_ORDER,
        ExchangeCommandKind.INITIAL_STOP,
        ExchangeCommandKind.CONTROLLED_FLATTEN,
    ]
    assert commands[-2].status is ExchangeCommandStatus.REJECTED
    assert commands[-1].status is ExchangeCommandStatus.PREPARED
    assert reservation is not None and reservation.status == "active"
    assert domain_active is True
    assert drain_blocked is True


def _request(
    ticket,
    *,
    now_ms: int,
    position_snapshot: PositionSnapshot | None = None,
) -> DrainStrategyEntryVacuumRequest:
    return DrainStrategyEntryVacuumRequest(
        strategy_group_id=ticket.identity.runtime.strategy_group_id,
        selection_spec_id=SELECTION_SPEC_ID,
        now_ms=now_ms,
        ticket_id=ticket.identity.ticket_id,
        position_snapshot=position_snapshot,
    )


def _position_snapshot(
    ticket,
    *,
    quantity: Decimal,
    average_entry_price: Decimal | None,
    open_entry_order: bool,
    observed_at_ms: int,
) -> PositionSnapshot:
    orders = (
        (
            VenueOrderSnapshot(
                exchange_order_id="venue-entry-1",
                venue_client_order_id="brc-entry-test",
                position_side=ticket.identity.netting_domain.position_side,
                reduce_only=False,
                order_namespace="regular",
            ),
        )
        if open_entry_order
        else ()
    )
    return PositionSnapshot(
        netting_domain=ticket.identity.netting_domain,
        quantity=quantity,
        average_entry_price=average_entry_price,
        open_orders=orders,
        observed_at_ms=observed_at_ms,
    )


async def _commands(engine, ticket):
    async with PostgresKernelUnitOfWork(engine) as uow:
        return await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )


async def _reach_retained_partial_pending(engine):
    ticket = _retained_partial_ticket()
    async with PostgresKernelUnitOfWork(engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1_000)
    await seed_policy(engine)
    await issue(engine, ticket, ticket_margin_budget=Decimal(90))
    await _seed_instrument_rules(engine, ticket)
    await dispatch_for_ticket(
        engine,
        AcceptingVenue(engine),
        ticket.identity.ticket_id,
        now_ms=1_100,
    )
    vacuum = await open_entry_vacuum(engine, ticket)
    partial_qty = Decimal("0.002")
    partial_open = _position_snapshot(
        ticket,
        quantity=partial_qty,
        average_entry_price=ticket.entry_reference_price,
        open_entry_order=True,
        observed_at_ms=vacuum.fenced_at_ms + 1,
    )
    async with PostgresKernelUnitOfWork(engine) as uow:
        requested = await drain_strategy_entry_vacuum_once(
            uow,
            _request(
                ticket,
                now_ms=vacuum.fenced_at_ms + 1,
                position_snapshot=partial_open,
            ),
        )
    assert requested.status is VacuumDrainStatus.CANCEL_REQUESTED
    await dispatch_for_ticket(
        engine,
        KindAwareAcceptingVenue(),
        ticket.identity.ticket_id,
        now_ms=vacuum.fenced_at_ms + 2,
    )
    partial_absent = partial_open.model_copy(
        update={
            "open_orders": (),
            "observed_at_ms": vacuum.fenced_at_ms + 3,
        }
    )
    async with PostgresKernelUnitOfWork(engine) as uow:
        absent = await drain_strategy_entry_vacuum_once(
            uow,
            _request(
                ticket,
                now_ms=vacuum.fenced_at_ms + 3,
                position_snapshot=partial_absent,
            ),
        )
    assert absent.status is VacuumDrainStatus.ORDER_ABSENCE_RECORDED
    async with PostgresKernelUnitOfWork(engine) as uow:
        retained = await drain_strategy_entry_vacuum_once(
            uow,
            _request(ticket, now_ms=vacuum.fenced_at_ms + 4),
        )
    assert retained.status is VacuumDrainStatus.PARTIAL_RETAINED_PROTECTION_REQUESTED
    return ticket, vacuum, partial_qty


def _retained_partial_ticket() -> TradeTicket:
    base = registered_sor_long_ticket()
    values = base.model_dump(mode="python")
    values.update(
        quantity=Decimal("0.004"),
        notional=Decimal(240),
        planned_stop_risk_budget=Decimal(4),
        post_fill_stop_risk_limit=Decimal("4.4"),
        reserved_margin=Decimal(48),
        risk_at_stop=Decimal(4),
        take_profit_quantities=(Decimal("0.002"),),
    )
    return TradeTicket.model_validate(values)


async def _seed_instrument_rules(engine, ticket) -> None:
    rules = await PreflightFacts().read_instrument_rules(
        InstrumentRulesRequest(
            venue_id=ticket.identity.netting_domain.venue_id,
            account_id=ticket.identity.netting_domain.account_id,
            exchange_instrument_id=(
                ticket.identity.netting_domain.exchange_instrument_id
            ),
            observed_at_ms=SESSION_START_MS,
            valid_for_ms=172_800_000,
        )
    )
    assert isinstance(rules.maintenance_margin_brackets[0], MaintenanceMarginBracket)
    async with PostgresKernelUnitOfWork(engine) as uow:
        await uow.signals.upsert_instrument_rules(
            venue_id=ticket.identity.netting_domain.venue_id,
            exchange_instrument_id=(
                ticket.identity.netting_domain.exchange_instrument_id
            ),
            quantity_step=rules.quantity_step,
            price_tick=rules.price_tick,
            min_quantity=rules.min_quantity,
            min_notional=rules.min_notional,
            exchange_max_leverage=rules.exchange_max_leverage,
            maintenance_margin_brackets=rules.maintenance_margin_brackets,
            maintenance_margin_brackets_digest=(
                rules.maintenance_margin_brackets_digest
            ),
            notional_coefficient=rules.notional_coefficient,
            notional_coefficient_certified=(
                rules.notional_coefficient_certified
            ),
            observed_at_ms=rules.observed_at_ms,
            valid_until_ms=rules.valid_until_ms,
        )
