from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
from collections.abc import AsyncGenerator
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.trading_kernel.application.dispatch_exchange_command import (
    DispatchCommandRequest,
    DispatchCommandStatus,
    dispatch_one_command,
)
from src.trading_kernel.application.issue_ticket import IssueTicketStatus, issue_ticket
from src.trading_kernel.application.ports import (
    MonitorOwnerStatus,
    VenueCommandRequest,
    VenueMutationFailure,
    VenueSetLeverageRequest,
)
from src.trading_kernel.application.project_owner_state import (
    owner_ticket_monitor_key,
)
from src.trading_kernel.application.reconcile_ticket import (
    ExitTicketRequest,
    ReconcileTicketRequest,
    reconcile_ticket,
    request_exit,
)
from src.trading_kernel.application.runtime_facts import (
    AccountRiskSnapshotRequest,
    EntryAdmissionSnapshotRequest,
    InstrumentRulesFacts,
    InstrumentRulesRequest,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommandKind,
    ExchangeCommandResult,
    ExchangeCommandStatus,
    OrderCommandPayload,
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
from src.trading_kernel.domain.events import PostFillStressAssessed, TakeProfitFilled
from src.trading_kernel.domain.position import PositionSnapshot, VenueOrderSnapshot
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.infrastructure.pg_models import (
    exchange_commands,
    owner_policy_current,
    runtime_capabilities_current,
    strategy_universe_current,
    strategy_versions,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.integration.test_issue_ticket import (
    _issue_request,
    _seed_replacement_universe,
    _seed_ticket_runtime_scope,
    _stress_evidence,
)
from tests.trading_kernel.unit.test_ticket import _ticket

REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_DSN = os.getenv(
    "BRC_TEST_POSTGRES_ADMIN_URL",
    "postgresql://dingdingbot:dingdingbot_dev@127.0.0.1:5432/postgres",
)
SAFE_DATABASE = re.compile(r"^brc_kernel_test_[a-f0-9]{12}$")


def _raw_liquidation_observation(ticket, average_fill_price: Decimal) -> Decimal:
    del ticket, average_fill_price
    return Decimal(0)


@pytest_asyncio.fixture
async def dispatch_engine() -> AsyncGenerator[AsyncEngine, None]:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
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


class AcceptingVenue:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self.saw_committed_claim = False

    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        async with PostgresKernelUnitOfWork(self._engine) as uow:
            command = await uow.exchange_commands.get(request.command_id)
        self.saw_committed_claim = (
            command is not None and command.status is ExchangeCommandStatus.CLAIMED
        )
        exchange_order_id = (
            request.payload.exchange_order_id
            if isinstance(request.payload, CancelCommandPayload)
            else f"venue-{request.kind.value}-1"
        )
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=2_000,
            exchange_order_id=exchange_order_id,
        )

    async def set_leverage(
        self, request: VenueSetLeverageRequest
    ) -> SetLeverageCommandResult:
        return SetLeverageCommandResult(
            exchange_configured_leverage=request.payload.desired_leverage,
            leverage_verified_at_ms=2_000,
            leverage_verification_digest="sha256:" + "4" * 64,
        )


class RejectingVenue:
    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.REJECTED,
            observed_at_ms=2_000,
            reason="insufficient_margin",
        )

    async def set_leverage(
        self, request: VenueSetLeverageRequest
    ) -> SetLeverageCommandResult:
        return SetLeverageCommandResult(
            exchange_configured_leverage=request.payload.desired_leverage,
            leverage_verified_at_ms=2_000,
            leverage_verification_digest="sha256:" + "4" * 64,
        )


class SlowVenue:
    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        await asyncio.sleep(0.1)
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=2_000,
            exchange_order_id="late-order",
        )

    async def set_leverage(
        self, request: VenueSetLeverageRequest
    ) -> SetLeverageCommandResult:
        await asyncio.sleep(0.1)
        return SetLeverageCommandResult(
            exchange_configured_leverage=request.payload.desired_leverage,
            leverage_verified_at_ms=2_000,
            leverage_verification_digest="sha256:" + "4" * 64,
        )


class CountingVenue:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        self.calls += 1
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=2_000,
            exchange_order_id="unexpected-order",
        )

    async def set_leverage(
        self, request: VenueSetLeverageRequest
    ) -> SetLeverageCommandResult:
        raise AssertionError(
            f"unexpected set leverage for {request.exchange_instrument_id}"
        )


class CountingEntryVenue(CountingVenue):
    def __init__(self) -> None:
        super().__init__()
        self.leverage_calls = 0

    async def set_leverage(
        self, request: VenueSetLeverageRequest
    ) -> SetLeverageCommandResult:
        self.leverage_calls += 1
        return SetLeverageCommandResult(
            exchange_configured_leverage=request.payload.desired_leverage,
            leverage_verified_at_ms=2_000,
            leverage_verification_digest="sha256:" + "4" * 64,
        )


class PreflightExitBarrierFactory:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._exit_count = 0
        self.preflight_closed = asyncio.Event()
        self.release_dispatch = asyncio.Event()

    def __call__(self):
        return _PreflightExitBarrierUnitOfWork(
            PostgresKernelUnitOfWork(self._engine),
            self,
        )


class _PreflightExitBarrierUnitOfWork:
    def __init__(
        self,
        inner: PostgresKernelUnitOfWork,
        barrier: PreflightExitBarrierFactory,
    ) -> None:
        self._inner = inner
        self._barrier = barrier

    async def __aenter__(self):
        return await self._inner.__aenter__()

    async def __aexit__(self, exc_type, exc, traceback):
        outcome = await self._inner.__aexit__(exc_type, exc, traceback)
        self._barrier._exit_count += 1
        if self._barrier._exit_count == 3:
            self._barrier.preflight_closed.set()
            await self._barrier.release_dispatch.wait()
        return outcome


