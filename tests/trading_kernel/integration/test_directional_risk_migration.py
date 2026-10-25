import asyncio

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from scripts.trading_kernel.verify_schema import (
    _directional_source_preservation_manifest,
)
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
async def test_0012_to_0013_preserves_every_source_table_and_installs_only_unset():
    name, url = await create_empty_database()
    engine = create_async_engine(url)
    try:
        await asyncio.to_thread(
            run_alembic, url, "upgrade", "0012_generic_signal_path_v1"
        )
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id="test",
                    runtime_commit="a" * 40,
                    schema_revision="0012_generic_signal_path_v1",
                    seeded_at_ms=1000,
                ),
            )
        async with engine.begin() as c:
            before = await _directional_source_preservation_manifest(c)
            assert before["table_count"] == 85 and before["row_count"] > 100
        await asyncio.to_thread(run_alembic, url, "upgrade", "head")
        async with engine.connect() as c:
            after = await _directional_source_preservation_manifest(c)
            assert before["digest"] == after["digest"]
            assert (
                await c.execute(
                    sa.text("SELECT view,version FROM brc_directional_risk_controls")
                )
            ).all() == [("unset", 1)]
            assert (
                await c.scalar(
                    sa.text("SELECT count(*) FROM brc_directional_risk_events")
                )
                == 0
            )
    finally:
        await engine.dispose()
        await drop_disposable_database(name)
