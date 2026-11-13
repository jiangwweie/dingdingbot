"""Installer compares exact source columns, retaining every original control value."""
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from scripts.trading_kernel.manual_same_schema_upgrade import read_preserved_controls
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from tests.trading_kernel.support.postgres import (
    create_empty_database,
    drop_disposable_database,
    run_alembic,
)


@pytest.mark.asyncio
async def test_forward_policy_addition_preserves_controls_but_real_changes_fail_comparison():
    name,url=await create_empty_database();engine=create_async_engine(url)
    try:
        run_alembic(url,'upgrade','0021_manual_operational_closure')
        async with PostgresKernelUnitOfWork(engine) as u:
            await seed_runtime_authority(u,RuntimeAuthoritySeedRequest(account_id='projection',runtime_commit='a'*40,schema_revision='0021_manual_operational_closure',seeded_at_ms=1000))
        async with engine.connect() as c:
            columns={n:(await c.execute(sa.text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=:n ORDER BY ordinal_position"),{'n':n})).scalars().all() for n in ['brc_owner_policy_current','brc_strategy_entry_controls_current','brc_strategy_selection_control_current']}
            before=await read_preserved_controls(c,columns)
            raw_before=(await c.execute(sa.text('SELECT * FROM brc_owner_policy_current'))).mappings().all()
        run_alembic(url,'upgrade','head')
        await engine.dispose()  # DDL invalidates asyncpg's cached SELECT-star shape.
        async with engine.connect() as c:
            after=await read_preserved_controls(c,columns)
            raw_after=(await c.execute(sa.text('SELECT * FROM brc_owner_policy_current'))).mappings().all()
            assert raw_before!=raw_after
            assert before==after
            assert all('margin_allocation_contract' not in row for row in after['policy'])
        async with engine.begin() as c:
            await c.execute(sa.text('UPDATE brc_owner_policy_current SET priority_rank=priority_rank+1'))
        async with engine.connect() as c:
            assert await read_preserved_controls(c,columns)!=before
    finally:
        await engine.dispose();await drop_disposable_database(name)
