from __future__ import annotations

from decimal import Decimal

import pytest

from tests.trading_kernel.integration import test_command_dispatch as dispatch_fixture
from src.trading_kernel.application.dispatch_exchange_command import (
    DispatchCommandRequest,
    DispatchCommandStatus,
    dispatch_one_command,
)
from src.trading_kernel.application.recover_unknown_command import (
    RecoverUnknownCommandRequest,
    recover_unknown_command,
)
from src.trading_kernel.application.ports import VenueTruthRequest
from src.trading_kernel.application.reconcile_ticket import (
    ExitTicketRequest,
    ReconcileTicketRequest,
    reconcile_ticket,
    request_exit,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import (
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandStatus,
    OrderCommandPayload,
)
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.events import (
    ControlledFlattenAbsenceConfirmed,
    ExitAbsenceConfirmed,
    InitialStopAbsenceConfirmed,
)
from src.trading_kernel.domain.venue_truth import (
    UnknownRecoveryStatus,
    VenueLookupStatus,
    VenueOrderTruth,
    VenueTruthSnapshot,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.integration.test_command_dispatch import (
    AcceptingVenue,
    SlowVenue,
    _issue,
    _reach_cancel_pending,
    _seed_policy,
)
from tests.trading_kernel.unit.test_ticket import _ticket


dispatch_engine = dispatch_fixture.dispatch_engine


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


@pytest.mark.asyncio
async def test_visible_unknown_entry_reconciles_submitted_without_redispatch(
    dispatch_engine,
) -> None:
    ticket, command = await _make_unknown_entry(dispatch_engine)
    truth = StaticTruthPort(
        VenueTruthSnapshot(
            lookup_status=VenueLookupStatus.VISIBLE,
            order=VenueOrderTruth(
                exchange_order_id="venue-entry-recovered",
                venue_client_order_id=command.venue_client_order_id,
                exchange_instrument_id=(
                    ticket.identity.netting_domain.exchange_instrument_id
                ),
                position_side="long",
                order_side="buy",
                quantity=ticket.quantity,
                reduce_only=False,
            ),
            position_quantity=Decimal("0"),
            matching_fill_quantity=Decimal("0"),
            regular_open_client_order_ids=(command.venue_client_order_id,),
            conditional_open_client_order_ids=(),
            observed_at_ms=2_100,
        )
    )

    result = await recover_unknown_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        truth,
        RecoverUnknownCommandRequest(
            command_id=command.command_id,
            now_ms=2_100,
            visibility_deadline_ms=2_000,
            timeout_seconds=1,
        ),
    )

    assert result.status is UnknownRecoveryStatus.RECONCILED_SUBMITTED
    assert len(truth.requests) == 1
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        persisted = await uow.exchange_commands.get(command.command_id)
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    assert persisted is not None
    assert persisted.status is ExchangeCommandStatus.RECONCILED_ACCEPTED
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.ENTRY_ACCEPTED
    assert aggregate.entry_exchange_order_id == "venue-entry-recovered"
    assert incident is None
    assert len(commands) == 1


@pytest.mark.asyncio
async def test_proven_absent_unknown_entry_closes_without_second_generation(
    dispatch_engine,
) -> None:
    ticket, command = await _make_unknown_entry(dispatch_engine)
    truth = StaticTruthPort(_absent_truth(observed_at_ms=2_100))

    result = await recover_unknown_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        truth,
        RecoverUnknownCommandRequest(
            command_id=command.command_id,
            now_ms=2_100,
            visibility_deadline_ms=2_000,
            timeout_seconds=1,
        ),
    )

    assert result.status is UnknownRecoveryStatus.RECONCILED_ABSENT
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        persisted = await uow.exchange_commands.get(command.command_id)
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
        lane = await uow.entry_admission.get_global_lane()
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
    assert persisted is not None
    assert persisted.status is ExchangeCommandStatus.RECONCILED_ABSENT
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.ENTRY_RECONCILED_ABSENT
    assert reservation is not None and reservation.status == "released"
    assert lane is not None and lane.status == "idle"
    assert incident is None
    assert len(commands) == 1