class PreflightFacts:
    def __init__(self, *, configured_leverage: int = 5) -> None:
        self._configured_leverage = configured_leverage

    async def read_entry_admission_snapshot(
        self, request: EntryAdmissionSnapshotRequest
    ) -> EntryAdmissionSnapshot:
        return EntryAdmissionSnapshot(
            account_risk_snapshot=self._account_risk_snapshot(
                venue_id=request.venue_id,
                account_id=request.account_id,
                exchange_instrument_id=request.exchange_instrument_id,
                observed_at_ms=request.observed_at_ms,
                valid_for_ms=request.valid_for_ms,
            ),
            best_bid_price=Decimal(59999),
            best_ask_price=Decimal(60000),
            open_orders=(),
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )

    async def read_account_risk_snapshot(
        self, request: AccountRiskSnapshotRequest
    ) -> AccountRiskSnapshot:
        return self._account_risk_snapshot(
            venue_id=request.venue_id,
            account_id=request.account_id,
            exchange_instrument_id=request.exchange_instrument_id,
            observed_at_ms=request.observed_at_ms,
            valid_for_ms=request.valid_for_ms,
        )

    def _account_risk_snapshot(
        self,
        *,
        venue_id: str,
        account_id: str,
        exchange_instrument_id: str,
        observed_at_ms: int,
        valid_for_ms: int,
    ) -> AccountRiskSnapshot:
        return AccountRiskSnapshot.create(
            venue_id=venue_id,
            account_id=account_id,
            account_risk_mode="standard_usdm_single_asset",
            settlement_asset="USDT",
            position_mode="independent_sides",
            margin_mode="cross",
            exchange_instrument_id=exchange_instrument_id,
            mark_price=Decimal(60000),
            configured_leverage=self._configured_leverage,
            total_wallet_balance=Decimal(100),
            total_margin_balance=Decimal(100),
            total_initial_margin=Decimal(10),
            total_maintenance_margin=Decimal(1),
            available_margin=Decimal(90),
            account_positions=(),
            observed_at_ms=observed_at_ms,
            valid_until_ms=observed_at_ms + valid_for_ms,
        )

    async def read_instrument_rules(
        self, request: InstrumentRulesRequest
    ) -> InstrumentRulesFacts:
        brackets = (
            MaintenanceMarginBracket(
                bracket_id="test:1",
                notional_floor=Decimal(0),
                notional_cap=None,
                maintenance_margin_rate=Decimal("0.005"),
                maintenance_amount=Decimal(0),
            ),
        )
        return InstrumentRulesFacts(
            exchange_instrument_id=request.exchange_instrument_id,
            quantity_step=Decimal("0.001"),
            price_tick=Decimal("0.1"),
            min_quantity=Decimal("0.001"),
            min_notional=Decimal(5),
            exchange_max_leverage=10,
            maintenance_margin_brackets=brackets,
            maintenance_margin_brackets_digest=canonical_digest(brackets),
            notional_coefficient=Decimal(1),
            notional_coefficient_certified=True,
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )


class KindAwareAcceptingVenue:
    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        exchange_order_id = (
            request.payload.exchange_order_id
            if isinstance(request.payload, CancelCommandPayload)
            else f"venue-{request.kind.value}-1"
        )
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=2_000,
            exchange_order_id=exchange_order_id,
        )

    async def set_leverage(
        self, request: VenueSetLeverageRequest
    ) -> SetLeverageCommandResult:
        return SetLeverageCommandResult(
            exchange_configured_leverage=request.payload.desired_leverage,
            leverage_verified_at_ms=2_000,
            leverage_verification_digest="sha256:" + "4" * 64,
        )


class CountingKindAwareAcceptingVenue(KindAwareAcceptingVenue):
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        self.calls += 1
        return await super().execute(request)


class LeverageThenEntryVenue:
    def __init__(self) -> None:
        self.mutations: list[str] = []

    async def set_leverage(
        self, request: VenueSetLeverageRequest
    ) -> SetLeverageCommandResult:
        self.mutations.append("set_leverage")
        return SetLeverageCommandResult(
            exchange_configured_leverage=request.payload.desired_leverage,
            leverage_verified_at_ms=2_000,
            leverage_verification_digest="sha256:" + "4" * 64,
        )

    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        self.mutations.append("create_order")
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=2_100,
            exchange_order_id="venue-entry-1",
        )


class LeverageReadbackMismatchVenue(LeverageThenEntryVenue):
    async def set_leverage(
        self, request: VenueSetLeverageRequest
    ) -> SetLeverageCommandResult:
        self.mutations.append("set_leverage")
        return SetLeverageCommandResult(
            exchange_configured_leverage=request.payload.desired_leverage - 1,
            leverage_verified_at_ms=2_000,
            leverage_verification_digest="sha256:" + "5" * 64,
        )


class CodedLeverageFailureVenue:
    async def set_leverage(
        self, request: VenueSetLeverageRequest
    ) -> SetLeverageCommandResult:
        del request
        raise VenueMutationFailure("exchange_code_-4164")

    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        del request
        raise AssertionError("SET_LEVERAGE must not create an order")


@pytest.mark.asyncio
async def test_entry_without_action_time_facts_is_rejected_before_venue(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)
    venue = CountingEntryVenue()

    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
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
        entry_facts_source=None,
    )

    assert result.status is DispatchCommandStatus.SUPERSEDED
    assert venue.calls == 0
    assert venue.leverage_calls == 0
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        command = await uow.exchange_commands.get(result.command_id or "")
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        owner_projection = await uow.monitors.get(
            owner_ticket_monitor_key(ticket.identity.ticket_id)
        )
    assert command is not None and command.status is ExchangeCommandStatus.REJECTED
    assert aggregate is not None and aggregate.status is AggregateStatus.ENTRY_REJECTED
    assert owner_projection is not None
    assert owner_projection.owner_status is MonitorOwnerStatus.COMPLETED


@pytest.mark.asyncio
async def test_set_leverage_without_action_time_facts_is_rejected_before_venue(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket(leverage_change_required=True)
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)
    venue = CountingEntryVenue()

    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        venue,
        DispatchCommandRequest(
            worker_id="leverage-dispatcher",
            ticket_id=ticket.identity.ticket_id,
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=1,
            runtime_commit="kernel-test-head",
            schema_revision="0001_trading_kernel_baseline_v4",
            admission_snapshot_validity_ms=1_000,
        ),
        entry_facts_source=None,
    )

    assert result.status is DispatchCommandStatus.SUPERSEDED
    assert venue.calls == 0
    assert venue.leverage_calls == 0
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        command = await uow.exchange_commands.get(result.command_id or "")
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
    assert command is not None and command.status is ExchangeCommandStatus.REJECTED
    assert aggregate is not None and aggregate.status is AggregateStatus.LEVERAGE_REJECTED


