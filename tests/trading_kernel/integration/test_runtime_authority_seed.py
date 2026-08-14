from __future__ import annotations

import importlib
import subprocess
import sys
from collections.abc import AsyncGenerator
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from scripts.trading_kernel import seed_runtime_authority as seed_cli
from scripts.trading_kernel.certify_readonly import _certify
from src.trading_kernel.infrastructure.pg_models import (
    account_exposure_current,
    budget_reservations,
    entry_lane_current,
    instrument_product_profiles,
    instruments,
    owner_policy_current,
    owner_policy_events,
    runtime_capabilities_current,
    runtime_incidents,
    runtime_profiles,
    runtime_scopes_current,
    schema_metadata,
    strategy_universe_current,
    strategy_universe_members,
    strategy_universe_versions,
    trade_aggregates,
    trade_reviews,
    trade_tickets,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_identity import (
    CURRENT_SCHEMA_REVISION,
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
_TICKET_STRATEGY_GROUP_ID = "CPM-RO-001"
_TICKET_STRATEGY_VERSION_ID = "sgv:CPM-RO-001:v3"
_TICKET_EVENT_SPEC_ID = "event_spec:CPM-RO-001:CPM-LONG:v3"
_TICKET_UNIVERSE_VERSION_ID = "universe:test-cpm:v1"
_TICKET_UNIVERSE_DIGEST = "sha256:" + "3" * 64
_TICKET_RUNTIME_SCOPE_ID = "scope:test-cpm"
_TICKET_EXCHANGE_INSTRUMENT_ID = "binance-usdm:ETHUSDT:perpetual"
_TICKET_POSITION_SIDE = "long"
_TICKET_EXIT_POLICY_ID = (
    "exit-policy:CPM-RO-001:CPM-LONG:portfolio-admission-v1"
)
_TICKET_EXIT_POLICY_HASH = "sha256:" + "5" * 64


def _runtime_seed_module() -> ModuleType:
    try:
        return importlib.import_module(
            "src.trading_kernel.infrastructure.runtime_authority_seed"
        )
    except ModuleNotFoundError:
        pytest.fail("runtime authority seed module is missing")


def test_runtime_authority_seed_module_exists() -> None:
    _runtime_seed_module()


def test_runtime_authority_seed_cli_is_runnable_outside_repo(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(
                REPO_ROOT
                / "scripts"
                / "trading_kernel"
                / "seed_runtime_authority.py"
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
    assert "deploy-identity" in result.stdout
    assert "deploy-compatible-identity" in result.stdout
    assert "deploy-closure-identity" in result.stdout
    assert "deploy-protected-identity" not in result.stdout
    assert "arm-acceptance" in result.stdout
    assert "promote-full" in result.stdout
    assert list(tmp_path.rglob("*")) == []


@pytest.mark.parametrize(
    "action_args",
    (
        ("seed",),
        ("deploy-identity",),
        ("deploy-compatible-identity",),
        ("deploy-recovery-identity", "--recovery-ticket-id", "ticket:recovery"),
        ("deploy-closure-identity", "--closure-ticket-id", "ticket:closure"),
    ),
)
def test_runtime_authority_cli_defaults_to_current_schema_revision(
    monkeypatch: pytest.MonkeyPatch,
    action_args: tuple[str, ...],
) -> None:
    monkeypatch.delenv("TRADING_KERNEL_SCHEMA_REVISION", raising=False)

    args = seed_cli._parser().parse_args(action_args)

    assert args.schema_revision == CURRENT_SCHEMA_REVISION


@pytest_asyncio.fixture
async def runtime_seed_engine() -> AsyncGenerator[AsyncEngine, None]:
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
async def test_seed_creates_exact_idempotent_acceptance_authority(
    runtime_seed_engine: AsyncEngine,
) -> None:
    runtime_seed = _runtime_seed_module()
    request = runtime_seed.RuntimeAuthoritySeedRequest(
        account_id="subaccount-main",
        runtime_commit="commit-acceptance",
        schema_revision=CURRENT_SCHEMA_REVISION,
        seeded_at_ms=1_800_000_000_000,
    )

    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        first = await runtime_seed.seed_runtime_authority(uow, request)
    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        second = await runtime_seed.seed_runtime_authority(
            uow,
            request.model_copy(update={"seeded_at_ms": 1_800_000_000_001}),
        )
    assert "runtime_scope_count" not in type(first).model_fields
    assert first.new_entry_submit_enabled is False
    assert first.policy_version == 1
    assert first.max_concurrent_tickets == 3
    assert first.family_ticket_limits.model_dump() == {
        "long_continuation": 1,
        "opening_range": 2,
        "rally_failure_short": 1,
    }
    assert first.max_ticket_stop_risk_fraction == Decimal("0.02")
    assert first.max_gross_stop_risk_fraction == Decimal("0.06")
    assert first.max_ticket_initial_margin_fraction == Decimal("0.30")
    assert first.max_gross_initial_margin_utilization == Decimal("0.90")
    assert first.directional_stop_risk_limit_fraction == Decimal("0.04")
    assert first.min_materialization_ratio == Decimal("0.50")
    assert first.max_leverage == 10
    assert first.supported_margin_mode == "cross"
    assert first.post_stop_stress_multiple == Decimal("2.0")
    assert first.max_post_fill_stop_risk_overrun_fraction == Decimal("0.10")
    assert first.total_inserted_count > 0
    assert second.total_inserted_count == 0
    assert second.runtime_seed_semantic_hash == first.runtime_seed_semantic_hash
    assert runtime_seed.build_runtime_seed_identity(request) == (
        first.runtime_seed_semantic_hash
    )

    async with runtime_seed_engine.connect() as connection:
        policy = (
            await connection.execute(
                sa.select(owner_policy_current).where(
                    owner_policy_current.c.owner_policy_id == "policy-main"
                )
            )
        ).mappings().one()
        assert policy["policy_version"] == 1
        assert policy["enabled"] is True
        assert policy["new_entry_submit_enabled"] is False
        assert policy["max_concurrent_tickets"] == 3
        assert policy["family_ticket_limits"] == {
            "long_continuation": 1,
            "opening_range": 2,
            "rally_failure_short": 1,
        }
        assert policy["max_strategy_group_concurrent_tickets"] is None
        assert Decimal(policy["max_ticket_stop_risk_fraction"]) == Decimal("0.02")
        assert Decimal(policy["max_gross_stop_risk_fraction"]) == Decimal("0.06")
        assert Decimal(policy["max_ticket_initial_margin_fraction"]) == Decimal("0.30")
        assert Decimal(policy["max_gross_initial_margin_utilization"]) == Decimal("0.90")
        assert Decimal(policy["directional_stop_risk_limit_fraction"]) == Decimal("0.04")
        assert Decimal(policy["min_materialization_ratio"]) == Decimal("0.50")
        assert policy["max_leverage"] == 10
        assert policy["supported_margin_mode"] == "cross"
        assert Decimal(
            policy["post_stop_stress_multiple"]
        ) == Decimal("2.0")
        assert Decimal(
            policy["max_post_fill_stop_risk_overrun_fraction"]
        ) == Decimal("0.10")
        assert policy["scope"] == {
            "event_runtime_profiles": [
                {
                    "event_spec_id": "event_spec:BRF2-001:BRF2-SHORT:v3",
                    "runtime_profile_id": "tiny-live-v1",
                },
                {
                    "event_spec_id": "event_spec:CPM-RO-001:CPM-LONG:v3",
                    "runtime_profile_id": "tiny-live-v1",
                },
                {
                    "event_spec_id": "event_spec:MI-001:MI-LONG:v3",
                    "runtime_profile_id": "tiny-live-v1",
                },
                {
                    "event_spec_id": "event_spec:MPG-001:MPG-LONG:v3",
                    "runtime_profile_id": "tiny-live-v1",
                },
                {
                    "event_spec_id": "event_spec:SOR-001:SOR-LONG:v4",
                    "runtime_profile_id": "tiny-live-v1",
                },
                {
                    "event_spec_id": "event_spec:SOR-001:SOR-SHORT:v4",
                    "runtime_profile_id": "tiny-live-v1",
                },
                {
                    "event_spec_id": (
                        "event_spec:SOR-US-EQ-PERP-001:SOR-US-LONG-15M:v1"
                    ),
                    "runtime_profile_id": "tradfi-equity-usdm-v1",
                },
                {
                    "event_spec_id": (
                        "event_spec:SOR-US-EQ-PERP-001:SOR-US-SHORT-15M:v1"
                    ),
                    "runtime_profile_id": "tradfi-equity-usdm-v1",
                },
            ]
        }

        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(runtime_profiles)
        ) == 2
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(owner_policy_current)
        ) == 1
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(
                sa.table("brc_runtime_scopes_current")
            )
        ) == 0

        lane = (
            await connection.execute(sa.select(entry_lane_current))
        ).mappings().one()
        assert lane["lane_id"] == "global-entry"
        assert lane["status"] == "idle"
        assert lane["version"] == 0

        exposure = (
            await connection.execute(sa.select(account_exposure_current))
        ).mappings().one()
        assert exposure["venue_id"] == "binance-usdm"
        assert exposure["account_id"] == "subaccount-main"
        assert Decimal(exposure["gross_notional"]) == 0
        assert Decimal(exposure["gross_risk_at_stop"]) == 0
        assert exposure["active_ticket_count"] == 0

        capabilities = {
            str(row["capability_key"]): bool(row["enabled"])
            for row in (
                await connection.execute(sa.select(runtime_capabilities_current))
            ).mappings()
        }
        assert capabilities == {
            "exchange_commands": False,
            "strategy_signal_ingest": True,
        }

        metadata_rows = {
            str(row["metadata_key"]): str(row["metadata_value"])
            for row in (
                await connection.execute(sa.select(schema_metadata))
            ).mappings()
        }
        assert metadata_rows["runtime_commit"] == "commit-acceptance"
        assert metadata_rows["schema_revision"] == CURRENT_SCHEMA_REVISION
        assert metadata_rows["registry_semantic_hash"].startswith("sha256:")
        assert metadata_rows["seed_identity"].startswith("sha256:")


@pytest.mark.asyncio
async def test_deploy_identity_refreshes_commit_without_resetting_policy(
    runtime_seed_engine: AsyncEngine,
) -> None:
    runtime_seed = _runtime_seed_module()
    initial = runtime_seed.RuntimeAuthoritySeedRequest(
        account_id="subaccount-main",
        runtime_commit="a" * 40,
        schema_revision=CURRENT_SCHEMA_REVISION,
        seeded_at_ms=1_800_000_000_000,
    )
    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        await runtime_seed.deploy_runtime_identity(uow, initial)
    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        await runtime_seed.arm_acceptance_policy(
            uow,
            runtime_seed.ArmAcceptancePolicyRequest(
                armed_at_ms=1_800_000_000_100,
            ),
        )

    refreshed = initial.model_copy(
        update={
            "runtime_commit": "b" * 40,
            "seeded_at_ms": 1_800_000_000_200,
        }
    )
    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        first = await runtime_seed.deploy_runtime_identity(uow, refreshed)
    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        second = await runtime_seed.deploy_runtime_identity(
            uow,
            refreshed.model_copy(update={"seeded_at_ms": 1_800_000_000_300}),
        )

    assert first.runtime_commit == "b" * 40
    assert second.runtime_commit == "b" * 40
    assert first.runtime_seed_semantic_hash == second.runtime_seed_semantic_hash
    async with runtime_seed_engine.connect() as connection:
        policy = (
            await connection.execute(
                sa.select(owner_policy_current).where(
                    owner_policy_current.c.owner_policy_id == "policy-main"
                )
            )
        ).mappings().one()
        assert policy["policy_version"] == 2
        assert policy["new_entry_submit_enabled"] is True
        metadata_rows = {
            str(row["metadata_key"]): str(row["metadata_value"])
            for row in (
                await connection.execute(sa.select(schema_metadata))
            ).mappings()
        }
        assert metadata_rows["runtime_commit"] == "b" * 40
        capabilities = (
            await connection.execute(sa.select(runtime_capabilities_current))
        ).mappings().all()
        assert {str(row["certified_commit"]) for row in capabilities} == {
            "b" * 40
        }
        assert {
            str(row["capability_key"]): bool(row["enabled"])
            for row in capabilities
        } == {
            "exchange_commands": True,
            "strategy_signal_ingest": True,
        }


@pytest.mark.asyncio
async def test_compatible_fix_forward_resolves_only_exact_runtime_fence(
    runtime_seed_engine: AsyncEngine,
) -> None:
    """Catches the target identity transition being blocked by its own fence."""

    runtime_seed = _runtime_seed_module()
    initial = runtime_seed.RuntimeAuthoritySeedRequest(
        account_id="subaccount-main",
        runtime_commit="a" * 40,
        schema_revision=CURRENT_SCHEMA_REVISION,
        seeded_at_ms=1_800_000_000_000,
    )
    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        await runtime_seed.deploy_runtime_identity(uow, initial)
    async with runtime_seed_engine.begin() as connection:
        await connection.execute(
            sa.insert(runtime_incidents).values(
                incident_id="incident:runtime-fence",
                ticket_id=None,
                incident_kind="runtime_identity_mismatch",
                status="open",
                first_blocker="runtime_identity_mismatch",
                entry_block_scope="runtime",
                entry_block_key="global",
                details={
                    "worker_id": "tokyo-lifecycle-1",
                    "runtime_commit": "a" * 40,
                    "schema_revision": CURRENT_SCHEMA_REVISION,
                },
                opened_at_ms=1_800_000_000_050,
                resolved_at_ms=None,
            )
        )

    refreshed = initial.model_copy(
        update={
            "runtime_commit": "b" * 40,
            "seeded_at_ms": 1_800_000_000_100,
        }
    )
    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        result = await runtime_seed.deploy_compatible_upgrade_identity(
            uow,
            refreshed,
        )

    assert result.runtime_commit == "b" * 40
    async with runtime_seed_engine.connect() as connection:
        incident = (
            await connection.execute(
                sa.select(
                    runtime_incidents.c.status,
                    runtime_incidents.c.resolved_at_ms,
                ).where(
                    runtime_incidents.c.incident_id == "incident:runtime-fence"
                )
            )
        ).mappings().one()
    assert incident == {
        "status": "resolved",
        "resolved_at_ms": 1_800_000_000_100,
    }


@pytest.mark.asyncio
async def test_compatible_fix_forward_rejects_any_other_open_incident(
    runtime_seed_engine: AsyncEngine,
) -> None:
    """Catches broad Incident bypass in the target-schema recovery path."""

    runtime_seed = _runtime_seed_module()
    initial = runtime_seed.RuntimeAuthoritySeedRequest(
        account_id="subaccount-main",
        runtime_commit="a" * 40,
        schema_revision=CURRENT_SCHEMA_REVISION,
        seeded_at_ms=1_800_000_000_000,
    )
    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        await runtime_seed.deploy_runtime_identity(uow, initial)
    async with runtime_seed_engine.begin() as connection:
        await connection.execute(
            sa.insert(runtime_incidents).values(
                incident_id="incident:other",
                ticket_id=None,
                incident_kind="other_runtime_failure",
                status="open",
                first_blocker="other_runtime_failure",
                entry_block_scope="runtime",
                entry_block_key="global",
                details={},
                opened_at_ms=1_800_000_000_050,
                resolved_at_ms=None,
            )
        )

    with pytest.raises(
        runtime_seed.RuntimeAuthorityTransitionRefused,
        match="zero open Incidents",
    ):
        async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
            await runtime_seed.deploy_compatible_upgrade_identity(
                uow,
                initial.model_copy(
                    update={
                        "runtime_commit": "b" * 40,
                        "seeded_at_ms": 1_800_000_000_100,
                    }
                ),
            )


@pytest.mark.asyncio
async def test_compatible_identity_rotates_exact_migrated_v4_authority(
    runtime_seed_engine: AsyncEngine,
) -> None:
    runtime_seed = _runtime_seed_module()
    source_revision = "0002_sor_v3_strategy_group_capacity"
    source_commit = "b" * 40
    source_seed = "sha256:" + "9" * 64
    allowed_vnext = (
        "event_spec:BRF2-001:BRF2-SHORT:v3",
        "event_spec:CPM-RO-001:CPM-LONG:v3",
        "event_spec:MI-001:MI-LONG:v3",
        "event_spec:MPG-001:MPG-LONG:v3",
        "event_spec:SOR-001:SOR-LONG:v4",
        "event_spec:SOR-001:SOR-SHORT:v4",
    )
    policy = runtime_seed._crypto_source_policy_values(
        version=4,
        new_entry_submit_enabled=False,
        allowed_event_spec_ids=allowed_vnext,
        updated_at_ms=1_800_000_000_000,
    )
    async with runtime_seed_engine.begin() as connection:
        await connection.execute(
            sa.insert(runtime_profiles).values(
                runtime_profile_id="tiny-live-v1",
                venue_id="binance-usdm",
                account_id="subaccount-main",
                environment="live",
                position_mode="independent_sides",
                status="active",
                updated_at_ms=1_800_000_000_000,
            )
        )
        await connection.execute(sa.insert(owner_policy_current).values(policy))
        await connection.execute(
            sa.insert(owner_policy_events).values(
                owner_policy_event_id="policy-event:policy-main:v4",
                owner_policy_id="policy-main",
                policy_version=4,
                operation="compatible_upgrade_portfolio_admission_v4",
                payload={"source": "0003_migration"},
                created_at_ms=1_800_000_000_000,
            )
        )
        await connection.execute(
            sa.insert(entry_lane_current).values(
                lane_id="global-entry",
                ticket_id=None,
                signal_event_id=None,
                status="idle",
                claimed_at_ms=None,
                lease_until_ms=None,
                claim_owner=None,
                version=0,
            )
        )
        await connection.execute(
            sa.insert(account_exposure_current).values(
                venue_id="binance-usdm",
                account_id="subaccount-main",
                gross_notional=0,
                gross_risk_at_stop=0,
                current_reserved_margin=0,
                active_ticket_count=0,
                projection_version=0,
                updated_at_ms=1_800_000_000_000,
            )
        )
        await connection.execute(
            sa.insert(runtime_capabilities_current),
            [
                {
                    "capability_key": key,
                    "enabled": enabled,
                    "certified_commit": source_commit,
                    "schema_revision": source_revision,
                    "certification": {"stage": "acceptance_armed"},
                    "updated_at_ms": 1_800_000_000_000,
                }
                for key, enabled in (
                    ("exchange_commands", True),
                    ("strategy_signal_ingest", True),
                )
            ],
        )
        await connection.execute(
            sa.insert(schema_metadata),
            [
                {
                    "metadata_key": key,
                    "metadata_value": value,
                    "updated_at_ms": 1_800_000_000_000,
                }
                for key, value in (
                    ("registry_semantic_hash", "sha256:" + "8" * 64),
                    ("runtime_commit", source_commit),
                    ("schema_revision", source_revision),
                    ("seed_identity", source_seed),
                    (
                        "preservation_source_revision",
                        "0002_sor_v3_strategy_group_capacity",
                    ),
                    (
                        "preservation_target_revision",
                        CURRENT_SCHEMA_REVISION,
                    ),
                    ("preservation_digest", "sha256:" + "6" * 64),
                    (
                        "preservation_database_identity",
                        "postgresql:7665555261146054689:16384",
                    ),
                    ("preservation_proof_digest", "sha256:" + "7" * 64),
                )
            ],
        )
        await connection.execute(
            sa.insert(runtime_incidents).values(
                incident_id="incident:runtime-fence",
                ticket_id=None,
                incident_kind="runtime_identity_mismatch",
                status="open",
                first_blocker="runtime_identity_mismatch",
                entry_block_scope="runtime",
                entry_block_key="global",
                details={
                    "worker_id": "tokyo-lifecycle-1",
                    "runtime_commit": source_commit,
                    "schema_revision": CURRENT_SCHEMA_REVISION,
                },
                opened_at_ms=1_800_000_000_050,
                resolved_at_ms=None,
            )
        )

    request = runtime_seed.RuntimeAuthoritySeedRequest(
        account_id="subaccount-main",
        runtime_commit="a" * 40,
        schema_revision=CURRENT_SCHEMA_REVISION,
        seeded_at_ms=1_800_000_000_100,
    )
    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        result = await runtime_seed.deploy_compatible_upgrade_identity(uow, request)

    assert result.runtime_commit == "a" * 40
    assert result.schema_revision == CURRENT_SCHEMA_REVISION
    async with runtime_seed_engine.connect() as connection:
        current = (
            await connection.execute(
                sa.select(owner_policy_current).where(
                    owner_policy_current.c.owner_policy_id == "policy-main"
                )
            )
        ).mappings().one()
        events = (
            await connection.execute(
                sa.select(owner_policy_events.c.policy_version)
                .where(owner_policy_events.c.owner_policy_id == "policy-main")
                .order_by(owner_policy_events.c.policy_version)
            )
        ).scalars().all()
        metadata_rows = dict(
            (
                await connection.execute(
                    sa.select(
                        schema_metadata.c.metadata_key,
                        schema_metadata.c.metadata_value,
                    )
                )
            ).all()
        )
        incident = (
            await connection.execute(
                sa.select(
                    runtime_incidents.c.status,
                    runtime_incidents.c.resolved_at_ms,
                ).where(
                    runtime_incidents.c.incident_id == "incident:runtime-fence"
                )
            )
        ).mappings().one()
    assert current["policy_version"] == 5
    assert current["new_entry_submit_enabled"] is False
    assert current["max_concurrent_tickets"] == 3
    assert current["max_strategy_group_concurrent_tickets"] is None
    assert current["max_ticket_stop_risk_fraction"] == Decimal("0.02")
    assert current["max_gross_stop_risk_fraction"] == Decimal("0.06")
    assert current["max_ticket_initial_margin_fraction"] == Decimal("0.30")
    assert current["max_gross_initial_margin_utilization"] == Decimal("0.90")
    assert current["max_leverage"] == 10
    assert current["supported_margin_mode"] == "cross"
    assert len(current["scope"]["event_runtime_profiles"]) == 8
    assert {
        item["runtime_profile_id"]
        for item in current["scope"]["event_runtime_profiles"]
    } == {"tiny-live-v1", "tradfi-equity-usdm-v1"}
    assert events == [4, 5]
    assert metadata_rows["runtime_commit"] == "a" * 40
    assert metadata_rows["schema_revision"] == CURRENT_SCHEMA_REVISION
    assert metadata_rows["seed_identity"] == result.runtime_seed_semantic_hash
    assert metadata_rows["preservation_source_revision"] == source_revision
    assert metadata_rows["preservation_target_revision"] == CURRENT_SCHEMA_REVISION
    assert metadata_rows["preservation_digest"] == "sha256:" + "6" * 64
    assert metadata_rows["preservation_database_identity"] == (
        "postgresql:7665555261146054689:16384"
    )
    assert metadata_rows["preservation_proof_digest"] == "sha256:" + "7" * 64
    assert incident == {
        "status": "resolved",
        "resolved_at_ms": 1_800_000_000_100,
    }

@pytest.mark.asyncio
async def test_recovery_identity_refuses_a_runtime_without_one_unknown_leverage_ticket(
    runtime_seed_engine: AsyncEngine,
) -> None:
    runtime_seed = _runtime_seed_module()
    request = runtime_seed.RuntimeAuthoritySeedRequest(
        account_id="subaccount-main",
        runtime_commit="a" * 40,
        schema_revision=CURRENT_SCHEMA_REVISION,
        seeded_at_ms=1_800_000_000_000,
    )
    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        await runtime_seed.deploy_runtime_identity(uow, request)

    with pytest.raises(
        runtime_seed.RuntimeAuthorityTransitionRefused,
        match="recovery identity requires exactly one active Ticket",
    ):
        async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
            await runtime_seed.deploy_recovery_identity(
                uow,
                request.model_copy(
                    update={
                        "runtime_commit": "b" * 40,
                        "seeded_at_ms": 1_800_000_000_100,
                    }
                ),
                recovery_ticket_id="ticket:recovery",
            )


@pytest.mark.asyncio
async def test_closure_identity_rotates_only_one_exact_released_pending_ticket(
    runtime_seed_engine: AsyncEngine,
) -> None:
    runtime_seed = _runtime_seed_module()
    initial = runtime_seed.RuntimeAuthoritySeedRequest(
        account_id="subaccount-main",
        runtime_commit="a" * 40,
        schema_revision=CURRENT_SCHEMA_REVISION,
        seeded_at_ms=1_800_000_000_000,
    )
    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        await runtime_seed.deploy_runtime_identity(uow, initial)
    await _insert_released_pending_closure_ticket(runtime_seed_engine)

    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        result = await runtime_seed.deploy_closure_identity(
            uow,
            initial.model_copy(
                update={
                    "runtime_commit": "b" * 40,
                    "seeded_at_ms": 1_800_000_000_100,
                }
            ),
            closure_ticket_id="ticket:closure",
        )

    assert result.runtime_commit == "b" * 40


@pytest.mark.asyncio
async def test_readonly_certification_emits_exact_pending_closure_manifest(
    runtime_seed_engine: AsyncEngine,
) -> None:
    runtime_seed = _runtime_seed_module()
    request = runtime_seed.RuntimeAuthoritySeedRequest(
        account_id="subaccount-main",
        runtime_commit="a" * 40,
        schema_revision=CURRENT_SCHEMA_REVISION,
        seeded_at_ms=1_800_000_000_000,
    )
    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        await runtime_seed.deploy_runtime_identity(uow, request)
    await _insert_released_pending_closure_ticket(runtime_seed_engine)

    payload = await _certify(
        runtime_seed_engine.url.render_as_string(hide_password=False),
        require_flat=False,
        closure_ticket_id="ticket:closure",
    )

    assert payload["status"] == "pass", payload
    assert payload["closure_ticket"] == {
        "ticket_id": "ticket:closure",
        "aggregate_status": "settlement_pending",
        "aggregate_version": 7,
        "last_event_sequence": 7,
        "netting_domain_key": "closure-domain",
        "position_quantity": "0",
        "protected_quantity": "0",
        "owned_order_residue_count": 0,
        "unresolved_command_count": 0,
        "open_incident_count": 0,
        "budget_reservation_status": "released",
        "account_capacity_released": True,
        "netting_domain_released": True,
        "review_presence": False,
    }


@pytest.mark.asyncio
async def test_policy_transitions_require_terminal_reviewed_acceptance_ticket(
    runtime_seed_engine: AsyncEngine,
) -> None:
    runtime_seed = _runtime_seed_module()
    seed_request = runtime_seed.RuntimeAuthoritySeedRequest(
        account_id="subaccount-main",
        runtime_commit="commit-acceptance",
        schema_revision=CURRENT_SCHEMA_REVISION,
        seeded_at_ms=1_800_000_000_000,
    )
    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        seeded = await runtime_seed.seed_runtime_authority(uow, seed_request)
    before = runtime_seed.RuntimePolicyState(
        **{
            field: getattr(seeded, field)
            for field in runtime_seed.RuntimePolicyState.model_fields
        }
    )
    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        armed = await runtime_seed.arm_acceptance_policy(
            uow,
            runtime_seed.ArmAcceptancePolicyRequest(
                armed_at_ms=1_800_000_000_100,
            ),
        )

    assert armed.policy_version == 2
    assert armed.new_entry_submit_enabled is True
    assert armed.max_concurrent_tickets == 3
    assert armed.family_ticket_limits.opening_range == 2
    assert armed.max_ticket_stop_risk_fraction == Decimal("0.02")
    assert armed.max_gross_stop_risk_fraction == Decimal("0.06")
    assert armed.max_ticket_initial_margin_fraction == Decimal("0.30")
    assert armed.max_gross_initial_margin_utilization == Decimal("0.90")
    assert armed.max_leverage == 10
    assert armed.model_dump(
        exclude={"policy_version", "new_entry_submit_enabled"}
    ) == before.model_dump(exclude={"policy_version", "new_entry_submit_enabled"})

    with pytest.raises(
        runtime_seed.RuntimeAuthorityTransitionRefused,
        match="terminal reviewed acceptance Ticket",
    ):
        async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
            await runtime_seed.promote_full_policy(
                uow,
                runtime_seed.PromoteFullPolicyRequest(
                    acceptance_ticket_id="ticket-acceptance",
                    promoted_at_ms=1_800_000_000_200,
                ),
            )

    await _insert_terminal_reviewed_ticket(runtime_seed_engine)

    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        promoted = await runtime_seed.promote_full_policy(
            uow,
            runtime_seed.PromoteFullPolicyRequest(
                acceptance_ticket_id="ticket-acceptance",
                promoted_at_ms=1_800_000_000_300,
            ),
        )

    assert promoted.policy_version == 3
    assert promoted.new_entry_submit_enabled is True
    assert promoted.max_concurrent_tickets == 3
    assert promoted.family_ticket_limits.opening_range == 2
    assert promoted.max_ticket_stop_risk_fraction == Decimal("0.02")
    assert promoted.max_gross_stop_risk_fraction == Decimal("0.06")
    assert promoted.max_ticket_initial_margin_fraction == Decimal("0.30")
    assert promoted.max_gross_initial_margin_utilization == Decimal("0.90")
    assert promoted.max_leverage == 10
    assert promoted.supported_margin_mode == "cross"

    async with runtime_seed_engine.connect() as connection:
        exchange_commands_enabled = await connection.scalar(
            sa.select(runtime_capabilities_current.c.enabled).where(
                runtime_capabilities_current.c.capability_key
                == "exchange_commands"
            )
        )
        assert exchange_commands_enabled is True


async def _insert_ticket_universe(connection: AsyncConnection) -> None:
    await connection.execute(
        sa.insert(instruments).values(
            exchange_instrument_id=_TICKET_EXCHANGE_INSTRUMENT_ID,
            venue_id="binance-usdm",
            asset_class="crypto",
            venue_symbol="ETHUSDT",
            contract_kind="perpetual",
            status="active",
        )
    )
    await connection.execute(
        sa.insert(instrument_product_profiles).values(
            exchange_instrument_id=_TICKET_EXCHANGE_INSTRUMENT_ID,
            product_family="crypto_perpetual",
            asset_class="crypto",
            contract_type="PERPETUAL",
            underlying_type="CRYPTO",
            margin_asset="USDT",
            entry_session_policy="continuous",
            status="candidate",
            max_entry_spread_bps=None,
            max_mark_index_deviation_bps=None,
            semantic_digest="sha256:" + "6" * 64,
            updated_at_ms=1_800_000_000_001,
        )
    )
    await connection.execute(
        sa.insert(strategy_universe_versions).values(
            universe_version_id=_TICKET_UNIVERSE_VERSION_ID,
            strategy_group_id=_TICKET_STRATEGY_GROUP_ID,
            event_spec_id=_TICKET_EVENT_SPEC_ID,
            universe_version=1,
            semantic_digest=_TICKET_UNIVERSE_DIGEST,
            lifecycle_state="active",
            installed_at_ms=1_800_000_000_001,
            activated_at_ms=1_800_000_000_002,
            retired_at_ms=None,
        )
    )
    await connection.execute(
        sa.insert(strategy_universe_members).values(
            universe_version_id=_TICKET_UNIVERSE_VERSION_ID,
            exchange_instrument_id=_TICKET_EXCHANGE_INSTRUMENT_ID,
        )
    )
    await connection.execute(
        sa.insert(strategy_universe_current).values(
            event_spec_id=_TICKET_EVENT_SPEC_ID,
            universe_version_id=_TICKET_UNIVERSE_VERSION_ID,
            semantic_digest=_TICKET_UNIVERSE_DIGEST,
            lifecycle_state="active",
            activation_generation=1,
            activated_at_ms=1_800_000_000_002,
        )
    )
    await connection.execute(
        sa.insert(runtime_scopes_current).values(
            runtime_scope_id=_TICKET_RUNTIME_SCOPE_ID,
            strategy_group_id=_TICKET_STRATEGY_GROUP_ID,
            strategy_version_id=_TICKET_STRATEGY_VERSION_ID,
            event_spec_id=_TICKET_EVENT_SPEC_ID,
            runtime_profile_id="tiny-live-v1",
            owner_policy_id="policy-main",
            exchange_instrument_id=_TICKET_EXCHANGE_INSTRUMENT_ID,
            position_side=_TICKET_POSITION_SIDE,
            universe_version_id=_TICKET_UNIVERSE_VERSION_ID,
            universe_semantic_digest=_TICKET_UNIVERSE_DIGEST,
            lifecycle_state="active",
            observation_enabled=True,
            entry_enabled=True,
            scope_version=1,
            warm_closed_bar_time_ms=1_800_000_000_002,
            warm_completed_at_ms=1_800_000_000_002,
            warm_readiness_digest="sha256:" + "4" * 64,
            warm_valid_until_ms=1_800_000_060_002,
            next_observation_due_at_ms=1_800_000_000_002,
            lease_expires_at_ms=None,
            lease_owner=None,
            observation_generation=0,
            updated_at_ms=1_800_000_000_002,
        )
    )


async def _insert_terminal_reviewed_ticket(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await _insert_ticket_universe(connection)
        await connection.execute(
            sa.insert(trade_tickets).values(
                ticket_id="ticket-acceptance",
                exposure_episode_id="exposure-acceptance",
                signal_event_id="signal-acceptance",
                strategy_group_id=_TICKET_STRATEGY_GROUP_ID,
                strategy_version_id=_TICKET_STRATEGY_VERSION_ID,
                event_spec_id=_TICKET_EVENT_SPEC_ID,
                universe_version_id=_TICKET_UNIVERSE_VERSION_ID,
                universe_semantic_digest=_TICKET_UNIVERSE_DIGEST,
                runtime_profile_id="tiny-live-v1",
                owner_policy_id="policy-main",
                owner_policy_version=2,
                runtime_scope_id=_TICKET_RUNTIME_SCOPE_ID,
                runtime_scope_version=1,
                account_id="subaccount-main",
                venue_id="binance-usdm",
                exchange_instrument_id=_TICKET_EXCHANGE_INSTRUMENT_ID,
                position_side=_TICKET_POSITION_SIDE,
                netting_domain_key="acceptance-domain",
                active_netting_domain_key=None,
                exit_policy_id=_TICKET_EXIT_POLICY_ID,
                exit_policy_semantic_hash=_TICKET_EXIT_POLICY_HASH,
                entry_reference_price=Decimal(100),
                quantity=Decimal("0.1"),
                notional=Decimal(10),
                capacity_claim_id="claim-acceptance",
                planned_stop_risk_budget=Decimal(1),
                post_fill_stop_risk_limit=Decimal("1.1"),
                selected_leverage=2,
                leverage_change_required=False,
                reserved_margin=Decimal(5),
                risk_reservation_basis="planned_stop_distance",
                margin_mode="cross",
                cross_margin_stress_model_id="cross-margin-stop-stress-v1",
                post_stop_stress_multiple=Decimal(2),
                claim_stress_proof_digest="sha256:" + "3" * 64,
                risk_at_stop=Decimal(1),
                entry_order_type="market",
                entry_limit_price=None,
                initial_stop_price=Decimal(90),
                take_profit_prices=[],
                take_profit_quantities=[],
                fact_digest="sha256:" + "1" * 64,
                decision_digest="sha256:" + "2" * 64,
                status="terminal",
                created_at_ms=1_800_000_000_110,
                expires_at_ms=1_800_000_001_110,
                terminal_at_ms=1_800_000_000_250,
            )
        )
        await connection.execute(
            sa.insert(trade_reviews).values(
                review_id="review-acceptance",
                ticket_id="ticket-acceptance",
                revision=1,
                supersedes_review_id=None,
                outcome="closed",
                metrics={"net_pnl_quote": "0"},
                decision_impact={"policy_transition": "acceptance_complete"},
                created_at_ms=1_800_000_000_260,
            )
        )


async def _insert_released_pending_closure_ticket(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await _insert_ticket_universe(connection)
        await connection.execute(
            sa.insert(trade_tickets).values(
                ticket_id="ticket:closure",
                exposure_episode_id="exposure:closure",
                signal_event_id="signal:closure",
                strategy_group_id=_TICKET_STRATEGY_GROUP_ID,
                strategy_version_id=_TICKET_STRATEGY_VERSION_ID,
                event_spec_id=_TICKET_EVENT_SPEC_ID,
                universe_version_id=_TICKET_UNIVERSE_VERSION_ID,
                universe_semantic_digest=_TICKET_UNIVERSE_DIGEST,
                runtime_profile_id="tiny-live-v1",
                owner_policy_id="policy-main",
                owner_policy_version=2,
                runtime_scope_id=_TICKET_RUNTIME_SCOPE_ID,
                runtime_scope_version=1,
                account_id="subaccount-main",
                venue_id="binance-usdm",
                exchange_instrument_id=_TICKET_EXCHANGE_INSTRUMENT_ID,
                position_side=_TICKET_POSITION_SIDE,
                netting_domain_key="closure-domain",
                active_netting_domain_key=None,
                exit_policy_id=_TICKET_EXIT_POLICY_ID,
                exit_policy_semantic_hash=_TICKET_EXIT_POLICY_HASH,
                entry_reference_price=Decimal(100),
                quantity=Decimal("0.1"),
                notional=Decimal(10),
                capacity_claim_id="claim:closure",
                planned_stop_risk_budget=Decimal(1),
                post_fill_stop_risk_limit=Decimal("1.1"),
                selected_leverage=5,
                leverage_change_required=False,
                reserved_margin=Decimal(2),
                risk_reservation_basis="planned_stop_distance",
                margin_mode="cross",
                cross_margin_stress_model_id="cross-margin-stop-stress-v1",
                post_stop_stress_multiple=Decimal(2),
                claim_stress_proof_digest="sha256:" + "3" * 64,
                risk_at_stop=Decimal(1),
                entry_order_type="market",
                entry_limit_price=None,
                initial_stop_price=Decimal(90),
                take_profit_prices=[],
                take_profit_quantities=[],
                fact_digest="sha256:" + "1" * 64,
                decision_digest="sha256:" + "2" * 64,
                status="settlement_pending",
                created_at_ms=1_800_000_000_010,
                expires_at_ms=1_800_000_001_010,
                terminal_at_ms=None,
            )
        )
        await connection.execute(
            sa.insert(trade_aggregates).values(
                ticket_id="ticket:closure",
                status="settlement_pending",
                version=7,
                last_event_sequence=7,
                entry_lane_held=False,
                position_qty=Decimal(0),
                average_fill_price=Decimal(100),
                actual_stop_risk=Decimal(1),
                venue_reported_liquidation_price=Decimal(80),
                post_fill_risk_status="within_budget",
                post_fill_disposition="normal",
                post_fill_stress_status="passed",
                post_fill_stress_proof_digest="sha256:" + "4" * 64,
                protected_qty=Decimal(0),
                entry_exchange_order_id="entry:closure",
                initial_stop_exchange_order_id=None,
                active_stop_exchange_order_id=None,
                active_stop_price=None,
                tp1_exchange_order_id=None,
                tp1_target_qty=Decimal(0),
                tp1_filled_qty=Decimal(0),
                break_even_floor_price=None,
                pending_replaced_stop_exchange_order_id=None,
                pending_stop_price=None,
                pending_stop_watermark_ms=None,
                runner_stop_watermark_ms=None,
                pending_cancel_exchange_order_id=None,
                exit_exchange_order_id="exit:closure",
                review_id=None,
                lifecycle_due_at_ms=None,
                reconciliation_due_at_ms=1_800_000_000_010,
                updated_at_ms=1_800_000_000_010,
            )
        )
        await connection.execute(
            sa.insert(budget_reservations).values(
                budget_reservation_id="reservation:closure",
                ticket_id="ticket:closure",
                owner_policy_id="policy-main",
                venue_id="binance-usdm",
                account_id="subaccount-main",
                reserved_notional=Decimal(10),
                reserved_risk=Decimal(1),
                reserved_margin=Decimal(2),
                planned_stop_risk_budget=Decimal(1),
                risk_reservation_basis="planned_stop_distance",
                status="released",
                created_at_ms=1_800_000_000_010,
                released_at_ms=1_800_000_000_020,
            )
        )
