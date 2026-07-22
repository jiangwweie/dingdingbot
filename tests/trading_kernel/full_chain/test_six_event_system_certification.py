from __future__ import annotations

from decimal import Decimal
import re
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.trading_kernel.application.maintain_ticket_lifecycle import (
    TicketLifecycleFacts,
)
from src.trading_kernel.application.market_ports import ClosedCandleRequest
from src.trading_kernel.application.observe_strategy_scope import ObservationStatus
from src.trading_kernel.application.ports import (
    MonitorOwnerStatus,
    VenueCommandRequest,
)
from src.trading_kernel.application.project_owner_state import (
    OwnerProjectionRequest,
    project_owner_state,
)
from src.trading_kernel.application.runtime_facts import (
    ActionTimeFactsRequest,
    LifecycleFactsRequest,
    PositionSnapshotRequest,
    ReviewEconomicsRequest,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.capacity import ActionTimeFacts
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommandResult,
    ExchangeCommandStatus,
)
from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.review import ReviewEconomicsFacts, ReviewFill
from src.trading_kernel.domain.strategy_registry import (
    RegisteredStrategyContract,
    registered_strategy_contracts,
)
from src.trading_kernel.infrastructure.pg_models import (
    instrument_rules_current,
    owner_policy_current,
    runtime_capabilities_current,
    runtime_profiles,
    runtime_scopes_current,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    seed_strategy_registry,
)
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
from src.trading_kernel.interfaces.observation_worker import (
    ObservationWorkerRequest,
    ObservationWorkerStatus,
    run_observation_worker_once,
)
from src.trading_kernel.interfaces.reconciliation_worker import (
    ReconciliationWorkerRequest,
    ReconciliationWorkerStatus,
    run_reconciliation_worker_once,
)
from tests.trading_kernel.integration.test_issue_ticket import (
    ADMIN_DSN,
    SAFE_DATABASE,
    _database_url,
    _run_alembic,
)
from tests.trading_kernel.unit.detectors.fixtures import (
    AVAX,
    BTC,
    ETH,
    NOW_MS,
    OP,
    SOL,
    SUI,
    brf2_short_snapshot,
    cpm_long_snapshot,
    flat_candles,
    mpg_long_snapshot,
    sor_snapshot,
)


SAFE_TEST_DATABASE = re.compile(r"^brc_kernel_test_[a-f0-9]{12}$")
EVENT_INSTRUMENTS = {
    "CPM-LONG": ETH,
    "MPG-LONG": SOL,
    "MI-LONG": SOL,
    "SOR-LONG": AVAX,
    "SOR-SHORT": BTC,
    "BRF2-SHORT": BTC,
}


@pytest_asyncio.fixture
async def six_event_engine() -> AsyncEngine:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_TEST_DATABASE.fullmatch(database_name)
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    await admin.execute(f'CREATE DATABASE "{database_name}"')
    database_url = _database_url(database_name)
    _run_alembic(database_url, "upgrade", "head")
    engine = create_async_engine(database_url)
    try:
        yield engine
    finally:
        await engine.dispose()
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            database_name,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await admin.close()


class CertifiedMarketSource:
    def __init__(self) -> None:
        cpm = cpm_long_snapshot()
        mpg = mpg_long_snapshot()
        brf2 = brf2_short_snapshot()
        sor_long = sor_snapshot(side="long").model_copy(
            update={"exchange_instrument_id": AVAX}
        )
        sor_short = sor_snapshot(side="short").model_copy(
            update={"exchange_instrument_id": BTC}
        )
        peer_1h = flat_candles(13, 3_600_000)
        self.responses = {
            (ETH, "1h"): cpm.candles_1h,
            (ETH, "4h"): cpm.candles_4h,
            (SOL, "1h"): mpg.candles_1h,
            (SOL, "4h"): mpg.candles_4h,
            (OP, "1h"): peer_1h,
            (AVAX, "1h"): peer_1h,
            (SUI, "1h"): peer_1h,
            (BTC, "1h"): brf2.candles_1h,
            (BTC, "4h"): brf2.candles_4h,
            (AVAX, "15m"): sor_long.candles_15m,
            (BTC, "15m"): sor_short.candles_15m,
        }

    async def fetch_closed_candles(
        self,
        request: ClosedCandleRequest,
    ) -> tuple[ClosedCandle, ...]:
        return self.responses.get(
            (request.exchange_instrument_id, request.timeframe),
            (),
        )


