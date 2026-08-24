"""Reusable exact Selection Entry Vacuum setup for PostgreSQL tests."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.domain.strategy_entry_vacuum import (
    StrategyEntryVacuum,
    StrategyEntryVacuumState,
)
from src.trading_kernel.infrastructure.pg_models import (
    instrument_selection_specs,
    strategy_entry_vacuum_events,
    strategy_entry_vacuums_current,
    strategy_selection_control_current,
)

SELECTION_SPEC_ID = "sor-dynamic-selection-v0"
SESSION_START_MS = 86_400_000


async def open_entry_vacuum(
    engine: AsyncEngine,
    ticket,
    *,
    entry_vacuum_id: str = "vacuum:SOR-001:86400000:test",
    state: StrategyEntryVacuumState = StrategyEntryVacuumState.DRAINING_ENTRY,
    first_blocker: str = "TEST_SELECTION_RECONFIGURATION",
    fenced_at_ms: int = SESSION_START_MS + 3_600_000,
) -> StrategyEntryVacuum:
    """Install only the exact durable facts required by a Vacuum boundary test."""

    return await open_strategy_entry_vacuum(
        engine,
        strategy_group_id=ticket.identity.runtime.strategy_group_id,
        strategy_version_id=ticket.identity.runtime.strategy_version_id,
        entry_vacuum_id=entry_vacuum_id,
        state=state,
        first_blocker=first_blocker,
        fenced_at_ms=fenced_at_ms,
    )


async def open_strategy_entry_vacuum(
    engine: AsyncEngine,
    *,
    strategy_group_id: str,
    strategy_version_id: str,
    entry_vacuum_id: str = "vacuum:SOR-001:86400000:test",
    state: StrategyEntryVacuumState = StrategyEntryVacuumState.DRAINING_ENTRY,
    first_blocker: str = "TEST_SELECTION_RECONFIGURATION",
    fenced_at_ms: int = SESSION_START_MS + 3_600_000,
) -> StrategyEntryVacuum:
    """Install a scoped Vacuum without requiring a pre-existing Ticket."""

    vacuum = StrategyEntryVacuum(
        entry_vacuum_id=entry_vacuum_id,
        strategy_group_id=strategy_group_id,
        selection_spec_id=SELECTION_SPEC_ID,
        session_start_ms=SESSION_START_MS,
        source_generation_id=None,
        state=state,
        fenced_at_ms=fenced_at_ms,
        drained_at_ms=None,
        resolved_at_ms=None,
        first_blocker=first_blocker,
        projection_version=1,
    )
    async with engine.begin() as connection:
        await connection.execute(
            pg_insert(instrument_selection_specs)
            .values(
                selection_spec_id=SELECTION_SPEC_ID,
                strategy_group_id=strategy_group_id,
                strategy_version_id=strategy_version_id,
                selection_version=1,
                selection_kind="sor_dynamic_v0",
                algorithm_semantic_digest="sha256:" + "d" * 64,
                status="active",
                installed_at_ms=fenced_at_ms,
            )
            .on_conflict_do_nothing(
                index_elements=[instrument_selection_specs.c.selection_spec_id]
            )
        )
        await connection.execute(
            pg_insert(strategy_selection_control_current)
            .values(
                strategy_group_id=strategy_group_id,
                selection_spec_id=SELECTION_SPEC_ID,
                selection_mode="dynamic_selection",
                pending_selection_mode=None,
                pending_effective_session_start_ms=None,
                pending_authorization_id=None,
                control_version=1,
                rollback_baseline_id=None,
                updated_at_ms=fenced_at_ms,
            )
            .on_conflict_do_update(
                index_elements=[
                    strategy_selection_control_current.c.strategy_group_id
                ],
                set_={
                    "selection_spec_id": SELECTION_SPEC_ID,
                    "selection_mode": "dynamic_selection",
                    "pending_selection_mode": None,
                    "pending_effective_session_start_ms": None,
                    "pending_authorization_id": None,
                    "control_version": 1,
                    "rollback_baseline_id": None,
                    "updated_at_ms": fenced_at_ms,
                },
            )
        )
        await connection.execute(
            sa.insert(strategy_entry_vacuums_current).values(
                **vacuum.model_dump(mode="json")
            )
        )
        await connection.execute(
            sa.insert(strategy_entry_vacuum_events).values(
                entry_vacuum_event_id=f"vacuum-event:{entry_vacuum_id}:1",
                entry_vacuum_id=entry_vacuum_id,
                event_sequence=1,
                event_type=state.value,
                payload={"test_fixture": True},
                occurred_at_ms=fenced_at_ms,
            )
        )
    return vacuum
