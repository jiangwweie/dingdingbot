"""Canonical fresh schema/seed remains account-isolated and incapable of ENTRY."""

from __future__ import annotations

import asyncio

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from tests.trading_kernel.support.postgres import (
    create_empty_database,
    drop_disposable_database,
    run_alembic,
)


@pytest.mark.asyncio
async def test_manual_initial_database_can_be_installed_empty_and_seeded_paused():
    name, url = await create_empty_database()
    engine = create_async_engine(url)
    try:
        await asyncio.to_thread(run_alembic, url, "upgrade", "head")
        async with engine.connect() as c:
            await c.execute(sa.text("SET TRANSACTION READ ONLY"))
            assert (
                await c.scalar(sa.text("SELECT count(*) FROM brc_runtime_profiles"))
                == 0
            )
            assert (
                await c.scalar(sa.text("SELECT count(*) FROM brc_owner_policy_current"))
                == 0
            )
        async with PostgresKernelUnitOfWork(engine) as u:
            request = RuntimeAuthoritySeedRequest(
                account_id="manual-test-independent",
                runtime_commit="a" * 40,
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=1000,
            )
            await seed_runtime_authority(u, request)
        async with engine.connect() as c:
            await c.execute(sa.text("SET TRANSACTION READ ONLY"))
            await c.execute(sa.text("SET LOCAL statement_timeout='5s'"))
            assert (
                await c.scalar(
                    sa.text(
                        "SELECT account_id FROM brc_runtime_profiles WHERE runtime_profile_id='tiny-live-v1'"
                    )
                )
                == "manual-test-independent"
            )
            assert (
                await c.scalar(
                    sa.text(
                        "SELECT new_entry_submit_enabled FROM brc_owner_policy_current"
                    )
                )
                is False
            )
            assert (
                await c.scalar(
                    sa.text(
                        "SELECT enabled FROM brc_runtime_capabilities_current WHERE capability_key='exchange_commands'"
                    )
                )
                is False
            )
            assert (
                await c.scalar(
                    sa.text(
                        "SELECT count(*) FROM brc_runtime_capabilities_current WHERE certification->>'product_id'='brc-app-manual-v1'"
                    )
                )
                == 2
            )
            assert (
                await c.scalar(sa.text("SELECT count(*) FROM brc_trade_tickets")) == 0
            )
            assert (
                await c.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands"))
                == 0
            )
    finally:
        await engine.dispose()
        await drop_disposable_database(name)
