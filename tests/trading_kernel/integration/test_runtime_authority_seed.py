from __future__ import annotations

from decimal import Decimal
import importlib
from pathlib import Path
import subprocess
import sys
from types import ModuleType
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.trading_kernel.infrastructure.pg_models import (
    account_exposure_current,
    entry_lane_current,
    owner_policy_current,
    runtime_capabilities_current,
    runtime_profiles,
    runtime_scopes_current,
    schema_metadata,
    trade_reviews,
    trade_tickets,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.integration.test_issue_ticket import (
    ADMIN_DSN,
    SAFE_DATABASE,
    _database_url,
    _run_alembic,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


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
    assert "arm-acceptance" in result.stdout
    assert "promote-full" in result.stdout
    assert list(tmp_path.rglob("*")) == []


@pytest_asyncio.fixture
async def runtime_seed_engine() -> AsyncEngine:
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
        schema_revision="0001_initial",
        seeded_at_ms=1_800_000_000_000,
    )

    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        first = await runtime_seed.seed_runtime_authority(uow, request)
    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        second = await runtime_seed.seed_runtime_authority(
            uow,
            request.model_copy(update={"seeded_at_ms": 1_800_000_000_001}),
        )

    assert first.runtime_scope_count == 22
    assert first.new_entry_submit_enabled is False
    assert first.policy_version == 1
    assert first.max_concurrent_tickets == 3
    assert first.planned_stop_risk_fraction == Decimal("0.03")
    assert first.max_initial_margin_utilization == Decimal("0.90")
    assert first.max_leverage == 10
    assert first.supported_margin_mode == "cross"
    assert first.min_liquidation_distance_to_stop_distance_ratio == Decimal("2.0")
    assert first.max_post_fill_stop_risk_overrun_fraction == Decimal("0.10")
    assert first.total_inserted_count > 0
    assert second.total_inserted_count == 0
    assert second.runtime_seed_semantic_hash == first.runtime_seed_semantic_hash
    assert runtime_seed.build_runtime_seed_identity(request) == (
        first.runtime_seed_semantic_hash
    )

    async with runtime_seed_engine.connect() as connection:
        policy = (
            await connection.execute(sa.select(owner_policy_current))
        ).mappings().one()
        assert policy["policy_version"] == 1
        assert policy["enabled"] is True
        assert policy["new_entry_submit_enabled"] is False
        assert policy["max_concurrent_tickets"] == 3
        assert Decimal(policy["planned_stop_risk_fraction"]) == Decimal("0.03")
        assert Decimal(policy["max_initial_margin_utilization"]) == Decimal("0.90")
        assert policy["max_leverage"] == 10
        assert policy["supported_margin_mode"] == "cross"
        assert Decimal(
            policy["min_liquidation_distance_to_stop_distance_ratio"]
        ) == Decimal("2.0")
        assert Decimal(
            policy["max_post_fill_stop_risk_overrun_fraction"]
        ) == Decimal("0.10")

        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(runtime_profiles)
        ) == 1
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(runtime_scopes_current)
        ) == 22
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(runtime_scopes_current).where(
                runtime_scopes_current.c.enabled.is_(True)
            )
        ) == 22

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
        assert metadata_rows["schema_revision"] == "0001_initial"
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
        schema_revision="0001_initial",
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
            await connection.execute(sa.select(owner_policy_current))
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
async def test_recovery_identity_refuses_a_runtime_without_one_unknown_leverage_ticket(
    runtime_seed_engine: AsyncEngine,
) -> None:
    runtime_seed = _runtime_seed_module()
    request = runtime_seed.RuntimeAuthoritySeedRequest(
        account_id="subaccount-main",
        runtime_commit="a" * 40,
        schema_revision="0001_initial",
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
async def test_policy_transitions_require_terminal_reviewed_acceptance_ticket(
    runtime_seed_engine: AsyncEngine,
) -> None:
    runtime_seed = _runtime_seed_module()
    seed_request = runtime_seed.RuntimeAuthoritySeedRequest(
        account_id="subaccount-main",
        runtime_commit="commit-acceptance",
        schema_revision="0001_initial",
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
    assert armed.planned_stop_risk_fraction == Decimal("0.03")
    assert armed.max_initial_margin_utilization == Decimal("0.90")
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
    assert promoted.planned_stop_risk_fraction == Decimal("0.03")
    assert promoted.max_initial_margin_utilization == Decimal("0.90")
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


async def _insert_terminal_reviewed_ticket(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        scope = (
            await connection.execute(
                sa.select(runtime_scopes_current).order_by(
                    runtime_scopes_current.c.runtime_scope_id
                )
            )
        ).mappings().first()
        assert scope is not None
        await connection.execute(
            sa.insert(trade_tickets).values(
                ticket_id="ticket-acceptance",
                exposure_episode_id="exposure-acceptance",
                signal_event_id="signal-acceptance",
                strategy_group_id=scope["strategy_group_id"],
                strategy_version_id=scope["strategy_version_id"],
                event_spec_id=scope["event_spec_id"],
                runtime_profile_id=scope["runtime_profile_id"],
                owner_policy_id=scope["owner_policy_id"],
                owner_policy_version=2,
                runtime_scope_id=scope["runtime_scope_id"],
                runtime_scope_version=scope["scope_version"],
                account_id="subaccount-main",
                venue_id="binance-usdm",
                exchange_instrument_id=scope["exchange_instrument_id"],
                position_side=scope["position_side"],
                netting_domain_key="acceptance-domain",
                active_netting_domain_key=None,
                entry_reference_price=Decimal("100"),
                quantity=Decimal("0.1"),
                notional=Decimal("10"),
                capacity_claim_id="claim-acceptance",
                planned_stop_risk_budget=Decimal("1"),
                post_fill_stop_risk_limit=Decimal("1.1"),
                selected_leverage=2,
                leverage_change_required=False,
                reserved_margin=Decimal("5"),
                risk_reservation_basis="planned_stop_distance",
                margin_mode="cross",
                min_liquidation_distance_to_stop_distance_ratio=Decimal("2"),
                projected_liquidation_price=Decimal("80"),
                projected_liquidation_distance_to_stop_distance_ratio=Decimal("2.5"),
                risk_at_stop=Decimal("1"),
                entry_order_type="market",
                entry_limit_price=None,
                initial_stop_price=Decimal("90"),
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
                outcome="closed",
                metrics={"net_pnl_quote": "0"},
                decision_impact={"policy_transition": "acceptance_complete"},
                created_at_ms=1_800_000_000_260,
            )
        )