@pytest.mark.asyncio
async def test_unknown_entry_survives_restart_and_pending_visibility_never_dispatches(
    dispatch_engine,
) -> None:
    ticket, command = await _make_unknown_entry(dispatch_engine)
    truth = StaticTruthPort(_absent_truth(observed_at_ms=1_500))

    result = await recover_unknown_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        truth,
        RecoverUnknownCommandRequest(
            command_id=command.command_id,
            now_ms=1_500,
            visibility_deadline_ms=2_000,
            timeout_seconds=1,
        ),
    )

    assert result.status is UnknownRecoveryStatus.PENDING_VISIBILITY
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.ENTRY_OUTCOME_UNKNOWN
    assert len(commands) == 1
    assert commands[0].status is ExchangeCommandStatus.OUTCOME_UNKNOWN


@pytest.mark.asyncio
async def test_identity_contradiction_keeps_unknown_and_opens_hard_incident(
    dispatch_engine,
) -> None:
    ticket, command = await _make_unknown_entry(dispatch_engine)
    truth = StaticTruthPort(
        VenueTruthSnapshot(
            lookup_status=VenueLookupStatus.VISIBLE,
            order=VenueOrderTruth(
                exchange_order_id="venue-wrong-side",
                venue_client_order_id=command.venue_client_order_id,
                exchange_instrument_id=(
                    ticket.identity.netting_domain.exchange_instrument_id
                ),
                position_side="short",
                order_side="sell",
                quantity=ticket.quantity,
                reduce_only=False,
            ),
            position_quantity=Decimal("0"),
            matching_fill_quantity=Decimal("0"),
            regular_open_client_order_ids=(),
            conditional_open_client_order_ids=(),
            observed_at_ms=2_100,
        )
    )

    result = await recover_unknown_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        truth,
        RecoverUnknownCommandRequest(
            command_id=command.command_id,
            now_ms=2_100,
            visibility_deadline_ms=2_000,
            timeout_seconds=1,
        ),
    )

    assert result.status is UnknownRecoveryStatus.IDENTITY_CONTRADICTION
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
        persisted = await uow.exchange_commands.get(command.command_id)
    assert incident is not None
    assert incident.first_blocker == "hard_safety_stop"
    assert incident.incident_kind == "venue_identity_contradiction"
    assert persisted is not None
    assert persisted.status is ExchangeCommandStatus.OUTCOME_UNKNOWN

    recovered = await recover_unknown_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        StaticTruthPort(_visible_truth(ticket, command, "venue-entry-recovered")),
        RecoverUnknownCommandRequest(
            command_id=command.command_id,
            now_ms=2_200,
            visibility_deadline_ms=2_000,
            timeout_seconds=1,
        ),
    )

    assert recovered.status is UnknownRecoveryStatus.RECONCILED_SUBMITTED
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.ENTRY_ACCEPTED
    assert incident is not None
    assert incident.incident_kind == "venue_identity_contradiction"


@pytest.mark.asyncio
async def test_visible_unknown_initial_stop_recovers_protection_without_exit(
    dispatch_engine,
) -> None:
    ticket, command = await _make_unknown_initial_stop(dispatch_engine)

    result = await recover_unknown_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        StaticTruthPort(_visible_truth(ticket, command, "venue-stop-recovered")),
        RecoverUnknownCommandRequest(
            command_id=command.command_id,
            now_ms=2_500,
            visibility_deadline_ms=2_400,
            timeout_seconds=1,
        ),
    )

    assert result.status is UnknownRecoveryStatus.RECONCILED_SUBMITTED
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
        lane = await uow.entry_admission.get_global_lane()
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.POSITION_PROTECTED
    assert aggregate.initial_stop_exchange_order_id == "venue-stop-recovered"
    assert all(item.kind is not ExchangeCommandKind.EXIT for item in commands)
    assert incident is None
    assert lane is not None and lane.status == "idle"


