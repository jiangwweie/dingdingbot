from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.application.ingest_signal import IngestSignalRequest, ingest_signal
from src.trading_kernel.application.runtime_facts import (
    ActionTimeFactsRequest,
    InstrumentRulesFacts,
    InstrumentRulesRequest,
    LifecycleFactsRequest,
    PositionSnapshotRequest,
)
from src.trading_kernel.domain.capacity import ActionTimeFacts
from src.trading_kernel.domain.commands import (
    ExchangeCommandResult,
    ExchangeCommandStatus,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.interfaces.entry_worker import (
    EntryWorkerRequest,
    EntryWorkerStatus,
    run_entry_worker_once,
)
from src.trading_kernel.interfaces.lifecycle_worker import (
    LifecycleWorkerRequest,
    LifecycleWorkerStatus,
    run_lifecycle_worker_once,
)
from src.trading_kernel.application.maintain_ticket_lifecycle import (
    TicketLifecycleFacts,
)
from src.trading_kernel.interfaces.reconciliation_worker import (
    ReconciliationWorkerRequest,
    ReconciliationWorkerStatus,
    run_reconciliation_worker_once,
)
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.identities import NettingDomain
from tests.trading_kernel.integration import test_command_dispatch as dispatch_fixture
from tests.trading_kernel.integration.test_signal_to_ticket import (
    _seed_runtime_authority,
    _signal,
)
from src.trading_kernel.domain.events import TicketIssued
from src.trading_kernel.domain.reducer import reduce_event
from tests.trading_kernel.unit.test_ticket import _ticket


runtime_fact_worker_engine = dispatch_fixture.dispatch_engine


class FakeActionTimeFactsSource:
    def __init__(self) -> None:
        self.requests: list[ActionTimeFactsRequest] = []
        self.rule_requests: list[InstrumentRulesRequest] = []

    async def read_action_time_facts(
        self,
        request: ActionTimeFactsRequest,
    ) -> ActionTimeFacts:
        self.requests.append(request)
        return ActionTimeFacts(
            signal_event_id=request.signal_event_id,
            runtime_scope_id=request.runtime_scope_id,
            venue_id=request.venue_id,
            account_id=request.account_id,
            exchange_instrument_id=request.exchange_instrument_id,
            position_side=request.position_side,
            account_position_mode="independent_sides",
            best_bid_price=Decimal("9999.9"),
            best_ask_price=Decimal("10000"),
            account_equity=Decimal("1000"),
            available_margin=Decimal("1000"),
            netting_domain_position_qty=Decimal("0"),
            netting_domain_open_order_count=0,
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )

    async def read_instrument_rules(
        self,
        request: InstrumentRulesRequest,
    ) -> InstrumentRulesFacts:
        self.rule_requests.append(request)
        return InstrumentRulesFacts(
            exchange_instrument_id=request.exchange_instrument_id,
            quantity_step=Decimal("0.001"),
            price_tick=Decimal("0.1"),
            min_quantity=Decimal("0.001"),
            min_notional=Decimal("5"),
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )


class RecordingAcceptingVenue:
    def __init__(self) -> None:
        self.command_kinds: list[str] = []
        self.observed_at_ms = 1_005

    async def execute(self, request):
        self.command_kinds.append(request.kind.value)
        self.observed_at_ms += 1
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=self.observed_at_ms,
            exchange_order_id=(
                request.payload.exchange_order_id
                if hasattr(request.payload, "exchange_order_id")
                else f"venue-{request.kind.value}-{len(self.command_kinds)}"
            ),
        )


class FakePositionSnapshotSource:
    def __init__(self, *, quantity: Decimal, average_entry_price: Decimal | None) -> None:
        self.quantity = quantity
        self.average_entry_price = average_entry_price
        self.requests: list[PositionSnapshotRequest] = []

    async def read_position_snapshot(
        self,
        request: PositionSnapshotRequest,
    ) -> PositionSnapshot:
        self.requests.append(request)
        return PositionSnapshot(
            netting_domain=request.netting_domain,
            quantity=self.quantity,
            average_entry_price=self.average_entry_price,
            observed_at_ms=request.observed_at_ms,
        )


class FakeLifecycleFactsSource:
    def __init__(self, facts: TicketLifecycleFacts) -> None:
        self.facts = facts
        self.requests: list[LifecycleFactsRequest] = []

    async def read_lifecycle_facts(
        self,
        request: LifecycleFactsRequest,
    ) -> TicketLifecycleFacts:
        self.requests.append(request)
        return self.facts.model_copy(update={"observed_at_ms": request.observed_at_ms})


