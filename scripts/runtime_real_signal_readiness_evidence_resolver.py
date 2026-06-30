#!/usr/bin/env python3
"""Resolve readiness evidence for a real strategy signal path.

The resolver is deliberately conservative: it may assemble
RuntimeExecutableSubmitReadinessEvidence from explicit trusted evidence IDs,
but it must not invent FinalGate, account, position, idempotency, or protection
facts.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys
import time
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.domain.runtime_executable_submit_readiness import (  # noqa: E402
    RuntimeExecutableSubmitReadinessEvidence,
)


READY_STATUS = "ready_for_readiness_evidence"
BLOCKED_STATUS = "blocked_readiness_evidence_unresolved"

_REQUIRED_ID_FIELDS = (
    "final_gate_preview_id",
    "trusted_submit_fact_snapshot_id",
    "submit_idempotency_policy_id",
    "attempt_outcome_policy_id",
    "protection_creation_failure_policy_id",
    "local_registration_enablement_decision_id",
    "exchange_submit_enablement_decision_id",
    "exchange_submit_action_authorization_id",
    "order_lifecycle_submit_enablement_id",
    "exchange_submit_adapter_enablement_id",
)

_REQUIRED_TRUE_FIELDS = (
    "final_gate_passed",
    "protection_required_and_ready",
    "active_position_source_trusted",
    "account_facts_fresh",
    "duplicate_submit_guard_ready",
)


def _read_json_file(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return _unwrap_payload(value)


def _unwrap_payload(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("api_payload", "artifact", "body"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            return nested
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _present(value: str | None) -> bool:
    return bool(str(value or "").strip())


def _optional_str(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _source_status(source: dict[str, Any]) -> str:
    return str(source.get("status") or "")


def _source_ready(source: dict[str, Any]) -> bool:
    return (
        _source_status(source) == "persisted_ready_intent_draft"
        and source.get("ready_for_official_handoff_source") is not False
    )


def _evidence_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "final_gate_preview_id": _optional_str(args.final_gate_preview_id),
        "final_gate_passed": bool(args.final_gate_passed),
        "runtime_grant_authorization_id": _optional_str(
            args.runtime_grant_authorization_id
        ),
        "owner_real_submit_authorization_id": _optional_str(
            args.owner_real_submit_authorization_id
        ),
        "trusted_submit_fact_snapshot_id": _optional_str(
            args.trusted_submit_fact_snapshot_id
        ),
        "submit_idempotency_policy_id": _optional_str(
            args.submit_idempotency_policy_id
        ),
        "attempt_outcome_policy_id": _optional_str(args.attempt_outcome_policy_id),
        "protection_creation_failure_policy_id": _optional_str(
            args.protection_creation_failure_policy_id
        ),
        "local_registration_enablement_decision_id": _optional_str(
            args.local_registration_enablement_decision_id
        ),
        "exchange_submit_enablement_decision_id": _optional_str(
            args.exchange_submit_enablement_decision_id
        ),
        "exchange_submit_action_authorization_id": _optional_str(
            args.exchange_submit_action_authorization_id
        ),
        "order_lifecycle_submit_enablement_id": _optional_str(
            args.order_lifecycle_submit_enablement_id
        ),
        "exchange_submit_adapter_enablement_id": _optional_str(
            args.exchange_submit_adapter_enablement_id
        ),
        "deployment_readiness_evidence_id": _optional_str(
            args.deployment_readiness_evidence_id
        ),
        "protection_required_and_ready": bool(args.protection_required_and_ready),
        "active_position_source_trusted": bool(args.active_position_source_trusted),
        "account_facts_fresh": bool(args.account_facts_fresh),
        "duplicate_submit_guard_ready": bool(args.duplicate_submit_guard_ready),
        "legacy_runtime_submit_rehearsal_id": _optional_str(
            args.legacy_runtime_submit_rehearsal_id
        ),
        "durable_exchange_submit_execution_result_id": _optional_str(
            args.durable_exchange_submit_execution_result_id
        ),
    }


def _missing_fields(payload: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in _REQUIRED_ID_FIELDS:
        if not _present(payload.get(field)):
            missing.append(field)
    if not (
        _present(payload.get("runtime_grant_authorization_id"))
        or _present(payload.get("owner_real_submit_authorization_id"))
    ):
        missing.append("runtime_grant_or_owner_real_submit_authorization_id")
    for field in _REQUIRED_TRUE_FIELDS:
        if payload.get(field) is not True:
            missing.append(field)
    return missing


def _build_report(args: argparse.Namespace) -> dict[str, Any]:
    source = _read_json_file(args.intent_draft_source_json)
    payload = _evidence_payload(args)
    missing = _missing_fields(payload)
    blockers: list[str] = []
    warnings: list[str] = []

    if str(source.get("runtime_instance_id") or args.runtime_instance_id) != (
        args.runtime_instance_id
    ):
        blockers.append("runtime_instance_id_mismatch")
    if not _source_ready(source):
        blockers.append("intent_draft_source_not_ready_for_readiness_evidence")
    blockers.extend(f"{field}_missing" for field in missing)
    if not _present(payload.get("deployment_readiness_evidence_id")):
        warnings.append("deployment_readiness_evidence_id_missing")
    if _present(payload.get("legacy_runtime_submit_rehearsal_id")):
        warnings.append("legacy_runtime_submit_rehearsal_id_is_compatibility_only")
    if _present(payload.get("durable_exchange_submit_execution_result_id")):
        warnings.append("durable_execution_result_is_post_submit_evidence_only")

    evidence_path: str | None = None
    evidence: dict[str, Any] | None = None
    status = BLOCKED_STATUS
    if not blockers:
        model = RuntimeExecutableSubmitReadinessEvidence(**payload)
        evidence = model.model_dump(mode="json")
        if args.artifact_dir:
            evidence_file = Path(args.artifact_dir).expanduser() / (
                "02-auto-readiness-evidence.json"
            )
            _write_json(evidence_file, evidence)
            evidence_path = str(evidence_file)
        status = READY_STATUS

    report = {
        "scope": "runtime_real_signal_readiness_evidence_resolver",
        "status": status,
        "runtime_instance_id": args.runtime_instance_id,
        "intent_draft_source_status": _source_status(source),
        "intent_draft_source_artifact_id": source.get("artifact_id"),
        "signal_evaluation_id": source.get("signal_evaluation_id"),
        "order_candidate_id": source.get("order_candidate_id"),
        "runtime_execution_intent_draft_id": source.get(
            "runtime_execution_intent_draft_id"
        ),
        "missing_fields": missing,
        "evidence_json_path": evidence_path,
        "evidence": evidence,
        "blockers": _dedupe(blockers),
        "warnings": _dedupe(warnings),
        "safety_invariants": {
            "does_not_call_api": True,
            "does_not_create_execution_intent": True,
            "does_not_create_order": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
            "does_not_submit_order": True,
            "does_not_mutate_runtime": True,
            "does_not_create_withdrawal_or_transfer": True,
            "does_not_invent_trusted_facts": True,
        },
        "created_at_ms": int(time.time() * 1000),
    }
    if args.output:
        _write_json(Path(args.output).expanduser(), report)
    return report


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _add_evidence_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--final-gate-preview-id")
    parser.add_argument("--final-gate-passed", action="store_true")
    parser.add_argument("--runtime-grant-authorization-id")
    parser.add_argument("--owner-real-submit-authorization-id")
    parser.add_argument("--trusted-submit-fact-snapshot-id")
    parser.add_argument("--submit-idempotency-policy-id")
    parser.add_argument("--attempt-outcome-policy-id")
    parser.add_argument("--protection-creation-failure-policy-id")
    parser.add_argument("--local-registration-enablement-decision-id")
    parser.add_argument("--exchange-submit-enablement-decision-id")
    parser.add_argument("--exchange-submit-action-authorization-id")
    parser.add_argument("--order-lifecycle-submit-enablement-id")
    parser.add_argument("--exchange-submit-adapter-enablement-id")
    parser.add_argument("--deployment-readiness-evidence-id")
    parser.add_argument("--protection-required-and-ready", action="store_true")
    parser.add_argument("--active-position-source-trusted", action="store_true")
    parser.add_argument("--account-facts-fresh", action="store_true")
    parser.add_argument("--duplicate-submit-guard-ready", action="store_true")
    parser.add_argument("--legacy-runtime-submit-rehearsal-id")
    parser.add_argument("--durable-exchange-submit-execution-result-id")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve a real signal readiness evidence JSON without inventing "
            "trusted facts."
        ),
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--intent-draft-source-json", required=True)
    parser.add_argument("--artifact-dir")
    parser.add_argument("--output")
    _add_evidence_args(parser)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    with redirect_stdout(sys.stderr):
        report = _build_report(args)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if report["status"] in {READY_STATUS, BLOCKED_STATUS} else 2


if __name__ == "__main__":
    raise SystemExit(main())
