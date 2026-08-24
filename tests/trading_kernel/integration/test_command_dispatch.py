from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.application.dispatch_exchange_command import (
    DispatchCommandRequest,
    DispatchCommandStatus,
    dispatch_one_command,
)
from src.trading_kernel.application.issue_ticket import IssueTicketStatus, issue_ticket
from src.trading_kernel.application.ports import (
    MonitorOwnerStatus,
    VenueCommandRequest,
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
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import (
    ExchangeCommandKind,
    ExchangeCommandResult,
    ExchangeCommandStatus,
    OrderCommandPayload,
    SetLeverageCommandResult,
)
from src.trading_kernel.domain.events import PostFillStressAssessed, TakeProfitFilled
from src.trading_kernel.domain.identities import TicketIdentity
from src.trading_kernel.domain.position import PositionSnapshot, VenueOrderSnapshot
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.domain.ticket import build_ticket_id
from src.trading_kernel.infrastructure.pg_models import (
    exchange_commands,
    instrument_product_profiles,
    owner_policy_current,
    runtime_capabilities_current,
    strategy_entry_controls_current,
    strategy_universe_current,
    strategy_versions,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_identity import (
    CURRENT_SCHEMA_REVISION,
)
from tests.trading_kernel.support.capacity_claims import (
    make_issue_request as _issue_request,
)
from tests.trading_kernel.support.capacity_claims import (
    make_stress_evidence as _stress_evidence,
)
from tests.trading_kernel.support.dispatch_venues import (
    AcceptingVenue,
    CountingVenue,
    KindAwareAcceptingVenue,
    PreflightFacts,
    SlowVenue,
)
from tests.trading_kernel.support.runtime_scope import (
    seed_replacement_universe as _seed_replacement_universe,
)
from tests.trading_kernel.support.runtime_scope import (
    seed_ticket_runtime_scope as _seed_ticket_runtime_scope,
)
from tests.trading_kernel.support.selection_vacuum import open_entry_vacuum
from tests.trading_kernel.support.tickets import make_ticket as _retired_ticket


def _raw_liquidation_observation(ticket, average_fill_price: Decimal) -> Decimal:
    del ticket, average_fill_price
    return Decimal(0)


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


class CountingKindAwareAcceptingVenue(KindAwareAcceptingVenue):
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        self.calls += 1
        return await super().execute(request)


class PausingPreflightFacts(PreflightFacts):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def read_entry_admission_snapshot(self, request):
        self.started.set()
        await self.release.wait()
        return await super().read_entry_admission_snapshot(request)


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
            schema_revision=CURRENT_SCHEMA_REVISION,
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
            schema_revision=CURRENT_SCHEMA_REVISION,
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


@pytest.mark.parametrize(
    ("drift", "expected_reason"),
    [
        ("policy_scope", "dispatch_preflight:policy_drift"),
        ("strategy_pause", "dispatch_preflight:strategy_paused"),
        ("product_identity", "dispatch_preflight:product_entry_blocked"),
    ],
)
@pytest.mark.asyncio
async def test_action_time_entry_authority_drift_causes_zero_venue_mutations(
    dispatch_engine: AsyncEngine,
    drift: str,
    expected_reason: str,
) -> None:
    ticket = _registered_sor_ticket()
    await _seed_policy(dispatch_engine)
    async with dispatch_engine.begin() as connection:
        await connection.execute(
            sa.update(owner_policy_current)
            .where(owner_policy_current.c.owner_policy_id == "policy-main")
            .values(
                scope={
                    "event_runtime_profiles": [
                        {
                            "event_spec_id": (ticket.identity.runtime.event_spec_id),
                            "runtime_profile_id": (
                                ticket.identity.runtime.runtime_profile_id
                            ),
                        }
                    ]
                }
            )
        )
    await _issue(dispatch_engine, ticket)
    async with dispatch_engine.begin() as connection:
        if drift == "policy_scope":
            await connection.execute(
                sa.update(owner_policy_current)
                .where(owner_policy_current.c.owner_policy_id == "policy-main")
                .values(
                    scope={
                        "event_runtime_profiles": [
                            {
                                "event_spec_id": (
                                    ticket.identity.runtime.event_spec_id
                                ),
                                "runtime_profile_id": "replacement-profile",
                            }
                        ]
                    }
                )
            )
        elif drift == "strategy_pause":
            await connection.execute(
                sa.update(strategy_entry_controls_current)
                .where(
                    strategy_entry_controls_current.c.strategy_group_id
                    == ticket.identity.runtime.strategy_group_id
                )
                .values(
                    entry_state="paused",
                    control_version=2,
                    reason="test_action_time_pause",
                    updated_at_ms=1_050,
                )
            )
        else:
            await connection.execute(
                sa.update(instrument_product_profiles)
                .where(
                    instrument_product_profiles.c.exchange_instrument_id
                    == ticket.identity.netting_domain.exchange_instrument_id
                )
                .values(
                    product_family="tradfi_equity_perpetual",
                    asset_class="equity",
                    contract_type="TRADIFI_PERPETUAL",
                    underlying_type="EQUITY",
                    entry_session_policy="regular_only",
                    status="active",
                    max_entry_spread_bps=Decimal(20),
                    max_mark_index_deviation_bps=Decimal(50),
                    semantic_digest="sha256:" + "d" * 64,
                    updated_at_ms=1_050,
                )
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
            schema_revision=CURRENT_SCHEMA_REVISION,
            admission_snapshot_validity_ms=1_000,
        ),
        entry_facts_source=PreflightFacts(),
    )

    assert result.status is DispatchCommandStatus.SUPERSEDED
    assert venue.calls == 0
    async with dispatch_engine.connect() as connection:
        command = (
            (
                await connection.execute(
                    sa.select(exchange_commands).where(
                        exchange_commands.c.command_id == result.command_id
                    )
                )
            )
            .mappings()
            .one()
        )
    assert command["status"] == ExchangeCommandStatus.REJECTED.value
    assert command["result_payload"]["reason"] == expected_reason
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.ENTRY_REJECTED


@pytest.mark.asyncio
async def test_unregistered_event_at_dispatch_is_terminally_fenced_before_venue(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _retired_ticket()
    await _seed_policy(
        dispatch_engine,
        event_spec_id=ticket.identity.runtime.event_spec_id,
    )
    await _issue(dispatch_engine, ticket)
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
            schema_revision=CURRENT_SCHEMA_REVISION,
            admission_snapshot_validity_ms=1_000,
        ),
        entry_facts_source=PreflightFacts(),
    )

    assert result.status is DispatchCommandStatus.SUPERSEDED
    assert venue.calls == 0
    async with dispatch_engine.connect() as connection:
        command = (
            (
                await connection.execute(
                    sa.select(exchange_commands).where(
                        exchange_commands.c.command_id == result.command_id
                    )
                )
            )
            .mappings()
            .one()
        )
    assert command["status"] == ExchangeCommandStatus.REJECTED.value
    assert command["result_payload"]["reason"] == (
        "dispatch_preflight:product_entry_blocked"
    )


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
            schema_revision=CURRENT_SCHEMA_REVISION,
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
async def test_selection_vacuum_opened_during_preflight_supersedes_before_venue(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)
    facts = PausingPreflightFacts()
    venue = CountingVenue()
    dispatch_task = asyncio.create_task(
        dispatch_one_command(
            lambda: PostgresKernelUnitOfWork(dispatch_engine),
            venue,
            DispatchCommandRequest(
                worker_id="entry-dispatcher",
                now_ms=1_100,
                lease_until_ms=6_100,
                timeout_seconds=1,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                admission_snapshot_validity_ms=1_000,
            ),
            entry_facts_source=facts,
        )
    )
    await asyncio.wait_for(facts.started.wait(), timeout=2)
    vacuum = await open_entry_vacuum(dispatch_engine, ticket)
    facts.release.set()

    result = await dispatch_task

    assert result.status is DispatchCommandStatus.SUPERSEDED
    assert venue.calls == 0
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        command = await uow.exchange_commands.get(result.command_id or "")
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
        domain_active = await uow.entry_admission.has_active_ticket_in_domain(
            ticket.identity.netting_domain.key()
        )
    assert command is not None
    assert command.status is ExchangeCommandStatus.SUPERSEDED
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.ENTRY_REJECTED
    assert aggregate.entry_vacuum_id == vacuum.entry_vacuum_id
    assert reservation is not None and reservation.status == "released"
    assert domain_active is False


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
                schema_revision=CURRENT_SCHEMA_REVISION,
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
    ticket = _ticket()
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
            schema_revision=CURRENT_SCHEMA_REVISION,
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
                event_id=(f"event:{ticket_id}:{aggregate.last_event_sequence + 1}"),
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
            schema_revision=CURRENT_SCHEMA_REVISION,
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
            schema_revision=CURRENT_SCHEMA_REVISION,
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
            ticket.identity.netting_domain.account_id,
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
            schema_revision=CURRENT_SCHEMA_REVISION,
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
            schema_revision=CURRENT_SCHEMA_REVISION,
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
            schema_revision=CURRENT_SCHEMA_REVISION,
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
        command.status for command in commands if command.kind.value == "initial_stop"
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
            schema_revision=CURRENT_SCHEMA_REVISION,
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
    exit_commands = [command for command in commands if command.kind.value == "exit"]
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


