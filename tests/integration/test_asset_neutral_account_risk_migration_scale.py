"""PostgreSQL scale certification for asset-neutral account-risk migrations."""

from __future__ import annotations

import gc
import importlib.util
import os
from pathlib import Path
import re
import sys
import time
import tracemalloc
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext


ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "migrations/versions"
MIGRATIONS = (
    VERSIONS / "2026-07-04-086_create_pg_runtime_control_state_foundation.py",
    VERSIONS / "2026-07-10-105_create_ticket_bound_exchange_commands.py",
    VERSIONS / "2026-07-14-121_create_account_risk_policy.py",
    VERSIONS / "2026-07-14-122_create_account_risk_current_projections.py",
    VERSIONS / "2026-07-14-124_add_account_capacity_reservation_scope.py",
    VERSIONS / "2026-07-14-125_add_account_capacity_claim_policy_event.py",
    VERSIONS / "2026-07-15-126_expand_asset_neutral_account_risk_identity.py",
)
BACKFILL = VERSIONS / "2026-07-15-127_backfill_asset_neutral_account_risk_identity.py"
ENFORCE = VERSIONS / "2026-07-15-128_enforce_asset_neutral_account_risk_identity.py"
_DSN = os.getenv("BRC_LOCAL_TEST_POSTGRES_DSN", "")
_SAFE_SCHEMA = re.compile(r"^brc_asset_neutral_scale_[a-f0-9]{12}$")

pytestmark = pytest.mark.skipif(
    not _DSN,
    reason="requires isolated local PostgreSQL DSN",
)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _run_upgrade(conn: sa.Connection, path: Path, name: str) -> None:
    module = _load(path, name)
    _run_loaded_upgrade(conn, module)


def _run_loaded_upgrade(conn: sa.Connection, module: object) -> None:
    old_op = module.op
    module.op = Operations(MigrationContext.configure(conn))
    try:
        module.upgrade()
    finally:
        module.op = old_op


@pytest.fixture()
def postgres_scale_connection():
    engine = sa.create_engine(_DSN)
    schema = f"brc_asset_neutral_scale_{uuid4().hex[:12]}"
    assert _SAFE_SCHEMA.fullmatch(schema)
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        with engine.begin() as conn:
            conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            yield conn
    finally:
        with engine.begin() as conn:
            conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        engine.dispose()


