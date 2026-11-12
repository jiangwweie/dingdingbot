"""Flat forward upgrade retains old columns and cannot issue unversioned claims."""

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
async def test_wallet_migration_preserves_source_columns_and_installs_insert_guard():
    name, url = await create_empty_database()
    engine = create_async_engine(url)
    try:
        run_alembic(url, "upgrade", "0021_manual_operational_closure")
        async with PostgresKernelUnitOfWork(engine) as u:
            await seed_runtime_authority(
                u,
                RuntimeAuthoritySeedRequest(
                    account_id="manual-migration",
                    runtime_commit="a" * 40,
                    schema_revision="0021_manual_operational_closure",
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
            cols = {
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
                n: (await c.execute(sa.text(preservation_projection_sql(n, cols[n]))))
                .scalars()
                .all()
                for n in names
            }
        run_alembic(url, "upgrade", "head")
        async with PostgresKernelUnitOfWork(engine) as u:
            await deploy_compatible_upgrade_identity(
                u,
                RuntimeAuthoritySeedRequest(
                    account_id="manual-migration",
                    runtime_commit="b" * 40,
                    schema_revision="0022_wallet_margin_allocation",
                    seeded_at_ms=2000,
                ),
            )
        async with engine.connect() as c:
            assert before == {
                n: (await c.execute(sa.text(preservation_projection_sql(n, cols[n]))))
                .scalars()
                .all()
                for n in names
            }
            assert not await c.scalar(
                sa.text("SELECT new_entry_submit_enabled FROM brc_owner_policy_current")
            )
            assert await c.scalar(
                sa.text(
                    "SELECT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='trg_brc_require_wallet_allocation' AND tgenabled='O')"
                )
            )
        with pytest.raises(AssertionError, match="forward-only"):
            run_alembic(url, "downgrade", "0021_manual_operational_closure")
    finally:
        await engine.dispose()
        await drop_disposable_database(name)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "table,change",
    [
        ("brc_owner_policy_current", "new_entry_submit_enabled=true"),
        ("brc_entry_lane_current", "status='claimed'"),
        ("brc_account_exposure_current", "active_ticket_count=1"),
    ],
)
async def test_wallet_migration_rejects_dirty_source_atomically(table, change):
    name, url = await create_empty_database()
    engine = create_async_engine(url)
    try:
        run_alembic(url, "upgrade", "0021_manual_operational_closure")
        async with PostgresKernelUnitOfWork(engine) as u:
            await seed_runtime_authority(
                u,
                RuntimeAuthoritySeedRequest(
                    account_id="manual-migration",
                    runtime_commit="a" * 40,
                    schema_revision="0021_manual_operational_closure",
                    seeded_at_ms=1000,
                ),
            )
        async with engine.begin() as c:
            await c.execute(sa.text(f"UPDATE {table} SET {change}"))
        with pytest.raises(AssertionError, match="0022 requires"):
            run_alembic(url, "upgrade", "head")
        async with engine.connect() as c:
            assert (
                await c.scalar(sa.text("SELECT version_num FROM alembic_version"))
                == "0021_manual_operational_closure"
            )
            assert not await c.scalar(
                sa.text(
                    "SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='brc_capacity_claims' AND column_name='margin_allocation')"
                )
            )
    finally:
        await engine.dispose()
        await drop_disposable_database(name)


@pytest.mark.asyncio
async def test_old_terminal_claim_is_preserved_without_fabricating_new_allocation():
    from src.trading_kernel.infrastructure.pg_models import (
        capacity_claims,
        trade_tickets,
    )
    from src.trading_kernel.infrastructure.pg_repositories import (
        _capacity_claim_values,
        _ticket_values,
    )
    from tests.trading_kernel.support.capacity_claims import make_issue_request
    from tests.trading_kernel.support.command_dispatch import seed_policy, ticket
    from tests.trading_kernel.support.runtime_scope import seed_ticket_runtime_scope

    name, url = await create_empty_database()
    engine = create_async_engine(url)
    try:
        run_alembic(url, "upgrade", "0021_manual_operational_closure")
        await seed_policy(engine)
        t = ticket()
        await seed_ticket_runtime_scope(engine, t)
        claim = make_issue_request(
            ticket=t, now_ms=1001, claim_owner="historical-fixture"
        ).capacity_claim
        claim_values = _capacity_claim_values(claim)
        claim_values.pop("margin_allocation")
        ticket_values = _ticket_values(claim.to_ticket())
        ticket_values.update(
            status="terminal", terminal_at_ms=2000, active_netting_domain_key=None
        )
        async with engine.begin() as c:
            await c.execute(sa.insert(capacity_claims).values(claim_values))
            await c.execute(sa.insert(trade_tickets).values(ticket_values))
            await c.execute(
                sa.text(
                    "UPDATE brc_owner_policy_current SET new_entry_submit_enabled=false"
                )
            )
            before = await c.scalar(
                sa.text("SELECT row_to_json(c)::text FROM brc_capacity_claims c")
            )
        run_alembic(url, "upgrade", "head")
        async with engine.connect() as c:
            after = await c.scalar(
                sa.text(
                    "SELECT (to_jsonb(c)-'margin_allocation') FROM brc_capacity_claims c"
                )
            )
            import json

            assert after == json.loads(before)
            assert (
                await c.scalar(
                    sa.text("SELECT margin_allocation FROM brc_capacity_claims")
                )
                is None
            )
        async with PostgresKernelUnitOfWork(engine) as u:
            assert await u.capacity_claims.get_for_ticket(t.identity.ticket_id) is None
            historic = await u.capacity_claims.get_historical_terminal(
                claim.capacity_claim_id
            )
            assert historic is not None and historic.ticket_id == t.identity.ticket_id
        async with engine.connect() as c:
            with pytest.raises(
                sa.exc.DBAPIError, match="allocation evidence immutable"
            ):
                await c.execute(
                    sa.text(
                        "UPDATE brc_capacity_claims SET margin_allocation=CAST(:proof AS jsonb)"
                    ),
                    {"proof": claim.margin_allocation.model_dump_json()},
                )
        # A new unversioned insert must fail at the DB boundary, before any FK use.
        async with engine.connect() as c:
            with pytest.raises(sa.exc.DBAPIError, match="requires wallet allocation"):
                await c.execute(sa.insert(capacity_claims).values(claim_values))
    finally:
        await engine.dispose()
        await drop_disposable_database(name)
