"""Exact 0018 -> 0019 preserves terminal lineage and pauses Owner authority."""

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

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
async def test_management_upgrade_preserves_history_and_exits_recovery_only_mode():
    name, url = await create_empty_database()
    e = create_async_engine(url)
    try:
        run_alembic(url, "upgrade", "0018_notice_outbox_v1")
        async with PostgresKernelUnitOfWork(e) as u:
            await seed_runtime_authority(
                u,
                RuntimeAuthoritySeedRequest(
                    account_id="manual-migration",
                    runtime_commit="a" * 40,
                    schema_revision="0018_notice_outbox_v1",
                    seeded_at_ms=1000,
                ),
            )
        async with e.begin() as c:
            await c.execute(
                sa.text(
                    'UPDATE brc_runtime_capabilities_current SET enabled=false, certification=certification || \'{"runtime_mode":"management_recovery_only","management_recovery_ticket_ids":["ticket:closed"]}\'::jsonb'
                )
            )

        async def snapshot():
            async with e.connect() as c:
                names = (
                    (
                        await c.execute(
                            sa.text(
                                "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename NOT IN ('alembic_version','brc_schema_metadata','brc_runtime_capabilities_current') AND tablename NOT IN ('brc_management_stream_events','brc_order_command_baselines','brc_management_coverage_events','brc_management_feed_current') ORDER BY tablename"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                result={}
                for n in names:
                    projection="to_jsonb(t)"
                    if n=='brc_management_observation_current':
                        projection="(to_jsonb(t)-'current_complete'-'attribution_complete'-'proof_refs'-'continuity_complete') || jsonb_build_object('facts_complete',coalesce(to_jsonb(t)->'facts_complete',to_jsonb(t)->'proof_refs'->'migration'->'legacy_facts_complete'))"
                    result[n]=(await c.execute(sa.text(f'SELECT ({projection})::text FROM "{n}" t ORDER BY to_jsonb(t)::text'))).scalars().all()
                return result

        before = await snapshot()
        run_alembic(url, "upgrade", "head")
        async with PostgresKernelUnitOfWork(e) as u:
            await deploy_compatible_upgrade_identity(
                u,
                RuntimeAuthoritySeedRequest(
                    account_id="manual-migration",
                    runtime_commit="b" * 40,
                    schema_revision="0019_management_evidence_v2",
                    seeded_at_ms=2000,
                ),
            )
        assert await snapshot() == before
        async with e.connect() as c:
            caps = (
                (
                    await c.execute(
                        sa.text("SELECT * FROM brc_runtime_capabilities_current")
                    )
                )
                .mappings()
                .all()
            )
            assert len(caps) == 2 and all(r["enabled"] for r in caps)
            assert all(r["certification"]["management_feed_required"] for r in caps)
            assert all("runtime_mode" not in r["certification"] for r in caps)
            assert await c.scalar(
                sa.text(
                    "SELECT NOT new_entry_submit_enabled FROM brc_owner_policy_current"
                )
            )
    finally:
        await e.dispose()
        await drop_disposable_database(name)
