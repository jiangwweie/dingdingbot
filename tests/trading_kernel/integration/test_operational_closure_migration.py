import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from scripts.trading_kernel.manual_same_schema_upgrade import (
    preservation_projection_sql,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    deploy_compatible_upgrade_identity,
    seed_runtime_authority,
)
from tests.trading_kernel.support.postgres import (
    create_empty_database,
    drop_disposable_database,
    run_alembic,
)


@pytest.mark.asyncio
async def test_0020_to_0021_preserves_every_source_column_and_keeps_entry_paused():
    name,url=await create_empty_database();e=create_async_engine(url)
    try:
        run_alembic(url,'upgrade','0020_manual_exit_regime_v1')
        async with PostgresKernelUnitOfWork(e) as u:
            await seed_runtime_authority(u,RuntimeAuthoritySeedRequest(account_id='manual-migration',runtime_commit='a'*40,
                schema_revision='0020_manual_exit_regime_v1',seeded_at_ms=1000))
        async with e.connect() as c:
            names=(await c.execute(sa.text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename NOT IN ('alembic_version','brc_schema_metadata','brc_runtime_capabilities_current') ORDER BY tablename"))).scalars().all()
            cols={n:(await c.execute(sa.text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=:n ORDER BY ordinal_position"),{'n':n})).scalars().all() for n in names}
            before={n:(await c.execute(sa.text(preservation_projection_sql(n,cols[n])))).scalars().all() for n in names}
        run_alembic(url,'upgrade','head')
        async with PostgresKernelUnitOfWork(e) as u:
            await deploy_compatible_upgrade_identity(u,RuntimeAuthoritySeedRequest(account_id='manual-migration',runtime_commit='b'*40,
                schema_revision='0021_manual_operational_closure',seeded_at_ms=2000))
        async with e.connect() as c:
            assert before=={n:(await c.execute(sa.text(preservation_projection_sql(n,cols[n])))).scalars().all() for n in names}
            assert not await c.scalar(sa.text('SELECT new_entry_submit_enabled FROM brc_owner_policy_current'))
            for table in ['brc_failure_diagnostics','brc_review_enrichment_requests']:
                assert await c.scalar(sa.text(f'SELECT count(*) FROM {table}'))==0
    finally:
        await e.dispose();await drop_disposable_database(name)


@pytest.mark.asyncio
@pytest.mark.parametrize('table,change',[('brc_owner_policy_current','new_entry_submit_enabled=true'),
    ('brc_entry_lane_current',"status='claimed'"),('brc_account_exposure_current','active_ticket_count=1')])
async def test_0021_refuses_dirty_source_before_schema_or_data_mutation(table,change):
    name,url=await create_empty_database();e=create_async_engine(url)
    try:
        run_alembic(url,'upgrade','0020_manual_exit_regime_v1')
        async with PostgresKernelUnitOfWork(e) as u:
            await seed_runtime_authority(u,RuntimeAuthoritySeedRequest(account_id='manual-migration',runtime_commit='a'*40,
                schema_revision='0020_manual_exit_regime_v1',seeded_at_ms=1000))
        async with e.begin() as c:
            await c.execute(sa.text(f'UPDATE {table} SET {change}'))
        with pytest.raises(AssertionError,match='0021 requires'):
            run_alembic(url,'upgrade','head')
        async with e.connect() as c:
            assert await c.scalar(sa.text('SELECT version_num FROM alembic_version'))=='0020_manual_exit_regime_v1'
            assert not await c.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM pg_tables WHERE tablename='brc_failure_diagnostics')"))
    finally:
        await e.dispose();await drop_disposable_database(name)