async def _seed_policy(
    engine: AsyncEngine,
    *,
    event_spec_id: str = "event_spec:SOR-001:SOR-LONG:v4",
    event_spec_ids: tuple[str, ...] | None = None,
) -> None:
    authorized_event_spec_ids = event_spec_ids or (event_spec_id,)
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
                family_ticket_limits={
                    "long_continuation": 1,
                    "opening_range": 2,
                    "rally_failure_short": 1,
                },
                max_ticket_stop_risk_fraction="0.02",
                max_gross_stop_risk_fraction="0.06",
                max_ticket_initial_margin_fraction="0.30",
                max_gross_initial_margin_utilization="0.90",
                directional_stop_risk_limit_fraction="0.04",
                min_materialization_ratio="0.50",
                max_leverage=10,
                supported_margin_mode="cross",
                post_stop_stress_multiple="2.0",
                max_post_fill_stop_risk_overrun_fraction="0.10",
                scope={
                    "event_runtime_profiles": [
                        {
                            "event_spec_id": authorized_event_spec_id,
                            "runtime_profile_id": "tiny-live-v1",
                        }
                        for authorized_event_spec_id in authorized_event_spec_ids
                    ]
                },
                updated_at_ms=1_000,
            )
        )


def _ticket():
    return _registered_sor_ticket()


