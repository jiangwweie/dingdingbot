from __future__ import annotations

import subprocess
import sys
from collections.abc import AsyncGenerator
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from src.trading_kernel.domain.exit_policy import registered_exit_profiles
from src.trading_kernel.domain.strategy_registry import (
    build_registry_semantic_hash,
    registered_strategy_contracts,
)
from src.trading_kernel.infrastructure.pg_models import (
    event_exit_profile_binding_current,
    event_exit_profile_bindings,
    event_specs,
    exit_policies,
    instruments,
    owner_policy_current,
    runtime_profiles,
    runtime_scopes_current,
    strategy_groups,
    strategy_versions,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RUNTIME_PROFILE_ID,
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import (
    CURRENT_SCHEMA_REVISION,
)
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    RegistrySeedConflict,
    seed_strategy_registry,
)
from tests.trading_kernel.support.postgres import (
    SAFE_TEST_DATABASE as SAFE_DATABASE,
)
from tests.trading_kernel.support.postgres import (
    TEST_POSTGRES_ADMIN_DSN as ADMIN_DSN,
)
from tests.trading_kernel.support.postgres import (
    async_database_url as _database_url,
)
from tests.trading_kernel.support.postgres import (
    run_alembic as _run_alembic,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_strategy_registry_seed_cli_is_runnable_outside_repo(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(
                REPO_ROOT
                / "scripts"
                / "trading_kernel"
                / "seed_strategy_registry.py"
            ),
            "--help",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--database-url" in result.stdout
    assert list(tmp_path.rglob("*")) == []


@pytest_asyncio.fixture
async def registry_engine() -> AsyncGenerator[AsyncEngine, None]:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    await admin.execute(f'CREATE DATABASE "{database_name}"')
    database_url = _database_url(database_name)
    _run_alembic(database_url, "upgrade", "head")
    engine = create_async_engine(database_url)
    try:
        yield engine
    finally:
        await engine.dispose()
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            database_name,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await admin.close()


@pytest.mark.asyncio
async def test_strategy_seed_is_exact_idempotent_and_does_not_grant_live_authority(
    registry_engine: AsyncEngine,
) -> None:
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        first = await seed_strategy_registry(uow, seeded_at_ms=1_800_000_000_000)
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        second = await seed_strategy_registry(uow, seeded_at_ms=1_800_000_000_001)
        event_ids = await uow.strategy_registry.list_current_event_ids()

    assert first.inserted_strategy_group_count == 6
    assert first.inserted_strategy_version_count == 6
    assert first.inserted_event_count == 8
    assert first.inserted_product_compatibility_count == 8
    assert first.inserted_exit_policy_count == 0
    assert first.inserted_exit_profile_count == 8
    assert first.inserted_exit_binding_count == 8
    assert first.inserted_exit_binding_current_count == 8
    assert first.inserted_exit_binding_event_count == 8
    assert first.inserted_fact_definition_count == 29
    assert first.inserted_event_fact_count == 39
    assert "inserted_instrument_count" not in type(first).model_fields
    assert "inserted_candidate_scope_count" not in type(first).model_fields
    assert second.total_inserted_count == 0
    assert event_ids == (
        "BRF2-SHORT",
        "CPM-LONG",
        "MI-LONG",
        "MPG-LONG",
        "SOR-LONG",
        "SOR-SHORT",
        "SOR-US-LONG-15M",
        "SOR-US-SHORT-15M",
    )

    async with registry_engine.connect() as connection:
        assert await connection.scalar(sa.select(sa.func.count()).select_from(runtime_profiles)) == 0
        assert await connection.scalar(sa.select(sa.func.count()).select_from(runtime_scopes_current)) == 0
        assert await connection.scalar(sa.select(sa.func.count()).select_from(owner_policy_current)) == 0
        assert await connection.scalar(sa.select(sa.func.count()).select_from(instruments)) == 0
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(exit_policies)
        ) == 8
        current_versions = dict(
            (
                await connection.execute(
                sa.select(
                    strategy_versions.c.strategy_group_id,
                    strategy_versions.c.strategy_version_id,
                ).where(strategy_versions.c.status == "active")
                .order_by(strategy_versions.c.strategy_group_id)
                )
            ).all()
        )
        assert current_versions == {
            "BRF2-001": "sgv:BRF2-001:v3",
            "CPM-RO-001": "sgv:CPM-RO-001:v3",
            "MI-001": "sgv:MI-001:v3",
            "MPG-001": "sgv:MPG-001:v3",
            "SOR-001": "sgv:SOR-001:v4",
            "SOR-US-EQ-PERP-001": "sgv:SOR-US-EQ-PERP-001:v1",
        }


@pytest.mark.asyncio
async def test_strategy_seed_fails_closed_on_existing_semantic_conflict(
    registry_engine: AsyncEngine,
) -> None:
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1_800_000_000_000)

    async with registry_engine.begin() as connection:
        await connection.execute(
            sa.update(event_specs)
            .where(event_specs.c.event_id == "SOR-LONG")
            .values(timeframe="1h")
        )

    with pytest.raises(RegistrySeedConflict, match="event_spec:SOR-001:SOR-LONG:v4"):
        async with PostgresKernelUnitOfWork(registry_engine) as uow:
            await seed_strategy_registry(uow, seeded_at_ms=1_800_000_000_001)


