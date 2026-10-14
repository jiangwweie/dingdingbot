from __future__ import annotations

import pytest
import sqlalchemy as sa

from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    seed_strategy_registry,
)
from tests.trading_kernel.support.command_dispatch import seed_policy
from tests.trading_kernel.support.reconciliation_lifecycle import (
    _active_ticket,
    _reach_position_protected,
)


@pytest.mark.asyncio
async def test_expedite_preserves_queue_age_and_normal_retry(dispatch_engine):
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1000)
    await seed_policy(
        dispatch_engine, event_spec_ids=("event_spec:SOR-1H-001:SOR-1H-LONG:v1",)
    )
    ticket = _active_ticket(instrument="SOLUSDT", signal_event_id="signal-expedite")
    await _reach_position_protected(dispatch_engine, ticket)
    tid = ticket.identity.ticket_id
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await uow.aggregates.schedule_next_check(
            tid, work_kind="reconciliation", due_at_ms=4000
        )
        for now in (5000, 6000, 7000):
            await uow.aggregates.expedite_reconciliation(tid, due_at_ms=now)
    async with dispatch_engine.connect() as c:
        assert (
            await c.scalar(
                sa.text(
                    "SELECT reconciliation_due_at_ms FROM brc_trade_aggregates WHERE ticket_id=:id"
                ),
                {"id": tid},
            )
            == 4000
        )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await uow.aggregates.schedule_next_check(
            tid, work_kind="reconciliation", due_at_ms=9000
        )
        await uow.aggregates.expedite_reconciliation(tid, due_at_ms=8000)
    async with dispatch_engine.connect() as c:
        assert (
            await c.scalar(
                sa.text(
                    "SELECT reconciliation_due_at_ms FROM brc_trade_aggregates WHERE ticket_id=:id"
                ),
                {"id": tid},
            )
            == 8000
        )
        original = await c.scalar(
            sa.text(
                "SELECT updated_at_ms FROM brc_trade_aggregates WHERE ticket_id=:id"
            ),
            {"id": tid},
        )
    async with dispatch_engine.begin() as c:
        await c.execute(
            sa.text(
                "UPDATE brc_trade_aggregates SET reconciliation_due_at_ms=NULL WHERE ticket_id=:id"
            ),
            {"id": tid},
        )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await uow.aggregates.expedite_reconciliation(tid, due_at_ms=10000)
    async with dispatch_engine.connect() as c:
        assert (
            await c.scalar(
                sa.text(
                    "SELECT reconciliation_due_at_ms FROM brc_trade_aggregates WHERE ticket_id=:id"
                ),
                {"id": tid},
            )
            == original
        )


@pytest.mark.asyncio
async def test_mismatch_monitor_keeps_first_wait_and_clears(dispatch_engine):
    from src.trading_kernel.application.ports import MonitorOwnerStatus
    from src.trading_kernel.application.reconciliation_health import (
        record_reconciliation_wait,
        resolve_reconciliation_wait,
    )

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await record_reconciliation_wait(
            uow,
            key="reconciliation:probe",
            reason="external_flat_internal_live",
            now_ms=1000,
            allowed_delay_ms=4000,
        )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await record_reconciliation_wait(
            uow,
            key="reconciliation:probe",
            reason="external_flat_internal_live",
            now_ms=2000,
            allowed_delay_ms=4000,
        )
        assert (await uow.monitors.get("reconciliation:probe")).updated_at_ms == 1000
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await record_reconciliation_wait(
            uow,
            key="reconciliation:probe",
            reason="external_flat_internal_live",
            now_ms=6000,
            allowed_delay_ms=4000,
        )
        assert (
            await uow.monitors.get("reconciliation:probe")
        ).owner_status is MonitorOwnerStatus.NEEDS_INTERVENTION
        await resolve_reconciliation_wait(uow, key="reconciliation:probe", now_ms=7000)
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        assert (
            await uow.monitors.get("reconciliation:probe")
        ).owner_status is MonitorOwnerStatus.COMPLETED


@pytest.mark.asyncio
async def test_three_positions_remain_fair_under_continuous_expedite(dispatch_engine):
    from src.trading_kernel.infrastructure.runtime_identity import (
        CURRENT_SCHEMA_REVISION,
    )
    from src.trading_kernel.interfaces.reconciliation_worker import (
        ReconciliationWorkerRequest,
        run_reconciliation_worker_once,
    )
    from tests.trading_kernel.integration.universe_certification_support import (
        NoTicketVenueTruth,
    )
    from tests.trading_kernel.support.reconciliation_lifecycle import (
        _active_stop_truth,
        _ActivePositionSource,
    )

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1000)
    await seed_policy(
        dispatch_engine,
        event_spec_ids=tuple(
            sorted(
                (
                    "event_spec:SOR-1H-001:SOR-1H-LONG:v1",
                    "event_spec:BRF2-001:BRF2-SHORT:v3",
                )
            )
        ),
    )
    tickets = [
        _active_ticket(instrument=i, signal_event_id=f"signal-fair-{i}", event_id=e)
        for i, e in (
            ("SOLUSDT", "SOR-1H-LONG"),
            ("AVAXUSDT", "SOR-1H-LONG"),
            ("BTCUSDT", "BRF2-SHORT"),
        )
    ]
    from decimal import Decimal

    tickets[-1] = tickets[-1].model_copy(
        update={
            "initial_stop_price": Decimal(61000),
            "take_profit_prices": (Decimal(58000),),
            "identity": tickets[-1].identity.model_copy(
                update={
                    "netting_domain": tickets[-1].identity.netting_domain.model_copy(
                        update={"position_side": "short"}
                    )
                }
            ),
        }
    )
    for ticket in tickets:
        await _reach_position_protected(dispatch_engine, ticket)
    source = _ActivePositionSource(
        tickets,
        open_orders_by_ticket=await _active_stop_truth(dispatch_engine, tickets),
    )
    ids = [t.identity.ticket_id for t in tickets]
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        for tid in ids:
            await uow.aggregates.schedule_next_check(
                tid, work_kind="reconciliation", due_at_ms=30000
            )
    seen = set()
    for now in (40000, 45000, 50000, 55000):
        async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
            await uow.aggregates.expedite_reconciliation(ids[0], due_at_ms=now)
        r = await run_reconciliation_worker_once(
            lambda: PostgresKernelUnitOfWork(dispatch_engine),
            NoTicketVenueTruth(),
            source,
            ReconciliationWorkerRequest(
                worker_id="fairness",
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=now,
                timeout_seconds=1,
                unknown_visibility_grace_ms=30000,
                idle_poll_interval_ms=2000,
            ),
        )
        seen.add(r.ticket_id)
    assert seen == set(ids)


