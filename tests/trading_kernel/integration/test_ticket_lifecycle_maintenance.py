from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa

from src.trading_kernel.application.dispatch_exchange_command import (
    DispatchCommandRequest,
    dispatch_one_command,
)
from src.trading_kernel.application.maintain_ticket_lifecycle import (
    LifecycleMaintenanceRequest,
    LifecycleMaintenanceStatus,
    TicketLifecycleFacts,
    maintain_ticket_lifecycle,
)
from src.trading_kernel.application.reconcile_ticket import (
    ExitTicketRequest,
    ReconcileTicketRequest,
    reconcile_ticket,
    request_exit,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import ExchangeCommandKind, OrderCommandPayload
from src.trading_kernel.domain.exit_policy import LifecycleMarketFacts, exit_policy_for
from src.trading_kernel.domain.position import PositionSnapshot, VenueOrderSnapshot
from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts
from src.trading_kernel.infrastructure.pg_models import owner_policy_current
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    seed_strategy_registry,
)
from tests.trading_kernel.integration import test_command_dispatch as dispatch_fixture
from tests.trading_kernel.integration.test_command_dispatch import (
    KindAwareAcceptingVenue,
    PreflightFacts,
    _issue,
    _seed_policy,
)
from tests.trading_kernel.support.tickets import make_ticket as _ticket

lifecycle_engine = dispatch_fixture.dispatch_engine


@pytest.mark.asyncio
async def test_maintenance_turns_full_tp1_fill_into_cost_adjusted_runner_protection(
    lifecycle_engine,
) -> None:
    ticket = _registered_sor_long_ticket()
    await _reach_position_protected(lifecycle_engine, ticket)

    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        result = await maintain_ticket_lifecycle(
            uow,
            LifecycleMaintenanceRequest(
                ticket_id=ticket.identity.ticket_id,
                facts=TicketLifecycleFacts(
                    position_quantity=(
                        ticket.quantity - ticket.take_profit_quantities[0]
                    ),
                    tp1_filled_quantity=ticket.take_profit_quantities[0],
                    tp1_average_fill_price=ticket.take_profit_prices[0],
                    allocated_entry_fee_quote=Decimal("0.01"),
                    exit_taker_fee_rate=Decimal("0.001"),
                    price_tick=Decimal("0.1"),
                    market_facts=None,
                    observed_at_ms=2_500,
                ),
                now_ms=2_500,
            ),
        )

    assert result.status is LifecycleMaintenanceStatus.BREAK_EVEN_REQUESTED
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.RUNNER_REPLACEMENT_PENDING
    assert aggregate.break_even_floor_price == Decimal("60080.3")
    assert aggregate.tp1_exchange_order_id is None
    replacement = next(
        item
        for item in commands
        if item.kind is ExchangeCommandKind.REPLACE_PROTECTION
    )
    assert isinstance(replacement.payload, OrderCommandPayload)
    assert replacement.payload.stop_price == Decimal("60080.3")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("latest_close", "holding_bars", "session_end_ms", "reason"),
    [
        (Decimal(60000), 10, 86_400_000, "failed_breakout_reclaimed"),
        (Decimal(60500), 10, 3_000, "sor_session_expired"),
        (Decimal(60500), 96, 86_400_000, "time_stop_hit"),
    ],
)
async def test_sor_v3_position_protected_exit_plan_is_durable(
    lifecycle_engine,
    latest_close: Decimal,
    holding_bars: int,
    session_end_ms: int,
    reason: str,
) -> None:
    ticket = _registered_sor_long_ticket().model_copy(
        update={"exposure_session_end_ms": session_end_ms}
    )
    await _reach_position_protected(lifecycle_engine, ticket)

    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        result = await maintain_ticket_lifecycle(
            uow,
            LifecycleMaintenanceRequest(
                ticket_id=ticket.identity.ticket_id,
                facts=TicketLifecycleFacts(
                    position_quantity=ticket.quantity,
                    tp1_filled_quantity=Decimal(0),
                    tp1_average_fill_price=None,
                    allocated_entry_fee_quote=Decimal("0.01"),
                    exit_taker_fee_rate=Decimal("0.001"),
                    price_tick=Decimal("0.1"),
                    market_facts=LifecycleMarketFacts(
                        watermark_ms=3_000,
                        is_final_closed_candle=True,
                        latest_close=latest_close,
                        structure_reference=Decimal(60500),
                        atr=Decimal(100),
                        holding_bars=holding_bars,
                    ),
                    observed_at_ms=3_000,
                ),
                now_ms=3_000,
            ),
        )

    assert result.status is LifecycleMaintenanceStatus.EXIT_REQUESTED
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        events = await uow.events.list_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None and aggregate.status is AggregateStatus.EXIT_PENDING
    assert events[-1].reason == reason
    assert any(command.kind is ExchangeCommandKind.EXIT for command in commands)