@pytest.mark.asyncio
async def test_policy_disable_before_entry_preflight_causes_zero_venue_mutations(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)
    async with dispatch_engine.begin() as connection:
        await connection.execute(
            sa.update(owner_policy_current)
            .where(owner_policy_current.c.owner_policy_id == "policy-main")
            .values(new_entry_submit_enabled=False)
        )
    venue = CountingVenue()

    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        venue,
        DispatchCommandRequest(
            worker_id="entry-dispatcher",
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=1,
            runtime_commit="kernel-test-head",
            schema_revision="0001_trading_kernel_baseline_v4",
            admission_snapshot_validity_ms=1_000,
        ),
        entry_facts_source=PreflightFacts(),
    )

    assert result.status is DispatchCommandStatus.SUPERSEDED
    assert venue.calls == 0
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        command = await uow.exchange_commands.get(result.command_id or "")
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
    assert command is not None and command.status is ExchangeCommandStatus.REJECTED
    assert aggregate is not None and aggregate.status is AggregateStatus.ENTRY_REJECTED
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
        exposure = await uow.entry_admission.get_account_exposure(
            ticket.identity.netting_domain.venue_id,
            ticket.identity.netting_domain.account_id,
        )
        domain_active = await uow.entry_admission.has_active_ticket_in_domain(
            ticket.identity.netting_domain.key()
        )
    assert reservation is not None and reservation.status == "released"
    assert exposure is not None and exposure.active_ticket_count == 0
    assert domain_active is False


@pytest.mark.asyncio
async def test_retired_strategy_version_before_entry_preflight_causes_zero_venue_mutations(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)
    async with dispatch_engine.begin() as connection:
        await connection.execute(
            sa.update(strategy_versions)
            .where(
                strategy_versions.c.strategy_version_id
                == ticket.identity.runtime.strategy_version_id
            )
            .values(status="retired")
        )
    venue = CountingVenue()

    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        venue,
        DispatchCommandRequest(
            worker_id="entry-dispatcher",
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=1,
            runtime_commit="kernel-test-head",
            schema_revision="0001_trading_kernel_baseline_v4",
            admission_snapshot_validity_ms=1_000,
        ),
        entry_facts_source=PreflightFacts(),
    )

    assert result.status is DispatchCommandStatus.SUPERSEDED
    assert venue.calls == 0
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
    assert aggregate is not None and aggregate.status is AggregateStatus.ENTRY_REJECTED


@pytest.mark.asyncio
async def test_universe_pointer_switch_after_preflight_is_fenced_by_claimed_entry_lane(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)
    await _seed_replacement_universe(dispatch_engine, ticket)
    venue = CountingVenue()
    barrier_factory = PreflightExitBarrierFactory(dispatch_engine)
    dispatch_task = asyncio.create_task(
        dispatch_one_command(
            barrier_factory,
            venue,
            DispatchCommandRequest(
                worker_id="entry-dispatcher",
                now_ms=1_100,
                lease_until_ms=6_100,
                timeout_seconds=1,
                runtime_commit="kernel-test-head",
                schema_revision="0001_trading_kernel_baseline_v4",
                admission_snapshot_validity_ms=1_000,
            ),
            entry_facts_source=PreflightFacts(),
        )
    )
    await asyncio.wait_for(barrier_factory.preflight_closed.wait(), timeout=2)

    switch_blocked = False
    switch_error = ""
    try:
        async with dispatch_engine.begin() as connection:
            await connection.execute(
                sa.update(strategy_universe_current)
                .where(
                    strategy_universe_current.c.event_spec_id
                    == ticket.identity.runtime.event_spec_id
                )
                .values(
                    universe_version_id="universe:sor-long:replacement",
                    semantic_digest="sha256:" + "b" * 64,
                    activation_generation=2,
                    activated_at_ms=1_101,
                )
            )
    except DBAPIError as exc:
        switch_error = str(exc)
        switch_blocked = (
            "strategy universe activation is fenced by global ENTRY lane"
            in switch_error
            and getattr(exc.orig, "sqlstate", None) == "55000"
        )
    finally:
        barrier_factory.release_dispatch.set()

    result = await dispatch_task
    assert switch_blocked is True, switch_error
    assert result.status is DispatchCommandStatus.ACCEPTED
    assert venue.calls == 1
    async with dispatch_engine.connect() as connection:
        current_version_id = await connection.scalar(
            sa.select(strategy_universe_current.c.universe_version_id).where(
                strategy_universe_current.c.event_spec_id
                == ticket.identity.runtime.event_spec_id
            )
        )
    assert current_version_id == ticket.universe_version_id


@pytest.mark.parametrize(
    ("command_kind", "command_status", "switch_allowed"),
    [
        pytest.param(
            ExchangeCommandKind.SET_LEVERAGE,
            ExchangeCommandStatus.PREPARED,
            False,
            id="set-leverage-prepared-blocks",
        ),
        pytest.param(
            ExchangeCommandKind.SET_LEVERAGE,
            ExchangeCommandStatus.CLAIMED,
            False,
            id="set-leverage-claimed-blocks",
        ),
        pytest.param(
            ExchangeCommandKind.SET_LEVERAGE,
            ExchangeCommandStatus.OUTCOME_UNKNOWN,
            False,
            id="set-leverage-outcome-unknown-blocks",
        ),
        pytest.param(
            ExchangeCommandKind.ENTRY,
            ExchangeCommandStatus.PREPARED,
            False,
            id="entry-prepared-blocks",
        ),
        pytest.param(
            ExchangeCommandKind.ENTRY,
            ExchangeCommandStatus.CLAIMED,
            False,
            id="entry-claimed-blocks",
        ),
        pytest.param(
            ExchangeCommandKind.ENTRY,
            ExchangeCommandStatus.OUTCOME_UNKNOWN,
            False,
            id="entry-outcome-unknown-blocks",
        ),
        pytest.param(
            ExchangeCommandKind.ENTRY,
            ExchangeCommandStatus.ACCEPTED,
            True,
            id="entry-accepted-allows",
        ),
    ],
)
@pytest.mark.asyncio
async def test_universe_pointer_fence_uses_entry_mutation_state_matrix(
    dispatch_engine: AsyncEngine,
    command_kind: ExchangeCommandKind,
    command_status: ExchangeCommandStatus,
    switch_allowed: bool,
) -> None:
    ticket = _ticket(
        leverage_change_required=command_kind is ExchangeCommandKind.SET_LEVERAGE
    )
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)
    await _seed_replacement_universe(dispatch_engine, ticket)
    async with dispatch_engine.begin() as connection:
        update_result = await connection.execute(
            sa.update(exchange_commands)
            .where(
                exchange_commands.c.ticket_id == ticket.identity.ticket_id,
                exchange_commands.c.command_kind == command_kind.value,
            )
            .values(status=command_status.value)
        )
    assert update_result.rowcount == 1

    pointer_update = (
        sa.update(strategy_universe_current)
        .where(
            strategy_universe_current.c.event_spec_id
            == ticket.identity.runtime.event_spec_id
        )
        .values(
            universe_version_id="universe:sor-long:replacement",
            semantic_digest="sha256:" + "b" * 64,
            activation_generation=2,
            activated_at_ms=1_101,
        )
    )
    if switch_allowed:
        async with dispatch_engine.begin() as connection:
            await connection.execute(pointer_update)
    else:
        with pytest.raises(DBAPIError) as error:
            async with dispatch_engine.begin() as connection:
                await connection.execute(pointer_update)
        assert getattr(error.value.orig, "sqlstate", None) == "55000"

    async with dispatch_engine.connect() as connection:
        current_version_id = await connection.scalar(
            sa.select(strategy_universe_current.c.universe_version_id).where(
                strategy_universe_current.c.event_spec_id
                == ticket.identity.runtime.event_spec_id
            )
        )
    expected_version_id = (
        "universe:sor-long:replacement"
        if switch_allowed
        else ticket.universe_version_id
    )
    assert current_version_id == expected_version_id


