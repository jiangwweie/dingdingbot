#!/usr/bin/env python3
"""Verify next-attempt gate -> strategy planning locally.

This verifier proves that a finalized post-submit runtime payload can move into
fresh strategy-signal planning without reusing the consumed authorization, and
without creating executable intents, orders, OrderLifecycle calls, exchange
writes, withdrawals, or transfers.
"""

from __future__ import annotations

import argparse
import asyncio
from decimal import Decimal
import json
from pathlib import Path
import sys
import time
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.build_runtime_strategy_signal_input_artifact import (  # noqa: E402
    _build_signal_input,
)
from src.application.runtime_next_attempt_strategy_planning_service import (  # noqa: E402
    RuntimeNextAttemptStrategyPlanningService,
    RuntimeNextAttemptStrategyPlanningStatus,
)
from src.application.runtime_strategy_signal_planning_service import (  # noqa: E402
    RuntimeStrategySignalCandidatePlanningStatus,
    RuntimeStrategySignalPlanningService,
)
from src.application.strategy_group_live_readonly_observation import (  # noqa: E402
    SampleStrategyGroupMarketBarSource,
)
from src.application.strategy_runtime_fact_overlay_service import (  # noqa: E402
    StrategyRuntimeFactOverlayService,
)
from src.application.strategy_semantics_shadow_binding_service import (  # noqa: E402
    StrategySemanticsShadowBindingService,
)
from src.application.trial_readiness_account_facts import (  # noqa: E402
    AccountFactsFreshnessStatus,
    AccountFactsReconciliationStatus,
    AccountFactsSourceType,
    StaticTrialReadinessAccountFactsSource,
    TrialReadinessAccountFacts,
)
from src.domain.brc_audit_ids import BrcSemanticIds  # noqa: E402
from src.domain.models import Direction, Order, OrderRole, OrderStatus, OrderType  # noqa: E402
from src.domain.runtime_execution_attempt_outcome_policy import (  # noqa: E402
    RuntimeExecutionAttemptBudgetAction,
)
from src.domain.runtime_execution_exchange_submit_execution_result import (  # noqa: E402
    RuntimeExecutionExchangeSubmitExecutionMode,
    RuntimeExecutionExchangeSubmitExecutionResult,
    RuntimeExecutionExchangeSubmitExecutionStatus,
    RuntimeExecutionSubmittedExchangeOrder,
)
from src.domain.runtime_execution_post_submit_budget_settlement import (  # noqa: E402
    RuntimeExecutionPostSubmitBudgetSettlement,
    RuntimeExecutionPostSubmitBudgetSettlementStatus,
)
from src.domain.runtime_execution_submit_outcome_review import (  # noqa: E402
    build_runtime_execution_submit_outcome_review,
)
from src.domain.runtime_post_submit_finalize import (  # noqa: E402
    RuntimePostSubmitFinalizePayload,
    build_runtime_post_submit_finalize_payload,
)
from src.domain.signal_evaluation import (  # noqa: E402
    OrderCandidate,
    SignalEvaluation,
    SignalEvaluationDecision,
    SignalEvaluationStatus,
)
from src.domain.strategy_family_signal import (  # noqa: E402
    SignalSide,
    StrategyFamilySignalOutput,
)
from src.domain.strategy_runtime import (  # noqa: E402
    StrategyRuntimeBoundary,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)


NOW_MS = 1_786_020_000_000


class _NoActivePositionsSource:
    async def list_active(self, *, symbol: str | None = None, limit: int = 100) -> list[Any]:
        return []