@pytest.mark.asyncio
async def test_absent_unknown_initial_stop_prepares_one_controlled_exit(
    dispatch_engine,
) -> None:
    ticket, command = await _make_unknown_initial_stop(dispatch_engine)

    result = await recover_unknown_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        StaticTruthPort(
            _absent_truth(
                observed_at_ms=2_500,
                position_quantity=ticket.quantity,
            )
        ),
        RecoverUnknownCommandRequest(
            command_id=command.command_id,
            now_ms=2_500,
            visibility_deadline_ms=2_400,
            timeout_seconds=1,
        ),
    )

    assert result.status is UnknownRecoveryStatus.RECONCILED_ABSENT
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        events = await uow.events.list_for_ticket(ticket.identity.ticket_id)
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.EXIT_PENDING
    assert [item.status for item in commands if item.kind is ExchangeCommandKind.INITIAL_STOP] == [
        ExchangeCommandStatus.RECONCILED_ABSENT
    ]
    assert [item.status for item in commands if item.kind is ExchangeCommandKind.EXIT] == [
        ExchangeCommandStatus.PREPARED
    ]
    assert isinstance(events[-1], InitialStopAbsenceConfirmed)
    assert incident is not None and incident.incident_kind == "initial_stop_absent"


@pytest.mark.asyncio
async def test_visible_unknown_exit_recovers_accepted_without_duplicate_command(
    dispatch_engine,
) -> None:
    ticket, command = await _make_unknown_exit(dispatch_engine)

    result = await recover_unknown_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        StaticTruthPort(_visible_truth(ticket, command, "venue-exit-recovered")),
        RecoverUnknownCommandRequest(
            command_id=command.command_id,
            now_ms=3_300,
            visibility_deadline_ms=3_200,
            timeout_seconds=1,
        ),
    )

    assert result.status is UnknownRecoveryStatus.RECONCILED_SUBMITTED
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None and aggregate.status is AggregateStatus.EXIT_ACCEPTED
    assert aggregate.exit_exchange_order_id == "venue-exit-recovered"
    assert len([item for item in commands if item.kind is ExchangeCommandKind.EXIT]) == 1
    assert incident is None


@pytest.mark.asyncio
async def test_absent_unknown_exit_remains_nonflat_and_does_not_auto_retry(
    dispatch_engine,
) -> None:
    ticket, command = await _make_unknown_exit(dispatch_engine)

    result = await recover_unknown_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        StaticTruthPort(
            _absent_truth(
                observed_at_ms=3_300,
                position_quantity=ticket.quantity,
            )
        ),
        RecoverUnknownCommandRequest(
            command_id=command.command_id,
            now_ms=3_300,
            visibility_deadline_ms=3_200,
            timeout_seconds=1,
        ),
    )

    assert result.status is UnknownRecoveryStatus.RECONCILED_ABSENT
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        events = await uow.events.list_for_ticket(ticket.identity.ticket_id)
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None and aggregate.status is AggregateStatus.EXIT_REJECTED
    assert aggregate.position_qty == ticket.quantity
    exit_commands = [item for item in commands if item.kind is ExchangeCommandKind.EXIT]
    assert len(exit_commands) == 1
    assert exit_commands[0].status is ExchangeCommandStatus.RECONCILED_ABSENT
    assert isinstance(events[-1], ExitAbsenceConfirmed)
    assert incident is None


@pytest.mark.asyncio
async def test_visible_unknown_controlled_flatten_recovers_without_second_flatten(
    dispatch_engine,
) -> None:
    ticket, command = await _make_unknown_controlled_flatten(dispatch_engine)

    result = await recover_unknown_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        StaticTruthPort(_visible_truth(ticket, command, "venue-flatten-recovered")),
        RecoverUnknownCommandRequest(
            command_id=command.command_id,
            now_ms=2_700,
            visibility_deadline_ms=2_600,
            timeout_seconds=1,
        ),
    )

    assert result.status is UnknownRecoveryStatus.RECONCILED_SUBMITTED
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.CONTROLLED_FLATTEN_ACCEPTED
    flatten_commands = [
        item for item in commands if item.kind is ExchangeCommandKind.CONTROLLED_FLATTEN
    ]
    assert len(flatten_commands) == 1
    assert incident is not None
    assert incident.incident_kind == "unsupported_partial_entry_fill"