class CertifiedActionFactsSource:
    def __init__(self, *, reference_price: Decimal, position_side: str) -> None:
        offset = max(reference_price * Decimal("0.01"), Decimal("1"))
        if position_side == "long":
            self.best_ask = reference_price + offset
            self.best_bid = self.best_ask - Decimal("0.1")
        else:
            self.best_bid = reference_price - offset
            self.best_ask = self.best_bid + Decimal("0.1")

    async def read_action_time_facts(
        self,
        request: ActionTimeFactsRequest,
    ) -> ActionTimeFacts:
        return ActionTimeFacts(
            signal_event_id=request.signal_event_id,
            runtime_scope_id=request.runtime_scope_id,
            venue_id=request.venue_id,
            account_id=request.account_id,
            exchange_instrument_id=request.exchange_instrument_id,
            position_side=request.position_side,
            account_position_mode="independent_sides",
            best_bid_price=self.best_bid,
            best_ask_price=self.best_ask,
            account_equity=Decimal("1000000"),
            available_margin=Decimal("1000000"),
            netting_domain_position_qty=Decimal("0"),
            netting_domain_open_order_count=0,
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )


class CertifiedVenue:
    def __init__(self) -> None:
        self.calls: list[VenueCommandRequest] = []
        self.last_observed_at_ms = NOW_MS

    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        self.calls.append(request)
        self.last_observed_at_ms = max(
            self.last_observed_at_ms + 1,
            request.deadline_at_ms - 29_999,
        )
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=self.last_observed_at_ms,
            exchange_order_id=(
                request.payload.exchange_order_id
                if isinstance(request.payload, CancelCommandPayload)
                else f"venue-{request.kind.value}-{len(self.calls)}"
            ),
        )

    async def lookup_command_truth(self, request):
        raise AssertionError(f"unexpected unknown command lookup: {request.command_id}")


class CertifiedPositionSource:
    def __init__(self) -> None:
        self.quantity = Decimal("0")
        self.average_entry_price: Decimal | None = None

    def set_open(self, *, quantity: Decimal, average_entry_price: Decimal) -> None:
        self.quantity = quantity
        self.average_entry_price = average_entry_price

    def set_flat(self) -> None:
        self.quantity = Decimal("0")
        self.average_entry_price = None

    async def read_position_snapshot(
        self,
        request: PositionSnapshotRequest,
    ) -> PositionSnapshot:
        return PositionSnapshot(
            netting_domain=request.netting_domain,
            quantity=self.quantity,
            average_entry_price=self.average_entry_price,
            open_orders=(),
            observed_at_ms=request.observed_at_ms,
        )


class CertifiedLifecycleFactsSource:
    def __init__(self) -> None:
        self.facts: TicketLifecycleFacts | None = None

    async def read_lifecycle_facts(
        self,
        request: LifecycleFactsRequest,
    ) -> TicketLifecycleFacts:
        if self.facts is None:
            raise AssertionError("lifecycle facts requested before TP1 fill")
        return self.facts.model_copy(
            update={"observed_at_ms": request.observed_at_ms}
        )


