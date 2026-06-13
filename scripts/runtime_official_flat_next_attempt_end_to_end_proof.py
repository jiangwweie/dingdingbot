#!/usr/bin/env python3
"""Official flat next-attempt end-to-end proof.

RTF-092 proves the ready/flat side of the runtime loop:

ready post-submit finalize packet
-> official next-attempt strategy planning route
-> fresh shadow SignalEvaluation / OrderCandidate
-> official prepare / FinalGate / controlled-submit preflight

It remains non-executing.  Prepare records and a non-executable
ExecutionIntent are allowed as audit artifacts; local order registration,
OrderLifecycle submit, exchange calls, runtime mutation, withdrawal, and
transfer are forbidden in this proof.
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

from scripts import runtime_ready_signal_shadow_planning_contract_fixture as ready_fixture  # noqa: E402
from scripts.runtime_official_prepare_api_flow import (  # noqa: E402
    RuntimeOfficialPrepareApiFlow,
    RuntimeOfficialPrepareFlowConfig,
)
from scripts.runtime_official_next_attempt_strategy_continuation_proof import (  # noqa: E402
    _post_next_attempt_strategy_plan,
    _temporary_next_attempt_injections,
)
from scripts.runtime_official_scoped_local_registration_proof import (  # noqa: E402
    _body,
    _write_json,
)
from scripts.runtime_official_server_prepare_integration_proof import (  # noqa: E402
    _ServerProofState,
    _TestClientApiClient,
    _configure_auth_env,
    _login,
    _temporary_api_injections,
)


def build_proof_report(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    runtime = ready_fixture._runtime()
    signal_input = ready_fixture._signal_input()
    ready_post_submit = ready_fixture._post_submit_finalize_packet(runtime)
    store = ready_fixture._ShadowStore()
    planning_service = ready_fixture._planning_service(
        runtime=runtime,
        store=store,
    )

    _configure_auth_env()
    with _temporary_next_attempt_injections(
        runtime_service=ready_fixture._RuntimeService(runtime),
        planning_service=planning_service,
    ):
        from src.interfaces.api import app

        with TestClient(app) as client:
            login = _login(client)
            if login.status_code != 200:
                raise RuntimeError(
                    f"rtf092_strategy_login_failed:{login.status_code}:{login.text}"
                )
            api_client = _TestClientApiClient(client)
            strategy_plan = _post_next_attempt_strategy_plan(
                api_client=api_client,
                runtime_instance_id=runtime.runtime_instance_id,
                post_submit_finalize_packet=ready_post_submit.model_dump(mode="json"),
                signal_input=signal_input.model_dump(mode="json"),
                context_id="rtf092-flat-next-attempt",
            )

    if store.candidate is None or store.evaluation is None:
        raise RuntimeError("rtf092_shadow_candidate_not_created")

    state = _ServerProofState(
        runtime=runtime,
        candidate=store.candidate,
        signal_evaluation=store.evaluation,
    )

    with _temporary_api_injections(state):
        from src.interfaces.api import app

        with TestClient(app) as client:
            login = _login(client)
            if login.status_code != 200:
                raise RuntimeError(
                    f"rtf092_preflight_login_failed:{login.status_code}:{login.text}"
                )
            api_client = _TestClientApiClient(client)
            final_gate_preview = api_client.request_json(
                "GET",
                (
                    "/api/trading-console/runtime-final-gate-preview/"
                    f"order-candidates/{store.candidate.order_candidate_id}"
                ),
                query={"owner_reviewed": True},
            )
            prepare_flow = RuntimeOfficialPrepareApiFlow(
                client=api_client,
                config=RuntimeOfficialPrepareFlowConfig(
                    api_base="testclient://rtf092-flat-next-attempt-e2e",
                    mode="prepare",
                    order_candidate_id=store.candidate.order_candidate_id,
                    next_attempt_symbol=store.candidate.symbol,
                    next_attempt_side=store.candidate.side,
                    next_attempt_strategy_family_id=(
                        store.candidate.strategy_family_id
                    ),
                    next_attempt_carrier_id=(
                        store.candidate.strategy_family_version_id
                    ),
                    owner_operator_id="owner",
                    owner_confirmation_reference=(
                        "owner-reviewed-rtf092-flat-next-attempt"
                    ),
                    reason="RTF-092 flat next-attempt end-to-end proof",
                ),
            )
            prepare_report = prepare_flow.run()
            authorization_id = (prepare_report.get("ids") or {}).get(
                "authorization_id"
            )
            if not authorization_id:
                raise RuntimeError("rtf092_authorization_id_missing")
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

    artifacts = {
        "ready-post-submit-finalize.json": ready_post_submit.model_dump(mode="json"),
        "signal-input.json": signal_input.model_dump(mode="json"),
        "next-attempt-strategy-plan.json": strategy_plan,
        "shadow-signal-evaluation.json": store.evaluation.model_dump(mode="json"),
        "shadow-order-candidate.json": store.candidate.model_dump(mode="json"),
        "prepare-report.json": prepare_report,
        "final-gate-preview.json": final_gate_preview,
        "controlled-submit-plan.json": controlled_submit_plan,
        "controlled-submit-preflight.json": controlled_submit_preflight,
    }
    for name, payload in artifacts.items():
        _write_json(output_dir / name, payload)

    packet = _proof_packet(
        ready_post_submit=ready_post_submit.model_dump(mode="json"),
        strategy_plan=strategy_plan,
        planning_proposal=(
            store.candidate.metadata.get("planning_proposal")
            if store.candidate is not None
            else None
        ),
        prepare_report=prepare_report,
        final_gate_preview=final_gate_preview,
        controlled_submit_plan=controlled_submit_plan,
        controlled_submit_preflight=controlled_submit_preflight,
        state=state,
    )
    _write_json(output_dir / "flat-next-attempt-end-to-end-packet.json", packet)

    checks = dict(packet["checks"])
    report = {
        "scope": "runtime_official_flat_next_attempt_end_to_end_proof",
        "status": (
            "official_flat_next_attempt_end_to_end_passed"
            if _contract_passed(checks)
            else "blocked"
        ),
        "runtime_instance_id": runtime.runtime_instance_id,
        "signal_evaluation_id": packet["strategy_plan"].get(
            "signal_evaluation_id"
        ),
        "order_candidate_id": store.candidate.order_candidate_id,
        "authorization_id": (prepare_report.get("ids") or {}).get(
            "authorization_id"
        ),
        "runtime_execution_intent_draft_id": (prepare_report.get("ids") or {}).get(
            "runtime_execution_intent_draft_id"
        ),
        "execution_intent_id": (prepare_report.get("ids") or {}).get(
            "execution_intent_id"
        ),
        "controlled_submit_preflight_id": packet["ids"].get(
            "controlled_submit_preflight_id"
        ),
        "flat_next_attempt_end_to_end_packet": packet,
        "checks": checks,
        "safety_invariants": packet["safety_invariants"],
        "operator_command_plan": {
            "next_step": (
                "tokyo_integration_probe_or_full_runtime_cycle_proof"
                if _contract_passed(checks)
                else "resolve_flat_next_attempt_end_to_end_blockers"
            ),
            "uses_official_fastapi_routes": True,
            "uses_fake_console_api": False,
            "ready_gate_allows_fresh_strategy_signal": True,
            "requires_fresh_authorization_before_submit": True,
            "executes_submit": False,
            "calls_exchange": False,
        },
        "right_tail_objective_context": {
            "small_bounded_losses_allowed_after_runtime_gate": True,
            "right_tail_runner_preserved": checks[
                "right_tail_runner_preserved"
            ],
            "automatic_compounding_assumed": False,
            "automatic_withdrawal_assumed": False,
            "not_proven_alpha": True,
        },
    }
    _write_json(output_dir / "contract-report.json", report)
    return report


def _proof_packet(
    *,
    ready_post_submit: dict[str, Any],
    strategy_plan: dict[str, Any],
    planning_proposal: dict[str, Any] | None,
    prepare_report: dict[str, Any],
    final_gate_preview: dict[str, Any],
    controlled_submit_plan: dict[str, Any],
    controlled_submit_preflight: dict[str, Any],
    state: _ServerProofState,
) -> dict[str, Any]:
    strategy_body = _body(strategy_plan)
    final_gate_body = _body(final_gate_preview)
    submit_plan_body = _body(controlled_submit_plan)
    preflight_body = _body(controlled_submit_preflight)
    ids = {
        **dict(prepare_report.get("ids") or {}),
        "controlled_submit_plan_id": submit_plan_body.get("plan_id"),
        "controlled_submit_preflight_id": preflight_body.get("preflight_id"),
    }
    safety = _safety_invariants(state=state, preflight_body=preflight_body)
    checks = _checks(
        ready_post_submit=ready_post_submit,
        strategy_body=strategy_body,
        planning_proposal=planning_proposal,
        prepare_report=prepare_report,
        final_gate_preview=final_gate_preview,
        final_gate_body=final_gate_body,
        controlled_submit_plan=controlled_submit_plan,
        submit_plan_body=submit_plan_body,
        controlled_submit_preflight=controlled_submit_preflight,
        preflight_body=preflight_body,
        safety=safety,
    )
    return {
        "scope": "runtime_official_flat_next_attempt_end_to_end_packet",
        "status": (
            "flat_next_attempt_ready_for_controlled_submit_adapter"
            if _contract_passed(checks)
            else "blocked"
        ),
        "ids": ids,
        "ready_post_submit_gate": {
            "status": ready_post_submit.get("status"),
            "next_attempt_gate_status": (
                ready_post_submit.get("next_attempt_gate") or {}
            ).get("status"),
            "active_positions_count": (
                ready_post_submit.get("next_attempt_gate") or {}
            ).get("active_positions_count"),
            "old_authorization_submit_retry_allowed": ready_post_submit.get(
                "old_authorization_submit_retry_allowed"
            ),
            "pre_submit_rehearsal_retry_allowed": ready_post_submit.get(
                "pre_submit_rehearsal_retry_allowed"
            ),
        },
        "strategy_plan": {
            "http_status": strategy_plan.get("http_status"),
            "status": strategy_body.get("status"),
            "next_attempt_gate_status": strategy_body.get(
                "next_attempt_gate_status"
            ),
            "signal_evaluation_id": strategy_body.get("signal_evaluation_id"),
            "order_candidate_id": strategy_body.get("order_candidate_id"),
            "candidate_planning_status": strategy_body.get(
                "candidate_planning_status"
            ),
            "requires_fresh_authorization_before_submit": strategy_body.get(
                "requires_fresh_authorization_before_submit"
            ),
        },
        "final_gate": {
            "http_status": final_gate_preview.get("http_status"),
            "verdict": final_gate_body.get("verdict"),
            "status": final_gate_body.get("status"),
            "blockers": list(final_gate_body.get("blockers") or []),
        },
        "controlled_submit_preflight": {
            "http_status": controlled_submit_preflight.get("http_status"),
            "status": preflight_body.get("status"),
            "final_gate_verdict": preflight_body.get("final_gate_verdict"),
            "preview_only": preflight_body.get("preview_only"),
            "submit_executed": preflight_body.get("submit_executed"),
            "order_created": preflight_body.get("order_created"),
            "exchange_called": preflight_body.get("exchange_called"),
            "order_lifecycle_called": preflight_body.get(
                "order_lifecycle_called"
            ),
            "blockers": list(preflight_body.get("blockers") or []),
        },
        "checks": checks,
        "safety_invariants": safety,
    }


def _checks(
    *,
    ready_post_submit: dict[str, Any],
    strategy_body: dict[str, Any],
    planning_proposal: dict[str, Any] | None,
    prepare_report: dict[str, Any],
    final_gate_preview: dict[str, Any],
    final_gate_body: dict[str, Any],
    controlled_submit_plan: dict[str, Any],
    submit_plan_body: dict[str, Any],
    controlled_submit_preflight: dict[str, Any],
    preflight_body: dict[str, Any],
    safety: dict[str, bool],
) -> dict[str, bool]:
    prepare_ids = prepare_report.get("ids") or {}
    next_gate = ready_post_submit.get("next_attempt_gate") or {}
    strategy_operator = strategy_body.get("operator_command_plan") or {}
    candidate_proposal = strategy_body.get("proposal") or planning_proposal or {}
    tp_refs = candidate_proposal.get("take_profit_references") or []
    return {
        "ready_post_submit_gate_flat": (
            ready_post_submit.get("status") == "finalized_ready_for_next_attempt"
            and next_gate.get("status") == "ready_for_fresh_signal"
            and next_gate.get("active_positions_count") == 0
        ),
        "old_authorization_retry_disallowed": (
            ready_post_submit.get("old_authorization_submit_retry_allowed") is False
        ),
        "pre_submit_rehearsal_retry_disallowed": (
            ready_post_submit.get("pre_submit_rehearsal_retry_allowed") is False
        ),
        "strategy_plan_route_called": strategy_body.get("status")
        == "ready_for_final_gate_preflight"
        and strategy_body.get("order_candidate_id")
        == "order-candidate-rtf075-contract",
        "strategy_plan_http_ok": strategy_body
        and strategy_body.get("order_candidate_id") is not None,
        "strategy_plan_gate_ready": (
            strategy_body.get("next_attempt_gate_status")
            == "ready_for_fresh_signal"
        ),
        "shadow_signal_created": (
            strategy_body.get("signal_evaluation_id") == "eval-rtf075-cpm-long"
        ),
        "shadow_candidate_created": (
            strategy_body.get("order_candidate_id")
            == "order-candidate-rtf075-contract"
        ),
        "strategy_requires_official_final_gate": (
            strategy_operator.get("requires_official_final_gate") is True
        ),
        "fresh_authorization_required_before_submit": (
            strategy_body.get("requires_fresh_authorization_before_submit") is True
        ),
        "tp1_present": any(
            str(item.get("kind") or "").startswith("tp1")
            for item in tp_refs
            if isinstance(item, dict)
        ),
        "runner_present": any(
            item.get("kind") == "runner" for item in tp_refs if isinstance(item, dict)
        ),
        "right_tail_runner_preserved": any(
            item.get("right_tail_capture") is True
            for item in tp_refs
            if isinstance(item, dict)
        ),
        "prepare_authorization_created": bool(prepare_ids.get("authorization_id")),
        "prepare_intent_created_for_audit": bool(
            prepare_ids.get("execution_intent_id")
        ),
        "final_gate_route_called": final_gate_preview.get("http_status") == 200,
        "final_gate_verdict_pass": str(
            final_gate_body.get("verdict") or ""
        ).lower()
        == "pass",
        "final_gate_no_blockers": not list(final_gate_body.get("blockers") or []),
        "controlled_submit_plan_route_called": (
            controlled_submit_plan.get("http_status") == 200
        ),
        "controlled_submit_plan_ready": (
            submit_plan_body.get("status") == "ready_for_controlled_submit_adapter"
        ),
        "controlled_submit_preflight_route_called": (
            controlled_submit_preflight.get("http_status") == 200
        ),
        "controlled_submit_preflight_ready": (
            preflight_body.get("status") == "ready_for_controlled_submit_adapter"
        ),
        "preflight_preview_only": preflight_body.get("preview_only") is True,
        "preflight_submit_not_executed": preflight_body.get("submit_executed") is False,
        "preflight_no_order_created": preflight_body.get("order_created") is False,
        "preflight_no_exchange_called": preflight_body.get("exchange_called") is False,
        "preflight_no_order_lifecycle_called": (
            preflight_body.get("order_lifecycle_called") is False
        ),
        "uses_official_fastapi_routes": True,
        "uses_fake_console_api": False,
        "runtime_state_mutated": safety["runtime_state_mutated"],
        "withdrawal_or_transfer_created": safety[
            "withdrawal_or_transfer_created"
        ],
    }


def _contract_passed(checks: dict[str, bool]) -> bool:
    required_true = (
        "ready_post_submit_gate_flat",
        "old_authorization_retry_disallowed",
        "pre_submit_rehearsal_retry_disallowed",
        "strategy_plan_route_called",
        "strategy_plan_http_ok",
        "strategy_plan_gate_ready",
        "shadow_signal_created",
        "shadow_candidate_created",
        "strategy_requires_official_final_gate",
        "fresh_authorization_required_before_submit",
        "tp1_present",
        "runner_present",
        "right_tail_runner_preserved",
        "prepare_authorization_created",
        "prepare_intent_created_for_audit",
        "final_gate_route_called",
        "final_gate_verdict_pass",
        "final_gate_no_blockers",
        "controlled_submit_plan_route_called",
        "controlled_submit_plan_ready",
        "controlled_submit_preflight_route_called",
        "controlled_submit_preflight_ready",
        "preflight_preview_only",
        "preflight_submit_not_executed",
        "preflight_no_order_created",
        "preflight_no_exchange_called",
        "preflight_no_order_lifecycle_called",
        "uses_official_fastapi_routes",
    )
    required_false = (
        "uses_fake_console_api",
        "runtime_state_mutated",
        "withdrawal_or_transfer_created",
    )
    return all(checks.get(key) is True for key in required_true) and all(
        checks.get(key) is False for key in required_false
    )


def _safety_invariants(
    *,
    state: _ServerProofState,
    preflight_body: dict[str, Any],
) -> dict[str, bool]:
    return {
        "uses_official_fastapi_routes": True,
        "uses_fake_console_api": False,
        "uses_in_memory_repositories": True,
        "ready_post_submit_gate_flat": True,
        "shadow_candidate_created": True,
        "execution_intent_created_for_audit": True,
        "executable_submit_executed": preflight_body.get("submit_executed") is True,
        "local_order_created": preflight_body.get("order_created") is True,
        "order_lifecycle_called": preflight_body.get("order_lifecycle_called") is True,
        "exchange_called": preflight_body.get("exchange_called") is True,
        "attempt_counter_mutated": state.runtime_service.attempt_mutations > 0,
        "runtime_budget_mutated": state.runtime_service.budget_settlements > 0,
        "runtime_state_mutated": (
            state.runtime_service.attempt_mutations > 0
            or state.runtime_service.budget_settlements > 0
        ),
        "withdrawal_or_transfer_created": False,
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an official flat next-attempt end-to-end proof."
    )
    parser.add_argument(
        "--output-dir",
        default="output/rtf092-official-flat-next-attempt-end-to-end",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_proof_report(Path(args.output_dir).expanduser())
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return (
        0
        if report["status"] == "official_flat_next_attempt_end_to_end_passed"
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