@pytest.mark.asyncio
async def test_strategy_seed_conflicts_when_contract_status_changes(
    registry_engine: AsyncEngine,
) -> None:
    contracts = registered_strategy_contracts()
    disabled = contracts[0].model_validate(
        {**contracts[0].model_dump(mode="python"), "status": "disabled"}
    )
    disabled_contracts = (disabled, *contracts[1:])

    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        await uow.strategy_registry.seed_exact(
            disabled_contracts,
            registry_semantic_hash=build_registry_semantic_hash(disabled_contracts),
            seeded_at_ms=1_800_000_000_000,
        )

    with pytest.raises(RegistrySeedConflict, match="strategy Registry conflict"):
        async with PostgresKernelUnitOfWork(registry_engine) as uow:
            await seed_strategy_registry(uow, seeded_at_ms=1_800_000_000_001)


@pytest.mark.asyncio
async def test_strategy_seed_fails_closed_on_exit_profile_semantic_conflict(
    registry_engine: AsyncEngine,
) -> None:
    profile = registered_exit_profiles()[0]
    async with registry_engine.begin() as connection:
        await connection.execute(
            sa.insert(exit_policies).values(
                exit_policy_id=profile.exit_profile_id,
                exit_policy_version=str(profile.exit_profile_version),
                event_spec_id=None,
                profile_schema_version=profile.profile_schema_version,
                position_side=profile.position_side,
                policy=profile.model_dump(mode="json"),
                semantic_hash="sha256:" + "0" * 64,
                status="active",
                created_at_ms=1_800_000_000_000,
            )
        )

    with pytest.raises(RegistrySeedConflict, match=profile.exit_profile_id):
        async with PostgresKernelUnitOfWork(registry_engine) as uow:
            await seed_strategy_registry(uow, seeded_at_ms=1_800_000_000_001)


