from __future__ import annotations

import importlib
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from scripts.trading_kernel.certify_readonly import _certify
from src.trading_kernel.infrastructure.pg_models import (
    account_exposure_current,
    budget_reservations,
    entry_lane_current,
    exchange_commands,
    instruments,
    owner_policy_current,
    positions_current,
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
from tests.trading_kernel.integration.test_issue_ticket import (
    ADMIN_DSN,
    SAFE_DATABASE,
    _database_url,
    _run_alembic,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
_TICKET_STRATEGY_GROUP_ID = "CPM-RO-001"
_TICKET_STRATEGY_VERSION_ID = "sgv:CPM-RO-001:v2"
_TICKET_EVENT_SPEC_ID = "event_spec:CPM-RO-001:CPM-LONG:v2"
_TICKET_UNIVERSE_VERSION_ID = "universe:test-cpm:v1"
_TICKET_UNIVERSE_DIGEST = "sha256:" + "3" * 64
_TICKET_RUNTIME_SCOPE_ID = "scope:test-cpm"
_TICKET_EXCHANGE_INSTRUMENT_ID = "binance-usdm:ETHUSDT:perpetual"
_TICKET_POSITION_SIDE = "long"


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
    assert "deploy-closure-identity" in result.stdout
    assert "deploy-protected-identity" in result.stdout
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
        schema_revision="0003_cross_margin_stop_stress",
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
    assert first.planned_stop_risk_fraction == Decimal("0.03")
    assert first.max_initial_margin_utilization == Decimal("0.90")
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
            policy["post_stop_stress_multiple"]
        ) == Decimal("2.0")
        assert Decimal(
            policy["max_post_fill_stop_risk_overrun_fraction"]
        ) == Decimal("0.10")
        assert policy["scope"] == {
            "runtime_profile_id": "tiny-live-v1",
            "allowed_event_spec_ids": [
                "event_spec:BRF2-001:BRF2-SHORT:v2",
                "event_spec:CPM-RO-001:CPM-LONG:v2",
                "event_spec:MI-001:MI-LONG:v2",
                "event_spec:MPG-001:MPG-LONG:v2",
                "event_spec:SOR-001:SOR-LONG:v2",
                "event_spec:SOR-001:SOR-SHORT:v2",
            ],
        }

        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(runtime_profiles)
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
        assert metadata_rows["schema_revision"] == "0003_cross_margin_stop_stress"
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
        schema_revision="0003_cross_margin_stop_stress",
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
        schema_revision="0003_cross_margin_stop_stress",
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
async def test_protected_identity_rotates_only_the_exact_protected_ticket_set(
    runtime_seed_engine: AsyncEngine,
) -> None:
    runtime_seed = _runtime_seed_module()
    initial = runtime_seed.RuntimeAuthoritySeedRequest(
        account_id="subaccount-main",
        runtime_commit="a" * 40,
        schema_revision="0003_cross_margin_stop_stress",
        seeded_at_ms=1_800_000_000_000,
    )
    ticket_ids = ("ticket:avax", "ticket:btc", "ticket:sol")
    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        await runtime_seed.deploy_runtime_identity(uow, initial)
    await _insert_protected_tickets(
        runtime_seed_engine,
        ticket_ids,
        runner_ticket_ids=ticket_ids[1:],
    )

    target = initial.model_copy(
        update={
            "runtime_commit": "b" * 40,
            "seeded_at_ms": 1_800_000_000_100,
        }
    )
    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        result = await runtime_seed.deploy_protected_identity(
            uow,
            target,
            protected_ticket_ids=ticket_ids,
        )

    assert result.runtime_commit == "b" * 40
    async with runtime_seed_engine.connect() as connection:
        runtime_commit = await connection.scalar(
            sa.select(schema_metadata.c.metadata_value).where(
                schema_metadata.c.metadata_key == "runtime_commit"
            )
        )
    assert runtime_commit == "b" * 40


@pytest.mark.asyncio
async def test_closure_identity_rotates_only_one_exact_released_pending_ticket(
    runtime_seed_engine: AsyncEngine,
) -> None:
    runtime_seed = _runtime_seed_module()
    initial = runtime_seed.RuntimeAuthoritySeedRequest(
        account_id="subaccount-main",
        runtime_commit="a" * 40,
        schema_revision="0003_cross_margin_stop_stress",
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
        schema_revision="0003_cross_margin_stop_stress",
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

    assert payload["status"] == "pass"
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
async def test_protected_identity_refuses_extra_activity_and_open_incidents(
    runtime_seed_engine: AsyncEngine,
) -> None:
    runtime_seed = _runtime_seed_module()
    request = runtime_seed.RuntimeAuthoritySeedRequest(
        account_id="subaccount-main",
        runtime_commit="a" * 40,
        schema_revision="0003_cross_margin_stop_stress",
        seeded_at_ms=1_800_000_000_000,
    )
    ticket_ids = ("ticket:avax", "ticket:btc", "ticket:sol")
    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        await runtime_seed.deploy_runtime_identity(uow, request)
    await _insert_protected_tickets(runtime_seed_engine, ticket_ids)

    with pytest.raises(
        runtime_seed.RuntimeAuthorityTransitionRefused,
        match="exact active protected Ticket set",
    ):
        async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
            await runtime_seed.deploy_protected_identity(
                uow,
                request.model_copy(
                    update={
                        "runtime_commit": "b" * 40,
                        "seeded_at_ms": 1_800_000_000_100,
                    }
                ),
                protected_ticket_ids=ticket_ids[:2],
            )

    async with runtime_seed_engine.begin() as connection:
        await connection.execute(
            sa.insert(exchange_commands).values(
                command_id="command:protected",
                ticket_id=ticket_ids[0],
                command_kind="set_leverage",
                generation=1,
                idempotency_key="idempotency:protected",
                venue_client_order_id=None,
                status="outcome_unknown",
                quantity=None,
                request_payload={},
                result_payload=None,
                claim_owner=None,
                lease_until_ms=None,
                created_at_ms=1_800_000_000_125,
                deadline_at_ms=1_800_000_010_125,
                completed_at_ms=None,
            )
        )

    with pytest.raises(
        runtime_seed.RuntimeAuthorityTransitionRefused,
        match="zero unresolved Exchange Commands",
    ):
        async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
            await runtime_seed.deploy_protected_identity(
                uow,
                request.model_copy(
                    update={
                        "runtime_commit": "b" * 40,
                        "seeded_at_ms": 1_800_000_000_125,
                    }
                ),
                protected_ticket_ids=ticket_ids,
            )

    async with runtime_seed_engine.begin() as connection:
        await connection.execute(
            sa.delete(exchange_commands).where(
                exchange_commands.c.command_id == "command:protected"
            )
        )
        await connection.execute(
            sa.insert(runtime_incidents).values(
                incident_id="incident:protected",
                ticket_id=ticket_ids[0],
                incident_kind="handover_blocked",
                status="open",
                first_blocker="test",
                entry_block_scope="none",
                entry_block_key=None,
                details={},
                opened_at_ms=1_800_000_000_150,
                resolved_at_ms=None,
            )
        )

    with pytest.raises(
        runtime_seed.RuntimeAuthorityTransitionRefused,
        match="zero open Incidents",
    ):
        async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
            await runtime_seed.deploy_protected_identity(
                uow,
                request.model_copy(
                    update={
                        "runtime_commit": "b" * 40,
                        "seeded_at_ms": 1_800_000_000_200,
                    }
                ),
                protected_ticket_ids=ticket_ids,
            )


@pytest.mark.asyncio
async def test_protected_identity_rotates_a_complete_runner_ticket(
    runtime_seed_engine: AsyncEngine,
) -> None:
    runtime_seed = _runtime_seed_module()
    initial = runtime_seed.RuntimeAuthoritySeedRequest(
        account_id="subaccount-main",
        runtime_commit="a" * 40,
        schema_revision="0003_cross_margin_stop_stress",
        seeded_at_ms=1_800_000_000_000,
    )
    ticket_ids = ("ticket:avax", "ticket:btc", "ticket:sol")
    runner_ticket_ids = ticket_ids[1:]
    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        await runtime_seed.deploy_runtime_identity(uow, initial)
    await _insert_protected_tickets(
        runtime_seed_engine,
        ticket_ids,
        runner_ticket_ids=runner_ticket_ids,
    )

    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        result = await runtime_seed.deploy_protected_identity(
            uow,
            initial.model_copy(
                update={
                    "runtime_commit": "b" * 40,
                    "seeded_at_ms": 1_800_000_000_100,
                }
            ),
            protected_ticket_ids=ticket_ids,
        )

    assert result.runtime_commit == "b" * 40


@pytest.mark.asyncio
async def test_readonly_certification_emits_exact_protected_ticket_manifest(
    runtime_seed_engine: AsyncEngine,
) -> None:
    runtime_seed = _runtime_seed_module()
    initial = runtime_seed.RuntimeAuthoritySeedRequest(
        account_id="subaccount-main",
        runtime_commit="a" * 40,
        schema_revision="0003_cross_margin_stop_stress",
        seeded_at_ms=1_800_000_000_000,
    )
    ticket_ids = ("ticket:avax", "ticket:btc", "ticket:sol")
    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        await runtime_seed.deploy_runtime_identity(uow, initial)
    await _insert_protected_tickets(
        runtime_seed_engine,
        ticket_ids,
        runner_ticket_ids=ticket_ids[1:],
    )

    payload = await _certify(
        runtime_seed_engine.url.render_as_string(hide_password=False),
        require_flat=False,
    )

    assert payload["status"] == "pass"
    protected_tickets = payload["protected_tickets"]
    assert isinstance(protected_tickets, list)
    assert [ticket["ticket_id"] for ticket in protected_tickets] == list(ticket_ids)
    assert protected_tickets[0]["active_tp1_order"]["exchange_order_id"] == "tp1:1"
    assert protected_tickets[1]["recorded_tp1_fill_quantity"] == "1"


@pytest.mark.asyncio
async def test_protected_identity_refuses_missing_active_budget_reservation(
    runtime_seed_engine: AsyncEngine,
) -> None:
    runtime_seed = _runtime_seed_module()
    initial = runtime_seed.RuntimeAuthoritySeedRequest(
        account_id="subaccount-main",
        runtime_commit="a" * 40,
        schema_revision="0003_cross_margin_stop_stress",
        seeded_at_ms=1_800_000_000_000,
    )
    ticket_ids = ("ticket:avax", "ticket:btc", "ticket:sol")
    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        await runtime_seed.deploy_runtime_identity(uow, initial)
    await _insert_protected_tickets(
        runtime_seed_engine,
        ticket_ids,
        include_budget_reservations=False,
    )

    with pytest.raises(
        runtime_seed.RuntimeAuthorityTransitionRefused,
        match="active Budget Reservations",
    ):
        async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
            await runtime_seed.deploy_protected_identity(
                uow,
                initial.model_copy(
                    update={
                        "runtime_commit": "b" * 40,
                        "seeded_at_ms": 1_800_000_000_100,
                    }
                ),
                protected_ticket_ids=ticket_ids,
            )


@pytest.mark.asyncio
async def test_protected_identity_refuses_unrelated_active_budget_reservation(
    runtime_seed_engine: AsyncEngine,
) -> None:
    runtime_seed = _runtime_seed_module()
    initial = runtime_seed.RuntimeAuthoritySeedRequest(
        account_id="subaccount-main",
        runtime_commit="a" * 40,
        schema_revision="0003_cross_margin_stop_stress",
        seeded_at_ms=1_800_000_000_000,
    )
    ticket_ids = ("ticket:avax", "ticket:btc", "ticket:sol")
    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        await runtime_seed.deploy_runtime_identity(uow, initial)
    await _insert_protected_tickets(runtime_seed_engine, ticket_ids)
    async with runtime_seed_engine.begin() as connection:
        await connection.execute(
            sa.insert(budget_reservations).values(
                budget_reservation_id="reservation:unrelated",
                ticket_id="ticket:unrelated",
                owner_policy_id="policy-main",
                venue_id="binance-usdm",
                account_id="subaccount-main",
                reserved_notional=Decimal(1),
                reserved_risk=Decimal(0),
                reserved_margin=Decimal("0.2"),
                planned_stop_risk_budget=Decimal(0),
                risk_reservation_basis="planned_stop_distance",
                status="active",
                created_at_ms=1_800_000_000_099,
                released_at_ms=None,
            )
        )

    with pytest.raises(
        runtime_seed.RuntimeAuthorityTransitionRefused,
        match="exact active Budget Reservations",
    ):
        async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
            await runtime_seed.deploy_protected_identity(
                uow,
                initial.model_copy(
                    update={
                        "runtime_commit": "b" * 40,
                        "seeded_at_ms": 1_800_000_000_100,
                    }
                ),
                protected_ticket_ids=ticket_ids,
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("notional_delta", "risk_delta"),
    (
        (Decimal(1), Decimal(0)),
        (Decimal(0), Decimal(1)),
    ),
)
async def test_protected_identity_refuses_mismatched_account_exposure_totals(
    runtime_seed_engine: AsyncEngine,
    notional_delta: Decimal,
    risk_delta: Decimal,
) -> None:
    runtime_seed = _runtime_seed_module()
    initial = runtime_seed.RuntimeAuthoritySeedRequest(
        account_id="subaccount-main",
        runtime_commit="a" * 40,
        schema_revision="0003_cross_margin_stop_stress",
        seeded_at_ms=1_800_000_000_000,
    )
    ticket_ids = ("ticket:avax", "ticket:btc", "ticket:sol")
    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        await runtime_seed.deploy_runtime_identity(uow, initial)
    await _insert_protected_tickets(
        runtime_seed_engine,
        ticket_ids,
        exposure_notional_delta=notional_delta,
        exposure_risk_delta=risk_delta,
    )

    with pytest.raises(
        runtime_seed.RuntimeAuthorityTransitionRefused,
        match="matching account exposure",
    ):
        async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
            await runtime_seed.deploy_protected_identity(
                uow,
                initial.model_copy(
                    update={
                        "runtime_commit": "b" * 40,
                        "seeded_at_ms": 1_800_000_000_100,
                    }
                ),
                protected_ticket_ids=ticket_ids,
            )


@pytest.mark.asyncio
async def test_policy_transitions_require_terminal_reviewed_acceptance_ticket(
    runtime_seed_engine: AsyncEngine,
) -> None:
    runtime_seed = _runtime_seed_module()
    seed_request = runtime_seed.RuntimeAuthoritySeedRequest(
        account_id="subaccount-main",
        runtime_commit="commit-acceptance",
        schema_revision="0003_cross_margin_stop_stress",
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
            warm_ready_at_ms=1_800_000_000_002,
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


async def _insert_protected_tickets(
    engine: AsyncEngine,
    ticket_ids: tuple[str, ...],
    *,
    runner_ticket_ids: tuple[str, ...] = (),
    include_budget_reservations: bool = True,
    exposure_notional_delta: Decimal = Decimal(0),
    exposure_risk_delta: Decimal = Decimal(0),
) -> None:
    async with engine.begin() as connection:
        await _insert_ticket_universe(connection)
        total_notional = Decimal(0)
        total_risk = Decimal(0)
        for index, ticket_id in enumerate(ticket_ids, start=1):
            quantity = Decimal(index)
            is_runner = ticket_id in runner_ticket_ids
            projected_quantity = (
                quantity / Decimal(2) if is_runner else quantity
            )
            notional = Decimal(100) * quantity
            risk = Decimal(3) * quantity
            netting_domain = f"binance-usdm:subaccount-main:{index}:short"
            await connection.execute(
                sa.insert(trade_tickets).values(
                    ticket_id=ticket_id,
                    exposure_episode_id=f"exposure:{index}",
                    signal_event_id=f"signal:{index}",
                    strategy_group_id=_TICKET_STRATEGY_GROUP_ID,
                    strategy_version_id=_TICKET_STRATEGY_VERSION_ID,
                    event_spec_id=_TICKET_EVENT_SPEC_ID,
                    universe_version_id=_TICKET_UNIVERSE_VERSION_ID,
                    universe_semantic_digest=_TICKET_UNIVERSE_DIGEST,
                    runtime_profile_id="tiny-live-v1",
                    owner_policy_id="policy-main",
                    owner_policy_version=1,
                    runtime_scope_id=_TICKET_RUNTIME_SCOPE_ID,
                    runtime_scope_version=1,
                    account_id="subaccount-main",
                    venue_id="binance-usdm",
                    exchange_instrument_id=f"instrument:{index}",
                    position_side="short",
                    netting_domain_key=netting_domain,
                    active_netting_domain_key=netting_domain,
                    entry_reference_price=Decimal(100),
                    quantity=quantity,
                    notional=notional,
                    capacity_claim_id=f"claim:{index}",
                    planned_stop_risk_budget=risk,
                    post_fill_stop_risk_limit=risk * Decimal("1.1"),
                    selected_leverage=5,
                    leverage_change_required=False,
                    reserved_margin=notional / Decimal(5),
                    risk_reservation_basis="planned_stop_distance",
                    margin_mode="cross",
                    cross_margin_stress_model_id="cross-margin-stop-stress-v1",
                    post_stop_stress_multiple=Decimal(2),
                    claim_stress_proof_digest="sha256:" + "3" * 64,
                    risk_at_stop=risk,
                    entry_order_type="market",
                    entry_limit_price=None,
                    initial_stop_price=Decimal(103),
                    take_profit_prices=["97"],
                    take_profit_quantities=[str(quantity / Decimal(2))],
                    fact_digest="sha256:" + "1" * 64,
                    decision_digest="sha256:" + "2" * 64,
                    status="position_protected",
                    created_at_ms=1_800_000_000_010 + index,
                    expires_at_ms=1_800_000_100_010 + index,
                    terminal_at_ms=None,
                )
            )
            await connection.execute(
                sa.insert(trade_aggregates).values(
                    ticket_id=ticket_id,
                    status=("runner_protected" if is_runner else "position_protected"),
                    version=5,
                    last_event_sequence=5,
                    entry_lane_held=False,
                    position_qty=projected_quantity,
                    average_fill_price=Decimal(100),
                    actual_stop_risk=risk,
                    venue_reported_liquidation_price=Decimal(110),
                    post_fill_risk_status="within_budget",
                    post_fill_disposition="normal",
                    post_fill_stress_status="passed",
                    post_fill_stress_proof_digest="sha256:" + "4" * 64,
                    protected_qty=projected_quantity,
                    entry_exchange_order_id=f"entry:{index}",
                    initial_stop_exchange_order_id=(
                        None if is_runner else f"initial-stop:{index}"
                    ),
                    active_stop_exchange_order_id=f"stop:{index}",
                    active_stop_price=Decimal(103),
                    tp1_exchange_order_id=(None if is_runner else f"tp1:{index}"),
                    tp1_target_qty=quantity / Decimal(2),
                    tp1_filled_qty=(
                        quantity / Decimal(2) if is_runner else Decimal(0)
                    ),
                    break_even_floor_price=(Decimal(99) if is_runner else None),
                    pending_replaced_stop_exchange_order_id=None,
                    pending_stop_price=None,
                    pending_stop_watermark_ms=None,
                    runner_stop_watermark_ms=None,
                    pending_cancel_exchange_order_id=None,
                    exit_exchange_order_id=None,
                    review_id=None,
                    lifecycle_due_at_ms=None,
                    reconciliation_due_at_ms=None,
                    updated_at_ms=1_800_000_000_020 + index,
                )
            )
            await connection.execute(
                sa.insert(positions_current).values(
                    netting_domain_key=netting_domain,
                    ticket_id=ticket_id,
                    venue_id="binance-usdm",
                    account_id="subaccount-main",
                    exchange_instrument_id=f"instrument:{index}",
                    position_side="short",
                    quantity=(
                        projected_quantity
                    ),
                    average_entry_price=Decimal(100),
                    observed_at_ms=1_800_000_000_020 + index,
                    projection_version=5,
                    venue_reported_liquidation_observation_status="missing",
                )
            )
            if include_budget_reservations:
                await connection.execute(
                    sa.insert(budget_reservations).values(
                        budget_reservation_id=f"reservation:{index}",
                        ticket_id=ticket_id,
                        owner_policy_id="policy-main",
                        venue_id="binance-usdm",
                        account_id="subaccount-main",
                        reserved_notional=notional,
                        reserved_risk=risk,
                        reserved_margin=notional / Decimal(5),
                        planned_stop_risk_budget=risk,
                        risk_reservation_basis="planned_stop_distance",
                        status="active",
                        created_at_ms=1_800_000_000_010 + index,
                        released_at_ms=None,
                    )
                )
            total_notional += notional
            total_risk += risk
        await connection.execute(
            sa.update(account_exposure_current)
            .where(
                account_exposure_current.c.venue_id == "binance-usdm",
                account_exposure_current.c.account_id == "subaccount-main",
            )
            .values(
                gross_notional=total_notional + exposure_notional_delta,
                gross_risk_at_stop=total_risk + exposure_risk_delta,
                active_ticket_count=len(ticket_ids),
                projection_version=5,
                updated_at_ms=1_800_000_000_030,
            )
        )
