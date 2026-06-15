#!/usr/bin/env python3
"""Build a read-only post-deploy acceptance packet for Tokyo runtime governance.

This script is intended to run after an Owner-authorized deployment. It
aggregates the post-deploy verifier and the pre-live runtime submit packet to
prove the deployed release is current while real submit remains blocked.

It does not deploy, run migrations, restart services, create execution records,
create orders, call OrderLifecycle, call exchange APIs, read secrets, or
authorize a real submit.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORT))

from scripts.verify_runtime_submit_rehearsal_pre_live_packet import (
    build_pre_live_packet,
)
from scripts.verify_tokyo_runtime_governance_postdeploy import (
    DEFAULT_API_BASE,
    DEFAULT_DEPLOY_ROOT,
    DEFAULT_EXPECTED_LATEST_MIGRATION,
    DEFAULT_EXPECTED_MIGRATION_COUNT,
    DEFAULT_HOST,
    build_postdeploy_report,
)


class PostDeployAcceptancePacketError(RuntimeError):
    """Raised when the post-deploy acceptance packet cannot be built."""


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    packet = asyncio.run(_build_postdeploy_acceptance_packet_from_args(args))
    if args.json:
        print(json.dumps(packet, indent=2, sort_keys=True))
    else:
        _print_human(packet)
    return 0 if packet["checks"]["postdeploy_acceptance_ready"] else 2


async def _build_postdeploy_acceptance_packet_from_args(
    args: argparse.Namespace,
) -> dict[str, Any]:
    postdeploy_report = build_postdeploy_report(
        host=args.host,
        deploy_root=args.deploy_root,
        api_base=args.api_base,
        expected_current_head=args.expected_current_head,
        expected_migration_count=args.expected_migration_count,
        expected_latest_migration=args.expected_latest_migration,
        connect_timeout_seconds=args.connect_timeout_seconds,
    )
    pre_live_packet = None
    if args.pre_live_packet_path:
        pre_live_packet = _load_json_object(Path(args.pre_live_packet_path))
    elif not args.skip_pre_live_packet:
        pre_live_packet = await build_pre_live_packet(
            deployed_head=args.expected_current_head,
            owner_real_submit_authorized=False,
            owner_live_runtime_enablement_authorized=False,
            require_current_head_deployed=True,
            active_positions=args.active_positions,
        )
    return build_postdeploy_acceptance_packet(
        postdeploy_report=postdeploy_report,
        pre_live_packet=pre_live_packet,
        expected_current_head=args.expected_current_head,
    )


def build_postdeploy_acceptance_packet(
    *,
    postdeploy_report: dict[str, Any],
    pre_live_packet: dict[str, Any] | None,
    expected_current_head: str,
) -> dict[str, Any]:
    """Aggregate post-deploy facts into one acceptance packet."""

    postdeploy_checks = (
        postdeploy_report.get("checks")
        if isinstance(postdeploy_report.get("checks"), dict)
        else {}
    )
    pre_live_checks = (
        pre_live_packet.get("checks")
        if isinstance(pre_live_packet, dict)
        and isinstance(pre_live_packet.get("checks"), dict)
        else {}
    )

    postdeploy_ready = postdeploy_checks.get("postdeploy_acceptance_passed") is True
    current_head_matches = _postdeploy_current_head(postdeploy_report) == expected_current_head
    health_live_ready_false = (
        _postdeploy_health(postdeploy_report).get("live_ready") is False
    )
    pre_live_technical_ready = bool(
        pre_live_packet
        and pre_live_checks.get("technical_rehearsal_passed") is True
        and pre_live_checks.get("registration_draft_chain_passed") is True
    )
    current_head_deployed_gate = pre_live_checks.get("current_head_deployed") is True
    first_real_submit_still_blocked = bool(
        pre_live_packet
        and pre_live_packet.get("status") == "blocked_before_first_real_submit"
        and pre_live_checks.get("ready_for_first_real_submit") is False
    )
    forbidden_pre_live_flags = list(
        pre_live_checks.get("forbidden_execution_flags") or []
    )
    forbidden_effects = _forbidden_effects(
        postdeploy_report=postdeploy_report,
        pre_live_packet=pre_live_packet,
    )

    blockers: list[str] = []
    if not postdeploy_ready:
        blockers.append("postdeploy_verifier_not_passed")
    if not current_head_matches:
        blockers.append("postdeploy_current_head_mismatch")
    if not health_live_ready_false:
        blockers.append("postdeploy_health_live_ready_not_false")
    if not pre_live_technical_ready:
        blockers.append("pre_live_submit_rehearsal_not_technically_ready")
    if not current_head_deployed_gate:
        blockers.append("pre_live_current_head_deployed_gate_not_true")
    if forbidden_pre_live_flags:
        blockers.append("pre_live_packet_contains_forbidden_execution_flags")
    if forbidden_effects:
        blockers.append("postdeploy_packet_contains_forbidden_side_effect_flags")

    warnings = sorted(
        set(
            list(postdeploy_checks.get("warnings") or [])
            + list(pre_live_checks.get("warnings") or [])
        )
    )
    if not first_real_submit_still_blocked:
        warnings.append("first_real_submit_not_a_postdeploy_acceptance_precondition")
    packet = {
        "status": "postdeploy_acceptance_ready" if not blockers else "blocked",
        "scope": "tokyo_runtime_governance_postdeploy_acceptance_packet",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "expected_current_head": expected_current_head,
        "postdeploy_summary": {
            "status": postdeploy_report.get("status"),
            "current_head": _postdeploy_current_head(postdeploy_report),
            "migration_count": postdeploy_report.get("facts", {}).get("migration_count"),
            "latest_migration": postdeploy_report.get("facts", {}).get(
                "latest_migration"
            ),
            "health": _postdeploy_health(postdeploy_report),
            "http_check_count": len(
                postdeploy_report.get("facts", {}).get("http_checks") or []
            ),
        },
        "pre_live_submit_summary": _pre_live_summary(pre_live_packet),
        "checks": {
            "postdeploy_acceptance_ready": not blockers,
            "postdeploy_verifier_passed": postdeploy_ready,
            "current_head_matches_expected": current_head_matches,
            "health_live_ready_false": health_live_ready_false,
            "pre_live_submit_technical_ready": pre_live_technical_ready,
            "current_head_deployed_gate": current_head_deployed_gate,
            "first_real_submit_still_blocked": first_real_submit_still_blocked,
            "forbidden_pre_live_flags": forbidden_pre_live_flags,
            "forbidden_effects": forbidden_effects,
            "blockers": blockers,
            "warnings": warnings,
        },
        "owner_gate": {
            "postdeploy_acceptance_only": True,
            "does_not_authorize": [
                "real runtime submit",
                "exchange order placement",
                "OrderLifecycle adapter enablement",
                "withdrawal or transfer",
                "live runtime profile change",
            ],
        },
        "safety_invariants": {
            "packet_build_only": True,
            "remote_files_modified": False,
            "migrations_run": False,
            "services_restarted": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_called": False,
            "withdrawal_or_transfer_created": False,
            "secrets_read": False,
        },
    }
    return packet


def _postdeploy_current_head(postdeploy_report: dict[str, Any]) -> str | None:
    facts = postdeploy_report.get("facts")
    if not isinstance(facts, dict):
        return None
    release_identity = facts.get("release_identity")
    if not isinstance(release_identity, dict):
        return None
    head = release_identity.get("head")
    return str(head).strip() if head else None


def _postdeploy_health(postdeploy_report: dict[str, Any]) -> dict[str, Any]:
    facts = postdeploy_report.get("facts")
    if not isinstance(facts, dict):
        return {}
    http_checks = facts.get("http_checks")
    if not isinstance(http_checks, list):
        return {}
    for item in http_checks:
        if isinstance(item, dict) and item.get("name") == "health":
            body_json = item.get("body_json")
            return body_json if isinstance(body_json, dict) else {}
    return {}


def _pre_live_summary(pre_live_packet: dict[str, Any] | None) -> dict[str, Any]:
    if not pre_live_packet:
        return {"status": "not_collected"}
    checks = pre_live_packet.get("checks", {})
    return {
        "status": pre_live_packet.get("status"),
        "technical_rehearsal_passed": checks.get("technical_rehearsal_passed"),
        "registration_draft_chain_passed": checks.get(
            "registration_draft_chain_passed"
        ),
        "current_head_deployed": checks.get("current_head_deployed"),
        "ready_for_first_real_submit": checks.get("ready_for_first_real_submit"),
        "implementation_blockers": checks.get("implementation_blockers"),
        "technical_blockers": checks.get("technical_blockers"),
        "forbidden_execution_flags": checks.get("forbidden_execution_flags"),
    }


def _forbidden_effects(
    *,
    postdeploy_report: dict[str, Any],
    pre_live_packet: dict[str, Any] | None,
) -> list[str]:
    sources = {
        "postdeploy_report": postdeploy_report.get("safety_invariants", {}),
        "pre_live_packet": (pre_live_packet or {}).get("safety_invariants", {}),
    }
    allowed_true = {"packet_build_only"}
    forbidden: list[str] = []
    for source, flags in sources.items():
        if not isinstance(flags, dict):
            continue
        for name, value in flags.items():
            if name in allowed_true:
                continue
            if value is True:
                forbidden.append(f"{source}.{name}")
    return forbidden


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a read-only Tokyo post-deploy acceptance packet."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument(
        "--expected-current-head",
        required=True,
        help="Expected deployed release commit after controlled deployment.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--deploy-root", default=DEFAULT_DEPLOY_ROOT)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument(
        "--expected-migration-count",
        type=int,
        default=DEFAULT_EXPECTED_MIGRATION_COUNT,
    )
    parser.add_argument(
        "--expected-latest-migration",
        default=DEFAULT_EXPECTED_LATEST_MIGRATION,
    )
    parser.add_argument("--connect-timeout-seconds", type=int, default=8)
    parser.add_argument("--active-positions", type=int, default=0)
    parser.add_argument(
        "--pre-live-packet-path",
        help=(
            "Use an existing pre-live submit packet instead of building one "
            "from the local checkout. Useful for git-archive deployments where "
            "the release manifest is the deployed identity source."
        ),
    )
    parser.add_argument(
        "--skip-pre-live-packet",
        action="store_true",
        help="Skip the pre-live submit packet. The packet will not be acceptance-ready.",
    )
    return parser.parse_args(argv)


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PostDeployAcceptancePacketError(f"{path} did not contain a JSON object")
    return payload


def _print_human(packet: dict[str, Any]) -> None:
    checks = packet["checks"]
    print(f"status={packet['status']}")
    print(
        "postdeploy_acceptance_ready="
        + str(checks["postdeploy_acceptance_ready"]).lower()
    )
    print(f"expected_current_head={packet['expected_current_head']}")
    print(f"current_head={packet['postdeploy_summary']['current_head']}")
    print(
        "first_real_submit_still_blocked="
        + str(checks["first_real_submit_still_blocked"]).lower()
    )
    if checks["blockers"]:
        print("blockers=" + ",".join(checks["blockers"]))
    if checks["warnings"]:
        print("warnings=" + ",".join(checks["warnings"]))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PostDeployAcceptancePacketError as exc:
        print(f"postdeploy_acceptance_packet_error={exc}", file=sys.stderr)
        raise SystemExit(2)
