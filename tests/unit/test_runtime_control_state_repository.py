from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from src.infrastructure.runtime_control_state_repository import (
    PgBackedRuntimeControlStateRepository,
    RuntimeControlStateRepositoryError,
)
from scripts import runtime_active_observation_monitor


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py"
)
SEED_PATH = REPO_ROOT / "scripts/seed_runtime_control_state_foundation.py"
VALIDATOR_PATH = REPO_ROOT / "scripts/validate_runtime_control_state_repository.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def pg_control_connection():
    migration = _load_module(MIGRATION_PATH, "migration_086_repository")
    seed = _load_module(SEED_PATH, "seed_runtime_control_state_repository")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        old_op = migration.op
        migration.op = Operations(MigrationContext.configure(conn))
        try:
            migration.upgrade()
        finally:
            migration.op = old_op
        seed.seed_runtime_control_state_foundation(conn)
    with engine.connect() as conn:
        yield conn
    engine.dispose()


def test_pg_backed_runtime_control_state_repository_reads_seeded_state(
    pg_control_connection,
):
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770000120100,
    )

    state = repository.read_control_state()

    assert state["schema"] == "brc.runtime_control_state_repository.v1"
    assert state["source_mode"] == "db_backed"
    assert state["projection_target"] == "production_current"
    assert state["table_counts"]["strategy_groups"] == 5
    assert state["table_counts"]["strategy_side_event_specs"] == 6
    assert state["table_counts"]["candidate_scope"] == 22
    assert state["table_counts"]["runtime_scope_bindings"] == 22
    assert state["table_counts"]["current_projection_ownership"] == 6

    scope = {
        (row["strategy_group_id"], row["symbol"], row["side"])
        for row in state["candidate_scope"]
    }
    assert ("CPM-RO-001", "ETHUSDT", "short") not in scope
    assert ("MI-001", "AVAXUSDT", "short") not in scope
    assert ("BRF2-001", "BTCUSDT", "long") not in scope
    assert ("SOR-001", "ETHUSDT", "long") in scope
    assert ("SOR-001", "ETHUSDT", "short") in scope

    brf2_binding = next(
        row
        for row in state["runtime_scope_bindings"]
        if row["strategy_group_id"] == "BRF2-001"
        and row["symbol"] == "BTCUSDT"
        and row["side"] == "short"
    )
    assert brf2_binding["conditional_hard_gates"] == [
        "short_side_disable_clear",
        "squeeze_clear",
        "liquidity_clear",
    ]


