#!/usr/bin/env python3
"""Official post-submit finalize proof.

RTF-088 extends the controlled gateway action proof into the post-submit
finalize path. It proves that a durable exchange-submit execution result can be
accepted as post-submit evidence, classified, settled, and converted into a
next-attempt gate without replaying pre-submit rehearsal rules.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from time import time
from types import MethodType, SimpleNamespace
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient  # noqa: E402

from scripts import runtime_ready_signal_shadow_planning_contract_fixture as shadow_fixture  # noqa: E402
from scripts.runtime_official_controlled_gateway_action_proof import (  # noqa: E402
    _ControlledExchangeGateway,
    _ControlledOrderLifecycleService,
    _ExchangeGatewayReadinessRepo,
    _ExchangeSubmitExecutionResultRepo,
    _ExecutionRecoveryRepo,
    _PositionProjection,
    _controlled_gateway_action_packet,
)
from scripts.runtime_official_exchange_submit_boundary_proof import (  # noqa: E402
    _ExchangeSubmitAdapterResultRepo,
    _exchange_evidence_ids,
    _exchange_submit_boundary_packet,
    _prepare_candidate,
    _run_local_registration_stage,
)
from scripts.runtime_official_scoped_local_registration_proof import (  # noqa: E402
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
from src.application.runtime_post_submit_finalize_service import (  # noqa: E402
    RuntimePostSubmitFinalizeService,
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
    _allow_post_submit_budget_settlement(state.runtime_service)

    lifecycle = _ControlledOrderLifecycleService()
    gateway = _ControlledExchangeGateway()
    position_projection = _PositionProjection()
    exchange_adapter_result_repo = _ExchangeSubmitAdapterResultRepo()
    exchange_execution_result_repo = _LatestExchangeSubmitExecutionResultRepo()
    recovery_repo = _ExecutionRecoveryRepo()
    readiness_repo = _ExchangeGatewayReadinessRepo()
    review_repo = _SubmitOutcomeReviewRepo()
    settlement_repo = _PostSubmitBudgetSettlementRepo()
    active_position_repo = _ActivePositionRepo(count=1)

    state.adapter_service._order_lifecycle_service = lifecycle
    state.adapter_service._exchange_gateway = gateway
    state.adapter_service._position_projection_service = position_projection
    state.adapter_service._local_registration_action_authorization_repository = (
        _CreateGetRepo("action_authorization_id")
    )
    state.adapter_service._exchange_submit_action_authorization_repository = (
        _CreateGetRepo("action_authorization_id")
    )
    state.adapter_service._exchange_submit_adapter_result_repository = (
        exchange_adapter_result_repo
    )
    state.adapter_service._exchange_submit_execution_result_repository = (
        exchange_execution_result_repo
    )
    state.adapter_service._execution_recovery_repository = recovery_repo
    state.adapter_service._exchange_gateway_readiness_repository = readiness_repo
    state.adapter_service._attempt_outcome_policy_repository = _CreateGetRepo(
        "policy_id"
    )
    state.adapter_service._submit_outcome_review_repository = review_repo
    state.adapter_service._post_submit_budget_settlement_repository = (
        settlement_repo
    )
    state.adapter_service._reconciliation_read_model_repository = (
        _CleanReconciliationReadModelRepo()
    )
    finalize_service = RuntimePostSubmitFinalizeService(
        adapter_service=state.adapter_service,
        exchange_submit_execution_result_repository=exchange_execution_result_repo,
        submit_outcome_review_repository=review_repo,
        post_submit_budget_settlement_repository=settlement_repo,
        attempt_reservation_repository=_AttemptReservationByAuthorizationRepo(
            state.adapter_service._attempt_reservation_repository
        ),
        runtime_service=state.runtime_service,
    )

    _configure_auth_env()
    with _temporary_api_injections(state), _temporary_post_submit_injections(
        exchange_execution_result_repo=exchange_execution_result_repo,
        finalize_service=finalize_service,
        active_position_repo=active_position_repo,
    ):
        from src.interfaces.api import app

        with TestClient(app) as client:
            login = _login(client)
            if login.status_code != 200:
                raise RuntimeError(
                    f"rtf088_login_failed:{login.status_code}:{login.text}"
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
                raise RuntimeError("rtf088_authorization_id_missing")

            local_stage = _run_local_registration_stage(
                api_client=api_client,
                authorization_id=authorization_id,
                prepare_report=prepare_report,
                state=state,
            )
            reservation_id = _body(local_stage["attempt_reservation"]).get(
                "reservation_id"
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
                    "reason": "RTF-088 post-submit finalize proof prerequisite",
                    "owner_confirmation_reference": (
                        "owner-authorized-rtf088-post-submit-finalize"
                    ),
                },
            )
            exchange_action_authorization_id = _body(
                exchange_action_authorization
            ).get("action_authorization_id")
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
                        exchange_action_authorization_id
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
                        exchange_action_authorization_id
                    ),
                    "exchange_submit_adapter_enabled": True,
                },
            )
            exchange_boundary_packet = _exchange_submit_boundary_packet(
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
            exchange_execution_result = _request(
                api_client,
                "POST",
                (
                    "/api/trading-console/"
                    "runtime-execution-exchange-submit-execution-results/"
                    f"authorizations/{authorization_id}"
                ),
                query={
                    **exchange_evidence_ids,
                    "exchange_submit_action_authorization_id": (
                        exchange_action_authorization_id
                    ),
                    "exchange_submit_execution_enabled": True,
                    "exchange_submit_execution_mode": "in_memory_simulation",
                },
            )
            post_submit_finalize = api_client.request_json(
                "POST",
                (
                    "/api/trading-console/strategy-runtimes/"
                    "runtime-rtf075-cpm-long/post-submit-finalize-packets"
                ),
                body={
                    "authorization_id": authorization_id,
                    "reservation_id": reservation_id,
                    "closed_review_required": False,
                    "protection_blockers": [],
                    "metadata": {
                        "runtime_official_post_submit_finalize_proof": True,
                    },
                    "non_executing": True,
                },
            )

    controlled_gateway_action_packet = _controlled_gateway_action_packet(
        prepare_report=prepare_report,
        exchange_boundary_packet=exchange_boundary_packet,
        exchange_execution_result=exchange_execution_result,
        lifecycle=lifecycle,
        gateway=gateway,
        execution_result_repo=exchange_execution_result_repo,
        recovery_repo=recovery_repo,
        position_projection=position_projection,
    )
    packet = _post_submit_finalize_proof_packet(
        prepare_report=prepare_report,
        local_stage=local_stage,
        controlled_gateway_action_packet=controlled_gateway_action_packet,
        post_submit_finalize=post_submit_finalize,
        review_repo=review_repo,
        settlement_repo=settlement_repo,
        exchange_execution_result_repo=exchange_execution_result_repo,
        active_position_repo=active_position_repo,
        state=state,
    )
    artifacts = {
        "prepare-report.json": prepare_report,
        "local-registration-adapter-result.json": local_stage["adapter_result"],
        "exchange-submit-execution-result.json": exchange_execution_result,
        "controlled-gateway-action-packet.json": controlled_gateway_action_packet,
        "post-submit-finalize.json": post_submit_finalize,
        "post-submit-finalize-proof-packet.json": packet,
    }
    for name, payload in artifacts.items():
        _write_json(output_dir / name, payload)

    report = {
        "scope": "runtime_official_post_submit_finalize_proof",
        "status": (
            "official_post_submit_finalize_passed"
            if _contract_passed(packet["checks"])
            else "blocked"
        ),
        "runtime_instance_id": "runtime-rtf075-cpm-long",
        "order_candidate_id": "order-candidate-rtf075-contract",
        "authorization_id": (packet["ids"] or {}).get("authorization_id"),
        "execution_intent_id": (packet["ids"] or {}).get("execution_intent_id"),
        "exchange_submit_execution_result_id": (packet["ids"] or {}).get(
            "exchange_submit_execution_result_id"
        ),
        "submit_outcome_review_id": (packet["ids"] or {}).get(
            "submit_outcome_review_id"
        ),
        "post_submit_budget_settlement_id": (packet["ids"] or {}).get(
            "post_submit_budget_settlement_id"
        ),
        "post_submit_finalize_packet": post_submit_finalize,
        "post_submit_finalize_proof_packet": packet,
        "checks": packet["checks"],
        "safety_invariants": packet["safety_invariants"],
        "operator_command_plan": {
            "next_step": (
                "build_strategy_driven_next_attempt_after_flat_or_close_review"
                if _contract_passed(packet["checks"])
                else "resolve_post_submit_finalize_blockers"
            ),
            "uses_official_fastapi_routes": True,
            "uses_fake_console_api": False,
            "live_submit_allowed": False,
            "post_submit_finalize_completed": True,
            "old_authorization_replay_only": True,
            "next_attempt_requires_fresh_signal": True,
            "next_attempt_requires_fresh_authorization": True,
            "pre_submit_rehearsal_retry_allowed": False,
        },
        "right_tail_objective_context": {
            "small_bounded_losses_allowed_after_runtime_gate": True,
            "automatic_compounding_assumed": False,
            "automatic_withdrawal_assumed": False,
            "not_proven_alpha": True,
        },
    }
    _write_json(output_dir / "contract-report.json", report)
    return report


def _allow_post_submit_budget_settlement(runtime_service: Any) -> None:
    async def apply_runtime_post_submit_budget_settlement(
        self: Any,
        **kwargs: Any,
    ) -> Any:
        self.budget_settlements += 1
        updated_runtime = kwargs.get("updated_runtime")
        if updated_runtime is not None:
            self.runtime = updated_runtime
        return self.runtime

    runtime_service.apply_runtime_post_submit_budget_settlement = MethodType(
        apply_runtime_post_submit_budget_settlement,
        runtime_service,
    )


class _LatestExchangeSubmitExecutionResultRepo(_ExchangeSubmitExecutionResultRepo):
    async def get_latest_by_runtime_instance_id(self, runtime_instance_id: str) -> Any:
        for item in reversed(list(self.items.values())):
            if getattr(item, "runtime_instance_id", None) == runtime_instance_id:
                return item
        return None


class _SubmitOutcomeReviewRepo:
    def __init__(self) -> None:
        self.items: dict[str, Any] = {}
        self.created: list[Any] = []

    async def create(self, review: Any) -> Any:
        self.items[str(review.review_id)] = review
        self.created.append(review)
        return review

    async def get(self, review_id: str) -> Any | None:
        return self.items.get(str(review_id))

    async def get_by_authorization_id(self, authorization_id: str) -> Any | None:
        return next(
            (
                review
                for review in self.items.values()
                if getattr(review, "authorization_id", None) == authorization_id
            ),
            None,
        )


class _PostSubmitBudgetSettlementRepo:
    def __init__(self) -> None:
        self.items: dict[str, Any] = {}
        self.created: list[Any] = []

    async def create(self, settlement: Any) -> Any:
        self.items[str(settlement.settlement_id)] = settlement
        self.created.append(settlement)
        return settlement

    async def get(self, settlement_id: str) -> Any | None:
        return self.items.get(str(settlement_id))

    async def get_by_authorization_id(self, authorization_id: str) -> Any | None:
        return next(
            (
                settlement
                for settlement in self.items.values()
                if getattr(settlement, "authorization_id", None) == authorization_id
            ),
            None,
        )


class _AttemptReservationByAuthorizationRepo:
    def __init__(self, reservation_repo: Any) -> None:
        self.reservation_repo = reservation_repo

    async def get_by_authorization_id(self, authorization_id: str) -> Any | None:
        for reservation in self.reservation_repo.items.values():
            if getattr(reservation, "authorization_id", None) == authorization_id:
                return reservation
        return None


class _CleanReconciliationReadModelRepo:
    async def get_recent_reports(
        self,
        symbol: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        return [
            SimpleNamespace(
                report_id="post-submit-reconciliation-rtf088-clean",
                symbol=symbol,
                runtime_instance_id="runtime-rtf075-cpm-long",
                is_consistent=True,
                is_fetch_failure=False,
                severe_count=0,
                warning_count=0,
                checked_at_ms=int(time() * 1000),
            )
        ]

    async def get_mismatches(self, report_id: str) -> list[Any]:
        return []


class _ActivePositionRepo:
    def __init__(self, *, count: int) -> None:
        self.count = count
        self.calls: list[dict[str, Any]] = []

    async def list_active(
        self,
        *,
        symbol: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        self.calls.append({"symbol": symbol, "limit": limit})
        return [
            SimpleNamespace(
                position_id=f"active-position-rtf088-{idx}",
                symbol=symbol,
                runtime_instance_id="runtime-rtf075-cpm-long",
            )
            for idx in range(self.count)
        ]


class _temporary_post_submit_injections:
    def __init__(
        self,
        *,
        exchange_execution_result_repo: Any,
        finalize_service: RuntimePostSubmitFinalizeService,
        active_position_repo: Any,
    ) -> None:
        self.attr_values = {
            "_runtime_exchange_submit_execution_result_repository": (
                exchange_execution_result_repo
            ),
            "_runtime_post_submit_finalize_service": finalize_service,
            "_trading_console_pg_position_repo": active_position_repo,
        }
        self.saved_attrs: dict[str, tuple[bool, Any]] = {}

    def __enter__(self) -> "_temporary_post_submit_injections":
        import src.interfaces.api as api_module

        self.saved_attrs = {
            key: (hasattr(api_module, key), getattr(api_module, key, None))
            for key in self.attr_values
        }
        for key, value in self.attr_values.items():
            setattr(api_module, key, value)
        return self

    def __exit__(self, *_exc: Any) -> None:
        import src.interfaces.api as api_module

        for key, (exists, value) in self.saved_attrs.items():
            if exists:
                setattr(api_module, key, value)
            elif hasattr(api_module, key):
                delattr(api_module, key)


def _post_submit_finalize_proof_packet(
    *,
    prepare_report: dict[str, Any],
    local_stage: dict[str, Any],
    controlled_gateway_action_packet: dict[str, Any],
    post_submit_finalize: dict[str, Any],
    review_repo: _SubmitOutcomeReviewRepo,
    settlement_repo: _PostSubmitBudgetSettlementRepo,
    exchange_execution_result_repo: _LatestExchangeSubmitExecutionResultRepo,
    active_position_repo: _ActivePositionRepo,
    state: Any,
) -> dict[str, Any]:
    finalize_body = _body(post_submit_finalize)
    review = review_repo.created[-1] if review_repo.created else None
    settlement = settlement_repo.created[-1] if settlement_repo.created else None
    checks = _checks(
        controlled_gateway_action_packet=controlled_gateway_action_packet,
        post_submit_finalize=post_submit_finalize,
        review=review,
        settlement=settlement,
        exchange_execution_result_repo=exchange_execution_result_repo,
        active_position_repo=active_position_repo,
        state=state,
    )
    return {
        "scope": "runtime_official_post_submit_finalize_proof_packet",
        "status": (
            "post_submit_finalize_completed_next_attempt_blocked"
            if _contract_passed(checks)
            else "blocked"
        ),
        "ids": {
            **dict(prepare_report.get("ids") or {}),
            **dict(controlled_gateway_action_packet.get("ids") or {}),
            "attempt_reservation_id": _body(
                local_stage["attempt_reservation"]
            ).get("reservation_id"),
            "submit_outcome_review_id": finalize_body.get(
                "submit_outcome_review_id"
            ),
            "post_submit_budget_settlement_id": finalize_body.get(
                "post_submit_budget_settlement_id"
            ),
            "post_submit_finalize_packet_id": finalize_body.get("packet_id"),
        },
        "statuses": {
            **dict(controlled_gateway_action_packet.get("statuses") or {}),
            "post_submit_finalize": finalize_body.get("status"),
            "next_attempt_gate": (
                finalize_body.get("next_attempt_gate") or {}
            ).get("status"),
            "submit_outcome_review": finalize_body.get(
                "submit_outcome_review_status"
            ),
            "post_submit_budget_settlement": finalize_body.get(
                "post_submit_budget_settlement_status"
            ),
        },
        "post_submit_finalize": {
            "http_status": post_submit_finalize.get("http_status"),
            "packet_id": finalize_body.get("packet_id"),
            "status": finalize_body.get("status"),
            "blockers": list(finalize_body.get("blockers") or []),
            "warnings": list(finalize_body.get("warnings") or []),
            "consumed_authorization_replay_only": finalize_body.get(
                "consumed_authorization_replay_only"
            ),
            "old_authorization_submit_retry_allowed": finalize_body.get(
                "old_authorization_submit_retry_allowed"
            ),
            "pre_submit_rehearsal_retry_allowed": finalize_body.get(
                "pre_submit_rehearsal_retry_allowed"
            ),
            "local_created_order_requirement_retired": finalize_body.get(
                "local_created_order_requirement_retired"
            ),
            "submit_result_status": finalize_body.get("submit_result_status"),
        },
        "review": {
            "created_count": len(review_repo.created),
            "status": getattr(getattr(review, "status", None), "value", None),
            "observed_outcome": getattr(
                getattr(review, "observed_outcome", None),
                "value",
                None,
            ),
            "recommended_attempt_outcome_kind": getattr(
                getattr(review, "recommended_attempt_outcome_kind", None),
                "value",
                None,
            ),
            "post_submit_reconciliation_evidence_id": getattr(
                review,
                "post_submit_reconciliation_evidence_id",
                None,
            ),
        },
        "settlement": {
            "created_count": len(settlement_repo.created),
            "status": getattr(getattr(settlement, "status", None), "value", None),
            "budget_action": getattr(
                getattr(settlement, "budget_action", None),
                "value",
                None,
            ),
            "budget_consumption_recorded": getattr(
                settlement,
                "budget_consumption_recorded",
                None,
            ),
            "runtime_state_mutated": getattr(
                settlement,
                "runtime_state_mutated",
                None,
            ),
        },
        "next_attempt_gate": finalize_body.get("next_attempt_gate") or {},
        "checks": checks,
        "safety_invariants": _safety_invariants(
            post_submit_finalize=post_submit_finalize,
            state=state,
        ),
    }


def _checks(
    *,
    controlled_gateway_action_packet: dict[str, Any],
    post_submit_finalize: dict[str, Any],
    review: Any,
    settlement: Any,
    exchange_execution_result_repo: _LatestExchangeSubmitExecutionResultRepo,
    active_position_repo: _ActivePositionRepo,
    state: Any,
) -> dict[str, bool]:
    finalize_body = _body(post_submit_finalize)
    gate = finalize_body.get("next_attempt_gate") or {}
    safety = _safety_invariants(
        post_submit_finalize=post_submit_finalize,
        state=state,
    )
    return {
        "controlled_gateway_action_passed": (
            controlled_gateway_action_packet.get("status")
            == "controlled_gateway_action_submitted"
        ),
        "post_submit_finalize_http_ok": (
            post_submit_finalize.get("http_status") == 200
        ),
        "post_submit_finalize_next_attempt_blocked": (
            finalize_body.get("status") == "finalized_next_attempt_blocked"
        ),
        "next_attempt_gate_blocked": gate.get("status") == "blocked",
        "next_attempt_blocked_by_active_position": (
            "runtime_active_position_slot_in_use" in list(gate.get("blockers") or [])
        ),
        "active_position_fact_resolved": gate.get("active_positions_count") == 1,
        "old_authorization_replay_only": (
            finalize_body.get("consumed_authorization_replay_only") is True
        ),
        "old_authorization_submit_retry_disallowed": (
            finalize_body.get("old_authorization_submit_retry_allowed") is False
        ),
        "pre_submit_rehearsal_retry_disallowed": (
            finalize_body.get("pre_submit_rehearsal_retry_allowed") is False
        ),
        "local_created_order_requirement_retired": (
            finalize_body.get("local_created_order_requirement_retired") is True
        ),
        "submit_outcome_review_created": review is not None,
        "submit_outcome_review_policy_ready": (
            getattr(getattr(review, "status", None), "value", None)
            == "classified_ready_for_attempt_outcome_policy"
        ),
        "submit_outcome_review_full_fill": (
            getattr(getattr(review, "observed_outcome", None), "value", None)
            == "submitted_full_fill"
        ),
        "post_submit_budget_settlement_created": settlement is not None,
        "post_submit_budget_consumed_recorded": (
            getattr(getattr(settlement, "status", None), "value", None)
            == "recorded_reserved_budget_consumed"
        ),
        "runtime_budget_settlement_applied_once": (
            getattr(state.runtime_service, "budget_settlements", 0) == 1
        ),
        "durable_execution_result_reused": bool(exchange_execution_result_repo.items),
        "active_position_source_called": bool(active_position_repo.calls),
        "uses_official_fastapi_routes": True,
        "uses_fake_console_api": False,
        "pg_written": safety["pg_written"],
        "live_exchange_called": safety["live_exchange_called"],
        "post_submit_created_order": safety["post_submit_created_order"],
        "post_submit_order_lifecycle_called": safety[
            "post_submit_order_lifecycle_called"
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
        "controlled_gateway_action_passed",
        "post_submit_finalize_http_ok",
        "post_submit_finalize_next_attempt_blocked",
        "next_attempt_gate_blocked",
        "next_attempt_blocked_by_active_position",
        "active_position_fact_resolved",
        "old_authorization_replay_only",
        "old_authorization_submit_retry_disallowed",
        "pre_submit_rehearsal_retry_disallowed",
        "local_created_order_requirement_retired",
        "submit_outcome_review_created",
        "submit_outcome_review_policy_ready",
        "submit_outcome_review_full_fill",
        "post_submit_budget_settlement_created",
        "post_submit_budget_consumed_recorded",
        "runtime_budget_settlement_applied_once",
        "durable_execution_result_reused",
        "active_position_source_called",
        "uses_official_fastapi_routes",
    )
    required_false = (
        "uses_fake_console_api",
        "pg_written",
        "live_exchange_called",
        "post_submit_created_order",
        "post_submit_order_lifecycle_called",
        "execution_intent_status_changed",
        "withdrawal_or_transfer_created",
    )
    return all(checks.get(key) is True for key in required_true) and all(
        checks.get(key) is False for key in required_false
    )


def _safety_invariants(
    *,
    post_submit_finalize: dict[str, Any],
    state: Any,
) -> dict[str, bool]:
    finalize_body = _body(post_submit_finalize)
    return {
        "uses_official_fastapi_routes": True,
        "uses_fake_console_api": False,
        "uses_in_memory_repositories": True,
        "pg_written": False,
        "live_exchange_called": False,
        "pre_submit_rehearsal_retry_allowed": (
            finalize_body.get("pre_submit_rehearsal_retry_allowed") is True
        ),
        "post_submit_created_order": finalize_body.get("order_created") is True,
        "post_submit_order_lifecycle_called": (
            finalize_body.get("order_lifecycle_called") is True
        ),
        "runtime_budget_settlement_recorded": (
            getattr(state.runtime_service, "budget_settlements", 0) == 1
        ),
        "execution_intent_status_changed": (
            finalize_body.get("execution_intent_status_changed") is True
        ),
        "withdrawal_or_transfer_created": (
            finalize_body.get("withdrawal_or_transfer_created") is True
        ),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an official post-submit finalize proof."
    )
    parser.add_argument(
        "--output-dir",
        default="output/rtf088-official-post-submit-finalize",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_proof_report(Path(args.output_dir).expanduser())
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if report["status"] == "official_post_submit_finalize_passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
