from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
import sqlalchemy as sa

from src.trading_kernel.application.ingest_signal import (
    IngestSignalRequest,
    ingest_signal,
)
from src.trading_kernel.application.issue_ticket import IssueTicketStatus
from src.trading_kernel.application.maintain_ticket_lifecycle import (
    TicketLifecycleFacts,
)
from src.trading_kernel.application.ports import (
    LeverageTruthRequest,
    LeverageTruthSnapshot,
    VenueCommandRequest,
    VenueSetLeverageRequest,
    VenueTruthRequest,
)
from src.trading_kernel.application.runtime_facts import (
    AccountRiskSnapshotRequest,
    EntryAdmissionSnapshotRequest,
    InstrumentRulesFacts,
    InstrumentRulesRequest,
    LifecycleFactsRequest,
    PositionSnapshotRequest,
)
from src.trading_kernel.application.runtime_fence import runtime_writer_is_certified
from src.trading_kernel.application.select_entry_candidate import (
    SelectEntryCandidateRequest,
    SelectEntryCandidateStatus,
    select_entry_candidate,
)
from src.trading_kernel.domain.aggregate import AggregateStatus, TradeAggregate
from src.trading_kernel.domain.commands import (
    ExchangeCommandResult,
    ExchangeCommandStatus,
    SetLeverageCommandResult,
)
from src.trading_kernel.domain.cross_margin_stress import (
    AccountRiskSnapshot,
    MaintenanceMarginBracket,
)
from src.trading_kernel.domain.entry_admission_snapshot import (
    EntryAdmissionSnapshot,
    canonical_digest,
)
from src.trading_kernel.domain.events import RunnerStopRequested, TakeProfitFilled
from src.trading_kernel.domain.exit_policy import LifecycleMarketFacts
from src.trading_kernel.domain.identities import NettingDomain
from src.trading_kernel.domain.incident_blocking import EntryBlockScope
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.venue_truth import VenueTruthSnapshot
from src.trading_kernel.infrastructure.pg_models import (
    exchange_commands,
    owner_policy_current,
    runtime_capabilities_current,
    runtime_incidents,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
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
from src.trading_kernel.interfaces.reconciliation_worker import (
    ReconciliationWorkerRequest,
    ReconciliationWorkerStatus,
    run_reconciliation_worker_once,
)
from tests.trading_kernel.support.command_dispatch import (
    commit_passed_post_fill_stress_if_pending,
)
from tests.trading_kernel.support.runtime_scope import (
    seed_ticket_runtime_scope as _seed_ticket_runtime_scope,
)
from tests.trading_kernel.support.signal_ingest import (
    seed_runtime_authority as _seed_runtime_authority,
)
from tests.trading_kernel.support.signal_ingest import (
    signal as _signal,
)
from tests.trading_kernel.support.tickets import make_ticket as _ticket


class FakeEntryAdmissionFactsSource:
    def __init__(self) -> None:
        self.requests: list[EntryAdmissionSnapshotRequest] = []
        self.rule_requests: list[InstrumentRulesRequest] = []

    async def read_entry_admission_snapshot(
        self,
        request: EntryAdmissionSnapshotRequest,
    ) -> EntryAdmissionSnapshot:
        self.requests.append(request)
        return EntryAdmissionSnapshot(
            account_risk_snapshot=AccountRiskSnapshot.create(
                venue_id=request.venue_id,
                account_id=request.account_id,
                account_risk_mode="standard_usdm_single_asset",
                settlement_asset="USDT",
                position_mode="independent_sides",
                margin_mode="cross",
                exchange_instrument_id=request.exchange_instrument_id,
                mark_price=Decimal(10000),
                configured_leverage=5,
                total_wallet_balance=Decimal(1000),
                total_margin_balance=Decimal(1000),
                total_initial_margin=Decimal(0),
                total_maintenance_margin=Decimal(0),
                available_margin=Decimal(1000),
                account_positions=(),
                observed_at_ms=request.observed_at_ms,
                valid_until_ms=request.observed_at_ms + request.valid_for_ms,
            ),
            best_bid_price=Decimal("9999.9"),
            best_ask_price=Decimal(10000),
            open_orders=(),
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
            min_notional=Decimal(5),
            exchange_max_leverage=10,
            maintenance_margin_brackets=_maintenance_brackets(),
            maintenance_margin_brackets_digest=canonical_digest(
                _maintenance_brackets()
            ),
            notional_coefficient=Decimal(1),
            notional_coefficient_certified=True,
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )

    async def read_account_risk_snapshot(
        self,
        request: AccountRiskSnapshotRequest,
    ) -> AccountRiskSnapshot:
        return AccountRiskSnapshot.create(
            venue_id=request.venue_id,
            account_id=request.account_id,
            account_risk_mode="standard_usdm_single_asset",
            settlement_asset="USDT",
            position_mode="independent_sides",
            margin_mode="cross",
            exchange_instrument_id=request.exchange_instrument_id,
            mark_price=Decimal(10000),
            configured_leverage=5,
            total_wallet_balance=Decimal(1000),
            total_margin_balance=Decimal(1000),
            total_initial_margin=Decimal(0),
            total_maintenance_margin=Decimal(0),
            available_margin=Decimal(1000),
            account_positions=(),
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )


class CandidateSupersedingFactsSource(FakeEntryAdmissionFactsSource):
    def __init__(self, engine, higher_rank_signal) -> None:
        super().__init__()
        self._engine = engine
        self._higher_rank_signal = higher_rank_signal
        self._injected = False
        self._lock = asyncio.Lock()

    async def _inject_higher_rank_candidate_once(self) -> None:
        async with self._lock:
            if self._injected:
                return
            async with PostgresKernelUnitOfWork(self._engine) as uow:
                await ingest_signal(
                    uow,
                    IngestSignalRequest(
                        signal=self._higher_rank_signal,
                        runtime_commit="kernel-test-head",
                        schema_revision=CURRENT_SCHEMA_REVISION,
                        now_ms=1_002,
                    ),
                )
            self._injected = True

    async def read_entry_admission_snapshot(
        self,
        request: EntryAdmissionSnapshotRequest,
    ) -> EntryAdmissionSnapshot:
        await self._inject_higher_rank_candidate_once()
        return await super().read_entry_admission_snapshot(request)

    async def read_instrument_rules(
        self,
        request: InstrumentRulesRequest,
    ) -> InstrumentRulesFacts:
        await self._inject_higher_rank_candidate_once()
        return await super().read_instrument_rules(request)


class UnavailableEntryAdmissionFactsSource:
    async def read_entry_admission_snapshot(
        self,
        request: EntryAdmissionSnapshotRequest,
    ) -> EntryAdmissionSnapshot:
        raise TimeoutError(request.exchange_instrument_id)

    async def read_instrument_rules(
        self,
        request: InstrumentRulesRequest,
    ) -> InstrumentRulesFacts:
        raise TimeoutError(request.exchange_instrument_id)


def _maintenance_brackets() -> tuple[MaintenanceMarginBracket, ...]:
    return (
        MaintenanceMarginBracket(
            bracket_id="test:1",
            notional_floor=Decimal(0),
            notional_cap=None,
            maintenance_margin_rate=Decimal("0.005"),
            maintenance_amount=Decimal(0),
        ),
    )


class RecordingAcceptingVenue:
    def __init__(self) -> None:
        self.command_kinds: list[str] = []
        self.observed_at_ms = 1_005

    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
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

    async def set_leverage(
        self,
        request: VenueSetLeverageRequest,
    ) -> SetLeverageCommandResult:
        self.command_kinds.append("set_leverage")
        self.observed_at_ms += 1
        return SetLeverageCommandResult(
            exchange_configured_leverage=request.payload.desired_leverage,
            leverage_verified_at_ms=self.observed_at_ms,
            leverage_verification_digest="sha256:" + "4" * 64,
        )

    async def lookup_command_truth(
        self,
        request: VenueTruthRequest,
    ) -> VenueTruthSnapshot:
        del request
        raise AssertionError("runtime-fact worker test did not prepare unknown truth")

    async def read_configured_leverage(
        self,
        request: LeverageTruthRequest,
    ) -> LeverageTruthSnapshot:
        return LeverageTruthSnapshot(
            exchange_configured_leverage=request.desired_leverage,
            long_position_quantity=Decimal(0),
            short_position_quantity=Decimal(0),
            regular_open_order_ids=(),
            conditional_open_order_ids=(),
            observed_at_ms=self.observed_at_ms,
        )


class FakePositionSnapshotSource:
    def __init__(
        self,
        *,
        quantity: Decimal,
        average_entry_price: Decimal | None,
        venue_reported_liquidation_price: Decimal | None = None,
    ) -> None:
        self.quantity = quantity
        self.average_entry_price = average_entry_price
        self.venue_reported_liquidation_price = venue_reported_liquidation_price
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
            venue_reported_liquidation_price=(self.venue_reported_liquidation_price),
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


async def _enable_exchange_commands(engine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(runtime_capabilities_current).values(
                capability_key="exchange_commands",
                enabled=True,
                certified_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                certification={},
                updated_at_ms=1_000,
            )
        )


@pytest.mark.asyncio
async def test_expected_readonly_command_fence_resolves_prior_identity_incident(
    runtime_fact_worker_engine,
) -> None:
    await _seed_runtime_authority(runtime_fact_worker_engine)
    async with runtime_fact_worker_engine.begin() as connection:
        await connection.execute(
            sa.insert(runtime_capabilities_current).values(
                capability_key="exchange_commands",
                enabled=False,
                certified_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                certification={},
                updated_at_ms=1_000,
            )
        )

    mismatched = await runtime_writer_is_certified(
        lambda: PostgresKernelUnitOfWork(runtime_fact_worker_engine),
        worker_id="lifecycle-worker-1",
        runtime_commit="wrong-commit",
        schema_revision=CURRENT_SCHEMA_REVISION,
        observed_at_ms=1_001,
    )
    readonly = await runtime_writer_is_certified(
        lambda: PostgresKernelUnitOfWork(runtime_fact_worker_engine),
        worker_id="lifecycle-worker-1",
        runtime_commit="kernel-test-head",
        schema_revision=CURRENT_SCHEMA_REVISION,
        observed_at_ms=1_002,
    )

    assert mismatched is False
    assert readonly is False
    async with runtime_fact_worker_engine.connect() as connection:
        incident_status = (
            await connection.execute(
                sa.select(runtime_incidents.c.status).where(
                    runtime_incidents.c.incident_id == "incident:runtime-fence"
                )
            )
        ).scalar_one()
    assert incident_status == "resolved"


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
    for ticket in (first_ticket, second_ticket):
        await _seed_ticket_runtime_scope(runtime_fact_worker_engine, ticket)
    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        for ticket in (first_ticket, second_ticket):
            await uow.tickets.add(ticket)
            await uow.aggregates.add(
                TradeAggregate(
                    identity=ticket.identity,
                    ticket=ticket,
                    status=AggregateStatus.POSITION_PROTECTED,
                    version=1,
                    last_event_sequence=1,
                    entry_lane_held=False,
                    position_qty=ticket.quantity,
                    average_fill_price=ticket.entry_reference_price,
                    protected_qty=ticket.quantity,
                    initial_stop_exchange_order_id="stop:selector",
                    active_stop_exchange_order_id="stop:selector",
                    active_stop_price=ticket.initial_stop_price,
                ),
                updated_at_ms=1_000,
            )

    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        first = await uow.aggregates.get_next_for_statuses(
            (AggregateStatus.POSITION_PROTECTED,),
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
            (AggregateStatus.POSITION_PROTECTED,),
            work_kind="lifecycle",
            now_ms=1_100,
        )

    assert second is not None
    assert second.identity.ticket_id != first.identity.ticket_id


@pytest.mark.asyncio
async def test_reconciliation_selector_prioritizes_overdue_closure_over_due_position(
    runtime_fact_worker_engine,
) -> None:
    position_ticket = _ticket()
    closure_identity = position_ticket.identity.model_copy(
        update={
            "ticket_id": "ticket:closure-overdue",
            "exposure_episode_id": "episode-closure-overdue",
            "signal_event_id": "signal-closure-overdue",
            "netting_domain": NettingDomain(
                venue_id="binance-usdm",
                account_id="experiment-1",
                exchange_instrument_id="binance-usdm:ETHUSDT:perpetual",
                position_side="long",
            ),
        }
    )
    closure_ticket = _ticket(identity=closure_identity)
    for ticket in (position_ticket, closure_ticket):
        await _seed_ticket_runtime_scope(runtime_fact_worker_engine, ticket)
    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        await uow.tickets.add(position_ticket)
        await uow.tickets.add(closure_ticket)
        await uow.aggregates.add(
            TradeAggregate(
                identity=position_ticket.identity,
                ticket=position_ticket,
                status=AggregateStatus.POSITION_PROTECTED,
                version=1,
                last_event_sequence=1,
                entry_lane_held=False,
                position_qty=position_ticket.quantity,
                average_fill_price=position_ticket.entry_reference_price,
                protected_qty=position_ticket.quantity,
                initial_stop_exchange_order_id="stop:position",
                active_stop_exchange_order_id="stop:position",
                active_stop_price=position_ticket.initial_stop_price,
            ),
            updated_at_ms=1_000,
        )
        await uow.aggregates.add(
            TradeAggregate(
                identity=closure_ticket.identity,
                ticket=closure_ticket,
                status=AggregateStatus.SETTLEMENT_PENDING,
                version=1,
                last_event_sequence=1,
                entry_lane_held=False,
                position_qty=Decimal(0),
                average_fill_price=closure_ticket.entry_reference_price,
            ),
            updated_at_ms=1_000,
        )

    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        selected = await uow.aggregates.claim_next_critical_reconciliation_work(
            now_ms=31_000,
        )

    assert selected is not None
    assert selected.identity.ticket_id == position_ticket.identity.ticket_id


@pytest.mark.asyncio
async def test_entry_worker_owns_candidate_facts_ticket_and_entry_dispatch(
    runtime_fact_worker_engine,
) -> None:
    await _seed_runtime_authority(runtime_fact_worker_engine)
    await _enable_exchange_commands(runtime_fact_worker_engine)
    signal = _signal(signal_event_id="signal-entry-worker-owned")
    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_002,
            ),
        )

    facts = FakeEntryAdmissionFactsSource()
    venue = RecordingAcceptingVenue()
    result = await run_entry_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_fact_worker_engine),
        venue,
        facts,
        EntryWorkerRequest(
            worker_id="entry-worker-1",
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            now_ms=1_003,
            lease_until_ms=6_003,
            timeout_seconds=1,
            admission_snapshot_validity_ms=1_000,
        ),
    )

    assert result.status is EntryWorkerStatus.DISPATCHED
    assert result.ticket_id is not None
    assert len(facts.requests) == 2
    assert len(facts.rule_requests) == 2
    assert venue.command_kinds == ["entry"]
    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        ticket = await uow.tickets.get(result.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(result.ticket_id)
        rules = await uow.signals.get_instrument_rules(
            "binance-usdm",
            signal.exchange_instrument_id,
        )
    assert ticket is not None
    assert rules is not None
    assert rules.observed_at_ms == 1_003
    assert rules.valid_until_ms == 2_003
    assert rules.projection_version == 2
    assert len(commands) == 1
    assert commands[0].status is ExchangeCommandStatus.ACCEPTED


@pytest.mark.asyncio
async def test_entry_action_facts_timeout_records_infrastructure_decision(
    runtime_fact_worker_engine,
) -> None:
    await _seed_runtime_authority(runtime_fact_worker_engine)
    signal = _signal(signal_event_id="signal-entry-facts-timeout")
    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_002,
            ),
        )

    result = await run_entry_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_fact_worker_engine),
        RecordingAcceptingVenue(),
        UnavailableEntryAdmissionFactsSource(),
        EntryWorkerRequest(
            worker_id="entry-worker-timeout",
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            now_ms=1_003,
            lease_until_ms=6_003,
            timeout_seconds=1,
            admission_snapshot_validity_ms=1_000,
        ),
    )

    assert result.status is EntryWorkerStatus.FACTS_UNAVAILABLE
    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        decision = await uow.admission_decisions.get_for_signal(signal.signal_event_id)
        readiness = await uow.signals.get_readiness(signal.runtime_scope_id)
        claim = await uow.capacity_claims.get_for_signal(signal.signal_event_id)
        has_ticket = await uow.entry_admission.has_ticket_for_signal(
            signal.signal_event_id
        )
    assert decision is not None
    assert decision.decision_status.value == "rejected"
    assert decision.first_blocker == "observation_unavailable"
    assert decision.entry_admission_snapshot_digest is None
    assert readiness is not None
    assert readiness.first_blocker == "observation_unavailable"
    assert claim is None
    assert has_ticket is False
    async with runtime_fact_worker_engine.connect() as connection:
        assert (
            await connection.scalar(
                sa.select(sa.func.count()).select_from(exchange_commands)
            )
            == 0
        )


