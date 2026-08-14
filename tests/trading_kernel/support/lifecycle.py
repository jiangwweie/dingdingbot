"""Reusable current SOR lifecycle progression helpers for tests."""

from __future__ import annotations

from decimal import Decimal

from src.trading_kernel.application.maintain_ticket_lifecycle import (
    LifecycleMaintenanceRequest,
    LifecycleMaintenanceStatus,
    TicketLifecycleFacts,
    maintain_ticket_lifecycle,
)
from src.trading_kernel.application.reconcile_ticket import (
    ReconcileTicketRequest,
    reconcile_ticket,
)
from src.trading_kernel.domain.exit_policy import exit_policy_for
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts
from src.trading_kernel.infrastructure.pg_models import owner_policy_current
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    seed_strategy_registry,
)
from tests.trading_kernel.support.command_dispatch import (
    dispatch_for_ticket,
    issue,
    seed_policy,
)
from tests.trading_kernel.support.dispatch_venues import KindAwareAcceptingVenue
from tests.trading_kernel.support.tickets import make_ticket


def registered_sor_long_ticket():
    contract = next(
        item for item in registered_strategy_contracts() if item.event_id == "SOR-LONG"
    )
    ticket = make_ticket()
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


async def reach_position_protected(engine, ticket) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1_000)
    await seed_policy(engine)
    async with engine.begin() as connection:
        await connection.execute(
            owner_policy_current.update()
            .where(owner_policy_current.c.owner_policy_id == ticket.owner_policy_id)
            .values(
                scope={
                    "event_runtime_profiles": [
                        {
                            "event_spec_id": ticket.identity.runtime.event_spec_id,
                            "runtime_profile_id": ticket.identity.runtime.runtime_profile_id,
                        }
                    ]
                }
            )
        )
    await issue(engine, ticket)
    venue = KindAwareAcceptingVenue()
    await dispatch_for_ticket(engine, venue, ticket.identity.ticket_id, now_ms=1_100)
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
    await dispatch_for_ticket(engine, venue, ticket.identity.ticket_id, now_ms=2_200)
    await dispatch_for_ticket(engine, venue, ticket.identity.ticket_id, now_ms=2_300)


async def reach_runner_protected(engine, ticket) -> None:
    await reach_position_protected(engine, ticket)
    async with PostgresKernelUnitOfWork(engine) as uow:
        result = await maintain_ticket_lifecycle(
            uow,
            LifecycleMaintenanceRequest(
                ticket_id=ticket.identity.ticket_id,
                facts=TicketLifecycleFacts(
                    position_quantity=ticket.quantity
                    - ticket.take_profit_quantities[0],
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
    await dispatch_for_ticket(engine, venue, ticket.identity.ticket_id, now_ms=2_600)
    await dispatch_for_ticket(engine, venue, ticket.identity.ticket_id, now_ms=2_700)
