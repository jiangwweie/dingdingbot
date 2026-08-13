from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

import scripts.trading_kernel.verify_schema as schema_verifier
from scripts.trading_kernel.certify_readonly import _certify
from scripts.trading_kernel.verify_schema import (
    _verify_compatible_source,
    _verify_preservation,
)
from src.trading_kernel.domain.strategy_registry import (
    build_registry_semantic_hash,
    registered_strategy_contracts,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    deploy_compatible_upgrade_identity,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from tests.trading_kernel.integration.test_portfolio_admission_observability_migration import (
    SOURCE_REVISION,
    _database_url,
    _prepare_production_shaped_0002,
)
from tests.trading_kernel.integration.test_sor_v3_compatible_migration import (
    _run_migration,
    compatible_migration_engine,
)

__all__ = ["compatible_migration_engine"]

HEAD_REVISION = CURRENT_SCHEMA_REVISION
HISTORICAL_PRESERVATION_TARGET_REVISION = "0003_portfolio_admission_observability"


async def test_mig_007_nonflat_0002_is_blocked_before_migration(
    compatible_migration_engine: AsyncEngine,
) -> None:
    engine = compatible_migration_engine
    await _prepare_production_shaped_0002(engine)
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "UPDATE brc_trade_tickets SET terminal_at_ms = NULL, "
                "status = 'protected' WHERE ticket_id = 'ticket-v3-terminal'"
            )
        )

    source = await _verify_compatible_source(_database_url(engine), SOURCE_REVISION)

    assert source["status"] == "fail"
    assert source["migration_gate"]["active_tickets"] == 1
    async with engine.connect() as connection:
        assert await connection.scalar(
            sa.text("SELECT version_num FROM alembic_version")
        ) == SOURCE_REVISION


async def test_mig_008_manifest_covers_every_0002_table_column_and_value(
    compatible_migration_engine: AsyncEngine,
) -> None:
    engine = compatible_migration_engine
    await _prepare_production_shaped_0002(engine)
    await _install_source_runtime_identity(engine)
    database_url = _database_url(engine)
    async with engine.connect() as connection:
        source_shape = await connection.run_sync(
            lambda sync: {
                table_name: tuple(
                    column["name"]
                    for column in sa.inspect(sync).get_columns(table_name)
                )
                for table_name in sa.inspect(sync).get_table_names()
                if table_name != "alembic_version"
            }
        )

    source = await _verify_compatible_source(database_url, SOURCE_REVISION)
    manifest = source["preservation_manifest"]
    table_entries = {entry["table"]: entry for entry in manifest["tables"]}

    assert source["status"] == "pass", source
    assert set(table_entries) == set(source_shape)
    for table_name, columns in source_shape.items():
        entry = table_entries[table_name]
        assert tuple(entry["columns"]) == columns
        assert all(
            len(row["value_digests"]) == len(columns)
            for row in entry["rows"]
        )

    result = _run_migration(database_url, "upgrade", HEAD_REVISION)
    assert result.returncode == 0, result.stderr[-4000:]
    target = await _verify_preservation(
        database_url,
        source_revision=SOURCE_REVISION,
        expected_digest=str(manifest["digest"]),
    )

    source_digests = {
        entry["table"]: entry["digest"] for entry in manifest["tables"]
    }
    target_digests = {
        entry["table"]: entry["digest"]
        for entry in target["preservation_manifest"]["tables"]
    }
    assert target["alembic_revision"] == HEAD_REVISION
    assert target["preservation_manifest"] == manifest, {
        table_name: (source_digests[table_name], target_digests[table_name])
        for table_name in source_digests
        if source_digests[table_name] != target_digests[table_name]
    }


@pytest.mark.parametrize(
    "status",
    ("leverage_rejected", "entry_rejected", "entry_reconciled_absent"),
)
async def test_no_exposure_terminal_rejection_needs_no_fabricated_review(
    compatible_migration_engine: AsyncEngine,
    status: str,
) -> None:
    engine = compatible_migration_engine
    await _prepare_production_shaped_0002(engine)
    await _install_source_runtime_identity(engine)
    await _make_no_exposure_terminal_rejection(engine, status=status)
    database_url = _database_url(engine)

    source = await _verify_compatible_source(database_url, SOURCE_REVISION)
    result = _run_migration(
        database_url,
        "upgrade",
        HISTORICAL_PRESERVATION_TARGET_REVISION,
    )

    assert source["status"] == "pass", source
    assert source["migration_gate"]["active_tickets"] == 0
    assert source["migration_gate"]["unreviewed_terminal_tickets"] == 0
    assert source["migration_gate"]["nonterminal_aggregates"] == 0
    assert result.returncode == 0, result.stderr[-4000:]


