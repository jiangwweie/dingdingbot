from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
import sqlalchemy as sa

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
from src.trading_kernel.application.maintain_ticket_lifecycle import (
    LifecycleMaintenanceRequest,
    TicketLifecycleFacts,
    maintain_ticket_lifecycle,
)
from src.trading_kernel.application.ports import (
    LeverageTruthRequest,
    LeverageTruthSnapshot,
    VenueCommandRequest,
    VenueSetLeverageRequest,
    VenueTruthRequest,
)
from src.trading_kernel.application.reconcile_ticket import (
    ReconcileTicketRequest,
    ReconcileTicketStatus,
    reconcile_ticket,
)
from src.trading_kernel.application.recover_unknown_command import (
    RecoverUnknownCommandRequest,
    recover_unknown_command,
)
from src.trading_kernel.application.recover_vacuum_late_fill import (
    RecoverVacuumLateFillRequest,
    RecoverVacuumLateFillStatus,
    recover_vacuum_late_fill,
)
from src.trading_kernel.application.runtime_facts import (
    InstrumentRulesRequest,
    PositionSnapshotRequest,
)
from src.trading_kernel.application.settle_ticket import (
    RecordTradeReviewRequest,
    SettleTicketRequest,
    record_trade_review,
    settle_ticket,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommandKind,
    ExchangeCommandResult,
    ExchangeCommandStatus,
    SetLeverageCommandResult,
)
from src.trading_kernel.domain.cross_margin_stress import MaintenanceMarginBracket
from src.trading_kernel.domain.events import PostFillStressAssessed
from src.trading_kernel.domain.exit_policy import registered_event_exit_bindings
from src.trading_kernel.domain.generic_selection_spec import (
    SpecNumericInstallationEvidence,
    generic_selection_spec,
)
from src.trading_kernel.domain.identities import TicketIdentity
from src.trading_kernel.domain.orb_session_selection import (
    ORB_SELECTION_SPEC_ID as SELECTION_SPEC_ID,
)
from src.trading_kernel.domain.position import PositionSnapshot, VenueOrderSnapshot
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.domain.strategy_entry_vacuum import StrategyEntryVacuum
from src.trading_kernel.domain.ticket import TradeTicket, build_ticket_id
from src.trading_kernel.domain.venue_truth import (
    UnknownRecoveryStatus,
    VenueLookupStatus,
    VenueOrderTruth,
    VenueTruthSnapshot,
)
from src.trading_kernel.infrastructure.pg_models import strategy_entry_vacuums_current
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    seed_strategy_registry,
)
from src.trading_kernel.interfaces.reconciliation_worker import (
    ReconciliationWorkerRequest,
    ReconciliationWorkerStatus,
    run_reconciliation_worker_once,
)
from tests.trading_kernel.support.capacity_claims import make_stress_evidence
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


class NoVenueTruth:
    async def lookup_command_truth(self, request):
        del request
        raise AssertionError("Vacuum position-fact drain must not read command truth")

    async def read_configured_leverage(self, request):
        del request
        raise AssertionError("Vacuum position-fact drain must not read leverage")


class RecordingVacuumPositionSource:
    def __init__(self, snapshot: PositionSnapshot) -> None:
        self.snapshot = snapshot
        self.requests: list[PositionSnapshotRequest] = []

    async def read_position_snapshot(
        self,
        request: PositionSnapshotRequest,
    ) -> PositionSnapshot:
        self.requests.append(request)
        return self.snapshot


class FailingVacuumPositionSource:
    async def read_position_snapshot(
        self,
        request: PositionSnapshotRequest,
    ) -> PositionSnapshot:
        del request
        raise TimeoutError("test_position_snapshot_timeout")


class ConcurrentVacuumPositionSource(RecordingVacuumPositionSource):
    def __init__(self, engine, ticket, snapshot: PositionSnapshot) -> None:
        super().__init__(snapshot)
        self._engine = engine
        self._ticket = ticket

    async def read_position_snapshot(
        self,
        request: PositionSnapshotRequest,
    ) -> PositionSnapshot:
        snapshot = await super().read_position_snapshot(request)
        async with PostgresKernelUnitOfWork(self._engine) as uow:
            advanced = await drain_strategy_entry_vacuum_once(
                uow,
                _request(
                    self._ticket,
                    now_ms=snapshot.observed_at_ms,
                    position_snapshot=snapshot,
                ),
            )
        assert advanced.status is VacuumDrainStatus.CANCEL_REQUESTED
        return snapshot


def _ticket_for_group(ticket: TradeTicket, group: str | None) -> TradeTicket:
    if group is not None:
        spec = generic_selection_spec(group)
        runtime = ticket.identity.runtime.model_copy(update={"strategy_group_id":spec.strategy_group_id,
            "strategy_version_id":spec.strategy_version_id,"event_spec_id":spec.event_spec_id})
        domain = ticket.identity.netting_domain.model_copy(update={"position_side":spec.position_side})
        identity = TicketIdentity(**{**ticket.identity.model_dump(),"runtime":runtime,"netting_domain":domain,
            "ticket_id":build_ticket_id(signal_event_id=ticket.identity.signal_event_id,runtime=runtime,netting_domain=domain)})
        binding = next(b for b in registered_event_exit_bindings() if b.event_spec_id == spec.event_spec_id)
        ticket = TradeTicket.model_validate({**ticket.model_dump(),"identity":identity,
            "exposure_family":"rally_failure_short" if spec.position_side == "short" else "long_continuation","family_ticket_limit":1,
            "initial_stop_price":2*ticket.entry_reference_price-ticket.initial_stop_price if spec.position_side == "short" else ticket.initial_stop_price,
            "take_profit_prices":tuple(2*ticket.entry_reference_price-price for price in ticket.take_profit_prices) if spec.position_side == "short" else ticket.take_profit_prices,
            "exit_policy_id":binding.exit_profile_id,"exit_policy_semantic_hash":binding.exit_profile_semantic_hash,
            "exit_binding_id":binding.exit_binding_id,"exit_binding_semantic_hash":binding.binding_semantic_hash,
            "pre_tp1_reclaim_price":None,"exposure_session_end_ms":None})
    return ticket


async def _open_group_vacuum(dispatch_engine, ticket, group):
    if group is not None:
        spec = generic_selection_spec(group)
        async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
            await uow.instrument_selection.install_generic_spec(spec,installed_at_ms=2_000,
                certification=SpecNumericInstallationEvidence(selection_spec_id=spec.selection_spec_id,
                    algorithm_semantic_digest=spec.algorithm_semantic_digest,checked_cutoffs=463 if spec.cadence_hours==4 else 1852,mismatch_count=0,
                    source_archive_count=96,reference_commit="f65d72fa92580de4b8c0323f4106d5975b97f4eb",
                    common_numeric_authority="PASS",sor_golden="PASS",spec_cert="PASS"))
        # Exact negative-fence prerequisite; this test starts at an issued Ticket,
        # not at the Selection/Coordinator producer boundary.
        vacuum = StrategyEntryVacuum(entry_vacuum_id=f"vacuum:{group}:prepared",strategy_group_id=spec.strategy_group_id,
            selection_spec_id=spec.selection_spec_id,period_anchor_ms=100*3_600_000,source_generation_id=None,
            state="DRAINING_ENTRY",fenced_at_ms=101*3_600_000,drained_at_ms=None,resolved_at_ms=None,
            first_blocker="TEST_SELECTION_RECONFIGURATION",projection_version=1)
        async with dispatch_engine.begin() as conn:
            await conn.execute(sa.insert(strategy_entry_vacuums_current).values(**vacuum.model_dump(mode="json")))
    else:
        vacuum = await open_entry_vacuum(dispatch_engine, ticket)

    return vacuum


