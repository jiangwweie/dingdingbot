from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy.pool import StaticPool


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/2026-07-13-118_conserve_runtime_lane_identity.py"
)


def _migration():
    spec = importlib.util.spec_from_file_location("migration_118_lane_identity", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_legacy_schema(conn: sa.engine.Connection) -> None:
    conn.execute(
        sa.text(
            """
            CREATE TABLE brc_live_signal_events (
              signal_event_id TEXT PRIMARY KEY,
              candidate_scope_id TEXT,
              event_spec_id TEXT,
              strategy_group_id TEXT,
              symbol TEXT,
              side TEXT,
              detector_key TEXT,
              signal_type TEXT,
              source_kind TEXT,
              status TEXT,
              freshness_state TEXT,
              event_time_ms INTEGER,
              expires_at_ms INTEGER,
              invalidated_at_ms INTEGER
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE TABLE brc_runtime_process_outcomes (
              process_outcome_id TEXT PRIMARY KEY,
              process_name TEXT NOT NULL,
              scope_key TEXT NOT NULL,
              run_id TEXT NOT NULL,
              process_state TEXT NOT NULL,
              business_state TEXT NOT NULL,
              first_blocker TEXT,
              started_at_ms INTEGER NOT NULL,
              completed_at_ms INTEGER NOT NULL,
              runtime_head TEXT NOT NULL,
              source_watermark TEXT NOT NULL,
              projector_owner TEXT NOT NULL,
              updated_at_ms INTEGER NOT NULL
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE TABLE brc_promotion_candidates (
              promotion_candidate_id TEXT PRIMARY KEY,
              signal_event_id TEXT NOT NULL,
              status TEXT NOT NULL,
              expires_at_ms INTEGER NOT NULL,
              closed_at_ms INTEGER
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE TABLE brc_action_time_lane_inputs (
              action_time_lane_input_id TEXT PRIMARY KEY,
              promotion_candidate_id TEXT NOT NULL,
              signal_event_id TEXT NOT NULL,
              status TEXT NOT NULL,
              expires_at_ms INTEGER NOT NULL,
              closed_at_ms INTEGER
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE TABLE brc_action_time_tickets (
              ticket_id TEXT PRIMARY KEY,
              action_time_lane_input_id TEXT NOT NULL,
              promotion_candidate_id TEXT NOT NULL,
              signal_event_id TEXT NOT NULL,
              status TEXT NOT NULL,
              expires_at_ms INTEGER NOT NULL
            )
            """
        )
    )


def _run_upgrade(conn: sa.engine.Connection) -> None:
    migration = _migration()
    old_op = migration.op
    migration.op = Operations(MigrationContext.configure(conn))
    try:
        migration.upgrade()
    finally:
        migration.op = old_op


def test_migration_adds_typed_identity_and_reconciles_only_known_false_cpm_short_row():
    engine = sa.create_engine("sqlite://", poolclass=StaticPool)
    try:
        with engine.begin() as conn:
            _create_legacy_schema(conn)
            conn.execute(
                sa.text(
                    """
                    INSERT INTO brc_runtime_process_outcomes VALUES (
                      'known-false', 'live_signal_materialization',
                      'lane:CPM-RO-001:SOLUSDT:short', 'run-1',
                      'retryable_failure', 'temporarily_unavailable',
                      'pg_live_signal_event_materialization_failed:runtime_summary_blocked:waiting_for_signal',
                      1, 1, 'head', 'strategy-runtime-d3e7af7d4f6e:1783907999999',
                      'runtime_process_outcome_projector', 1
                    )
                    """
                )
            )
            conn.execute(
                sa.text(
                    """
                    INSERT INTO brc_runtime_process_outcomes VALUES (
                      'unrelated-cpm', 'live_signal_materialization',
                      'lane:CPM-RO-001:SOLUSDT:short', 'run-2',
                      'retryable_failure', 'temporarily_unavailable',
                      'different_blocker', 2, 2, 'head', 'different-watermark',
                      'runtime_process_outcome_projector', 2
                    )
                    """
                )
            )
            conn.execute(
                sa.text(
                    """
                    INSERT INTO brc_live_signal_events VALUES (
                      'legacy-live', 'scope-1', 'event-1', 'CPM-RO-001', 'SOLUSDT',
                      'long', 'watcher', 'CPM-LONG', 'live_market',
                      'facts_validated', 'fresh', 1000, 2000, NULL
                    )
                    """
                )
            )
            conn.execute(
                sa.text(
                    """
                    INSERT INTO brc_promotion_candidates VALUES (
                      'legacy-promotion', 'legacy-live', 'arbitration_won', 9999999999999, NULL
                    )
                    """
                )
            )
            conn.execute(
                sa.text(
                    """
                    INSERT INTO brc_action_time_lane_inputs VALUES (
                      'legacy-lane', 'legacy-promotion', 'legacy-live', 'ticket_pending',
                      9999999999999, NULL
                    )
                    """
                )
            )
            conn.execute(
                sa.text(
                    """
                    INSERT INTO brc_action_time_tickets VALUES (
                      'legacy-ticket', 'legacy-lane', 'legacy-promotion', 'legacy-live',
                      'created', 9999999999999
                    )
                    """
                )
            )
            _run_upgrade(conn)

            signal_columns = {
                row["name"] for row in sa.inspect(conn).get_columns("brc_live_signal_events")
            }
            outcome_columns = {
                row["name"]
                for row in sa.inspect(conn).get_columns("brc_runtime_process_outcomes")
            }
            promotion_columns = {
                row["name"]
                for row in sa.inspect(conn).get_columns("brc_promotion_candidates")
            }
            lane_columns = {
                row["name"]
                for row in sa.inspect(conn).get_columns("brc_action_time_lane_inputs")
            }
            ticket_columns = {
                row["name"]
                for row in sa.inspect(conn).get_columns("brc_action_time_tickets")
            }
            assert {
                "candidate_scope_event_binding_id",
                "runtime_scope_binding_id",
                "runtime_instance_id",
                "strategy_group_version_id",
                "event_spec_version",
                "event_id",
                "timeframe",
                "lane_identity_key",
                "runtime_profile_id",
                "policy_current_id",
                "asset_class",
                "time_authority",
                "source_watermark",
            } <= signal_columns
            assert {"lane_identity_key", "source_watermark"} <= promotion_columns
            assert {"lane_identity_key", "source_watermark"} <= lane_columns
            assert {"lane_identity_key", "source_watermark"} <= ticket_columns
            assert {
                "scope_kind",
                "candidate_scope_id",
                "candidate_scope_event_binding_id",
                "runtime_scope_binding_id",
                "runtime_instance_id",
                "strategy_group_version_id",
                "asset_class",
                "event_spec_version",
                "event_id",
                "timeframe",
                "lane_identity_key",
                "legacy_evidence",
            } <= outcome_columns

            known = conn.execute(
                sa.text(
                    """
                    SELECT process_state, business_state, first_blocker, scope_kind,
                           legacy_evidence
                    FROM brc_runtime_process_outcomes
                    WHERE process_outcome_id = 'known-false'
                    """
                )
            ).mappings().one()
            assert dict(known) == {
                "process_state": "noop",
                "business_state": "completed",
                "first_blocker": "legacy_invalid_runtime_lane_identity_reconciled",
                "scope_kind": "legacy_invalid_scope",
                "legacy_evidence": (
                    "pg_live_signal_event_materialization_failed:"
                    "runtime_summary_blocked:waiting_for_signal"
                ),
            }
            unrelated = conn.execute(
                sa.text(
                    """
                    SELECT process_state, business_state, first_blocker, scope_kind
                    FROM brc_runtime_process_outcomes
                    WHERE process_outcome_id = 'unrelated-cpm'
                    """
                )
            ).mappings().one()
            assert dict(unrelated) == {
                "process_state": "retryable_failure",
                "business_state": "temporarily_unavailable",
                "first_blocker": "different_blocker",
                "scope_kind": None,
            }
            legacy_signal = conn.execute(
                sa.text(
                    """
                    SELECT status, freshness_state, invalidated_at_ms
                    FROM brc_live_signal_events
                    WHERE signal_event_id = 'legacy-live'
                    """
                )
            ).mappings().one()
            assert dict(legacy_signal)["status"] == "superseded"
            assert dict(legacy_signal)["freshness_state"] == "expired"
            assert dict(legacy_signal)["invalidated_at_ms"] is not None
            assert conn.execute(
                sa.text(
                    "SELECT status, closed_at_ms FROM brc_promotion_candidates "
                    "WHERE promotion_candidate_id = 'legacy-promotion'"
                )
            ).mappings().one()["status"] == "expired"
            assert conn.execute(
                sa.text(
                    "SELECT status, closed_at_ms FROM brc_action_time_lane_inputs "
                    "WHERE action_time_lane_input_id = 'legacy-lane'"
                )
            ).mappings().one()["status"] == "invalidated"
            assert conn.execute(
                sa.text(
                    "SELECT status FROM brc_action_time_tickets "
                    "WHERE ticket_id = 'legacy-ticket'"
                )
            ).scalar_one() == "invalidated"
    finally:
        engine.dispose()
