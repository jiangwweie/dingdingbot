from __future__ import annotations

import json
from contextlib import suppress
from decimal import Decimal
from uuid import uuid4

import asyncpg
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from scripts.trading_kernel.verify_schema import (
    _certify_r4_recovery,
    _verify_compatible_source,
    _verify_preservation,
)
from src.trading_kernel.application.owner_console.models import (
    InstrumentCenterQuery,
    StrategySummaryQuery,
)
from src.trading_kernel.infrastructure.pg_models import (
    admission_decisions,
    instruments,
    owner_authorizations,
    owner_policy_current,
    runtime_capabilities_current,
    runtime_scopes_current,
    schema_metadata,
    shadow_outcomes_current,
    signal_events,
    strategy_entry_control_events,
    strategy_entry_controls_current,
    strategy_universe_current,
    strategy_universe_members,
    strategy_universe_versions,
)
from src.trading_kernel.infrastructure.pg_owner_read_repository import (
    PostgresOwnerReadRepository,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    ArmAcceptancePolicyRequest,
    RuntimeAuthoritySeedRequest,
    arm_acceptance_policy,
    deploy_compatible_upgrade_identity,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
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

SOURCE_SCHEMA_REVISION = "0004_owner_control_plane"


@pytest.mark.asyncio
async def test_flat_0004_upgrade_installs_unified_tradfi_live_authority() -> None:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    await admin.execute(f'CREATE DATABASE "{database_name}"')
    database_url = _database_url(database_name)
    engine = create_async_engine(database_url)
    try:
        _run_alembic(database_url, "upgrade", SOURCE_SCHEMA_REVISION)
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id="owner-account",
                    runtime_commit="4" * 40,
                    schema_revision=SOURCE_SCHEMA_REVISION,
                    seeded_at_ms=1_800_000_000_000,
                ),
            )
        async with PostgresKernelUnitOfWork(engine) as uow:
            enabled = await arm_acceptance_policy(
                uow,
                ArmAcceptancePolicyRequest(armed_at_ms=1_800_000_000_100),
            )
        assert enabled.new_entry_submit_enabled
        async with engine.begin() as connection:
            await connection.execute(
                sa.update(owner_policy_current)
                .where(owner_policy_current.c.owner_policy_id == "policy-main")
                .values(policy_version=9, updated_at_ms=1_800_000_000_120)
            )
        await _install_source_crypto_universe(engine)
        await _install_source_portfolio_shadow(engine)

        source = await _verify_compatible_source(
            database_url,
            SOURCE_SCHEMA_REVISION,
        )
        assert source["status"] == "pass", json.dumps(source, default=str)
        preservation_digest = str(source["preservation_manifest"]["digest"])
        _run_alembic(database_url, "upgrade", CURRENT_SCHEMA_REVISION)
        preserved = await _verify_preservation(
            database_url,
            source_revision=SOURCE_SCHEMA_REVISION,
            expected_digest=preservation_digest,
        )
        assert preserved["status"] == "pass", preserved
        async with PostgresKernelUnitOfWork(engine) as uow:
            deployed = await deploy_compatible_upgrade_identity(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id="owner-account",
                    runtime_commit="5" * 40,
                    schema_revision=CURRENT_SCHEMA_REVISION,
                    seeded_at_ms=1_800_000_000_300,
                ),
            )
        assert deployed.schema_revision == CURRENT_SCHEMA_REVISION

        async with engine.connect() as connection:
            policies = {
                str(row["owner_policy_id"]): row
                for row in (
                    await connection.execute(
                        sa.select(owner_policy_current).order_by(
                            owner_policy_current.c.owner_policy_id
                        )
                    )
                ).mappings()
            }
            assert set(policies) == {"policy-main"}
            assert policies["policy-main"]["policy_version"] == 11
            assert not policies["policy-main"]["new_entry_submit_enabled"]
            mappings = policies["policy-main"]["scope"][
                "event_runtime_profiles"
            ]
            assert len(mappings) == 8
            assert {
                item["runtime_profile_id"] for item in mappings
            } == {"tiny-live-v1", "tradfi-equity-usdm-v1"}

            controls = {
                str(row["strategy_group_id"]): row
                for row in (
                    await connection.execute(
                        sa.select(strategy_entry_controls_current).order_by(
                            strategy_entry_controls_current.c.strategy_group_id
                        )
                    )
                ).mappings()
            }
            assert len(controls) == 6
            assert controls["SOR-001"]["entry_state"] == "paused"
            assert controls["SOR-001"]["control_version"] == 2
            assert controls["SOR-US-EQ-PERP-001"]["entry_state"] == "paused"
            assert controls["SOR-US-EQ-PERP-001"]["control_version"] == 1

            assert await connection.scalar(
                sa.select(sa.func.count()).select_from(runtime_capabilities_current).where(
                    runtime_capabilities_current.c.schema_revision
                    == CURRENT_SCHEMA_REVISION
                )
            ) == 2
            assert await connection.scalar(
                sa.select(schema_metadata.c.metadata_value).where(
                    schema_metadata.c.metadata_key == "schema_revision"
                )
            ) == CURRENT_SCHEMA_REVISION
            assert await connection.scalar(
                sa.select(strategy_universe_current.c.universe_version_id).where(
                    strategy_universe_current.c.event_spec_id
                    == "event_spec:SOR-001:SOR-LONG:v4"
                )
            ) == "universe:source-sor-long:v1"
            preserved_shadow = (
                await connection.execute(
                    sa.select(shadow_outcomes_current).where(
                        shadow_outcomes_current.c.shadow_outcome_id
                        == "shadow:source:portfolio-rejection"
                    )
                )
            ).mappings().one()
            assert preserved_shadow["signal_event_id"] == "signal:source:rejected"
            assert preserved_shadow["source_kind"] == "portfolio_rejection"
            assert preserved_shadow["admission_decision_id"] == "admission:source:rejected"
            assert preserved_shadow["status"] == "completed"
            assert preserved_shadow["max_favorable_price"] == 104
            assert preserved_shadow["max_adverse_price"] == 99
            assert preserved_shadow["mfe_r"] == 2
            assert preserved_shadow["mae_r"] == Decimal("0.5")
            assert preserved_shadow["projection_version"] == 2

            facts = await PostgresOwnerReadRepository(
                connection
            ).read_strategy_page_facts(
                StrategySummaryQuery(
                    from_ms=1_799_000_000_000,
                    to_ms=1_801_000_000_000,
                    view="current",
                )
            )
            by_group = {item.strategy_group_id: item for item in facts.versions}
            crypto_events = by_group["SOR-001"].product_events
            tradfi_events = by_group["SOR-US-EQ-PERP-001"].product_events
            assert {item.owner_policy_id for item in crypto_events} == {"policy-main"}
            assert any(
                item.active_universe_version_id == "universe:source-sor-long:v1"
                and item.active_exchange_instrument_ids
                == ("binance-usdm:BTCUSDT:perpetual",)
                for item in crypto_events
            )
            assert {item.owner_policy_id for item in tradfi_events} == {
                "policy-main"
            }
            assert all(
                item.active_universe_version_id is None for item in tradfi_events
            )
            instrument_page = await PostgresOwnerReadRepository(
                connection
            ).read_instrument_center(
                InstrumentCenterQuery(
                    product_family="tradfi_equity_perpetual",
                )
            )
            assert {item.event_id for item in instrument_page.universes} == {
                "SOR-US-LONG-15M",
                "SOR-US-SHORT-15M",
            }

        recovery = await _certify_r4_recovery(
            database_url,
            legacy_preservation_digest=preservation_digest,
        )
        assert recovery["target_shape"]["status"] == "pass", recovery
        assert recovery["migration_gate"] == {
            key: 0 for key in recovery["migration_gate"]
        }
        terminal_digest = str(recovery["terminal_lineage_manifest"]["digest"])

        async with engine.begin() as connection:
            await connection.execute(
                sa.update(owner_policy_current)
                .where(owner_policy_current.c.owner_policy_id == "policy-main")
                .values(updated_at_ms=1_800_000_000_400)
            )
        refreshed = await _certify_r4_recovery(
            database_url,
            legacy_preservation_digest=preservation_digest,
        )
        assert refreshed["target_shape"]["status"] == "pass", refreshed
        assert str(refreshed["terminal_lineage_manifest"]["digest"]) == terminal_digest

        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "UPDATE brc_signal_events SET observed_at_ms = observed_at_ms + 1"
                )
            )
        tampered = await _certify_r4_recovery(
            database_url,
            legacy_preservation_digest=preservation_digest,
        )
        assert str(tampered["terminal_lineage_manifest"]["digest"]) != terminal_digest
    finally:
        await engine.dispose()
        with suppress(asyncpg.UndefinedObjectError):
            await admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = $1 AND pid <> pg_backend_pid()",
                database_name,
            )
            await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await admin.close()