def test_live_signal_writer_output_is_readable_by_repository(pg_control_connection):
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_runtime_fact_snapshots (
              fact_snapshot_id, strategy_group_id, symbol, side, runtime_profile_id,
              fact_surface, source_kind, source_ref, computed, satisfied,
              freshness_state, failed_facts, fact_values, blocker_class,
              observed_at_ms, valid_until_ms, created_at_ms
            ) VALUES (
              'fact:MPG-001:OPUSDT:long:public:writer-consumer',
              'MPG-001', 'OPUSDT', 'long', 'owner-runtime-console-v1',
              'pretrade_public', 'live_market', 'unit-test', 1, 1,
              'fresh', '[]', '{}', NULL,
              1770000120000, 1770003720000, 1770000120001
            )
            """
        )
    )
    pg_control_connection.commit()

    result = runtime_active_observation_monitor.write_runtime_signal_summaries_to_pg(
        {
            "runtime_summaries": [
                {
                    "runtime_instance_id": "runtime:MPG-001:OPUSDT:long",
                    "strategy_family_id": "MPG-001",
                    "strategy_family_version_id": "sgv:MPG-001:v1",
                    "symbol": "OPUSDT",
                    "side": "long",
                    "status": "ready_for_prepare",
                    "signal_summary": {
                        "signal_type": "would_enter",
                        "side": "long",
                        "timestamp_ms": 1770000120000,
                        "trigger_candle_close_time_ms": 1770000120000,
                        "confidence": "0.82",
                        "reason_codes": ["writer_consumer_contract"],
                    },
                }
            ]
        },
        database_url="unused://repository-test",
        allow_non_postgres_for_test=True,
        now_ms=1770000120100,
        conn=pg_control_connection,
    )

    assert result["status"] == "pg_live_signal_events_written"
    state = PgBackedRuntimeControlStateRepository(
        pg_control_connection
    ).read_control_state()
    signal = next(row for row in state["live_signal_events"])
    payload = signal["signal_payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    assert signal["strategy_group_id"] == "MPG-001"
    assert signal["symbol"] == "OPUSDT"
    assert signal["side"] == "long"
    assert signal["signal_type"] == "MPG-LONG"
    assert payload["detector_verdict"] == "would_enter"


def test_repository_monitor_read_profile_bounds_high_growth_tables(pg_control_connection):
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_watcher_runtime_coverage (
              runtime_coverage_id, strategy_group_id, symbol, side, detector_key,
              runtime_profile_id, coverage_state, liveness_state,
              last_tick_at_ms, valid_until_ms, is_current, created_at_ms
            ) VALUES (
              'coverage:historical:MPG-001:OPUSDT:long', 'MPG-001', 'OPUSDT',
              'long', 'detector:MPG-001:long', 'owner-runtime-console-v1',
              'covered', 'healthy', 1770000000000, 1770003600000, 0,
              1770000000000
            )
            """
        )
    )
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_live_signal_events (
              signal_event_id, candidate_scope_id, event_spec_id, strategy_group_id,
              symbol, side, detector_key, signal_type, source_kind, status,
              freshness_state, confidence, fact_snapshot_id, reason_codes,
              signal_payload, event_time_ms, trigger_candle_close_time_ms,
              observed_at_ms, expires_at_ms, invalidated_at_ms, created_at_ms
            ) VALUES (
              'signal:SOR-001:ETHUSDT:long:expired-monitor-bound',
              'candidate_scope:SOR-001:ETHUSDT:long:SOR-LONG',
              'event_spec:SOR-001:SOR-LONG:v1', 'SOR-001', 'ETHUSDT',
              'long', 'detector:SOR-001:long', 'SOR-LONG', 'live_market',
              'facts_validated', 'fresh', 0.9, 'fact:SOR:expired-monitor',
              '[]', '{}', 1770000120000, 1770000120000, 1770000120001,
              1770000120002, NULL, 1770000120003
            )
            """
        )
    )
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_pretrade_readiness_rows (
              readiness_row_id, candidate_scope_id, strategy_group_id, symbol, side,
              readiness_state, detector_state, watcher_state, public_facts_state,
              signal_lifecycle_status, signal_freshness_state, risk_state,
              scope_state, promotion_state, first_blocker_class,
              first_blocker_detail, next_action,
              stop_condition, evidence_ref, source_watermark, computed_at_ms,
              valid_until_ms
            ) VALUES (
              'readiness:SOR-001:ETHUSDT:long:expired-monitor-bound',
              'candidate_scope:SOR-001:ETHUSDT:long:SOR-LONG',
              'SOR-001', 'ETHUSDT', 'long', 'ready', 'attached', 'healthy',
              'satisfied', 'facts_validated', 'fresh', 'acceptable',
              'live_submit_allowed', 'action_time_lane',
              'action_time_preflight_ready', 'expired_monitor_bound',
              'materialize_ticket',
              'ticket_created_or_lane_expires', 'fact:SOR:expired-monitor',
              'unit', 1770000120003, 1770000120004
            )
            """
        )
    )
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_promotion_candidates (
              promotion_candidate_id, signal_event_id, readiness_row_id,
              strategy_group_id, symbol, side, promotion_scope, status,
              scope_state, risk_state, facts_snapshot_id, blockers,
              arbitration_rank, created_at_ms, expires_at_ms, closed_at_ms,
              authority_boundary
            ) VALUES (
              'promotion:SOR-001:ETHUSDT:long:expired-monitor-bound',
              'signal:SOR-001:ETHUSDT:long:expired-monitor-bound',
              'readiness:SOR-001:ETHUSDT:long:expired-monitor-bound',
              'SOR-001', 'ETHUSDT', 'long', 'live_submit_candidate',
              'arbitration_won', 'live_submit_allowed', 'acceptable',
              'fact:SOR:expired-monitor', '[]', 1, 1770000120004,
              1770000120005, NULL,
              'expired_pg_current_object_test; no_finalgate_no_operation_layer_no_exchange_write'
            )
            """
        )
    )
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_action_time_lane_inputs (
              action_time_lane_input_id, promotion_candidate_id, strategy_group_id,
              symbol, side, runtime_profile_id, lane_scope, status,
              signal_event_id, public_fact_snapshot_id, action_time_fact_snapshot_id,
              runtime_scope_binding_id, candidate_authorization_ref,
              runtime_safety_snapshot_id, first_blocker_class, created_at_ms,
              expires_at_ms, closed_at_ms, authority_boundary
            ) VALUES (
              'lane:SOR-001:ETHUSDT:long:expired-monitor-bound',
              'promotion:SOR-001:ETHUSDT:long:expired-monitor-bound',
              'SOR-001', 'ETHUSDT', 'long', 'owner-runtime-console-v1',
              'real_submit_candidate', 'ticket_created',
              'signal:SOR-001:ETHUSDT:long:expired-monitor-bound',
              'fact:SOR:expired-monitor', 'fact:SOR:expired-action-monitor',
              'runtime_scope:candidate_scope:SOR-001:ETHUSDT:long:SOR-LONG:owner-runtime-console-v1',
              'ticket:SOR-001:ETHUSDT:long:expired-monitor-bound',
              NULL, 'action_time_preflight_ready', 1770000120006,
              1770000120007, NULL,
              'expired_pg_current_object_test; no_finalgate_no_operation_layer_no_exchange_write'
            )
            """
        )
    )
    pg_control_connection.execute(
        text(
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
              created_under_versions_hash, created_at_ms
            ) VALUES (
              'ticket:SOR-001:ETHUSDT:long:expired-monitor-bound',
              'lane:SOR-001:ETHUSDT:long:expired-monitor-bound',
              'promotion:SOR-001:ETHUSDT:long:expired-monitor-bound',
              'signal:SOR-001:ETHUSDT:long:expired-monitor-bound',
              'event_spec:SOR-001:SOR-LONG:v1',
              'event_spec_version:SOR-001:SOR-LONG:v1',
              'candidate_scope:SOR-001:ETHUSDT:long:SOR-LONG',
              'runtime_scope:candidate_scope:SOR-001:ETHUSDT:long:SOR-LONG:owner-runtime-console-v1',
              'SOR-001', 'strategy_group_version:SOR-001:v1', 'ETHUSDT',
              'binance_usdm:ETHUSDT', 'long', 'SOR-LONG',
              1770000120000, 1770000120000, 'owner-runtime-console-v1',
              'fact:SOR:expired-monitor', 'fact:SOR:expired-action-monitor',
              'fact:SOR:expired-account-safe-monitor',
              'fact:SOR:expired-account-mode-monitor',
              'budget:SOR:expired-monitor', 'protection:SOR:expired-monitor',
              'execution_policy:owner-runtime-console-v1',
              'execution-policy-v1', 'owner-policy-v1', 'sizing-policy-v1',
              'protection-policy-v1', 100, 1, 1770000120008, 'created',
              'expired_pg_current_object_test; no_finalgate_no_operation_layer_no_exchange_write',
              'ticket-hash:expired-monitor-bound',
              'versions-hash:expired-monitor-bound', 1770000120009
            )
            """
        )
    )
    pg_control_connection.commit()

    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770001000000,
    )
    full_state = repository.read_control_state()
    monitor_state = repository.read_monitor_control_state()

    assert full_state["table_counts"]["watcher_runtime_coverage"] == 1
    assert full_state["table_counts"]["live_signal_events"] == 1
    assert full_state["table_counts"]["pretrade_readiness_rows"] == 1
    assert full_state["table_counts"]["promotion_candidates"] == 1
    assert full_state["table_counts"]["action_time_lane_inputs"] == 1
    assert full_state["table_counts"]["action_time_tickets"] == 1
    assert monitor_state["read_profile"] == "monitor_bounded_current"
    assert monitor_state["table_counts"]["watcher_runtime_coverage"] == 0
    assert monitor_state["table_counts"]["live_signal_events"] == 0
    assert monitor_state["table_counts"]["promotion_candidates"] == 0
    assert monitor_state["table_counts"]["action_time_lane_inputs"] == 0
    assert monitor_state["table_counts"]["action_time_tickets"] == 0


def test_pg_backed_runtime_control_state_repository_rejects_non_db_modes(
    pg_control_connection,
):
    with pytest.raises(RuntimeControlStateRepositoryError, match="source_mode='db_backed'"):
        PgBackedRuntimeControlStateRepository(
            pg_control_connection,
            source_mode="local_file_inventory",
        )

    with pytest.raises(RuntimeControlStateRepositoryError, match="production_current"):
        PgBackedRuntimeControlStateRepository(
            pg_control_connection,
            projection_target="diagnostic",
        )


def test_pg_backed_runtime_control_state_repository_fails_closed_without_tables():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        with engine.connect() as conn:
            repository = PgBackedRuntimeControlStateRepository(conn)
            with pytest.raises(
                RuntimeControlStateRepositoryError,
                match="tables missing",
            ):
                repository.read_control_state()
    finally:
        engine.dispose()


def test_pg_backed_runtime_control_state_repository_requires_projection_ownership(
    pg_control_connection,
):
    pg_control_connection.execute(text("DELETE FROM brc_current_projection_ownership"))
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770000120100,
    )

    with pytest.raises(
        RuntimeControlStateRepositoryError,
        match="current projection ownership is empty",
    ):
        repository.read_control_state()


def test_pg_backed_runtime_control_state_repository_requires_event_binding(
    pg_control_connection,
):
    pg_control_connection.execute(
        text(
            """
            DELETE FROM brc_candidate_scope_event_bindings
            WHERE candidate_scope_id = 'candidate_scope:CPM-RO-001:ETHUSDT:long:CPM-LONG'
            """
        )
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770000120100,
    )

    with pytest.raises(RuntimeControlStateRepositoryError, match="has no active event binding"):
        repository.read_control_state()


@pytest.mark.parametrize(
    ("candidate_scope_id", "side"),
    [
        ("candidate_scope:CPM-RO-001:ETHUSDT:long:CPM-LONG", "short"),
        ("candidate_scope:MPG-001:OPUSDT:long:MPG-LONG", "short"),
        ("candidate_scope:MI-001:AVAXUSDT:long:MI-LONG", "short"),
        ("candidate_scope:BRF2-001:BTCUSDT:short:BRF2-SHORT", "long"),
    ],
)
def test_pg_backed_runtime_control_state_repository_rejects_unsupported_active_side(
    pg_control_connection,
    candidate_scope_id: str,
    side: str,
):
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_strategy_group_candidate_scope
            SET side = :side
            WHERE candidate_scope_id = :candidate_scope_id
            """
        ),
        {"candidate_scope_id": candidate_scope_id, "side": side},
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770000120100,
    )

    with pytest.raises(RuntimeControlStateRepositoryError, match="mismatches candidate side"):
        repository.read_control_state()


