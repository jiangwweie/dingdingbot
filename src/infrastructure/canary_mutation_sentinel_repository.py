"""Read-only PostgreSQL capture for the deployment mutation sentinel."""

from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa

from src.application.readmodels.canary_mutation_sentinel import (
    CanaryMutationSentinelProjection,
    CanaryMutationSentinelScopeV1,
)
from src.infrastructure.canary_mutation_sentinel_queries import (
    build_canary_sentinel_queries,
    expected_storage_columns,
)


def capture_canary_mutation_sentinel(
    conn: sa.engine.Connection,
    *,
    scope: CanaryMutationSentinelScopeV1,
    canary_db_now_ms: int,
    canary_window_floor_ms: int,
) -> CanaryMutationSentinelProjection:
    if conn.dialect.name != "postgresql":
        raise ValueError("canary_sentinel_postgresql_required")
    conn.execute(sa.text("SET LOCAL statement_timeout = '10s'"))
    conn.execute(sa.text("SET LOCAL TRANSACTION READ ONLY"))
    _verify_storage_schemas(conn)
    slices: dict[str, list[dict[str, Any]]] = {}
    for query in build_canary_sentinel_queries(
        scope,
        canary_window_floor_ms=canary_window_floor_ms,
    ):
        rows = [dict(row) for row in conn.execute(sa.text(query.sql), query.params).mappings()]
        if len(rows) > query.row_limit:
            raise ValueError(f"canary_sentinel_row_limit_exceeded:{query.slice_id}")
        _guard_logical_value_sizes(query.slice_id, rows)
        slices[query.slice_id] = rows
    return CanaryMutationSentinelProjection.freeze(
        canary_db_now_ms=canary_db_now_ms,
        canary_window_floor_ms=canary_window_floor_ms,
        slices=slices,
        require_complete=True,
    )


def database_clock_ms(conn: sa.engine.Connection) -> int:
    value = conn.execute(
        sa.text("SELECT floor(extract(epoch from clock_timestamp()) * 1000)::bigint")
    ).scalar_one()
    return int(value)


