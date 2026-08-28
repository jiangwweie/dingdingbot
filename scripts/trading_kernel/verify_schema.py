#!/usr/bin/env python3
"""Verify the exact clean trading-kernel PostgreSQL table allowlist."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sys
from collections.abc import Mapping
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from migrations.trading_kernel import v4_schema
from src.trading_kernel.domain.exit_policy import registered_exit_policies
from src.trading_kernel.domain.instrument_selection import (
    CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS,
)
from src.trading_kernel.domain.strategy_registry import (
    build_registry_semantic_hash,
    registered_strategy_contracts,
)
from src.trading_kernel.infrastructure.pg_models import metadata
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    OWNER_POLICY_ID,
    RUNTIME_PROFILE_ID,
)
from src.trading_kernel.infrastructure.runtime_identity import (
    CURRENT_SCHEMA_REVISION,
)

SCHEMA = "brc.trading_kernel.schema_verification.v1"
PRESERVATION_SCHEMA = "brc.trading_kernel.0002_preservation.v1"
PRESERVATION_PROOF_SCHEMA = "brc.trading_kernel.0002_preservation_proof.v1"
R4_RECOVERY_SCHEMA = "brc.trading_kernel.0005_recovery_certification.v1"
EXPECTED_ALEMBIC_REVISION = CURRENT_SCHEMA_REVISION
COMPATIBLE_SOURCE_REVISION = "0002_sor_v3_strategy_group_capacity"
OWNER_CONTROL_SOURCE_REVISION = "0003_portfolio_admission_observability"
TRADFI_INSTRUMENT_SOURCE_REVISION = "0004_owner_control_plane"
DYNAMIC_SELECTION_SOURCE_REVISION = "0005_tradfi_instrument_center"
HISTORICAL_PRESERVATION_TARGET_REVISION = "0003_portfolio_admission_observability"
_OWNER_CONTROL_TABLES = frozenset(
    {
        "brc_owner_authorizations",
        "brc_strategy_entry_control_events",
        "brc_strategy_entry_controls_current",
        "brc_owner_control_operation_events",
        "brc_owner_control_operations_current",
    }
)
_TRADFI_INSTRUMENT_TABLES = frozenset(
    {
        "brc_event_product_compatibility",
        "brc_instrument_product_profiles",
        "brc_instrument_product_current",
    }
)
_TRADFI_SHADOW_COLUMNS = frozenset(
    {
        "signal_event_id",
        "source_kind",
        "take_profit_price",
        "opening_range_boundary_price",
        "session_exit_deadline_ms",
        "mark_price",
        "index_price",
        "funding_rate",
        "best_bid_price",
        "best_ask_price",
        "best_bid_quantity",
        "best_ask_quantity",
        "spread_bps",
        "mark_index_deviation_bps",
        "first_path",
        "first_path_at_ms",
        "observed_bar_count",
    }
)
_DYNAMIC_SELECTION_TABLES = frozenset(
    {
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
)
_DYNAMIC_SELECTION_ADDED_COLUMNS = {
    "brc_strategy_universe_versions": (
        "source_kind",
        "materialization_generation_id",
    ),
    "brc_signal_events": ("selection_authority_id",),
    "brc_capacity_claims": ("selection_authority_id",),
    "brc_admission_decisions": ("selection_authority_id",),
    "brc_trade_tickets": ("selection_authority_id",),
    "brc_trade_aggregates": (
        "entry_vacuum_id",
        "entry_materialization_kind",
    ),
}
_DYNAMIC_SELECTION_ADDITIVE_EXISTING_TABLES = frozenset(
    {
        "brc_instruments",
        "brc_instrument_product_profiles",
    }
)
_EXIT_PROFILE_TABLES = frozenset(
    {
        "brc_event_exit_profile_bindings",
        "brc_event_exit_profile_binding_current",
        "brc_event_exit_profile_binding_events",
    }
)
_EXIT_PROFILE_ADDED_COLUMNS = {
    "brc_exit_policies": ("profile_schema_version",),
    "brc_capacity_claims": (
        "exit_binding_id",
        "exit_binding_semantic_hash",
        "exit_binding_authority_version",
    ),
    "brc_trade_tickets": (
        "exit_binding_id",
        "exit_binding_semantic_hash",
        "exit_binding_authority_version",
    ),
}
_R4_TERMINAL_LINEAGE_TABLES = frozenset(
    {
        "brc_admission_decisions",
        "brc_capacity_claims",
        "brc_exchange_commands",
        "brc_owner_authorizations",
        "brc_owner_control_operation_events",
        "brc_owner_policy_events",
        "brc_signal_events",
        "brc_signal_fact_snapshots",
        "brc_strategy_entry_control_events",
        "brc_trade_events",
        "brc_trade_aggregates",
        "brc_trade_reviews",
        "brc_trade_tickets",
    }
)
_PRESERVATION_PROOF_METADATA_KEYS = (
    "preservation_source_revision",
    "preservation_target_revision",
    "preservation_digest",
    "preservation_database_identity",
    "preservation_proof_digest",
)
_PORTFOLIO_MIGRATION = importlib.import_module(
    "migrations.trading_kernel.versions.0003_portfolio_admission_observability"
)
_CERTIFIED_0002_REGISTRY_MANIFEST_HASH = str(
    _PORTFOLIO_MIGRATION.CERTIFIED_0002_REGISTRY_MANIFEST_HASH
)
_CERTIFIED_0002_REGISTRY_MANIFEST_COUNTS = dict(
    _PORTFOLIO_MIGRATION.CERTIFIED_0002_REGISTRY_MANIFEST_COUNTS
)
_SOURCE_VERSION_IDS = frozenset(
    {
        "sgv:BRF2-001:v2",
        "sgv:CPM-RO-001:v2",
        "sgv:MI-001:v2",
        "sgv:MPG-001:v2",
        "sgv:SOR-001:v3",
    }
)
_SOURCE_EVENT_IDS = frozenset(
    {
        "event_spec:BRF2-001:BRF2-SHORT:v2",
        "event_spec:CPM-RO-001:CPM-LONG:v2",
        "event_spec:MI-001:MI-LONG:v2",
        "event_spec:MPG-001:MPG-LONG:v2",
        "event_spec:SOR-001:SOR-LONG:v3",
        "event_spec:SOR-001:SOR-SHORT:v3",
    }
)
_TARGET_CONTRACTS = registered_strategy_contracts()
_TARGET_VERSION_IDS = frozenset(
    contract.strategy_version_id for contract in _TARGET_CONTRACTS
)
_TARGET_EVENT_IDS = frozenset(contract.event_spec_id for contract in _TARGET_CONTRACTS)
_TARGET_EXIT_POLICY_IDS = frozenset(
    policy.exit_policy_id for policy in registered_exit_policies()
)
_TARGET_FACT_IDS = frozenset(
    fact.fact_definition_id
    for contract in _TARGET_CONTRACTS
    for fact in (*contract.required_facts, *contract.disable_facts)
)
_SOURCE_GROUP_POINTERS = {
    "BRF2-001": "sgv:BRF2-001:v2",
    "CPM-RO-001": "sgv:CPM-RO-001:v2",
    "MI-001": "sgv:MI-001:v2",
    "MPG-001": "sgv:MPG-001:v2",
    "SOR-001": "sgv:SOR-001:v3",
}
_SOURCE_POLICY_EVENT_IDS = tuple(sorted(_SOURCE_EVENT_IDS))
_SOURCE_0002_ADDED_COLUMNS = {
    "brc_signal_events": ("exposure_episode_id",),
    "brc_owner_policy_current": ("max_strategy_group_concurrent_tickets",),
    "brc_capacity_claims": (
        "exit_policy_id",
        "exit_policy_semantic_hash",
        "active_strategy_group_ticket_count_at_claim",
        "max_strategy_group_concurrent_tickets",
        "remaining_strategy_group_slots_at_claim",
        "pre_tp1_reclaim_price",
        "exposure_session_end_ms",
    ),
    "brc_trade_tickets": (
        "exit_policy_id",
        "exit_policy_semantic_hash",
        "pre_tp1_reclaim_price",
        "exposure_session_end_ms",
    ),
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""),
        help="PostgreSQL SQLAlchemy URL; defaults to TRADING_KERNEL_DATABASE_URL",
    )
    parser.add_argument(
        "--compatible-source-revision",
        help="Verify an exact flat source revision and emit its v4 preservation manifest.",
    )
    parser.add_argument(
        "--preserve-source-revision",
        help="Recompute one source-revision manifest after migration.",
    )
    parser.add_argument(
        "--expected-preservation-digest",
        help="Expected sha256 digest for post-migration preservation verification.",
    )
    parser.add_argument(
        "--deployment-revision",
        action="store_true",
        help="Report only the exact 0002/0003 deployment phase revision.",
    )
    parser.add_argument(
        "--record-preservation-proof",
        action="store_true",
        help="Persist an exact database-identity-bound 0002 preservation proof.",
    )
    parser.add_argument(
        "--verify-preservation-proof",
        action="store_true",
        help="Verify the stored database-bound preservation proof.",
    )
    parser.add_argument(
        "--verify-stored-preservation-proof",
        action="store_true",
        help="Verify only the immutable stored proof without re-scanning projections.",
    )
    parser.add_argument(
        "--expected-preservation-proof-digest",
        help="Release marker proof digest expected from PostgreSQL metadata.",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Emit only bounded preservation-manifest metadata for deployment RPC.",
    )
    parser.add_argument(
        "--certify-r4-recovery",
        action="store_true",
        help=(
            "Certify the one 0005 fix-forward recovery after a frozen 0004 "
            "full-projection manifest drifted."
        ),
    )
    parser.add_argument(
        "--legacy-preservation-digest",
        help="Frozen 0004 full-projection digest bound into R4 recovery evidence.",
    )
    return parser


async def _verify(database_url: str) -> dict[str, object]:
    if not database_url.startswith("postgresql+asyncpg://"):
        raise ValueError("database URL must use postgresql+asyncpg")
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            revision = str(
                (
                    await connection.execute(
                        text("SELECT version_num FROM alembic_version")
                    )
                ).scalar_one()
            )
            actual_tables = {
                str(name)
                for name in (
                    await connection.execute(
                        text(
                            """
                            SELECT relname
                              FROM pg_catalog.pg_class
                             WHERE relkind IN ('r', 'p')
                               AND relnamespace = current_schema()::regnamespace
                               AND relname LIKE 'brc\\_%' ESCAPE '\\'
                             ORDER BY relname
                            """
                        )
                    )
                ).scalars()
            }
            await connection.rollback()
    finally:
        await engine.dispose()

    expected_tables = set(metadata.tables)
    missing_tables = sorted(expected_tables - actual_tables)
    unexpected_tables = sorted(actual_tables - expected_tables)
    passed = (
        revision == EXPECTED_ALEMBIC_REVISION
        and not missing_tables
        and not unexpected_tables
    )
    return {
        "schema": SCHEMA,
        "status": "pass" if passed else "fail",
        "alembic_revision": revision,
        "expected_table_count": len(expected_tables),
        "actual_table_count": len(actual_tables),
        "missing_tables": missing_tables,
        "unexpected_tables": unexpected_tables,
    }


async def _verify_compatible_source(
    database_url: str,
    source_revision: str,
) -> dict[str, object]:
    if source_revision == DYNAMIC_SELECTION_SOURCE_REVISION:
        return await _verify_dynamic_selection_source(
            database_url,
            source_revision,
        )
    if source_revision == TRADFI_INSTRUMENT_SOURCE_REVISION:
        return await _verify_tradfi_instrument_source(
            database_url,
            source_revision,
        )
    if source_revision == OWNER_CONTROL_SOURCE_REVISION:
        return await _verify_owner_control_source(database_url, source_revision)
    if source_revision != COMPATIBLE_SOURCE_REVISION:
        raise ValueError("compatible source revision is unsupported")
    engine = _create_engine(database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            revision = await _alembic_revision(connection)
            shape = await _verify_exact_metadata_shape(
                connection,
                expected_columns=_source_0002_table_columns(),
            )
            migration_gate = await _migration_gate(connection)
            manifest = await _source_preservation_manifest(
                connection,
                revision=revision,
            )
            runtime_identity = await _runtime_identity(connection)
            registry_identity = await _certified_0002_registry_identity(connection)
            owner_policy = await _certified_0002_owner_policy(connection)
            runtime_profile = await _certified_0002_runtime_profile(connection)
            capabilities = await _certified_0002_capabilities(
                connection,
                runtime_identity=runtime_identity,
            )
            account_mode = {
                "status": (
                    "pass"
                    if runtime_profile["status"] == "pass"
                    and runtime_profile["position_mode"] == "independent_sides"
                    and owner_policy["status"] == "pass"
                    and owner_policy["supported_margin_mode"] == "cross"
                    else "fail"
                ),
                "position_mode": runtime_profile["position_mode"],
                "margin_mode": owner_policy["supported_margin_mode"],
            }
            await connection.rollback()
    finally:
        await engine.dispose()
    passed = bool(
        revision == source_revision
        and shape["status"] == "pass"
        and all(int(value) == 0 for value in migration_gate.values())
        and all(runtime_identity.values())
        and runtime_identity["schema_revision"] == source_revision
        and registry_identity["status"] == "pass"
        and owner_policy["status"] == "pass"
        and runtime_profile["status"] == "pass"
        and capabilities["status"] == "pass"
        and account_mode["status"] == "pass"
    )
    return {
        "schema": SCHEMA,
        "status": "pass" if passed else "fail",
        "alembic_revision": revision,
        "source_shape": shape,
        "runtime_identity": runtime_identity,
        "registry_identity": registry_identity,
        "owner_policy": owner_policy,
        "runtime_profile": runtime_profile,
        "capabilities": capabilities,
        "account_mode": account_mode,
        "migration_gate": migration_gate,
        "preservation_manifest": manifest,
    }


async def _verify_preservation(
    database_url: str,
    *,
    source_revision: str,
    expected_digest: str,
) -> dict[str, object]:
    if source_revision not in {
        COMPATIBLE_SOURCE_REVISION,
        OWNER_CONTROL_SOURCE_REVISION,
        TRADFI_INSTRUMENT_SOURCE_REVISION,
        DYNAMIC_SELECTION_SOURCE_REVISION,
    }:
        raise ValueError("preservation source revision is unsupported")
    if not _is_sha256_identity(expected_digest):
        raise ValueError(
            "expected preservation digest must be an exact sha256 identity"
        )
    engine = _create_engine(database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            revision = await _alembic_revision(connection)
            if source_revision == DYNAMIC_SELECTION_SOURCE_REVISION:
                manifest = await _dynamic_selection_preservation_manifest(connection)
            elif source_revision == TRADFI_INSTRUMENT_SOURCE_REVISION:
                manifest = await _tradfi_instrument_preservation_manifest(connection)
            elif source_revision == OWNER_CONTROL_SOURCE_REVISION:
                manifest = await _owner_control_preservation_manifest(connection)
            else:
                manifest = await _source_preservation_manifest(
                    connection,
                    revision=revision,
                )
            await connection.rollback()
    finally:
        await engine.dispose()
    allowed_targets_by_source: dict[str, frozenset[str]] = {
        COMPATIBLE_SOURCE_REVISION: frozenset(
            {
                HISTORICAL_PRESERVATION_TARGET_REVISION,
                "0004_owner_control_plane",
                "0005_tradfi_instrument_center",
                "0006_sor_dynamic_selection_v0",
                EXPECTED_ALEMBIC_REVISION,
            }
        ),
        OWNER_CONTROL_SOURCE_REVISION: frozenset(
            {
                "0004_owner_control_plane",
                "0005_tradfi_instrument_center",
                "0006_sor_dynamic_selection_v0",
                EXPECTED_ALEMBIC_REVISION,
            }
        ),
        TRADFI_INSTRUMENT_SOURCE_REVISION: frozenset(
            {
                "0005_tradfi_instrument_center",
                "0006_sor_dynamic_selection_v0",
                EXPECTED_ALEMBIC_REVISION,
            }
        ),
        DYNAMIC_SELECTION_SOURCE_REVISION: frozenset(
            {
                "0006_sor_dynamic_selection_v0",
                EXPECTED_ALEMBIC_REVISION,
            }
        ),
    }
    allowed_target_revisions = allowed_targets_by_source[source_revision]
    passed = bool(
        revision in allowed_target_revisions and manifest["digest"] == expected_digest
    )
    return {
        "schema": SCHEMA,
        "status": "pass" if passed else "fail",
        "alembic_revision": revision,
        "source_revision": source_revision,
        "allowed_target_revisions": sorted(allowed_target_revisions),
        "expected_preservation_digest": expected_digest,
        "preservation_manifest": manifest,
    }


async def _certify_r4_recovery(
    database_url: str,
    *,
    legacy_preservation_digest: str,
) -> dict[str, object]:
    """Certify fix-forward recovery without treating mutable projections as history.

    The initial 0004 preservation gate deliberately hashed every source table.
    That makes an interrupted target recovery unrecoverable once the target's
    readonly safety cadence refreshes a ``*_current`` projection.  The recovery
    gate instead keeps all append-only terminal lineage exact, independently
    proves the pre-existing 0002 database-bound lineage, and requires the
    current target projection/authority shape to be healthy.
    """

    if not _is_sha256_identity(legacy_preservation_digest):
        raise ValueError("legacy preservation digest must be an exact sha256 identity")
    engine = _create_engine(database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            revision = await _alembic_revision(connection)
            target_shape = await _verify_exact_metadata_shape(
                connection,
                expected_columns={
                    table.name: tuple(table.c.keys())
                    for table in sorted(
                        metadata.tables.values(),
                        key=lambda item: item.name,
                    )
                },
            )
            migration_gate = await _migration_gate(connection)
            lineage_manifest = await _r4_terminal_lineage_manifest(connection)
            historical_proof = await _stored_preservation_proof_status(connection)
            await connection.rollback()
    finally:
        await engine.dispose()
    passed = bool(
        revision == EXPECTED_ALEMBIC_REVISION
        and target_shape["status"] == "pass"
        and all(int(value) == 0 for value in migration_gate.values())
        and historical_proof["status"] == "pass"
    )
    return {
        "schema": R4_RECOVERY_SCHEMA,
        "status": "pass" if passed else "fail",
        "alembic_revision": revision,
        "legacy_preservation_digest": legacy_preservation_digest,
        "target_shape": target_shape,
        "migration_gate": migration_gate,
        "terminal_lineage_manifest": lineage_manifest,
        "historical_preservation_proof": historical_proof,
    }


async def _verify_owner_control_source(
    database_url: str,
    source_revision: str,
) -> dict[str, object]:
    engine = _create_engine(database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            revision = await _alembic_revision(connection)
            shape = await _verify_exact_metadata_shape(
                connection,
                expected_columns=_source_0003_table_columns(),
            )
            migration_gate = await _migration_gate(connection)
            manifest = await _owner_control_preservation_manifest(connection)
            runtime_identity = await _runtime_identity(connection)
            registry_identity = await _current_registry_identity(connection)
            owner_policy = await _current_owner_policy(connection)
            runtime_profile = await _current_runtime_profile(connection)
            capabilities = await _current_capabilities(
                connection,
                runtime_identity=runtime_identity,
            )
            account_mode = {
                "status": (
                    "pass"
                    if runtime_profile["status"] == "pass"
                    and runtime_profile["position_mode"] == "independent_sides"
                    and owner_policy["status"] == "pass"
                    and owner_policy["supported_margin_mode"] == "cross"
                    else "fail"
                ),
                "position_mode": runtime_profile["position_mode"],
                "margin_mode": owner_policy["supported_margin_mode"],
            }
            await connection.rollback()
    finally:
        await engine.dispose()
    passed = bool(
        revision == source_revision
        and shape["status"] == "pass"
        and all(int(value) == 0 for value in migration_gate.values())
        and runtime_identity["schema_revision"] == source_revision
        and registry_identity["status"] == "pass"
        and owner_policy["status"] == "pass"
        and runtime_profile["status"] == "pass"
        and capabilities["status"] == "pass"
        and account_mode["status"] == "pass"
    )
    return {
        "schema": SCHEMA,
        "status": "pass" if passed else "fail",
        "alembic_revision": revision,
        "source_shape": shape,
        "runtime_identity": runtime_identity,
        "registry_identity": registry_identity,
        "owner_policy": owner_policy,
        "runtime_profile": runtime_profile,
        "capabilities": capabilities,
        "account_mode": account_mode,
        "migration_gate": migration_gate,
        "preservation_manifest": manifest,
    }


async def _verify_tradfi_instrument_source(
    database_url: str,
    source_revision: str,
) -> dict[str, object]:
    engine = _create_engine(database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            revision = await _alembic_revision(connection)
            shape = await _verify_exact_metadata_shape(
                connection,
                expected_columns=_source_0004_table_columns(),
            )
            migration_gate = await _migration_gate(connection)
            manifest = await _tradfi_instrument_preservation_manifest(connection)
            runtime_identity = await _runtime_identity(connection)
            registry_identity = await _current_registry_identity(connection)
            owner_policy = await _current_owner_policy(connection)
            runtime_profile = await _current_runtime_profile(connection)
            controls = await _current_strategy_controls(connection)
            capabilities = await _current_capabilities(
                connection,
                runtime_identity=runtime_identity,
            )
            account_mode = {
                "status": (
                    "pass"
                    if runtime_profile["status"] == "pass"
                    and runtime_profile["position_mode"] == "independent_sides"
                    and owner_policy["status"] == "pass"
                    and owner_policy["supported_margin_mode"] == "cross"
                    else "fail"
                ),
                "position_mode": runtime_profile["position_mode"],
                "margin_mode": owner_policy["supported_margin_mode"],
            }
            await connection.rollback()
    finally:
        await engine.dispose()
    passed = bool(
        revision == source_revision
        and shape["status"] == "pass"
        and all(int(value) == 0 for value in migration_gate.values())
        and runtime_identity["schema_revision"] == source_revision
        and registry_identity["status"] == "pass"
        and owner_policy["status"] == "pass"
        and runtime_profile["status"] == "pass"
        and controls["status"] == "pass"
        and capabilities["status"] == "pass"
        and account_mode["status"] == "pass"
    )
    return {
        "schema": SCHEMA,
        "status": "pass" if passed else "fail",
        "alembic_revision": revision,
        "source_shape": shape,
        "runtime_identity": runtime_identity,
        "registry_identity": registry_identity,
        "owner_policy": owner_policy,
        "runtime_profile": runtime_profile,
        "strategy_controls": controls,
        "capabilities": capabilities,
        "account_mode": account_mode,
        "migration_gate": migration_gate,
        "preservation_manifest": manifest,
    }


async def _verify_dynamic_selection_source(
    database_url: str,
    source_revision: str,
) -> dict[str, object]:
    """Verify the exact flat 0005 source before the 0006 authority upgrade."""

    engine = _create_engine(database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            revision = await _alembic_revision(connection)
            shape = await _verify_exact_metadata_shape(
                connection,
                expected_columns=_source_0005_table_columns(),
            )
            migration_gate = await _migration_gate(connection)
            manifest = await _dynamic_selection_preservation_manifest(connection)
            runtime_identity = await _runtime_identity(connection)
            registry_identity = await _target_registry_identity(connection)
            owner_policy = await _current_owner_policy(connection)
            runtime_profile = await _current_runtime_profile(connection)
            controls = await _target_strategy_controls(connection)
            capabilities = await _current_capabilities(
                connection,
                runtime_identity=runtime_identity,
            )
            account_mode = {
                "status": (
                    "pass"
                    if runtime_profile["status"] == "pass"
                    and runtime_profile["position_mode"] == "independent_sides"
                    and owner_policy["status"] == "pass"
                    and owner_policy["supported_margin_mode"] == "cross"
                    else "fail"
                ),
                "position_mode": runtime_profile["position_mode"],
                "margin_mode": owner_policy["supported_margin_mode"],
            }
            await connection.rollback()
    finally:
        await engine.dispose()
    passed = bool(
        revision == source_revision
        and shape["status"] == "pass"
        and all(int(value) == 0 for value in migration_gate.values())
        and runtime_identity["schema_revision"] == source_revision
        and registry_identity["status"] == "pass"
        and owner_policy["status"] == "pass"
        and runtime_profile["status"] == "pass"
        and controls["status"] == "pass"
        and capabilities["status"] == "pass"
        and account_mode["status"] == "pass"
    )
    return {
        "schema": SCHEMA,
        "status": "pass" if passed else "fail",
        "alembic_revision": revision,
        "source_shape": shape,
        "runtime_identity": runtime_identity,
        "registry_identity": registry_identity,
        "owner_policy": owner_policy,
        "runtime_profile": runtime_profile,
        "strategy_controls": controls,
        "capabilities": capabilities,
        "account_mode": account_mode,
        "migration_gate": migration_gate,
        "preservation_manifest": manifest,
    }


async def _record_preservation_proof(
    database_url: str,
    *,
    source_revision: str,
    expected_digest: str,
) -> dict[str, object]:
    if source_revision != COMPATIBLE_SOURCE_REVISION:
        raise ValueError("preservation source must be the exact 0002 revision")
    if not _is_sha256_identity(expected_digest):
        raise ValueError(
            "expected preservation digest must be an exact sha256 identity"
        )
    engine = _create_engine(database_url)
    try:
        async with engine.begin() as connection:
            revision = await _alembic_revision(connection)
            manifest = await _source_preservation_manifest(
                connection,
                revision=revision,
            )
            database_identity = await _database_identity(connection)
            proof = _build_preservation_proof(
                source_revision=source_revision,
                target_revision=revision,
                preservation_digest=expected_digest,
                database_identity=database_identity,
            )
            stored = await _preservation_proof_metadata(connection, for_update=True)
            expected_metadata = _preservation_proof_metadata_values(proof)
            eligible = bool(
                revision == HISTORICAL_PRESERVATION_TARGET_REVISION
                and manifest["digest"] == expected_digest
                and (not stored or stored == expected_metadata)
            )
            if eligible and not stored:
                updated_at_ms = int(
                    (
                        await connection.scalar(
                            text(
                                "SELECT floor(extract(epoch FROM clock_timestamp()) "
                                "* 1000)::bigint"
                            )
                        )
                    )
                    or 0
                )
                for key, value in expected_metadata.items():
                    await connection.execute(
                        text(
                            "INSERT INTO brc_schema_metadata "
                            "(metadata_key, metadata_value, updated_at_ms) "
                            "VALUES (:key, :value, :updated_at_ms)"
                        ),
                        {
                            "key": key,
                            "value": value,
                            "updated_at_ms": updated_at_ms,
                        },
                    )
    finally:
        await engine.dispose()
    return {
        "schema": SCHEMA,
        "status": "pass" if eligible else "fail",
        "alembic_revision": revision,
        "expected_preservation_digest": expected_digest,
        "preservation_manifest": manifest,
        "preservation_proof": proof,
        "stored_preservation_proof": stored,
    }


async def _verify_preservation_proof(
    database_url: str,
    *,
    source_revision: str,
    expected_digest: str,
    expected_proof_digest: str,
) -> dict[str, object]:
    if source_revision != COMPATIBLE_SOURCE_REVISION:
        raise ValueError("preservation source must be the exact 0002 revision")
    if not _is_sha256_identity(expected_digest):
        raise ValueError(
            "expected preservation digest must be an exact sha256 identity"
        )
    if not _is_sha256_identity(expected_proof_digest):
        raise ValueError("expected preservation proof must be an exact sha256 identity")
    stored_verification = await _verify_stored_preservation_proof(database_url)
    proof = stored_verification["preservation_proof"]
    assert isinstance(proof, Mapping)
    passed = bool(
        stored_verification["status"] == "pass"
        and proof["preservation_digest"] == expected_digest
        and proof["proof_digest"] == expected_proof_digest
    )
    return {
        **stored_verification,
        "status": "pass" if passed else "fail",
        "expected_preservation_digest": expected_digest,
        "expected_preservation_proof_digest": expected_proof_digest,
    }


async def _verify_stored_preservation_proof(
    database_url: str,
) -> dict[str, object]:
    engine = _create_engine(database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            payload = await _stored_preservation_proof_status(connection)
            await connection.rollback()
    finally:
        await engine.dispose()
    return payload


async def _stored_preservation_proof_status(
    connection: AsyncConnection,
) -> dict[str, object]:
    revision = await _alembic_revision(connection)
    database_identity = await _database_identity(connection)
    stored = await _preservation_proof_metadata(connection, for_update=False)
    complete = set(stored) == set(_PRESERVATION_PROOF_METADATA_KEYS)
    proof = _build_preservation_proof(
        source_revision=stored.get("preservation_source_revision", ""),
        target_revision=stored.get("preservation_target_revision", ""),
        preservation_digest=stored.get("preservation_digest", ""),
        database_identity=stored.get("preservation_database_identity", ""),
    )
    passed = bool(
        complete
        and revision
        in {HISTORICAL_PRESERVATION_TARGET_REVISION, EXPECTED_ALEMBIC_REVISION}
        and proof["source_revision"] == COMPATIBLE_SOURCE_REVISION
        and proof["target_revision"] == HISTORICAL_PRESERVATION_TARGET_REVISION
        and _is_sha256_identity(str(proof["preservation_digest"]))
        and proof["database_identity"] == database_identity
        and _is_sha256_identity(stored.get("preservation_proof_digest", ""))
        and proof["proof_digest"] == stored.get("preservation_proof_digest")
    )
    return {
        "schema": SCHEMA,
        "status": "pass" if passed else "fail",
        "alembic_revision": revision,
        "preservation_proof": proof,
        "stored_preservation_proof": stored,
    }


async def _database_identity(connection: AsyncConnection) -> str:
    row = (
        (
            await connection.execute(
                text(
                    "SELECT system_identifier::text AS system_identifier, "
                    "(SELECT oid::text FROM pg_database "
                    "WHERE datname = current_database()) AS database_oid "
                    "FROM pg_control_system()"
                )
            )
        )
        .mappings()
        .one()
    )
    system_identifier = str(row["system_identifier"])
    database_oid = str(row["database_oid"])
    if not system_identifier.isdigit() or not database_oid.isdigit():
        raise RuntimeError("PostgreSQL immutable database identity is invalid")
    return f"postgresql:{system_identifier}:{database_oid}"


def _build_preservation_proof(
    *,
    source_revision: str,
    target_revision: str,
    preservation_digest: str,
    database_identity: str,
) -> dict[str, str]:
    payload = {
        "schema": PRESERVATION_PROOF_SCHEMA,
        "source_revision": source_revision,
        "target_revision": target_revision,
        "preservation_digest": preservation_digest,
        "database_identity": database_identity,
    }
    return {
        **payload,
        "proof_digest": _sha256_json(payload),
    }


def _preservation_proof_metadata_values(
    proof: Mapping[str, object],
) -> dict[str, str]:
    return {
        "preservation_source_revision": str(proof["source_revision"]),
        "preservation_target_revision": str(proof["target_revision"]),
        "preservation_digest": str(proof["preservation_digest"]),
        "preservation_database_identity": str(proof["database_identity"]),
        "preservation_proof_digest": str(proof["proof_digest"]),
    }


async def _preservation_proof_metadata(
    connection: AsyncConnection,
    *,
    for_update: bool,
) -> dict[str, str]:
    statement = (
        "SELECT metadata_key, metadata_value FROM brc_schema_metadata "
        "WHERE metadata_key = ANY(:keys) ORDER BY metadata_key"
    )
    if for_update:
        statement += " FOR UPDATE"
    rows = (
        await connection.execute(
            text(statement),
            {"keys": list(_PRESERVATION_PROOF_METADATA_KEYS)},
        )
    ).mappings()
    return {str(row["metadata_key"]): str(row["metadata_value"]) for row in rows}


def _create_engine(database_url: str):
    if not database_url.startswith("postgresql+asyncpg://"):
        raise ValueError("database URL must use postgresql+asyncpg")
    return create_async_engine(database_url)


async def _alembic_revision(connection: AsyncConnection) -> str:
    return str(
        (
            await connection.execute(text("SELECT version_num FROM alembic_version"))
        ).scalar_one()
    )


async def _verify_exact_metadata_shape(
    connection: AsyncConnection,
    *,
    expected_columns: Mapping[str, tuple[str, ...]],
) -> dict[str, object]:
    actual_tables = {
        str(name)
        for name in (
            await connection.execute(
                text(
                    """
                    SELECT relname
                      FROM pg_catalog.pg_class
                     WHERE relkind IN ('r', 'p')
                       AND relnamespace = current_schema()::regnamespace
                       AND relname LIKE 'brc\\_%' ESCAPE '\\'
                     ORDER BY relname
                    """
                )
            )
        ).scalars()
    }
    expected_tables = set(expected_columns)
    missing_tables = sorted(expected_tables - actual_tables)
    unexpected_tables = sorted(actual_tables - expected_tables)
    column_mismatches: dict[str, dict[str, list[str]]] = {}
    for table_name, table_columns in expected_columns.items():
        actual_columns = {
            str(name)
            for name in (
                await connection.execute(
                    text(
                        """
                        SELECT attname
                          FROM pg_catalog.pg_attribute
                         WHERE attrelid = to_regclass(:table_name)
                           AND attnum > 0
                           AND NOT attisdropped
                         ORDER BY attnum
                        """
                    ),
                    {"table_name": table_name},
                )
            ).scalars()
        }
        expected_column_names = set(table_columns)
        if actual_columns != expected_column_names:
            column_mismatches[table_name] = {
                "missing": sorted(expected_column_names - actual_columns),
                "unexpected": sorted(actual_columns - expected_column_names),
            }
    return {
        "status": (
            "pass"
            if not missing_tables and not unexpected_tables and not column_mismatches
            else "fail"
        ),
        "missing_tables": missing_tables,
        "unexpected_tables": unexpected_tables,
        "column_mismatches": column_mismatches,
    }


async def _migration_gate(connection: AsyncConnection) -> dict[str, int]:
    statements = {
        "active_tickets": (
            "SELECT count(*) FROM brc_trade_tickets WHERE terminal_at_ms IS NULL"
        ),
        "non_flat_positions": (
            "SELECT count(*) FROM brc_positions_current WHERE quantity <> 0"
        ),
        "active_reservations": (
            "SELECT count(*) FROM brc_budget_reservations "
            "WHERE status <> 'released' OR released_at_ms IS NULL"
        ),
        "active_domains": (
            "SELECT count(*) FROM brc_trade_tickets "
            "WHERE active_netting_domain_key IS NOT NULL"
        ),
        "unreviewed_terminal_tickets": (
            "SELECT count(*) FROM brc_trade_tickets ticket "
            "JOIN brc_trade_aggregates aggregate "
            "ON aggregate.ticket_id = ticket.ticket_id "
            "WHERE ticket.terminal_at_ms IS NOT NULL "
            "AND ticket.status = 'terminal' AND aggregate.status = 'terminal' "
            "AND NOT EXISTS (SELECT 1 FROM brc_trade_reviews review "
            "WHERE review.ticket_id = ticket.ticket_id)"
        ),
        "unresolved_commands": (
            "SELECT count(*) FROM brc_exchange_commands "
            "WHERE status IN ('prepared', 'claimed', 'dispatch_started', "
            "'outcome_unknown')"
        ),
        "open_incidents": (
            "SELECT count(*) FROM brc_runtime_incidents WHERE status <> 'resolved'"
        ),
        "busy_entry_lane": (
            "SELECT count(*) FROM brc_entry_lane_current "
            "WHERE status <> 'idle' OR ticket_id IS NOT NULL "
            "OR signal_event_id IS NOT NULL OR claimed_at_ms IS NOT NULL "
            "OR lease_until_ms IS NOT NULL OR claim_owner IS NOT NULL"
        ),
        "nonterminal_aggregates": (
            "SELECT count(*) FROM brc_trade_aggregates aggregate "
            "JOIN brc_trade_tickets ticket "
            "ON ticket.ticket_id = aggregate.ticket_id WHERE NOT ("
            "ticket.terminal_at_ms IS NOT NULL "
            "AND ticket.active_netting_domain_key IS NULL "
            "AND aggregate.entry_lane_held = false "
            "AND aggregate.position_qty = 0 AND aggregate.protected_qty = 0 "
            "AND ((ticket.status = 'terminal' AND aggregate.status = 'terminal' "
            "AND aggregate.active_stop_exchange_order_id IS NULL "
            "AND aggregate.pending_replaced_stop_exchange_order_id IS NULL "
            "AND aggregate.pending_cancel_exchange_order_id IS NULL) OR ("
            "(ticket.status, aggregate.status) IN ("
            "('leverage_rejected','leverage_rejected'),"
            "('entry_rejected','entry_rejected'),"
            "('entry_reconciled_absent','entry_reconciled_absent')) "
            "AND aggregate.entry_exchange_order_id IS NULL "
            "AND aggregate.initial_stop_exchange_order_id IS NULL "
            "AND aggregate.active_stop_exchange_order_id IS NULL "
            "AND aggregate.tp1_exchange_order_id IS NULL "
            "AND aggregate.pending_replaced_stop_exchange_order_id IS NULL "
            "AND aggregate.pending_cancel_exchange_order_id IS NULL "
            "AND aggregate.exit_exchange_order_id IS NULL)))"
        ),
    }
    return {
        key: int((await connection.scalar(text(statement))) or 0)
        for key, statement in statements.items()
    }


async def _runtime_identity(connection: AsyncConnection) -> dict[str, str]:
    rows = (
        await connection.execute(
            text(
                "SELECT metadata_key, metadata_value FROM brc_schema_metadata "
                "WHERE metadata_key IN "
                "('runtime_commit', 'schema_revision', 'seed_identity')"
            )
        )
    ).mappings()
    values = {str(row["metadata_key"]): str(row["metadata_value"]) for row in rows}
    return {
        "runtime_commit": values.get("runtime_commit", ""),
        "schema_revision": values.get("schema_revision", ""),
        "seed_identity": values.get("seed_identity", ""),
    }


async def _certified_0002_registry_identity(
    connection: AsyncConnection,
) -> dict[str, object]:
    queries = {
        "groups": """
            SELECT strategy_group_id, display_name, active_version_id, status
              FROM brc_strategy_groups
             WHERE status = 'active'
          ORDER BY strategy_group_id
        """,
        "versions": """
            SELECT strategy_version_id, strategy_group_id, version,
                   semantics, status
              FROM brc_strategy_versions
             WHERE status = 'active'
          ORDER BY strategy_version_id
        """,
        "events": """
            SELECT event_spec_id, strategy_version_id, event_id,
                   position_side, timeframe, freshness_window_ms,
                   event_time_authority, entry_order_type,
                   protection_reference_fact_definition_id,
                   exit_policy_id, execution_semantics, status
              FROM brc_event_specs
             WHERE status = 'active'
          ORDER BY event_spec_id
        """,
        "facts": """
            SELECT fact.fact_definition_id, fact.fact_name, fact.value_type,
                   fact.freshness_ms, fact.validation
              FROM brc_fact_definitions AS fact
             WHERE EXISTS (
                    SELECT 1
                      FROM brc_event_required_facts AS link
                      JOIN brc_event_specs AS event
                        ON event.event_spec_id = link.event_spec_id
                       AND event.status = 'active'
                     WHERE link.fact_definition_id = fact.fact_definition_id
                  )
          ORDER BY fact.fact_definition_id
        """,
        "event_facts": """
            SELECT link.event_spec_id, link.fact_definition_id,
                   link.role, link.required
              FROM brc_event_required_facts AS link
              JOIN brc_event_specs AS event
                ON event.event_spec_id = link.event_spec_id
               AND event.status = 'active'
          ORDER BY link.event_spec_id, link.fact_definition_id
        """,
        "policies": """
            SELECT exit_policy_id, exit_policy_version, event_spec_id,
                   position_side, policy, semantic_hash, status
              FROM brc_exit_policies
             WHERE status = 'active'
          ORDER BY exit_policy_id
        """,
    }
    manifest = {
        name: [dict(row) for row in (await connection.execute(text(query))).mappings()]
        for name, query in queries.items()
    }
    counts = {name: len(rows) for name, rows in manifest.items()}
    live_hash = _sha256_json(manifest)
    passed = bool(
        counts == _CERTIFIED_0002_REGISTRY_MANIFEST_COUNTS
        and live_hash == _CERTIFIED_0002_REGISTRY_MANIFEST_HASH
    )
    return {
        "status": "pass" if passed else "fail",
        "expected_semantic_hash": _CERTIFIED_0002_REGISTRY_MANIFEST_HASH,
        "live_semantic_hash": live_hash,
        "expected_counts": _CERTIFIED_0002_REGISTRY_MANIFEST_COUNTS,
        "live_counts": counts,
    }


async def _certified_0002_owner_policy(
    connection: AsyncConnection,
) -> dict[str, object]:
    row = (
        (
            await connection.execute(
                text(
                    "SELECT owner_policy_id, policy_version, enabled, "
                    "new_entry_submit_enabled, priority_rank, "
                    "max_concurrent_tickets, max_strategy_group_concurrent_tickets, "
                    "max_ticket_stop_risk_fraction, max_gross_stop_risk_fraction, "
                    "max_ticket_initial_margin_fraction, "
                    "max_gross_initial_margin_utilization, max_leverage, "
                    "supported_margin_mode, post_stop_stress_multiple, "
                    "max_post_fill_stop_risk_overrun_fraction, scope "
                    "FROM brc_owner_policy_current"
                )
            )
        )
        .mappings()
        .one_or_none()
    )
    expected_scope = {
        "runtime_profile_id": RUNTIME_PROFILE_ID,
        "allowed_event_spec_ids": list(_SOURCE_POLICY_EVENT_IDS),
    }
    passed = bool(
        row is not None
        and row["owner_policy_id"] == OWNER_POLICY_ID
        and int(str(row["policy_version"])) == 3
        and row["enabled"] is True
        and row["new_entry_submit_enabled"] is True
        and int(str(row["priority_rank"])) == 1
        and int(str(row["max_concurrent_tickets"])) == 3
        and int(str(row["max_strategy_group_concurrent_tickets"])) == 2
        and Decimal(str(row["max_ticket_stop_risk_fraction"])) == Decimal("0.03")
        and Decimal(str(row["max_gross_stop_risk_fraction"])) == Decimal("0.06")
        and Decimal(str(row["max_ticket_initial_margin_fraction"])) == Decimal("0.45")
        and Decimal(str(row["max_gross_initial_margin_utilization"])) == Decimal("0.90")
        and int(str(row["max_leverage"])) == 10
        and row["supported_margin_mode"] == "cross"
        and Decimal(str(row["post_stop_stress_multiple"])) == Decimal("2.0")
        and Decimal(str(row["max_post_fill_stop_risk_overrun_fraction"]))
        == Decimal("0.10")
        and row["scope"] == expected_scope
    )
    return {
        "status": "pass" if passed else "fail",
        "owner_policy_id": "" if row is None else str(row["owner_policy_id"]),
        "policy_version": -1 if row is None else int(str(row["policy_version"])),
        "new_entry_submit_enabled": (
            None if row is None else bool(row["new_entry_submit_enabled"])
        ),
        "supported_margin_mode": (
            "" if row is None else str(row["supported_margin_mode"])
        ),
    }


async def _certified_0002_runtime_profile(
    connection: AsyncConnection,
) -> dict[str, object]:
    rows = (
        (
            await connection.execute(
                text(
                    "SELECT runtime_profile_id, venue_id, account_id, environment, "
                    "position_mode, status FROM brc_runtime_profiles "
                    "ORDER BY runtime_profile_id"
                )
            )
        )
        .mappings()
        .all()
    )
    row = rows[0] if len(rows) == 1 else None
    passed = bool(
        row is not None
        and row["runtime_profile_id"] == RUNTIME_PROFILE_ID
        and row["venue_id"] == "binance-usdm"
        and str(row["account_id"]).strip()
        and row["environment"] == "live"
        and row["position_mode"] == "independent_sides"
        and row["status"] == "active"
    )
    return {
        "status": "pass" if passed else "fail",
        "runtime_profile_id": ("" if row is None else str(row["runtime_profile_id"])),
        "position_mode": "" if row is None else str(row["position_mode"]),
    }


async def _certified_0002_capabilities(
    connection: AsyncConnection,
    *,
    runtime_identity: Mapping[str, str],
) -> dict[str, object]:
    rows = {
        str(row["capability_key"]): row
        for row in (
            await connection.execute(
                text(
                    "SELECT capability_key, enabled, certified_commit, "
                    "schema_revision FROM brc_runtime_capabilities_current "
                    "ORDER BY capability_key"
                )
            )
        ).mappings()
    }
    expected_enabled = {
        "exchange_commands": True,
        "strategy_signal_ingest": True,
    }
    passed = bool(
        set(rows) == set(expected_enabled)
        and all(
            row["enabled"] is expected_enabled[key]
            and row["certified_commit"] == runtime_identity["runtime_commit"]
            and row["schema_revision"] == COMPATIBLE_SOURCE_REVISION
            for key, row in rows.items()
        )
    )
    return {
        "status": "pass" if passed else "fail",
        "exchange_commands": (
            None
            if "exchange_commands" not in rows
            else bool(rows["exchange_commands"]["enabled"])
        ),
        "strategy_signal_ingest": (
            None
            if "strategy_signal_ingest" not in rows
            else bool(rows["strategy_signal_ingest"]["enabled"])
        ),
    }


def _source_0002_table_columns() -> dict[str, tuple[str, ...]]:
    return {
        table.name: (
            *tuple(table.c.keys()),
            *_SOURCE_0002_ADDED_COLUMNS.get(table.name, ()),
        )
        for table in v4_schema.metadata.sorted_tables
    }


def _source_0003_table_columns() -> dict[str, tuple[str, ...]]:
    return {
        table.name: _source_columns_before_dynamic_selection(table)
        for table in sorted(metadata.tables.values(), key=lambda item: item.name)
        if table.name
        not in _OWNER_CONTROL_TABLES
        | _TRADFI_INSTRUMENT_TABLES
        | _DYNAMIC_SELECTION_TABLES
        | _EXIT_PROFILE_TABLES
    }


def _source_0004_table_columns() -> dict[str, tuple[str, ...]]:
    return {
        table.name: _source_columns_before_dynamic_selection(table)
        for table in sorted(metadata.tables.values(), key=lambda item: item.name)
        if table.name
        not in _TRADFI_INSTRUMENT_TABLES
        | _DYNAMIC_SELECTION_TABLES
        | _EXIT_PROFILE_TABLES
    }


def _source_0005_table_columns() -> dict[str, tuple[str, ...]]:
    return {
        table.name: tuple(
            column.name
            for column in table.c
            if column.name not in _DYNAMIC_SELECTION_ADDED_COLUMNS.get(table.name, ())
            and column.name not in _EXIT_PROFILE_ADDED_COLUMNS.get(table.name, ())
        )
        for table in sorted(metadata.tables.values(), key=lambda item: item.name)
        if table.name not in _DYNAMIC_SELECTION_TABLES | _EXIT_PROFILE_TABLES
    }


def _source_columns_before_tradfi(table: sa.Table) -> tuple[str, ...]:
    columns = tuple(table.c.keys())
    if table.name != "brc_shadow_outcomes_current":
        return columns
    return tuple(name for name in columns if name not in _TRADFI_SHADOW_COLUMNS)


def _source_columns_before_dynamic_selection(table: sa.Table) -> tuple[str, ...]:
    return tuple(
        name
        for name in _source_columns_before_tradfi(table)
        if name not in _DYNAMIC_SELECTION_ADDED_COLUMNS.get(table.name, ())
        and name not in _EXIT_PROFILE_ADDED_COLUMNS.get(table.name, ())
    )


async def _owner_control_preservation_manifest(
    connection: AsyncConnection,
) -> dict[str, object]:
    table_entries: list[dict[str, object]] = []
    total_rows = 0
    for table_name, column_names in sorted(_source_0003_table_columns().items()):
        table = sa.table(table_name, *(sa.column(name) for name in column_names))
        rows = (
            (
                await connection.execute(
                    sa.select(*(table.c[name] for name in column_names))
                )
            )
            .mappings()
            .all()
        )
        canonical_rows = sorted(
            (
                _row_manifest(column_names, projected)
                for row in rows
                if (
                    projected := _project_pre_dynamic_selection_row(
                        table_name,
                        dict(row),
                    )
                )
                is not None
            ),
            key=lambda row: str(row["digest"]),
        )
        table_payload = {
            "table": table_name,
            "columns": list(column_names),
            "row_count": len(canonical_rows),
            "rows": canonical_rows,
        }
        table_entries.append(
            {
                **table_payload,
                "digest": _sha256_json(table_payload),
            }
        )
        total_rows += len(canonical_rows)
    payload = {
        "schema": "brc.trading_kernel.0003_preservation.v1",
        "source_revision": OWNER_CONTROL_SOURCE_REVISION,
        "tables": table_entries,
        "table_count": len(table_entries),
        "row_count": total_rows,
    }
    return {**payload, "digest": _sha256_json(payload)}


async def _tradfi_instrument_preservation_manifest(
    connection: AsyncConnection,
) -> dict[str, object]:
    table_entries: list[dict[str, object]] = []
    total_rows = 0
    for table_name, column_names in sorted(_source_0004_table_columns().items()):
        table = sa.table(table_name, *(sa.column(name) for name in column_names))
        rows = (
            (
                await connection.execute(
                    sa.select(*(table.c[name] for name in column_names))
                )
            )
            .mappings()
            .all()
        )
        canonical_rows = sorted(
            (
                _row_manifest(column_names, projected)
                for row in rows
                if (
                    projected := _project_pre_dynamic_selection_row(
                        table_name,
                        dict(row),
                    )
                )
                is not None
            ),
            key=lambda row: str(row["digest"]),
        )
        table_payload = {
            "table": table_name,
            "columns": list(column_names),
            "row_count": len(canonical_rows),
            "rows": canonical_rows,
        }
        table_entries.append(
            {
                **table_payload,
                "digest": _sha256_json(table_payload),
            }
        )
        total_rows += len(canonical_rows)
    payload = {
        "schema": "brc.trading_kernel.0004_preservation.v1",
        "source_revision": TRADFI_INSTRUMENT_SOURCE_REVISION,
        "tables": table_entries,
        "table_count": len(table_entries),
        "row_count": total_rows,
    }
    return {**payload, "digest": _sha256_json(payload)}


async def _dynamic_selection_preservation_manifest(
    connection: AsyncConnection,
) -> dict[str, object]:
    table_entries: list[dict[str, object]] = []
    total_rows = 0
    source_columns = _source_0005_table_columns()
    for table_name, column_names in sorted(source_columns.items()):
        if table_name in _DYNAMIC_SELECTION_ADDITIVE_EXISTING_TABLES:
            continue
        table = sa.table(table_name, *(sa.column(name) for name in column_names))
        rows = (
            (
                await connection.execute(
                    sa.select(*(table.c[name] for name in column_names))
                )
            )
            .mappings()
            .all()
        )
        canonical_rows = sorted(
            (_row_manifest(column_names, dict(row)) for row in rows),
            key=lambda row: str(row["digest"]),
        )
        table_payload = {
            "table": table_name,
            "columns": list(column_names),
            "row_count": len(canonical_rows),
            "rows": canonical_rows,
        }
        table_entries.append(
            {
                **table_payload,
                "digest": _sha256_json(table_payload),
            }
        )
        total_rows += len(canonical_rows)
    payload = {
        "schema": "brc.trading_kernel.0005_preservation.v1",
        "source_revision": DYNAMIC_SELECTION_SOURCE_REVISION,
        "tables": table_entries,
        "table_count": len(table_entries),
        "row_count": total_rows,
    }
    return {**payload, "digest": _sha256_json(payload)}


async def _r4_terminal_lineage_manifest(
    connection: AsyncConnection,
) -> dict[str, object]:
    """Hash the immutable, terminal trading lineage in the target schema.

    Mutable ``*_current`` projections are intentionally absent.  Their health
    is checked through target shape, flatness, registry/policy identity and the
    exchange postflight; they are not historic evidence.
    """

    table_entries: list[dict[str, object]] = []
    total_rows = 0
    for table_name in sorted(_R4_TERMINAL_LINEAGE_TABLES):
        table = metadata.tables[table_name]
        column_names = tuple(table.c.keys())
        rows = (
            (
                await connection.execute(
                    sa.select(*(table.c[name] for name in column_names))
                )
            )
            .mappings()
            .all()
        )
        canonical_rows = sorted(
            (_row_manifest(column_names, dict(row)) for row in rows),
            key=lambda row: str(row["digest"]),
        )
        table_payload = {
            "table": table_name,
            "columns": list(column_names),
            "row_count": len(canonical_rows),
            "rows": canonical_rows,
        }
        table_entries.append(
            {
                **table_payload,
                "digest": _sha256_json(table_payload),
            }
        )
        total_rows += len(canonical_rows)
    payload = {
        "schema": "brc.trading_kernel.0004_terminal_lineage.v1",
        "source_revision": TRADFI_INSTRUMENT_SOURCE_REVISION,
        "tables": table_entries,
        "table_count": len(table_entries),
        "row_count": total_rows,
    }
    return {**payload, "digest": _sha256_json(payload)}


async def _current_registry_identity(
    connection: AsyncConnection,
) -> dict[str, object]:
    source_contracts = tuple(
        contract
        for contract in registered_strategy_contracts()
        if contract.strategy_group_id != "SOR-US-EQ-PERP-001"
    )
    expected_hash = build_registry_semantic_hash(source_contracts)
    expected_groups = {contract.strategy_group_id for contract in source_contracts}
    expected_versions = {contract.strategy_version_id for contract in source_contracts}
    expected_events = {contract.event_spec_id for contract in source_contracts}
    metadata_hash = str(
        (
            await connection.scalar(
                text(
                    "SELECT metadata_value FROM brc_schema_metadata "
                    "WHERE metadata_key = 'registry_semantic_hash'"
                )
            )
        )
        or ""
    )
    groups = {
        str(row["strategy_group_id"]): str(row["active_version_id"])
        for row in (
            await connection.execute(
                text(
                    "SELECT strategy_group_id, active_version_id "
                    "FROM brc_strategy_groups WHERE status = 'active' "
                    "ORDER BY strategy_group_id"
                )
            )
        ).mappings()
    }
    versions = {
        str(row["strategy_version_id"]): row["semantics"]
        for row in (
            await connection.execute(
                text(
                    "SELECT strategy_version_id, semantics "
                    "FROM brc_strategy_versions WHERE status = 'active' "
                    "ORDER BY strategy_version_id"
                )
            )
        ).mappings()
    }
    events = {
        str(value)
        for value in (
            await connection.execute(
                text(
                    "SELECT event_spec_id FROM brc_event_specs "
                    "WHERE status = 'active' ORDER BY event_spec_id"
                )
            )
        ).scalars()
    }
    passed = bool(
        metadata_hash == expected_hash
        and set(groups) == expected_groups
        and set(groups.values()) == expected_versions
        and set(versions) == expected_versions
        and events == expected_events
        and all(
            isinstance(semantics, Mapping)
            and semantics.get("registry_semantic_hash") == expected_hash
            for semantics in versions.values()
        )
    )
    return {
        "status": "pass" if passed else "fail",
        "expected_semantic_hash": expected_hash,
        "live_semantic_hash": metadata_hash,
        "active_group_count": len(groups),
    }


async def _target_registry_identity(
    connection: AsyncConnection,
) -> dict[str, object]:
    contracts = registered_strategy_contracts()
    expected_hash = build_registry_semantic_hash(contracts)
    expected_groups = {contract.strategy_group_id for contract in contracts}
    expected_versions = {contract.strategy_version_id for contract in contracts}
    expected_events = {contract.event_spec_id for contract in contracts}
    metadata_hash = str(
        (
            await connection.scalar(
                text(
                    "SELECT metadata_value FROM brc_schema_metadata "
                    "WHERE metadata_key = 'registry_semantic_hash'"
                )
            )
        )
        or ""
    )
    groups = {
        str(row["strategy_group_id"]): str(row["active_version_id"])
        for row in (
            await connection.execute(
                text(
                    "SELECT strategy_group_id, active_version_id "
                    "FROM brc_strategy_groups WHERE status = 'active'"
                )
            )
        ).mappings()
    }
    versions = {
        str(row["strategy_version_id"]): row["semantics"]
        for row in (
            await connection.execute(
                text(
                    "SELECT strategy_version_id, semantics "
                    "FROM brc_strategy_versions WHERE status = 'active'"
                )
            )
        ).mappings()
    }
    events = {
        str(value)
        for value in (
            await connection.execute(
                text(
                    "SELECT event_spec_id FROM brc_event_specs WHERE status = 'active'"
                )
            )
        ).scalars()
    }
    passed = bool(
        metadata_hash == expected_hash
        and set(groups) == expected_groups
        and set(groups.values()) == expected_versions
        and set(versions) == expected_versions
        and events == expected_events
        and all(
            isinstance(semantics, Mapping)
            and semantics.get("registry_semantic_hash") == expected_hash
            for semantics in versions.values()
        )
    )
    return {
        "status": "pass" if passed else "fail",
        "expected_semantic_hash": expected_hash,
        "live_semantic_hash": metadata_hash,
        "active_group_count": len(groups),
    }


async def _current_strategy_controls(
    connection: AsyncConnection,
) -> dict[str, object]:
    expected_groups = {
        contract.strategy_group_id
        for contract in registered_strategy_contracts()
        if contract.strategy_group_id != "SOR-US-EQ-PERP-001"
    }
    rows = (
        (
            await connection.execute(
                text(
                    "SELECT strategy_group_id, entry_state, control_version "
                    "FROM brc_strategy_entry_controls_current "
                    "ORDER BY strategy_group_id"
                )
            )
        )
        .mappings()
        .all()
    )
    actual_groups = {str(row["strategy_group_id"]) for row in rows}
    passed = bool(
        actual_groups == expected_groups
        and all(
            row["entry_state"] in {"paused", "enabled"}
            and int(str(row["control_version"])) > 0
            for row in rows
        )
    )
    return {
        "status": "pass" if passed else "fail",
        "strategy_group_ids": sorted(actual_groups),
    }


async def _target_strategy_controls(
    connection: AsyncConnection,
) -> dict[str, object]:
    expected_groups = {
        contract.strategy_group_id for contract in registered_strategy_contracts()
    }
    rows = (
        (
            await connection.execute(
                text(
                    "SELECT strategy_group_id, entry_state, control_version "
                    "FROM brc_strategy_entry_controls_current"
                )
            )
        )
        .mappings()
        .all()
    )
    actual_groups = {str(row["strategy_group_id"]) for row in rows}
    passed = bool(
        actual_groups == expected_groups
        and all(
            row["entry_state"] in {"paused", "enabled"}
            and int(str(row["control_version"])) > 0
            for row in rows
        )
    )
    return {
        "status": "pass" if passed else "fail",
        "strategy_group_ids": sorted(actual_groups),
    }


async def _current_owner_policy(
    connection: AsyncConnection,
) -> dict[str, object]:
    row = (
        (
            await connection.execute(
                text(
                    "SELECT policy_version, enabled, new_entry_submit_enabled, "
                    "supported_margin_mode FROM brc_owner_policy_current "
                    "WHERE owner_policy_id = :owner_policy_id"
                ),
                {"owner_policy_id": OWNER_POLICY_ID},
            )
        )
        .mappings()
        .one_or_none()
    )
    passed = bool(
        row is not None
        and int(str(row["policy_version"])) >= 4
        and row["enabled"] is True
        and row["supported_margin_mode"] == "cross"
    )
    return {
        "status": "pass" if passed else "fail",
        "policy_version": -1 if row is None else int(str(row["policy_version"])),
        "new_entry_submit_enabled": (
            None if row is None else bool(row["new_entry_submit_enabled"])
        ),
        "supported_margin_mode": (
            None if row is None else str(row["supported_margin_mode"])
        ),
    }


async def _current_runtime_profile(
    connection: AsyncConnection,
) -> dict[str, object]:
    row = (
        (
            await connection.execute(
                text(
                    "SELECT venue_id, environment, position_mode, status "
                    "FROM brc_runtime_profiles WHERE runtime_profile_id = :profile_id"
                ),
                {"profile_id": RUNTIME_PROFILE_ID},
            )
        )
        .mappings()
        .one_or_none()
    )
    passed = bool(
        row is not None
        and row["venue_id"] == "binance-usdm"
        and row["environment"] == "live"
        and row["position_mode"] == "independent_sides"
        and row["status"] == "active"
    )
    return {
        "status": "pass" if passed else "fail",
        "position_mode": None if row is None else str(row["position_mode"]),
    }


async def _current_capabilities(
    connection: AsyncConnection,
    *,
    runtime_identity: Mapping[str, str],
) -> dict[str, object]:
    rows = {
        str(row["capability_key"]): row
        for row in (
            await connection.execute(
                text(
                    "SELECT capability_key, enabled, certified_commit, "
                    "schema_revision FROM brc_runtime_capabilities_current"
                )
            )
        ).mappings()
    }
    expected = {"exchange_commands", "strategy_signal_ingest"}
    passed = bool(
        set(rows) == expected
        and all(
            row["enabled"] is True
            and row["certified_commit"] == runtime_identity["runtime_commit"]
            and row["schema_revision"] == runtime_identity["schema_revision"]
            for row in rows.values()
        )
    )
    return {
        "status": "pass" if passed else "fail",
        "exchange_commands": (
            None
            if "exchange_commands" not in rows
            else bool(rows["exchange_commands"]["enabled"])
        ),
        "strategy_signal_ingest": (
            None
            if "strategy_signal_ingest" not in rows
            else bool(rows["strategy_signal_ingest"]["enabled"])
        ),
    }


async def _source_preservation_manifest(
    connection: AsyncConnection,
    *,
    revision: str,
) -> dict[str, object]:
    if revision not in {
        COMPATIBLE_SOURCE_REVISION,
        "0003_portfolio_admission_observability",
        EXPECTED_ALEMBIC_REVISION,
    }:
        raise ValueError("historical preservation revision is unsupported")
    source_columns = _source_0002_table_columns()
    event_facts = sa.table(
        "brc_event_required_facts",
        sa.column("event_spec_id"),
        sa.column("fact_definition_id"),
    )
    source_fact_ids = frozenset(
        str(value)
        for value in (
            await connection.execute(
                sa.select(event_facts.c.fact_definition_id)
                .where(event_facts.c.event_spec_id.not_in(_TARGET_EVENT_IDS))
                .distinct()
            )
        ).scalars()
    )
    table_entries: list[dict[str, object]] = []
    total_rows = 0
    for table_name, column_names in source_columns.items():
        table = sa.table(table_name, *(sa.column(name) for name in column_names))
        rows = (
            (
                await connection.execute(
                    sa.select(*(table.c[name] for name in column_names))
                )
            )
            .mappings()
            .all()
        )
        projected_rows = [
            projected
            for row in rows
            if (
                projected := _project_source_row(
                    table_name,
                    dict(row),
                    revision=revision,
                    source_fact_ids=source_fact_ids,
                )
            )
            is not None
        ]
        canonical_rows = sorted(
            (_row_manifest(column_names, row) for row in projected_rows),
            key=lambda row: str(row["digest"]),
        )
        table_payload = {
            "table": table_name,
            "columns": list(column_names),
            "rows": canonical_rows,
        }
        table_digest = _sha256_json(table_payload)
        table_entries.append(
            {
                "table": table_name,
                "columns": list(column_names),
                "rows": canonical_rows,
                "row_count": len(canonical_rows),
                "digest": table_digest,
            }
        )
        total_rows += len(canonical_rows)
    manifest_payload = {
        "schema": PRESERVATION_SCHEMA,
        "source_revision": COMPATIBLE_SOURCE_REVISION,
        "tables": table_entries,
    }
    return {
        "schema": PRESERVATION_SCHEMA,
        "source_revision": COMPATIBLE_SOURCE_REVISION,
        "table_count": len(table_entries),
        "row_count": total_rows,
        "table_digests": [
            {
                "table": entry["table"],
                "row_count": entry["row_count"],
                "digest": entry["digest"],
            }
            for entry in table_entries
        ],
        "tables": table_entries,
        "digest": _sha256_json(manifest_payload),
    }


def _project_source_row(
    table_name: str,
    row: dict[str, Any],
    *,
    revision: str,
    source_fact_ids: frozenset[str],
) -> dict[str, Any] | None:
    if revision == COMPATIBLE_SOURCE_REVISION:
        return row
    if (
        table_name == "brc_instruments"
        and str(row["exchange_instrument_id"])
        in CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS
        and row["status"] == "pending_certification"
    ):
        return None
    if (
        table_name == "brc_schema_metadata"
        and str(row["metadata_key"]) in _PRESERVATION_PROOF_METADATA_KEYS
    ):
        return None
    if table_name == "brc_strategy_versions":
        identity = str(row["strategy_version_id"])
        if identity in _TARGET_VERSION_IDS:
            return None
        if identity in _SOURCE_VERSION_IDS:
            row["status"] = "active"
    elif table_name == "brc_event_specs":
        identity = str(row["event_spec_id"])
        if identity in _TARGET_EVENT_IDS:
            return None
        if identity in _SOURCE_EVENT_IDS:
            row["status"] = "active"
    elif table_name == "brc_exit_policies":
        identity = str(row["exit_policy_id"])
        if identity in _TARGET_EXIT_POLICY_IDS:
            return None
        if str(row["event_spec_id"]) in _SOURCE_EVENT_IDS:
            row["status"] = "active"
    elif table_name == "brc_event_required_facts":
        if str(row["event_spec_id"]) in _TARGET_EVENT_IDS:
            return None
    elif table_name == "brc_fact_definitions":
        identity = str(row["fact_definition_id"])
        if identity in _TARGET_FACT_IDS and identity not in source_fact_ids:
            return None
    elif table_name == "brc_strategy_groups":
        group_id = str(row["strategy_group_id"])
        if group_id in _SOURCE_GROUP_POINTERS:
            row["active_version_id"] = _SOURCE_GROUP_POINTERS[group_id]
    elif table_name == "brc_owner_policy_events":
        if int(str(row["policy_version"])) == 4:
            return None
    elif table_name == "brc_owner_policy_current":
        row.update(
            {
                "policy_version": 3,
                "new_entry_submit_enabled": True,
                "max_strategy_group_concurrent_tickets": 2,
                "max_ticket_stop_risk_fraction": Decimal("0.030000000000000000"),
                "max_ticket_initial_margin_fraction": Decimal("0.450000000000000000"),
            }
        )
        scope = dict(row["scope"])
        scope["allowed_event_spec_ids"] = list(_SOURCE_POLICY_EVENT_IDS)
        row["scope"] = scope
    return row


def _project_pre_dynamic_selection_row(
    table_name: str,
    row: dict[str, Any],
) -> dict[str, Any] | None:
    if (
        table_name == "brc_instruments"
        and str(row["exchange_instrument_id"])
        in CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS
        and row["status"] == "pending_certification"
    ):
        return None
    return row


def _row_manifest(
    column_names: tuple[str, ...],
    row: Mapping[str, Any],
) -> dict[str, object]:
    value_digests = [
        _sha256_json(
            {
                "column": column_name,
                "value": _canonical_value(row[column_name]),
            }
        )
        for column_name in column_names
    ]
    return {
        "value_digests": value_digests,
        "digest": _sha256_json(
            {
                "columns": list(column_names),
                "value_digests": value_digests,
            }
        ),
    }


async def _inspect_deployment_revision(database_url: str) -> dict[str, object]:
    engine = _create_engine(database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            revision = await _alembic_revision(connection)
            await connection.rollback()
    finally:
        await engine.dispose()
    return {
        "schema": SCHEMA,
        "status": (
            "pass"
            if revision
            in {
                COMPATIBLE_SOURCE_REVISION,
                OWNER_CONTROL_SOURCE_REVISION,
                TRADFI_INSTRUMENT_SOURCE_REVISION,
                DYNAMIC_SELECTION_SOURCE_REVISION,
                EXPECTED_ALEMBIC_REVISION,
            }
            else "fail"
        ),
        "alembic_revision": revision,
    }


def _canonical_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, bytes):
        return value.hex()
    raise TypeError(f"unsupported preservation value type: {type(value).__name__}")


def _sha256_json(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def _is_sha256_identity(value: str) -> bool:
    return bool(
        len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    database_url = str(args.database_url or "").strip()
    if args.certify_r4_recovery:
        if (
            args.deployment_revision
            or args.compatible_source_revision
            or args.preserve_source_revision
            or args.expected_preservation_digest
            or args.record_preservation_proof
            or args.verify_preservation_proof
            or args.verify_stored_preservation_proof
            or args.expected_preservation_proof_digest
            or not args.legacy_preservation_digest
        ):
            raise ValueError("R4 recovery certification mode is ambiguous")
        payload = asyncio.run(
            _certify_r4_recovery(
                database_url,
                legacy_preservation_digest=str(args.legacy_preservation_digest),
            )
        )
    elif args.deployment_revision:
        if (
            args.compatible_source_revision
            or args.preserve_source_revision
            or args.expected_preservation_digest
            or args.record_preservation_proof
            or args.verify_preservation_proof
            or args.verify_stored_preservation_proof
            or args.expected_preservation_proof_digest
            or args.legacy_preservation_digest
        ):
            raise ValueError("schema verification mode is ambiguous")
        payload = asyncio.run(_inspect_deployment_revision(database_url))
    elif args.compatible_source_revision:
        if (
            args.preserve_source_revision
            or args.expected_preservation_digest
            or args.record_preservation_proof
            or args.verify_preservation_proof
            or args.verify_stored_preservation_proof
            or args.expected_preservation_proof_digest
            or args.legacy_preservation_digest
        ):
            raise ValueError("schema verification mode is ambiguous")
        payload = asyncio.run(
            _verify_compatible_source(
                database_url,
                str(args.compatible_source_revision),
            )
        )
    elif args.preserve_source_revision:
        if not args.expected_preservation_digest:
            raise ValueError("post-migration preservation requires an expected digest")
        if (
            int(args.record_preservation_proof)
            + int(args.verify_preservation_proof)
            + int(args.verify_stored_preservation_proof)
            > 1
        ):
            raise ValueError("preservation proof mode is ambiguous")
        if args.verify_stored_preservation_proof:
            raise ValueError("stored proof verification requires no source revision")
        if args.record_preservation_proof:
            if args.expected_preservation_proof_digest:
                raise ValueError("recording proof forbids an expected proof digest")
            payload = asyncio.run(
                _record_preservation_proof(
                    database_url,
                    source_revision=str(args.preserve_source_revision),
                    expected_digest=str(args.expected_preservation_digest),
                )
            )
        elif args.verify_preservation_proof:
            if not args.expected_preservation_proof_digest:
                raise ValueError("proof verification requires an expected proof digest")
            payload = asyncio.run(
                _verify_preservation_proof(
                    database_url,
                    source_revision=str(args.preserve_source_revision),
                    expected_digest=str(args.expected_preservation_digest),
                    expected_proof_digest=str(args.expected_preservation_proof_digest),
                )
            )
        else:
            if args.expected_preservation_proof_digest:
                raise ValueError("expected proof digest requires proof verification")
            payload = asyncio.run(
                _verify_preservation(
                    database_url,
                    source_revision=str(args.preserve_source_revision),
                    expected_digest=str(args.expected_preservation_digest),
                )
            )
    elif args.verify_stored_preservation_proof:
        if (
            args.expected_preservation_digest
            or args.expected_preservation_proof_digest
            or args.record_preservation_proof
            or args.verify_preservation_proof
            or args.legacy_preservation_digest
        ):
            raise ValueError("stored proof verification mode is ambiguous")
        payload = asyncio.run(_verify_stored_preservation_proof(database_url))
    elif args.expected_preservation_digest or args.legacy_preservation_digest:
        raise ValueError("expected preservation digest requires a source revision")
    elif (
        args.record_preservation_proof
        or args.verify_preservation_proof
        or args.verify_stored_preservation_proof
        or args.expected_preservation_proof_digest
    ):
        raise ValueError("preservation proof requires a source revision")
    else:
        payload = asyncio.run(_verify(database_url))
    if args.summary_only:
        payload = _summary_payload(payload)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["status"] == "pass" else 1


def _summary_payload(payload: dict[str, object]) -> dict[str, object]:
    """Keep deployment RPC bounded without weakening manifest verification."""

    manifest = payload.get("preservation_manifest")
    if not isinstance(manifest, dict):
        return payload
    return {
        **payload,
        "preservation_manifest": {
            key: manifest[key]
            for key in (
                "schema",
                "source_revision",
                "table_count",
                "row_count",
                "digest",
            )
            if key in manifest
        },
    }


if __name__ == "__main__":
    raise SystemExit(main())
