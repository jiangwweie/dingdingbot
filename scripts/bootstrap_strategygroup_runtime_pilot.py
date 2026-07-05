#!/usr/bin/env python3
"""Plan or execute StrategyGroup runtime pilot bootstrap.

This script connects the Owner-facing StrategyGroup picker to the existing
official runtime bootstrap API flow. Default mode is plan-only. With
``--execute`` it may create StrategyFamily / Admission / TrialBinding /
shadow StrategyRuntimeInstance records through official API surfaces. It never
creates candidates, ExecutionIntents, orders, withdrawals, transfers, or
exchange submit actions.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from decimal import Decimal
import json
import os
from pathlib import Path
import shlex
import sys
import time
from typing import Any

import sqlalchemy as sa

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.infrastructure.runtime_control_state_repository import (  # noqa: E402
    PgBackedRuntimeControlStateRepository,
)
from scripts.runtime_first_real_submit_api_flow import (  # noqa: E402
    DEFAULT_API_BASE,
    UrlLibApiClient,
)
from scripts.runtime_live_bootstrap_api_flow import (  # noqa: E402
    BootstrapConfig,
    RuntimeLiveBootstrapApiFlow,
)


DEFAULT_OUTPUT_JSON = (
    ROOT_DIR / "output/strategygroup-runtime-pilot/runtime-bootstrap-artifact.json"
)
DEFAULT_PLAYBOOK_ID = "PB-BRC-STRATEGYGROUP-RUNTIME-PILOT-V1"
DEFAULT_MAX_SYMBOLS_PER_GROUP = 1
DEFAULT_MAX_TOTAL_NEW_RUNTIMES = 4
PG_SOURCE_REF = "pg_runtime_control_state:candidate_scope"
BOOTSTRAPPABLE_INTAKE_STATUSES = {
    "armed_observation_intake_ready",
    "conditional_armed_observation_intake_ready",
}
BOOTSTRAPPABLE_DEFAULT_MODES = {
    "armed_observation",
    "conditional_armed_observation",
}
FORBIDDEN_EFFECT_FLAGS = {
    "creates_order_candidate",
    "creates_execution_intent",
    "creates_order",
    "calls_exchange_submit",
    "withdrawal_or_transfer_created",
}


@dataclass(frozen=True)
class RuntimePilotBootstrapConfig:
    api_base: str = DEFAULT_API_BASE
    execute: bool = False
    strategy_group_ids: tuple[str, ...] = ()
    include_observe_only: bool = False
    max_symbols_per_group: int = DEFAULT_MAX_SYMBOLS_PER_GROUP
    max_total_new_runtimes: int = DEFAULT_MAX_TOTAL_NEW_RUNTIMES
    account_facts_source: str = "binance_readonly"
    owner_operator_id: str = "owner-standing-authorization"
    playbook_id: str = DEFAULT_PLAYBOOK_ID
    output_json: str | None = None
    renew_exhausted_runtimes: bool = False
    renewal_batch_id: str | None = None
    candidate_universe_source: str | None = None


def _is_postgres_dsn(database_url: str) -> bool:
    return database_url.startswith(("postgresql://", "postgresql+psycopg://"))


def _read_control_state_from_pg(
    *,
    database_url: str,
    allow_non_postgres_for_test: bool = False,
) -> dict[str, Any]:
    if not database_url:
        raise RuntimeError("PG_DATABASE_URL is required for runtime bootstrap")
    if not _is_postgres_dsn(database_url) and not allow_non_postgres_for_test:
        raise RuntimeError("DB-backed runtime bootstrap requires PostgreSQL DSN")
    engine = sa.create_engine(database_url)
    try:
        with engine.connect() as conn:
            return PgBackedRuntimeControlStateRepository(conn).read_control_state()
    finally:
        engine.dispose()


def _dict_rows(control_state: dict[str, Any], key: str) -> list[dict[str, Any]]:
    return [
        row
        for row in control_state.get(key) or []
        if isinstance(row, dict)
    ]


def _risk_defaults_from_policy(policy: dict[str, Any] | None) -> dict[str, str]:
    policy = policy if isinstance(policy, dict) else {}
    return {
        "max_notional_per_action_usdt": str(
            policy.get("max_notional") or policy.get("max_notional_usdt") or "8"
        ),
        "max_leverage": str(policy.get("leverage") or "1"),
    }


def _required_policy_risk_defaults(policy: dict[str, Any] | None) -> dict[str, str]:
    if not policy:
        raise RuntimeError("owner policy current row is required for runtime bootstrap")
    policy_current_id = str(policy.get("policy_current_id") or "unknown_policy")
    raw_notional = policy.get("max_notional") or policy.get("max_notional_usdt")
    raw_leverage = policy.get("leverage")
    if raw_notional in (None, "") or raw_leverage in (None, ""):
        raise RuntimeError(
            f"{policy_current_id} missing max_notional or leverage scope"
        )
    try:
        max_notional = Decimal(str(raw_notional))
        max_leverage = Decimal(str(raw_leverage))
    except Exception as exc:
        raise RuntimeError(
            f"{policy_current_id} has invalid max_notional or leverage scope"
        ) from exc
    if max_notional <= 0 or max_leverage <= 0:
        raise RuntimeError(
            f"{policy_current_id} has non-positive max_notional or leverage scope"
        )
    return {
        "max_notional_per_action_usdt": str(max_notional),
        "max_leverage": str(max_leverage),
    }


def _active_runtime_bindings_by_candidate(
    control_state: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for binding in _dict_rows(control_state, "runtime_scope_bindings"):
        if binding.get("status") != "active":
            continue
        candidate_scope_id = str(binding.get("candidate_scope_id") or "").strip()
        if not candidate_scope_id:
            raise RuntimeError("active runtime scope binding missing candidate_scope_id")
        if candidate_scope_id in result:
            raise RuntimeError(
                f"{candidate_scope_id} has multiple active runtime scope bindings"
            )
        result[candidate_scope_id] = binding
    return result


def _require_closed_runtime_scope_binding(
    *,
    row: dict[str, Any],
    binding: dict[str, Any] | None,
    policy: dict[str, Any] | None,
) -> None:
    candidate_scope_id = str(row.get("candidate_scope_id") or "unknown_candidate")
    if not binding:
        raise RuntimeError(f"{candidate_scope_id} has no active runtime scope binding")
    for key in ("strategy_group_id", "symbol", "side", "policy_current_id"):
        if str(binding.get(key) or "") != str(row.get(key) or ""):
            raise RuntimeError(f"{candidate_scope_id} runtime binding mismatches {key}")
    required_flags = (
        "selected_strategygroup_scope",
        "symbol_side_scope_closed",
        "notional_leverage_scope_closed",
        "live_submit_allowed",
    )
    for flag in required_flags:
        if binding.get(flag) is not True:
            raise RuntimeError(f"{candidate_scope_id} runtime binding missing {flag}")
    if not policy:
        raise RuntimeError(f"{candidate_scope_id} has no current owner policy")
    for key in ("strategy_group_id", "symbol", "side"):
        if str(policy.get(key) or "") != str(row.get(key) or ""):
            raise RuntimeError(f"{candidate_scope_id} owner policy mismatches {key}")
    if policy.get("enabled_state") != "enabled":
        raise RuntimeError(f"{candidate_scope_id} owner policy is not enabled")
    if policy.get("pretrade_candidate_allowed") is not True:
        raise RuntimeError(
            f"{candidate_scope_id} owner policy blocks pretrade candidate"
        )
    if policy.get("action_time_rehearsal_allowed") is not True:
        raise RuntimeError(
            f"{candidate_scope_id} owner policy blocks action-time rehearsal"
        )
    if policy.get("live_submit_allowed") not in {"scoped", "conditional_hard_gated"}:
        raise RuntimeError(f"{candidate_scope_id} owner policy blocks live submit")
    _required_policy_risk_defaults(policy)


def _bootstrap_inputs_from_control_state(
    control_state: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    candidate_rows = [
        row
        for row in _dict_rows(control_state, "candidate_scope")
        if row.get("status") == "active"
    ]
    if not candidate_rows:
        raise RuntimeError("PG runtime bootstrap has no active candidate scope")

    strategy_rows = {
        str(row.get("strategy_group_id") or ""): row
        for row in _dict_rows(control_state, "strategy_groups")
    }
    version_rows = {
        str(row.get("strategy_group_id") or ""): row
        for row in _dict_rows(control_state, "strategy_group_versions")
        if row.get("status") == "current"
    }
    policy_rows = {
        str(row.get("policy_current_id") or ""): row
        for row in _dict_rows(control_state, "owner_policy_current")
    }
    runtime_bindings = _active_runtime_bindings_by_candidate(control_state)

    symbols_by_group: dict[str, list[str]] = {}
    lanes_by_group: dict[str, list[str]] = {}
    sides_by_group: dict[str, list[str]] = {}
    candidate_by_group: dict[str, list[dict[str, Any]]] = {}
    risk_defaults_by_group_lane: dict[str, dict[str, dict[str, str]]] = {}
    for row in candidate_rows:
        candidate_scope_id = str(row.get("candidate_scope_id") or "unknown_candidate")
        strategy_group_id = str(row.get("strategy_group_id") or "").strip()
        symbol = _exchange_symbol(row.get("symbol"))
        side = str(row.get("side") or "").strip().lower()
        if (
            not strategy_group_id
            or not symbol
            or not symbol.endswith("USDT")
            or side not in {"long", "short"}
        ):
            raise RuntimeError(f"{candidate_scope_id} has malformed active candidate scope")
        policy_current_id = str(row.get("policy_current_id") or "")
        binding = runtime_bindings.get(candidate_scope_id)
        policy = policy_rows.get(policy_current_id)
        _require_closed_runtime_scope_binding(
            row=row,
            binding=binding,
            policy=policy,
        )
        candidate_by_group.setdefault(strategy_group_id, []).append(row)
        risk_defaults_by_group_lane.setdefault(strategy_group_id, {})[
            f"{symbol}:{side}"
        ] = _required_policy_risk_defaults(policy)
        symbols_by_group.setdefault(strategy_group_id, [])
        if symbol not in symbols_by_group[strategy_group_id]:
            symbols_by_group[strategy_group_id].append(symbol)
        lanes_by_group.setdefault(strategy_group_id, [])
        lane_key = f"{symbol}:{side}"
        if lane_key not in lanes_by_group[strategy_group_id]:
            lanes_by_group[strategy_group_id].append(lane_key)
        sides_by_group.setdefault(strategy_group_id, [])
        if side not in sides_by_group[strategy_group_id]:
            sides_by_group[strategy_group_id].append(side)

    strategy_picker: list[dict[str, Any]] = []
    readiness_rows: list[dict[str, Any]] = []
    symbol_readiness_rows: list[dict[str, Any]] = []
    candidate_pool_rows: list[dict[str, Any]] = []
    for strategy_group_id, rows in sorted(candidate_by_group.items()):
        rows = sorted(
            rows,
            key=lambda row: (
                int(row.get("priority_rank") or 999),
                str(row.get("symbol") or ""),
                str(row.get("side") or ""),
            ),
        )
        first = rows[0]
        strategy = strategy_rows.get(strategy_group_id) or {}
        version = version_rows.get(strategy_group_id) or {}
        policy = policy_rows.get(str(first.get("policy_current_id") or ""))
        min_rank = min(int(row.get("priority_rank") or 999) for row in rows)
        symbols = sorted(symbols_by_group.get(strategy_group_id) or [])
        sides = sorted(sides_by_group.get(strategy_group_id) or [])
        strategy_picker.append(
            {
                "strategy_group_id": strategy_group_id,
                "name": strategy.get("owner_label") or strategy_group_id,
                "intake_status": "armed_observation_intake_ready",
                "supported_symbols": symbols,
                "supported_sides": sides,
                "signal_ready_rule": {"side": sides[0] if sides else "long"},
                "risk_defaults": _required_policy_risk_defaults(policy),
                "risk_defaults_by_lane": risk_defaults_by_group_lane.get(
                    strategy_group_id,
                    {},
                ),
                "picker": {
                    "rank": min_rank,
                    "default_mode": "armed_observation",
                },
                "edge_thesis": version.get("edge_thesis"),
                "candidate_universe_source": PG_SOURCE_REF,
            }
        )
        readiness_rows.append(
            {
                "strategy_group_id": strategy_group_id,
                "readiness_status": "pg_runtime_scope_ready",
                "observe_ready": True,
                "armed_candidate_prepare_ready": False,
                "exchange_rules": {
                    "ready_symbols": symbols,
                    "blocked_symbols": [],
                },
                "blockers": [],
                "source": PG_SOURCE_REF,
            }
        )
        for row in rows:
            symbol = _exchange_symbol(row.get("symbol"))
            side = str(row.get("side") or "").strip().lower()
            symbol_readiness_rows.append(
                {
                    "strategy_group_id": strategy_group_id,
                    "candidate_scope_id": row.get("candidate_scope_id"),
                    "symbol": symbol,
                    "side": side,
                    "status": "runtime_scope_ready",
                    "source": PG_SOURCE_REF,
                }
            )
        candidate_pool_rows.append(
            {
                "strategy_group_id": strategy_group_id,
                "daily_rank": min_rank,
                "side": str(first.get("side") or "long"),
            }
        )

    candidate_pool = {
        "schema": "brc.strategy_live_candidate_pool.v1",
        "status": "strategy_live_candidate_pool_ready",
        "source_mode": "db_backed",
        "authority_boundary": "pg_runtime_control_state_only",
        "candidate_universe": {
            key: sorted(value) for key, value in sorted(symbols_by_group.items())
        },
        "candidate_lane_universe": {
            key: sorted(value) for key, value in sorted(lanes_by_group.items())
        },
        "candidate_rows": candidate_pool_rows,
        "symbol_readiness_rows": symbol_readiness_rows,
    }
    return (
        {
            "status": "ready_for_main_control_intake",
            "source_mode": "db_backed",
            "authority_boundary": "pg_runtime_control_state_only",
            "strategy_picker": strategy_picker,
        },
        {
            "status": "runtime_scope_readiness_ready",
            "source_mode": "db_backed",
            "readiness": readiness_rows,
        },
        candidate_pool,
        PG_SOURCE_REF,
    )


def _load_bootstrap_inputs(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str | None]:
    database_url = str(getattr(args, "database_url", "") or "")
    if getattr(args, "execute", False) and getattr(
        args,
        "allow_non_postgres_for_test",
        False,
    ):
        raise RuntimeError(
            "--allow-non-postgres-for-test must not be combined with --execute"
        )
    if getattr(args, "require_database_url", False) and not database_url:
        raise RuntimeError("PG_DATABASE_URL is required for runtime bootstrap")
    if database_url:
        control_state = _read_control_state_from_pg(
            database_url=database_url,
            allow_non_postgres_for_test=bool(
                getattr(args, "allow_non_postgres_for_test", False)
            ),
        )
        return _bootstrap_inputs_from_control_state(control_state)

    raise RuntimeError("PG_DATABASE_URL is required for PG-only runtime bootstrap")


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
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


def _list_active_runtimes(client: Any) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        response = client.request_json("GET", "/api/trading-console/strategy-runtimes")
    except Exception as exc:
        return [], [f"active_runtime_inventory_unavailable:{type(exc).__name__}"]
    body = response.get("body")
    if response.get("http_status", 0) >= 300 or response.get("error"):
        return [], [f"active_runtime_inventory_http_{response.get('http_status')}"]
    items = body if isinstance(body, list) else (body or {}).get("items", [])
    if not isinstance(items, list):
        return [], ["active_runtime_inventory_response_not_list"]
    active = [
        item
        for item in items
        if isinstance(item, dict)
        and str(item.get("status") or "").lower() == "active"
    ]
    return active, []


def _exchange_symbol(symbol: Any) -> str:
    text = str(symbol or "").strip().upper()
    if not text:
        return ""
    return text.replace("/", "").replace(":USDT", "")


def _runtime_symbol(symbol: Any) -> str:
    text = str(symbol or "").strip()
    if not text:
        return ""
    if "/" in text:
        return text
    upper = text.upper()
    if upper.endswith("USDT"):
        return f"{upper[:-4]}/USDT:USDT"
    return text


def _safe_id(value: str) -> str:
    return (
        value.lower()
        .replace("/", "-")
        .replace(":", "-")
        .replace("_", "-")
        .replace(" ", "-")
    )


def _group_id(row: dict[str, Any]) -> str:
    return str(row.get("strategy_group_id") or "").strip()


def _side(group: dict[str, Any]) -> str:
    rule = group.get("signal_ready_rule")
    if isinstance(rule, dict):
        side = str(rule.get("side") or "").strip().lower()
        if side in {"long", "short"}:
            return side
    for item in group.get("supported_sides") or []:
        side = str(item).strip().lower()
        if side in {"long", "short"}:
            return side
    return "long"


def _decimal_from(value: Any, default: str) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


def _readiness_by_group(readiness_artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("strategy_group_id")): item
        for item in readiness_artifact.get("readiness") or []
        if isinstance(item, dict) and item.get("strategy_group_id")
    }


def _candidate_pool_symbols(candidate_pool: dict[str, Any]) -> dict[str, list[str]]:
    if not candidate_pool:
        return {}
    if candidate_pool.get("status") != "strategy_live_candidate_pool_ready":
        return {}
    universe = candidate_pool.get("candidate_universe")
    if not isinstance(universe, dict):
        return {}
    result: dict[str, list[str]] = {}
    for group_id, symbols in universe.items():
        strategy_group_id = str(group_id or "").strip()
        if not strategy_group_id or not isinstance(symbols, list):
            continue
        selected: list[str] = []
        for symbol in symbols:
            exchange_symbol = _exchange_symbol(symbol)
            if not exchange_symbol.endswith("USDT"):
                continue
            if exchange_symbol not in selected:
                selected.append(exchange_symbol)
        if selected:
            result[strategy_group_id] = selected
    return result


def _candidate_pool_lanes_by_group(
    candidate_pool: dict[str, Any],
) -> dict[str, dict[str, list[str]]]:
    if not candidate_pool:
        return {}
    if candidate_pool.get("status") != "strategy_live_candidate_pool_ready":
        return {}
    lane_universe = candidate_pool.get("candidate_lane_universe")
    result: dict[str, dict[str, list[str]]] = {}
    if isinstance(lane_universe, dict):
        for group_id, lanes in lane_universe.items():
            strategy_group_id = str(group_id or "").strip()
            if not strategy_group_id or not isinstance(lanes, list):
                continue
            for lane in lanes:
                if isinstance(lane, str) and ":" in lane:
                    symbol, side = lane.rsplit(":", 1)
                elif isinstance(lane, dict):
                    symbol = str(lane.get("symbol") or "")
                    side = str(lane.get("side") or "")
                else:
                    continue
                exchange_symbol = _exchange_symbol(symbol)
                side = side.strip().lower()
                if not exchange_symbol.endswith("USDT") or side not in {"long", "short"}:
                    continue
                bucket = result.setdefault(strategy_group_id, {})
                bucket.setdefault(side, [])
                if exchange_symbol not in bucket[side]:
                    bucket[side].append(exchange_symbol)
    if result:
        return result

    symbols_by_group = _candidate_pool_symbols(candidate_pool)
    side_by_group = _candidate_pool_side_by_group(candidate_pool)
    for strategy_group_id, symbols in symbols_by_group.items():
        side = side_by_group.get(strategy_group_id)
        if side in {"long", "short"}:
            result[strategy_group_id] = {side: symbols}
    return result


def _candidate_pool_side_by_group(candidate_pool: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in candidate_pool.get("symbol_readiness_rows") or []:
        if not isinstance(row, dict):
            continue
        group_id = str(row.get("strategy_group_id") or "").strip()
        side = str(row.get("side") or "").strip().lower()
        if group_id and side in {"long", "short"} and group_id not in result:
            result[group_id] = side
    for row in candidate_pool.get("candidate_rows") or []:
        if not isinstance(row, dict):
            continue
        group_id = str(row.get("strategy_group_id") or "").strip()
        side = str(row.get("side") or "").strip().lower()
        if group_id and side in {"long", "short"} and group_id not in result:
            result[group_id] = side
    return result


def _candidate_pool_rank_by_group(candidate_pool: dict[str, Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in candidate_pool.get("candidate_rows") or []:
        if not isinstance(row, dict):
            continue
        group_id = str(row.get("strategy_group_id") or "").strip()
        if not group_id:
            continue
        try:
            result[group_id] = int(row.get("daily_rank"))
        except Exception:
            continue
    return result


def _groups_from_candidate_pool(
    *,
    intake_artifact: dict[str, Any],
    candidate_pool: dict[str, Any],
) -> list[dict[str, Any]]:
    lanes_by_group = _candidate_pool_lanes_by_group(candidate_pool)
    if not lanes_by_group:
        return [
            item
            for item in intake_artifact.get("strategy_picker") or []
            if isinstance(item, dict)
        ]
    base_by_group = {
        _group_id(item): item
        for item in intake_artifact.get("strategy_picker") or []
        if isinstance(item, dict) and _group_id(item)
    }
    rank_by_group = _candidate_pool_rank_by_group(candidate_pool)
    groups: list[dict[str, Any]] = []
    for strategy_group_id, lanes_by_side in lanes_by_group.items():
        base = dict(base_by_group.get(strategy_group_id) or {})
        base_side = _side(base) if base else ""
        for side, symbols in sorted(lanes_by_side.items()):
            side = side or base_side or "long"
            picker = dict(base.get("picker") or {})
            picker["rank"] = rank_by_group.get(strategy_group_id, picker.get("rank", 999))
            picker["default_mode"] = picker.get("default_mode") or "armed_observation"
            risk_defaults = (
                base.get("risk_defaults")
                if isinstance(base.get("risk_defaults"), dict)
                else {}
            )
            risk_defaults_by_lane = (
                base.get("risk_defaults_by_lane")
                if isinstance(base.get("risk_defaults_by_lane"), dict)
                else {}
            )
            groups.append(
                {
                    **base,
                    "strategy_group_id": strategy_group_id,
                    "name": base.get("name") or f"{strategy_group_id} Candidate Pool",
                    "intake_status": base.get("intake_status")
                    or "armed_observation_intake_ready",
                    "supported_symbols": symbols,
                    "supported_sides": [side],
                    "signal_ready_rule": {
                        **(
                            base.get("signal_ready_rule")
                            if isinstance(base.get("signal_ready_rule"), dict)
                            else {}
                        ),
                        "side": side,
                    },
                    "risk_defaults": {
                        "max_notional_per_action_usdt": str(
                            risk_defaults.get("max_notional_per_action_usdt")
                            or risk_defaults.get("max_notional_usdt")
                            or "8"
                        ),
                        "max_leverage": str(risk_defaults.get("max_leverage") or "1"),
                        **risk_defaults,
                    },
                    "risk_defaults_by_lane": risk_defaults_by_lane,
                    "picker": picker,
                    "candidate_universe_source": "strategy_live_candidate_pool",
                }
            )
    return groups


def _active_key(runtime: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(runtime.get("strategy_family_id") or runtime.get("family") or ""),
        _exchange_symbol(runtime.get("symbol")),
        str(runtime.get("side") or "").lower(),
    )


def _active_groups(active_runtimes: list[dict[str, Any]]) -> set[str]:
    return {
        str(runtime.get("strategy_family_id") or runtime.get("family") or "")
        for runtime in active_runtimes
        if runtime.get("strategy_family_id") or runtime.get("family")
    }


def _active_runtime_id(runtime: dict[str, Any]) -> str | None:
    value = runtime.get("runtime_instance_id") or runtime.get("runtime_id")
    return str(value) if value else None


def _runtime_attempts_remaining(runtime: dict[str, Any]) -> int | None:
    candidates: list[Any] = [
        runtime.get("attempts_remaining"),
        runtime.get("daily_attempts_remaining"),
        runtime.get("runtime_attempts_remaining"),
    ]
    for key in ("boundary", "runtime_boundary", "fact_coverage"):
        nested = runtime.get(key)
        if isinstance(nested, dict):
            candidates.extend(
                [
                    nested.get("attempts_remaining"),
                    nested.get("daily_attempts_remaining"),
                    nested.get("runtime_attempts_remaining"),
                ]
            )
            budget = nested.get("budget")
            if isinstance(budget, dict):
                candidates.extend(
                    [
                        budget.get("attempts_remaining"),
                        budget.get("daily_attempts_remaining"),
                    ]
                )
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            return int(Decimal(str(candidate)))
        except Exception:
            continue
    return None


def _runtime_blocker_text(runtime: dict[str, Any]) -> str:
    fragments: list[str] = []
    for key in (
        "blocker",
        "blocker_class",
        "blocked_reason",
        "status_reason",
        "next_attempt_gate",
    ):
        value = runtime.get(key)
        if isinstance(value, dict):
            fragments.extend(str(item) for item in value.values())
        elif value is not None:
            fragments.append(str(value))
    for key in ("blockers", "gate_blockers", "runtime_blockers"):
        values = runtime.get(key)
        if isinstance(values, list):
            fragments.extend(str(item) for item in values)
    return " ".join(fragments).lower()


def _runtime_attempts_exhausted(runtime: dict[str, Any]) -> bool:
    attempts_remaining = _runtime_attempts_remaining(runtime)
    if attempts_remaining is not None:
        return attempts_remaining <= 0
    blocker_text = _runtime_blocker_text(runtime)
    return (
        "runtime_attempts_exhausted" in blocker_text
        or "attempts_exhausted" in blocker_text
        or "no_attempts_remaining" in blocker_text
    )


def _is_bootstrappable_group(
    group: dict[str, Any],
    *,
    include_observe_only: bool,
    selected_ids: set[str],
) -> tuple[bool, str]:
    strategy_group_id = _group_id(group)
    if selected_ids and strategy_group_id not in selected_ids:
        return False, "not_selected"
    picker = group.get("picker") if isinstance(group.get("picker"), dict) else {}
    default_mode = str(picker.get("default_mode") or "").strip()
    intake_status = str(group.get("intake_status") or "").strip()
    if include_observe_only:
        return True, "selected"
    if (
        intake_status in BOOTSTRAPPABLE_INTAKE_STATUSES
        or default_mode in BOOTSTRAPPABLE_DEFAULT_MODES
    ):
        return True, "selected"
    return False, f"mode_not_bootstrappable:{default_mode or intake_status or 'unknown'}"


def _ready_symbols(
    *,
    group: dict[str, Any],
    readiness: dict[str, Any] | None,
) -> list[str]:
    if readiness:
        exchange_rules = readiness.get("exchange_rules")
        if isinstance(exchange_rules, dict):
            symbols = [
                _exchange_symbol(item)
                for item in exchange_rules.get("ready_symbols") or []
            ]
            if symbols:
                return [item for item in symbols if item]
    return [_exchange_symbol(item) for item in group.get("supported_symbols") or [] if item]


def _bootstrap_config(
    *,
    config: RuntimePilotBootstrapConfig,
    group: dict[str, Any],
    symbol: str,
    side: str,
    renewal_suffix: str | None = None,
) -> BootstrapConfig:
    strategy_group_id = _group_id(group)
    risk_defaults_by_lane = (
        group.get("risk_defaults_by_lane")
        if isinstance(group.get("risk_defaults_by_lane"), dict)
        else {}
    )
    lane_risk_defaults = risk_defaults_by_lane.get(
        f"{_exchange_symbol(symbol)}:{side}",
        {},
    )
    risk_defaults = (
        lane_risk_defaults
        if isinstance(lane_risk_defaults, dict) and lane_risk_defaults
        else (
            group.get("risk_defaults")
            if isinstance(group.get("risk_defaults"), dict)
            else {}
        )
    )
    max_notional = _decimal_from(
        risk_defaults.get("max_notional_per_action_usdt")
        or risk_defaults.get("max_notional_usdt"),
        "8",
    )
    max_leverage = int(_decimal_from(risk_defaults.get("max_leverage"), "1"))
    supported_symbols = [
        _runtime_symbol(item)
        for item in group.get("supported_symbols") or []
        if _runtime_symbol(item)
    ]
    runtime_symbol = _runtime_symbol(symbol)
    runtime_carrier_id = (
        f"strategygroup-runtime-pilot:{strategy_group_id}:"
        f"{_safe_id(runtime_symbol)}:{side}"
    )
    if renewal_suffix:
        runtime_carrier_id = (
            f"{runtime_carrier_id}:renewal:{_safe_id(renewal_suffix)}"
        )
    reason = (
        "Owner standing-authorized StrategyGroup runtime pilot bootstrap; "
        "creates observation runtime only, not order authority."
    )
    if renewal_suffix:
        reason = (
            "Owner standing-authorized StrategyGroup runtime attempt renewal; "
            "creates a new observation runtime admission for an exhausted prior "
            "runtime, not order authority."
        )
    return BootstrapConfig(
        api_base=config.api_base,
        mode="bootstrap",
        strategy_family_id=strategy_group_id,
        strategy_family_version_id=f"{strategy_group_id}-v0",
        family_key=f"{strategy_group_id.lower()}-strategygroup-pilot",
        family_name=str(group.get("name") or strategy_group_id),
        symbol=runtime_symbol,
        supported_symbols=supported_symbols,
        side=side,
        capital_base=Decimal("30"),
        max_loss_budget=Decimal("9"),
        max_notional=max_notional,
        max_leverage=max_leverage,
        max_attempts=3,
        playbook_id=config.playbook_id,
        account_facts_source=config.account_facts_source,
        owner_operator_id=config.owner_operator_id,
        runtime_carrier_id=runtime_carrier_id,
        reason=reason,
    )


def _target_row(
    *,
    group: dict[str, Any],
    symbol: str,
    side: str,
    readiness: dict[str, Any] | None,
    status: str,
    reason: str,
    runtime_instance_id: str | None = None,
    renewal_of_runtime_instance_id: str | None = None,
) -> dict[str, Any]:
    strategy_group_id = _group_id(group)
    picker = group.get("picker") if isinstance(group.get("picker"), dict) else {}
    return {
        "strategy_group_id": strategy_group_id,
        "strategy_family_version_id": f"{strategy_group_id}-v0",
        "symbol": _runtime_symbol(symbol),
        "exchange_symbol": _exchange_symbol(symbol),
        "side": side,
        "picker_rank": picker.get("rank"),
        "default_mode": picker.get("default_mode"),
        "readiness_status": (
            readiness.get("readiness_status") if isinstance(readiness, dict) else None
        ),
        "status": status,
        "reason": reason,
        "runtime_instance_id": runtime_instance_id,
        "renewal_of_runtime_instance_id": renewal_of_runtime_instance_id,
    }


def build_artifact(
    *,
    config: RuntimePilotBootstrapConfig,
    intake_artifact: dict[str, Any],
    live_facts_readiness: dict[str, Any],
    active_runtimes: list[dict[str, Any]],
    active_inventory_blockers: list[str] | None = None,
    active_inventory_counts: dict[str, Any] | None = None,
    client: Any | None = None,
    candidate_pool: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at_ms = int(time.time() * 1000)
    selected_ids = {item.strip() for item in config.strategy_group_ids if item.strip()}
    readiness_map = _readiness_by_group(live_facts_readiness)
    active_key_map: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for runtime in active_runtimes:
        active_key_map.setdefault(_active_key(runtime), []).append(runtime)
    active_keys = set(active_key_map)
    active_group_ids = _active_groups(active_runtimes)
    blockers = list(active_inventory_blockers or [])
    targets: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    executions: list[dict[str, Any]] = []
    new_runtime_ids: list[str] = []
    total_new = 0

    groups = _groups_from_candidate_pool(
        intake_artifact=intake_artifact,
        candidate_pool=candidate_pool or {},
    )
    candidate_pool_symbols = _candidate_pool_symbols(candidate_pool or {})
    candidate_pool_lanes = _candidate_pool_lanes_by_group(candidate_pool or {})
    groups.sort(
        key=lambda item: (
            (item.get("picker") or {}).get("rank", 999),
            str(item.get("strategy_group_id") or ""),
        )
    )
    for group in groups:
        strategy_group_id = _group_id(group)
        selected, selected_reason = _is_bootstrappable_group(
            group,
            include_observe_only=config.include_observe_only,
            selected_ids=selected_ids,
        )
        side = _side(group)
        readiness = readiness_map.get(strategy_group_id)
        if not selected:
            skipped.append(
                _target_row(
                    group=group,
                    symbol=(group.get("supported_symbols") or [""])[0],
                    side=side,
                    readiness=readiness,
                    status="skipped",
                    reason=selected_reason,
                )
            )
            continue
        if not readiness or not bool(readiness.get("observe_ready")):
            skipped.append(
                _target_row(
                    group=group,
                    symbol=(group.get("supported_symbols") or [""])[0],
                    side=side,
                    readiness=readiness,
                    status="blocked",
                    reason="strategy_group_observe_readiness_not_ready",
                )
            )
            continue
        active_group_runtimes = [
            runtime
            for runtime in active_runtimes
            if str(runtime.get("strategy_family_id") or runtime.get("family") or "")
            == strategy_group_id
        ]
        group_has_exhausted_runtime = any(
            _runtime_attempts_exhausted(runtime) for runtime in active_group_runtimes
        )
        if (
            strategy_group_id in active_group_ids
            and not selected_ids
            and not (
                config.renew_exhausted_runtimes and group_has_exhausted_runtime
            )
            and not candidate_pool_symbols
        ):
            skipped.append(
                _target_row(
                    group=group,
                    symbol=(group.get("supported_symbols") or [""])[0],
                    side=side,
                    readiness=readiness,
                    status="skipped",
                    reason="strategy_group_already_has_active_runtime",
                )
            )
            continue
        selected_symbols = _ready_symbols(group=group, readiness=readiness)[
            : max(config.max_symbols_per_group, 0)
        ]
        if not selected_symbols:
            skipped.append(
                _target_row(
                    group=group,
                    symbol=(group.get("supported_symbols") or [""])[0],
                    side=side,
                    readiness=readiness,
                    status="blocked",
                    reason="no_exchange_ready_symbols",
                )
            )
            continue
        for symbol in selected_symbols:
            key = (strategy_group_id, _exchange_symbol(symbol), side)
            matching_active = active_key_map.get(key, [])
            exhausted_runtime = next(
                (
                    runtime
                    for runtime in matching_active
                    if _runtime_attempts_exhausted(runtime)
                ),
                None,
            )
            if key in active_keys and not (
                config.renew_exhausted_runtimes and exhausted_runtime is not None
            ):
                skipped.append(
                    _target_row(
                        group=group,
                        symbol=symbol,
                        side=side,
                        readiness=readiness,
                        status="skipped",
                        reason="runtime_already_active_for_group_symbol_side",
                    )
                )
                continue
            renewal_runtime_id = (
                _active_runtime_id(exhausted_runtime)
                if exhausted_runtime is not None
                else None
            )
            if total_new >= config.max_total_new_runtimes:
                skipped.append(
                    _target_row(
                        group=group,
                        symbol=symbol,
                        side=side,
                        readiness=readiness,
                        status="skipped",
                        reason="max_total_new_runtimes_reached",
                    )
                )
                continue
            row = _target_row(
                group=group,
                symbol=symbol,
                side=side,
                readiness=readiness,
                status="planned",
                reason=(
                    "runtime_attempts_exhausted_renewal_ready_for_runtime_bootstrap"
                    if renewal_runtime_id
                    else "ready_for_runtime_bootstrap"
                ),
                renewal_of_runtime_instance_id=renewal_runtime_id,
            )
            targets.append(row)
            total_new += 1

    if config.execute and blockers:
        status = "blocked_active_runtime_inventory_unavailable"
    elif not targets and not blockers:
        status = "noop_runtime_bootstrap_not_needed"
    elif not config.execute:
        status = "planned_runtime_bootstrap"
    else:
        api_client = client or UrlLibApiClient(api_base=config.api_base)
        for target in targets:
            group = next(
                item for item in groups
                if _group_id(item) == target["strategy_group_id"]
            )
            flow = RuntimeLiveBootstrapApiFlow(
                client=api_client,
                config=_bootstrap_config(
                    config=config,
                    group=group,
                    symbol=target["exchange_symbol"],
                    side=target["side"],
                    renewal_suffix=(
                        (
                            config.renewal_batch_id
                            or f"{generated_at_ms}"
                        )
                        if target.get("renewal_of_runtime_instance_id")
                        else None
                    ),
                ),
            )
            report = flow.run()
            execution = {
                "target": target,
                "report": report,
                "blockers": list(report.get("blockers") or []),
                "ready_for_shadow_candidate_planning": bool(
                    report.get("ready_for_shadow_candidate_planning")
                ),
                "runtime_instance_id": (report.get("ids") or {}).get(
                    "runtime_instance_id"
                ),
                "runtime_status": (report.get("ids") or {}).get("runtime_status"),
                "safety": report.get("safety") or {},
            }
            executions.append(execution)
            if execution["runtime_instance_id"]:
                new_runtime_ids.append(str(execution["runtime_instance_id"]))
        execution_blockers = [
            f"{item['target']['strategy_group_id']}:{blocker}"
            for item in executions
            for blocker in item["blockers"]
        ]
        blockers.extend(execution_blockers)
        status = "executed_runtime_bootstrap" if not blockers else "blocked_runtime_bootstrap"

    selected_runtime_instance_ids = [
        str(runtime.get("runtime_instance_id") or runtime.get("runtime_id"))
        for runtime in active_runtimes
        if runtime.get("runtime_instance_id") or runtime.get("runtime_id")
    ] + new_runtime_ids
    return {
        "scope": "strategygroup_runtime_pilot_bootstrap",
        "status": status,
        "generated_at_ms": generated_at_ms,
        "mode": "execute" if config.execute else "plan",
        "standing_authorization_reference": (
            "OWNER_STANDING_AUTHORIZATION_STRATEGYGROUP_RUNTIME_PILOT_DEV_STAGE"
        ),
        "counts": {
            "strategy_groups_in_intake": len(groups),
            "active_runtime_rows_seen": len(active_runtimes),
            "active_runtime_count_reported": (
                (active_inventory_counts or {}).get("active_runtime_count")
            ),
            "monitored_runtime_count_reported": (
                (active_inventory_counts or {}).get("monitored_runtime_count")
            ),
            "targets": len(targets),
            "skipped": len(skipped),
            "executions": len(executions),
            "new_runtime_ids": len(new_runtime_ids),
        },
        "targets": targets,
        "skipped": skipped,
        "executions": executions,
        "runtime_scope": {
            "selected_runtime_instance_ids": selected_runtime_instance_ids,
            "new_runtime_instance_ids": new_runtime_ids,
            "watcher_scope_update_needed": bool(new_runtime_ids),
            "candidate_universe_source": (
                config.candidate_universe_source
                if candidate_pool_symbols
                else None
            ),
            "candidate_universe_strategy_groups": sorted(candidate_pool_symbols),
            "candidate_universe_symbol_count": sum(
                len(symbols) for symbols in candidate_pool_symbols.values()
            ),
            "candidate_universe_lane_count": sum(
                len(symbols)
                for lanes_by_side in candidate_pool_lanes.values()
                for symbols in lanes_by_side.values()
            ),
            "watcher_scope_note": (
                "The default systemd watcher monitors all ACTIVE runtimes when "
                "no --runtime-instance-id filter is present; server env/drop-in "
                "must be inspected if selected runtime count stays lower."
            ),
        },
        "operator_path": {
            "next_step": _next_step(status, bool(new_runtime_ids)),
            "can_start_or_continue_watcher_observation": (
                status in {
                    "planned_runtime_bootstrap",
                    "executed_runtime_bootstrap",
                    "noop_runtime_bootstrap_not_needed",
                }
            ),
            "requires_fresh_strategy_signal_before_candidate": True,
            "requires_action_time_final_gate_before_submit": True,
            "requires_official_operation_layer": True,
        },
        "safety_invariants": {
            "official_api_surfaces_only": True,
            "plan_only": not config.execute,
            "creates_runtime_records": bool(new_runtime_ids),
            "mutates_pg_only_for_runtime_admission": bool(executions),
            "creates_candidate": False,
            "creates_execution_intent": False,
            "creates_order": False,
            "calls_exchange_submit": False,
            "withdrawal_or_transfer_created": False,
            "forbidden_effects": {
                name: False for name in sorted(FORBIDDEN_EFFECT_FLAGS)
            },
        },
        "blockers": sorted(set(blockers)),
    }


def _next_step(status: str, new_runtime_created: bool) -> str:
    if status == "executed_runtime_bootstrap" and new_runtime_created:
        return "restart_or_wait_for_runtime_signal_watcher_tick"
    if status == "planned_runtime_bootstrap":
        return "execute_strategygroup_runtime_bootstrap_under_standing_authorization"
    if status == "noop_runtime_bootstrap_not_needed":
        return "continue_watcher_observation"
    if status == "blocked_active_runtime_inventory_unavailable":
        return "restore_trading_console_api_or_operator_session"
    return "resolve_strategygroup_runtime_bootstrap_blockers"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default=os.environ.get("RUNTIME_LIVE_BOOTSTRAP_API_BASE", DEFAULT_API_BASE))
    parser.add_argument("--env-file")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("PG_DATABASE_URL", ""),
        help="PG runtime control-state DSN for production bootstrap source.",
    )
    parser.add_argument("--require-database-url", action="store_true")
    parser.add_argument("--allow-non-postgres-for-test", action="store_true")
    parser.add_argument("--strategy-group-id", action="append", default=[])
    parser.add_argument("--include-observe-only", action="store_true")
    parser.add_argument("--max-symbols-per-group", type=int, default=DEFAULT_MAX_SYMBOLS_PER_GROUP)
    parser.add_argument("--max-total-new-runtimes", type=int, default=DEFAULT_MAX_TOTAL_NEW_RUNTIMES)
    parser.add_argument(
        "--account-facts-source",
        choices=["binance_readonly", "static"],
        default="binance_readonly",
    )
    parser.add_argument("--owner-operator-id", default="owner-standing-authorization")
    parser.add_argument("--playbook-id", default=DEFAULT_PLAYBOOK_ID)
    parser.add_argument("--renew-exhausted-runtimes", action="store_true")
    parser.add_argument("--renewal-batch-id")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        _load_env_file(args.env_file)
        intake, live_facts_readiness, candidate_pool, candidate_universe_source = (
            _load_bootstrap_inputs(args)
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2
    client = UrlLibApiClient(api_base=args.api_base)
    active_runtimes, active_blockers = _list_active_runtimes(client)
    active_counts = {
        "active_runtime_count": len(active_runtimes),
        "monitored_runtime_count": None,
    }
    artifact = build_artifact(
        config=RuntimePilotBootstrapConfig(
            api_base=args.api_base,
            execute=args.execute,
            strategy_group_ids=tuple(args.strategy_group_id or []),
            include_observe_only=args.include_observe_only,
            max_symbols_per_group=args.max_symbols_per_group,
            max_total_new_runtimes=args.max_total_new_runtimes,
            account_facts_source=args.account_facts_source,
            owner_operator_id=args.owner_operator_id,
            playbook_id=args.playbook_id,
            output_json=args.output_json,
            renew_exhausted_runtimes=args.renew_exhausted_runtimes,
            renewal_batch_id=args.renewal_batch_id,
            candidate_universe_source=candidate_universe_source,
        ),
        intake_artifact=intake,
        live_facts_readiness=live_facts_readiness,
        active_runtimes=active_runtimes,
        active_inventory_blockers=active_blockers,
        active_inventory_counts=active_counts,
        client=client,
        candidate_pool=candidate_pool,
    )
    _write_json(args.output_json, artifact)
    print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if not artifact["blockers"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
