#!/usr/bin/env python3
"""Build StrategyGroup live-facts readiness read model from PG current state.

The artifact separates observe readiness from armed candidate-preparation
readiness. Missing account, open-order, budget, protection, or next-gate facts
must block candidate preparation, but they do not erase the StrategyGroup
candidate scope or authorize any execution.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sqlalchemy as sa

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.application.readmodels.strategy_live_candidate_pool import (
    build_strategy_live_candidate_pool_from_control_state,
)
from src.application.action_time.runtime_pg_fact_snapshots import (
    read_latest_account_safe_facts_artifact,
    read_pretrade_public_facts_artifact,
)
from src.infrastructure.runtime_control_state_repository import (
    PgBackedRuntimeControlStateRepository,
)


PASS_VALUES = {
    "available",
    "available_for_candidate_specific_reservation",
    "clear",
    "flat",
    "fresh",
    "no_active_position",
    "no_open_orders",
    "none",
    "pass",
    "present",
    "ready",
    "ready_for_candidate_specific_plan",
    "trading",
    "valid",
    "waiting_for_fresh_strategy_signal",
    "ready_for_strategy_signal",
}
UNKNOWN_VALUES = {"", "missing", "not_available", "unknown", "unavailable"}
UNSAFE_FLAGS = {
    "exchange_write_called",
    "order_created",
    "order_lifecycle_called",
    "execution_intent_created",
    "runtime_budget_mutated",
    "withdrawal_or_transfer_created",
}


def _status(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("status", "state", "readiness", "value"):
            if value.get(key) is not None:
                return str(value.get(key)).strip().lower()
        return "present"
    if value is None:
        return "missing"
    return str(value).strip().lower()


def _is_pass(value: Any) -> bool:
    return _status(value) in PASS_VALUES


def _is_unknown(value: Any) -> bool:
    return _status(value) in UNKNOWN_VALUES


def _fact(live_facts: dict[str, Any], key: str) -> Any:
    value = live_facts.get(key)
    if value is not None:
        return value
    facts = live_facts.get("facts")
    if isinstance(facts, dict):
        return facts.get(key)
    return None


def _symbols_exchange_ready(
    *,
    group: dict[str, Any],
    live_facts: dict[str, Any],
) -> tuple[bool, list[str], list[str]]:
    symbols = [str(item) for item in group.get("supported_symbols") or []]
    rules = _fact(live_facts, "exchange_rules")
    if not isinstance(rules, dict):
        return False, [], symbols
    symbol_rules = rules.get("symbols") if isinstance(rules.get("symbols"), dict) else rules
    ready: list[str] = []
    blocked: list[str] = []
    for symbol in symbols:
        status = _status(symbol_rules.get(symbol) if isinstance(symbol_rules, dict) else None)
        if status in {"trading", "ready", "available", "pass"}:
            ready.append(symbol)
        else:
            blocked.append(symbol)
    return bool(ready), ready, blocked


def _candidate_fact_checks(live_facts: dict[str, Any]) -> list[dict[str, Any]]:
    checks = [
        ("account", "account", "block_candidate_prepare"),
        ("same_symbol_position_state", "active_position", "block_candidate_prepare"),
        ("open_order_same_symbol_state", "open_orders", "block_candidate_prepare"),
        ("protection_plan_state", "protection", "block_candidate_prepare"),
        ("budget_state", "budget", "block_candidate_prepare"),
        ("next_attempt_gate_state", "next_attempt_gate", "block_candidate_prepare"),
    ]
    rows: list[dict[str, Any]] = []
    for fact_key, live_key, missing_behavior in checks:
        value = _fact(live_facts, live_key)
        rows.append(
            {
                "fact_key": fact_key,
                "live_fact_key": live_key,
                "status": _status(value),
                "ready": _is_pass(value),
                "missing": _is_unknown(value),
                "missing_behavior": missing_behavior,
            }
        )
    return rows


def _group_readiness(
    *,
    group: dict[str, Any],
    live_facts: dict[str, Any],
) -> dict[str, Any]:
    exchange_ready, ready_symbols, blocked_symbols = _symbols_exchange_ready(
        group=group,
        live_facts=live_facts,
    )
    candidate_checks = _candidate_fact_checks(live_facts)
    candidate_blockers = [
        f"{item['live_fact_key']}:{item['status']}"
        for item in candidate_checks
        if not item["ready"]
    ]
    if blocked_symbols:
        if ready_symbols:
            candidate_warnings = [
                "exchange_rules_not_ready_for_some_supported_symbols"
            ]
        else:
            candidate_warnings = []
            candidate_blockers.append(
                "exchange_rules_not_ready_for_any_supported_symbol"
            )
    else:
        candidate_warnings = []
    observe_ready = exchange_ready
    default_mode = str((group.get("picker") or {}).get("default_mode") or "")
    if not observe_ready:
        readiness_status = "blocked_observation_exchange_rules"
    elif default_mode == "observe_only":
        readiness_status = "observe_only_ready_candidate_blocked"
    elif candidate_blockers:
        readiness_status = "observe_ready_armed_candidate_blocked"
    else:
        readiness_status = "armed_observation_live_facts_ready"
    return {
        "strategy_group_id": group.get("strategy_group_id"),
        "default_mode": default_mode,
        "readiness_status": readiness_status,
        "observe_ready": observe_ready,
        "armed_candidate_prepare_ready": (
            readiness_status == "armed_observation_live_facts_ready"
        ),
        "supported_symbol_count": group.get("supported_symbol_count"),
        "exchange_rules": {
            "ready": exchange_ready,
            "ready_symbols": ready_symbols,
            "blocked_symbols": blocked_symbols,
        },
        "candidate_fact_checks": candidate_checks,
        "blockers": candidate_blockers,
        "warnings": [
            *list(group.get("warnings") or []),
            *candidate_warnings,
        ],
    }


def _operator_path(
    *,
    observe_ready_count: int,
    armed_ready_count: int,
    blocked: list[dict[str, Any]],
) -> dict[str, Any]:
    candidate_blocked = bool(blocked)
    if armed_ready_count > 0:
        next_gate = "review_ready_groups_before_fresh_candidate_prepare"
    elif observe_ready_count > 0 and candidate_blocked:
        next_gate = "continue_observation_and_prepare_candidate_prerequisites"
    elif observe_ready_count > 0:
        next_gate = "wait_for_or_generate_fresh_strategy_signal"
    else:
        next_gate = "resolve_live_fact_blockers"
    return {
        "can_continue_observation": observe_ready_count > 0,
        "can_prepare_fresh_candidate": armed_ready_count > 0,
        "next_gate": next_gate,
        "requires_action_time_final_gate_before_submit": True,
        "requires_official_operation_layer": True,
    }


def _owner_state(
    *,
    rows: list[dict[str, Any]],
    observe_ready_count: int,
    armed_ready_count: int,
    blockers: list[str],
) -> dict[str, Any]:
    if not rows:
        return {
            "status": "blocked",
            "blocked_at": "pg_strategy_group_intake",
            "blocked_reason": "no_pg_strategy_group_candidate_scope",
            "next_recover_condition": "pg_current_candidate_scope_projection_exists",
            "non_authority_checkpoint": "publish_pg_current_strategy_group_intake_projection",
            "checkpoint_source": "owner_state",
            "authority_mode": "not_selected",
        }
    if armed_ready_count > 0:
        return {
            "status": "armed_observation_ready",
            "blocked_at": "none",
            "blocked_reason": "none",
            "next_recover_condition": "fresh_strategy_signal_arrives",
            "non_authority_checkpoint": "continue_watcher_observation",
            "checkpoint_source": "owner_state",
            "authority_mode": "none",
        }
    if observe_ready_count > 0:
        return {
            "status": "observe_ready_candidate_prerequisites_missing",
            "blocked_at": "candidate_prepare_facts",
            "blocked_reason": ",".join(blockers) if blockers else "candidate_prerequisites_missing",
            "next_recover_condition": (
                "budget_protection_and_next_attempt_gate_are_ready_before_candidate_prepare"
            ),
            "non_authority_checkpoint": (
                "continue_observation_and_prepare_candidate_prerequisite_facts"
            ),
            "checkpoint_source": "owner_state",
            "authority_mode": "observe_only_until_candidate_prerequisites_ready",
        }
    return {
        "status": "blocked",
        "blocked_at": "live_fact_readiness",
        "blocked_reason": ",".join(blockers) if blockers else "live_facts_not_ready",
        "next_recover_condition": "exchange_account_position_open_order_facts_are_ready",
        "non_authority_checkpoint": "refresh_strategy_group_live_facts_readonly",
        "checkpoint_source": "owner_state",
        "authority_mode": "not_observing",
    }


def build_readiness_artifact(
    *,
    intake_artifact: dict[str, Any],
    live_facts: dict[str, Any],
    generated_at_ms: int | None = None,
) -> dict[str, Any]:
    generated_at_ms = generated_at_ms or int(time.time() * 1000)
    groups = [
        item for item in intake_artifact.get("strategy_picker") or []
        if isinstance(item, dict)
    ]
    rows = [_group_readiness(group=group, live_facts=live_facts) for group in groups]
    blocked = [row for row in rows if row["blockers"]]
    observe_ready_count = sum(1 for row in rows if row["observe_ready"])
    armed_ready_count = sum(1 for row in rows if row["armed_candidate_prepare_ready"])
    if not rows:
        status = "blocked_no_strategy_group_intake"
    elif armed_ready_count:
        status = "strategy_group_live_facts_ready_for_armed_observation"
    elif observe_ready_count:
        status = "strategy_group_observe_ready_candidate_prerequisites_pending"
    else:
        status = "strategy_group_live_facts_blocked"
    candidate_prepare_blockers = sorted(
        {
            f"{row['strategy_group_id']}:{blocker}"
            for row in rows
            for blocker in row.get("blockers") or []
        }
    )
    observation_blockers = sorted(
        {
            f"{row['strategy_group_id']}:{blocker}"
            for row in rows
            if not row.get("observe_ready")
            for blocker in row.get("blockers") or []
        }
    )
    return {
        "scope": "strategy_group_live_facts_readiness",
        "status": status,
        "generated_at_ms": generated_at_ms,
        "source_anchor": intake_artifact.get("source_anchor") or {},
        "counts": {
            "strategy_groups": len(rows),
            "observe_ready": observe_ready_count,
            "armed_candidate_prepare_ready": armed_ready_count,
            "blocked_for_candidate_prepare": len(blocked),
        },
        "readiness": rows,
        "operator_path": _operator_path(
            observe_ready_count=observe_ready_count,
            armed_ready_count=armed_ready_count,
            blocked=blocked,
        ),
        "owner_state": _owner_state(
            rows=rows,
            observe_ready_count=observe_ready_count,
            armed_ready_count=armed_ready_count,
            blockers=candidate_prepare_blockers,
        ),
        "safety_invariants": {
            **{name: False for name in sorted(UNSAFE_FLAGS)},
            "reads_live_facts_only": True,
            "registers_runtime": False,
            "creates_candidate": False,
            "authorizes_execution": False,
            "places_order": False,
            "mutates_pg": False,
        },
        "candidate_prepare_blockers": candidate_prepare_blockers,
        "blockers": observation_blockers,
    }


def build_strategy_group_intake_artifact_from_candidate_pool(
    candidate_pool: dict[str, Any],
    *,
    generated_at_ms: int | None = None,
) -> dict[str, Any]:
    generated_at_ms = generated_at_ms or int(time.time() * 1000)
    rows = [
        row
        for row in candidate_pool.get("symbol_readiness_rows") or []
        if isinstance(row, dict)
    ]
    by_group: dict[str, dict[str, Any]] = {}
    for row in rows:
        strategy_group_id = str(row.get("strategy_group_id") or "")
        symbol = str(row.get("symbol") or "")
        side = str(row.get("side") or "")
        if not strategy_group_id:
            continue
        group = by_group.setdefault(
            strategy_group_id,
            {
                "strategy_group_id": strategy_group_id,
                "version": "pg_current",
                "name": strategy_group_id,
                "source_path": "pg_current_projection:candidate_pool",
                "intake_status": "armed_observation_intake_ready",
                "picker": {
                    "show": True,
                    "rank": len(by_group) + 1,
                    "default_mode": "armed_observation",
                    "badge": "pg_current",
                },
                "supported_symbols": [],
                "supported_symbol_count": 0,
                "supported_sides": [],
                "risk_defaults": {},
                "required_fact_categories": [],
                "required_fact_count": 0,
                "watcher_scope": {
                    "source": "pg_current_projection:candidate_pool",
                    "candidate_scope_closed": True,
                },
                "sample_statuses": {},
                "hard_stop_count": 0,
                "blockers": [],
                "warnings": [],
                "execution_boundary": {
                    "research_intake_source_only": False,
                    "pg_current_projection_source": True,
                    "runtime_registration_authorized": False,
                    "candidate_creation_authorized": False,
                    "final_gate_input": False,
                    "operation_layer_input": False,
                    "real_submit_authorized": False,
                },
            },
        )
        if symbol and symbol not in group["supported_symbols"]:
            group["supported_symbols"].append(symbol)
        if side and side not in group["supported_sides"]:
            group["supported_sides"].append(side)

    strategy_picker = sorted(
        by_group.values(),
        key=lambda item: (int(item["picker"]["rank"]), item["strategy_group_id"]),
    )
    for index, group in enumerate(strategy_picker, start=1):
        group["picker"]["rank"] = index
        group["supported_symbols"] = sorted(group["supported_symbols"])
        group["supported_sides"] = sorted(group["supported_sides"])
        group["supported_symbol_count"] = len(group["supported_symbols"])

    blockers: list[str] = []
    if not strategy_picker:
        blockers.append("pg_current_candidate_scope_missing")
    status = (
        "ready_for_main_control_intake"
        if not blockers
        else "blocked_pg_strategy_intake_source"
    )
    return {
        "scope": "strategy_group_intake_main_control_projection",
        "status": status,
        "generated_at_ms": generated_at_ms,
        "source_anchor": {
            "source_mode": str(candidate_pool.get("source_mode") or "db_backed"),
            "projection_target": str(
                candidate_pool.get("projection_target") or "production_current"
            ),
            "model": "strategy_live_candidate_pool",
            "legacy_file_source": False,
        },
        "counts": {
            "strategy_groups": len(strategy_picker),
            "armed_observation_intake_ready": len(strategy_picker),
            "observe_only_intake_ready": 0,
            "required_fact_rows": 0,
            "candidate_lanes": len(rows),
        },
        "strategy_picker": strategy_picker,
        "required_facts_matrix": [],
        "watcher_scope": [
            {
                "strategy_group_id": group["strategy_group_id"],
                "candidate_symbols": group["supported_symbols"],
                "side_scope": group["supported_sides"],
                "source": "pg_current_projection:candidate_pool",
                "default_mode": group["picker"]["default_mode"],
                "intake_status": group["intake_status"],
            }
            for group in strategy_picker
        ],
        "source_refs": {
            "candidate_pool": "pg_current_projection:strategy_live_candidate_pool",
            "legacy_handoff_json_read": False,
            "legacy_packet_env_read": False,
        },
        "safety_invariants": {
            **{name: False for name in sorted(UNSAFE_FLAGS)},
            "reads_research_intake_source_only": False,
            "reads_pg_current_projection": True,
            "registers_runtime": False,
            "creates_candidate": False,
            "authorizes_execution": False,
            "places_order": False,
            "mutates_pg": False,
        },
        "blockers": blockers,
        "warnings": [],
    }


def build_strategy_group_intake_artifact_from_control_state(
    control_state: dict[str, Any],
    *,
    generated_at_ms: int | None = None,
) -> dict[str, Any]:
    generated_at_utc = datetime.now(timezone.utc).isoformat()
    candidate_pool = build_strategy_live_candidate_pool_from_control_state(
        control_state,
        generated_at_utc=generated_at_utc,
    )
    return build_strategy_group_intake_artifact_from_candidate_pool(
        candidate_pool,
        generated_at_ms=generated_at_ms,
    )


def build_readiness_artifact_from_pg(
    *,
    conn: sa.engine.Connection,
    intake_artifact: dict[str, Any],
    generated_at_ms: int | None = None,
) -> dict[str, Any]:
    live_facts = build_live_facts_from_pg_snapshots(
        conn=conn,
        intake_artifact=intake_artifact,
    )
    artifact = build_readiness_artifact(
        intake_artifact=intake_artifact,
        live_facts=live_facts,
        generated_at_ms=generated_at_ms,
    )
    artifact["live_facts_source"] = live_facts.get("source") or {}
    artifact["live_facts"] = live_facts
    if live_facts.get("source_mode") != "db_backed":
        artifact["blockers"] = sorted(
            set(list(artifact.get("blockers") or []) + ["pg_live_facts_missing"])
        )
        artifact["status"] = "strategy_group_live_facts_blocked"
    return artifact


def build_readiness_artifact_from_database_url(
    *,
    database_url: str,
    intake_artifact: dict[str, Any],
    generated_at_ms: int | None = None,
    allow_non_postgres_for_test: bool = False,
) -> dict[str, Any]:
    if not database_url:
        raise RuntimeError(
            "PG_DATABASE_URL is required for DB-backed live-facts readiness"
        )
    if not database_url.startswith(
        ("postgresql://", "postgresql+psycopg://")
    ) and not allow_non_postgres_for_test:
        raise RuntimeError("DB-backed live-facts readiness requires PostgreSQL DSN")
    engine = sa.create_engine(database_url)
    try:
        with engine.connect() as conn:
            return build_readiness_artifact_from_pg(
                conn=conn,
                intake_artifact=intake_artifact,
                generated_at_ms=generated_at_ms,
            )
    finally:
        engine.dispose()


def build_live_facts_from_pg_snapshots(
    *,
    conn: sa.engine.Connection,
    intake_artifact: dict[str, Any],
) -> dict[str, Any]:
    public = read_pretrade_public_facts_artifact(conn)
    account_safe = read_latest_account_safe_facts_artifact(conn)
    public_rows = {
        str(item.get("symbol") or "").upper(): item
        for item in public.get("symbols") or []
        if isinstance(item, dict)
    }
    supported_symbols = sorted(
        {
            str(symbol or "").upper()
            for group in intake_artifact.get("strategy_picker") or []
            if isinstance(group, dict)
            for symbol in group.get("supported_symbols") or []
            if str(symbol or "").strip()
        }
    )
    exchange_symbols: dict[str, dict[str, Any]] = {}
    for symbol in supported_symbols:
        row = public_rows.get(symbol)
        ready = bool(row) and row.get("public_facts_ready") is True
        exchange_symbols[symbol] = {
            "status": "TRADING" if ready else "missing",
            "fact_snapshot_ready": ready,
            "source_ref": row.get("fact_snapshot_id") if row else None,
        }

    checks = (
        account_safe.get("checks")
        if isinstance(account_safe.get("checks"), dict)
        else {}
    )
    account_ready = checks.get("account_trade_permission") is True
    active_position_clear = checks.get("active_position_clear") is True or checks.get(
        "active_position_or_open_order_clear"
    ) is True
    open_orders_clear = checks.get("open_orders_clear") is True or checks.get(
        "active_position_or_open_order_clear"
    ) is True
    budget_available = checks.get("budget_available") is True or checks.get(
        "action_time_available_balance"
    ) is True
    protection_ready = checks.get("protection_template_ready") is True
    next_attempt_ready = checks.get("next_attempt_gate_ready") is True
    return {
        "scope": "strategy_group_live_facts_input",
        "status": (
            "ready"
            if account_safe.get("status") == "runtime_account_safe_facts_ready"
            and exchange_symbols
            and all(
                item.get("fact_snapshot_ready") is True
                for item in exchange_symbols.values()
            )
            else "partial"
        ),
        "source_mode": "db_backed",
        "source": {
            "mode": "pg_runtime_fact_snapshots",
            "public_facts_status": public.get("status"),
            "account_safe_status": account_safe.get("status"),
            "account_safe_fact_snapshot_id": account_safe.get(
                "account_safe_fact_snapshot_id"
            ),
            "account_mode_snapshot_id": account_safe.get("account_mode_snapshot_id"),
        },
        "exchange_rules": {
            "status": "ready" if exchange_symbols else "missing",
            "symbols": exchange_symbols,
        },
        "account": {
            "status": "fresh" if account_ready else "missing",
            "available_balance_present": checks.get("account_balance_present") is True
            or checks.get("action_time_available_balance") is True,
            "available_balance_positive": checks.get("account_balance_positive") is True
            or checks.get("action_time_available_balance") is True,
            "total_wallet_balance_present": checks.get("total_wallet_balance_present")
            is True
            or checks.get("account_balance_present") is True
            or checks.get("action_time_available_balance") is True,
            "exchange_account_trade_permission": account_ready,
        },
        "active_position": {
            "status": (
                "no_active_position"
                if active_position_clear
                else "active_position_present"
            ),
            "active_count": 0 if active_position_clear else 1,
            "active_symbols": [],
        },
        "open_orders": {
            "status": "no_open_orders" if open_orders_clear else "open_orders_present",
            "open_order_count": 0 if open_orders_clear else 1,
            "open_order_symbols": [],
        },
        "protection": {
            "status": (
                "ready_for_candidate_specific_plan"
                if protection_ready
                else "missing"
            )
        },
        "budget": {
            "status": (
                "available_for_candidate_specific_reservation"
                if budget_available
                else "missing"
            ),
            "reason": (
                "account_available_balance_covers_strategygroup_tiny_notional"
                if budget_available
                else "budget_fact_not_ready"
            ),
            "max_notional_requirement_usdt": checks.get("max_notional_requirement_usdt"),
        },
        "next_attempt_gate": {
            "status": "ready_for_strategy_signal" if next_attempt_ready else "missing"
        },
        "collector_errors": {},
        "safety_invariants": {
            "signed_get_only": checks.get("source_signed_get_only") is True,
            "exchange_write_called": checks.get("source_exchange_write_called") is True,
            "order_created": checks.get("source_order_created") is True,
            "withdrawal_or_transfer_created": False,
        },
    }


def build_blocked_pg_readiness_artifact(
    *,
    intake_artifact: dict[str, Any],
    generated_at_ms: int | None,
    reason: str,
) -> dict[str, Any]:
    artifact = build_readiness_artifact(
        intake_artifact=intake_artifact,
        live_facts={},
        generated_at_ms=generated_at_ms,
    )
    artifact["status"] = "strategy_group_live_facts_blocked"
    artifact["blockers"] = sorted(
        set(list(artifact.get("blockers") or []) + [reason])
    )
    artifact["live_facts_source"] = {
        "mode": "pg_runtime_fact_snapshots",
        "present": False,
        "reason": reason,
    }
    artifact["live_facts"] = {}
    return artifact


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build StrategyGroup live-facts readiness from PG current state.",
    )
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--require-database-url", action="store_true")
    parser.add_argument("--allow-non-postgres-for-test", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.database_url:
        raise RuntimeError("PG_DATABASE_URL is required for live-facts readiness")
    engine = sa.create_engine(args.database_url)
    try:
        with engine.connect() as conn:
            control_state = PgBackedRuntimeControlStateRepository(
                conn
            ).read_control_state()
            intake = build_strategy_group_intake_artifact_from_control_state(
                control_state
            )
            artifact = build_readiness_artifact_from_pg(
                conn=conn,
                intake_artifact=intake,
            )
    finally:
        engine.dispose()
    print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if artifact["operator_path"]["can_continue_observation"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