def test_migration_classifies_100000_terminal_rows_without_python_materialization(
    postgres_scale_connection: sa.Connection,
) -> None:
    conn = postgres_scale_connection
    for index, migration in enumerate(MIGRATIONS):
        _run_upgrade(conn, migration, f"migration_asset_neutral_scale_{index}")
    _seed_instrument_and_mapping(conn)
    _seed_terminal_history(conn)
    _seed_complete_active_claim_and_ticket(conn)

    source = BACKFILL.read_text()
    assert ".fetchall(" not in source
    assert ".all(" not in source
    assert "list(result)" not in source

    backfill = _load(BACKFILL, "migration_asset_neutral_scale_127")
    gc.collect()
    tracemalloc.start()
    started = time.monotonic()
    try:
        _run_loaded_upgrade(conn, backfill)
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    elapsed_seconds = time.monotonic() - started

    terminal_count = conn.execute(
        sa.text(
            "SELECT count(*) FROM brc_budget_reservations WHERE status = 'released'"
        )
    ).scalar_one()
    unresolved_terminal_count = conn.execute(
        sa.text(
            """
            SELECT count(*)
            FROM brc_budget_reservations
            WHERE status = 'released'
              AND exchange_instrument_id IS NULL
            """
        )
    ).scalar_one()

    assert terminal_count == 100_000
    assert unresolved_terminal_count == 0
    assert peak_bytes <= 16 * 1024 * 1024
    assert elapsed_seconds < 60

    _run_upgrade(conn, ENFORCE, "migration_asset_neutral_scale_128")
    index_names = {
        row[0]
        for row in conn.execute(
            sa.text(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = current_schema()
                """
            )
        )
    }
    assert {
        "uq_brc_budget_reservation_idempotency",
        "uq_brc_budget_reservation_invocation",
        "idx_brc_budget_reservation_effective_hot_path",
    } <= index_names


def _seed_instrument_and_mapping(conn: sa.Connection) -> None:
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_exchange_instruments (
              exchange_instrument_id, exchange_id, exchange_symbol, asset_class,
              price_tick, quantity_step, min_notional, status, created_at_ms,
              instrument_type, settlement_asset, margin_asset,
              instrument_identity_schema_version
            ) VALUES (
              'instrument-1', 'binance-usdm', 'SOLUSDT', 'crypto',
              0.01, 0.001, 5, 'active', 1,
              'perpetual', 'USDT', 'USDT', 'v1'
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_symbol_instrument_mappings (
              mapping_id, symbol, exchange_instrument_id, status,
              valid_from_ms, valid_until_ms, created_at_ms
            ) VALUES (
              'mapping-1', 'SOLUSDT', 'instrument-1', 'active', 0, NULL, 1
            )
            """
        )
    )


def _seed_terminal_history(conn: sa.Connection) -> None:
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_budget_reservations (
              budget_reservation_id, promotion_candidate_id, action_time_lane_input_id,
              ticket_id, signal_event_id, event_spec_id, runtime_profile_id,
              account_id, strategy_group_id, symbol, side, target_notional,
              leverage, reserved_margin, reserved_at_ms, expires_at_ms,
              status, policy_version
            )
            SELECT
              'terminal-' || lpad(series_id::text, 6, '0'),
              'promotion-' || series_id,
              'lane-' || series_id,
              NULL,
              'signal-' || series_id,
              'event-spec-1',
              'profile-1',
              'account-1',
              'MPG-001',
              'SOLUSDT',
              'long',
              100,
              10,
              10,
              series_id,
              series_id + 60000,
              'released',
              'policy-v1'
            FROM generate_series(1, 100000) AS series_id
            """
        )
    )


def _seed_complete_active_claim_and_ticket(conn: sa.Connection) -> None:
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_budget_reservations (
              budget_reservation_id, promotion_candidate_id, action_time_lane_input_id,
              ticket_id, signal_event_id, event_spec_id, runtime_profile_id,
              account_id, strategy_group_id, symbol, side, target_notional,
              leverage, reserved_margin, reserved_at_ms, expires_at_ms, status,
              policy_version, exchange_instrument_id, account_risk_policy_version,
              risk_cluster_id, account_capacity_projection_version,
              account_risk_policy_event_id, allowed_risk_budget,
              margin_accounting_state, exposure_episode_id,
              action_time_invocation_id, asset_class, instrument_type,
              settlement_asset, margin_asset, instrument_rule_snapshot_id,
              instrument_rule_schema_version, pricing_source_fact_snapshot_id,
              account_source_fact_snapshot_id, account_fact_schema_version,
              primary_risk_cluster_id, cluster_membership_snapshot_id,
              capacity_claim_schema_version, capacity_claim_hash,
              reservation_idempotency_key
            ) VALUES (
              'reservation-active', 'promotion-active', 'lane-active',
              'ticket-active', 'signal-active', 'event-spec-1', 'profile-1',
              'account-1', 'MPG-001', 'SOLUSDT', 'long', 100, 10, 10,
              200000, 260000, 'active', 'policy-v1', 'instrument-1',
              'risk-policy-v1', 'cluster-1', 1, 'risk-policy-event-1', 2.5,
              'reserved_unreflected', 'episode-1', 'invocation-1', 'crypto',
              'perpetual', 'USDT', 'USDT', 'rule-snapshot-1', 'v1',
              'pricing-fact-1', 'account-fact-1', 'v1', 'cluster-1',
              'membership-snapshot-1', 'v1', 'claim-hash-1', 'claim-key-1'
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_action_time_tickets (
              ticket_id, action_time_lane_input_id, promotion_candidate_id,
              signal_event_id, event_spec_id, event_spec_version_id,
              candidate_scope_id, runtime_scope_binding_id, strategy_group_id,
              strategy_group_version_id, symbol, exchange_instrument_id, side,
              event_id, event_time_ms, trigger_candle_close_time_ms,
              runtime_profile_id, public_fact_snapshot_id,
              action_time_fact_snapshot_id, account_safe_fact_snapshot_id,
              account_mode_snapshot_id, budget_reservation_id, protection_ref_id,
              execution_policy_id, execution_policy_version, owner_policy_version,
              sizing_policy_version, protection_policy_version, target_notional,
              leverage, expires_at_ms, status, authority_boundary, ticket_hash,
              created_under_versions_hash, created_at_ms, exposure_episode_id,
              asset_class, instrument_type, capacity_claim_hash
            ) VALUES (
              'ticket-active', 'lane-active', 'promotion-active', 'signal-active',
              'event-spec-1', 'event-spec-version-1', 'scope-1', 'runtime-scope-1',
              'MPG-001', 'strategy-version-1', 'SOLUSDT', 'instrument-1', 'long',
              'event-1', 200000, 200000, 'profile-1', 'public-fact-1',
              'action-fact-1', 'account-safe-fact-1', 'account-mode-fact-1',
              'reservation-active', 'protection-1', 'execution-policy-1', 'v1',
              'v1', 'v1', 'v1', 100, 10, 260000, 'created', 'unit',
              'ticket-hash-active', 'versions-hash-1', 200000, 'episode-1',
              'crypto', 'perpetual', 'claim-hash-1'
            )
            """
        )
    )