def test_pg_backed_runtime_control_state_repository_rejects_generic_current_event_spec(
    pg_control_connection,
):
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_strategy_side_event_specs (
                event_spec_id, strategy_group_id, strategy_group_version_id,
                event_id, side, timeframe, event_spec_version, status,
                freshness_window_ms, time_authority, protection_ref_type,
                created_at_ms, created_by
            ) VALUES (
                'event_spec:SOR-001:SOR-GENERIC:v1', 'SOR-001',
                'sgv:SOR-001:v1', 'SOR-GENERIC', 'long', '15m', 'v1',
                'current', 900000, 'trigger_candle_close_time_ms',
                'opening_range_low_reference', 1770000000000, 'unit_test'
            )
            """
        )
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770000120100,
    )

    with pytest.raises(RuntimeControlStateRepositoryError, match="event_id is not side-specific"):
        repository.read_control_state()


def test_pg_backed_runtime_control_state_repository_rejects_event_without_current_version(
    pg_control_connection,
):
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_strategy_side_event_specs (
                event_spec_id, strategy_group_id, strategy_group_version_id,
                event_id, side, timeframe, event_spec_version, status,
                freshness_window_ms, time_authority, protection_ref_type,
                created_at_ms, created_by
            ) VALUES (
                'event_spec:SUPPORT-001:SUPPORT-LONG:v1', 'SUPPORT-001',
                'sgv:SUPPORT-001:v1', 'SUPPORT-LONG', 'long', '1h', 'v1',
                'current', 3600000, 'trigger_candle_close_time_ms',
                'support_reference', 1770000000000, 'unit_test'
            )
            """
        )
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770000120100,
    )

    with pytest.raises(
        RuntimeControlStateRepositoryError,
        match="has no current StrategyGroup version",
    ):
        repository.read_control_state()