@pytest.mark.parametrize(
    "status",
    ("leverage_rejected", "entry_rejected", "entry_reconciled_absent"),
)
async def test_no_exposure_terminal_rejection_allows_target_identity_rotation(
    compatible_migration_engine: AsyncEngine,
    status: str,
) -> None:
    engine = compatible_migration_engine
    await _prepare_production_shaped_0002(engine)
    await _install_source_runtime_identity(engine)
    await _make_no_exposure_terminal_rejection(engine, status=status)
    result = _run_migration(_database_url(engine), "upgrade", HEAD_REVISION)
    assert result.returncode == 0, result.stderr[-4000:]
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "INSERT INTO brc_schema_metadata "
                "(metadata_key, metadata_value, updated_at_ms) VALUES "
                "('registry_semantic_hash', :value, 9000) "
                "ON CONFLICT (metadata_key) DO UPDATE "
                "SET metadata_value = EXCLUDED.metadata_value, "
                "updated_at_ms = EXCLUDED.updated_at_ms"
            ),
            {
                "value": schema_verifier._CERTIFIED_0002_REGISTRY_MANIFEST_HASH,
            },
        )
        await connection.execute(
            sa.text(
                "INSERT INTO brc_account_exposure_current "
                "(venue_id, account_id, gross_notional, gross_risk_at_stop, "
                "current_reserved_margin, active_ticket_count, "
                "projection_version, updated_at_ms) VALUES "
                "('binance-usdm', 'subaccount-source-test', 0, 0, 0, 0, 0, 9000)"
            )
        )
        await connection.execute(
            sa.text(
                "INSERT INTO brc_entry_lane_current "
                "(lane_id, ticket_id, signal_event_id, status, claimed_at_ms, "
                "lease_until_ms, claim_owner, version) VALUES "
                "('global-entry', NULL, NULL, 'idle', NULL, NULL, NULL, 0) "
                "ON CONFLICT (lane_id) DO UPDATE SET ticket_id = NULL, "
                "signal_event_id = NULL, status = 'idle', claimed_at_ms = NULL, "
                "lease_until_ms = NULL, claim_owner = NULL"
            )
        )
        await connection.execute(
            sa.text(
                "INSERT INTO brc_schema_metadata "
                "(metadata_key, metadata_value, updated_at_ms) VALUES "
                "('registry_semantic_hash', :registry_hash, 9000) "
                "ON CONFLICT (metadata_key) DO UPDATE SET "
                "metadata_value = EXCLUDED.metadata_value, "
                "updated_at_ms = EXCLUDED.updated_at_ms"
            ),
            {
                "registry_hash": (
                    schema_verifier._CERTIFIED_0002_REGISTRY_MANIFEST_HASH
                )
            },
        )

    async with PostgresKernelUnitOfWork(engine) as uow:
        deployed = await deploy_compatible_upgrade_identity(
            uow,
            RuntimeAuthoritySeedRequest(
                account_id="subaccount-source-test",
                runtime_commit="a" * 40,
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=10_000,
            ),
        )

    assert deployed.runtime_commit == "a" * 40
    assert deployed.schema_revision == CURRENT_SCHEMA_REVISION


async def test_exposure_terminal_ticket_without_review_remains_blocked(
    compatible_migration_engine: AsyncEngine,
) -> None:
    engine = compatible_migration_engine
    await _prepare_production_shaped_0002(engine)
    await _install_source_runtime_identity(engine)
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "DELETE FROM brc_trade_reviews "
                "WHERE ticket_id = 'ticket-v3-terminal'"
            )
        )

    database_url = _database_url(engine)
    source = await _verify_compatible_source(database_url, SOURCE_REVISION)
    result = _run_migration(
        database_url,
        "upgrade",
        HISTORICAL_PRESERVATION_TARGET_REVISION,
    )

    assert source["status"] == "fail"
    assert source["migration_gate"]["unreviewed_terminal_tickets"] == 1
    assert result.returncode != 0
    assert "terminal Ticket Review" in result.stderr


