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

from scripts.trading_kernel.verify_schema import (
    _verify_compatible_source,
    _verify_preservation,
)
from src.trading_kernel.domain.product import InstrumentProductProfile
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    ArmAcceptancePolicyRequest,
    RuntimeAuthoritySeedRequest,
    arm_acceptance_policy,
    seed_runtime_authority,
)
from tests.trading_kernel.support.postgres import TEST_POSTGRES_ADMIN_DSN

REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCE_REVISION = "0005_tradfi_instrument_center"
TARGET_REVISION = "0006_sor_dynamic_selection_v0"
NEW_TABLES = {
    "brc_instrument_selection_specs",
    "brc_sor_dynamic_selection_specs_v0",
    "brc_instrument_selection_spec_events",
    "brc_instrument_selection_spec_members",
    "brc_strategy_selection_control_current",
    "brc_strategy_selection_rollback_baselines",
    "brc_instrument_selection_jobs_current",
    "brc_instrument_selection_attempts",
    "brc_instrument_selection_snapshots",
    "brc_instrument_selection_member_decisions",
    "brc_strategy_universe_materialization_generations",
    "brc_strategy_universe_materialization_targets",
    "brc_strategy_universe_materialization_events",
    "brc_selection_session_authorities",
    "brc_selection_authority_current",
    "brc_strategy_entry_vacuums_current",
    "brc_strategy_entry_vacuum_events",
    "brc_selection_authority_gap_audits_current",
    "brc_selection_authority_gap_audit_events",
    "brc_strategy_trigger_suppressions",
    "brc_runtime_release_compatibility_facts",
}


@pytest.mark.asyncio
async def test_empty_and_flat_0005_upgrade_create_schema_without_runtime_side_effects() -> None:
    database_name, database_url = await _create_database()
    engine = create_async_engine(database_url)
    try:
        result = _run_alembic(database_url, "upgrade", SOURCE_REVISION)
        assert result.returncode == 0, result.stderr[-4000:]
        result = _run_alembic(database_url, "upgrade", TARGET_REVISION)
        assert result.returncode == 0, result.stderr[-4000:]

        async with engine.connect() as connection:
            revision = await connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
            tables = await connection.run_sync(
                lambda sync: set(sa.inspect(sync).get_table_names())
            )
            columns = await connection.run_sync(
                lambda sync: {
                    table: {column["name"] for column in sa.inspect(sync).get_columns(table)}
                    for table in (
                        "brc_signal_events",
                        "brc_capacity_claims",
                        "brc_admission_decisions",
                        "brc_trade_tickets",
                        "brc_strategy_universe_versions",
                    )
                }
            )
            counts = {
                table: int(
                    await connection.scalar(sa.text(f"SELECT count(*) FROM {table}"))
                    or 0
                )
                for table in (
                    "brc_instrument_selection_snapshots",
                    "brc_strategy_universe_materialization_generations",
                    "brc_selection_session_authorities",
                    "brc_strategy_entry_vacuums_current",
                    "brc_exchange_commands",
                )
            }
            staged_scope_constraint = await connection.scalar(
                sa.text(
                    "SELECT pg_get_constraintdef(oid) "
                    "FROM pg_constraint "
                    "WHERE conname = "
                    "'ck_brc_runtime_scopes_current_lifecycle_permissions_valid'"
                )
            )

        assert revision == TARGET_REVISION
        assert NEW_TABLES <= tables
        for table in (
            "brc_signal_events",
            "brc_capacity_claims",
            "brc_admission_decisions",
            "brc_trade_tickets",
        ):
            assert "selection_authority_id" in columns[table]
        assert {
            "source_kind",
            "materialization_generation_id",
        } <= columns["brc_strategy_universe_versions"]
        assert counts == {table: 0 for table in counts}
        assert staged_scope_constraint is not None
        assert "staged" in staged_scope_constraint

        result = _run_alembic(database_url, "downgrade", SOURCE_REVISION)
        assert result.returncode != 0
        assert "fix-forward" in result.stderr
    finally:
        await engine.dispose()
        await _drop_database(database_name)


@pytest.mark.asyncio
async def test_nonflat_0005_source_is_rejected_before_schema_change() -> None:
    database_name, database_url = await _create_database()
    engine = create_async_engine(database_url)
    try:
        result = _run_alembic(database_url, "upgrade", SOURCE_REVISION)
        assert result.returncode == 0, result.stderr[-4000:]
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    """
                    INSERT INTO brc_runtime_incidents (
                        incident_id, ticket_id, incident_kind, status, first_blocker,
                        entry_block_scope, entry_block_key, details, opened_at_ms,
                        resolved_at_ms
                    ) VALUES (
                        'incident:0006-blocker', NULL, 'migration_test', 'open',
                        'migration_test', 'runtime', 'global', '{}'::jsonb, 1000, NULL
                    )
                    """
                )
            )

        result = _run_alembic(database_url, "upgrade", TARGET_REVISION)
        assert result.returncode != 0
        assert "0006 migration requires exact flat source" in result.stderr
        async with engine.connect() as connection:
            revision = await connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
            tables = await connection.run_sync(
                lambda sync: set(sa.inspect(sync).get_table_names())
            )
        assert revision == SOURCE_REVISION
        assert NEW_TABLES.isdisjoint(tables)
    finally:
        await engine.dispose()
        await _drop_database(database_name)


