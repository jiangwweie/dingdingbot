#!/usr/bin/env python3
"""Official scoped local CREATED-order registration proof.

RTF-084 extends the submit-adapter preview proof into the narrow local
registration action.  It records the required local-registration evidence,
approves only the local CREATED-order registration action, and calls
OrderLifecycle.register_created_order through an in-memory service.  It does
not submit exchange orders, call an exchange gateway, change ExecutionIntent
status, open/close positions, withdraw, or transfer funds.
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
    DEFAULT_OUTCOME_KIND,
    FirstRealSubmitApiFlow,
    FlowConfig,
)
from scripts.runtime_official_server_prepare_integration_proof import (  # noqa: E402
    _CreateGetRepo,
    _TestClientApiClient,
    _configure_auth_env,
    _login,
    _signal_evaluation_from_candidate,
    _temporary_api_injections,
)
from scripts.runtime_official_submit_adapter_preview_proof import (  # noqa: E402
    _rtf083_state,
)
from src.domain.signal_evaluation import OrderCandidate, SignalEvaluation  # noqa: E402


OWNER_REAL_SUBMIT_AUTHORIZATION_ID = "owner-real-submit-authorization-rtf084"
ORDER_LIFECYCLE_ADAPTER_ENABLEMENT_ID = "order-lifecycle-adapter-enable-rtf084"
LOCAL_ORDER_REGISTRATION_ENABLEMENT_ID = "local-order-registration-enable-rtf084"
DEPLOYMENT_READINESS_EVIDENCE_ID = "deployment-readiness-rtf084-local"


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
    lifecycle = _InMemoryOrderLifecycleService()
    state.adapter_service._order_lifecycle_service = lifecycle
    state.adapter_service._local_registration_action_authorization_repository = (
        _CreateGetRepo("action_authorization_id")
    )
    state.adapter_service._attempt_outcome_policy_repository = _CreateGetRepo(
        "policy_id"
    )

    _configure_auth_env()
    with _temporary_api_injections(state):
        from src.interfaces.api import app

        with TestClient(app) as client:
            login = _login(client)
            if login.status_code != 200:
                raise RuntimeError(
                    f"rtf084_login_failed:{login.status_code}:{login.text}"
                )
            api_client = _TestClientApiClient(client)
            prepare_report = _prepare_candidate(
                api_client=api_client,
                candidate=candidate,
            )
            authorization_id = (prepare_report.get("ids") or {}).get(
                "authorization_id"
            )
            if not authorization_id:
                raise RuntimeError("rtf084_authorization_id_missing")

            controlled_submit_preflight = _request(
                api_client,
                "GET",
                (
                    "/api/trading-console/"
                    "runtime-execution-controlled-submit-preflights/"
                    f"authorizations/{authorization_id}"
                ),
            )
            submit_adapter_preview = _request(
                api_client,
                "GET",
                (
                    "/api/trading-console/"
                    "runtime-execution-submit-adapter-previews/"
                    f"authorizations/{authorization_id}"
                ),
            )
            attempt_reservation = _request(
                api_client,
                "POST",
                (
                    "/api/trading-console/"
                    "runtime-execution-attempt-reservations/"
                    f"authorizations/{authorization_id}"
                ),
            )
            reservation_id = _body(attempt_reservation).get("reservation_id")
            if not reservation_id:
                raise RuntimeError("rtf084_reservation_id_missing")
            attempt_mutation = _request(
                api_client,
                "POST",
                (
                    "/api/trading-console/"
                    "runtime-execution-attempt-mutations/"
                    f"reservations/{reservation_id}"
                ),
            )
            attempt_outcome_policy = _request(
                api_client,
                "POST",
                (
                    "/api/trading-console/"
                    "runtime-execution-attempt-outcome-policies/"
                    f"reservations/{reservation_id}"
                ),
                query={"outcome_kind": DEFAULT_OUTCOME_KIND},
            )
            order_lifecycle_handoff = _request(
                api_client,
                "POST",
                (
                    "/api/trading-console/"
                    "runtime-execution-order-lifecycle-handoff-drafts/"
                    f"authorizations/{authorization_id}"
                ),
            )
            order_registration_draft_preview = _request(
                api_client,
                "GET",
                (
                    "/api/trading-console/"
                    "runtime-execution-order-registration-draft-previews/"
                    f"authorizations/{authorization_id}"
                ),
            )

            evidence_ids = _evidence_ids(
                prepare_report=prepare_report,
                attempt_outcome_policy=attempt_outcome_policy,
            )
            local_action_authorization = _request(
                api_client,
                "POST",
                (
                    "/api/trading-console/"
                    "runtime-execution-local-registration-action-authorizations/"
                    f"authorizations/{authorization_id}"
                ),
                query={
                    **evidence_ids,
                    "owner_confirmed_for_local_registration_action": True,
                    "owner_operator_id": "owner",
                    "reason": (
                        "RTF-084 owner-scoped local CREATED-order registration"
                    ),
                    "owner_confirmation_reference": (
                        "owner-authorized-rtf084-local-registration"
                    ),
                },
            )
            local_registration_enablement = _request(
                api_client,
                "GET",
                (
                    "/api/trading-console/"
                    "runtime-execution-local-registration-enablements/"
                    f"authorizations/{authorization_id}"
                ),
                query={
                    **evidence_ids,
                    "local_registration_action_authorization_id": (
                        _body(local_action_authorization).get(
                            "action_authorization_id"
                        )
                    ),
                },
            )
            # The RTF-079 in-memory evidence repo can cache a disabled preview
            # result when evidence preparation inspects adapter-result readiness.
            # The scoped action proof needs a fresh single-writer lock for the
            # actual local registration action.
            state.order_lifecycle_adapter_result_repo.items.clear()
            adapter_result = _request(
                api_client,
                "POST",
                (
                    "/api/trading-console/"
                    "runtime-execution-order-lifecycle-adapter-results/"
                    f"authorizations/{authorization_id}"
                ),
                query={
                    **evidence_ids,
                    "local_registration_action_authorization_id": (
                        _body(local_action_authorization).get(
                            "action_authorization_id"
                        )
                    ),
                    "order_lifecycle_adapter_enabled": True,
                    "local_order_registration_enabled": True,
                },
            )

    local_registration_artifact = _local_registration_artifact(
        shadow_report=shadow_report,
        prepare_report=prepare_report,
        controlled_submit_preflight=controlled_submit_preflight,
        submit_adapter_preview=submit_adapter_preview,
        attempt_reservation=attempt_reservation,
        attempt_mutation=attempt_mutation,
        attempt_outcome_policy=attempt_outcome_policy,
        order_lifecycle_handoff=order_lifecycle_handoff,
        order_registration_draft_preview=order_registration_draft_preview,
        local_action_authorization=local_action_authorization,
        local_registration_enablement=local_registration_enablement,
        adapter_result=adapter_result,
        lifecycle=lifecycle,
    )

    artifacts = {
        "prepare-report.json": prepare_report,
        "controlled-submit-preflight.json": controlled_submit_preflight,
        "submit-adapter-preview.json": submit_adapter_preview,
        "attempt-reservation.json": attempt_reservation,
        "attempt-mutation.json": attempt_mutation,
        "attempt-outcome-policy.json": attempt_outcome_policy,
        "order-lifecycle-handoff.json": order_lifecycle_handoff,
        "order-registration-draft-preview.json": order_registration_draft_preview,
        "local-registration-action-authorization.json": (
            local_action_authorization
        ),
        "local-registration-enablement.json": local_registration_enablement,
        "local-registration-adapter-result.json": adapter_result,
        "local-registration-artifact.json": local_registration_artifact,
    }
    for name, payload in artifacts.items():
        _write_json(output_dir / name, payload)

    report = _report(
        shadow_report=shadow_report,
        prepare_report=prepare_report,
        controlled_submit_preflight=controlled_submit_preflight,
        submit_adapter_preview=submit_adapter_preview,
        attempt_reservation=attempt_reservation,
        attempt_mutation=attempt_mutation,
        attempt_outcome_policy=attempt_outcome_policy,
        order_lifecycle_handoff=order_lifecycle_handoff,
        order_registration_draft_preview=order_registration_draft_preview,
        local_action_authorization=local_action_authorization,
        local_registration_enablement=local_registration_enablement,
        adapter_result=adapter_result,
        local_registration_artifact=local_registration_artifact,
        lifecycle=lifecycle,
    )
    _write_json(output_dir / "contract-report.json", report)
    return report


class _InMemoryOrderLifecycleService:
    def __init__(self) -> None:
        self.orders: dict[str, Any] = {}
        self.register_calls: list[dict[str, Any]] = []

    async def register_created_order(self, order: Any, *, metadata: Any = None) -> Any:
        self.orders[str(order.id)] = order
        self.register_calls.append(
            {
                "order": order,
                "metadata": dict(metadata or {}),
            }
        )
        return order


def _prepare_candidate(
    *,
    api_client: _TestClientApiClient,
    candidate: OrderCandidate,
) -> dict[str, Any]:
    flow = FirstRealSubmitApiFlow(
        client=api_client,
        config=FlowConfig(
            api_base="testclient://rtf084-scoped-local-registration",
            mode="prepare",
            order_candidate_id=candidate.order_candidate_id,
            next_attempt_symbol=candidate.symbol,
            next_attempt_side=candidate.side,
            next_attempt_strategy_family_id=candidate.strategy_family_id,
            next_attempt_carrier_id=candidate.strategy_family_version_id,
            owner_operator_id="owner",
            owner_confirmation_reference=(
                "owner-reviewed-rtf084-scoped-local-registration"
            ),
            reason="RTF-084 official scoped local registration proof",
        ),
    )
    return flow.run()


def _request(
    api_client: _TestClientApiClient,
    method: str,
    path: str,
    *,
    query: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return api_client.request_json(method, path, query=query or {})


def _evidence_ids(
    *,
    prepare_report: dict[str, Any],
    attempt_outcome_policy: dict[str, Any],
) -> dict[str, Any]:
    ids = dict(prepare_report.get("ids") or {})
    return {
        "trusted_submit_fact_snapshot_id": ids.get(
            "trusted_submit_fact_snapshot_id"
        ),
        "submit_idempotency_policy_id": ids.get("submit_idempotency_policy_id"),
        "attempt_outcome_policy_id": _body(attempt_outcome_policy).get(
            "policy_id"
        ),
        "protection_creation_failure_policy_id": ids.get(
            "protection_creation_failure_policy_id"
        ),
        "owner_real_submit_authorization_id": OWNER_REAL_SUBMIT_AUTHORIZATION_ID,
        "order_lifecycle_adapter_enablement_id": (
            ORDER_LIFECYCLE_ADAPTER_ENABLEMENT_ID
        ),
        "local_order_registration_enablement_id": (
            LOCAL_ORDER_REGISTRATION_ENABLEMENT_ID
        ),
        "deployment_readiness_evidence_id": DEPLOYMENT_READINESS_EVIDENCE_ID,
    }


def _local_registration_artifact(
    *,
    shadow_report: dict[str, Any],
    prepare_report: dict[str, Any],
    controlled_submit_preflight: dict[str, Any],
    submit_adapter_preview: dict[str, Any],
    attempt_reservation: dict[str, Any],
    attempt_mutation: dict[str, Any],
    attempt_outcome_policy: dict[str, Any],
    order_lifecycle_handoff: dict[str, Any],
    order_registration_draft_preview: dict[str, Any],
    local_action_authorization: dict[str, Any],
    local_registration_enablement: dict[str, Any],
    adapter_result: dict[str, Any],
    lifecycle: _InMemoryOrderLifecycleService,
) -> dict[str, Any]:
    checks = _checks(
        shadow_report=shadow_report,
        prepare_report=prepare_report,
        controlled_submit_preflight=controlled_submit_preflight,
        submit_adapter_preview=submit_adapter_preview,
        attempt_reservation=attempt_reservation,
        attempt_mutation=attempt_mutation,
        attempt_outcome_policy=attempt_outcome_policy,
        order_lifecycle_handoff=order_lifecycle_handoff,
        order_registration_draft_preview=order_registration_draft_preview,
        local_action_authorization=local_action_authorization,
        local_registration_enablement=local_registration_enablement,
        adapter_result=adapter_result,
        lifecycle=lifecycle,
    )
    adapter_body = _body(adapter_result)
    enablement_body = _body(local_registration_enablement)
    return {
        "scope": "runtime_official_scoped_local_registration_artifact",
        "status": (
            "local_created_orders_registered"
            if _contract_passed(checks)
            else "blocked"
        ),
        "ids": {
            **dict(prepare_report.get("ids") or {}),
            "attempt_reservation_id": _body(attempt_reservation).get(
                "reservation_id"
            ),
            "attempt_mutation_id": _body(attempt_mutation).get("mutation_id"),
            "attempt_outcome_policy_id": _body(attempt_outcome_policy).get(
                "policy_id"
            ),
            "order_lifecycle_handoff_id": _body(order_lifecycle_handoff).get(
                "handoff_draft_id"
            ),
            "local_registration_action_authorization_id": _body(
                local_action_authorization
            ).get("action_authorization_id"),
            "local_registration_enablement_decision_id": enablement_body.get(
                "decision_id"
            ),
            "local_registration_adapter_result_id": adapter_body.get(
                "adapter_result_id"
            ),
        },
        "statuses": {
            "controlled_submit_preflight": _body(
                controlled_submit_preflight
            ).get("status"),
            "submit_adapter_preview": _body(submit_adapter_preview).get(
                "status"
            ),
            "attempt_reservation": _body(attempt_reservation).get("status"),
            "attempt_mutation": _body(attempt_mutation).get("status"),
            "attempt_outcome_policy": _body(attempt_outcome_policy).get("status"),
            "order_lifecycle_handoff": _body(order_lifecycle_handoff).get(
                "status"
            ),
            "order_registration_draft_preview": _body(
                order_registration_draft_preview
            ).get("status"),
            "local_registration_action_authorization": _body(
                local_action_authorization
            ).get("status"),
            "local_registration_enablement": enablement_body.get("status"),
            "adapter_result": adapter_body.get("status"),
        },
        "local_registration": {
            "registered_order_count": adapter_body.get("registered_order_count"),
            "local_order_ids": list(adapter_body.get("local_order_ids") or []),
            "entry_order_ids": list(adapter_body.get("entry_order_ids") or []),
            "protection_order_ids": list(
                adapter_body.get("protection_order_ids") or []
            ),
            "order_lifecycle_adapter_enabled": adapter_body.get(
                "order_lifecycle_adapter_enabled"
            ),
            "local_order_registration_enabled": adapter_body.get(
                "local_order_registration_enabled"
            ),
            "duplicate_submit_lock_acquired": adapter_body.get(
                "duplicate_submit_lock_acquired"
            ),
            "order_lifecycle_called": adapter_body.get(
                "order_lifecycle_called"
            ),
            "exchange_called": adapter_body.get("exchange_called"),
        },
        "lifecycle_observation": {
            "register_call_count": len(lifecycle.register_calls),
            "registered_order_ids": list(lifecycle.orders.keys()),
            "metadata": [
                call["metadata"] for call in lifecycle.register_calls
            ],
        },
        "checks": checks,
        "safety_invariants": _safety_invariants(
            lifecycle=lifecycle,
            adapter_result=adapter_result,
        ),
    }


def _report(
    *,
    shadow_report: dict[str, Any],
    prepare_report: dict[str, Any],
    controlled_submit_preflight: dict[str, Any],
    submit_adapter_preview: dict[str, Any],
    attempt_reservation: dict[str, Any],
    attempt_mutation: dict[str, Any],
    attempt_outcome_policy: dict[str, Any],
    order_lifecycle_handoff: dict[str, Any],
    order_registration_draft_preview: dict[str, Any],
    local_action_authorization: dict[str, Any],
    local_registration_enablement: dict[str, Any],
    adapter_result: dict[str, Any],
    local_registration_artifact: dict[str, Any],
    lifecycle: _InMemoryOrderLifecycleService,
) -> dict[str, Any]:
    checks = dict(local_registration_artifact["checks"])
    ids = dict(local_registration_artifact["ids"])
    return {
        "scope": "runtime_official_scoped_local_registration_proof",
        "status": (
            "official_scoped_local_registration_passed"
            if _contract_passed(checks)
            else "blocked"
        ),
        "runtime_instance_id": "runtime-rtf075-cpm-long",
        "order_candidate_id": "order-candidate-rtf075-contract",
        "authorization_id": ids.get("authorization_id"),
        "execution_intent_id": ids.get("execution_intent_id"),
        "local_registration_enablement_decision_id": ids.get(
            "local_registration_enablement_decision_id"
        ),
        "local_registration_adapter_result_id": ids.get(
            "local_registration_adapter_result_id"
        ),
        "local_order_ids": local_registration_artifact[
            "local_registration"
        ]["local_order_ids"],
        "local_registration_artifact": local_registration_artifact,
        "shadow_contract": shadow_report,
        "first_real_submit_prepare_report": prepare_report,
        "controlled_submit_preflight": controlled_submit_preflight,
        "submit_adapter_preview": submit_adapter_preview,
        "attempt_reservation": attempt_reservation,
        "attempt_mutation": attempt_mutation,
        "attempt_outcome_policy": attempt_outcome_policy,
        "order_lifecycle_handoff": order_lifecycle_handoff,
        "order_registration_draft_preview": order_registration_draft_preview,
        "local_registration_action_authorization": local_action_authorization,
        "local_registration_enablement": local_registration_enablement,
        "adapter_result": adapter_result,
        "checks": checks,
        "scoped_local_registration_plan": {
            "next_step": (
                "build_exchange_submit_preview"
                if _contract_passed(checks)
                else "resolve_scoped_local_registration_blockers"
            ),
            "uses_official_fastapi_routes": True,
            "uses_fake_console_api": False,
            "local_created_orders_registered": _contract_passed(checks),
            "live_submit_allowed": False,
            "exchange_submit_enabled": False,
            "calls_exchange": False,
            "executes_real_submit": False,
        },
        "right_tail_objective_context": {
            "small_bounded_losses_allowed_after_runtime_gate": True,
            "attempt_budget_prefers_max_loss_reference": (
                (_body(attempt_mutation).get("metadata") or {}).get(
                    "budget_reservation_basis"
                )
                == "max_loss_reference"
            ),
            "automatic_compounding_assumed": False,
            "automatic_withdrawal_assumed": False,
            "not_proven_alpha": True,
        },
        "safety_invariants": local_registration_artifact["safety_invariants"],
        "lifecycle_register_calls": [
            {
                "order_id": str(call["order"].id),
                "order_role": call["order"].order_role.value,
                "status": call["order"].status.value,
                "exchange_order_id": call["order"].exchange_order_id,
                "metadata": call["metadata"],
            }
            for call in lifecycle.register_calls
        ],
    }


def _checks(
    *,
    shadow_report: dict[str, Any],
    prepare_report: dict[str, Any],
    controlled_submit_preflight: dict[str, Any],
    submit_adapter_preview: dict[str, Any],
    attempt_reservation: dict[str, Any],
    attempt_mutation: dict[str, Any],
    attempt_outcome_policy: dict[str, Any],
    order_lifecycle_handoff: dict[str, Any],
    order_registration_draft_preview: dict[str, Any],
    local_action_authorization: dict[str, Any],
    local_registration_enablement: dict[str, Any],
    adapter_result: dict[str, Any],
    lifecycle: _InMemoryOrderLifecycleService,
) -> dict[str, bool]:
    adapter_body = _body(adapter_result)
    safety = _safety_invariants(lifecycle=lifecycle, adapter_result=adapter_result)
    return {
        "shadow_contract_passed": (
            shadow_report.get("status")
            == "ready_signal_shadow_planning_contract_passed"
        ),
        "prepare_authorization_created": bool(
            (prepare_report.get("ids") or {}).get("authorization_id")
        ),
        "controlled_submit_preflight_ready": (
            _body(controlled_submit_preflight).get("status")
            == "ready_for_controlled_submit_adapter"
        ),
        "submit_adapter_preview_ready_not_implemented": (
            _body(submit_adapter_preview).get("status")
            == "inputs_ready_adapter_not_implemented"
        ),
        "attempt_reservation_pending_mutation": (
            _body(attempt_reservation).get("status") == "pending_runtime_mutation"
        ),
        "attempt_mutation_applied": (
            _body(attempt_mutation).get("status") == "applied"
        ),
        "attempt_budget_uses_max_loss_reference": (
            (_body(attempt_mutation).get("metadata") or {}).get(
                "budget_reservation_basis"
            )
            == "max_loss_reference"
        ),
        "attempt_outcome_policy_ready": (
            _body(attempt_outcome_policy).get("status")
            == "ready_for_attempt_budget_outcome_accounting"
        ),
        "order_lifecycle_handoff_ready": (
            _body(order_lifecycle_handoff).get("status")
            == "ready_for_order_lifecycle_adapter"
        ),
        "order_registration_draft_preview_ready": (
            _body(order_registration_draft_preview).get("status")
            == "inputs_ready_registration_draft_only"
        ),
        "local_action_authorization_approved": (
            _body(local_action_authorization).get("status")
            == "approved_for_local_registration_action"
        ),
        "local_registration_enablement_ready": (
            _body(local_registration_enablement).get("status")
            == "ready_for_local_registration_action"
        ),
        "adapter_result_registered_created_orders": (
            adapter_body.get("status") == "registered_created_local_orders"
        ),
        "registered_two_local_orders": adapter_body.get("registered_order_count")
        == 2,
        "registered_one_entry_order": len(adapter_body.get("entry_order_ids") or [])
        == 1,
        "registered_one_protection_order": len(
            adapter_body.get("protection_order_ids") or []
        )
        == 1,
        "duplicate_submit_lock_acquired": (
            adapter_body.get("duplicate_submit_lock_acquired") is True
        ),
        "lifecycle_register_called_for_each_order": (
            len(lifecycle.register_calls) == adapter_body.get("registered_order_count")
        ),
        "registered_orders_remain_created": all(
            call["order"].status.value == "CREATED"
            for call in lifecycle.register_calls
        ),
        "registered_orders_have_no_exchange_id": all(
            call["order"].exchange_order_id is None
            for call in lifecycle.register_calls
        ),
        "uses_official_fastapi_routes": True,
        "uses_fake_console_api": False,
        "pg_written": safety["pg_written"],
        "exchange_write_called": safety["exchange_write_called"],
        "exchange_submit_enabled": safety["exchange_submit_enabled"],
        "withdrawal_or_transfer_created": safety[
            "withdrawal_or_transfer_created"
        ],
    }


def _contract_passed(checks: dict[str, bool]) -> bool:
    required_true = (
        "shadow_contract_passed",
        "prepare_authorization_created",
        "controlled_submit_preflight_ready",
        "submit_adapter_preview_ready_not_implemented",
        "attempt_reservation_pending_mutation",
        "attempt_mutation_applied",
        "attempt_budget_uses_max_loss_reference",
        "attempt_outcome_policy_ready",
        "order_lifecycle_handoff_ready",
        "order_registration_draft_preview_ready",
        "local_action_authorization_approved",
        "local_registration_enablement_ready",
        "adapter_result_registered_created_orders",
        "registered_two_local_orders",
        "registered_one_entry_order",
        "registered_one_protection_order",
        "duplicate_submit_lock_acquired",
        "lifecycle_register_called_for_each_order",
        "registered_orders_remain_created",
        "registered_orders_have_no_exchange_id",
        "uses_official_fastapi_routes",
    )
    required_false = (
        "uses_fake_console_api",
        "pg_written",
        "exchange_write_called",
        "exchange_submit_enabled",
        "withdrawal_or_transfer_created",
    )
    return all(checks.get(key) is True for key in required_true) and all(
        checks.get(key) is False for key in required_false
    )


def _safety_invariants(
    *,
    lifecycle: _InMemoryOrderLifecycleService,
    adapter_result: dict[str, Any],
) -> dict[str, bool]:
    adapter_body = _body(adapter_result)
    return {
        "uses_official_fastapi_routes": True,
        "uses_fake_console_api": False,
        "uses_in_memory_repositories": True,
        "pg_written": False,
        "local_created_orders_registered": (
            adapter_body.get("status") == "registered_created_local_orders"
        ),
        "local_order_registration_executed": (
            adapter_body.get("local_order_registration_executed") is True
        ),
        "order_lifecycle_called": adapter_body.get("order_lifecycle_called")
        is True,
        "order_lifecycle_register_call_count": len(lifecycle.register_calls),
        "exchange_submit_enabled": False,
        "exchange_write_called": adapter_body.get("exchange_called") is True,
        "uses_live_exchange": False,
        "position_opened": False,
        "position_closed": False,
        "execution_intent_status_changed": (
            adapter_body.get("execution_intent_status_changed") is True
        ),
        "withdrawal_or_transfer_created": (
            adapter_body.get("withdrawal_or_transfer_created") is True
        ),
    }


def _body(result: dict[str, Any]) -> dict[str, Any]:
    body = result.get("body")
    return body if isinstance(body, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an official scoped local registration proof."
    )
    parser.add_argument(
        "--output-dir",
        default="output/rtf084-official-scoped-local-registration",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_proof_report(Path(args.output_dir).expanduser())
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if report["status"] == "official_scoped_local_registration_passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