@pytest.mark.asyncio
@pytest.mark.parametrize("group", [None, "CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
@pytest.mark.parametrize("sent", [False, True, "unknown"])
async def test_entry_vacuum_clears_prepared_or_zero_fill_entry(
    dispatch_engine, group: str | None, sent: bool | str,
) -> None:
    ticket = _ticket_for_group(make_ticket(), group)
    await seed_policy(dispatch_engine,event_spec_id=ticket.identity.runtime.event_spec_id)
    await issue(dispatch_engine, ticket)
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        issued_ticket = await uow.tickets.get(ticket.identity.ticket_id)
        assert issued_ticket is not None
        assert issued_ticket.identity == ticket.identity
    if sent:
        await dispatch_for_ticket(dispatch_engine,AcceptingVenue(dispatch_engine),ticket.identity.ticket_id,now_ms=1_100)
    vacuum = await _open_group_vacuum(dispatch_engine, ticket, group)

    if sent == "unknown":
        await _assert_unknown_cancel(dispatch_engine,ticket,vacuum)
    elif sent:
        await _assert_zero_fill_cancel(dispatch_engine,ticket,vacuum)
    if sent:
        async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
            terminal_ticket = await uow.tickets.get(ticket.identity.ticket_id)
            assert terminal_ticket is not None and terminal_ticket.status.value == "entry_reconciled_absent"
            assert terminal_ticket.model_dump(exclude={"status"}) == issued_ticket.model_dump(exclude={"status"})
        return

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        result = await drain_strategy_entry_vacuum_once(
            uow,
            _request(ticket, now_ms=vacuum.fenced_at_ms + 1).model_copy(update={"selection_spec_id":vacuum.selection_spec_id}),
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
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        terminal_ticket = await uow.tickets.get(ticket.identity.ticket_id)
        assert terminal_ticket is not None and terminal_ticket.status.value == "entry_rejected"
        assert terminal_ticket.model_dump(exclude={"status"}) == issued_ticket.model_dump(exclude={"status"})


async def _assert_zero_fill_cancel(
    dispatch_engine, ticket, vacuum, *, late_after_order_absence: str | None = None,
    worker_for_terminal: bool = False,
    late_quantity: Decimal | None = None,
) -> None:
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
    if late_after_order_absence:
        positive = _position_snapshot(
            ticket,
            quantity=((late_quantity or ticket.quantity)
                if late_after_order_absence == "position" else Decimal(0)),
            average_entry_price=(
                ticket.entry_reference_price if late_after_order_absence == "position" else None
            ),
            open_entry_order=late_after_order_absence == "order",
            observed_at_ms=vacuum.fenced_at_ms + 6,
        )
        if worker_for_terminal:
            worker = await run_reconciliation_worker_once(
                lambda: PostgresKernelUnitOfWork(dispatch_engine), NoVenueTruth(),
                RecordingVacuumPositionSource(positive),
                _reconciliation_request(vacuum.fenced_at_ms + 6).model_copy(update={
                    "entry_vacuum_strategy_group_id": None,
                    "entry_vacuum_selection_spec_id": None,
                    "entry_vacuum_scan_all": True,
                }),
            )
            assert worker.status is ReconciliationWorkerStatus.VACUUM_DRAIN_WAITING
            assert worker.detail == VacuumDrainStatus.BLOCKED.value
        async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
            blocked = (
                None if worker_for_terminal else await drain_strategy_entry_vacuum_once(
                    uow, _request(ticket, now_ms=vacuum.fenced_at_ms + 6,
                        position_snapshot=positive),
                )
            )
            aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
            reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
            incident = await uow.incidents.get_open_for_ticket_kind(
                ticket.identity.ticket_id, "vacuum_post_absence_contradiction",
            )
            commands = await uow.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
        assert worker_for_terminal or blocked is not None and blocked.status is VacuumDrainStatus.BLOCKED
        assert aggregate is not None and aggregate.status is AggregateStatus.ENTRY_VACUUM_CANCELLED
        assert reservation is not None and reservation.status == "active"
        assert incident is not None and incident.entry_block_scope.value == "account_capacity"
        assert [command.kind for command in commands] == [
            ExchangeCommandKind.ENTRY, ExchangeCommandKind.CANCEL_ORDER,
        ]
        async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
            later_flat = await drain_strategy_entry_vacuum_once(
                uow, _request(ticket, now_ms=vacuum.fenced_at_ms + 7,
                    position_snapshot=flat_snapshot.model_copy(update={
                        "observed_at_ms": vacuum.fenced_at_ms + 7,
                    })),
            )
            still_active = await uow.entry_admission.has_active_ticket_in_domain(
                ticket.identity.netting_domain.key()
            )
        assert later_flat.status is VacuumDrainStatus.BLOCKED
        assert still_active
        return
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        needs_fresh = await drain_strategy_entry_vacuum_once(
            uow,
            _request(ticket, now_ms=vacuum.fenced_at_ms + 6),
        )
    assert needs_fresh.status is VacuumDrainStatus.POSITION_FACTS_REQUIRED
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        stale = await drain_strategy_entry_vacuum_once(
            uow,
            _request(ticket, now_ms=vacuum.fenced_at_ms + 6,
                position_snapshot=flat_snapshot),
        )
    assert stale.status is VacuumDrainStatus.POSITION_FACTS_REQUIRED

    fresh_flat = _position_snapshot(
        ticket,
        quantity=Decimal(0),
        average_entry_price=None,
        open_entry_order=False,
        observed_at_ms=vacuum.fenced_at_ms + 6,
    )
    if worker_for_terminal:
        worker = await run_reconciliation_worker_once(
            lambda: PostgresKernelUnitOfWork(dispatch_engine), NoVenueTruth(),
            RecordingVacuumPositionSource(fresh_flat),
            _reconciliation_request(vacuum.fenced_at_ms + 6).model_copy(update={
                "entry_vacuum_strategy_group_id": None,
                "entry_vacuum_selection_spec_id": None,
                "entry_vacuum_scan_all": True,
            }),
        )
        assert worker.status is ReconciliationWorkerStatus.VACUUM_DRAIN_ADVANCED
        assert worker.detail == VacuumDrainStatus.ZERO_FILL_CLOSED.value
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        closed = (
            None if worker_for_terminal else await drain_strategy_entry_vacuum_once(
                uow,
                _request(
                    ticket,
                    now_ms=vacuum.fenced_at_ms + 6,
                    position_snapshot=fresh_flat,
                ),
            )
        )
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
        domain_active = await uow.entry_admission.has_active_ticket_in_domain(
            ticket.identity.netting_domain.key()
        )

    assert absent.status is VacuumDrainStatus.ORDER_ABSENCE_RECORDED
    assert worker_for_terminal or closed is not None and closed.status is VacuumDrainStatus.ZERO_FILL_CLOSED
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.ENTRY_RECONCILED_ABSENT
    assert reservation is not None and reservation.status == "released"
    assert domain_active is False
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        final_commands = await uow.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
        assert [command.kind for command in final_commands].count(ExchangeCommandKind.ENTRY) == 1
        assert [command.kind for command in final_commands].count(ExchangeCommandKind.CANCEL_ORDER) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("group", [None, "CPM-RO-001", "BRF2-001"])
@pytest.mark.parametrize("late_kind", ["position", "order"])
async def test_vacuum_does_not_close_when_positive_position_appears_after_order_absence(
    dispatch_engine, group: str | None, late_kind: str,
) -> None:
    ticket = _ticket_for_group(make_ticket(), group)
    await seed_policy(dispatch_engine, event_spec_id=ticket.identity.runtime.event_spec_id)
    await issue(dispatch_engine, ticket)
    await dispatch_for_ticket(dispatch_engine, AcceptingVenue(dispatch_engine),
        ticket.identity.ticket_id, now_ms=1_100)
    vacuum = await _open_group_vacuum(dispatch_engine, ticket, group)
    await _assert_zero_fill_cancel(
        dispatch_engine, ticket, vacuum, late_after_order_absence=late_kind,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("group", [None, "CPM-RO-001", "BRF2-001"])
@pytest.mark.parametrize("via_worker", [False, True])
async def test_exact_late_fill_rejoins_original_ticket_and_prepares_protection(
    dispatch_engine, group: str | None, via_worker: bool,
) -> None:
    ticket = _ticket_for_group(make_ticket(), group)
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1_000)
    await seed_policy(dispatch_engine, event_spec_id=ticket.identity.runtime.event_spec_id)
    await issue(dispatch_engine, ticket)
    await dispatch_for_ticket(dispatch_engine, AcceptingVenue(dispatch_engine),
        ticket.identity.ticket_id, now_ms=1_100)
    vacuum = await _open_group_vacuum(dispatch_engine, ticket, group)
    await _assert_zero_fill_cancel(
        dispatch_engine, ticket, vacuum, late_after_order_absence="position",
    )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None and aggregate.entry_exchange_order_id is not None
    entry = next(command for command in commands if command.kind is ExchangeCommandKind.ENTRY)
    position = _position_snapshot(
        ticket, quantity=ticket.quantity, average_entry_price=ticket.entry_reference_price,
        open_entry_order=False, observed_at_ms=vacuum.fenced_at_ms + 7,
    )
    truth = VenueTruthSnapshot(
        lookup_status=VenueLookupStatus.VISIBLE,
        order=VenueOrderTruth(
            exchange_order_id=aggregate.entry_exchange_order_id,
            venue_client_order_id=str(entry.venue_client_order_id),
            exchange_instrument_id=ticket.identity.netting_domain.exchange_instrument_id,
            position_side=ticket.identity.netting_domain.position_side,
            order_side="buy" if ticket.identity.netting_domain.position_side == "long" else "sell",
            quantity=ticket.quantity, reduce_only=False,
            order_namespace="regular", is_open=False,
        ),
        position_quantity=ticket.quantity,
        matching_fill_quantity=ticket.quantity,
        matching_fill_average_price=ticket.entry_reference_price,
        matching_fill_complete=True,
        regular_open_client_order_ids=(), conditional_open_client_order_ids=(),
        observed_at_ms=vacuum.fenced_at_ms + 8,
    )
    source = RecordingVacuumPositionSource(position)
    truth_port = StaticTruthPort(truth)
    if via_worker:
        worker_request = _reconciliation_request(vacuum.fenced_at_ms + 7).model_copy(update={
            "entry_vacuum_strategy_group_id": None,
            "entry_vacuum_selection_spec_id": None,
            "entry_vacuum_scan_all": True,
        })
        recovered_worker = await run_reconciliation_worker_once(
            lambda: PostgresKernelUnitOfWork(dispatch_engine), truth_port,
            source, worker_request,
        )
        assert recovered_worker.status is ReconciliationWorkerStatus.VACUUM_DRAIN_ADVANCED
        assert recovered_worker.detail == "late_fill:exact_original_entry_fill"
    else:
        recovered = await recover_vacuum_late_fill(
            lambda: PostgresKernelUnitOfWork(dispatch_engine),
            source, truth_port,
            RecoverVacuumLateFillRequest(ticket_id=ticket.identity.ticket_id,
                worker_id="late-fill-test",runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=vacuum.fenced_at_ms + 7, timeout_seconds=1),
        )
        assert recovered.status is RecoverVacuumLateFillStatus.ATTRIBUTED
    if via_worker:
        advanced_worker = await run_reconciliation_worker_once(
            lambda:PostgresKernelUnitOfWork(dispatch_engine),truth_port,source,
            _reconciliation_request(vacuum.fenced_at_ms+9).model_copy(update={
                "entry_vacuum_strategy_group_id":None,
                "entry_vacuum_selection_spec_id":None,
                "entry_vacuum_scan_all":True,
            }),
        )
        assert advanced_worker.status is ReconciliationWorkerStatus.VACUUM_DRAIN_ADVANCED
        assert advanced_worker.detail == VacuumDrainStatus.FULL_FILL_PROTECTION_REQUESTED.value
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        advanced = (
            None if via_worker else await drain_strategy_entry_vacuum_once(
                uow, _request(ticket, now_ms=vacuum.fenced_at_ms + 9),
            )
        )
        new_aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        new_commands = await uow.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
        events = await uow.events.list_for_ticket(ticket.identity.ticket_id)
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
        active = await uow.entry_admission.has_active_ticket_in_domain(
            ticket.identity.netting_domain.key())
        monitor = await uow.monitors.get(
            f"vacuum-post-absence:{ticket.identity.ticket_id}"
        )
    assert via_worker or advanced is not None and advanced.status is VacuumDrainStatus.FULL_FILL_PROTECTION_REQUESTED
    assert new_aggregate is not None and new_aggregate.status is AggregateStatus.PROTECTION_PENDING
    assert reservation is not None and reservation.status == "active" and active
    assert [command.kind for command in new_commands] == [
        ExchangeCommandKind.ENTRY, ExchangeCommandKind.CANCEL_ORDER,
        ExchangeCommandKind.INITIAL_STOP,
    ]
    assert sum(type(event).__name__ == "VacuumLateFillAttributed" for event in events) == 1
    assert monitor is not None and monitor.owner_status.value == "processing"

    class TimedVenue:
        now_ms = vacuum.fenced_at_ms + 10

        async def execute(self, request):
            async with PostgresKernelUnitOfWork(dispatch_engine) as durable_uow:
                command = await durable_uow.exchange_commands.get(request.command_id)
                assert command is not None and command.status is ExchangeCommandStatus.CLAIMED
            return ExchangeCommandResult(
                status=ExchangeCommandStatus.ACCEPTED,
                observed_at_ms=self.now_ms,
                exchange_order_id=f"late-{request.kind.value}-1",
            )

        async def set_leverage(self, request):
            del request
            raise AssertionError("late fill protection must not mutate leverage")

    venue = TimedVenue()
    dispatched_stop = await dispatch_one_command(
        lambda:PostgresKernelUnitOfWork(dispatch_engine),venue,
        DispatchCommandRequest(worker_id="late-fill-stop",ticket_id=ticket.identity.ticket_id,
            now_ms=vacuum.fenced_at_ms+10,lease_until_ms=vacuum.fenced_at_ms+5_010,
            timeout_seconds=1,runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,admission_snapshot_validity_ms=1_000),
        entry_facts_source=PreflightFacts(),
        clock_ms=lambda: vacuum.fenced_at_ms+10,
    )
    assert dispatched_stop.status is DispatchCommandStatus.ACCEPTED, dispatched_stop
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        pending_stress = await uow.aggregates.get(ticket.identity.ticket_id)
        assert pending_stress is not None
        assert pending_stress.status is AggregateStatus.POST_FILL_RISK_PENDING
        stress = PostFillStressAssessed(
            event_id=f"event:{ticket.identity.ticket_id}:{pending_stress.last_event_sequence+1}",
            ticket_id=ticket.identity.ticket_id,
            sequence=pending_stress.last_event_sequence+1,
            occurred_at_ms=vacuum.fenced_at_ms+11,
            status="passed",evidence=make_stress_evidence(pending_stress.ticket),
            owner_policy_id=pending_stress.ticket.owner_policy_id,
            owner_policy_version=pending_stress.ticket.owner_policy_version,
            filled_qty=pending_stress.position_qty,
            average_fill_price=pending_stress.average_fill_price,
            initial_stop_price=pending_stress.ticket.initial_stop_price,
            initial_stop_exchange_order_id=pending_stress.initial_stop_exchange_order_id,
        )
        await uow.commit_reduction(
            event=stress,reduction=reduce_event(pending_stress,stress),
            expected_version=pending_stress.version,
        )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        after_stop = await uow.aggregates.get(ticket.identity.ticket_id)
        after_stop_commands = await uow.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
    assert after_stop is not None and after_stop.status is AggregateStatus.TP1_PENDING, (
        after_stop, after_stop_commands,
    )
    assert len(after_stop_commands) == 4
    assert {command.kind for command in after_stop_commands} == {
        ExchangeCommandKind.ENTRY,ExchangeCommandKind.CANCEL_ORDER,
        ExchangeCommandKind.INITIAL_STOP,ExchangeCommandKind.TAKE_PROFIT,
    }
    venue.now_ms = vacuum.fenced_at_ms + 12
    dispatched_tp1 = await dispatch_one_command(
        lambda:PostgresKernelUnitOfWork(dispatch_engine),venue,
        DispatchCommandRequest(worker_id="late-fill-tp1",ticket_id=ticket.identity.ticket_id,
            now_ms=vacuum.fenced_at_ms+12,lease_until_ms=vacuum.fenced_at_ms+5_012,
            timeout_seconds=1,runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,admission_snapshot_validity_ms=1_000),
        entry_facts_source=PreflightFacts(),
        clock_ms=lambda: vacuum.fenced_at_ms+12,
    )
    assert dispatched_tp1.status is DispatchCommandStatus.ACCEPTED, dispatched_tp1
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        protected = await uow.aggregates.get(ticket.identity.ticket_id)
        protected_commands = await uow.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
        incident = await uow.incidents.get_open_for_ticket_kind(
            ticket.identity.ticket_id,"vacuum_post_absence_contradiction")
    assert protected is not None and protected.status is AggregateStatus.POSITION_PROTECTED
    assert protected.protected_qty == ticket.quantity
    assert [command.kind for command in protected_commands] == [
        ExchangeCommandKind.ENTRY, ExchangeCommandKind.CANCEL_ORDER,
        ExchangeCommandKind.INITIAL_STOP, ExchangeCommandKind.TAKE_PROFIT,
    ]
    assert incident is not None
    if not via_worker:
        await _finish_exact_late_fill_ticket(
            dispatch_engine, ticket, vacuum, venue,
        )


async def _finish_exact_late_fill_ticket(dispatch_engine, ticket, vacuum, venue) -> None:
    base_time = vacuum.fenced_at_ms + 100
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        runner = await maintain_ticket_lifecycle(
            uow,
            LifecycleMaintenanceRequest(
                ticket_id=ticket.identity.ticket_id,
                facts=TicketLifecycleFacts(
                    position_quantity=ticket.quantity-ticket.take_profit_quantities[0],
                    tp1_filled_quantity=ticket.take_profit_quantities[0],
                    tp1_average_fill_price=ticket.take_profit_prices[0],
                    allocated_entry_fee_quote=Decimal("0.01"),
                    exit_taker_fee_rate=Decimal("0.001"),
                    price_tick=Decimal("0.01"),
                    market_facts=None,
                    observed_at_ms=base_time,
                ),
                now_ms=base_time,
            ),
        )
    assert runner.status.value == "break_even_requested"

    for offset in (10, 20):
        venue.now_ms = base_time + offset
        dispatched = await dispatch_one_command(
            lambda:PostgresKernelUnitOfWork(dispatch_engine),venue,
            DispatchCommandRequest(
                worker_id=f"late-fill-runner-{offset}",
                ticket_id=ticket.identity.ticket_id,
                now_ms=venue.now_ms,
                lease_until_ms=venue.now_ms+5_000,
                timeout_seconds=1,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                admission_snapshot_validity_ms=1_000,
            ),
            entry_facts_source=PreflightFacts(),
            clock_ms=lambda: venue.now_ms,
        )
        assert dispatched.status is DispatchCommandStatus.ACCEPTED, dispatched

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        external_flat = await reconcile_ticket(uow,ReconcileTicketRequest(
            ticket_id=ticket.identity.ticket_id,
            snapshot=_position_snapshot(ticket,quantity=Decimal(0),
                average_entry_price=None,open_entry_order=False,
                observed_at_ms=base_time+30),
        ))
    assert external_flat.status is ReconcileTicketStatus.EXTERNAL_FLAT_INCIDENT
    venue.now_ms = base_time + 40
    dispatched_cleanup = await dispatch_one_command(
        lambda:PostgresKernelUnitOfWork(dispatch_engine),venue,
        DispatchCommandRequest(
            worker_id="late-fill-cleanup",ticket_id=ticket.identity.ticket_id,
            now_ms=venue.now_ms,lease_until_ms=venue.now_ms+5_000,
            timeout_seconds=1,runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,admission_snapshot_validity_ms=1_000,
        ),entry_facts_source=PreflightFacts(),
        clock_ms=lambda: venue.now_ms,
    )
    assert dispatched_cleanup.status is DispatchCommandStatus.ACCEPTED
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        matched = await reconcile_ticket(uow,ReconcileTicketRequest(
            ticket_id=ticket.identity.ticket_id,
            snapshot=_position_snapshot(ticket,quantity=Decimal(0),
                average_entry_price=None,open_entry_order=False,
                observed_at_ms=base_time+50),
        ))
        settled = await settle_ticket(uow,SettleTicketRequest(
            ticket_id=ticket.identity.ticket_id,settled_at_ms=base_time+60))
        reviewed = await record_trade_review(uow,RecordTradeReviewRequest(
            ticket_id=ticket.identity.ticket_id,
            review_id=f"review:late-fill-{ticket.identity.runtime.strategy_group_id}",
            outcome="closed",metrics={"realized_pnl":"1.25"},
            decision_impact={"strategy_action":"keep"},recorded_at_ms=base_time+70))
        terminal = await uow.aggregates.get(ticket.identity.ticket_id)
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
        active = await uow.entry_admission.has_active_ticket_in_domain(
            ticket.identity.netting_domain.key())
    assert matched.status is ReconcileTicketStatus.MATCHED
    assert settled.status.value == "budget_settled"
    assert reviewed.status.value == "review_recorded"
    assert terminal is not None and terminal.status is AggregateStatus.TERMINAL
    assert incident is None and reservation is not None and reservation.status == "released"
    assert not active


@pytest.mark.asyncio
@pytest.mark.parametrize("group,expected", [
    (None, VacuumDrainStatus.PARTIAL_RETAINED_PROTECTION_REQUESTED),
    ("MPG-001", VacuumDrainStatus.PARTIAL_FLATTEN_REQUESTED),
])
async def test_exact_partial_late_fill_uses_existing_vacuum_reduction(
    dispatch_engine, group: str | None, expected: VacuumDrainStatus,
) -> None:
    ticket = _ticket_for_group(_retained_partial_ticket(), group)
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1_000)
    await seed_policy(dispatch_engine, event_spec_id=ticket.identity.runtime.event_spec_id)
    await issue(dispatch_engine, ticket, ticket_margin_budget=Decimal(90))
    await _seed_instrument_rules(dispatch_engine, ticket)
    await dispatch_for_ticket(dispatch_engine, AcceptingVenue(dispatch_engine),
        ticket.identity.ticket_id, now_ms=1_100)
    vacuum = await _open_group_vacuum(dispatch_engine, ticket, group)
    partial_qty = Decimal("0.002")
    await _assert_zero_fill_cancel(
        dispatch_engine, ticket, vacuum, late_after_order_absence="position",
        late_quantity=partial_qty,
    )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None and aggregate.entry_exchange_order_id is not None
    entry = next(command for command in commands if command.kind is ExchangeCommandKind.ENTRY)
    position = _position_snapshot(ticket, quantity=partial_qty,
        average_entry_price=ticket.entry_reference_price, open_entry_order=False,
        observed_at_ms=vacuum.fenced_at_ms + 7)
    truth = VenueTruthSnapshot(
        lookup_status=VenueLookupStatus.VISIBLE,
        order=VenueOrderTruth(
            exchange_order_id=aggregate.entry_exchange_order_id,
            venue_client_order_id=str(entry.venue_client_order_id),
            exchange_instrument_id=ticket.identity.netting_domain.exchange_instrument_id,
            position_side=ticket.identity.netting_domain.position_side,
            order_side="buy" if ticket.identity.netting_domain.position_side == "long" else "sell",
            quantity=ticket.quantity, reduce_only=False,
            order_namespace="regular", is_open=False,
        ),
        position_quantity=partial_qty,
        matching_fill_quantity=partial_qty,
        matching_fill_average_price=ticket.entry_reference_price,
        matching_fill_complete=True,
        regular_open_client_order_ids=(), conditional_open_client_order_ids=(),
        observed_at_ms=vacuum.fenced_at_ms + 8,
    )
    recovered = await recover_vacuum_late_fill(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        RecordingVacuumPositionSource(position), StaticTruthPort(truth),
        RecoverVacuumLateFillRequest(ticket_id=ticket.identity.ticket_id,
            worker_id="late-fill-test",runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            now_ms=vacuum.fenced_at_ms + 7, timeout_seconds=1),
    )
    assert recovered.status is RecoverVacuumLateFillStatus.ATTRIBUTED
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        advanced = await drain_strategy_entry_vacuum_once(
            uow, _request(ticket, now_ms=vacuum.fenced_at_ms + 9),
        )
        persisted = await uow.aggregates.get(ticket.identity.ticket_id)
        persisted_commands = await uow.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
    assert advanced.status is expected
    assert persisted is not None and persisted.position_qty == partial_qty
    assert reservation is not None and reservation.status == "active"
    assert len([command for command in persisted_commands if command.kind is ExchangeCommandKind.ENTRY]) == 1
    if expected is VacuumDrainStatus.PARTIAL_RETAINED_PROTECTION_REQUESTED:
        assert persisted.status is AggregateStatus.PROTECTION_PENDING
        assert persisted_commands[-1].kind is ExchangeCommandKind.INITIAL_STOP
    else:
        assert persisted.status is AggregateStatus.CONTROLLED_FLATTEN_PENDING
        assert persisted_commands[-1].kind is ExchangeCommandKind.CONTROLLED_FLATTEN
        await dispatch_for_ticket(
            dispatch_engine,KindAwareAcceptingVenue(),ticket.identity.ticket_id,
            now_ms=vacuum.fenced_at_ms+10,
        )
        async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
            flattened = await reconcile_ticket(uow,ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=_position_snapshot(ticket,quantity=Decimal(0),
                    average_entry_price=None,open_entry_order=False,
                    observed_at_ms=vacuum.fenced_at_ms+11),
            ))
            matched = await reconcile_ticket(uow,ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=_position_snapshot(ticket,quantity=Decimal(0),
                    average_entry_price=None,open_entry_order=False,
                    observed_at_ms=vacuum.fenced_at_ms+12),
            ))
            settled = await settle_ticket(uow,SettleTicketRequest(
                ticket_id=ticket.identity.ticket_id,settled_at_ms=vacuum.fenced_at_ms+13))
            reviewed = await record_trade_review(uow,RecordTradeReviewRequest(
                ticket_id=ticket.identity.ticket_id,
                review_id="review:late-partial-flatten-mpg",
                outcome="closed",metrics={"realized_pnl":"-1.0"},
                decision_impact={"strategy_action":"review"},
                recorded_at_ms=vacuum.fenced_at_ms+14))
            terminal = await uow.aggregates.get(ticket.identity.ticket_id)
            incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
            released = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
            active = await uow.entry_admission.has_active_ticket_in_domain(
                ticket.identity.netting_domain.key())
        assert flattened.status is ReconcileTicketStatus.POSITION_FLAT_RECORDED
        assert matched.status is ReconcileTicketStatus.MATCHED
        assert settled.status.value == "budget_settled"
        assert reviewed.status.value == "review_recorded"
        assert terminal is not None and terminal.status is AggregateStatus.TERMINAL
        assert incident is None and released is not None and released.status == "released"
        assert not active