async def _install_source_crypto_universe(engine) -> None:
    digest = "sha256:" + "a" * 64
    event_spec_id = "event_spec:SOR-001:SOR-LONG:v4"
    universe_version_id = "universe:source-sor-long:v1"
    instrument_id = "binance-usdm:BTCUSDT:perpetual"
    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(owner_authorizations).values(
                authorization_id="owner-authorization:source-sor-pause",
                purpose="strategy_pause",
                owner_identity="owner",
                authentication_strength="session",
                request_digest="sha256:" + "b" * 64,
                target_scope={"strategy_group_id": "SOR-001"},
                idempotency_key="owner-request:source-sor-pause",
                authorized_at_ms=1_800_000_000_150,
            )
        )
        await connection.execute(
            sa.insert(strategy_entry_control_events).values(
                strategy_entry_control_event_id="strategy-control-event:source-sor-pause",
                strategy_group_id="SOR-001",
                control_version=2,
                operation="pause",
                target_state="paused",
                authorization_id="owner-authorization:source-sor-pause",
                reason="owner_manual_pause",
                payload={},
                created_at_ms=1_800_000_000_150,
            )
        )
        await connection.execute(
            sa.update(strategy_entry_controls_current)
            .where(strategy_entry_controls_current.c.strategy_group_id == "SOR-001")
            .values(
                entry_state="paused",
                control_version=2,
                last_event_id="strategy-control-event:source-sor-pause",
                reason="owner_manual_pause",
                updated_at_ms=1_800_000_000_150,
            )
        )
        await connection.execute(
            sa.insert(instruments).values(
                exchange_instrument_id=instrument_id,
                venue_id="binance-usdm",
                asset_class="crypto",
                venue_symbol="BTCUSDT",
                contract_kind="perpetual",
                status="active",
            )
        )
        await connection.execute(
            sa.insert(strategy_universe_versions).values(
                universe_version_id=universe_version_id,
                strategy_group_id="SOR-001",
                event_spec_id=event_spec_id,
                universe_version=1,
                semantic_digest=digest,
                lifecycle_state="active",
                installed_at_ms=1_800_000_000_160,
                activated_at_ms=1_800_000_000_170,
                retired_at_ms=None,
                abandoned_at_ms=None,
                abandon_reason_code=None,
            )
        )
        await connection.execute(
            sa.insert(strategy_universe_members).values(
                universe_version_id=universe_version_id,
                exchange_instrument_id=instrument_id,
            )
        )
        await connection.execute(
            sa.insert(strategy_universe_current).values(
                event_spec_id=event_spec_id,
                universe_version_id=universe_version_id,
                semantic_digest=digest,
                lifecycle_state="active",
                activation_generation=1,
                activated_at_ms=1_800_000_000_170,
            )
        )
        await connection.execute(
            sa.insert(runtime_scopes_current).values(
                runtime_scope_id="runtime-scope:source-sor-long:btc",
                strategy_group_id="SOR-001",
                strategy_version_id="sgv:SOR-001:v4",
                event_spec_id=event_spec_id,
                runtime_profile_id="tiny-live-v1",
                owner_policy_id="policy-main",
                exchange_instrument_id=instrument_id,
                position_side="long",
                universe_version_id=universe_version_id,
                universe_semantic_digest=digest,
                lifecycle_state="active",
                observation_enabled=True,
                entry_enabled=True,
                scope_version=1,
                warm_closed_bar_time_ms=1_800_000_000_160,
                warm_completed_at_ms=1_800_000_000_165,
                warm_readiness_digest="sha256:" + "c" * 64,
                warm_valid_until_ms=1_800_000_900_000,
                observation_generation=0,
                updated_at_ms=1_800_000_000_170,
            )
        )