class CertifiedReviewEconomicsSource:
    def __init__(self) -> None:
        self.requests: list[ReviewEconomicsRequest] = []

    async def read_review_economics(
        self,
        request: ReviewEconomicsRequest,
    ) -> ReviewEconomicsFacts:
        self.requests.append(request)
        entry_price = Decimal("100")
        exit_price = (
            Decimal("110")
            if request.netting_domain.position_side == "long"
            else Decimal("90")
        )
        half = request.expected_entry_quantity / Decimal("2")
        return ReviewEconomicsFacts(
            ticket_id=request.ticket_id,
            entry_fills=(
                ReviewFill(
                    exchange_trade_id=f"trade:{request.ticket_id}:entry",
                    venue_client_order_id=request.entry_venue_client_order_id,
                    quantity=request.expected_entry_quantity,
                    price=entry_price,
                    fee_quote=Decimal("0.1"),
                    occurred_at_ms=request.entry_time_ms,
                ),
            ),
            exit_fills=(
                ReviewFill(
                    exchange_trade_id=f"trade:{request.ticket_id}:exit:1",
                    venue_client_order_id=request.exit_venue_client_order_ids[0],
                    quantity=half,
                    price=exit_price,
                    fee_quote=Decimal("0.05"),
                    occurred_at_ms=request.exit_time_ms,
                ),
                ReviewFill(
                    exchange_trade_id=f"trade:{request.ticket_id}:exit:2",
                    venue_client_order_id=request.exit_venue_client_order_ids[-1],
                    quantity=request.expected_entry_quantity - half,
                    price=exit_price,
                    fee_quote=Decimal("0.05"),
                    occurred_at_ms=request.exit_time_ms,
                ),
            ),
            funding_quote=Decimal("0"),
            funding_unavailable_reason=None,
            observed_at_ms=request.observed_at_ms,
        )