@pytest.mark.asyncio
async def test_late_fill_recovery_keeps_incident_and_vacuum_on_wrong_venue_identity(
    dispatch_engine,
) -> None:
    ticket = make_ticket()
    await seed_policy(dispatch_engine)
    await issue(dispatch_engine, ticket)
    await dispatch_for_ticket(dispatch_engine, AcceptingVenue(dispatch_engine),
        ticket.identity.ticket_id, now_ms=1_100)
    vacuum = await open_entry_vacuum(dispatch_engine, ticket)
    await _assert_zero_fill_cancel(
        dispatch_engine, ticket, vacuum, late_after_order_absence="position",
    )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands_before = await uow.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
        events_before = await uow.events.list_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None and aggregate.entry_exchange_order_id is not None
    entry = next(command for command in commands_before if command.kind is ExchangeCommandKind.ENTRY)
    position = _position_snapshot(ticket,quantity=ticket.quantity,
        average_entry_price=ticket.entry_reference_price,open_entry_order=False,
        observed_at_ms=vacuum.fenced_at_ms+7)
    wrong_truth = VenueTruthSnapshot(
        lookup_status=VenueLookupStatus.VISIBLE,
        order=VenueOrderTruth(exchange_order_id=aggregate.entry_exchange_order_id,
            venue_client_order_id="wrong-client-id",
            exchange_instrument_id=ticket.identity.netting_domain.exchange_instrument_id,
            position_side=ticket.identity.netting_domain.position_side,
            order_side="buy",quantity=ticket.quantity,reduce_only=False,is_open=False),
        position_quantity=ticket.quantity,matching_fill_quantity=ticket.quantity,
        matching_fill_average_price=ticket.entry_reference_price,
        matching_fill_complete=True,
        regular_open_client_order_ids=(),conditional_open_client_order_ids=(),
        observed_at_ms=vacuum.fenced_at_ms+8,
    )
    result = await recover_vacuum_late_fill(
        lambda:PostgresKernelUnitOfWork(dispatch_engine),
        RecordingVacuumPositionSource(position),StaticTruthPort(wrong_truth),
        RecoverVacuumLateFillRequest(ticket_id=ticket.identity.ticket_id,
            worker_id="late-fill-test",runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            now_ms=vacuum.fenced_at_ms+7,timeout_seconds=1),
    )
    assert result.status is RecoverVacuumLateFillStatus.UNVERIFIED
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        after = await uow.aggregates.get(ticket.identity.ticket_id)
        commands_after = await uow.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
        events_after = await uow.events.list_for_ticket(ticket.identity.ticket_id)
        incident = await uow.incidents.get_open_for_ticket_kind(
            ticket.identity.ticket_id,"vacuum_post_absence_contradiction")
        position_after = await uow.positions.get(ticket.identity.netting_domain.key())
    assert after is not None and after.status is AggregateStatus.ENTRY_VACUUM_CANCELLED
    assert after.position_qty == 0
    assert commands_after == commands_before and events_after == events_before
    assert incident is not None and position_after is not None and position_after.quantity == 0
    assert entry.venue_client_order_id != wrong_truth.order.venue_client_order_id


