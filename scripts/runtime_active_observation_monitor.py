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
from src.infrastructure.runtime_control_state_repository import (  # noqa: E402
    PgBackedRuntimeControlStateRepository,
)
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
    "strategy_signal_not_ready_for_shadow_candidate_prepare",
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
    for row in control_state.get("candidate_scope") or []:
        if not isinstance(row, dict) or row.get("status") != "active":
            continue
        strategy_group_id = str(row.get("strategy_group_id") or "").strip()
        symbol = _compact_symbol(row.get("symbol"))
        side = _normalize_side(row.get("side"))
        if not strategy_group_id or not symbol or not side:
            continue
        universe.setdefault(strategy_group_id, [])
        if symbol not in universe[strategy_group_id]:
            universe[strategy_group_id].append(symbol)
        side_scope.setdefault(strategy_group_id, [])
        if side not in side_scope[strategy_group_id]:
            side_scope[strategy_group_id].append(side)

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
            "source_mode": str(control_state.get("source_mode") or ""),
            "projection_target": str(control_state.get("projection_target") or ""),
        },
    )


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
            return _candidate_universe_from_control_state(repository.read_control_state())
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


def write_candidate_universe_coverage_to_pg(
    artifact: dict[str, Any],
    *,
    database_url: str,
    allow_non_postgres_for_test: bool = False,
    now_ms: int | None = None,
) -> dict[str, Any]:
    if not database_url:
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

    normalized_url = normalize_sync_postgres_dsn(database_url)
    if not is_sync_postgres_dsn(normalized_url) and not allow_non_postgres_for_test:
        raise RuntimeError("PG watcher runtime coverage write requires PostgreSQL DSN")
    observed_ms = int(now_ms if now_ms is not None else time.time() * 1000)
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


