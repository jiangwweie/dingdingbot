import pytest
import sqlalchemy as sa

from src.trading_kernel.application.ports import MonitorOwnerStatus
from src.trading_kernel.application.reconciliation_health import (
    record_reconciliation_wait,
)
from src.trading_kernel.domain.operational_evidence import FailureDiagnostic
from src.trading_kernel.infrastructure.pg_operational_evidence import (
    PostgresFailureDiagnostics,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork


@pytest.mark.asyncio
async def test_failure_history_survives_success_and_exact_retry_is_idempotent(head_template_engine):
    engine=head_template_engine
    async with engine.begin() as c:
        repo=PostgresFailureDiagnostics(c)
        first=FailureDiagnostic(stage='certification',subject_id='DOGE',reason_code='projected_position_exceeds_venue',
            basis={'projected_quantity':'32811','venue_quantity':'16406'},occurred_at_ms=1000)
        await repo.record(first);await repo.record(first)
        await repo.record(FailureDiagnostic(stage='certification',subject_id='DOGE',reason_code='readonly_facts_unavailable',
            basis={'error_type':'TimeoutError'},occurred_at_ms=2000))
    async with engine.connect() as c:
        rows=await PostgresFailureDiagnostics(c).recent('DOGE')
        assert [r['reason_code'] for r in rows]==['readonly_facts_unavailable','projected_position_exceeds_venue']
        assert rows[1]['basis']['venue_quantity']=='16406'
    with pytest.raises(sa.exc.DBAPIError,match='immutable'):
        async with engine.begin() as c:
            await c.execute(sa.text("UPDATE brc_failure_diagnostics SET reason_code='success'"))


@pytest.mark.asyncio
async def test_closure_health_survives_restart_and_emits_one_real_time_alert(head_template_engine):
    e=head_template_engine
    for now,delay in [(1000,300_000),(181_000,180_000),(301_000,300_000),(301_001,900_000)]:
        async with PostgresKernelUnitOfWork(e) as u:
            await record_reconciliation_wait(u,key='reconciliation-closure:probe',reason='closure_wait:review_pending',
                now_ms=now,allowed_delay_ms=delay)
    async with PostgresKernelUnitOfWork(e) as u:
        state=await u.monitors.get('reconciliation-closure:probe')
        assert state.owner_status is MonitorOwnerStatus.NEEDS_INTERVENTION
        assert state.first_wait_at_ms==1000 and state.last_checked_at_ms==301001
        assert state.escalated_at_ms==301000
    async with e.connect() as c:
        assert await c.scalar(sa.text("SELECT count(*) FROM brc_monitor_events WHERE monitor_key='reconciliation-closure:probe'"))==2
        assert await c.scalar(sa.text("SELECT count(*) FROM brc_notice_outbox WHERE kind='runtime_fault'"))==1
        assert await c.scalar(sa.text("SELECT created_at_ms FROM brc_notice_outbox WHERE kind='runtime_fault'"))==301000
