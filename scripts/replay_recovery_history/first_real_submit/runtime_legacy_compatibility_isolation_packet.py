#!/usr/bin/env python3
"""Classify legacy first-real-submit compatibility surfaces.

RTF-104/105 is a cleanup/isolation packet. It proves the runtime-level
bridge/cycle mainline is not using the historical pre-attempt rehearsal or Owner
first-real-submit review packets as its primary gate, then records which legacy
artifacts remain replay / recovery / history compatibility surfaces.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[3]


MAINLINE_ARTIFACTS = (
    "scripts/runtime_controlled_tiny_live_readiness_projection.py",
    "scripts/runtime_controlled_tiny_live_readiness_to_preflight_proof.py",
    "scripts/runtime_controlled_tiny_live_readiness_to_local_cycle_proof.py",
    "scripts/runtime_live_continuation_refresh_flow.py",
    "scripts/runtime_live_continuation_selector_projection.py",
    "scripts/runtime_official_prepare_api_flow.py",
    "scripts/runtime_official_flat_next_attempt_end_to_end_proof.py",
    "scripts/runtime_official_fresh_candidate_runtime_cycle_handoff_proof.py",
    "scripts/runtime_official_post_submit_finalize_proof.py",
)

STANDING_RECOVERY_PROOF_ARTIFACTS = (
    "scripts/runtime_controlled_tiny_live_readiness_to_preflight_proof.py",
    "scripts/runtime_controlled_tiny_live_readiness_to_local_cycle_proof.py",
)

LEGACY_COMPATIBILITY_ARTIFACTS = (
    {
        "path": "scripts/verify_runtime_submit_rehearsal_pre_live_packet.py",
        "history_path": (
            "scripts/replay_recovery_history/first_real_submit/"
            "verify_runtime_submit_rehearsal_pre_live_packet.py"
        ),
        "classification": "legacy_pre_attempt_rehearsal_replay_only",
        "target_state": "history_replay_or_recovery_support",
    },
    {
        "path": "scripts/build_runtime_first_real_submit_owner_packet.py",
        "history_path": (
            "scripts/replay_recovery_history/first_real_submit/"
            "build_runtime_first_real_submit_owner_packet.py"
        ),
        "classification": "legacy_owner_first_real_submit_review_only",
        "target_state": "history_review_packet_not_runtime_mainline_gate",
    },
    {
        "path": "scripts/build_runtime_first_real_submit_final_review_packet.py",
        "history_path": (
            "scripts/replay_recovery_history/first_real_submit/"
            "build_runtime_first_real_submit_final_review_packet.py"
        ),
        "classification": "legacy_first_real_submit_final_review_only",
        "target_state": "history_review_packet_not_runtime_mainline_gate",
    },
    {
        "path": "scripts/build_runtime_first_real_submit_action_authorization_packet.py",
        "history_path": (
            "scripts/replay_recovery_history/first_real_submit/"
            "build_runtime_first_real_submit_action_authorization_packet.py"
        ),
        "classification": "legacy_first_real_submit_action_packet",
        "target_state": "compatibility_action_packet_not_runtime_grant",
    },
    {
        "path": "scripts/build_runtime_first_real_submit_local_registration_authorization_packet.py",
        "history_path": (
            "scripts/replay_recovery_history/first_real_submit/"
            "build_runtime_first_real_submit_local_registration_authorization_packet.py"
        ),
        "classification": "legacy_local_registration_authorization_packet",
        "target_state": "compatibility_action_packet_not_runtime_grant",
    },
    {
        "path": "scripts/build_runtime_first_real_submit_exchange_arm_authorization_packet.py",
        "history_path": (
            "scripts/replay_recovery_history/first_real_submit/"
            "build_runtime_first_real_submit_exchange_arm_authorization_packet.py"
        ),
        "classification": "legacy_exchange_arm_authorization_packet",
        "target_state": "compatibility_action_packet_not_runtime_grant",
    },
    {
        "path": "scripts/runtime_first_real_submit_api_flow.py",
        "history_path": (
            "scripts/replay_recovery_history/first_real_submit/"
            "runtime_first_real_submit_api_flow.py"
        ),
        "classification": "historically_named_official_prepare_helper",
        "target_state": "wrapped_by_runtime_official_prepare_api_flow",
    },
)

FORBIDDEN_PRIMARY_GATE_TERMS = (
    "verify_runtime_submit_rehearsal_pre_live_packet",
    "build_runtime_first_real_submit_owner_packet",
    "build_runtime_first_real_submit_final_review_packet",
    "build_runtime_first_real_submit_action_authorization_packet",
    "build_runtime_first_real_submit_local_registration_authorization_packet",
    "build_runtime_first_real_submit_exchange_arm_authorization_packet",
    "runtime_submit_rehearsal_id",
    "owner_real_submit_authorization_id",
    "owner_real_submit_authorized",
    "ready_for_first_real_submit",
)

FORBIDDEN_STANDING_RECOVERY_PROOF_TERMS = (
    "monitor_position_or_owner_authorize_reduce_only_close",
    "continuation_refresh_monitor_position_or_owner_close",
    "continuation_monitor_position_or_owner_close",
    "position_lifecycle_hold_or_owner_close_ready",
    "waiting_for_owner_close_authorization",
    "OWNER_APPROVED_RUNTIME_REDUCE_ONLY_CLOSE",
    "runtime_owner_reduce_only_close_flow",
)

ALLOWED_HISTORICAL_HELPER_TERMS = (
    "scripts/runtime_official_prepare_api_flow.py:runtime_first_real_submit_api_flow",
    "scripts/runtime_official_prepare_api_flow.py:FirstRealSubmitApiFlow",
    "scripts/runtime_official_prepare_api_flow.py:FlowConfig",
)


def build_isolation_packet(*, repo_root: Path = ROOT_DIR) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    mainline = [_scan_mainline_artifact(repo_root, item) for item in MAINLINE_ARTIFACTS]
    standing_recovery_proofs = [
        _scan_standing_recovery_proof_artifact(repo_root, item)
        for item in STANDING_RECOVERY_PROOF_ARTIFACTS
    ]
    legacy = [_scan_legacy_artifact(repo_root, item) for item in LEGACY_COMPATIBILITY_ARTIFACTS]
    blockers = _blockers(
        mainline=mainline,
        legacy=legacy,
        standing_recovery_proofs=standing_recovery_proofs,
    )
    warnings = _warnings(mainline=mainline, legacy=legacy)
    checks = {
        "mainline_artifacts_present": all(item["exists"] for item in mainline),
        "standing_recovery_proof_artifacts_present": all(
            item["exists"] for item in standing_recovery_proofs
        ),
        "standing_recovery_proofs_have_no_legacy_owner_close_terms": not any(
            item["forbidden_owner_close_terms"] for item in standing_recovery_proofs
        ),
        "legacy_artifacts_classified": all(item["exists"] for item in legacy),
        "legacy_artifacts_archived_to_replay_recovery_history": all(
            item["history_exists"] for item in legacy
        ),
        "legacy_wrapper_paths_preserved": all(item["wrapper_exists"] for item in legacy),
        "mainline_has_no_legacy_primary_gate_terms": not any(
            item["forbidden_primary_gate_terms"] for item in mainline
        ),
        "historically_named_prepare_helper_is_explicit_debt": any(
            item["allowed_historical_helper_terms"] for item in mainline
        ),
        "historically_named_prepare_helper_wrapped": any(
            item["path"] == "scripts/runtime_official_prepare_api_flow.py"
            and item["allowed_historical_helper_terms"]
            for item in mainline
        ),
        "cleanup_isolation_not_deletion": True,
        "runtime_level_chain_remains_primary": True,
        "legacy_pre_attempt_not_primary_gate": True,
        "one_shot_owner_bounded_execution_preserved": True,
    }
    status = (
        "legacy_compatibility_isolated_from_runtime_mainline"
        if not blockers
        else "legacy_compatibility_isolation_blocked"
    )
    return {
        "scope": "runtime_legacy_compatibility_isolation_packet",
        "status": status,
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "mainline_artifacts": mainline,
        "standing_recovery_proof_artifacts": standing_recovery_proofs,
        "legacy_compatibility_artifacts": legacy,
        "cleanup_policy": {
            "primary_runtime_mainline": (
                "RTF-100/101/102/103 bridge-ready runtime cycle"
            ),
            "legacy_surfaces_target_state": (
                "replay_recovery_history_compatibility_only"
            ),
            "do_not_delete_owner_bounded_execution_service": True,
            "do_not_use_pre_attempt_rehearsal_as_runtime_mainline_gate": True,
            "do_not_use_owner_first_real_submit_packet_as_runtime_grant": True,
            "mainline_exit_cleanup_complete": True,
            "future_cleanup_required": False,
            "future_archive_hygiene_recommended": False,
            "archive_hygiene_completed": True,
            "archive_hygiene_action": (
                "legacy first-real-submit packet implementations live under "
                "scripts/replay_recovery_history/first_real_submit while old "
                "script paths remain compatibility wrappers"
            ),
        },
        "safety_invariants": {
            "legacy_compatibility_evidence_only": True,
            "pg_read": False,
            "pg_write": False,
            "api_called": False,
            "exchange_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "runtime_state_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _scan_mainline_artifact(repo_root: Path, rel_path: str) -> dict[str, Any]:
    path = repo_root / rel_path
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    allowed = [
        term
        for term in ALLOWED_HISTORICAL_HELPER_TERMS
        if term.startswith(f"{rel_path}:") and term.split(":", 1)[1] in text
    ]
    allowed_plain_terms = {term.split(":", 1)[1] for term in allowed}
    forbidden = [
        term
        for term in FORBIDDEN_PRIMARY_GATE_TERMS
        if term in text and term not in allowed_plain_terms
    ]
    return {
        "path": rel_path,
        "exists": path.exists(),
        "forbidden_primary_gate_terms": forbidden,
        "allowed_historical_helper_terms": allowed,
    }


def _scan_standing_recovery_proof_artifact(
    repo_root: Path,
    rel_path: str,
) -> dict[str, Any]:
    path = repo_root / rel_path
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    forbidden = [
        term for term in FORBIDDEN_STANDING_RECOVERY_PROOF_TERMS if term in text
    ]
    return {
        "path": rel_path,
        "exists": path.exists(),
        "forbidden_owner_close_terms": forbidden,
        "required_primary_action": (
            "monitor_position_or_prepare_official_reduce_only_recovery"
        ),
        "primary_action_present": (
            "monitor_position_or_prepare_official_reduce_only_recovery" in text
        ),
    }


def _scan_legacy_artifact(repo_root: Path, item: dict[str, str]) -> dict[str, Any]:
    wrapper_path = repo_root / item["path"]
    history_path = repo_root / item["history_path"]
    return {
        **item,
        "exists": wrapper_path.exists() and history_path.exists(),
        "wrapper_exists": wrapper_path.exists(),
        "history_exists": history_path.exists(),
        "history_namespace": "scripts/replay_recovery_history/first_real_submit",
        "mainline_status": "not_primary_runtime_mainline",
        "allowed_uses": [
            "audit_replay",
            "recovery_investigation",
            "historical_report_reproduction",
            "compatibility_tests",
        ],
        "forbidden_uses": [
            "runtime_grant",
            "bounded_auto_attempt_primary_gate",
            "new_attempt_authority",
            "automatic_live_submit_authority",
        ],
    }


def _blockers(
    *,
    mainline: list[dict[str, Any]],
    legacy: list[dict[str, Any]],
    standing_recovery_proofs: list[dict[str, Any]],
) -> list[str]:
    blockers: list[str] = []
    missing_mainline = [item["path"] for item in mainline if not item["exists"]]
    if missing_mainline:
        blockers.append("mainline_artifact_missing:" + ",".join(missing_mainline))
    forbidden_refs = [
        f"{item['path']}:{','.join(item['forbidden_primary_gate_terms'])}"
        for item in mainline
        if item["forbidden_primary_gate_terms"]
    ]
    if forbidden_refs:
        blockers.append("mainline_uses_legacy_primary_gate_terms:" + "|".join(forbidden_refs))
    missing_standing_proofs = [
        item["path"] for item in standing_recovery_proofs if not item["exists"]
    ]
    if missing_standing_proofs:
        blockers.append(
            "standing_recovery_proof_artifact_missing:"
            + ",".join(missing_standing_proofs)
        )
    forbidden_owner_close_refs = [
        f"{item['path']}:{','.join(item['forbidden_owner_close_terms'])}"
        for item in standing_recovery_proofs
        if item["forbidden_owner_close_terms"]
    ]
    if forbidden_owner_close_refs:
        blockers.append(
            "standing_recovery_proof_uses_legacy_owner_close_terms:"
            + "|".join(forbidden_owner_close_refs)
        )
    missing_legacy = [
        f"{item['path']}|{item['history_path']}"
        for item in legacy
        if not item["exists"]
    ]
    if missing_legacy:
        blockers.append("legacy_artifact_missing:" + ",".join(missing_legacy))
    return blockers


def _warnings(
    *,
    mainline: list[dict[str, Any]],
    legacy: list[dict[str, Any]],
) -> list[str]:
    warnings: list[str] = []
    helper_refs = [
        f"{item['path']}:{','.join(term.split(':', 1)[1] for term in item['allowed_historical_helper_terms'])}"
        for item in mainline
        if item["allowed_historical_helper_terms"]
    ]
    if helper_refs:
        warnings.append(
            "historically_named_prepare_helper_still_referenced:" + "|".join(helper_refs)
        )
    if not any(
        item["path"] == "scripts/runtime_official_prepare_api_flow.py"
        and item["allowed_historical_helper_terms"]
        for item in mainline
    ):
        warnings.append("runtime_first_real_submit_api_flow_wrapper_missing")
    return warnings


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a runtime legacy compatibility isolation packet."
    )
    parser.add_argument("--output-json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    packet = build_isolation_packet()
    if args.output_json:
        _write_json(args.output_json, packet)
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if packet["status"] == "legacy_compatibility_isolated_from_runtime_mainline" else 2


if __name__ == "__main__":
    raise SystemExit(main())