@pytest.mark.asyncio
async def test_late_fill_recovery_rechecks_runtime_identity_after_external_reads(
    dispatch_engine,
) -> None:
    ticket = make_ticket()
    await seed_policy(dispatch_engine)
    await issue(dispatch_engine, ticket)
    await dispatch_for_ticket(dispatch_engine, AcceptingVenue(dispatch_engine),
        ticket.identity.ticket_id, now_ms=1_100)
    vacuum = await open_entry_vacuum(dispatch_engine, ticket)
    await _assert_zero_fill_cancel(
        dispatch_engine, ticket, vacuum, late_after_order_absence="position",
    )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None and aggregate.entry_exchange_order_id is not None
    entry = next(command for command in commands if command.kind is ExchangeCommandKind.ENTRY)
    position = _position_snapshot(ticket,quantity=ticket.quantity,
        average_entry_price=ticket.entry_reference_price,open_entry_order=False,
        observed_at_ms=vacuum.fenced_at_ms+7)
    truth = VenueTruthSnapshot(
        lookup_status=VenueLookupStatus.VISIBLE,
        order=VenueOrderTruth(exchange_order_id=aggregate.entry_exchange_order_id,
            venue_client_order_id=str(entry.venue_client_order_id),
            exchange_instrument_id=ticket.identity.netting_domain.exchange_instrument_id,
            position_side=ticket.identity.netting_domain.position_side,
            order_side="buy",quantity=ticket.quantity,reduce_only=False,is_open=False),
        position_quantity=ticket.quantity,matching_fill_quantity=ticket.quantity,
        matching_fill_average_price=ticket.entry_reference_price,
        matching_fill_complete=True,
        regular_open_client_order_ids=(),conditional_open_client_order_ids=(),
        observed_at_ms=vacuum.fenced_at_ms+8,
    )

    class DriftDuringRead(RecordingVacuumPositionSource):
        async def read_position_snapshot(self, request):
            result = await super().read_position_snapshot(request)
            async with dispatch_engine.begin() as conn:
                await conn.execute(sa.text(
                    "UPDATE brc_runtime_capabilities_current SET certified_commit=:commit "
                    "WHERE capability_key='exchange_commands'"
                ), {"commit":"f"*40})
            return result

    recovered = await recover_vacuum_late_fill(
        lambda:PostgresKernelUnitOfWork(dispatch_engine),
        DriftDuringRead(position),StaticTruthPort(truth),
        RecoverVacuumLateFillRequest(ticket_id=ticket.identity.ticket_id,
            worker_id="late-fill-test",runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            now_ms=vacuum.fenced_at_ms+7,timeout_seconds=1),
    )
    assert recovered.status is RecoverVacuumLateFillStatus.UNVERIFIED
    assert recovered.reason_code == "runtime_fenced"
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        after = await uow.aggregates.get(ticket.identity.ticket_id)
        events = await uow.events.list_for_ticket(ticket.identity.ticket_id)
        incident = await uow.incidents.get_open_for_ticket_kind(
            ticket.identity.ticket_id,"vacuum_post_absence_contradiction")
    assert after is not None and after.status is AggregateStatus.ENTRY_VACUUM_CANCELLED
    assert after.position_qty == 0 and incident is not None
    assert not any(type(event).__name__ == "VacuumLateFillAttributed" for event in events)