@pytest.mark.asyncio
async def test_runtime_selector_reschedules_no_change_ticket_without_starving_next(
    runtime_fact_worker_engine,
) -> None:
    first_ticket = _ticket()
    second_identity = first_ticket.identity.model_copy(
        update={
            "ticket_id": "ticket:selector-second",
            "exposure_episode_id": "episode-selector-second",
            "signal_event_id": "signal-selector-second",
            "netting_domain": NettingDomain(
                venue_id="binance-usdm",
                account_id="experiment-1",
                exchange_instrument_id="binance-usdm:ETHUSDT:perpetual",
                position_side="long",
            ),
        }
    )
    second_ticket = _ticket(identity=second_identity)
    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        for index, ticket in enumerate((first_ticket, second_ticket), start=1):
            event = TicketIssued(
                event_id=f"event:selector:{index}",
                sequence=1,
                occurred_at_ms=1_000 + index,
                ticket=ticket,
            )
            await uow.commit_reduction(
                event=event,
                reduction=reduce_event(None, event),
                expected_version=0,
            )

    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        first = await uow.aggregates.get_next_for_statuses(
            (AggregateStatus.ENTRY_PENDING,),
            work_kind="lifecycle",
            now_ms=1_100,
        )
        assert first is not None
        await uow.aggregates.schedule_next_check(
            first.identity.ticket_id,
            work_kind="lifecycle",
            due_at_ms=5_000,
        )
    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        second = await uow.aggregates.get_next_for_statuses(
            (AggregateStatus.ENTRY_PENDING,),
            work_kind="lifecycle",
            now_ms=1_100,
        )

    assert second is not None
    assert second.identity.ticket_id != first.identity.ticket_id


@pytest.mark.asyncio
async def test_entry_worker_owns_candidate_facts_ticket_and_entry_dispatch(
    runtime_fact_worker_engine,
) -> None:
    await _seed_runtime_authority(runtime_fact_worker_engine)
    signal = _signal(signal_event_id="signal-entry-worker-owned")
    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision="0001_initial",
                now_ms=1_002,
            ),
        )

    facts = FakeActionTimeFactsSource()
    venue = RecordingAcceptingVenue()
    result = await run_entry_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_fact_worker_engine),
        venue,
        facts,
        EntryWorkerRequest(
            worker_id="entry-worker-1",
            runtime_commit="kernel-test-head",
            schema_revision="0001_initial",
            now_ms=1_003,
            lease_until_ms=6_003,
            timeout_seconds=1,
            action_fact_validity_ms=1_000,
        ),
    )

    assert result.status is EntryWorkerStatus.DISPATCHED
    assert result.ticket_id is not None
    assert len(facts.requests) == 1
    assert len(facts.rule_requests) == 1
    assert venue.command_kinds == ["entry"]
    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        ticket = await uow.tickets.get(result.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(result.ticket_id)
        rules = await uow.signals.get_instrument_rules(
            signal.exchange_instrument_id
        )
    assert ticket is not None
    assert rules is not None
    assert rules.observed_at_ms == 1_003
    assert rules.valid_until_ms == 2_003
    assert rules.projection_version == 2
    assert len(commands) == 1
    assert commands[0].status is ExchangeCommandStatus.ACCEPTED


@pytest.mark.asyncio
async def test_reconciliation_worker_selects_ticket_and_reads_venue_snapshot(
    runtime_fact_worker_engine,
) -> None:
    await _seed_runtime_authority(runtime_fact_worker_engine)
    signal = _signal(signal_event_id="signal-reconciliation-worker-owned")
    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision="0001_initial",
                now_ms=1_002,
            ),
        )
    entry = await run_entry_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_fact_worker_engine),
        RecordingAcceptingVenue(),
        FakeActionTimeFactsSource(),
        EntryWorkerRequest(
            worker_id="entry-worker-1",
            runtime_commit="kernel-test-head",
            schema_revision="0001_initial",
            now_ms=1_003,
            lease_until_ms=6_003,
            timeout_seconds=1,
            action_fact_validity_ms=1_000,
        ),
    )
    assert entry.ticket_id is not None
    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        ticket = await uow.tickets.get(entry.ticket_id)
    assert ticket is not None

    snapshots = FakePositionSnapshotSource(
        quantity=ticket.quantity,
        average_entry_price=Decimal("10000"),
    )
    reconciled = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_fact_worker_engine),
        RecordingAcceptingVenue(),
        snapshots,
        ReconciliationWorkerRequest(
            worker_id="reconciliation-worker-1",
            now_ms=1_006,
            timeout_seconds=1,
            unknown_visibility_grace_ms=30_000,
            idle_poll_interval_ms=2_000,
        ),
    )

    assert reconciled.status is ReconciliationWorkerStatus.POSITION_RECONCILED
    assert reconciled.ticket_id == entry.ticket_id
    assert len(snapshots.requests) == 1
    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        aggregate = await uow.aggregates.get(entry.ticket_id)
    assert aggregate is not None
    assert aggregate.status.value == "protection_pending"


