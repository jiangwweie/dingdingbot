#!/usr/bin/env python3
"""Build a non-executing first-real-submit action authorization packet.

This is the handoff layer after the final review packet. It freezes the exact
Owner confirmation value and the official API-flow command shape, but it never
calls the Trading Console API, never submits to exchange, never registers local
orders, and never mutates runtime attempts or budgets.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORT))

from scripts.runtime_first_real_submit_api_flow import (  # noqa: E402
    API_BASE_ENV,
    APPROVAL_ENV,
    DEFAULT_API_BASE,
    _approval_value,
)


class FirstRealSubmitActionAuthorizationPacketError(RuntimeError):
    """Raised when the action authorization packet cannot be built."""


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    packet = build_first_real_submit_action_authorization_packet(
        final_review_packet=_load_json_object(Path(args.final_review_packet_path)),
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
    return 0 if packet["checks"]["ready_for_owner_action_authorization"] else 2


def build_first_real_submit_action_authorization_packet(
    *,
    final_review_packet: dict[str, Any],
    authorization_id: str | None = None,
    owner_confirmation_value: str | None = None,
    api_base: str = DEFAULT_API_BASE,
    env_file: str | None = None,
) -> dict[str, Any]:
    """Create an auditable action boundary without executing it."""

    checks = _as_dict(final_review_packet.get("checks"))
    owner_gate = _as_dict(final_review_packet.get("owner_gate"))
    target_head = _optional_str(final_review_packet.get("target_head"))
    action_context = _as_dict(
        final_review_packet.get("first_real_submit_action_context")
    )
    normalized_authorization_id = _first_present(
        authorization_id,
        action_context.get("submit_authorization_id"),
    )
    expected_confirmation = (
        _approval_value(normalized_authorization_id)
        if normalized_authorization_id
        else None
    )
    supplied_confirmation = _optional_str(owner_confirmation_value)

    final_review_ready = (
        final_review_packet.get("status")
        == "ready_for_owner_first_real_submit_action_review"
        and checks.get("ready_for_owner_action_review") is True
        and checks.get("owner_action_ready") is True
        and not list(checks.get("blockers") or [])
        and not list(checks.get("forbidden_effects") or [])
        and owner_gate.get("final_review_only") is True
    )
    confirmation_matches = bool(
        expected_confirmation and supplied_confirmation == expected_confirmation
    )

    blockers: list[str] = []
    if not final_review_ready:
        blockers.append("final_review_not_ready_for_action_authorization")
    if not target_head:
        blockers.append("target_head_missing")
    if not normalized_authorization_id:
        blockers.append("submit_authorization_id_missing_for_action_plan")
    if supplied_confirmation and not confirmation_matches:
        blockers.append("owner_confirmation_value_mismatch")

    ready_for_owner_action_authorization = (
        final_review_ready and bool(target_head) and bool(normalized_authorization_id)
    )
    action_authorized = (
        ready_for_owner_action_authorization and confirmation_matches
    )

    if not ready_for_owner_action_authorization:
        status = "blocked_before_first_real_submit_action_authorization"
    elif action_authorized:
        status = "owner_first_real_submit_action_authorization_packet_ready"
    else:
        status = "waiting_for_owner_first_real_submit_action_authorization"

    command_plan = _command_plan(
        authorization_id=normalized_authorization_id,
        api_base=api_base,
        env_file=env_file,
        expected_confirmation=expected_confirmation,
    )

    return {
        "status": status,
        "scope": "runtime_first_real_submit_action_authorization_packet",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_head": target_head,
        "authorization_id": normalized_authorization_id,
        "evidence": {
            "final_review_status": final_review_packet.get("status"),
            "final_review_ready_for_owner_action": checks.get(
                "ready_for_owner_action_review"
            ),
            "owner_action_ready": checks.get("owner_action_ready"),
            "target_head_consistent": checks.get("target_head_consistent"),
            "final_review_only": owner_gate.get("final_review_only"),
        },
        "owner_confirmation": {
            "env_name": APPROVAL_ENV,
            "required_value": expected_confirmation,
            "supplied_value_matches": confirmation_matches,
            "action_authorized": action_authorized,
            "must_be_supplied_out_of_band_before_execute_command": (
                not action_authorized
            ),
        },
        "checks": {
            "ready_for_owner_action_authorization": (
                ready_for_owner_action_authorization
            ),
            "action_authorized": action_authorized,
            "final_review_ready": final_review_ready,
            "authorization_id_present": bool(normalized_authorization_id),
            "owner_confirmation_value_matches": confirmation_matches,
            "blockers": _dedupe(blockers),
            "warnings": list(checks.get("warnings") or []),
        },
        "operator_command_plan": command_plan,
        "owner_gate": {
            "packet_build_only": True,
            "requires_separate_execute_step": True,
            "does_not_authorize_by_itself": [
                "real runtime submit",
                "exchange order placement",
                "OrderLifecycle submit",
                "local order registration",
                "attempt or budget mutation",
                "withdrawal or transfer",
            ],
            "authorized_execute_step_available": action_authorized,
        },
        "safety_invariants": {
            "packet_build_only": True,
            "api_called": False,
            "remote_files_modified": False,
            "migrations_run": False,
            "services_restarted": False,
            "database_connected": False,
            "runtime_started": False,
            "prepare_records_created": False,
            "execution_intent_created": False,
            "execution_intent_status_changed": False,
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "order_created": False,
            "owner_bounded_execution_called": False,
            "order_lifecycle_called": False,
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
) -> dict[str, Any]:
    if not authorization_id:
        return {
            "not_executed": True,
            "authorization_id_required": True,
            "disabled_smoke_command": None,
            "execute_command": None,
        }

    base = [
        "python3",
        "scripts/runtime_first_real_submit_api_flow.py",
        "--api-base",
        api_base,
    ]
    if env_file:
        base.extend(["--env-file", env_file])

    disabled_smoke = base + [
        "--mode",
        "arm",
        "--authorization-id",
        authorization_id,
        "--preview-disabled-first-real-submit-action",
    ]
    execute = base + [
        "--mode",
        "execute",
        "--authorization-id",
        authorization_id,
        "--execute-real-submit",
    ]
    return {
        "not_executed": True,
        "uses_official_api_flow": True,
        "api_base_env": API_BASE_ENV,
        "api_base": api_base,
        "disabled_smoke_command": disabled_smoke,
        "execute_command": execute,
        "execute_env_required": {
            "name": APPROVAL_ENV,
            "value": expected_confirmation,
        },
        "execute_command_is_preview_only_in_this_packet": True,
    }


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise FirstRealSubmitActionAuthorizationPacketError(
            f"packet unreadable: {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise FirstRealSubmitActionAuthorizationPacketError(
            f"packet is not JSON: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise FirstRealSubmitActionAuthorizationPacketError(
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


def _dedupe(values: list[str]) -> list[str]:
    return sorted(dict.fromkeys(values))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a non-executing first-real-submit action authorization packet."
        )
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument("--final-review-packet-path", required=True)
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
        "ready_for_owner_action_authorization="
        + str(checks["ready_for_owner_action_authorization"]).lower()
    )
    print("action_authorized=" + str(checks["action_authorized"]).lower())
    print(f"target_head={packet['target_head']}")
    print(f"authorization_id={packet['authorization_id']}")
    if checks["blockers"]:
        print("blockers=" + ",".join(checks["blockers"]))
    if checks["warnings"]:
        print("warnings=" + ",".join(checks["warnings"]))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FirstRealSubmitActionAuthorizationPacketError as exc:
        print(
            f"first_real_submit_action_authorization_packet_error={exc}",
            file=sys.stderr,
        )
        raise SystemExit(2)