class _InMemoryShadowService:
    def __init__(self, *, suffix: str) -> None:
        self.suffix = suffix
        self.evaluation: SignalEvaluation | None = None

    async def create_signal_evaluation_from_strategy_family_output(
        self,
        output: StrategyFamilySignalOutput,
        *,
        runtime: StrategyRuntimeInstance | None = None,
        metadata: dict | None = None,
    ) -> SignalEvaluation:
        side = "none" if output.side == SignalSide.NONE else output.side.value
        self.evaluation = SignalEvaluation(
            signal_evaluation_id=f"signal-eval-rtf049-{self.suffix}",
            runtime_instance_id=runtime.runtime_instance_id if runtime else None,
            trial_binding_id=runtime.trial_binding_id if runtime else None,
            strategy_family_id=output.strategy_family_id,
            strategy_family_version_id=output.strategy_family_version_id,
            source_signal_id=output.signal_id,
            symbol=output.symbol,
            side=side,
            status=SignalEvaluationStatus.EVALUATED,
            decision=(
                SignalEvaluationDecision.CANDIDATE
                if side in {"long", "short"}
                else SignalEvaluationDecision.NO_ACTION
            ),
            reason_codes=list(output.reason_codes),
            rationale=output.human_summary,
            evidence_snapshot=output.model_dump(mode="json"),
            policy_snapshot={"required_execution_mode": output.required_execution_mode},
            evaluated_at_ms=NOW_MS,
            created_at_ms=NOW_MS,
            updated_at_ms=NOW_MS,
            metadata=metadata or {},
        )
        return self.evaluation

    async def get_signal_evaluation(self, signal_evaluation_id: str) -> SignalEvaluation:
        if self.evaluation is None:
            raise RuntimeError("signal evaluation not created")
        if signal_evaluation_id != self.evaluation.signal_evaluation_id:
            raise RuntimeError("unexpected signal evaluation id")
        return self.evaluation

    async def create_order_candidate_from_signal_evaluation(
        self,
        signal_evaluation_id: str,
        **kwargs: Any,
    ) -> OrderCandidate:
        if self.evaluation is None:
            raise RuntimeError("signal evaluation not created")
        return OrderCandidate(
            order_candidate_id=f"order-candidate-rtf049-{self.suffix}",
            signal_evaluation_id=signal_evaluation_id,
            runtime_instance_id=self.evaluation.runtime_instance_id,
            trial_binding_id=self.evaluation.trial_binding_id,
            strategy_family_id=self.evaluation.strategy_family_id,
            strategy_family_version_id=self.evaluation.strategy_family_version_id,
            symbol=self.evaluation.symbol,
            side=self.evaluation.side,  # type: ignore[arg-type]
            candidate_order_type=kwargs["candidate_order_type"],
            proposed_quantity=kwargs.get("proposed_quantity"),
            intended_notional=kwargs.get("intended_notional"),
            entry_price_reference=kwargs.get("entry_price_reference"),
            risk_preview=kwargs["risk_preview"],
            protection_preview=kwargs["protection_preview"],
            rationale=kwargs.get("rationale") or self.evaluation.rationale,
            evidence_refs=kwargs["evidence_refs"],
            created_at_ms=NOW_MS,
            updated_at_ms=NOW_MS,
            expires_at_ms=kwargs.get("expires_at_ms"),
            metadata=kwargs["metadata"],
        )


class _CountingPlanner:
    def __init__(self, delegate: RuntimeStrategySignalPlanningService) -> None:
        self.delegate = delegate
        self.calls = 0
        self.last_metadata: dict[str, Any] | None = None

    async def plan_shadow_candidate_from_signal_input(self, *args: Any, **kwargs: Any):
        self.calls += 1
        self.last_metadata = dict(kwargs.get("metadata") or {})
        return await self.delegate.plan_shadow_candidate_from_signal_input(*args, **kwargs)


def _json_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _json_value(value.model_dump(mode="python"))
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _runtime(
    *,
    family_id: str,
    version_id: str,
    symbol: str,
    side: str,
    suffix: str,
    budget_reserved: Decimal = Decimal("0"),
) -> StrategyRuntimeInstance:
    return StrategyRuntimeInstance(
        runtime_instance_id=f"runtime-rtf049-{suffix}",
        trial_binding_id=f"binding-rtf049-{suffix}",
        admission_decision_id=f"admission-rtf049-{suffix}",
        strategy_family_id=family_id,
        strategy_family_version_id=version_id,
        symbol=symbol,
        side=side,
        status=StrategyRuntimeInstanceStatus.ACTIVE,
        boundary=StrategyRuntimeBoundary(
            max_attempts=3,
            attempts_used=1,
            budget_reserved=budget_reserved,
            max_active_positions=1,
            max_notional_per_attempt=Decimal("8"),
            total_budget=Decimal("30"),
            allowed_symbols=[symbol],
            allowed_sides=[side],
            max_leverage=Decimal("1"),
            max_margin_per_attempt=Decimal("8"),
            requires_protection=True,
            requires_review=True,
        ),
        execution_enabled=False,
        shadow_mode=True,
        created_at_ms=NOW_MS,
        updated_at_ms=NOW_MS,
        activated_at_ms=NOW_MS,
        metadata={"rtf049_next_attempt_gate_strategy_planning": True},
    )


