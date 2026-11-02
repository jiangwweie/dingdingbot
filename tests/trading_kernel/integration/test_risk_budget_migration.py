import asyncio

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from scripts.trading_kernel.verify_schema import (
    _risk_budget_source_preservation_manifest,
)
from tests.trading_kernel.support.postgres import (
    create_empty_database,
    drop_disposable_database,
    run_alembic,
)


@pytest.mark.asyncio
async def test_risk_budget_migration_preserves_source_history_and_owner_view():
    name, url = await create_empty_database()
    engine = create_async_engine(url)
    try:
        await asyncio.to_thread(
            run_alembic, url, "upgrade", "0013_owner_directional_risk_v1"
        )
        from src.trading_kernel.infrastructure.pg_unit_of_work import (
            PostgresKernelUnitOfWork,
        )
        from src.trading_kernel.infrastructure.runtime_authority_seed import (
            RuntimeAuthoritySeedRequest,
            seed_runtime_authority,
        )

        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id="test",
                    runtime_commit="a" * 40,
                    schema_revision="0013_owner_directional_risk_v1",
                    seeded_at_ms=1000,
                ),
            )
        async with engine.begin() as c:
            await c.execute(
                sa.text(
                    "INSERT INTO brc_directional_risk_controls(venue_id,account_id,version,view,rule_id,rule_digest,effective_at_ms) SELECT 'binance-usdm','test',6,'bearish',rule_id,rule_digest,1000 FROM brc_directional_risk_rules WHERE rule_id='owner-directional-risk:v1'"
                )
            )
            before = await _risk_budget_source_preservation_manifest(c)
        await asyncio.to_thread(run_alembic, url, "upgrade", "0014_dynamic_risk_budget_v1")
        async with engine.connect() as c:
            after = await _risk_budget_source_preservation_manifest(c)
            assert before["digest"] == after["digest"]
            row = (
                await c.execute(
                    sa.text(
                        "SELECT view,version,pending_baseline,rule_id FROM brc_directional_risk_controls"
                    )
                )
            ).one()
            assert tuple(row) == ("bearish", 7, None, "owner-directional-risk:v2")
    finally:
        await engine.dispose()
        await drop_disposable_database(name)
