from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    ArmAcceptancePolicyRequest,
    RuntimeAuthoritySeedRequest,
    arm_acceptance_policy,
    seed_runtime_authority,
)
from tests.trading_kernel.support.postgres import TEST_POSTGRES_ADMIN_DSN

REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCE_REVISION = "0006_sor_dynamic_selection_v0"
TARGET_REVISION = "0007_exit_profile_authority_v1"
NEW_TABLES = {
    "brc_event_exit_profile_bindings",
    "brc_event_exit_profile_binding_current",
    "brc_event_exit_profile_binding_events",
}


@pytest.mark.asyncio
async def test_flat_0006_upgrade_adds_exit_profile_authority_without_runtime_work() -> None:
    database_name, database_url = await _create_database()
    engine = create_async_engine(database_url)
    try:
        source = _run_alembic(database_url, "upgrade", SOURCE_REVISION)
        assert source.returncode == 0, (
            source.stdout[-4000:] + source.stderr[-4000:]
        )
        async with engine.connect() as connection:
            legacy_profiles = tuple(
                (
                    await connection.execute(
                        sa.text(
                            "SELECT exit_policy_id, event_spec_id, semantic_hash "
                            "FROM brc_exit_policies ORDER BY exit_policy_id"
                        )
                    )
                ).all()
            )

        target = _run_alembic(database_url, "upgrade", TARGET_REVISION)
        assert target.returncode == 0, target.stderr[-4000:]

        async with engine.connect() as connection:
            revision = await connection.scalar(
                sa.text("SELECT version_num FROM alembic_version")
            )
            tables = await connection.run_sync(
                lambda sync: set(sa.inspect(sync).get_table_names())
            )
            profile_columns = {
                column["name"]
                for column in await connection.run_sync(
                    lambda sync: sa.inspect(sync).get_columns("brc_exit_policies")
                )
            }
            claim_columns = {
                column["name"]
                for column in await connection.run_sync(
                    lambda sync: sa.inspect(sync).get_columns("brc_capacity_claims")
                )
            }
            ticket_columns = {
                column["name"]
                for column in await connection.run_sync(
                    lambda sync: sa.inspect(sync).get_columns("brc_trade_tickets")
                )
            }
            runtime_counts = {
                table: int(
                    await connection.scalar(sa.text(f"SELECT count(*) FROM {table}"))
                    or 0
                )
                for table in (
                    *sorted(NEW_TABLES),
                    "brc_trade_tickets",
                    "brc_exchange_commands",
                    "brc_positions_current",
                    "brc_runtime_incidents",
                )
            }
            preserved_profiles = tuple(
                (
                    await connection.execute(
                        sa.text(
                            "SELECT exit_policy_id, event_spec_id, semantic_hash "
                            "FROM brc_exit_policies ORDER BY exit_policy_id"
                        )
                    )
                ).all()
            )
            lineage_constraints = {
                str(row.conname): str(row.definition)
                for row in (
                    await connection.execute(
                        sa.text(
                            """
                            SELECT conname, pg_get_constraintdef(oid) AS definition
                            FROM pg_constraint
                            WHERE conrelid IN (
                                'brc_capacity_claims'::regclass,
                                'brc_trade_tickets'::regclass
                            )
                              AND (
                                conname LIKE '%exit_binding_lineage_shape_valid'
                                OR conname LIKE 'fk_%_exit_binding'
                              )
                            ORDER BY conname
                            """
                        )
                    )
                ).all()
            }

        assert revision == TARGET_REVISION
        assert NEW_TABLES <= tables
        assert "profile_schema_version" in profile_columns
        expected_lineage = {
            "exit_binding_id",
            "exit_binding_semantic_hash",
            "exit_binding_authority_version",
        }
        assert expected_lineage <= claim_columns
        assert expected_lineage <= ticket_columns
        assert all(value == 0 for value in runtime_counts.values())
        assert preserved_profiles == legacy_profiles
        assert sum("exit_binding_lineage_shape_valid" in name for name in lineage_constraints) == 2
        assert sum("MATCH FULL" in value for value in lineage_constraints.values()) == 2

        downgrade = _run_alembic(database_url, "downgrade", SOURCE_REVISION)
        assert downgrade.returncode != 0
        assert "fix-forward only" in downgrade.stderr
    finally:
        await engine.dispose()
        await _drop_database(database_name)