@pytest.mark.asyncio
async def test_lifecycle_worker_reads_tp1_facts_and_replaces_runner_protection(
    runtime_fact_worker_engine,
) -> None:
    await _seed_runtime_authority(runtime_fact_worker_engine)
    signal = _signal(signal_event_id="signal-lifecycle-worker-owned")
    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision="0001_initial",
                now_ms=1_002,
            ),
        )
    venue = RecordingAcceptingVenue()
    entry = await run_entry_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_fact_worker_engine),
        venue,
        FakeActionTimeFactsSource(),
        EntryWorkerRequest(
            worker_id="entry-worker-1",
            runtime_commit="kernel-test-head",
            schema_revision="0001_initial",
            now_ms=1_003,
            lease_until_ms=6_003,
            timeout_seconds=1,
            action_fact_validity_ms=1_000,
        ),
    )
    assert entry.ticket_id is not None
    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        ticket = await uow.tickets.get(entry.ticket_id)
    assert ticket is not None
    await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_fact_worker_engine),
        venue,
        FakePositionSnapshotSource(
            quantity=ticket.quantity,
            average_entry_price=ticket.entry_reference_price,
        ),
        ReconciliationWorkerRequest(
            worker_id="reconciliation-worker-1",
            now_ms=1_007,
            timeout_seconds=1,
            unknown_visibility_grace_ms=30_000,
            idle_poll_interval_ms=2_000,
        ),
    )

    no_fill_facts = FakeLifecycleFactsSource(
        TicketLifecycleFacts(
            position_quantity=ticket.quantity,
            tp1_filled_quantity=Decimal("0"),
            tp1_average_fill_price=None,
            allocated_entry_fee_quote=Decimal("0"),
            exit_taker_fee_rate=Decimal("0.0005"),
            price_tick=Decimal("0.1"),
            market_facts=None,
            observed_at_ms=1_008,
        )
    )
    worker_request = LifecycleWorkerRequest(
        worker_id="lifecycle-worker-1",
        now_ms=1_008,
        lease_until_ms=6_008,
        timeout_seconds=1,
        idle_poll_interval_ms=2_000,
    )
    initial_stop = await run_lifecycle_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_fact_worker_engine),
        venue,
        no_fill_facts,
        worker_request,
    )
    assert initial_stop.status is LifecycleWorkerStatus.DISPATCHED
    tp1 = await run_lifecycle_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_fact_worker_engine),
        venue,
        no_fill_facts,
        worker_request.model_copy(
            update={"now_ms": 1_009, "lease_until_ms": 6_009}
        ),
    )
    assert tp1.status is LifecycleWorkerStatus.DISPATCHED

    mismatched_facts = FakeLifecycleFactsSource(
        TicketLifecycleFacts(
            position_quantity=Decimal("0"),
            tp1_filled_quantity=Decimal("0"),
            tp1_average_fill_price=None,
            allocated_entry_fee_quote=Decimal("0"),
            exit_taker_fee_rate=Decimal("0.0005"),
            price_tick=Decimal("0.1"),
            market_facts=None,
            observed_at_ms=1_010,
        )
    )
    mismatch = await run_lifecycle_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_fact_worker_engine),
        venue,
        mismatched_facts,
        worker_request.model_copy(
            update={"now_ms": 1_010, "lease_until_ms": 6_010}
        ),
    )
    assert mismatch.status is LifecycleWorkerStatus.RECONCILIATION_REQUIRED

    tp1_quantity = ticket.take_profit_quantities[0]
    runner_quantity = ticket.quantity - tp1_quantity
    filled_facts = FakeLifecycleFactsSource(
        TicketLifecycleFacts(
            position_quantity=runner_quantity,
            tp1_filled_quantity=tp1_quantity,
            tp1_average_fill_price=ticket.take_profit_prices[0],
            allocated_entry_fee_quote=Decimal("0.02"),
            exit_taker_fee_rate=Decimal("0.0005"),
            price_tick=Decimal("0.1"),
            market_facts=None,
            observed_at_ms=3_011,
        )
    )
    replacement = await run_lifecycle_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_fact_worker_engine),
        venue,
        filled_facts,
        worker_request.model_copy(
            update={"now_ms": 3_011, "lease_until_ms": 8_011}
        ),
    )

    assert replacement.status is LifecycleWorkerStatus.DISPATCHED
    assert len(filled_facts.requests) == 1
    assert venue.command_kinds == [
        "entry",
        "initial_stop",
        "take_profit",
        "replace_protection",
    ]
    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        aggregate = await uow.aggregates.get(entry.ticket_id)
    assert aggregate is not None
    assert aggregate.status.value == "runner_old_stop_cancel_pending"