@pytest.mark.parametrize(
    "contract",
    registered_strategy_contracts(),
    ids=lambda contract: contract.event_id,
)
@pytest.mark.asyncio
async def test_registered_event_reaches_terminal_review_from_closed_market_input(
    six_event_engine: AsyncEngine,
    contract: RegisteredStrategyContract,
) -> None:
    instrument_id = EVENT_INSTRUMENTS[contract.event_id]
    runtime_scope_id = f"scope-certification-{contract.event_id.lower()}"
    await _seed_runtime(
        six_event_engine,
        contract=contract,
        runtime_scope_id=runtime_scope_id,
        instrument_id=instrument_id,
    )
    def uow_factory() -> PostgresKernelUnitOfWork:
        return PostgresKernelUnitOfWork(six_event_engine)

    market_source = CertifiedMarketSource()

    observed = await run_observation_worker_once(
        uow_factory,
        market_source,
        ObservationWorkerRequest(
            worker_id="observation-worker-certification",
            runtime_commit="kernel-test-head",
            schema_revision="0001_initial",
            now_ms=NOW_MS,
            lease_until_ms=NOW_MS + 30_000,
            timeout_seconds=5,
            retry_interval_ms=1_000,
        ),
    )
    assert observed.status is ObservationWorkerStatus.OBSERVED
    assert observed.runtime_scope_id == runtime_scope_id
    assert observed.observation_status is ObservationStatus.SIGNAL_CREATED

    async with uow_factory() as uow:
        readiness = await uow.signals.get_readiness(runtime_scope_id)
        assert readiness is not None
        assert readiness.signal_event_id is not None
        signal = await uow.signals.get(readiness.signal_event_id)
    assert signal is not None
    reference_price = Decimal(
        str(next(fact.value for fact in signal.facts if fact.role == "protection_reference"))
    )

    venue = CertifiedVenue()
    position_source = CertifiedPositionSource()
    lifecycle_source = CertifiedLifecycleFactsSource()
    review_source = CertifiedReviewEconomicsSource()
    entry = await run_entry_worker_once(
        uow_factory,
        venue,
        CertifiedActionFactsSource(
            reference_price=reference_price,
            position_side=contract.position_side,
        ),
        EntryWorkerRequest(
            worker_id="entry-worker-certification",
            runtime_commit="kernel-test-head",
            schema_revision="0001_initial",
            now_ms=NOW_MS + 1_000,
            lease_until_ms=NOW_MS + 6_000,
            timeout_seconds=1,
            action_fact_validity_ms=30_000,
        ),
    )
    assert entry.status is EntryWorkerStatus.DISPATCHED
    assert entry.ticket_id is not None

    async with uow_factory() as uow:
        ticket = await uow.tickets.get(entry.ticket_id)
    assert ticket is not None
    position_source.set_open(
        quantity=ticket.quantity,
        average_entry_price=ticket.entry_reference_price,
    )
    reconciliation_request = ReconciliationWorkerRequest(
        worker_id="reconciliation-worker-certification",
        now_ms=NOW_MS + 2_000,
        timeout_seconds=1,
        unknown_visibility_grace_ms=30_000,
        idle_poll_interval_ms=1_000,
    )
    filled = await run_reconciliation_worker_once(
        uow_factory,
        venue,
        position_source,
        reconciliation_request,
    )
    assert filled.status is ReconciliationWorkerStatus.POSITION_RECONCILED

    lifecycle_request = LifecycleWorkerRequest(
        worker_id="lifecycle-worker-certification",
        now_ms=NOW_MS + 3_000,
        lease_until_ms=NOW_MS + 8_000,
        timeout_seconds=1,
        idle_poll_interval_ms=1_000,
    )
    initial_stop = await run_lifecycle_worker_once(
        uow_factory,
        venue,
        lifecycle_source,
        lifecycle_request,
    )
    assert initial_stop.status is LifecycleWorkerStatus.DISPATCHED
    take_profit = await run_lifecycle_worker_once(
        uow_factory,
        venue,
        lifecycle_source,
        lifecycle_request.model_copy(
            update={"now_ms": NOW_MS + 4_000, "lease_until_ms": NOW_MS + 9_000}
        ),
    )
    assert take_profit.status is LifecycleWorkerStatus.DISPATCHED

    tp1_quantity = ticket.take_profit_quantities[0]
    runner_quantity = ticket.quantity - tp1_quantity
    lifecycle_source.facts = TicketLifecycleFacts(
        position_quantity=runner_quantity,
        tp1_filled_quantity=tp1_quantity,
        tp1_average_fill_price=ticket.take_profit_prices[0],
        allocated_entry_fee_quote=Decimal("0.1"),
        exit_taker_fee_rate=Decimal("0.0005"),
        price_tick=Decimal("0.1"),
        market_facts=None,
        observed_at_ms=NOW_MS + 5_000,
    )
    runner_replacement = await run_lifecycle_worker_once(
        uow_factory,
        venue,
        lifecycle_source,
        lifecycle_request.model_copy(
            update={"now_ms": NOW_MS + 5_000, "lease_until_ms": NOW_MS + 10_000}
        ),
    )
    assert runner_replacement.status is LifecycleWorkerStatus.DISPATCHED
    old_stop_cancel = await run_lifecycle_worker_once(
        uow_factory,
        venue,
        lifecycle_source,
        lifecycle_request.model_copy(
            update={"now_ms": NOW_MS + 6_000, "lease_until_ms": NOW_MS + 11_000}
        ),
    )
    assert old_stop_cancel.status is LifecycleWorkerStatus.DISPATCHED

    position_source.set_flat()
    external_flat = await run_reconciliation_worker_once(
        uow_factory,
        venue,
        position_source,
        reconciliation_request.model_copy(update={"now_ms": NOW_MS + 7_000}),
    )
    assert external_flat.status is ReconciliationWorkerStatus.POSITION_RECONCILED
    runner_stop_cleanup = await run_lifecycle_worker_once(
        uow_factory,
        venue,
        lifecycle_source,
        lifecycle_request.model_copy(
            update={"now_ms": NOW_MS + 8_000, "lease_until_ms": NOW_MS + 13_000}
        ),
    )
    assert runner_stop_cleanup.status is LifecycleWorkerStatus.DISPATCHED
    matched = await run_reconciliation_worker_once(
        uow_factory,
        venue,
        position_source,
        reconciliation_request.model_copy(update={"now_ms": NOW_MS + 9_000}),
    )
    assert matched.status is ReconciliationWorkerStatus.POSITION_RECONCILED
    settled = await run_reconciliation_worker_once(
        uow_factory,
        venue,
        position_source,
        reconciliation_request.model_copy(update={"now_ms": NOW_MS + 10_000}),
    )
    assert settled.status is ReconciliationWorkerStatus.SETTLED
    reviewed = await run_reconciliation_worker_once(
        uow_factory,
        venue,
        position_source,
        reconciliation_request.model_copy(update={"now_ms": NOW_MS + 11_000}),
        review_economics_source=review_source,
    )
    assert reviewed.status is ReconciliationWorkerStatus.REVIEWED

    async with uow_factory() as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        review = await uow.reviews.get_for_ticket(ticket.identity.ticket_id)
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        owner_state = await project_owner_state(
            uow,
            OwnerProjectionRequest(
                monitor_key=f"certification:{runtime_scope_id}",
                owner_policy_id="policy-certification",
                runtime_scope_id=runtime_scope_id,
                ticket_id=ticket.identity.ticket_id,
                updated_at_ms=NOW_MS + 12_000,
            ),
        )

    assert aggregate is not None
    assert aggregate.status is AggregateStatus.TERMINAL
    assert aggregate.position_qty == 0
    assert review is not None
    assert review.metrics["event_spec_id"] == contract.event_spec_id
    assert review.metrics["economics_completeness"] == "complete"
    assert review.metrics["gross_realized_pnl_quote"] is not None
    assert review.metrics["trading_fees_quote"] == "0.20"
    assert review.metrics["net_pnl_quote"] is not None
    assert review.metrics["r_multiple"] is not None
    assert len(review_source.requests) == 1
    assert incident is None
    assert owner_state.owner_status is MonitorOwnerStatus.COMPLETED
    assert [command.kind.value for command in commands] == [
        "entry",
        "initial_stop",
        "take_profit",
        "replace_protection",
        "cancel_order",
        "cancel_order",
    ]