@pytest.mark.asyncio
async def test_absent_unknown_controlled_flatten_keeps_nonflat_incident(
    dispatch_engine,
) -> None:
    ticket, command = await _make_unknown_controlled_flatten(dispatch_engine)

    result = await recover_unknown_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        StaticTruthPort(
            _absent_truth(
                observed_at_ms=2_700,
                position_quantity=Decimal("0.0004"),
            )
        ),
        RecoverUnknownCommandRequest(
            command_id=command.command_id,
            now_ms=2_700,
            visibility_deadline_ms=2_600,
            timeout_seconds=1,
        ),
    )

    assert result.status is UnknownRecoveryStatus.RECONCILED_ABSENT
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        events = await uow.events.list_for_ticket(ticket.identity.ticket_id)
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.CONTROLLED_FLATTEN_REJECTED
    assert aggregate.position_qty == Decimal("0.0004")
    assert isinstance(events[-1], ControlledFlattenAbsenceConfirmed)
    assert incident is not None
    assert incident.incident_kind == "controlled_flatten_absent"


@pytest.mark.asyncio
async def test_absent_unknown_cancel_confirms_target_removal_and_resolves_unknown(
    dispatch_engine,
) -> None:
    ticket, command = await _make_unknown_cancel(dispatch_engine)

    result = await recover_unknown_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        StaticTruthPort(_absent_truth(observed_at_ms=3_500)),
        RecoverUnknownCommandRequest(
            command_id=command.command_id,
            now_ms=3_500,
            visibility_deadline_ms=3_400,
            timeout_seconds=1,
        ),
    )

    assert result.status is UnknownRecoveryStatus.RECONCILED_ABSENT
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        persisted = await uow.exchange_commands.get(command.command_id)
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.RECONCILIATION_PENDING
    assert aggregate.pending_cancel_exchange_order_id is None
    assert persisted is not None
    assert persisted.status is ExchangeCommandStatus.RECONCILED_ABSENT
    assert incident is None


async def _make_unknown_entry(engine):
    ticket = _ticket()
    await _seed_policy(engine)
    await _issue(engine, ticket)
    dispatched = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine),
        SlowVenue(),
        DispatchCommandRequest(
            worker_id="dispatcher-unknown",
            now_ms=1_100,
            lease_until_ms=1_200,
            timeout_seconds=0.01,
        ),
    )
    assert dispatched.status is DispatchCommandStatus.OUTCOME_UNKNOWN
    async with PostgresKernelUnitOfWork(engine) as uow:
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    return ticket, commands[0]


async def _make_unknown_initial_stop(engine):
    ticket = _ticket()
    await _seed_policy(engine)
    await _issue(engine, ticket)
    accepting = AcceptingVenue(engine)
    await _dispatch(engine, accepting, worker_id="entry-dispatcher", now_ms=1_100)
    async with PostgresKernelUnitOfWork(engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price="60000",
                    observed_at_ms=2_100,
                ),
            ),
        )
    await _dispatch(
        engine,
        SlowVenue(),
        worker_id="stop-dispatcher",
        now_ms=2_200,
        timeout_seconds=0.01,
    )
    return ticket, await _command_of_kind(engine, ticket, ExchangeCommandKind.INITIAL_STOP)


async def _make_unknown_exit(engine):
    ticket, _ = await _make_unknown_initial_stop(engine)
    stop_command = await _command_of_kind(engine, ticket, ExchangeCommandKind.INITIAL_STOP)
    await recover_unknown_command(
        lambda: PostgresKernelUnitOfWork(engine),
        StaticTruthPort(_visible_truth(ticket, stop_command, "venue-stop-1")),
        RecoverUnknownCommandRequest(
            command_id=stop_command.command_id,
            now_ms=2_400,
            visibility_deadline_ms=2_300,
            timeout_seconds=1,
        ),
    )
    async with PostgresKernelUnitOfWork(engine) as uow:
        await request_exit(
            uow,
            ExitTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                reason="strategy_exit",
                requested_at_ms=3_000,
            ),
        )
    await _dispatch(
        engine,
        SlowVenue(),
        worker_id="exit-dispatcher",
        now_ms=3_100,
        timeout_seconds=0.01,
    )
    return ticket, await _command_of_kind(engine, ticket, ExchangeCommandKind.EXIT)


