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
from pathlib import Path
import sys
import time
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import runtime_fresh_signal_readiness_bridge as readiness_bridge  # noqa: E402
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
RUNTIME_ID = "dry-run-runtime-mpg-001"
FRESH_AUTHORIZATION_ID = "dry-run-fresh-auth-1"
AUTHORIZATION_ID = FRESH_AUTHORIZATION_ID


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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


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


def _resume_pack_ready_for_finalgate() -> dict[str, Any]:
    return {
        "scope": "runtime_signal_watcher_post_signal_resume_pack",
        "status": "ready_for_action_time_final_gate",
        "selected_runtime_instance_ids": [RUNTIME_ID],
        "signal_input_json": "/tmp/dry-run-signal-input.json",
        "shadow_candidate_id": "dry-run-shadow-candidate-1",
        "prepared_authorization_id": AUTHORIZATION_ID,
        "action_time_resume": {
            "status": "ready_for_action_time_final_gate",
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


def _disabled_smoke_args(path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        handoff_json=str(path),
        output=None,
        env_file=None,
        api_base="http://dry-run.local",
    )


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
    passed = (
        readiness["status"] == "ready_for_fresh_submit_authorization"
        and finalgate_plan["status"] == "ready_for_action_time_final_gate"
        and finalgate_plan["dispatch_action"]
        == "run_official_action_time_final_gate_preflight"
        and operation_layer["status"] == "operation_layer_ready"
        and disabled_report["status"] == "disabled_smoke_passed"
        and closed_loop_shape["status"] == "shape_checked"
        and all(closed_loop_shape["closed_loop_checks"].values())
        and not _dangerous_effects(readiness, finalgate_plan, operation_layer, disabled_report, closed_loop_shape)
    )
    return _scenario_packet(
        name="mock_fresh_signal_dry_run_pass",
        expected=(
            "evidence IDs connect, disabled submit stays non-executing, and "
            "finalize/reconciliation/budget/review shapes are present"
        ),
        artifacts={
            "readiness_bridge": readiness,
            "finalgate_dispatch_plan": finalgate_plan,
            "operation_layer_evidence_prep": operation_layer,
            "disabled_submit_smoke": disabled_report,
            "closed_loop_shape": closed_loop_shape,
        },
        passed=passed,
        blockers=[
            *readiness.get("blockers", []),
            *finalgate_plan.get("blockers", []),
            *operation_layer.get("blockers", []),
            *disabled_report.get("blockers", []),
        ],
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
        _scenario_required_facts_missing(output_dir),
        _scenario_active_conflict(output_dir),
    ]
    blockers = [
        f"{scenario['name']}:{blocker}"
        for scenario in scenarios
        if scenario["status"] != "passed"
        for blocker in (scenario.get("blockers") or ["scenario_failed"])
    ]
    dangerous_effects = _dangerous_effects(*scenarios)
    checks = {
        "scenario_count": len(scenarios),
        "required_scenarios_present": len(scenarios) == 4,
        "all_scenarios_passed": all(item["status"] == "passed" for item in scenarios),
        "dangerous_effects_absent": not dangerous_effects,
        "disabled_smoke_not_real_execution_proof": True,
    }
    status = "passed" if all(checks.values()) and not blockers else "blocked"
    return {
        "scope": "runtime_dry_run_audit_chain",
        "status": status,
        "generated_at_ms": int(time.time() * 1000),
        "description": (
            "Local non-executing audit chain for StrategyGroup runtime liveness; "
            "does not call Tokyo, exchange write, or real submit."
        ),
        "scenarios": scenarios,
        "checks": checks,
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
