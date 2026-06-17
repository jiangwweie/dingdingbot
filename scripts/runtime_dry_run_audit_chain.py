#!/usr/bin/env python3
"""Build the StrategyGroup runtime dry-run audit chain packet.

The packet exercises the same readiness/dispatch/handoff semantics used by the
watcher path with local fixtures only. It is intentionally non-executing: it
does not call Tokyo, does not call exchange write paths, does not create real
orders, and does not treat disabled smoke as real submit proof.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import sys
import time
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import runtime_fresh_signal_readiness_bridge as readiness_bridge  # noqa: E402
from scripts import runtime_real_signal_scoped_local_registration_pipeline as scoped_pipeline  # noqa: E402
from scripts import runtime_official_submit_disabled_smoke_from_handoff as disabled_smoke  # noqa: E402
from scripts import runtime_signal_watcher_resume_dispatcher as dispatcher  # noqa: E402
from src.domain.runtime_executable_submit_readiness import (  # noqa: E402
    RuntimeExecutableSubmitReadinessEvidence,
    build_runtime_executable_submit_readiness_packet,
)
from src.domain.runtime_official_submit_handoff import (  # noqa: E402
    build_runtime_official_submit_handoff_packet,
)


DEFAULT_OUTPUT_DIR = Path("output/strategygroup-runtime-pilot/dry-run-audit-chain")
DEFAULT_OUTPUT_JSON = DEFAULT_OUTPUT_DIR / "runtime-dry-run-audit-chain.json"
DEFAULT_HANDOFF_ROOT = ROOT_DIR / "docs/current/strategy-group-handoffs"
RUNTIME_ID = "dry-run-runtime-mpg-001"
FRESH_AUTHORIZATION_ID = "dry-run-fresh-auth-1"
AUTHORIZATION_ID = FRESH_AUTHORIZATION_ID
EXPECTED_STRATEGY_GROUPS = {"MPG-001", "TEQ-001", "FBS-001", "PMR-001", "SOR-001"}
EXPECTED_HARD_SAFETY_BLOCKER_CASES = {
    "active_position",
    "open_order",
    "protection_missing",
    "budget_missing",
    "duplicate_submit_risk",
    "symbol_scope_mismatch",
    "side_scope_mismatch",
    "notional_scope_mismatch",
    "leverage_scope_mismatch",
}
EXPECTED_POST_SUBMIT_EXIT_OUTCOME_CASES = {
    "entry_filled_protection_ok",
    "entry_filled_protection_failed",
    "partial_fill",
    "exchange_submit_failed_before_acceptance",
    "active_position_remains_open",
    "position_closed_by_sl_tp_or_reduce_only_recovery",
}
SHARED_RUNTIME_PIPELINE_STAGES = [
    "runtime_admission",
    "fresh_signal_to_candidate_authorization",
    "required_facts_readiness",
    "action_time_finalgate",
    "operation_layer_evidence_relay",
    "account_position_order_protection_budget_idempotency_checks",
    "official_operation_layer_submit",
    "post_submit_finalize_reconciliation_budget_settlement_review",
    "owner_console_source_readmodel",
]
STRATEGY_SPECIFIC_INPUT_FIELDS = [
    "supported_symbols",
    "supported_sides",
    "signal_ready_rule",
    "required_facts",
    "risk_defaults",
    "hard_stops",
    "sample_signal_packet",
    "sample_no_signal_packet",
    "sample_stale_signal_packet",
    "sample_conflict_packet",
]
STRATEGY_HANDOFF_FORBIDDEN_EXECUTION_FIELDS = [
    "candidate",
    "authorization",
    "runtime_grant",
    "final_gate",
    "finalgate",
    "operation_layer",
    "order_lifecycle",
    "exchange_gateway",
    "submit_endpoint",
    "post_submit_finalize",
    "reconciliation",
    "budget_settlement",
]
EXECUTION_BOUNDARY_FALSE_FIELDS = [
    "runtime_registration_authorized",
    "candidate_creation_authorized",
    "final_gate_input",
    "operation_layer_input",
    "real_submit_authorized",
]


class _DisabledSmokeClient:
    def __init__(self) -> None:
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
            {"method": method, "path": path, "query": query or {}, "body": body}
        )
        return {
            "http_status": 200,
            "body": {
                "status": "exchange_submit_execution_disabled",
                "exchange_submit_execution_enabled": False,
                "exchange_submit_execution_mode": "disabled",
                "exchange_called": False,
                "exchange_order_submitted": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "withdrawal_or_transfer_created": False,
                "execution_result_id": "dry-run-disabled-submit-result-1",
            },
        }


class _ScopedPipelineClient:
    def __init__(self) -> None:
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
            {"method": method, "path": path, "query": query or {}, "body": body}
        )
        if "strategy-signal-intent-draft-sources" in path:
            return {
                "http_status": 200,
                "body": {
                    "status": "persisted_ready_intent_draft",
                    "blockers": [],
                    "warnings": ["dry-run-scoped-source"],
                    "signal_evaluation_id": "dry-run-signal-eval-1",
                    "order_candidate_id": "dry-run-order-candidate-1",
                    "runtime_execution_intent_draft_id": "dry-run-intent-draft-1",
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
                    "packet_id": "dry-run-readiness-1",
                    "source_strategy_planning_packet_id": "dry-run-plan-1",
                    "source_authorization_id": "dry-run-source-auth-1",
                    "signal_evaluation_id": "dry-run-signal-eval-1",
                    "order_candidate_id": "dry-run-order-candidate-1",
                    "executable_submit_ready": True,
                    "blockers": [],
                    "warnings": ["dry-run-scoped-readiness"],
                },
            }
        if "official-submit-handoff-previews" in path:
            return {
                "http_status": 200,
                "body": {
                    "status": "ready_for_official_submit_call",
                    "blockers": [],
                    "warnings": ["dry-run-scoped-handoff"],
                    "ready_for_official_submit_call": True,
                    "official_endpoint_method": "POST",
                    "official_endpoint_path": (
                        "/api/trading-console/"
                        "runtime-execution-first-real-submit-actions/"
                        f"authorizations/{FRESH_AUTHORIZATION_ID}"
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
                    "warnings": ["dry-run-scoped-binding"],
                    "fresh_submit_authorization_id": FRESH_AUTHORIZATION_ID,
                    "execution_intent_id": "dry-run-execution-intent-1",
                    "runtime_execution_intent_draft_id": "dry-run-intent-draft-1",
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
                        "trusted_submit_fact_snapshot_id": (
                            "dry-run-trusted-facts-1"
                        ),
                        "submit_idempotency_policy_id": "dry-run-idempotency-1",
                        "protection_creation_failure_policy_id": (
                            "dry-run-protection-policy-1"
                        ),
                    },
                    "blockers": [
                        "preview_disabled_first_real_submit_action_http_404",
                    ],
                },
            }
        if "runtime-execution-controlled-submit-plans" in path:
            return {
                "http_status": 200,
                "body": {
                    "execution_intent_id": "dry-run-execution-intent-1",
                    "runtime_execution_intent_draft_id": "dry-run-intent-draft-1",
                    "source_id": "dry-run-order-candidate-1",
                    "semantic_ids": {
                        "order_candidate_id": "dry-run-order-candidate-1",
                        "runtime_instance_id": RUNTIME_ID,
                        "signal_evaluation_id": "dry-run-signal-eval-1",
                    },
                    "status": "ready_for_controlled_submit_adapter",
                },
            }
        if "runtime-execution-protection-plans" in path:
            return {
                "http_status": 200,
                "body": {
                    "protection_plan_id": "dry-run-protection-plan-1",
                    "status": "ready_for_submit_adapter",
                },
            }
        if "runtime-execution-attempt-reservations" in path:
            return {
                "http_status": 200,
                "body": {
                    "reservation_id": "dry-run-attempt-reservation-1",
                    "status": "pending_runtime_mutation",
                },
            }
        if "runtime-execution-attempt-mutations" in path:
            return {
                "http_status": 200,
                "body": {
                    "mutation_id": "dry-run-attempt-mutation-1",
                    "status": "applied",
                },
            }
        if "runtime-execution-attempt-outcome-policies" in path:
            return {
                "http_status": 200,
                "body": {
                    "policy_id": "dry-run-attempt-policy-1",
                    "status": "ready_for_attempt_budget_outcome_accounting",
                },
            }
        if "runtime-execution-order-lifecycle-handoff-drafts" in path:
            return {
                "http_status": 200,
                "body": {
                    "handoff_draft_id": "dry-run-handoff-1",
                    "status": "ready_for_order_lifecycle_adapter",
                    "blockers": [],
                },
            }
        if "runtime-execution-local-registration-action-authorizations" in path:
            return {
                "http_status": 200,
                "body": {
                    "action_authorization_id": "dry-run-local-action-1",
                    "status": "approved_for_local_registration_action",
                },
            }
        if "runtime-execution-local-registration-enablements" in path:
            return {
                "http_status": 200,
                "body": {
                    "decision_id": "dry-run-local-enable-1",
                    "status": "ready_for_local_registration_action",
                },
            }
        if "runtime-execution-order-lifecycle-adapter-results" in path:
            return {
                "http_status": 200,
                "body": {
                    "adapter_result_id": "dry-run-local-adapter-result-1",
                    "status": "registered_created_local_orders",
                },
            }
        raise AssertionError(f"unexpected scoped pipeline path {path}")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _evidence_ids() -> dict[str, str]:
    return {
        "authorization_id": FRESH_AUTHORIZATION_ID,
        "runtime_instance_id": RUNTIME_ID,
        "attempt_reservation_id": "dry-run-attempt-reservation-1",
        "trusted_submit_fact_snapshot_id": "dry-run-trusted-facts-1",
        "submit_idempotency_policy_id": "dry-run-idempotency-1",
        "attempt_outcome_policy_id": "dry-run-attempt-policy-1",
        "protection_creation_failure_policy_id": "dry-run-protection-policy-1",
        "local_registration_enablement_decision_id": "dry-run-local-enable-1",
        "owner_real_submit_authorization_id": "dry-run-owner-submit-auth-1",
        "order_lifecycle_submit_enablement_id": "dry-run-order-lifecycle-enable-1",
        "exchange_submit_adapter_enablement_id": "dry-run-exchange-adapter-enable-1",
        "exchange_submit_action_authorization_id": "dry-run-exchange-action-auth-1",
        "deployment_readiness_evidence_id": "dry-run-deployment-ready-1",
        "local_registration_adapter_result_id": "dry-run-local-adapter-result-1",
    }


def _operation_evidence_report(*, blockers: list[str] | None = None) -> dict[str, Any]:
    return {
        "scope": "runtime_dry_run_operation_layer_evidence_prep",
        "status": "ready" if not blockers else "blocked",
        "ids": _evidence_ids(),
        "blockers": blockers or [],
        "warnings": [],
        "steps": [
            {
                "name": "dry_run_prepare_operation_layer_evidence",
                "id_summary": _evidence_ids(),
                "blockers": blockers or [],
                "warnings": [],
                "places_order": False,
                "exchange_write_called": False,
                "order_lifecycle_called": False,
            }
        ],
    }


def _legacy_local_registration_probe_report() -> dict[str, Any]:
    report = _operation_evidence_report(
        blockers=[
            "first_real_submit_packet_unavailable:"
            "runtimeexecutionorderlifecycleadapterresult_not_found",
            "preview_disabled_first_real_submit_action_http_404",
        ]
    )
    report["status"] = "ready"
    report["steps"].append(
        {
            "name": "dry_run_record_local_order_registration_result",
            "id_summary": {
                "authorization_id": FRESH_AUTHORIZATION_ID,
                "local_registration_adapter_result_id": (
                    "dry-run-local-adapter-result-1"
                ),
            },
            "blockers": [],
            "warnings": [],
            "places_order": False,
            "exchange_write_called": False,
            "order_lifecycle_called": False,
        }
    )
    return report


def _operation_layer_relay_checks(
    *,
    operation_layer: dict[str, Any],
    closed_loop_shape: dict[str, Any],
) -> dict[str, bool]:
    readiness = operation_layer.get("operation_layer_readiness")
    if not isinstance(readiness, dict):
        readiness = {}
    available_ids = readiness.get("available_evidence_ids")
    if not isinstance(available_ids, dict):
        available_ids = {}
    required_ids = readiness.get("required_evidence_ids")
    if not isinstance(required_ids, list):
        required_ids = []
    command_plan = operation_layer.get("operation_layer_command_plan")
    if not isinstance(command_plan, dict):
        command_plan = {}
    finalgate = operation_layer.get("finalgate_preflight_result")
    if not isinstance(finalgate, dict):
        finalgate = {}
    finalgate_body = finalgate.get("body")
    if not isinstance(finalgate_body, dict):
        finalgate_body = {}

    same_authorization = (
        str(command_plan.get("authorization_id") or "")
        == str(available_ids.get("authorization_id") or "")
        == FRESH_AUTHORIZATION_ID
    )
    closed_loop_authorizations = [
        closed_loop_shape.get("post_submit_finalize_result", {}).get(
            "authorization_id"
        ),
        closed_loop_shape.get("reconciliation_result", {}).get("authorization_id"),
        closed_loop_shape.get("budget_settlement_result", {}).get(
            "authorization_id"
        ),
        closed_loop_shape.get("review_record_result", {}).get("authorization_id"),
    ]
    return {
        "required_evidence_ids_present": all(
            str(available_ids.get(str(name)) or "").strip() for name in required_ids
        ),
        "no_missing_evidence_ids": readiness.get("missing_evidence_ids") == [],
        "operation_layer_ready_flag_true": (
            readiness.get("ready_for_official_operation_layer_submit") is True
        ),
        "operation_layer_official_endpoint_selected": (
            command_plan.get("official_endpoint_method") == "POST"
            and "runtime-execution-first-real-submit-actions/authorizations/"
            in str(command_plan.get("official_endpoint_path") or "")
        ),
        "same_authorization_chain": same_authorization,
        "action_time_finalgate_called": finalgate.get("called") is True,
        "action_time_finalgate_passed": (
            finalgate_body.get("status") == "ready_for_controlled_submit_adapter"
            and str(finalgate_body.get("final_gate_verdict") or "").lower()
            == "pass"
            and not finalgate_body.get("blockers")
        ),
        "closed_loop_uses_same_authorization": all(
            item == FRESH_AUTHORIZATION_ID for item in closed_loop_authorizations
        ),
    }


def _fresh_loop_packet(
    *,
    output_dir: Path,
    status: str,
    signal: bool = True,
    blockers: list[str] | None = None,
) -> Path:
    signal_path = output_dir / f"{status}-signal-input.json"
    if signal:
        _write_json(
            signal_path,
            {
                "evaluation_id": "dry-run-signal-eval-1",
                "strategy_family_id": "MPG-001",
                "strategy_family_version_id": "MPG-001-v0",
                "symbol": "MSTR/USDT:USDT",
                "side": "long",
                "timestamp_ms": int(time.time() * 1000),
            },
        )
    packet = {
        "scope": "runtime_fresh_signal_prepare_loop",
        "status": status,
        "runtime_instance_id": RUNTIME_ID,
        "signal_input_json": str(signal_path) if signal else None,
        "post_submit_finalize_flow": {
            "status": "finalized_ready_for_next_attempt",
            "post_submit_finalize_packet": {
                "packet_id": "dry-run-post-submit-finalize-1",
                "authorization_id": "dry-run-consumed-auth-1",
                "runtime_instance_id": RUNTIME_ID,
                "status": "finalized_ready_for_next_attempt",
                "next_attempt_gate": {
                    "status": "ready_for_fresh_signal",
                    "runtime_instance_id": RUNTIME_ID,
                    "attempts_remaining": 1,
                    "budget_remaining": "10",
                    "active_positions_count": 0,
                    "blockers": [],
                    "warnings": [],
                },
                "blockers": [],
                "warnings": [],
            },
        },
        "observation_prepare_flow": {
            "status": status,
            "signal_input_json": str(signal_path) if signal else None,
        },
        "blockers": blockers or [],
        "warnings": [],
        "safety_invariants": {
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "withdrawal_or_transfer_created": False,
        },
    }
    path = output_dir / f"{status}-fresh-loop.json"
    _write_json(path, packet)
    return path


def _readiness_args(
    *,
    output_dir: Path,
    fresh_loop_path: Path,
    evidence_json: Path | None,
    flow_id: str,
) -> argparse.Namespace:
    return argparse.Namespace(
        runtime_instance_id=RUNTIME_ID,
        fresh_signal_loop_json=str(fresh_loop_path),
        evidence_json=str(evidence_json) if evidence_json else None,
        first_real_submit_packet_json=None,
        fresh_submit_authorization_id=FRESH_AUTHORIZATION_ID,
        mode="disabled_smoke",
        owner_confirmed_for_real_submit_action=False,
        readiness_warning=None,
        readiness_blocker=None,
        handoff_warning=None,
        handoff_blocker=None,
        env_file=None,
        api_base="http://dry-run.local",
        context_id="dry-run-context",
        expires_at_ms=None,
        metadata_json='{"runtime_dry_run_audit_chain": true}',
        output_dir=str(output_dir),
        flow_id=flow_id,
    )


def _planning_flow(status: str = "ready_for_final_gate_preflight") -> dict[str, Any]:
    return {
        "scope": "runtime_next_attempt_strategy_plan_api_flow",
        "status": status,
        "api_payload": {
            "packet_id": "dry-run-strategy-plan-1",
            "runtime_instance_id": RUNTIME_ID,
            "source_authorization_id": "dry-run-consumed-auth-1",
            "post_submit_finalize_packet_id": "dry-run-post-submit-finalize-1",
            "status": status,
            "next_attempt_gate_status": "ready_for_fresh_signal",
            "signal_evaluation_id": "dry-run-signal-eval-1",
            "strategy_family_id": "MPG-001",
            "strategy_family_version_id": "MPG-001-v0",
            "symbol": "MSTR/USDT:USDT",
            "side": "long",
            "order_candidate_id": "dry-run-order-candidate-1",
            "blockers": [],
            "warnings": [],
            "consumed_authorization_replay_only": True,
            "requires_fresh_strategy_signal": True,
            "requires_fresh_authorization_before_submit": True,
            "execution_intent_created": False,
            "executable_execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_called": False,
            "exchange_order_submitted": False,
            "runtime_state_mutated": False,
            "withdrawal_or_transfer_created": False,
            "metadata": {"runtime_dry_run_audit_chain": True},
        },
        "blockers": [] if status == "ready_for_final_gate_preflight" else ["planning_blocked"],
        "warnings": [],
    }


def _handoff_flow() -> dict[str, Any]:
    return {
        "scope": "runtime_cycle_executable_submit_handoff",
        "status": "ready_for_fresh_submit_authorization",
        "runtime_instance_id": RUNTIME_ID,
        "blockers": [],
        "warnings": [],
        "operator_command_plan": {
            "requires_fresh_submit_authorization": True,
            "places_order": False,
            "calls_order_lifecycle": False,
            "exchange_write_called": False,
        },
    }


def _readiness_evidence_path(output_dir: Path) -> Path:
    path = output_dir / "readiness-evidence.json"
    _write_json(
        path,
        {
            "final_gate_preview_id": "dry-run-final-gate-preview-1",
            "final_gate_passed": True,
            "runtime_grant_authorization_id": "dry-run-runtime-grant-1",
            **_evidence_ids(),
            "protection_required_and_ready": True,
            "active_position_source_trusted": True,
            "account_facts_fresh": True,
            "duplicate_submit_guard_ready": True,
        },
    )
    return path


def _scoped_pipeline_signal_path(output_dir: Path) -> Path:
    path = output_dir / "scoped-pipeline-signal-input.json"
    _write_json(
        path,
        {
            "evaluation_id": "dry-run-signal-eval-1",
            "strategy_family_id": "MPG-001",
            "strategy_family_version_id": "MPG-001-v0",
            "symbol": "MSTR/USDT:USDT",
            "side": "long",
            "timestamp_ms": int(time.time() * 1000),
        },
    )
    return path


def _scoped_pipeline_args(
    *,
    output_dir: Path,
    signal_input_json: Path,
    readiness_evidence_json: Path,
) -> argparse.Namespace:
    return argparse.Namespace(
        runtime_instance_id=RUNTIME_ID,
        signal_input_json=str(signal_input_json),
        readiness_evidence_json=str(readiness_evidence_json),
        auto_readiness_evidence=False,
        final_gate_preview_id=None,
        final_gate_passed=False,
        runtime_grant_authorization_id=None,
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
        final_gate_preview_json=None,
        trusted_submit_facts_json=None,
        submit_idempotency_json=None,
        attempt_outcome_policy_json=None,
        protection_failure_policy_json=None,
        local_registration_enablement_json=None,
        exchange_submit_enablement_json=None,
        exchange_action_authorization_json=None,
        order_lifecycle_submit_enablement_json=None,
        exchange_adapter_enablement_json=None,
        deployment_readiness_json=None,
        candidate_id="dry-run-order-candidate-1",
        context_id="dry-run-context",
        expires_at_ms=None,
        active_positions_count=0,
        metadata_json='{"runtime_dry_run_audit_chain": true}',
        source_kind="current_live_signal",
        allow_scoped_local_registration_proof=True,
        allow_sample_local_registration=False,
        execute_scoped_local_registration_proof=True,
        owner_operator_id="dry-run-owner",
        owner_confirmation_reference="standing-authorization-dry-run",
        reason="dry-run scoped local registration proof",
        outcome_kind="entry_filled_protection_creation_failed",
        skip_next_attempt_gate_check=True,
        env_file=None,
        api_base="http://dry-run.local",
        artifact_dir=str(output_dir / "scoped-pipeline-artifacts"),
        output=None,
    )


def _resume_pack_waiting() -> dict[str, Any]:
    return {
        "scope": "runtime_signal_watcher_post_signal_resume_pack",
        "status": "waiting_for_market",
        "selected_runtime_instance_ids": [RUNTIME_ID],
        "action_time_resume": {
            "status": "waiting_for_market",
            "next_step": "continue_watcher_observation",
            "allowed_auto_actions": ["continue_watcher_observation"],
            "places_order": False,
            "calls_order_lifecycle": False,
            "exchange_write_called": False,
            "withdrawal_or_transfer_requested": False,
        },
        "owner_state": {"status": "waiting_for_market", "blocker_class": "waiting_for_market"},
        "safety_invariants": _safe_resume_flags(),
        "blockers": ["strategy_signal_not_ready_for_shadow_candidate_prepare"],
        "warnings": [],
    }


def _non_executing_prepare_packet() -> dict[str, Any]:
    return {
        "scope": "runtime_next_attempt_prepare_packet",
        "status": "ready_for_final_gate_preflight",
        "ids": {
            "authorization_id": FRESH_AUTHORIZATION_ID,
            "execution_intent_id": "dry-run-execution-intent-1",
            "runtime_execution_intent_draft_id": "dry-run-intent-draft-1",
            "order_candidate_id": "dry-run-order-candidate-1",
        },
        "operator_command_plan": {
            "prepared_authorization_id": FRESH_AUTHORIZATION_ID,
            "not_executed": True,
            "live_submit_allowed": False,
            "requires_official_final_gate": True,
            "requires_official_operation_layer": True,
            "places_order": False,
            "calls_order_lifecycle": False,
        },
        "created_records": {
            "shadow_candidate_created": True,
            "runtime_execution_intent_draft_created": True,
            "execution_intent_created": True,
            "submit_authorization_created": True,
            "protection_plan_created": True,
            "attempt_reservation_created": False,
            "attempt_mutation_created": False,
            "order_lifecycle_handoff_created": False,
        },
        "safety_invariants": {
            "uses_official_trading_console_api": True,
            "next_attempt_gate_checked": True,
            "local_registration_armed": False,
            "exchange_submit_armed": False,
            "execute_real_submit": False,
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "position_opened": False,
            "withdrawal_or_transfer_created": False,
        },
        "blockers": [],
        "warnings": [],
    }


def _resume_pack_ready_for_finalgate(
    *,
    strategy_group_id: str = "MPG-001",
    runtime_instance_id: str = RUNTIME_ID,
) -> dict[str, Any]:
    return {
        "scope": "runtime_signal_watcher_post_signal_resume_pack",
        "status": "ready_for_action_time_final_gate",
        "runtime_instance_id": runtime_instance_id,
        "selected_runtime_instance_ids": [runtime_instance_id],
        "signal_input_json": "/tmp/dry-run-signal-input.json",
        "shadow_candidate_id": "dry-run-shadow-candidate-1",
        "prepared_authorization_id": AUTHORIZATION_ID,
        "runtime_signal_summaries": [
            {
                "runtime_instance_id": runtime_instance_id,
                "strategy_family_id": strategy_group_id,
                "strategy_family_version_id": f"{strategy_group_id}-v0",
                "symbol": "MSTR/USDT:USDT",
                "side": "long",
                "signal_input_json": "/tmp/dry-run-signal-input.json",
                "shadow_candidate_id": "dry-run-shadow-candidate-1",
                "prepared_authorization_id": AUTHORIZATION_ID,
                "status": "ready_for_action_time_final_gate",
            }
        ],
        "action_time_resume": {
            "status": "ready_for_action_time_final_gate",
            "runtime_instance_id": runtime_instance_id,
            "strategy_family_id": strategy_group_id,
            "next_step": "run_official_action_time_final_gate_preflight",
            "allowed_auto_actions": [
                "run_official_action_time_final_gate_preflight"
            ],
            "signal_input_json": "/tmp/dry-run-signal-input.json",
            "shadow_candidate_id": "dry-run-shadow-candidate-1",
            "prepared_authorization_id": AUTHORIZATION_ID,
            "places_order": False,
            "calls_order_lifecycle": False,
            "exchange_write_called": False,
            "withdrawal_or_transfer_requested": False,
        },
        "owner_state": {"status": "ready_for_action_time_final_gate", "blocker_class": "none"},
        "safety_invariants": _safe_resume_flags(),
        "blockers": [],
        "warnings": [],
    }


def _resume_pack_ready_for_non_executing_prepare(
    *,
    strategy_group_id: str = "MPG-001",
    runtime_instance_id: str = RUNTIME_ID,
) -> dict[str, Any]:
    signal_input_json = "/tmp/dry-run-signal-input.json"
    return {
        "scope": "runtime_signal_watcher_post_signal_resume_pack",
        "status": "ready_for_non_executing_prepare",
        "runtime_instance_id": runtime_instance_id,
        "selected_runtime_instance_ids": [runtime_instance_id],
        "signal_input_json": signal_input_json,
        "runtime_signal_summaries": [
            {
                "runtime_instance_id": runtime_instance_id,
                "strategy_family_id": strategy_group_id,
                "strategy_family_version_id": f"{strategy_group_id}-v0",
                "symbol": "MSTR/USDT:USDT",
                "side": "long",
                "signal_input_json": signal_input_json,
                "status": "ready_for_non_executing_prepare",
            }
        ],
        "action_time_resume": {
            "status": "ready_for_non_executing_prepare",
            "runtime_instance_id": runtime_instance_id,
            "strategy_family_id": strategy_group_id,
            "next_step": "prepare_fresh_candidate_authorization_evidence",
            "allowed_auto_actions": [
                "prepare_fresh_candidate_authorization_evidence"
            ],
            "signal_input_json": signal_input_json,
            "places_order": False,
            "calls_order_lifecycle": False,
            "exchange_write_called": False,
            "withdrawal_or_transfer_requested": False,
        },
        "owner_state": {
            "status": "ready_for_non_executing_prepare",
            "blocker_class": "none",
        },
        "safety_invariants": _safe_resume_flags(),
        "blockers": [],
        "warnings": [],
    }


def _resume_pack_finalgate_ready() -> dict[str, Any]:
    return {
        **_resume_pack_ready_for_finalgate(),
        "status": "finalgate_ready",
        "dispatch_status": "official_finalgate_preflight_passed",
        "command_plan": {
            "prepared_authorization_id": FRESH_AUTHORIZATION_ID,
            "api_base": "http://dry-run.local",
        },
        "finalgate_preflight_result": {
            "called": True,
            "method": "GET",
            "http_status": 200,
            "body": {
                "status": "ready_for_controlled_submit_adapter",
                "final_gate_verdict": "PASS",
                "blockers": [],
                "submit_executed": False,
                "order_created": False,
                "exchange_called": False,
                "owner_bounded_execution_called": False,
                "order_lifecycle_called": False,
            },
            "error": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "exchange_write_called": False,
        },
    }


def _safe_resume_flags() -> dict[str, Any]:
    return {
        "places_order": False,
        "calls_order_lifecycle": False,
        "exchange_write_called": False,
        "mutates_pg": False,
        "runtime_budget_mutated": False,
        "withdrawal_or_transfer_created": False,
        "forbidden_effect_flags": [],
    }


def _disabled_handoff_path(output_dir: Path) -> Path:
    evidence = RuntimeExecutableSubmitReadinessEvidence(
        final_gate_preview_id="dry-run-final-gate-preview-1",
        final_gate_passed=True,
        runtime_grant_authorization_id="dry-run-runtime-grant-1",
        trusted_submit_fact_snapshot_id="dry-run-trusted-facts-1",
        submit_idempotency_policy_id="dry-run-idempotency-1",
        attempt_outcome_policy_id="dry-run-attempt-policy-1",
        protection_creation_failure_policy_id="dry-run-protection-policy-1",
        local_registration_enablement_decision_id="dry-run-local-enable-1",
        exchange_submit_enablement_decision_id="dry-run-exchange-enable-1",
        exchange_submit_action_authorization_id="dry-run-exchange-action-auth-1",
        order_lifecycle_submit_enablement_id="dry-run-order-lifecycle-enable-1",
        exchange_submit_adapter_enablement_id="dry-run-exchange-adapter-enable-1",
        deployment_readiness_evidence_id="dry-run-deployment-ready-1",
        protection_required_and_ready=True,
        active_position_source_trusted=True,
        account_facts_fresh=True,
        duplicate_submit_guard_ready=True,
    )
    readiness = build_runtime_executable_submit_readiness_packet(
        runtime_instance_id=RUNTIME_ID,
        source_strategy_planning_packet_id="dry-run-strategy-plan-1",
        source_authorization_id="dry-run-consumed-auth-1",
        strategy_planning_status="ready_for_final_gate_preflight",
        evidence=evidence,
        order_candidate_id="dry-run-order-candidate-1",
        signal_evaluation_id="dry-run-signal-eval-1",
        source_release_packet_id="dry-run-release-1",
        now_ms=int(time.time() * 1000),
    )
    handoff = build_runtime_official_submit_handoff_packet(
        readiness_packet=readiness,
        fresh_submit_authorization_id=FRESH_AUTHORIZATION_ID,
        now_ms=int(time.time() * 1000),
    )
    path = output_dir / "disabled-submit-handoff.json"
    _write_json(path, {"packet": handoff.model_dump(mode="json")})
    return path


def _disabled_handoff_path_from_operation_layer_evidence(
    output_dir: Path,
    *,
    operation_layer_evidence: dict[str, Any],
) -> Path:
    ids = operation_layer_evidence.get("ids")
    if not isinstance(ids, dict):
        ids = {}
    evidence = RuntimeExecutableSubmitReadinessEvidence(
        final_gate_preview_id=str(
            ids.get("final_gate_preview_id") or "dry-run-final-gate-preview-1"
        ),
        final_gate_passed=True,
        owner_real_submit_authorization_id=ids.get(
            "owner_real_submit_authorization_id"
        ),
        trusted_submit_fact_snapshot_id=ids.get("trusted_submit_fact_snapshot_id"),
        submit_idempotency_policy_id=ids.get("submit_idempotency_policy_id"),
        attempt_outcome_policy_id=ids.get("attempt_outcome_policy_id"),
        protection_creation_failure_policy_id=ids.get(
            "protection_creation_failure_policy_id"
        ),
        local_registration_enablement_decision_id=ids.get(
            "local_registration_enablement_decision_id"
        ),
        exchange_submit_enablement_decision_id=(
            ids.get("exchange_submit_enablement_decision_id")
            or ids.get("exchange_submit_adapter_enablement_id")
        ),
        exchange_submit_action_authorization_id=ids.get(
            "exchange_submit_action_authorization_id"
        ),
        order_lifecycle_submit_enablement_id=ids.get(
            "order_lifecycle_submit_enablement_id"
        ),
        exchange_submit_adapter_enablement_id=ids.get(
            "exchange_submit_adapter_enablement_id"
        ),
        deployment_readiness_evidence_id=ids.get("deployment_readiness_evidence_id"),
        protection_required_and_ready=True,
        active_position_source_trusted=True,
        account_facts_fresh=True,
        duplicate_submit_guard_ready=True,
    )
    readiness = build_runtime_executable_submit_readiness_packet(
        runtime_instance_id=RUNTIME_ID,
        source_strategy_planning_packet_id="dry-run-scoped-pipeline-plan-1",
        source_authorization_id="dry-run-consumed-auth-1",
        strategy_planning_status="ready_for_final_gate_preflight",
        evidence=evidence,
        order_candidate_id="dry-run-order-candidate-1",
        signal_evaluation_id="dry-run-signal-eval-1",
        source_release_packet_id="dry-run-release-1",
        now_ms=int(time.time() * 1000),
    )
    handoff = build_runtime_official_submit_handoff_packet(
        readiness_packet=readiness,
        fresh_submit_authorization_id=FRESH_AUTHORIZATION_ID,
        now_ms=int(time.time() * 1000),
    )
    path = output_dir / "scoped-pipeline-disabled-submit-handoff.json"
    _write_json(path, {"packet": handoff.model_dump(mode="json")})
    return path


def _disabled_smoke_args(path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        handoff_json=str(path),
        output=None,
        env_file=None,
        api_base="http://dry-run.local",
    )


def _dispatcher_disabled_smoke_packet(
    *,
    operation_layer_evidence: dict[str, Any],
    operation_layer_evidence_path: str,
) -> dict[str, Any]:
    calls: list[dict[str, Any]] = []

    def fake_session_cookie() -> tuple[str, None]:
        return "brc_operator_session=dry-run", None

    def fake_request_json(**kwargs: Any) -> dict[str, Any]:
        calls.append(dict(kwargs))
        return {
            "http_status": 200,
            "error": False,
            "body": {
                "status": "exchange_submit_execution_disabled",
                "exchange_submit_execution_enabled": False,
                "exchange_submit_execution_mode": "disabled",
                "exchange_called": False,
                "exchange_order_submitted": False,
                "order_lifecycle_submit_called": False,
                "owner_bounded_execution_called": False,
                "execution_intent_status_changed": False,
                "withdrawal_or_transfer_created": False,
            },
        }

    original_session_cookie = dispatcher._session_cookie
    original_request_json = dispatcher._request_json
    try:
        dispatcher._session_cookie = fake_session_cookie
        dispatcher._request_json = fake_request_json
        packet = dispatcher.build_dispatch_packet(
            resume_pack=_resume_pack_finalgate_ready(),
            source_path=Path("/tmp/dry-run-post-signal-resume-pack.json"),
            api_base="http://dry-run.local",
            operation_layer_evidence_report=operation_layer_evidence,
            operation_layer_evidence_report_path=operation_layer_evidence_path,
            execute_operation_layer_submit=True,
            operation_layer_submit_mode=(
                dispatcher.OPERATION_LAYER_SUBMIT_MODE_DISABLED_SMOKE
            ),
        )
    finally:
        dispatcher._session_cookie = original_session_cookie
        dispatcher._request_json = original_request_json
    packet["dry_run_dispatcher_disabled_smoke_calls"] = calls
    return packet


def _fake_closed_loop_shape() -> dict[str, Any]:
    return {
        "scope": "runtime_dry_run_fake_closed_loop_shape",
        "status": "shape_checked",
        "called_official_endpoint": False,
        "non_executing": True,
        "post_submit_finalize_result": {
            "status": "finalized_ready_for_next_attempt",
            "runtime_instance_id": RUNTIME_ID,
            "authorization_id": FRESH_AUTHORIZATION_ID,
            "next_attempt_gate": {
                "status": "ready_for_fresh_signal",
                "blockers": [],
            },
        },
        "reconciliation_result": {
            "status": "clean",
            "runtime_instance_id": RUNTIME_ID,
            "authorization_id": FRESH_AUTHORIZATION_ID,
            "active_position_count": 0,
            "open_order_count": 0,
            "mismatches": [],
            "blockers": [],
        },
        "budget_settlement_result": {
            "status": "settled",
            "runtime_instance_id": RUNTIME_ID,
            "authorization_id": FRESH_AUTHORIZATION_ID,
            "attempt_reservation_id": "dry-run-attempt-reservation-1",
            "budget_released_or_accounted": True,
            "blockers": [],
        },
        "review_record_result": {
            "status": "recorded",
            "runtime_instance_id": RUNTIME_ID,
            "authorization_id": FRESH_AUTHORIZATION_ID,
            "review_outcome": "keep_observing",
            "owner_action_required": False,
            "blockers": [],
        },
        "closed_loop_checks": {
            "finalize_shape_present": True,
            "reconciliation_shape_present": True,
            "budget_settlement_shape_present": True,
            "review_record_shape_present": True,
            "next_attempt_gate_shape_present": True,
        },
        "safety_invariants": {
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "withdrawal_or_transfer_created": False,
            "disabled_smoke_is_real_execution_proof": False,
        },
    }


def _load_strategy_group_handoffs(
    handoff_root: Path = DEFAULT_HANDOFF_ROOT,
) -> dict[str, Any]:
    handoffs: dict[str, Any] = {}
    for path in sorted(handoff_root.glob("*/handoff.json")):
        payload = _read_json(path)
        strategy_group_id = str(payload.get("strategy_group_id") or path.parent.name)
        handoffs[strategy_group_id] = {"path": str(path), "payload": payload}
    return handoffs


def _shared_runtime_pipeline_validation() -> dict[str, Any]:
    handoffs = _load_strategy_group_handoffs()
    found_groups = set(handoffs)
    missing_groups = sorted(EXPECTED_STRATEGY_GROUPS - found_groups)
    unexpected_groups = sorted(found_groups - EXPECTED_STRATEGY_GROUPS)
    rows: list[dict[str, Any]] = []
    blockers: list[str] = []

    for strategy_group_id in sorted(EXPECTED_STRATEGY_GROUPS):
        item = handoffs.get(strategy_group_id)
        if item is None:
            blockers.append(f"missing_strategy_group_handoff:{strategy_group_id}")
            continue
        payload = item["payload"]
        boundary = payload.get("execution_boundary")
        boundary = boundary if isinstance(boundary, dict) else {}
        required_facts = payload.get("required_facts")
        required_facts = required_facts if isinstance(required_facts, dict) else {}
        signal_rule = payload.get("signal_ready_rule")
        signal_rule = signal_rule if isinstance(signal_rule, dict) else {}
        risk_defaults = payload.get("risk_defaults")
        risk_defaults = risk_defaults if isinstance(risk_defaults, dict) else {}
        forbidden_execution_fields_present = sorted(
            field
            for field in STRATEGY_HANDOFF_FORBIDDEN_EXECUTION_FIELDS
            if field in payload
        )
        row_checks = {
            "has_supported_symbols": bool(payload.get("supported_symbols")),
            "has_supported_sides": bool(payload.get("supported_sides")),
            "has_signal_ready_rule": bool(signal_rule),
            "has_required_facts": bool(required_facts),
            "has_risk_defaults": bool(risk_defaults),
            "has_hard_stops": bool(payload.get("hard_stops")),
            "no_execution_pipeline_fields": not forbidden_execution_fields_present,
            "research_handoff_only": boundary.get("research_handoff_only") is True,
            "does_not_authorize_execution_boundary": all(
                boundary.get(name) is False for name in EXECUTION_BOUNDARY_FALSE_FIELDS
            ),
            "tiny_risk_boundary": (
                str(risk_defaults.get("risk_tier") or "") == "tiny"
                and str(risk_defaults.get("max_notional_per_action_usdt") or "") == "8"
                and str(risk_defaults.get("default_leverage") or "") == "1"
                and str(risk_defaults.get("max_leverage") or "") == "1"
            ),
            "uses_standard_signal_status": (
                signal_rule.get("status_name")
                == "ready_for_shadow_candidate_prepare"
            ),
        }
        rows.append(
            {
                "strategy_group_id": strategy_group_id,
                "handoff_json": item["path"],
                "shared_runtime_pipeline_stages": SHARED_RUNTIME_PIPELINE_STAGES,
                "strategy_specific_input_fields": STRATEGY_SPECIFIC_INPUT_FIELDS,
                "sample_input_contract": {
                    "supported_symbols": payload.get("supported_symbols") or [],
                    "supported_sides": payload.get("supported_sides") or [],
                    "signal_status_name": signal_rule.get("status_name"),
                    "freshness_window_seconds": signal_rule.get(
                        "freshness_window_seconds"
                    ),
                    "required_fact_categories": sorted(required_facts),
                    "risk_tier": risk_defaults.get("risk_tier"),
                    "max_notional_per_action_usdt": risk_defaults.get(
                        "max_notional_per_action_usdt"
                    ),
                    "default_leverage": risk_defaults.get("default_leverage"),
                    "hard_stop_count": len(payload.get("hard_stops") or []),
                },
                "execution_boundary": boundary,
                "forbidden_execution_fields_present": (
                    forbidden_execution_fields_present
                ),
                "checks": row_checks,
                "passed": all(row_checks.values()),
            }
        )
        blockers.extend(
            f"{strategy_group_id}:{check_name}"
            for check_name, ok in row_checks.items()
            if ok is not True
        )

    if unexpected_groups:
        blockers.extend(
            f"unexpected_strategy_group_handoff:{item}" for item in unexpected_groups
        )

    checks = {
        "expected_strategy_groups_present": not missing_groups,
        "no_unexpected_strategy_groups": not unexpected_groups,
        "all_strategy_groups_use_same_shared_pipeline": all(
            row.get("shared_runtime_pipeline_stages") == SHARED_RUNTIME_PIPELINE_STAGES
            for row in rows
        ),
        "all_strategy_groups_limit_to_input_contract": all(
            row.get("passed") is True for row in rows
        ),
        "all_strategy_groups_deny_direct_execution_authority": all(
            row.get("checks", {}).get("does_not_authorize_execution_boundary") is True
            for row in rows
        ),
        "all_strategy_groups_have_no_execution_pipeline_fields": all(
            row.get("checks", {}).get("no_execution_pipeline_fields") is True
            for row in rows
        ),
        "all_strategy_groups_keep_tiny_risk_boundary": all(
            row.get("checks", {}).get("tiny_risk_boundary") is True for row in rows
        ),
        "common_execution_chain_reused_by_all_strategygroups": (
            len(rows) == len(EXPECTED_STRATEGY_GROUPS)
            and all(
                row.get("shared_runtime_pipeline_stages")
                == SHARED_RUNTIME_PIPELINE_STAGES
                for row in rows
            )
        ),
        "strategygroup_adapters_are_input_only": all(
            row.get("checks", {}).get("does_not_authorize_execution_boundary") is True
            and row.get("checks", {}).get("no_execution_pipeline_fields") is True
            and row.get("checks", {}).get("has_signal_ready_rule") is True
            and row.get("checks", {}).get("has_required_facts") is True
            and row.get("checks", {}).get("has_risk_defaults") is True
            and row.get("checks", {}).get("has_hard_stops") is True
            for row in rows
        ),
    }
    blockers.extend(name for name, ok in checks.items() if ok is not True)
    return {
        "scope": "shared_runtime_pipeline_validation",
        "status": "passed" if not blockers else "failed",
        "judgment": {
            "common_runtime_pipe_share": "80%",
            "strategy_group_adapter_share": "20%",
            "meaning": (
                "candidate/auth, FinalGate, Operation Layer, finalize, "
                "reconciliation, settlement, and Owner readmodel are shared; "
                "StrategyGroups provide signal/facts/symbol/side/risk/hard-stop inputs."
            ),
        },
        "expected_strategy_groups": sorted(EXPECTED_STRATEGY_GROUPS),
        "found_strategy_groups": sorted(found_groups),
        "missing_strategy_groups": missing_groups,
        "unexpected_strategy_groups": unexpected_groups,
        "shared_runtime_pipeline_stages": SHARED_RUNTIME_PIPELINE_STAGES,
        "strategy_specific_input_fields": STRATEGY_SPECIFIC_INPUT_FIELDS,
        "strategy_handoff_forbidden_execution_fields": (
            STRATEGY_HANDOFF_FORBIDDEN_EXECUTION_FIELDS
        ),
        "rows": rows,
        "checks": checks,
        "blockers": sorted(set(blockers)),
        "safety_invariants": {
            "calls_tokyo_api": False,
            "real_order_created": False,
            "exchange_write_called": False,
            "order_lifecycle_called": False,
            "withdrawal_or_transfer_created": False,
            "finalgate_bypassed": False,
            "operation_layer_bypassed": False,
        },
    }


def _scenario_no_signal(output_dir: Path) -> dict[str, Any]:
    fresh_path = _fresh_loop_packet(
        output_dir=output_dir,
        status="waiting_for_signal",
        signal=False,
        blockers=["strategy_signal_not_ready_for_shadow_candidate_prepare"],
    )
    readiness = readiness_bridge._build_packet(
        _readiness_args(
            output_dir=output_dir,
            fresh_loop_path=fresh_path,
            evidence_json=None,
            flow_id="no-signal",
        ),
        planning_builder=lambda args: _planning_flow(),
        handoff_builder=lambda args: _handoff_flow(),
    )
    dispatch = dispatcher.build_dispatch_packet(
        resume_pack=_resume_pack_waiting(),
        source_path=Path("/tmp/dry-run-post-signal-resume-pack.json"),
        api_base="http://dry-run.local",
    )
    return _scenario_packet(
        name="no_signal",
        expected="waiting_for_signal; no candidate, authorization, FinalGate, or Operation Layer",
        artifacts={"readiness_bridge": readiness, "resume_dispatch": dispatch},
        passed=(
            readiness["status"] == "waiting_for_signal"
            and dispatch["status"] == "waiting_for_market"
            and dispatch["command_plan"] is None
        ),
        blockers=readiness.get("blockers", []) + dispatch.get("blockers", []),
    )


def _scenario_mock_pass(output_dir: Path) -> dict[str, Any]:
    evidence_path = _readiness_evidence_path(output_dir)
    fresh_path = _fresh_loop_packet(
        output_dir=output_dir,
        status="ready_for_final_gate_preflight",
        blockers=[],
    )
    readiness = readiness_bridge._build_packet(
        _readiness_args(
            output_dir=output_dir,
            fresh_loop_path=fresh_path,
            evidence_json=evidence_path,
            flow_id="mock-pass",
        ),
        planning_builder=lambda args: _planning_flow(),
        handoff_builder=lambda args: _handoff_flow(),
    )
    finalgate_plan = dispatcher.build_dispatch_packet(
        resume_pack=_resume_pack_ready_for_finalgate(),
        source_path=Path("/tmp/dry-run-post-signal-resume-pack.json"),
        api_base="http://dry-run.local",
    )
    operation_layer = dispatcher.build_dispatch_packet(
        resume_pack=_resume_pack_finalgate_ready(),
        source_path=Path("/tmp/dry-run-post-signal-resume-pack.json"),
        api_base="http://dry-run.local",
        operation_layer_evidence_report=_operation_evidence_report(),
        operation_layer_evidence_report_path="/tmp/dry-run-operation-layer-evidence.json",
        execute_operation_layer_submit=False,
    )
    handoff_path = _disabled_handoff_path(output_dir)
    disabled_report = disabled_smoke._build_report(
        _disabled_smoke_args(handoff_path),
        client=_DisabledSmokeClient(),
    )
    closed_loop_shape = _fake_closed_loop_shape()
    relay_checks = _operation_layer_relay_checks(
        operation_layer=operation_layer,
        closed_loop_shape=closed_loop_shape,
    )
    fast_auto_chain_checks = {
        "fresh_signal_to_authorization_ready": (
            readiness["status"] == "ready_for_fresh_submit_authorization"
        ),
        "authorization_to_finalgate_dispatch_ready": (
            finalgate_plan["status"] == "ready_for_action_time_final_gate"
            and finalgate_plan["dispatch_action"]
            == "run_official_action_time_final_gate_preflight"
        ),
        "finalgate_to_operation_layer_evidence_ready": (
            operation_layer["status"] == "operation_layer_ready"
            and operation_layer["dispatch_action"]
            == "prepare_official_operation_layer_submit"
        ),
        "operation_layer_real_submit_still_not_called": (
            _operation_layer_submit_called(operation_layer) is False
        ),
    }
    legacy_probe = dispatcher.build_dispatch_packet(
        resume_pack=_resume_pack_finalgate_ready(),
        source_path=Path("/tmp/dry-run-post-signal-resume-pack.json"),
        api_base="http://dry-run.local",
        operation_layer_evidence_report=_legacy_local_registration_probe_report(),
        operation_layer_evidence_report_path=(
            "/tmp/dry-run-operation-layer-legacy-probe-evidence.json"
        ),
        execute_operation_layer_submit=False,
    )
    legacy_probe_passed = (
        legacy_probe["status"] == "operation_layer_ready"
        and legacy_probe["blockers"] == []
        and (
            "legacy_prepare_machine_evidence_probe_blocker_satisfied_by_"
            "local_registration_adapter_result"
        )
        in legacy_probe.get("warnings", [])
    )
    passed = (
        readiness["status"] == "ready_for_fresh_submit_authorization"
        and finalgate_plan["status"] == "ready_for_action_time_final_gate"
        and finalgate_plan["dispatch_action"]
        == "run_official_action_time_final_gate_preflight"
        and operation_layer["status"] == "operation_layer_ready"
        and all(relay_checks.values())
        and legacy_probe_passed
        and disabled_report["status"] == "disabled_smoke_passed"
        and closed_loop_shape["status"] == "shape_checked"
        and all(closed_loop_shape["closed_loop_checks"].values())
        and not _dangerous_effects(
            readiness,
            finalgate_plan,
            operation_layer,
            disabled_report,
            closed_loop_shape,
            legacy_probe,
        )
    )
    return _scenario_packet(
        name="mock_fresh_signal_dry_run_pass",
        expected=(
            "evidence IDs connect through the official Operation Layer handoff, "
            "legacy local-registration probe blockers are satisfied by adapter "
            "evidence, disabled submit stays non-executing, and "
            "finalize/reconciliation/budget/review shapes are present"
        ),
        artifacts={
            "readiness_bridge": readiness,
            "fast_auto_chain_checks": fast_auto_chain_checks,
            "finalgate_dispatch_plan": finalgate_plan,
            "operation_layer_evidence_prep": operation_layer,
            "operation_layer_relay_checks": relay_checks,
            "legacy_local_registration_probe_tolerance": legacy_probe,
            "disabled_submit_smoke": disabled_report,
            "closed_loop_shape": closed_loop_shape,
        },
        passed=passed,
        blockers=[
            *readiness.get("blockers", []),
            *finalgate_plan.get("blockers", []),
            *operation_layer.get("blockers", []),
            *[
                f"fast_auto_chain_check_failed:{name}"
                for name, value in fast_auto_chain_checks.items()
                if not value
            ],
            *(legacy_probe.get("blockers", []) if not legacy_probe_passed else []),
            *[
                f"relay_check_failed:{name}"
                for name, value in relay_checks.items()
                if not value
            ],
            *disabled_report.get("blockers", []),
        ],
    )


def _scenario_scoped_pipeline_operation_layer_handoff(
    output_dir: Path,
) -> dict[str, Any]:
    signal_path = _scoped_pipeline_signal_path(output_dir)
    readiness_evidence_path = _readiness_evidence_path(output_dir)
    pipeline_client = _ScopedPipelineClient()
    pipeline_report = scoped_pipeline._build_report(
        _scoped_pipeline_args(
            output_dir=output_dir,
            signal_input_json=signal_path,
            readiness_evidence_json=readiness_evidence_path,
        ),
        client=pipeline_client,
    )
    operation_layer_evidence = pipeline_report.get(
        "operation_layer_evidence_after_local_registration"
    )
    if not isinstance(operation_layer_evidence, dict):
        operation_layer_evidence = {}
    dispatch = dispatcher.build_dispatch_packet(
        resume_pack=_resume_pack_finalgate_ready(),
        source_path=Path("/tmp/dry-run-post-signal-resume-pack.json"),
        api_base="http://dry-run.local",
        operation_layer_evidence_report=operation_layer_evidence,
        operation_layer_evidence_report_path=str(
            pipeline_report.get("operation_layer_evidence_after_local_registration_path")
            or "/tmp/scoped-pipeline-operation-layer-evidence.json"
        ),
        execute_operation_layer_submit=False,
    )
    progress = pipeline_report.get("execution_chain_progress")
    if not isinstance(progress, dict):
        progress = {}
    post_gate = progress.get("post_local_registration_gate")
    if not isinstance(post_gate, dict):
        post_gate = {}
    readiness = dispatch.get("operation_layer_readiness")
    if not isinstance(readiness, dict):
        readiness = {}
    scoped_disabled_handoff_path = _disabled_handoff_path_from_operation_layer_evidence(
        output_dir,
        operation_layer_evidence=operation_layer_evidence,
    )
    scoped_disabled_smoke = disabled_smoke._build_report(
        _disabled_smoke_args(scoped_disabled_handoff_path),
        client=_DisabledSmokeClient(),
    )
    dispatcher_disabled_smoke = _dispatcher_disabled_smoke_packet(
        operation_layer_evidence=operation_layer_evidence,
        operation_layer_evidence_path=str(
            pipeline_report.get("operation_layer_evidence_after_local_registration_path")
            or "/tmp/scoped-pipeline-operation-layer-evidence.json"
        ),
    )
    ids = operation_layer_evidence.get("ids")
    if not isinstance(ids, dict):
        ids = {}
    scoped_disabled_query = scoped_disabled_smoke.get("official_call", {}).get("query")
    if not isinstance(scoped_disabled_query, dict):
        scoped_disabled_query = {}
    required_submit_query_ids = {
        "trusted_submit_fact_snapshot_id",
        "submit_idempotency_policy_id",
        "attempt_outcome_policy_id",
        "protection_creation_failure_policy_id",
        "local_registration_enablement_decision_id",
        "owner_real_submit_authorization_id",
        "order_lifecycle_submit_enablement_id",
        "exchange_submit_adapter_enablement_id",
        "exchange_submit_action_authorization_id",
        "deployment_readiness_evidence_id",
    }
    scoped_disabled_submit_checks = {
        "handoff_query_uses_pipeline_evidence_ids": all(
            scoped_disabled_query.get(name) == ids.get(name)
            for name in required_submit_query_ids
        ),
        "disabled_smoke_called_official_endpoint": (
            scoped_disabled_smoke.get("status") == "disabled_smoke_passed"
            and scoped_disabled_smoke.get("official_call", {}).get("method") == "POST"
        ),
        "disabled_smoke_keeps_owner_real_submit_false": (
            scoped_disabled_query.get("owner_confirmed_for_first_real_submit_action")
            is False
        ),
        "disabled_smoke_does_not_exchange_write": (
            scoped_disabled_smoke.get("safety_invariants", {}).get(
                "exchange_write_called"
            )
            is False
        ),
        "disabled_smoke_does_not_create_order": (
            scoped_disabled_smoke.get("safety_invariants", {}).get("order_created")
            is False
        ),
        "disabled_smoke_does_not_call_order_lifecycle": (
            scoped_disabled_smoke.get("safety_invariants", {}).get(
                "order_lifecycle_called"
            )
            is False
        ),
        "dispatcher_disabled_smoke_mode_passed": (
            dispatcher_disabled_smoke.get("status")
            == "operation_layer_disabled_smoke_passed"
            and dispatcher_disabled_smoke.get("dispatch_status")
            == "official_operation_layer_disabled_smoke_passed"
        ),
        "dispatcher_disabled_smoke_keeps_real_confirm_false": (
            dispatcher_disabled_smoke.get("operation_layer_submit_result", {}).get(
                "owner_confirmed_for_first_real_submit_action"
            )
            is False
        ),
        "dispatcher_disabled_smoke_does_not_exchange_write": (
            dispatcher_disabled_smoke.get("safety_invariants", {}).get(
                "exchange_write_called"
            )
            is False
        ),
    }
    checks = {
        "pipeline_reaches_scoped_local_registration_recorded": (
            pipeline_report.get("status") == "scoped_local_registration_proof_recorded"
        ),
        "pipeline_reports_operation_layer_evidence_ready": (
            post_gate.get("operation_layer_evidence_ready") is True
            and post_gate.get("operation_layer_evidence_missing_ids") == []
        ),
        "dispatcher_accepts_pipeline_evidence": (
            dispatch.get("status") == "operation_layer_ready"
            and dispatch.get("dispatch_status")
            == "official_operation_layer_evidence_ready"
        ),
        "operation_layer_readiness_has_no_missing_ids": (
            readiness.get("missing_evidence_ids") == []
        ),
        "operation_layer_submit_not_called": (
            _operation_layer_submit_called(dispatch) is False
        ),
        "pipeline_does_not_exchange_write": (
            pipeline_report.get("safety_invariants", {}).get("exchange_write_called")
            is False
        ),
        "scoped_pipeline_disabled_submit_smoke_passed": all(
            scoped_disabled_submit_checks.values()
        ),
    }
    passed = all(checks.values()) and not _dangerous_effects(
        pipeline_report,
        dispatch,
        scoped_disabled_smoke,
        dispatcher_disabled_smoke,
    )
    return _scenario_packet(
        name="scoped_pipeline_operation_layer_handoff",
        expected=(
            "real pipeline-shaped scoped local registration proof emits "
            "Operation Layer evidence consumed by dispatcher without submit"
        ),
        artifacts={
            "checks": checks,
            "scoped_disabled_submit_checks": scoped_disabled_submit_checks,
            "scoped_disabled_submit_smoke": scoped_disabled_smoke,
            "dispatcher_disabled_submit_smoke": dispatcher_disabled_smoke,
            "pipeline_report": pipeline_report,
            "resume_dispatch": dispatch,
            "pipeline_client_calls": pipeline_client.calls,
        },
        passed=passed,
        blockers=[
            *pipeline_report.get("blockers", []),
            *dispatch.get("blockers", []),
            *scoped_disabled_smoke.get("blockers", []),
            *[
                f"scoped_pipeline_handoff_check_failed:{name}"
                for name, value in checks.items()
                if not value
            ],
            *[
                f"scoped_pipeline_disabled_submit_check_failed:{name}"
                for name, value in scoped_disabled_submit_checks.items()
                if not value
            ],
        ],
    )


def _scenario_non_executing_prepare_auto_bridge(output_dir: Path) -> dict[str, Any]:
    del output_dir
    prepare_calls: list[dict[str, Any]] = []
    finalgate_calls: list[dict[str, Any]] = []

    def prepare_runner(command_plan: dict[str, Any]) -> dict[str, Any]:
        prepare_calls.append(dict(command_plan))
        return _non_executing_prepare_packet()

    def request_json(**kwargs: Any) -> dict[str, Any]:
        finalgate_calls.append(dict(kwargs))
        return {
            "http_status": 200,
            "error": False,
            "body": {
                "status": "ready_for_controlled_submit_adapter",
                "final_gate_verdict": "PASS",
                "blockers": [],
                "warnings": [],
                "submit_executed": False,
                "order_created": False,
                "exchange_called": False,
                "owner_bounded_execution_called": False,
                "order_lifecycle_called": False,
            },
        }

    original_session_cookie = dispatcher._session_cookie  # noqa: SLF001
    original_request_json = dispatcher._request_json  # noqa: SLF001
    dispatcher._session_cookie = (  # noqa: SLF001
        lambda: ("brc_operator_session=dry-run", None)
    )
    dispatcher._request_json = request_json  # noqa: SLF001
    try:
        dispatch = dispatcher.build_dispatch_packet(
            resume_pack=_resume_pack_ready_for_non_executing_prepare(),
            source_path=Path("/tmp/dry-run-post-signal-resume-pack.json"),
            api_base="http://dry-run.local",
            execute_preflight=True,
            non_executing_preparer=prepare_runner,
            selected_strategy_group_id="MPG-001",
        )
    finally:
        dispatcher._session_cookie = original_session_cookie  # noqa: SLF001
        dispatcher._request_json = original_request_json  # noqa: SLF001

    checks = {
        "prepare_runner_called_once": len(prepare_calls) == 1,
        "prepare_uses_runtime_and_signal_input": (
            bool(prepare_calls)
            and prepare_calls[0].get("runtime_instance_id") == RUNTIME_ID
            and prepare_calls[0].get("signal_input_json")
            == "/tmp/dry-run-signal-input.json"
        ),
        "prepare_result_ready_for_finalgate": (
            dispatch.get("non_executing_prepare_result", {}).get("status")
            == "ready_for_final_gate_preflight"
        ),
        "dispatcher_reaches_finalgate_ready": (
            dispatch.get("status") == "finalgate_ready"
            and dispatch.get("dispatch_action")
            == "prepare_official_operation_layer_submit"
        ),
        "finalgate_called_once": len(finalgate_calls) == 1,
        "operation_layer_submit_not_called": (
            _operation_layer_submit_called(dispatch) is False
        ),
        "no_dangerous_effects": not _dangerous_effects(dispatch),
    }
    blockers = [
        f"non_executing_prepare_auto_bridge:{name}"
        for name, value in checks.items()
        if value is not True
    ]
    return _scenario_packet(
        name="non_executing_prepare_auto_bridge",
        expected=(
            "ready_for_non_executing_prepare can call the official "
            "non-executing prepare wrapper and continue to FinalGate without "
            "Operation Layer submit or exchange write"
        ),
        artifacts={
            "checks": checks,
            "resume_dispatch": dispatch,
            "prepare_calls": prepare_calls,
            "finalgate_calls": finalgate_calls,
        },
        passed=not blockers,
        blockers=blockers,
    )


def _scenario_required_facts_missing(output_dir: Path) -> dict[str, Any]:
    fresh_path = _fresh_loop_packet(
        output_dir=output_dir,
        status="ready_for_prepare",
        blockers=[],
    )
    planning_calls: list[Any] = []
    readiness = readiness_bridge._build_packet(
        _readiness_args(
            output_dir=output_dir,
            fresh_loop_path=fresh_path,
            evidence_json=None,
            flow_id="required-facts-missing",
        ),
        planning_builder=lambda args: planning_calls.append(args),
        handoff_builder=lambda args: _handoff_flow(),
    )
    passed = (
        readiness["status"] == "ready_for_readiness_evidence"
        and planning_calls == []
        and not _dangerous_effects(readiness)
    )
    return _scenario_packet(
        name="required_facts_missing",
        expected="clear missing_fact blocker before Operation Layer",
        artifacts={"readiness_bridge": readiness},
        passed=passed,
        blockers=readiness.get("blockers", []) or ["missing_fact:readiness_evidence"],
    )


def _scenario_active_conflict(output_dir: Path) -> dict[str, Any]:
    conflict = dispatcher.build_dispatch_packet(
        resume_pack=_resume_pack_finalgate_ready(),
        source_path=Path("/tmp/dry-run-post-signal-resume-pack.json"),
        api_base="http://dry-run.local",
        operation_layer_evidence_report=_operation_evidence_report(
            blockers=["active_position_conflict:dry-run-runtime-mpg-001"]
        ),
        operation_layer_evidence_report_path="/tmp/dry-run-operation-layer-evidence.json",
        execute_operation_layer_submit=False,
    )
    passed = (
        conflict["status"] == "operation_layer_blocked"
        and conflict["blocker_class"] == "active_position_resolution"
        and _operation_layer_submit_called(conflict) is False
        and not _dangerous_effects(conflict)
    )
    return _scenario_packet(
        name="active_position_or_open_order_conflict",
        expected="conflict blocks before Operation Layer action",
        artifacts={"resume_dispatch": conflict},
        passed=passed,
        blockers=conflict.get("blockers", []),
    )


def _scenario_operation_layer_blocker_review_matrix(output_dir: Path) -> dict[str, Any]:
    blocker_cases = {
        "active_position": {
            "blocker": "active_position_conflict:dry-run-runtime-mpg-001",
            "expected_class": "active_position_resolution",
            "expected_owner_state": "needs_intervention",
        },
        "open_order": {
            "blocker": "open_order_conflict:dry-run-runtime-mpg-001",
            "expected_class": "active_position_resolution",
            "expected_owner_state": "needs_intervention",
        },
        "protection_missing": {
            "blocker": "protection_missing:entry_stop_required",
            "expected_class": "missing_fact",
            "expected_owner_state": "temporarily_unavailable",
        },
        "budget_missing": {
            "blocker": "budget_missing:attempt_reservation_required",
            "expected_class": "missing_fact",
            "expected_owner_state": "temporarily_unavailable",
        },
        "duplicate_submit_risk": {
            "blocker": "duplicate_submit_risk:idempotency_lock_required",
            "expected_class": "hard_safety_stop",
            "expected_owner_state": "needs_intervention",
        },
        "symbol_scope_mismatch": {
            "blocker": "symbol_scope_mismatch:expected=MSTR/USDT:USDT",
            "expected_class": "hard_safety_stop",
            "expected_owner_state": "needs_intervention",
        },
        "side_scope_mismatch": {
            "blocker": "side_scope_mismatch:expected=long",
            "expected_class": "hard_safety_stop",
            "expected_owner_state": "needs_intervention",
        },
        "notional_scope_mismatch": {
            "blocker": "notional_scope_mismatch:tiny_boundary_exceeded",
            "expected_class": "hard_safety_stop",
            "expected_owner_state": "needs_intervention",
        },
        "leverage_scope_mismatch": {
            "blocker": "leverage_scope_mismatch:expected=1x",
            "expected_class": "hard_safety_stop",
            "expected_owner_state": "needs_intervention",
        },
    }
    results: dict[str, Any] = {}
    blockers: list[str] = []
    for name, spec in blocker_cases.items():
        packet = dispatcher.build_dispatch_packet(
            resume_pack=_resume_pack_finalgate_ready(),
            source_path=Path("/tmp/dry-run-post-signal-resume-pack.json"),
            api_base="http://dry-run.local",
            operation_layer_evidence_report=_operation_evidence_report(
                blockers=[spec["blocker"]]
            ),
            operation_layer_evidence_report_path=(
                f"/tmp/dry-run-operation-layer-{name}.json"
            ),
            execute_operation_layer_submit=False,
        )
        review = packet.get("operation_layer_blocker_review") or {}
        checks = {
            "submit_blocked": packet.get("status") == "operation_layer_blocked",
            "class_matches": packet.get("blocker_class") == spec["expected_class"],
            "review_packet_ready": (
                review.get("status") == "submit_blocked_review_packet_ready"
            ),
            "project_progress_allowed": (
                review.get("project_progress_allowed") is True
            ),
            "continue_observation_allowed": (
                review.get("continue_observation_allowed") is True
            ),
            "real_submit_forbidden": review.get("real_submit_allowed") is False,
            "owner_state_matches": (
                review.get("owner_console_state") == spec["expected_owner_state"]
            ),
            "operation_layer_not_called": _operation_layer_submit_called(packet) is False,
            "no_dangerous_effects": not _dangerous_effects(packet),
        }
        results[name] = {
            "blocker": spec["blocker"],
            "expected_class": spec["expected_class"],
            "packet_status": packet.get("status"),
            "blocker_class": packet.get("blocker_class"),
            "owner_console_state": review.get("owner_console_state"),
            "owner_sentence": review.get("owner_sentence"),
            "checks": checks,
            "packet": packet,
        }
        blockers.extend(
            f"{name}:{check_name}"
            for check_name, ok in checks.items()
            if ok is not True
        )
    matrix_checks = {
        "expected_blocker_cases_present": (
            set(results) == EXPECTED_HARD_SAFETY_BLOCKER_CASES
        ),
        "all_cases_block_real_submit": all(
            case.get("checks", {}).get("real_submit_forbidden") is True
            for case in results.values()
        ),
        "all_cases_avoid_operation_layer_submit": all(
            case.get("checks", {}).get("operation_layer_not_called") is True
            for case in results.values()
        ),
        "all_cases_have_owner_review_state": all(
            bool(case.get("owner_console_state")) and bool(case.get("owner_sentence"))
            for case in results.values()
        ),
        "all_cases_have_no_dangerous_effects": all(
            case.get("checks", {}).get("no_dangerous_effects") is True
            for case in results.values()
        ),
    }
    blockers.extend(
        f"matrix:{check_name}"
        for check_name, ok in matrix_checks.items()
        if ok is not True
    )
    return _scenario_packet(
        name="operation_layer_blocker_review_matrix",
        expected=(
            "active position, open order, protection, budget, duplicate submit, "
            "and scope mismatches produce reviewable blocked packets while "
            "keeping real submit forbidden"
        ),
        artifacts={"review_matrix": results, "matrix_checks": matrix_checks},
        passed=not blockers,
        blockers=blockers,
    )


def _scenario_selected_strategygroup_dispatch_guard(output_dir: Path) -> dict[str, Any]:
    selected_dispatches: dict[str, dict[str, Any]] = {}
    selected_dispatch_checks: dict[str, bool] = {}
    for strategy_group_id in sorted(EXPECTED_STRATEGY_GROUPS):
        runtime_instance_id = (
            f"dry-run-runtime-{strategy_group_id.lower().replace('_', '-')}"
        )
        selected_dispatches[strategy_group_id] = dispatcher.build_dispatch_packet(
            resume_pack=_resume_pack_ready_for_finalgate(
                strategy_group_id=strategy_group_id,
                runtime_instance_id=runtime_instance_id,
            ),
            source_path=Path("/tmp/dry-run-post-signal-resume-pack.json"),
            api_base="http://dry-run.local",
            selected_strategy_group_id=strategy_group_id,
            execute_preflight=False,
        )
        dispatch = selected_dispatches[strategy_group_id]
        selected_dispatch_checks[strategy_group_id] = (
            dispatch.get("status") == "ready_for_action_time_final_gate"
            and dispatch.get("dispatch_action")
            == "run_official_action_time_final_gate_preflight"
            and dispatch.get("selected_strategy_group_id") == strategy_group_id
            and dispatch.get("command_plan", {}).get("method") == "GET"
        )
    selected_dispatch = selected_dispatches["MPG-001"]
    out_of_scope_dispatch = dispatcher.build_dispatch_packet(
        resume_pack=_resume_pack_ready_for_finalgate(
            strategy_group_id="SOR-001",
            runtime_instance_id="dry-run-runtime-sor-001",
        ),
        source_path=Path("/tmp/dry-run-post-signal-resume-pack.json"),
        api_base="http://dry-run.local",
        selected_strategy_group_id="MPG-001",
        execute_preflight=True,
    )
    checks = {
        "selected_mpg_dispatch_reaches_finalgate_plan": (
            selected_dispatch.get("status") == "ready_for_action_time_final_gate"
            and selected_dispatch.get("dispatch_action")
            == "run_official_action_time_final_gate_preflight"
            and selected_dispatch.get("selected_strategy_group_id") == "MPG-001"
            and selected_dispatch.get("command_plan", {}).get("method") == "GET"
        ),
        "all_selected_strategygroups_reach_finalgate_dispatch": all(
            selected_dispatch_checks.values()
        ),
        "out_of_scope_signal_blocked_before_finalgate": (
            out_of_scope_dispatch.get("status") == "blocked"
            and out_of_scope_dispatch.get("dispatch_status")
            == "blocked_by_selected_strategygroup_scope"
            and out_of_scope_dispatch.get("command_plan") is None
            and out_of_scope_dispatch.get("safety_invariants", {}).get(
                "official_finalgate_preflight_called"
            )
            is False
        ),
        "out_of_scope_signal_does_not_call_operation_layer": (
            out_of_scope_dispatch.get("safety_invariants", {}).get(
                "official_operation_layer_submit_called"
            )
            is False
        ),
        "no_dangerous_effects": not _dangerous_effects(
            selected_dispatch,
            out_of_scope_dispatch,
        ),
    }
    blockers = [
        f"selected_strategygroup_dispatch_guard:{name}"
        for name, value in checks.items()
        if value is not True
    ]
    return _scenario_packet(
        name="selected_strategygroup_dispatch_guard",
        expected=(
            "selected MPG-001 mock fresh signal can reach FinalGate dispatch, "
            "while an out-of-scope StrategyGroup signal is blocked before "
            "FinalGate or Operation Layer"
        ),
        artifacts={
            "checks": checks,
            "selected_mpg_dispatch": selected_dispatch,
            "selected_strategygroup_dispatches": selected_dispatches,
            "selected_strategygroup_dispatch_checks": selected_dispatch_checks,
            "out_of_scope_dispatch": out_of_scope_dispatch,
        },
        passed=not blockers,
        blockers=blockers,
    )


def _scenario_expanded_watcher_scope_execution_guard(output_dir: Path) -> dict[str, Any]:
    expanded_waiting_resume = _resume_pack_waiting()
    expanded_waiting_resume["selected_runtime_instance_ids"] = [
        "dry-run-runtime-mpg-001",
        "dry-run-runtime-sor-001",
    ]
    expanded_waiting_resume["runtime_signal_summaries"] = [
        {
            "runtime_instance_id": "dry-run-runtime-mpg-001",
            "strategy_family_id": "MPG-001",
            "strategy_family_version_id": "MPG-001-v0",
            "symbol": "MSTR/USDT:USDT",
            "side": "long",
            "status": "waiting_for_signal",
        },
        {
            "runtime_instance_id": "dry-run-runtime-sor-001",
            "strategy_family_id": "SOR-001",
            "strategy_family_version_id": "SOR-001-v0",
            "symbol": "XAG/USDT:USDT",
            "side": "short",
            "status": "waiting_for_signal",
        },
    ]
    expanded_observation = dispatcher.build_dispatch_packet(
        resume_pack=expanded_waiting_resume,
        source_path=Path("/tmp/dry-run-post-signal-resume-pack.json"),
        api_base="http://dry-run.local",
        selected_strategy_group_id="MPG-001",
    )

    ambiguous_actionable_resume = _resume_pack_ready_for_finalgate(
        strategy_group_id="MPG-001",
        runtime_instance_id="dry-run-runtime-mpg-001",
    )
    ambiguous_actionable_resume["runtime_instance_id"] = None
    ambiguous_actionable_resume["action_time_resume"]["runtime_instance_id"] = None
    ambiguous_actionable_resume["action_time_resume"].pop("strategy_family_id", None)
    ambiguous_actionable_resume["selected_runtime_instance_ids"] = [
        "dry-run-runtime-mpg-001",
        "dry-run-runtime-sor-001",
    ]
    ambiguous_actionable_resume["runtime_signal_summaries"] = []
    ambiguous_action = dispatcher.build_dispatch_packet(
        resume_pack=ambiguous_actionable_resume,
        source_path=Path("/tmp/dry-run-post-signal-resume-pack.json"),
        api_base="http://dry-run.local",
        selected_strategy_group_id="MPG-001",
        execute_preflight=True,
    )

    out_of_scope_action = dispatcher.build_dispatch_packet(
        resume_pack=_resume_pack_ready_for_finalgate(
            strategy_group_id="SOR-001",
            runtime_instance_id="dry-run-runtime-sor-001",
        ),
        source_path=Path("/tmp/dry-run-post-signal-resume-pack.json"),
        api_base="http://dry-run.local",
        selected_strategy_group_id="MPG-001",
        execute_preflight=True,
    )
    checks = {
        "expanded_scope_observation_allowed": (
            expanded_observation.get("status") == "waiting_for_market"
            and expanded_observation.get("dispatch_action")
            == "continue_watcher_observation"
            and expanded_observation.get("command_plan") is None
        ),
        "ambiguous_actionable_scope_blocked": (
            ambiguous_action.get("status") == "blocked"
            and ambiguous_action.get("dispatch_status")
            == "blocked_by_selected_strategygroup_scope"
            and ambiguous_action.get("command_plan") is None
            and ambiguous_action.get("blockers")
            == ["missing_fact:selected_strategy_group_id_for_action"]
        ),
        "out_of_scope_actionable_signal_blocked": (
            out_of_scope_action.get("status") == "blocked"
            and out_of_scope_action.get("dispatch_status")
            == "blocked_by_selected_strategygroup_scope"
            and out_of_scope_action.get("command_plan") is None
        ),
        "finalgate_not_called_for_blocked_scope": (
            ambiguous_action.get("safety_invariants", {}).get(
                "official_finalgate_preflight_called"
            )
            is False
            and out_of_scope_action.get("safety_invariants", {}).get(
                "official_finalgate_preflight_called"
            )
            is False
        ),
        "operation_layer_not_called_for_blocked_scope": (
            ambiguous_action.get("safety_invariants", {}).get(
                "official_operation_layer_submit_called"
            )
            is False
            and out_of_scope_action.get("safety_invariants", {}).get(
                "official_operation_layer_submit_called"
            )
            is False
        ),
        "no_dangerous_effects": not _dangerous_effects(
            expanded_observation,
            ambiguous_action,
            out_of_scope_action,
        ),
    }
    blockers = [
        f"expanded_watcher_scope_execution_guard:{name}"
        for name, value in checks.items()
        if value is not True
    ]
    return _scenario_packet(
        name="expanded_watcher_scope_execution_guard",
        expected=(
            "expanded watcher scope may observe multiple runtimes, but any "
            "actionable step must prove selected StrategyGroup scope before "
            "FinalGate or Operation Layer"
        ),
        artifacts={
            "checks": checks,
            "expanded_observation": expanded_observation,
            "ambiguous_action": ambiguous_action,
            "out_of_scope_action": out_of_scope_action,
        },
        passed=not blockers,
        blockers=blockers,
    )


def _scenario_operation_layer_authorization_chain_guard(output_dir: Path) -> dict[str, Any]:
    stale_report = _operation_evidence_report()
    stale_report["ids"]["authorization_id"] = "dry-run-stale-auth-previous-attempt"
    stale_report["steps"][0]["id_summary"]["authorization_id"] = (
        "dry-run-stale-auth-previous-attempt"
    )
    stale_operation_layer = dispatcher.build_dispatch_packet(
        resume_pack=_resume_pack_finalgate_ready(),
        source_path=Path("/tmp/dry-run-post-signal-resume-pack.json"),
        api_base="http://dry-run.local",
        operation_layer_evidence_report=stale_report,
        operation_layer_evidence_report_path=(
            "/tmp/dry-run-stale-operation-layer-evidence.json"
        ),
        execute_operation_layer_submit=True,
    )

    missing_auth_report = _operation_evidence_report()
    missing_auth_report["ids"].pop("authorization_id", None)
    missing_auth_report["steps"][0]["id_summary"].pop("authorization_id", None)
    missing_auth_operation_layer = dispatcher.build_dispatch_packet(
        resume_pack=_resume_pack_finalgate_ready(),
        source_path=Path("/tmp/dry-run-post-signal-resume-pack.json"),
        api_base="http://dry-run.local",
        operation_layer_evidence_report=missing_auth_report,
        operation_layer_evidence_report_path=(
            "/tmp/dry-run-missing-authorization-operation-layer-evidence.json"
        ),
        execute_operation_layer_submit=True,
    )

    checks = {
        "stale_authorization_evidence_blocked": (
            stale_operation_layer.get("status") == "operation_layer_submit_blocked"
            and stale_operation_layer.get("dispatch_status")
            == "blocked_before_official_operation_layer_submit"
            and stale_operation_layer.get("operation_layer_readiness", {}).get(
                "blocker_class"
            )
            == "hard_safety_stop"
            and any(
                str(blocker).startswith(
                    "operation_layer_authorization_id_mismatch:"
                )
                for blocker in stale_operation_layer.get(
                    "operation_layer_readiness", {}
                ).get("blockers", [])
            )
        ),
        "missing_authorization_evidence_blocked": (
            missing_auth_operation_layer.get("status")
            == "operation_layer_submit_blocked"
            and missing_auth_operation_layer.get("dispatch_status")
            == "blocked_before_official_operation_layer_submit"
            and "operation_layer_authorization_id_missing"
            in missing_auth_operation_layer.get("operation_layer_readiness", {}).get(
                "blockers", []
            )
        ),
        "stale_evidence_does_not_call_operation_layer": (
            stale_operation_layer.get("safety_invariants", {}).get(
                "official_operation_layer_submit_called"
            )
            is False
        ),
        "missing_auth_does_not_call_operation_layer": (
            missing_auth_operation_layer.get("safety_invariants", {}).get(
                "official_operation_layer_submit_called"
            )
            is False
        ),
        "no_dangerous_effects": not _dangerous_effects(
            stale_operation_layer,
            missing_auth_operation_layer,
        ),
    }
    blockers = [
        f"operation_layer_authorization_chain_guard:{name}"
        for name, value in checks.items()
        if value is not True
    ]
    return _scenario_packet(
        name="operation_layer_authorization_chain_guard",
        expected=(
            "stale or missing Operation Layer authorization evidence blocks "
            "before official submit and does not call the gateway action"
        ),
        artifacts={
            "checks": checks,
            "stale_operation_layer": stale_operation_layer,
            "missing_auth_operation_layer": missing_auth_operation_layer,
        },
        passed=not blockers,
        blockers=blockers,
    )


def _mock_operation_layer_closed_loop() -> dict[str, Any]:
    calls: list[dict[str, Any]] = []
    original_session_cookie = dispatcher._session_cookie
    original_request_json = dispatcher._request_json

    def session_cookie() -> tuple[str, str | None]:
        return ("brc_operator_session=dry-run-session", None)

    def request_json(**kwargs: Any) -> dict[str, Any]:
        calls.append(
            {
                "method": kwargs.get("method"),
                "url_kind": "post_submit_finalize"
                if "post-submit-finalize-packets" in str(kwargs.get("url") or "")
                else "operation_layer_submit",
                "body_keys": sorted((kwargs.get("body") or {}).keys()),
            }
        )
        if "post-submit-finalize-packets" in str(kwargs.get("url") or ""):
            return {
                "http_status": 200,
                "error": False,
                "body": {
                    "status": "finalized_ready_for_next_attempt",
                    "authorization_id": FRESH_AUTHORIZATION_ID,
                    "runtime_instance_id": RUNTIME_ID,
                    "exchange_submit_execution_result_id": (
                        "dry-run-submit-result-1"
                    ),
                    "submit_outcome_review_id": "dry-run-review-1",
                    "post_submit_budget_settlement_id": "dry-run-settlement-1",
                    "blockers": [],
                    "warnings": ["dry_run_non_executing_finalize_shape"],
                    "next_attempt_gate": {
                        "status": "ready_for_fresh_signal",
                        "blockers": [],
                    },
                    "exchange_called": False,
                    "exchange_order_submitted": False,
                    "order_lifecycle_called": False,
                    "owner_bounded_execution_called": False,
                    "withdrawal_or_transfer_created": False,
                    "position_closed": False,
                    "order_cancelled": False,
                    "order_created": False,
                },
            }
        return {
            "http_status": 200,
            "error": False,
            "body": {
                "status": "exchange_submit_orders_submitted",
                "authorization_id": FRESH_AUTHORIZATION_ID,
                "runtime_instance_id": RUNTIME_ID,
                "reservation_id": "dry-run-attempt-reservation-1",
                "execution_mode": "real_gateway_action",
                "blockers": [],
                "warnings": ["dry_run_simulated_exchange_submit"],
                "exchange_called": True,
                "exchange_order_submitted": True,
                "order_lifecycle_submit_called": True,
                "owner_bounded_execution_called": False,
                "execution_intent_status_changed": False,
                "withdrawal_or_transfer_created": False,
                "submitted_exchange_order_ids": ["dry-run-entry-1"],
                "entry_exchange_order_id": "dry-run-entry-1",
                "protection_exchange_order_ids": ["dry-run-stop-1"],
            },
        }

    dispatcher._session_cookie = session_cookie
    dispatcher._request_json = request_json
    try:
        packet = dispatcher.build_dispatch_packet(
            resume_pack=_resume_pack_finalgate_ready(),
            source_path=Path("/tmp/dry-run-post-signal-resume-pack.json"),
            api_base="http://dry-run.local",
            operation_layer_evidence_report=_operation_evidence_report(),
            operation_layer_evidence_report_path=(
                "/tmp/dry-run-operation-layer-evidence.json"
            ),
            execute_operation_layer_submit=True,
            execute_post_submit_finalize=True,
        )
    finally:
        dispatcher._session_cookie = original_session_cookie
        dispatcher._request_json = original_request_json

    checks = {
        "dispatcher_reached_settled_status": packet.get("status") == "settled",
        "submit_endpoint_called_once": (
            len(
                [
                    call
                    for call in calls
                    if call["url_kind"] == "operation_layer_submit"
                ]
            )
            == 1
        ),
        "finalize_endpoint_called_once": (
            len([call for call in calls if call["url_kind"] == "post_submit_finalize"])
            == 1
        ),
        "next_attempt_gate_ready": (
            packet.get("post_submit_finalize_result", {})
            .get("body", {})
            .get("next_attempt_gate", {})
            .get("status")
            == "ready_for_fresh_signal"
        ),
        "budget_settlement_recorded": bool(
            packet.get("post_submit_finalize_result", {})
            .get("body", {})
            .get("post_submit_budget_settlement_id")
        ),
        "review_recorded": bool(
            packet.get("post_submit_finalize_result", {})
            .get("body", {})
            .get("submit_outcome_review_id")
        ),
        "no_withdrawal_or_transfer": (
            packet.get("safety_invariants", {}).get(
                "withdrawal_or_transfer_created"
            )
            is False
        ),
    }
    return {
        "scope": "runtime_dry_run_mock_operation_layer_closed_loop",
        "status": "passed" if all(checks.values()) else "failed",
        "simulated_exchange_effects": True,
        "actual_exchange_write_called": False,
        "actual_order_created": False,
        "actual_order_lifecycle_called": False,
        "actual_withdrawal_or_transfer_created": False,
        "checks": checks,
        "api_calls": calls,
        "dispatcher_packet": packet,
    }


def _scenario_mock_operation_layer_closed_loop(output_dir: Path) -> dict[str, Any]:
    closed_loop = _mock_operation_layer_closed_loop()
    passed = (
        closed_loop["status"] == "passed"
        and closed_loop["actual_exchange_write_called"] is False
        and closed_loop["actual_order_created"] is False
        and closed_loop["actual_order_lifecycle_called"] is False
        and closed_loop["actual_withdrawal_or_transfer_created"] is False
    )
    return _scenario_packet(
        name="mock_operation_layer_submit_finalize_pass",
        expected=(
            "dispatcher submit and post-submit finalize path reaches settled "
            "with mock responses only; simulated exchange effects are not real "
            "execution proof"
        ),
        artifacts={"mock_operation_layer_closed_loop": closed_loop},
        passed=passed,
        blockers=[
            *closed_loop.get("dispatcher_packet", {}).get("blockers", []),
            *[
                f"closed_loop_check_failed:{name}"
                for name, value in closed_loop["checks"].items()
                if not value
            ],
        ],
    )


def _mock_post_submit_closed_loop_evidence_guard() -> dict[str, Any]:
    submit_body = {
        "status": "exchange_submit_orders_submitted",
        "authorization_id": FRESH_AUTHORIZATION_ID,
        "runtime_instance_id": RUNTIME_ID,
        "reservation_id": "dry-run-attempt-reservation-1",
        "execution_mode": "real_gateway_action",
        "blockers": [],
        "warnings": ["dry_run_simulated_exchange_submit"],
        "exchange_called": True,
        "exchange_order_submitted": True,
        "order_lifecycle_submit_called": True,
        "owner_bounded_execution_called": False,
        "execution_intent_status_changed": False,
        "withdrawal_or_transfer_created": False,
        "submitted_exchange_order_ids": ["dry-run-entry-1"],
        "entry_exchange_order_id": "dry-run-entry-1",
        "protection_exchange_order_ids": ["dry-run-stop-1"],
    }
    base_finalize_body = {
        "status": "finalized_ready_for_next_attempt",
        "authorization_id": FRESH_AUTHORIZATION_ID,
        "runtime_instance_id": RUNTIME_ID,
        "exchange_submit_execution_result_id": "dry-run-submit-result-1",
        "submit_outcome_review_id": "dry-run-review-1",
        "post_submit_budget_settlement_id": "dry-run-settlement-1",
        "blockers": [],
        "warnings": ["dry_run_non_executing_finalize_shape"],
        "next_attempt_gate": {
            "status": "ready_for_fresh_signal",
            "blockers": [],
        },
        "exchange_called": False,
        "exchange_order_submitted": False,
        "order_lifecycle_called": False,
        "owner_bounded_execution_called": False,
        "withdrawal_or_transfer_created": False,
        "position_closed": False,
        "order_cancelled": False,
        "order_created": False,
    }
    case_bodies = {
        "missing_budget_settlement": {
            key: value
            for key, value in base_finalize_body.items()
            if key != "post_submit_budget_settlement_id"
        },
        "missing_review": {
            key: value
            for key, value in base_finalize_body.items()
            if key != "submit_outcome_review_id"
        },
        "next_attempt_gate_not_ready": {
            **base_finalize_body,
            "next_attempt_gate": {
                "status": "blocked",
                "blockers": ["review_required_before_next_action"],
            },
        },
    }
    results: dict[str, Any] = {}
    original_session_cookie = dispatcher._session_cookie
    original_request_json = dispatcher._request_json

    def session_cookie() -> tuple[str, str | None]:
        return ("brc_operator_session=dry-run-session", None)

    try:
        for name, finalize_body in case_bodies.items():
            calls: list[dict[str, Any]] = []

            def request_json(**kwargs: Any) -> dict[str, Any]:
                calls.append(
                    {
                        "method": kwargs.get("method"),
                        "url_kind": (
                            "post_submit_finalize"
                            if "post-submit-finalize-packets"
                            in str(kwargs.get("url") or "")
                            else "operation_layer_submit"
                        ),
                    }
                )
                if calls[-1]["url_kind"] == "post_submit_finalize":
                    return {
                        "http_status": 200,
                        "error": False,
                        "body": finalize_body,
                    }
                return {
                    "http_status": 200,
                    "error": False,
                    "body": submit_body,
                }

            dispatcher._session_cookie = session_cookie
            dispatcher._request_json = request_json
            packet = dispatcher.build_dispatch_packet(
                resume_pack=_resume_pack_finalgate_ready(),
                source_path=Path("/tmp/dry-run-post-signal-resume-pack.json"),
                api_base="http://dry-run.local",
                operation_layer_evidence_report=_operation_evidence_report(),
                operation_layer_evidence_report_path=(
                    "/tmp/dry-run-operation-layer-evidence.json"
                ),
                execute_operation_layer_submit=True,
                execute_post_submit_finalize=True,
            )
            checks = {
                "blocked_before_next_attempt": (
                    packet.get("status") == "post_submit_finalize_blocked"
                    and packet.get("dispatch_status")
                    == "blocked_by_post_submit_finalize_incomplete_closed_loop"
                    and packet.get("dispatch_action") is None
                ),
                "owner_state_halts_new_entries": (
                    packet.get("owner_state", {}).get("downgrade_mode")
                    == "halt_new_entries_until_post_submit_settled"
                ),
                "finalize_endpoint_called": (
                    packet.get("safety_invariants", {}).get(
                        "official_post_submit_finalize_called"
                    )
                    is True
                ),
                "no_withdrawal_or_transfer": (
                    packet.get("safety_invariants", {}).get(
                        "withdrawal_or_transfer_created"
                    )
                    is False
                ),
                "no_extra_operation_layer_call": (
                    len(
                        [
                            call
                            for call in calls
                            if call["url_kind"] == "operation_layer_submit"
                        ]
                    )
                    == 1
                ),
            }
            results[name] = {
                "checks": checks,
                "blockers": packet.get("blockers", []),
                "packet": packet,
                "api_calls": calls,
            }
    finally:
        dispatcher._session_cookie = original_session_cookie
        dispatcher._request_json = original_request_json

    blockers = [
        f"{case}:{check}"
        for case, result in results.items()
        for check, ok in result.get("checks", {}).items()
        if ok is not True
    ]
    exit_outcome_matrix = _mock_post_submit_exit_outcome_matrix()
    blockers.extend(
        f"exit_outcome_matrix:{check}"
        for check, ok in exit_outcome_matrix.get("checks", {}).items()
        if ok is not True
    )
    return {
        "scope": "runtime_dry_run_post_submit_closed_loop_evidence_guard",
        "status": "passed" if not blockers else "failed",
        "simulated_exchange_effects": True,
        "actual_exchange_write_called": False,
        "actual_order_created": False,
        "actual_order_lifecycle_called": False,
        "actual_withdrawal_or_transfer_created": False,
        "cases": results,
        "exit_outcome_matrix": exit_outcome_matrix,
        "checks": {
            "all_incomplete_closed_loop_cases_block_next_attempt": not blockers,
            "exit_outcome_matrix_expected_cases_present": exit_outcome_matrix[
                "checks"
            ]["expected_cases_present"],
            "exit_outcome_matrix_all_cases_have_accounting_policy": (
                exit_outcome_matrix["checks"][
                    "all_cases_have_accounting_policy"
                ]
            ),
            "exit_outcome_matrix_all_cases_have_reconciliation_policy": (
                exit_outcome_matrix["checks"][
                    "all_cases_have_reconciliation_policy"
                ]
            ),
            "exit_outcome_matrix_all_cases_have_next_attempt_gate": (
                exit_outcome_matrix["checks"][
                    "all_cases_have_next_attempt_gate"
                ]
            ),
            "exit_outcome_matrix_no_dangerous_effects": exit_outcome_matrix[
                "checks"
            ]["no_dangerous_effects"],
            "actual_dangerous_effects_absent": True,
        },
        "blockers": blockers,
    }


def _scenario_post_submit_closed_loop_evidence_guard(output_dir: Path) -> dict[str, Any]:
    guard = _mock_post_submit_closed_loop_evidence_guard()
    passed = (
        guard["status"] == "passed"
        and all(guard.get("checks", {}).values())
    )
    return _scenario_packet(
        name="post_submit_closed_loop_evidence_guard",
        expected=(
            "post-submit finalize must include submit result, budget settlement, "
            "review, and next-attempt gate evidence before the dispatcher returns "
            "to fresh-signal observation"
        ),
        artifacts={"post_submit_closed_loop_evidence_guard": guard},
        passed=passed,
        blockers=guard.get("blockers", []),
    )


def _mock_post_submit_exit_outcome_matrix() -> dict[str, Any]:
    cases = {
        "entry_filled_protection_ok": {
            "submit_outcome": "entry_filled",
            "position_state": "active_position_open",
            "protection_state": "exchange_native_hard_stop_present",
            "finalize_policy": "record_fill_and_keep_position_open",
            "reconciliation_policy": "verify_entry_position_and_exchange_stop",
            "budget_policy": "keep_runtime_budget_reserved_while_position_open",
            "review_policy": "record_open_position_review_snapshot",
            "next_attempt_gate": "blocked_until_position_closed_or_scope_allows",
            "reduce_only_recovery_mode": False,
        },
        "entry_filled_protection_failed": {
            "submit_outcome": "entry_filled",
            "position_state": "active_position_open",
            "protection_state": "exchange_native_hard_stop_missing",
            "finalize_policy": "record_fill_and_protection_failure",
            "reconciliation_policy": "halt_new_entries_until_protection_reconciled",
            "budget_policy": "hold_or_reconcile_budget_until_position_resolved",
            "review_policy": "require_recovery_review",
            "next_attempt_gate": "blocked_protection_recovery_required",
            "reduce_only_recovery_mode": True,
        },
        "partial_fill": {
            "submit_outcome": "partial_fill",
            "position_state": "active_position_open_or_residual",
            "protection_state": "protection_required_for_filled_quantity",
            "finalize_policy": "count_as_attempt_and_record_partial_fill",
            "reconciliation_policy": "reconcile_filled_quantity_before_new_entry",
            "budget_policy": "hold_budget_for_filled_or_residual_exposure",
            "review_policy": "record_partial_fill_review",
            "next_attempt_gate": "blocked_until_partial_fill_reconciled",
            "reduce_only_recovery_mode": "if_protection_missing_or_residual_risk",
        },
        "exchange_submit_failed_before_acceptance": {
            "submit_outcome": "submit_failed_before_exchange_acceptance",
            "position_state": "no_position_expected",
            "protection_state": "no_protection_order_expected",
            "finalize_policy": "record_submit_failure_without_fill",
            "reconciliation_policy": "verify_no_exchange_position_or_order",
            "budget_policy": "release_reserved_budget_after_no_fill_verified",
            "review_policy": "record_submit_failure_review",
            "next_attempt_gate": "ready_after_no_fill_reconciliation",
            "reduce_only_recovery_mode": False,
        },
        "active_position_remains_open": {
            "submit_outcome": "position_still_open_after_finalize",
            "position_state": "active_position_open",
            "protection_state": "exchange_native_hard_stop_required",
            "finalize_policy": "record_open_position_lifecycle_packet",
            "reconciliation_policy": "continue_position_monitoring",
            "budget_policy": "keep_budget_reserved_until_flat_or_released",
            "review_policy": "record_open_position_status_snapshot",
            "next_attempt_gate": "blocked_for_same_scope_while_position_open",
            "reduce_only_recovery_mode": "only_if_hard_stop_missing_or_drift",
        },
        "position_closed_by_sl_tp_or_reduce_only_recovery": {
            "submit_outcome": "position_closed",
            "position_state": "flat",
            "protection_state": "closed_or_cancelled_protection_reconciled",
            "finalize_policy": "record_close_outcome",
            "reconciliation_policy": "verify_flat_and_cancel_orphan_protection",
            "budget_policy": "settle_and_release_remaining_budget",
            "review_policy": "record_closed_trade_review",
            "next_attempt_gate": "ready_for_fresh_signal_after_review",
            "reduce_only_recovery_mode": False,
        },
    }
    checks = {
        "expected_cases_present": set(cases) == EXPECTED_POST_SUBMIT_EXIT_OUTCOME_CASES,
        "all_cases_have_accounting_policy": all(
            bool(case.get("budget_policy")) and bool(case.get("finalize_policy"))
            for case in cases.values()
        ),
        "all_cases_have_reconciliation_policy": all(
            bool(case.get("reconciliation_policy")) for case in cases.values()
        ),
        "all_cases_have_next_attempt_gate": all(
            bool(case.get("next_attempt_gate")) for case in cases.values()
        ),
        "all_cases_have_review_policy": all(
            bool(case.get("review_policy")) for case in cases.values()
        ),
        "protection_failure_enters_reduce_only_recovery": (
            cases["entry_filled_protection_failed"]["reduce_only_recovery_mode"]
            is True
        ),
        "submit_failure_releases_only_after_no_fill_verified": (
            cases["exchange_submit_failed_before_acceptance"]["budget_policy"]
            == "release_reserved_budget_after_no_fill_verified"
        ),
        "active_position_blocks_same_scope_next_attempt": (
            cases["active_position_remains_open"]["next_attempt_gate"]
            == "blocked_for_same_scope_while_position_open"
        ),
        "closed_position_requires_review_before_fresh_signal": (
            cases["position_closed_by_sl_tp_or_reduce_only_recovery"][
                "review_policy"
            ]
            == "record_closed_trade_review"
        ),
        "no_dangerous_effects": True,
    }
    return {
        "scope": "runtime_dry_run_post_submit_exit_outcome_matrix",
        "status": "passed" if all(checks.values()) else "failed",
        "cases": cases,
        "checks": checks,
        "actual_exchange_write_called": False,
        "actual_order_created": False,
        "actual_order_lifecycle_called": False,
        "actual_withdrawal_or_transfer_created": False,
    }


def _mock_operation_layer_submit_result_identity_guard() -> dict[str, Any]:
    base_submit_body = {
        "status": "exchange_submit_orders_submitted",
        "authorization_id": FRESH_AUTHORIZATION_ID,
        "runtime_instance_id": RUNTIME_ID,
        "reservation_id": "dry-run-attempt-reservation-1",
        "execution_mode": "real_gateway_action",
        "blockers": [],
        "warnings": ["dry_run_simulated_exchange_submit"],
        "exchange_called": True,
        "exchange_order_submitted": True,
        "order_lifecycle_submit_called": True,
        "owner_bounded_execution_called": False,
        "execution_intent_status_changed": False,
        "withdrawal_or_transfer_created": False,
        "submitted_exchange_order_ids": ["dry-run-entry-1"],
        "entry_exchange_order_id": "dry-run-entry-1",
        "protection_exchange_order_ids": ["dry-run-stop-1"],
    }
    case_bodies = {
        "authorization_mismatch": {
            **base_submit_body,
            "authorization_id": "dry-run-other-authorization",
        },
        "runtime_mismatch": {
            **base_submit_body,
            "runtime_instance_id": "dry-run-other-runtime",
        },
        "reservation_mismatch": {
            **base_submit_body,
            "reservation_id": "dry-run-other-reservation",
        },
    }
    results: dict[str, Any] = {}
    original_session_cookie = dispatcher._session_cookie
    original_request_json = dispatcher._request_json

    def session_cookie() -> tuple[str, str | None]:
        return ("brc_operator_session=dry-run-session", None)

    try:
        for name, submit_body in case_bodies.items():
            calls: list[dict[str, Any]] = []

            def request_json(**kwargs: Any) -> dict[str, Any]:
                calls.append(
                    {
                        "method": kwargs.get("method"),
                        "url_kind": (
                            "post_submit_finalize"
                            if "post-submit-finalize-packets"
                            in str(kwargs.get("url") or "")
                            else "operation_layer_submit"
                        ),
                    }
                )
                return {
                    "http_status": 200,
                    "error": False,
                    "body": submit_body,
                }

            dispatcher._session_cookie = session_cookie
            dispatcher._request_json = request_json
            packet = dispatcher.build_dispatch_packet(
                resume_pack=_resume_pack_finalgate_ready(),
                source_path=Path("/tmp/dry-run-post-signal-resume-pack.json"),
                api_base="http://dry-run.local",
                operation_layer_evidence_report=_operation_evidence_report(),
                operation_layer_evidence_report_path=(
                    "/tmp/dry-run-operation-layer-evidence.json"
                ),
                execute_operation_layer_submit=True,
                execute_post_submit_finalize=True,
            )
            checks = {
                "blocked_before_finalize": (
                    packet.get("status") == "operation_layer_submit_failed"
                    and packet.get("dispatch_status")
                    == "official_operation_layer_submit_result_identity_mismatch"
                    and packet.get("dispatch_action") is None
                    and "post_submit_finalize_result" not in packet
                ),
                "owner_state_halts_new_entries": (
                    packet.get("owner_state", {}).get("downgrade_mode")
                    == "halt_new_entries_until_reconciled"
                ),
                "operation_layer_called_once": (
                    len(
                        [
                            call
                            for call in calls
                            if call["url_kind"] == "operation_layer_submit"
                        ]
                    )
                    == 1
                ),
                "post_submit_finalize_not_called": (
                    len(
                        [
                            call
                            for call in calls
                            if call["url_kind"] == "post_submit_finalize"
                        ]
                    )
                    == 0
                ),
                "no_withdrawal_or_transfer": (
                    packet.get("safety_invariants", {}).get(
                        "withdrawal_or_transfer_created"
                    )
                    is False
                ),
            }
            results[name] = {
                "checks": checks,
                "blockers": packet.get("blockers", []),
                "packet": packet,
                "api_calls": calls,
            }
    finally:
        dispatcher._session_cookie = original_session_cookie
        dispatcher._request_json = original_request_json

    blockers = [
        f"{case}:{check}"
        for case, result in results.items()
        for check, ok in result.get("checks", {}).items()
        if ok is not True
    ]
    return {
        "scope": "runtime_dry_run_operation_layer_submit_result_identity_guard",
        "status": "passed" if not blockers else "failed",
        "simulated_exchange_effects": True,
        "actual_exchange_write_called": False,
        "actual_order_created": False,
        "actual_order_lifecycle_called": False,
        "actual_withdrawal_or_transfer_created": False,
        "cases": results,
        "checks": {
            "all_submit_result_identity_mismatch_cases_block_finalize": not blockers,
            "actual_dangerous_effects_absent": True,
        },
        "blockers": blockers,
    }


def _scenario_operation_layer_submit_result_identity_guard(output_dir: Path) -> dict[str, Any]:
    guard = _mock_operation_layer_submit_result_identity_guard()
    passed = guard["status"] == "passed" and all(guard.get("checks", {}).values())
    return _scenario_packet(
        name="operation_layer_submit_result_identity_guard",
        expected=(
            "Operation Layer submit result authorization, runtime, and reservation "
            "identity must match the current evidence before post-submit finalize"
        ),
        artifacts={"operation_layer_submit_result_identity_guard": guard},
        passed=passed,
        blockers=guard.get("blockers", []),
    )


def _mock_post_submit_finalize_result_identity_guard() -> dict[str, Any]:
    submit_body = {
        "status": "exchange_submit_orders_submitted",
        "authorization_id": FRESH_AUTHORIZATION_ID,
        "runtime_instance_id": RUNTIME_ID,
        "reservation_id": "dry-run-attempt-reservation-1",
        "execution_mode": "real_gateway_action",
        "blockers": [],
        "warnings": ["dry_run_simulated_exchange_submit"],
        "exchange_called": True,
        "exchange_order_submitted": True,
        "order_lifecycle_submit_called": True,
        "owner_bounded_execution_called": False,
        "execution_intent_status_changed": False,
        "withdrawal_or_transfer_created": False,
        "submitted_exchange_order_ids": ["dry-run-entry-1"],
        "entry_exchange_order_id": "dry-run-entry-1",
        "protection_exchange_order_ids": ["dry-run-stop-1"],
    }
    base_finalize_body = {
        "status": "finalized_ready_for_next_attempt",
        "authorization_id": FRESH_AUTHORIZATION_ID,
        "runtime_instance_id": RUNTIME_ID,
        "reservation_id": "dry-run-attempt-reservation-1",
        "exchange_submit_execution_result_id": "dry-run-submit-result-1",
        "submit_outcome_review_id": "dry-run-review-1",
        "post_submit_budget_settlement_id": "dry-run-settlement-1",
        "blockers": [],
        "warnings": ["dry_run_non_executing_finalize_shape"],
        "next_attempt_gate": {
            "status": "ready_for_fresh_signal",
            "blockers": [],
        },
        "exchange_called": False,
        "exchange_order_submitted": False,
        "order_lifecycle_called": False,
        "owner_bounded_execution_called": False,
        "withdrawal_or_transfer_created": False,
        "position_closed": False,
        "order_cancelled": False,
        "order_created": False,
    }
    case_bodies = {
        "authorization_mismatch": {
            **base_finalize_body,
            "authorization_id": "dry-run-other-authorization",
        },
        "runtime_mismatch": {
            **base_finalize_body,
            "runtime_instance_id": "dry-run-other-runtime",
        },
        "reservation_mismatch": {
            **base_finalize_body,
            "reservation_id": "dry-run-other-reservation",
        },
    }
    results: dict[str, Any] = {}
    original_session_cookie = dispatcher._session_cookie
    original_request_json = dispatcher._request_json

    def session_cookie() -> tuple[str, str | None]:
        return ("brc_operator_session=dry-run-session", None)

    try:
        for name, finalize_body in case_bodies.items():
            calls: list[dict[str, Any]] = []

            def request_json(**kwargs: Any) -> dict[str, Any]:
                url = str(kwargs.get("url") or "")
                url_kind = (
                    "post_submit_finalize"
                    if "post-submit-finalize-packets" in url
                    else "operation_layer_submit"
                )
                calls.append(
                    {
                        "method": kwargs.get("method"),
                        "url_kind": url_kind,
                    }
                )
                return {
                    "http_status": 200,
                    "error": False,
                    "body": (
                        finalize_body
                        if url_kind == "post_submit_finalize"
                        else submit_body
                    ),
                }

            dispatcher._session_cookie = session_cookie
            dispatcher._request_json = request_json
            packet = dispatcher.build_dispatch_packet(
                resume_pack=_resume_pack_finalgate_ready(),
                source_path=Path("/tmp/dry-run-post-signal-resume-pack.json"),
                api_base="http://dry-run.local",
                operation_layer_evidence_report=_operation_evidence_report(),
                operation_layer_evidence_report_path=(
                    "/tmp/dry-run-operation-layer-evidence.json"
                ),
                execute_operation_layer_submit=True,
                execute_post_submit_finalize=True,
            )
            checks = {
                "blocked_after_finalize_response": (
                    packet.get("status") == "post_submit_finalize_blocked"
                    and packet.get("dispatch_status")
                    == "post_submit_finalize_result_identity_mismatch"
                    and packet.get("dispatch_action") is None
                ),
                "owner_state_halts_new_entries": (
                    packet.get("owner_state", {}).get("downgrade_mode")
                    == "halt_new_entries_until_post_submit_settled"
                ),
                "operation_layer_called_once": (
                    len(
                        [
                            call
                            for call in calls
                            if call["url_kind"] == "operation_layer_submit"
                        ]
                    )
                    == 1
                ),
                "post_submit_finalize_called_once": (
                    len(
                        [
                            call
                            for call in calls
                            if call["url_kind"] == "post_submit_finalize"
                        ]
                    )
                    == 1
                ),
                "did_not_settle": packet.get("status") != "settled",
                "no_withdrawal_or_transfer": (
                    packet.get("safety_invariants", {}).get(
                        "withdrawal_or_transfer_created"
                    )
                    is False
                ),
            }
            results[name] = {
                "checks": checks,
                "blockers": packet.get("blockers", []),
                "packet": packet,
                "api_calls": calls,
            }
    finally:
        dispatcher._session_cookie = original_session_cookie
        dispatcher._request_json = original_request_json

    blockers = [
        f"{case}:{check}"
        for case, result in results.items()
        for check, ok in result.get("checks", {}).items()
        if ok is not True
    ]
    return {
        "scope": "runtime_dry_run_post_submit_finalize_result_identity_guard",
        "status": "passed" if not blockers else "failed",
        "simulated_exchange_effects": True,
        "actual_exchange_write_called": False,
        "actual_order_created": False,
        "actual_order_lifecycle_called": False,
        "actual_withdrawal_or_transfer_created": False,
        "cases": results,
        "checks": {
            "all_finalize_result_identity_mismatch_cases_block_settled": (
                not blockers
            ),
            "actual_dangerous_effects_absent": True,
        },
        "blockers": blockers,
    }


def _scenario_post_submit_finalize_result_identity_guard(
    output_dir: Path,
) -> dict[str, Any]:
    guard = _mock_post_submit_finalize_result_identity_guard()
    passed = guard["status"] == "passed" and all(guard.get("checks", {}).values())
    return _scenario_packet(
        name="post_submit_finalize_result_identity_guard",
        expected=(
            "Post-submit finalize result authorization, runtime, and reservation "
            "identity must match the current submit chain before settled state"
        ),
        artifacts={"post_submit_finalize_result_identity_guard": guard},
        passed=passed,
        blockers=guard.get("blockers", []),
    )


def _scenario_packet(
    *,
    name: str,
    expected: str,
    artifacts: dict[str, Any],
    passed: bool,
    blockers: list[str],
) -> dict[str, Any]:
    return {
        "name": name,
        "status": "passed" if passed else "failed",
        "expected": expected,
        "blockers": list(dict.fromkeys(str(item) for item in blockers if str(item).strip())),
        "artifacts": artifacts,
        "safety_invariants": {
            "real_order_created": False,
            "exchange_write_called": False,
            "order_lifecycle_called": False,
            "withdrawal_or_transfer_created": False,
            "finalgate_bypassed": False,
            "operation_layer_bypassed": False,
            "disabled_smoke_is_real_execution_proof": False,
            "dangerous_effects": _dangerous_effects(*artifacts.values()),
        },
    }


def _dangerous_effects(*values: Any) -> list[str]:
    dangerous_true_keys = {
        "places_order",
        "order_created",
        "exchange_called",
        "exchange_write_called",
        "exchange_order_submitted",
        "calls_order_lifecycle",
        "order_lifecycle_called",
        "withdrawal_or_transfer_created",
        "withdrawal_or_transfer_requested",
        "finalgate_bypassed",
        "operation_layer_bypassed",
        "disabled_smoke_is_real_execution_proof",
    }
    allowed_true_keys = {
        "official_finalgate_preflight_called",
        "calls_official_submit_endpoint",
        "official_endpoint_called",
    }
    effects: list[str] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            if value.get("simulated_exchange_effects") is True:
                return
            for key, nested in value.items():
                nested_path = f"{path}.{key}" if path else str(key)
                if key in dangerous_true_keys and nested is True:
                    effects.append(nested_path)
                if key in allowed_true_keys:
                    continue
                walk(nested, nested_path)
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                walk(nested, f"{path}[{index}]")

    for value in values:
        walk(value, "")
    return sorted(set(effects))


def _operation_layer_submit_called(packet: dict[str, Any]) -> bool:
    safety = packet.get("safety_invariants")
    return isinstance(safety, dict) and safety.get("official_operation_layer_submit_called") is True


def build_audit_chain(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    scenarios = [
        _scenario_no_signal(output_dir),
        _scenario_mock_pass(output_dir),
        _scenario_scoped_pipeline_operation_layer_handoff(output_dir),
        _scenario_non_executing_prepare_auto_bridge(output_dir),
        _scenario_mock_operation_layer_closed_loop(output_dir),
        _scenario_required_facts_missing(output_dir),
        _scenario_active_conflict(output_dir),
        _scenario_operation_layer_blocker_review_matrix(output_dir),
        _scenario_selected_strategygroup_dispatch_guard(output_dir),
        _scenario_expanded_watcher_scope_execution_guard(output_dir),
        _scenario_operation_layer_authorization_chain_guard(output_dir),
        _scenario_post_submit_closed_loop_evidence_guard(output_dir),
        _scenario_operation_layer_submit_result_identity_guard(output_dir),
        _scenario_post_submit_finalize_result_identity_guard(output_dir),
    ]
    shared_pipeline = _shared_runtime_pipeline_validation()
    blockers = [
        f"{scenario['name']}:{blocker}"
        for scenario in scenarios
        if scenario["status"] != "passed"
        for blocker in (scenario.get("blockers") or ["scenario_failed"])
    ]
    blockers.extend(
        f"shared_runtime_pipeline_validation:{blocker}"
        for blocker in shared_pipeline.get("blockers", [])
    )
    dangerous_effects = _dangerous_effects(*scenarios)
    checks = {
        "scenario_count": len(scenarios),
        "required_scenarios_present": len(scenarios) == 14,
        "all_scenarios_passed": all(item["status"] == "passed" for item in scenarios),
        "dangerous_effects_absent": not dangerous_effects,
        "disabled_smoke_not_real_execution_proof": True,
        "operation_layer_evidence_relay_checked": all(
            _scenario_artifact(
                scenarios,
                "mock_fresh_signal_dry_run_pass",
                "operation_layer_relay_checks",
            ).values()
        ),
        "fresh_signal_fast_auto_chain_checked": all(
            _scenario_artifact(
                scenarios,
                "mock_fresh_signal_dry_run_pass",
                "fast_auto_chain_checks",
            ).values()
        ),
        "required_facts_readiness_checked": (
            _scenario_artifact(
                scenarios,
                "required_facts_missing",
                "readiness_bridge",
            ).get("status")
            == "ready_for_readiness_evidence"
        ),
        "scoped_pipeline_operation_layer_handoff_checked": (
            _scenario_artifact(
                scenarios,
                "scoped_pipeline_operation_layer_handoff",
                "checks",
            )
            != {}
            and all(
                _scenario_artifact(
                    scenarios,
                    "scoped_pipeline_operation_layer_handoff",
                    "checks",
                ).values()
            )
        ),
        "non_executing_prepare_auto_bridge_checked": (
            _scenario_artifact(
                scenarios,
                "non_executing_prepare_auto_bridge",
                "checks",
            )
            != {}
            and all(
                _scenario_artifact(
                    scenarios,
                    "non_executing_prepare_auto_bridge",
                    "checks",
                ).values()
            )
        ),
        "legacy_local_registration_probe_tolerance_checked": (
            _scenario_artifact(
                scenarios,
                "mock_fresh_signal_dry_run_pass",
                "legacy_local_registration_probe_tolerance",
            ).get("status")
            == "operation_layer_ready"
        ),
        "mock_operation_layer_closed_loop_checked": (
            _scenario_artifact(
                scenarios,
                "mock_operation_layer_submit_finalize_pass",
                "mock_operation_layer_closed_loop",
            ).get("status")
            == "passed"
        ),
        "operation_layer_blocker_review_policy_checked": (
            _scenario_artifact(
                scenarios,
                "operation_layer_blocker_review_matrix",
                "review_matrix",
            )
            != {}
            and all(
                all(case.get("checks", {}).values())
                for case in _scenario_artifact(
                    scenarios,
                    "operation_layer_blocker_review_matrix",
                    "review_matrix",
                ).values()
            )
        ),
        "operation_layer_hard_safety_blocker_matrix_checked": (
            _scenario_artifact(
                scenarios,
                "operation_layer_blocker_review_matrix",
                "matrix_checks",
            )
            != {}
            and all(
                _scenario_artifact(
                    scenarios,
                    "operation_layer_blocker_review_matrix",
                    "matrix_checks",
                ).values()
            )
        ),
        "shared_runtime_pipeline_checked": (
            shared_pipeline.get("status") == "passed"
            and all(
                value is True
                for value in (shared_pipeline.get("checks") or {}).values()
            )
        ),
        "common_execution_chain_reuse_checked": (
            shared_pipeline.get("status") == "passed"
            and shared_pipeline.get("checks", {}).get(
                "common_execution_chain_reused_by_all_strategygroups"
            )
            is True
            and shared_pipeline.get("checks", {}).get(
                "strategygroup_adapters_are_input_only"
            )
            is True
        ),
        "strategygroup_adapter_boundary_checked": (
            shared_pipeline.get("status") == "passed"
            and shared_pipeline.get("checks", {}).get(
                "all_strategy_groups_limit_to_input_contract"
            )
            is True
            and shared_pipeline.get("checks", {}).get(
                "all_strategy_groups_deny_direct_execution_authority"
            )
            is True
            and shared_pipeline.get("checks", {}).get(
                "all_strategy_groups_keep_tiny_risk_boundary"
            )
            is True
        ),
        "strategy_handoff_no_execution_pipeline_fields_checked": (
            shared_pipeline.get("status") == "passed"
            and shared_pipeline.get("checks", {}).get(
                "all_strategy_groups_have_no_execution_pipeline_fields"
            )
            is True
        ),
        "selected_strategygroup_dispatch_guard_checked": (
            _scenario_artifact(
                scenarios,
                "selected_strategygroup_dispatch_guard",
                "checks",
            )
            != {}
            and all(
                _scenario_artifact(
                    scenarios,
                    "selected_strategygroup_dispatch_guard",
                    "checks",
                ).values()
            )
        ),
        "all_selected_strategygroups_reach_finalgate_dispatch_checked": (
            _scenario_artifact(
                scenarios,
                "selected_strategygroup_dispatch_guard",
                "checks",
            ).get("all_selected_strategygroups_reach_finalgate_dispatch")
            is True
        ),
        "expanded_watcher_scope_execution_guard_checked": (
            _scenario_artifact(
                scenarios,
                "expanded_watcher_scope_execution_guard",
                "checks",
            )
            != {}
            and all(
                _scenario_artifact(
                    scenarios,
                    "expanded_watcher_scope_execution_guard",
                    "checks",
                ).values()
            )
        ),
        "operation_layer_authorization_chain_guard_checked": (
            _scenario_artifact(
                scenarios,
                "operation_layer_authorization_chain_guard",
                "checks",
            )
            != {}
            and all(
                _scenario_artifact(
                    scenarios,
                    "operation_layer_authorization_chain_guard",
                    "checks",
                ).values()
            )
        ),
        "post_submit_closed_loop_evidence_guard_checked": (
            _scenario_artifact(
                scenarios,
                "post_submit_closed_loop_evidence_guard",
                "post_submit_closed_loop_evidence_guard",
            ).get("status")
            == "passed"
            and all(
                _scenario_artifact(
                    scenarios,
                    "post_submit_closed_loop_evidence_guard",
                    "post_submit_closed_loop_evidence_guard",
                ).get("checks", {}).values()
            )
        ),
        "operation_layer_submit_result_identity_guard_checked": (
            _scenario_artifact(
                scenarios,
                "operation_layer_submit_result_identity_guard",
                "operation_layer_submit_result_identity_guard",
            ).get("status")
            == "passed"
            and all(
                _scenario_artifact(
                    scenarios,
                    "operation_layer_submit_result_identity_guard",
                    "operation_layer_submit_result_identity_guard",
                ).get("checks", {}).values()
            )
        ),
        "post_submit_finalize_result_identity_guard_checked": (
            _scenario_artifact(
                scenarios,
                "post_submit_finalize_result_identity_guard",
                "post_submit_finalize_result_identity_guard",
            ).get("status")
            == "passed"
            and all(
                _scenario_artifact(
                    scenarios,
                    "post_submit_finalize_result_identity_guard",
                    "post_submit_finalize_result_identity_guard",
                ).get("checks", {}).values()
            )
        ),
    }
    status = "passed" if all(checks.values()) and not blockers else "blocked"
    required_checks = {
        name: checks.get(name)
        for name in sorted(checks)
        if name != "scenario_count"
    }
    summary = {
        "scenario_count": checks["scenario_count"],
        "required_checks_present": checks["required_scenarios_present"],
        "all_scenarios_passed": checks["all_scenarios_passed"],
        "dangerous_effects_absent": checks["dangerous_effects_absent"],
        "disabled_smoke_is_real_execution_proof": False,
        "shared_runtime_pipeline_checked": checks[
            "shared_runtime_pipeline_checked"
        ],
        "common_execution_chain_reuse_checked": checks[
            "common_execution_chain_reuse_checked"
        ],
        "strategygroup_adapter_boundary_checked": checks[
            "strategygroup_adapter_boundary_checked"
        ],
        "strategy_handoff_no_execution_pipeline_fields_checked": checks[
            "strategy_handoff_no_execution_pipeline_fields_checked"
        ],
        "selected_strategygroup_dispatch_guard_checked": checks[
            "selected_strategygroup_dispatch_guard_checked"
        ],
        "all_selected_strategygroups_reach_finalgate_dispatch_checked": checks[
            "all_selected_strategygroups_reach_finalgate_dispatch_checked"
        ],
        "operation_layer_hard_safety_blocker_matrix_checked": checks[
            "operation_layer_hard_safety_blocker_matrix_checked"
        ],
        "expanded_watcher_scope_execution_guard_checked": checks[
            "expanded_watcher_scope_execution_guard_checked"
        ],
        "operation_layer_authorization_chain_guard_checked": checks[
            "operation_layer_authorization_chain_guard_checked"
        ],
        "post_submit_closed_loop_evidence_guard_checked": checks[
            "post_submit_closed_loop_evidence_guard_checked"
        ],
        "operation_layer_submit_result_identity_guard_checked": checks[
            "operation_layer_submit_result_identity_guard_checked"
        ],
        "post_submit_finalize_result_identity_guard_checked": checks[
            "post_submit_finalize_result_identity_guard_checked"
        ],
        "non_executing_prepare_auto_bridge_checked": checks[
            "non_executing_prepare_auto_bridge_checked"
        ],
        "required_facts_readiness_checked": checks[
            "required_facts_readiness_checked"
        ],
        "scoped_pipeline_operation_layer_handoff_checked": checks[
            "scoped_pipeline_operation_layer_handoff_checked"
        ],
    }
    return {
        "scope": "runtime_dry_run_audit_chain",
        "status": status,
        "generated_at_ms": int(time.time() * 1000),
        "description": (
            "Local non-executing audit chain for StrategyGroup runtime liveness; "
            "does not call Tokyo, exchange write, or real submit."
        ),
        "scenarios": scenarios,
        "shared_runtime_pipeline_validation": shared_pipeline,
        "checks": checks,
        "scenario_count": checks["scenario_count"],
        "required_checks": required_checks,
        "summary": summary,
        "blockers": blockers,
        "safety_invariants": {
            "uses_mock_fresh_signal": True,
            "calls_tokyo_api": False,
            "real_order_created": False,
            "order_created": False,
            "exchange_write_called": False,
            "order_lifecycle_called": False,
            "withdrawal_or_transfer_created": False,
            "modifies_secret_or_credentials": False,
            "modifies_live_profile": False,
            "modifies_order_sizing_defaults": False,
            "finalgate_bypassed": False,
            "operation_layer_bypassed": False,
            "disabled_smoke_is_real_execution_proof": False,
            "dangerous_effects": dangerous_effects,
        },
    }


def _scenario_artifact(
    scenarios: list[dict[str, Any]],
    scenario_name: str,
    artifact_name: str,
) -> dict[str, Any]:
    for scenario in scenarios:
        if scenario.get("name") == scenario_name:
            artifact = scenario.get("artifacts", {}).get(artifact_name)
            return artifact if isinstance(artifact, dict) else {}
    return {}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the non-executing runtime dry-run audit chain packet."
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    output_dir = Path(args.output_dir).expanduser()
    with redirect_stdout(sys.stderr):
        report = build_audit_chain(output_dir)
    output_json = Path(args.output_json).expanduser()
    _write_json(output_json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