async def _make_unknown_controlled_flatten(engine):
    ticket = _ticket()
    await _seed_policy(engine)
    await _issue(engine, ticket)
    accepting = AcceptingVenue(engine)
    await _dispatch(engine, accepting, worker_id="entry-dispatcher", now_ms=1_100)
    async with PostgresKernelUnitOfWork(engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=Decimal("0.0004"),
                    average_entry_price="60000",
                    observed_at_ms=2_100,
                ),
            ),
        )
    await _dispatch(engine, accepting, worker_id="cancel-dispatcher", now_ms=2_200)
    await _dispatch(
        engine,
        SlowVenue(),
        worker_id="flatten-dispatcher",
        now_ms=2_300,
        timeout_seconds=0.01,
    )
    return ticket, await _command_of_kind(
        engine,
        ticket,
        ExchangeCommandKind.CONTROLLED_FLATTEN,
    )


async def _make_unknown_cancel(engine):
    ticket = _ticket()
    await _seed_policy(engine)
    await _reach_cancel_pending(engine, ticket, AcceptingVenue(engine))
    await _dispatch(
        engine,
        SlowVenue(),
        worker_id="cancel-dispatcher",
        now_ms=3_300,
        timeout_seconds=0.01,
    )
    return ticket, await _command_of_kind(engine, ticket, ExchangeCommandKind.CANCEL_ORDER)


async def _dispatch(
    engine,
    venue,
    *,
    worker_id: str,
    now_ms: int,
    timeout_seconds: float = 1,
) -> None:
    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine),
        venue,
        DispatchCommandRequest(
            worker_id=worker_id,
            now_ms=now_ms,
            lease_until_ms=now_ms + 5_000,
            timeout_seconds=timeout_seconds,
        ),
    )
    assert result.status is not DispatchCommandStatus.NO_COMMAND


async def _command_of_kind(
    engine,
    ticket,
    kind: ExchangeCommandKind,
) -> ExchangeCommand:
    async with PostgresKernelUnitOfWork(engine) as uow:
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    matches = [item for item in commands if item.kind is kind]
    assert len(matches) == 1
    return matches[0]


def _visible_truth(
    ticket,
    command: ExchangeCommand,
    exchange_order_id: str,
) -> VenueTruthSnapshot:
    assert isinstance(command.payload, OrderCommandPayload)
    return VenueTruthSnapshot(
        lookup_status=VenueLookupStatus.VISIBLE,
        order=VenueOrderTruth(
            exchange_order_id=exchange_order_id,
            venue_client_order_id=command.venue_client_order_id,
            exchange_instrument_id=(
                ticket.identity.netting_domain.exchange_instrument_id
            ),
            position_side=ticket.identity.netting_domain.position_side,
            order_side=command.payload.side,
            quantity=command.payload.quantity,
            reduce_only=command.payload.reduce_only,
        ),
        position_quantity=Decimal("0"),
        matching_fill_quantity=Decimal("0"),
        regular_open_client_order_ids=(command.venue_client_order_id,),
        conditional_open_client_order_ids=(),
        observed_at_ms=2_500,
    )


def _absent_truth(
    *,
    observed_at_ms: int,
    position_quantity: Decimal = Decimal("0"),
) -> VenueTruthSnapshot:
    return VenueTruthSnapshot(
        lookup_status=VenueLookupStatus.ABSENT,
        position_quantity=position_quantity,
        matching_fill_quantity=Decimal("0"),
        regular_open_client_order_ids=(),
        conditional_open_client_order_ids=(),
        observed_at_ms=observed_at_ms,
    )
