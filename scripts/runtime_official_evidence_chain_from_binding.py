#!/usr/bin/env python3
"""Run official non-executing evidence-chain probe from a binding report."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.runtime_first_real_submit_api_flow import (  # noqa: E402
    API_BASE_ENV as FIRST_REAL_SUBMIT_API_BASE_ENV,
    DEFAULT_API_BASE,
    FirstRealSubmitApiFlow,
    FlowConfig,
    UrlLibApiClient,
    _load_env_file,
)


API_BASE_ENV = "RUNTIME_OFFICIAL_EVIDENCE_CHAIN_API_BASE"


def _api_base(args: argparse.Namespace) -> str:
    return (
        args.api_base
        or os.environ.get(API_BASE_ENV)
        or os.environ.get(FIRST_REAL_SUBMIT_API_BASE_ENV)
        or DEFAULT_API_BASE
    )


def _read_json(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _unwrap_payload(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("api_payload", "body"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            return nested
    return payload


def _fresh_submit_authorization_id(payload: dict[str, Any]) -> str:
    direct = payload.get("fresh_submit_authorization_id")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    preview = payload.get("operator_action_preview")
    if isinstance(preview, dict):
        value = preview.get("fresh_submit_authorization_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ValueError("fresh_submit_authorization_id_missing_from_binding_report")


def _evidence_chain_status(report: dict[str, Any]) -> str:
    ids = report.get("ids") if isinstance(report.get("ids"), dict) else {}
    blockers = [str(item) for item in report.get("blockers") or []]
    warnings = [str(item) for item in report.get("warnings") or []]
    if not blockers:
        return "official_evidence_chain_ready"
    expected_local_prerequisite = any(
        "RuntimeExecutionOrderLifecycleAdapterResult not found" in item
        or "runtimeexecutionorderlifecycleadapterresult_not_found" in item
        for item in blockers + warnings
    )
    prepared_minimum = all(
        ids.get(key)
        for key in (
            "trusted_submit_fact_snapshot_id",
            "submit_idempotency_policy_id",
            "protection_creation_failure_policy_id",
        )
    )
    if expected_local_prerequisite and prepared_minimum:
        return "prepared_machine_evidence_blocked_before_local_order_adapter"
    return "official_evidence_chain_blocked"


def _build_report(
    args: argparse.Namespace,
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    _load_env_file(args.env_file)
    binding_report = _read_json(args.binding_json)
    binding_payload = _unwrap_payload(binding_report)
    authorization_id = _fresh_submit_authorization_id(binding_payload)
    flow = FirstRealSubmitApiFlow(
        client=client or UrlLibApiClient(api_base=_api_base(args)),
        config=FlowConfig(
            api_base=_api_base(args),
            env_file=args.env_file,
            mode="disabled-smoke",
            authorization_id=authorization_id,
            adapter_result_store_implemented=True,
            real_adapter_boundary_implemented=True,
            explain_disabled_smoke_prerequisites=(
                not args.skip_evidence_preparation_probe
            ),
        ),
    )
    flow_report = flow.run()
    report = {
        "scope": "runtime_official_evidence_chain_from_binding",
        "status": _evidence_chain_status(flow_report),
        "binding_report_path": args.binding_json,
        "fresh_submit_authorization_id": authorization_id,
        "flow_report": flow_report,
        "ids": dict(flow_report.get("ids") or {}),
        "blockers": list(flow_report.get("blockers") or []),
        "warnings": list(flow_report.get("warnings") or []),
        "safety_invariants": {
            "uses_official_trading_console_api": True,
            "non_executing": True,
            "owner_confirmed_for_first_real_submit_action": False,
            "execute_real_submit": False,
            "exchange_write_called": False,
            "order_created_by_wrapper": False,
            "order_lifecycle_called_by_wrapper": False,
            "runtime_budget_mutated_by_wrapper": False,
            "withdrawal_or_transfer_created": False,
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
            "Run official non-executing evidence-chain probe from a fresh "
            "authorization binding report."
        ),
    )
    parser.add_argument("--binding-json", required=True)
    parser.add_argument("--output")
    parser.add_argument("--env-file")
    parser.add_argument("--api-base")
    parser.add_argument("--skip-evidence-preparation-probe", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = _build_report(args)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if report["status"] in {
        "official_evidence_chain_ready",
        "prepared_machine_evidence_blocked_before_local_order_adapter",
        "official_evidence_chain_blocked",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