@pytest.mark.asyncio
async def test_production_shaped_0005_upgrade_preserves_static_pair_and_seeds_no_runtime_work() -> None:
    database_name, database_url = await _create_database()
    engine = create_async_engine(database_url)
    try:
        result = _run_alembic(database_url, "upgrade", SOURCE_REVISION)
        assert result.returncode == 0, result.stderr[-4000:]
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id="selection-migration-test",
                    runtime_commit="5" * 40,
                    schema_revision=SOURCE_REVISION,
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
                    "UPDATE brc_owner_policy_current SET policy_version = 4 "
                    "WHERE owner_policy_id = 'policy-main'"
                )
            )
            await _seed_static_sor_pair(connection)

        source = await _verify_compatible_source(database_url, SOURCE_REVISION)
        assert source["status"] == "pass", json.dumps(source, default=str)
        preservation_digest = str(source["preservation_manifest"]["digest"])
        result = _run_alembic(database_url, "upgrade", TARGET_REVISION)
        assert result.returncode == 0, result.stderr[-4000:]
        preserved = await _verify_preservation(
            database_url,
            source_revision=SOURCE_REVISION,
            expected_digest=preservation_digest,
        )
        assert preserved["status"] == "pass", preserved

        async with engine.connect() as connection:
            revision = await connection.scalar(
                sa.text("SELECT version_num FROM alembic_version")
            )
            selection_spec = (
                await connection.execute(
                    sa.text(
                        "SELECT selection_spec_id, algorithm_semantic_digest "
                        "FROM brc_instrument_selection_specs"
                    )
                )
            ).one()
            feature_numeric_types = {
                str(row.column_name): (
                    row.numeric_precision,
                    row.numeric_scale,
                )
                for row in (
                    await connection.execute(
                        sa.text(
                            "SELECT column_name, numeric_precision, numeric_scale "
                            "FROM information_schema.columns "
                            "WHERE table_schema = current_schema() "
                            "AND table_name = "
                            "'brc_instrument_selection_member_decisions' "
                            "AND column_name IN ("
                            "'or_high', 'or_low', 'or_width', 'pre_or_atr14', "
                            "'pre_or_width_atr14', "
                            "'trailing_24h_quote_volume')"
                        )
                    )
                ).all()
            }
            seeded_counts = {
                table: int(
                    await connection.scalar(sa.text(f"SELECT count(*) FROM {table}"))
                    or 0
                )
                for table in (
                    "brc_instrument_selection_specs",
                    "brc_instrument_selection_spec_members",
                    "brc_strategy_selection_control_current",
                    "brc_strategy_selection_rollback_baselines",
                )
            }
            source_kinds = tuple(
                (
                    await connection.execute(
                        sa.text(
                            "SELECT universe_version_id, source_kind "
                            "FROM brc_strategy_universe_versions "
                            "ORDER BY universe_version_id"
                        )
                    )
                ).all()
            )
            runtime_counts = {
                table: int(
                    await connection.scalar(sa.text(f"SELECT count(*) FROM {table}"))
                    or 0
                )
                for table in (
                    "brc_instrument_selection_snapshots",
                    "brc_strategy_universe_materialization_generations",
                    "brc_selection_session_authorities",
                    "brc_strategy_entry_vacuums_current",
                    "brc_exchange_commands",
                )
            }
            candidate_profiles = tuple(
                (
                    await connection.execute(
                        sa.text(
                            "SELECT p.* "
                            "FROM brc_instrument_product_profiles p "
                            "JOIN brc_instrument_selection_spec_members m "
                            "ON m.exchange_instrument_id = p.exchange_instrument_id "
                            "WHERE m.selection_spec_id = "
                            "'sor-dynamic-selection-v0' "
                            "ORDER BY p.exchange_instrument_id"
                        )
                    )
                )
                .mappings()
                .all()
            )

        assert revision == TARGET_REVISION
        assert selection_spec == (
            "sor-dynamic-selection-v0",
            "sha256:a2c0d5d809a54b90564086f4eab230726a16fdb5524a1ce8f29f48ad659cfb10",
        )
        assert feature_numeric_types == {
            "or_high": (None, None),
            "or_low": (None, None),
            "or_width": (None, None),
            "pre_or_atr14": (None, None),
            "pre_or_width_atr14": (None, None),
            "trailing_24h_quote_volume": (None, None),
        }
        assert seeded_counts == {
            "brc_instrument_selection_specs": 1,
            "brc_instrument_selection_spec_members": 24,
            "brc_strategy_selection_control_current": 1,
            "brc_strategy_selection_rollback_baselines": 1,
        }
        assert source_kinds == (
            ("universe:static:long", "manual"),
            ("universe:static:short", "manual"),
        )
        assert runtime_counts == {table: 0 for table in runtime_counts}
        assert len(candidate_profiles) == 24
        for row in candidate_profiles:
            profile = InstrumentProductProfile.model_validate(
                {
                    "exchange_instrument_id": row["exchange_instrument_id"],
                    "product_family": row["product_family"],
                    "asset_class": row["asset_class"],
                    "contract_type": row["contract_type"],
                    "underlying_type": row["underlying_type"],
                    "margin_asset": row["margin_asset"],
                    "entry_session_policy": row["entry_session_policy"],
                    "status": row["status"],
                    "max_entry_spread_bps": row["max_entry_spread_bps"],
                    "max_mark_index_deviation_bps": row[
                        "max_mark_index_deviation_bps"
                    ],
                }
            )
            assert row["semantic_digest"] == profile.semantic_digest

        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    """
                    INSERT INTO brc_strategy_entry_vacuums_current (
                        entry_vacuum_id, strategy_group_id, selection_spec_id,
                        session_start_ms, source_generation_id, state,
                        fenced_at_ms, drained_at_ms, resolved_at_ms,
                        first_blocker, projection_version
                    ) VALUES
                        ('vacuum:history:1', 'SOR-001',
                         'sor-dynamic-selection-v0', 1703980800000, NULL,
                         'VALID_EMPTY', 1703984400000, 1703984401000,
                         1703984402000, 'NO_SELECTION_READY_MEMBERS', 3),
                        ('vacuum:history:2', 'SOR-001',
                         'sor-dynamic-selection-v0', 1704067200000, NULL,
                         'VALID_EMPTY', 1704070800000, 1704070801000,
                         1704070802000, 'NO_SELECTION_READY_MEMBERS', 3),
                        ('vacuum:open:1', 'SOR-001',
                         'sor-dynamic-selection-v0', 1704153600000, NULL,
                         'OPEN', 1704157200000, NULL, NULL,
                         'NO_SELECTION_READY_MEMBERS', 1)
                    """
                )
            )

        with pytest.raises(DBAPIError, match="open_scope"):
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        """
                        INSERT INTO brc_strategy_entry_vacuums_current (
                            entry_vacuum_id, strategy_group_id, selection_spec_id,
                            session_start_ms, source_generation_id, state,
                            fenced_at_ms, drained_at_ms, resolved_at_ms,
                            first_blocker, projection_version
                        ) VALUES (
                            'vacuum:open:2', 'SOR-001',
                            'sor-dynamic-selection-v0', 1704240000000, NULL,
                            'DRAINING_ENTRY', 1704243600000, NULL, NULL,
                            'NO_SELECTION_READY_MEMBERS', 1
                        )
                        """
                    )
                )

        with pytest.raises(DBAPIError, match="exact bound LONG/SHORT targets"):
            async with engine.begin() as connection:
                await _insert_static_generation(
                    connection,
                    generation_id="generation:missing-short",
                )
                await connection.execute(
                    sa.text(
                        """
                        INSERT INTO brc_strategy_universe_materialization_targets (
                            materialization_generation_id, event_spec_id,
                            position_side, expected_member_set_digest,
                            materialization_order
                        ) VALUES (
                            'generation:missing-short',
                            'event_spec:SOR-001:SOR-LONG:v4', 'long',
                            :digest, 1
                        )
                        """
                    ),
                    {"digest": "sha256:" + "b" * 64},
                )

        async with engine.connect() as connection:
            generation_count = int(
                await connection.scalar(
                    sa.text(
                        "SELECT count(*) FROM "
                        "brc_strategy_universe_materialization_generations"
                    )
                )
                or 0
            )
        assert generation_count == 0

        with pytest.raises(DBAPIError, match="immutable Selection fact"):
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "UPDATE brc_instrument_selection_specs "
                        "SET status = 'retired' "
                        "WHERE selection_spec_id = 'sor-dynamic-selection-v0'"
                    )
                )
    finally:
        await engine.dispose()
        await _drop_database(database_name)


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