@pytest.mark.asyncio
async def test_concurrent_exact_late_fill_recovery_appends_one_event(dispatch_engine) -> None:
    ticket = make_ticket()
    await seed_policy(dispatch_engine)
    await issue(dispatch_engine, ticket)
    await dispatch_for_ticket(dispatch_engine, AcceptingVenue(dispatch_engine),
        ticket.identity.ticket_id, now_ms=1_100)
    vacuum = await open_entry_vacuum(dispatch_engine, ticket)
    await _assert_zero_fill_cancel(
        dispatch_engine, ticket, vacuum, late_after_order_absence="position",
    )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None and aggregate.entry_exchange_order_id is not None
    entry = next(command for command in commands if command.kind is ExchangeCommandKind.ENTRY)
    source = RecordingVacuumPositionSource(_position_snapshot(ticket,
        quantity=ticket.quantity,average_entry_price=ticket.entry_reference_price,
        open_entry_order=False,observed_at_ms=vacuum.fenced_at_ms+7))
    truth = StaticTruthPort(VenueTruthSnapshot(
        lookup_status=VenueLookupStatus.VISIBLE,
        order=VenueOrderTruth(exchange_order_id=aggregate.entry_exchange_order_id,
            venue_client_order_id=str(entry.venue_client_order_id),
            exchange_instrument_id=ticket.identity.netting_domain.exchange_instrument_id,
            position_side=ticket.identity.netting_domain.position_side,
            order_side="buy",quantity=ticket.quantity,reduce_only=False,is_open=False),
        position_quantity=ticket.quantity,matching_fill_quantity=ticket.quantity,
        matching_fill_average_price=ticket.entry_reference_price,
        matching_fill_complete=True,
        regular_open_client_order_ids=(),conditional_open_client_order_ids=(),
        observed_at_ms=vacuum.fenced_at_ms+8,
    ))
    request = RecoverVacuumLateFillRequest(ticket_id=ticket.identity.ticket_id,
        worker_id="late-fill-concurrent",runtime_commit="kernel-test-head",
        schema_revision=CURRENT_SCHEMA_REVISION,
        now_ms=vacuum.fenced_at_ms+7,timeout_seconds=1)
    results = await asyncio.gather(*(
        recover_vacuum_late_fill(
            lambda:PostgresKernelUnitOfWork(dispatch_engine),source,truth,request,
        ) for _ in range(2)
    ))
    assert sum(result.status is RecoverVacuumLateFillStatus.ATTRIBUTED
        for result in results) == 1
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        events = await uow.events.list_for_ticket(ticket.identity.ticket_id)
        commands_after = await uow.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
        frozen = await uow.tickets.get(ticket.identity.ticket_id)
    assert sum(type(event).__name__ == "VacuumLateFillAttributed" for event in events) == 1
    assert commands_after == commands
    assert frozen is not None and frozen.identity == ticket.identity


@pytest.mark.asyncio
async def test_worker_late_fill_retry_is_bounded_and_then_attributes_exact_entry(
    dispatch_engine,
) -> None:
    ticket = make_ticket()
    await seed_policy(dispatch_engine)
    await issue(dispatch_engine, ticket)
    await dispatch_for_ticket(dispatch_engine, AcceptingVenue(dispatch_engine),
        ticket.identity.ticket_id, now_ms=1_100)
    vacuum = await open_entry_vacuum(dispatch_engine, ticket)
    await _assert_zero_fill_cancel(
        dispatch_engine, ticket, vacuum, late_after_order_absence="position",
    )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None and aggregate.entry_exchange_order_id is not None
    entry = next(command for command in commands if command.kind is ExchangeCommandKind.ENTRY)
    source = RecordingVacuumPositionSource(_position_snapshot(
        ticket, quantity=ticket.quantity, average_entry_price=ticket.entry_reference_price,
        open_entry_order=False, observed_at_ms=vacuum.fenced_at_ms+7,
    ))
    truth = StaticTruthPort(VenueTruthSnapshot(
        lookup_status=VenueLookupStatus.VISIBLE,
        order=VenueOrderTruth(
            exchange_order_id=aggregate.entry_exchange_order_id,
            venue_client_order_id="wrong-client-id",
            exchange_instrument_id=ticket.identity.netting_domain.exchange_instrument_id,
            position_side=ticket.identity.netting_domain.position_side,
            order_side="buy", quantity=ticket.quantity, reduce_only=False,
            order_namespace="regular", is_open=False,
        ),
        position_quantity=ticket.quantity, matching_fill_quantity=ticket.quantity,
        matching_fill_average_price=ticket.entry_reference_price,
        matching_fill_complete=True,
        regular_open_client_order_ids=(), conditional_open_client_order_ids=(),
        observed_at_ms=vacuum.fenced_at_ms+8,
    ))

    async def tick(at_ms: int):
        return await run_reconciliation_worker_once(
            lambda:PostgresKernelUnitOfWork(dispatch_engine),truth,source,
            _reconciliation_request(at_ms).model_copy(update={
                "entry_vacuum_strategy_group_id":None,
                "entry_vacuum_selection_spec_id":None,
                "entry_vacuum_scan_all":True,
            }),
        )

    unverified = await tick(vacuum.fenced_at_ms+7)
    await tick(vacuum.fenced_at_ms+8)
    assert unverified.status is ReconciliationWorkerStatus.VACUUM_DRAIN_WAITING
    assert len(truth.requests) == 1

    retry_at = vacuum.fenced_at_ms + 30_008
    source.snapshot = source.snapshot.model_copy(update={"observed_at_ms":retry_at})
    assert truth.truth.order is not None
    truth.truth = truth.truth.model_copy(update={
        "order":truth.truth.order.model_copy(update={
            "venue_client_order_id":str(entry.venue_client_order_id),
        }),
        "observed_at_ms":retry_at+1,
    })
    attributed = await tick(retry_at)
    assert attributed.status is ReconciliationWorkerStatus.VACUUM_DRAIN_ADVANCED
    assert attributed.detail == "late_fill:exact_original_entry_fill"
    assert len(truth.requests) == 2
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        updated = await uow.aggregates.get(ticket.identity.ticket_id)
        events = await uow.events.list_for_ticket(ticket.identity.ticket_id)
        retry_monitor = await uow.monitors.get(
            f"vacuum-late-fill-retry:{ticket.identity.ticket_id}"
        )
    assert updated is not None and updated.position_qty == ticket.quantity
    assert sum(type(event).__name__ == "VacuumLateFillAttributed" for event in events) == 1
    assert retry_monitor is not None and retry_monitor.owner_status.value == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize("via_worker", [False, True])