def _semantic_ids(runtime: StrategyRuntimeInstance) -> BrcSemanticIds:
    return BrcSemanticIds(
        runtime_instance_id=runtime.runtime_instance_id,
        trial_binding_id=runtime.trial_binding_id,
        strategy_family_id=runtime.strategy_family_id,
        strategy_family_version_id=runtime.strategy_family_version_id,
        signal_evaluation_id=f"signal-eval-{runtime.runtime_instance_id}",
        order_candidate_id=f"candidate-{runtime.runtime_instance_id}",
    )


def _submitted_order(local_order_id: str, role: str) -> RuntimeExecutionSubmittedExchangeOrder:
    return RuntimeExecutionSubmittedExchangeOrder(
        local_order_id=local_order_id,
        order_role=role,
        exchange_order_id=f"ex-{local_order_id}",
        exchange_status="OPEN",
        amount="1",
        filled_qty="0",
        average_exec_price=None,
        reduce_only=role != "ENTRY",
        order_lifecycle_submit_called=True,
    )


def _execution_result(runtime: StrategyRuntimeInstance) -> RuntimeExecutionExchangeSubmitExecutionResult:
    suffix = runtime.runtime_instance_id
    submitted_orders = [
        _submitted_order(f"entry-{suffix}", "ENTRY"),
        _submitted_order(f"sl-{suffix}", "SL"),
    ]
    return RuntimeExecutionExchangeSubmitExecutionResult(
        execution_result_id=f"exchange-submit-result-{suffix}",
        enablement_decision_id=f"exchange-submit-enable-{suffix}",
        submit_preview_id=f"submit-preview-{suffix}",
        binding_id=runtime.trial_binding_id,
        authorization_id=f"auth-{suffix}-consumed",
        execution_intent_id=f"intent-{suffix}",
        runtime_instance_id=runtime.runtime_instance_id,
        source_type="brc_runtime_order_candidate",
        source_id=f"candidate-{suffix}",
        semantic_ids=_semantic_ids(runtime),
        status=(
            RuntimeExecutionExchangeSubmitExecutionStatus
            .EXCHANGE_SUBMIT_ORDERS_SUBMITTED
        ),
        symbol=runtime.symbol,
        exchange_submit_action_authorization_id=f"exchange-submit-action-{suffix}",
        local_order_ids=[item.local_order_id for item in submitted_orders],
        entry_order_id=f"entry-{suffix}",
        protection_order_ids=[f"sl-{suffix}"],
        submitted_orders=submitted_orders,
        submitted_local_order_ids=[item.local_order_id for item in submitted_orders],
        submitted_exchange_order_ids=[
            item.exchange_order_id
            for item in submitted_orders
            if item.exchange_order_id is not None
        ],
        entry_exchange_order_id=f"ex-entry-{suffix}",
        protection_exchange_order_ids=[f"ex-sl-{suffix}"],
        exchange_submit_execution_enabled=True,
        execution_mode=RuntimeExecutionExchangeSubmitExecutionMode.IN_MEMORY_SIMULATION,
        exchange_call_count=2,
        order_lifecycle_submit_call_count=2,
        blockers=[],
        warnings=[],
        real_exchange_submit_adapter_executed=True,
        exchange_order_submitted=True,
        exchange_called=True,
        order_lifecycle_submit_called=True,
        execution_intent_status_changed=False,
        owner_bounded_execution_called=False,
        withdrawal_or_transfer_created=False,
        created_at_ms=NOW_MS,
        metadata={"scope": "rtf049_durable_execution_result"},
    )