@pytest.mark.asyncio
async def test_adm_010_higher_candidate_during_network_read_supersedes_original(
    runtime_fact_worker_engine,
) -> None:
    await _seed_runtime_authority(runtime_fact_worker_engine)
    original = _signal(
        signal_event_id="signal-adm-010-original",
        occurred_at_ms=1_000,
    )
    higher_rank = _signal(
        signal_event_id="signal-adm-010-a-higher",
        occurred_at_ms=1_000,
    )
    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=original,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_002,
            ),
        )
    venue = RecordingAcceptingVenue()

    result = await run_entry_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_fact_worker_engine),
        venue,
        CandidateSupersedingFactsSource(
            runtime_fact_worker_engine,
            higher_rank,
        ),
        EntryWorkerRequest(
            worker_id="entry-worker-adm-010",
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            now_ms=1_003,
            lease_until_ms=6_003,
            timeout_seconds=1,
            admission_snapshot_validity_ms=1_000,
        ),
    )

    assert result.status is EntryWorkerStatus.ISSUE_REFUSED
    assert result.issue_status is IssueTicketStatus.NO_READY_SIGNAL
    assert venue.command_kinds == []
    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        original_decision = await uow.admission_decisions.get_for_signal(
            original.signal_event_id
        )
        original_claim = await uow.capacity_claims.get_for_signal(
            original.signal_event_id
        )
        original_has_ticket = await uow.entry_admission.has_ticket_for_signal(
            original.signal_event_id
        )
        selected = await select_entry_candidate(
            uow,
            SelectEntryCandidateRequest(now_ms=1_003),
        )
    assert original_decision is None
    assert original_claim is None
    assert original_has_ticket is False
    assert selected.status is SelectEntryCandidateStatus.SELECTED
    assert selected.candidate is not None
    assert selected.candidate.signal.signal_event_id == higher_rank.signal_event_id


