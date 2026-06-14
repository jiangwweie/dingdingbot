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
from pathlib import Path
import sys
from typing import Any, Callable, Mapping

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.runtime_first_real_submit_api_flow import (  # noqa: E402
    DEFAULT_API_BASE,
    FirstRealSubmitApiFlow,
    FlowConfig,
    UrlLibApiClient,
    _load_env_file,
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
) -> dict[str, Any]:
    _load_env_file(args.env_file)
    config = FlowConfig(
        api_base=args.api_base,
        mode="arm",
        env_file=args.env_file,
        authorization_id=authorization_id,
        record_attempt_consumption=False,
        preview_disabled_first_real_submit_action=False,
    )
    return FirstRealSubmitApiFlow(
        client=UrlLibApiClient(api_base=config.api_base),
        config=config,
    ).run()


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
    effects: list[str] = []
    for step in report.get("steps") or []:
        if not isinstance(step, dict):
            continue
        path = str(step.get("path") or "")
        name = str(step.get("name") or "")
        if "attempt-mutations" in path:
            effects.append(f"{name}:attempt_mutation")
        if "attempt-reservations" in path:
            effects.append(f"{name}:attempt_reservation")
        if "local-registration-action-authorizations" in path:
            effects.append(f"{name}:local_registration_authorization")
        if "exchange-submit-action-authorizations" in path:
            effects.append(f"{name}:exchange_submit_authorization")
        if "exchange-submit-adapter-results" in path:
            effects.append(f"{name}:exchange_submit_adapter_arm")
        if "order-lifecycle-adapter-results" in path:
            effects.append(f"{name}:order_lifecycle_adapter_result")
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
        classification = "ready_for_owner_local_registration_authorization_packet"
    elif expected_stop:
        classification = "expected_non_mutating_preview_stop_missing_evidence"
    else:
        classification = "not_ready_for_local_registration_authorization_packet"

    return {
        "classification": classification,
        "expected_non_mutating_preview_stop": expected_stop,
        "ready_for_local_registration_authorization_packet": ready_for_packet,
        "authorization_id_present": bool(authorization_id),
        "arm_stopped_before_attempt_consumption": arm_stopped_before_attempt,
        "disabled_smoke_stopped_before_first_real_submit_action": (
            disabled_stopped_before_action
        ),
        "missing_order_lifecycle_adapter_result_proven": adapter_result_missing,
        "required_evidence_ids_present": not missing_evidence_ids,
        "missing_evidence_ids": missing_evidence_ids,
        "next_mutating_stage": "attempt_consumption_and_local_order_registration",
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
            arm_runner = arm_preview_runner or (
                lambda auth_id, parsed_args: _run_arm_preview(
                    authorization_id=auth_id,
                    args=parsed_args,
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
        if disabled_smoke_runner is not None:
            disabled_report = disabled_smoke_runner(authorization_id, args)
        else:
            disabled_report = _run_disabled_smoke(
                authorization_id=authorization_id,
                args=args,
                evidence_ids=_as_dict((arm_report or {}).get("ids")),
            )
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
            "disabled_smoke_called": disabled_report is not None,
            "owner_confirmed_for_first_real_submit_action": False,
            "next_step": _next_step(
                followup_status,
                local_registration_readiness=local_registration_readiness,
            ),
            "local_registration_authorization_packet_script": (
                "scripts/build_runtime_first_real_submit_"
                "local_registration_authorization_packet.py"
                if local_registration_readiness.get(
                    "expected_non_mutating_preview_stop"
                )
                else None
            ),
            "mutating_attempt_consumption_allowed_by_this_packet": False,
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
            "disabled_smoke_called": disabled_report is not None,
            "owner_confirmed_for_first_real_submit_action": False,
            "real_submit_requested": False,
            "exchange_called": False,
            "exchange_order_submitted": False,
            "order_created": False,
            "order_lifecycle_submit_called": False,
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "loop_forbidden_effects": loop_forbidden,
            "arm_preview_forbidden_effects": arm_forbidden,
            "disabled_smoke_forbidden_effects": disabled_forbidden,
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
                "for_fresh_real_signal_build_local_registration_authorization_packet_"
                "then_owner_confirm_attempt_consumption"
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
        "--arm-report-json",
        help=(
            "Reuse an existing successful arm report as the evidence source for "
            "disabled smoke instead of running a new arm preview."
        ),
    )
    parser.add_argument("--allow-disabled-smoke", action="store_true")
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