def test_pg_backed_runtime_control_state_repository_requires_hard_required_facts(
    pg_control_connection,
):
    pg_control_connection.execute(
        text(
            """
            DELETE FROM brc_strategy_event_required_facts
            WHERE event_spec_id = 'event_spec:MI-001:MI-LONG:v1'
            """
        )
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770000120100,
    )

    with pytest.raises(RuntimeControlStateRepositoryError, match="MI-LONG.*no required facts"):
        repository.read_control_state()


def test_pg_backed_runtime_control_state_repository_requires_exact_required_fact_manifest(
    pg_control_connection,
):
    pg_control_connection.execute(
        text(
            """
            DELETE FROM brc_strategy_event_required_facts
            WHERE event_spec_id = 'event_spec:CPM-RO-001:CPM-LONG:v1'
              AND fact_key = 'htf_trend_intact'
            """
        )
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770000120100,
    )

    with pytest.raises(
        RuntimeControlStateRepositoryError,
        match="CPM-LONG.*RequiredFacts manifest mismatch.*htf_trend_intact",
    ):
        repository.read_control_state()


def test_pg_backed_runtime_control_state_repository_requires_exact_disable_fact_manifest(
    pg_control_connection,
):
    pg_control_connection.execute(
        text(
            """
            DELETE FROM brc_strategy_event_required_facts
            WHERE event_spec_id = 'event_spec:BRF2-001:BRF2-SHORT:v1'
              AND fact_key = 'strong_uptrend_disable'
            """
        )
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770000120100,
    )

    with pytest.raises(
        RuntimeControlStateRepositoryError,
        match="BRF2-SHORT.*disable manifest mismatch.*strong_uptrend_disable",
    ):
        repository.read_control_state()


