from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.application.reconcile_ticket import (
    ReconcileTicketRequest,
    reconcile_ticket,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.identities import NettingDomain
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.ticket import build_ticket_id
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    seed_strategy_registry,
)
from src.trading_kernel.interfaces.reconciliation_worker import (
    ReconciliationWorkerRequest,
    ReconciliationWorkerStatus,
    run_reconciliation_worker_once,
)
from tests.trading_kernel.full_chain.lifecycle_support import (
    dispatch_lifecycle_command,
    reach_runner_protected,
    safe_liquidation_price,
)
from tests.trading_kernel.integration import test_command_dispatch as dispatch_fixture
from tests.trading_kernel.integration.test_command_dispatch import (
    KindAwareAcceptingVenue,
    _issue,
    _seed_policy,
)
from tests.trading_kernel.integration.test_ticket_lifecycle_maintenance import (
    _registered_sor_long_ticket,
)

dispatch_engine = dispatch_fixture.dispatch_engine


class _ActivePositionSource:
    def __init__(self, tickets) -> None:
        self.tickets = {ticket.identity.ticket_id: ticket for ticket in tickets}
        self.requests: list[str] = []

    async def read_position_snapshot(self, request):
        ticket = self.tickets[request.ticket_id]
        self.requests.append(request.ticket_id)
        return PositionSnapshot(
            netting_domain=ticket.identity.netting_domain,
            quantity=ticket.quantity,
            average_entry_price=ticket.entry_reference_price,
            liquidation_price=safe_liquidation_price(ticket),
            open_orders=(),
            observed_at_ms=request.observed_at_ms,
        )


def _active_ticket(*, instrument: str, signal_event_id: str):
    original = _registered_sor_long_ticket()
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
                runtime=original.identity.runtime,
                netting_domain=domain,
            ),
            "signal_event_id": signal_event_id,
            "exposure_episode_id": f"episode:{instrument}",
            "netting_domain": domain,
        }
    )
    return original.model_copy(
        update={
            "identity": identity,
            "runtime_scope_id": f"scope:{instrument}",
        }
    )


async def _reach_position_protected(engine, ticket) -> None:
    await _issue(engine, ticket)
    venue = KindAwareAcceptingVenue()
    assert (await dispatch_lifecycle_command(
        engine, venue, ticket.identity.ticket_id, now_ms=1_100, entry=True
    )).status.value == "accepted"
    async with PostgresKernelUnitOfWork(engine) as uow:
        filled = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price=ticket.entry_reference_price,
                    liquidation_price=safe_liquidation_price(ticket),
                    open_orders=(),
                    observed_at_ms=2_100,
                ),
            ),
        )
    assert filled.status.value == "entry_fill_recorded"
    assert (await dispatch_lifecycle_command(
        engine, venue, ticket.identity.ticket_id, now_ms=2_200
    )).status.value == "accepted"
    assert (await dispatch_lifecycle_command(
        engine, venue, ticket.identity.ticket_id, now_ms=2_300
    )).status.value == "accepted"


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
    assert (await dispatch_lifecycle_command(
        engine, venue, ticket.identity.ticket_id, now_ms=3_550
    )).status.value == "accepted"
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


@pytest.mark.asyncio
async def test_two_due_active_positions_cannot_starve_btc_like_settlement(
    dispatch_engine,
) -> None:
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1_000)
    await _seed_policy(dispatch_engine)
    sol_ticket = _active_ticket(instrument="SOLUSDT", signal_event_id="signal-sol")
    avax_ticket = _active_ticket(instrument="AVAXUSDT", signal_event_id="signal-avax")
    await _reach_position_protected(dispatch_engine, sol_ticket)
    await _reach_position_protected(dispatch_engine, avax_ticket)

    btc_ticket = _registered_sor_long_ticket()
    await _settlement_pending_from_runner(dispatch_engine, btc_ticket)
    source = _ActivePositionSource((sol_ticket, avax_ticket))
    request = ReconciliationWorkerRequest(
        worker_id="reconciliation-fairness-full-chain",
        runtime_commit="kernel-test-head",
        schema_revision="0002_crypto_strategy_universe",
        now_ms=33_600,
        timeout_seconds=1,
        unknown_visibility_grace_ms=30_000,
        idle_poll_interval_ms=2_000,
        closure_starvation_limit_ms=30_000,
    )

    closure = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        object(),
        source,
        request,
    )
    assert closure.status is ReconciliationWorkerStatus.SETTLED
    assert closure.ticket_id == btc_ticket.identity.ticket_id
    assert source.requests == []

    protected = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        object(),
        source,
        request.model_copy(update={"now_ms": 33_601}),
    )
    assert protected.status is ReconciliationWorkerStatus.POSITION_RECONCILED
    assert protected.ticket_id in {sol_ticket.identity.ticket_id, avax_ticket.identity.ticket_id}
    other_protected = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        object(),
        source,
        request.model_copy(update={"now_ms": 33_602}),
    )
    assert other_protected.status is ReconciliationWorkerStatus.POSITION_RECONCILED
    assert {
        protected.ticket_id,
        other_protected.ticket_id,
    } == {sol_ticket.identity.ticket_id, avax_ticket.identity.ticket_id}
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        btc = await uow.aggregates.get(btc_ticket.identity.ticket_id)
        sol = await uow.aggregates.get(sol_ticket.identity.ticket_id)
        avax = await uow.aggregates.get(avax_ticket.identity.ticket_id)
    assert btc is not None and btc.status is AggregateStatus.REVIEW_PENDING
    assert sol is not None and sol.status is AggregateStatus.POSITION_PROTECTED
    assert avax is not None and avax.status is AggregateStatus.POSITION_PROTECTED
