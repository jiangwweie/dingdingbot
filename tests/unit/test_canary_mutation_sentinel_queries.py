from __future__ import annotations

import sqlalchemy as sa

from src.application.readmodels.canary_mutation_sentinel import (
    CanaryMutationSentinelScopeV1,
)
from src.infrastructure.canary_mutation_sentinel_queries import (
    build_canary_sentinel_queries,
    expected_storage_columns,
)
from tests.unit.test_action_time_full_chain_impact import pg_control_connection


def _scope() -> CanaryMutationSentinelScopeV1:
    return CanaryMutationSentinelScopeV1(
        fact_snapshot_ids=("fact:1",),
        signal_event_ids=("signal:1",),
        lane_ids=("lane:1",),
        lane_identity_keys=("identity:1",),
        ticket_ids=("ticket:1",),
        protected_attempt_ids=("attempt:1",),
        lifecycle_ids=("lifecycle:1",),
        protection_set_ids=("set:1",),
        account_mode_ids=("mode:1",),
        readiness_keys=(("SOR-001", "ETHUSDT", "long"),),
        snapshot_ids=("snapshot:1",),
        projection_run_ids=("projection:1",),
        release_activation_process_outcome_id="process_outcome:release",
    )


def test_query_plan_has_all_18_bounded_slices_and_no_select_star():
    queries = build_canary_sentinel_queries(
        _scope(), canary_window_floor_ms=1_800_000_000_000
    )

    assert len(queries) == 18
    assert len({query.slice_id for query in queries}) == 18
    assert all("SELECT * FROM brc_" not in query.sql for query in queries)
    assert all(f"LIMIT {query.row_limit + 1}" in query.sql or query.slice_id == "process_current" for query in queries)


def test_process_queries_use_exact_index_compatible_and_window_predicates():
    queries = {
        query.slice_id: query
        for query in build_canary_sentinel_queries(
            _scope(), canary_window_floor_ms=1_800_000_000_000
        )
    }
    current = queries["process_current"].sql
    window = queries["process_window"].sql

    assert "CROSS JOIN LATERAL" in current
    assert "outcome.lane_identity_key=requested.lane_identity_key" in current
    assert "outcome.process_name=requested.process_name" in current
    assert "ORDER BY outcome.updated_at_ms DESC,outcome.process_outcome_id DESC LIMIT 1" in current
    assert "release_activation_id" in current
    assert "updated_at_ms >= :canary_window_floor_ms" in window
    assert "scope_key='production:tokyo'" in window
    assert "lane_identity_key = ANY(:lane_identity_keys)" in window


def test_ticket_and_exchange_slices_have_no_status_filter():
    queries = {
        query.slice_id: query
        for query in build_canary_sentinel_queries(_scope(), canary_window_floor_ms=1)
    }
    assert "status" not in queries["tickets"].sql.split(" WHERE ", 1)[1].split(" ORDER BY ", 1)[0]
    assert "command_state" not in queries["exchange_commands"].sql.split(" WHERE ", 1)[1].split(" ORDER BY ", 1)[0]


def test_storage_contract_names_only_explicitly_excluded_volatile_columns():
    expected = expected_storage_columns()

    assert "payload" in expected["brc_control_read_model_snapshots"]
    assert "semantic_payload" not in expected["brc_control_read_model_snapshots"]
    assert "generated_at_ms" in expected["brc_control_read_model_snapshots"]
    assert "computed_at_ms" in expected["brc_pretrade_readiness_rows"]
    assert "updated_at_ms" in expected["brc_goal_status_current"]
    assert {"started_at_ms", "finished_at_ms"} <= expected["brc_projection_runs"]


def test_storage_contract_matches_schema_124_fixture(pg_control_connection):
    pg_control_connection.execute(
        sa.text("ALTER TABLE brc_runtime_capabilities_current ADD COLUMN proof_schema VARCHAR(128)")
    )
    pg_control_connection.execute(
        sa.text("ALTER TABLE brc_runtime_capabilities_current ADD COLUMN proof_payload JSON")
    )
    inspector = sa.inspect(pg_control_connection)
    for relation, expected in expected_storage_columns().items():
        actual = {str(column["name"]) for column in inspector.get_columns(relation)}
        assert actual == set(expected), relation
