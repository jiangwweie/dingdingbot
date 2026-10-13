from __future__ import annotations

import asyncio
import io
import os
import subprocess
import sys
import tarfile

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from src.trading_kernel.infrastructure.pg_models import (
    owner_policy_current,
    owner_policy_events,
    schema_metadata,
    strategy_entry_controls_current,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    RuntimeAuthorityTransitionRefused,
    deploy_compatible_upgrade_identity,
    seed_runtime_authority,
)
from tests.trading_kernel.support.postgres import (
    create_empty_database,
    drop_disposable_database,
    run_alembic,
)

# This historical release contract is exact 0009, not the later function-only head.
CAPACITY_SCHEMA_REVISION = "0009_capacity_policy_v0"


@pytest.fixture
async def issue_engine():
    name, url = await create_empty_database()
    engine = create_async_engine(url)
    try:
        run_alembic(url, "upgrade", CAPACITY_SCHEMA_REVISION)
        yield engine
    finally:
        await engine.dispose()
        await drop_disposable_database(name)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_revision",
    [
        "0007_exit_profile_authority_v1",
        "0008_generic_dynamic_selection_v1",
        CAPACITY_SCHEMA_REVISION,
    ],
)
@pytest.mark.parametrize("source_entry_enabled", [False, True])
async def test_default_release_capacity_is_atomic_idempotent_and_does_not_resume_sor(
    issue_engine, source_revision, source_entry_enabled
) -> None:
    source = RuntimeAuthoritySeedRequest(
        account_id="capacity-release-test",
        runtime_commit="a" * 40,
        schema_revision=source_revision,
        seeded_at_ms=1000,
    )
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        await seed_runtime_authority(uow, source)
    async with issue_engine.begin() as connection:
        if source_entry_enabled:
            await connection.execute(sa.update(owner_policy_current).values(new_entry_submit_enabled=True))
        await connection.execute(
            sa.update(strategy_entry_controls_current)
            .where(strategy_entry_controls_current.c.strategy_group_id == "SOR-001")
            .values(entry_state="paused")
        )
    async with issue_engine.connect() as connection:
        before = (
            (await connection.execute(sa.select(owner_policy_current))).mappings().one()
        )
        controls = tuple(
            (
                await connection.execute(
                    sa.select(strategy_entry_controls_current).order_by(
                        strategy_entry_controls_current.c.strategy_group_id
                    )
                )
            ).mappings()
        )
    assert before["max_same_strategy_side"] is None
    assert before["family_ticket_limits"]["long_continuation"] == 1
    with pytest.raises(DBAPIError, match="Capacity release authority"):
        async with issue_engine.begin() as connection:
            await connection.execute(sa.update(owner_policy_current).values(
                max_same_strategy_side=2,
                family_ticket_limits={"long_continuation": 2, "opening_range": 2, "rally_failure_short": 1},
            ))
    target = source.model_copy(
        update={
            "runtime_commit": "b" * 40,
            "schema_revision": CAPACITY_SCHEMA_REVISION,
            "seeded_at_ms": 2000,
        }
    )
    if source_revision == CAPACITY_SCHEMA_REVISION and source_entry_enabled:
        with pytest.raises(RuntimeAuthorityTransitionRefused, match="Entry fenced"):
            async with PostgresKernelUnitOfWork(issue_engine) as uow:
                await deploy_compatible_upgrade_identity(uow, target)
        return
    with pytest.raises(RuntimeError, match="injected release abort"):
        async with PostgresKernelUnitOfWork(issue_engine) as uow:
            await deploy_compatible_upgrade_identity(uow, target)
            raise RuntimeError("injected release abort")
    async with issue_engine.connect() as connection:
        assert (
            await connection.execute(sa.select(owner_policy_current))
        ).mappings().one() == before
        assert (
            await connection.scalar(
                sa.select(sa.func.count())
                .select_from(owner_policy_events)
                .where(
                    owner_policy_events.c.operation == "compatible_capacity_policy_v0"
                )
            )
            == 0
        )
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        await deploy_compatible_upgrade_identity(uow, target)
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        await deploy_compatible_upgrade_identity(
            uow, target.model_copy(update={"seeded_at_ms": 2001})
        )
    async with issue_engine.connect() as connection:
        after = (
            (await connection.execute(sa.select(owner_policy_current))).mappings().one()
        )
        events = (
            (
                await connection.execute(
                    sa.select(owner_policy_events).where(
                        owner_policy_events.c.operation
                        == "compatible_capacity_policy_v0"
                    )
                )
            )
            .mappings()
            .all()
        )
        assert (
            tuple(
                (
                    await connection.execute(
                        sa.select(strategy_entry_controls_current).order_by(
                            strategy_entry_controls_current.c.strategy_group_id
                        )
                    )
                ).mappings()
            )
            == controls
        )
        assert (
            await connection.scalar(
                sa.select(schema_metadata.c.metadata_value).where(
                    schema_metadata.c.metadata_key == "runtime_commit"
                )
            )
            == target.runtime_commit
        )
    assert after["policy_version"] == before["policy_version"] + 1 + int(source_entry_enabled)
    assert after["max_same_strategy_side"] == 2
    assert after["family_ticket_limits"] == {
        "long_continuation": 2,
        "opening_range": 2,
        "rally_failure_short": 1,
    }
    assert not after["new_entry_submit_enabled"]
    assert len(events) == 1
    assert events[0]["payload"]["target_commit"] == target.runtime_commit
    assert events[0]["payload"]["source_commit"] == source.runtime_commit
    assert events[0]["payload"]["source_schema_revision"] == source_revision
    for name, value in before.items():
        if name not in {
            "policy_version",
            "max_same_strategy_side",
            "family_ticket_limits",
            "updated_at_ms",
            "new_entry_submit_enabled",
        }:
            assert after[name] == value


