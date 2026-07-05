#!/usr/bin/env python3
"""Build an operator live-fact projection from read-only runtime facts.

The CLI reads account/action-time safety facts from PG and may read remaining
legacy diagnostic reports as non-authority evidence. It does not call exchange,
create orders, call OrderLifecycle, mutate runtime state, or create withdrawal /
transfer instructions.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

import sqlalchemy as sa


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from runtime_pg_fact_snapshots import read_latest_account_safe_facts_artifact  # noqa: E402


FORBIDDEN_TRUE_KEYS = {
    "attempt_counter_mutated",
    "attempt_counter_mutated_by_script",
    "exchange_called",
    "exchange_called_by_classifier",
    "exchange_order_submitted",
    "exchange_submit_armed",
    "exchange_write_called",
    "exchange_write_called_by_classifier",
    "execute_real_submit",
    "execution_intent_created",
    "local_registration_armed",
    "order_cancelled",
    "order_created",
    "order_lifecycle_called",
    "order_lifecycle_called_by_classifier",
    "order_lifecycle_submit_called",
    "position_closed",
    "position_opened",
    "real_exchange_submit_adapter_executed",
    "runtime_budget_mutated",
    "runtime_budget_mutated_by_script",
    "runtime_state_mutated",
    "runtime_state_mutated_by_classifier",
    "withdrawal_or_transfer_created",
    "withdrawal_or_transfer_created_by_classifier",
}


def _read_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    text = Path(path).expanduser().read_text(encoding="utf-8")
    start = text.find("{")
    if start < 0:
        raise ValueError(f"{path} does not contain a JSON object")
    value = json.loads(text[start:])
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _payload(report: dict[str, Any] | None, *keys: str) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {}
    for key in keys:
        value = report.get(key)
        if isinstance(value, dict):
            return value
    return report


def _path_get(value: Any, *path: str) -> Any:
    current = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _truthy_forbidden_effects(value: Any, prefix: str = "") -> list[str]:
    effects: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            if key == "forbidden_effects":
                if isinstance(item, dict):
                    effects.extend(
                        f"{name}.{effect_key}"
                        for effect_key, enabled in item.items()
                        if bool(enabled)
                    )
                elif isinstance(item, list):
                    effects.extend(f"{name}.{entry}" for entry in item if entry)
                continue
            if key in FORBIDDEN_TRUE_KEYS and bool(item):
                effects.append(name)
            effects.extend(_truthy_forbidden_effects(item, name))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            effects.extend(_truthy_forbidden_effects(item, f"{prefix}[{index}]"))
    return sorted(set(effects))


def _list_values(*values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        if isinstance(value, list):
            result.extend(str(item) for item in value if item is not None)
        elif value:
            result.append(str(value))
    return result


def _account_facts_ready(account_facts: dict[str, Any]) -> bool:
    if not account_facts:
        return False
    checks = account_facts.get("checks")
    if isinstance(checks, dict):
        return (
            checks.get("account_safe_facts_ready") is True
            and checks.get("private_action_time_facts_ready") is True
        )
    return True


def _fact_coverage(
    *,
    runtime_instance_id: str,
    account_facts: dict[str, Any],
    monitor_payload: dict[str, Any],
    finalize_payload: dict[str, Any],
    release_payload: dict[str, Any],
    gate_payload: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    active_count = (
        _int_or_none(monitor_payload.get("local_active_position_count"))
        if monitor_payload
        else None
    )
    exchange_count = _int_or_none(monitor_payload.get("exchange_active_position_count"))
    open_order_count = _int_or_none(monitor_payload.get("local_open_order_count"))
    exchange_stop_count = _int_or_none(
        monitor_payload.get("exchange_open_stop_order_count")
    )
    attempts_remaining = _path_get(
        finalize_payload,
        "next_attempt_gate",
        "attempts_remaining",
    )
    budget_remaining = _path_get(
        finalize_payload,
        "next_attempt_gate",
        "budget_remaining",
    )
    if attempts_remaining is None:
        attempts_remaining = gate_payload.get("attempts_remaining")
    if budget_remaining is None:
        budget_remaining = gate_payload.get("budget_remaining")
    if attempts_remaining is None:
        attempts_remaining = monitor_payload.get("attempts_remaining")
    if budget_remaining is None:
        budget_remaining = monitor_payload.get("budget_remaining")

    return {
        "runtime": {
            "status": "present" if runtime_instance_id else "missing",
            "runtime_instance_id": runtime_instance_id,
        },
        "account": {
            "status": "present" if _account_facts_ready(account_facts) else "missing",
            "source": account_facts.get("source") or account_facts.get("scope"),
            "as_of": (
                account_facts.get("as_of")
                or account_facts.get("timestamp_ms")
                or account_facts.get("generated_at_utc")
            ),
        },
        "position": {
            "status": "present" if monitor_payload else "missing",
            "active_position_present": bool(
                monitor_payload.get("active_position_present")
            ),
            "local_active_position_count": active_count,
            "exchange_active_position_count": exchange_count,
            "symbol": monitor_payload.get("symbol"),
            "side": monitor_payload.get("side"),
        },
        "open_order": {
            "status": "present" if monitor_payload else "missing",
            "local_open_order_count": open_order_count,
            "exchange_open_stop_order_count": exchange_stop_count,
        },
        "protection": {
            "status": "present" if monitor_payload else "missing",
            "protection_status": monitor_payload.get("protection_status"),
            "sl_protection_present": bool(monitor_payload.get("sl_protection_present")),
            "tp_protection_present": bool(monitor_payload.get("tp_protection_present")),
            "hard_stop_boundary_present": bool(
                monitor_payload.get("hard_stop_boundary_present")
            ),
        },
        "budget": {
            "status": "present"
            if attempts_remaining is not None or budget_remaining is not None
            else "missing",
            "attempts_remaining": attempts_remaining,
            "budget_remaining": budget_remaining,
            "budget_reserved": gate_payload.get("budget_reserved")
            or monitor_payload.get("budget_reserved"),
        },
        "next_attempt_gate": {
            "status": "present"
            if finalize_payload or release_payload or gate_payload
            else "missing",
            "finalize_gate_status": _path_get(
                finalize_payload, "next_attempt_gate", "status"
            ),
            "release_status": release_payload.get("status"),
            "gate_classification_status": gate_payload.get("status"),
        },
    }


def _missing_coverage(coverage: dict[str, dict[str, Any]]) -> list[str]:
    return [
        key
        for key, value in coverage.items()
        if value.get("status") in {"missing", "unknown"}
    ]


def _next_attempt_status(
    *,
    coverage: dict[str, dict[str, Any]],
    release_payload: dict[str, Any],
    gate_payload: dict[str, Any],
    finalize_payload: dict[str, Any],
    blockers: list[str],
    missing: list[str],
    forbidden_effects: list[str],
) -> str:
    if forbidden_effects:
        return "blocked_forbidden_effect"
    if missing:
        return "incomplete_live_fact_evidence"

    gate_status = str(gate_payload.get("status") or "")
    release_status = str(release_payload.get("status") or "")
    finalize_gate_status = str(_path_get(finalize_payload, "next_attempt_gate", "status") or "")

    if gate_status == "gate_blocked_by_active_position_slot":
        return "waiting_for_position_resolution"
    if release_status == "waiting_for_position_resolution":
        return "waiting_for_position_resolution"
    has_active_position = bool(
        coverage.get("position", {}).get("active_position_present")
    )
    active_slot_blocker = any(
        str(blocker).endswith("runtime_max_active_positions_in_use")
        or str(blocker).endswith("next_attempt_gate_blocked")
        for blocker in blockers
    )
    if has_active_position and active_slot_blocker:
        return "waiting_for_position_resolution"
    if release_status == "ready_for_strategy_signal":
        return "ready_for_strategy_signal"
    if gate_status == "gate_blocker_classification_no_next_attempt_gate_blocker":
        return "ready_for_strategy_signal"
    if finalize_gate_status in {"ready_for_fresh_signal", "ready_for_next_attempt"}:
        return "ready_for_strategy_signal"
    if gate_status or release_status or finalize_gate_status:
        return "blocked"
    return "operator_review"


def build_operator_live_fact_evidence(
    *,
    runtime_instance_id: str,
    account_facts: dict[str, Any] | None = None,
    account_facts_source_mode: str = "provided",
    live_position_monitor: dict[str, Any] | None = None,
    post_submit_finalize: dict[str, Any] | None = None,
    active_position_resolution: dict[str, Any] | None = None,
    next_attempt_release: dict[str, Any] | None = None,
    next_attempt_gate_classification: dict[str, Any] | None = None,
    observation_operator: dict[str, Any] | None = None,
    deployed_head: str | None = None,
    release_name: str | None = None,
    remote_report_path: str | None = None,
    generated_at_ms: int | None = None,
) -> dict[str, Any]:
    monitor_payload = _payload(live_position_monitor, "artifact")
    finalize_payload = _payload(post_submit_finalize, "post_submit_finalize_payload")
    resolution_payload = _payload(active_position_resolution, "artifact")
    release_payload = _payload(next_attempt_release, "release_evidence")
    gate_payload = _payload(next_attempt_gate_classification)
    observation_payload = _payload(observation_operator)
    account_payload = _payload(account_facts)

    coverage = _fact_coverage(
        runtime_instance_id=runtime_instance_id,
        account_facts=account_payload,
        monitor_payload=monitor_payload,
        finalize_payload=finalize_payload,
        release_payload=release_payload,
        gate_payload=gate_payload,
    )
    missing = _missing_coverage(coverage)
    forbidden_effects = _truthy_forbidden_effects(
        {
            "account_facts": account_facts or {},
            "live_position_monitor": live_position_monitor or {},
            "post_submit_finalize": post_submit_finalize or {},
            "active_position_resolution": active_position_resolution or {},
            "next_attempt_release": next_attempt_release or {},
            "next_attempt_gate_classification": next_attempt_gate_classification or {},
            "observation_operator": observation_operator or {},
        }
    )
    blockers = []
    if missing:
        blockers.extend(f"{item}_facts_missing" for item in missing)
    blockers.extend(
        _list_values(
            account_payload.get("blockers"),
            live_position_monitor.get("blockers") if live_position_monitor else [],
            post_submit_finalize.get("blockers") if post_submit_finalize else [],
            active_position_resolution.get("blockers") if active_position_resolution else [],
            next_attempt_release.get("blockers") if next_attempt_release else [],
            next_attempt_gate_classification.get("blockers")
            if next_attempt_gate_classification
            else [],
            observation_operator.get("blockers") if observation_operator else [],
        )
    )
    status = _next_attempt_status(
        coverage=coverage,
        release_payload=release_payload,
        gate_payload=gate_payload,
        finalize_payload=finalize_payload,
        blockers=blockers,
        missing=missing,
        forbidden_effects=forbidden_effects,
    )
    warnings = _list_values(
        live_position_monitor.get("warnings") if live_position_monitor else [],
        post_submit_finalize.get("warnings") if post_submit_finalize else [],
        active_position_resolution.get("warnings") if active_position_resolution else [],
        next_attempt_release.get("warnings") if next_attempt_release else [],
        next_attempt_gate_classification.get("warnings")
        if next_attempt_gate_classification
        else [],
        observation_operator.get("warnings") if observation_operator else [],
    )
    return {
        "scope": "runtime_operator_live_fact_evidence",
        "status": status,
        "runtime_instance_id": runtime_instance_id,
        "generated_at_ms": generated_at_ms if generated_at_ms is not None else int(time.time() * 1000),
        "deployment_context": {
            "deployed_head": deployed_head,
            "release_name": release_name,
            "remote_report_path": remote_report_path,
        },
        "fact_coverage": coverage,
        "missing_required_fact_groups": missing,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "next_attempt_gate_state": {
            "status": status,
            "finalize_gate_status": coverage["next_attempt_gate"].get(
                "finalize_gate_status"
            ),
            "release_status": coverage["next_attempt_gate"].get("release_status"),
            "gate_classification_status": coverage["next_attempt_gate"].get(
                "gate_classification_status"
            ),
            "requires_fresh_strategy_signal": True,
            "requires_fresh_authorization_before_submit": True,
            "legacy_authorization_replay_allowed": False,
            "executable_submit_allowed_by_evidence": False,
        },
        "active_position_resolution": {
            "status": resolution_payload.get("status"),
            "recommended_review_checkpoint": resolution_payload.get(
                "recommended_review_checkpoint"
            ),
            "can_continue_holding": bool(
                monitor_payload.get("can_continue_holding")
            ),
        },
        "observation_state": {
            "status": observation_payload.get("status"),
            "watch_status": observation_payload.get("watch_status"),
            "diagnostic_status": observation_payload.get("diagnostic_status"),
        },
        "operator_live_fact_plan": {
            "not_executed": True,
            "next_step": _operator_next_step(status),
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "calls_exchange_write": False,
            "requires_owner_close_authorization_now": status
            == "waiting_for_position_resolution"
            and not bool(monitor_payload.get("hard_stop_boundary_present")),
        },
        "safety_invariants": {
            "operator_live_fact_projection_only": True,
            "account_facts_source_mode": account_facts_source_mode,
            "reads_json_reports_only": False,
            "pg_called_by_builder": account_facts_source_mode == "db_backed",
            "exchange_called_by_builder": False,
            "exchange_write_called_by_builder": False,
            "order_lifecycle_called_by_builder": False,
            "runtime_state_mutated_by_builder": False,
            "withdrawal_or_transfer_created_by_builder": False,
            "no_forbidden_live_side_effects": not forbidden_effects,
            "forbidden_effects": forbidden_effects,
        },
    }


def _operator_next_step(status: str) -> str:
    if status == "ready_for_strategy_signal":
        return "start_fresh_strategy_signal_observation"
    if status == "waiting_for_position_resolution":
        return "continue_read_only_position_monitoring_until_flat_or_reviewed"
    if status == "incomplete_live_fact_evidence":
        return "collect_missing_read_only_live_fact_groups"
    if status == "blocked_forbidden_effect":
        return "stop_and_review_forbidden_side_effects"
    if status == "blocked":
        return "resolve_next_attempt_gate_blockers"
    return "operator_review_live_fact_evidence"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a P0-A read-only runtime operator live-fact evidence.",
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--allow-non-postgres-for-test", action="store_true")
    parser.add_argument("--live-position-monitor-json")
    parser.add_argument("--post-submit-finalize-json")
    parser.add_argument("--active-position-resolution-json")
    parser.add_argument("--next-attempt-release-json")
    parser.add_argument("--next-attempt-gate-classification-json")
    parser.add_argument("--observation-operator-json")
    parser.add_argument("--deployed-head")
    parser.add_argument("--release-name")
    parser.add_argument("--remote-report-path")
    parser.add_argument("--generated-at-ms", type=int)
    parser.add_argument("--output-json")
    return parser.parse_args(argv)


def _account_facts_from_pg(
    database_url: str,
    *,
    allow_non_postgres_for_test: bool = False,
) -> dict[str, Any]:
    if not database_url:
        raise RuntimeError(
            "PG_DATABASE_URL is required for DB-backed operator live fact evidence"
        )
    if not database_url.startswith(
        ("postgresql://", "postgresql+psycopg://")
    ) and not allow_non_postgres_for_test:
        raise RuntimeError(
            "DB-backed operator live fact evidence requires PostgreSQL DSN"
        )
    engine = sa.create_engine(database_url)
    try:
        with engine.connect() as conn:
            return read_latest_account_safe_facts_artifact(conn)
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        account_facts = _account_facts_from_pg(
            args.database_url,
            allow_non_postgres_for_test=args.allow_non_postgres_for_test,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2
    evidence = build_operator_live_fact_evidence(
        runtime_instance_id=args.runtime_instance_id,
        account_facts=account_facts,
        account_facts_source_mode="db_backed",
        live_position_monitor=_read_json(args.live_position_monitor_json),
        post_submit_finalize=_read_json(args.post_submit_finalize_json),
        active_position_resolution=_read_json(args.active_position_resolution_json),
        next_attempt_release=_read_json(args.next_attempt_release_json),
        next_attempt_gate_classification=_read_json(
            args.next_attempt_gate_classification_json
        ),
        observation_operator=_read_json(args.observation_operator_json),
        deployed_head=args.deployed_head,
        release_name=args.release_name,
        remote_report_path=args.remote_report_path,
        generated_at_ms=args.generated_at_ms,
    )
    if args.output_json:
        _write_json(args.output_json, evidence)
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if evidence["status"] in {
        "ready_for_strategy_signal",
        "waiting_for_position_resolution",
        "incomplete_live_fact_evidence",
        "blocked",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
