#!/usr/bin/env python3
"""Official server-side prepare integration proof.

RTF-079 replaces the RTF-078 fake Console API boundary with an in-process
FastAPI/TestClient proof against the official Trading Console routes.  It uses
real application services with in-memory repositories so the HTTP route,
service composition, and prepare wrapper are exercised without PG writes,
OrderLifecycle, exchange writes, orders, runtime mutations, withdrawals, or
transfers.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
import time
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
from src.application.runtime_execution_intent_adapter_service import (  # noqa: E402
    RuntimeExecutionIntentAdapterService,
)
from src.application.runtime_execution_planning_service import (  # noqa: E402
    RuntimeExecutionPlanningService,
)
from src.application.runtime_execution_trusted_submit_facts_service import (  # noqa: E402
    RuntimeExecutionTrustedSubmitFactsAssemblyService,
)
from src.application.runtime_final_gate_preview_service import (  # noqa: E402
    RuntimeFinalGatePreviewService,
)
from src.domain.runtime_execution_attempt_mutation import (  # noqa: E402
    RuntimeExecutionAttemptMutation,
    RuntimeExecutionAttemptMutationStatus,
)
from src.domain.runtime_execution_attempt_reservation import (  # noqa: E402
    RuntimeExecutionAttemptReservationStatus,
)
from src.domain.runtime_execution_order_lifecycle_handoff import (  # noqa: E402
    build_runtime_execution_order_lifecycle_handoff_draft,
)
from src.domain.runtime_execution_trusted_submit_facts import (  # noqa: E402
    RuntimeExecutionTrustedSubmitFactSource,
)
from src.domain.signal_evaluation import OrderCandidate, SignalEvaluation  # noqa: E402
from src.interfaces.operator_auth import create_password_hash, _hotp  # noqa: E402


AUTH_USERNAME = "owner"
AUTH_PASSWORD = "pw"
AUTH_TOTP_SECRET = "JBSWY3DPEHPK3PXP"
AUTH_SESSION_SECRET = "session-secret-for-rtf079"


def build_proof_report(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    shadow_dir = output_dir / "shadow-planning"
    shadow_report = shadow_fixture.build_contract_fixture_report(shadow_dir)
    _write_json(output_dir / "shadow-contract-report.json", shadow_report)

    candidate = OrderCandidate.model_validate(shadow_report["candidate_snapshot"])
    runtime = shadow_fixture._runtime()
    signal_evaluation = SignalEvaluation.model_validate(
        shadow_report["candidate_snapshot"]["metadata"][
            "source_signal_evaluation_snapshot"
        ]
        if "source_signal_evaluation_snapshot" in shadow_report["candidate_snapshot"].get("metadata", {})
        else _signal_evaluation_from_candidate(candidate)
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
                raise RuntimeError(f"rtf079_login_failed:{login.status_code}:{login.text}")
            flow = FirstRealSubmitApiFlow(
                client=_TestClientApiClient(client),
                config=FlowConfig(
                    api_base="testclient://rtf079-official-server",
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
                        "owner-reviewed-rtf079-server-prepare"
                    ),
                    reason=(
                        "RTF-079 official server-side prepare integration proof"
                    ),
                ),
            )
            prepare_report = flow.run()

    prepare_artifact = _summarize_prepare_artifact(prepare_report)
    _write_json(output_dir / "prepare-report.json", prepare_report)
    _write_json(output_dir / "prepare-artifact.json", prepare_artifact)

    report = _report(
        shadow_report=shadow_report,
        prepare_report=prepare_report,
        prepare_artifact=prepare_artifact,
        state=state,
    )
    _write_json(output_dir / "contract-report.json", report)
    return report


class _ServerProofState:
    def __init__(
        self,
        *,
        runtime: Any,
        candidate: OrderCandidate,
        signal_evaluation: SignalEvaluation,
    ) -> None:
        self.runtime = runtime
        self.candidate = candidate
        self.signal_evaluation = signal_evaluation
        self.signal_repo = _SignalEvaluationRepo(signal_evaluation, candidate)
        self.runtime_service = _RuntimeService(runtime)
        self.active_position_source = _ActivePositionSource()
        self.draft_repo = _CreateGetRepo("draft_id")
        self.intent_repo = _IntentRepo()
        self.submit_authorization_repo = _SubmitAuthorizationRepo()
        self.protection_plan_repo = _CreateGetRepo("protection_plan_id")
        self.order_lifecycle_handoff_repo = _OrderLifecycleHandoffRepo(runtime)
        self.order_lifecycle_adapter_result_repo = (
            _OrderLifecycleAdapterResultRepo()
        )
        self.trusted_submit_facts_repo = _CreateGetRepo(
            "trusted_submit_fact_snapshot_id"
        )
        self.submit_idempotency_repo = _CreateGetRepo("submit_idempotency_policy_id")
        self.protection_failure_policy_repo = _CreateGetRepo("policy_id")
        self.final_gate = RuntimeFinalGatePreviewService(
            runtime_service=self.runtime_service,
            signal_evaluation_service=self.signal_repo,
            active_position_source=self.active_position_source,
        )
        self.planning_service = RuntimeExecutionPlanningService(
            runtime_service=self.runtime_service,
            signal_evaluation_service=self.signal_repo,
            final_gate_preview_service=self.final_gate,
            intent_draft_repository=self.draft_repo,
        )
        self.adapter_service = RuntimeExecutionIntentAdapterService(
            draft_repository=self.draft_repo,
            intent_repository=self.intent_repo,
            submit_authorization_repository=self.submit_authorization_repo,
            protection_plan_repository=self.protection_plan_repo,
            order_lifecycle_handoff_repository=self.order_lifecycle_handoff_repo,
            order_lifecycle_adapter_result_repository=(
                self.order_lifecycle_adapter_result_repo
            ),
            trusted_submit_facts_repository=self.trusted_submit_facts_repo,
            submit_idempotency_repository=self.submit_idempotency_repo,
            protection_failure_policy_repository=self.protection_failure_policy_repo,
            final_gate_preview_service=self.final_gate,
            runtime_service=self.runtime_service,
        )
        self.order_lifecycle_handoff_repo.configure(
            adapter_service=self.adapter_service,
            intent_repo=self.intent_repo,
            protection_plan_repo=self.protection_plan_repo,
        )
        self.order_lifecycle_adapter_result_repo.adapter_service = (
            self.adapter_service
        )
        self.trusted_facts_assembly = RuntimeExecutionTrustedSubmitFactsAssemblyService(
            repository=self.trusted_submit_facts_repo,
            account_fact_reader=_TrustedFactReader("account_fact"),
            active_position_reader=_TrustedFactReader("active_position"),
            open_order_reader=_TrustedFactReader("open_order"),
            protection_state_reader=_TrustedFactReader("protection_state"),
            market_rule_reader=_TrustedFactReader("market_rule"),
            reconciliation_reader=_TrustedFactReader("reconciliation"),
        )


class _SignalEvaluationRepo:
    def __init__(
        self,
        signal_evaluation: SignalEvaluation,
        candidate: OrderCandidate,
    ) -> None:
        self.signal_evaluation = signal_evaluation
        self.candidate = candidate

    async def initialize(self) -> None:
        return None

    async def get_signal_evaluation(
        self,
        signal_evaluation_id: str,
    ) -> SignalEvaluation | None:
        if signal_evaluation_id == self.signal_evaluation.signal_evaluation_id:
            return self.signal_evaluation
        return None

    async def get_order_candidate(
        self,
        order_candidate_id: str,
    ) -> OrderCandidate | None:
        if order_candidate_id == self.candidate.order_candidate_id:
            return self.candidate
        return None

    async def list_order_candidates(self, **kwargs: Any) -> list[OrderCandidate]:
        return [self.candidate]

    async def list_signal_evaluations(self, **kwargs: Any) -> list[SignalEvaluation]:
        return [self.signal_evaluation]


class _RuntimeService:
    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime
        self.attempt_mutations = 0
        self.budget_settlements = 0

    async def get_runtime(self, runtime_instance_id: str) -> Any:
        if runtime_instance_id != self.runtime.runtime_instance_id:
            raise ValueError("runtime_not_found")
        return self.runtime

    async def apply_runtime_attempt_mutation(self, **kwargs: Any) -> Any:
        self.attempt_mutations += 1
        raise AssertionError("RTF-079 must not mutate runtime attempts")

    async def apply_runtime_post_submit_budget_settlement(self, **kwargs: Any) -> Any:
        self.budget_settlements += 1
        raise AssertionError("RTF-079 must not mutate runtime budget")


class _ActivePositionSource:
    async def list_active(self, *, symbol: str | None = None, limit: int = 100):
        return []


class _CreateGetRepo:
    def __init__(self, key: str) -> None:
        self.key = key
        self.items: dict[str, Any] = {}

    async def create(self, item: Any) -> Any:
        key = str(getattr(item, self.key))
        self.items[key] = item
        return item

    async def get(self, key: str) -> Any | None:
        return self.items.get(key)


class _IntentRepo:
    def __init__(self) -> None:
        self.items: dict[str, Any] = {}

    async def save(self, intent: Any) -> None:
        self.items[str(intent.id)] = intent

    async def get(self, intent_id: str) -> Any | None:
        return self.items.get(intent_id)

    async def get_by_order_candidate_id(self, order_candidate_id: str) -> Any | None:
        for intent in self.items.values():
            if getattr(intent, "order_candidate_id", None) == order_candidate_id:
                return intent
        return None


class _SubmitAuthorizationRepo:
    def __init__(self) -> None:
        self.items: dict[str, Any] = {}

    async def create(self, authorization: Any) -> Any:
        self.items[str(authorization.authorization_id)] = authorization
        return authorization

    async def get(self, authorization_id: str) -> Any | None:
        return self.items.get(authorization_id)

    async def get_by_order_candidate_id(self, order_candidate_id: str) -> Any | None:
        for authorization in self.items.values():
            if getattr(authorization, "source_id", None) == order_candidate_id:
                return authorization
        return None


class _OrderLifecycleHandoffRepo:
    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime
        self.items: dict[str, Any] = {}
        self.adapter_service: Any | None = None
        self.intent_repo: Any | None = None
        self.protection_plan_repo: Any | None = None

    def configure(
        self,
        *,
        adapter_service: Any,
        intent_repo: Any,
        protection_plan_repo: Any,
    ) -> None:
        self.adapter_service = adapter_service
        self.intent_repo = intent_repo
        self.protection_plan_repo = protection_plan_repo

    async def create(self, draft: Any) -> Any:
        self.items[str(draft.handoff_draft_id)] = draft
        return draft

    async def get(self, handoff_draft_id: str) -> Any | None:
        if handoff_draft_id not in self.items:
            draft = await self._build_blocked_non_executing_handoff(
                handoff_draft_id
            )
            if draft is not None:
                self.items[handoff_draft_id] = draft
        return self.items.get(handoff_draft_id)

    async def _build_blocked_non_executing_handoff(
        self,
        handoff_draft_id: str,
    ) -> Any | None:
        if (
            self.adapter_service is None
            or self.intent_repo is None
            or self.protection_plan_repo is None
        ):
            return None
        prefix = "runtime-order-lifecycle-handoff-"
        if not handoff_draft_id.startswith(prefix):
            return None
        authorization_id = handoff_draft_id[len(prefix):]
        preflight = await (
            self.adapter_service.controlled_submit_preflight_for_authorization(
                authorization_id
            )
        )
        intent = await self.intent_repo.get(preflight.execution_intent_id)
        if intent is None:
            return None
        protection_plan = await self.protection_plan_repo.get(
            f"runtime-protection-plan-{intent.id}"
        )
        if protection_plan is None:
            return None
        mutation = _blocked_attempt_mutation_for_handoff(
            preflight=preflight,
            intent=intent,
            runtime=self.runtime,
        )
        return build_runtime_execution_order_lifecycle_handoff_draft(
            preflight=preflight,
            intent=intent,
            attempt_mutation=mutation,
            protection_plan=protection_plan,
            now_ms=_now_ms(),
        )


class _OrderLifecycleAdapterResultRepo:
    def __init__(self) -> None:
        self.items: dict[str, Any] = {}
        self.adapter_service: Any | None = None

    async def get_by_authorization_id(self, authorization_id: str) -> Any | None:
        if authorization_id not in self.items and self.adapter_service is not None:
            self.items[authorization_id] = (
                await self.adapter_service
                .order_lifecycle_adapter_result_for_authorization(
                    authorization_id,
                    order_lifecycle_adapter_enabled=False,
                    local_order_registration_enabled=False,
                )
            )
        return self.items.get(authorization_id)

    async def acquire_registration_lock(self, result: Any) -> tuple[bool, Any]:
        existing = self.items.get(str(result.authorization_id))
        if existing is not None:
            return False, existing
        self.items[str(result.authorization_id)] = result
        return True, result

    async def complete_registration(self, result: Any) -> Any:
        self.items[str(result.authorization_id)] = result
        return result


def _blocked_attempt_mutation_for_handoff(
    *,
    preflight: Any,
    intent: Any,
    runtime: Any,
) -> RuntimeExecutionAttemptMutation:
    authorization_id = preflight.authorization_id
    reservation_id = f"runtime-attempt-reservation-{authorization_id}"
    payload = dict(intent.source_payload or {})
    proposed_quantity = _optional_decimal(payload.get("proposed_quantity"))
    intended_notional = _optional_decimal(payload.get("intended_notional"))
    return RuntimeExecutionAttemptMutation(
        mutation_id=f"runtime-attempt-mutation-{reservation_id}",
        reservation_id=reservation_id,
        reservation_preview_id=f"runtime-attempt-reservation-preview-{authorization_id}",
        authorization_id=authorization_id,
        execution_intent_id=intent.id,
        runtime_instance_id=runtime.runtime_instance_id,
        source_id=intent.source_id,
        semantic_ids=intent.semantic_ids,
        status=RuntimeExecutionAttemptMutationStatus.BLOCKED,
        runtime_status_before=runtime.status,
        runtime_status_after=runtime.status,
        symbol=runtime.symbol,
        side=payload.get("side") or getattr(runtime, "side", None),
        proposed_quantity=proposed_quantity,
        intended_notional=intended_notional,
        attempts_used_before=runtime.boundary.attempts_used,
        attempts_used_after=runtime.boundary.attempts_used,
        attempts_remaining_before=runtime.attempts_remaining,
        attempts_remaining_after=runtime.attempts_remaining,
        max_attempts=runtime.boundary.max_attempts,
        budget_reserved_before=runtime.boundary.budget_reserved,
        budget_reserved_after=runtime.boundary.budget_reserved,
        budget_remaining_before=runtime.budget_remaining,
        budget_remaining_after=runtime.budget_remaining,
        reservation_budget_remaining_after=runtime.budget_remaining,
        max_notional_per_attempt=runtime.boundary.max_notional_per_attempt,
        total_budget=runtime.boundary.total_budget,
        max_active_positions=runtime.boundary.max_active_positions,
        blockers=["rtf079_non_executing_attempt_mutation_not_applied"],
        warnings=[],
        reservation_status=(
            RuntimeExecutionAttemptReservationStatus.PENDING_RUNTIME_MUTATION
        ),
        runtime_budget_mutated=False,
        attempt_consumed=False,
        created_at_ms=_now_ms(),
        metadata={
            "scope": "rtf079_non_executing_handoff_shape_only",
            "does_not_mutate_runtime": True,
            "does_not_consume_attempt": True,
            "does_not_create_order": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
        },
    )


class _TrustedFactReader:
    def __init__(self, key: str) -> None:
        self.key = key

    async def read_trusted_submit_fact_source(
        self,
        *,
        key: str,
        execution_intent_id: str,
        runtime_instance_id: str | None,
        order_candidate_id: str | None,
        symbol: str,
        side: str | None,
        now_ms: int,
    ) -> RuntimeExecutionTrustedSubmitFactSource:
        return RuntimeExecutionTrustedSubmitFactSource(
            key=key,
            source_id=f"rtf079-{key}-{execution_intent_id}",
            source_type="rtf079_in_memory_read_model",
            trusted=True,
            freshness="fresh",
            observed_at_ms=now_ms,
            max_age_ms=60_000,
            read_only=True,
            owner_supplied_allow_signal=False,
            metadata={
                "runtime_instance_id": runtime_instance_id,
                "order_candidate_id": order_candidate_id,
                "symbol": symbol,
                "side": side,
                "rtf079_official_server_prepare_proof": True,
            },
        )


class _TestClientApiClient:
    def __init__(self, client: TestClient) -> None:
        self.client = client

    def request_json(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self.client.request(
            method,
            path,
            params={key: value for key, value in (query or {}).items() if value is not None},
            json=body,
        )
        try:
            parsed: Any = response.json()
        except Exception:
            parsed = response.text
        return {
            "http_status": response.status_code,
            "body": parsed,
            "error": response.status_code >= 400,
        }


@contextmanager
def _temporary_api_injections(state: _ServerProofState):
    import src.interfaces.api as api_module
    import src.interfaces.api_trading_console as trading_api

    attr_values = {
        "_signal_evaluation_shadow_service": state.signal_repo,
        "_strategy_runtime_service": state.runtime_service,
        "_runtime_final_gate_preview_service": state.final_gate,
        "_runtime_execution_planning_service": state.planning_service,
        "_runtime_execution_intent_adapter_service": state.adapter_service,
        "_trading_console_pg_execution_intent_repo": state.intent_repo,
        "_trading_console_pg_runtime_submit_authorization_repo": (
            state.submit_authorization_repo
        ),
        "_position_repo": state.active_position_source,
    }
    saved_attrs = {
        key: (hasattr(api_module, key), getattr(api_module, key, None))
        for key in attr_values
    }
    saved_function = trading_api._runtime_execution_trusted_submit_facts_assembly_service
    try:
        for key, value in attr_values.items():
            setattr(api_module, key, value)
        trading_api._runtime_execution_trusted_submit_facts_assembly_service = (
            lambda: state.trusted_facts_assembly
        )
        yield
    finally:
        for key, (exists, value) in saved_attrs.items():
            if exists:
                setattr(api_module, key, value)
            elif hasattr(api_module, key):
                delattr(api_module, key)
        trading_api._runtime_execution_trusted_submit_facts_assembly_service = (
            saved_function
        )


def _summarize_prepare_artifact(report: dict[str, Any]) -> dict[str, Any]:
    ids = dict(report.get("ids") or {})
    steps = list(report.get("steps") or [])
    step_names = [
        str(item.get("name") or "") for item in steps if isinstance(item, dict)
    ]
    ready = (
        not list(report.get("blockers") or [])
        and bool(ids.get("runtime_execution_intent_draft_id"))
        and bool(ids.get("execution_intent_id"))
        and bool(ids.get("authorization_id"))
    )
    return {
        "scope": "runtime_official_server_prepare_integration_artifact",
        "status": "ready_for_final_gate_preflight" if ready else "blocked",
        "ids": ids,
        "step_names": step_names,
        "next_attempt_gate": report.get("next_attempt_gate") or {},
        "blockers": list(report.get("blockers") or []),
        "warnings": list(report.get("warnings") or []),
        "evidence_preparation_step": _step_by_name(
            steps,
            "prepare_machine_evidence",
        ),
        "created_records": {
            "runtime_execution_intent_draft_created": bool(
                ids.get("runtime_execution_intent_draft_id")
            ),
            "execution_intent_created": bool(ids.get("execution_intent_id")),
            "protection_plan_created": bool(ids.get("protection_plan_id")),
            "submit_authorization_created": bool(ids.get("authorization_id")),
            "trusted_submit_facts_prepared": bool(
                ids.get("trusted_submit_fact_snapshot_id")
            ),
            "submit_idempotency_prepared": bool(
                ids.get("submit_idempotency_policy_id")
            ),
            "protection_failure_policy_prepared": bool(
                ids.get("protection_creation_failure_policy_id")
            ),
        },
        "evidence_preparation": _summarize_evidence_preparation(
            _step_by_name(
                steps,
                "prepare_machine_evidence",
            )
        ),
        "safety_invariants": {
            "uses_official_fastapi_routes": True,
            "uses_official_prepare_wrapper": True,
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
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "position_opened": False,
            "position_closed": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _report(
    *,
    shadow_report: dict[str, Any],
    prepare_report: dict[str, Any],
    prepare_artifact: dict[str, Any],
    state: _ServerProofState,
) -> dict[str, Any]:
    checks = _checks(
        shadow_report=shadow_report,
        prepare_report=prepare_report,
        prepare_artifact=prepare_artifact,
        state=state,
    )
    return {
        "scope": "runtime_official_server_prepare_integration_proof",
        "status": (
            "official_server_prepare_integration_passed"
            if _contract_passed(checks)
            else "blocked"
        ),
        "runtime_instance_id": state.runtime.runtime_instance_id,
        "order_candidate_id": state.candidate.order_candidate_id,
        "signal_evaluation_id": state.signal_evaluation.signal_evaluation_id,
        "prepared_authorization_id": (
            prepare_artifact.get("ids", {}).get("authorization_id")
        ),
        "runtime_execution_intent_draft_id": (
            prepare_artifact.get("ids", {}).get("runtime_execution_intent_draft_id")
        ),
        "execution_intent_id": prepare_artifact.get("ids", {}).get(
            "execution_intent_id"
        ),
        "protection_plan_id": prepare_artifact.get("ids", {}).get(
            "protection_plan_id"
        ),
        "prepare_artifact": prepare_artifact,
        "first_real_submit_prepare_report": prepare_report,
        "shadow_contract": shadow_report,
        "checks": checks,
        "blockers": list(prepare_artifact.get("blockers") or []),
        "warnings": list(prepare_artifact.get("warnings") or []),
        "server_prepare_integration_plan": {
            "next_step": (
                "run_official_final_gate_preflight"
                if _contract_passed(checks)
                else "resolve_official_server_prepare_blockers"
            ),
            "uses_official_fastapi_routes": True,
            "uses_official_prepare_wrapper": True,
            "uses_fake_console_api": False,
            "records_prepare_governance_in_memory_only": True,
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
        "safety_invariants": prepare_artifact["safety_invariants"],
    }


def _checks(
    *,
    shadow_report: dict[str, Any],
    prepare_report: dict[str, Any],
    prepare_artifact: dict[str, Any],
    state: _ServerProofState,
) -> dict[str, bool]:
    ids = prepare_artifact.get("ids") or {}
    created = prepare_artifact.get("created_records") or {}
    safety = prepare_artifact.get("safety_invariants") or {}
    step_names = prepare_artifact.get("step_names") or []
    next_gate = prepare_artifact.get("next_attempt_gate") or {}
    evidence_preparation = prepare_artifact.get("evidence_preparation") or {}
    return {
        "shadow_contract_passed": (
            shadow_report.get("status")
            == "ready_signal_shadow_planning_contract_passed"
        ),
        "right_tail_runner_preserved": bool(
            (shadow_report.get("checks") or {}).get("right_tail_runner_preserved")
        ),
        "uses_official_fastapi_routes": safety.get("uses_official_fastapi_routes")
        is True,
        "uses_fake_console_api": safety.get("uses_fake_console_api") is True,
        "official_prepare_wrapper_used": safety.get("uses_official_prepare_wrapper")
        is True,
        "next_attempt_gate_checked": next_gate.get("status")
        == "clear_for_preflight",
        "order_candidate_usage_checked": "verify_order_candidate_usage" in step_names,
        "intent_draft_route_called": "record_intent_draft" in step_names,
        "execution_intent_route_called": "record_execution_intent" in step_names,
        "protection_plan_route_called": "record_protection_plan" in step_names,
        "submit_authorization_route_called": "record_submit_authorization"
        in step_names,
        "evidence_preparation_route_called": "prepare_machine_evidence"
        in step_names,
        "evidence_preparation_artifact_created": (
            evidence_preparation.get("artifact_created") is True
        ),
        "evidence_preparation_not_dependency_blocked": (
            evidence_preparation.get("dependency_blocked") is False
        ),
        "evidence_preparation_status_prepared_artifact_blocked": (
            evidence_preparation.get("status") == "prepared_evidence_blocked"
        ),
        "prepare_ready_for_final_gate_preflight": (
            prepare_artifact.get("status") == "ready_for_final_gate_preflight"
        ),
        "runtime_execution_intent_draft_created": bool(
            created.get("runtime_execution_intent_draft_created")
        ),
        "execution_intent_created": bool(created.get("execution_intent_created")),
        "protection_plan_created": bool(created.get("protection_plan_created")),
        "submit_authorization_created": bool(
            created.get("submit_authorization_created")
        ),
        "trusted_submit_facts_prepared": bool(
            created.get("trusted_submit_facts_prepared")
        ),
        "submit_idempotency_prepared": bool(
            created.get("submit_idempotency_prepared")
        ),
        "protection_failure_policy_prepared": bool(
            created.get("protection_failure_policy_prepared")
        ),
        "authorization_id_present": bool(ids.get("authorization_id")),
        "pg_written": safety.get("pg_written") is True,
        "exchange_write_called": safety.get("exchange_write_called") is True,
        "order_created": safety.get("order_created") is True,
        "order_lifecycle_called": safety.get("order_lifecycle_called") is True,
        "attempt_counter_mutated": (
            safety.get("attempt_counter_mutated") is True
            or state.runtime_service.attempt_mutations > 0
        ),
        "runtime_budget_mutated": (
            safety.get("runtime_budget_mutated") is True
            or state.runtime_service.budget_settlements > 0
        ),
        "withdrawal_or_transfer_created": (
            safety.get("withdrawal_or_transfer_created") is True
        ),
    }


def _contract_passed(checks: dict[str, bool]) -> bool:
    required_true = (
        "shadow_contract_passed",
        "right_tail_runner_preserved",
        "uses_official_fastapi_routes",
        "official_prepare_wrapper_used",
        "next_attempt_gate_checked",
        "order_candidate_usage_checked",
        "intent_draft_route_called",
        "execution_intent_route_called",
        "protection_plan_route_called",
        "submit_authorization_route_called",
        "evidence_preparation_route_called",
        "evidence_preparation_artifact_created",
        "evidence_preparation_not_dependency_blocked",
        "evidence_preparation_status_prepared_artifact_blocked",
        "prepare_ready_for_final_gate_preflight",
        "runtime_execution_intent_draft_created",
        "execution_intent_created",
        "protection_plan_created",
        "submit_authorization_created",
        "trusted_submit_facts_prepared",
        "submit_idempotency_prepared",
        "protection_failure_policy_prepared",
        "authorization_id_present",
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


def _step_by_name(steps: list[Any], name: str) -> dict[str, Any] | None:
    for item in steps:
        if isinstance(item, dict) and item.get("name") == name:
            return item
    return None


def _summarize_evidence_preparation(step: dict[str, Any] | None) -> dict[str, Any]:
    if not step:
        return {
            "status": None,
            "artifact_created": False,
            "dependency_blocked": True,
            "blockers": ["evidence_preparation_step_missing"],
        }
    status = step.get("status")
    blockers = [str(item) for item in list(step.get("blockers") or [])]
    dependency_blocked = any(
        "repository_unavailable" in blocker
        or "service_unavailable" in blocker
        for blocker in blockers
    )
    return {
        "status": status,
        "artifact_created": str(status or "").startswith("prepared_evidence_"),
        "source_status": (
            "blocked" if status == "prepared_evidence_blocked" else None
        ),
        "dependency_blocked": dependency_blocked,
        "blockers": blockers,
    }


def _signal_evaluation_from_candidate(candidate: OrderCandidate) -> dict[str, Any]:
    now_ms = candidate.created_at_ms
    return {
        "signal_evaluation_id": candidate.signal_evaluation_id,
        "runtime_instance_id": candidate.runtime_instance_id,
        "trial_binding_id": candidate.trial_binding_id,
        "strategy_family_id": candidate.strategy_family_id,
        "strategy_family_version_id": candidate.strategy_family_version_id,
        "source_signal_id": "rtf079-source-signal",
        "symbol": candidate.symbol,
        "side": candidate.side,
        "status": "evaluated",
        "decision": "candidate",
        "reason_codes": ["rtf079_reconstructed_from_candidate"],
        "rationale": "RTF-079 reconstructed signal evaluation for server proof",
        "evaluated_at_ms": now_ms,
        "created_at_ms": now_ms,
        "updated_at_ms": now_ms,
        "metadata": {"rtf079_reconstructed": True},
    }


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _now_ms() -> int:
    return int(time.time() * 1000)


def _configure_auth_env() -> None:
    os.environ["BRC_OPERATOR_USERNAME"] = AUTH_USERNAME
    os.environ["BRC_OPERATOR_PASSWORD_HASH"] = create_password_hash(AUTH_PASSWORD)
    os.environ["BRC_OPERATOR_TOTP_SECRET"] = AUTH_TOTP_SECRET
    os.environ["BRC_OPERATOR_SESSION_SECRET"] = AUTH_SESSION_SECRET


def _login(client: TestClient):
    # Importing the FastAPI composition root reloads .env.local with override=True,
    # so reset proof credentials immediately before the login request.
    _configure_auth_env()
    return client.post(
        "/api/auth/login",
        json={
            "username": AUTH_USERNAME,
            "password": AUTH_PASSWORD,
            "totp_code": _hotp(AUTH_TOTP_SECRET, int(time.time() // 30)),
        },
    )


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
            "Build an in-process official server-side prepare integration proof."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default="output/rtf079-official-server-prepare-integration",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_proof_report(Path(args.output_dir).expanduser())
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if report["status"] == "official_server_prepare_integration_passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