@pytest.mark.asyncio
async def test_reconciliation_worker_selects_ticket_and_reads_venue_snapshot(
    runtime_fact_worker_engine,
) -> None:
    await _seed_runtime_authority(runtime_fact_worker_engine)
    await _enable_exchange_commands(runtime_fact_worker_engine)
    signal = _signal(signal_event_id="signal-reconciliation-worker-owned")
    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_002,
            ),
        )
    entry = await run_entry_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_fact_worker_engine),
        RecordingAcceptingVenue(),
        FakeEntryAdmissionFactsSource(),
        EntryWorkerRequest(
            worker_id="entry-worker-1",
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            now_ms=1_003,
            lease_until_ms=6_003,
            timeout_seconds=1,
            admission_snapshot_validity_ms=1_000,
        ),
    )
    assert entry.ticket_id is not None
    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        ticket = await uow.tickets.get(entry.ticket_id)
    assert ticket is not None

    snapshots = FakePositionSnapshotSource(
        quantity=ticket.quantity,
        average_entry_price=Decimal(10000),
        venue_reported_liquidation_price=Decimal(0),
    )
    reconciliation_request = ReconciliationWorkerRequest(
        worker_id="reconciliation-worker-1",
        runtime_commit="kernel-test-head",
        schema_revision=CURRENT_SCHEMA_REVISION,
        now_ms=1_006,
        timeout_seconds=1,
        unknown_visibility_grace_ms=30_000,
        idle_poll_interval_ms=2_000,
    )
    fenced = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_fact_worker_engine),
        RecordingAcceptingVenue(),
        snapshots,
        reconciliation_request.model_copy(update={"runtime_commit": "wrong-commit"}),
    )

    assert fenced.status is ReconciliationWorkerStatus.RUNTIME_FENCED
    assert len(snapshots.requests) == 1
    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        aggregate = await uow.aggregates.get(entry.ticket_id)
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.ENTRY_ACCEPTED

    reconciled = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_fact_worker_engine),
        RecordingAcceptingVenue(),
        snapshots,
        reconciliation_request,
    )

    assert reconciled.status is ReconciliationWorkerStatus.POSITION_RECONCILED
    assert reconciled.ticket_id == entry.ticket_id
    assert len(snapshots.requests) == 2
    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        aggregate = await uow.aggregates.get(entry.ticket_id)
    assert aggregate is not None
    assert aggregate.status.value == "protection_pending"


