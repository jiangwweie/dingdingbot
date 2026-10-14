from __future__ import annotations

import pytest

from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_identity import (
    CURRENT_SCHEMA_REVISION,
)
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    seed_strategy_registry,
)
from src.trading_kernel.interfaces.reconciliation_worker import (
    ReconciliationWorkerRequest,
    ReconciliationWorkerStatus,
    run_reconciliation_worker_once,
)
from tests.trading_kernel.full_chain.lifecycle_support import (
    reach_runner_protected,
)
from tests.trading_kernel.integration.universe_certification_support import (
    NoTicketVenueTruth,
)
from tests.trading_kernel.support.command_dispatch import (
    seed_policy as _seed_policy,
)
from tests.trading_kernel.support.reconciliation_lifecycle import (
    _active_stop_truth,
    _active_ticket,
    _ActivePositionSource,
    _assert_active_protection_is_unchanged,
    _reach_position_protected,
    _run_no_change_lifecycle,
    _settlement_pending_from_runner,
)


@pytest.mark.asyncio
async def test_two_due_active_positions_cannot_starve_btc_like_settlement(
    dispatch_engine,
) -> None:
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1_000)
    await _seed_policy(
        dispatch_engine,
        event_spec_ids=(
            "event_spec:MI-001:MI-LONG:v3",
            "event_spec:SOR-1H-001:SOR-1H-LONG:v1",
        ),
    )
    sol_ticket = _active_ticket(instrument="SOLUSDT", signal_event_id="signal-sol")
    avax_ticket = _active_ticket(instrument="AVAXUSDT", signal_event_id="signal-avax")
    await _reach_position_protected(dispatch_engine, sol_ticket)
    await reach_runner_protected(dispatch_engine, avax_ticket, seed_policy=False)

    btc_ticket = _active_ticket(
        instrument="BTCUSDT",
        signal_event_id="signal-btc",
        event_id="MI-LONG",
    )
    await _settlement_pending_from_runner(dispatch_engine, btc_ticket)
    open_orders_by_ticket = await _active_stop_truth(
        dispatch_engine,
        (sol_ticket, avax_ticket),
    )
    source = _ActivePositionSource(
        (sol_ticket, avax_ticket),
        open_orders_by_ticket=open_orders_by_ticket,
    )
    request = ReconciliationWorkerRequest(
        worker_id="reconciliation-fairness-full-chain",
        runtime_commit="kernel-test-head",
        schema_revision=CURRENT_SCHEMA_REVISION,
        now_ms=33_600,
        timeout_seconds=1,
        unknown_visibility_grace_ms=30_000,
        idle_poll_interval_ms=2_000,
    )

    protected = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        NoTicketVenueTruth(),
        source,
        request,
    )
    assert protected.status is ReconciliationWorkerStatus.POSITION_RECONCILED
    assert protected.housekeeping_status is ReconciliationWorkerStatus.SETTLED
    assert protected.housekeeping_ticket_id == btc_ticket.identity.ticket_id
    assert protected.ticket_id in {
        sol_ticket.identity.ticket_id,
        avax_ticket.identity.ticket_id,
    }

    other_protected = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        NoTicketVenueTruth(),
        source,
        request.model_copy(update={"now_ms": 38_600}),
    )
    assert other_protected.status is ReconciliationWorkerStatus.POSITION_RECONCILED
    assert other_protected.ticket_id in {
        sol_ticket.identity.ticket_id,
        avax_ticket.identity.ticket_id,
    }
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
    assert avax is not None and avax.status is AggregateStatus.RUNNER_PROTECTED
    await _run_no_change_lifecycle(dispatch_engine, sol_ticket, runner=False)
    await _run_no_change_lifecycle(dispatch_engine, avax_ticket, runner=True)
    await _assert_active_protection_is_unchanged(
        dispatch_engine,
        sol_ticket,
        status=AggregateStatus.POSITION_PROTECTED,
        expected_stop=open_orders_by_ticket[sol_ticket.identity.ticket_id][0],
    )
    await _assert_active_protection_is_unchanged(
        dispatch_engine,
        avax_ticket,
        status=AggregateStatus.RUNNER_PROTECTED,
        expected_stop=open_orders_by_ticket[avax_ticket.identity.ticket_id][0],
    )
