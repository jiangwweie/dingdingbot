from __future__ import annotations

from decimal import Decimal

import pytest

from tests.trading_kernel.integration import test_command_dispatch as dispatch_fixture
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
from src.trading_kernel.domain.commands import ExchangeCommandKind
from src.trading_kernel.domain.exit_policy import LifecycleMarketFacts
from src.trading_kernel.domain.position import PositionSnapshot, VenueOrderSnapshot
from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    seed_strategy_registry,
)
from tests.trading_kernel.integration.test_command_dispatch import (
    KindAwareAcceptingVenue,
    _issue,
    _seed_policy,
)
from tests.trading_kernel.unit.test_ticket import _ticket


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
    assert replacement.payload.stop_price == Decimal("60080.3")


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
                        structure_reference=Decimal("60500"),
                        atr=Decimal("100"),
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
                        structure_reference=Decimal("60500"),
                        atr=Decimal("100"),
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
                        structure_reference=Decimal("60500"),
                        atr=Decimal("100"),
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
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.RUNNER_REPLACEMENT_PENDING
    assert aggregate.pending_stop_price == Decimal("60450")
    replacements = [
        item
        for item in commands
        if item.kind is ExchangeCommandKind.REPLACE_PROTECTION
    ]
    assert [item.generation for item in replacements] == [1, 2]


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
                    quantity=Decimal("0"),
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
                    quantity=Decimal("0"),
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
                    quantity=Decimal("0"),
                    average_entry_price=None,
                    open_orders=(),
                    observed_at_ms=3_600,
                ),
            ),
        )
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
    assert matched.status.value == "matched"
    assert reservation is not None and reservation.status == "released"


async def _reach_position_protected(engine, ticket) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1_000)
    await _seed_policy(engine)
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
    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine),
        venue,
        DispatchCommandRequest(
            worker_id="lifecycle-dispatcher",
            ticket_id=ticket_id,
            now_ms=now_ms,
            lease_until_ms=now_ms + 5_000,
            timeout_seconds=1,
        ),
    )
    assert result.command_id is not None


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
    return ticket.model_copy(update={"identity": identity})
