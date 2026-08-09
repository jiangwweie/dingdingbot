from __future__ import annotations

import os
import re
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from scripts.trading_kernel.verify_schema import (
    _verify_compatible_source,
    _verify_preservation,
)
from src.trading_kernel.application.owner_control import (
    ControlMutationRequest,
    OwnerControlConflict,
    preview_flatten_all,
    set_global_entry_state,
    set_strategy_entry_state,
)
from src.trading_kernel.domain.owner_control import StrategyEntryState
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    OWNER_POLICY_ID,
    ArmAcceptancePolicyRequest,
    RuntimeAuthoritySeedRequest,
    arm_acceptance_policy,
    deploy_compatible_upgrade_identity,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION

REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_DSN = os.getenv(
    "BRC_TEST_POSTGRES_ADMIN_URL",
    "postgresql://dingdingbot:dingdingbot_dev@127.0.0.1:5432/postgres",
)
SAFE_DATABASE = re.compile(r"^brc_kernel_test_[a-f0-9]{12}$")


@pytest.mark.asyncio
async def test_strategy_and_global_pause_commit_without_exchange_authority() -> None:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    admin = await asyncpg.connect(ADMIN_DSN)
    assert SAFE_DATABASE.fullmatch(database_name)
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        database_url = _database_url(database_name)
        result = subprocess.run(  # noqa: ASYNC221 - isolated migration subprocess
            (
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "migrations/trading_kernel/alembic.ini",
                "upgrade",
                "head",
            ),
            cwd=REPO_ROOT,
            env=os.environ | {"TRADING_KERNEL_DATABASE_URL": database_url},
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        engine = create_async_engine(database_url)
        try:
            async with PostgresKernelUnitOfWork(engine) as uow:
                await seed_runtime_authority(
                    uow,
                    RuntimeAuthoritySeedRequest(
                        account_id="owner-account",
                        runtime_commit="a" * 40,
                        schema_revision=CURRENT_SCHEMA_REVISION,
                        seeded_at_ms=1_799_999_999_000,
                    ),
                )
            async with PostgresKernelUnitOfWork(engine) as uow:
                paused = await set_strategy_entry_state(
                    uow,
                    strategy_group_id="SOR-001",
                    target_state=StrategyEntryState.PAUSED,
                    request=ControlMutationRequest(
                        expected_version=1,
                        reason="owner_manual_pause",
                        idempotency_key="owner-request:test-sor-pause",
                        owner_identity="owner",
                        now_ms=1_800_000_000_000,
                    ),
                    authentication_strength="session",
                )
                assert paused.entry_state is StrategyEntryState.PAUSED

            async with PostgresKernelUnitOfWork(engine) as uow:
                policy = await uow.entry_admission.get_owner_policy(OWNER_POLICY_ID)
                assert policy is not None
                with pytest.raises(OwnerControlConflict, match="idempotency_key_conflict"):
                    await set_global_entry_state(
                        uow,
                        owner_policy_id=OWNER_POLICY_ID,
                        enabled=False,
                        request=ControlMutationRequest(
                            expected_version=policy.policy_version,
                            reason="owner_manual_pause",
                            idempotency_key="owner-request:test-sor-pause",
                            owner_identity="owner",
                            now_ms=1_800_000_000_050,
                        ),
                        authentication_strength="session",
                    )

            async with PostgresKernelUnitOfWork(engine) as uow:
                policy = await uow.entry_admission.get_owner_policy(OWNER_POLICY_ID)
                assert policy is not None
                paused_policy = await set_global_entry_state(
                    uow,
                    owner_policy_id=OWNER_POLICY_ID,
                    enabled=False,
                    request=ControlMutationRequest(
                        expected_version=policy.policy_version,
                        reason="owner_manual_pause",
                        idempotency_key="owner-request:test-entry-pause",
                        owner_identity="owner",
                        now_ms=1_800_000_000_100,
                    ),
                    authentication_strength="session",
                )
                assert not paused_policy.new_entry_submit_enabled

            async with PostgresKernelUnitOfWork(engine) as uow:
                preview = await preview_flatten_all(
                    uow,
                    owner_policy_id=OWNER_POLICY_ID,
                    runtime_profile_id="tiny-live-v1",
                    venue_id="binance-usdm",
                    account_id="owner-account",
                )
                assert preview.ticket_ids == ()
                assert not preview.global_entry_enabled
        finally:
            await engine.dispose()
    finally:
        with suppress(asyncpg.UndefinedObjectError):
            await admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = $1 AND pid <> pg_backend_pid()",
                database_name,
            )
            await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await admin.close()


