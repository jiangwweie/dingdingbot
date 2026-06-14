#!/usr/bin/env python3
"""Build a fresh-attempt readiness packet from existing runtime reports.

The packet is an operator-facing guardrail over already-produced evidence:

operator live-fact packet
-> fresh strategy signal loop
-> fresh candidate / readiness evidence
-> fresh authorization / FinalGate action-time gate

It never calls the API, PG, exchange, OrderLifecycle, or submit endpoints.  Its
job is to prevent an old authorization or rehearsal packet from being mistaken
for current next-attempt authority.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any


READY_LIVE_FACT_GATE = "ready_for_strategy_signal"
WAITING_FOR_SIGNAL = "waiting_for_signal"
READY_FOR_PREPARE = "ready_for_prepare"
READY_FOR_FINAL_GATE_PREFLIGHT = "ready_for_final_gate_preflight"
READY_FOR_READINESS_EVIDENCE = "ready_for_readiness_evidence"
READY_FOR_FRESH_SUBMIT_AUTHORIZATION = "ready_for_fresh_submit_authorization"
READY_FOR_OFFICIAL_SUBMIT_CALL = "ready_for_official_submit_call"

FORBIDDEN_TRUE_KEYS = {
    "attempt_counter_mutated",
    "attempt_counter_mutated_by_script",
    "calls_official_submit_endpoint",
    "exchange_called",
    "exchange_order_submitted",
    "exchange_submit_armed",
    "exchange_write_called",
    "execute_real_submit",
    "executable_execution_intent_created",
    "execution_intent_created",
    "execution_intent_created_by_script",
    "local_order_created",
    "local_registration_armed",
    "order_created",
    "order_lifecycle_called",
    "pg_write_by_script",
    "position_closed",
    "position_opened",
    "runtime_budget_mutated",
    "runtime_budget_mutated_by_script",
    "runtime_state_mutated",
    "withdrawal_or_transfer_created",
}

LEGACY_AUTHORITY_KEYS = {
    "legacy_authorization_replay_allowed",
    "old_authorization_submit_retry_allowed",
    "pre_submit_rehearsal_retry_allowed",
    "uses_legacy_pre_attempt_rehearsal_as_primary_gate",
}


def _read_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    text = Path(path).expanduser().read_text(encoding="utf-8")
    start = text.find("{")
    if start < 0:
        raise ValueError(f"{path} does not contain a JSON object")
    payload = json.loads(text[start:])
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _get(value: Any, *path: str) -> Any:
    current = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _status(packet: dict[str, Any] | None) -> str:
    return str((packet or {}).get("status") or "")


def _list_values(*values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        if isinstance(value, list):
            result.extend(str(item) for item in value if item is not None)
        elif value:
            result.append(str(value))
    return result


def _truthy_keys(
    value: Any,
    keys: set[str],
    *,
    include_forbidden_effects: bool = False,
    prefix: str = "",
) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            if include_forbidden_effects and key == "forbidden_effects" and isinstance(item, dict):
                found.extend(
                    f"{name}.{effect_key}"
                    for effect_key, enabled in item.items()
                    if bool(enabled)
                )
            if key in keys and bool(item):
                found.append(name)
            found.extend(
                _truthy_keys(
                    item,
                    keys,
                    include_forbidden_effects=include_forbidden_effects,
                    prefix=name,
                )
            )
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(
                _truthy_keys(
                    item,
                    keys,
                    include_forbidden_effects=include_forbidden_effects,
                    prefix=f"{prefix}[{index}]",
                )
            )
    return sorted(set(found))


def _fresh_signal_summary(packet: dict[str, Any] | None) -> dict[str, Any]:
    if not packet:
        return {
            "status": "missing",
            "signal_input_json": None,
            "prepared_authorization_id": None,
            "blocked_stage": None,
        }
    observation = packet.get("observation_prepare_flow")
    if not isinstance(observation, dict):
        observation = {}
    return {
        "status": _status(packet),
        "signal_input_json": packet.get("signal_input_json")
        or observation.get("signal_input_json"),
        "prepared_authorization_id": packet.get("prepared_authorization_id")
        or _get(packet, "operator_command_plan", "prepared_authorization_id"),
        "blocked_stage": packet.get("blocked_stage"),
    }


def _candidate_summary(
    *,
    fresh_signal_loop: dict[str, Any] | None,
    readiness_bridge: dict[str, Any] | None,
    final_gate_preflight: dict[str, Any] | None,
) -> dict[str, Any]:
    bridge_plan = (readiness_bridge or {}).get("next_attempt_strategy_plan_flow")
    if not isinstance(bridge_plan, dict):
        bridge_plan = {}
    return {
        "signal_evaluation_id": (
            bridge_plan.get("signal_evaluation_id")
            or (final_gate_preflight or {}).get("signal_evaluation_id")
        ),
        "order_candidate_id": (
            bridge_plan.get("order_candidate_id")
            or (final_gate_preflight or {}).get("order_candidate_id")
        ),
        "fresh_signal_loop_status": _status(fresh_signal_loop),
        "readiness_bridge_status": _status(readiness_bridge),
        "final_gate_preflight_status": _status(final_gate_preflight),
    }


def _evidence_summary(
    *,
    readiness_evidence: dict[str, Any] | None,
    readiness_bridge: dict[str, Any] | None,
    fresh_authorization_binding: dict[str, Any] | None,
    official_handoff: dict[str, Any] | None,
) -> dict[str, Any]:
    evidence = (readiness_evidence or {}).get("evidence")
    if not isinstance(evidence, dict):
        evidence = {}
    return {
        "readiness_evidence_status": _status(readiness_evidence),
        "readiness_bridge_status": _status(readiness_bridge),
        "fresh_authorization_binding_status": _status(fresh_authorization_binding),
        "official_handoff_status": _status(official_handoff),
        "runtime_grant_authorization_id": evidence.get(
            "runtime_grant_authorization_id"
        ),
        "owner_real_submit_authorization_id": evidence.get(
            "owner_real_submit_authorization_id"
        ),
        "fresh_submit_authorization_id": (
            (fresh_authorization_binding or {}).get("fresh_submit_authorization_id")
            or (official_handoff or {}).get("fresh_submit_authorization_id")
            or _get(readiness_bridge, "operator_action_preview", "fresh_submit_authorization_id")
        ),
        "final_gate_preview_id": evidence.get("final_gate_preview_id"),
        "trusted_submit_fact_snapshot_id": evidence.get(
            "trusted_submit_fact_snapshot_id"
        ),
    }


def _chain_coverage(
    *,
    operator_live_fact_packet: dict[str, Any],
    fresh_signal_loop: dict[str, Any] | None,
    readiness_bridge: dict[str, Any] | None,
    readiness_evidence: dict[str, Any] | None,
    fresh_authorization_binding: dict[str, Any] | None,
    official_handoff: dict[str, Any] | None,
    final_gate_preflight: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    fresh_signal = _fresh_signal_summary(fresh_signal_loop)
    candidate = _candidate_summary(
        fresh_signal_loop=fresh_signal_loop,
        readiness_bridge=readiness_bridge,
        final_gate_preflight=final_gate_preflight,
    )
    evidence = _evidence_summary(
        readiness_evidence=readiness_evidence,
        readiness_bridge=readiness_bridge,
        fresh_authorization_binding=fresh_authorization_binding,
        official_handoff=official_handoff,
    )
    return {
        "live_fact_gate": {
            "status": "present",
            "packet_status": _status(operator_live_fact_packet),
            "ready": _status(operator_live_fact_packet) == READY_LIVE_FACT_GATE,
            "runtime_instance_id": operator_live_fact_packet.get(
                "runtime_instance_id"
            ),
        },
        "fresh_strategy_signal": {
            "status": "present" if fresh_signal_loop else "missing",
            "packet_status": fresh_signal["status"],
            "signal_input_json": fresh_signal["signal_input_json"],
            "blocked_stage": fresh_signal["blocked_stage"],
        },
        "fresh_candidate": {
            "status": "present"
            if candidate.get("order_candidate_id") or candidate.get("signal_evaluation_id")
            else "missing",
            **candidate,
        },
        "readiness_evidence": {
            "status": "present" if readiness_evidence else "missing",
            **evidence,
        },
        "fresh_authorization": {
            "status": "present"
            if evidence.get("fresh_submit_authorization_id")
            or evidence.get("runtime_grant_authorization_id")
            or evidence.get("owner_real_submit_authorization_id")
            else "missing",
            "fresh_submit_authorization_id": evidence.get(
                "fresh_submit_authorization_id"
            ),
            "runtime_grant_authorization_id": evidence.get(
                "runtime_grant_authorization_id"
            ),
            "owner_real_submit_authorization_id": evidence.get(
                "owner_real_submit_authorization_id"
            ),
        },
        "final_gate_action_time": {
            "status": "present"
            if final_gate_preflight or _status(official_handoff) == READY_FOR_OFFICIAL_SUBMIT_CALL
            else "missing",
            "final_gate_preflight_status": _status(final_gate_preflight),
            "official_handoff_status": _status(official_handoff),
            "final_gate_preview_id": evidence.get("final_gate_preview_id"),
        },
    }


def _status_from_chain(
    *,
    coverage: dict[str, dict[str, Any]],
    operator_live_fact_packet: dict[str, Any],
    fresh_signal_loop: dict[str, Any] | None,
    readiness_bridge: dict[str, Any] | None,
    readiness_evidence: dict[str, Any] | None,
    final_gate_preflight: dict[str, Any] | None,
    forbidden_effects: list[str],
    legacy_authority_attempts: list[str],
) -> str:
    if forbidden_effects:
        return "blocked_forbidden_effect"
    if legacy_authority_attempts:
        return "blocked_legacy_authorization_replay"
    if _status(operator_live_fact_packet) != READY_LIVE_FACT_GATE:
        return "blocked_by_live_fact_gate"

    fresh_status = _status(fresh_signal_loop)
    if not fresh_signal_loop or fresh_status == WAITING_FOR_SIGNAL:
        return "waiting_for_fresh_strategy_signal"
    if fresh_status not in {READY_FOR_PREPARE, READY_FOR_FINAL_GATE_PREFLIGHT}:
        return "blocked_fresh_signal_prepare_loop"

    bridge_status = _status(readiness_bridge)
    if not readiness_bridge and not readiness_evidence:
        return "ready_for_readiness_evidence"
    if bridge_status == READY_FOR_READINESS_EVIDENCE:
        return "ready_for_readiness_evidence"
    if bridge_status == READY_FOR_FRESH_SUBMIT_AUTHORIZATION:
        return "waiting_for_fresh_authorization"
    if bridge_status == READY_FOR_OFFICIAL_SUBMIT_CALL:
        return "ready_for_action_time_gate"
    if bridge_status == "blocked":
        return "blocked_readiness_bridge"

    if _status(final_gate_preflight) == "official_fresh_candidate_final_gate_preflight_passed":
        return "ready_for_action_time_gate"
    if coverage["fresh_authorization"]["status"] == "missing":
        return "waiting_for_fresh_authorization"
    return "operator_review"


def _operator_next_step(status: str) -> str:
    if status == "blocked_by_live_fact_gate":
        return "resolve_live_fact_gate_before_fresh_attempt"
    if status == "waiting_for_fresh_strategy_signal":
        return "continue_fresh_strategy_signal_observation"
    if status == "ready_for_readiness_evidence":
        return "collect_fresh_readiness_evidence"
    if status == "waiting_for_fresh_authorization":
        return "bind_or_resolve_fresh_authorization"
    if status == "ready_for_action_time_gate":
        return "run_action_time_final_gate_before_any_official_submit"
    if status == "blocked_legacy_authorization_replay":
        return "discard_legacy_authorization_as_current_authority"
    if status == "blocked_forbidden_effect":
        return "stop_and_review_forbidden_side_effects"
    return "resolve_fresh_attempt_readiness_blocker"


def build_fresh_attempt_readiness_packet(
    *,
    operator_live_fact_packet: dict[str, Any],
    fresh_signal_loop: dict[str, Any] | None = None,
    readiness_bridge: dict[str, Any] | None = None,
    readiness_evidence: dict[str, Any] | None = None,
    fresh_authorization_binding: dict[str, Any] | None = None,
    official_handoff: dict[str, Any] | None = None,
    final_gate_preflight: dict[str, Any] | None = None,
    generated_at_ms: int | None = None,
) -> dict[str, Any]:
    sources = {
        "operator_live_fact_packet": operator_live_fact_packet,
        "fresh_signal_loop": fresh_signal_loop or {},
        "readiness_bridge": readiness_bridge or {},
        "readiness_evidence": readiness_evidence or {},
        "fresh_authorization_binding": fresh_authorization_binding or {},
        "official_handoff": official_handoff or {},
        "final_gate_preflight": final_gate_preflight or {},
    }
    forbidden_effects = _truthy_keys(
        sources,
        FORBIDDEN_TRUE_KEYS,
        include_forbidden_effects=True,
    )
    legacy_authority_attempts = _truthy_keys(sources, LEGACY_AUTHORITY_KEYS)
    coverage = _chain_coverage(
        operator_live_fact_packet=operator_live_fact_packet,
        fresh_signal_loop=fresh_signal_loop,
        readiness_bridge=readiness_bridge,
        readiness_evidence=readiness_evidence,
        fresh_authorization_binding=fresh_authorization_binding,
        official_handoff=official_handoff,
        final_gate_preflight=final_gate_preflight,
    )
    status = _status_from_chain(
        coverage=coverage,
        operator_live_fact_packet=operator_live_fact_packet,
        fresh_signal_loop=fresh_signal_loop,
        readiness_bridge=readiness_bridge,
        readiness_evidence=readiness_evidence,
        final_gate_preflight=final_gate_preflight,
        forbidden_effects=forbidden_effects,
        legacy_authority_attempts=legacy_authority_attempts,
    )
    blockers = _list_values(
        operator_live_fact_packet.get("blockers"),
        (fresh_signal_loop or {}).get("blockers"),
        (readiness_bridge or {}).get("blockers"),
        (readiness_evidence or {}).get("blockers"),
        (fresh_authorization_binding or {}).get("blockers"),
        (official_handoff or {}).get("blockers"),
        (final_gate_preflight or {}).get("blockers"),
    )
    if status == "blocked_by_live_fact_gate":
        blockers.append("live_fact_gate_not_ready_for_fresh_attempt")
    if status == "blocked_legacy_authorization_replay":
        blockers.append("legacy_authorization_replay_attempted_as_current_authority")
    if status == "blocked_forbidden_effect":
        blockers.append("forbidden_live_side_effect_reported")

    return {
        "scope": "runtime_fresh_attempt_readiness_packet",
        "status": status,
        "runtime_instance_id": operator_live_fact_packet.get("runtime_instance_id"),
        "generated_at_ms": generated_at_ms
        if generated_at_ms is not None
        else int(time.time() * 1000),
        "chain_coverage": coverage,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(
            set(
                _list_values(
                    operator_live_fact_packet.get("warnings"),
                    (fresh_signal_loop or {}).get("warnings"),
                    (readiness_bridge or {}).get("warnings"),
                    (readiness_evidence or {}).get("warnings"),
                    (fresh_authorization_binding or {}).get("warnings"),
                    (official_handoff or {}).get("warnings"),
                    (final_gate_preflight or {}).get("warnings"),
                )
            )
        ),
        "fresh_attempt_policy": {
            "requires_ready_live_fact_gate_first": True,
            "requires_fresh_strategy_signal": True,
            "requires_fresh_candidate_or_signal_evaluation": True,
            "requires_fresh_readiness_evidence": True,
            "requires_fresh_authorization_before_submit": True,
            "requires_action_time_final_gate": True,
            "legacy_authorization_replay_allowed": False,
            "old_first_real_submit_authority_allowed": False,
            "executable_submit_allowed_by_packet": False,
        },
        "operator_command_plan": {
            "not_executed": True,
            "next_step": _operator_next_step(status),
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
            "creates_executable_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "calls_exchange_write": False,
            "requires_owner_chat_confirmation": False,
            "uses_standing_runtime_authorization": status == "ready_for_action_time_gate",
            "requires_action_time_final_gate": status == "ready_for_action_time_gate",
            "requires_official_operation_layer": status == "ready_for_action_time_gate",
            "can_continue_without_owner_chat": status == "ready_for_action_time_gate",
            "requires_action_time_confirmation": False,
        },
        "safety_invariants": {
            "packet_only": True,
            "reads_json_reports_only": True,
            "api_called_by_builder": False,
            "pg_called_by_builder": False,
            "exchange_called_by_builder": False,
            "exchange_write_called_by_builder": False,
            "order_lifecycle_called_by_builder": False,
            "submit_endpoint_called_by_builder": False,
            "runtime_state_mutated_by_builder": False,
            "withdrawal_or_transfer_created_by_builder": False,
            "no_forbidden_live_side_effects": not forbidden_effects,
            "forbidden_effects": forbidden_effects,
            "legacy_authority_attempts": legacy_authority_attempts,
        },
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a P0-B fresh-attempt readiness packet from reports.",
    )
    parser.add_argument("--operator-live-fact-packet-json", required=True)
    parser.add_argument("--fresh-signal-loop-json")
    parser.add_argument("--readiness-bridge-json")
    parser.add_argument("--readiness-evidence-json")
    parser.add_argument("--fresh-authorization-binding-json")
    parser.add_argument("--official-handoff-json")
    parser.add_argument("--final-gate-preflight-json")
    parser.add_argument("--generated-at-ms", type=int)
    parser.add_argument("--output-json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    packet = build_fresh_attempt_readiness_packet(
        operator_live_fact_packet=_read_json(args.operator_live_fact_packet_json) or {},
        fresh_signal_loop=_read_json(args.fresh_signal_loop_json),
        readiness_bridge=_read_json(args.readiness_bridge_json),
        readiness_evidence=_read_json(args.readiness_evidence_json),
        fresh_authorization_binding=_read_json(args.fresh_authorization_binding_json),
        official_handoff=_read_json(args.official_handoff_json),
        final_gate_preflight=_read_json(args.final_gate_preflight_json),
        generated_at_ms=args.generated_at_ms,
    )
    if args.output_json:
        _write_json(args.output_json, packet)
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if packet["status"] in {
        "blocked_by_live_fact_gate",
        "waiting_for_fresh_strategy_signal",
        "ready_for_readiness_evidence",
        "waiting_for_fresh_authorization",
        "ready_for_action_time_gate",
        "operator_review",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
