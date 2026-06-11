#!/usr/bin/env python3
"""Build the final read-only review packet before a first real runtime submit.

This script joins two existing evidence packets:

1. Tokyo post-deploy acceptance packet.
2. Runtime first-real-submit Owner packet.

It does not deploy, mutate Tokyo, run migrations, start runtimes, register
orders, call OrderLifecycle, call exchange APIs, or authorize a real submit.
The output is an Owner/Codex review surface only.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class FirstRealSubmitFinalReviewPacketError(RuntimeError):
    """Raised when a final review packet cannot be built."""


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    packet = build_first_real_submit_final_review_packet(
        postdeploy_acceptance_packet=_load_json_object(
            Path(args.postdeploy_acceptance_packet_path)
        ),
        first_real_submit_owner_packet=_load_json_object(
            Path(args.first_real_submit_owner_packet_path)
        ),
        expected_current_head=args.expected_current_head,
    )
    if args.json:
        print(json.dumps(packet, indent=2, sort_keys=True))
    else:
        _print_human(packet)
    return 0 if packet["checks"]["ready_for_owner_action_review"] else 2


def build_first_real_submit_final_review_packet(
    *,
    postdeploy_acceptance_packet: dict[str, Any],
    first_real_submit_owner_packet: dict[str, Any],
    expected_current_head: str | None = None,
) -> dict[str, Any]:
    """Combine deploy and first-submit evidence without creating authority."""

    postdeploy_checks = _as_dict(postdeploy_acceptance_packet.get("checks"))
    owner_checks = _as_dict(first_real_submit_owner_packet.get("checks"))
    action_boundary = _as_dict(
        first_real_submit_owner_packet.get("first_real_submit_action_boundary")
    )
    postdeploy_summary = _as_dict(
        postdeploy_acceptance_packet.get("postdeploy_summary")
    )
    owner_deployment_gate = _as_dict(
        first_real_submit_owner_packet.get("deployment_gate")
    )

    target_head = _first_present(
        expected_current_head,
        postdeploy_acceptance_packet.get("expected_current_head"),
        postdeploy_summary.get("current_head"),
    )
    postdeploy_expected_head = _optional_str(
        postdeploy_acceptance_packet.get("expected_current_head")
    )
    postdeploy_current_head = _optional_str(postdeploy_summary.get("current_head"))
    owner_local_head = _optional_str(
        _as_dict(first_real_submit_owner_packet.get("local_git")).get("head")
    )

    postdeploy_acceptance_ready = (
        postdeploy_checks.get("postdeploy_acceptance_ready") is True
    )
    owner_packet_ready = (
        owner_checks.get("packet_ready_for_owner_decision") is True
    )
    owner_action_ready = (
        owner_checks.get("ready_for_first_real_submit") is True
        and action_boundary.get("ready_for_first_real_submit") is True
        and action_boundary.get("exchange_submit_adapter_pre_execution_ready")
        is True
        and not list(action_boundary.get("remaining_action_blockers") or [])
    )
    owner_deployment_gate_ready = (
        owner_deployment_gate.get("current_head_deployed") is True
    )
    forbidden_effects = _forbidden_effects(
        postdeploy_acceptance_packet=postdeploy_acceptance_packet,
        first_real_submit_owner_packet=first_real_submit_owner_packet,
    )

    blockers: list[str] = []
    if not postdeploy_acceptance_ready:
        blockers.append("postdeploy_acceptance_not_ready")
    if not owner_packet_ready:
        blockers.append("first_real_submit_owner_packet_not_ready")
    if not target_head:
        blockers.append("target_head_missing")
    if target_head and postdeploy_expected_head and postdeploy_expected_head != target_head:
        blockers.append("postdeploy_expected_head_mismatch")
    if target_head and postdeploy_current_head != target_head:
        blockers.append("postdeploy_current_head_mismatch")
    if target_head and owner_local_head != target_head:
        blockers.append("first_real_submit_owner_packet_head_mismatch")
    if not owner_deployment_gate_ready:
        blockers.append("first_real_submit_owner_deployment_gate_not_ready")
    if forbidden_effects:
        blockers.append("final_review_packet_contains_forbidden_effects")

    ready_for_prerequisite_review = (
        not blockers and postdeploy_acceptance_ready and owner_packet_ready
    )
    ready_for_owner_action_review = ready_for_prerequisite_review and owner_action_ready
    status = "blocked_before_first_real_submit_final_review"
    if ready_for_owner_action_review:
        status = "ready_for_owner_first_real_submit_action_review"
    elif ready_for_prerequisite_review:
        status = "ready_for_owner_first_real_submit_prerequisite_review"

    warnings = _dedupe(
        list(postdeploy_checks.get("warnings") or [])
        + list(owner_checks.get("warnings") or [])
    )
    return {
        "status": status,
        "scope": "runtime_first_real_submit_final_review_packet",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_head": target_head,
        "evidence": {
            "postdeploy_acceptance_status": postdeploy_acceptance_packet.get(
                "status"
            ),
            "postdeploy_current_head": postdeploy_current_head,
            "postdeploy_expected_head": postdeploy_expected_head,
            "owner_packet_status": first_real_submit_owner_packet.get("status"),
            "owner_packet_local_head": owner_local_head,
            "owner_deployment_current_head_deployed": owner_deployment_gate_ready,
        },
        "action_review": {
            "owner_packet_ready_for_decision": owner_packet_ready,
            "ready_for_first_real_submit": owner_checks.get(
                "ready_for_first_real_submit"
            ),
            "exchange_submit_adapter_pre_execution_ready": action_boundary.get(
                "exchange_submit_adapter_pre_execution_ready"
            ),
            "exchange_submit_execution_disabled_proved": action_boundary.get(
                "exchange_submit_execution_disabled_proved"
            ),
            "requires_separate_action_authorization": action_boundary.get(
                "requires_separate_action_authorization"
            ),
            "remaining_action_blockers": list(
                action_boundary.get("remaining_action_blockers") or []
            ),
            "does_not_authorize_live_action": True,
        },
        "checks": {
            "ready_for_prerequisite_review": ready_for_prerequisite_review,
            "ready_for_owner_action_review": ready_for_owner_action_review,
            "postdeploy_acceptance_ready": postdeploy_acceptance_ready,
            "owner_packet_ready": owner_packet_ready,
            "owner_action_ready": owner_action_ready,
            "target_head_consistent": bool(
                target_head
                and postdeploy_current_head == target_head
                and owner_local_head == target_head
            ),
            "owner_deployment_gate_ready": owner_deployment_gate_ready,
            "forbidden_effects": forbidden_effects,
            "blockers": _dedupe(blockers),
            "warnings": warnings,
        },
        "owner_gate": {
            "final_review_only": True,
            "does_not_authorize": [
                "real runtime submit",
                "exchange order placement",
                "OrderLifecycle adapter enablement",
                "local order registration",
                "deployment or migration",
                "withdrawal or transfer",
                "live runtime profile change",
            ],
            "next_authorization_if_ready": (
                "explicit first-real-submit action authorization"
                if ready_for_owner_action_review
                else None
            ),
        },
        "safety_invariants": {
            "packet_build_only": True,
            "remote_files_modified": False,
            "migrations_run": False,
            "services_restarted": False,
            "database_connected": False,
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


def _forbidden_effects(
    *,
    postdeploy_acceptance_packet: dict[str, Any],
    first_real_submit_owner_packet: dict[str, Any],
) -> list[str]:
    allowed_true = {"packet_build_only"}
    sources = {
        "postdeploy_acceptance_packet": _as_dict(
            postdeploy_acceptance_packet.get("safety_invariants")
        ),
        "first_real_submit_owner_packet": _as_dict(
            first_real_submit_owner_packet.get("safety_invariants")
        ),
    }
    forbidden: list[str] = []
    for source, flags in sources.items():
        for name, value in flags.items():
            if name in allowed_true:
                continue
            if value is True:
                forbidden.append(f"{source}.{name}")
    return _dedupe(forbidden)


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except OSError as exc:
        raise FirstRealSubmitFinalReviewPacketError(
            f"packet unreadable: {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise FirstRealSubmitFinalReviewPacketError(
            f"packet is not JSON: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise FirstRealSubmitFinalReviewPacketError(
            f"packet must be a JSON object: {path}"
        )
    return payload


def _first_present(*values: Any) -> str | None:
    for value in values:
        normalized = _optional_str(value)
        if normalized:
            return normalized
    return None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dedupe(values: list[str]) -> list[str]:
    return sorted(dict.fromkeys(values))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a read-only first-real-submit final review packet."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument("--postdeploy-acceptance-packet-path", required=True)
    parser.add_argument("--first-real-submit-owner-packet-path", required=True)
    parser.add_argument(
        "--expected-current-head",
        default=None,
        help="Optional current HEAD expected across both evidence packets.",
    )
    return parser.parse_args(argv)


def _print_human(packet: dict[str, Any]) -> None:
    checks = packet["checks"]
    print(f"status={packet['status']}")
    print(
        "ready_for_owner_action_review="
        + str(checks["ready_for_owner_action_review"]).lower()
    )
    print(f"target_head={packet['target_head']}")
    if checks["blockers"]:
        print("blockers=" + ",".join(checks["blockers"]))
    if checks["warnings"]:
        print("warnings=" + ",".join(checks["warnings"]))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FirstRealSubmitFinalReviewPacketError as exc:
        print(f"first_real_submit_final_review_packet_error={exc}", file=sys.stderr)
        raise SystemExit(2)