async def test_exact_post_absence_no_fill_proof_closes_incident_without_new_command(
    dispatch_engine, via_worker: bool,
) -> None:
    ticket = make_ticket()
    await seed_policy(dispatch_engine)
    await issue(dispatch_engine, ticket)
    await dispatch_for_ticket(dispatch_engine, AcceptingVenue(dispatch_engine),
        ticket.identity.ticket_id, now_ms=1_100)
    vacuum = await open_entry_vacuum(dispatch_engine, ticket)
    await _assert_zero_fill_cancel(
        dispatch_engine, ticket, vacuum, late_after_order_absence="position",
    )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None and aggregate.entry_exchange_order_id is not None
    entry = next(command for command in commands if command.kind is ExchangeCommandKind.ENTRY)
    flat = _position_snapshot(ticket,quantity=Decimal(0),average_entry_price=None,
        open_entry_order=False,observed_at_ms=vacuum.fenced_at_ms+7)
    truth = VenueTruthSnapshot(
        lookup_status=VenueLookupStatus.VISIBLE,
        order=VenueOrderTruth(
            exchange_order_id=aggregate.entry_exchange_order_id,
            venue_client_order_id=str(entry.venue_client_order_id),
            exchange_instrument_id=ticket.identity.netting_domain.exchange_instrument_id,
            position_side=ticket.identity.netting_domain.position_side,
            order_side="buy",quantity=ticket.quantity,reduce_only=False,
            order_namespace="regular",is_open=False,
        ),
        position_quantity=Decimal(0),matching_fill_quantity=Decimal(0),
        matching_fill_complete=True,
        regular_open_client_order_ids=(),conditional_open_client_order_ids=(),
        observed_at_ms=vacuum.fenced_at_ms+8,
    )
    if via_worker:
        worked = await run_reconciliation_worker_once(
            lambda:PostgresKernelUnitOfWork(dispatch_engine),StaticTruthPort(truth),
            RecordingVacuumPositionSource(flat),
            _reconciliation_request(vacuum.fenced_at_ms+7).model_copy(update={
                "entry_vacuum_strategy_group_id":None,
                "entry_vacuum_selection_spec_id":None,
                "entry_vacuum_scan_all":True,
            }),
        )
        assert worked.status is ReconciliationWorkerStatus.VACUUM_DRAIN_ADVANCED
        assert worked.detail == "late_fill:exact_original_entry_no_fill"
    else:
        result = await recover_vacuum_late_fill(
            lambda:PostgresKernelUnitOfWork(dispatch_engine),
            RecordingVacuumPositionSource(flat),StaticTruthPort(truth),
            RecoverVacuumLateFillRequest(ticket_id=ticket.identity.ticket_id,
                worker_id="late-fill-test",runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=vacuum.fenced_at_ms+7,timeout_seconds=1),
        )
        assert result.status is RecoverVacuumLateFillStatus.NO_FILL_CLOSED
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        closed = await uow.aggregates.get(ticket.identity.ticket_id)
        commands_after = await uow.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
        events = await uow.events.list_for_ticket(ticket.identity.ticket_id)
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
        active = await uow.entry_admission.has_active_ticket_in_domain(
            ticket.identity.netting_domain.key())
        open_incident = await uow.incidents.get_open_for_ticket_kind(
            ticket.identity.ticket_id,"vacuum_post_absence_contradiction")
        monitor = await uow.monitors.get(
            f"vacuum-post-absence:{ticket.identity.ticket_id}"
        )
    assert closed is not None and closed.status is AggregateStatus.ENTRY_RECONCILED_ABSENT
    assert reservation is not None and reservation.status == "released" and not active
    assert commands_after == commands
    assert sum(type(event).__name__ == "VacuumPostAbsenceNoFillVerified" for event in events) == 1
    assert open_incident is None
    assert monitor is not None and monitor.owner_status.value == "completed"
    repeated = await recover_vacuum_late_fill(
        lambda:PostgresKernelUnitOfWork(dispatch_engine),
        RecordingVacuumPositionSource(flat),StaticTruthPort(truth),
        RecoverVacuumLateFillRequest(ticket_id=ticket.identity.ticket_id,
            worker_id="late-fill-test",runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            now_ms=vacuum.fenced_at_ms+9,timeout_seconds=1),
    )
    assert repeated.status is RecoverVacuumLateFillStatus.NO_CHANGE


@pytest.mark.asyncio
@pytest.mark.parametrize("group", [None, "CPM-RO-001", "BRF2-001"])
async def test_reconciliation_worker_drains_sor_and_generic_zero_fill_vacuums(
    dispatch_engine, group: str | None,
) -> None:
    ticket = _ticket_for_group(make_ticket(), group)
    await seed_policy(dispatch_engine, event_spec_id=ticket.identity.runtime.event_spec_id)
    await issue(dispatch_engine, ticket)
    await dispatch_for_ticket(dispatch_engine, AcceptingVenue(dispatch_engine),
        ticket.identity.ticket_id, now_ms=1_100)
    vacuum = await _open_group_vacuum(dispatch_engine, ticket, group)
    await _assert_zero_fill_cancel(
        dispatch_engine, ticket, vacuum, worker_for_terminal=True,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("group", [None, "CPM-RO-001", "BRF2-001"])
async def test_reconciliation_worker_keeps_vacuum_fenced_on_post_absence_position(
    dispatch_engine, group: str | None,
) -> None:
    ticket = _ticket_for_group(make_ticket(), group)
    await seed_policy(dispatch_engine, event_spec_id=ticket.identity.runtime.event_spec_id)
    await issue(dispatch_engine, ticket)
    await dispatch_for_ticket(dispatch_engine, AcceptingVenue(dispatch_engine),
        ticket.identity.ticket_id, now_ms=1_100)
    vacuum = await _open_group_vacuum(dispatch_engine, ticket, group)
    await _assert_zero_fill_cancel(
        dispatch_engine, ticket, vacuum, late_after_order_absence="position",
        worker_for_terminal=True,
    )


@pytest.mark.asyncio
async def test_global_vacuum_scan_skips_earlier_scope_without_entry_ticket(
    dispatch_engine,
) -> None:
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1_000)
    empty_ticket = _ticket_for_group(make_ticket(), "BRF2-001")
    active_ticket = _ticket_for_group(make_ticket(), "CPM-RO-001")
    await seed_policy(dispatch_engine, event_spec_id=active_ticket.identity.runtime.event_spec_id)
    await issue(dispatch_engine, active_ticket)
    await dispatch_for_ticket(dispatch_engine, AcceptingVenue(dispatch_engine),
        active_ticket.identity.ticket_id, now_ms=1_100)
    await _open_group_vacuum(dispatch_engine, empty_ticket, "BRF2-001")
    vacuum = await _open_group_vacuum(dispatch_engine, active_ticket, "CPM-RO-001")
    open_order = _position_snapshot(
        active_ticket, quantity=Decimal(0), average_entry_price=None,
        open_entry_order=True, observed_at_ms=vacuum.fenced_at_ms + 1,
    )

    result = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(dispatch_engine), NoVenueTruth(),
        RecordingVacuumPositionSource(open_order),
        _reconciliation_request(vacuum.fenced_at_ms + 1).model_copy(update={
            "entry_vacuum_strategy_group_id": None,
            "entry_vacuum_selection_spec_id": None,
            "entry_vacuum_scan_all": True,
        }),
    )

    assert result.status is ReconciliationWorkerStatus.VACUUM_DRAIN_ADVANCED
    assert result.ticket_id == active_ticket.identity.ticket_id
    assert result.detail == VacuumDrainStatus.CANCEL_REQUESTED.value


@pytest.mark.asyncio
@pytest.mark.parametrize("group", [None, "CPM-RO-001", "BRF2-001"])
async def test_late_fill_after_zero_fill_vacuum_closure_is_not_silent(
    dispatch_engine, group: str | None,
) -> None:
    ticket = _ticket_for_group(make_ticket(), group)
    await seed_policy(dispatch_engine, event_spec_id=ticket.identity.runtime.event_spec_id)
    await issue(dispatch_engine, ticket)
    await dispatch_for_ticket(
        dispatch_engine,
        AcceptingVenue(dispatch_engine),
        ticket.identity.ticket_id,
        now_ms=1_100,
    )
    vacuum = await _open_group_vacuum(dispatch_engine, ticket, group)
    await _assert_zero_fill_cancel(dispatch_engine, ticket, vacuum)

    stale_positive = _position_snapshot(
        ticket,
        quantity=ticket.quantity,
        average_entry_price=ticket.entry_reference_price,
        open_entry_order=False,
        observed_at_ms=vacuum.fenced_at_ms + 4,
    )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        stale = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(ticket_id=ticket.identity.ticket_id, snapshot=stale_positive),
        )
        stale_incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
    assert stale.status is ReconcileTicketStatus.NO_CHANGE
    assert stale_incident is None

    late_fill = _position_snapshot(
        ticket,
        quantity=ticket.quantity,
        average_entry_price=ticket.entry_reference_price,
        open_entry_order=False,
        observed_at_ms=vacuum.fenced_at_ms + 10,
    )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        result = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(ticket_id=ticket.identity.ticket_id, snapshot=late_fill),
        )
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
        position = await uow.positions.get(ticket.identity.netting_domain.key())
        ownership = await uow.entry_admission.read_admission_ownership(
            venue_id=ticket.identity.netting_domain.venue_id,
            account_id=ticket.identity.netting_domain.account_id,
            exchange_instrument_id=ticket.identity.netting_domain.exchange_instrument_id,
        )

    assert result.status is ReconcileTicketStatus.LATE_FILL_INCIDENT
    assert incident is not None and incident.incident_kind == "late_fill_after_entry_absence"
    assert incident.entry_block_scope.value == "account_capacity"
    assert aggregate is not None and aggregate.status is AggregateStatus.ENTRY_RECONCILED_ABSENT
    assert position is not None and position.quantity == 0
    assert [command.kind for command in commands] == [
        ExchangeCommandKind.ENTRY, ExchangeCommandKind.CANCEL_ORDER,
    ]
    assert "account_capacity" in {scope.value for scope in ownership.open_incident_scopes}

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        repeated = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(ticket_id=ticket.identity.ticket_id, snapshot=late_fill),
        )
    assert repeated.status is ReconcileTicketStatus.LATE_FILL_INCIDENT
    async with dispatch_engine.connect() as conn:
        assert await conn.scalar(sa.text(
            "SELECT count(*) FROM brc_runtime_incidents WHERE ticket_id=:ticket AND status='open'"
        ), {"ticket":ticket.identity.ticket_id}) == 1