@pytest.mark.asyncio
async def test_confirmed_leverage_creates_first_entry_command_in_later_transaction(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket(leverage_change_required=True)
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)
    venue = LeverageThenEntryVenue()

    first = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        venue,
        DispatchCommandRequest(
            worker_id="leverage-dispatcher",
            ticket_id=ticket.identity.ticket_id,
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=1,
            runtime_commit="kernel-test-head",
            schema_revision="0001_trading_kernel_baseline_v4",
            admission_snapshot_validity_ms=1_000,
        ),
        entry_facts_source=PreflightFacts(configured_leverage=4),
    )

    assert first.status is DispatchCommandStatus.ACCEPTED
    assert venue.mutations == ["set_leverage"]
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
    assert [(item.kind, item.generation) for item in commands] == [
        (ExchangeCommandKind.SET_LEVERAGE, 1),
        (ExchangeCommandKind.ENTRY, 1),
    ]
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.LEVERAGE_CONFIRMED


@pytest.mark.asyncio
async def test_leverage_readback_mismatch_becomes_unknown_without_entry_or_resend(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket(leverage_change_required=True)
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)
    venue = LeverageReadbackMismatchVenue()

    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        venue,
        DispatchCommandRequest(
            worker_id="leverage-dispatcher",
            ticket_id=ticket.identity.ticket_id,
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=1,
            runtime_commit="kernel-test-head",
            schema_revision="0001_trading_kernel_baseline_v4",
            admission_snapshot_validity_ms=1_000,
        ),
        entry_facts_source=PreflightFacts(configured_leverage=4),
    )

    assert result.status is DispatchCommandStatus.OUTCOME_UNKNOWN
    assert venue.mutations == ["set_leverage"]
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
    assert [(item.kind, item.status) for item in commands] == [
        (ExchangeCommandKind.SET_LEVERAGE, ExchangeCommandStatus.OUTCOME_UNKNOWN)
    ]
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.LEVERAGE_OUTCOME_UNKNOWN


@pytest.mark.asyncio
async def test_coded_leverage_failure_persists_sanitized_reason(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket(leverage_change_required=True)
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)

    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        CodedLeverageFailureVenue(),
        DispatchCommandRequest(
            worker_id="leverage-dispatcher",
            ticket_id=ticket.identity.ticket_id,
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=1,
            runtime_commit="kernel-test-head",
            schema_revision="0001_trading_kernel_baseline_v4",
            admission_snapshot_validity_ms=1_000,
        ),
        entry_facts_source=PreflightFacts(configured_leverage=4),
    )

    assert result.status is DispatchCommandStatus.OUTCOME_UNKNOWN
    assert result.command_id is not None
    async with dispatch_engine.connect() as connection:
        payload = await connection.scalar(
            sa.select(exchange_commands.c.result_payload).where(
                exchange_commands.c.command_id == result.command_id
            )
        )
    assert payload == {
        "status": "outcome_unknown",
        "observed_at_ms": 1_100,
        "exchange_order_id": None,
        "reason": "venue_error:exchange_code_-4164",
        "venue_payload": {},
    }


@pytest.mark.asyncio
async def test_prepared_command_is_superseded_before_venue_write_when_state_moves_on(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)
    accepting = KindAwareAcceptingVenue()
    await _dispatch_for_ticket(dispatch_engine, accepting, ticket.identity.ticket_id)
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price=ticket.entry_reference_price,
                    venue_reported_liquidation_price=_raw_liquidation_observation(
                        ticket, ticket.entry_reference_price
                    ),
                    observed_at_ms=2_100,
                ),
            ),
        )
    await _dispatch_for_ticket(dispatch_engine, accepting, ticket.identity.ticket_id)

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        assert aggregate is not None
        assert aggregate.status is AggregateStatus.TP1_PENDING
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=Decimal(0),
                    average_entry_price=None,
                    open_orders=(
                        VenueOrderSnapshot(
                            exchange_order_id=str(
                                aggregate.initial_stop_exchange_order_id
                            ),
                            venue_client_order_id="brc-initial-stop",
                            position_side="long",
                            reduce_only=True,
                        ),
                    ),
                    observed_at_ms=2_300,
                ),
            ),
        )

    venue = CountingKindAwareAcceptingVenue()
    superseded = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        venue,
        DispatchCommandRequest(
            worker_id="lifecycle-dispatcher",
            ticket_id=ticket.identity.ticket_id,
            now_ms=2_400,
            lease_until_ms=7_400,
            timeout_seconds=1,
        ),
    )

    assert superseded.status is DispatchCommandStatus.SUPERSEDED
    assert venue.calls == 0
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    tp1 = next(
        command
        for command in commands
        if command.kind is ExchangeCommandKind.TAKE_PROFIT
    )
    assert tp1.status is ExchangeCommandStatus.SUPERSEDED

    cleanup = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        venue,
        DispatchCommandRequest(
            worker_id="lifecycle-dispatcher",
            ticket_id=ticket.identity.ticket_id,
            now_ms=2_500,
            lease_until_ms=7_500,
            timeout_seconds=1,
        ),
    )
    assert cleanup.status is DispatchCommandStatus.ACCEPTED
    assert venue.calls == 1


