#!/usr/bin/env python3
"""Run or preview a scoped local-registration proof from RTF evidence."""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import json
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
from src.domain.standing_authorization import (  # noqa: E402
    OWNER_STANDING_AUTHORIZATION_OPERATOR_ID,
    OWNER_STANDING_AUTHORIZATION_REASON,
    OWNER_STANDING_AUTHORIZATION_REFERENCE,
)
from scripts.runtime_scoped_local_order_adapter_boundary_from_evidence import (  # noqa: E402
    _build_report as build_boundary_report,
)


API_BASE_ENV = "RUNTIME_SCOPED_LOCAL_REGISTRATION_PROOF_API_BASE"


def _api_base(args: argparse.Namespace) -> str:
    import os

    return (
        args.api_base
        or os.environ.get(API_BASE_ENV)
        or os.environ.get(FIRST_REAL_SUBMIT_API_BASE_ENV)
        or DEFAULT_API_BASE
    )


def _prepared_ids(boundary_report: dict[str, Any]) -> dict[str, str]:
    values = boundary_report.get("prepared_evidence_ids")
    if not isinstance(values, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in values.items()
        if value is not None and str(value).strip()
    }


def _build_flow_config(
    args: argparse.Namespace,
    *,
    authorization_id: str,
    prepared_ids: dict[str, str],
) -> FlowConfig:
    return FlowConfig(
        api_base=_api_base(args),
        env_file=args.env_file,
        mode="arm",
        authorization_id=authorization_id,
        owner_operator_id=args.owner_operator_id,
        owner_confirmation_reference=args.owner_confirmation_reference,
        reason=args.reason,
        outcome_kind=args.outcome_kind,
        skip_next_attempt_gate_check=args.skip_next_attempt_gate_check,
        skip_order_candidate_usage_check=True,
        enable_local_registration=True,
        arm_exchange_submit_adapter=False,
        record_gateway_readiness=False,
        preview_disabled_first_real_submit_action=False,
        execute_real_submit=False,
        record_attempt_consumption=True,
        standing_authorized_scoped_evidence_preparation=True,
        record_post_submit_accounting=False,
        record_post_submit_reconciliation=False,
        trusted_submit_fact_snapshot_id=prepared_ids.get(
            "trusted_submit_fact_snapshot_id"
        ),
        submit_idempotency_policy_id=prepared_ids.get(
            "submit_idempotency_policy_id"
        ),
        attempt_outcome_policy_id=prepared_ids.get("attempt_outcome_policy_id"),
        protection_creation_failure_policy_id=prepared_ids.get(
            "protection_creation_failure_policy_id"
        ),
    )


def _classify_execute_result(flow_report: dict[str, Any]) -> str:
    blockers = list(flow_report.get("blockers") or [])
    ids = flow_report.get("ids") if isinstance(flow_report.get("ids"), dict) else {}
    if not blockers and ids.get("local_registration_adapter_result_id"):
        return "scoped_local_registration_proof_recorded"
    if any(
        "owner_runtime_local_registration_env_confirmation_missing" in item
        for item in blockers
    ):
        return "blocked_local_registration_env_confirmation_missing"
    return "blocked_scoped_local_registration_proof"


