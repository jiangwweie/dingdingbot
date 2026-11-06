import asyncio

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from tests.trading_kernel.support.postgres import (
    create_empty_database,
    drop_disposable_database,
    run_alembic,
)


@pytest.mark.asyncio
async def test_app_management_migration_preserves_source_rows():
    name,url=await create_empty_database();engine=create_async_engine(url)
    try:
        await asyncio.to_thread(run_alembic,url,'upgrade','0015_generic_owner_recovery_v1')
        async with engine.begin() as c:
            await c.execute(sa.text("INSERT INTO brc_schema_metadata(metadata_key,metadata_value,updated_at_ms) VALUES ('amt-preservation-test','do-not-change',1000)"))
            columns=(await c.execute(sa.text("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='public' AND table_name LIKE 'brc_%' ORDER BY table_name,ordinal_position"))).all()
            tables={}
            for table,column in columns:tables.setdefault(table,[]).append(column)
            before={}
            for table,cols in tables.items():
                before[table]=sorted((dict(r) for r in (await c.execute(sa.text('SELECT '+','.join(cols)+' FROM '+table))).mappings()),key=str)
        await asyncio.to_thread(run_alembic,url,'upgrade','head')
        async with engine.connect() as c:
            for table,cols in tables.items():
                after=sorted((dict(r) for r in (await c.execute(sa.text('SELECT '+','.join(cols)+' FROM '+table))).mappings()),key=str)
                assert after==before[table],table
    finally:
        await engine.dispose();await drop_disposable_database(name)