@pytest.mark.asyncio
async def test_tp1_and_replacement_commands_reach_protected_runner(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)
    venue = KindAwareAcceptingVenue()

    await _dispatch_for_ticket(dispatch_engine, venue, ticket.identity.ticket_id)
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price=ticket.entry_reference_price,
                    venue_reported_liquidation_price=_raw_liquidation_observation(
                        ticket, ticket.entry_reference_price
                    ),
                    observed_at_ms=2_100,
                ),
            ),
        )
    await _dispatch_for_ticket(dispatch_engine, venue, ticket.identity.ticket_id)
    await _dispatch_for_ticket(dispatch_engine, venue, ticket.identity.ticket_id)

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.POSITION_PROTECTED
    tp1 = next(
        command
        for command in commands
        if command.kind is ExchangeCommandKind.TAKE_PROFIT
    )
    assert isinstance(tp1.payload, OrderCommandPayload)
    assert tp1.payload.order_type == "limit"
    assert tp1.payload.time_in_force == "GTX"
    assert tp1.payload.reduce_only is True
    assert tp1.payload.quantity == ticket.take_profit_quantities[0]
    assert tp1.payload.limit_price == ticket.take_profit_prices[0]

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        assert aggregate is not None
        event = TakeProfitFilled(
            event_id=f"event:{ticket.identity.ticket_id}:{aggregate.last_event_sequence + 1}",
            ticket_id=ticket.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_300,
            filled_qty=ticket.take_profit_quantities[0],
            average_fill_price=ticket.take_profit_prices[0],
            runner_floor_price=Decimal(60010),
        )
        await uow.commit_reduction(
            event=event,
            reduction=reduce_event(aggregate, event),
            expected_version=aggregate.version,
        )

    await _dispatch_for_ticket(dispatch_engine, venue, ticket.identity.ticket_id)
    await _dispatch_for_ticket(dispatch_engine, venue, ticket.identity.ticket_id)

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.RUNNER_PROTECTED
    assert aggregate.position_qty == ticket.quantity - ticket.take_profit_quantities[0]
    replacement = next(
        command
        for command in commands
        if command.kind is ExchangeCommandKind.REPLACE_PROTECTION
    )
    assert isinstance(replacement.payload, OrderCommandPayload)
    assert replacement.payload.order_type == "stop_market"
    assert replacement.payload.stop_price == Decimal(60010)
    assert replacement.payload.replaces_exchange_order_id == "venue-initial_stop-1"
    assert replacement.payload.source_watermark_ms == 2_300


@pytest.mark.asyncio
async def test_tp1_rejection_is_persisted_without_losing_initial_protection(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)
    accepting = KindAwareAcceptingVenue()
    await _dispatch_for_ticket(dispatch_engine, accepting, ticket.identity.ticket_id)
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price=ticket.entry_reference_price,
                    venue_reported_liquidation_price=_raw_liquidation_observation(
                        ticket, ticket.entry_reference_price
                    ),
                    observed_at_ms=2_100,
                ),
            ),
        )
    await _dispatch_for_ticket(dispatch_engine, accepting, ticket.identity.ticket_id)
    rejected = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        RejectingVenue(),
        DispatchCommandRequest(
            worker_id="tp1-dispatcher",
            ticket_id=ticket.identity.ticket_id,
            now_ms=2_300,
            lease_until_ms=7_300,
            timeout_seconds=1,
        ),
    )
    assert rejected.status is DispatchCommandStatus.REJECTED
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.TP1_REJECTED
    assert aggregate.active_stop_exchange_order_id == "venue-initial_stop-1"
    assert incident is not None and incident.incident_kind == "take_profit_rejected"


@pytest.mark.asyncio
async def test_replacement_rejection_preserves_the_prior_active_stop(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)
    accepting = KindAwareAcceptingVenue()
    await _dispatch_for_ticket(dispatch_engine, accepting, ticket.identity.ticket_id)
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price=ticket.entry_reference_price,
                    venue_reported_liquidation_price=_raw_liquidation_observation(
                        ticket, ticket.entry_reference_price
                    ),
                    observed_at_ms=2_100,
                ),
            ),
        )
    await _dispatch_for_ticket(dispatch_engine, accepting, ticket.identity.ticket_id)
    await _dispatch_for_ticket(dispatch_engine, accepting, ticket.identity.ticket_id)
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        assert aggregate is not None
        event = TakeProfitFilled(
            event_id=f"event:{ticket.identity.ticket_id}:{aggregate.last_event_sequence + 1}",
            ticket_id=ticket.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_300,
            filled_qty=ticket.take_profit_quantities[0],
            average_fill_price=ticket.take_profit_prices[0],
            runner_floor_price=Decimal(60010),
        )
        await uow.commit_reduction(
            event=event,
            reduction=reduce_event(aggregate, event),
            expected_version=aggregate.version,
        )
    rejected = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        RejectingVenue(),
        DispatchCommandRequest(
            worker_id="replacement-dispatcher",
            ticket_id=ticket.identity.ticket_id,
            now_ms=2_400,
            lease_until_ms=7_400,
            timeout_seconds=1,
        ),
    )
    assert rejected.status is DispatchCommandStatus.REJECTED
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.RUNNER_REPLACEMENT_REJECTED
    assert aggregate.active_stop_exchange_order_id == "venue-initial_stop-1"
    assert incident is not None
    assert incident.incident_kind == "protection_replacement_rejected"


async def _dispatch_for_ticket(
    engine: AsyncEngine,
    venue,
    ticket_id: str,
) -> None:
    await _commit_passed_post_fill_stress_if_pending(engine, ticket_id)
    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine),
        venue,
        DispatchCommandRequest(
            worker_id="lifecycle-dispatcher",
            ticket_id=ticket_id,
            now_ms=2_200,
            lease_until_ms=7_200,
            timeout_seconds=1,
            runtime_commit="kernel-test-head",
            schema_revision="0001_trading_kernel_baseline_v4",
            admission_snapshot_validity_ms=1_000,
        ),
        entry_facts_source=PreflightFacts(),
    )
    assert result.status is DispatchCommandStatus.ACCEPTED
    await _commit_passed_post_fill_stress_if_pending(engine, ticket_id)