@pytest.mark.asyncio
async def test_exit_profile_constraints_reject_hash_drift_and_duplicate_lifecycle() -> None:
    database_name, database_url = await _create_database()
    engine = create_async_engine(database_url)
    try:
        result = _run_alembic(database_url, "upgrade", TARGET_REVISION)
        assert result.returncode == 0, result.stderr[-4000:]
        profile_hash = "sha256:" + "a" * 64
        binding_hash = "sha256:" + "b" * 64
        event_spec_id = "event_spec:exit-profile-test:v1"
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    """
                    INSERT INTO brc_event_specs (
                        event_spec_id, strategy_version_id, event_id,
                        position_side, timeframe, freshness_window_ms,
                        event_time_authority, entry_order_type,
                        protection_reference_fact_definition_id,
                        exit_policy_id, execution_semantics, status, created_at_ms
                    ) VALUES (
                        :event_spec_id, 'strategy-version:test', 'EXIT-TEST',
                        'long', '1h', 3600000, 'closed_bar', 'market',
                        'fact:test', 'legacy-exit-policy:test', '{}'::jsonb,
                        'active', 1000
                    )
                    """
                ),
                {"event_spec_id": event_spec_id},
            )
            await connection.execute(
                sa.text(
                    """
                    INSERT INTO brc_exit_policies (
                        exit_policy_id, exit_policy_version, event_spec_id,
                        position_side, policy, semantic_hash, status,
                        created_at_ms, profile_schema_version
                    ) VALUES (
                        'exit-profile:test:v1', '1', NULL, 'long', '{}'::jsonb,
                        :profile_hash, 'active', 1000, 'exit_profile_v1'
                    )
                    """
                ),
                {"profile_hash": profile_hash},
            )
            await connection.execute(
                sa.text(
                    """
                    INSERT INTO brc_event_exit_profile_bindings (
                        exit_binding_id, binding_version, event_spec_id,
                        exit_profile_id, exit_profile_semantic_hash,
                        binding_semantic_hash, activation_reason, created_at_ms
                    ) VALUES (
                        'exit-binding:test:v1', 1, :event_spec_id,
                        'exit-profile:test:v1', :profile_hash,
                        :binding_hash, 'test', 1000
                    )
                    """
                ),
                {
                    "event_spec_id": event_spec_id,
                    "profile_hash": profile_hash,
                    "binding_hash": binding_hash,
                },
            )
            await connection.execute(
                sa.text(
                    """
                    INSERT INTO brc_event_exit_profile_binding_events (
                        binding_event_id, event_spec_id, exit_binding_id,
                        binding_version, operation, authorization_source,
                        owner_authorization_id, reason, created_at_ms
                    ) VALUES (
                        'binding-event:test:activated', :event_spec_id,
                        'exit-binding:test:v1', 1, 'ACTIVATED',
                        'system_migration', NULL, 'test', 1000
                    )
                    """
                ),
                {"event_spec_id": event_spec_id},
            )

        with pytest.raises(DBAPIError):
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "UPDATE brc_exit_policies "
                        "SET policy=CAST(:changed AS jsonb) "
                        "WHERE exit_policy_id='exit-profile:test:v1'"
                    ),
                    {"changed": '{"changed":true}'},
                )
        with pytest.raises(DBAPIError):
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "UPDATE brc_event_exit_profile_bindings "
                        "SET activation_reason='changed' "
                        "WHERE exit_binding_id='exit-binding:test:v1'"
                    )
                )
        with pytest.raises(DBAPIError):
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        """
                        INSERT INTO brc_event_exit_profile_binding_events (
                            binding_event_id, event_spec_id, exit_binding_id,
                            binding_version, operation, authorization_source,
                            owner_authorization_id, reason, created_at_ms
                        ) SELECT
                            'binding-event:test:activated-duplicate', event_spec_id,
                            exit_binding_id, binding_version, 'ACTIVATED',
                            'system_migration', NULL, 'duplicate', 2000
                        FROM brc_event_exit_profile_bindings
                        WHERE exit_binding_id='exit-binding:test:v1'
                        """
                    )
                )
    finally:
        await engine.dispose()
        await _drop_database(database_name)