@pytest.mark.asyncio
async def test_runner_maintenance_uses_closed_candle_and_sor_time_stop(
    lifecycle_engine,
) -> None:
    ticket = _registered_sor_long_ticket()
    await _reach_runner_protected(lifecycle_engine, ticket)

    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        open_candle = await maintain_ticket_lifecycle(
            uow,
            LifecycleMaintenanceRequest(
                ticket_id=ticket.identity.ticket_id,
                facts=TicketLifecycleFacts(
                    position_quantity=(
                        ticket.quantity - ticket.take_profit_quantities[0]
                    ),
                    tp1_filled_quantity=ticket.take_profit_quantities[0],
                    tp1_average_fill_price=ticket.take_profit_prices[0],
                    allocated_entry_fee_quote=Decimal("0.01"),
                    exit_taker_fee_rate=Decimal("0.001"),
                    price_tick=Decimal("0.1"),
                    market_facts=LifecycleMarketFacts(
                        watermark_ms=3_000,
                        is_final_closed_candle=False,
                        latest_close=Decimal(60500),
                        structure_reference=Decimal(60500),
                        atr=Decimal(100),
                        holding_bars=95,
                    ),
                    observed_at_ms=3_000,
                ),
                now_ms=3_000,
            ),
        )
    assert open_candle.status is LifecycleMaintenanceStatus.NO_CHANGE

    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        time_stop = await maintain_ticket_lifecycle(
            uow,
            LifecycleMaintenanceRequest(
                ticket_id=ticket.identity.ticket_id,
                facts=TicketLifecycleFacts(
                    position_quantity=(
                        ticket.quantity - ticket.take_profit_quantities[0]
                    ),
                    tp1_filled_quantity=ticket.take_profit_quantities[0],
                    tp1_average_fill_price=ticket.take_profit_prices[0],
                    allocated_entry_fee_quote=Decimal("0.01"),
                    exit_taker_fee_rate=Decimal("0.001"),
                    price_tick=Decimal("0.1"),
                    market_facts=LifecycleMarketFacts(
                        watermark_ms=3_100,
                        is_final_closed_candle=True,
                        latest_close=Decimal(60500),
                        structure_reference=Decimal(60500),
                        atr=Decimal(100),
                        holding_bars=96,
                    ),
                    observed_at_ms=3_100,
                ),
                now_ms=3_100,
            ),
        )

    assert time_stop.status is LifecycleMaintenanceStatus.EXIT_REQUESTED
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    assert aggregate is not None and aggregate.status is AggregateStatus.EXIT_PENDING
    assert any(item.kind is ExchangeCommandKind.EXIT for item in commands)


@pytest.mark.asyncio
async def test_runner_maintenance_requests_monotonic_structural_atr_stop(
    lifecycle_engine,
) -> None:
    ticket = _registered_sor_long_ticket()
    await _reach_runner_protected(lifecycle_engine, ticket)

    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        result = await maintain_ticket_lifecycle(
            uow,
            LifecycleMaintenanceRequest(
                ticket_id=ticket.identity.ticket_id,
                facts=TicketLifecycleFacts(
                    position_quantity=(
                        ticket.quantity - ticket.take_profit_quantities[0]
                    ),
                    tp1_filled_quantity=ticket.take_profit_quantities[0],
                    tp1_average_fill_price=ticket.take_profit_prices[0],
                    allocated_entry_fee_quote=Decimal("0.01"),
                    exit_taker_fee_rate=Decimal("0.001"),
                    price_tick=Decimal("0.1"),
                    market_facts=LifecycleMarketFacts(
                        watermark_ms=3_100,
                        is_final_closed_candle=True,
                        latest_close=Decimal(60500),
                        structure_reference=Decimal(60500),
                        atr=Decimal(100),
                        holding_bars=10,
                    ),
                    observed_at_ms=3_100,
                ),
                now_ms=3_100,
            ),
        )

    assert result.status is LifecycleMaintenanceStatus.RUNNER_MOVE_REQUESTED
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        events = await uow.events.list_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.RUNNER_REPLACEMENT_PENDING
    assert aggregate.pending_stop_price == Decimal(60450)
    replacements = [
        item
        for item in commands
        if item.kind is ExchangeCommandKind.REPLACE_PROTECTION
    ]
    assert [item.generation for item in replacements] == [1, 2]
    assert type(events[-1]).__name__ == "RunnerStopRequested"