def test_pg_backed_runtime_control_state_repository_rejects_signal_event_spec_mismatch(
    pg_control_connection,
):
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_live_signal_events (
              signal_event_id, candidate_scope_id, event_spec_id, strategy_group_id,
              symbol, side, detector_key, signal_type, source_kind, status,
              freshness_state, confidence, fact_snapshot_id, reason_codes,
              signal_payload, event_time_ms, trigger_candle_close_time_ms,
              observed_at_ms, expires_at_ms, invalidated_at_ms, created_at_ms
            ) VALUES (
              'signal:SOR-001:ETHUSDT:long:wrong-event',
              'candidate_scope:SOR-001:ETHUSDT:long:SOR-LONG',
              'event_spec:SOR-001:SOR-SHORT:v1', 'SOR-001', 'ETHUSDT',
              'long', 'detector:SOR-001:long', 'SOR-SHORT', 'live_market',
              'facts_validated', 'fresh', 0.9, 'fact:SOR:wrong-event',
              '[]', '{}', 1770000120000, 1770000120000, 1770000120001,
              1770000720000, NULL, 1770000120002
            )
            """
        )
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770000120100,
    )

    with pytest.raises(RuntimeControlStateRepositoryError, match="mismatches candidate event spec"):
        repository.read_control_state()


def test_pg_backed_runtime_control_state_repository_rejects_generic_sor_signal_type(
    pg_control_connection,
):
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_live_signal_events (
              signal_event_id, candidate_scope_id, event_spec_id, strategy_group_id,
              symbol, side, detector_key, signal_type, source_kind, status,
              freshness_state, confidence, fact_snapshot_id, reason_codes,
              signal_payload, event_time_ms, trigger_candle_close_time_ms,
              observed_at_ms, expires_at_ms, invalidated_at_ms, created_at_ms
            ) VALUES (
              'signal:SOR-001:ETHUSDT:long:generic-type',
              'candidate_scope:SOR-001:ETHUSDT:long:SOR-LONG',
              'event_spec:SOR-001:SOR-LONG:v1', 'SOR-001', 'ETHUSDT',
              'long', 'detector:SOR-001:long', 'SOR-GENERIC', 'live_market',
              'facts_validated', 'fresh', 0.9, 'fact:SOR:generic-type',
              '[]', '{}', 1770000120000, 1770000120000, 1770000120001,
              1770000720000, NULL, 1770000120002
            )
            """
        )
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770000120100,
    )

    with pytest.raises(RuntimeControlStateRepositoryError, match="signal_type must equal event_id"):
        repository.read_control_state()