async def _commit_passed_post_fill_stress_if_pending(
    engine: AsyncEngine,
    ticket_id: str,
) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        aggregate = await uow.aggregates.get(ticket_id)
        if (
            aggregate is not None
            and aggregate.status is AggregateStatus.POST_FILL_RISK_PENDING
        ):
            assert aggregate.average_fill_price is not None
            assert aggregate.initial_stop_exchange_order_id is not None
            event = PostFillStressAssessed(
                event_id=(
                    f"event:{ticket_id}:"
                    f"{aggregate.last_event_sequence + 1}"
                ),
                ticket_id=ticket_id,
                sequence=aggregate.last_event_sequence + 1,
                occurred_at_ms=2_200,
                status="passed",
                evidence=_stress_evidence(aggregate.ticket),
                owner_policy_id=aggregate.ticket.owner_policy_id,
                owner_policy_version=aggregate.ticket.owner_policy_version,
                filled_qty=aggregate.position_qty,
                average_fill_price=aggregate.average_fill_price,
                initial_stop_price=aggregate.ticket.initial_stop_price,
                initial_stop_exchange_order_id=(
                    aggregate.initial_stop_exchange_order_id
                ),
            )
            await uow.commit_reduction(
                event=event,
                reduction=reduce_event(aggregate, event),
                expected_version=aggregate.version,
            )


@pytest.mark.asyncio
async def test_dispatch_claims_then_calls_venue_outside_transaction_and_records_acceptance(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)
    venue = AcceptingVenue(dispatch_engine)

    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        venue,
        DispatchCommandRequest(
            worker_id="dispatcher-1",
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=1,
            runtime_commit="kernel-test-head",
            schema_revision="0001_trading_kernel_baseline_v4",
            admission_snapshot_validity_ms=1_000,
        ),
        entry_facts_source=PreflightFacts(),
    )

    assert result.status is DispatchCommandStatus.ACCEPTED
    assert venue.saw_committed_claim is True

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        events = await uow.events.list_for_ticket(ticket.identity.ticket_id)

    assert len(commands) == 1
    assert commands[0].status is ExchangeCommandStatus.ACCEPTED
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.ENTRY_ACCEPTED
    assert aggregate.entry_exchange_order_id == "venue-entry-1"
    assert len(events) == 2

    repeated = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        venue,
        DispatchCommandRequest(
            worker_id="dispatcher-2",
            now_ms=2_100,
            lease_until_ms=7_100,
            timeout_seconds=1,
        ),
    )
    assert repeated.status is DispatchCommandStatus.NO_COMMAND


@pytest.mark.asyncio
async def test_authoritative_entry_rejection_releases_lane_and_budget_without_retry(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)

    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        RejectingVenue(),
        DispatchCommandRequest(
            worker_id="dispatcher-1",
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=1,
            runtime_commit="kernel-test-head",
            schema_revision="0001_trading_kernel_baseline_v4",
            admission_snapshot_validity_ms=1_000,
        ),
        entry_facts_source=PreflightFacts(),
    )

    assert result.status is DispatchCommandStatus.REJECTED
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
        lane = await uow.entry_admission.get_global_lane()
        exposure = await uow.entry_admission.get_account_exposure(
            ticket.identity.netting_domain.venue_id,
            ticket.identity.netting_domain.account_id
        )
        persisted_ticket = await uow.tickets.get(ticket.identity.ticket_id)

    assert aggregate is not None
    assert aggregate.status is AggregateStatus.ENTRY_REJECTED
    assert len(commands) == 1
    assert commands[0].status is ExchangeCommandStatus.REJECTED
    assert reservation is not None and reservation.status == "released"
    assert lane is not None and lane.status == "idle"
    assert exposure is not None and exposure.active_ticket_count == 0
    assert persisted_ticket is not None
    assert persisted_ticket.status.value == "entry_rejected"

    repeated = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        RejectingVenue(),
        DispatchCommandRequest(
            worker_id="dispatcher-2",
            now_ms=2_100,
            lease_until_ms=7_100,
            timeout_seconds=1,
        ),
    )
    assert repeated.status is DispatchCommandStatus.NO_COMMAND


@pytest.mark.asyncio
async def test_timeout_becomes_unknown_outcome_incident_and_is_never_redispatched(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)

    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        SlowVenue(),
        DispatchCommandRequest(
            worker_id="dispatcher-1",
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=0.01,
            runtime_commit="kernel-test-head",
            schema_revision="0001_trading_kernel_baseline_v4",
            admission_snapshot_validity_ms=1_000,
        ),
        entry_facts_source=PreflightFacts(),
    )

    assert result.status is DispatchCommandStatus.OUTCOME_UNKNOWN
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
        lane = await uow.entry_admission.get_global_lane()

    assert aggregate is not None
    assert aggregate.status is AggregateStatus.ENTRY_OUTCOME_UNKNOWN
    assert len(commands) == 1
    assert commands[0].status is ExchangeCommandStatus.OUTCOME_UNKNOWN
    assert incident is not None
    assert incident.incident_kind == "entry_outcome_unknown"
    assert reservation is not None and reservation.status == "active"
    assert lane is not None and lane.status == "claimed"

    repeated = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        SlowVenue(),
        DispatchCommandRequest(
            worker_id="dispatcher-2",
            now_ms=7_000,
            lease_until_ms=12_000,
            timeout_seconds=0.01,
        ),
    )
    assert repeated.status is DispatchCommandStatus.NO_COMMAND


@pytest.mark.asyncio
async def test_restart_conserves_expired_claim_as_unknown_without_redispatch(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        claimed = await uow.exchange_commands.claim_one_prepared(
            worker_id="crashed-worker",
            now_ms=1_100,
            lease_until_ms=1_200,
        )
    assert claimed is not None

    venue = CountingVenue()
    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        venue,
        DispatchCommandRequest(
            worker_id="restart-worker",
            now_ms=1_300,
            lease_until_ms=6_300,
            timeout_seconds=1,
        ),
    )

    assert result.status is DispatchCommandStatus.OUTCOME_UNKNOWN
    assert venue.calls == 0

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)

    assert aggregate is not None
    assert aggregate.status is AggregateStatus.ENTRY_OUTCOME_UNKNOWN
    assert commands[0].status is ExchangeCommandStatus.OUTCOME_UNKNOWN
    assert incident is not None


