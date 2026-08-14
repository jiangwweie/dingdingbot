from __future__ import annotations

import sqlalchemy as sa

from src.trading_kernel.application.ports import (
    MonitorOwnerStatus,
    MonitorStateRecord,
)
from src.trading_kernel.infrastructure.pg_models import monitor_events
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)


async def test_unchanged_monitor_state_advances_observed_time_without_new_event(
    dispatch_engine,
) -> None:
    """Catches a real monitor read being persisted as if it never happened."""

    first = MonitorStateRecord(
        monitor_key="account:binance-usdm:bnb-fee-capability",
        owner_status=MonitorOwnerStatus.RUNNING,
        summary="available",
        intervention="none",
        updated_at_ms=100_000,
    )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await uow.monitors.save_if_changed(first)
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        persisted = await uow.monitors.save_if_changed(
            first.model_copy(update={"updated_at_ms": 400_000})
        )
    async with dispatch_engine.connect() as connection:
        event_count = int(
            await connection.scalar(
                sa.select(sa.func.count()).select_from(monitor_events)
            )
            or 0
        )

    assert persisted.updated_at_ms == 400_000
    assert persisted.projection_version == 1
    assert event_count == 1
