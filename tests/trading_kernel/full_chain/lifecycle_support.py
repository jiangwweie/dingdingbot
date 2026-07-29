from __future__ import annotations

from decimal import Decimal

from src.trading_kernel.application.dispatch_exchange_command import (
    DispatchCommandRequest,
    dispatch_one_command,
)
from src.trading_kernel.application.maintain_ticket_lifecycle import (
    LifecycleMaintenanceRequest,
    TicketLifecycleFacts,
    maintain_ticket_lifecycle,
)
from src.trading_kernel.application.reconcile_ticket import (
    ReconcileTicketRequest,
    reconcile_ticket,
)
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    seed_strategy_registry,
)
from tests.trading_kernel.integration.test_command_dispatch import (
    KindAwareAcceptingVenue,
    PreflightFacts,
    _commit_passed_post_fill_stress_if_pending,
    _issue,
    _seed_policy,
)


async def dispatch_lifecycle_command(
    engine,
    venue,
    ticket_id: str,
    *,
    now_ms: int,
    entry: bool = False,
):
    await _commit_passed_post_fill_stress_if_pending(engine, ticket_id)
    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine),
        venue,
        DispatchCommandRequest(
            worker_id="full-chain-dispatcher",
            ticket_id=ticket_id,
            now_ms=now_ms,
            lease_until_ms=now_ms + 5_000,
            timeout_seconds=1,
            runtime_commit="kernel-test-head" if entry else None,
            schema_revision="0003_cross_margin_stop_stress" if entry else None,
            admission_snapshot_validity_ms=1_000 if entry else None,
        ),
        entry_facts_source=PreflightFacts() if entry else None,
    )
    await _commit_passed_post_fill_stress_if_pending(engine, ticket_id)
    return result


async def reach_runner_protected(engine, ticket, *, seed_policy: bool = True) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1_000)
    if seed_policy:
        await _seed_policy(engine)
    await _issue(engine, ticket)
    venue = KindAwareAcceptingVenue()
    assert (
        await dispatch_lifecycle_command(
            engine,
            venue,
            ticket.identity.ticket_id,
            now_ms=1_100,
            entry=True,
        )
    ).status.value == "accepted"
    async with PostgresKernelUnitOfWork(engine) as uow:
        filled = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price=ticket.entry_reference_price,
                    venue_reported_liquidation_price=Decimal(0),
                    open_orders=(),
                    observed_at_ms=2_100,
                ),
            ),
        )
    assert filled.status.value == "entry_fill_recorded"
    assert (
        await dispatch_lifecycle_command(
            engine, venue, ticket.identity.ticket_id, now_ms=2_200
        )
    ).status.value == "accepted"
    assert (
        await dispatch_lifecycle_command(
            engine, venue, ticket.identity.ticket_id, now_ms=2_300
        )
    ).status.value == "accepted"
    async with PostgresKernelUnitOfWork(engine) as uow:
        lifecycle = await maintain_ticket_lifecycle(
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
    assert lifecycle.status.value == "break_even_requested"
    assert (
        await dispatch_lifecycle_command(
            engine, venue, ticket.identity.ticket_id, now_ms=2_600
        )
    ).status.value == "accepted"
    assert (
        await dispatch_lifecycle_command(
            engine, venue, ticket.identity.ticket_id, now_ms=2_700
        )
    ).status.value == "accepted"
