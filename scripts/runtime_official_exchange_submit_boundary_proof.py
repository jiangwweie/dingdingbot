#!/usr/bin/env python3
"""Official exchange-submit packet and action-boundary proof.

RTF-085 extends the RTF-084 scoped local CREATED-order registration proof into
the exchange-submit boundary. It builds the exchange submit packet preview,
records scoped exchange-submit action authorization, verifies exchange-submit
enablement, and acquires the exchange-submit adapter lock. It does not call
ExchangeGateway, submit exchange orders, call OrderLifecycle.submit_order,
change ExecutionIntent status, open/close positions, withdraw, or transfer.
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
from scripts.runtime_official_scoped_local_registration_proof import (  # noqa: E402
    LOCAL_ORDER_REGISTRATION_ENABLEMENT_ID,
    ORDER_LIFECYCLE_ADAPTER_ENABLEMENT_ID,
    _body,
    _request,
    _signal_evaluation_from_candidate,
    _write_json,
)
from scripts.runtime_official_server_prepare_integration_proof import (  # noqa: E402
    _CreateGetRepo,
    _TestClientApiClient,
    _configure_auth_env,
    _login,
    _temporary_api_injections,
)
from scripts.runtime_official_submit_adapter_preview_proof import (  # noqa: E402
    _rtf083_state,
)
from src.domain.signal_evaluation import OrderCandidate, SignalEvaluation  # noqa: E402


OWNER_REAL_SUBMIT_AUTHORIZATION_ID = "owner-real-submit-authorization-rtf085"
ORDER_LIFECYCLE_SUBMIT_ENABLEMENT_ID = "order-lifecycle-submit-enable-rtf085"
EXCHANGE_SUBMIT_ADAPTER_ENABLEMENT_ID = "exchange-submit-adapter-enable-rtf085"
DEPLOYMENT_READINESS_EVIDENCE_ID = "deployment-readiness-rtf085-local"


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
    exchange_adapter_result_repo = _ExchangeSubmitAdapterResultRepo()
    state.adapter_service._order_lifecycle_service = lifecycle
    state.adapter_service._local_registration_action_authorization_repository = (
        _CreateGetRepo("action_authorization_id")
    )
    state.adapter_service._exchange_submit_action_authorization_repository = (
        _CreateGetRepo("action_authorization_id")
    )
    state.adapter_service._exchange_submit_adapter_result_repository = (
        exchange_adapter_result_repo
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
                    f"rtf085_login_failed:{login.status_code}:{login.text}"
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
                raise RuntimeError("rtf085_authorization_id_missing")

            local_stage = _run_local_registration_stage(
                api_client=api_client,
                authorization_id=authorization_id,
                prepare_report=prepare_report,
                state=state,
            )
            exchange_packet_preview = _request(
                api_client,
                "GET",
                (
                    "/api/trading-console/"
                    "runtime-execution-exchange-submit-packet-previews/"
                    f"authorizations/{authorization_id}"
                ),
            )
            exchange_evidence_ids = _exchange_evidence_ids(
                prepare_report=prepare_report,
                local_stage=local_stage,
            )
            exchange_action_authorization = _request(
                api_client,
                "POST",
                (
                    "/api/trading-console/"
                    "runtime-execution-exchange-submit-action-authorizations/"
                    f"authorizations/{authorization_id}"
                ),
                query={
                    **exchange_evidence_ids,
                    "owner_confirmed_for_exchange_submit_action": True,
                    "owner_operator_id": "owner",
                    "reason": (
                        "RTF-085 owner-scoped exchange submit action boundary"
                    ),
                    "owner_confirmation_reference": (
                        "owner-authorized-rtf085-exchange-submit-boundary"
                    ),
                },
            )
            exchange_submit_enablement = _request(
                api_client,
                "GET",
                (
                    "/api/trading-console/"
                    "runtime-execution-exchange-submit-enablements/"
                    f"authorizations/{authorization_id}"
                ),
                query={
                    **exchange_evidence_ids,
                    "exchange_submit_action_authorization_id": (
                        _body(exchange_action_authorization).get(
                            "action_authorization_id"
                        )
                    ),
                },
            )
            exchange_adapter_result = _request(
                api_client,
                "POST",
                (
                    "/api/trading-console/"
                    "runtime-execution-exchange-submit-adapter-results/"
                    f"authorizations/{authorization_id}"
                ),
                query={
                    **exchange_evidence_ids,
                    "exchange_submit_action_authorization_id": (
                        _body(exchange_action_authorization).get(
                            "action_authorization_id"
                        )
                    ),
                    "exchange_submit_adapter_enabled": True,
                },
            )

    packet = _exchange_submit_boundary_packet(
        shadow_report=shadow_report,
        prepare_report=prepare_report,
        local_stage=local_stage,
        exchange_packet_preview=exchange_packet_preview,
        exchange_action_authorization=exchange_action_authorization,
        exchange_submit_enablement=exchange_submit_enablement,
        exchange_adapter_result=exchange_adapter_result,
        lifecycle=lifecycle,
        exchange_adapter_result_repo=exchange_adapter_result_repo,
    )
    artifacts = {
        "prepare-report.json": prepare_report,
        "controlled-submit-preflight.json": local_stage[
            "controlled_submit_preflight"
        ],
        "submit-adapter-preview.json": local_stage["submit_adapter_preview"],
        "attempt-reservation.json": local_stage["attempt_reservation"],
        "attempt-mutation.json": local_stage["attempt_mutation"],
        "attempt-outcome-policy.json": local_stage["attempt_outcome_policy"],
        "order-lifecycle-handoff.json": local_stage["order_lifecycle_handoff"],
        "order-registration-draft-preview.json": local_stage[
            "order_registration_draft_preview"
        ],
        "local-registration-action-authorization.json": local_stage[
            "local_action_authorization"
        ],
        "local-registration-enablement.json": local_stage[
            "local_registration_enablement"
        ],
        "local-registration-adapter-result.json": local_stage["adapter_result"],
        "exchange-submit-packet-preview.json": exchange_packet_preview,
        "exchange-submit-action-authorization.json": exchange_action_authorization,
        "exchange-submit-enablement.json": exchange_submit_enablement,
        "exchange-submit-adapter-result.json": exchange_adapter_result,
        "exchange-submit-boundary-packet.json": packet,
    }
    for name, payload in artifacts.items():
        _write_json(output_dir / name, payload)

    report = {
        "scope": "runtime_official_exchange_submit_boundary_proof",
        "status": (
            "official_exchange_submit_boundary_passed"
            if _contract_passed(packet["checks"])
            else "blocked"
        ),
        "runtime_instance_id": "runtime-rtf075-cpm-long",
        "order_candidate_id": "order-candidate-rtf075-contract",
        "authorization_id": (packet["ids"] or {}).get("authorization_id"),
        "execution_intent_id": (packet["ids"] or {}).get("execution_intent_id"),
        "exchange_submit_packet_preview_id": (packet["ids"] or {}).get(
            "exchange_submit_packet_preview_id"
        ),
        "exchange_submit_action_authorization_id": (packet["ids"] or {}).get(
            "exchange_submit_action_authorization_id"
        ),
        "exchange_submit_enablement_decision_id": (packet["ids"] or {}).get(
            "exchange_submit_enablement_decision_id"
        ),
        "exchange_submit_adapter_result_id": (packet["ids"] or {}).get(
            "exchange_submit_adapter_result_id"
        ),
        "exchange_submit_boundary_packet": packet,
        "shadow_contract": shadow_report,
        "first_real_submit_prepare_report": prepare_report,
        "local_registration_stage": local_stage,
        "exchange_submit_packet_preview": exchange_packet_preview,
        "exchange_submit_action_authorization": exchange_action_authorization,
        "exchange_submit_enablement": exchange_submit_enablement,
        "exchange_submit_adapter_result": exchange_adapter_result,
        "checks": packet["checks"],
        "safety_invariants": packet["safety_invariants"],
        "operator_command_plan": {
            "next_step": (
                "build_exchange_submit_execution_result_boundary"
                if _contract_passed(packet["checks"])
                else "resolve_exchange_submit_boundary_blockers"
            ),
            "uses_official_fastapi_routes": True,
            "uses_fake_console_api": False,
            "live_submit_allowed": False,
            "exchange_submit_execution_enabled": False,
            "calls_exchange_gateway": False,
            "calls_order_lifecycle_submit": False,
            "executes_real_submit": False,
        },
        "right_tail_objective_context": {
            "small_bounded_losses_allowed_after_runtime_gate": True,
            "attempt_budget_prefers_max_loss_reference": (
                packet["runtime_attempt_budget_boundary"].get(
                    "budget_reservation_basis"
                )
                == "max_loss_reference"
            ),
            "automatic_compounding_assumed": False,
            "automatic_withdrawal_assumed": False,
            "not_proven_alpha": True,
        },
    }
    _write_json(output_dir / "contract-report.json", report)
    return report


class _InMemoryOrderLifecycleService:
    def __init__(self) -> None:
        self.orders: dict[str, Any] = {}
        self.register_calls: list[dict[str, Any]] = []
        self.submit_calls: list[dict[str, Any]] = []

    async def register_created_order(self, order: Any, *, metadata: Any = None) -> Any:
        self.orders[str(order.id)] = order
        self.register_calls.append(
            {
                "order": order,
                "metadata": dict(metadata or {}),
            }
        )
        return order

    async def get_order(self, order_id: str) -> Any | None:
        return self.orders.get(str(order_id))

    async def submit_order(
        self,
        order_id: str,
        exchange_order_id: str | None = None,
    ) -> Any:
        self.submit_calls.append(
            {
                "order_id": order_id,
                "exchange_order_id": exchange_order_id,
            }
        )
        raise AssertionError("RTF-085 must not call OrderLifecycle.submit_order")


class _ExchangeSubmitAdapterResultRepo:
    def __init__(self) -> None:
        self.items: dict[str, Any] = {}
        self.acquire_calls = 0
        self.complete_calls = 0

    async def get_by_authorization_id(self, authorization_id: str) -> Any | None:
        return self.items.get(str(authorization_id))

    async def acquire_exchange_submit_lock(self, result: Any) -> tuple[bool, Any]:
        self.acquire_calls += 1
        key = str(result.authorization_id)
        existing = self.items.get(key)
        if existing is not None:
            return False, existing
        self.items[key] = result
        return True, result

    async def complete_exchange_submit_result(self, result: Any) -> Any:
        self.complete_calls += 1
        self.items[str(result.authorization_id)] = result
        return result


def _prepare_candidate(
    *,
    api_client: _TestClientApiClient,
    candidate: OrderCandidate,
) -> dict[str, Any]:
    flow = FirstRealSubmitApiFlow(
        client=api_client,
        config=FlowConfig(
            api_base="testclient://rtf085-exchange-submit-boundary",
            mode="prepare",
            order_candidate_id=candidate.order_candidate_id,
            next_attempt_symbol=candidate.symbol,
            next_attempt_side=candidate.side,
            next_attempt_strategy_family_id=candidate.strategy_family_id,
            next_attempt_carrier_id=candidate.strategy_family_version_id,
            owner_operator_id="owner",
            owner_confirmation_reference=(
                "owner-reviewed-rtf085-exchange-submit-boundary"
            ),
            reason="RTF-085 official exchange submit boundary proof",
        ),
    )
    return flow.run()


def _run_local_registration_stage(
    *,
    api_client: _TestClientApiClient,
    authorization_id: str,
    prepare_report: dict[str, Any],
    state: Any,
) -> dict[str, Any]:
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
        raise RuntimeError("rtf085_reservation_id_missing")
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
    evidence_ids = _local_registration_evidence_ids(
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
            "reason": "RTF-085 prerequisite local CREATED-order registration",
            "owner_confirmation_reference": (
                "owner-authorized-rtf085-local-registration-prerequisite"
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
                _body(local_action_authorization).get("action_authorization_id")
            ),
        },
    )
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
                _body(local_action_authorization).get("action_authorization_id")
            ),
            "order_lifecycle_adapter_enabled": True,
            "local_order_registration_enabled": True,
        },
    )
    return {
        "controlled_submit_preflight": controlled_submit_preflight,
        "submit_adapter_preview": submit_adapter_preview,
        "attempt_reservation": attempt_reservation,
        "attempt_mutation": attempt_mutation,
        "attempt_outcome_policy": attempt_outcome_policy,
        "order_lifecycle_handoff": order_lifecycle_handoff,
        "order_registration_draft_preview": order_registration_draft_preview,
        "local_action_authorization": local_action_authorization,
        "local_registration_enablement": local_registration_enablement,
        "adapter_result": adapter_result,
    }


def _local_registration_evidence_ids(
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


def _exchange_evidence_ids(
    *,
    prepare_report: dict[str, Any],
    local_stage: dict[str, Any],
) -> dict[str, Any]:
    ids = dict(prepare_report.get("ids") or {})
    return {
        "trusted_submit_fact_snapshot_id": ids.get(
            "trusted_submit_fact_snapshot_id"
        ),
        "submit_idempotency_policy_id": ids.get("submit_idempotency_policy_id"),
        "attempt_outcome_policy_id": _body(
            local_stage["attempt_outcome_policy"]
        ).get("policy_id"),
        "protection_creation_failure_policy_id": ids.get(
            "protection_creation_failure_policy_id"
        ),
        "local_registration_enablement_decision_id": _body(
            local_stage["local_registration_enablement"]
        ).get("decision_id"),
        "owner_real_submit_authorization_id": OWNER_REAL_SUBMIT_AUTHORIZATION_ID,
        "order_lifecycle_submit_enablement_id": (
            ORDER_LIFECYCLE_SUBMIT_ENABLEMENT_ID
        ),
        "exchange_submit_adapter_enablement_id": (
            EXCHANGE_SUBMIT_ADAPTER_ENABLEMENT_ID
        ),
        "deployment_readiness_evidence_id": DEPLOYMENT_READINESS_EVIDENCE_ID,
    }


def _exchange_submit_boundary_packet(
    *,
    shadow_report: dict[str, Any],
    prepare_report: dict[str, Any],
    local_stage: dict[str, Any],
    exchange_packet_preview: dict[str, Any],
    exchange_action_authorization: dict[str, Any],
    exchange_submit_enablement: dict[str, Any],
    exchange_adapter_result: dict[str, Any],
    lifecycle: _InMemoryOrderLifecycleService,
    exchange_adapter_result_repo: _ExchangeSubmitAdapterResultRepo,
) -> dict[str, Any]:
    checks = _checks(
        shadow_report=shadow_report,
        prepare_report=prepare_report,
        local_stage=local_stage,
        exchange_packet_preview=exchange_packet_preview,
        exchange_action_authorization=exchange_action_authorization,
        exchange_submit_enablement=exchange_submit_enablement,
        exchange_adapter_result=exchange_adapter_result,
        lifecycle=lifecycle,
        exchange_adapter_result_repo=exchange_adapter_result_repo,
    )
    exchange_packet_body = _body(exchange_packet_preview)
    action_body = _body(exchange_action_authorization)
    enablement_body = _body(exchange_submit_enablement)
    adapter_body = _body(exchange_adapter_result)
    local_adapter_body = _body(local_stage["adapter_result"])
    mutation_body = _body(local_stage["attempt_mutation"])
    return {
        "scope": "runtime_official_exchange_submit_boundary_packet",
        "status": (
            "exchange_submit_adapter_armed_boundary"
            if _contract_passed(checks)
            else "blocked"
        ),
        "ids": {
            **dict(prepare_report.get("ids") or {}),
            "attempt_reservation_id": _body(
                local_stage["attempt_reservation"]
            ).get("reservation_id"),
            "attempt_mutation_id": mutation_body.get("mutation_id"),
            "attempt_outcome_policy_id": _body(
                local_stage["attempt_outcome_policy"]
            ).get("policy_id"),
            "local_registration_enablement_decision_id": _body(
                local_stage["local_registration_enablement"]
            ).get("decision_id"),
            "local_registration_adapter_result_id": local_adapter_body.get(
                "adapter_result_id"
            ),
            "exchange_submit_packet_preview_id": exchange_packet_body.get(
                "packet_preview_id"
            ),
            "exchange_submit_action_authorization_id": action_body.get(
                "action_authorization_id"
            ),
            "exchange_submit_enablement_decision_id": enablement_body.get(
                "decision_id"
            ),
            "exchange_submit_adapter_result_id": adapter_body.get(
                "adapter_result_id"
            ),
        },
        "statuses": {
            "local_registration_adapter_result": local_adapter_body.get("status"),
            "exchange_submit_packet_preview": exchange_packet_body.get("status"),
            "exchange_submit_action_authorization": action_body.get("status"),
            "exchange_submit_enablement": enablement_body.get("status"),
            "exchange_submit_adapter_result": adapter_body.get("status"),
        },
        "exchange_submit_packet": {
            "local_order_count": exchange_packet_body.get("local_order_count"),
            "submit_request_count": len(
                exchange_packet_body.get("submit_request_previews") or []
            ),
            "entry_submit_request_count": exchange_packet_body.get(
                "entry_submit_request_count"
            ),
            "protection_submit_request_count": exchange_packet_body.get(
                "protection_submit_request_count"
            ),
            "entry_order_id": exchange_packet_body.get("entry_order_id"),
            "local_order_ids": list(exchange_packet_body.get("local_order_ids") or []),
            "protection_order_ids": list(
                exchange_packet_body.get("protection_order_ids") or []
            ),
            "exchange_payload_created": False,
            "exchange_order_id_assigned": False,
        },
        "exchange_submit_boundary": {
            "duplicate_submit_lock_acquired": adapter_body.get(
                "duplicate_submit_lock_acquired"
            ),
            "exchange_submit_adapter_enabled": adapter_body.get(
                "exchange_submit_adapter_enabled"
            ),
            "exchange_submit_action_authorized": adapter_body.get(
                "exchange_submit_action_authorized"
            ),
            "exchange_submit_adapter_implemented": adapter_body.get(
                "exchange_submit_adapter_implemented"
            ),
            "exchange_called": adapter_body.get("exchange_called"),
            "exchange_order_submitted": adapter_body.get(
                "exchange_order_submitted"
            ),
            "order_lifecycle_submit_called": adapter_body.get(
                "order_lifecycle_submit_called"
            ),
            "exchange_result_repo_acquire_calls": (
                exchange_adapter_result_repo.acquire_calls
            ),
            "exchange_result_repo_complete_calls": (
                exchange_adapter_result_repo.complete_calls
            ),
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
        "safety_invariants": _safety_invariants(
            lifecycle=lifecycle,
            exchange_adapter_result=exchange_adapter_result,
        ),
    }


def _checks(
    *,
    shadow_report: dict[str, Any],
    prepare_report: dict[str, Any],
    local_stage: dict[str, Any],
    exchange_packet_preview: dict[str, Any],
    exchange_action_authorization: dict[str, Any],
    exchange_submit_enablement: dict[str, Any],
    exchange_adapter_result: dict[str, Any],
    lifecycle: _InMemoryOrderLifecycleService,
    exchange_adapter_result_repo: _ExchangeSubmitAdapterResultRepo,
) -> dict[str, bool]:
    local_adapter_body = _body(local_stage["adapter_result"])
    packet_body = _body(exchange_packet_preview)
    action_body = _body(exchange_action_authorization)
    enablement_body = _body(exchange_submit_enablement)
    adapter_body = _body(exchange_adapter_result)
    mutation_body = _body(local_stage["attempt_mutation"])
    safety = _safety_invariants(
        lifecycle=lifecycle,
        exchange_adapter_result=exchange_adapter_result,
    )
    return {
        "shadow_contract_passed": (
            shadow_report.get("status")
            == "ready_signal_shadow_planning_contract_passed"
        ),
        "prepare_authorization_created": bool(
            (prepare_report.get("ids") or {}).get("authorization_id")
        ),
        "local_adapter_registered_created_orders": (
            local_adapter_body.get("status") == "registered_created_local_orders"
        ),
        "local_registered_two_orders": (
            local_adapter_body.get("registered_order_count") == 2
        ),
        "local_orders_available_for_packet": len(lifecycle.orders) == 2,
        "local_order_lifecycle_submit_not_called": len(lifecycle.submit_calls) == 0,
        "exchange_packet_preview_ready": (
            packet_body.get("status")
            == "ready_for_exchange_submit_adapter_design"
        ),
        "exchange_packet_has_two_requests": (
            len(packet_body.get("submit_request_previews") or []) == 2
        ),
        "exchange_packet_has_entry_request": (
            packet_body.get("entry_submit_request_count") == 1
        ),
        "exchange_packet_has_protection_request": (
            packet_body.get("protection_submit_request_count") == 1
        ),
        "exchange_packet_preview_only": packet_body.get("preview_only") is True,
        "exchange_action_authorization_approved": (
            action_body.get("status") == "approved_for_exchange_submit_action"
        ),
        "exchange_enablement_ready": (
            enablement_body.get("status") == "ready_for_exchange_submit_action"
        ),
        "exchange_adapter_result_armed": (
            adapter_body.get("status") == "exchange_submit_adapter_armed"
        ),
        "exchange_duplicate_lock_acquired": (
            adapter_body.get("duplicate_submit_lock_acquired") is True
        ),
        "exchange_adapter_lock_repo_used": (
            exchange_adapter_result_repo.acquire_calls == 1
            and exchange_adapter_result_repo.complete_calls == 1
        ),
        "attempt_budget_uses_max_loss_reference": (
            (mutation_body.get("metadata") or {}).get("budget_reservation_basis")
            == "max_loss_reference"
        ),
        "uses_official_fastapi_routes": True,
        "uses_fake_console_api": False,
        "pg_written": safety["pg_written"],
        "exchange_write_called": safety["exchange_write_called"],
        "exchange_order_submitted": safety["exchange_order_submitted"],
        "order_lifecycle_submit_called": safety[
            "order_lifecycle_submit_called"
        ],
        "execution_intent_status_changed": safety[
            "execution_intent_status_changed"
        ],
        "withdrawal_or_transfer_created": safety[
            "withdrawal_or_transfer_created"
        ],
    }


def _contract_passed(checks: dict[str, bool]) -> bool:
    required_true = (
        "shadow_contract_passed",
        "prepare_authorization_created",
        "local_adapter_registered_created_orders",
        "local_registered_two_orders",
        "local_orders_available_for_packet",
        "local_order_lifecycle_submit_not_called",
        "exchange_packet_preview_ready",
        "exchange_packet_has_two_requests",
        "exchange_packet_has_entry_request",
        "exchange_packet_has_protection_request",
        "exchange_packet_preview_only",
        "exchange_action_authorization_approved",
        "exchange_enablement_ready",
        "exchange_adapter_result_armed",
        "exchange_duplicate_lock_acquired",
        "exchange_adapter_lock_repo_used",
        "attempt_budget_uses_max_loss_reference",
        "uses_official_fastapi_routes",
    )
    required_false = (
        "uses_fake_console_api",
        "pg_written",
        "exchange_write_called",
        "exchange_order_submitted",
        "order_lifecycle_submit_called",
        "execution_intent_status_changed",
        "withdrawal_or_transfer_created",
    )
    return all(checks.get(key) is True for key in required_true) and all(
        checks.get(key) is False for key in required_false
    )


def _safety_invariants(
    *,
    lifecycle: _InMemoryOrderLifecycleService,
    exchange_adapter_result: dict[str, Any],
) -> dict[str, bool]:
    adapter_body = _body(exchange_adapter_result)
    return {
        "uses_official_fastapi_routes": True,
        "uses_fake_console_api": False,
        "uses_in_memory_repositories": True,
        "pg_written": False,
        "local_created_orders_registered": len(lifecycle.register_calls) == 2,
        "order_lifecycle_register_call_count": len(lifecycle.register_calls),
        "order_lifecycle_submit_called": (
            adapter_body.get("order_lifecycle_submit_called") is True
            or bool(lifecycle.submit_calls)
        ),
        "exchange_submit_adapter_boundary_armed": (
            adapter_body.get("status") == "exchange_submit_adapter_armed"
        ),
        "exchange_submit_execution_enabled": False,
        "exchange_write_called": adapter_body.get("exchange_called") is True,
        "exchange_order_submitted": (
            adapter_body.get("exchange_order_submitted") is True
        ),
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


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an official exchange submit boundary proof."
    )
    parser.add_argument(
        "--output-dir",
        default="output/rtf085-official-exchange-submit-boundary",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_proof_report(Path(args.output_dir).expanduser())
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if report["status"] == "official_exchange_submit_boundary_passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
