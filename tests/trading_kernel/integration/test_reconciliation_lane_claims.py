from __future__ import annotations

import sqlalchemy as sa

from src.trading_kernel.infrastructure.pg_models import trade_aggregates
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    seed_strategy_registry,
)
from tests.trading_kernel.integration import test_command_dispatch as dispatch_fixture
from tests.trading_kernel.integration.test_command_dispatch import _issue, _seed_policy
from tests.trading_kernel.integration.test_ticket_lifecycle_maintenance import (
    _registered_sor_long_ticket,
)

dispatch_engine = dispatch_fixture.dispatch_engine


async def test_routine_claim_lease_prevents_duplicate_process_work(
    dispatch_engine,
) -> None:
    """Catches a row becoming immediately claimable after the selector transaction."""

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1_000)
    await _seed_policy(dispatch_engine)
    ticket = _registered_sor_long_ticket()
    await _issue(dispatch_engine, ticket)
    async with dispatch_engine.begin() as connection:
        await connection.execute(
            sa.update(trade_aggregates)
            .where(trade_aggregates.c.ticket_id == ticket.identity.ticket_id)
            .values(
                status="settlement_pending",
                reconciliation_due_at_ms=10_000,
            )
        )

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        first = await uow.aggregates.claim_next_routine_reconciliation_work(
            worker_id="worker-a",
            now_ms=10_000,
            lease_until_ms=70_000,
        )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        duplicate = await uow.aggregates.claim_next_routine_reconciliation_work(
            worker_id="worker-b",
            now_ms=10_000,
            lease_until_ms=70_000,
        )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        recovered = await uow.aggregates.claim_next_routine_reconciliation_work(
            worker_id="worker-b",
            now_ms=70_000,
            lease_until_ms=130_000,
        )

    assert first is not None and first.identity.ticket_id == ticket.identity.ticket_id
    assert duplicate is None
    assert recovered is not None
    assert recovered.identity.ticket_id == ticket.identity.ticket_id
