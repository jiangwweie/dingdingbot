"""0022->0023 preserves every source value and rejects enabled ENTRY."""

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


@pytest.mark.parametrize("entry_enabled", [False, True])
async def test_recovery_migration_is_flat_paused_and_preservation_gated(entry_enabled):
    name, url = await create_empty_database()
    e = create_async_engine(url)
    try:
        run_alembic(url, "upgrade", "0022_wallet_margin_allocation")
        async with PostgresKernelUnitOfWork(e) as u:
            await seed_runtime_authority(
                u,
                RuntimeAuthoritySeedRequest(
                    account_id="manual-recovery",
                    runtime_commit="a" * 40,
                    schema_revision="0022_wallet_margin_allocation",
                    seeded_at_ms=1000,
                ),
            )
        async with e.begin() as c:
            if entry_enabled:
                await c.execute(
                    sa.text(
                        "UPDATE brc_owner_policy_current SET new_entry_submit_enabled=true"
                    )
                )
        async with e.connect() as c:
            tables = (
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
                for n in tables
            }
            before = {
                n: (
                    await c.execute(sa.text(preservation_projection_sql(n, columns[n])))
                )
                .scalars()
                .all()
                for n in tables
            }
        if entry_enabled:
            with pytest.raises(AssertionError, match="0023 requires stopped flat"):
                run_alembic(url, "upgrade", "0023_management_recovery")
        else:
            run_alembic(url, "upgrade", "0023_management_recovery")
        async with e.connect() as c:
            after = {
                n: (
                    await c.execute(sa.text(preservation_projection_sql(n, columns[n])))
                )
                .scalars()
                .all()
                for n in tables
            }
            assert before == after
            assert await c.scalar(
                sa.text("SELECT version_num FROM alembic_version")
            ) == (
                "0022_wallet_margin_allocation"
                if entry_enabled
                else "0023_management_recovery"
            )
        if not entry_enabled:
            async with PostgresKernelUnitOfWork(e) as u:
                await deploy_compatible_upgrade_identity(
                    u,
                    RuntimeAuthoritySeedRequest(
                        account_id="manual-recovery",
                        runtime_commit="b" * 40,
                        schema_revision="0023_management_recovery",
                        seeded_at_ms=2000,
                    ),
                )
            with pytest.raises(AssertionError, match="forward-only"):
                run_alembic(url, "downgrade", "0022_wallet_margin_allocation")
    finally:
        await e.dispose()
        await drop_disposable_database(name)