@pytest.mark.asyncio
async def test_initial_stop_rejection_is_persisted_and_prepares_controlled_exit(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)
    await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        AcceptingVenue(dispatch_engine),
        DispatchCommandRequest(
            worker_id="entry-dispatcher",
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=1,
            runtime_commit="kernel-test-head",
            schema_revision="0001_trading_kernel_baseline_v4",
            admission_snapshot_validity_ms=1_000,
        ),
        entry_facts_source=PreflightFacts(),
    )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price=Decimal(60000),
                    venue_reported_liquidation_price=_raw_liquidation_observation(
                        ticket, Decimal(60000)
                    ),
                    observed_at_ms=2_100,
                ),
            ),
        )

    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        RejectingVenue(),
        DispatchCommandRequest(
            worker_id="stop-dispatcher",
            now_ms=2_200,
            lease_until_ms=7_200,
            timeout_seconds=1,
        ),
    )

    assert result.status is DispatchCommandStatus.REJECTED
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
        lane = await uow.entry_admission.get_global_lane()

    assert aggregate is not None
    assert aggregate.status is AggregateStatus.EXIT_PENDING
    assert aggregate.entry_lane_held is True
    assert {command.kind.value: command.status for command in commands} == {
        "entry": ExchangeCommandStatus.ACCEPTED,
        "initial_stop": ExchangeCommandStatus.REJECTED,
        "exit": ExchangeCommandStatus.PREPARED,
    }
    assert incident is not None
    assert incident.incident_kind == "initial_stop_rejected"
    assert lane is not None and lane.status == "claimed"


@pytest.mark.asyncio
async def test_initial_stop_timeout_waits_for_truth_without_duplicate_exit(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)
    await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        AcceptingVenue(dispatch_engine),
        DispatchCommandRequest(
            worker_id="entry-dispatcher",
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=1,
            runtime_commit="kernel-test-head",
            schema_revision="0001_trading_kernel_baseline_v4",
            admission_snapshot_validity_ms=1_000,
        ),
        entry_facts_source=PreflightFacts(),
    )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price=Decimal(60000),
                    venue_reported_liquidation_price=_raw_liquidation_observation(
                        ticket, Decimal(60000)
                    ),
                    observed_at_ms=2_100,
                ),
            ),
        )

    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        SlowVenue(),
        DispatchCommandRequest(
            worker_id="stop-dispatcher",
            now_ms=2_200,
            lease_until_ms=7_200,
            timeout_seconds=0.01,
        ),
    )

    assert result.status is DispatchCommandStatus.OUTCOME_UNKNOWN
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)

    assert (
        aggregate is not None
        and aggregate.status is AggregateStatus.INITIAL_STOP_OUTCOME_UNKNOWN
    )
    assert [
        command.status
        for command in commands
        if command.kind.value == "initial_stop"
    ] == [ExchangeCommandStatus.OUTCOME_UNKNOWN]
    assert [command.kind.value for command in commands].count("initial_stop") == 1
    assert all(command.kind.value != "exit" for command in commands)
    assert incident is not None
    assert incident.incident_kind == "initial_stop_outcome_unknown"


@pytest.mark.asyncio
async def test_exit_rejection_is_persisted_and_explicit_retry_uses_new_generation(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)
    accepting = AcceptingVenue(dispatch_engine)
    await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        accepting,
        DispatchCommandRequest(
            worker_id="entry-dispatcher",
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=1,
            runtime_commit="kernel-test-head",
            schema_revision="0001_trading_kernel_baseline_v4",
            admission_snapshot_validity_ms=1_000,
        ),
        entry_facts_source=PreflightFacts(),
    )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price=Decimal(60000),
                    venue_reported_liquidation_price=_raw_liquidation_observation(
                        ticket, Decimal(60000)
                    ),
                    observed_at_ms=2_100,
                ),
            ),
        )
    await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        accepting,
        DispatchCommandRequest(
            worker_id="stop-dispatcher",
            now_ms=2_200,
            lease_until_ms=7_200,
            timeout_seconds=1,
        ),
    )
    await _dispatch_for_ticket(
        dispatch_engine,
        accepting,
        ticket.identity.ticket_id,
    )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await request_exit(
            uow,
            ExitTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                reason="strategy_exit",
                requested_at_ms=3_000,
            ),
        )

    rejected = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        RejectingVenue(),
        DispatchCommandRequest(
            worker_id="exit-dispatcher",
            now_ms=3_100,
            lease_until_ms=8_100,
            timeout_seconds=1,
        ),
    )
    assert rejected.status is DispatchCommandStatus.REJECTED

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None and aggregate.status is AggregateStatus.EXIT_REJECTED
    assert incident is not None and incident.incident_kind == "exit_rejected"

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await request_exit(
            uow,
            ExitTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                reason="recover_exit_rejection",
                requested_at_ms=3_200,
            ),
        )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    exit_commands = [
        command for command in commands if command.kind.value == "exit"
    ]
    assert [command.generation for command in exit_commands] == [1, 2]
    assert [command.status for command in exit_commands] == [
        ExchangeCommandStatus.REJECTED,
        ExchangeCommandStatus.PREPARED,
    ]


@pytest.mark.asyncio
async def test_cancel_rejection_is_persisted_and_blocks_settlement(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    accepting = AcceptingVenue(dispatch_engine)
    await _reach_cancel_pending(dispatch_engine, ticket, accepting)

    rejected = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        RejectingVenue(),
        DispatchCommandRequest(
            worker_id="cancel-dispatcher",
            now_ms=3_300,
            lease_until_ms=8_300,
            timeout_seconds=1,
        ),
    )

    assert rejected.status is DispatchCommandStatus.REJECTED
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)

    assert aggregate is not None
    assert aggregate.status is AggregateStatus.CANCEL_REJECTED
    assert aggregate.pending_cancel_exchange_order_id == "venue-take_profit-1"
    cancel_commands = [
        command for command in commands if command.kind.value == "cancel_order"
    ]
    assert len(cancel_commands) == 1
    assert cancel_commands[0].status is ExchangeCommandStatus.REJECTED
    assert incident is not None and incident.incident_kind == "cancel_order_rejected"
    assert reservation is not None and reservation.status == "active"

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        retry_requested = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=Decimal(0),
                    average_entry_price=None,
                    open_orders=(
                        VenueOrderSnapshot(
                            exchange_order_id="venue-take_profit-1",
                            venue_client_order_id="brc-owned-tp1",
                            position_side="long",
                            reduce_only=True,
                        ),
                    ),
                    observed_at_ms=3_400,
                ),
            ),
        )
    assert retry_requested.status.value == "owned_orphan_cancel_requested"
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    cancel_commands = [
        command for command in commands if command.kind.value == "cancel_order"
    ]
    assert [command.generation for command in cancel_commands] == [1, 2]
    assert [command.status for command in cancel_commands] == [
        ExchangeCommandStatus.REJECTED,
        ExchangeCommandStatus.PREPARED,
    ]

    accepted = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        accepting,
        DispatchCommandRequest(
            worker_id="retry-cancel-dispatcher",
            now_ms=3_500,
            lease_until_ms=8_500,
            timeout_seconds=1,
        ),
    )

    assert accepted.status is DispatchCommandStatus.ACCEPTED
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.RECONCILIATION_PENDING
    assert aggregate.pending_cancel_exchange_order_id is None