def _replace_current_watcher_runtime_coverage(
    conn: sa.engine.Connection,
    *,
    rows: list[dict[str, Any]],
    observed_ms: int,
) -> None:
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
        conn.execute(
            sa.text(
                """
                INSERT INTO brc_watcher_runtime_coverage (
                  runtime_coverage_id,
                  strategy_group_id,
                  symbol,
                  side,
                  detector_key,
                  runtime_profile_id,
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
                  :runtime_profile_id,
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
                "runtime_profile_id": str(
                    runtime_profile.get("runtime_profile_id") or ""
                )
                or None,
                "coverage_state": coverage_state,
                "liveness_state": liveness_state,
                "last_tick_at_ms": observed_ms,
                "valid_until_ms": valid_until_ms,
                "is_current": True,
                "created_at_ms": observed_ms,
            },
        )


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
        allow_prepare_records=args.allow_prepare_records,
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
        "allow_prepare_records": False,
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
                "creates_shadow_candidate": False,
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
                "creates_shadow_candidate": False,
                "creates_execution_intent": False,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "safety_invariants": _non_executing_runtime_observation_safety(),
        }
    return payload


def _non_executing_runtime_observation_safety() -> dict[str, bool]:
    return {
        "allow_prepare_records": False,
        "prepare_records_created": False,
        "shadow_candidate_created": False,
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


def _signal_summary(artifact: dict[str, Any]) -> dict[str, Any]:
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
        signal_artifact = {}
    evaluation = signal_artifact.get("evaluation_result")
    if not isinstance(evaluation, dict):
        evaluation = {}
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
    return {
        "evaluation_status": evaluation.get("status"),
        "evaluator_id": evaluation.get("evaluator_id"),
        "signal_type": output.get("signal_type"),
        "required_execution_mode": output.get("required_execution_mode"),
        "side": output.get("side"),
        "reason_codes": list(output.get("reason_codes") or []),
        "human_summary": output.get("human_summary"),
        "confidence": output.get("confidence"),
        "data_quality_status": data_quality.get("status"),
        "context_tags": context_tags,
        "can_call_semantic_binding": evaluation.get("can_call_semantic_binding"),
        "semantics_binding_found": evaluation.get("semantics_binding_found"),
        "strategy_candidate_mode": evaluation.get("strategy_candidate_mode"),
        "timestamp_ms": output.get("timestamp_ms"),
    }


def _summary(runtime: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
    safety = artifact.get("safety_invariants")
    if not isinstance(safety, dict):
        safety = {}
    plan = (
        artifact.get("observation_cycle_plan")
        or artifact.get("observation_monitor_plan")
        or artifact.get("api_prepare_plan")
        or {}
    )
    return {
        "runtime_instance_id": _runtime_value(runtime, "runtime_instance_id", "runtime_id"),
        "status": artifact.get("status"),
        "symbol": _runtime_value(runtime, "symbol"),
        "side": _runtime_value(runtime, "side"),
        "strategy_family_id": _runtime_value(runtime, "strategy_family_id", "family"),
        "strategy_family_version_id": _runtime_value(
            runtime,
            "strategy_family_version_id",
            "carrier_id",
        ),
        "ready_for_prepare": artifact.get("ready_for_prepare"),
        "ready_for_final_gate_preflight": artifact.get(
            "ready_for_final_gate_preflight"
        ),
        "blockers": list(artifact.get("blockers") or []),
        "warnings": list(artifact.get("warnings") or []),
        "signal_input_json": artifact.get("signal_input_json")
        or plan.get("signal_input_json"),
        "prepared_authorization_id": artifact.get("prepared_authorization_id")
        or plan.get("prepared_authorization_id"),
        "signal_summary": _signal_summary(artifact),
        "prepare_records_created": bool(safety.get("prepare_records_created")),
        "created_records": {
            "shadow_candidate_created": bool(safety.get("shadow_candidate_created")),
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
    allow_prepare_records: bool,
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
        "allow_prepare_records": allow_prepare_records,
        "prepare_records_created": any_flag("prepare_records_created"),
        "shadow_candidate_created": any_flag("shadow_candidate_created"),
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
    if "ready_for_prepare" in statuses:
        return "ready_for_prepare"
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
        runtime_artifact = _downgrade_non_actionable_observation_blockers(
            runtime_artifact
        )
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

    signal_input_json = _first_summary_text(summaries, "signal_input_json")
    prepared_authorization_id = _first_summary_text(
        summaries,
        "prepared_authorization_id",
    )

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
        "allow_prepare_records": args.allow_prepare_records,
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
            "signal_input_json": signal_input_json,
            "prepared_authorization_id": prepared_authorization_id,
            "creates_shadow_candidate": any(
                bool(
                    (artifact.get("safety_invariants") or {}).get(
                        "prepare_records_created"
                    )
                )
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
            allow_prepare_records=args.allow_prepare_records,
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
        return "run_official_final_gate_preflight_for_prepared_authorization"
    if status == "ready_for_prepare":
        return "rerun_active_monitor_with_allow_prepare_records_under_standing_authorization"
    if status == "blocked":
        return "resolve_runtime_observation_blockers"
    if status == "no_active_runtimes":
        return "start_or_authorize_a_runtime_before_monitoring"
    return "wait_for_next_observation_cycle"


def _downgrade_non_actionable_observation_blockers(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    if str(artifact.get("status") or "") != "blocked":
        return artifact
    blockers = [str(blocker) for blocker in artifact.get("blockers") or []]
    if not blockers:
        return artifact
    observation_only = _is_observe_only_review_artifact(artifact)
    allowed_blockers = set(NON_ACTIONABLE_OBSERVATION_BLOCKERS)
    if observation_only:
        allowed_blockers.update(OBSERVE_ONLY_REVIEW_BLOCKERS)
    if any(blocker not in allowed_blockers for blocker in blockers):
        return artifact
    safety = artifact.get("safety_invariants")
    if not isinstance(safety, dict):
        safety = {}
    if any(
        bool(safety.get(flag))
        for flag in (
            "submit_authorization_created",
            "protection_plan_created",
            "executable_execution_intent_created",
            "local_registration_armed",
            "exchange_submit_armed",
            "execute_real_submit",
            "exchange_write_called",
            "order_created",
            "order_lifecycle_called",
            "attempt_counter_mutated",
            "runtime_budget_mutated",
            "position_opened",
            "position_closed",
            "withdrawal_or_transfer_created",
        )
    ):
        return artifact

    signal_input_json = _artifact_signal_input_json(artifact)
    if signal_input_json:
        promoted = dict(artifact)
        promoted["status"] = "ready_for_prepare"
        promoted["blockers"] = []
        promoted["warnings"] = sorted(
            {
                *[str(warning) for warning in artifact.get("warnings") or []],
                *[
                    f"non_actionable_prepare_blocker:{blocker}"
                    for blocker in blockers
                ],
            }
        )
        promoted["signal_input_json"] = signal_input_json
        plan = dict(
            artifact.get("api_prepare_plan")
            or artifact.get("observation_cycle_plan")
            or artifact.get("observation_monitor_plan")
            or {}
        )
        plan["next_step"] = (
            plan.get("next_step")
            or "prepare_fresh_candidate_authorization_evidence"
        )
        plan["signal_input_json"] = signal_input_json
        plan["not_executed"] = True
        plan["creates_execution_intent"] = False
        plan["places_order"] = False
        plan["calls_order_lifecycle"] = False
        promoted["observation_monitor_plan"] = plan
        promoted["non_actionable_observation_blockers"] = blockers
        return promoted

    downgraded = dict(artifact)
    downgraded["status"] = "waiting_for_signal"
    downgraded["blockers"] = []
    downgraded["warnings"] = sorted(
        {
            *[str(warning) for warning in artifact.get("warnings") or []],
            *[
                f"non_actionable_observation_blocker:{blocker}"
                for blocker in blockers
            ],
        }
    )
    plan = dict(
        artifact.get("observation_cycle_plan")
        or artifact.get("observation_monitor_plan")
        or {}
    )
    plan["next_step"] = "continue_waiting_for_strategy_signal"
    plan["not_executed"] = True
    plan["places_order"] = False
    plan["calls_order_lifecycle"] = False
    downgraded["observation_monitor_plan"] = plan
    downgraded["non_actionable_observation_blockers"] = blockers
    return downgraded


def _artifact_signal_input_json(artifact: dict[str, Any]) -> str | None:
    for candidate in (
        artifact.get("signal_input_json"),
        _nested_get(artifact, ("api_prepare_plan", "signal_input_json")),
        _nested_get(artifact, ("observation_cycle_plan", "signal_input_json")),
        _nested_get(artifact, ("observation_monitor_plan", "signal_input_json")),
    ):
        text = str(candidate or "").strip()
        if text:
            return text
    return None


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
    parser.add_argument("--allow-prepare-records", action="store_true", default=False)
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
    output = json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    print(output)
    return 0 if artifact["status"] in {
        "waiting_for_signal",
        "ready_for_prepare",
        "ready_for_final_gate_preflight",
        "no_active_runtimes",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