async def test_no_exposure_terminal_rejection_with_residue_is_blocked(
    compatible_migration_engine: AsyncEngine,
) -> None:
    engine = compatible_migration_engine
    await _prepare_production_shaped_0002(engine)
    await _install_source_runtime_identity(engine)
    await _make_no_exposure_terminal_rejection(engine, status="entry_rejected")
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "UPDATE brc_trade_aggregates SET position_qty = 1 "
                "WHERE ticket_id = 'ticket-v3-terminal'"
            )
        )

    source = await _verify_compatible_source(_database_url(engine), SOURCE_REVISION)

    assert source["status"] == "fail"
    assert source["migration_gate"]["nonterminal_aggregates"] == 1


@pytest.mark.parametrize("source_drift", ("registry", "policy", "profile", "capability"))
async def test_compatible_source_requires_exact_live_0002_authority(
    compatible_migration_engine: AsyncEngine,
    source_drift: str,
) -> None:
    engine = compatible_migration_engine
    await _prepare_production_shaped_0002(engine)
    await _install_source_runtime_identity(engine)
    database_url = _database_url(engine)

    baseline = await _verify_compatible_source(database_url, SOURCE_REVISION)

    assert baseline["status"] == "pass", baseline
    for key in (
        "registry_identity",
        "owner_policy",
        "runtime_profile",
        "capabilities",
        "account_mode",
    ):
        authority = baseline[key]
        assert isinstance(authority, dict)
        assert authority["status"] == "pass", authority

    statements = {
        "registry": (
            "UPDATE brc_event_specs SET freshness_window_ms = "
            "freshness_window_ms + 1 WHERE event_spec_id = "
            "'event_spec:CPM-RO-001:CPM-LONG:v2'"
        ),
        "policy": (
            "UPDATE brc_owner_policy_current SET "
            "new_entry_submit_enabled = false"
        ),
        "profile": (
            "UPDATE brc_runtime_profiles SET position_mode = 'one_way' "
            "WHERE runtime_profile_id = 'tiny-live-v1'"
        ),
        "capability": (
            "UPDATE brc_runtime_capabilities_current SET enabled = false "
            "WHERE capability_key = 'exchange_commands'"
        ),
    }
    async with engine.begin() as connection:
        await connection.execute(sa.text(statements[source_drift]))

    drifted = await _verify_compatible_source(database_url, SOURCE_REVISION)

    assert drifted["status"] == "fail"


async def test_mig_008_one_changed_0002_value_breaks_equivalence(
    compatible_migration_engine: AsyncEngine,
) -> None:
    engine = compatible_migration_engine
    await _prepare_production_shaped_0002(engine)
    await _install_source_runtime_identity(engine)
    database_url = _database_url(engine)
    source = await _verify_compatible_source(database_url, SOURCE_REVISION)
    digest = str(source["preservation_manifest"]["digest"])
    result = _run_migration(
        database_url,
        "upgrade",
        HISTORICAL_PRESERVATION_TARGET_REVISION,
    )
    assert result.returncode == 0, result.stderr[-4000:]
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "UPDATE brc_trade_tickets SET decision_digest = "
                "'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' "
                "WHERE ticket_id = 'ticket-v3-terminal'"
            )
        )

    target = await _verify_preservation(
        database_url,
        source_revision=SOURCE_REVISION,
        expected_digest=digest,
    )

    assert target["status"] == "fail"
    assert target["preservation_manifest"]["digest"] != digest