@pytest.mark.asyncio
async def test_cancel_timeout_is_conserved_without_retry_and_blocks_settlement(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _reach_cancel_pending(
        dispatch_engine,
        ticket,
        AcceptingVenue(dispatch_engine),
    )

    unknown = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        SlowVenue(),
        DispatchCommandRequest(
            worker_id="cancel-dispatcher",
            now_ms=3_300,
            lease_until_ms=8_300,
            timeout_seconds=0.01,
        ),
    )

    assert unknown.status is DispatchCommandStatus.OUTCOME_UNKNOWN
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.CANCEL_OUTCOME_UNKNOWN
    cancel_commands = [
        command for command in commands if command.kind.value == "cancel_order"
    ]
    assert len(cancel_commands) == 1
    assert cancel_commands[0].status is ExchangeCommandStatus.OUTCOME_UNKNOWN
    assert incident is not None
    assert incident.incident_kind == "cancel_order_outcome_unknown"
    assert reservation is not None and reservation.status == "active"

    repeated = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        CountingVenue(),
        DispatchCommandRequest(
            worker_id="repeat-dispatcher",
            now_ms=8_500,
            lease_until_ms=13_500,
            timeout_seconds=1,
        ),
    )
    assert repeated.status is DispatchCommandStatus.NO_COMMAND

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        blocked = await reconcile_ticket(
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
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
    assert blocked.status.value == "cancel_absence_recorded"
    assert reservation is not None and reservation.status == "active"
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.RECONCILIATION_PENDING
    assert aggregate.pending_cancel_exchange_order_id is None
    cancel_commands = [
        command for command in commands if command.kind.value == "cancel_order"
    ]
    assert cancel_commands[0].status is ExchangeCommandStatus.RECONCILED_ABSENT

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        stop_absence = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=Decimal(0),
                    average_entry_price=None,
                    open_orders=(),
                    observed_at_ms=3_500,
                ),
            ),
        )
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
    assert stop_absence.status.value == "cancel_absence_recorded"
    assert reservation is not None and reservation.status == "active"

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        matched = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=Decimal(0),
                    average_entry_price=None,
                    open_orders=(),
                    observed_at_ms=3_600,
                ),
            ),
        )
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
    assert matched.status.value == "matched"
    assert reservation is not None and reservation.status == "released"


async def _seed_policy(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(owner_policy_current).values(
                owner_policy_id="policy-main",
                policy_version=7,
                enabled=True,
                new_entry_submit_enabled=True,
                priority_rank=1,
                max_concurrent_tickets=3,
                max_strategy_group_concurrent_tickets=2,
                max_ticket_stop_risk_fraction="0.03",
                max_gross_stop_risk_fraction="0.06",
                max_ticket_initial_margin_fraction="0.45",
                max_gross_initial_margin_utilization="0.90",
                max_leverage=10,
                supported_margin_mode="cross",
                post_stop_stress_multiple="2.0",
                max_post_fill_stop_risk_overrun_fraction="0.10",
                scope={},
                updated_at_ms=1_000,
            )
        )


async def _issue(engine: AsyncEngine, ticket) -> None:
    await _seed_ticket_runtime_scope(engine, ticket)
    async with engine.begin() as connection:
        await connection.execute(
            pg_insert(runtime_capabilities_current)
            .values(
                capability_key="exchange_commands",
                enabled=True,
                certified_commit="kernel-test-head",
                schema_revision="0001_trading_kernel_baseline_v4",
                certification={},
                updated_at_ms=1_000,
            )
            .on_conflict_do_update(
                index_elements=[runtime_capabilities_current.c.capability_key],
                set_={
                    "enabled": True,
                    "certified_commit": "kernel-test-head",
                    "schema_revision": "0001_trading_kernel_baseline_v4",
                    "certification": {},
                    "updated_at_ms": 1_000,
                },
            )
        )
    async with PostgresKernelUnitOfWork(engine) as uow:
        result = await issue_ticket(
            uow,
            _issue_request(ticket=ticket, now_ms=1_001, claim_owner="issuer-1"),
        )
    assert result.status is IssueTicketStatus.ISSUED


async def _reach_cancel_pending(
    engine: AsyncEngine,
    ticket,
    accepting: AcceptingVenue,
) -> None:
    await _issue(engine, ticket)
    await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine),
        accepting,
        DispatchCommandRequest(
            worker_id="entry-dispatcher",
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=1,
            runtime_commit="kernel-test-head",
            schema_revision="0001_trading_kernel_baseline_v4",
            admission_snapshot_validity_ms=1_000,
        ),
        entry_facts_source=PreflightFacts(),
    )
    async with PostgresKernelUnitOfWork(engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price=Decimal(60000),
                    venue_reported_liquidation_price=_raw_liquidation_observation(
                        ticket, Decimal(60000)
                    ),
                    observed_at_ms=2_100,
                ),
            ),
        )
    await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine),
        accepting,
        DispatchCommandRequest(
            worker_id="stop-dispatcher",
            now_ms=2_200,
            lease_until_ms=7_200,
            timeout_seconds=1,
        ),
    )
    await _dispatch_for_ticket(engine, accepting, ticket.identity.ticket_id)
    async with PostgresKernelUnitOfWork(engine) as uow:
        await request_exit(
            uow,
            ExitTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                reason="strategy_exit",
                requested_at_ms=3_000,
            ),
        )
    await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine),
        accepting,
        DispatchCommandRequest(
            worker_id="exit-dispatcher",
            now_ms=3_100,
            lease_until_ms=8_100,
            timeout_seconds=1,
        ),
    )
    async with PostgresKernelUnitOfWork(engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=Decimal(0),
                    average_entry_price=None,
                    observed_at_ms=3_200,
                ),
            ),
        )


def _database_url(database_name: str) -> str:
    if SAFE_DATABASE.fullmatch(database_name) is None:
        raise ValueError("unsafe kernel test database name")
    base = ADMIN_DSN.rsplit("/", 1)[0]
    return f"{base.replace('postgresql://', 'postgresql+asyncpg://', 1)}/{database_name}"


def _run_alembic(database_url: str, *args: str) -> None:
    env = {**os.environ, "TRADING_KERNEL_DATABASE_URL": database_url}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "migrations/trading_kernel/alembic.ini",
            *args,
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-4000:]
