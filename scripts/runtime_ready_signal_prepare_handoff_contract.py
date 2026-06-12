#!/usr/bin/env python3
"""Contract proof for ready shadow candidate -> prepare / FinalGate preflight.

RTF-077 composes the RTF-075 ready-signal shadow planning fixture with the
official next-attempt prepare wrapper.  The contract uses a fake Console API
client so it can prove the handoff shape locally before Tokyo integration
without writing PG, calling OrderLifecycle, submitting orders, or touching an
exchange.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import runtime_next_attempt_prepare_api_flow as prepare_flow  # noqa: E402
from scripts import runtime_ready_signal_shadow_planning_contract_fixture as shadow_fixture  # noqa: E402
from scripts.runtime_first_real_submit_api_flow import (  # noqa: E402
    FirstRealSubmitApiFlow,
)


def build_contract_report(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    shadow_dir = output_dir / "shadow-planning"
    shadow_report = shadow_fixture.build_contract_fixture_report(shadow_dir)
    _write_json(output_dir / "shadow-contract-report.json", shadow_report)

    candidate = _candidate_snapshot(shadow_report)
    prepare_report = _run_prepare_contract(
        order_candidate_id=str(shadow_report.get("order_candidate_id") or ""),
        candidate=candidate,
    )
    prepare_packet = prepare_flow._summarize_prepare_report(prepare_report)
    _write_json(output_dir / "prepare-packet.json", prepare_packet)

    report = _report(
        shadow_report=shadow_report,
        prepare_report=prepare_report,
        prepare_packet=prepare_packet,
    )
    _write_json(output_dir / "contract-report.json", report)
    return report


def _run_prepare_contract(
    *,
    order_candidate_id: str,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    args = argparse.Namespace(
        api_base="fake://rtf077-local-contract",
        mode="prepare",
        order_candidate_id=order_candidate_id,
        signal_input_json=None,
        runtime_instance_id=candidate.get("runtime_instance_id"),
        candidate_id=None,
        context_id="context-rtf077-prepare-handoff",
        owner_operator_id="owner",
        owner_confirmation_reference="owner-reviewed-rtf077-prepare-handoff",
        reason="RTF-077 local ready-signal prepare handoff contract",
        next_attempt_symbol=candidate.get("symbol"),
        next_attempt_side=candidate.get("side"),
        next_attempt_family=None,
        next_attempt_strategy_family_id=candidate.get("strategy_family_id"),
        next_attempt_carrier_id=candidate.get("strategy_family_version_id"),
    )
    config = prepare_flow._build_flow_config(args)
    return FirstRealSubmitApiFlow(
        client=_FakePrepareApiClient(candidate=candidate),
        config=config,
    ).run()


class _FakePrepareApiClient:
    def __init__(self, *, candidate: dict[str, Any]) -> None:
        self.candidate = candidate
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
                "query": query or {},
                "body": body or {},
            }
        )
        candidate_id = str(self.candidate.get("order_candidate_id") or "")
        if method == "GET" and path == "/api/trading-console/owner-action-flow":
            return _ok(
                {
                    "status": "ok",
                    "post_action_state": {
                        "next_attempt_gate": {
                            "status": "clear_for_preflight",
                            "gate": "clear_for_next_preflight",
                            "runtime_instance_id": self.candidate.get(
                                "runtime_instance_id"
                            ),
                            "next_attempt_allowed_by_lifecycle": True,
                            "attempts_remaining": 2,
                            "budget_remaining": "9",
                            "active_positions_count": 0,
                            "max_active_positions": 1,
                            "requires_fresh_strategy_signal": True,
                            "requires_fresh_authorization": True,
                            "blockers": [],
                            "warnings": [],
                        }
                    },
                    "blockers": [],
                    "warnings": [],
                }
            )
        if method == "GET" and path == f"/api/trading-console/order-candidates/{candidate_id}":
            return _ok(
                {
                    "status": "ok",
                    "order_candidate_id": candidate_id,
                    "candidate_reusable_for_new_attempt": True,
                    "candidate_usage_status": "unused_for_submit",
                    "reuse_blocker": None,
                    "blockers": [],
                    "warnings": [],
                }
            )
        if (
            method == "POST"
            and path
            == (
                "/api/trading-console/"
                f"runtime-execution-intent-drafts/order-candidates/{candidate_id}"
            )
        ):
            return _ok(
                {
                    "status": "draft_recorded",
                    "draft_id": "draft-rtf077-prepare-handoff",
                    "order_candidate_id": candidate_id,
                    "blockers": [],
                    "warnings": [],
                }
            )
        if (
            method == "POST"
            and path
            == (
                "/api/trading-console/"
                "runtime-execution-intents/drafts/draft-rtf077-prepare-handoff"
            )
        ):
            return _ok(
                {
                    "status": "execution_intent_recorded",
                    "id": "intent-rtf077-prepare-handoff",
                    "runtime_execution_intent_draft_id": (
                        "draft-rtf077-prepare-handoff"
                    ),
                    "blockers": [],
                    "warnings": [],
                }
            )
        if (
            method == "POST"
            and path
            == (
                "/api/trading-console/"
                "runtime-execution-protection-plans/intents/"
                "intent-rtf077-prepare-handoff"
            )
        ):
            return _ok(
                {
                    "status": "protection_plan_recorded",
                    "protection_plan_id": "protection-rtf077-prepare-handoff",
                    "blockers": [],
                    "warnings": [],
                }
            )
        if (
            method == "POST"
            and path
            == (
                "/api/trading-console/"
                "runtime-execution-submit-authorizations/intents/"
                "intent-rtf077-prepare-handoff"
            )
        ):
            return _ok(
                {
                    "status": "submit_authorization_recorded",
                    "authorization_id": "auth-rtf077-prepare-handoff",
                    "blockers": [],
                    "warnings": [],
                }
            )
        if (
            method == "POST"
            and path
            == (
                "/api/trading-console/"
                "runtime-execution-first-real-submit-evidence-preparations/"
                "authorizations/auth-rtf077-prepare-handoff"
            )
        ):
            return _ok(
                {
                    "status": "machine_evidence_prepared",
                    "prepared_evidence_ids": {
                        "trusted_submit_fact_snapshot_id": (
                            "trusted-submit-facts-rtf077"
                        ),
                        "submit_idempotency_policy_id": (
                            "submit-idempotency-rtf077"
                        ),
                        "protection_creation_failure_policy_id": (
                            "protection-failure-policy-rtf077"
                        ),
                    },
                    "available_evidence_ids": {},
                    "blockers": [],
                    "warnings": [],
                }
            )
        return {
            "http_status": 404,
            "body": {
                "status": "not_found",
                "detail": f"unexpected_fake_prepare_api_call:{method}:{path}",
                "blockers": [f"unexpected_fake_prepare_api_call:{method}:{path}"],
                "warnings": [],
            },
            "error": True,
        }


def _report(
    *,
    shadow_report: dict[str, Any],
    prepare_report: dict[str, Any],
    prepare_packet: dict[str, Any],
) -> dict[str, Any]:
    checks = _checks(
        shadow_report=shadow_report,
        prepare_report=prepare_report,
        prepare_packet=prepare_packet,
    )
    candidate = _candidate_snapshot(shadow_report)
    return {
        "scope": "runtime_ready_signal_prepare_handoff_contract",
        "status": (
            "ready_signal_prepare_handoff_contract_passed"
            if _contract_passed(checks)
            else "blocked"
        ),
        "runtime_instance_id": candidate.get("runtime_instance_id"),
        "order_candidate_id": shadow_report.get("order_candidate_id"),
        "signal_evaluation_id": shadow_report.get("signal_evaluation_id"),
        "prepared_authorization_id": (
            (prepare_packet.get("operator_command_plan") or {}).get(
                "prepared_authorization_id"
            )
        ),
        "runtime_execution_intent_draft_id": (
            (prepare_packet.get("ids") or {}).get("runtime_execution_intent_draft_id")
        ),
        "execution_intent_id": (prepare_packet.get("ids") or {}).get(
            "execution_intent_id"
        ),
        "protection_plan_id": (prepare_packet.get("ids") or {}).get(
            "protection_plan_id"
        ),
        "proposal": shadow_report.get("proposal"),
        "shadow_contract": shadow_report,
        "prepare_packet": prepare_packet,
        "first_real_submit_prepare_report": prepare_report,
        "checks": checks,
        "blockers": _dedupe(
            list(shadow_report.get("blockers") or [])
            + list(prepare_packet.get("blockers") or [])
        ),
        "warnings": _dedupe(
            list(shadow_report.get("warnings") or [])
            + list(prepare_packet.get("warnings") or [])
        ),
        "operator_command_plan": {
            "next_step": (
                "run_official_final_gate_preflight"
                if _contract_passed(checks)
                else "resolve_ready_signal_prepare_handoff_blockers"
            ),
            "uses_official_prepare_wrapper": True,
            "uses_fake_console_api": True,
            "records_prepare_governance_shape_only": True,
            "live_submit_allowed": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "executes_real_submit": False,
        },
        "right_tail_objective_context": {
            "small_bounded_losses_allowed_after_runtime_gate": True,
            "right_tail_runner_preserved": checks["right_tail_runner_preserved"],
            "automatic_compounding_assumed": False,
            "automatic_withdrawal_assumed": False,
            "not_proven_alpha": True,
        },
        "safety_invariants": {
            "local_contract_only": True,
            "uses_fake_console_api": True,
            "pg_written": False,
            "uses_live_exchange": False,
            "runtime_execution_intent_draft_shape_created": checks[
                "runtime_execution_intent_draft_created"
            ],
            "execution_intent_shape_created": checks["execution_intent_created"],
            "submit_authorization_shape_created": checks[
                "submit_authorization_created"
            ],
            "local_registration_armed": False,
            "exchange_submit_armed": False,
            "execute_real_submit": False,
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "position_opened": False,
            "position_closed": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _checks(
    *,
    shadow_report: dict[str, Any],
    prepare_report: dict[str, Any],
    prepare_packet: dict[str, Any],
) -> dict[str, bool]:
    shadow_checks = shadow_report.get("checks") or {}
    prepare_records = prepare_packet.get("created_records") or {}
    prepare_safety = prepare_packet.get("safety_invariants") or {}
    ids = prepare_packet.get("ids") or {}
    steps = [
        str(item.get("name") or "")
        for item in prepare_report.get("steps") or []
        if isinstance(item, dict)
    ]
    return {
        "shadow_contract_passed": (
            shadow_report.get("status")
            == "ready_signal_shadow_planning_contract_passed"
        ),
        "shadow_candidate_created": bool(
            shadow_checks.get("shadow_order_candidate_created")
        ),
        "right_tail_runner_preserved": bool(
            shadow_checks.get("right_tail_runner_preserved")
        ),
        "prepare_ready_for_final_gate_preflight": (
            prepare_packet.get("status") == "ready_for_final_gate_preflight"
        ),
        "next_attempt_gate_checked": bool(
            prepare_safety.get("next_attempt_gate_checked")
        ),
        "order_candidate_usage_checked": "verify_order_candidate_usage" in steps,
        "runtime_execution_intent_draft_created": bool(
            prepare_records.get("runtime_execution_intent_draft_created")
        ),
        "execution_intent_created": bool(
            prepare_records.get("execution_intent_created")
        ),
        "protection_plan_created": bool(
            prepare_records.get("protection_plan_created")
        ),
        "submit_authorization_created": bool(
            prepare_records.get("submit_authorization_created")
        ),
        "prepared_authorization_id_present": bool(ids.get("authorization_id")),
        "places_order": bool(prepare_safety.get("order_created")),
        "calls_order_lifecycle": bool(prepare_safety.get("order_lifecycle_called")),
        "exchange_write_called": bool(prepare_safety.get("exchange_write_called")),
        "attempt_counter_mutated": bool(prepare_safety.get("attempt_counter_mutated")),
        "runtime_budget_mutated": bool(prepare_safety.get("runtime_budget_mutated")),
        "withdrawal_or_transfer_created": bool(
            prepare_safety.get("withdrawal_or_transfer_created")
        ),
    }


def _contract_passed(checks: dict[str, bool]) -> bool:
    required_true = (
        "shadow_contract_passed",
        "shadow_candidate_created",
        "right_tail_runner_preserved",
        "prepare_ready_for_final_gate_preflight",
        "next_attempt_gate_checked",
        "order_candidate_usage_checked",
        "runtime_execution_intent_draft_created",
        "execution_intent_created",
        "protection_plan_created",
        "submit_authorization_created",
        "prepared_authorization_id_present",
    )
    required_false = (
        "places_order",
        "calls_order_lifecycle",
        "exchange_write_called",
        "attempt_counter_mutated",
        "runtime_budget_mutated",
        "withdrawal_or_transfer_created",
    )
    return all(checks.get(key) is True for key in required_true) and all(
        checks.get(key) is False for key in required_false
    )


def _candidate_snapshot(shadow_report: dict[str, Any]) -> dict[str, Any]:
    candidate = shadow_report.get("candidate_snapshot")
    if not isinstance(candidate, dict):
        raise ValueError("shadow_candidate_snapshot_missing")
    return candidate


def _ok(body: dict[str, Any]) -> dict[str, Any]:
    return {"http_status": 200, "body": body}


def _dedupe(items: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a local contract proof for ready shadow candidate to "
            "prepare / FinalGate preflight handoff."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default="output/rtf077-ready-signal-prepare-handoff-contract",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_contract_report(Path(args.output_dir).expanduser())
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return (
        0
        if report["status"] == "ready_signal_prepare_handoff_contract_passed"
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