def test_pg_backed_runtime_control_state_repository_rejects_generated_at_as_event_time(
    pg_control_connection,
):
    with pytest.raises(IntegrityError, match="ck_brc_live_signal_no_generated_at_event_time"):
        pg_control_connection.execute(
            text(
                """
                INSERT INTO brc_live_signal_events (
                  signal_event_id, candidate_scope_id, event_spec_id, strategy_group_id,
                  symbol, side, detector_key, signal_type, source_kind, status,
                  freshness_state, confidence, fact_snapshot_id, reason_codes,
                  signal_payload, event_time_ms, trigger_candle_close_time_ms,
                  observed_at_ms, expires_at_ms, invalidated_at_ms, created_at_ms
                ) VALUES (
                  'signal:SOR-001:ETHUSDT:long:generated-at-time',
                  'candidate_scope:SOR-001:ETHUSDT:long:SOR-LONG',
                  'event_spec:SOR-001:SOR-LONG:v1', 'SOR-001', 'ETHUSDT',
                  'long', 'detector:SOR-001:long', 'SOR-LONG', 'live_market',
                  'facts_validated', 'fresh', 0.9, 'fact:SOR:generated-at-time',
                  '[]', '{}', 1770000120000, 1770000120000, 1770000120001,
                  1770000720000, NULL, 1770000120000
                )
                """
            )
        )