async def _seed_runtime(
    engine: AsyncEngine,
    *,
    contract: RegisteredStrategyContract,
    runtime_scope_id: str,
    instrument_id: str,
) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=NOW_MS - 1)
    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(instrument_rules_current).values(
                exchange_instrument_id=instrument_id,
                quantity_step=Decimal("0.001"),
                price_tick=Decimal("0.1"),
                min_quantity=Decimal("0.001"),
                min_notional=Decimal("5"),
                session_and_settlement={},
                observed_at_ms=NOW_MS - 1,
                valid_until_ms=NOW_MS + 86_400_000,
                projection_version=1,
            )
        )
        await connection.execute(
            sa.insert(owner_policy_current).values(
                owner_policy_id="policy-certification",
                policy_version=1,
                enabled=True,
                real_submit_enabled=True,
                priority_rank=1,
                max_concurrent_tickets=8,
                max_gross_notional=Decimal("1000000"),
                max_gross_risk_at_stop=Decimal("10000"),
                max_ticket_risk_at_stop=Decimal("1000"),
                target_leverage=Decimal("2"),
                scope={},
                updated_at_ms=NOW_MS - 1,
            )
        )
        await connection.execute(
            sa.insert(runtime_profiles).values(
                runtime_profile_id="profile-certification",
                venue_id="binance-usdm",
                account_id="account-certification",
                environment="test",
                position_mode="independent_sides",
                status="active",
                updated_at_ms=NOW_MS - 1,
            )
        )
        await connection.execute(
            sa.insert(runtime_scopes_current).values(
                runtime_scope_id=runtime_scope_id,
                strategy_group_id=contract.strategy_group_id,
                strategy_version_id=contract.strategy_version_id,
                event_spec_id=contract.event_spec_id,
                runtime_profile_id="profile-certification",
                owner_policy_id="policy-certification",
                exchange_instrument_id=instrument_id,
                position_side=contract.position_side,
                enabled=True,
                scope_version=1,
                updated_at_ms=NOW_MS - 1,
            )
        )
        await connection.execute(
            sa.insert(runtime_capabilities_current).values(
                capability_key="strategy_signal_ingest",
                enabled=True,
                certified_commit="kernel-test-head",
                schema_revision="0001_initial",
                certification={},
                updated_at_ms=NOW_MS - 1,
            )
        )