@pytest.mark.asyncio
async def test_nonflat_0006_source_is_rejected_before_exit_profile_schema_change() -> None:
    database_name, database_url = await _create_database()
    engine = create_async_engine(database_url)
    try:
        source = _run_alembic(database_url, "upgrade", SOURCE_REVISION)
        assert source.returncode == 0, (
            source.stdout[-4000:] + source.stderr[-4000:]
        )
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    """
                    INSERT INTO brc_runtime_incidents (
                        incident_id, ticket_id, incident_kind, status,
                        first_blocker, entry_block_scope, entry_block_key,
                        details, opened_at_ms, resolved_at_ms
                    ) VALUES (
                        'incident:exit-profile-migration', NULL, 'migration_test',
                        'open', 'migration_test', 'runtime', 'global',
                        '{}'::jsonb, 1000, NULL
                    )
                    """
                )
            )

        target = _run_alembic(database_url, "upgrade", TARGET_REVISION)
        assert target.returncode != 0
        assert "requires exact flat source" in target.stderr
        async with engine.connect() as connection:
            revision = await connection.scalar(
                sa.text("SELECT version_num FROM alembic_version")
            )
            tables = await connection.run_sync(
                lambda sync: set(sa.inspect(sync).get_table_names())
            )
        assert revision == SOURCE_REVISION
        assert NEW_TABLES.isdisjoint(tables)
    finally:
        await engine.dispose()
        await _drop_database(database_name)


@pytest.mark.asyncio
async def test_real_0006_to_0007_source_verification_preservation_and_identity_path() -> None:
    database_name, database_url = await _create_database()
    engine = create_async_engine(database_url)
    try:
        result = _run_alembic(database_url, "upgrade", "0005_tradfi_instrument_center")
        assert result.returncode == 0, result.stderr[-4000:]
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id="exit-profile-deployment-path",
                    runtime_commit="5" * 40,
                    schema_revision="0005_tradfi_instrument_center",
                    seeded_at_ms=1_800_000_000_000,
                ),
            )
        async with PostgresKernelUnitOfWork(engine) as uow:
            await arm_acceptance_policy(
                uow,
                ArmAcceptancePolicyRequest(armed_at_ms=1_800_000_000_100),
            )
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "UPDATE brc_runtime_capabilities_current "
                    "SET enabled = true "
                    "WHERE capability_key = 'exchange_commands'"
                )
            )
            await connection.execute(
                sa.text(
                    "UPDATE brc_owner_policy_current SET policy_version = 4 "
                    "WHERE owner_policy_id = 'policy-main'"
                )
            )
            await _seed_static_sor_pair(connection)

        result = _run_alembic(database_url, "upgrade", SOURCE_REVISION)
        assert result.returncode == 0, result.stderr[-4000:]

        upgraded_0006 = _run_seed_runtime_authority(
            database_url,
            action="deploy-compatible-identity",
            runtime_commit="6" * 40,
            schema_revision=SOURCE_REVISION,
            now_ms=1_800_000_000_200,
        )
        assert upgraded_0006.returncode == 0, upgraded_0006.stderr[-4000:]

        source = _run_verify_schema(
            database_url,
            "--compatible-source-revision",
            SOURCE_REVISION,
        )
        source_payload = json.loads(source.stdout)
        assert source.returncode == 0, {
            key: source_payload[key]
            for key in (
                "status",
                "source_shape",
                "migration_gate",
                "runtime_identity",
                "registry_identity",
                "owner_policy",
                "runtime_profile",
                "strategy_controls",
                "capabilities",
                "account_mode",
            )
        }
        assert source_payload["status"] == "pass", source_payload
        preservation_digest = str(source_payload["preservation_manifest"]["digest"])
        source_tables = {
            str(entry["table"])
            for entry in source_payload["preservation_manifest"]["tables"]
        }
        assert {
            "brc_instrument_selection_specs",
            "brc_sor_dynamic_selection_specs_v0",
            "brc_strategy_selection_control_current",
            "brc_strategy_selection_rollback_baselines",
            "brc_runtime_release_compatibility_facts",
            "brc_strategy_universe_current",
        } <= source_tables

        result = _run_alembic(database_url, "upgrade", TARGET_REVISION)
        assert result.returncode == 0, result.stderr[-4000:]

        preserved = _run_verify_schema(
            database_url,
            "--preserve-source-revision",
            SOURCE_REVISION,
            "--expected-preservation-digest",
            preservation_digest,
        )
        assert preserved.returncode == 0, preserved.stderr[-4000:]
        assert json.loads(preserved.stdout)["status"] == "pass"

        upgraded_0007 = _run_seed_runtime_authority(
            database_url,
            action="deploy-compatible-identity",
            runtime_commit="7" * 40,
            schema_revision=TARGET_REVISION,
            now_ms=1_800_000_000_300,
        )
        assert upgraded_0007.returncode == 0, upgraded_0007.stderr[-4000:]

        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "UPDATE brc_strategy_selection_control_current "
                    "SET control_version = control_version + 1 "
                    "WHERE strategy_group_id = 'SOR-001'"
                )
            )
        tampered = _run_verify_schema(
            database_url,
            "--preserve-source-revision",
            SOURCE_REVISION,
            "--expected-preservation-digest",
            preservation_digest,
        )
        assert tampered.returncode != 0
        assert json.loads(tampered.stdout)["status"] == "fail"
    finally:
        await engine.dispose()
        await _drop_database(database_name)


