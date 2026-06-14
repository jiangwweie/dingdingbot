#!/usr/bin/env python3
"""Build a non-executing exchange-arm authorization packet.

This packet sits after local-registration prep.  It freezes the next Owner
confirmation boundary for exchange-submit adapter arm, but it never calls the
Trading Console API and never submits to exchange.
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
    EXCHANGE_ARM_APPROVAL_ENV,
    LOCAL_REGISTRATION_APPROVAL_ENV,
    _exchange_arm_approval_value,
    _local_registration_approval_value,
)


APPROVAL_ENV = EXCHANGE_ARM_APPROVAL_ENV


class ExchangeArmAuthorizationPacketError(RuntimeError):
    """Raised when the exchange-arm packet cannot be built."""


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    packet = build_exchange_arm_authorization_packet(
        local_registration_report=_load_json_object(
            Path(args.local_registration_report_path)
        ),
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
    return 0 if packet["checks"]["ready_for_owner_exchange_arm_authorization"] else 2


def build_exchange_arm_authorization_packet(
    *,
    local_registration_report: dict[str, Any],
    authorization_id: str | None = None,
    owner_confirmation_value: str | None = None,
    api_base: str = DEFAULT_API_BASE,
    env_file: str | None = None,
) -> dict[str, Any]:
    """Create an auditable boundary for exchange-submit adapter arm."""

    ids = _as_dict(local_registration_report.get("ids"))
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

    report_is_arm = (
        local_registration_report.get("script") == "runtime_first_real_submit_api_flow"
        and local_registration_report.get("mode") == "arm"
    )
    exchange_arm_blocked = "owner_runtime_exchange_arm_env_confirmation_missing" in list(
        local_registration_report.get("blockers") or []
    )
    required_local_ids = [
        "attempt_outcome_policy_id",
        "local_registration_action_authorization_id",
        "local_registration_enablement_decision_id",
        "local_registration_adapter_result_id",
    ]
    local_registration_ids_present = all(
        _optional_str(ids.get(key)) for key in required_local_ids
    )
    exchange_not_already_armed = not any(
        _optional_str(ids.get(key))
        for key in [
            "exchange_submit_action_authorization_id",
            "exchange_submit_enablement_decision_id",
            "exchange_submit_adapter_result_id",
            "disabled_first_real_submit_execution_result_id",
            "execution_result_id",
        ]
    )
    forbidden_steps_absent = not _contains_any_step(
        local_registration_report.get("steps"),
        [
            "record_exchange_submit_action_authorization",
            "preview_exchange_submit_enablement",
            "record_exchange_submit_adapter_result",
            "preview_disabled_first_real_submit_action",
            "execute_first_real_submit_action",
        ],
    )

    blockers: list[str] = []
    if not report_is_arm:
        blockers.append("local_registration_arm_report_required")
    if not normalized_authorization_id:
        blockers.append("authorization_id_missing")
    if not exchange_arm_blocked:
        blockers.append("exchange_arm_confirmation_blocker_missing")
    if not local_registration_ids_present:
        blockers.append("local_registration_evidence_ids_missing")
    if not exchange_not_already_armed:
        blockers.append("exchange_or_submit_evidence_already_present")
    if not forbidden_steps_absent:
        blockers.append("exchange_or_submit_step_already_called")
    if supplied_confirmation and not confirmation_matches:
        blockers.append("owner_confirmation_value_mismatch")

    ready_for_owner_authorization = (
        report_is_arm
        and bool(normalized_authorization_id)
        and exchange_arm_blocked
        and local_registration_ids_present
        and exchange_not_already_armed
        and forbidden_steps_absent
        and "owner_confirmation_value_mismatch" not in blockers
    )
    action_authorized = ready_for_owner_authorization and confirmation_matches

    if not ready_for_owner_authorization:
        status = "blocked_before_exchange_arm_authorization"
    elif action_authorized:
        status = "owner_exchange_arm_authorization_packet_ready"
    else:
        status = "waiting_for_owner_exchange_arm_authorization"

    return {
        "status": status,
        "scope": "runtime_first_real_submit_exchange_arm_authorization_packet",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "authorization_id": normalized_authorization_id,
        "evidence": {
            "arm_report_blockers": list(local_registration_report.get("blockers") or []),
            "available_local_registration_ids": {
                key: ids.get(key) for key in required_local_ids if ids.get(key)
            },
            "exchange_or_submit_ids_present": not exchange_not_already_armed,
            "forbidden_exchange_or_submit_steps_absent": forbidden_steps_absent,
        },
        "owner_confirmation": {
            "env_name": APPROVAL_ENV,
            "required_value": expected_confirmation,
            "supplied_value_matches": confirmation_matches,
            "action_authorized": action_authorized,
            "must_be_supplied_out_of_band_before_exchange_arm_command": (
                not action_authorized
            ),
        },
        "checks": {
            "ready_for_owner_exchange_arm_authorization": (
                ready_for_owner_authorization
            ),
            "action_authorized": action_authorized,
            "local_registration_arm_report_valid": report_is_arm,
            "exchange_arm_confirmation_blocker_present": exchange_arm_blocked,
            "local_registration_evidence_ids_present": (
                local_registration_ids_present
            ),
            "exchange_not_already_armed": exchange_not_already_armed,
            "forbidden_exchange_or_submit_steps_absent": forbidden_steps_absent,
            "authorization_id_present": bool(normalized_authorization_id),
            "owner_confirmation_value_matches": confirmation_matches,
            "blockers": _dedupe(blockers),
            "warnings": [],
        },
        "operator_command_plan": _command_plan(
            authorization_id=normalized_authorization_id,
            api_base=api_base,
            env_file=env_file,
            local_registration_confirmation=_local_registration_approval_value(
                normalized_authorization_id
            )
            if normalized_authorization_id
            else None,
            exchange_arm_confirmation=expected_confirmation,
            action_authorized=action_authorized,
        ),
        "owner_gate": {
            "packet_build_only": True,
            "requires_separate_exchange_arm_step": True,
            "authorized_exchange_arm_step_available": action_authorized,
            "authorized_step_scope_if_confirmed": [
                "exchange gateway readiness record",
                "exchange submit action authorization",
                "exchange submit enablement preview",
                "exchange submit adapter arm record",
                "first-real-submit enablement packet preview",
            ],
            "does_not_authorize": [
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
            "exchange_submit_adapter_armed": False,
            "first_real_submit_action_called": False,
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
    local_registration_confirmation: str | None,
    exchange_arm_confirmation: str | None,
    action_authorized: bool,
) -> dict[str, Any]:
    if not authorization_id:
        return {
            "not_executed": True,
            "authorization_id_required": True,
            "authorized_exchange_arm_command": None,
        }

    base = [
        "python3",
        "scripts/runtime_first_real_submit_api_flow.py",
        "--api-base",
        api_base,
    ]
    if env_file:
        base.extend(["--env-file", env_file])
    command = [
        f"{LOCAL_REGISTRATION_APPROVAL_ENV}={local_registration_confirmation}",
        f"{APPROVAL_ENV}={exchange_arm_confirmation}",
        *base,
        "--mode",
        "arm",
        "--authorization-id",
        authorization_id,
    ]
    return {
        "not_executed": True,
        "uses_official_api_flow": True,
        "api_base_env": API_BASE_ENV,
        "api_base": api_base,
        "authorized_exchange_arm_command": command if action_authorized else None,
        "required_env": [
            {
                "name": LOCAL_REGISTRATION_APPROVAL_ENV,
                "value": local_registration_confirmation,
            },
            {
                "name": APPROVAL_ENV,
                "value": exchange_arm_confirmation,
            },
        ],
        "authorized_command_records_attempt_consumption": False,
        "authorized_command_non_mutating_arm_only": True,
        "authorized_command_may_reuse_existing_attempt_policy": True,
        "authorized_command_does_not_execute_first_real_submit": True,
        "authorized_command_not_available_until_owner_confirmation_matches": (
            not action_authorized
        ),
    }


def _approval_value(authorization_id: str) -> str:
    return _exchange_arm_approval_value(authorization_id)


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ExchangeArmAuthorizationPacketError(
            f"packet unreadable: {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ExchangeArmAuthorizationPacketError(
            f"packet is not JSON: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise ExchangeArmAuthorizationPacketError(
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


def _contains_any_step(value: Any, names: list[str]) -> bool:
    wanted = set(names)
    for item in value or []:
        if isinstance(item, dict) and item.get("name") in wanted:
            return True
    return False


def _dedupe(values: list[str]) -> list[str]:
    return sorted(dict.fromkeys(values))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a non-executing exchange-arm authorization packet."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument("--local-registration-report-path", required=True)
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
        "ready_for_owner_exchange_arm_authorization="
        + str(checks["ready_for_owner_exchange_arm_authorization"]).lower()
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
    except ExchangeArmAuthorizationPacketError as exc:
        print(
            f"exchange_arm_authorization_packet_error={exc}",
            file=sys.stderr,
        )
        raise SystemExit(2)