async def test_postflight_recomputes_registry_identity_from_live_rows(
    compatible_migration_engine: AsyncEngine,
) -> None:
    """Catches trusting registry_semantic_hash metadata after one live-row drift."""

    engine = compatible_migration_engine
    await _prepare_production_shaped_0002(engine)
    await _install_source_runtime_identity(engine)
    database_url = _database_url(engine)
    result = _run_migration(database_url, "upgrade", HEAD_REVISION)
    assert result.returncode == 0, result.stderr[-4000:]
    expected_registry_hash = build_registry_semantic_hash(
        registered_strategy_contracts()
    )
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "INSERT INTO brc_schema_metadata "
                "(metadata_key, metadata_value, updated_at_ms) VALUES "
                "('registry_semantic_hash', :value, 9000) "
                "ON CONFLICT (metadata_key) DO UPDATE "
                "SET metadata_value = EXCLUDED.metadata_value, "
                "updated_at_ms = EXCLUDED.updated_at_ms"
            ),
            {
                "value": schema_verifier._CERTIFIED_0002_REGISTRY_MANIFEST_HASH,
            },
        )
        await connection.execute(
            sa.text(
                "INSERT INTO brc_account_exposure_current "
                "(venue_id, account_id, gross_notional, gross_risk_at_stop, "
                "current_reserved_margin, active_ticket_count, "
                "projection_version, updated_at_ms) VALUES "
                "('binance-usdm', 'subaccount-source-test', 0, 0, 0, 0, 0, 9000)"
            )
        )
        await connection.execute(
            sa.text(
                "INSERT INTO brc_entry_lane_current "
                "(lane_id, ticket_id, signal_event_id, status, claimed_at_ms, "
                "lease_until_ms, claim_owner, version) VALUES "
                "('global-entry', NULL, NULL, 'idle', NULL, NULL, NULL, 0)"
            )
        )
    async with PostgresKernelUnitOfWork(engine) as uow:
        await deploy_compatible_upgrade_identity(
            uow,
            RuntimeAuthoritySeedRequest(
                account_id="subaccount-source-test",
                runtime_commit="a" * 40,
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=10_000,
            ),
        )
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "INSERT INTO brc_schema_metadata "
                "(metadata_key, metadata_value, updated_at_ms) "
                "VALUES ('registry_semantic_hash', :value, 1000) "
                "ON CONFLICT (metadata_key) DO UPDATE "
                "SET metadata_value = EXCLUDED.metadata_value, "
                "updated_at_ms = EXCLUDED.updated_at_ms"
            ),
            {"value": expected_registry_hash},
        )

    baseline = await _certify(database_url, require_flat=True, now_ms=10_000)
    baseline_registry = baseline["registry_identity"]
    assert isinstance(baseline_registry, dict)
    assert baseline_registry["status"] == "pass", baseline_registry

    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "UPDATE brc_event_specs SET freshness_window_ms = "
                "freshness_window_ms + 1 "
                "WHERE event_spec_id = 'event_spec:CPM-RO-001:CPM-LONG:v3'"
            )
        )

    drifted = await _certify(database_url, require_flat=True, now_ms=10_000)
    drifted_registry = drifted["registry_identity"]
    assert isinstance(drifted_registry, dict)
    assert drifted_registry["metadata_semantic_hash"] == baseline_registry[
        "metadata_semantic_hash"
    ]
    assert drifted_registry["live_semantic_hash"] != drifted_registry[
        "expected_live_semantic_hash"
    ]
    assert drifted_registry["status"] == "fail"


async def test_preservation_proof_is_persisted_in_postgresql_and_identity_bound(
    compatible_migration_engine: AsyncEngine,
) -> None:
    """Catches treating a release-local marker as proof for any target database."""

    engine = compatible_migration_engine
    await _prepare_production_shaped_0002(engine)
    await _install_source_runtime_identity(engine)
    database_url = _database_url(engine)
    source = await _verify_compatible_source(database_url, SOURCE_REVISION)
    digest = str(source["preservation_manifest"]["digest"])
    result = _run_migration(
        database_url,
        "upgrade",
        HISTORICAL_PRESERVATION_TARGET_REVISION,
    )
    assert result.returncode == 0, result.stderr[-4000:]

    recorded = await schema_verifier._record_preservation_proof(
        database_url,
        source_revision=SOURCE_REVISION,
        expected_digest=digest,
    )

    assert recorded["status"] == "pass", recorded
    proof = recorded["preservation_proof"]
    assert isinstance(proof, dict)
    proof_digest = str(proof["proof_digest"])
    verified = await schema_verifier._verify_preservation_proof(
        database_url,
        source_revision=SOURCE_REVISION,
        expected_digest=digest,
        expected_proof_digest=proof_digest,
    )
    assert verified["status"] == "pass", verified

    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "UPDATE brc_schema_metadata SET metadata_value = "
                "'postgresql:restored-cluster:999999' "
                "WHERE metadata_key = 'preservation_database_identity'"
            )
        )

    restored_database = await schema_verifier._verify_preservation_proof(
        database_url,
        source_revision=SOURCE_REVISION,
        expected_digest=digest,
        expected_proof_digest=proof_digest,
    )
    assert restored_database["status"] == "fail"