def test_pg_backed_runtime_control_state_repository_rejects_lane_without_arbitration_winner(
    pg_control_connection,
):
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_live_signal_events (
              signal_event_id, candidate_scope_id, event_spec_id, strategy_group_id,
              symbol, side, detector_key, signal_type, source_kind, status,
              freshness_state, confidence, fact_snapshot_id, reason_codes,
              signal_payload, event_time_ms, trigger_candle_close_time_ms,
              observed_at_ms, expires_at_ms, invalidated_at_ms, created_at_ms
            ) VALUES (
              'signal:SOR-001:ETHUSDT:long:lost',
              'candidate_scope:SOR-001:ETHUSDT:long:SOR-LONG',
              'event_spec:SOR-001:SOR-LONG:v1', 'SOR-001', 'ETHUSDT',
              'long', 'detector:SOR-001:long', 'SOR-LONG', 'live_market',
              'facts_validated', 'fresh', 0.9, 'fact:SOR:lost',
              '[]', '{}', 1770000120000, 1770000120000, 1770000120001,
              1770000720000, NULL, 1770000120002
            )
            """
        )
    )
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_pretrade_readiness_rows (
              readiness_row_id, candidate_scope_id, strategy_group_id, symbol,
              side, readiness_state, detector_state, watcher_state,
              public_facts_state, signal_lifecycle_status,
              signal_freshness_state, risk_state, scope_state, promotion_state,
              first_blocker_class, first_blocker_detail, next_action,
              stop_condition, evidence_ref, source_watermark, computed_at_ms,
              valid_until_ms
            ) VALUES (
              'readiness:SOR-001:ETHUSDT:long:lost',
              'candidate_scope:SOR-001:ETHUSDT:long:SOR-LONG',
              'SOR-001', 'ETHUSDT', 'long', 'ready', 'ready', 'fresh',
              'satisfied', 'facts_validated', 'fresh', 'acceptable',
              'live_submit_allowed', 'action_time_lane',
              'action_time_preflight_ready', 'ready', 'materialize_ticket',
              'ticket_created_or_lane_expires', 'fact:SOR:lost', 'unit',
              1770000120003, 1770000720000
            )
            """
        )
    )
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_promotion_candidates (
              promotion_candidate_id, signal_event_id, readiness_row_id,
              strategy_group_id, symbol, side, promotion_scope, status,
              scope_state, risk_state, facts_snapshot_id, blockers,
              arbitration_rank, created_at_ms, expires_at_ms, closed_at_ms,
              authority_boundary
            ) VALUES (
              'promotion:SOR-001:ETHUSDT:long:lost',
              'signal:SOR-001:ETHUSDT:long:lost',
              'readiness:SOR-001:ETHUSDT:long:lost',
              'SOR-001', 'ETHUSDT', 'long', 'live_submit_candidate',
              'arbitration_lost', 'live_submit_allowed', 'acceptable',
              'fact:SOR:lost', '[]', 2, 1770000120004, 1770000720000,
              1770000120005,
              'pg_promotion_candidate_non_executing; no_finalgate_no_operation_layer_no_exchange_write'
            )
            """
        )
    )
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_action_time_lane_inputs (
              action_time_lane_input_id, promotion_candidate_id, strategy_group_id,
              symbol, side, runtime_profile_id, lane_scope, status,
              signal_event_id, public_fact_snapshot_id, action_time_fact_snapshot_id,
              runtime_scope_binding_id, candidate_authorization_ref,
              runtime_safety_snapshot_id, first_blocker_class, created_at_ms,
              expires_at_ms, closed_at_ms, authority_boundary
            ) VALUES (
              'lane:SOR-001:ETHUSDT:long:lost',
              'promotion:SOR-001:ETHUSDT:long:lost', 'SOR-001', 'ETHUSDT',
              'long', 'owner-runtime-console-v1', 'real_submit_candidate',
              'ticket_pending', 'signal:SOR-001:ETHUSDT:long:lost',
              'fact:SOR:lost', 'fact:SOR:action',
              'runtime_scope:candidate_scope:SOR-001:ETHUSDT:long:SOR-LONG:owner-runtime-console-v1',
              NULL, NULL, 'action_time_preflight_ready', 1770000120006,
              1770000720000, NULL,
              'pg_real_submit_candidate_identity_only; no_finalgate_no_operation_layer_no_exchange_write'
            )
            """
        )
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770000120010,
    )

    with pytest.raises(RuntimeControlStateRepositoryError, match="does not reference arbitration_won"):
        repository.read_control_state()


