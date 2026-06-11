#!/usr/bin/env python3
"""Local ready-signal rehearsal for observation API -> prepare bridge.

This verifier uses in-memory fakes only. It proves that a ready observation
payload can move through ``runtime_next_attempt_observation_api_prepare_flow``
into a prepare packet when explicitly enabled, while still never submitting
orders, calling OrderLifecycle, calling exchange APIs, or moving funds.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import runtime_next_attempt_observation_api_prepare_flow as bridge  # noqa: E402


def build_rehearsal_report() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="brc-ready-prepare-rehearsal-") as tmp:
        output_dir = Path(tmp)
        dry_args = _args(output_dir=output_dir, allow_prepare_records=False)
        dry_payload = bridge._build_packet(
            dry_args,
            client=_ReadyObservationClient(),
            prepare_runner=_prepare_runner_should_not_run,
        )
        allow_args = _args(output_dir=output_dir, allow_prepare_records=True)
        allow_payload = bridge._build_packet(
            allow_args,
            client=_ReadyObservationClient(),
            prepare_runner=_fake_prepare_runner,
        )

    forbidden_flags = _forbidden_flags(dry_payload, allow_payload)
    checks = {
        "ready_without_allow_stops_before_prepare": (
            dry_payload.get("status") == "ready_for_prepare"
            and dry_payload.get("prepare_packet") is None
            and dry_payload.get("safety_invariants", {}).get("prepare_records_created")
            is False
        ),
        "allow_prepare_reaches_final_gate_preflight": (
            allow_payload.get("status") == "ready_for_final_gate_preflight"
            and allow_payload.get("prepare_packet", {}).get("status")
            == "ready_for_final_gate_preflight"
        ),
        "prepared_authorization_id_present": bool(
            allow_payload.get("operator_command_plan", {}).get(
                "prepared_authorization_id"
            )
        ),
        "forbidden_execution_flags": forbidden_flags,
    }
    passed = (
        checks["ready_without_allow_stops_before_prepare"]
        and checks["allow_prepare_reaches_final_gate_preflight"]
        and checks["prepared_authorization_id_present"]
        and not forbidden_flags
    )
    return {
        "status": "rehearsal_passed" if passed else "blocked",
        "scope": "runtime_observation_api_prepare_ready_rehearsal",
        "checks": checks,
        "dry_run_payload": dry_payload,
        "allow_prepare_payload": allow_payload,
        "safety_invariants": {
            "local_in_memory_only": True,
            "database_connected": False,
            "http_network_called": False,
            "exchange_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "real_submit_authorized": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _args(*, output_dir: Path, allow_prepare_records: bool) -> argparse.Namespace:
    return argparse.Namespace(
        runtime_instance_id="rehearsal-runtime-ready",
        env_file=None,
        api_base="http://unit",
        source="sample",
        include_exchange=False,
        symbol=None,
        side=None,
        family=None,
        strategy_family_id=None,
        carrier_id=None,
        quantity=None,
        target_notional_usdt=None,
        max_notional=None,
        leverage=None,
        max_attempts=None,
        protection_mode=None,
        review_requirement=None,
        evaluation_id=None,
        playbook_id=None,
        one_hour_limit=25,
        four_hour_limit=25,
        timeout_seconds=10.0,
        signal_output_json=None,
        output_dir=str(output_dir),
        allow_prepare_records=allow_prepare_records,
        candidate_id="rehearsal-candidate-ready",
        context_id="rehearsal-context-ready",
        owner_operator_id="owner",
        owner_confirmation_reference="owner-authorized-ready-rehearsal",
        reason="local ready-signal prepare rehearsal",
        next_attempt_symbol="AVAX/USDT:USDT",
        next_attempt_side="short",
        next_attempt_family=None,
        next_attempt_strategy_family_id="BTPC-001",
        next_attempt_carrier_id="BTPC-001-v0",
    )


class _ReadyObservationClient:
    def request_json(self, method: str, path: str, *, query=None, body=None) -> dict[str, Any]:
        return {
            "http_status": 200,
            "body": {
                "status": "ready_for_prepare",
                "runtime_instance_id": "rehearsal-runtime-ready",
                "next_attempt_gate": {
                    "status": "clear_for_preflight",
                    "gate": "clear_for_next_preflight",
                    "next_attempt_allowed_by_lifecycle": True,
                },
                "just_in_time_lifecycle_audit": {
                    "can_continue_to_authorization": True,
                    "can_execute_live": False,
                },
                "signal_packet": {
                    "status": "ready_for_shadow_candidate_prepare",
                    "signal_input": {
                        "evaluation_id": "rehearsal-eval-ready",
                        "strategy_family_id": "BTPC-001",
                        "strategy_family_version_id": "BTPC-001-v0",
                        "symbol": "AVAX/USDT:USDT",
                        "timestamp_ms": 1781000000000,
                    },
                    "evaluation_result": {
                        "status": "ready_for_semantic_binding",
                        "blockers": [],
                        "warnings": [],
                    },
                },
                "blockers": [],
                "warnings": [],
                "operator_command_plan": {
                    "next_step": "run_official_runtime_next_attempt_prepare_api_flow",
                    "places_order": False,
                    "calls_order_lifecycle": False,
                },
                "safety_invariants": {
                    "exchange_write_called": False,
                    "order_created": False,
                    "order_lifecycle_called": False,
                },
            },
        }


def _prepare_runner_should_not_run(
    args: argparse.Namespace,
    signal_input_json: str,
) -> dict[str, Any]:
    raise AssertionError("prepare runner must not run without explicit allow")


def _fake_prepare_runner(
    args: argparse.Namespace,
    signal_input_json: str,
) -> dict[str, Any]:
    return {
        "scope": "runtime_next_attempt_prepare_packet",
        "status": "ready_for_final_gate_preflight",
        "ids": {
            "runtime_execution_intent_draft_id": "draft-ready-rehearsal",
            "execution_intent_id": "intent-ready-rehearsal",
            "authorization_id": "auth-ready-rehearsal",
            "protection_plan_id": "protection-ready-rehearsal",
        },
        "blockers": [],
        "warnings": [],
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
        "operator_command_plan": {
            "prepared_authorization_id": "auth-ready-rehearsal",
            "live_submit_allowed": False,
            "places_order": False,
            "calls_order_lifecycle": False,
        },
        "safety_invariants": {
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _forbidden_flags(*payloads: dict[str, Any]) -> list[str]:
    forbidden: list[str] = []
    for index, payload in enumerate(payloads):
        safety = payload.get("safety_invariants") or {}
        for key in (
            "exchange_write_called",
            "order_created",
            "order_lifecycle_called",
            "attempt_counter_mutated",
            "runtime_budget_mutated",
            "withdrawal_or_transfer_created",
        ):
            if safety.get(key) is not False:
                forbidden.append(f"payload_{index}.{key}")
        prepare = payload.get("prepare_packet") or {}
        prepare_safety = prepare.get("safety_invariants") or {}
        for key in (
            "exchange_write_called",
            "order_created",
            "order_lifecycle_called",
            "attempt_counter_mutated",
            "runtime_budget_mutated",
            "withdrawal_or_transfer_created",
        ):
            if prepare_safety.get(key) is True:
                forbidden.append(f"payload_{index}.prepare.{key}")
    return forbidden


def main() -> int:
    report = build_rehearsal_report()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if report["status"] == "rehearsal_passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