@pytest.mark.asyncio
async def test_reconciliation_worker_detects_orphan_position_after_terminal_zero_fill(
    dispatch_engine,
) -> None:
    ticket = make_ticket()
    await seed_policy(dispatch_engine)
    await issue(dispatch_engine, ticket)
    await dispatch_for_ticket(
        dispatch_engine, AcceptingVenue(dispatch_engine), ticket.identity.ticket_id,
        now_ms=1_100,
    )
    vacuum = await open_entry_vacuum(dispatch_engine, ticket)
    await _assert_zero_fill_cancel(dispatch_engine, ticket, vacuum)

    from src.trading_kernel.application.runtime_facts import (
        AccountPositionAuditSnapshot,
    )
    from src.trading_kernel.domain.cross_margin_stress import AccountRiskPosition

    class LateAccountPositionSource:
        calls = 0
        positions_present = True

        async def read_account_position_audit(self, *, observed_at_ms: int):
            self.calls += 1
            return AccountPositionAuditSnapshot(
                venue_id=ticket.identity.netting_domain.venue_id,
                account_id=ticket.identity.netting_domain.account_id,
                positions=(AccountRiskPosition(
                    exchange_instrument_id=ticket.identity.netting_domain.exchange_instrument_id,
                    position_side=ticket.identity.netting_domain.position_side,
                    quantity=ticket.quantity,
                    average_entry_price=ticket.entry_reference_price,
                    current_unrealized_pnl=Decimal(0),
                    current_maintenance_margin=Decimal(0),
                ),) if self.positions_present else (),
                observed_at_ms=observed_at_ms,
            )

    source = LateAccountPositionSource()
    worker_request = _reconciliation_request(vacuum.fenced_at_ms + 20)
    result = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(dispatch_engine), NoVenueTruth(),
        RecordingVacuumPositionSource(_position_snapshot(
            ticket, quantity=Decimal(0), average_entry_price=None,
            open_entry_order=False, observed_at_ms=worker_request.now_ms,
        )),
        worker_request,
        account_position_audit_source=source,
    )
    assert result.status is ReconciliationWorkerStatus.ACCOUNT_POSITION_INCIDENT
    assert source.calls == 1
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        ownership = await uow.entry_admission.read_admission_ownership(
            venue_id=ticket.identity.netting_domain.venue_id,
            account_id=ticket.identity.netting_domain.account_id,
            exchange_instrument_id=ticket.identity.netting_domain.exchange_instrument_id,
        )
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
    assert "account_capacity" in {scope.value for scope in ownership.open_incident_scopes}
    assert aggregate is not None and aggregate.status is AggregateStatus.ENTRY_RECONCILED_ABSENT
    assert [command.kind for command in commands] == [
        ExchangeCommandKind.ENTRY, ExchangeCommandKind.CANCEL_ORDER,
    ]

    before_due = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(dispatch_engine), NoVenueTruth(),
        RecordingVacuumPositionSource(_position_snapshot(
            ticket, quantity=Decimal(0), average_entry_price=None,
            open_entry_order=False, observed_at_ms=worker_request.now_ms + 1,
        )),
        worker_request.model_copy(update={"now_ms": worker_request.now_ms + 1}),
        account_position_audit_source=source,
    )
    assert before_due.status is ReconciliationWorkerStatus.NO_WORK
    assert source.calls == 1

    source.positions_present = False
    recovered = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(dispatch_engine), NoVenueTruth(),
        RecordingVacuumPositionSource(_position_snapshot(
            ticket, quantity=Decimal(0), average_entry_price=None,
            open_entry_order=False, observed_at_ms=worker_request.now_ms + 60_001,
        )),
        worker_request.model_copy(update={"now_ms": worker_request.now_ms + 60_001}),
        account_position_audit_source=source,
    )
    assert recovered.status is ReconciliationWorkerStatus.ACCOUNT_POSITION_INCIDENT
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        ownership_after = await uow.entry_admission.read_admission_ownership(
            venue_id=ticket.identity.netting_domain.venue_id,
            account_id=ticket.identity.netting_domain.account_id,
            exchange_instrument_id=ticket.identity.netting_domain.exchange_instrument_id,
        )
    assert "account_capacity" in {
        scope.value for scope in ownership_after.open_incident_scopes
    }
    assert source.calls == 2
    async with dispatch_engine.connect() as conn:
        assert await conn.scalar(sa.text(
            "SELECT count(*) FROM brc_runtime_incidents WHERE incident_kind='unowned_account_position'"
        )) == 1


@pytest.mark.asyncio
async def test_account_position_audit_healthy_and_source_retry_are_bounded(
    dispatch_engine,
) -> None:
    from src.trading_kernel.application.runtime_facts import (
        AccountPositionAuditSnapshot,
    )

    await seed_policy(dispatch_engine)

    async with dispatch_engine.begin() as conn:
        await conn.execute(sa.text(
            "INSERT INTO brc_runtime_capabilities_current "
            "(capability_key,enabled,certified_commit,schema_revision,certification,updated_at_ms) "
            "VALUES ('exchange_commands',true,'kernel-test-head',:schema,'{}'::jsonb,1000)"
        ), {"schema": CURRENT_SCHEMA_REVISION})

    class Source:
        calls = 0
        fails = False
        stale = False

        async def read_account_position_audit(self, *, observed_at_ms: int):
            self.calls += 1
            if self.fails:
                raise TimeoutError("account_read_unavailable")
            return AccountPositionAuditSnapshot(
                venue_id="binance-usdm", account_id="experiment-1",
                positions=(), observed_at_ms=(
                    observed_at_ms - 1 if self.stale else observed_at_ms
                ),
            )

    source = Source()
    request = _reconciliation_request(10_000)
    async def tick(now_ms: int):
        return await run_reconciliation_worker_once(
            lambda: PostgresKernelUnitOfWork(dispatch_engine), NoVenueTruth(),
            FailingVacuumPositionSource(),
            request.model_copy(update={"now_ms": now_ms}),
            account_position_audit_source=source,
        )

    first = await tick(10_000)
    before_due = await tick(10_001)
    source.fails = True
    failed = await tick(70_001)
    retry_not_due = await tick(70_002)
    source.fails = False
    source.stale = True
    stale = await tick(130_002)
    source.stale = False
    restored = await tick(190_003)

    assert first.status is ReconciliationWorkerStatus.ACCOUNT_POSITION_AUDITED
    assert before_due.status is ReconciliationWorkerStatus.NO_WORK
    assert failed.status is ReconciliationWorkerStatus.FACTS_UNAVAILABLE
    assert retry_not_due.status is ReconciliationWorkerStatus.NO_WORK
    assert stale.status is ReconciliationWorkerStatus.FACTS_UNAVAILABLE
    assert restored.status is ReconciliationWorkerStatus.ACCOUNT_POSITION_AUDITED
    assert source.calls == 4
    async with dispatch_engine.connect() as conn:
        assert await conn.scalar(sa.text(
            "SELECT count(*) FROM brc_runtime_incidents WHERE status='open'"
        )) == 0


@pytest.mark.asyncio
async def test_concurrent_account_audits_create_one_open_incident(dispatch_engine) -> None:
    from src.trading_kernel.application.runtime_facts import (
        AccountPositionAuditSnapshot,
    )
    from src.trading_kernel.domain.cross_margin_stress import AccountRiskPosition

    async with dispatch_engine.begin() as conn:
        await conn.execute(sa.text(
            "INSERT INTO brc_runtime_capabilities_current "
            "(capability_key,enabled,certified_commit,schema_revision,certification,updated_at_ms) "
            "VALUES ('exchange_commands',true,'kernel-test-head',:schema,'{}'::jsonb,1000)"
        ), {"schema": CURRENT_SCHEMA_REVISION})

    class Source:
        async def read_account_position_audit(self, *, observed_at_ms: int):
            return AccountPositionAuditSnapshot(
                venue_id="binance-usdm", account_id="experiment-1",
                positions=(AccountRiskPosition(
                    exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
                    position_side="long", quantity=Decimal("0.01"),
                    average_entry_price=Decimal(100),
                    current_unrealized_pnl=Decimal(0),
                    current_maintenance_margin=Decimal(0),
                ),), observed_at_ms=observed_at_ms,
            )

    async def audit(worker_id: str):
        return await run_reconciliation_worker_once(
            lambda: PostgresKernelUnitOfWork(dispatch_engine), NoVenueTruth(),
            FailingVacuumPositionSource(),
            _reconciliation_request(10_000).model_copy(update={"worker_id":worker_id}),
            account_position_audit_source=Source(),
        )

    left, right = await asyncio.gather(audit("audit-left"), audit("audit-right"))
    assert left.status is ReconciliationWorkerStatus.ACCOUNT_POSITION_INCIDENT
    assert right.status is ReconciliationWorkerStatus.ACCOUNT_POSITION_INCIDENT
    async with dispatch_engine.connect() as conn:
        assert await conn.scalar(sa.text(
            "SELECT count(*) FROM brc_runtime_incidents "
            "WHERE incident_kind='unowned_account_position' AND status='open'"
        )) == 1


@pytest.mark.asyncio
async def test_account_position_audit_does_not_fence_an_active_ticket_domain(
    dispatch_engine,
) -> None:
    from src.trading_kernel.application.runtime_facts import (
        AccountPositionAuditSnapshot,
    )
    from src.trading_kernel.domain.cross_margin_stress import AccountRiskPosition

    ticket = make_ticket()
    await seed_policy(dispatch_engine)
    await issue(dispatch_engine, ticket)

    class Source:
        async def read_account_position_audit(self, *, observed_at_ms: int):
            return AccountPositionAuditSnapshot(
                venue_id=ticket.identity.netting_domain.venue_id,
                account_id=ticket.identity.netting_domain.account_id,
                positions=(AccountRiskPosition(
                    exchange_instrument_id=ticket.identity.netting_domain.exchange_instrument_id,
                    position_side=ticket.identity.netting_domain.position_side,
                    quantity=ticket.quantity,
                    average_entry_price=ticket.entry_reference_price,
                    current_unrealized_pnl=Decimal(0),
                    current_maintenance_margin=Decimal(0),
                ),), observed_at_ms=observed_at_ms,
            )

    result = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(dispatch_engine), NoVenueTruth(),
        FailingVacuumPositionSource(), _reconciliation_request(10_000),
        account_position_audit_source=Source(),
    )

    assert result.status is ReconciliationWorkerStatus.ACCOUNT_POSITION_AUDITED
    async with dispatch_engine.connect() as conn:
        assert await conn.scalar(sa.text(
            "SELECT count(*) FROM brc_runtime_incidents WHERE status='open'"
        )) == 0


@pytest.mark.asyncio
async def test_reconciliation_worker_supplies_position_facts_to_vacuum_reducer(
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
    source = RecordingVacuumPositionSource(
        _position_snapshot(
            ticket,
            quantity=Decimal(0),
            average_entry_price=None,
            open_entry_order=True,
            observed_at_ms=vacuum.fenced_at_ms + 1,
        )
    )

    result = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        NoVenueTruth(),
        source,
        ReconciliationWorkerRequest(
            worker_id="reconciliation-worker:vacuum",
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            now_ms=vacuum.fenced_at_ms + 1,
            timeout_seconds=1,
            unknown_visibility_grace_ms=30_000,
            idle_poll_interval_ms=2_000,
            entry_vacuum_strategy_group_id="SOR-1H-001",
            entry_vacuum_selection_spec_id=SELECTION_SPEC_ID,
        ),
    )

    assert result.status is ReconciliationWorkerStatus.VACUUM_DRAIN_ADVANCED
    assert result.ticket_id == ticket.identity.ticket_id
    assert result.detail == VacuumDrainStatus.CANCEL_REQUESTED.value
    assert len(source.requests) == 1
    assert source.requests[0].ticket_id == ticket.identity.ticket_id
    assert source.requests[0].netting_domain == ticket.identity.netting_domain
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.ENTRY_VACUUM_CANCEL_PENDING
    assert [command.kind for command in commands] == [
        ExchangeCommandKind.ENTRY,
        ExchangeCommandKind.CANCEL_ORDER,
    ]
    assert commands[-1].status is ExchangeCommandStatus.PREPARED