def _order(
    runtime: StrategyRuntimeInstance,
    *,
    role: OrderRole,
    status: OrderStatus,
    filled_qty: Decimal,
) -> Order:
    order_id = f"{role.value.lower()}-{runtime.runtime_instance_id}"
    return Order(
        id=order_id,
        signal_id=f"signal-eval-{runtime.runtime_instance_id}",
        exchange_order_id=f"ex-{order_id}",
        symbol=runtime.symbol,
        direction=Direction.LONG if runtime.side == "long" else Direction.SHORT,
        order_type=OrderType.MARKET if role == OrderRole.ENTRY else OrderType.STOP_MARKET,
        order_role=role,
        price=None,
        trigger_price=Decimal("90") if role == OrderRole.SL else None,
        requested_qty=Decimal("1"),
        filled_qty=filled_qty,
        average_exec_price=Decimal("100") if filled_qty > Decimal("0") else None,
        status=status,
        created_at=NOW_MS,
        updated_at=NOW_MS,
        reduce_only=role != OrderRole.ENTRY,
        runtime_instance_id=runtime.runtime_instance_id,
        trial_binding_id=runtime.trial_binding_id,
        strategy_family_id=runtime.strategy_family_id,
        strategy_family_version_id=runtime.strategy_family_version_id,
        signal_evaluation_id=f"signal-eval-{runtime.runtime_instance_id}",
        order_candidate_id=f"candidate-{runtime.runtime_instance_id}",
    )


def _reconciliation(runtime: StrategyRuntimeInstance) -> Any:
    return type(
        "ReconciliationReport",
        (),
        {
            "report_id": f"recon-{runtime.runtime_instance_id}",
            "symbol": runtime.symbol,
            "checked_at_ms": NOW_MS,
            "is_consistent": True,
            "severe_count": 0,
            "warning_count": 0,
            "is_fetch_failure": False,
            "runtime_instance_id": runtime.runtime_instance_id,
        },
    )()


def _settlement(runtime: StrategyRuntimeInstance) -> RuntimeExecutionPostSubmitBudgetSettlement:
    suffix = runtime.runtime_instance_id
    return RuntimeExecutionPostSubmitBudgetSettlement(
        settlement_id=f"runtime-post-submit-budget-settlement-{suffix}",
        accounting_id=f"runtime-first-real-submit-outcome-accounting-{suffix}",
        authorization_id=f"auth-{suffix}-consumed",
        execution_intent_id=f"intent-{suffix}",
        runtime_instance_id=runtime.runtime_instance_id,
        reservation_id=f"runtime-attempt-reservation-{suffix}",
        mutation_id=f"runtime-attempt-mutation-{suffix}",
        attempt_outcome_policy_id=f"runtime-attempt-outcome-policy-{suffix}",
        status=(
            RuntimeExecutionPostSubmitBudgetSettlementStatus
            .RELEASED_RESERVED_BUDGET
        ),
        runtime_status_before=StrategyRuntimeInstanceStatus.ACTIVE,
        runtime_status_after=StrategyRuntimeInstanceStatus.ACTIVE,
        budget_action=RuntimeExecutionAttemptBudgetAction.RELEASE_RESERVED_BUDGET,
        outcome_kind="submitted_no_fill_cancelled",
        budget_reservation_amount=Decimal("6"),
        budget_release_amount=Decimal("6"),
        budget_reserved_before=Decimal("6"),
        budget_reserved_after=Decimal("0"),
        budget_remaining_before=Decimal("24"),
        budget_remaining_after=Decimal("30"),
        attempts_used_before=1,
        attempts_used_after=1,
        attempts_remaining_before=2,
        attempts_remaining_after=2,
        blockers=[],
        warnings=[],
        runtime_state_mutated=True,
        runtime_budget_mutated=True,
        attempt_already_consumed=True,
        budget_released=True,
        budget_consumption_recorded=False,
        reserved_budget_remains_held=False,
        requires_reconciliation_before_retry=True,
        blocks_new_entries_until_resolved=False,
        created_at_ms=NOW_MS + 1,
        metadata={"scope": "rtf049_budget_settlement"},
    )


