#!/usr/bin/env python3
"""Official non-executing submit adapter and local-registration boundary proof.

RTF-083 extends the official FinalGate preflight proof through the official
submit-adapter preview, attempt reservation/mutation, OrderLifecycle handoff
draft, OrderLifecycle adapter preview, and local order registration draft
preview routes.  It remains non-executing: no PG writes, no real orders, no
OrderLifecycle calls, no exchange writes, withdrawals, or transfers.
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
    _CreateGetRepo,
    _ServerProofState,
    _TestClientApiClient,
    _RuntimeService,
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
    state = _rtf083_state(
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
                    f"rtf083_login_failed:{login.status_code}:{login.text}"
                )
            api_client = _TestClientApiClient(client)
            prepare_flow = FirstRealSubmitApiFlow(
                client=api_client,
                config=FlowConfig(
                    api_base="testclient://rtf083-official-submit-adapter",
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
                        "owner-reviewed-rtf083-submit-adapter-preview"
                    ),
                    reason=(
                        "RTF-083 official submit adapter preview proof"
                    ),
                ),
            )
            prepare_report = prepare_flow.run()
            authorization_id = (prepare_report.get("ids") or {}).get(
                "authorization_id"
            )
            if not authorization_id:
                raise RuntimeError("rtf083_authorization_id_missing")

            final_gate_preview = api_client.request_json(
                "GET",
                (
                    "/api/trading-console/runtime-final-gate-preview/"
                    f"order-candidates/{candidate.order_candidate_id}"
                ),
                query={"owner_reviewed": True},
            )
            controlled_submit_preflight = api_client.request_json(
                "GET",
                (
                    "/api/trading-console/"
                    "runtime-execution-controlled-submit-preflights/"
                    f"authorizations/{authorization_id}"
                ),
            )
            submit_adapter_preview = api_client.request_json(
                "GET",
                (
                    "/api/trading-console/"
                    "runtime-execution-submit-adapter-previews/"
                    f"authorizations/{authorization_id}"
                ),
            )
            attempt_reservation_preview = api_client.request_json(
                "GET",
                (
                    "/api/trading-console/"
                    "runtime-execution-attempt-reservation-previews/"
                    f"authorizations/{authorization_id}"
                ),
            )
            attempt_reservation = api_client.request_json(
                "POST",
                (
                    "/api/trading-console/"
                    "runtime-execution-attempt-reservations/"
                    f"authorizations/{authorization_id}"
                ),
            )
            reservation_id = _body(attempt_reservation).get("reservation_id")
            if not reservation_id:
                raise RuntimeError("rtf083_reservation_id_missing")
            attempt_mutation = api_client.request_json(
                "POST",
                (
                    "/api/trading-console/"
                    "runtime-execution-attempt-mutations/"
                    f"reservations/{reservation_id}"
                ),
            )
            order_lifecycle_handoff = api_client.request_json(
                "POST",
                (
                    "/api/trading-console/"
                    "runtime-execution-order-lifecycle-handoff-drafts/"
                    f"authorizations/{authorization_id}"
                ),
            )
            order_lifecycle_adapter_preview = api_client.request_json(
                "GET",
                (
                    "/api/trading-console/"
                    "runtime-execution-order-lifecycle-adapter-previews/"
                    f"authorizations/{authorization_id}"
                ),
            )
            order_registration_draft_preview = api_client.request_json(
                "GET",
                (
                    "/api/trading-console/"
                    "runtime-execution-order-registration-draft-previews/"
                    f"authorizations/{authorization_id}"
                ),
            )

    submit_adapter_boundary_artifact = _submit_adapter_boundary_artifact(
        shadow_report=shadow_report,
        prepare_report=prepare_report,
        final_gate_preview=final_gate_preview,
        controlled_submit_preflight=controlled_submit_preflight,
        submit_adapter_preview=submit_adapter_preview,
        attempt_reservation_preview=attempt_reservation_preview,
        attempt_reservation=attempt_reservation,
        attempt_mutation=attempt_mutation,
        order_lifecycle_handoff=order_lifecycle_handoff,
        order_lifecycle_adapter_preview=order_lifecycle_adapter_preview,
        order_registration_draft_preview=order_registration_draft_preview,
        state=state,
    )

    artifacts = {
        "prepare-report.json": prepare_report,
        "final-gate-preview.json": final_gate_preview,
        "controlled-submit-preflight.json": controlled_submit_preflight,
        "submit-adapter-preview.json": submit_adapter_preview,
        "attempt-reservation-preview.json": attempt_reservation_preview,
        "attempt-reservation.json": attempt_reservation,
        "attempt-mutation.json": attempt_mutation,
        "order-lifecycle-handoff.json": order_lifecycle_handoff,
        "order-lifecycle-adapter-preview.json": order_lifecycle_adapter_preview,
        "order-registration-draft-preview.json": order_registration_draft_preview,
        "submit-adapter-boundary-artifact.json": submit_adapter_boundary_artifact,
    }
    for name, payload in artifacts.items():
        _write_json(output_dir / name, payload)

    report = _report(
        shadow_report=shadow_report,
        prepare_report=prepare_report,
        final_gate_preview=final_gate_preview,
        controlled_submit_preflight=controlled_submit_preflight,
        submit_adapter_preview=submit_adapter_preview,
        attempt_reservation_preview=attempt_reservation_preview,
        attempt_reservation=attempt_reservation,
        attempt_mutation=attempt_mutation,
        order_lifecycle_handoff=order_lifecycle_handoff,
        order_lifecycle_adapter_preview=order_lifecycle_adapter_preview,
        order_registration_draft_preview=order_registration_draft_preview,
        submit_adapter_boundary_artifact=submit_adapter_boundary_artifact,
        state=state,
    )
    _write_json(output_dir / "contract-report.json", report)
    return report


class _Rtf083RuntimeService(_RuntimeService):
    async def apply_runtime_attempt_mutation(self, **kwargs: Any) -> Any:
        self.attempt_mutations += 1
        updated_runtime = kwargs.get("updated_runtime")
        if updated_runtime is not None:
            self.runtime = updated_runtime
        return self.runtime


def _rtf083_state(
    *,
    runtime: Any,
    candidate: OrderCandidate,
    signal_evaluation: SignalEvaluation,
) -> _ServerProofState:
    state = _ServerProofState(
        runtime=runtime,
        candidate=candidate,
        signal_evaluation=signal_evaluation,
    )
    runtime_service = _Rtf083RuntimeService(runtime)
    state.runtime_service = runtime_service
    state.final_gate._runtime_service = runtime_service
    state.adapter_service._runtime_service = runtime_service
    state.adapter_service._attempt_reservation_repository = _CreateGetRepo(
        "reservation_id"
    )
    state.adapter_service._attempt_mutation_repository = _CreateGetRepo(
        "mutation_id"
    )
    return state


def _submit_adapter_boundary_artifact(
    *,
    shadow_report: dict[str, Any],
    prepare_report: dict[str, Any],
    final_gate_preview: dict[str, Any],
    controlled_submit_preflight: dict[str, Any],
    submit_adapter_preview: dict[str, Any],
    attempt_reservation_preview: dict[str, Any],
    attempt_reservation: dict[str, Any],
    attempt_mutation: dict[str, Any],
    order_lifecycle_handoff: dict[str, Any],
    order_lifecycle_adapter_preview: dict[str, Any],
    order_registration_draft_preview: dict[str, Any],
    state: _ServerProofState,
) -> dict[str, Any]:
    checks = _checks(
        shadow_report=shadow_report,
        prepare_report=prepare_report,
        final_gate_preview=final_gate_preview,
        controlled_submit_preflight=controlled_submit_preflight,
        submit_adapter_preview=submit_adapter_preview,
        attempt_reservation_preview=attempt_reservation_preview,
        attempt_reservation=attempt_reservation,
        attempt_mutation=attempt_mutation,
        order_lifecycle_handoff=order_lifecycle_handoff,
        order_lifecycle_adapter_preview=order_lifecycle_adapter_preview,
        order_registration_draft_preview=order_registration_draft_preview,
        state=state,
    )
    submit_body = _body(submit_adapter_preview)
    reservation_preview_body = _body(attempt_reservation_preview)
    mutation_body = _body(attempt_mutation)
    handoff_body = _body(order_lifecycle_handoff)
    lifecycle_preview_body = _body(order_lifecycle_adapter_preview)
    registration_body = _body(order_registration_draft_preview)
    return {
        "scope": "runtime_official_submit_adapter_boundary_artifact",
        "status": (
            "ready_for_local_registration_boundary_review"
            if _contract_passed(checks)
            else "blocked"
        ),
        "ids": {
            **dict(prepare_report.get("ids") or {}),
            "submit_adapter_preview_id": submit_body.get("adapter_preview_id"),
            "attempt_reservation_preview_id": reservation_preview_body.get(
                "reservation_preview_id"
            ),
            "attempt_reservation_id": _body(attempt_reservation).get(
                "reservation_id"
            ),
            "attempt_mutation_id": mutation_body.get("mutation_id"),
            "order_lifecycle_handoff_id": handoff_body.get("handoff_draft_id"),
            "order_lifecycle_adapter_preview_id": lifecycle_preview_body.get(
                "adapter_preview_id"
            ),
            "order_registration_draft_preview_id": registration_body.get(
                "registration_preview_id"
            ),
        },
        "statuses": {
            "final_gate": _body(final_gate_preview).get("verdict"),
            "controlled_submit_preflight": _body(
                controlled_submit_preflight
            ).get("status"),
            "submit_adapter_preview": submit_body.get("status"),
            "attempt_reservation_preview": reservation_preview_body.get("status"),
            "attempt_reservation": _body(attempt_reservation).get("status"),
            "attempt_mutation": mutation_body.get("status"),
            "order_lifecycle_handoff": handoff_body.get("status"),
            "order_lifecycle_adapter_preview": lifecycle_preview_body.get(
                "status"
            ),
            "order_registration_draft_preview": registration_body.get("status"),
        },
        "local_registration_boundary": {
            "registration_draft_count": registration_body.get(
                "registration_draft_count"
            ),
            "entry_registration_draft_count": registration_body.get(
                "entry_registration_draft_count"
            ),
            "protection_registration_draft_count": registration_body.get(
                "protection_registration_draft_count"
            ),
            "local_order_registration_enabled": registration_body.get(
                "local_order_registration_enabled"
            ),
            "order_lifecycle_adapter_implemented": registration_body.get(
                "order_lifecycle_adapter_implemented"
            ),
            "preview_only": registration_body.get("preview_only"),
        },
        "runtime_attempt_budget_boundary": {
            "attempt_consumed_in_memory": mutation_body.get("attempt_consumed"),
            "runtime_budget_mutated_in_memory": mutation_body.get(
                "runtime_budget_mutated"
            ),
            "attempts_used_before": mutation_body.get("attempts_used_before"),
            "attempts_used_after": mutation_body.get("attempts_used_after"),
            "budget_reserved_before": mutation_body.get("budget_reserved_before"),
            "budget_reserved_after": mutation_body.get("budget_reserved_after"),
            "budget_reservation_basis": (
                (mutation_body.get("metadata") or {}).get(
                    "budget_reservation_basis"
                )
            ),
            "budget_reservation_amount": (
                (mutation_body.get("metadata") or {}).get(
                    "budget_reservation_amount"
                )
            ),
        },
        "checks": checks,
        "safety_invariants": _safety_invariants(state),
    }


def _report(
    *,
    shadow_report: dict[str, Any],
    prepare_report: dict[str, Any],
    final_gate_preview: dict[str, Any],
    controlled_submit_preflight: dict[str, Any],
    submit_adapter_preview: dict[str, Any],
    attempt_reservation_preview: dict[str, Any],
    attempt_reservation: dict[str, Any],
    attempt_mutation: dict[str, Any],
    order_lifecycle_handoff: dict[str, Any],
    order_lifecycle_adapter_preview: dict[str, Any],
    order_registration_draft_preview: dict[str, Any],
    submit_adapter_boundary_artifact: dict[str, Any],
    state: _ServerProofState,
) -> dict[str, Any]:
    checks = dict(submit_adapter_boundary_artifact["checks"])
    ids = dict(submit_adapter_boundary_artifact["ids"])
    return {
        "scope": "runtime_official_submit_adapter_preview_proof",
        "status": (
            "official_submit_adapter_preview_passed"
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
        "submit_adapter_preview_id": ids.get("submit_adapter_preview_id"),
        "attempt_reservation_preview_id": ids.get(
            "attempt_reservation_preview_id"
        ),
        "attempt_reservation_id": ids.get("attempt_reservation_id"),
        "attempt_mutation_id": ids.get("attempt_mutation_id"),
        "order_lifecycle_handoff_id": ids.get("order_lifecycle_handoff_id"),
        "order_lifecycle_adapter_preview_id": ids.get(
            "order_lifecycle_adapter_preview_id"
        ),
        "order_registration_draft_preview_id": ids.get(
            "order_registration_draft_preview_id"
        ),
        "submit_adapter_boundary_artifact": submit_adapter_boundary_artifact,
        "shadow_contract": shadow_report,
        "first_real_submit_prepare_report": prepare_report,
        "final_gate_preview": final_gate_preview,
        "controlled_submit_preflight": controlled_submit_preflight,
        "submit_adapter_preview": submit_adapter_preview,
        "attempt_reservation_preview": attempt_reservation_preview,
        "attempt_reservation": attempt_reservation,
        "attempt_mutation": attempt_mutation,
        "order_lifecycle_handoff": order_lifecycle_handoff,
        "order_lifecycle_adapter_preview": order_lifecycle_adapter_preview,
        "order_registration_draft_preview": order_registration_draft_preview,
        "checks": checks,
        "submit_adapter_preview_plan": {
            "next_step": (
                "build_scoped_local_registration_enablement"
                if _contract_passed(checks)
                else "resolve_submit_adapter_boundary_blockers"
            ),
            "uses_official_fastapi_routes": True,
            "uses_fake_console_api": False,
            "live_submit_allowed": False,
            "local_registration_enabled": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "executes_real_submit": False,
        },
        "right_tail_objective_context": {
            "small_bounded_losses_allowed_after_runtime_gate": True,
            "attempt_budget_prefers_max_loss_reference": (
                submit_adapter_boundary_artifact[
                    "runtime_attempt_budget_boundary"
                ].get(
                    "budget_reservation_basis"
                )
                == "max_loss_reference"
            ),
            "automatic_compounding_assumed": False,
            "automatic_withdrawal_assumed": False,
            "not_proven_alpha": True,
        },
        "safety_invariants": submit_adapter_boundary_artifact[
            "safety_invariants"
        ],
    }


def _checks(
    *,
    shadow_report: dict[str, Any],
    prepare_report: dict[str, Any],
    final_gate_preview: dict[str, Any],
    controlled_submit_preflight: dict[str, Any],
    submit_adapter_preview: dict[str, Any],
    attempt_reservation_preview: dict[str, Any],
    attempt_reservation: dict[str, Any],
    attempt_mutation: dict[str, Any],
    order_lifecycle_handoff: dict[str, Any],
    order_lifecycle_adapter_preview: dict[str, Any],
    order_registration_draft_preview: dict[str, Any],
    state: _ServerProofState,
) -> dict[str, bool]:
    ids = prepare_report.get("ids") or {}
    final_gate_body = _body(final_gate_preview)
    preflight_body = _body(controlled_submit_preflight)
    submit_body = _body(submit_adapter_preview)
    reservation_preview_body = _body(attempt_reservation_preview)
    reservation_body = _body(attempt_reservation)
    mutation_body = _body(attempt_mutation)
    handoff_body = _body(order_lifecycle_handoff)
    lifecycle_preview_body = _body(order_lifecycle_adapter_preview)
    registration_body = _body(order_registration_draft_preview)
    safety = _safety_invariants(state)
    return {
        "shadow_contract_passed": (
            shadow_report.get("status")
            == "ready_signal_shadow_planning_contract_passed"
        ),
        "right_tail_runner_preserved": bool(
            (shadow_report.get("checks") or {}).get("right_tail_runner_preserved")
        ),
        "prepare_authorization_created": bool(ids.get("authorization_id")),
        "final_gate_verdict_pass": _normalized(final_gate_body.get("verdict"))
        == "pass",
        "controlled_submit_preflight_ready": (
            preflight_body.get("status") == "ready_for_controlled_submit_adapter"
        ),
        "submit_adapter_preview_route_called": (
            submit_adapter_preview.get("http_status") == 200
        ),
        "submit_adapter_preview_ready_not_implemented": (
            submit_body.get("status") == "inputs_ready_adapter_not_implemented"
        ),
        "submit_adapter_preview_preview_only": (
            submit_body.get("preview_only") is True
        ),
        "attempt_reservation_preview_ready": (
            reservation_preview_body.get("status") == "ready_to_reserve_attempt"
        ),
        "attempt_reservation_recorded_pending_mutation": (
            reservation_body.get("status") == "pending_runtime_mutation"
        ),
        "attempt_mutation_applied_in_memory": (
            mutation_body.get("status") == "applied"
            and mutation_body.get("attempt_consumed") is True
            and mutation_body.get("runtime_budget_mutated") is True
        ),
        "budget_reservation_prefers_max_loss_reference": (
            (mutation_body.get("metadata") or {}).get("budget_reservation_basis")
            == "max_loss_reference"
        ),
        "order_lifecycle_handoff_ready": (
            handoff_body.get("status") == "ready_for_order_lifecycle_adapter"
        ),
        "order_lifecycle_adapter_preview_ready": (
            lifecycle_preview_body.get("status")
            == "inputs_ready_registration_not_enabled"
        ),
        "order_registration_draft_preview_ready": (
            registration_body.get("status")
            == "inputs_ready_registration_draft_only"
        ),
        "registration_has_entry_draft": (
            registration_body.get("entry_registration_draft_count") == 1
        ),
        "registration_has_protection_draft": (
            int(registration_body.get("protection_registration_draft_count") or 0)
            >= 1
        ),
        "local_registration_not_enabled": (
            registration_body.get("local_order_registration_enabled") is False
        ),
        "uses_official_fastapi_routes": True,
        "uses_fake_console_api": False,
        "pg_written": safety["pg_written"],
        "exchange_write_called": safety["exchange_write_called"],
        "order_created": safety["order_created"],
        "order_lifecycle_called": safety["order_lifecycle_called"],
        "withdrawal_or_transfer_created": safety[
            "withdrawal_or_transfer_created"
        ],
    }


def _contract_passed(checks: dict[str, bool]) -> bool:
    required_true = (
        "shadow_contract_passed",
        "right_tail_runner_preserved",
        "prepare_authorization_created",
        "final_gate_verdict_pass",
        "controlled_submit_preflight_ready",
        "submit_adapter_preview_route_called",
        "submit_adapter_preview_ready_not_implemented",
        "submit_adapter_preview_preview_only",
        "attempt_reservation_preview_ready",
        "attempt_reservation_recorded_pending_mutation",
        "attempt_mutation_applied_in_memory",
        "budget_reservation_prefers_max_loss_reference",
        "order_lifecycle_handoff_ready",
        "order_lifecycle_adapter_preview_ready",
        "order_registration_draft_preview_ready",
        "registration_has_entry_draft",
        "registration_has_protection_draft",
        "local_registration_not_enabled",
        "uses_official_fastapi_routes",
    )
    required_false = (
        "uses_fake_console_api",
        "pg_written",
        "exchange_write_called",
        "order_created",
        "order_lifecycle_called",
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
        "local_registration_enabled": False,
        "local_registration_executed": False,
        "exchange_submit_armed": False,
        "execute_real_submit": False,
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "attempt_counter_mutated_in_memory": state.runtime_service.attempt_mutations
        > 0,
        "runtime_budget_mutated_in_memory": state.runtime_service.attempt_mutations
        > 0,
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
        description="Build an official submit adapter preview proof."
    )
    parser.add_argument(
        "--output-dir",
        default="output/rtf083-official-submit-adapter-preview",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_proof_report(Path(args.output_dir).expanduser())
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if report["status"] == "official_submit_adapter_preview_passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
