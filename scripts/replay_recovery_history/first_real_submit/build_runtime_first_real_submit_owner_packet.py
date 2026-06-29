#!/usr/bin/env python3
"""Build a non-executing Owner packet for the first real runtime submit gate.

This packet aggregates the existing pre-live runtime submit rehearsal into a
compact review surface. It does not authorize, submit, place, register, or
cancel orders; it does not call OrderLifecycle or exchange APIs; and it does
not mutate Tokyo, runtime state, budgets, attempts, or credentials.

Explicit Owner authorization remains required before any real runtime submit or
live-runtime enablement action.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from typing import Any

from pathlib import Path

REPO_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORT))

from scripts.verify_runtime_submit_rehearsal_pre_live_evidence import (
    DEFAULT_DEPLOYED_HEAD,
    OWNER_AUTHORIZATION_FLAG,
    OWNER_LIVE_RUNTIME_ENABLEMENT_FLAG,
    build_pre_live_evidence,
)


OWNER_REAL_SUBMIT_AUTH_MISSING = "owner_real_submit_authorization_missing"
OWNER_LIVE_RUNTIME_AUTH_MISSING = "owner_live_runtime_enablement_authorization_missing"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    packet = asyncio.run(_build_packet_from_args(args))
    if args.json:
        print(json.dumps(packet, indent=2, sort_keys=True))
    else:
        _print_human(packet)
    return 0 if packet["checks"]["packet_ready_for_owner_decision"] else 2


async def _build_packet_from_args(args: argparse.Namespace) -> dict[str, Any]:
    pre_live_evidence = await build_pre_live_evidence(
        deployed_head=args.deployed_head,
        owner_real_submit_authorized=args.owner_real_submit_authorized,
        owner_live_runtime_enablement_authorized=(
            args.owner_live_runtime_enable_authorized
        ),
        require_current_head_deployed=not args.skip_current_head_deployed_check,
        active_positions=args.active_positions,
        exercise_local_registration_pre_exchange=(
            args.exercise_local_registration_pre_exchange
        ),
        exercise_exchange_submit_adapter_pre_execution=(
            args.exercise_exchange_submit_adapter_pre_execution
        ),
        exercise_in_memory_exchange_execution_simulation=(
            args.exercise_in_memory_exchange_execution_simulation
        ),
    )
    return build_first_real_submit_owner_packet(pre_live_evidence=pre_live_evidence)


def build_first_real_submit_owner_packet(
    *,
    pre_live_evidence: dict[str, Any] | None = None,
    pre_live_packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize first-real-submit readiness without granting authority."""

    pre_live_payload = pre_live_evidence if pre_live_evidence is not None else pre_live_packet
    if pre_live_payload is None:
        raise ValueError("pre_live_evidence.checks must be present")
    pre_live_packet = pre_live_payload
    checks = pre_live_packet.get("checks")
    if not isinstance(checks, dict):
        raise ValueError("pre_live_evidence.checks must be present")
    owner_gate = (
        pre_live_packet.get("owner_gate")
        if isinstance(pre_live_packet.get("owner_gate"), dict)
        else {}
    )
    deployment_gate = (
        pre_live_packet.get("deployment_gate")
        if isinstance(pre_live_packet.get("deployment_gate"), dict)
        else {}
    )
    pipeline = (
        pre_live_packet.get("pipeline")
        if isinstance(pre_live_packet.get("pipeline"), dict)
        else {}
    )
    evidence_preparation = (
        pre_live_packet.get("evidence_preparation")
        if isinstance(pre_live_packet.get("evidence_preparation"), dict)
        else {}
    )
    exchange_rehearsal = (
        pre_live_packet.get("exchange_submit_adapter_rehearsal")
        if isinstance(pre_live_packet.get("exchange_submit_adapter_rehearsal"), dict)
        else {}
    )
    local_registration_rehearsal = _as_dict(
        pre_live_packet.get("local_registration_rehearsal")
    )
    local_registration_adapter_result = _as_dict(
        local_registration_rehearsal.get("adapter_result")
    )
    disabled_execution_result = _as_dict(
        exchange_rehearsal.get("disabled_execution_result")
    )
    in_memory_execution_simulation = _as_dict(
        exchange_rehearsal.get("in_memory_execution_simulation")
    )

    technical_blockers = list(checks.get("technical_blockers") or [])
    protection_failure_policy_blockers = list(
        checks.get("protection_failure_policy_blockers") or []
    )
    operational_blockers = list(checks.get("operational_blockers") or [])
    implementation_blockers = list(checks.get("implementation_blockers") or [])
    live_enablement_blockers = list(checks.get("live_enablement_blockers") or [])
    forbidden_execution_flags = list(checks.get("forbidden_execution_flags") or [])

    owner_decision_items = _owner_decision_items(
        operational_blockers=operational_blockers,
        live_enablement_blockers=live_enablement_blockers,
        owner_gate=owner_gate,
    )
    deployment_blockers = []
    if deployment_gate.get("require_current_head_deployed") is True and (
        deployment_gate.get("current_head_deployed") is not True
    ):
        deployment_blockers.append("current_head_not_deployed_to_tokyo")
    non_owner_operational_blockers = [
        blocker
        for blocker in operational_blockers
        if blocker not in {OWNER_REAL_SUBMIT_AUTH_MISSING}
    ]
    non_owner_live_enablement_blockers = _non_owner_live_enablement_blockers(
        live_enablement_blockers=live_enablement_blockers,
        owner_gate=owner_gate,
    )

    technical_ready = (
        checks.get("technical_rehearsal_passed") is True
        and checks.get("registration_draft_chain_passed") is True
        and checks.get("protection_failure_policy_passed") is True
        and not technical_blockers
        and not protection_failure_policy_blockers
        and not forbidden_execution_flags
    )
    implementation_ready = not implementation_blockers
    deployment_ready = not deployment_blockers
    ready_for_owner_decision = (
        technical_ready
        and implementation_ready
        and deployment_ready
        and not non_owner_operational_blockers
        and not non_owner_live_enablement_blockers
    )
    ready_for_first_real_submit = checks.get("ready_for_first_real_submit") is True

    blockers = _dedupe(
        technical_blockers
        + protection_failure_policy_blockers
        + deployment_blockers
        + non_owner_operational_blockers
        + implementation_blockers
        + non_owner_live_enablement_blockers
        + forbidden_execution_flags
    )
    if checks.get("protection_failure_policy_passed") is not True:
        blockers.append("protection_failure_policy_not_ready")
    if not ready_for_owner_decision:
        blockers.append("first_real_submit_prerequisites_not_ready")
        blockers = _dedupe(blockers)
    exchange_submit_action_blockers = _exchange_submit_action_blockers(
        checks=checks,
        ready_for_first_real_submit=ready_for_first_real_submit,
    )

    status = "blocked_before_owner_first_real_submit_decision"
    if ready_for_first_real_submit:
        status = "ready_for_owner_controlled_first_real_submit_review"
    elif ready_for_owner_decision:
        status = "ready_for_owner_first_real_submit_decision"

    packet = {
        "status": status,
        "scope": "runtime_first_real_submit_owner_review_artifact",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "local_git": pre_live_packet.get("local_git", {}),
        "deployment_gate": deployment_gate,
        "owner_gate": {
            "owner_real_submit_authorized": owner_gate.get(
                "owner_real_submit_authorized"
            ),
            "owner_live_runtime_enablement_authorized": owner_gate.get(
                "owner_live_runtime_enablement_authorized"
            ),
            "required_flags": [
                OWNER_AUTHORIZATION_FLAG,
                OWNER_LIVE_RUNTIME_ENABLEMENT_FLAG,
            ],
            "packet_does_not_authorize_submit": True,
        },
        "readiness_summary": {
            "technical_ready": technical_ready,
            "protection_failure_policy_ready": (
                checks.get("protection_failure_policy_passed") is True
            ),
            "deployment_ready": deployment_ready,
            "implementation_ready": implementation_ready,
            "ready_for_owner_decision": ready_for_owner_decision,
            "ready_for_first_real_submit": ready_for_first_real_submit,
            "owner_decision_scope": _owner_decision_scope(
                ready_for_owner_decision=ready_for_owner_decision,
                ready_for_first_real_submit=ready_for_first_real_submit,
            ),
            "local_order_registration_adapter_enablement_ready": (
                checks.get("local_registration_pre_exchange_ready") is True
            ),
            "exchange_submit_action_ready": ready_for_first_real_submit,
            "local_registration_pre_exchange_ready": checks.get(
                "local_registration_pre_exchange_ready"
            ),
            "exchange_submit_adapter_pre_execution_ready": checks.get(
                "exchange_submit_adapter_pre_execution_ready"
            ),
            "exchange_submit_execution_disabled_proved": (
                disabled_execution_result.get("status")
                == "exchange_submit_execution_disabled"
                and disabled_execution_result.get("exchange_called") is False
                and disabled_execution_result.get("order_lifecycle_submit_called")
                is False
            ),
            "in_memory_exchange_execution_simulation_submitted": checks.get(
                "in_memory_exchange_execution_simulation_submitted"
            ),
            "machine_evidence_preparation_status": evidence_preparation.get(
                "status"
            ),
            "pipeline": {
                "submit_rehearsal_status": pipeline.get("submit_rehearsal_status"),
                "submit_adapter_preview_status": pipeline.get(
                    "submit_adapter_preview_status"
                ),
                "order_lifecycle_handoff_status": pipeline.get(
                    "order_lifecycle_handoff_status"
                ),
                "order_lifecycle_adapter_preview_status": pipeline.get(
                    "order_lifecycle_adapter_preview_status"
                ),
                "order_registration_draft_preview_status": pipeline.get(
                    "order_registration_draft_preview_status"
                ),
                "next_required_gate": pipeline.get("next_required_gate"),
            },
        },
        "remaining_gates": {
            "technical_blockers": technical_blockers,
            "protection_failure_policy_blockers": protection_failure_policy_blockers,
            "deployment_blockers": deployment_blockers,
            "owner_decision_items": owner_decision_items,
            "non_owner_operational_blockers": non_owner_operational_blockers,
            "non_owner_live_enablement_blockers": (
                non_owner_live_enablement_blockers
            ),
            "implementation_blockers": implementation_blockers,
            "live_enablement_blockers": live_enablement_blockers,
            "forbidden_execution_flags": forbidden_execution_flags,
            "machine_evidence_blockers": list(
                evidence_preparation.get("blockers") or []
            ),
            "machine_evidence_skipped": list(
                evidence_preparation.get("skipped_evidence") or []
            ),
            "exchange_submit_rehearsal_blockers": list(
                checks.get("exchange_submit_rehearsal_blockers") or []
            ),
        },
        "local_registration_rehearsal": {
            "enabled": local_registration_rehearsal.get("enabled"),
            "ready": local_registration_rehearsal.get("ready"),
            "enablement_decision_id": local_registration_rehearsal.get(
                "enablement_decision_id"
            ),
            "action_authorization_id": local_registration_rehearsal.get(
                "action_authorization_id"
            ),
            "adapter_result_status": local_registration_adapter_result.get(
                "status"
            ),
            "registered_order_count": local_registration_adapter_result.get(
                "registered_order_count"
            ),
            "order_lifecycle_called": local_registration_adapter_result.get(
                "order_lifecycle_called"
            ),
            "exchange_called": local_registration_adapter_result.get(
                "exchange_called"
            ),
            "does_not_authorize_live_action": True,
        },
        "exchange_submit_rehearsal": {
            "enabled": exchange_rehearsal.get("enabled"),
            "ready": exchange_rehearsal.get("ready"),
            "enablement_decision_id": exchange_rehearsal.get(
                "enablement_decision_id"
            ),
            "adapter_result_status": _nested(
                exchange_rehearsal,
                "adapter_result",
                "status",
            ),
            "disabled_execution_result_status": disabled_execution_result.get(
                "status"
            ),
            "disabled_execution_mode": disabled_execution_result.get(
                "execution_mode"
            ),
            "disabled_execution_result_exchange_called": (
                disabled_execution_result.get("exchange_called")
            ),
            "disabled_execution_result_order_lifecycle_submit_called": (
                disabled_execution_result.get("order_lifecycle_submit_called")
            ),
            "in_memory_simulation_status": (
                in_memory_execution_simulation.get("status")
            ),
            "in_memory_simulation_execution_mode": (
                in_memory_execution_simulation.get("execution_mode")
            ),
            "in_memory_simulation_exchange_called": (
                in_memory_execution_simulation.get("exchange_called")
            ),
            "in_memory_simulation_is_fake_gateway_only": bool(
                in_memory_execution_simulation
            ),
            "does_not_authorize_live_action": True,
        },
        "first_real_submit_action_boundary": {
            "owner_packet_ready_for_decision": ready_for_owner_decision,
            "ready_for_first_real_submit": ready_for_first_real_submit,
            "local_registration_pre_exchange_ready": checks.get(
                "local_registration_pre_exchange_ready"
            ),
            "exchange_submit_adapter_pre_execution_ready": checks.get(
                "exchange_submit_adapter_pre_execution_ready"
            ),
            "exchange_submit_execution_disabled_proved": (
                disabled_execution_result.get("status")
                == "exchange_submit_execution_disabled"
                and disabled_execution_result.get("exchange_called") is False
                and disabled_execution_result.get("order_lifecycle_submit_called")
                is False
            ),
            "remaining_action_blockers": exchange_submit_action_blockers,
            "owner_decision_is_submit_authority": False,
            "requires_separate_action_authorization": True,
            "does_not_authorize_live_action": True,
        },
        "evidence_preparation": {
            "status": evidence_preparation.get("status"),
            "prepared_evidence_ids": dict(
                evidence_preparation.get("prepared_evidence_ids") or {}
            ),
            "available_evidence_ids": dict(
                evidence_preparation.get("available_evidence_ids") or {}
            ),
            "prepared_evidence_status": (
                evidence_preparation.get("packet", {}).get("status")
                if isinstance(evidence_preparation.get("packet"), dict)
                else None
            ),
            "does_not_authorize_live_action": True,
        },
        "checks": {
            "packet_ready_for_owner_decision": ready_for_owner_decision,
            "ready_for_first_real_submit": ready_for_first_real_submit,
            "blockers": blockers,
        },
        "source_pre_live_evidence": {
            "status": pre_live_packet.get("status"),
            "scope": pre_live_packet.get("scope"),
            "safety_invariants": pre_live_packet.get("safety_invariants", {}),
        },
        "does_not_authorize": [
            "real runtime submit",
            "exchange order placement",
            "OrderLifecycle adapter enablement",
            "local order registration",
            "withdrawal or transfer",
            "live runtime profile change",
        ],
        "safety_invariants": {
            "packet_build_only": True,
            "database_connected": False,
            "remote_files_modified": False,
            "services_restarted": False,
            "migrations_run": False,
            "runtime_started": False,
            "persistent_runtime_budget_mutated": False,
            "execution_intent_status_changed": False,
            "order_created": False,
            "owner_bounded_execution_called": False,
            "order_lifecycle_called": False,
            "exchange_called": False,
            "withdrawal_or_transfer_created": False,
        },
    }
    return packet