@pytest.mark.asyncio
async def test_reconciliation_vacuum_position_source_failure_is_retryable_and_mutates_nothing(
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

    result = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        NoVenueTruth(),
        FailingVacuumPositionSource(),
        _reconciliation_request(vacuum.fenced_at_ms + 1),
    )

    assert result.status is ReconciliationWorkerStatus.FACTS_UNAVAILABLE
    assert result.ticket_id == ticket.identity.ticket_id
    assert result.detail == "vacuum_position_snapshot:TimeoutError"
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        position = await uow.positions.get(ticket.identity.netting_domain.key())
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.ENTRY_ACCEPTED
    assert [command.kind for command in commands] == [ExchangeCommandKind.ENTRY]
    assert position is None


@pytest.mark.asyncio
async def test_reconciliation_vacuum_rejects_position_netting_domain_drift_without_mutation(
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
    drifted = _position_snapshot(
        ticket,
        quantity=Decimal(0),
        average_entry_price=None,
        open_entry_order=True,
        observed_at_ms=vacuum.fenced_at_ms + 1,
    ).model_copy(
        update={
            "netting_domain": ticket.identity.netting_domain.model_copy(
                update={"position_side": "short"}
            )
        }
    )

    result = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        NoVenueTruth(),
        RecordingVacuumPositionSource(drifted),
        _reconciliation_request(vacuum.fenced_at_ms + 1),
    )

    assert result.status is ReconciliationWorkerStatus.FACTS_UNAVAILABLE
    assert result.ticket_id == ticket.identity.ticket_id
    assert result.detail == "vacuum_position_snapshot:ValueError"
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        correct_position = await uow.positions.get(
            ticket.identity.netting_domain.key()
        )
        drifted_position = await uow.positions.get(drifted.netting_domain.key())
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.ENTRY_ACCEPTED
    assert [command.kind for command in commands] == [ExchangeCommandKind.ENTRY]
    assert correct_position is None
    assert drifted_position is None


@pytest.mark.asyncio
async def test_reconciliation_vacuum_relocks_after_network_and_does_not_duplicate_cancel(
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
    snapshot = _position_snapshot(
        ticket,
        quantity=Decimal(0),
        average_entry_price=None,
        open_entry_order=True,
        observed_at_ms=vacuum.fenced_at_ms + 1,
    )

    result = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        NoVenueTruth(),
        ConcurrentVacuumPositionSource(dispatch_engine, ticket, snapshot),
        _reconciliation_request(vacuum.fenced_at_ms + 1),
    )

    assert result.status is ReconciliationWorkerStatus.VACUUM_DRAIN_WAITING
    assert result.detail == VacuumDrainStatus.WAITING_COMMAND.value
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.ENTRY_VACUUM_CANCEL_PENDING
    assert [command.kind for command in commands] == [
        ExchangeCommandKind.ENTRY,
        ExchangeCommandKind.CANCEL_ORDER,
    ]


async def _assert_unknown_cancel(
    dispatch_engine, ticket, vacuum,
) -> None:
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
        clock_ms=lambda: vacuum.fenced_at_ms + 2,
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

    class MustNotDispatch:
        async def execute(self, request):
            raise AssertionError("unknown cancel must not be blindly resent")

    no_resend = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),MustNotDispatch(),
        DispatchCommandRequest(worker_id="unknown-retry",ticket_id=ticket.identity.ticket_id,
            now_ms=vacuum.fenced_at_ms+3,lease_until_ms=vacuum.fenced_at_ms+5_003,timeout_seconds=1), clock_ms=lambda: vacuum.fenced_at_ms+3)
    assert no_resend.status == DispatchCommandStatus.NO_COMMAND

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
                    order_side="buy" if ticket.identity.netting_domain.position_side == "long" else "sell",
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
    await dispatch_for_ticket(dispatch_engine,KindAwareAcceptingVenue(),ticket.identity.ticket_id,
        now_ms=vacuum.fenced_at_ms+6)
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        waiting = await drain_strategy_entry_vacuum_once(uow,_request(ticket,now_ms=vacuum.fenced_at_ms+7))
        assert waiting.status == VacuumDrainStatus.POSITION_FACTS_REQUIRED
        absent = await drain_strategy_entry_vacuum_once(uow,_request(ticket,now_ms=vacuum.fenced_at_ms+8,
            position_snapshot=_position_snapshot(ticket,quantity=Decimal(0),average_entry_price=None,
                open_entry_order=False,observed_at_ms=vacuum.fenced_at_ms+8)))
        assert absent.status == VacuumDrainStatus.ORDER_ABSENCE_RECORDED
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        closed = await drain_strategy_entry_vacuum_once(uow,_request(ticket,now_ms=vacuum.fenced_at_ms+9,
            position_snapshot=_position_snapshot(ticket,quantity=Decimal(0),average_entry_price=None,
                open_entry_order=False,observed_at_ms=vacuum.fenced_at_ms+9)))
        assert closed.status == VacuumDrainStatus.ZERO_FILL_CLOSED
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
        assert reservation is not None and reservation.status == "released"
        assert not await uow.entry_admission.has_active_ticket_in_domain(ticket.identity.netting_domain.key())
        final_commands = await uow.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
        assert sum(c.kind == ExchangeCommandKind.ENTRY for c in final_commands) == 1
        assert sum(c.kind == ExchangeCommandKind.CANCEL_ORDER for c in final_commands) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("group", [None, "CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
async def test_retained_partial_keeps_original_capacity_until_protected(
    dispatch_engine, group: str | None,
) -> None:
    ticket, vacuum, partial_qty = await _reach_retained_partial_pending(
        dispatch_engine, group=group,
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
@pytest.mark.parametrize("group", [None, "CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
async def test_retained_partial_initial_stop_rejection_requires_controlled_flatten(
    dispatch_engine, group: str | None,
) -> None:
    ticket, vacuum, partial_qty = await _reach_retained_partial_pending(
        dispatch_engine, group=group,
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
        clock_ms=lambda: vacuum.fenced_at_ms + 5,
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
        selection_spec_id=(SELECTION_SPEC_ID if ticket.identity.runtime.strategy_group_id == "SOR-1H-001"
            else generic_selection_spec(ticket.identity.runtime.strategy_group_id).selection_spec_id),
        now_ms=now_ms,
        ticket_id=ticket.identity.ticket_id,
        position_snapshot=position_snapshot,
    )


def _reconciliation_request(now_ms: int) -> ReconciliationWorkerRequest:
    return ReconciliationWorkerRequest(
        worker_id="reconciliation-worker:vacuum",
        runtime_commit="kernel-test-head",
        schema_revision=CURRENT_SCHEMA_REVISION,
        now_ms=now_ms,
        timeout_seconds=1,
        unknown_visibility_grace_ms=30_000,
        idle_poll_interval_ms=2_000,
        entry_vacuum_strategy_group_id="SOR-1H-001",
        entry_vacuum_selection_spec_id=SELECTION_SPEC_ID,
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


async def _reach_retained_partial_pending(engine, *, group: str | None = None, splittable: bool = True):
    ticket = _ticket_for_group(_retained_partial_ticket(), group)
    if group == "MPG-001" and splittable:
        # 33% of two quantity steps rounds to zero. Use four filled steps
        # out of six requested to exercise a legally splittable retained fill.
        ticket = TradeTicket.model_validate({**ticket.model_dump(),
            "quantity":Decimal("0.006"),"notional":Decimal(360),
            "planned_stop_risk_budget":Decimal(6),"post_fill_stop_risk_limit":Decimal("6.6"),
            "reserved_margin":Decimal(72),"risk_at_stop":Decimal(6),
            "take_profit_quantities":(Decimal("0.001"),)})
    async with PostgresKernelUnitOfWork(engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1_000)
    await seed_policy(engine,event_spec_id=ticket.identity.runtime.event_spec_id)
    await issue(engine, ticket, ticket_margin_budget=Decimal(90))
    await _seed_instrument_rules(engine, ticket)
    await dispatch_for_ticket(
        engine,
        AcceptingVenue(engine),
        ticket.identity.ticket_id,
        now_ms=1_100,
    )
    vacuum = await _open_group_vacuum(engine, ticket, group)
    partial_qty = Decimal("0.004") if group == "MPG-001" and splittable else Decimal("0.002")
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
    assert retained.status is (VacuumDrainStatus.PARTIAL_RETAINED_PROTECTION_REQUESTED
        if splittable else VacuumDrainStatus.PARTIAL_FLATTEN_REQUESTED)
    return ticket, vacuum, partial_qty


@pytest.mark.asyncio
async def test_mpg_unsplittable_partial_requests_exact_controlled_flatten(dispatch_engine) -> None:
    ticket, _vacuum, quantity = await _reach_retained_partial_pending(dispatch_engine,group="MPG-001",splittable=False)
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        assert aggregate is not None and aggregate.status == AggregateStatus.CONTROLLED_FLATTEN_PENDING
        assert aggregate.position_qty == quantity
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
        assert reservation is not None and reservation.status == "active"
        assert await uow.instrument_selection.entry_vacuum_has_drain_blockers(strategy_group_id="MPG-001")
        commands = await uow.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
        exits = [c for c in commands if c.kind == ExchangeCommandKind.CONTROLLED_FLATTEN]
        assert len(exits) == 1 and exits[0].payload.quantity == quantity


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
