#!/usr/bin/env python3
"""Classify whether RTF evidence may proceed to scoped local registration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.runtime_first_real_submit_api_flow import (  # noqa: E402
    LOCAL_REGISTRATION_APPROVAL_ENV,
    _local_registration_approval_value,
)


LOCAL_ADAPTER_MISSING_TEXT = "RuntimeExecutionOrderLifecycleAdapterResult not found"
LOCAL_ADAPTER_MISSING_NORMALIZED = (
    "runtimeexecutionorderlifecycleadapterresult_not_found"
)
REQUIRED_EVIDENCE_IDS = (
    "trusted_submit_fact_snapshot_id",
    "submit_idempotency_policy_id",
    "protection_creation_failure_policy_id",
)


def _read_json(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _extract_ids(report: dict[str, Any]) -> dict[str, Any]:
    ids = report.get("ids")
    if isinstance(ids, dict):
        return dict(ids)
    flow = report.get("flow_report")
    if isinstance(flow, dict) and isinstance(flow.get("ids"), dict):
        return dict(flow["ids"])
    return {}


def _extract_authorization_id(report: dict[str, Any], ids: dict[str, Any]) -> str | None:
    for value in (
        report.get("fresh_submit_authorization_id"),
        ids.get("authorization_id"),
    ):
        if isinstance(value, str) and value.strip():
            return value.strip()
    flow = report.get("flow_report")
    if isinstance(flow, dict):
        nested_ids = flow.get("ids")
        if isinstance(nested_ids, dict):
            value = nested_ids.get("authorization_id")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _messages(report: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("blockers", "warnings"):
        values.extend(str(item) for item in report.get(key) or [])
    flow = report.get("flow_report")
    if isinstance(flow, dict):
        for key in ("blockers", "warnings"):
            values.extend(str(item) for item in flow.get(key) or [])
    return values


def _at_expected_local_adapter_boundary(report: dict[str, Any]) -> bool:
    status = str(report.get("status") or "")
    if status == "prepared_machine_evidence_blocked_before_local_order_adapter":
        return True
    return any(
        LOCAL_ADAPTER_MISSING_TEXT in item
        or LOCAL_ADAPTER_MISSING_NORMALIZED in item.lower()
        for item in _messages(report)
    )


def _operator_command_preview(
    *,
    authorization_id: str,
    api_base: str | None,
    env_file: str | None,
) -> dict[str, Any]:
    command = [
        "python",
        "scripts/runtime_first_real_submit_api_flow.py",
        "--mode",
        "arm",
        "--authorization-id",
        authorization_id,
        "--record-attempt-consumption",
        "--skip-exchange-arm",
    ]
    if api_base:
        command.extend(["--api-base", api_base])
    if env_file:
        command.extend(["--env-file", env_file])
    return {
        "scope": "local_registration_only_no_exchange_arm",
        "required_env": {
            LOCAL_REGISTRATION_APPROVAL_ENV: (
                _local_registration_approval_value(authorization_id)
            )
        },
        "command": command,
    }


def _build_report(args: argparse.Namespace) -> dict[str, Any]:
    evidence_report = _read_json(args.evidence_chain_json)
    ids = _extract_ids(evidence_report)
    blockers: list[str] = []
    warnings: list[str] = []

    authorization_id = _extract_authorization_id(evidence_report, ids)
    if not authorization_id:
        blockers.append("fresh_submit_authorization_id_missing")

    missing_evidence = [key for key in REQUIRED_EVIDENCE_IDS if not ids.get(key)]
    if missing_evidence:
        blockers.append("required_machine_evidence_missing")
        blockers.extend(f"{key}_missing" for key in missing_evidence)

    at_local_adapter_boundary = _at_expected_local_adapter_boundary(evidence_report)
    if not at_local_adapter_boundary:
        blockers.append("evidence_chain_not_at_local_order_adapter_boundary")

    source_kind = args.source_kind
    explicit_scoped_proof = bool(args.allow_scoped_local_registration_proof)
    if source_kind == "sample_rehearsal":
        warnings.append("sample_rehearsal_is_not_current_live_alpha")
        if not explicit_scoped_proof:
            blockers.append("sample_rehearsal_local_registration_not_allowed")
    elif source_kind == "scoped_local_registration_proof":
        if not explicit_scoped_proof:
            blockers.append("scoped_local_registration_proof_flag_missing")
    elif source_kind == "current_live_signal":
        warnings.append("current_live_signal_must_still_pass_official_gates")
    else:
        blockers.append(f"unsupported_source_kind:{source_kind}")

    if blockers:
        if "sample_rehearsal_local_registration_not_allowed" in blockers:
            status = "blocked_sample_rehearsal_local_registration_not_allowed"
        elif "required_machine_evidence_missing" in blockers:
            status = "blocked_required_machine_evidence_missing"
        elif "evidence_chain_not_at_local_order_adapter_boundary" in blockers:
            status = "blocked_evidence_chain_not_at_local_order_adapter_boundary"
        else:
            status = "blocked_scoped_local_registration_boundary"
    elif source_kind == "sample_rehearsal":
        status = "ready_for_scoped_sample_local_registration_proof"
    else:
        status = "ready_for_scoped_local_registration_proof"

    command_preview = None
    if authorization_id:
        command_preview = _operator_command_preview(
            authorization_id=authorization_id,
            api_base=args.api_base,
            env_file=args.env_file,
        )

    report = {
        "scope": "runtime_scoped_local_order_adapter_boundary_from_evidence",
        "status": status,
        "source_kind": source_kind,
        "evidence_chain_report_path": args.evidence_chain_json,
        "fresh_submit_authorization_id": authorization_id,
        "prepared_evidence_ids": {
            key: ids.get(key)
            for key in (
                *REQUIRED_EVIDENCE_IDS,
                "attempt_outcome_policy_id",
                "post_submit_budget_settlement_persistence_evidence_id",
            )
            if ids.get(key)
        },
        "at_expected_local_order_adapter_boundary": at_local_adapter_boundary,
        "operator_command_preview": command_preview,
        "blockers": blockers,
        "warnings": warnings,
        "safety_invariants": {
            "uses_official_trading_console_api": False,
            "boundary_classification_only": True,
            "non_executing": True,
            "local_order_registration_called": False,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "sample_rehearsal_cannot_register_by_default": True,
        },
    }
    if args.output:
        Path(args.output).expanduser().write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return report


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Classify whether an RTF-016 evidence report may proceed to scoped "
            "local order adapter registration."
        ),
    )
    parser.add_argument("--evidence-chain-json", required=True)
    parser.add_argument(
        "--source-kind",
        choices=[
            "sample_rehearsal",
            "current_live_signal",
            "scoped_local_registration_proof",
        ],
        default="sample_rehearsal",
    )
    parser.add_argument("--allow-scoped-local-registration-proof", action="store_true")
    parser.add_argument("--api-base")
    parser.add_argument("--env-file")
    parser.add_argument("--output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = _build_report(args)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if report["status"].startswith(("ready_", "blocked_")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