def test_pg_backed_runtime_control_state_repository_ignores_closed_rehearsal_lineage(
    pg_control_connection,
):
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_live_signal_events (
              signal_event_id, candidate_scope_id, event_spec_id, strategy_group_id,
              symbol, side, detector_key, signal_type, source_kind, status,
              freshness_state, confidence, fact_snapshot_id, reason_codes,
              signal_payload, event_time_ms, trigger_candle_close_time_ms,
              observed_at_ms, expires_at_ms, invalidated_at_ms, created_at_ms
            ) VALUES (
              'signal:historical:closed:review', 'candidate_scope:retired',
              'event_spec:SOR-001:SOR-LONG:v1', 'SOR-001', 'ETHUSDT',
              'long', 'detector:SOR-001:long', 'SOR-LONG', 'historical',
              'stale', 'stale', NULL, NULL, '[]', '{}', 1770000120000,
              1770000120000, 1770000120001, NULL, 1770000130000,
              1770000120002
            )
            """
        )
    )
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_promotion_candidates (
              promotion_candidate_id, signal_event_id, readiness_row_id,
              strategy_group_id, symbol, side, promotion_scope, status,
              scope_state, risk_state, facts_snapshot_id, blockers,
              arbitration_rank, created_at_ms, expires_at_ms, closed_at_ms,
              authority_boundary
            ) VALUES (
              'promotion:historical:closed:review',
              'signal:historical:closed:review',
              'readiness:historical:closed:review',
              'SOR-001', 'ETHUSDT', 'long', 'action_time_rehearsal',
              'arbitration_lost', 'live_submit_allowed', 'acceptable',
              NULL, '[]', 2, 1770000120004, 1770000720000,
              1770000120005,
              'historical_rehearsal_lineage; no_finalgate_no_operation_layer_no_exchange_write'
            )
            """
        )
    )
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_action_time_lane_inputs (
              action_time_lane_input_id, promotion_candidate_id, strategy_group_id,
              symbol, side, runtime_profile_id, lane_scope, status,
              signal_event_id, public_fact_snapshot_id, action_time_fact_snapshot_id,
              runtime_scope_binding_id, candidate_authorization_ref,
              runtime_safety_snapshot_id, first_blocker_class, created_at_ms,
              expires_at_ms, closed_at_ms, authority_boundary
            ) VALUES (
              'lane:historical:closed:review',
              'promotion:historical:closed:review', 'SOR-001', 'ETHUSDT',
              'long', 'owner-runtime-console-v1', 'rehearsal',
              'closed', 'signal:historical:closed:review', NULL, NULL,
              'runtime_scope:retired', NULL, NULL, NULL, 1770000120006,
              1770000720000, 1770000120010,
              'closed_rehearsal_lineage; no_finalgate_no_operation_layer_no_exchange_write'
            )
            """
        )
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(pg_control_connection)

    state = repository.read_control_state()

    assert state["table_counts"]["action_time_lane_inputs"] == 1
    assert state["table_counts"]["promotion_candidates"] == 1
    assert state["table_counts"]["live_signal_events"] == 1


def test_pg_backed_runtime_control_state_repository_requires_runtime_policy_binding(
    pg_control_connection,
):
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_runtime_scope_bindings
            SET policy_current_id = 'policy_current:missing'
            WHERE runtime_scope_binding_id =
              'runtime_scope:candidate_scope:MPG-001:OPUSDT:long:MPG-LONG:owner-runtime-console-v1'
            """
        )
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(pg_control_connection)

    with pytest.raises(RuntimeControlStateRepositoryError, match="has no current owner policy"):
        repository.read_control_state()


def test_runtime_control_state_repository_validator_rejects_non_postgres_without_test_flag(
    capsys,
):
    validator = _load_module(VALIDATOR_PATH, "validate_runtime_control_state_repository")

    assert validator.main(["--database-url", "sqlite:///tmp/runtime-control-state.db"]) == 2

    captured = capsys.readouterr()
    assert "requires PostgreSQL DSN" in captured.err


def test_runtime_control_state_repository_validator_reports_seeded_state(
    tmp_path: Path,
    capsys,
):
    database_url = f"sqlite:///{tmp_path / 'runtime-control-state.db'}"
    _seed_database_url(database_url)
    validator = _load_module(VALIDATOR_PATH, "validate_runtime_control_state_repository")

    assert (
        validator.main(
            [
                "--database-url",
                database_url,
                "--allow-non-postgres-for-test",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "runtime_control_state_repository_valid"
    assert payload["strategy_group_count"] == 5
    assert payload["event_spec_count"] == 6
    assert payload["candidate_scope_count"] == 22
    assert payload["runtime_scope_binding_count"] == 22
    assert payload["current_projection_ownership_count"] == 6
    assert all(value is False for value in payload["forbidden_effects"].values())


def _seed_database_url(database_url: str) -> None:
    migration = _load_module(MIGRATION_PATH, "migration_086_repository_validator")
    seed = _load_module(SEED_PATH, "seed_runtime_control_state_repository_validator")
    engine = create_engine(database_url)
    try:
        with engine.begin() as conn:
            old_op = migration.op
            migration.op = Operations(MigrationContext.configure(conn))
            try:
                migration.upgrade()
            finally:
                migration.op = old_op
            seed.seed_runtime_control_state_foundation(conn)
    finally:
        engine.dispose()