def _finalize_payload(
    runtime: StrategyRuntimeInstance,
    *,
    active_positions_count: int | None,
) -> RuntimePostSubmitFinalizePayload:
    result = _execution_result(runtime)
    review = build_runtime_execution_submit_outcome_review(
        exchange_submit_execution_result=result,
        local_orders=[
            _order(runtime, role=OrderRole.ENTRY, status=OrderStatus.CANCELED, filled_qty=Decimal("0")),
            _order(runtime, role=OrderRole.SL, status=OrderStatus.CANCELED, filled_qty=Decimal("0")),
        ],
        post_submit_reconciliation_report=_reconciliation(runtime),
        now_ms=NOW_MS,
    )
    return build_runtime_post_submit_finalize_payload(
        authorization_id=result.authorization_id,
        runtime=runtime,
        exchange_submit_execution_result=result,
        submit_outcome_review=review,
        post_submit_budget_settlement=_settlement(runtime),
        active_positions_count=active_positions_count,
        closed_review_required=False,
        now_ms=NOW_MS,
    )


def _account_facts() -> TrialReadinessAccountFacts:
    return TrialReadinessAccountFacts(
        account_id="local-rtf049-fake-account",
        account_type="usdt_futures_read_only_snapshot",
        source_id="local_rtf049_injected_read_only_account_facts",
        source_type=AccountFactsSourceType.INJECTED_FAKE,
        account_equity=Decimal("30"),
        available_margin=Decimal("30"),
        timestamp_ms=NOW_MS,
        freshness_status=AccountFactsFreshnessStatus.FRESH,
        reconciliation_status=AccountFactsReconciliationStatus.CLEAN,
        read_only_guarantee=True,
        external_call_performed=False,
        external_call_type="none",
        notes=("local in-memory RTF-049 verifier facts",),
    )


def _signal_input(runtime: StrategyRuntimeInstance, *, suffix: str) -> Any:
    source = SampleStrategyGroupMarketBarSource()
    one_hour = source.latest_closed_candles(symbol=runtime.symbol, timeframe="1h", limit=25)
    four_hour = source.latest_closed_candles(symbol=runtime.symbol, timeframe="4h", limit=25)
    return _build_signal_input(
        runtime=runtime,
        one_hour=one_hour,
        four_hour=four_hour,
        source_id=source.source_id,
        source_type="sample_rehearsal",
        evaluation_id=f"runtime-signal-input-rtf049-{suffix}",
        playbook_id=f"rtf049-{suffix}-playbook",
        now_ms=NOW_MS,
    )


def _planner(*, suffix: str) -> _CountingPlanner:
    shadow = _InMemoryShadowService(suffix=suffix)
    service = RuntimeStrategySignalPlanningService(
        semantics_binding_service=StrategySemanticsShadowBindingService(
            shadow_service=shadow,
        ),
        runtime_execution_planning_service=object(),
        runtime_fact_overlay_service=StrategyRuntimeFactOverlayService(
            active_position_source=_NoActivePositionsSource(),
            account_facts_source=StaticTrialReadinessAccountFactsSource(_account_facts()),
            require_trusted_account_source=True,
            require_trusted_market_fact_source=False,
        ),
    )
    return _CountingPlanner(service)