def _registered_sor_ticket():
    base = _retired_ticket()
    runtime = base.identity.runtime.model_copy(
        update={
            "strategy_group_id": "SOR-001",
            "strategy_version_id": "sgv:SOR-001:v4",
            "event_spec_id": "event_spec:SOR-001:SOR-LONG:v4",
        }
    )
    identity = TicketIdentity(
        ticket_id=build_ticket_id(
            signal_event_id=base.identity.signal_event_id,
            runtime=runtime,
            netting_domain=base.identity.netting_domain,
        ),
        exposure_episode_id=base.identity.exposure_episode_id,
        signal_event_id=base.identity.signal_event_id,
        runtime=runtime,
        netting_domain=base.identity.netting_domain,
    )
    return base.model_copy(update={"identity": identity})


async def _issue(engine: AsyncEngine, ticket) -> None:
    await _seed_ticket_runtime_scope(engine, ticket)
    async with engine.begin() as connection:
        await connection.execute(
            pg_insert(runtime_capabilities_current)
            .values(
                capability_key="exchange_commands",
                enabled=True,
                certified_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                certification={},
                updated_at_ms=1_000,
            )
            .on_conflict_do_update(
                index_elements=[runtime_capabilities_current.c.capability_key],
                set_={
                    "enabled": True,
                    "certified_commit": "kernel-test-head",
                    "schema_revision": CURRENT_SCHEMA_REVISION,
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
            schema_revision=CURRENT_SCHEMA_REVISION,
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
