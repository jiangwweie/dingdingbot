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
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import OrderCommandPayload
from src.trading_kernel.domain.exit_policy import exit_policy_for
from src.trading_kernel.domain.identities import NettingDomain
from src.trading_kernel.domain.position import PositionSnapshot, VenueOrderSnapshot
from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts
from src.trading_kernel.domain.ticket import build_ticket_id
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.full_chain.lifecycle_support import (
    dispatch_lifecycle_command,
    reach_runner_protected,
)
from tests.trading_kernel.support.command_dispatch import (
    issue as _issue,
)
from tests.trading_kernel.support.dispatch_venues import KindAwareAcceptingVenue
from tests.trading_kernel.support.lifecycle import (
    registered_sor_long_ticket as _registered_sor_long_ticket,
)


class _ActivePositionSource:
    def __init__(self, tickets, *, open_orders_by_ticket) -> None:
        self.tickets = {ticket.identity.ticket_id: ticket for ticket in tickets}
        self.open_orders_by_ticket = open_orders_by_ticket
        self.requests: list[str] = []

    async def read_position_snapshot(self, request):
        ticket = self.tickets[request.ticket_id]
        self.requests.append(request.ticket_id)
        return PositionSnapshot(
            netting_domain=ticket.identity.netting_domain,
            quantity=ticket.quantity,
            average_entry_price=ticket.entry_reference_price,
            venue_reported_liquidation_price=Decimal(0),
            open_orders=self.open_orders_by_ticket[ticket.identity.ticket_id],
            observed_at_ms=request.observed_at_ms,
        )


def _active_ticket(
    *,
    instrument: str,
    signal_event_id: str,
    event_id: str = "SOR-1H-LONG",
):
    original = _registered_sor_long_ticket()
    contract = next(
        item for item in registered_strategy_contracts() if item.event_id == event_id
    )
    policy = exit_policy_for(contract.event_spec_id)
    runtime = original.identity.runtime.model_copy(
        update={
            "strategy_group_id": contract.strategy_group_id,
            "strategy_version_id": contract.strategy_version_id,
            "event_spec_id": contract.event_spec_id,
        }
    )
    domain = NettingDomain(
        venue_id=original.identity.netting_domain.venue_id,
        account_id=original.identity.netting_domain.account_id,
        exchange_instrument_id=f"binance-usdm:{instrument}:perpetual",
        position_side="long",
    )
    identity = original.identity.model_copy(
        update={
            "ticket_id": build_ticket_id(
                signal_event_id=signal_event_id,
                runtime=runtime,
                netting_domain=domain,
            ),
            "signal_event_id": signal_event_id,
            "exposure_episode_id": f"episode:{instrument}",
            "runtime": runtime,
            "netting_domain": domain,
        }
    )
    return original.model_copy(
        update={
            "identity": identity,
            "runtime_scope_id": f"scope:{instrument}",
            "universe_version_id": (
                original.universe_version_id
                if contract.strategy_group_id
                == original.identity.runtime.strategy_group_id
                else f"universe:{contract.event_id.lower()}:1"
            ),
            "exit_policy_id": policy.exit_policy_id,
            "exit_policy_semantic_hash": policy.semantic_hash(),
            "exposure_family": contract.exposure_family,
            "family_ticket_limit": (
                2 if contract.exposure_family == "opening_range" else 1
            ),
            "pre_tp1_reclaim_price": (
                original.pre_tp1_reclaim_price if event_id.startswith("SOR-") else None
            ),
            "exposure_session_end_ms": (
                original.exposure_session_end_ms
                if event_id.startswith("SOR-")
                else None
            ),
        }
    )


async def _reach_position_protected(engine, ticket) -> None:
    await _issue(engine, ticket)
    venue = KindAwareAcceptingVenue()
    assert (
        await dispatch_lifecycle_command(
            engine, venue, ticket.identity.ticket_id, now_ms=1_100, entry=True
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


async def _settlement_pending_from_runner(engine, ticket) -> None:
    await reach_runner_protected(engine, ticket, seed_policy=False)
    venue = KindAwareAcceptingVenue()
    async with PostgresKernelUnitOfWork(engine) as uow:
        external_flat = await reconcile_ticket(
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
    assert external_flat.status.value == "external_flat_incident"
    assert (
        await dispatch_lifecycle_command(
            engine, venue, ticket.identity.ticket_id, now_ms=3_550
        )
    ).status.value == "accepted"
    async with PostgresKernelUnitOfWork(engine) as uow:
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
    assert matched.status.value == "matched"


async def _active_stop_truth(engine, tickets):
    open_orders_by_ticket = {}
    async with PostgresKernelUnitOfWork(engine) as uow:
        for ticket in tickets:
            aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
            references = await uow.exchange_commands.list_order_references(
                ticket.identity.ticket_id
            )
            assert aggregate is not None
            assert aggregate.active_stop_exchange_order_id is not None
            reference = next(
                reference
                for reference in references
                if reference.submitted_exchange_order_id
                == aggregate.active_stop_exchange_order_id
            )
            open_orders_by_ticket[ticket.identity.ticket_id] = (
                VenueOrderSnapshot(
                    exchange_order_id=aggregate.active_stop_exchange_order_id,
                    venue_client_order_id=reference.venue_client_order_id,
                    position_side=ticket.identity.netting_domain.position_side,
                    reduce_only=True,
                    order_namespace="conditional",
                ),
            )
    return open_orders_by_ticket


async def _assert_active_protection_is_unchanged(
    engine,
    ticket,
    *,
    status,
    expected_stop: VenueOrderSnapshot,
) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None
    assert aggregate.status is status
    assert aggregate.position_qty == (
        ticket.quantity
        if status is AggregateStatus.POSITION_PROTECTED
        else ticket.quantity - ticket.take_profit_quantities[0]
    )
    assert aggregate.active_stop_exchange_order_id == expected_stop.exchange_order_id
    assert incident is None
    active_command = next(
        command
        for command in commands
        if command.venue_client_order_id == expected_stop.venue_client_order_id
    )
    assert isinstance(active_command.payload, OrderCommandPayload)
    assert active_command.payload.quantity == aggregate.position_qty
    assert len(commands) == (3 if status is AggregateStatus.POSITION_PROTECTED else 5)


async def _run_no_change_lifecycle(engine, ticket, *, runner: bool) -> None:
    facts = TicketLifecycleFacts(
        position_quantity=(
            ticket.quantity - ticket.take_profit_quantities[0]
            if runner
            else ticket.quantity
        ),
        tp1_filled_quantity=(
            ticket.take_profit_quantities[0] if runner else Decimal(0)
        ),
        tp1_average_fill_price=(ticket.take_profit_prices[0] if runner else None),
        allocated_entry_fee_quote=Decimal("0.01"),
        exit_taker_fee_rate=Decimal("0.001"),
        price_tick=Decimal("0.1"),
        market_facts=None,
        observed_at_ms=33_700,
    )
    async with PostgresKernelUnitOfWork(engine) as uow:
        result = await maintain_ticket_lifecycle(
            uow,
            LifecycleMaintenanceRequest(
                ticket_id=ticket.identity.ticket_id,
                facts=facts,
                now_ms=33_700,
            ),
        )
    assert result.status is LifecycleMaintenanceStatus.NO_CHANGE