async def _scenario(
    *,
    scenario_id: str,
    family_id: str,
    version_id: str,
    symbol: str,
    side: str,
    active_positions_count: int | None,
    expected_status: RuntimeNextAttemptStrategyPlanningStatus,
) -> dict[str, Any]:
    runtime = _runtime(
        family_id=family_id,
        version_id=version_id,
        symbol=symbol,
        side=side,
        suffix=scenario_id,
    )
    finalize_payload = _finalize_payload(
        runtime,
        active_positions_count=active_positions_count,
    )
    planner = _planner(suffix=scenario_id)
    service = RuntimeNextAttemptStrategyPlanningService(strategy_signal_planner=planner)
    artifact = await service.plan_from_post_submit_gate(
        post_submit_finalize_payload=finalize_payload,
        signal_input=_signal_input(runtime, suffix=scenario_id),
        runtime=runtime,
        context_id=f"strategy-context-rtf049-{scenario_id}",
        expires_at_ms=NOW_MS + 15 * 60 * 1000,
        metadata={"rtf049": True, "local_in_memory_only": True},
    )
    should_call_planner = (
        finalize_payload.status.value == "finalized_ready_for_next_attempt"
    )
    checks = {
        "expected_status": artifact.status == expected_status,
        "planner_call_boundary": (
            planner.calls == 1 if should_call_planner else planner.calls == 0
        ),
        "consumed_authorization_replay_only": (
            artifact.consumed_authorization_replay_only is True
            and artifact.old_authorization_submit_retry_allowed is False
        ),
        "fresh_signal_required": artifact.requires_fresh_strategy_signal is True,
        "fresh_authorization_required_before_submit": (
            artifact.requires_fresh_authorization_before_submit is True
        ),
        "pre_submit_rehearsal_retry_disallowed": (
            artifact.pre_submit_rehearsal_retry_allowed is False
        ),
        "no_execution_side_effects": (
            artifact.execution_intent_created is False
            and artifact.executable_execution_intent_created is False
            and artifact.order_created is False
            and artifact.order_lifecycle_called is False
            and artifact.exchange_called is False
            and artifact.exchange_order_submitted is False
            and artifact.withdrawal_or_transfer_created is False
        ),
    }
    if artifact.status == RuntimeNextAttemptStrategyPlanningStatus.READY_FOR_FINAL_GATE_PREFLIGHT:
        checks["shadow_candidate_created"] = (
            artifact.order_candidate_id is not None
            and artifact.candidate_planning_status
            == RuntimeStrategySignalCandidatePlanningStatus.SHADOW_CANDIDATE_CREATED
            and artifact.strategy_planning_plan.get("requires_official_final_gate") is True
        )
    else:
        checks["shadow_candidate_created"] = artifact.order_candidate_id is None
    return {
        "scenario_id": scenario_id,
        "status": "passed" if all(checks.values()) else "failed",
        "post_submit_status": finalize_payload.status.value,
        "next_attempt_gate_status": finalize_payload.next_attempt_gate.status.value,
        "strategy_planning_status": artifact.status.value,
        "planner_calls": planner.calls,
        "order_candidate_id": artifact.order_candidate_id,
        "blockers": list(artifact.blockers),
        "warnings": list(artifact.warnings),
        "checks": checks,
        "post_submit_finalize_payload": _json_value(finalize_payload),
        "strategy_planning_artifact": _json_value(artifact),
    }


async def build_next_attempt_gate_strategy_planning_report() -> dict[str, Any]:
    scenarios = [
        await _scenario(
            scenario_id="ready-cpm-long",
            family_id="CPM-RO-001",
            version_id="CPM-RO-001-v0",
            symbol="ETH/USDT:USDT",
            side="long",
            active_positions_count=0,
            expected_status=(
                RuntimeNextAttemptStrategyPlanningStatus
                .READY_FOR_FINAL_GATE_PREFLIGHT
            ),
        ),
        await _scenario(
            scenario_id="blocked-active-position",
            family_id="CPM-RO-001",
            version_id="CPM-RO-001-v0",
            symbol="ETH/USDT:USDT",
            side="long",
            active_positions_count=1,
            expected_status=(
                RuntimeNextAttemptStrategyPlanningStatus
                .BLOCKED_BY_POST_SUBMIT_GATE
            ),
        ),
        await _scenario(
            scenario_id="waiting-rmr-observe-only",
            family_id="RMR-001",
            version_id="RMR-001-v0",
            symbol="ETH/USDT:USDT",
            side="long",
            active_positions_count=0,
            expected_status=RuntimeNextAttemptStrategyPlanningStatus.WAITING_FOR_SIGNAL,
        ),
    ]
    passed = all(item["status"] == "passed" for item in scenarios)
    return {
        "scope": "rtf049_next_attempt_gate_strategy_planning",
        "status": (
            "rtf049_next_attempt_gate_strategy_planning_passed"
            if passed
            else "rtf049_next_attempt_gate_strategy_planning_failed"
        ),
        "generated_at_ms": int(time.time() * 1000),
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
        "safety_summary": {
            "local_in_memory_only": True,
            "database_connected": False,
            "http_network_called": False,
            "exchange_write_called": False,
            "pre_submit_rehearsal_called": False,
            "order_lifecycle_called": False,
            "execution_intent_created": False,
            "order_created": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify next-attempt gate to strategy planning locally.",
    )
    parser.add_argument("--output-json")
    args = parser.parse_args()
    report = asyncio.run(build_next_attempt_gate_strategy_planning_report())
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["status"].endswith("_passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