async def _insert_static_generation(connection, *, generation_id: str) -> None:
    await connection.execute(
        sa.text(
            """
            INSERT INTO brc_strategy_universe_materialization_generations (
                materialization_generation_id, selection_spec_id,
                strategy_group_id, strategy_version_id, selection_mode,
                selection_snapshot_id, rollback_baseline_id, session_start_ms,
                previous_long_universe_version_id,
                previous_short_universe_version_id, desired_member_count,
                semantic_digest, lifecycle_state, fallback_reason_code,
                lease_owner, lease_expires_at_ms, projection_version,
                created_at_ms, desired_at_ms, fenced_at_ms, activated_at_ms,
                fallback_at_ms, terminal_at_ms
            ) VALUES (
                :generation_id, 'sor-dynamic-selection-v0', 'SOR-001',
                'sgv:SOR-001:v4', 'static_baseline', NULL,
                'rollback-baseline:SOR-001:pre-dynamic-v0', NULL,
                'universe:static:long', 'universe:static:short', 1,
                :digest, 'PENDING', NULL, NULL, NULL, 1, 2000,
                NULL, NULL, NULL, NULL, NULL
            )
            """
        ),
        {
            "generation_id": generation_id,
            "digest": "sha256:" + "c" * 64,
        },
    )


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
