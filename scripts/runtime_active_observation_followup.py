#!/usr/bin/env python3
"""Run authorized non-executing follow-up after active observation stops.

The script consumes ``runtime_active_observation_loop`` output. It never creates
prepare records itself. When the loop has already reached
``ready_for_final_gate_preflight`` and a prepared submit authorization is
available, it can run the existing disabled first-real-submit smoke with
``owner_confirmed_for_first_real_submit_action=false``.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Mapping

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.runtime_first_real_submit_api_flow import (  # noqa: E402
    DEFAULT_API_BASE,
    DEFAULT_OUTCOME_KIND,
    EXCHANGE_ARM_APPROVAL_ENV,
    FirstRealSubmitApiFlow,
    FlowConfig,
    LOCAL_REGISTRATION_APPROVAL_ENV,
    UrlLibApiClient,
    _load_env_file,
    _exchange_arm_approval_value,
    _local_registration_approval_value,
)


READY_STATUS = "ready_for_final_gate_preflight"
READY_FOR_PREPARE_STATUS = "ready_for_prepare"
MAX_ITERATIONS_EXHAUSTED = "max_iterations_exhausted"
EXPECTED_LOCAL_REGISTRATION_ARM_BLOCKER = (
    "attempt_consumption_required_before_order_lifecycle_handoff"
)
EXPECTED_DISABLED_SMOKE_ADAPTER_BLOCKER = (
    "preview_disabled_first_real_submit_action_http_404"
)
EXPECTED_DISABLED_SMOKE_ADAPTER_DETAIL = (
    "RuntimeExecutionOrderLifecycleAdapterResult not found"
)
LOCAL_REGISTRATION_REQUIRED_EVIDENCE_IDS = (
    "trusted_submit_fact_snapshot_id",
    "submit_idempotency_policy_id",
    "protection_creation_failure_policy_id",
)
ATTEMPT_POLICY_PREPARED_STATUS = "attempt_policy_prepared"
FORBIDDEN_LOOP_FLAGS = (
    "exchange_write_called",
    "order_created",
    "order_lifecycle_called",
    "attempt_counter_mutated",
    "runtime_budget_mutated",
    "withdrawal_or_transfer_created",
    "executable_execution_intent_created",
    "creates_execution_intent",
    "places_order",
    "calls_order_lifecycle",
)


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"loop packet not found: {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("loop packet must be a JSON object")
    return payload


def _load_arm_report(args: argparse.Namespace) -> dict[str, Any] | None:
    path_value = getattr(args, "arm_report_json", None)
    if not path_value:
        return None
    report = _load_json_object(Path(path_value).expanduser())
    if report.get("script") != "runtime_first_real_submit_api_flow":
        raise RuntimeError("arm report must come from runtime_first_real_submit_api_flow")
    if report.get("mode") != "arm":
        raise RuntimeError("arm report must have mode=arm")
    return report


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _latest_summary(loop_packet: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(loop_packet.get("latest_summary"))
    if summary:
        return summary
    runtime_summaries = loop_packet.get("runtime_summaries")
    if isinstance(runtime_summaries, list):
        for item in runtime_summaries:
            if not isinstance(item, dict):
                continue
            if (
                item.get("status") == READY_STATUS
                or item.get("ready_for_final_gate_preflight") is True
            ):
                return item
        for item in runtime_summaries:
            if isinstance(item, dict):
                return item
    summaries = loop_packet.get("cycle_summaries")
    if isinstance(summaries, list) and summaries:
        last = summaries[-1]
        if isinstance(last, dict):
            return last
    return {}


def _prepared_authorization_id(loop_packet: dict[str, Any]) -> str | None:
    summary = _latest_summary(loop_packet)
    candidates = [
        summary.get("prepared_authorization_id"),
        _as_dict(loop_packet.get("operator_command_plan")).get(
            "prepared_authorization_id"
        ),
    ]
    packets = loop_packet.get("cycle_packets")
    if isinstance(packets, list) and packets:
        packet = packets[-1]
        if isinstance(packet, dict):
            candidates.append(
                _as_dict(packet.get("operator_command_plan")).get(
                    "prepared_authorization_id"
                )
            )
    runtime_summaries = loop_packet.get("runtime_summaries")
    if isinstance(runtime_summaries, list):
        for item in runtime_summaries:
            if not isinstance(item, dict):
                continue
            if (
                item.get("status") == READY_STATUS
                or item.get("ready_for_final_gate_preflight") is True
            ):
                candidates.append(item.get("prepared_authorization_id"))
    runtime_packets = loop_packet.get("runtime_packets")
    if isinstance(runtime_packets, list):
        for item in runtime_packets:
            if not isinstance(item, dict):
                continue
            if (
                item.get("status") == READY_STATUS
                or item.get("ready_for_final_gate_preflight") is True
            ):
                candidates.append(
                    _as_dict(item.get("operator_command_plan")).get(
                        "prepared_authorization_id"
                    )
                )
                latest_packet = _as_dict(item.get("latest_packet"))
                candidates.append(
                    _as_dict(latest_packet.get("operator_command_plan")).get(
                        "prepared_authorization_id"
                    )
                )
                prepare_packet = _as_dict(latest_packet.get("prepare_packet"))
                candidates.append(_as_dict(prepare_packet.get("ids")).get("authorization_id"))
    for value in candidates:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _loop_forbidden_effects(loop_packet: dict[str, Any]) -> list[str]:
    safety = _as_dict(loop_packet.get("safety_invariants"))
    summary = _latest_summary(loop_packet)
    effects: list[str] = []
    for source_name, source in (
        ("loop", safety),
        ("latest_summary", summary),
    ):
        for name in FORBIDDEN_LOOP_FLAGS:
            if source.get(name) is True:
                effects.append(f"{source_name}.{name}")
    return sorted(set(effects))


def _run_disabled_smoke(
    *,
    authorization_id: str,
    args: argparse.Namespace,
    evidence_ids: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    _load_env_file(args.env_file)
    ids = evidence_ids or {}
    config = FlowConfig(
        api_base=args.api_base,
        mode="disabled-smoke",
        env_file=args.env_file,
        authorization_id=authorization_id,
        trusted_submit_fact_snapshot_id=_optional_id(
            ids, "trusted_submit_fact_snapshot_id"
        ),
        submit_idempotency_policy_id=_optional_id(
            ids, "submit_idempotency_policy_id"
        ),
        attempt_outcome_policy_id=_optional_id(ids, "attempt_outcome_policy_id"),
        protection_creation_failure_policy_id=_optional_id(
            ids, "protection_creation_failure_policy_id"
        ),
        local_registration_enablement_decision_id=_optional_id(
            ids, "local_registration_enablement_decision_id"
        ),
        owner_real_submit_authorization_id=_optional_id(
            ids, "owner_real_submit_authorization_id"
        ),
        order_lifecycle_submit_enablement_id=_optional_id(
            ids, "order_lifecycle_submit_enablement_id"
        ),
        exchange_submit_adapter_enablement_id=_optional_id(
            ids, "exchange_submit_adapter_enablement_id"
        ),
        exchange_submit_action_authorization_id=_optional_id(
            ids, "exchange_submit_action_authorization_id"
        ),
        deployment_readiness_evidence_id=_optional_id(
            ids, "deployment_readiness_evidence_id"
        ),
        exchange_submit_adapter_result_id=_optional_id(
            ids, "exchange_submit_adapter_result_id"
        ),
        explain_disabled_smoke_prerequisites=(
            not args.skip_disabled_smoke_prerequisite_probe
        ),
    )
    return FirstRealSubmitApiFlow(
        client=UrlLibApiClient(api_base=config.api_base),
        config=config,
    ).run()


def _optional_id(ids: Mapping[str, Any], key: str) -> str | None:
    value = ids.get(key)
    text = str(value or "").strip()
    return text or None


def _run_arm_preview(
    *,
    authorization_id: str,
    args: argparse.Namespace,
    evidence_ids: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    _load_env_file(args.env_file)
    ids = evidence_ids or {}
    os.environ.setdefault(
        LOCAL_REGISTRATION_APPROVAL_ENV,
        _local_registration_approval_value(authorization_id),
    )
    os.environ.setdefault(
        EXCHANGE_ARM_APPROVAL_ENV,
        _exchange_arm_approval_value(authorization_id),
    )
    config = FlowConfig(
        api_base=args.api_base,
        mode="arm",
        env_file=args.env_file,
        authorization_id=authorization_id,
        record_attempt_consumption=bool(
            getattr(args, "allow_standing_operation_layer_evidence_prep", False)
        ),
        standing_authorized_scoped_evidence_preparation=bool(
            getattr(args, "allow_standing_operation_layer_evidence_prep", False)
        ),
        preview_disabled_first_real_submit_action=False,
        attempt_outcome_policy_id=_optional_id(ids, "attempt_outcome_policy_id"),
    )
    return FirstRealSubmitApiFlow(
        client=UrlLibApiClient(api_base=config.api_base),
        config=config,
    ).run()


def _prepare_attempt_policy(
    *,
    authorization_id: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    _load_env_file(args.env_file)
    client = UrlLibApiClient(api_base=args.api_base)
    steps: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    ids: dict[str, str] = {}

    reservation = _attempt_policy_step(
        client,
        steps=steps,
        blockers=blockers,
        warnings=warnings,
        name="record_attempt_reservation",
        method="POST",
        path=(
            "/api/trading-console/"
            f"runtime-execution-attempt-reservations/authorizations/{authorization_id}"
        ),
    )
    ids.update(_ids_from_body(_as_dict(reservation.get("body"))))
    reservation_id = ids.get("reservation_id")
    if not reservation_id and _recoverable_existing_record(reservation):
        reservation_id = f"runtime-attempt-reservation-{authorization_id}"
        ids["reservation_id"] = reservation_id
        warnings.append("existing_attempt_reservation_reused")
        _remove_step_http_blocker(blockers, "record_attempt_reservation")
    if not reservation_id:
        blockers.append("attempt_reservation_id_missing")

    if reservation_id and not blockers:
        mutation = _attempt_policy_step(
            client,
            steps=steps,
            blockers=blockers,
            warnings=warnings,
            name="apply_attempt_mutation",
            method="POST",
            path=(
                "/api/trading-console/"
                f"runtime-execution-attempt-mutations/reservations/{reservation_id}"
            ),
        )
        ids.update(_ids_from_body(_as_dict(mutation.get("body"))))
        if not ids.get("mutation_id") and _recoverable_existing_record(mutation):
            ids["mutation_id"] = f"runtime-attempt-mutation-{reservation_id}"
            warnings.append("existing_attempt_mutation_reused")
            _remove_step_http_blocker(blockers, "apply_attempt_mutation")
        if not ids.get("mutation_id"):
            blockers.append("attempt_mutation_id_missing")

    if reservation_id and not blockers:
        policy = _attempt_policy_step(
            client,
            steps=steps,
            blockers=blockers,
            warnings=warnings,
            name="record_attempt_outcome_policy",
            method="POST",
            path=(
                "/api/trading-console/"
                f"runtime-execution-attempt-outcome-policies/reservations/{reservation_id}"
            ),
            query={"outcome_kind": DEFAULT_OUTCOME_KIND},
        )
        ids.update(_ids_from_body(_as_dict(policy.get("body"))))
        if not ids.get("policy_id") and _recoverable_existing_record(policy):
            ids["policy_id"] = (
                f"runtime-attempt-outcome-policy-{reservation_id}-{DEFAULT_OUTCOME_KIND}"
            )
            warnings.append("existing_attempt_outcome_policy_reused")
            _remove_step_http_blocker(blockers, "record_attempt_outcome_policy")
        if not ids.get("policy_id"):
            blockers.append("attempt_outcome_policy_id_missing")

    status = ATTEMPT_POLICY_PREPARED_STATUS if not blockers else "attempt_policy_blocked"
    return {
        "scope": "runtime_attempt_policy_preparation",
        "status": status,
        "authorization_id": authorization_id,
        "ids": {
            "reservation_id": ids.get("reservation_id"),
            "attempt_mutation_id": ids.get("mutation_id"),
            "attempt_outcome_policy_id": ids.get("policy_id"),
        },
        "steps": steps,
        "blockers": _dedupe_text(blockers),
        "warnings": _dedupe_text(warnings),
        "safety": {
            "uses_official_trading_console_api": True,
            "mutates_attempt_counter": status == ATTEMPT_POLICY_PREPARED_STATUS,
            "mutates_runtime_budget": status == ATTEMPT_POLICY_PREPARED_STATUS,
            "exchange_write_called": False,
            "exchange_order_submitted": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _run_attempt_policy_preflight(
    *,
    authorization_id: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    _load_env_file(args.env_file)
    result = UrlLibApiClient(api_base=args.api_base).request_json(
        "GET",
        (
            "/api/trading-console/"
            f"runtime-execution-controlled-submit-preflights/authorizations/{authorization_id}"
        ),
    )
    body = _as_dict(result.get("body"))
    blockers = [str(item) for item in body.get("blockers") or []]
    raw_status = body.get("status") or body.get("controlled_submit_plan_status")
    verdict = body.get("final_gate_verdict")
    if raw_status is not None and str(raw_status) != "ready_for_controlled_submit_adapter":
        blockers.append(f"preflight_status:{raw_status}")
    if verdict is not None and str(verdict).lower() != "pass":
        blockers.append(f"final_gate_verdict:{verdict}")
    if result.get("http_status", 0) >= 300 or result.get("error"):
        blockers.append(f"preflight_http_{result.get('http_status')}")
    passed = (
        result.get("http_status") == 200
        and str(raw_status) == "ready_for_controlled_submit_adapter"
        and str(verdict).lower() == "pass"
        and not blockers
    )
    return {
        "scope": "runtime_attempt_policy_preflight",
        "status": "pass" if passed else "blocked",
        "authorization_id": authorization_id,
        "http_status": result.get("http_status"),
        "body_status": raw_status,
        "final_gate_verdict": verdict,
        "blockers": _dedupe_text(blockers),
        "warnings": [str(item) for item in body.get("warnings") or []],
        "safety": {
            "uses_official_trading_console_api": True,
            "mutates_attempt_counter": False,
            "mutates_runtime_budget": False,
            "exchange_write_called": False,
            "exchange_order_submitted": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _attempt_policy_step(
    client: UrlLibApiClient,
    *,
    steps: list[dict[str, Any]],
    blockers: list[str],
    warnings: list[str],
    name: str,
    method: str,
    path: str,
    query: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = client.request_json(method, path, query=query)
    body = _as_dict(result.get("body"))
    steps.append(
        {
            "name": name,
            "method": method,
            "path": path,
            "query_keys": sorted((query or {}).keys()),
            "http_status": result.get("http_status"),
            "status": body.get("status"),
            "detail": body.get("detail") or body.get("message"),
            "id_summary": _ids_from_body(body),
            "blockers": list(body.get("blockers") or []),
            "warnings": list(body.get("warnings") or []),
        }
    )
    if result.get("http_status", 0) >= 300 or result.get("error"):
        blockers.append(f"{name}_http_{result.get('http_status')}")
    blockers.extend(str(item) for item in body.get("blockers") or [])
    warnings.extend(str(item) for item in body.get("warnings") or [])
    return result


def _ids_from_body(body: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key in ("reservation_id", "mutation_id", "policy_id"):
        value = body.get(key)
        text = str(value or "").strip()
        if text:
            result[key] = text
    return result


def _recoverable_existing_record(result: Mapping[str, Any]) -> bool:
    if int(result.get("http_status") or 0) < 300:
        return False
    text = json.dumps(result.get("body"), ensure_ascii=False, default=str).lower()
    return any(fragment in text for fragment in ("already", "exist", "duplicate"))


def _remove_step_http_blocker(blockers: list[str], name: str) -> None:
    expected = f"{name}_http_"
    blockers[:] = [item for item in blockers if not item.startswith(expected)]


def _disabled_smoke_forbidden_effects(report: dict[str, Any]) -> list[str]:
    effects: list[str] = []
    for step in report.get("steps") or []:
        if not isinstance(step, dict):
            continue
        path = str(step.get("path") or "")
        name = str(step.get("name") or "")
        if "attempt-mutations" in path:
            effects.append(f"{name}:attempt_mutation")
        if "local-registration-action-authorizations" in path:
            effects.append(f"{name}:local_registration_authorization")
        if "exchange-submit-action-authorizations" in path:
            effects.append(f"{name}:exchange_submit_authorization")
        if "exchange-submit-adapter-results" in path:
            effects.append(f"{name}:exchange_submit_adapter_arm")
        if "order-lifecycle-adapter-results" in path:
            effects.append(f"{name}:order_lifecycle_adapter_result")
    if report.get("ready_for_real_submit_action") is True:
        effects.append("ready_for_real_submit_action_true")
    return sorted(set(effects))


def _arm_preview_forbidden_effects(report: dict[str, Any]) -> list[str]:
    safety = _as_dict(report.get("safety"))
    standing_prep = (
        safety.get("standing_authorized_scoped_evidence_preparation") is True
    )
    effects: list[str] = []
    for step in report.get("steps") or []:
        if not isinstance(step, dict):
            continue
        path = str(step.get("path") or "")
        name = str(step.get("name") or "")
        if "attempt-mutations" in path and not standing_prep:
            effects.append(f"{name}:unexpected_attempt_mutation_in_arm_preview")
        if "attempt-reservations" in path and not standing_prep:
            effects.append(f"{name}:unexpected_attempt_reservation_in_arm_preview")
        if "order-lifecycle-adapter-results" in path and not standing_prep:
            continue
        if "exchange-submit-execution" in path:
            effects.append(f"{name}:exchange_submit_execution")
        if "first-real-submit-actions" in path:
            effects.append(f"{name}:first_real_submit_action")
    if report.get("ready_for_real_submit_action") is True:
        effects.append("ready_for_real_submit_action_true")
    return sorted(set(effects))


def _attached_arm_report_forbidden_effects(report: dict[str, Any]) -> list[str]:
    """Check an existing arm report without counting its prior evidence writes."""

    effects: list[str] = []
    safety = _as_dict(report.get("safety"))
    for name in (
        "exchange_called",
        "exchange_order_submitted",
        "order_created",
        "order_lifecycle_submit_called",
        "withdrawal_or_transfer_created",
    ):
        if safety.get(name) is True:
            effects.append(f"arm_report.{name}")
    if report.get("ready_for_real_submit_action") is True:
        effects.append("arm_report.ready_for_real_submit_action_true")
    return sorted(set(effects))


def _report_has_step_path(report: dict[str, Any] | None, fragment: str) -> bool:
    if not isinstance(report, dict):
        return False
    return any(
        fragment in str(step.get("path") or "")
        for step in report.get("steps") or []
        if isinstance(step, dict)
    )


def _local_registration_readiness(
    *,
    authorization_id: str | None,
    arm_report: dict[str, Any] | None,
    disabled_report: dict[str, Any] | None,
) -> dict[str, Any]:
    """Classify the normal pre-mutation stop after arm + disabled smoke."""

    if not arm_report and not disabled_report:
        return {
            "classification": "not_evaluated",
            "expected_non_mutating_preview_stop": False,
            "ready_for_local_registration_authorization_packet": False,
        }

    arm_blockers = [str(item) for item in (arm_report or {}).get("blockers") or []]
    arm_warnings = [str(item) for item in (arm_report or {}).get("warnings") or []]
    disabled_blockers = [
        str(item) for item in (disabled_report or {}).get("blockers") or []
    ]
    disabled_warnings = [
        str(item) for item in (disabled_report or {}).get("warnings") or []
    ]
    ids = {
        **_as_dict((arm_report or {}).get("ids")),
        **_as_dict((disabled_report or {}).get("ids")),
    }
    missing_evidence_ids = [
        key for key in LOCAL_REGISTRATION_REQUIRED_EVIDENCE_IDS if not _optional_id(ids, key)
    ]
    arm_stopped_before_attempt = (
        EXPECTED_LOCAL_REGISTRATION_ARM_BLOCKER in arm_blockers
        or EXPECTED_LOCAL_REGISTRATION_ARM_BLOCKER in arm_warnings
    )
    disabled_stopped_before_action = (
        EXPECTED_DISABLED_SMOKE_ADAPTER_BLOCKER in disabled_blockers
    )
    adapter_result_missing = _contains_text(
        disabled_warnings,
        EXPECTED_DISABLED_SMOKE_ADAPTER_DETAIL,
    ) or _contains_text(
        (disabled_report or {}).get("steps"),
        "runtimeexecutionorderlifecycleadapterresult_not_found",
    )
    expected_stop = (
        arm_stopped_before_attempt
        and disabled_stopped_before_action
        and adapter_result_missing
    )
    ready_for_packet = (
        bool(authorization_id)
        and expected_stop
        and not missing_evidence_ids
    )
    if ready_for_packet:
        classification = "ready_for_standing_authorized_operation_layer_evidence_prep"
    elif expected_stop:
        classification = "expected_non_mutating_preview_stop_missing_evidence"
    else:
        classification = "not_ready_for_local_registration_authorization_packet"

    return {
        "classification": classification,
        "expected_non_mutating_preview_stop": expected_stop,
        "ready_for_local_registration_authorization_packet": ready_for_packet,
        "ready_for_standing_authorized_operation_layer_evidence_prep": ready_for_packet,
        "authorization_id_present": bool(authorization_id),
        "arm_stopped_before_attempt_consumption": arm_stopped_before_attempt,
        "disabled_smoke_stopped_before_first_real_submit_action": (
            disabled_stopped_before_action
        ),
        "missing_order_lifecycle_adapter_result_proven": adapter_result_missing,
        "required_evidence_ids_present": not missing_evidence_ids,
        "missing_evidence_ids": missing_evidence_ids,
        "next_mutating_stage": (
            "standing_authorized_attempt_consumption_local_registration_"
            "and_exchange_submit_evidence_preparation"
        ),
        "requires_fresh_real_signal_revalidation": True,
        "must_not_consume_attempt_for_sample_or_stale_signal": True,
        "does_not_authorize": [
            "exchange order placement",
            "OrderLifecycle submit",
            "withdrawal or transfer",
        ],
    }


def _contains_text(values: Any, expected: str) -> bool:
    needle = expected.lower()
    if isinstance(values, str):
        return needle in values.lower()
    if isinstance(values, Mapping):
        return any(_contains_text(value, expected) for value in values.values())
    if isinstance(values, list):
        return any(_contains_text(value, expected) for value in values)
    return needle in str(values or "").lower()


def build_followup_packet(
    args: argparse.Namespace,
    *,
    loop_packet: dict[str, Any] | None = None,
    arm_preview_runner: Callable[[str, argparse.Namespace], dict[str, Any]]
    | None = None,
    attempt_policy_preflight_runner: Callable[[str, argparse.Namespace], dict[str, Any]]
    | None = None,
    attempt_policy_preparer: Callable[[str, argparse.Namespace], dict[str, Any]]
    | None = None,
    disabled_smoke_runner: Callable[[str, argparse.Namespace], dict[str, Any]]
    | None = None,
) -> dict[str, Any]:
    packet = loop_packet or _load_json_object(Path(args.loop_packet_json).expanduser())
    latest = _latest_summary(packet)
    status = str(packet.get("status") or latest.get("status") or "unknown")
    authorization_id = _prepared_authorization_id(packet)
    loop_forbidden = _loop_forbidden_effects(packet)
    blockers: list[str] = []
    warnings: list[str] = []
    arm_report: dict[str, Any] | None = None
    arm_report_json_used = False
    arm_forbidden: list[str] = []
    attempt_policy_preflight: dict[str, Any] | None = None
    attempt_policy_report: dict[str, Any] | None = None
    disabled_report: dict[str, Any] | None = None
    disabled_forbidden: list[str] = []
    local_registration_readiness: dict[str, Any] = {
        "classification": "not_evaluated",
        "expected_non_mutating_preview_stop": False,
        "ready_for_local_registration_authorization_packet": False,
    }

    if loop_forbidden:
        blockers.append("loop_packet_contains_forbidden_effects")
    if status == READY_FOR_PREPARE_STATUS:
        followup_status = "ready_for_prepare_records"
    elif (
        status == "waiting_for_signal"
        and packet.get("stop_reason") == MAX_ITERATIONS_EXHAUSTED
    ):
        followup_status = "observation_window_complete_no_signal"
    elif status != READY_STATUS:
        followup_status = "waiting_for_ready_final_gate_preflight"
    elif not authorization_id:
        followup_status = "blocked"
        blockers.append("prepared_authorization_id_missing")
    elif not args.allow_disabled_smoke:
        followup_status = "ready_for_disabled_smoke"
        blockers.append("allow_disabled_smoke_flag_required")
    elif blockers:
        followup_status = "blocked"
    else:
        arm_report = _load_arm_report(args)
        arm_report_json_used = arm_report is not None
        if arm_report is not None:
            arm_forbidden = _attached_arm_report_forbidden_effects(arm_report)
            warnings.extend(
                f"arm_report:{item}"
                for item in arm_report.get("blockers") or []
            )
            warnings.extend(
                f"arm_report:{item}"
                for item in arm_report.get("warnings") or []
            )
            if arm_forbidden:
                blockers.append("arm_report_contains_forbidden_effects")
        elif args.allow_arm_preview:
            if getattr(args, "allow_attempt_policy_prepare", False):
                preflight_runner = attempt_policy_preflight_runner or (
                    lambda auth_id, parsed_args: _run_attempt_policy_preflight(
                        authorization_id=auth_id,
                        args=parsed_args,
                    )
                )
                attempt_policy_preflight = preflight_runner(authorization_id, args)
                warnings.extend(
                    f"attempt_policy_preflight:{item}"
                    for item in attempt_policy_preflight.get("warnings") or []
                )
                if attempt_policy_preflight.get("status") != "pass":
                    blockers.extend(
                        f"attempt_policy_preflight:{item}"
                        for item in attempt_policy_preflight.get("blockers") or []
                    )
                    blockers.append("attempt_policy_preflight_not_passed")
                else:
                    warnings.append(
                        "attempt_policy_prepare_deferred_until_operation_layer_submit"
                    )
            if not blockers:
                arm_runner = arm_preview_runner or (
                    lambda auth_id, parsed_args: _run_arm_preview(
                        authorization_id=auth_id,
                        args=parsed_args,
                        evidence_ids=_as_dict((attempt_policy_report or {}).get("ids")),
                    )
                )
                arm_report = arm_runner(authorization_id, args)
                arm_forbidden = _arm_preview_forbidden_effects(arm_report)
                warnings.extend(
                    f"arm_preview:{item}"
                    for item in arm_report.get("blockers") or []
                )
                warnings.extend(
                    f"arm_preview:{item}"
                    for item in arm_report.get("warnings") or []
                )
                if arm_forbidden:
                    blockers.append("arm_preview_contains_forbidden_effects")
        if blockers:
            disabled_report = None
        elif disabled_smoke_runner is not None:
            disabled_report = disabled_smoke_runner(authorization_id, args)
        else:
            disabled_report = _run_disabled_smoke(
                authorization_id=authorization_id,
                args=args,
                evidence_ids=_as_dict((arm_report or {}).get("ids")),
            )
        if disabled_report is not None:
            disabled_forbidden = _disabled_smoke_forbidden_effects(disabled_report)
            blockers.extend(
                f"disabled_smoke:{item}"
                for item in disabled_report.get("blockers") or []
            )
            warnings.extend(
                f"disabled_smoke:{item}"
                for item in disabled_report.get("warnings") or []
            )
            if disabled_forbidden:
                blockers.append("disabled_smoke_contains_forbidden_effects")
        followup_status = (
            "disabled_smoke_completed"
            if not blockers
            else "disabled_smoke_blocked"
        )
        local_registration_readiness = _local_registration_readiness(
            authorization_id=authorization_id,
            arm_report=arm_report,
            disabled_report=disabled_report,
        )

    return {
        "scope": "runtime_active_observation_followup",
        "status": followup_status,
        "source_loop_status": status,
        "source_loop_stop_reason": packet.get("stop_reason"),
        "prepared_authorization_id": authorization_id,
        "attempt_policy_preflight_report": attempt_policy_preflight,
        "attempt_policy_prepare_report": attempt_policy_report,
        "arm_preview_report": arm_report,
        "disabled_smoke_report": disabled_report,
        "local_registration_readiness": local_registration_readiness,
        "blockers": blockers,
        "warnings": warnings,
        "operator_command_plan": {
            "not_executed": followup_status
            not in {"disabled_smoke_completed", "disabled_smoke_blocked"},
            "arm_preview_called": arm_report is not None and not arm_report_json_used,
            "arm_report_attached": arm_report is not None,
            "arm_report_json_used": arm_report_json_used,
            "attempt_policy_preflight_called": attempt_policy_preflight is not None,
            "attempt_policy_prepare_called": attempt_policy_report is not None,
            "disabled_smoke_called": disabled_report is not None,
            "owner_confirmed_for_first_real_submit_action": False,
            "next_step": _next_step(
                followup_status,
                local_registration_readiness=local_registration_readiness,
            ),
            "local_registration_authorization_packet_script": (
                "scripts/runtime_first_real_submit_api_flow.py"
                if local_registration_readiness.get(
                    "expected_non_mutating_preview_stop"
                )
                else None
            ),
            "standing_authorized_operation_layer_evidence_prep_allowed": bool(
                getattr(args, "allow_standing_operation_layer_evidence_prep", False)
            ),
            "mutating_attempt_consumption_allowed_by_this_packet": (
                bool(
                    getattr(
                        args,
                        "allow_standing_operation_layer_evidence_prep",
                        False,
                    )
                )
            ),
            "requires_fresh_real_signal_revalidation_before_mutation": (
                local_registration_readiness.get(
                    "requires_fresh_real_signal_revalidation"
                )
                is True
            ),
        },
        "safety_invariants": {
            "loop_packet_read_only": True,
            "arm_preview_called": arm_report is not None and not arm_report_json_used,
            "arm_report_attached": arm_report is not None,
            "arm_report_json_used": arm_report_json_used,
            "attempt_policy_preflight_called": attempt_policy_preflight is not None,
            "attempt_policy_prepare_called": attempt_policy_report is not None,
            "disabled_smoke_called": disabled_report is not None,
            "owner_confirmed_for_first_real_submit_action": False,
            "real_submit_requested": False,
            "exchange_called": False,
            "exchange_order_submitted": False,
            "order_created": False,
            "order_lifecycle_submit_called": False,
            "attempt_counter_mutated": (
                (
                    attempt_policy_report is not None
                    and _as_dict(attempt_policy_report.get("safety")).get(
                        "mutates_attempt_counter"
                    )
                    is True
                )
                or _report_has_step_path(
                    arm_report,
                    "runtime-execution-attempt-mutations",
                )
            ),
            "runtime_budget_mutated": (
                (
                    attempt_policy_report is not None
                    and _as_dict(attempt_policy_report.get("safety")).get(
                        "mutates_runtime_budget"
                    )
                    is True
                )
                or _report_has_step_path(
                    arm_report,
                    "runtime-execution-attempt-mutations",
                )
            ),
            "standing_authorized_operation_layer_evidence_prep_called": (
                _as_dict((arm_report or {}).get("safety")).get(
                    "standing_authorized_scoped_evidence_preparation"
                )
                is True
            ),
            "local_registration_recorded": _report_has_step_path(
                arm_report,
                "runtime-execution-order-lifecycle-adapter-results",
            ),
            "exchange_submit_adapter_armed": _report_has_step_path(
                arm_report,
                "runtime-execution-exchange-submit-adapter-results",
            ),
            "withdrawal_or_transfer_created": False,
            "loop_forbidden_effects": loop_forbidden,
            "arm_preview_forbidden_effects": arm_forbidden,
            "disabled_smoke_forbidden_effects": disabled_forbidden,
        },
}


def _dedupe_text(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value)
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def _operation_layer_arm_evidence_path(args: argparse.Namespace, output_path: Path) -> Path:
    if args.operation_layer_arm_evidence_json:
        return Path(args.operation_layer_arm_evidence_json).expanduser()
    return output_path.parent / "operation-layer-arm-evidence.json"


def _operation_layer_arm_evidence_payload(packet: Mapping[str, Any]) -> dict[str, Any]:
    arm_report = packet.get("arm_preview_report")
    if isinstance(arm_report, dict):
        return dict(arm_report)
    return {
        "scope": "runtime_operation_layer_arm_evidence",
        "status": "no_current_arm_preview",
        "source_followup_status": packet.get("status"),
        "prepared_authorization_id": packet.get("prepared_authorization_id"),
        "blockers": [],
        "warnings": [],
        "ids": {},
        "safety": {
            "stale_arm_evidence_cleared": True,
            "exchange_called": False,
            "exchange_order_submitted": False,
            "order_created": False,
            "order_lifecycle_submit_called": False,
            "real_submit_requested": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _next_step(
    status: str,
    *,
    local_registration_readiness: Mapping[str, Any] | None = None,
) -> str:
    readiness = local_registration_readiness or {}
    if status == "ready_for_prepare_records":
        return "review_ready_signal_then_continue_prepare_record_path"
    if status == "observation_window_complete_no_signal":
        return "review_no_signal_window_or_start_new_observation"
    if status == "waiting_for_ready_final_gate_preflight":
        return "continue_active_observation_loop"
    if status == "ready_for_disabled_smoke":
        return "rerun_with_allow_disabled_smoke_after_operator_review"
    if status == "disabled_smoke_completed":
        return "review_disabled_smoke_report_then_wait_for_explicit_real_submit_authorization"
    if status == "disabled_smoke_blocked":
        if readiness.get("ready_for_local_registration_authorization_packet") is True:
            return (
                "for_fresh_real_signal_run_standing_authorized_operation_layer_"
                "evidence_prep_then_rerun_action_time_finalgate"
            )
        if readiness.get("expected_non_mutating_preview_stop") is True:
            return (
                "resolve_missing_evidence_before_local_registration_authorization_packet"
            )
        return "review_disabled_smoke_blockers"
    return "resolve_followup_blockers"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run non-executing follow-up after active observation reaches "
            "ready_for_final_gate_preflight."
        ),
    )
    parser.add_argument("--loop-packet-json", required=True)
    parser.add_argument("--output-json")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--env-file")
    parser.add_argument("--allow-arm-preview", action="store_true")
    parser.add_argument(
        "--allow-attempt-policy-prepare",
        action="store_true",
        help=(
            "For a fresh prepared authorization, run the official controlled-submit "
            "preflight before arm preview. Attempt reservation/mutation is deferred "
            "until the official Operation Layer submit path."
        ),
    )
    parser.add_argument(
        "--operation-layer-arm-evidence-json",
        help=(
            "Write the current arm preview report for the resume dispatcher. "
            "Defaults to operation-layer-arm-evidence.json next to --output-json."
        ),
    )
    parser.add_argument(
        "--arm-report-json",
        help=(
            "Reuse an existing successful arm report as the evidence source for "
            "disabled smoke instead of running a new arm preview."
        ),
    )
    parser.add_argument("--allow-disabled-smoke", action="store_true")
    parser.add_argument(
        "--allow-standing-operation-layer-evidence-prep",
        action="store_true",
        help=(
            "For a fresh live signal, allow standing-authorization bounded "
            "attempt/local-registration/exchange-arm evidence preparation. "
            "This never calls the first-real-submit action."
        ),
    )
    parser.add_argument(
        "--skip-disabled-smoke-prerequisite-probe",
        action="store_true",
        help="Do not call evidence preparation after a disabled-smoke 404.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    packet = build_followup_packet(args)
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str)
            + "\n",
            encoding="utf-8",
        )
        arm_evidence_path = _operation_layer_arm_evidence_path(args, output_path)
        arm_evidence_path.parent.mkdir(parents=True, exist_ok=True)
        arm_evidence_path.write_text(
            json.dumps(
                _operation_layer_arm_evidence_payload(packet),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                default=str,
            )
            + "\n",
            encoding="utf-8",
        )
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if packet["status"] in {
        "observation_window_complete_no_signal",
        "waiting_for_ready_final_gate_preflight",
        "ready_for_prepare_records",
        "ready_for_disabled_smoke",
        "disabled_smoke_completed",
        "disabled_smoke_blocked",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
