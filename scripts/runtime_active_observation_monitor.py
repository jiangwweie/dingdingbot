#!/usr/bin/env python3
"""Monitor all active strategy runtimes without submitting orders.

This is an operator wrapper around ``runtime_next_attempt_observation_monitor``.
It discovers ACTIVE runtimes from the Trading Console API, runs the existing
per-runtime monitor for each one, and prints an aggregate monitor summary.

It is observe-only. It never arms local registration, arms exchange submit,
calls OrderLifecycle, submits orders, or moves funds.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys
import time
from typing import Any, Callable

import sqlalchemy as sa

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.pg_dsn import is_sync_postgres_dsn, normalize_sync_postgres_dsn  # noqa: E402
from scripts.build_daily_live_enablement_table import WIP_LANES  # noqa: E402
from src.infrastructure.runtime_control_state_repository import (  # noqa: E402
    PgBackedRuntimeControlStateRepository,
)
from src.domain.execution_eligibility import (  # noqa: E402
    RequiredExecutionMode,
    SignalGrade,
    resolve_execution_eligibility,
)
from src.application.runtime_process_outcome import (  # noqa: E402
    materialize_runtime_process_outcome,
)
from src.domain.runtime_lane_identity import RuntimeLaneIdentity  # noqa: E402
from scripts.runtime_first_real_submit_api_flow import (  # noqa: E402
    API_BASE_ENV as FIRST_REAL_SUBMIT_API_BASE_ENV,
    DEFAULT_API_BASE,
    UrlLibApiClient,
)

MAX_OBSERVATION_API_TIMEOUT_SECONDS = 60.0
NON_ACTIONABLE_OBSERVATION_BLOCKERS = {
    "runtime_attempts_exhausted",
    "order_candidate_id_or_authorization_id_required",
}
OBSERVE_ONLY_REVIEW_BLOCKERS = {
    "strategy_stop_reference_unavailable",
}
WAITING_FOR_SIGNAL_BLOCKERS = {
    "strategy_signal_not_ready_for_action_time_ticket",
}
WATCHER_COVERAGE_DETECTOR_KEY = "runtime_active_observation_monitor"


def _api_base(args: argparse.Namespace) -> str:
    import os

    return (
        args.api_base
        or os.environ.get(FIRST_REAL_SUBMIT_API_BASE_ENV)
        or DEFAULT_API_BASE
    )


def _load_env_file(path_value: str | None) -> None:
    if not path_value:
        return
    path = Path(path_value).expanduser()
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        try:
            parsed = shlex.split(raw_value, comments=False, posix=True)
        except ValueError:
            parsed = []
        value = parsed[0] if len(parsed) == 1 else raw_value.strip().strip("\"'")
        if value and not os.environ.get(key):
            os.environ[key] = value


def _effective_observation_timeout_seconds(args: argparse.Namespace) -> float:
    timeout = float(args.timeout_seconds or 10.0)
    return min(timeout, MAX_OBSERVATION_API_TIMEOUT_SECONDS)


def _active_runtimes(*, client: Any) -> list[dict[str, Any]]:
    response = client.request_json("GET", "/api/trading-console/strategy-runtimes")
    body = response.get("body")
    if response.get("http_status", 0) >= 300 or response.get("error"):
        raise RuntimeError(f"strategy_runtimes_http_{response.get('http_status')}")
    items = body if isinstance(body, list) else (body or {}).get("items", [])
    if not isinstance(items, list):
        raise RuntimeError("strategy_runtimes_response_not_list")
    return [
        item
        for item in items
        if isinstance(item, dict) and str(item.get("status") or "").lower() == "active"
    ]


def _selected_active_runtimes(
    active: list[dict[str, Any]],
    *,
    runtime_instance_ids: list[str] | None,
    strategy_family_ids: list[str] | None,
    max_runtimes: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    requested = [
        str(item).strip()
        for item in (runtime_instance_ids or [])
        if str(item or "").strip()
    ]
    requested_families = {
        str(item).strip()
        for item in (strategy_family_ids or [])
        if str(item or "").strip()
    }
    if requested_families:
        active = [
            runtime
            for runtime in active
            if str(_runtime_value(runtime, "strategy_family_id", "family") or "")
            in requested_families
        ]
    if not requested:
        return active[: max(max_runtimes, 0)], []

    requested_set = set(requested)
    selected = [
        runtime
        for runtime in active
        if str(_runtime_value(runtime, "runtime_instance_id", "runtime_id") or "")
        in requested_set
    ]
    found = {
        str(_runtime_value(runtime, "runtime_instance_id", "runtime_id") or "")
        for runtime in selected
    }
    missing = [runtime_id for runtime_id in requested if runtime_id not in found]
    return selected[: max(max_runtimes, 0)], missing


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _candidate_universe_from_control_state(
    control_state: dict[str, Any],
) -> tuple[dict[str, list[str]], dict[str, Any]]:
    universe: dict[str, list[str]] = {}
    side_scope: dict[str, list[str]] = {}
    wip_lanes = set(WIP_LANES)
    extra_strategy_groups: set[str] = set()
    for row in control_state.get("candidate_scope") or []:
        if not isinstance(row, dict) or row.get("status") != "active":
            continue
        strategy_group_id = str(row.get("strategy_group_id") or "").strip()
        symbol = _compact_symbol(row.get("symbol"))
        side = _normalize_side(row.get("side"))
        if not strategy_group_id or not symbol or not side:
            continue
        if strategy_group_id not in wip_lanes:
            extra_strategy_groups.add(strategy_group_id)
            continue
        universe.setdefault(strategy_group_id, [])
        if symbol not in universe[strategy_group_id]:
            universe[strategy_group_id].append(symbol)
        side_scope.setdefault(strategy_group_id, [])
        if side not in side_scope[strategy_group_id]:
            side_scope[strategy_group_id].append(side)
    if extra_strategy_groups:
        raise ValueError(
            "PG control state has active candidate scope outside WIP replacement audit: "
            + ", ".join(sorted(extra_strategy_groups))
        )

    return (
        {
            strategy_group_id: sorted(symbols)
            for strategy_group_id, symbols in sorted(universe.items())
        },
        {
            "source": "pg_runtime_control_state:candidate_scope",
            "loaded": bool(universe),
            "strategy_group_count": len(universe),
            "side_scope": {
                strategy_group_id: sorted(sides)
                for strategy_group_id, sides in sorted(side_scope.items())
            },
            "runtime_lane_static_identity_by_key": (
                _runtime_lane_static_identity_by_key(control_state)
            ),
            "source_mode": str(control_state.get("source_mode") or ""),
            "projection_target": str(control_state.get("projection_target") or ""),
        },
    )


def _runtime_lane_static_identity_by_key(
    control_state: dict[str, Any],
) -> dict[str, dict[str, str]]:
    """Build the PG-owned identity fields before watcher runtime attachment.

    The active watcher supplies only the concrete runtime instance ID.  Scope,
    policy, event, and asset identity remain PG authority, so a watcher display
    row cannot invent or alter a lane merely because its labels look similar.
    """

    bindings_by_candidate = {
        str(row.get("candidate_scope_id") or ""): row
        for row in control_state.get("candidate_scope_event_bindings") or []
        if isinstance(row, dict) and str(row.get("status") or "") == "active"
    }
    runtime_by_candidate = {
        str(row.get("candidate_scope_id") or ""): row
        for row in control_state.get("runtime_scope_bindings") or []
        if isinstance(row, dict) and str(row.get("status") or "") == "active"
    }
    event_by_id = {
        str(row.get("event_spec_id") or ""): row
        for row in control_state.get("strategy_side_event_specs") or []
        if isinstance(row, dict) and str(row.get("status") or "") == "current"
    }
    identities: dict[str, dict[str, str]] = {}
    for candidate in control_state.get("candidate_scope") or []:
        if not isinstance(candidate, dict) or candidate.get("status") != "active":
            continue
        candidate_scope_id = str(candidate.get("candidate_scope_id") or "")
        binding = bindings_by_candidate.get(candidate_scope_id, {})
        runtime_scope = runtime_by_candidate.get(candidate_scope_id, {})
        event_spec = event_by_id.get(str(binding.get("event_spec_id") or ""), {})
        strategy_group_id = str(candidate.get("strategy_group_id") or "")
        symbol = _compact_symbol(candidate.get("symbol"))
        side = _normalize_side(candidate.get("side"))
        if not all((candidate_scope_id, strategy_group_id, symbol, side)):
            continue
        if any(
            str(row.get(key) or "") != str(candidate.get(key) or "")
            for row in (binding, runtime_scope)
            if row
            for key in ("strategy_group_id", "symbol", "side")
        ):
            continue
        if event_spec and (
            str(event_spec.get("strategy_group_id") or "") != strategy_group_id
            or str(event_spec.get("side") or "") != side
        ):
            continue
        static_identity = {
            "candidate_scope_id": candidate_scope_id,
            "candidate_scope_event_binding_id": str(
                binding.get("candidate_scope_event_binding_id")
                or binding.get("binding_id")
                or ""
            ),
            "runtime_scope_binding_id": str(
                runtime_scope.get("runtime_scope_binding_id") or ""
            ),
            "runtime_profile_id": str(runtime_scope.get("runtime_profile_id") or ""),
            "policy_current_id": str(candidate.get("policy_current_id") or ""),
            "strategy_group_id": strategy_group_id,
            "strategy_group_version_id": str(
                event_spec.get("strategy_group_version_id") or ""
            ),
            "symbol": symbol,
            "asset_class": str(candidate.get("asset_class") or ""),
            "side": side,
            "event_spec_id": str(event_spec.get("event_spec_id") or ""),
            "event_spec_version": str(event_spec.get("event_spec_version") or ""),
            "event_id": str(event_spec.get("event_id") or ""),
            "timeframe": str(event_spec.get("timeframe") or ""),
            "time_authority": str(event_spec.get("time_authority") or ""),
        }
        if all(static_identity.values()):
            identities[_runtime_lane_static_identity_key(
                strategy_group_id,
                symbol,
                side,
            )] = static_identity
    return identities


def _runtime_lane_static_identity_key(
    strategy_group_id: str,
    symbol: str,
    side: str,
) -> str:
    return f"{strategy_group_id}:{symbol}:{side}"


def _read_candidate_universe_from_pg(
    *,
    database_url: str,
    allow_non_postgres_for_test: bool,
) -> tuple[dict[str, list[str]], dict[str, Any]]:
    database_url = normalize_sync_postgres_dsn(database_url)
    if not is_sync_postgres_dsn(database_url) and not allow_non_postgres_for_test:
        raise RuntimeError("DB-backed active observation monitor requires PostgreSQL DSN")
    engine = sa.create_engine(database_url)
    try:
        with engine.connect() as conn:
            repository = PgBackedRuntimeControlStateRepository(conn)
            projection = repository.read_watcher_candidate_universe_current()
            return _candidate_universe_from_control_state(
                projection.to_control_state()
            )
    finally:
        engine.dispose()


def _compact_symbol(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    if "/" in text:
        base, rest = text.split("/", 1)
        quote = rest.split(":", 1)[0]
        return f"{base}{quote}"
    return text.replace(":", "").replace("-", "")


def _candidate_universe_for_args(args: argparse.Namespace) -> tuple[dict[str, list[str]], dict[str, Any]]:
    database_url = str(getattr(args, "database_url", "") or "")
    if not database_url:
        raise RuntimeError(
            "PG_DATABASE_URL is required for DB-backed active observation candidate universe"
        )
    return _read_candidate_universe_from_pg(
        database_url=database_url,
        allow_non_postgres_for_test=bool(
            getattr(args, "allow_non_postgres_for_test", False)
        ),
    )


def _side_scope_from_source(source: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    raw = source.get("side_scope")
    if not isinstance(raw, dict):
        return {}
    result: dict[str, tuple[str, ...]] = {}
    for strategy_group_id, sides in raw.items():
        parsed = tuple(
            side
            for side in (
                _normalize_side(item)
                for item in (sides if isinstance(sides, list) else [])
            )
            if side
        )
        if parsed:
            result[str(strategy_group_id)] = parsed
    return result


def _filter_selected_to_candidate_universe(
    selected: list[dict[str, Any]],
    candidate_universe: dict[str, list[str]],
    *,
    side_scope: dict[str, tuple[str, ...]] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    if not candidate_universe:
        return selected, []
    allowed_lanes = {
        (str(strategy_group_id), str(symbol), side)
        for strategy_group_id, symbols in candidate_universe.items()
        for symbol in symbols
        for side in _expected_sides(strategy_group_id, side_scope=side_scope)
    }
    filtered: list[dict[str, Any]] = []
    excluded_runtime_ids: list[str] = []
    for runtime in selected:
        lane = (
            str(_runtime_value(runtime, "strategy_family_id", "family") or ""),
            _compact_symbol(_runtime_value(runtime, "symbol")),
            _normalize_side(_runtime_value(runtime, "side")),
        )
        runtime_id = str(
            _runtime_value(runtime, "runtime_instance_id", "runtime_id") or ""
        )
        if lane in allowed_lanes:
            filtered.append(runtime)
        elif runtime_id:
            excluded_runtime_ids.append(runtime_id)
    return filtered, excluded_runtime_ids


def _candidate_universe_coverage(
    *,
    candidate_universe: dict[str, list[str]],
    source: dict[str, Any],
    active: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    side_scope: dict[str, tuple[str, ...]] | None = None,
) -> dict[str, Any]:
    selected_lanes: dict[tuple[str, str, str], list[str]] = {}
    active_lanes: dict[tuple[str, str, str], list[str]] = {}
    selected_pairs: dict[tuple[str, str], list[dict[str, str]]] = {}
    active_pairs: dict[tuple[str, str], list[dict[str, str]]] = {}
    static_identity_by_key = _as_dict(
        source.get("runtime_lane_static_identity_by_key")
    )
    for lane_bucket, pair_bucket, runtimes in (
        (active_lanes, active_pairs, active),
        (selected_lanes, selected_pairs, selected),
    ):
        for runtime in runtimes:
            strategy_group_id = str(
                _runtime_value(runtime, "strategy_family_id", "family") or ""
            )
            symbol = _compact_symbol(_runtime_value(runtime, "symbol"))
            side = _normalize_side(_runtime_value(runtime, "side"))
            runtime_id = str(
                _runtime_value(runtime, "runtime_instance_id", "runtime_id") or ""
            )
            if strategy_group_id and symbol:
                lane_bucket.setdefault((strategy_group_id, symbol, side), []).append(
                    runtime_id
                )
                pair_bucket.setdefault((strategy_group_id, symbol), []).append(
                    {"runtime_instance_id": runtime_id, "side": side}
                )
    rows: list[dict[str, Any]] = []
    for strategy_group_id in sorted(candidate_universe):
        for symbol in sorted(set(candidate_universe[strategy_group_id])):
            for expected_side in _expected_sides(strategy_group_id, side_scope=side_scope):
                lane_key = (strategy_group_id, symbol, expected_side)
                pair_key = (strategy_group_id, symbol)
                selected_matches = selected_lanes.get(lane_key, [])
                active_matches = active_lanes.get(lane_key, [])
                selected_pair_matches = selected_pairs.get(pair_key, [])
                active_pair_matches = active_pairs.get(pair_key, [])
                matched_runtime_sides = sorted(
                    {
                        item["side"]
                        for item in active_pair_matches + selected_pair_matches
                        if item.get("side")
                    }
                )
                side_mismatch_runtime_instance_ids = sorted(
                    {
                        item["runtime_instance_id"]
                        for item in active_pair_matches + selected_pair_matches
                        if item.get("runtime_instance_id")
                        and item.get("side")
                        and item.get("side") != expected_side
                    }
                )
                if selected_matches:
                    state = "active_watcher_scope"
                    blocker_class = "none"
                    next_action = "continue_pretrade_observation"
                elif active_matches:
                    state = "active_runtime_filtered_out"
                    blocker_class = "runtime_profile_scope_missing"
                    next_action = "include_candidate_runtime_in_watcher_scope"
                else:
                    state = "runtime_profile_scope_missing"
                    blocker_class = "runtime_profile_scope_missing"
                    next_action = (
                        "bind_or_repair_runtime_profile_scope_side"
                        if side_mismatch_runtime_instance_ids
                        else "bind_or_start_pretrade_runtime_for_candidate_symbol"
                    )
                rows.append(
                    {
                        "strategy_group_id": strategy_group_id,
                        "symbol": symbol,
                        "side": expected_side,
                        "state": state,
                        "blocker_class": blocker_class,
                        "active_runtime_instance_ids": active_matches,
                        "selected_runtime_instance_ids": selected_matches,
                        "expected_side": expected_side,
                        "matched_runtime_sides": matched_runtime_sides,
                        "side_mismatch_runtime_instance_ids": (
                            side_mismatch_runtime_instance_ids
                        ),
                        "runtime_profile": _runtime_profile_for_lane(
                            selected + active,
                            strategy_group_id=strategy_group_id,
                            symbol=symbol,
                            side=expected_side,
                        ),
                        "lane_identity": _watcher_coverage_lane_identity(
                            static_identity_by_key=static_identity_by_key,
                            selected=selected,
                            strategy_group_id=strategy_group_id,
                            symbol=symbol,
                            side=expected_side,
                        ),
                        "next_action": next_action,
                        "authority_boundary": (
                            "candidate_universe_coverage_is_read_only; "
                            "no_finalgate_no_operation_layer_no_exchange_write"
                        ),
                    }
                )
    missing_rows = [row for row in rows if row["blocker_class"] != "none"]
    return {
        "status": "complete" if not missing_rows else "incomplete",
        "source": source,
        "expected_row_count": len(rows),
        "active_matched_row_count": len(rows) - len(missing_rows),
        "missing_row_count": len(missing_rows),
        "rows": rows,
        "authority_boundary": (
            "candidate_universe_coverage_is_read_only; "
            "does_not_create_runtime_or_expand_live_submit"
        ),
    }


def _watcher_coverage_lane_identity(
    *,
    static_identity_by_key: dict[str, Any],
    selected: list[dict[str, Any]],
    strategy_group_id: str,
    symbol: str,
    side: str,
) -> dict[str, str]:
    """Join one active watcher runtime to PG-owned lane identity fields."""

    static = static_identity_by_key.get(
        _runtime_lane_static_identity_key(strategy_group_id, symbol, side)
    )
    if not isinstance(static, dict):
        return {}
    matching_runtimes = [
        runtime
        for runtime in selected
        if str(_runtime_value(runtime, "strategy_family_id", "family") or "")
        == strategy_group_id
        and _compact_symbol(_runtime_value(runtime, "symbol")) == symbol
        and _normalize_side(_runtime_value(runtime, "side")) == side
    ]
    if len(matching_runtimes) != 1:
        return {}
    runtime = matching_runtimes[0]
    runtime_instance_id = str(
        _runtime_value(runtime, "runtime_instance_id", "runtime_id") or ""
    )
    if not runtime_instance_id:
        return {}
    runtime_profile = _runtime_profile_for_lane(
        [runtime],
        strategy_group_id=strategy_group_id,
        symbol=symbol,
        side=side,
    )
    reported_profile_id = str(runtime_profile.get("runtime_profile_id") or "")
    expected_profile_id = str(static.get("runtime_profile_id") or "")
    if reported_profile_id and reported_profile_id != expected_profile_id:
        return {}
    try:
        identity = RuntimeLaneIdentity.model_validate(
            {
                **static,
                "runtime_instance_id": runtime_instance_id,
            }
        )
    except (TypeError, ValueError):
        return {}
    return {
        **identity.model_dump(mode="json"),
        "lane_identity_key": identity.identity_key,
    }


def write_candidate_universe_coverage_to_pg(
    artifact: dict[str, Any],
    *,
    database_url: str,
    allow_non_postgres_for_test: bool = False,
    now_ms: int | None = None,
    conn: sa.engine.Connection | None = None,
) -> dict[str, Any]:
    if not database_url and conn is None:
        return {
            "status": "pg_watcher_runtime_coverage_skipped",
            "reason": "database_url_missing",
            "written_count": 0,
        }
    coverage = artifact.get("candidate_universe_coverage")
    if not isinstance(coverage, dict):
        return {
            "status": "pg_watcher_runtime_coverage_skipped",
            "reason": "candidate_universe_coverage_missing",
            "written_count": 0,
        }
    rows = [row for row in coverage.get("rows") or [] if isinstance(row, dict)]
    if not rows:
        return {
            "status": "pg_watcher_runtime_coverage_skipped",
            "reason": "candidate_universe_coverage_rows_missing",
            "written_count": 0,
        }

    observed_ms = int(now_ms if now_ms is not None else time.time() * 1000)
    if conn is not None:
        _replace_current_watcher_runtime_coverage(
            conn,
            rows=rows,
            observed_ms=observed_ms,
        )
        return {
            "status": "pg_watcher_runtime_coverage_written",
            "detector_key": WATCHER_COVERAGE_DETECTOR_KEY,
            "written_count": len(rows),
            "observed_at_ms": observed_ms,
            "authority_boundary": (
                "watcher_runtime_coverage_projection_only; "
                "no_finalgate_no_operation_layer_no_exchange_write"
            ),
        }

    normalized_url = normalize_sync_postgres_dsn(database_url)
    if not is_sync_postgres_dsn(normalized_url) and not allow_non_postgres_for_test:
        raise RuntimeError("PG watcher runtime coverage write requires PostgreSQL DSN")
    engine = sa.create_engine(normalized_url)
    try:
        with engine.begin() as conn:
            _replace_current_watcher_runtime_coverage(
                conn,
                rows=rows,
                observed_ms=observed_ms,
            )
    finally:
        engine.dispose()
    return {
        "status": "pg_watcher_runtime_coverage_written",
        "detector_key": WATCHER_COVERAGE_DETECTOR_KEY,
        "written_count": len(rows),
        "observed_at_ms": observed_ms,
        "authority_boundary": (
            "watcher_runtime_coverage_projection_only; "
            "no_finalgate_no_operation_layer_no_exchange_write"
        ),
    }


def write_runtime_signal_summaries_to_pg(
    artifact: dict[str, Any],
    *,
    database_url: str,
    allow_non_postgres_for_test: bool = False,
    now_ms: int | None = None,
    conn: sa.engine.Connection | None = None,
) -> dict[str, Any]:
    if not database_url and conn is None:
        return {
            "status": "pg_live_signal_events_skipped",
            "reason": "database_url_missing",
            "written_count": 0,
        }
    summaries = [row for row in artifact.get("runtime_summaries") or [] if isinstance(row, dict)]
    candidates = _live_signal_candidates_from_summaries(summaries)
    identity_faults = _materializable_identity_faults_from_summaries(summaries)
    if not candidates and not identity_faults:
        return {
            "status": "pg_live_signal_events_noop",
            "reason": "would_enter_signal_summary_missing",
            "written_count": 0,
            "signal_event_ids": [],
            "signals": [],
            "process_outcomes": [],
        }

    observed_ms = int(now_ms if now_ms is not None else time.time() * 1000)
    written: list[str] = []
    written_signals: list[dict[str, str]] = []
    write_dispositions: list[dict[str, str]] = []
    skipped: list[dict[str, Any]] = []
    process_outcomes: list[dict[str, object]] = []
    if conn is not None:
        for candidate in [*candidates, *identity_faults]:
            result = _write_live_signal_candidate(
                conn,
                candidate=candidate,
                observed_ms=observed_ms,
                enforce_identity_revalidation=not allow_non_postgres_for_test,
            )
            if result.get("written") is True:
                written.append(str(result["signal_event_id"]))
                written_signals.append(_signal_identity(result))
                write_dispositions.append(
                    {
                        "signal_event_id": str(result["signal_event_id"]),
                        "disposition": str(result["write_disposition"]),
                    }
                )
            else:
                skipped.append(result)
            process_outcome = _materialize_signal_process_outcome(
                conn,
                candidate=candidate,
                result=result,
                observed_ms=observed_ms,
            )
            if process_outcome:
                process_outcomes.append(process_outcome)
        return _pg_live_signal_events_result(
            written=written,
            written_signals=written_signals,
            write_dispositions=write_dispositions,
            skipped=skipped,
            process_outcomes=process_outcomes,
        )

    normalized_url = normalize_sync_postgres_dsn(database_url)
    if not is_sync_postgres_dsn(normalized_url) and not allow_non_postgres_for_test:
        raise RuntimeError("PG live signal event write requires PostgreSQL DSN")
    engine = sa.create_engine(normalized_url)
    try:
        with engine.begin() as conn:
            for candidate in [*candidates, *identity_faults]:
                result = _write_live_signal_candidate(
                    conn,
                    candidate=candidate,
                    observed_ms=observed_ms,
                    enforce_identity_revalidation=not allow_non_postgres_for_test,
                )
                if result.get("written") is True:
                    written.append(str(result["signal_event_id"]))
                    written_signals.append(_signal_identity(result))
                    write_dispositions.append(
                        {
                            "signal_event_id": str(result["signal_event_id"]),
                            "disposition": str(result["write_disposition"]),
                        }
                    )
                else:
                    skipped.append(result)
                process_outcome = _materialize_signal_process_outcome(
                    conn,
                    candidate=candidate,
                    result=result,
                    observed_ms=observed_ms,
                )
                if process_outcome:
                    process_outcomes.append(process_outcome)
    finally:
        engine.dispose()
    return _pg_live_signal_events_result(
        written=written,
        written_signals=written_signals,
        write_dispositions=write_dispositions,
        skipped=skipped,
        process_outcomes=process_outcomes,
    )


def _pg_live_signal_events_result(
    *,
    written: list[str],
    written_signals: list[dict[str, str]],
    write_dispositions: list[dict[str, str]],
    skipped: list[dict[str, Any]],
    process_outcomes: list[dict[str, object]],
) -> dict[str, Any]:
    return {
        "status": (
            "pg_live_signal_events_written"
            if written
            else "pg_live_signal_events_blocked"
        ),
        "detector_key": WATCHER_COVERAGE_DETECTOR_KEY,
        "written_count": len(written),
        "signal_event_ids": written,
        "signals": written_signals,
        "write_dispositions": write_dispositions,
        "skipped": skipped,
        "process_outcomes": process_outcomes,
        "authority_boundary": (
            "live_signal_event_projection_only; "
            "no_finalgate_no_operation_layer_no_exchange_write"
        ),
    }


def _signal_identity(result: dict[str, Any]) -> dict[str, str]:
    return {
        "signal_event_id": str(result.get("signal_event_id") or ""),
        "strategy_group_id": str(result.get("strategy_group_id") or ""),
        "symbol": str(result.get("symbol") or ""),
        "side": str(result.get("side") or ""),
    }


def _materialize_signal_process_outcome(
    conn: sa.engine.Connection,
    *,
    candidate: dict[str, Any],
    result: dict[str, Any],
    observed_ms: int,
) -> dict[str, object]:
    if not sa.inspect(conn).has_table("brc_runtime_process_outcomes"):
        return {}
    strategy_group_id = str(candidate.get("strategy_group_id") or "")
    symbol = str(candidate.get("symbol") or "")
    side = str(candidate.get("side") or "")
    if not strategy_group_id or not symbol or side not in {"long", "short"}:
        return {}
    raw_identity = candidate.get("lane_identity")
    if not isinstance(raw_identity, dict):
        return {}
    try:
        lane_identity = RuntimeLaneIdentity.model_validate(raw_identity)
    except ValueError:
        return {}

    blocker = str(result.get("blocker") or "")
    if result.get("written") is True:
        result_status = "live_signal_materialization_completed"
        blockers: list[str] = []
        source_watermark = str(result.get("signal_event_id") or "")
    elif blocker in {"signal_event_expired", "signal_event_identity_terminal"}:
        result_status = "no_current_fresh_live_signal"
        blockers = []
        source_watermark = _candidate_source_watermark(candidate)
    else:
        result_status = "pg_live_signal_event_materialization_failed"
        blockers = [
            "pg_live_signal_event_materialization_failed:"
            + (blocker or "unknown")
        ]
        source_watermark = _candidate_source_watermark(candidate)

    return materialize_runtime_process_outcome(
        conn,
        process_name="live_signal_materialization",
        scope_key=f"lane:{strategy_group_id}:{symbol}:{side}",
        run_id=(
            f"live-signal-materialization:{observed_ms}:"
            f"{str(candidate.get('runtime_instance_id') or 'unknown')}"
        ),
        result_status=result_status,
        blockers=blockers,
        started_at_ms=observed_ms,
        completed_at_ms=observed_ms,
        runtime_head=_current_runtime_head(conn),
        source_watermark=source_watermark,
        lane_identity=lane_identity,
    )


def _candidate_source_watermark(candidate: dict[str, Any]) -> str:
    runtime_instance_id = str(candidate.get("runtime_instance_id") or "unknown")
    event_time_ms = _int_or_zero(candidate.get("trigger_candle_close_time_ms"))
    return f"{runtime_instance_id}:{event_time_ms}"


def _current_runtime_head(conn: sa.engine.Connection) -> str:
    row = conn.execute(
        sa.text(
            """
            SELECT runtime_head
            FROM brc_runtime_process_outcomes
            WHERE process_name = 'runtime_release_activation'
            ORDER BY updated_at_ms DESC
            LIMIT 1
            """
        )
    ).first()
    return str(row[0]) if row and str(row[0] or "").strip() else "runtime-head-unavailable"


def _live_signal_candidates_from_summaries(
    summaries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in summaries:
        if row.get("can_materialize_live_signal_event") is not True:
            continue
        raw_identity = row.get("lane_identity")
        if not isinstance(raw_identity, dict):
            continue
        try:
            lane_identity = RuntimeLaneIdentity.model_validate(raw_identity)
        except ValueError:
            continue
        signal = row.get("signal_summary")
        if not isinstance(signal, dict):
            signal = {}
        if str(signal.get("signal_type") or "") != "would_enter":
            continue
        signal_side = _normalize_side(signal.get("side"))
        if signal_side != lane_identity.side:
            continue
        evaluated_at_ms = _int_or_zero(signal.get("evaluated_at_ms"))
        valid_until_ms = _int_or_zero(signal.get("valid_until_ms"))
        if evaluated_at_ms <= 0 or valid_until_ms <= evaluated_at_ms:
            continue
        candidates.append(
            {
                "strategy_group_id": lane_identity.strategy_group_id,
                "symbol": lane_identity.symbol,
                "side": lane_identity.side,
                "lane_identity": lane_identity.model_dump(mode="json"),
                "lane_identity_key": lane_identity.identity_key,
                "signal_type": "would_enter",
                "signal_grade": signal.get("signal_grade")
                or SignalGrade.OBSERVE_ONLY_SIGNAL.value,
                "required_execution_mode": signal.get("required_execution_mode")
                or RequiredExecutionMode.OBSERVE_ONLY.value,
                "confidence": signal.get("confidence"),
                "reason_codes": list(signal.get("reason_codes") or []),
                "trigger_candle_close_time_ms": _int_or_zero(
                    signal.get("trigger_candle_close_time_ms")
                ),
                "evaluated_at_ms": evaluated_at_ms,
                "valid_until_ms": valid_until_ms,
                "runtime_instance_id": row.get("runtime_instance_id"),
                "strategy_family_version_id": row.get("strategy_family_version_id"),
                "runtime_status": row.get("status"),
                "runtime_blockers": list(row.get("blockers") or []),
                "forbidden_effects": row.get("forbidden_effects")
                if isinstance(row.get("forbidden_effects"), dict)
                else {},
                "signal_summary": signal,
                "signal_input_ref": row.get("signal_input_ref"),
                "action_time_ticket_id": row.get("ticket_id"),
            }
        )
    return candidates


def _materializable_identity_faults_from_summaries(
    summaries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return malformed materialization claims as fail-closed lane faults.

    A normal computed-no-signal has ``can_materialize_live_signal_event=false``
    and never reaches this function. This path is exclusively for an envelope
    that claims materialization while contradicting its own resolved identity.
    """

    faults: list[dict[str, Any]] = []
    for row in summaries:
        if row.get("can_materialize_live_signal_event") is not True:
            continue
        raw_identity = row.get("lane_identity")
        if not isinstance(raw_identity, dict):
            continue
        try:
            lane_identity = RuntimeLaneIdentity.model_validate(raw_identity)
        except ValueError:
            continue
        signal = row.get("signal_summary")
        if not isinstance(signal, dict):
            signal = {}
        signal_side = _normalize_side(signal.get("side"))
        signal_type = str(signal.get("signal_type") or "")
        evaluated_at_ms = _int_or_zero(signal.get("evaluated_at_ms"))
        valid_until_ms = _int_or_zero(signal.get("valid_until_ms"))
        blocker = ""
        if signal_type != "would_enter" or signal_side != lane_identity.side:
            blocker = "runtime_lane_identity_mismatch:materializable_signal"
        elif evaluated_at_ms <= 0 or valid_until_ms <= evaluated_at_ms:
            blocker = "stale_signal_evidence"
        if not blocker:
            continue
        faults.append(
            {
                "strategy_group_id": lane_identity.strategy_group_id,
                "symbol": lane_identity.symbol,
                "side": lane_identity.side,
                "lane_identity": lane_identity.model_dump(mode="json"),
                "lane_identity_key": lane_identity.identity_key,
                "identity_fault": blocker,
                "signal_type": signal_type or "would_enter",
                "trigger_candle_close_time_ms": _int_or_zero(
                    signal.get("trigger_candle_close_time_ms")
                ),
                "evaluated_at_ms": evaluated_at_ms,
                "valid_until_ms": valid_until_ms,
                "runtime_instance_id": lane_identity.runtime_instance_id,
                "strategy_family_version_id": row.get("strategy_family_version_id"),
                "runtime_status": row.get("status"),
                "runtime_blockers": list(row.get("blockers") or []),
                "forbidden_effects": {},
                "signal_summary": signal,
                "signal_input_ref": row.get("signal_input_ref"),
            }
        )
    return faults