def _owner_decision_items(
    *,
    operational_blockers: list[str],
    live_enablement_blockers: list[str],
    owner_gate: dict[str, Any],
) -> list[str]:
    items: list[str] = []
    if OWNER_REAL_SUBMIT_AUTH_MISSING in operational_blockers or (
        owner_gate.get("owner_real_submit_authorized") is not True
    ):
        items.append("Owner real-submit authorization")
    if OWNER_LIVE_RUNTIME_AUTH_MISSING in live_enablement_blockers or (
        owner_gate.get("owner_live_runtime_enablement_authorized") is not True
    ):
        items.append("Owner live-runtime enablement authorization")
    return _dedupe(items)


def _non_owner_live_enablement_blockers(
    *,
    live_enablement_blockers: list[str],
    owner_gate: dict[str, Any],
) -> list[str]:
    owner_live_blockers = {
        OWNER_LIVE_RUNTIME_AUTH_MISSING,
        OWNER_REAL_SUBMIT_AUTH_MISSING,
    }
    if owner_gate.get("owner_real_submit_authorized") is not True:
        owner_live_blockers.update(
            {
                "promotion_gate_first_real_submit_explicit_owner_real_submit_authorization_missing",
                "promotion_gate_first_real_submit_owner_real_submit_authorization_id_missing",
            }
        )

    non_owner = [
        blocker
        for blocker in live_enablement_blockers
        if blocker not in owner_live_blockers
    ]
    if non_owner == ["promotion_gate_not_ready_for_first_real_submit"]:
        return []
    return _dedupe(non_owner)


