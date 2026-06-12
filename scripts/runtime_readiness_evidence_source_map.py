#!/usr/bin/env python3
"""Classify readiness evidence sources for the runtime submit chain.

This inventory prevents circular wiring: evidence that is only machine-prepared
after a fresh submit authorization must not be treated as automatically
available before the persisted-draft-source readiness preview.
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


SOURCE_MAP: dict[str, dict[str, str]] = {
    "final_gate_preview_id": {
        "source_class": "early_current_final_gate_preview",
        "blocking_policy": "block_before_readiness",
    },
    "final_gate_passed": {
        "source_class": "early_current_final_gate_preview",
        "blocking_policy": "block_before_readiness",
    },
    "runtime_grant_authorization_id": {
        "source_class": "explicit_runtime_grant_or_owner_authorization",
        "blocking_policy": "block_before_readiness_if_no_authorization",
    },
    "owner_real_submit_authorization_id": {
        "source_class": "explicit_runtime_grant_or_owner_authorization",
        "blocking_policy": "block_before_readiness_if_no_authorization",
    },
    "trusted_submit_fact_snapshot_id": {
        "source_class": "trusted_current_submit_fact_snapshot",
        "blocking_policy": "block_before_readiness",
    },
    "submit_idempotency_policy_id": {
        "source_class": "late_machine_preparable_after_fresh_authorization",
        "blocking_policy": "block_before_readiness_unless_existing_snapshot",
    },
    "attempt_outcome_policy_id": {
        "source_class": "existing_attempt_policy_or_post_submit_policy",
        "blocking_policy": "block_before_readiness",
    },
    "protection_creation_failure_policy_id": {
        "source_class": "late_machine_preparable_after_execution_intent",
        "blocking_policy": "block_before_readiness_unless_existing_policy",
    },
    "local_registration_enablement_decision_id": {
        "source_class": "scoped_local_registration_boundary_decision",
        "blocking_policy": "block_before_readiness",
    },
    "exchange_submit_enablement_decision_id": {
        "source_class": "scoped_exchange_submit_enablement_decision",
        "blocking_policy": "block_before_readiness",
    },
    "exchange_submit_action_authorization_id": {
        "source_class": "scoped_exchange_submit_action_authorization",
        "blocking_policy": "block_before_readiness",
    },
    "order_lifecycle_submit_enablement_id": {
        "source_class": "order_lifecycle_submit_boundary_enablement",
        "blocking_policy": "block_before_readiness",
    },
    "exchange_submit_adapter_enablement_id": {
        "source_class": "exchange_adapter_boundary_enablement",
        "blocking_policy": "block_before_readiness",
    },
    "deployment_readiness_evidence_id": {
        "source_class": "current_deployment_readiness_evidence",
        "blocking_policy": "warn_in_current_domain_block_before_real_submit",
    },
    "protection_required_and_ready": {
        "source_class": "trusted_protection_state_fact",
        "blocking_policy": "block_before_readiness",
    },
    "active_position_source_trusted": {
        "source_class": "trusted_position_projection_or_reconciliation_fact",
        "blocking_policy": "block_before_readiness",
    },
    "account_facts_fresh": {
        "source_class": "trusted_account_fact_snapshot",
        "blocking_policy": "block_before_readiness",
    },
    "duplicate_submit_guard_ready": {
        "source_class": "idempotency_and_adapter_duplicate_guard",
        "blocking_policy": "block_before_readiness",
    },
}

_LATE_EVIDENCE_ID_KEYS = {
    "trusted_submit_fact_snapshot_id",
    "submit_idempotency_policy_id",
    "attempt_outcome_policy_id",
    "protection_creation_failure_policy_id",
}


def _read_json(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    value = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _resolver_evidence(resolver_report: dict[str, Any]) -> dict[str, Any]:
    evidence = resolver_report.get("evidence")
    return evidence if isinstance(evidence, dict) else {}


def _late_available_ids(evidence_chain_report: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for source in (
        evidence_chain_report.get("ids"),
        (
            evidence_chain_report.get("flow_report", {})
            if isinstance(evidence_chain_report.get("flow_report"), dict)
            else {}
        ).get("ids"),
        (
            evidence_chain_report.get("flow_report", {})
            if isinstance(evidence_chain_report.get("flow_report"), dict)
            else {}
        ).get("available_evidence_ids"),
    ):
        if not isinstance(source, dict):
            continue
        for key, value in source.items():
            text = str(value or "").strip()
            if text:
                result[str(key)] = text
    return result


def _present(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return bool(str(value or "").strip())


def _coverage_status(
    *,
    field: str,
    resolver_evidence: dict[str, Any],
    late_ids: dict[str, str],
) -> tuple[str, str | None]:
    value = resolver_evidence.get(field)
    if _present(value):
        return "provided_by_readiness_evidence", str(value)
    if field in _LATE_EVIDENCE_ID_KEYS and late_ids.get(field):
        return "available_only_after_binding", late_ids[field]
    return "missing_before_readiness", None


def _build_report(args: argparse.Namespace) -> dict[str, Any]:
    resolver_report = _read_json(args.resolver_report_json)
    evidence_chain_report = _read_json(args.evidence_chain_json)
    evidence = _resolver_evidence(resolver_report)
    late_ids = _late_available_ids(evidence_chain_report)

    rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    for field, info in SOURCE_MAP.items():
        status, evidence_id = _coverage_status(
            field=field,
            resolver_evidence=evidence,
            late_ids=late_ids,
        )
        if status == "missing_before_readiness" and info["blocking_policy"].startswith(
            "block"
        ):
            blockers.append(f"{field}_missing_before_readiness")
        if status == "available_only_after_binding":
            warnings.append(f"{field}_is_late_machine_evidence_not_early_input")
        rows.append(
            {
                "field": field,
                "source_class": info["source_class"],
                "blocking_policy": info["blocking_policy"],
                "coverage_status": status,
                "evidence_id": evidence_id,
            }
        )

    report = {
        "scope": "runtime_readiness_evidence_source_map",
        "status": "readiness_evidence_source_map_ready",
        "runtime_instance_id": args.runtime_instance_id,
        "rows": rows,
        "blockers": _dedupe(blockers),
        "warnings": _dedupe(warnings),
        "summary": {
            "fields_total": len(rows),
            "provided_by_readiness_evidence": sum(
                1 for row in rows if row["coverage_status"] == "provided_by_readiness_evidence"
            ),
            "available_only_after_binding": sum(
                1 for row in rows if row["coverage_status"] == "available_only_after_binding"
            ),
            "missing_before_readiness": sum(
                1 for row in rows if row["coverage_status"] == "missing_before_readiness"
            ),
        },
        "safety_invariants": {
            "does_not_call_api": True,
            "does_not_create_execution_intent": True,
            "does_not_create_order": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
            "does_not_mutate_runtime": True,
            "does_not_create_withdrawal_or_transfer": True,
            "classifies_late_evidence_without_promoting_it_to_early_input": True,
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
        description="Classify runtime readiness evidence source availability."
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--resolver-report-json")
    parser.add_argument("--evidence-chain-json")
    parser.add_argument("--output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = _build_report(args)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if report["status"] == "readiness_evidence_source_map_ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
