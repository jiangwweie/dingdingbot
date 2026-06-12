#!/usr/bin/env python3
"""Collect early readiness facts from existing runtime evidence reports.

This script reduces manual evidence-field copying without changing authority:
it only reads already-produced JSON reports/snapshots and emits a
RuntimeExecutableSubmitReadinessEvidence-compatible JSON when those facts are
complete. Missing trusted facts remain blockers.
"""

from __future__ import annotations

import argparse
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


READY_STATUS = "ready_for_readiness_evidence_resolution"
BLOCKED_STATUS = "blocked_early_readiness_facts_incomplete"

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


def _read_json(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    value = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return _unwrap(value)


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("api_payload", "packet", "body", "readiness", "decision"):
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


def _present(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return bool(str(value or "").strip())


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if _present(value):
            return value
    return None


def _status(payload: dict[str, Any]) -> str:
    return str(payload.get("status") or payload.get("verdict") or "").strip()


def _is_ready(payload: dict[str, Any], *accepted: str) -> bool:
    return _status(payload) in set(accepted)


def _source_trusted_and_fresh(source: Any) -> bool:
    if not isinstance(source, dict):
        return False
    freshness = str(source.get("freshness") or "").lower()
    return source.get("trusted") is not False and freshness in {"fresh", ""}


def _collect_final_gate(payload: dict[str, Any], evidence: dict[str, Any]) -> None:
    evidence["final_gate_preview_id"] = _optional_str(
        _first(payload, "final_gate_preview_id", "preview_id", "packet_id", "id")
    )
    verdict = str(payload.get("verdict") or payload.get("status") or "").upper()
    evidence["final_gate_passed"] = bool(
        payload.get("final_gate_passed") is True
        or verdict == "PASS"
        or str(payload.get("status") or "") == "ready_for_final_gate_preflight"
    )
    candidate_snapshot = payload.get("candidate_snapshot")
    if isinstance(candidate_snapshot, dict):
        if candidate_snapshot.get("protection_reference_present") is True:
            evidence["protection_required_and_ready"] = True


def _collect_trusted_facts(payload: dict[str, Any], evidence: dict[str, Any]) -> None:
    evidence["trusted_submit_fact_snapshot_id"] = _optional_str(
        _first(payload, "trusted_submit_fact_snapshot_id", "snapshot_id", "id")
    )
    ready = _is_ready(payload, "ready_for_first_real_submit_confirmation")
    evidence["account_facts_fresh"] = bool(
        ready
        and payload.get("facts_fresh_enough") is not False
        and _source_trusted_and_fresh(payload.get("account_fact_source"))
    )
    evidence["active_position_source_trusted"] = bool(
        ready and _source_trusted_and_fresh(payload.get("active_position_source"))
    )
    evidence["protection_required_and_ready"] = bool(
        evidence.get("protection_required_and_ready")
        or (ready and _source_trusted_and_fresh(payload.get("protection_state_source")))
    )


def _collect_idempotency(payload: dict[str, Any], evidence: dict[str, Any]) -> None:
    evidence["submit_idempotency_policy_id"] = _optional_str(
        _first(payload, "submit_idempotency_policy_id", "policy_id", "id")
    )
    evidence["duplicate_submit_guard_ready"] = bool(
        _is_ready(payload, "ready_for_non_executing_policy_confirmation")
        and payload.get("blocks_concurrent_submit_without_lock") is not False
        and payload.get("replay_existing_result_on_duplicate") is not False
    )


def _collect_id(
    payload: dict[str, Any],
    evidence: dict[str, Any],
    *,
    target: str,
    keys: tuple[str, ...],
    ready_statuses: tuple[str, ...] = (),
) -> None:
    if ready_statuses and not _is_ready(payload, *ready_statuses):
        return
    evidence[target] = _optional_str(_first(payload, *keys))


def _evidence_payload(args: argparse.Namespace) -> tuple[dict[str, Any], list[str]]:
    evidence: dict[str, Any] = {
        "final_gate_preview_id": None,
        "final_gate_passed": False,
        "runtime_grant_authorization_id": _optional_str(
            args.runtime_grant_authorization_id
        ),
        "owner_real_submit_authorization_id": _optional_str(
            args.owner_real_submit_authorization_id
        ),
        "trusted_submit_fact_snapshot_id": None,
        "submit_idempotency_policy_id": None,
        "attempt_outcome_policy_id": None,
        "protection_creation_failure_policy_id": None,
        "local_registration_enablement_decision_id": None,
        "exchange_submit_enablement_decision_id": None,
        "exchange_submit_action_authorization_id": None,
        "order_lifecycle_submit_enablement_id": None,
        "exchange_submit_adapter_enablement_id": None,
        "deployment_readiness_evidence_id": None,
        "protection_required_and_ready": False,
        "active_position_source_trusted": False,
        "account_facts_fresh": False,
        "duplicate_submit_guard_ready": False,
        "legacy_runtime_submit_rehearsal_id": _optional_str(
            args.legacy_runtime_submit_rehearsal_id
        ),
        "durable_exchange_submit_execution_result_id": _optional_str(
            args.durable_exchange_submit_execution_result_id
        ),
    }
    sources: list[str] = []

    final_gate = _read_json(args.final_gate_preview_json)
    if final_gate:
        _collect_final_gate(final_gate, evidence)
        sources.append("final_gate_preview_json")

    trusted_facts = _read_json(args.trusted_submit_facts_json)
    if trusted_facts:
        _collect_trusted_facts(trusted_facts, evidence)
        sources.append("trusted_submit_facts_json")

    idempotency = _read_json(args.submit_idempotency_json)
    if idempotency:
        _collect_idempotency(idempotency, evidence)
        sources.append("submit_idempotency_json")

    _collect_id(
        _read_json(args.attempt_outcome_policy_json),
        evidence,
        target="attempt_outcome_policy_id",
        keys=("attempt_outcome_policy_id", "policy_id", "id"),
    )
    _collect_id(
        _read_json(args.protection_failure_policy_json),
        evidence,
        target="protection_creation_failure_policy_id",
        keys=("protection_creation_failure_policy_id", "policy_id", "id"),
    )
    _collect_id(
        _read_json(args.local_registration_enablement_json),
        evidence,
        target="local_registration_enablement_decision_id",
        keys=("local_registration_enablement_decision_id", "decision_id", "id"),
        ready_statuses=("ready_for_local_registration_action",),
    )
    _collect_id(
        _read_json(args.exchange_submit_enablement_json),
        evidence,
        target="exchange_submit_enablement_decision_id",
        keys=("exchange_submit_enablement_decision_id", "decision_id", "id"),
        ready_statuses=("ready_for_exchange_submit_action",),
    )
    _collect_id(
        _read_json(args.exchange_action_authorization_json),
        evidence,
        target="exchange_submit_action_authorization_id",
        keys=("exchange_submit_action_authorization_id", "authorization_id", "id"),
    )
    _collect_id(
        _read_json(args.order_lifecycle_submit_enablement_json),
        evidence,
        target="order_lifecycle_submit_enablement_id",
        keys=("order_lifecycle_submit_enablement_id", "enablement_id", "id"),
    )
    _collect_id(
        _read_json(args.exchange_adapter_enablement_json),
        evidence,
        target="exchange_submit_adapter_enablement_id",
        keys=("exchange_submit_adapter_enablement_id", "enablement_id", "id"),
    )
    _collect_id(
        _read_json(args.deployment_readiness_json),
        evidence,
        target="deployment_readiness_evidence_id",
        keys=("deployment_readiness_evidence_id", "readiness_id", "id"),
        ready_statuses=("ready_for_manual_gateway_binding",),
    )
    return evidence, sources


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
    evidence_payload, sources = _evidence_payload(args)
    missing = _missing_fields(evidence_payload)
    blockers = [f"{field}_missing" for field in missing]
    warnings: list[str] = []
    if not _present(evidence_payload.get("deployment_readiness_evidence_id")):
        warnings.append("deployment_readiness_evidence_id_missing")

    evidence: dict[str, Any] | None = None
    evidence_path: str | None = None
    status = BLOCKED_STATUS
    if not blockers:
        model = RuntimeExecutableSubmitReadinessEvidence(**evidence_payload)
        evidence = model.model_dump(mode="json")
        if args.artifact_dir:
            path = Path(args.artifact_dir).expanduser() / (
                "02-collected-readiness-evidence.json"
            )
            _write_json(path, evidence)
            evidence_path = str(path)
        status = READY_STATUS

    report = {
        "scope": "runtime_early_readiness_fact_collector",
        "status": status,
        "runtime_instance_id": args.runtime_instance_id,
        "collected_source_kinds": sources,
        "missing_fields": missing,
        "evidence": evidence,
        "evidence_json_path": evidence_path,
        "blockers": _dedupe(blockers),
        "warnings": _dedupe(warnings),
        "safety_invariants": {
            "does_not_call_api": True,
            "does_not_create_execution_intent": True,
            "does_not_create_order": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
            "does_not_mutate_runtime": True,
            "does_not_create_withdrawal_or_transfer": True,
            "does_not_invent_missing_facts": True,
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


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect early readiness facts from existing JSON reports."
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--runtime-grant-authorization-id")
    parser.add_argument("--owner-real-submit-authorization-id")
    parser.add_argument("--final-gate-preview-json")
    parser.add_argument("--trusted-submit-facts-json")
    parser.add_argument("--submit-idempotency-json")
    parser.add_argument("--attempt-outcome-policy-json")
    parser.add_argument("--protection-failure-policy-json")
    parser.add_argument("--local-registration-enablement-json")
    parser.add_argument("--exchange-submit-enablement-json")
    parser.add_argument("--exchange-action-authorization-json")
    parser.add_argument("--order-lifecycle-submit-enablement-json")
    parser.add_argument("--exchange-adapter-enablement-json")
    parser.add_argument("--deployment-readiness-json")
    parser.add_argument("--legacy-runtime-submit-rehearsal-id")
    parser.add_argument("--durable-exchange-submit-execution-result-id")
    parser.add_argument("--artifact-dir")
    parser.add_argument("--output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = _build_report(args)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if report["status"] in {READY_STATUS, BLOCKED_STATUS} else 2


if __name__ == "__main__":
    raise SystemExit(main())