def _exchange_submit_action_blockers(
    *,
    checks: dict[str, Any],
    ready_for_first_real_submit: bool,
) -> list[str]:
    items = list(checks.get("exchange_submit_rehearsal_blockers") or [])
    if checks.get("local_registration_pre_exchange_ready") is not True:
        items.append("local_registration_pre_exchange_not_ready")
    if checks.get("exchange_submit_adapter_pre_execution_ready") is not True:
        items.append("exchange_submit_adapter_pre_execution_not_ready")
    if not ready_for_first_real_submit:
        items.append("first_real_submit_action_not_ready")
    return _dedupe(items)


def _owner_decision_scope(
    *,
    ready_for_owner_decision: bool,
    ready_for_first_real_submit: bool,
) -> str:
    if ready_for_first_real_submit:
        return "owner_controlled_first_real_submit_review"
    if ready_for_owner_decision:
        return "owner_review_not_submit_authority"
    return "blocked_before_owner_review"


def _dedupe(values: list[str]) -> list[str]:
    return sorted(dict.fromkeys(values))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a non-executing first-real-submit Owner review artifact."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument(
        "--deployed-head",
        default=DEFAULT_DEPLOYED_HEAD,
        help="Read-only deployed code head used by the deployment gate.",
    )
    parser.add_argument(
        OWNER_AUTHORIZATION_FLAG,
        action="store_true",
        help="Mark Owner real-submit authorization as present for packet evaluation.",
    )
    parser.add_argument(
        OWNER_LIVE_RUNTIME_ENABLEMENT_FLAG,
        action="store_true",
        help="Mark Owner live-runtime enablement authorization as present.",
    )
    parser.add_argument(
        "--skip-current-head-deployed-check",
        action="store_true",
        help="Do not block when local HEAD differs from --deployed-head.",
    )
    parser.add_argument("--active-positions", type=int, default=0)
    parser.add_argument(
        "--exercise-local-registration-pre-exchange",
        action="store_true",
        help="Include in-memory local-registration rehearsal evidence.",
    )
    parser.add_argument(
        "--exercise-exchange-submit-adapter-pre-execution",
        action="store_true",
        help="Include exchange-submit pre-execution rehearsal evidence.",
    )
    parser.add_argument(
        "--exercise-in-memory-exchange-execution-simulation",
        action="store_true",
        help=(
            "Include fake-gateway enabled execution simulation evidence. This "
            "does not call Binance or any real exchange."
        ),
    )
    return parser.parse_args(argv)


