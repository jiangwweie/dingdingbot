from __future__ import annotations

from decimal import Decimal
from typing import Literal

import pytest

from src.trading_kernel.application.dispatch_exchange_command import (
    DispatchCommandRequest,
    DispatchCommandStatus,
    dispatch_one_command,
)
from src.trading_kernel.application.reconcile_ticket import (
    ReconcileTicketRequest,
    ReconcileTicketStatus,
    reconcile_ticket,
)
from src.trading_kernel.application.runtime_facts import (
    AccountRiskSnapshotRequest,
    EntryAdmissionSnapshotRequest,
    InstrumentRulesFacts,
    InstrumentRulesRequest,
    PositionSnapshotRequest,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import ExchangeCommandKind
from src.trading_kernel.domain.cross_margin_stress import (
    AccountRiskPosition,
    AccountRiskSnapshot,
    MaintenanceMarginBracket,
)
from src.trading_kernel.domain.entry_admission_snapshot import (
    EntryAdmissionSnapshot,
    canonical_digest,
)
from src.trading_kernel.domain.events import PostFillStressAssessed
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.interfaces.reconciliation_worker import (
    ReconciliationWorkerRequest,
    ReconciliationWorkerStatus,
    run_reconciliation_worker_once,
)
from tests.trading_kernel.integration import test_command_dispatch as dispatch_fixture
from tests.trading_kernel.integration.test_command_dispatch import (
    KindAwareAcceptingVenue,
    PreflightFacts,
    _issue,
    _seed_policy,
)
from tests.trading_kernel.integration.universe_certification_support import (
    NoTicketVenueTruth,
)
from tests.trading_kernel.unit.test_ticket import _ticket

stress_engine = dispatch_fixture.dispatch_engine


def _brackets() -> tuple[MaintenanceMarginBracket, ...]:
    return (
        MaintenanceMarginBracket(
            bracket_id="test:1",
            notional_floor=Decimal(0),
            notional_cap=None,
            maintenance_margin_rate=Decimal("0.005"),
            maintenance_amount=Decimal(0),
        ),
    )


class StressFactsSource:
    def __init__(
        self,
        ticket,
        *,
        margin_balance: Decimal,
        unavailable: bool = False,
        contradictory_rules: bool = False,
    ) -> None:
        self.ticket = ticket
        self.margin_balance = margin_balance
        self.unavailable = unavailable
        self.contradictory_rules = contradictory_rules
        self.account_reads = 0
        self.rule_reads = 0

    async def read_account_risk_snapshot(
        self,
        request: AccountRiskSnapshotRequest,
    ) -> AccountRiskSnapshot:
        self.account_reads += 1
        if self.unavailable:
            raise TimeoutError("sanitized account-risk timeout")
        ticket = self.ticket
        return AccountRiskSnapshot.create(
            venue_id=request.venue_id,
            account_id=request.account_id,
            account_risk_mode="standard_usdm_single_asset",
            settlement_asset="USDT",
            position_mode="independent_sides",
            margin_mode="cross",
            exchange_instrument_id=request.exchange_instrument_id,
            mark_price=ticket.entry_reference_price,
            configured_leverage=ticket.selected_leverage,
            total_wallet_balance=self.margin_balance,
            total_margin_balance=self.margin_balance,
            total_initial_margin=Decimal(0),
            total_maintenance_margin=Decimal(0),
            available_margin=self.margin_balance,
            account_positions=(
                AccountRiskPosition(
                    exchange_instrument_id=request.exchange_instrument_id,
                    position_side=ticket.identity.netting_domain.position_side,
                    quantity=ticket.quantity,
                    average_entry_price=ticket.entry_reference_price,
                    current_unrealized_pnl=Decimal(0),
                    current_maintenance_margin=Decimal(0),
                ),
            ),
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )

    async def read_instrument_rules(
        self,
        request: InstrumentRulesRequest,
    ) -> InstrumentRulesFacts:
        self.rule_reads += 1
        if self.unavailable:
            raise TimeoutError("sanitized instrument-rule timeout")
        return InstrumentRulesFacts(
            exchange_instrument_id=request.exchange_instrument_id,
            quantity_step=Decimal("0.001"),
            price_tick=Decimal("0.1"),
            min_quantity=Decimal("0.001"),
            min_notional=Decimal(5),
            exchange_max_leverage=10,
            maintenance_margin_brackets=_brackets(),
            maintenance_margin_brackets_digest=(
                "sha256:" + "6" * 64
                if self.contradictory_rules
                else canonical_digest(_brackets())
            ),
            notional_coefficient=Decimal(1),
            notional_coefficient_certified=True,
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )


class TicketPreflightFacts(PreflightFacts):
    def __init__(self, ticket) -> None:
        super().__init__(configured_leverage=ticket.selected_leverage)
        self.ticket = ticket

    async def read_entry_admission_snapshot(
        self,
        request: EntryAdmissionSnapshotRequest,
    ) -> EntryAdmissionSnapshot:
        ticket = self.ticket
        return EntryAdmissionSnapshot(
            account_risk_snapshot=AccountRiskSnapshot.create(
                venue_id=request.venue_id,
                account_id=request.account_id,
                account_risk_mode="standard_usdm_single_asset",
                settlement_asset="USDT",
                position_mode="independent_sides",
                margin_mode="cross",
                exchange_instrument_id=request.exchange_instrument_id,
                mark_price=ticket.entry_reference_price,
                configured_leverage=ticket.selected_leverage,
                total_wallet_balance=Decimal(100),
                total_margin_balance=Decimal(100),
                total_initial_margin=Decimal(10),
                total_maintenance_margin=Decimal(1),
                available_margin=Decimal(90),
                account_positions=(),
                observed_at_ms=request.observed_at_ms,
                valid_until_ms=request.observed_at_ms + request.valid_for_ms,
            ),
            best_bid_price=ticket.entry_reference_price,
            best_ask_price=ticket.entry_reference_price,
            open_orders=(),
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )


class UnusedPositionSource:
    async def read_position_snapshot(
        self,
        request: PositionSnapshotRequest,
    ) -> PositionSnapshot:
        raise AssertionError(
            f"post-fill stress must not use PositionSnapshot: {request.ticket_id}"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "case_name",
        "raw_liquidation_observation",
        "raw_observation_status",
        "expected_monitor_code",
    ),
    [
        (
            "eth_zero",
            Decimal(0),
            "valid",
            "venue_liquidation_observation_zero",
        ),
        (
            "avax_direction_inconsistent",
            Decimal("14.076"),
            "valid",
            "venue_liquidation_observation_not_side_directional",
        ),
        (
            "missing",
            None,
            "missing",
            "venue_liquidation_observation_unavailable",
        ),
        (
            "invalid",
            None,
            "invalid",
            "venue_liquidation_observation_invalid",
        ),
    ],
)
async def test_raw_liquidation_observation_never_controls_post_fill_decision(
    stress_engine,
    case_name: str,
    raw_liquidation_observation: Decimal | None,
    raw_observation_status: Literal["valid", "missing", "invalid"],
    expected_monitor_code: str,
) -> None:
    ticket = (
        _ticket(
            entry_reference_price=Decimal("6.60"),
            quantity=Decimal(10),
            notional=Decimal(66),
            reserved_margin=Decimal("13.2"),
            risk_at_stop=Decimal("2.17"),
            initial_stop_price=Decimal("6.383"),
            take_profit_prices=(Decimal(7),),
            take_profit_quantities=(Decimal(5),),
        )
        if case_name == "avax_direction_inconsistent"
        else _ticket()
    )
    await _reach_post_fill_pending(
        stress_engine,
        ticket,
        raw_liquidation_observation=raw_liquidation_observation,
        raw_observation_status=raw_observation_status,
    )
    source = StressFactsSource(
        ticket,
        margin_balance=max(Decimal(100), ticket.notional * Decimal(10)),
    )

    result = await _run_post_fill_worker(
        stress_engine,
        ticket,
        source,
        now_ms=3_000,
    )

    assert result.status is ReconciliationWorkerStatus.POSITION_RECONCILED
    assert result.detail == "post_fill_stress:passed"
    async with PostgresKernelUnitOfWork(stress_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        events = await uow.events.list_for_ticket(ticket.identity.ticket_id)
        monitor = await uow.monitors.get(
            f"venue-liquidation-observation:{ticket.identity.ticket_id}"
        )
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.TP1_PENDING
    assert aggregate.post_fill_stress_status == "passed"
    assert aggregate.venue_reported_liquidation_price == (
        raw_liquidation_observation
    )
    assessed = [
        event for event in events if isinstance(event, PostFillStressAssessed)
    ]
    assert len(assessed) == 1
    assert assessed[0].evidence.proof.proof_digest == (
        aggregate.post_fill_stress_proof_digest
    )
    assert monitor is not None
    assert expected_monitor_code in monitor.summary
    assert [command.kind for command in commands].count(
        ExchangeCommandKind.TAKE_PROFIT
    ) == 1
    assert ExchangeCommandKind.CONTROLLED_FLATTEN not in {
        command.kind for command in commands
    }


@pytest.mark.asyncio
async def test_unavailable_facts_retry_without_event_or_version_then_recover(
    stress_engine,
) -> None:
    ticket = _ticket()
    await _reach_post_fill_pending(stress_engine, ticket)
    async with PostgresKernelUnitOfWork(stress_engine) as uow:
        before = await uow.aggregates.get(ticket.identity.ticket_id)
        before_events = await uow.events.list_for_ticket(ticket.identity.ticket_id)
    assert before is not None
    unavailable = StressFactsSource(
        ticket,
        margin_balance=Decimal(100),
        unavailable=True,
    )

    for attempt in range(10):
        unavailable_result = await _run_post_fill_worker(
            stress_engine,
            ticket,
            unavailable,
            now_ms=3_000 + attempt * 1_000,
        )
        assert (
            unavailable_result.status
            is ReconciliationWorkerStatus.FACTS_UNAVAILABLE
        )
    async with PostgresKernelUnitOfWork(stress_engine) as uow:
        waiting = await uow.aggregates.get(ticket.identity.ticket_id)
        waiting_events = await uow.events.list_for_ticket(
            ticket.identity.ticket_id
        )
        incident = await uow.incidents.get_open_for_ticket_kind(
            ticket.identity.ticket_id,
            "post_fill_risk_facts_unavailable",
        )
        monitor = await uow.monitors.get(
            f"post-fill-stress:{ticket.identity.ticket_id}"
        )
    assert waiting is not None
    assert waiting.version == before.version
    assert waiting_events == before_events
    assert incident is not None
    assert monitor is not None
    assert monitor.owner_status.value == "temporarily_unavailable"
    assert unavailable.account_reads == 10
    assert unavailable.rule_reads == 10

    recovered = StressFactsSource(
        ticket,
        margin_balance=max(Decimal(100), ticket.notional * Decimal(10)),
    )
    second = await _run_post_fill_worker(
        stress_engine,
        ticket,
        recovered,
        now_ms=13_000,
    )

    assert second.detail == "post_fill_stress:passed"
    async with PostgresKernelUnitOfWork(stress_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        open_retry = await uow.incidents.get_open_for_ticket_kind(
            ticket.identity.ticket_id,
            "post_fill_risk_facts_unavailable",
        )
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.TP1_PENDING
    assert open_retry is None


@pytest.mark.asyncio
async def test_retry_state_switches_from_unavailable_to_contradictory(
    stress_engine,
) -> None:
    ticket = _ticket()
    await _reach_post_fill_pending(stress_engine, ticket)
    unavailable = StressFactsSource(
        ticket,
        margin_balance=Decimal(100),
        unavailable=True,
    )
    contradictory = StressFactsSource(
        ticket,
        margin_balance=Decimal(100),
        contradictory_rules=True,
    )

    first = await _run_post_fill_worker(
        stress_engine,
        ticket,
        unavailable,
        now_ms=3_000,
    )
    second = await _run_post_fill_worker(
        stress_engine,
        ticket,
        contradictory,
        now_ms=4_000,
    )

    assert first.status is ReconciliationWorkerStatus.FACTS_UNAVAILABLE
    assert second.status is ReconciliationWorkerStatus.FACTS_UNAVAILABLE
    assert second.detail == "post_fill_stress:facts_contradictory"
    async with PostgresKernelUnitOfWork(stress_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        events = await uow.events.list_for_ticket(ticket.identity.ticket_id)
        unavailable_incident = await uow.incidents.get_open_for_ticket_kind(
            ticket.identity.ticket_id,
            "post_fill_risk_facts_unavailable",
        )
        contradictory_incident = await uow.incidents.get_open_for_ticket_kind(
            ticket.identity.ticket_id,
            "post_fill_risk_facts_contradictory",
        )
        monitor = await uow.monitors.get(
            f"post-fill-stress:{ticket.identity.ticket_id}"
        )
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.POST_FILL_RISK_PENDING
    assert len(events) == aggregate.version
    assert unavailable_incident is None
    assert contradictory_incident is not None
    assert monitor is not None
    assert monitor.owner_status.value == "needs_intervention"


@pytest.mark.asyncio
async def test_failed_stress_materializes_one_flatten_and_keeps_lane_blocked(
    stress_engine,
) -> None:
    ticket = _ticket()
    await _reach_post_fill_pending(stress_engine, ticket)
    failed = StressFactsSource(ticket, margin_balance=Decimal(0))

    result = await _run_post_fill_worker(
        stress_engine,
        ticket,
        failed,
        now_ms=3_000,
    )

    assert result.detail == "post_fill_stress:failed"
    async with PostgresKernelUnitOfWork(stress_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        incident = await uow.incidents.get_open_for_ticket_kind(
            ticket.identity.ticket_id,
            "post_fill_stress_failed",
        )
        lane = await uow.entry_admission.get_global_lane()
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.CONTROLLED_FLATTEN_PENDING
    assert aggregate.post_fill_stress_status == "failed"
    assert [command.kind for command in commands].count(
        ExchangeCommandKind.CONTROLLED_FLATTEN
    ) == 1
    assert incident is not None
    assert lane is not None and lane.status == "claimed"

    venue = KindAwareAcceptingVenue()
    flatten = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(stress_engine),
        venue,
        DispatchCommandRequest(
            worker_id="controlled-flatten-dispatcher",
            ticket_id=ticket.identity.ticket_id,
            now_ms=3_100,
            lease_until_ms=8_100,
            timeout_seconds=1,
        ),
    )
    assert flatten.status is DispatchCommandStatus.ACCEPTED

    async with PostgresKernelUnitOfWork(stress_engine) as uow:
        flat = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=Decimal(0),
                    average_entry_price=None,
                    open_orders=(),
                    observed_at_ms=3_200,
                ),
            ),
        )
        incident_before_cleanup = (
            await uow.incidents.get_open_for_ticket_kind(
                ticket.identity.ticket_id,
                "post_fill_stress_failed",
            )
        )
        reservation_before_match = await uow.budgets.get_for_ticket(
            ticket.identity.ticket_id
        )
    assert flat.status is ReconcileTicketStatus.POSITION_FLAT_RECORDED
    assert incident_before_cleanup is not None
    assert reservation_before_match is not None
    assert reservation_before_match.status == "active"

    cancel_stop = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(stress_engine),
        venue,
        DispatchCommandRequest(
            worker_id="stop-cleanup-dispatcher",
            ticket_id=ticket.identity.ticket_id,
            now_ms=3_300,
            lease_until_ms=8_300,
            timeout_seconds=1,
        ),
    )
    assert cancel_stop.status is DispatchCommandStatus.ACCEPTED

    async with PostgresKernelUnitOfWork(stress_engine) as uow:
        matched = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=Decimal(0),
                    average_entry_price=None,
                    open_orders=(),
                    observed_at_ms=3_400,
                ),
            ),
        )
        closed_incident = await uow.incidents.get_open_for_ticket_kind(
            ticket.identity.ticket_id,
            "post_fill_stress_failed",
        )
        reservation_after_match = await uow.budgets.get_for_ticket(
            ticket.identity.ticket_id
        )
        domain_active = await uow.entry_admission.has_active_ticket_in_domain(
            ticket.identity.netting_domain.key()
        )
    assert matched.status is ReconcileTicketStatus.MATCHED
    assert closed_incident is None
    assert reservation_after_match is not None
    assert reservation_after_match.status == "released"
    assert not domain_active