@pytest.mark.asyncio
async def test_strategy_seed_monotonically_retires_source_sor_v3_and_activates_v4(
    registry_engine: AsyncEngine,
) -> None:
    async with registry_engine.begin() as connection:
        await _insert_source_sor_v3_registry(connection)

    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        first = await seed_strategy_registry(uow, seeded_at_ms=1_800_000_000_000)
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        second = await seed_strategy_registry(uow, seeded_at_ms=1_800_000_000_001)

    async with registry_engine.connect() as connection:
        group = (
            await connection.execute(
                sa.select(strategy_groups).where(
                    strategy_groups.c.strategy_group_id == "SOR-001"
                )
            )
        ).mappings().one()
        versions = (
            await connection.execute(
                sa.select(
                    strategy_versions.c.strategy_version_id,
                    strategy_versions.c.version,
                    strategy_versions.c.status,
                )
                .where(strategy_versions.c.strategy_group_id == "SOR-001")
                .order_by(strategy_versions.c.version)
            )
        ).all()
        events = (
            await connection.execute(
                sa.select(
                    event_specs.c.event_spec_id,
                    event_specs.c.status,
                )
                .where(event_specs.c.event_id.in_(("SOR-LONG", "SOR-SHORT")))
                .order_by(event_specs.c.event_spec_id)
            )
        ).all()
        policies = (
            await connection.execute(
                sa.select(
                    exit_policies.c.exit_policy_id,
                    exit_policies.c.status,
                )
                .where(
                    exit_policies.c.exit_policy_id.like(
                        "exit-policy:SOR-001:%"
                    )
                )
                .order_by(exit_policies.c.exit_policy_id)
            )
        ).all()

    assert group["active_version_id"] == "sgv:SOR-001:v4"
    assert versions == [
        ("sgv:SOR-001:v3", 3, "retired"),
        ("sgv:SOR-001:v4", 4, "active"),
    ]
    assert events == [
        ("event_spec:SOR-001:SOR-LONG:v3", "retired"),
        ("event_spec:SOR-001:SOR-LONG:v4", "active"),
        ("event_spec:SOR-001:SOR-SHORT:v3", "retired"),
        ("event_spec:SOR-001:SOR-SHORT:v4", "active"),
    ]
    assert policies == [
        ("exit-policy:SOR-001:SOR-LONG:sor-v3-right-tail-v1", "active"),
        ("exit-policy:SOR-001:SOR-SHORT:sor-v3-right-tail-v1", "active"),
    ]
    assert first.inserted_strategy_group_count == 5
    assert first.inserted_strategy_version_count == 6
    assert first.inserted_event_count == 8
    assert second.total_inserted_count == 0


@pytest.mark.asyncio
async def test_universe_install_resolves_the_active_v4_registry_pointer(
    registry_engine: AsyncEngine,
) -> None:
    async with registry_engine.begin() as connection:
        await _insert_source_sor_v3_registry(connection)

    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        await seed_runtime_authority(
            uow,
            RuntimeAuthoritySeedRequest(
                account_id="subaccount-registry-upgrade-test",
                runtime_commit="registry-upgrade-test",
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=1_800_000_000_000,
            ),
        )
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        context = await uow.strategy_universes.resolve_install_context(
            runtime_profile_id=RUNTIME_PROFILE_ID,
            event_id="SOR-LONG",
        )

    assert context.event_spec_id == "event_spec:SOR-001:SOR-LONG:v4"


@pytest.mark.asyncio
async def test_registry_seed_installs_exit_profile_catalog_and_initial_bindings(
    registry_engine: AsyncEngine,
) -> None:
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        first = await seed_strategy_registry(uow, seeded_at_ms=1_800_000_000_000)
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        second = await seed_strategy_registry(uow, seeded_at_ms=1_800_000_000_000)

    async with registry_engine.connect() as connection:
        profiles = (
            await connection.execute(
                sa.select(
                    exit_policies.c.exit_policy_id,
                    exit_policies.c.profile_schema_version,
                    exit_policies.c.event_spec_id,
                    exit_policies.c.semantic_hash,
                )
                .where(exit_policies.c.profile_schema_version == "exit_profile_v1")
                .order_by(exit_policies.c.exit_policy_id)
            )
        ).all()
        bindings = (
            await connection.execute(
                sa.select(
                    event_exit_profile_bindings.c.event_spec_id,
                    event_exit_profile_bindings.c.exit_profile_id,
                    event_exit_profile_bindings.c.exit_profile_semantic_hash,
                    event_exit_profile_bindings.c.binding_semantic_hash,
                ).order_by(event_exit_profile_bindings.c.event_spec_id)
            )
        ).all()
        current = (
            await connection.execute(
                sa.select(
                    event_exit_profile_binding_current.c.event_spec_id,
                    event_exit_profile_binding_current.c.exit_binding_id,
                    event_exit_profile_binding_current.c.projection_version,
                ).order_by(event_exit_profile_binding_current.c.event_spec_id)
            )
        ).all()

    assert len(profiles) == 8
    assert all(row.profile_schema_version == "exit_profile_v1" for row in profiles)
    assert all(row.event_spec_id is None for row in profiles)
    assert len(bindings) == 8
    assert len(current) == 8
    assert {row.projection_version for row in current} == {1}
    assert first.inserted_exit_profile_count == 8
    assert first.inserted_exit_binding_count == 8
    assert first.inserted_exit_binding_current_count == 8
    assert first.inserted_exit_binding_event_count == 8
    assert second.total_inserted_count == 0


