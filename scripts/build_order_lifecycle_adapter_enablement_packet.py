#!/usr/bin/env python3
"""Build a dry-run OrderLifecycle adapter enablement readiness packet.

This packet aggregates the pre-live runtime submit rehearsal evidence and
separates two questions:

1. Are the non-executing inputs ready for an adapter implementation task?
2. Is the runtime allowed to enable and invoke that adapter now?

It does not write PG, enable a runtime, register local orders, call
OrderLifecycle, call exchange APIs, submit orders, transfer funds, or authorize
live trading. Explicit Owner authorization remains required before any real
runtime submit or adapter invocation.
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
    DEFAULT_DEPLOYED_HEAD,
    OWNER_AUTHORIZATION_FLAG,
    OWNER_LIVE_RUNTIME_ENABLEMENT_FLAG,
    build_pre_live_packet,
)


READY_SUBMIT_ADAPTER_STATUS = "inputs_ready_dry_run_adapter_only"
READY_HANDOFF_STATUS = "ready_for_order_lifecycle_adapter"
READY_ADAPTER_PREVIEW_STATUS = "inputs_ready_registration_not_enabled"
READY_REGISTRATION_DRAFT_STATUS = "inputs_ready_registration_draft_only"
ADAPTER_IMPLEMENTATION_CAPABILITIES = {
    "order_object_construction_boundary_implemented": True,
    "local_order_registration_write_path_implemented": True,
    "order_lifecycle_adapter_invocation_implemented": True,
    "persistent_duplicate_submit_lock_implemented": True,
    "execution_intent_status_transition_after_registration_implemented": False,
    "protection_order_failure_recovery_implemented": False,
}


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    packet = asyncio.run(_build_packet_from_args(args))
    if args.json:
        print(json.dumps(packet, indent=2, sort_keys=True))
    else:
        _print_human(packet)
    return 0 if packet["checks"]["ready_for_non_executing_implementation_task"] else 2


async def _build_packet_from_args(args: argparse.Namespace) -> dict[str, Any]:
    pre_live_packet = await build_pre_live_packet(
        deployed_head=args.deployed_head,
        owner_real_submit_authorized=args.owner_real_submit_authorized,
        owner_live_runtime_enablement_authorized=(
            args.owner_live_runtime_enable_authorized
        ),
        require_current_head_deployed=not args.skip_current_head_deployed_check,
        active_positions=args.active_positions,
    )
    return build_order_lifecycle_adapter_enablement_packet(
        pre_live_packet=pre_live_packet
    )


def build_order_lifecycle_adapter_enablement_packet(
    *,
    pre_live_packet: dict[str, Any],
) -> dict[str, Any]:
    """Summarize adapter readiness without creating execution authority."""

    checks = _as_dict(pre_live_packet.get("checks"))
    pipeline = _as_dict(pre_live_packet.get("pipeline"))
    owner_gate = _as_dict(pre_live_packet.get("owner_gate"))
    deployment_gate = _as_dict(pre_live_packet.get("deployment_gate"))
    registration_chain = _as_dict(pre_live_packet.get("registration_draft_chain"))
    adapter_preview = _as_dict(
        registration_chain.get("order_lifecycle_adapter_preview")
    )
    registration_preview = _as_dict(
        registration_chain.get("order_registration_draft_preview")
    )
    live_enablement_preview = _as_dict(
        pre_live_packet.get("live_enablement_preview")
    )

    technical_blockers = list(checks.get("technical_blockers") or [])
    forbidden_execution_flags = list(checks.get("forbidden_execution_flags") or [])
    implementation_blockers = list(checks.get("implementation_blockers") or [])
    operational_blockers = list(checks.get("operational_blockers") or [])
    live_enablement_blockers = list(checks.get("live_enablement_blockers") or [])

    draft_readiness = _draft_readiness(registration_preview=registration_preview)
    technical_ready = (
        checks.get("technical_rehearsal_passed") is True
        and not technical_blockers
        and not forbidden_execution_flags
    )
    registration_chain_ready = (
        checks.get("registration_draft_chain_passed") is True
        and pipeline.get("order_lifecycle_handoff_status") == READY_HANDOFF_STATUS
        and pipeline.get("order_lifecycle_adapter_preview_status")
        == READY_ADAPTER_PREVIEW_STATUS
        and pipeline.get("order_registration_draft_preview_status")
        == READY_REGISTRATION_DRAFT_STATUS
        and adapter_preview.get("status") == READY_ADAPTER_PREVIEW_STATUS
        and registration_preview.get("status") == READY_REGISTRATION_DRAFT_STATUS
        and not adapter_preview.get("blockers")
        and not registration_preview.get("blockers")
    )
    submit_boundary_ready = (
        pipeline.get("submit_adapter_preview_status") == READY_SUBMIT_ADAPTER_STATUS
    )

    blockers = _dedupe(
        technical_blockers
        + forbidden_execution_flags
        + list(draft_readiness["blockers"])
    )
    if not technical_ready:
        blockers.append("technical_rehearsal_not_ready")
    if not submit_boundary_ready:
        blockers.append("submit_adapter_preview_not_ready")
    if not registration_chain_ready:
        blockers.append("order_registration_draft_chain_not_ready")
    blockers = _dedupe(blockers)

    ready_for_non_executing_implementation_task = (
        technical_ready
        and submit_boundary_ready
        and registration_chain_ready
        and draft_readiness["entry_registration_draft_ready"]
        and draft_readiness["hard_stop_registration_draft_ready"]
        and draft_readiness["registration_draft_ids_unique"]
        and draft_readiness["all_drafts_non_persisted_non_executing"]
        and not blockers
    )

    implementation_work_items = _implementation_work_items(
        adapter_preview=adapter_preview,
        registration_preview=registration_preview,
    )
    owner_real_submit_authorized = (
        owner_gate.get("owner_real_submit_authorized") is True
        or checks.get("owner_real_submit_authorization_present") is True
    )
    owner_live_runtime_enablement_authorized = (
        owner_gate.get("owner_live_runtime_enablement_authorized") is True
        or checks.get("owner_live_runtime_enablement_authorization_present") is True
    )
    runtime_enablement_blockers = _runtime_enablement_blockers(
        implementation_blockers=implementation_blockers,
        operational_blockers=operational_blockers,
        live_enablement_blockers=live_enablement_blockers,
        implementation_work_items=implementation_work_items,
        owner_real_submit_authorized=owner_real_submit_authorized,
        owner_live_runtime_enablement_authorized=owner_live_runtime_enablement_authorized,
        live_enablement_status=live_enablement_preview.get("status"),
    )
    ready_for_runtime_adapter_enablement = (
        ready_for_non_executing_implementation_task
        and not implementation_work_items
        and not runtime_enablement_blockers
    )

    status = "blocked_before_order_lifecycle_adapter_implementation_task"
    if ready_for_runtime_adapter_enablement:
        status = "ready_for_runtime_order_lifecycle_adapter_enablement"
    elif ready_for_non_executing_implementation_task:
        status = "ready_for_non_executing_order_lifecycle_adapter_implementation_task"

    return {
        "status": status,
        "scope": "runtime_order_lifecycle_adapter_enablement_packet",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "local_git": pre_live_packet.get("local_git", {}),
        "deployment_gate": deployment_gate,
        "owner_gate": {
            "owner_real_submit_authorized": owner_real_submit_authorized,
            "owner_live_runtime_enablement_authorized": (
                owner_live_runtime_enablement_authorized
            ),
            "required_before_runtime_adapter_enablement": [
                OWNER_AUTHORIZATION_FLAG,
                OWNER_LIVE_RUNTIME_ENABLEMENT_FLAG,
            ],
            "packet_does_not_authorize_submit": True,
        },
        "readiness_summary": {
            "technical_rehearsal_ready": technical_ready,
            "submit_boundary_ready": submit_boundary_ready,
            "registration_draft_chain_ready": registration_chain_ready,
            "entry_registration_draft_ready": draft_readiness[
                "entry_registration_draft_ready"
            ],
            "hard_stop_registration_draft_ready": draft_readiness[
                "hard_stop_registration_draft_ready"
            ],
            "registration_draft_ids_unique": draft_readiness[
                "registration_draft_ids_unique"
            ],
            "all_drafts_non_persisted_non_executing": draft_readiness[
                "all_drafts_non_persisted_non_executing"
            ],
            "ready_for_non_executing_implementation_task": (
                ready_for_non_executing_implementation_task
            ),
            "ready_for_runtime_adapter_enablement": (
                ready_for_runtime_adapter_enablement
            ),
        },
        "adapter_enablement_gate": {
            "current_state": {
                "submit_adapter_implemented": _from_rehearsal(
                    pre_live_packet,
                    "submit_adapter_implemented",
                    default=True,
                ),
                "order_lifecycle_adapter_enabled": _from_rehearsal(
                    pre_live_packet,
                    "order_lifecycle_adapter_enabled",
                    default=False,
                ),
                "order_lifecycle_adapter_implemented": adapter_preview.get(
                    "order_lifecycle_adapter_implemented"
                ),
                "local_order_registration_enabled": registration_preview.get(
                    "local_order_registration_enabled"
                ),
                "local_order_registration_executed": registration_preview.get(
                    "local_order_registration_executed"
                ),
                "order_objects_constructed": registration_preview.get(
                    "order_objects_constructed"
                ),
                "adapter_implementation_capabilities": dict(
                    ADAPTER_IMPLEMENTATION_CAPABILITIES
                ),
            },
            "implementation_work_items": implementation_work_items,
            "runtime_enablement_blockers": runtime_enablement_blockers,
        },
        "registration_draft_evidence": {
            "registration_preview_id": registration_preview.get(
                "registration_preview_id"
            ),
            "entry_registration_draft_count": registration_preview.get(
                "entry_registration_draft_count"
            ),
            "protection_registration_draft_count": registration_preview.get(
                "protection_registration_draft_count"
            ),
            "hard_stop_registration_draft_ids": draft_readiness[
                "hard_stop_registration_draft_ids"
            ],
            "local_order_draft_ids": draft_readiness["local_order_draft_ids"],
            "source_type": registration_preview.get("source_type"),
            "source_id": registration_preview.get("source_id"),
            "semantic_ids": registration_preview.get("semantic_ids", {}),
        },
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
        "checks": {
            "ready_for_non_executing_implementation_task": (
                ready_for_non_executing_implementation_task
            ),
            "ready_for_runtime_adapter_enablement": (
                ready_for_runtime_adapter_enablement
            ),
            "blockers": blockers,
        },
        "source_pre_live_packet": {
            "status": pre_live_packet.get("status"),
            "scope": pre_live_packet.get("scope"),
            "safety_invariants": pre_live_packet.get("safety_invariants", {}),
        },
        "does_not_authorize": [
            "real runtime submit",
            "exchange order placement",
            "OrderLifecycle adapter invocation",
            "local order registration",
            "runtime live execution enablement",
            "withdrawal or transfer",
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
            "order_objects_constructed": False,
            "local_order_registration_executed": False,
            "order_created": False,
            "owner_bounded_execution_called": False,
            "order_lifecycle_called": False,
            "exchange_called": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _draft_readiness(*, registration_preview: dict[str, Any]) -> dict[str, Any]:
    drafts = [
        _as_dict(item)
        for item in list(registration_preview.get("local_order_registration_drafts") or [])
    ]
    local_order_draft_ids = [
        str(item.get("local_order_draft_id") or "") for item in drafts
    ]
    entry_drafts = [
        item for item in drafts if str(item.get("order_role") or "").upper() == "ENTRY"
    ]
    entry_draft_id = (
        str(entry_drafts[0].get("local_order_draft_id") or "")
        if len(entry_drafts) == 1
        else ""
    )
    hard_stop_drafts = [
        item
        for item in drafts
        if str(item.get("order_role") or "").upper() == "SL"
        and str(item.get("order_type") or "").upper() in {"STOP_MARKET", "STOP_LIMIT"}
        and item.get("trigger_price") not in {None, ""}
        and item.get("reduce_only") is True
        and item.get("parent_local_order_draft_id") == entry_draft_id
    ]
    all_non_executing = all(
        item.get("not_order") is True
        and item.get("not_persisted") is True
        and item.get("persisted") is False
        and item.get("order_lifecycle_called") is False
        and item.get("exchange_called") is False
        for item in drafts
    )
    ids_unique = bool(local_order_draft_ids) and len(local_order_draft_ids) == len(
        set(local_order_draft_ids)
    )

    blockers: list[str] = []
    if len(entry_drafts) != 1:
        blockers.append("entry_registration_draft_count_invalid")
    if not hard_stop_drafts:
        blockers.append("hard_stop_registration_draft_missing")
    if not ids_unique:
        blockers.append("local_order_registration_draft_ids_not_unique")
    if not all_non_executing:
        blockers.append("registration_drafts_not_proven_non_executing")

    return {
        "entry_registration_draft_ready": len(entry_drafts) == 1,
        "hard_stop_registration_draft_ready": bool(hard_stop_drafts),
        "registration_draft_ids_unique": ids_unique,
        "all_drafts_non_persisted_non_executing": all_non_executing,
        "hard_stop_registration_draft_ids": [
            str(item.get("local_order_draft_id") or "") for item in hard_stop_drafts
        ],
        "local_order_draft_ids": local_order_draft_ids,
        "blockers": blockers,
    }


def _implementation_work_items(
    *,
    adapter_preview: dict[str, Any],
    registration_preview: dict[str, Any],
) -> list[str]:
    items: list[str] = []
    if (
        ADAPTER_IMPLEMENTATION_CAPABILITIES[
            "order_lifecycle_adapter_invocation_implemented"
        ]
        is not True
    ):
        items.append("order_lifecycle_adapter_invocation_not_implemented")
    if (
        ADAPTER_IMPLEMENTATION_CAPABILITIES[
            "local_order_registration_write_path_implemented"
        ]
        is not True
    ):
        items.append("local_order_registration_write_path_not_enabled")
    if (
        ADAPTER_IMPLEMENTATION_CAPABILITIES[
            "order_object_construction_boundary_implemented"
        ]
        is not True
    ):
        items.append("order_object_construction_boundary_not_enabled")
    if (
        ADAPTER_IMPLEMENTATION_CAPABILITIES[
            "persistent_duplicate_submit_lock_implemented"
        ]
        is not True
    ):
        items.append("persistent_duplicate_submit_lock_not_implemented")
    if (
        ADAPTER_IMPLEMENTATION_CAPABILITIES[
            "execution_intent_status_transition_after_registration_implemented"
        ]
        is not True
    ):
        items.append(
            "execution_intent_status_transition_after_registration_not_implemented"
        )
    if (
        ADAPTER_IMPLEMENTATION_CAPABILITIES[
            "protection_order_failure_recovery_implemented"
        ]
        is not True
    ):
        items.append("protection_order_failure_recovery_not_implemented")
    if adapter_preview.get("order_lifecycle_adapter_implemented") is not True:
        items.append("order_lifecycle_adapter_runtime_enablement_disabled")
    if registration_preview.get("local_order_registration_enabled") is not True:
        items.append("local_order_registration_runtime_enablement_disabled")
    return _dedupe(items)


def _runtime_enablement_blockers(
    *,
    implementation_blockers: list[str],
    operational_blockers: list[str],
    live_enablement_blockers: list[str],
    implementation_work_items: list[str],
    owner_real_submit_authorized: bool,
    owner_live_runtime_enablement_authorized: bool,
    live_enablement_status: Any,
) -> list[str]:
    blockers = list(implementation_blockers)
    blockers.extend(operational_blockers)
    blockers.extend(live_enablement_blockers)
    blockers.extend(implementation_work_items)
    if not owner_real_submit_authorized:
        blockers.append("owner_real_submit_authorization_missing")
    if not owner_live_runtime_enablement_authorized:
        blockers.append("owner_live_runtime_enablement_authorization_missing")
    if live_enablement_status != "ready_for_live_runtime_enablement_mutation_design":
        blockers.append("runtime_live_enablement_not_ready")
    return _dedupe(blockers)


def _from_rehearsal(
    pre_live_packet: dict[str, Any],
    key: str,
    *,
    default: Any,
) -> Any:
    rehearsal = _as_dict(pre_live_packet.get("rehearsal"))
    submit_adapter = _as_dict(rehearsal.get("submit_adapter_preview"))
    return submit_adapter.get(key, default)


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _dedupe(values: list[str]) -> list[str]:
    return sorted(dict.fromkeys(values))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a non-executing OrderLifecycle adapter enablement readiness packet."
        )
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
        help="Mark Owner real-submit authorization as present for readiness accounting.",
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
    return parser.parse_args(argv)


def _print_human(packet: dict[str, Any]) -> None:
    checks = packet["checks"]
    summary = packet["readiness_summary"]
    gate = packet["adapter_enablement_gate"]
    print(f"status={packet['status']}")
    print(
        "ready_for_non_executing_implementation_task="
        + str(checks["ready_for_non_executing_implementation_task"]).lower()
    )
    print(
        "ready_for_runtime_adapter_enablement="
        + str(checks["ready_for_runtime_adapter_enablement"]).lower()
    )
    print("technical_rehearsal_ready=" + str(summary["technical_rehearsal_ready"]).lower())
    print("registration_draft_chain_ready=" + str(summary["registration_draft_chain_ready"]).lower())
    if checks["blockers"]:
        print("blockers=" + ",".join(checks["blockers"]))
    if gate["implementation_work_items"]:
        print("implementation_work_items=" + ",".join(gate["implementation_work_items"]))
    if gate["runtime_enablement_blockers"]:
        print("runtime_enablement_blockers=" + ",".join(gate["runtime_enablement_blockers"]))


if __name__ == "__main__":
    raise SystemExit(main())