def _build_report(
    args: argparse.Namespace,
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    _load_env_file(args.env_file)
    boundary_report = build_boundary_report(args)
    authorization_id = boundary_report.get("fresh_submit_authorization_id")
    boundary_status = str(boundary_report.get("status") or "")
    source_kind = str(boundary_report.get("source_kind") or "")
    boundary_ready = boundary_status.startswith("ready_")

    blockers = list(boundary_report.get("blockers") or [])
    warnings = list(boundary_report.get("warnings") or [])
    if source_kind == "sample_rehearsal" and not args.allow_sample_local_registration:
        if "sample_rehearsal_execute_not_allowed" not in blockers:
            blockers.append("sample_rehearsal_execute_not_allowed")

    if not args.execute_scoped_local_registration_proof:
        status = (
            "ready_for_scoped_local_registration_proof_dry_run"
            if boundary_ready and not blockers
            else "blocked_scoped_local_registration_proof_dry_run"
        )
        return {
            "scope": "runtime_scoped_local_registration_proof_from_evidence",
            "status": status,
            "mode": "dry_run",
            "boundary_report": boundary_report,
            "flow_report": None,
            "fresh_submit_authorization_id": authorization_id,
            "blockers": blockers,
            "warnings": warnings,
            "safety_invariants": _safety(
                local_registration_attempted=False,
                local_registration_recorded=False,
            ),
        }

    if not boundary_ready or blockers:
        return {
            "scope": "runtime_scoped_local_registration_proof_from_evidence",
            "status": "blocked_scoped_local_registration_proof_precondition",
            "mode": "execute_scoped_local_registration_proof",
            "boundary_report": boundary_report,
            "flow_report": None,
            "fresh_submit_authorization_id": authorization_id,
            "blockers": blockers or ["boundary_report_not_ready"],
            "warnings": warnings,
            "safety_invariants": _safety(
                local_registration_attempted=False,
                local_registration_recorded=False,
            ),
        }

    if not isinstance(authorization_id, str) or not authorization_id.strip():
        return {
            "scope": "runtime_scoped_local_registration_proof_from_evidence",
            "status": "blocked_scoped_local_registration_proof_precondition",
            "mode": "execute_scoped_local_registration_proof",
            "boundary_report": boundary_report,
            "flow_report": None,
            "fresh_submit_authorization_id": None,
            "blockers": ["fresh_submit_authorization_id_missing"],
            "warnings": warnings,
            "safety_invariants": _safety(
                local_registration_attempted=False,
                local_registration_recorded=False,
            ),
        }

    flow = FirstRealSubmitApiFlow(
        client=client or UrlLibApiClient(api_base=_api_base(args)),
        config=_build_flow_config(
            args,
            authorization_id=authorization_id,
            prepared_ids=_prepared_ids(boundary_report),
        ),
    )
    flow_report = flow.run()
    status = _classify_execute_result(flow_report)
    flow_ids = flow_report.get("ids") if isinstance(flow_report.get("ids"), dict) else {}
    return {
        "scope": "runtime_scoped_local_registration_proof_from_evidence",
        "status": status,
        "mode": "execute_scoped_local_registration_proof",
        "boundary_report": boundary_report,
        "flow_report": flow_report,
        "fresh_submit_authorization_id": authorization_id,
        "local_registration_adapter_result_id": flow_ids.get(
            "local_registration_adapter_result_id"
        ),
        "blockers": list(flow_report.get("blockers") or []),
        "warnings": warnings + list(flow_report.get("warnings") or []),
        "safety_invariants": _safety(
            local_registration_attempted=True,
            local_registration_recorded=(
                status == "scoped_local_registration_proof_recorded"
            ),
        ),
    }


def _safety(
    *,
    local_registration_attempted: bool,
    local_registration_recorded: bool,
) -> dict[str, bool]:
    return {
        "uses_official_trading_console_api": local_registration_attempted,
        "non_executing_exchange": True,
        "local_registration_attempted": local_registration_attempted,
        "local_registration_recorded": local_registration_recorded,
        "order_lifecycle_called_only_for_local_registration": (
            local_registration_recorded
        ),
        "exchange_arm_enabled": False,
        "exchange_write_called": False,
        "execute_real_submit": False,
        "first_real_submit_action_called": False,
        "post_submit_accounting_called": False,
        "withdrawal_or_transfer_created": False,
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Preview or run a scoped local-registration-only proof from an "
            "RTF-016/RTF-017 evidence report."
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
        default="current_live_signal",
    )
    parser.add_argument("--allow-scoped-local-registration-proof", action="store_true")
    parser.add_argument("--allow-sample-local-registration", action="store_true")
    parser.add_argument("--execute-scoped-local-registration-proof", action="store_true")
    parser.add_argument("--api-base")
    parser.add_argument("--env-file")
    parser.add_argument(
        "--owner-operator-id",
        default=OWNER_STANDING_AUTHORIZATION_OPERATOR_ID,
    )
    parser.add_argument(
        "--owner-confirmation-reference",
        default=OWNER_STANDING_AUTHORIZATION_REFERENCE,
    )
    parser.add_argument(
        "--reason",
        default=OWNER_STANDING_AUTHORIZATION_REASON,
    )
    parser.add_argument(
        "--outcome-kind",
        default="entry_filled_protection_creation_failed",
    )
    parser.add_argument("--skip-next-attempt-gate-check", action="store_true")
    parser.add_argument("--output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    with redirect_stdout(sys.stderr):
        report = _build_report(args)
    if args.output:
        Path(args.output).expanduser().write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if report["status"].startswith(("ready_", "blocked_", "scoped_")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
