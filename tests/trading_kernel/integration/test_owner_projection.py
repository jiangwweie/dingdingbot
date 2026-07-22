from __future__ import annotations

import pytest

from src.trading_kernel.application.ports import MonitorOwnerStatus
from src.trading_kernel.application.project_owner_state import (
    OwnerProjectionFacts,
    OwnerProjectionRequest,
    derive_owner_projection,
    project_owner_state,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.integration import test_command_dispatch as dispatch_fixture
from tests.trading_kernel.integration.test_command_dispatch import _seed_policy


owner_projection_engine = dispatch_fixture.dispatch_engine


@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        (
            OwnerProjectionFacts(policy_exists=False, policy_enabled=False),
            MonitorOwnerStatus.NOT_ENABLED,
        ),
        (
            OwnerProjectionFacts(policy_exists=True, policy_enabled=True),
            MonitorOwnerStatus.RUNNING,
        ),
        (
            OwnerProjectionFacts(
                policy_exists=True,
                policy_enabled=True,
                readiness_state="signal_absent",
                first_blocker="signal_absent",
            ),
            MonitorOwnerStatus.WAITING_FOR_OPPORTUNITY,
        ),
        (
            OwnerProjectionFacts(
                policy_exists=True,
                policy_enabled=True,
                readiness_state="candidate_ready",
            ),
            MonitorOwnerStatus.PROCESSING,
        ),
        (
            OwnerProjectionFacts(
                policy_exists=True,
                policy_enabled=True,
                readiness_state="blocked",
                first_blocker="observation_unavailable",
            ),
            MonitorOwnerStatus.TEMPORARILY_UNAVAILABLE,
        ),
        (
            OwnerProjectionFacts(
                policy_exists=True,
                policy_enabled=True,
                incident_id="incident-1",
            ),
            MonitorOwnerStatus.NEEDS_INTERVENTION,
        ),
        (
            OwnerProjectionFacts(policy_exists=True, policy_enabled=False),
            MonitorOwnerStatus.PAUSED,
        ),
        (
            OwnerProjectionFacts(
                policy_exists=True,
                policy_enabled=True,
                aggregate_status=AggregateStatus.TERMINAL,
                ticket_id="ticket-1",
            ),
            MonitorOwnerStatus.COMPLETED,
        ),
    ],
)
def test_owner_projection_uses_all_documented_product_states(
    facts: OwnerProjectionFacts,
    expected: MonitorOwnerStatus,
) -> None:
    projection = derive_owner_projection(
        monitor_key="scope:SOR-LONG:BTCUSDT:long",
        facts=facts,
        updated_at_ms=2_000,
    )

    assert projection.owner_status is expected
    assert projection.intervention == (
        "需要介入"
        if expected is MonitorOwnerStatus.NEEDS_INTERVENTION
        else "无需操作"
    )


@pytest.mark.asyncio
async def test_owner_projection_reads_pg_authority_and_saves_only_material_change(
    owner_projection_engine,
) -> None:
    await _seed_policy(owner_projection_engine)
    async with PostgresKernelUnitOfWork(owner_projection_engine) as uow:
        await uow.signals.save_readiness(
            runtime_scope_id="scope-owner-projection",
            readiness_state="signal_absent",
            first_blocker="signal_absent",
            signal_event_id=None,
            fact_summary={"detector_reason": "not_triggered"},
            updated_at_ms=1_900,
        )

    request = OwnerProjectionRequest(
        monitor_key="scope-owner-projection",
        owner_policy_id="policy-main",
        runtime_scope_id="scope-owner-projection",
        ticket_id=None,
        updated_at_ms=2_000,
    )
    async with PostgresKernelUnitOfWork(owner_projection_engine) as uow:
        first = await project_owner_state(uow, request)
    async with PostgresKernelUnitOfWork(owner_projection_engine) as uow:
        repeated = await project_owner_state(
            uow,
            request.model_copy(update={"updated_at_ms": 2_100}),
        )

    assert first.owner_status is MonitorOwnerStatus.WAITING_FOR_OPPORTUNITY
    assert repeated.projection_version == first.projection_version
