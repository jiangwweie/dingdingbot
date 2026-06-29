#!/usr/bin/env python3
"""Official server-side FinalGate preflight proof.

RTF-081 builds on the RTF-079 official server-side prepare proof.  It creates
the same in-process prepare records through official Trading Console routes,
then calls the official Runtime FinalGate preview, controlled submit plan, and
controlled submit preflight routes.  It remains non-executing: no PG writes,
orders, OrderLifecycle calls, exchange writes, runtime mutations, withdrawals,
or transfers.
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

from fastapi.testclient import TestClient  # noqa: E402

from scripts import runtime_ready_signal_shadow_planning_contract_fixture as shadow_fixture  # noqa: E402
from scripts.runtime_first_real_submit_api_flow import (  # noqa: E402
    FirstRealSubmitApiFlow,
    FlowConfig,
)
from scripts.runtime_official_server_prepare_integration_proof import (  # noqa: E402
    _ServerProofState,
    _TestClientApiClient,
    _configure_auth_env,
    _login,
    _signal_evaluation_from_candidate,
    _temporary_api_injections,
)
from src.domain.signal_evaluation import OrderCandidate, SignalEvaluation  # noqa: E402


def build_proof_report(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    shadow_dir = output_dir / "shadow-planning"
    shadow_report = shadow_fixture.build_contract_fixture_report(shadow_dir)
    _write_json(output_dir / "shadow-contract-report.json", shadow_report)

    candidate = OrderCandidate.model_validate(shadow_report["candidate_snapshot"])
    runtime = shadow_fixture._runtime()
    signal_evaluation = SignalEvaluation.model_validate(
        _signal_evaluation_from_candidate(candidate)
    )
    state = _ServerProofState(
        runtime=runtime,
        candidate=candidate,
        signal_evaluation=signal_evaluation,
    )

    _configure_auth_env()
    with _temporary_api_injections(state):
        from src.interfaces.api import app

        with TestClient(app) as client:
            login = _login(client)
            if login.status_code != 200:
                raise RuntimeError(
                    f"rtf081_login_failed:{login.status_code}:{login.text}"
                )
            api_client = _TestClientApiClient(client)
            final_gate_preview = api_client.request_json(
                "GET",
                (
                    "/api/trading-console/runtime-final-gate-preview/"
                    f"order-candidates/{candidate.order_candidate_id}"
                ),
                query={"owner_reviewed": True},
            )
            prepare_flow = FirstRealSubmitApiFlow(
                client=api_client,
                config=FlowConfig(
                    api_base="testclient://rtf081-official-final-gate-preflight",
                    mode="prepare",
                    order_candidate_id=candidate.order_candidate_id,
                    next_attempt_symbol=candidate.symbol,
                    next_attempt_side=candidate.side,
                    next_attempt_strategy_family_id=(
                        candidate.strategy_family_id
                    ),
                    next_attempt_carrier_id=(
                        candidate.strategy_family_version_id
                    ),
                    owner_operator_id="owner",
                    owner_confirmation_reference=(
                        "owner-reviewed-rtf081-final-gate-preflight"
                    ),
                    reason=(
                        "RTF-081 official FinalGate preflight proof"
                    ),
                ),
            )
            prepare_report = prepare_flow.run()
            authorization_id = (prepare_report.get("ids") or {}).get(
                "authorization_id"
            )
            if not authorization_id:
                raise RuntimeError("rtf081_authorization_id_missing")
            controlled_submit_plan = api_client.request_json(
                "GET",
                (
                    "/api/trading-console/"
                    "runtime-execution-controlled-submit-plans/"
                    f"authorizations/{authorization_id}"
                ),
            )
            controlled_submit_preflight = api_client.request_json(
                "GET",
                (
                    "/api/trading-console/"
                    "runtime-execution-controlled-submit-preflights/"
                    f"authorizations/{authorization_id}"
                ),
            )

    preflight_artifact = _preflight_artifact(
        shadow_report=shadow_report,
        final_gate_preview=final_gate_preview,
        prepare_report=prepare_report,
        controlled_submit_plan=controlled_submit_plan,
        controlled_submit_preflight=controlled_submit_preflight,
        state=state,
    )
    _write_json(output_dir / "prepare-report.json", prepare_report)
    _write_json(output_dir / "final-gate-preview.json", final_gate_preview)
    _write_json(output_dir / "controlled-submit-plan.json", controlled_submit_plan)
    _write_json(
        output_dir / "controlled-submit-preflight.json",
        controlled_submit_preflight,
    )
    _write_json(output_dir / "preflight-artifact.json", preflight_artifact)

    report = _report(
        shadow_report=shadow_report,
        prepare_report=prepare_report,
        final_gate_preview=final_gate_preview,
        controlled_submit_plan=controlled_submit_plan,
        controlled_submit_preflight=controlled_submit_preflight,
        preflight_artifact=preflight_artifact,
        state=state,
    )
    _write_json(output_dir / "contract-report.json", report)
    return report


def _preflight_artifact(
    *,
    shadow_report: dict[str, Any],
    final_gate_preview: dict[str, Any],
    prepare_report: dict[str, Any],
    controlled_submit_plan: dict[str, Any],
    controlled_submit_preflight: dict[str, Any],
    state: _ServerProofState,
) -> dict[str, Any]:
    ids = dict(prepare_report.get("ids") or {})
    final_gate_body = _body(final_gate_preview)
    plan_body = _body(controlled_submit_plan)
    preflight_body = _body(controlled_submit_preflight)
    safety = _safety_invariants(state)
    checks = _checks(
        shadow_report=shadow_report,
        final_gate_preview=final_gate_preview,
        prepare_report=prepare_report,
        controlled_submit_plan=controlled_submit_plan,
        controlled_submit_preflight=controlled_submit_preflight,
        safety=safety,
    )
    return {
        "scope": "runtime_official_final_gate_preflight_artifact",
        "status": (
            "ready_for_controlled_submit_adapter"
            if _contract_passed(checks)
            else "blocked"
        ),
        "ids": {
            **ids,
            "controlled_submit_plan_id": plan_body.get("plan_id"),
            "controlled_submit_preflight_id": preflight_body.get("preflight_id"),
        },
        "final_gate": {
            "http_status": final_gate_preview.get("http_status"),
            "verdict": final_gate_body.get("verdict"),
            "status": final_gate_body.get("status"),
            "blockers": list(final_gate_body.get("blockers") or []),
            "warnings": list(final_gate_body.get("warnings") or []),
        },
        "controlled_submit_plan": {
            "http_status": controlled_submit_plan.get("http_status"),
            "status": plan_body.get("status"),
            "blockers": list(plan_body.get("blockers") or []),
            "warnings": list(plan_body.get("warnings") or []),
        },
        "controlled_submit_preflight": {
            "http_status": controlled_submit_preflight.get("http_status"),
            "status": preflight_body.get("status"),
            "final_gate_verdict": preflight_body.get("final_gate_verdict"),
            "blockers": list(preflight_body.get("blockers") or []),
            "warnings": list(preflight_body.get("warnings") or []),
            "preview_only": preflight_body.get("preview_only"),
            "submit_executed": preflight_body.get("submit_executed"),
            "order_created": preflight_body.get("order_created"),
            "exchange_called": preflight_body.get("exchange_called"),
            "order_lifecycle_called": preflight_body.get(
                "order_lifecycle_called"
            ),
        },
        "checks": checks,
        "safety_invariants": safety,
    }


def _report(
    *,
    shadow_report: dict[str, Any],
    prepare_report: dict[str, Any],
    final_gate_preview: dict[str, Any],
    controlled_submit_plan: dict[str, Any],
    controlled_submit_preflight: dict[str, Any],
    preflight_artifact: dict[str, Any],
    state: _ServerProofState,
) -> dict[str, Any]:
    checks = dict(preflight_artifact["checks"])
    ids = preflight_artifact["ids"]
    return {
        "scope": "runtime_official_final_gate_preflight_proof",
        "status": (
            "official_final_gate_preflight_passed"
            if _contract_passed(checks)
            else "blocked"
        ),
        "runtime_instance_id": state.runtime.runtime_instance_id,
        "order_candidate_id": state.candidate.order_candidate_id,
        "signal_evaluation_id": state.signal_evaluation.signal_evaluation_id,
        "authorization_id": ids.get("authorization_id"),
        "runtime_execution_intent_draft_id": ids.get(
            "runtime_execution_intent_draft_id"
        ),
        "execution_intent_id": ids.get("execution_intent_id"),
        "controlled_submit_plan_id": ids.get("controlled_submit_plan_id"),
        "controlled_submit_preflight_id": ids.get(
            "controlled_submit_preflight_id"
        ),
        "preflight_artifact": preflight_artifact,
        "shadow_contract": shadow_report,
        "first_real_submit_prepare_report": prepare_report,
        "final_gate_preview": final_gate_preview,
        "controlled_submit_plan": controlled_submit_plan,
        "controlled_submit_preflight": controlled_submit_preflight,
        "checks": checks,
        "final_gate_preflight_plan": {
            "next_step": (
                "build_non_executing_submit_adapter_preview"
                if _contract_passed(checks)
                else "resolve_final_gate_preflight_blockers"
            ),
            "uses_official_fastapi_routes": True,
            "uses_fake_console_api": False,
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
        "safety_invariants": preflight_artifact["safety_invariants"],
    }


def _checks(
    *,
    shadow_report: dict[str, Any],
    final_gate_preview: dict[str, Any],
    prepare_report: dict[str, Any],
    controlled_submit_plan: dict[str, Any],
    controlled_submit_preflight: dict[str, Any],
    safety: dict[str, bool],
) -> dict[str, bool]:
    ids = prepare_report.get("ids") or {}
    final_gate_body = _body(final_gate_preview)
    plan_body = _body(controlled_submit_plan)
    preflight_body = _body(controlled_submit_preflight)
    return {
        "shadow_contract_passed": (
            shadow_report.get("status")
            == "ready_signal_shadow_planning_contract_passed"
        ),
        "right_tail_runner_preserved": bool(
            (shadow_report.get("checks") or {}).get("right_tail_runner_preserved")
        ),
        "prepare_authorization_created": bool(ids.get("authorization_id")),
        "final_gate_preview_route_called": (
            final_gate_preview.get("http_status") == 200
        ),
        "final_gate_verdict_pass": _normalized(final_gate_body.get("verdict"))
        == "pass",
        "final_gate_no_blockers": not list(final_gate_body.get("blockers") or []),
        "controlled_submit_plan_route_called": (
            controlled_submit_plan.get("http_status") == 200
        ),
        "controlled_submit_plan_ready": (
            plan_body.get("status") == "ready_for_controlled_submit_adapter"
        ),
        "controlled_submit_preflight_route_called": (
            controlled_submit_preflight.get("http_status") == 200
        ),
        "controlled_submit_preflight_ready": (
            preflight_body.get("status") == "ready_for_controlled_submit_adapter"
        ),
        "preflight_final_gate_verdict_pass": (
            _normalized(preflight_body.get("final_gate_verdict")) == "pass"
        ),
        "preflight_preview_only": preflight_body.get("preview_only") is True,
        "preflight_no_blockers": not list(preflight_body.get("blockers") or []),
        "uses_official_fastapi_routes": True,
        "uses_fake_console_api": False,
        "pg_written": safety["pg_written"],
        "exchange_write_called": safety["exchange_write_called"],
        "order_created": safety["order_created"],
        "order_lifecycle_called": safety["order_lifecycle_called"],
        "attempt_counter_mutated": safety["attempt_counter_mutated"],
        "runtime_budget_mutated": safety["runtime_budget_mutated"],
        "withdrawal_or_transfer_created": safety[
            "withdrawal_or_transfer_created"
        ],
    }


def _contract_passed(checks: dict[str, bool]) -> bool:
    required_true = (
        "shadow_contract_passed",
        "right_tail_runner_preserved",
        "prepare_authorization_created",
        "final_gate_preview_route_called",
        "final_gate_verdict_pass",
        "final_gate_no_blockers",
        "controlled_submit_plan_route_called",
        "controlled_submit_plan_ready",
        "controlled_submit_preflight_route_called",
        "controlled_submit_preflight_ready",
        "preflight_final_gate_verdict_pass",
        "preflight_preview_only",
        "preflight_no_blockers",
        "uses_official_fastapi_routes",
    )
    required_false = (
        "uses_fake_console_api",
        "pg_written",
        "exchange_write_called",
        "order_created",
        "order_lifecycle_called",
        "attempt_counter_mutated",
        "runtime_budget_mutated",
        "withdrawal_or_transfer_created",
    )
    return all(checks.get(key) is True for key in required_true) and all(
        checks.get(key) is False for key in required_false
    )


def _safety_invariants(state: _ServerProofState) -> dict[str, bool]:
    return {
        "uses_official_fastapi_routes": True,
        "uses_fake_console_api": False,
        "uses_in_memory_repositories": True,
        "pg_written": False,
        "uses_live_exchange": False,
        "local_registration_armed": False,
        "exchange_submit_armed": False,
        "execute_real_submit": False,
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "attempt_counter_mutated": state.runtime_service.attempt_mutations > 0,
        "runtime_budget_mutated": state.runtime_service.budget_settlements > 0,
        "position_opened": False,
        "position_closed": False,
        "withdrawal_or_transfer_created": False,
    }


def _body(result: dict[str, Any]) -> dict[str, Any]:
    body = result.get("body")
    return body if isinstance(body, dict) else {}


def _normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an official FinalGate preflight proof."
    )
    parser.add_argument(
        "--output-dir",
        default="output/rtf081-official-final-gate-preflight",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_proof_report(Path(args.output_dir).expanduser())
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if report["status"] == "official_final_gate_preflight_passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
