#!/usr/bin/env python3
"""Build a local ready-signal readiness fixture for RTF-058.

The fixture proves the ready path that the live runtime will use when a fresh
runtime-compatible signal appears:

fresh-signal loop ready packet
-> RTF-057 readiness bridge
-> strategy planning ready
-> executable readiness / handoff preview ready

It uses fixture builders instead of a server so the proof is repeatable locally.
It does not call a server, create live records, arm local registration, arm
exchange submit, call OrderLifecycle, submit orders, or move funds.
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

from scripts import runtime_fresh_signal_readiness_bridge as bridge  # noqa: E402


READY_FOR_FRESH_SUBMIT_AUTHORIZATION = "ready_for_fresh_submit_authorization"
READY_FOR_OFFICIAL_SUBMIT_CALL = "ready_for_official_submit_call"
READY_FOR_FINAL_GATE_PREFLIGHT = "ready_for_final_gate_preflight"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _read_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _fixture_paths(root: Path) -> dict[str, Path]:
    return {
        "fresh_loop": root / "00-fresh-signal-loop-ready.json",
        "signal_input": root / "00-signal-input-ready.json",
        "evidence": root / "00-readiness-evidence.json",
        "bridge_output": root / "01-fresh-signal-readiness-bridge.json",
    }


def _signal_input(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "evaluation_id": "signal-rtf058-ready",
        "strategy_family_id": args.strategy_family_id,
        "strategy_family_version_id": args.strategy_family_version_id,
        "symbol": args.symbol,
        "side": args.side,
        "timestamp_ms": 1781300000000,
        "primary_timeframe": "1h",
        "context_timeframes": ["4h"],
        "freshness": "fresh_fixture_signal",
        "market_snapshot": {
            "symbol": args.symbol,
            "timestamp_ms": 1781300000000,
            "source": "rtf058_fixture",
            "freshness": "fresh",
        },
        "account_facts_snapshot": {
            "source": "rtf058_fixture",
            "truth_level": "trusted_fixture",
            "timestamp_ms": 1781300000000,
            "freshness": "fresh",
            "position_count": 0,
            "open_order_count": 0,
        },
    }


def _post_submit_packet(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "packet_id": "runtime-post-submit-finalize-rtf058",
        "authorization_id": "consumed-submit-auth-rtf058",
        "runtime_instance_id": args.runtime_instance_id,
        "status": "finalized_ready_for_next_attempt",
        "next_attempt_gate": {
            "runtime_instance_id": args.runtime_instance_id,
            "status": "ready_for_fresh_signal",
            "attempts_remaining": 2,
            "budget_remaining": "6.00",
            "active_positions_count": 0,
            "max_active_positions": 1,
            "requires_fresh_strategy_signal": True,
            "requires_fresh_authorization": True,
            "consumed_authorization_replay_only": True,
            "pre_submit_rehearsal_retry_allowed": False,
            "blockers": [],
            "warnings": [],
        },
        "consumed_authorization_replay_only": True,
        "old_authorization_submit_retry_allowed": False,
        "pre_submit_rehearsal_retry_allowed": False,
        "local_created_order_requirement_retired": True,
        "blockers": [],
        "warnings": [],
        "not_execution_authority": True,
        "runtime_state_mutated_by_packet": False,
        "execution_intent_created": False,
        "order_created": False,
        "exchange_called": False,
        "exchange_order_submitted": False,
        "order_lifecycle_called": False,
        "withdrawal_or_transfer_created": False,
    }


def _fresh_loop_packet(
    args: argparse.Namespace,
    *,
    signal_input_json: Path,
) -> dict[str, Any]:
    post_submit = _post_submit_packet(args)
    return {
        "scope": "runtime_fresh_signal_prepare_loop",
        "status": READY_FOR_FINAL_GATE_PREFLIGHT,
        "runtime_instance_id": args.runtime_instance_id,
        "post_submit_finalize_flow": {
            "scope": "runtime_post_submit_finalize_api_flow",
            "status": "finalized_ready_for_next_attempt",
            "post_submit_finalize_packet": post_submit,
            "api_payload": post_submit,
            "blockers": [],
            "warnings": [],
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
            },
        },
        "observation_prepare_flow": {
            "scope": "runtime_next_attempt_observation_api_prepare_flow",
            "status": READY_FOR_FINAL_GATE_PREFLIGHT,
            "signal_input_json": str(signal_input_json),
            "prepare_packet": {
                "status": READY_FOR_FINAL_GATE_PREFLIGHT,
                "ids": {
                    "authorization_id": "prepared-submit-auth-rtf058",
                    "execution_intent_id": "intent-rtf058",
                    "runtime_execution_intent_draft_id": "draft-rtf058",
                    "protection_plan_id": "protection-rtf058",
                },
                "operator_command_plan": {
                    "prepared_authorization_id": "prepared-submit-auth-rtf058",
                    "not_executed": True,
                    "places_order": False,
                    "calls_order_lifecycle": False,
                },
                "created_records": {
                    "shadow_candidate_created": True,
                    "runtime_execution_intent_draft_created": True,
                    "execution_intent_created": True,
                    "submit_authorization_created": True,
                    "protection_plan_created": True,
                },
            },
            "blockers": [],
            "warnings": [],
            "operator_command_plan": {
                "prepared_authorization_id": "prepared-submit-auth-rtf058",
                "creates_shadow_candidate": True,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "safety_invariants": {
                "allow_prepare_records": True,
                "prepare_records_created": True,
                "shadow_candidate_created": True,
                "runtime_execution_intent_draft_created": True,
                "recorded_execution_intent_created": True,
                "submit_authorization_created": True,
                "protection_plan_created": True,
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "withdrawal_or_transfer_created": False,
            },
        },
        "signal_input_json": str(signal_input_json),
        "prepared_authorization_id": "prepared-submit-auth-rtf058",
        "blockers": [],
        "warnings": ["rtf058_ready_signal_fixture"],
        "operator_command_plan": {
            "next_step": "run_official_final_gate_preflight",
            "creates_shadow_candidate": True,
            "creates_execution_intent": False,
            "creates_executable_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "requires_official_final_gate": True,
            "requires_fresh_authorization_before_submit": True,
        },
        "safety_invariants": {
            "uses_official_trading_console_api": False,
            "post_submit_finalize_required_first": True,
            "prepare_records_created": True,
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _readiness_evidence(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "final_gate_preview_id": "final-gate-preview-rtf058",
        "final_gate_passed": True,
        "runtime_grant_authorization_id": args.runtime_grant_authorization_id,
        "trusted_submit_fact_snapshot_id": "trusted-facts-rtf058",
        "submit_idempotency_policy_id": "idem-rtf058",
        "attempt_outcome_policy_id": "attempt-policy-rtf058",
        "protection_creation_failure_policy_id": "protect-policy-rtf058",
        "local_registration_enablement_decision_id": "local-enable-rtf058",
        "exchange_submit_enablement_decision_id": "exchange-enable-rtf058",
        "exchange_submit_action_authorization_id": "exchange-action-auth-rtf058",
        "order_lifecycle_submit_enablement_id": "ol-enable-rtf058",
        "exchange_submit_adapter_enablement_id": "exchange-adapter-enable-rtf058",
        "deployment_readiness_evidence_id": "deploy-ready-rtf058",
        "protection_required_and_ready": True,
        "active_position_source_trusted": True,
        "account_facts_fresh": True,
        "duplicate_submit_guard_ready": True,
    }


def _planning_packet(args: argparse.Namespace, planning_args: argparse.Namespace) -> dict[str, Any]:
    signal = _read_json(planning_args.signal_input_json)
    post_submit = _read_json(planning_args.post_submit_finalize_packet_json)
    strategy = {
        "packet_id": "strategy-plan-rtf058",
        "runtime_instance_id": args.runtime_instance_id,
        "source_authorization_id": post_submit.get("authorization_id"),
        "post_submit_finalize_packet_id": post_submit.get("packet_id"),
        "status": READY_FOR_FINAL_GATE_PREFLIGHT,
        "next_attempt_gate_status": "ready_for_fresh_signal",
        "signal_evaluation_id": signal.get("evaluation_id"),
        "strategy_family_id": signal.get("strategy_family_id"),
        "strategy_family_version_id": signal.get("strategy_family_version_id"),
        "symbol": signal.get("symbol"),
        "order_candidate_id": "order-candidate-rtf058",
        "blockers": [],
        "warnings": ["rtf058_fixture_strategy_planning"],
        "operator_command_plan": {
            "next_step": "run_executable_submit_readiness",
            "creates_shadow_candidate": True,
            "creates_executable_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "requires_fresh_authorization_before_submit": True,
        },
        "consumed_authorization_replay_only": True,
        "requires_fresh_strategy_signal": True,
        "requires_fresh_authorization_before_submit": True,
        "old_authorization_submit_retry_allowed": False,
        "pre_submit_rehearsal_retry_allowed": False,
        "execution_intent_created": False,
        "executable_execution_intent_created": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "exchange_called": False,
        "exchange_order_submitted": False,
        "runtime_state_mutated": False,
        "withdrawal_or_transfer_created": False,
        "metadata": {
            "source": "runtime_fresh_signal_readiness_fixture",
            "rtf058_ready_signal_fixture": True,
            "non_executing": True,
        },
    }
    return {
        "scope": "runtime_next_attempt_strategy_plan_api_flow",
        "status": READY_FOR_FINAL_GATE_PREFLIGHT,
        "runtime_instance_id": args.runtime_instance_id,
        "http_status": 200,
        "api_payload": strategy,
        "blockers": [],
        "warnings": ["rtf058_fixture_planning_flow"],
        "safety_invariants": {
            "uses_fake_api_client": True,
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _handoff_packet(
    args: argparse.Namespace,
    handoff_args: argparse.Namespace,
) -> dict[str, Any]:
    cycle = _read_json(handoff_args.cycle_packet_json)
    strategy_flow = cycle.get("next_attempt_strategy_plan_flow")
    if not isinstance(strategy_flow, dict):
        strategy_flow = {}
    status = (
        READY_FOR_OFFICIAL_SUBMIT_CALL
        if args.include_fresh_submit_authorization
        else READY_FOR_FRESH_SUBMIT_AUTHORIZATION
    )
    return {
        "scope": "runtime_cycle_executable_submit_handoff",
        "status": status,
        "blocked_stage": None,
        "runtime_instance_id": args.runtime_instance_id,
        "cycle_packet": cycle,
        "executable_readiness_flow": {
            "status": "ready_for_executable_submit",
            "api_payload": {
                "packet_id": "readiness-rtf058",
                "runtime_instance_id": args.runtime_instance_id,
                "source_strategy_planning_packet_id": (
                    (strategy_flow.get("api_payload") or {}).get("packet_id")
                ),
                "source_authorization_id": "consumed-submit-auth-rtf058",
                "status": "ready_for_executable_submit",
                "executable_submit_ready": True,
                "blockers": [],
                "warnings": [],
            },
            "blockers": [],
            "warnings": ["rtf058_fixture_readiness_flow"],
        },
        "official_submit_handoff_flow": {
            "status": READY_FOR_OFFICIAL_SUBMIT_CALL,
            "blockers": [],
            "warnings": ["rtf058_fixture_handoff_flow"],
        }
        if args.include_fresh_submit_authorization
        else None,
        "blockers": [],
        "warnings": ["rtf058_fixture_handoff_bridge"],
        "operator_action_preview": {
            "ready_for_call": args.include_fresh_submit_authorization,
            "mode": "disabled_smoke",
        }
        if args.include_fresh_submit_authorization
        else None,
        "operator_command_plan": {
            "next_step": (
                "call_official_submit_endpoint_after_action_time_final_gate_and_operation_layer_pass"
                if args.include_fresh_submit_authorization
                else "bind_or_resolve_fresh_submit_authorization"
            ),
            "calls_official_submit_endpoint": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "requires_fresh_submit_authorization": (
                not args.include_fresh_submit_authorization
            ),
            "requires_owner_chat_confirmation": False,
            "uses_standing_runtime_authorization": args.include_fresh_submit_authorization,
            "requires_action_time_final_gate": args.include_fresh_submit_authorization,
            "requires_official_operation_layer": args.include_fresh_submit_authorization,
            "can_continue_without_owner_chat": args.include_fresh_submit_authorization,
            "requires_action_time_confirmation": False,
        },
        "safety_invariants": {
            "uses_fake_api_client": True,
            "calls_official_submit_endpoint": False,
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _bridge_args(
    args: argparse.Namespace,
    *,
    paths: dict[str, Path],
    bridge_output_dir: Path,
) -> argparse.Namespace:
    return argparse.Namespace(
        runtime_instance_id=args.runtime_instance_id,
        fresh_signal_loop_json=str(paths["fresh_loop"]),
        evidence_json=str(paths["evidence"]),
        first_real_submit_packet_json=None,
        fresh_submit_authorization_id=(
            "fresh-submit-auth-rtf058"
            if args.include_fresh_submit_authorization
            else None
        ),
        mode="disabled_smoke",
        owner_confirmed_for_real_submit_action=False,
        readiness_warning=None,
        readiness_blocker=None,
        handoff_warning=None,
        handoff_blocker=None,
        env_file=None,
        api_base=args.api_base,
        context_id="context-rtf058",
        expires_at_ms=None,
        metadata_json=json.dumps(
            {
                "runtime_fresh_signal_readiness_fixture": True,
                "rtf058_ready_signal_path": True,
            },
            ensure_ascii=False,
        ),
        output_dir=str(bridge_output_dir),
        flow_id="rtf058-ready-signal",
    )


def _build_report(args: argparse.Namespace) -> dict[str, Any]:
    artifact_dir = Path(args.artifact_dir).expanduser()
    fixture_dir = artifact_dir / "fixture-inputs"
    bridge_dir = artifact_dir / "bridge"
    paths = _fixture_paths(fixture_dir)
    _write_json(paths["signal_input"], _signal_input(args))
    _write_json(
        paths["fresh_loop"],
        _fresh_loop_packet(args, signal_input_json=paths["signal_input"]),
    )
    _write_json(paths["evidence"], _readiness_evidence(args))

    planning_calls: list[dict[str, Any]] = []
    handoff_calls: list[dict[str, Any]] = []

    def planning_builder(planning_args: argparse.Namespace) -> dict[str, Any]:
        planning_calls.append(
            {
                "signal_input_json": planning_args.signal_input_json,
                "post_submit_finalize_packet_json": (
                    planning_args.post_submit_finalize_packet_json
                ),
            }
        )
        return _planning_packet(args, planning_args)

    def handoff_builder(handoff_args: argparse.Namespace) -> dict[str, Any]:
        handoff_calls.append(
            {
                "cycle_packet_json": handoff_args.cycle_packet_json,
                "evidence_json": handoff_args.evidence_json,
                "fresh_submit_authorization_id": (
                    handoff_args.fresh_submit_authorization_id
                ),
            }
        )
        return _handoff_packet(args, handoff_args)

    bridge_packet = bridge._build_packet(
        _bridge_args(args, paths=paths, bridge_output_dir=bridge_dir),
        planning_builder=planning_builder,
        handoff_builder=handoff_builder,
    )
    _write_json(paths["bridge_output"], bridge_packet)
    bridge_status = str(bridge_packet.get("status") or "")
    report = {
        "scope": "runtime_fresh_signal_readiness_fixture",
        "status": (
            "ready_fresh_signal_readiness_fixture"
            if bridge_status
            in {READY_FOR_FRESH_SUBMIT_AUTHORIZATION, READY_FOR_OFFICIAL_SUBMIT_CALL}
            else "blocked_fresh_signal_readiness_fixture"
        ),
        "runtime_instance_id": args.runtime_instance_id,
        "bridge_status": bridge_status,
        "artifact_dir": str(artifact_dir),
        "fixture_files": {key: str(value) for key, value in paths.items()},
        "bridge_packet": bridge_packet,
        "planning_call_count": len(planning_calls),
        "handoff_call_count": len(handoff_calls),
        "planning_calls": planning_calls,
        "handoff_calls": handoff_calls,
        "blockers": list(bridge_packet.get("blockers") or []),
        "warnings": list(bridge_packet.get("warnings") or []),
        "safety_invariants": {
            "uses_fake_api_builders": True,
            "does_not_call_server": True,
            "does_not_call_official_submit_endpoint": True,
            "does_not_arm_local_registration": True,
            "does_not_arm_exchange_submit": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
            "does_not_create_order": True,
            "does_not_mutate_runtime_budget": True,
            "does_not_open_or_close_position": True,
            "does_not_create_withdrawal_or_transfer": True,
            "bridge_exchange_write_called": bool(
                bridge_packet.get("safety_invariants", {}).get("exchange_write_called")
            ),
            "bridge_order_created": bool(
                bridge_packet.get("safety_invariants", {}).get("order_created")
            ),
            "bridge_order_lifecycle_called": bool(
                bridge_packet.get("safety_invariants", {}).get("order_lifecycle_called")
            ),
        },
        "created_at_ms": int(time.time() * 1000),
    }
    if args.output:
        _write_json(Path(args.output).expanduser(), report)
    return report


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a local RTF-058 ready-signal readiness fixture.",
    )
    parser.add_argument("--runtime-instance-id", default="runtime-rtf058")
    parser.add_argument("--runtime-grant-authorization-id", default="grant-rtf058")
    parser.add_argument("--strategy-family-id", default="BTPC-001")
    parser.add_argument("--strategy-family-version-id", default="BTPC-001-v0")
    parser.add_argument("--symbol", default="AVAX/USDT:USDT")
    parser.add_argument("--side", default="short")
    parser.add_argument("--api-base", default="http://fixture")
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--include-fresh-submit-authorization", action="store_true")
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