@pytest.mark.asyncio
async def test_lifecycle_worker_reads_tp1_facts_and_replaces_runner_protection(
    runtime_fact_worker_engine,
) -> None:
    await _seed_runtime_authority(runtime_fact_worker_engine)
    await _enable_exchange_commands(runtime_fact_worker_engine)
    signal = _signal(signal_event_id="signal-lifecycle-worker-owned")
    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_002,
            ),
        )
    venue = RecordingAcceptingVenue()
    entry = await run_entry_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_fact_worker_engine),
        venue,
        FakeEntryAdmissionFactsSource(),
        EntryWorkerRequest(
            worker_id="entry-worker-1",
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            now_ms=1_003,
            lease_until_ms=6_003,
            timeout_seconds=1,
            admission_snapshot_validity_ms=1_000,
        ),
    )
    assert entry.ticket_id is not None
    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        ticket = await uow.tickets.get(entry.ticket_id)
    assert ticket is not None
    async with runtime_fact_worker_engine.begin() as connection:
        await connection.execute(
            sa.update(owner_policy_current)
            .where(owner_policy_current.c.owner_policy_id == "policy-main")
            .values(new_entry_submit_enabled=False)
        )
    await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_fact_worker_engine),
        venue,
        FakePositionSnapshotSource(
            quantity=ticket.quantity,
            average_entry_price=ticket.entry_reference_price,
            venue_reported_liquidation_price=Decimal(0),
        ),
        ReconciliationWorkerRequest(
            worker_id="reconciliation-worker-1",
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            now_ms=1_007,
            timeout_seconds=1,
            unknown_visibility_grace_ms=30_000,
            idle_poll_interval_ms=2_000,
        ),
    )

    no_fill_facts = FakeLifecycleFactsSource(
        TicketLifecycleFacts(
            position_quantity=ticket.quantity,
            tp1_filled_quantity=Decimal(0),
            tp1_average_fill_price=None,
            allocated_entry_fee_quote=Decimal(0),
            exit_taker_fee_rate=Decimal("0.0005"),
            price_tick=Decimal("0.1"),
            market_facts=None,
            observed_at_ms=1_008,
        )
    )
    worker_request = LifecycleWorkerRequest(
        worker_id="lifecycle-worker-1",
        runtime_commit="kernel-test-head",
        schema_revision=CURRENT_SCHEMA_REVISION,
        now_ms=1_008,
        lease_until_ms=6_008,
        timeout_seconds=1,
        idle_poll_interval_ms=2_000,
    )
    fenced = await run_lifecycle_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_fact_worker_engine),
        venue,
        no_fill_facts,
        worker_request.model_copy(update={"runtime_commit": "wrong-commit"}),
    )
    assert fenced.status is LifecycleWorkerStatus.RUNTIME_FENCED
    assert venue.command_kinds == ["entry"]
    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        ownership = await uow.entry_admission.read_admission_ownership(
            venue_id=ticket.identity.netting_domain.venue_id,
            account_id=ticket.identity.netting_domain.account_id,
            exchange_instrument_id=(
                ticket.identity.netting_domain.exchange_instrument_id
            ),
        )
    assert EntryBlockScope.RUNTIME in ownership.open_incident_scopes

    initial_stop = await run_lifecycle_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_fact_worker_engine),
        venue,
        no_fill_facts,
        worker_request,
    )
    assert initial_stop.status is LifecycleWorkerStatus.DISPATCHED
    await commit_passed_post_fill_stress_if_pending(
        runtime_fact_worker_engine,
        ticket.identity.ticket_id,
    )
    tp1 = await run_lifecycle_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_fact_worker_engine),
        venue,
        no_fill_facts,
        worker_request.model_copy(update={"now_ms": 1_009, "lease_until_ms": 6_009}),
    )
    assert tp1.status is LifecycleWorkerStatus.DISPATCHED

    mismatched_facts = FakeLifecycleFactsSource(
        TicketLifecycleFacts(
            position_quantity=Decimal(0),
            tp1_filled_quantity=Decimal(0),
            tp1_average_fill_price=None,
            allocated_entry_fee_quote=Decimal(0),
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
        worker_request.model_copy(update={"now_ms": 1_010, "lease_until_ms": 6_010}),
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
        worker_request.model_copy(update={"now_ms": 3_011, "lease_until_ms": 8_011}),
    )

    assert replacement.status is LifecycleWorkerStatus.DISPATCHED
    assert len(filled_facts.requests) == 1
    assert filled_facts.requests[0].tp1_exchange_order_id is not None
    assert filled_facts.requests[0].exposure_started_at_ms == 1_007
    assert filled_facts.requests[0].time_stop_max_holding_bars == 96
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

    old_stop_cancel = await run_lifecycle_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_fact_worker_engine),
        venue,
        filled_facts,
        worker_request.model_copy(update={"now_ms": 3_012, "lease_until_ms": 8_012}),
    )
    assert old_stop_cancel.status is LifecycleWorkerStatus.DISPATCHED

    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        runner = await uow.aggregates.get(entry.ticket_id)
    assert runner is not None
    assert runner.status is AggregateStatus.RUNNER_PROTECTED
    break_even_stop = runner.active_stop_price
    assert break_even_stop is not None

    runner_facts = FakeLifecycleFactsSource(
        TicketLifecycleFacts(
            position_quantity=runner_quantity,
            tp1_filled_quantity=tp1_quantity,
            tp1_average_fill_price=ticket.take_profit_prices[0],
            allocated_entry_fee_quote=Decimal("0.02"),
            exit_taker_fee_rate=Decimal("0.0005"),
            price_tick=Decimal("0.1"),
            market_facts=LifecycleMarketFacts(
                watermark_ms=3_600_000,
                is_final_closed_candle=True,
                latest_close=Decimal(60500),
                structure_reference=Decimal(60500),
                atr=Decimal(100),
                holding_bars=10,
            ),
            observed_at_ms=3_600_000,
        )
    )
    runner_move = await run_lifecycle_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_fact_worker_engine),
        venue,
        runner_facts,
        worker_request.model_copy(
            update={"now_ms": 3_600_000, "lease_until_ms": 3_605_000}
        ),
    )

    assert runner_move.status is LifecycleWorkerStatus.DISPATCHED
    async with PostgresKernelUnitOfWork(runtime_fact_worker_engine) as uow:
        moved = await uow.aggregates.get(entry.ticket_id)
        events = await uow.events.list_for_ticket(entry.ticket_id)
    assert moved is not None
    assert moved.status is AggregateStatus.RUNNER_OLD_STOP_CANCEL_PENDING
    assert moved.active_stop_price is not None
    assert moved.active_stop_price > break_even_stop
    assert sum(isinstance(event, TakeProfitFilled) for event in events) == 1
    assert sum(isinstance(event, RunnerStopRequested) for event in events) == 1
    assert venue.command_kinds == [
        "entry",
        "initial_stop",
        "take_profit",
        "replace_protection",
        "cancel_order",
        "replace_protection",
    ]
