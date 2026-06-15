#!/usr/bin/env python3
"""Build a non-executing local-registration authorization packet.

This packet sits between disabled first-real-submit smoke and any remote command
that would consume an attempt or register local order records.  It never calls
the Trading Console API; it only freezes the next action boundary.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORT))

from scripts.runtime_first_real_submit_api_flow import (  # noqa: E402
    API_BASE_ENV,
    DEFAULT_API_BASE,
    LOCAL_REGISTRATION_APPROVAL_ENV,
    _local_registration_approval_value,
)


APPROVAL_ENV = LOCAL_REGISTRATION_APPROVAL_ENV


class LocalRegistrationAuthorizationPacketError(RuntimeError):
    """Raised when the local-registration packet cannot be built."""


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    packet = build_local_registration_authorization_packet(
        disabled_smoke_report=_load_json_object(Path(args.disabled_smoke_report_path)),
        authorization_id=args.authorization_id,
        owner_confirmation_value=args.owner_confirmation_value,
        api_base=args.api_base,
        env_file=args.env_file,
    )
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_human(packet)
    return 0 if packet["checks"]["ready_for_owner_local_registration_authorization"] else 2


def build_local_registration_authorization_packet(
    *,
    disabled_smoke_report: dict[str, Any],
    authorization_id: str | None = None,
    owner_confirmation_value: str | None = None,
    api_base: str = DEFAULT_API_BASE,
    env_file: str | None = None,
) -> dict[str, Any]:
    """Create an auditable boundary for attempt/local-registration prep."""

    ids = _as_dict(disabled_smoke_report.get("ids"))
    normalized_authorization_id = _first_present(
        authorization_id,
        ids.get("authorization_id"),
    )
    expected_confirmation = (
        _approval_value(normalized_authorization_id)
        if normalized_authorization_id
        else None
    )
    supplied_confirmation = _optional_str(owner_confirmation_value)
    confirmation_matches = bool(
        expected_confirmation and supplied_confirmation == expected_confirmation
    )

    report_is_disabled_smoke = (
        disabled_smoke_report.get("script") == "runtime_first_real_submit_api_flow"
        and disabled_smoke_report.get("mode") == "disabled-smoke"
    )
    first_action_blocked = "preview_disabled_first_real_submit_action_http_404" in list(
        disabled_smoke_report.get("blockers") or []
    )
    missing_adapter_result = _contains_text(
        disabled_smoke_report.get("warnings"),
        "RuntimeExecutionOrderLifecycleAdapterResult not found",
    ) or _contains_text(
        disabled_smoke_report.get("steps"),
        "runtimeexecutionorderlifecycleadapterresult_not_found",
    )
    evidence_probe_present = any(
        isinstance(step, dict) and step.get("name") == "prepare_machine_evidence"
        for step in disabled_smoke_report.get("steps") or []
    )
    required_evidence_ids = [
        "trusted_submit_fact_snapshot_id",
        "submit_idempotency_policy_id",
        "protection_creation_failure_policy_id",
    ]
    evidence_ids_present = all(_optional_str(ids.get(key)) for key in required_evidence_ids)

    blockers: list[str] = []
    if not report_is_disabled_smoke:
        blockers.append("disabled_smoke_report_required")
    if not normalized_authorization_id:
        blockers.append("authorization_id_missing")
    if not first_action_blocked:
        blockers.append("disabled_first_real_submit_action_blocker_missing")
    if not missing_adapter_result:
        blockers.append("missing_adapter_result_prerequisite_not_proven")
    if not evidence_probe_present:
        blockers.append("prepare_machine_evidence_probe_missing")
    if not evidence_ids_present:
        blockers.append("required_submit_evidence_ids_missing")
    if supplied_confirmation and not confirmation_matches:
        blockers.append("owner_confirmation_value_mismatch")

    ready_for_owner_authorization = (
        report_is_disabled_smoke
        and bool(normalized_authorization_id)
        and first_action_blocked
        and missing_adapter_result
        and evidence_probe_present
        and evidence_ids_present
        and "owner_confirmation_value_mismatch" not in blockers
    )
    action_authorized = ready_for_owner_authorization and confirmation_matches

    if not ready_for_owner_authorization:
        status = "blocked_before_local_registration_authorization"
    elif action_authorized:
        status = "owner_local_registration_authorization_packet_ready"
    else:
        status = "waiting_for_owner_local_registration_authorization"

    return {
        "status": status,
        "scope": "runtime_first_real_submit_local_registration_authorization_packet",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "authorization_id": normalized_authorization_id,
        "evidence": {
            "disabled_smoke_mode": disabled_smoke_report.get("mode"),
            "disabled_smoke_blockers": list(
                disabled_smoke_report.get("blockers") or []
            ),
            "disabled_smoke_warnings": list(
                disabled_smoke_report.get("warnings") or []
            ),
            "available_evidence_ids": {
                key: ids.get(key)
                for key in [
                    *required_evidence_ids,
                    "post_submit_budget_settlement_persistence_evidence_id",
                ]
                if ids.get(key)
            },
            "missing_prerequisite": (
                "RuntimeExecutionOrderLifecycleAdapterResult"
                if missing_adapter_result
                else None
            ),
        },
        "owner_confirmation": {
            "env_name": APPROVAL_ENV,
            "required_value": expected_confirmation,
            "supplied_value_matches": confirmation_matches,
            "action_authorized": action_authorized,
            "must_be_supplied_out_of_band_before_mutating_command": (
                not action_authorized
            ),
        },
        "checks": {
            "ready_for_owner_local_registration_authorization": (
                ready_for_owner_authorization
            ),
            "action_authorized": action_authorized,
            "disabled_smoke_report_valid": report_is_disabled_smoke,
            "first_real_submit_action_blocked": first_action_blocked,
            "missing_adapter_result_prerequisite_proven": missing_adapter_result,
            "prepare_machine_evidence_probe_present": evidence_probe_present,
            "required_submit_evidence_ids_present": evidence_ids_present,
            "authorization_id_present": bool(normalized_authorization_id),
            "owner_confirmation_value_matches": confirmation_matches,
            "blockers": _dedupe(blockers),
            "warnings": [],
        },
        "operator_command_plan": _command_plan(
            authorization_id=normalized_authorization_id,
            api_base=api_base,
            env_file=env_file,
            expected_confirmation=expected_confirmation,
            action_authorized=action_authorized,
        ),
        "owner_gate": {
            "packet_build_only": True,
            "requires_separate_mutating_step": True,
            "authorized_mutating_step_available": action_authorized,
            "authorized_mutating_step_scope_if_confirmed": [
                "attempt reservation",
                "attempt mutation",
                "attempt outcome policy",
                "order lifecycle handoff draft",
                "local registration action authorization",
                "local registration enablement preview",
                "local order registration result",
            ],
            "does_not_authorize": [
                "exchange submit adapter arm",
                "first-real-submit action",
                "real exchange order placement",
                "OrderLifecycle submit",
                "withdrawal or transfer",
            ],
        },
        "safety_invariants": {
            "packet_build_only": True,
            "api_called": False,
            "remote_files_modified": False,
            "database_connected": False,
            "runtime_started": False,
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "local_order_registration_executed": False,
            "order_lifecycle_called": False,
            "order_lifecycle_submit_called": False,
            "exchange_called": False,
            "exchange_order_submitted": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _command_plan(
    *,
    authorization_id: str | None,
    api_base: str,
    env_file: str | None,
    expected_confirmation: str | None,
    action_authorized: bool,
) -> dict[str, Any]:
    if not authorization_id:
        return {
            "not_executed": True,
            "authorization_id_required": True,
            "preview_command": None,
            "authorized_local_registration_command": None,
        }

    base = [
        "python3",
        "scripts/runtime_first_real_submit_api_flow.py",
        "--api-base",
        api_base,
    ]
    if env_file:
        base.extend(["--env-file", env_file])
    preview = base + [
        "--mode",
        "arm",
        "--authorization-id",
        authorization_id,
        "--skip-exchange-arm",
    ]
    authorized_preview = [
        f"{APPROVAL_ENV}={expected_confirmation}",
        *base,
        "--mode",
        "arm",
        "--authorization-id",
        authorization_id,
        "--skip-exchange-arm",
    ]
    return {
        "not_executed": True,
        "uses_official_api_flow": True,
        "api_base_env": API_BASE_ENV,
        "api_base": api_base,
        "preview_command": preview,
        "authorized_local_registration_command": (
            authorized_preview if action_authorized else None
        ),
        "authorized_command_env_required": {
            "name": APPROVAL_ENV,
            "value": expected_confirmation,
        },
        "authorized_command_records_attempt_consumption": False,
        "authorized_command_non_mutating_arm_only": True,
        "authorized_command_skips_exchange_arm": True,
        "authorized_command_not_available_until_owner_confirmation_matches": (
            not action_authorized
        ),
    }


def _approval_value(authorization_id: str) -> str:
    return _local_registration_approval_value(authorization_id)


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise LocalRegistrationAuthorizationPacketError(
            f"packet unreadable: {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise LocalRegistrationAuthorizationPacketError(
            f"packet is not JSON: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise LocalRegistrationAuthorizationPacketError(
            f"packet must be a JSON object: {path}"
        )
    return payload


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_present(*values: Any) -> str | None:
    for value in values:
        normalized = _optional_str(value)
        if normalized:
            return normalized
    return None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _contains_text(value: Any, needle: str) -> bool:
    haystack = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return needle in haystack


def _dedupe(values: list[str]) -> list[str]:
    return sorted(dict.fromkeys(values))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a non-executing local-registration authorization packet."
        )
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument("--disabled-smoke-report-path", required=True)
    parser.add_argument("--authorization-id")
    parser.add_argument("--owner-confirmation-value")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--env-file")
    parser.add_argument("--output-json")
    return parser.parse_args(argv)


def _print_human(packet: dict[str, Any]) -> None:
    checks = packet["checks"]
    print(f"status={packet['status']}")
    print(
        "ready_for_owner_local_registration_authorization="
        + str(checks["ready_for_owner_local_registration_authorization"]).lower()
    )
    print("action_authorized=" + str(checks["action_authorized"]).lower())
    print(f"authorization_id={packet['authorization_id']}")
    if checks["blockers"]:
        print("blockers=" + ",".join(checks["blockers"]))
    if checks["warnings"]:
        print("warnings=" + ",".join(checks["warnings"]))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LocalRegistrationAuthorizationPacketError as exc:
        print(
            f"local_registration_authorization_packet_error={exc}",
            file=sys.stderr,
        )
        raise SystemExit(2)