async def test_historical_preservation_proof_survives_runtime_projection_change(
    compatible_migration_engine: AsyncEngine,
) -> None:
    """Catches re-scanning mutable current projections during 0003 fix-forward."""

    engine = compatible_migration_engine
    await _prepare_production_shaped_0002(engine)
    await _install_source_runtime_identity(engine)
    database_url = _database_url(engine)
    source = await _verify_compatible_source(database_url, SOURCE_REVISION)
    digest = str(source["preservation_manifest"]["digest"])
    result = _run_migration(
        database_url,
        "upgrade",
        HISTORICAL_PRESERVATION_TARGET_REVISION,
    )
    assert result.returncode == 0, result.stderr[-4000:]

    recorded = await schema_verifier._record_preservation_proof(
        database_url,
        source_revision=SOURCE_REVISION,
        expected_digest=digest,
    )
    proof = recorded["preservation_proof"]
    assert isinstance(proof, dict)

    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "UPDATE brc_schema_metadata SET metadata_value = :runtime_commit "
                "WHERE metadata_key = 'runtime_commit'"
            ),
            {"runtime_commit": "d" * 40},
        )

    verified = await schema_verifier._verify_preservation_proof(
        database_url,
        source_revision=SOURCE_REVISION,
        expected_digest=digest,
        expected_proof_digest=str(proof["proof_digest"]),
    )

    assert verified["status"] == "pass", verified


async def _install_source_runtime_identity(engine: AsyncEngine) -> None:
    values = {
        "runtime_commit": "b" * 40,
        "schema_revision": SOURCE_REVISION,
        "seed_identity": "sha256:" + "c" * 64,
    }
    async with engine.begin() as connection:
        for key, value in values.items():
            await connection.execute(
                sa.text(
                    "INSERT INTO brc_schema_metadata "
                    "(metadata_key, metadata_value, updated_at_ms) "
                    "VALUES (:key, :value, 1000) "
                    "ON CONFLICT (metadata_key) DO UPDATE "
                    "SET metadata_value = EXCLUDED.metadata_value, "
                    "updated_at_ms = EXCLUDED.updated_at_ms"
                ),
                {"key": key, "value": value},
            )


async def _make_no_exposure_terminal_rejection(
    engine: AsyncEngine,
    *,
    status: str,
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "UPDATE brc_trade_tickets SET status = :status, "
                "active_netting_domain_key = NULL, terminal_at_ms = 4000 "
                "WHERE ticket_id = 'ticket-v3-terminal'"
            ),
            {"status": status},
        )
        await connection.execute(
            sa.text(
                "UPDATE brc_trade_aggregates SET status = :status, "
                "entry_lane_held = false, position_qty = 0, protected_qty = 0, "
                "entry_exchange_order_id = NULL, "
                "initial_stop_exchange_order_id = NULL, "
                "active_stop_exchange_order_id = NULL, "
                "tp1_exchange_order_id = NULL, "
                "pending_replaced_stop_exchange_order_id = NULL, "
                "pending_cancel_exchange_order_id = NULL, "
                "exit_exchange_order_id = NULL "
                "WHERE ticket_id = 'ticket-v3-terminal'"
            ),
            {"status": status},
        )
        await connection.execute(
            sa.text(
                "UPDATE brc_positions_current SET quantity = 0 "
                "WHERE ticket_id = 'ticket-v3-terminal'"
            )
        )
        await connection.execute(
            sa.text(
                "UPDATE brc_budget_reservations SET status = 'released', "
                "released_at_ms = 4000 "
                "WHERE ticket_id = 'ticket-v3-terminal'"
            )
        )
        await connection.execute(
            sa.text(
                "UPDATE brc_exchange_commands SET status = 'rejected', "
                "completed_at_ms = 3900 "
                "WHERE ticket_id = 'ticket-v3-terminal'"
            )
        )
        await connection.execute(
            sa.text(
                "UPDATE brc_runtime_incidents SET status = 'resolved', "
                "resolved_at_ms = 4000 "
                "WHERE ticket_id = 'ticket-v3-terminal'"
            )
        )
        await connection.execute(
            sa.text(
                "DELETE FROM brc_trade_reviews "
                "WHERE ticket_id = 'ticket-v3-terminal'"
            )
        )