@pytest.mark.asyncio
async def test_flat_cleanup_cancels_tp1_then_active_stop_before_settlement(
    lifecycle_engine,
) -> None:
    ticket = _registered_sor_long_ticket()
    await _reach_position_protected(lifecycle_engine, ticket)
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        await request_exit(
            uow,
            ExitTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                reason="strategy_exit",
                requested_at_ms=3_000,
            ),
        )
    venue = KindAwareAcceptingVenue()
    await _dispatch(lifecycle_engine, venue, ticket.identity.ticket_id, now_ms=3_100)

    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        first = await reconcile_ticket(
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
                            venue_client_order_id="brc-tp1",
                            position_side="long",
                            reduce_only=True,
                        ),
                        VenueOrderSnapshot(
                            exchange_order_id="venue-initial_stop-1",
                            venue_client_order_id="brc-stop",
                            position_side="long",
                            reduce_only=True,
                        ),
                    ),
                    observed_at_ms=3_200,
                ),
            ),
        )
    assert first.status.value == "position_flat_recorded"
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
    assert aggregate is not None
    assert aggregate.pending_cancel_exchange_order_id == "venue-take_profit-1"

    await _dispatch(lifecycle_engine, venue, ticket.identity.ticket_id, now_ms=3_300)
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        second = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=Decimal(0),
                    average_entry_price=None,
                    open_orders=(
                        VenueOrderSnapshot(
                            exchange_order_id="venue-initial_stop-1",
                            venue_client_order_id="brc-stop",
                            position_side="long",
                            reduce_only=True,
                        ),
                    ),
                    observed_at_ms=3_400,
                ),
            ),
        )
    assert second.status.value == "owned_orphan_cancel_requested"

    await _dispatch(lifecycle_engine, venue, ticket.identity.ticket_id, now_ms=3_500)
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
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


@pytest.mark.asyncio
async def test_hard_post_fill_risk_protects_then_flattens_without_tp1(
    lifecycle_engine,
) -> None:
    ticket = _registered_sor_long_ticket()
    await _seed_policy(lifecycle_engine)
    await _issue(lifecycle_engine, ticket)
    venue = KindAwareAcceptingVenue()
    await _dispatch(lifecycle_engine, venue, ticket.identity.ticket_id, now_ms=1_100)

    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        result = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price=Decimal(64000),
                    venue_reported_liquidation_price=Decimal(48000),
                    observed_at_ms=2_100,
                ),
            ),
        )
    assert result.status.value == "entry_fill_recorded"

    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.PROTECTION_PENDING
    assert aggregate.actual_stop_risk == Decimal(5)
    assert aggregate.post_fill_risk_status is not None
    assert aggregate.post_fill_risk_status.value == "hard_overrun"
    assert incident is not None and incident.incident_kind == "hard_overrun"
    assert {command.kind for command in commands} == {
        ExchangeCommandKind.ENTRY,
        ExchangeCommandKind.INITIAL_STOP,
    }

    await _dispatch(lifecycle_engine, venue, ticket.identity.ticket_id, now_ms=2_200)
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.CONTROLLED_FLATTEN_PENDING
    assert {command.kind for command in commands} == {
        ExchangeCommandKind.ENTRY,
        ExchangeCommandKind.INITIAL_STOP,
        ExchangeCommandKind.CONTROLLED_FLATTEN,
    }


@pytest.mark.asyncio
async def test_missing_liquidation_observation_does_not_control_post_fill_risk(
    lifecycle_engine,
) -> None:
    ticket = _registered_sor_long_ticket()
    await _seed_policy(lifecycle_engine)
    await _issue(lifecycle_engine, ticket)
    venue = KindAwareAcceptingVenue()
    await _dispatch(lifecycle_engine, venue, ticket.identity.ticket_id, now_ms=1_100)

    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price=ticket.entry_reference_price,
                    venue_reported_liquidation_price=None,
                    observed_at_ms=2_100,
                ),
            ),
        )
    await _dispatch(lifecycle_engine, venue, ticket.identity.ticket_id, now_ms=2_200)

    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    assert aggregate is not None
    assert aggregate.post_fill_risk_status is not None
    assert aggregate.post_fill_risk_status.value == "within_budget"
    assert aggregate.venue_reported_liquidation_price is None
    assert aggregate.post_fill_stress_status == "passed"
    assert aggregate.status is AggregateStatus.TP1_PENDING
    assert ExchangeCommandKind.TAKE_PROFIT in {
        command.kind for command in commands
    }