def _print_human(packet: dict[str, Any]) -> None:
    checks = packet["checks"]
    summary = packet["readiness_summary"]
    gates = packet["remaining_gates"]
    print(f"status={packet['status']}")
    print(
        "packet_ready_for_owner_decision="
        + str(checks["packet_ready_for_owner_decision"]).lower()
    )
    print(
        "ready_for_first_real_submit="
        + str(checks["ready_for_first_real_submit"]).lower()
    )
    print("technical_ready=" + str(summary["technical_ready"]).lower())
    print("deployment_ready=" + str(summary["deployment_ready"]).lower())
    print("implementation_ready=" + str(summary["implementation_ready"]).lower())
    print(
        "local_registration_pre_exchange_ready="
        + str(summary["local_registration_pre_exchange_ready"]).lower()
    )
    print(
        "exchange_submit_adapter_pre_execution_ready="
        + str(summary["exchange_submit_adapter_pre_execution_ready"]).lower()
    )
    print(
        "in_memory_exchange_execution_simulation_submitted="
        + str(
            summary["in_memory_exchange_execution_simulation_submitted"]
        ).lower()
    )
    if gates["owner_decision_items"]:
        print("owner_decision_items=" + ",".join(gates["owner_decision_items"]))
    if checks["blockers"]:
        print("blockers=" + ",".join(checks["blockers"]))


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _nested(payload: dict[str, Any], *keys: str) -> Any:
    value: Any = payload
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


if __name__ == "__main__":
    raise SystemExit(main())