async def _install_source_portfolio_shadow(engine) -> None:
    digest = "sha256:" + "d" * 64
    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(signal_events).values(
                signal_event_id="signal:source:rejected",
                exposure_episode_id="episode:source:rejected",
                runtime_scope_id="runtime-scope:source-sor-long:btc",
                runtime_scope_version=1,
                strategy_group_id="SOR-001",
                strategy_version_id="sgv:SOR-001:v4",
                event_spec_id="event_spec:SOR-001:SOR-LONG:v4",
                universe_version_id="universe:source-sor-long:v1",
                universe_semantic_digest="sha256:" + "a" * 64,
                exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
                position_side="long",
                fact_digest=digest,
                occurred_at_ms=1_800_000_000_180,
                observed_at_ms=1_800_000_000_180,
                expires_at_ms=1_800_000_900_000,
            )
        )
        await connection.execute(
            sa.insert(admission_decisions).values(
                admission_decision_id="admission:source:rejected",
                signal_event_id="signal:source:rejected",
                exposure_episode_id="episode:source:rejected",
                strategy_group_id="SOR-001",
                strategy_version_id="sgv:SOR-001:v4",
                event_spec_id="event_spec:SOR-001:SOR-LONG:v4",
                universe_version_id="universe:source-sor-long:v1",
                universe_semantic_digest="sha256:" + "a" * 64,
                runtime_profile_id="tiny-live-v1",
                runtime_scope_id="runtime-scope:source-sor-long:btc",
                runtime_scope_version=1,
                owner_policy_id="policy-main",
                owner_policy_version=9,
                venue_id="binance-usdm",
                account_id="owner-account",
                exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
                position_side="long",
                exposure_family="opening_range",
                candidate_rank=1,
                candidate_count=1,
                candidate_set_digest=digest,
                candidate_set_summary={},
                portfolio_usage={},
                decision_status="rejected",
                first_blocker="gross_stop_risk_exhausted",
                binding_constraint="gross_stop_risk_exhausted",
                capacity_claim_id=None,
                ticket_id=None,
                entry_admission_snapshot_digest=None,
                decision_digest="sha256:" + "e" * 64,
                decided_at_ms=1_800_000_000_200,
            )
        )
        await connection.execute(
            sa.insert(shadow_outcomes_current).values(
                shadow_outcome_id="shadow:source:portfolio-rejection",
                admission_decision_id="admission:source:rejected",
                status="completed",
                evaluation_kind="fixed_horizon_excursion_v1",
                exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
                position_side="long",
                timeframe="15m",
                entry_reference_price=100,
                initial_stop_price=98,
                initial_risk_per_unit=2,
                horizon_start_ms=1_800_000_000_200,
                horizon_end_ms=1_800_007_200_200,
                claim_owner=None,
                claim_token=None,
                lease_until_ms=None,
                max_favorable_price=104,
                max_adverse_price=99,
                mfe_r=2,
                mae_r=Decimal("0.5"),
                observed_through_ms=1_800_007_200_200,
                completion_reason="horizon_complete",
                projection_version=2,
                created_at_ms=1_800_000_000_200,
                completed_at_ms=1_800_007_200_200,
            )
        )