def discover_canary_mutation_scope(
    conn: sa.engine.Connection,
    *,
    target_runtime_head: str,
) -> CanaryMutationSentinelScopeV1:
    """Freeze exact bounded identifiers after final pre-canary projection."""

    if conn.dialect.name != "postgresql":
        raise ValueError("canary_sentinel_postgresql_required")
    if len(target_runtime_head) != 40 or any(
        char not in "0123456789abcdef" for char in target_runtime_head
    ):
        raise ValueError("target_runtime_head_invalid")
    conn.execute(sa.text("SET LOCAL statement_timeout = '10s'"))
    conn.execute(sa.text("SET LOCAL TRANSACTION READ ONLY"))

    lanes = _rows(
        conn,
        "SELECT action_time_lane_input_id,signal_event_id,public_fact_snapshot_id,"
        "action_time_fact_snapshot_id,account_safe_fact_snapshot_id,"
        "account_mode_fact_snapshot_id FROM brc_action_time_lane_inputs "
        "ORDER BY created_at_ms DESC,action_time_lane_input_id DESC LIMIT 22",
    )
    readiness = _rows(
        conn,
        "SELECT strategy_group_id,symbol,side FROM brc_pretrade_readiness_rows "
        "ORDER BY strategy_group_id,symbol,side LIMIT 22",
    )
    recent_facts = [
        str(row["fact_snapshot_id"])
        for row in _rows(
            conn,
            "SELECT fact_snapshot_id FROM brc_runtime_fact_snapshots "
            "ORDER BY created_at_ms DESC,fact_snapshot_id DESC LIMIT 128",
        )
        if row.get("fact_snapshot_id") is not None
    ]
    lane_facts = {
        str(row[name])
        for row in lanes
        for name in (
            "public_fact_snapshot_id", "action_time_fact_snapshot_id",
            "account_safe_fact_snapshot_id", "account_mode_fact_snapshot_id",
        )
        if row.get(name)
    }
    facts = _bounded_scope_ids(
        required_ids=lane_facts,
        recent_ids=recent_facts,
        limit=128,
        overflow_error="canary_scope_fact_limit_exceeded",
    )
    recent_signals = [
        str(row["signal_event_id"])
        for row in _rows(
            conn,
            "SELECT signal_event_id FROM brc_live_signal_events "
            "ORDER BY created_at_ms DESC,signal_event_id DESC LIMIT 22",
        )
        if row.get("signal_event_id") is not None
    ]
    signals = _bounded_scope_ids(
        required_ids={
            str(row["signal_event_id"])
            for row in lanes
            if row.get("signal_event_id")
        },
        recent_ids=recent_signals,
        limit=22,
        overflow_error="canary_scope_signal_limit_exceeded",
    )
    lane_ids = sorted(str(row["action_time_lane_input_id"]) for row in lanes)
    tickets = _rows_for_any(
        conn,
        "SELECT ticket_id FROM brc_action_time_tickets WHERE "
        "action_time_lane_input_id = ANY(:ids) ORDER BY ticket_id LIMIT 23",
        lane_ids,
    )
    ticket_ids = sorted(_ids(tickets, "ticket_id"))
    if len(ticket_ids) > 22:
        raise ValueError("canary_scope_ticket_limit_exceeded")
    attempts = _rows_for_any(
        conn,
        "SELECT protected_submit_attempt_id FROM "
        "brc_ticket_bound_protected_submit_attempts WHERE ticket_id = ANY(:ids) "
        "ORDER BY protected_submit_attempt_id LIMIT 45",
        ticket_ids,
    )
    lifecycles = _rows_for_any(
        conn,
        "SELECT lifecycle_run_id FROM brc_ticket_bound_order_lifecycle_runs "
        "WHERE ticket_id = ANY(:ids) ORDER BY lifecycle_run_id LIMIT 23",
        ticket_ids,
    )
    protection_sets = _rows_for_any(
        conn,
        "SELECT exit_protection_set_id FROM brc_ticket_bound_exit_protection_sets "
        "WHERE ticket_id = ANY(:ids) ORDER BY exit_protection_set_id LIMIT 23",
        ticket_ids,
    )
    lane_keys = _ids(
        _rows(
            conn,
            "SELECT DISTINCT lane_identity_key FROM brc_runtime_process_outcomes "
            "WHERE process_name='action_time_capability_certification' "
            "AND runtime_head=:runtime_head AND lane_identity_key IS NOT NULL "
            "ORDER BY lane_identity_key LIMIT 23",
            {"runtime_head": target_runtime_head},
        ),
        "lane_identity_key",
    )
    if len(lane_keys) > 22:
        raise ValueError("canary_scope_lane_identity_limit_exceeded")
    account_modes = _ids(
        _rows(
            conn,
            "SELECT account_mode_current_id FROM brc_exchange_account_modes_current "
            "ORDER BY account_mode_current_id LIMIT 23",
        ),
        "account_mode_current_id",
    )
    if len(account_modes) > 22:
        raise ValueError("canary_scope_account_mode_limit_exceeded")
    snapshots = _rows(
        conn,
        "SELECT snapshot_id FROM brc_control_read_model_snapshots WHERE is_current=true "
        "AND model_type=ANY(:model_types) ORDER BY snapshot_id LIMIT 4",
        {"model_types": ["candidate_pool", "daily_live_enablement_table", "goal_status"]},
    )
    projection_runs = _rows(
        conn,
        "SELECT DISTINCT ON (model_type) projection_run_id FROM brc_projection_runs "
        "WHERE model_type=ANY(:model_types) AND code_version=:runtime_head "
        "ORDER BY model_type,started_at_ms DESC,projection_run_id DESC LIMIT 4",
        {
            "model_types": ["candidate_pool", "daily_live_enablement_table", "goal_status"],
            "runtime_head": target_runtime_head,
        },
    )
    activation = _rows(
        conn,
        "SELECT process_outcome_id FROM brc_runtime_process_outcomes WHERE "
        "process_name='runtime_release_activation' AND scope_key='production:tokyo' "
        "AND runtime_head=:runtime_head ORDER BY updated_at_ms DESC LIMIT 2",
        {"runtime_head": target_runtime_head},
    )
    if len(activation) != 1:
        raise ValueError("canary_scope_release_activation_not_unique")
    return CanaryMutationSentinelScopeV1(
        fact_snapshot_ids=tuple(sorted(facts)),
        signal_event_ids=tuple(sorted(signals)),
        lane_ids=tuple(lane_ids),
        lane_identity_keys=tuple(sorted(lane_keys)),
        ticket_ids=tuple(ticket_ids),
        protected_attempt_ids=tuple(sorted(_ids(attempts, "protected_submit_attempt_id"))),
        lifecycle_ids=tuple(sorted(_ids(lifecycles, "lifecycle_run_id"))),
        protection_set_ids=tuple(sorted(_ids(protection_sets, "exit_protection_set_id"))),
        account_mode_ids=tuple(sorted(account_modes)),
        readiness_keys=tuple(sorted(
            (str(row["strategy_group_id"]), str(row["symbol"]), str(row["side"]))
            for row in readiness
        )),
        snapshot_ids=tuple(sorted(_ids(snapshots, "snapshot_id"))),
        projection_run_ids=tuple(sorted(_ids(projection_runs, "projection_run_id"))),
        release_activation_process_outcome_id=str(activation[0]["process_outcome_id"]),
    )


def _verify_storage_schemas(conn: sa.engine.Connection) -> None:
    inspector = sa.inspect(conn)
    for relation, expected in expected_storage_columns().items():
        actual = frozenset(str(item["name"]) for item in inspector.get_columns(relation))
        if actual != expected:
            raise ValueError(f"canary_sentinel_storage_schema_mismatch:{relation}")


def _rows(
    conn: sa.engine.Connection,
    sql: str,
    params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sa.text(sql), params or {}).mappings()]


def _rows_for_any(
    conn: sa.engine.Connection,
    sql: str,
    ids: list[str],
) -> list[dict[str, Any]]:
    return _rows(conn, sql, {"ids": ids}) if ids else []


def _ids(rows: list[dict[str, Any]], name: str) -> set[str]:
    return {str(row[name]) for row in rows if row.get(name) is not None}


def _bounded_scope_ids(
    *,
    required_ids: set[str],
    recent_ids: list[str],
    limit: int,
    overflow_error: str,
) -> set[str]:
    """Keep referenced rows first, then fill the bounded scope with recent rows."""

    selected = {str(value) for value in required_ids}
    if len(selected) > limit:
        raise ValueError(overflow_error)
    for value in recent_ids:
        if len(selected) >= limit:
            break
        selected.add(str(value))
    return selected


def _guard_logical_value_sizes(slice_id: str, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        for name, value in row.items():
            if value is None or isinstance(value, (bool, int, float)):
                continue
            raw = (
                json.dumps(value, ensure_ascii=False, allow_nan=False, default=str).encode("utf-8")
                if isinstance(value, (dict, list, tuple))
                else str(value).encode("utf-8")
            )
            limit = 1024 * 1024 if slice_id == "snapshots" and name == "semantic_payload" else 64 * 1024
            if len(raw) > limit:
                raise ValueError(f"canary_sentinel_field_too_large:{slice_id}:{name}")