def _write_live_signal_candidate(
    conn: sa.engine.Connection,
    *,
    candidate: dict[str, Any],
    observed_ms: int,
    enforce_identity_revalidation: bool = True,
) -> dict[str, Any]:
    identity_fault = str(candidate.get("identity_fault") or "")
    if identity_fault:
        return {
            "written": False,
            "blocker": identity_fault,
            "strategy_group_id": candidate["strategy_group_id"],
            "symbol": candidate["symbol"],
            "side": candidate["side"],
        }
    if enforce_identity_revalidation:
        identity_blocker = _revalidate_candidate_runtime_lane_identity(
            conn,
            candidate=candidate,
        )
        if identity_blocker:
            return {
                "written": False,
                "blocker": identity_blocker,
                "strategy_group_id": candidate["strategy_group_id"],
                "symbol": candidate["symbol"],
                "side": candidate["side"],
            }
    runtime_status = str(candidate.get("runtime_status") or "").strip()
    runtime_blockers = [
        str(item)
        for item in candidate.get("runtime_blockers") or []
        if str(item).strip()
    ]
    forbidden_effects = _truthy_forbidden_effects(candidate.get("forbidden_effects"))
    if runtime_status == "blocked" or runtime_blockers:
        return {
            "written": False,
            "blocker": f"runtime_summary_blocked:{runtime_status or 'unknown'}",
            "runtime_blockers": runtime_blockers,
            "strategy_group_id": candidate["strategy_group_id"],
            "symbol": candidate["symbol"],
            "side": candidate["side"],
        }
    if forbidden_effects:
        return {
            "written": False,
            "blocker": "runtime_summary_forbidden_effect",
            "forbidden_effects": forbidden_effects,
            "strategy_group_id": candidate["strategy_group_id"],
            "symbol": candidate["symbol"],
            "side": candidate["side"],
        }

    valid_until_ms = _int_or_zero(candidate.get("valid_until_ms"))
    if valid_until_ms <= observed_ms:
        return {
            "written": False,
            "blocker": "signal_evidence_expired",
            "strategy_group_id": candidate["strategy_group_id"],
            "symbol": candidate["symbol"],
            "side": candidate["side"],
            "valid_until_ms": valid_until_ms,
        }

    scope = _active_candidate_scope_event(conn, candidate=candidate)
    if scope.get("blocker"):
        return {
            "written": False,
            "blocker": str(scope["blocker"]),
            "strategy_group_id": candidate["strategy_group_id"],
            "symbol": candidate["symbol"],
            "side": candidate["side"],
            "binding_count": scope.get("binding_count"),
        }
    if not scope:
        return {
            "written": False,
            "blocker": "candidate_scope_event_binding_missing",
            "strategy_group_id": candidate["strategy_group_id"],
            "symbol": candidate["symbol"],
            "side": candidate["side"],
        }
    try:
        authority = resolve_execution_eligibility(
            declared_signal_grade=scope.get("declared_signal_grade")
            or SignalGrade.OBSERVE_ONLY_SIGNAL,
            declared_required_execution_mode=scope.get(
                "declared_required_execution_mode"
            )
            or RequiredExecutionMode.OBSERVE_ONLY,
            execution_eligibility_enabled=bool(
                scope.get("execution_eligibility_enabled")
            ),
            evaluator_signal_grade=candidate.get("signal_grade")
            or SignalGrade.OBSERVE_ONLY_SIGNAL,
            evaluator_required_execution_mode=candidate.get(
                "required_execution_mode"
            )
            or RequiredExecutionMode.OBSERVE_ONLY,
            authority_source_ref=f"event-spec:{scope['event_spec_id']}",
        )
    except ValueError as exc:
        return {
            "written": False,
            "blocker": "execution_eligibility_authority_invalid",
            "detail": str(exc),
            "strategy_group_id": candidate["strategy_group_id"],
            "symbol": candidate["symbol"],
            "side": candidate["side"],
            "event_spec_id": scope.get("event_spec_id"),
        }
    freshness_window_ms = _int_or_zero(scope.get("freshness_window_ms"))
    if freshness_window_ms <= 0:
        return {
            "written": False,
            "blocker": "event_spec_freshness_window_missing",
            "strategy_group_id": candidate["strategy_group_id"],
            "symbol": candidate["symbol"],
            "side": candidate["side"],
            "event_spec_id": scope.get("event_spec_id"),
        }

    time_authority = str(scope.get("time_authority") or "").strip()
    if time_authority != "trigger_candle_close_time_ms":
        return {
            "written": False,
            "blocker": "event_spec_time_authority_unsupported",
            "strategy_group_id": candidate["strategy_group_id"],
            "symbol": candidate["symbol"],
            "side": candidate["side"],
            "event_spec_id": scope.get("event_spec_id"),
            "time_authority": time_authority,
        }
    event_time_ms = _int_or_zero(candidate.get("trigger_candle_close_time_ms"))
    if event_time_ms <= 0:
        return {
            "written": False,
            "blocker": "signal_event_time_authority_missing",
            "strategy_group_id": candidate["strategy_group_id"],
            "symbol": candidate["symbol"],
            "side": candidate["side"],
            "event_spec_id": scope.get("event_spec_id"),
            "time_authority": time_authority,
        }

    expires_at_ms = event_time_ms + freshness_window_ms
    if expires_at_ms <= observed_ms:
        return {
            "written": False,
            "blocker": "signal_event_expired",
            "strategy_group_id": candidate["strategy_group_id"],
            "symbol": candidate["symbol"],
            "side": candidate["side"],
            "event_time_ms": event_time_ms,
            "freshness_window_ms": freshness_window_ms,
        }

    fact = _latest_fresh_public_fact(conn, candidate=candidate, now_ms=observed_ms)
    if not fact:
        return {
            "written": False,
            "blocker": "fresh_public_fact_snapshot_missing",
            "strategy_group_id": candidate["strategy_group_id"],
            "symbol": candidate["symbol"],
            "side": candidate["side"],
        }
    expires_at_ms = min(expires_at_ms, int(fact.get("valid_until_ms") or expires_at_ms))
    if expires_at_ms <= observed_ms:
        return {
            "written": False,
            "blocker": "fresh_public_fact_snapshot_expired",
            "strategy_group_id": candidate["strategy_group_id"],
            "symbol": candidate["symbol"],
            "side": candidate["side"],
        }

    event_id = str(scope.get("event_id") or "").strip()
    if not event_id:
        return {
            "written": False,
            "blocker": "event_spec_event_id_missing",
            "strategy_group_id": candidate["strategy_group_id"],
            "symbol": candidate["symbol"],
            "side": candidate["side"],
            "event_spec_id": scope.get("event_spec_id"),
        }
    detector_verdict = str(candidate["signal_type"])
    signal_event_id = _stable_signal_event_id(
        strategy_group_id=str(candidate["strategy_group_id"]),
        symbol=str(candidate["symbol"]),
        side=str(candidate["side"]),
        event_spec_id=str(scope["event_spec_id"]),
        signal_type=event_id,
        event_time_ms=event_time_ms,
    )
    created_at_ms = max(observed_ms, event_time_ms + 1)
    lane_identity = RuntimeLaneIdentity.model_validate(candidate["lane_identity"])
    row = {
        "signal_event_id": signal_event_id,
        "candidate_scope_id": lane_identity.candidate_scope_id,
        "candidate_scope_event_binding_id": (
            lane_identity.candidate_scope_event_binding_id
        ),
        "runtime_scope_binding_id": lane_identity.runtime_scope_binding_id,
        "runtime_instance_id": lane_identity.runtime_instance_id,
        "runtime_profile_id": lane_identity.runtime_profile_id,
        "policy_current_id": lane_identity.policy_current_id,
        "strategy_group_version_id": lane_identity.strategy_group_version_id,
        "asset_class": lane_identity.asset_class,
        "event_spec_id": lane_identity.event_spec_id,
        "event_spec_version": lane_identity.event_spec_version,
        "event_id": lane_identity.event_id,
        "timeframe": lane_identity.timeframe,
        "time_authority": lane_identity.time_authority,
        "lane_identity_key": lane_identity.identity_key,
        "source_watermark": _candidate_source_watermark(candidate),
        "strategy_group_id": lane_identity.strategy_group_id,
        "symbol": lane_identity.symbol,
        "side": lane_identity.side,
        "detector_key": WATCHER_COVERAGE_DETECTOR_KEY,
        "signal_type": event_id,
        "source_kind": "live_market",
        "status": "facts_validated",
        "freshness_state": "fresh",
        "confidence": candidate.get("confidence"),
        "fact_snapshot_id": fact["fact_snapshot_id"],
        "reason_codes": json.dumps(candidate.get("reason_codes") or []),
        "signal_payload": json.dumps(
            {
                "runtime_instance_id": candidate.get("runtime_instance_id"),
                "strategy_family_version_id": candidate.get("strategy_family_version_id"),
                "lane_identity": lane_identity.model_dump(mode="json"),
                "lane_identity_key": lane_identity.identity_key,
                "runtime_status": candidate.get("runtime_status"),
                "detector_verdict": detector_verdict,
                "signal_summary": candidate.get("signal_summary") or {},
                "event_time_authority_ref": "trigger_candle_close_time_ms",
                "signal_input_ref": candidate.get("signal_input_ref"),
                "action_time_ticket_id": candidate.get("action_time_ticket_id"),
                "source": "runtime_active_observation_monitor",
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        "event_time_ms": event_time_ms,
        "trigger_candle_close_time_ms": event_time_ms,
        "observed_at_ms": observed_ms,
        "expires_at_ms": expires_at_ms,
        "created_at_ms": created_at_ms,
        "signal_grade": authority.signal_grade.value,
        "required_execution_mode": authority.required_execution_mode.value,
        "execution_eligible": authority.execution_eligible,
        "authority_source_ref": authority.authority_source_ref,
    }
    if enforce_identity_revalidation:
        identity_blocker = _revalidate_candidate_runtime_lane_identity(
            conn,
            candidate=candidate,
        )
        if identity_blocker:
            return {
                "written": False,
                "blocker": identity_blocker,
                "strategy_group_id": candidate["strategy_group_id"],
                "symbol": candidate["symbol"],
                "side": candidate["side"],
            }
    inserted = _upsert_live_signal_event(conn, row)
    if not inserted:
        existing = _live_signal_event_by_identity(conn, identity=row)
        signal_event_id = str(existing.get("signal_event_id") or signal_event_id)
        existing_is_fresh = (
            str(existing.get("status") or "") == "facts_validated"
            and str(existing.get("freshness_state") or "") == "fresh"
            and int(existing.get("expires_at_ms") or 0) > observed_ms
            and existing.get("invalidated_at_ms") is None
        )
        if not existing_is_fresh:
            expired = (
                int(existing.get("expires_at_ms") or 0) <= observed_ms
                or str(existing.get("freshness_state") or "")
                in {"expired", "stale"}
            )
            return {
                "written": False,
                "blocker": (
                    "signal_event_expired"
                    if expired
                    else "signal_event_identity_terminal"
                ),
                "signal_event_id": signal_event_id,
                "strategy_group_id": candidate["strategy_group_id"],
                "symbol": candidate["symbol"],
                "side": candidate["side"],
            }
    return {
        "written": True,
        "write_disposition": (
            "inserted" if inserted else "duplicate_identity_preserved"
        ),
        "signal_event_id": signal_event_id,
        "strategy_group_id": candidate["strategy_group_id"],
        "symbol": candidate["symbol"],
        "side": candidate["side"],
        "signal_grade": authority.signal_grade.value,
        "required_execution_mode": authority.required_execution_mode.value,
        "execution_eligible": authority.execution_eligible,
        "authority_source_ref": authority.authority_source_ref,
    }


def _revalidate_candidate_runtime_lane_identity(
    conn: sa.engine.Connection,
    *,
    candidate: dict[str, Any],
) -> str | None:
    """Re-read PG identity immediately before an insert; no summary fallback."""

    raw_identity = candidate.get("lane_identity")
    if not isinstance(raw_identity, dict):
        return "runtime_lane_identity_mismatch:identity_envelope_missing"
    try:
        expected = RuntimeLaneIdentity.model_validate(raw_identity)
    except ValueError:
        return "runtime_lane_identity_mismatch:identity_envelope_invalid"
    runtime_instance_id = str(candidate.get("runtime_instance_id") or "")
    if runtime_instance_id != expected.runtime_instance_id:
        return "runtime_lane_identity_mismatch:runtime_instance_id"

    from src.application.runtime_lane_identity_service import (
        RuntimeLaneIdentityResolutionError,
        RuntimeLaneIdentityService,
    )

    try:
        resolved = RuntimeLaneIdentityService().resolve(
            conn,
            runtime_instance_id=expected.runtime_instance_id,
        ).identity
    except RuntimeLaneIdentityResolutionError as exc:
        return exc.blocker
    if resolved != expected:
        return "runtime_lane_identity_mismatch:pg_revalidation"
    return None


def _active_candidate_scope_event(
    conn: sa.engine.Connection,
    *,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    rows = list(
        conn.execute(
            sa.text(
                """
                SELECT
                  c.candidate_scope_id,
                  b.event_spec_id,
                  e.event_id,
                  e.time_authority,
                  e.freshness_window_ms,
                  e.declared_signal_grade,
                  e.declared_required_execution_mode,
                  e.execution_eligibility_enabled
                FROM brc_strategy_group_candidate_scope AS c
                JOIN brc_candidate_scope_event_bindings AS b
                  ON b.candidate_scope_id = c.candidate_scope_id
                 AND b.status = 'active'
                LEFT JOIN brc_strategy_side_event_specs AS e
                  ON e.event_spec_id = b.event_spec_id
                 AND e.status = 'current'
                WHERE c.strategy_group_id = :strategy_group_id
                  AND c.symbol = :symbol
                  AND c.side = :side
                  AND c.status = 'active'
                ORDER BY c.priority_rank ASC, b.created_at_ms DESC
                """
            ),
            {
                "strategy_group_id": candidate["strategy_group_id"],
                "symbol": candidate["symbol"],
                "side": candidate["side"],
            },
        ).mappings()
    )
    if len(rows) > 1:
        return {
            "blocker": "candidate_scope_event_binding_ambiguous",
            "binding_count": len(rows),
        }
    return dict(rows[0]) if rows else {}


def _latest_fresh_public_fact(
    conn: sa.engine.Connection,
    *,
    candidate: dict[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    row = conn.execute(
        sa.text(
            """
            SELECT fact_snapshot_id, valid_until_ms
            FROM brc_runtime_fact_snapshots
            WHERE strategy_group_id = :strategy_group_id
              AND symbol = :symbol
              AND side = :side
              AND fact_surface = 'pretrade_public'
              AND source_kind = 'live_market'
              AND computed = true
              AND satisfied = true
              AND freshness_state = 'fresh'
              AND valid_until_ms > :now_ms
            ORDER BY observed_at_ms DESC, created_at_ms DESC, fact_snapshot_id DESC
            LIMIT 1
            """
        ),
        {
            "strategy_group_id": candidate["strategy_group_id"],
            "symbol": candidate["symbol"],
            "side": candidate["side"],
            "now_ms": now_ms,
        },
    ).mappings().first()
    return dict(row) if row else {}


def _upsert_live_signal_event(
    conn: sa.engine.Connection,
    row: dict[str, Any],
) -> bool:
    table = sa.Table("brc_live_signal_events", sa.MetaData(), autoload_with=conn)
    payload = {
        **row,
        "invalidated_at_ms": None,
    }
    column_names = [name for name in payload if name in table.c]
    columns = ",\n          ".join(column_names)
    values = ",\n          ".join(f":{name}" for name in column_names)
    statement = sa.text(
        """
        INSERT INTO brc_live_signal_events (
          """
        + columns
        + """
        ) VALUES (
          """
        + values
        + """
        )
        """
    )
    if conn.dialect.name == "postgresql":
        statement = sa.text(
            statement.text
            + """
            ON CONFLICT ON CONSTRAINT uq_brc_live_signal_identity
            DO NOTHING
            RETURNING signal_event_id
            """
        )
    elif conn.dialect.name == "sqlite":
        statement = sa.text(
            statement.text.replace("INSERT INTO", "INSERT OR IGNORE INTO", 1)
            + " RETURNING signal_event_id"
        )
    result = conn.execute(statement, payload)
    if conn.dialect.name in {"postgresql", "sqlite"}:
        return result.scalar_one_or_none() is not None
    return result.rowcount != 0


def _live_signal_event_by_identity(
    conn: sa.engine.Connection,
    *,
    identity: dict[str, Any],
) -> dict[str, Any]:
    row = conn.execute(
        sa.text(
            """
            SELECT signal_event_id, status, freshness_state, expires_at_ms,
                   invalidated_at_ms
            FROM brc_live_signal_events
            WHERE strategy_group_id = :strategy_group_id
              AND symbol = :symbol
              AND side = :side
              AND detector_key = :detector_key
              AND event_spec_id = :event_spec_id
              AND signal_type = :signal_type
              AND event_time_ms = :event_time_ms
            LIMIT 1
            """
        ),
        {
            "strategy_group_id": identity["strategy_group_id"],
            "symbol": identity["symbol"],
            "side": identity["side"],
            "detector_key": identity["detector_key"],
            "event_spec_id": identity["event_spec_id"],
            "signal_type": identity["signal_type"],
            "event_time_ms": identity["event_time_ms"],
        },
    ).mappings().first()
    return dict(row) if row else {}


def _stable_signal_event_id(
    *,
    strategy_group_id: str,
    symbol: str,
    side: str,
    event_spec_id: str,
    signal_type: str,
    event_time_ms: int,
) -> str:
    payload = "|".join(
        (strategy_group_id, symbol, side, event_spec_id, signal_type, str(event_time_ms))
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return f"signal:{digest}"


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _truthy_forbidden_effects(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    return sorted(str(key) for key, flag in value.items() if bool(flag))


def _replace_current_watcher_runtime_coverage(
    conn: sa.engine.Connection,
    *,
    rows: list[dict[str, Any]],
    observed_ms: int,
) -> None:
    _require_typed_watcher_coverage_schema(conn)
    conn.execute(
        sa.text(
            """
            UPDATE brc_watcher_runtime_coverage
            SET is_current = false
            WHERE is_current = true
            """
        ),
    )
    valid_until_ms = observed_ms + 15 * 60 * 1000
    for index, row in enumerate(rows, start=1):
        strategy_group_id = str(row.get("strategy_group_id") or "")
        symbol = str(row.get("symbol") or "")
        side = _normalize_side(row.get("side"))
        if not strategy_group_id or not symbol or side not in {"long", "short"}:
            continue
        state = str(row.get("state") or "")
        coverage_state = (
            "covered"
            if state == "active_watcher_scope"
            else "not_covered"
            if state == "active_runtime_filtered_out"
            else "missing"
        )
        liveness_state = "active" if coverage_state == "covered" else coverage_state
        runtime_profile = row.get("runtime_profile")
        if not isinstance(runtime_profile, dict):
            runtime_profile = {}
        lane_identity = _coverage_runtime_lane_identity(row)
        if coverage_state == "covered" and lane_identity is None:
            # A display-level watcher match without the immutable PG lane
            # identity cannot certify execution coverage.  Preserve the row as
            # a diagnostic but fail coverage closed for the Action-Time path.
            coverage_state = "not_covered"
            liveness_state = "identity_missing"
        source_watermark = (
            f"watcher:{lane_identity.runtime_instance_id}:{observed_ms}"
            if lane_identity is not None
            else None
        )
        conn.execute(
            sa.text(
                """
                INSERT INTO brc_watcher_runtime_coverage (
                  runtime_coverage_id,
                  strategy_group_id,
                  symbol,
                  side,
                  detector_key,
                  candidate_scope_id,
                  candidate_scope_event_binding_id,
                  runtime_scope_binding_id,
                  runtime_instance_id,
                  runtime_profile_id,
                  policy_current_id,
                  strategy_group_version_id,
                  asset_class,
                  event_spec_id,
                  event_spec_version,
                  event_id,
                  timeframe,
                  time_authority,
                  lane_identity_key,
                  source_watermark,
                  coverage_state,
                  liveness_state,
                  last_tick_at_ms,
                  valid_until_ms,
                  is_current,
                  created_at_ms
                ) VALUES (
                  :runtime_coverage_id,
                  :strategy_group_id,
                  :symbol,
                  :side,
                  :detector_key,
                  :candidate_scope_id,
                  :candidate_scope_event_binding_id,
                  :runtime_scope_binding_id,
                  :runtime_instance_id,
                  :runtime_profile_id,
                  :policy_current_id,
                  :strategy_group_version_id,
                  :asset_class,
                  :event_spec_id,
                  :event_spec_version,
                  :event_id,
                  :timeframe,
                  :time_authority,
                  :lane_identity_key,
                  :source_watermark,
                  :coverage_state,
                  :liveness_state,
                  :last_tick_at_ms,
                  :valid_until_ms,
                  :is_current,
                  :created_at_ms
                )
                """
            ),
            {
                "runtime_coverage_id": (
                    "watcher_coverage:"
                    f"{WATCHER_COVERAGE_DETECTOR_KEY}:"
                    f"{strategy_group_id}:{symbol}:{side}:{observed_ms}:{index}"
                ),
                "strategy_group_id": strategy_group_id,
                "symbol": symbol,
                "side": side,
                "detector_key": WATCHER_COVERAGE_DETECTOR_KEY,
                "candidate_scope_id": (
                    lane_identity.candidate_scope_id if lane_identity else None
                ),
                "candidate_scope_event_binding_id": (
                    lane_identity.candidate_scope_event_binding_id
                    if lane_identity
                    else None
                ),
                "runtime_scope_binding_id": (
                    lane_identity.runtime_scope_binding_id if lane_identity else None
                ),
                "runtime_instance_id": (
                    lane_identity.runtime_instance_id if lane_identity else None
                ),
                "runtime_profile_id": (
                    lane_identity.runtime_profile_id
                    if lane_identity
                    else str(runtime_profile.get("runtime_profile_id") or "")
                    or None
                ),
                "policy_current_id": (
                    lane_identity.policy_current_id if lane_identity else None
                ),
                "strategy_group_version_id": (
                    lane_identity.strategy_group_version_id
                    if lane_identity
                    else None
                ),
                "asset_class": (
                    lane_identity.asset_class if lane_identity else None
                ),
                "event_spec_id": (
                    lane_identity.event_spec_id if lane_identity else None
                ),
                "event_spec_version": (
                    lane_identity.event_spec_version if lane_identity else None
                ),
                "event_id": lane_identity.event_id if lane_identity else None,
                "timeframe": lane_identity.timeframe if lane_identity else None,
                "time_authority": (
                    lane_identity.time_authority if lane_identity else None
                ),
                "lane_identity_key": (
                    lane_identity.identity_key if lane_identity else None
                ),
                "source_watermark": source_watermark,
                "coverage_state": coverage_state,
                "liveness_state": liveness_state,
                "last_tick_at_ms": observed_ms,
                "valid_until_ms": valid_until_ms,
                "is_current": True,
                "created_at_ms": observed_ms,
            },
        )


def _require_typed_watcher_coverage_schema(conn: sa.engine.Connection) -> None:
    required_columns = {
        "candidate_scope_id",
        "candidate_scope_event_binding_id",
        "runtime_scope_binding_id",
        "runtime_instance_id",
        "runtime_profile_id",
        "policy_current_id",
        "strategy_group_version_id",
        "asset_class",
        "event_spec_id",
        "event_spec_version",
        "event_id",
        "timeframe",
        "time_authority",
        "lane_identity_key",
        "source_watermark",
    }
    columns = {
        column["name"]
        for column in sa.inspect(conn).get_columns("brc_watcher_runtime_coverage")
    }
    missing = sorted(required_columns - columns)
    if missing:
        raise RuntimeError(
            "watcher_runtime_coverage_identity_schema_missing:"
            + ",".join(missing)
        )


def _coverage_runtime_lane_identity(
    row: dict[str, Any],
) -> RuntimeLaneIdentity | None:
    raw_identity = row.get("lane_identity")
    if not isinstance(raw_identity, dict):
        return None
    try:
        identity = RuntimeLaneIdentity.model_validate(
            {
                field: raw_identity.get(field)
                for field in RuntimeLaneIdentity.model_fields
            }
        )
    except (TypeError, ValueError):
        return None
    if str(raw_identity.get("lane_identity_key") or "") != identity.identity_key:
        return None
    if (
        str(row.get("strategy_group_id") or "") != identity.strategy_group_id
        or str(row.get("symbol") or "") != identity.symbol
        or _normalize_side(row.get("side")) != identity.side
    ):
        return None
    return identity


def _runtime_value(runtime: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = runtime.get(key)
        if value is not None and value != "":
            return value
    return None


def _expected_sides(
    strategy_group_id: Any,
    *,
    side_scope: dict[str, tuple[str, ...]] | None = None,
) -> tuple[str, ...]:
    strategy_group_id = str(strategy_group_id)
    if side_scope and strategy_group_id in side_scope:
        return side_scope[strategy_group_id]
    return ()


def _runtime_profile_for_lane(
    runtimes: list[dict[str, Any]],
    *,
    strategy_group_id: str,
    symbol: str,
    side: str,
) -> dict[str, str]:
    for runtime in runtimes:
        if (
            str(_runtime_value(runtime, "strategy_family_id", "family") or "")
            == strategy_group_id
            and _compact_symbol(_runtime_value(runtime, "symbol")) == symbol
            and _normalize_side(_runtime_value(runtime, "side")) == side
        ):
            profile = runtime.get("runtime_profile")
            if not isinstance(profile, dict):
                profile = {}
            runtime_profile_id = (
                _runtime_value(runtime, "runtime_profile_id", "profile_id")
                or profile.get("runtime_profile_id")
                or profile.get("profile_id")
                or ""
            )
            target_notional = (
                _runtime_value(runtime, "target_notional_usdt", "target_notional")
                or profile.get("target_notional_usdt")
                or profile.get("target_notional")
                or ""
            )
            max_notional = (
                _runtime_value(runtime, "max_notional", "max_notional_usdt")
                or profile.get("max_notional")
                or profile.get("max_notional_usdt")
                or profile.get("max_notional_per_action_usdt")
                or ""
            )
            leverage = (
                _runtime_value(runtime, "leverage", "max_leverage")
                or profile.get("leverage")
                or profile.get("max_leverage")
                or ""
            )
            profile_source = (
                "runtime"
                if any([runtime_profile_id, target_notional])
                else "missing_runtime_profile_boundary"
            )
            return {
                "runtime_profile_id": str(runtime_profile_id or ""),
                "target_notional_usdt": str(target_notional or ""),
                "max_notional": str(max_notional or ""),
                "leverage": str(leverage or ""),
                "profile_source": profile_source,
                "authority_boundary": (
                    "runtime_profile_projection_only; no_live_profile_or_sizing_change"
                ),
            }
    return {}


def _normalize_side(value: Any) -> str:
    return str(value or "").strip().lower()


def _monitor_args(args: argparse.Namespace, runtime: dict[str, Any]) -> argparse.Namespace:
    runtime_instance_id = str(_runtime_value(runtime, "runtime_instance_id", "runtime_id") or "")
    symbol = _runtime_value(runtime, "symbol")
    side = _runtime_value(runtime, "side")
    strategy_family_id = _runtime_value(runtime, "strategy_family_id", "family")
    carrier_id = _runtime_value(
        runtime,
        "carrier_id",
        "strategy_family_version_id",
        "strategy_family_id",
    )
    return argparse.Namespace(
        runtime_instance_id=runtime_instance_id,
        env_file=args.env_file,
        api_base=_api_base(args),
        source=args.source,
        include_exchange=args.include_exchange,
        symbol=symbol,
        side=side,
        family=strategy_family_id,
        strategy_family_id=strategy_family_id,
        carrier_id=carrier_id,
        quantity=None,
        target_notional_usdt=None,
        max_notional=None,
        leverage=None,
        max_attempts=None,
        protection_mode=None,
        review_requirement=None,
        evaluation_id=None,
        playbook_id=args.playbook_id,
        one_hour_limit=args.one_hour_limit,
        four_hour_limit=args.four_hour_limit,
        timeout_seconds=_effective_observation_timeout_seconds(args),
        allow_action_time_ticket_materialization=(
            getattr(args, "allow_action_time_ticket_materialization", False)
        ),
        candidate_id=None,
        context_id=None,
        owner_operator_id=args.owner_operator_id,
        owner_confirmation_reference=args.owner_confirmation_reference,
        reason=args.reason,
        next_attempt_symbol=symbol,
        next_attempt_side=side,
        next_attempt_family=strategy_family_id,
        next_attempt_strategy_family_id=strategy_family_id,
        next_attempt_carrier_id=carrier_id,
        max_cycles=args.max_cycles_per_runtime,
        interval_seconds=args.interval_seconds,
        continue_on_blocked=args.continue_on_blocked,
    )


def _build_runtime_observation_cycle_artifact(
    args: argparse.Namespace,
) -> dict[str, Any]:
    client = UrlLibApiClient(api_base=args.api_base)
    body = {
        "source": args.source,
        "include_exchange": bool(args.include_exchange),
        "allow_action_time_ticket_materialization": False,
        "symbol": args.symbol,
        "side": args.side,
        "family": args.family,
        "strategy_family_id": args.strategy_family_id,
        "carrier_id": args.carrier_id,
        "quantity": args.quantity,
        "target_notional_usdt": args.target_notional_usdt,
        "max_notional": args.max_notional,
        "leverage": args.leverage,
        "max_attempts": args.max_attempts,
        "protection_mode": args.protection_mode,
        "review_requirement": args.review_requirement,
        "evaluation_id": args.evaluation_id,
        "playbook_id": args.playbook_id,
        "one_hour_limit": args.one_hour_limit,
        "four_hour_limit": args.four_hour_limit,
        "timeout_seconds": args.timeout_seconds,
        "non_executing": True,
    }
    response = client.request_json(
        "POST",
        (
            "/api/trading-console/strategy-runtimes/"
            f"{args.runtime_instance_id}/next-attempt-observation-cycle"
        ),
        body=body,
    )
    payload = response.get("body")
    if response.get("http_status", 0) >= 300 or response.get("error"):
        return {
            "scope": "runtime_next_attempt_observation_cycle_api",
            "status": "blocked",
            "runtime_instance_id": args.runtime_instance_id,
            "blockers": [
                f"runtime_observation_cycle_http_{response.get('http_status')}"
            ],
            "warnings": [str(payload)] if payload else [],
            "observation_cycle_plan": {
                "next_step": "repair_runtime_observation_cycle_api",
                "not_executed": True,
                "creates_action_time_ticket": False,
                "creates_execution_intent": False,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "safety_invariants": _non_executing_runtime_observation_safety(),
        }
    if not isinstance(payload, dict):
        return {
            "scope": "runtime_next_attempt_observation_cycle_api",
            "status": "blocked",
            "runtime_instance_id": args.runtime_instance_id,
            "blockers": ["runtime_observation_cycle_response_not_object"],
            "warnings": [],
            "observation_cycle_plan": {
                "next_step": "repair_runtime_observation_cycle_api",
                "not_executed": True,
                "creates_action_time_ticket": False,
                "creates_execution_intent": False,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "safety_invariants": _non_executing_runtime_observation_safety(),
        }
    return payload


def _non_executing_runtime_observation_safety() -> dict[str, bool]:
    return {
        "allow_action_time_ticket_materialization": False,
        "action_time_ticket_created": False,
        "runtime_execution_intent_draft_created": False,
        "recorded_execution_intent_created": False,
        "submit_authorization_created": False,
        "protection_plan_created": False,
        "executable_execution_intent_created": False,
        "local_registration_armed": False,
        "exchange_submit_armed": False,
        "execute_real_submit": False,
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "attempt_counter_mutated": False,
        "runtime_budget_mutated": False,
        "position_opened": False,
        "position_closed": False,
        "withdrawal_or_transfer_created": False,
    }


def _signal_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    latest_artifact = artifact.get("latest_artifact")
    if not isinstance(latest_artifact, dict):
        latest_artifact = artifact
    observation_payload = latest_artifact.get("observation_payload")
    if not isinstance(observation_payload, dict):
        observation_payload = {}
    signal_artifact = observation_payload.get("signal_artifact")
    if not isinstance(signal_artifact, dict):
        signal_artifact = latest_artifact.get("signal_artifact")
    if not isinstance(signal_artifact, dict):
        return {}
    return signal_artifact


def _signal_summary(artifact: dict[str, Any]) -> dict[str, Any]:
    signal_artifact = _signal_artifact(artifact)
    evaluation = signal_artifact.get("evaluation_result")
    if not isinstance(evaluation, dict):
        evaluation = {}
    output = evaluation.get("signal")
    if not isinstance(output, dict):
        output = evaluation.get("output")
    if not isinstance(output, dict):
        output = {}
    signal_snapshot = output.get("signal_snapshot")
    if not isinstance(signal_snapshot, dict):
        signal_snapshot = {}
    context_tags = signal_snapshot.get("context_tags")
    if not isinstance(context_tags, dict):
        context_tags = {}
    data_quality = output.get("data_quality")
    if not isinstance(data_quality, dict):
        data_quality = {}
    fact_observations = output.get("fact_observations")
    if not isinstance(fact_observations, list):
        fact_observations = []
    return {
        "evaluation_status": evaluation.get("status"),
        "evaluator_id": evaluation.get("evaluator_id"),
        "evaluated_at_ms": evaluation.get("evaluated_at_ms"),
        "valid_until_ms": evaluation.get("valid_until_ms"),
        "signal_type": output.get("signal_type"),
        "signal_grade": output.get("signal_grade"),
        "required_execution_mode": output.get("required_execution_mode"),
        "side": output.get("side"),
        "reason_codes": list(
            output.get("reason_codes") or evaluation.get("reason_codes") or []
        ),
        "human_summary": output.get("human_summary"),
        "confidence": output.get("confidence"),
        "data_quality_status": data_quality.get("status"),
        "context_tags": context_tags,
        "can_call_semantic_binding": evaluation.get("can_call_semantic_binding"),
        "can_materialize_live_signal_event": signal_artifact.get(
            "can_materialize_live_signal_event"
        ),
        "semantics_binding_found": evaluation.get("semantics_binding_found"),
        "strategy_candidate_mode": evaluation.get("strategy_candidate_mode"),
        "timestamp_ms": output.get("timestamp_ms"),
        "time_authority": output.get("time_authority"),
        "trigger_candle_close_time_ms": output.get("trigger_candle_close_time_ms"),
        "signal_snapshot": signal_snapshot,
        "fact_observations": [
            dict(observation)
            for observation in fact_observations
            if isinstance(observation, dict)
        ],
        "evidence_payload": output.get("evidence_payload")
        if isinstance(output.get("evidence_payload"), dict)
        else {},
    }


def _summary(runtime: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
    safety = artifact.get("safety_invariants")
    if not isinstance(safety, dict):
        safety = {}
    plan = (
        artifact.get("observation_cycle_plan")
        or artifact.get("observation_monitor_plan")
        or {}
    )
    status = str(artifact.get("status") or "")
    signal_input_ref = artifact.get("signal_input_ref") or plan.get("signal_input_ref")
    signal_artifact = _signal_artifact(artifact)
    raw_lane_identity = signal_artifact.get("lane_identity")
    lane_identity: RuntimeLaneIdentity | None = None
    if isinstance(raw_lane_identity, dict):
        try:
            lane_identity = RuntimeLaneIdentity.model_validate(raw_lane_identity)
        except ValueError:
            lane_identity = None

    return {
        "runtime_instance_id": (
            lane_identity.runtime_instance_id
            if lane_identity is not None
            else _runtime_value(runtime, "runtime_instance_id", "runtime_id")
        ),
        "status": status,
        "symbol": (
            lane_identity.symbol
            if lane_identity is not None
            else _runtime_value(runtime, "symbol")
        ),
        "side": (
            lane_identity.side
            if lane_identity is not None
            else _runtime_value(runtime, "side")
        ),
        "strategy_family_id": (
            lane_identity.strategy_group_id
            if lane_identity is not None
            else _runtime_value(runtime, "strategy_family_id", "family")
        ),
        "strategy_family_version_id": _runtime_value(
            runtime,
            "strategy_family_version_id",
            "carrier_id",
        ),
        "lane_identity": (
            lane_identity.model_dump(mode="json") if lane_identity is not None else None
        ),
        "lane_identity_key": (
            lane_identity.identity_key if lane_identity is not None else None
        ),
        "can_materialize_live_signal_event": (
            signal_artifact.get("can_materialize_live_signal_event") is True
        ),
        "ready_for_action_time_ticket_materialization": artifact.get(
            "ready_for_action_time_ticket_materialization"
        ),
        "ready_for_final_gate_preflight": artifact.get(
            "ready_for_final_gate_preflight"
        ),
        "blockers": list(artifact.get("blockers") or []),
        "warnings": list(artifact.get("warnings") or []),
        "signal_input_ref": signal_input_ref,
        "action_time_ticket_id": artifact.get("ticket_id"),
        "signal_summary": _signal_summary(artifact),
        "action_time_ticket_created": bool(safety.get("action_time_ticket_created")),
        "created_records": {
            "action_time_ticket_created": bool(safety.get("action_time_ticket_created")),
            "runtime_execution_intent_draft_created": bool(
                safety.get("runtime_execution_intent_draft_created")
            ),
            "recorded_execution_intent_created": bool(
                safety.get("recorded_execution_intent_created")
            ),
            "submit_authorization_created": bool(
                safety.get("submit_authorization_created")
            ),
            "protection_plan_created": bool(safety.get("protection_plan_created")),
            "executable_execution_intent_created": bool(
                safety.get("executable_execution_intent_created")
            ),
        },
        "forbidden_effects": {
            "exchange_write_called": bool(safety.get("exchange_write_called")),
            "order_created": bool(safety.get("order_created")),
            "order_lifecycle_called": bool(safety.get("order_lifecycle_called")),
            "attempt_counter_mutated": bool(safety.get("attempt_counter_mutated")),
            "runtime_budget_mutated": bool(safety.get("runtime_budget_mutated")),
            "withdrawal_or_transfer_created": bool(
                safety.get("withdrawal_or_transfer_created")
            ),
        },
    }


def _safety(
    *,
    allow_action_time_ticket_materialization: bool,
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    def any_flag(name: str) -> bool:
        return any(
            bool((artifact.get("safety_invariants") or {}).get(name))
            for artifact in artifacts
        )

    return {
        "uses_official_trading_console_api": True,
        "monitors_active_runtimes": True,
        "allow_action_time_ticket_materialization": (
            allow_action_time_ticket_materialization
        ),
        "action_time_ticket_created": any_flag("action_time_ticket_created"),
        "runtime_execution_intent_draft_created": any_flag(
            "runtime_execution_intent_draft_created"
        ),
        "recorded_execution_intent_created": any_flag(
            "recorded_execution_intent_created"
        ),
        "submit_authorization_created": any_flag("submit_authorization_created"),
        "protection_plan_created": any_flag("protection_plan_created"),
        "executable_execution_intent_created": any_flag(
            "executable_execution_intent_created"
        ),
        "local_registration_armed": any_flag("local_registration_armed"),
        "exchange_submit_armed": any_flag("exchange_submit_armed"),
        "execute_real_submit": any_flag("execute_real_submit"),
        "exchange_write_called": any_flag("exchange_write_called"),
        "order_created": any_flag("order_created"),
        "order_lifecycle_called": any_flag("order_lifecycle_called"),
        "attempt_counter_mutated": any_flag("attempt_counter_mutated"),
        "runtime_budget_mutated": any_flag("runtime_budget_mutated"),
        "position_opened": any_flag("position_opened"),
        "position_closed": any_flag("position_closed"),
        "withdrawal_or_transfer_created": any_flag("withdrawal_or_transfer_created"),
    }


def _overall_status(artifacts: list[dict[str, Any]]) -> str:
    statuses = {str(artifact.get("status") or "unknown") for artifact in artifacts}
    if not artifacts:
        return "no_active_runtimes"
    if "ready_for_final_gate_preflight" in statuses:
        return "ready_for_final_gate_preflight"
    if "ready_for_action_time_ticket_materialization" in statuses:
        return "ready_for_action_time_ticket_materialization"
    if statuses == {"waiting_for_signal"}:
        return "waiting_for_signal"
    if "blocked" in statuses:
        return "blocked"
    return "mixed"


def _build_monitor_artifact(
    args: argparse.Namespace,
    *,
    client: Any | None = None,
    runtime_artifact_builder: Callable[[argparse.Namespace], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    _load_env_file(args.env_file)
    api_client = client or UrlLibApiClient(api_base=_api_base(args))
    builder = runtime_artifact_builder or _build_runtime_observation_cycle_artifact
    active = _active_runtimes(client=api_client)
    requested_runtime_instance_ids = list(
        getattr(args, "runtime_instance_id", None) or []
    )
    requested_strategy_family_ids = list(
        getattr(args, "strategy_family_id", None) or []
    )
    candidate_universe, candidate_universe_source = _candidate_universe_for_args(args)
    side_scope = _side_scope_from_source(candidate_universe_source)
    selected, missing_runtime_instance_ids = _selected_active_runtimes(
        active,
        runtime_instance_ids=requested_runtime_instance_ids,
        strategy_family_ids=requested_strategy_family_ids,
        max_runtimes=int(args.max_runtimes or 100),
    )
    enforce_candidate_universe_scope = (
        candidate_universe_source.get("source")
        == "pg_runtime_control_state:candidate_scope"
        and candidate_universe_source.get("loaded") is True
    )
    selected, candidate_universe_excluded_runtime_instance_ids = (
        _filter_selected_to_candidate_universe(
            selected,
            candidate_universe,
            side_scope=side_scope,
        )
        if enforce_candidate_universe_scope
        else (selected, [])
    )
    candidate_universe_coverage = _candidate_universe_coverage(
        candidate_universe=candidate_universe,
        source=candidate_universe_source,
        active=active,
        selected=selected,
        side_scope=side_scope,
    )

    runtime_artifacts: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for runtime in selected:
        runtime_args = _monitor_args(args, runtime)
        runtime_artifact = builder(runtime_args)
        runtime_artifact["runtime_instance_id"] = runtime_args.runtime_instance_id
        runtime_artifacts.append(runtime_artifact)
        summaries.append(_summary(runtime, runtime_artifact))

    status = _overall_status(runtime_artifacts)
    blockers: list[str] = []
    for item in summaries:
        for blocker in item["blockers"]:
            if _is_waiting_for_signal_blocker(
                status=str(item.get("status") or ""),
                blocker=str(blocker),
            ):
                continue
            scoped = f"{item['runtime_instance_id']}:{blocker}"
            if scoped not in blockers:
                blockers.append(scoped)
    warnings: list[str] = []
    for runtime_id in missing_runtime_instance_ids:
        warnings.append(f"requested_runtime_not_active_or_not_found:{runtime_id}")
    for runtime_id in candidate_universe_excluded_runtime_instance_ids:
        warnings.append(f"runtime_excluded_by_candidate_universe:{runtime_id}")
    effective_timeout = _effective_observation_timeout_seconds(args)
    if float(args.timeout_seconds or 10.0) != effective_timeout:
        warnings.append(
            "observation_timeout_seconds_clamped_to_api_max_60"
        )
    for row in candidate_universe_coverage["rows"]:
        if row["blocker_class"] == "runtime_profile_scope_missing":
            warnings.append(
                "candidate_universe_runtime_profile_scope_missing:"
                f"{row['strategy_group_id']}:{row['symbol']}"
            )

    signal_input_ref = _first_summary_text(summaries, "signal_input_ref")
    action_time_ticket_id = _first_summary_text(summaries, "action_time_ticket_id")

    return {
        "scope": "runtime_active_observation_monitor",
        "status": status,
        "active_runtime_count": len(active),
        "monitored_runtime_count": len(selected),
        "requested_runtime_instance_ids": requested_runtime_instance_ids,
        "requested_strategy_family_ids": requested_strategy_family_ids,
        "selected_runtime_instance_ids": [
            str(_runtime_value(runtime, "runtime_instance_id", "runtime_id") or "")
            for runtime in selected
        ],
        "candidate_universe_excluded_runtime_instance_ids": (
            candidate_universe_excluded_runtime_instance_ids
        ),
        "candidate_universe_coverage": candidate_universe_coverage,
        "allow_action_time_ticket_materialization": (
            getattr(args, "allow_action_time_ticket_materialization", False)
        ),
        "max_cycles_per_runtime": args.max_cycles_per_runtime,
        "requested_timeout_seconds": args.timeout_seconds,
        "effective_observation_timeout_seconds": effective_timeout,
        "runtime_summaries": summaries,
        "runtime_artifacts": runtime_artifacts if args.include_runtime_artifacts else [],
        "blockers": blockers,
        "warnings": warnings,
        "observation_monitor_plan": {
            "next_step": _next_step(status),
            "not_executed": True,
            "signal_input_ref": signal_input_ref,
            "action_time_ticket_id": action_time_ticket_id,
            "creates_action_time_ticket": any(
                bool((artifact.get("safety_invariants") or {}).get("action_time_ticket_created"))
                for artifact in runtime_artifacts
            ),
            "creates_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "requires_official_final_gate": True,
            "uses_standing_runtime_authorization": True,
            "requires_official_operation_layer": True,
            "candidate_universe_coverage_status": candidate_universe_coverage[
                "status"
            ],
        },
        "safety_invariants": _safety(
            allow_action_time_ticket_materialization=(
                getattr(args, "allow_action_time_ticket_materialization", False)
            ),
            artifacts=runtime_artifacts,
        ),
    }


def _first_summary_text(summaries: list[dict[str, Any]], key: str) -> str | None:
    for item in summaries:
        text = str(item.get(key) or "").strip()
        if text:
            return text
    return None


def _next_step(status: str) -> str:
    if status == "ready_for_final_gate_preflight":
        return "run_official_final_gate_preflight_for_action_time_ticket"
    if status == "ready_for_action_time_ticket_materialization":
        return "materialize_pg_action_time_ticket"
    if status == "blocked":
        return "resolve_runtime_observation_blockers"
    if status == "no_active_runtimes":
        return "start_or_authorize_a_runtime_before_monitoring"
    return "wait_for_next_observation_cycle"


def _nested_get(value: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _is_observe_only_review_artifact(artifact: dict[str, Any]) -> bool:
    summary = _signal_summary(artifact)
    return str(summary.get("required_execution_mode") or "") == "observe_only"


def _is_waiting_for_signal_blocker(*, status: str, blocker: str) -> bool:
    return (
        status == "waiting_for_signal"
        and blocker in WAITING_FOR_SIGNAL_BLOCKERS
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor all ACTIVE strategy runtimes without live submit.",
    )
    parser.add_argument("--env-file")
    parser.add_argument("--api-base")
    parser.add_argument("--source", choices=["live_market", "sample"], default="live_market")
    parser.add_argument("--include-exchange", action="store_true", default=False)
    parser.add_argument(
        "--allow-action-time-ticket-materialization",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--runtime-instance-id",
        action="append",
        default=[],
        help=(
            "Limit monitoring to the given ACTIVE runtime instance. "
            "May be repeated."
        ),
    )
    parser.add_argument(
        "--strategy-family-id",
        action="append",
        default=[],
        help=(
            "Limit monitoring to ACTIVE runtimes belonging to this strategy "
            "family. May be repeated."
        ),
    )
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument(
        "--require-database-url",
        action="store_true",
        help="Require PG_DATABASE_URL. Active observation candidate scope is PG-only.",
    )
    parser.add_argument(
        "--allow-non-postgres-for-test",
        action="store_true",
        help="Allow SQLite/non-PG DSNs only in tests.",
    )
    parser.add_argument("--max-runtimes", type=int, default=100)
    parser.add_argument("--max-cycles-per-runtime", type=int, default=1)
    parser.add_argument("--interval-seconds", type=float, default=0.0)
    parser.add_argument("--continue-on-blocked", action="store_true", default=False)
    parser.add_argument("--one-hour-limit", type=int, default=25)
    parser.add_argument("--four-hour-limit", type=int, default=25)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--include-runtime-artifacts", action="store_true", default=False)
    parser.add_argument("--playbook-id")
    parser.add_argument("--owner-operator-id", default="owner")
    parser.add_argument(
        "--owner-confirmation-reference",
        default="owner-authorized-active-runtime-observation-monitor",
    )
    parser.add_argument(
        "--reason",
        default="owner authorized active runtime observation monitor",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    with redirect_stdout(sys.stderr):
        artifact = _build_monitor_artifact(args)
        artifact["pg_watcher_runtime_coverage"] = (
            write_candidate_universe_coverage_to_pg(
                artifact,
                database_url=str(args.database_url or ""),
                allow_non_postgres_for_test=bool(args.allow_non_postgres_for_test),
            )
        )
        artifact["pg_live_signal_events"] = (
            write_runtime_signal_summaries_to_pg(
                artifact,
                database_url=str(args.database_url or ""),
                allow_non_postgres_for_test=bool(args.allow_non_postgres_for_test),
            )
        )
    output = json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    print(output)
    return 0 if artifact["status"] in {
        "waiting_for_signal",
        "ready_for_action_time_ticket_materialization",
        "ready_for_final_gate_preflight",
        "no_active_runtimes",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