@pytest.mark.asyncio
async def test_strategy_seed_rejects_an_extra_active_version_outside_the_pointer(
    registry_engine: AsyncEngine,
) -> None:
    async with registry_engine.begin() as connection:
        await _insert_source_sor_v3_registry(connection)
        await connection.execute(
            sa.insert(strategy_versions).values(
                strategy_version_id="sgv:SOR-001:v1",
                strategy_group_id="SOR-001",
                version=1,
                semantics={"source": "unexpected_parallel_authority"},
                status="active",
                created_at_ms=800,
            )
        )

    with pytest.raises(RegistrySeedConflict, match="active version conflicts"):
        async with PostgresKernelUnitOfWork(registry_engine) as uow:
            await seed_strategy_registry(uow, seeded_at_ms=1_800_000_000_000)


@pytest.mark.asyncio
async def test_strategy_seed_ignores_legacy_policy_retirement_for_current_profiles(
    registry_engine: AsyncEngine,
) -> None:
    async with registry_engine.begin() as connection:
        await _insert_source_sor_v3_registry(connection)
        await connection.execute(
            sa.update(exit_policies)
            .where(
                exit_policies.c.exit_policy_id
                == "exit-policy:SOR-001:SOR-SHORT:sor-v3-right-tail-v1"
            )
            .values(status="retired")
        )

    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1_800_000_000_000)

    async with registry_engine.connect() as connection:
        active_profiles = int(
            await connection.scalar(
                sa.select(sa.func.count())
                .select_from(exit_policies)
                .where(
                    exit_policies.c.profile_schema_version == "exit_profile_v1",
                    exit_policies.c.status == "active",
                )
            )
            or 0
        )
    assert active_profiles == 8


async def _insert_source_sor_v3_registry(
    connection: AsyncConnection,
) -> None:
    await connection.execute(
        sa.insert(strategy_groups).values(
            strategy_group_id="SOR-001",
            display_name="SOR opening range breakout and breakdown",
            active_version_id="sgv:SOR-001:v3",
            status="active",
            updated_at_ms=900,
        )
    )
    await connection.execute(
        sa.insert(strategy_versions).values(
            strategy_version_id="sgv:SOR-001:v3",
            strategy_group_id="SOR-001",
            version=3,
            semantics={
                "event_spec_ids": [
                    "event_spec:SOR-001:SOR-LONG:v3",
                    "event_spec:SOR-001:SOR-SHORT:v3",
                ],
                "registry_semantic_hash": "sha256:" + "1" * 64,
                "source": "committed_strategy_registry_contract",
            },
            status="active",
            created_at_ms=900,
        )
    )
    for event_id, position_side in (
        ("SOR-LONG", "long"),
        ("SOR-SHORT", "short"),
    ):
        event_spec_id = f"event_spec:SOR-001:{event_id}:v3"
        exit_policy_id = f"exit-policy:SOR-001:{event_id}:sor-v3-right-tail-v1"
        await connection.execute(
            sa.insert(event_specs).values(
                event_spec_id=event_spec_id,
                strategy_version_id="sgv:SOR-001:v3",
                event_id=event_id,
                position_side=position_side,
                timeframe="15m",
                freshness_window_ms=900_000,
                event_time_authority="trigger_candle_close_time_ms",
                entry_order_type="market",
                protection_reference_fact_definition_id=(
                    f"fact:legacy-{event_id.lower()}-protection:v1"
                ),
                exit_policy_id=exit_policy_id,
                execution_semantics={"source": "committed_old_main_program_v2"},
                status="active",
                created_at_ms=900,
            )
        )
        await connection.execute(
            sa.insert(exit_policies).values(
                exit_policy_id=exit_policy_id,
                exit_policy_version="sor-v3-right-tail-v1",
                event_spec_id=event_spec_id,
                position_side=position_side,
                policy={},
                semantic_hash="sha256:" + ("2" if position_side == "long" else "3") * 64,
                status="active",
                created_at_ms=900,
            )
        )
