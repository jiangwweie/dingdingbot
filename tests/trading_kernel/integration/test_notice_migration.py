import pytest
import sqlalchemy as sa

from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    deploy_compatible_upgrade_identity,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from tests.trading_kernel.support.postgres import (
    create_empty_database,
    drop_disposable_database,
    run_alembic,
)


@pytest.mark.asyncio
async def test_exact_0017_notice_migration_preserves_all_source_rows_and_owner_policy():
    name, url = await create_empty_database()
    from sqlalchemy.ext.asyncio import create_async_engine

    e = create_async_engine(url)
    try:
        run_alembic(url, "upgrade", "0017_app_management_observation")
        async with PostgresKernelUnitOfWork(e) as u:
            await seed_runtime_authority(
                u,
                RuntimeAuthoritySeedRequest(
                    account_id="manual-migration",
                    runtime_commit="a" * 40,
                    schema_revision="0017_app_management_observation",
                    seeded_at_ms=1000,
                ),
            )

        async def snapshot():
            async with e.connect() as c:
                names = (
                    (
                        await c.execute(
                            sa.text(
                                "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename NOT IN ('alembic_version','brc_schema_metadata','brc_runtime_capabilities_current','brc_notice_outbox') ORDER BY tablename"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                return {
                    n: (
                        await c.execute(
                            sa.text(
                                f'SELECT to_jsonb(t)::text FROM "{n}" t ORDER BY to_jsonb(t)::text'
                            )
                        )
                    )
                    .scalars()
                    .all()
                    for n in names
                }

        before = await snapshot()
        run_alembic(url, "upgrade", "head")
        async with PostgresKernelUnitOfWork(e) as u:
            await deploy_compatible_upgrade_identity(
                u,
                RuntimeAuthoritySeedRequest(
                    account_id="manual-migration",
                    runtime_commit="b" * 40,
                    schema_revision=CURRENT_SCHEMA_REVISION,
                    seeded_at_ms=2000,
                ),
            )
        assert await snapshot() == before
        async with e.connect() as c:
            assert (
                await c.scalar(sa.text("SELECT count(*) FROM brc_notice_outbox")) == 0
            )
    finally:
        await e.dispose()
        await drop_disposable_database(name)


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["seed", "capability", "account"])
async def test_notice_identity_upgrade_rejects_drifted_source(fault):
    from sqlalchemy.ext.asyncio import create_async_engine

    from src.trading_kernel.infrastructure.runtime_authority_seed import (
        RuntimeAuthorityTransitionRefused,
    )

    name, url = await create_empty_database()
    e = create_async_engine(url)
    try:
        run_alembic(url, "upgrade", "0017_app_management_observation")
        async with PostgresKernelUnitOfWork(e) as u:
            await seed_runtime_authority(
                u,
                RuntimeAuthoritySeedRequest(
                    account_id="manual-migration",
                    runtime_commit="a" * 40,
                    schema_revision="0017_app_management_observation",
                    seeded_at_ms=1000,
                ),
            )
        run_alembic(url, "upgrade", "head")
        async with e.begin() as c:
            if fault == "seed":
                await c.execute(
                    sa.text(
                        "UPDATE brc_schema_metadata SET metadata_value='sha256:invalid' WHERE metadata_key='seed_identity'"
                    )
                )
            if fault == "capability":
                await c.execute(
                    sa.text(
                        "UPDATE brc_runtime_capabilities_current SET certified_commit=:commit"
                    ),
                    {"commit": "c" * 40},
                )
        with pytest.raises(RuntimeAuthorityTransitionRefused):
            async with PostgresKernelUnitOfWork(e) as u:
                await deploy_compatible_upgrade_identity(
                    u,
                    RuntimeAuthoritySeedRequest(
                        account_id="wrong-account"
                        if fault == "account"
                        else "manual-migration",
                        runtime_commit="b" * 40,
                        schema_revision=CURRENT_SCHEMA_REVISION,
                        seeded_at_ms=2000,
                    ),
                )
    finally:
        await e.dispose()
        await drop_disposable_database(name)