@pytest.mark.asyncio
async def test_invalid_stop_direction_flattens_immediately_without_stop_or_tp1(
    lifecycle_engine,
) -> None:
    ticket = _registered_sor_long_ticket()
    await _seed_policy(lifecycle_engine)
    await _issue(lifecycle_engine, ticket)
    venue = KindAwareAcceptingVenue()
    await _dispatch(lifecycle_engine, venue, ticket.identity.ticket_id, now_ms=1_100)

    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price=Decimal(58000),
                    venue_reported_liquidation_price=Decimal(50000),
                    observed_at_ms=2_100,
                ),
            ),
        )
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.CONTROLLED_FLATTEN_PENDING
    assert aggregate.post_fill_risk_status is not None
    assert aggregate.post_fill_risk_status.value == "protection_direction_invalid"
    assert [command.kind for command in commands] == [
        ExchangeCommandKind.ENTRY,
        ExchangeCommandKind.CONTROLLED_FLATTEN,
    ]


async def _reach_position_protected(engine, ticket) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1_000)
    await _seed_policy(engine)
    async with engine.begin() as connection:
        await connection.execute(
            sa.update(owner_policy_current)
            .where(owner_policy_current.c.owner_policy_id == ticket.owner_policy_id)
            .values(
                scope={
                    "event_runtime_profiles": [
                        {
                            "event_spec_id": ticket.identity.runtime.event_spec_id,
                            "runtime_profile_id": (
                                ticket.identity.runtime.runtime_profile_id
                            ),
                        }
                    ]
                }
            )
        )
    await _issue(engine, ticket)
    venue = KindAwareAcceptingVenue()
    await _dispatch(engine, venue, ticket.identity.ticket_id, now_ms=1_100)
    async with PostgresKernelUnitOfWork(engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price=ticket.entry_reference_price,
                    venue_reported_liquidation_price=Decimal(0),
                    observed_at_ms=2_100,
                ),
            ),
        )
    await _dispatch(engine, venue, ticket.identity.ticket_id, now_ms=2_200)
    await _dispatch(engine, venue, ticket.identity.ticket_id, now_ms=2_300)


async def _reach_runner_protected(engine, ticket) -> None:
    await _reach_position_protected(engine, ticket)
    async with PostgresKernelUnitOfWork(engine) as uow:
        result = await maintain_ticket_lifecycle(
            uow,
            LifecycleMaintenanceRequest(
                ticket_id=ticket.identity.ticket_id,
                facts=TicketLifecycleFacts(
                    position_quantity=(
                        ticket.quantity - ticket.take_profit_quantities[0]
                    ),
                    tp1_filled_quantity=ticket.take_profit_quantities[0],
                    tp1_average_fill_price=ticket.take_profit_prices[0],
                    allocated_entry_fee_quote=Decimal("0.01"),
                    exit_taker_fee_rate=Decimal("0.001"),
                    price_tick=Decimal("0.1"),
                    market_facts=None,
                    observed_at_ms=2_500,
                ),
                now_ms=2_500,
            ),
        )
    assert result.status is LifecycleMaintenanceStatus.BREAK_EVEN_REQUESTED
    venue = KindAwareAcceptingVenue()
    await _dispatch(engine, venue, ticket.identity.ticket_id, now_ms=2_600)
    await _dispatch(engine, venue, ticket.identity.ticket_id, now_ms=2_700)


async def _dispatch(engine, venue, ticket_id: str, *, now_ms: int) -> None:
    await dispatch_fixture._commit_passed_post_fill_stress_if_pending(
        engine,
        ticket_id,
    )
    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine),
        venue,
        DispatchCommandRequest(
            worker_id="lifecycle-dispatcher",
            ticket_id=ticket_id,
            now_ms=now_ms,
            lease_until_ms=now_ms + 5_000,
            timeout_seconds=1,
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            admission_snapshot_validity_ms=1_000,
        ),
        entry_facts_source=PreflightFacts(),
    )
    assert result.command_id is not None
    await dispatch_fixture._commit_passed_post_fill_stress_if_pending(
        engine,
        ticket_id,
    )


def _registered_sor_long_ticket():
    contract = next(
        item
        for item in registered_strategy_contracts()
        if item.event_id == "SOR-LONG"
    )
    ticket = _ticket()
    identity = ticket.identity.model_copy(
        update={
            "runtime": ticket.identity.runtime.model_copy(
                update={
                    "strategy_group_id": contract.strategy_group_id,
                    "strategy_version_id": contract.strategy_version_id,
                    "event_spec_id": contract.event_spec_id,
                }
            )
        }
    )
    policy = exit_policy_for(contract.event_spec_id)
    return ticket.model_copy(
        update={
            "identity": identity,
            "exit_policy_id": policy.exit_policy_id,
            "exit_policy_semantic_hash": policy.semantic_hash(),
            "pre_tp1_reclaim_price": Decimal(60100),
            "exposure_session_end_ms": 86_400_000,
        }
    )
