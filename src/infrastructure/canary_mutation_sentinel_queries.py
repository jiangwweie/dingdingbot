"""Bounded PostgreSQL query plan for the deployment mutation sentinel."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from src.application.readmodels.canary_mutation_sentinel import (
    CANARY_SENTINEL_SPECS_V1,
    CanaryMutationSentinelScopeV1,
)
from src.application.runtime_process_outcome import RUNTIME_LANE_PROCESS_NAMES


@dataclass(frozen=True)
class CanarySentinelQuery:
    slice_id: str
    relation: str
    sql: str
    params: dict[str, Any]
    row_limit: int


def build_canary_sentinel_queries(
    scope: CanaryMutationSentinelScopeV1,
    *,
    canary_window_floor_ms: int,
) -> tuple[CanarySentinelQuery, ...]:
    if canary_window_floor_ms < 0:
        raise ValueError("canary_window_floor_invalid")
    spec = {item.slice_id: item for item in CANARY_SENTINEL_SPECS_V1}
    process_names = tuple(sorted(RUNTIME_LANE_PROCESS_NAMES))
    if not process_names:
        raise ValueError("canary_lane_process_name_set_empty")

    predicates: dict[str, tuple[str, dict[str, Any]]] = {
        "facts": ("fact_snapshot_id = ANY(:fact_snapshot_ids)", {"fact_snapshot_ids": list(scope.fact_snapshot_ids)}),
        "signals": ("signal_event_id = ANY(:signal_event_ids)", {"signal_event_ids": list(scope.signal_event_ids)}),
        "lanes": ("action_time_lane_input_id = ANY(:lane_ids)", {"lane_ids": list(scope.lane_ids)}),
        "tickets": ("ticket_id = ANY(:ticket_ids)", {"ticket_ids": list(scope.ticket_ids)}),
        "protected_attempts": ("protected_submit_attempt_id = ANY(:protected_attempt_ids)", {"protected_attempt_ids": list(scope.protected_attempt_ids)}),
        "exchange_commands": ("ticket_id = ANY(:ticket_ids)", {"ticket_ids": list(scope.ticket_ids)}),
        "lifecycles": ("lifecycle_run_id = ANY(:lifecycle_ids)", {"lifecycle_ids": list(scope.lifecycle_ids)}),
        "protection_sets": ("exit_protection_set_id = ANY(:protection_set_ids)", {"protection_set_ids": list(scope.protection_set_ids)}),
        "protection_orders": ("exit_protection_set_id = ANY(:protection_set_ids)", {"protection_set_ids": list(scope.protection_set_ids)}),
        "exit_policy": ("ticket_id = ANY(:ticket_ids)", {"ticket_ids": list(scope.ticket_ids)}),
        "account_modes": ("account_mode_current_id = ANY(:account_mode_ids)", {"account_mode_ids": list(scope.account_mode_ids)}),
        "lifecycle_capability": ("capability_id = 'ticket_lifecycle_durable_mutation'", {}),
        "pretrade": (
            "EXISTS (SELECT 1 FROM jsonb_to_recordset(CAST(:readiness_keys AS jsonb)) "
            "AS requested(strategy_group_id text,symbol text,side text) WHERE "
            "requested.strategy_group_id=brc_pretrade_readiness_rows.strategy_group_id "
            "AND requested.symbol=brc_pretrade_readiness_rows.symbol "
            "AND requested.side=brc_pretrade_readiness_rows.side)",
            {"readiness_keys": json.dumps([
                {"strategy_group_id": key[0], "symbol": key[1], "side": key[2]}
                for key in scope.readiness_keys
            ], separators=(",", ":"))},
        ),
        "goal": ("goal_status_current_id = 'strategygroup-runtime-goal-status'", {}),
        "snapshots": ("snapshot_id = ANY(:snapshot_ids)", {"snapshot_ids": list(scope.snapshot_ids)}),
        "projection_runs": ("projection_run_id = ANY(:projection_run_ids)", {"projection_run_ids": list(scope.projection_run_ids)}),
    }
    queries: list[CanarySentinelQuery] = []
    for slice_id, (predicate, params) in predicates.items():
        item = spec[slice_id]
        queries.append(_simple_query(item, predicate, params))

    current = spec["process_current"]
    process_columns = _columns(current.columns, relation_alias="outcome")
    queries.append(
        CanarySentinelQuery(
            slice_id=current.slice_id,
            relation=current.relation,
            sql=(
                "WITH requested AS (SELECT lane_identity_key,process_name FROM "
                "unnest(CAST(:lane_identity_keys AS text[])) AS lane_identity_key "
                "CROSS JOIN unnest(CAST(:process_names AS text[])) AS process_name), "
                "latest AS (SELECT selected.* FROM requested CROSS JOIN LATERAL "
                "(SELECT " + process_columns + " FROM brc_runtime_process_outcomes AS outcome "
                "WHERE outcome.lane_identity_key=requested.lane_identity_key AND "
                "outcome.process_name=requested.process_name ORDER BY "
                "outcome.updated_at_ms DESC,outcome.process_outcome_id DESC LIMIT 1) selected) "
                "SELECT * FROM latest UNION ALL SELECT " + process_columns +
                " FROM brc_runtime_process_outcomes AS outcome WHERE "
                "outcome.process_outcome_id=:release_activation_id LIMIT "
                + str(current.row_limit + 1)
            ),
            params={
                "lane_identity_keys": list(scope.lane_identity_keys),
                "process_names": list(process_names),
                "release_activation_id": scope.release_activation_process_outcome_id,
            },
            row_limit=current.row_limit,
        )
    )
    window = spec["process_window"]
    queries.append(
        _simple_query(
            window,
            "updated_at_ms >= :canary_window_floor_ms AND ("
            "lane_identity_key = ANY(:lane_identity_keys) OR "
            "scope_key='production:tokyo' OR process_name = ANY(:process_names))",
            {
                "canary_window_floor_ms": int(canary_window_floor_ms),
                "lane_identity_keys": list(scope.lane_identity_keys),
                "process_names": list(process_names),
            },
        )
    )
    return tuple(sorted(queries, key=lambda item: item.slice_id))


def _simple_query(spec, predicate: str, params: dict[str, Any]) -> CanarySentinelQuery:
    first = spec.columns[0]
    return CanarySentinelQuery(
        slice_id=spec.slice_id,
        relation=spec.relation,
        sql=(
            f"SELECT {_columns(spec.columns)} FROM {spec.relation} "
            f"WHERE {predicate} ORDER BY \"{first}\" LIMIT {spec.row_limit + 1}"
        ),
        params=params,
        row_limit=spec.row_limit,
    )


def _columns(columns: tuple[str, ...], relation_alias: str | None = None) -> str:
    prefix = f"{relation_alias}." if relation_alias else ""
    selected = []
    for column in columns:
        if column == "semantic_payload":
            selected.append(
                f"({prefix}\"payload\" - 'generated_at_ms') AS \"semantic_payload\""
            )
        else:
            selected.append(f'{prefix}"{column}"')
    return ",".join(selected)


def expected_storage_columns() -> dict[str, frozenset[str]]:
    """Return the reviewed schema-125 storage shape per sentinel relation."""

    expected: dict[str, frozenset[str]] = {}
    for spec in CANARY_SENTINEL_SPECS_V1:
        columns = set(spec.columns)
        if spec.relation == "brc_control_read_model_snapshots":
            columns.remove("semantic_payload")
            columns.update({"payload", "generated_at_ms"})
        elif spec.relation == "brc_pretrade_readiness_rows":
            columns.add("computed_at_ms")
        elif spec.relation == "brc_goal_status_current":
            columns.add("updated_at_ms")
        elif spec.relation == "brc_projection_runs":
            columns.update({"started_at_ms", "finished_at_ms"})
        existing = expected.get(spec.relation)
        frozen = frozenset(columns)
        if existing is not None and existing != frozen:
            raise ValueError("canary_relation_schema_contract_conflict")
        expected[spec.relation] = frozen
    return expected