async def _create_database() -> tuple[str, str]:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    admin = await asyncpg.connect(TEST_POSTGRES_ADMIN_DSN)
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
    finally:
        await admin.close()
    base = TEST_POSTGRES_ADMIN_DSN.rsplit("/", 1)[0]
    return database_name, (
        f"{base.replace('postgresql://', 'postgresql+asyncpg://', 1)}/{database_name}"
    )


async def _drop_database(database_name: str) -> None:
    admin = await asyncpg.connect(TEST_POSTGRES_ADMIN_DSN)
    try:
        with suppress(asyncpg.UndefinedObjectError):
            await admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = $1 AND pid <> pg_backend_pid()",
                database_name,
            )
        await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
    finally:
        await admin.close()


def _run_alembic(
    database_url: str,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "migrations/trading_kernel/alembic.ini",
            *arguments,
        ),
        cwd=REPO_ROOT,
        env=os.environ | {"TRADING_KERNEL_DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        check=False,
    )


def _run_verify_schema(
    database_url: str,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (
            sys.executable,
            "scripts/trading_kernel/verify_schema.py",
            "--database-url",
            database_url,
            *arguments,
        ),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_seed_runtime_authority(
    database_url: str,
    *,
    action: str,
    runtime_commit: str,
    schema_revision: str,
    now_ms: int,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (
            sys.executable,
            "scripts/trading_kernel/seed_runtime_authority.py",
            "--database-url",
            database_url,
            action,
            "--account-id",
            "exit-profile-deployment-path",
            "--runtime-commit",
            runtime_commit,
            "--schema-revision",
            schema_revision,
            "--now-ms",
            str(now_ms),
        ),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


async def _seed_static_sor_pair(connection) -> None:
    digest = "sha256:" + "a" * 64
    await connection.execute(
        sa.text(
            """
            INSERT INTO brc_strategy_universe_versions (
                universe_version_id, strategy_group_id, event_spec_id,
                universe_version, semantic_digest, lifecycle_state,
                installed_at_ms, activated_at_ms, retired_at_ms,
                abandoned_at_ms, abandon_reason_code
            ) VALUES
                ('universe:static:long', 'SOR-001',
                 'event_spec:SOR-001:SOR-LONG:v4', 1, :digest,
                 'active', 1000, 1100, NULL, NULL, NULL),
                ('universe:static:short', 'SOR-001',
                 'event_spec:SOR-001:SOR-SHORT:v4', 1, :digest,
                 'active', 1000, 1100, NULL, NULL, NULL)
            """
        ),
        {"digest": digest},
    )
    await connection.execute(
        sa.text(
            """
            INSERT INTO brc_strategy_universe_current (
                event_spec_id, universe_version_id, semantic_digest,
                lifecycle_state, activation_generation, activated_at_ms
            ) VALUES
                ('event_spec:SOR-001:SOR-LONG:v4',
                 'universe:static:long', :digest, 'active', 1, 1100),
                ('event_spec:SOR-001:SOR-SHORT:v4',
                 'universe:static:short', :digest, 'active', 1, 1100)
            """
        ),
        {"digest": digest},
    )
