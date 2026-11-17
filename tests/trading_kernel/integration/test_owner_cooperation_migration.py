"""Owner cooperation is an additive stopped/flat, preservation-gated upgrade."""

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from scripts.trading_kernel.manual_same_schema_upgrade import (
    preservation_projection_sql,
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
@pytest.mark.parametrize("enabled", [False, True])
async def test_owner_schema_preserves_source_values_and_rejects_enabled_entry(enabled):
    name, url = await create_empty_database()
    e = create_async_engine(url)
    try:
        run_alembic(url, "upgrade", "0023_management_recovery")
        async with PostgresKernelUnitOfWork(e) as u:
            await seed_runtime_authority(
                u,
                RuntimeAuthoritySeedRequest(
                    account_id="owner-migration",
                    runtime_commit="a" * 40,
                    schema_revision="0023_management_recovery",
                    seeded_at_ms=1000,
                ),
            )
        async with e.begin() as c:
            if enabled:
                await c.execute(
                    sa.text(
                        "UPDATE brc_owner_policy_current SET new_entry_submit_enabled=true"
                    )
                )
        async with e.connect() as c:
            names = (
                (
                    await c.execute(
                        sa.text(
                            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename<>'alembic_version' ORDER BY tablename"
                        )
                    )
                )
                .scalars()
                .all()
            )
            columns = {
                n: (
                    await c.execute(
                        sa.text(
                            "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=:n ORDER BY ordinal_position"
                        ),
                        {"n": n},
                    )
                )
                .scalars()
                .all()
                for n in names
            }
            before = {
                n: (
                    await c.execute(sa.text(preservation_projection_sql(n, columns[n])))
                )
                .scalars()
                .all()
                for n in names
            }
        if enabled:
            with pytest.raises(AssertionError, match="0024 requires stopped flat"):
                run_alembic(url, "upgrade", "0024_owner_cooperation")
        else:
            run_alembic(url, "upgrade", "0024_owner_cooperation")
        await e.dispose()
        async with e.connect() as c:
            after = {
                n: (
                    await c.execute(sa.text(preservation_projection_sql(n, columns[n])))
                )
                .scalars()
                .all()
                for n in names
            }
            assert before == after
            assert await c.scalar(
                sa.text("SELECT version_num FROM alembic_version")
            ) == ("0023_management_recovery" if enabled else "0024_owner_cooperation")
            if not enabled:
                for table in [
                    "brc_owner_device_registrations",
                    "brc_owner_device_sessions",
                    "brc_owner_binding_grants",
                    "brc_owner_request_nonces",
                    "brc_owner_position_operations",
                    "brc_owner_position_operation_events",
                ]:
                    assert await c.scalar(sa.text("SELECT count(*) FROM " + table)) == 0
    finally:
        await e.dispose()
        await drop_disposable_database(name)