async def _reach_post_fill_pending(
    engine,
    ticket,
    *,
    raw_liquidation_observation: Decimal | None = Decimal(0),
    raw_observation_status: Literal["valid", "missing", "invalid"] | None = None,
) -> None:
    await _seed_policy(engine)
    await _issue(engine, ticket)
    venue = KindAwareAcceptingVenue()
    entry = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine),
        venue,
        DispatchCommandRequest(
            worker_id="entry-dispatcher",
            ticket_id=ticket.identity.ticket_id,
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=1,
            runtime_commit="kernel-test-head",
            schema_revision="0001_trading_kernel_baseline_v4",
            admission_snapshot_validity_ms=1_000,
        ),
        entry_facts_source=TicketPreflightFacts(ticket),
    )
    assert entry.status is DispatchCommandStatus.ACCEPTED
    async with PostgresKernelUnitOfWork(engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price=ticket.entry_reference_price,
                    venue_reported_liquidation_price=(
                        raw_liquidation_observation
                    ),
                    venue_reported_liquidation_observation_status=(
                        raw_observation_status
                    ),
                    observed_at_ms=2_100,
                ),
            ),
        )
        await uow.signals.upsert_instrument_rules(
            venue_id=ticket.identity.netting_domain.venue_id,
            exchange_instrument_id=(
                ticket.identity.netting_domain.exchange_instrument_id
            ),
            quantity_step=Decimal("0.001"),
            price_tick=Decimal("0.1"),
            min_quantity=Decimal("0.001"),
            min_notional=Decimal(5),
            exchange_max_leverage=10,
            maintenance_margin_brackets=_brackets(),
            maintenance_margin_brackets_digest=canonical_digest(_brackets()),
            notional_coefficient=Decimal(1),
            notional_coefficient_certified=True,
            observed_at_ms=2_000,
            valid_until_ms=20_000,
        )
    stop = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine),
        venue,
        DispatchCommandRequest(
            worker_id="initial-stop-dispatcher",
            ticket_id=ticket.identity.ticket_id,
            now_ms=2_200,
            lease_until_ms=7_200,
            timeout_seconds=1,
        ),
    )
    assert stop.status is DispatchCommandStatus.ACCEPTED
    async with PostgresKernelUnitOfWork(engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.POST_FILL_RISK_PENDING


async def _run_post_fill_worker(
    engine,
    ticket,
    source: StressFactsSource,
    *,
    now_ms: int,
):
    return await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(engine),
        NoTicketVenueTruth(),
        UnusedPositionSource(),
        ReconciliationWorkerRequest(
            worker_id="post-fill-reconciliation",
            runtime_commit="kernel-test-head",
            schema_revision="0001_trading_kernel_baseline_v4",
            now_ms=now_ms,
            timeout_seconds=1,
            unknown_visibility_grace_ms=30_000,
            idle_poll_interval_ms=1_000,
        ),
        account_risk_source=source,
        instrument_rules_source=source,
    )
