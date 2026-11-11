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
async def test_exact_manual_forward_upgrade_preserves_all_source_rows_and_owner_controls():
    name, url = await create_empty_database()
    engine = create_async_engine(url)
    try:
        run_alembic(url, "upgrade", "0019_management_evidence_v2")
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id="manual-migration",
                    runtime_commit="a" * 40,
                    schema_revision="0019_management_evidence_v2",
                    seeded_at_ms=1000,
                ),
            )
        async with engine.connect() as c:
            names = (
                (
                    await c.execute(
                        sa.text(
                            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename NOT IN ('alembic_version','brc_schema_metadata','brc_runtime_capabilities_current') ORDER BY tablename"
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
        run_alembic(url, "upgrade", "0020_manual_exit_regime_v1")
        async with PostgresKernelUnitOfWork(engine) as uow:
            await deploy_compatible_upgrade_identity(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id="manual-migration",
                    runtime_commit="b" * 40,
                    schema_revision="0020_manual_exit_regime_v1",
                    seeded_at_ms=2000,
                ),
            )
        async with engine.connect() as c:
            after = {
                n: (
                    await c.execute(sa.text(preservation_projection_sql(n, columns[n])))
                )
                .scalars()
                .all()
                for n in names
            }
            assert after == before
            assert not await c.scalar(
                sa.text("SELECT new_entry_submit_enabled FROM brc_owner_policy_current")
            )
            assert await c.scalar(
                sa.text(
                    "SELECT bool_and((certification->>'management_feed_required')::boolean) FROM brc_runtime_capabilities_current"
                )
            )
            for n in [
                "brc_post_fill_exit_plans",
                "brc_exit_configurations",
                "brc_exit_configuration_current",
                "brc_btc_ma50_current",
            ]:
                assert await c.scalar(sa.text(f"SELECT count(*) FROM {n}")) == 0
    finally:
        await engine.dispose()
        await drop_disposable_database(name)


@pytest.mark.asyncio
@pytest.mark.parametrize("blocker", ["entry_lane", "exposure_counter"])
async def test_forward_upgrade_rejects_residual_lane_or_exposure_occupation(blocker):
    name, url = await create_empty_database()
    engine = create_async_engine(url)
    try:
        run_alembic(url, "upgrade", "0019_management_evidence_v2")
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id="manual-migration",
                    runtime_commit="a" * 40,
                    schema_revision="0019_management_evidence_v2",
                    seeded_at_ms=1000,
                ),
            )
        async with engine.begin() as c:
            if blocker == "entry_lane":
                await c.execute(
                    sa.text("UPDATE brc_entry_lane_current SET status='claimed'")
                )
            else:
                await c.execute(
                    sa.text(
                        "UPDATE brc_account_exposure_current SET active_ticket_count=1"
                    )
                )
        with pytest.raises(AssertionError, match="0020 requires"):
            run_alembic(url, "upgrade", "head")
        async with engine.connect() as c:
            assert (
                await c.scalar(sa.text("SELECT version_num FROM alembic_version"))
                == "0019_management_evidence_v2"
            )
    finally:
        await engine.dispose()
        await drop_disposable_database(name)