@pytest.mark.asyncio
async def test_flat_0003_upgrade_seeds_controls_and_pauses_entry() -> None:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    admin = await asyncpg.connect(ADMIN_DSN)
    assert SAFE_DATABASE.fullmatch(database_name)
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        database_url = _database_url(database_name)
        _run_alembic(database_url, "0003_portfolio_admission_observability")
        engine = create_async_engine(database_url)
        try:
            async with PostgresKernelUnitOfWork(engine) as uow:
                await seed_runtime_authority(
                    uow,
                    RuntimeAuthoritySeedRequest.model_construct(
                        account_id="owner-account",
                        runtime_commit="b" * 40,
                        schema_revision="0003_portfolio_admission_observability",
                        seeded_at_ms=1_800_000_000_000,
                    ),
                )
            async with PostgresKernelUnitOfWork(engine) as uow:
                armed = await arm_acceptance_policy(
                    uow,
                    ArmAcceptancePolicyRequest(armed_at_ms=1_800_000_000_100),
                )
                assert armed.new_entry_submit_enabled
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "UPDATE brc_owner_policy_current SET policy_version = 5 "
                        "WHERE owner_policy_id = 'policy-main'"
                    )
                )
        finally:
            await engine.dispose()

        source = await _verify_compatible_source(
            database_url,
            "0003_portfolio_admission_observability",
        )
        assert source["status"] == "pass", source
        manifest = source["preservation_manifest"]
        assert isinstance(manifest, dict)
        preservation_digest = str(manifest["digest"])
        _run_alembic(database_url, "head")
        preserved = await _verify_preservation(
            database_url,
            source_revision="0003_portfolio_admission_observability",
            expected_digest=preservation_digest,
        )
        assert preserved["status"] == "pass", preserved
        engine = create_async_engine(database_url)
        try:
            async with PostgresKernelUnitOfWork(engine) as uow:
                deployed = await deploy_compatible_upgrade_identity(
                    uow,
                    RuntimeAuthoritySeedRequest(
                        account_id="owner-account",
                        runtime_commit="c" * 40,
                        schema_revision=CURRENT_SCHEMA_REVISION,
                        seeded_at_ms=1_800_000_000_200,
                    ),
                )
                assert deployed.schema_revision == CURRENT_SCHEMA_REVISION
            async with PostgresKernelUnitOfWork(engine) as uow:
                policy = await uow.entry_admission.get_owner_policy(OWNER_POLICY_ID)
                controls = await uow.owner_controls.list_strategy_controls()
                assert policy is not None
                assert not policy.new_entry_submit_enabled
                assert len(controls) == 5
        finally:
            await engine.dispose()
    finally:
        with suppress(asyncpg.UndefinedObjectError):
            await admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = $1 AND pid <> pg_backend_pid()",
                database_name,
            )
            await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await admin.close()


def _run_alembic(database_url: str, revision: str) -> None:
    result = subprocess.run(
        (
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "migrations/trading_kernel/alembic.ini",
            "upgrade",
            revision,
        ),
        cwd=REPO_ROOT,
        env=os.environ | {"TRADING_KERNEL_DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def _database_url(database_name: str) -> str:
    base = ADMIN_DSN.rsplit("/", 1)[0]
    return f"{base.replace('postgresql://', 'postgresql+asyncpg://', 1)}/{database_name}"