@pytest.mark.asyncio
async def test_worker_deadlock_retries_but_other_database_errors_escape(
    dispatch_engine,
):
    from sqlalchemy.exc import DBAPIError

    from src.trading_kernel.application.ports import MonitorOwnerStatus
    from src.trading_kernel.interfaces.reconciliation_worker import (
        run_reconciliation_with_health,
    )

    class Cause(Exception):
        sqlstate = "40P01"

    async def deadlock():
        raise DBAPIError(None, None, Cause(), False)

    for now in (1000, 2000):
        r = await run_reconciliation_with_health(
            lambda: PostgresKernelUnitOfWork(dispatch_engine),
            deadlock,
            worker_id="health-test",
            now_ms=now,
            failure_window_ms=6000,
        )
        assert r.status.value == "database_retry"
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        assert (
            await uow.monitors.get("reconciliation-worker:health-test")
        ).owner_status is MonitorOwnerStatus.NEEDS_INTERVENTION

    class WrongIdentity(Exception):
        sqlstate = "23503"

    async def unsafe():
        raise DBAPIError(None, None, WrongIdentity(), False)

    with pytest.raises(DBAPIError):
        await run_reconciliation_with_health(
            lambda: PostgresKernelUnitOfWork(dispatch_engine),
            unsafe,
            worker_id="health-test",
            now_ms=3000,
            failure_window_ms=6000,
        )


@pytest.mark.asyncio
async def test_expedite_and_retry_updates_serialize(dispatch_engine):
    import asyncio

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1000)
    await seed_policy(dispatch_engine)
    ticket = _active_ticket(instrument="SOLUSDT", signal_event_id="signal-race")
    await _reach_position_protected(dispatch_engine, ticket)
    tid = ticket.identity.ticket_id
    ready = asyncio.Event()

    async def retry():
        async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
            await uow.aggregates.schedule_next_check(
                tid, work_kind="reconciliation", due_at_ms=10000
            )
            ready.set()
            await asyncio.sleep(0.1)

    async def expedite():
        await ready.wait()
        async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
            await uow.aggregates.expedite_reconciliation(tid, due_at_ms=5000)

    await asyncio.wait_for(asyncio.gather(retry(), expedite()), timeout=3)
    async with dispatch_engine.connect() as c:
        assert (
            await c.scalar(
                sa.text(
                    "SELECT reconciliation_due_at_ms FROM brc_trade_aggregates WHERE ticket_id=:id"
                ),
                {"id": tid},
            )
            == 5000
        )


@pytest.mark.asyncio
async def test_real_deadlock_rolls_back_before_next_tick(dispatch_engine):
    import asyncio

    from src.trading_kernel.interfaces.reconciliation_worker import (
        run_reconciliation_with_health,
    )

    ready_a = asyncio.Event()
    ready_b = asyncio.Event()
    async with dispatch_engine.begin() as c:
        await c.execute(
            sa.text(
                "CREATE TABLE reliability_probe(id integer PRIMARY KEY,value integer)"
            )
        )

    async with dispatch_engine.begin() as c:
        await c.execute(sa.text("INSERT INTO reliability_probe VALUES(1,0),(2,0)"))

    async def worker(first, second, own, other):
        async def tick():
            async with dispatch_engine.begin() as c:
                await c.execute(
                    sa.text("UPDATE reliability_probe SET value=value+1 WHERE id=:id"),
                    {"id": first},
                )
                own.set()
                await other.wait()
                await c.execute(
                    sa.text("UPDATE reliability_probe SET value=value+1 WHERE id=:id"),
                    {"id": second},
                )
            from src.trading_kernel.interfaces.reconciliation_worker import (
                ReconciliationWorkerResult,
                ReconciliationWorkerStatus,
            )

            return ReconciliationWorkerResult(status=ReconciliationWorkerStatus.NO_WORK)

        return await run_reconciliation_with_health(
            lambda: PostgresKernelUnitOfWork(dispatch_engine),
            tick,
            worker_id=f"deadlock-{first}",
            now_ms=1000,
            failure_window_ms=6000,
        )

    results = await asyncio.wait_for(
        asyncio.gather(worker(1, 2, ready_a, ready_b), worker(2, 1, ready_b, ready_a)),
        timeout=5,
    )
    assert sorted(r.status.value for r in results) == ["database_retry", "no_work"]
    async with dispatch_engine.connect() as c:
        assert (
            await c.execute(sa.text("SELECT value FROM reliability_probe ORDER BY id"))
        ).scalars().all() == [1, 1]