@pytest.mark.asyncio
@pytest.mark.parametrize("corruption", ["sor_enabled", "risk_changed", "entry_enabled", "time_reversed"])
async def test_default_capacity_release_refuses_invalid_source_without_partial_revision(issue_engine, corruption) -> None:
    source = RuntimeAuthoritySeedRequest(account_id="capacity-release-test", runtime_commit="a" * 40,
        schema_revision=CAPACITY_SCHEMA_REVISION, seeded_at_ms=1000)
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        await seed_runtime_authority(uow, source)
    async with issue_engine.begin() as connection:
        if corruption != "sor_enabled":
            await connection.execute(sa.update(strategy_entry_controls_current)
                .where(strategy_entry_controls_current.c.strategy_group_id == "SOR-001")
                .values(entry_state="paused"))
        if corruption == "risk_changed":
            await connection.execute(sa.update(owner_policy_current).values(max_gross_stop_risk_fraction="0.07"))
        if corruption == "entry_enabled":
            await connection.execute(sa.update(owner_policy_current).values(new_entry_submit_enabled=True))
    async with issue_engine.connect() as connection:
        before = (await connection.execute(sa.select(owner_policy_current))).mappings().one()
    target = source.model_copy(update={"runtime_commit": "b" * 40,
        "seeded_at_ms": 999 if corruption == "time_reversed" else 2000})
    with pytest.raises(RuntimeAuthorityTransitionRefused):
        async with PostgresKernelUnitOfWork(issue_engine) as uow:
            await deploy_compatible_upgrade_identity(uow, target)
    async with issue_engine.connect() as connection:
        assert (await connection.execute(sa.select(owner_policy_current))).mappings().one() == before
        assert await connection.scalar(sa.select(sa.func.count()).select_from(owner_policy_events)
            .where(owner_policy_events.c.operation == "compatible_capacity_policy_v0")) == 0
        assert await connection.scalar(sa.select(schema_metadata.c.metadata_value)
            .where(schema_metadata.c.metadata_key == "runtime_commit")) == source.runtime_commit


@pytest.mark.asyncio
async def test_0009_preserves_exact_frozen_0008_policy_until_release(tmp_path) -> None:
    name, url = await create_empty_database()
    engine = create_async_engine(url)
    try:
        run_alembic(url, "upgrade", "0008_generic_dynamic_selection_v1")
        archive = await asyncio.to_thread(subprocess.run, ["git", "archive", "9589d0c99ab09da3848fb5b92c0b1c08b2ba10d9", "src"],
            capture_output=True, check=True, timeout=20)
        with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as bundle:
            bundle.extractall(tmp_path, filter="data")
        code = """
import asyncio, os
from sqlalchemy.ext.asyncio import create_async_engine
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import seed_runtime_authority, RuntimeAuthoritySeedRequest
from src.trading_kernel.application.owner_control import set_strategy_entry_state, ControlMutationRequest
from src.trading_kernel.domain.owner_control import StrategyEntryState
async def main():
    engine=create_async_engine(os.environ['TRADING_KERNEL_DATABASE_URL'])
    try:
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(uow, RuntimeAuthoritySeedRequest(account_id='capacity-release-test',
                runtime_commit='a'*40, schema_revision='0008_generic_dynamic_selection_v1', seeded_at_ms=1000))
            await set_strategy_entry_state(uow, strategy_group_id='SOR-001', target_state=StrategyEntryState.PAUSED,
                authentication_strength='totp_step_up', request=ControlMutationRequest(expected_version=1,
                reason='owner_retired_sor', idempotency_key='capacity:retire-sor', owner_identity='owner', now_ms=1010))
    finally: await engine.dispose()
asyncio.run(main())
"""
        result = await asyncio.to_thread(subprocess.run, [sys.executable, "-c", code],
            cwd=tmp_path, env={**os.environ, "PYTHONPATH": str(tmp_path), "TRADING_KERNEL_DATABASE_URL": url},
            capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr[-3000:]
        async with engine.connect() as connection:
            inventory = await connection.run_sync(lambda sync: {
                table: [col["name"] for col in sa.inspect(sync).get_columns(table)]
                for table in sa.inspect(sync).get_table_names() if table != "alembic_version"})
            before = {}
            for table, columns in inventory.items():
                statement = sa.text('SELECT '+','.join('"'+col+'"' for col in columns)+' FROM "'+table+'"')
                before[table] = tuple((await connection.execute(statement)).all())
        run_alembic(url, "upgrade", CAPACITY_SCHEMA_REVISION)
        async with engine.connect() as connection:
            for table, columns in inventory.items():
                statement = sa.text('SELECT '+','.join('"'+col+'"' for col in columns)+' FROM "'+table+'"')
                assert tuple((await connection.execute(statement)).all()) == before[table], table
            policy = (await connection.execute(sa.select(owner_policy_current))).mappings().one()
            assert policy["max_same_strategy_side"] is None
            assert policy["family_ticket_limits"]["long_continuation"] == 1
        async with PostgresKernelUnitOfWork(engine) as uow:
            await deploy_compatible_upgrade_identity(uow, RuntimeAuthoritySeedRequest(
                account_id="capacity-release-test", runtime_commit="b"*40,
                schema_revision=CAPACITY_SCHEMA_REVISION, seeded_at_ms=2000))
        async with engine.connect() as connection:
            policy = (await connection.execute(sa.select(owner_policy_current))).mappings().one()
            assert policy["max_same_strategy_side"] == 2
            assert policy["family_ticket_limits"]["long_continuation"] == 2
    finally:
        await engine.dispose()
        await drop_disposable_database(name)
