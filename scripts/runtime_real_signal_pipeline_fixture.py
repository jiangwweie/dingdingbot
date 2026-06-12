#!/usr/bin/env python3
"""Build a local report-backed real-signal pipeline fixture.

This is a local proof harness. It uses a fake Trading Console API client and
real pipeline code to prove the report chain can feed readiness without manual
field transcription. It does not call a server, OrderLifecycle, exchange, or
create live records.
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

from scripts import runtime_real_signal_scoped_local_registration_pipeline  # noqa: E402


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _build_fixture_files(root: Path, *, runtime_instance_id: str) -> dict[str, str]:
    source = {"trusted": True, "freshness": "fresh"}
    files = {
        "signal_input_json": root / "00-signal-input.json",
        "final_gate_preview_json": root / "00-final-gate-preview.json",
        "trusted_submit_facts_json": root / "00-trusted-submit-facts.json",
        "submit_idempotency_json": root / "00-submit-idempotency.json",
        "attempt_outcome_policy_json": root / "00-attempt-outcome-policy.json",
        "protection_failure_policy_json": root / "00-protection-failure-policy.json",
        "local_registration_enablement_json": root / "00-local-registration-enable.json",
        "exchange_submit_enablement_json": root / "00-exchange-submit-enable.json",
        "exchange_action_authorization_json": root / "00-exchange-action-auth.json",
        "order_lifecycle_submit_enablement_json": root / "00-order-lifecycle-enable.json",
        "exchange_adapter_enablement_json": root / "00-exchange-adapter-enable.json",
        "deployment_readiness_json": root / "00-deployment-readiness.json",
    }
    _write_json(
        files["signal_input_json"],
        {
            "evaluation_id": "signal-rtf026",
            "strategy_family_id": "BTPC-001",
            "strategy_family_version_id": "BTPC-001-v0",
            "symbol": "AVAX/USDT:USDT",
            "side": "short",
        },
    )
    _write_json(
        files["final_gate_preview_json"],
        {
            "final_gate_preview_id": "fg-rtf026",
            "verdict": "PASS",
            "candidate_snapshot": {"protection_reference_present": True},
        },
    )
    _write_json(
        files["trusted_submit_facts_json"],
        {
            "status": "ready_for_first_real_submit_confirmation",
            "trusted_submit_fact_snapshot_id": "facts-rtf026",
            "runtime_instance_id": runtime_instance_id,
            "facts_fresh_enough": True,
            "account_fact_source": source,
            "active_position_source": source,
            "protection_state_source": source,
        },
    )
    _write_json(
        files["submit_idempotency_json"],
        {
            "status": "ready_for_non_executing_policy_confirmation",
            "submit_idempotency_policy_id": "idem-rtf026",
            "blocks_concurrent_submit_without_lock": True,
            "replay_existing_result_on_duplicate": True,
        },
    )
    _write_json(files["attempt_outcome_policy_json"], {"policy_id": "attempt-rtf026"})
    _write_json(
        files["protection_failure_policy_json"],
        {"policy_id": "protect-rtf026"},
    )
    _write_json(
        files["local_registration_enablement_json"],
        {
            "status": "ready_for_local_registration_action",
            "decision_id": "local-enable-rtf026",
        },
    )
    _write_json(
        files["exchange_submit_enablement_json"],
        {
            "status": "ready_for_exchange_submit_action",
            "decision_id": "exchange-enable-rtf026",
        },
    )
    _write_json(
        files["exchange_action_authorization_json"],
        {"authorization_id": "exchange-action-rtf026"},
    )
    _write_json(
        files["order_lifecycle_submit_enablement_json"],
        {"enablement_id": "ol-enable-rtf026"},
    )
    _write_json(
        files["exchange_adapter_enablement_json"],
        {"enablement_id": "adapter-enable-rtf026"},
    )
    _write_json(
        files["deployment_readiness_json"],
        {
            "status": "ready_for_manual_gateway_binding",
            "readiness_id": "deploy-rtf026",
        },
    )
    return {key: str(value) for key, value in files.items()}


def _pipeline_args(
    args: argparse.Namespace,
    *,
    fixture_files: dict[str, str],
    artifact_dir: Path,
) -> argparse.Namespace:
    return argparse.Namespace(
        runtime_instance_id=args.runtime_instance_id,
        signal_input_json=fixture_files["signal_input_json"],
        readiness_evidence_json=None,
        auto_readiness_evidence=True,
        final_gate_preview_id=None,
        final_gate_passed=False,
        runtime_grant_authorization_id=args.runtime_grant_authorization_id,
        owner_real_submit_authorization_id=None,
        trusted_submit_fact_snapshot_id=None,
        submit_idempotency_policy_id=None,
        attempt_outcome_policy_id=None,
        protection_creation_failure_policy_id=None,
        local_registration_enablement_decision_id=None,
        exchange_submit_enablement_decision_id=None,
        exchange_submit_action_authorization_id=None,
        order_lifecycle_submit_enablement_id=None,
        exchange_submit_adapter_enablement_id=None,
        deployment_readiness_evidence_id=None,
        protection_required_and_ready=False,
        active_position_source_trusted=False,
        account_facts_fresh=False,
        duplicate_submit_guard_ready=False,
        legacy_runtime_submit_rehearsal_id=None,
        durable_exchange_submit_execution_result_id=None,
        final_gate_preview_json=fixture_files["final_gate_preview_json"],
        trusted_submit_facts_json=fixture_files["trusted_submit_facts_json"],
        submit_idempotency_json=fixture_files["submit_idempotency_json"],
        attempt_outcome_policy_json=fixture_files["attempt_outcome_policy_json"],
        protection_failure_policy_json=fixture_files["protection_failure_policy_json"],
        local_registration_enablement_json=fixture_files[
            "local_registration_enablement_json"
        ],
        exchange_submit_enablement_json=fixture_files["exchange_submit_enablement_json"],
        exchange_action_authorization_json=fixture_files[
            "exchange_action_authorization_json"
        ],
        order_lifecycle_submit_enablement_json=fixture_files[
            "order_lifecycle_submit_enablement_json"
        ],
        exchange_adapter_enablement_json=fixture_files[
            "exchange_adapter_enablement_json"
        ],
        deployment_readiness_json=fixture_files["deployment_readiness_json"],
        candidate_id="BTPC-001",
        context_id="context-rtf026",
        expires_at_ms=None,
        active_positions_count=0,
        metadata_json=None,
        execute_scoped_local_registration_proof=False,
        owner_operator_id="owner",
        owner_confirmation_reference="owner-authorized-rtf026-local-fixture",
        reason="local report fixture scoped local registration proof",
        outcome_kind="entry_filled_protection_creation_failed",
        skip_next_attempt_gate_check=True,
        env_file=None,
        api_base=args.api_base,
        artifact_dir=str(artifact_dir),
        output=None,
    )


def _build_report(args: argparse.Namespace) -> dict[str, Any]:
    artifact_dir = Path(args.artifact_dir).expanduser()
    fixture_dir = artifact_dir / "fixture-inputs"
    pipeline_dir = artifact_dir / "pipeline"
    fixture_files = _build_fixture_files(
        fixture_dir,
        runtime_instance_id=args.runtime_instance_id,
    )
    client = _FixtureClient(runtime_instance_id=args.runtime_instance_id)
    pipeline = runtime_real_signal_scoped_local_registration_pipeline._build_report(
        _pipeline_args(args, fixture_files=fixture_files, artifact_dir=pipeline_dir),
        client=client,
    )
    report = {
        "scope": "runtime_real_signal_pipeline_fixture",
        "status": (
            "ready_real_signal_pipeline_fixture"
            if pipeline.get("status")
            == "ready_for_real_signal_scoped_local_registration_proof"
            else "blocked_real_signal_pipeline_fixture"
        ),
        "runtime_instance_id": args.runtime_instance_id,
        "artifact_dir": str(artifact_dir),
        "fixture_files": fixture_files,
        "pipeline_report": pipeline,
        "api_call_count": len(client.calls),
        "api_paths": [call["path"] for call in client.calls],
        "blockers": list(pipeline.get("blockers") or []),
        "warnings": list(pipeline.get("warnings") or []),
        "safety_invariants": {
            "uses_fake_api_client": True,
            "does_not_call_server": True,
            "does_not_create_execution_intent_in_real_store": True,
            "does_not_create_order": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
            "does_not_submit_order": True,
            "does_not_mutate_runtime": True,
            "does_not_create_withdrawal_or_transfer": True,
            "pipeline_exchange_write_called": bool(
                pipeline.get("safety_invariants", {}).get("exchange_write_called")
            ),
            "pipeline_local_registration_attempted": bool(
                pipeline.get("safety_invariants", {}).get(
                    "local_registration_attempted"
                )
            ),
        },
        "created_at_ms": int(time.time() * 1000),
    }
    if args.output:
        _write_json(Path(args.output).expanduser(), report)
    return report


class _FixtureClient:
    def __init__(self, *, runtime_instance_id: str) -> None:
        self.runtime_instance_id = runtime_instance_id
        self.calls: list[dict[str, Any]] = []

    def request_json(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "method": method,
                "path": path,
                "query": dict(query or {}),
                "body": body,
            }
        )
        if "strategy-signal-intent-draft-sources" in path:
            return {
                "http_status": 200,
                "body": {
                    "status": "persisted_ready_intent_draft",
                    "runtime_instance_id": self.runtime_instance_id,
                    "blockers": [],
                    "warnings": ["fixture-source"],
                    "signal_evaluation_id": "signal-rtf026",
                    "order_candidate_id": "candidate-rtf026",
                    "runtime_execution_intent_draft_id": "draft-rtf026",
                    "draft_status": "ready_for_intent_creation",
                    "ready_for_official_handoff_source": True,
                    "signal_evaluation_created": True,
                    "order_candidate_created": True,
                    "runtime_execution_intent_draft_created": True,
                },
            }
        if "persisted-draft-source-readiness-previews" in path:
            return {
                "http_status": 200,
                "body": {
                    "status": "ready_for_executable_submit",
                    "packet_id": "readiness-rtf026",
                    "source_strategy_planning_packet_id": "strategy-plan-rtf026",
                    "source_authorization_id": "persisted-draft-source:rtf026",
                    "signal_evaluation_id": "signal-rtf026",
                    "order_candidate_id": "candidate-rtf026",
                    "executable_submit_ready": True,
                    "blockers": [],
                    "warnings": ["fixture-readiness"],
                },
            }
        if "official-submit-handoff-previews" in path:
            return {
                "http_status": 200,
                "body": {
                    "status": "ready_for_official_submit_call",
                    "blockers": [],
                    "warnings": ["fixture-handoff"],
                    "ready_for_official_submit_call": True,
                    "official_endpoint_method": "POST",
                    "official_endpoint_path": (
                        "/api/trading-console/"
                        "runtime-execution-first-real-submit-actions/"
                        "authorizations/requested-fresh-submit-authorization-rtf026"
                    ),
                    "official_query": {
                        "owner_confirmed_for_first_real_submit_action": False,
                    },
                    "mode": "disabled_smoke",
                },
            }
        if "fresh-authorizations/bind" in path:
            return {
                "http_status": 200,
                "body": {
                    "status": "created_intent_and_authorization",
                    "blockers": [],
                    "warnings": ["fixture-binding"],
                    "fresh_submit_authorization_id": "auth-rtf026",
                    "execution_intent_id": "intent-rtf026",
                    "runtime_execution_intent_draft_id": "draft-rtf026",
                    "ready_for_fresh_authorization_resolution": True,
                    "ready_for_disabled_smoke_call": True,
                    "binding_source": "latest_ready_draft",
                    "creates_execution_intent": True,
                    "creates_submit_authorization": True,
                },
            }
        if "runtime-execution-first-real-submit-actions" in path:
            return {
                "http_status": 404,
                "body": {
                    "message": "RuntimeExecutionOrderLifecycleAdapterResult not found",
                },
                "error": True,
            }
        if "runtime-execution-first-real-submit-evidence-preparations" in path:
            return {
                "http_status": 200,
                "body": {
                    "status": "prepared_packet_blocked",
                    "available_evidence_ids": {
                        "trusted_submit_fact_snapshot_id": "facts-rtf026",
                        "submit_idempotency_policy_id": "idem-rtf026",
                        "protection_creation_failure_policy_id": "protect-rtf026",
                        "post_submit_budget_settlement_persistence_evidence_id": (
                            "settlement-rtf026"
                        ),
                    },
                    "blockers": [
                        "first_real_submit_packet_unavailable:"
                        "runtimeexecutionorderlifecycleadapterresult_not_found"
                    ],
                },
            }
        raise AssertionError(f"unexpected fixture path {path}")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a local real-signal pipeline report fixture."
    )
    parser.add_argument("--runtime-instance-id", default="runtime-rtf026")
    parser.add_argument("--runtime-grant-authorization-id", default="grant-rtf026")
    parser.add_argument("--api-base", default="http://fixture")
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    with redirect_stdout(sys.stderr):
        report = _build_report(args)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if report["status"].startswith(("ready_", "blocked_")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
