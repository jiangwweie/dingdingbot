#!/usr/bin/env python3
"""Verify runtime-level post-submit finalize loop locally.

This verifier proves the post-submit correction path:

Runtime latest durable ExchangeSubmitExecutionResult
-> SubmitOutcomeReview
-> PostSubmitBudgetSettlement
-> RuntimePostSubmitFinalizePacket
-> NextAttemptGate

It is local and in-memory. It does not retry pre-submit rehearsal, does not
require local orders to return to CREATED, does not call OrderLifecycle or an
exchange, and treats the old authorization as replay-only evidence.
"""

from __future__ import annotations

import argparse
import asyncio
from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import time
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.application.runtime_post_submit_finalize_service import (  # noqa: E402
    RuntimePostSubmitFinalizeService,
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
    RuntimeExecutionSubmitOutcomeReview,
    build_runtime_execution_submit_outcome_review,
)
from src.domain.runtime_post_submit_finalize import (  # noqa: E402
    RuntimeNextAttemptGateStatus,
    RuntimePostSubmitFinalizeStatus,
)
from src.domain.strategy_runtime import (  # noqa: E402
    StrategyRuntimeBoundary,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)


NOW_MS = 1_786_010_000_000


class _LatestExecutionResultRepo:
    def __init__(self, result: RuntimeExecutionExchangeSubmitExecutionResult | None) -> None:
        self.result = result
        self.get_by_authorization_calls: list[str] = []
        self.latest_calls: list[str] = []

    async def get_by_authorization_id(
        self,
        authorization_id: str,
    ) -> RuntimeExecutionExchangeSubmitExecutionResult | None:
        self.get_by_authorization_calls.append(authorization_id)
        if self.result is not None and self.result.authorization_id == authorization_id:
            return self.result
        return None

    async def get_latest_by_runtime_instance_id(
        self,
        runtime_instance_id: str,
    ) -> RuntimeExecutionExchangeSubmitExecutionResult | None:
        self.latest_calls.append(runtime_instance_id)
        if self.result is not None and self.result.runtime_instance_id == runtime_instance_id:
            return self.result
        return None


class _ReviewRepo:
    def __init__(self, review: RuntimeExecutionSubmitOutcomeReview | None) -> None:
        self.review = review

    async def get_by_authorization_id(
        self,
        authorization_id: str,
    ) -> RuntimeExecutionSubmitOutcomeReview | None:
        if self.review is not None and self.review.authorization_id == authorization_id:
            return self.review
        return None


class _SettlementRepo:
    def __init__(
        self,
        settlement: RuntimeExecutionPostSubmitBudgetSettlement | None,
    ) -> None:
        self.settlement = settlement

    async def get_by_authorization_id(
        self,
        authorization_id: str,
    ) -> RuntimeExecutionPostSubmitBudgetSettlement | None:
        if (
            self.settlement is not None
            and self.settlement.authorization_id == authorization_id
        ):
            return self.settlement
        return None


class _RuntimeReader:
    def __init__(self, runtime: StrategyRuntimeInstance) -> None:
        self.runtime = runtime

    async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
        if runtime_instance_id != self.runtime.runtime_instance_id:
            raise ValueError("runtime not found")
        return self.runtime


class _AdapterMustNotRecord:
    def __init__(self) -> None:
        self.review_record_calls = 0
        self.settlement_record_calls = 0

    async def record_submit_outcome_review_for_authorization(self, *args: Any, **kwargs: Any):
        self.review_record_calls += 1
        raise AssertionError("RTF-048 verifier must reuse durable review evidence")

    async def settle_first_real_submit_budget_for_authorization(self, *args: Any, **kwargs: Any):
        self.settlement_record_calls += 1
        raise AssertionError("RTF-048 verifier must reuse durable settlement evidence")


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


def _semantic_ids() -> BrcSemanticIds:
    return BrcSemanticIds(
        runtime_instance_id="runtime-rtf048",
        trial_binding_id="binding-rtf048",
        strategy_family_id="CPM-001",
        strategy_family_version_id="CPM-001-v0",
        signal_evaluation_id="signal-eval-rtf048",
        order_candidate_id="candidate-rtf048",
    )


def _runtime(*, active: bool = True, budget_reserved: Decimal = Decimal("0")) -> StrategyRuntimeInstance:
    return StrategyRuntimeInstance(
        runtime_instance_id="runtime-rtf048",
        trial_binding_id="binding-rtf048",
        admission_decision_id="admission-rtf048",
        strategy_family_id="CPM-001",
        strategy_family_version_id="CPM-001-v0",
        symbol="BNB/USDT:USDT",
        side="long",
        status=(
            StrategyRuntimeInstanceStatus.ACTIVE
            if active
            else StrategyRuntimeInstanceStatus.PAUSED
        ),
        boundary=StrategyRuntimeBoundary(
            max_attempts=3,
            attempts_used=1,
            budget_reserved=budget_reserved,
            max_active_positions=1,
            max_notional_per_attempt=Decimal("300"),
            total_budget=Decimal("30"),
            allowed_symbols=["BNB/USDT:USDT"],
            allowed_sides=["long"],
            max_leverage=Decimal("1"),
            requires_protection=True,
            requires_review=True,
        ),
        execution_enabled=False,
        shadow_mode=True,
        created_at_ms=NOW_MS,
        updated_at_ms=NOW_MS,
        activated_at_ms=NOW_MS,
        metadata={"rtf048_post_submit_finalize_loop": True},
    )


def _submitted_order(
    local_order_id: str,
    role: str,
    exchange_order_id: str,
) -> RuntimeExecutionSubmittedExchangeOrder:
    return RuntimeExecutionSubmittedExchangeOrder(
        local_order_id=local_order_id,
        order_role=role,
        exchange_order_id=exchange_order_id,
        exchange_status="OPEN",
        amount="1",
        filled_qty="0",
        average_exec_price=None,
        reduce_only=role != "ENTRY",
        order_lifecycle_submit_called=True,
    )


def _execution_result() -> RuntimeExecutionExchangeSubmitExecutionResult:
    submitted_orders = [
        _submitted_order("entry-rtf048", "ENTRY", "ex-entry-rtf048"),
        _submitted_order("sl-rtf048", "SL", "ex-sl-rtf048"),
    ]
    return RuntimeExecutionExchangeSubmitExecutionResult(
        execution_result_id="exchange-submit-result-rtf048",
        enablement_decision_id="exchange-submit-enable-rtf048",
        submit_preview_id="submit-preview-rtf048",
        binding_id="binding-rtf048",
        authorization_id="auth-rtf048-consumed",
        execution_intent_id="intent-rtf048",
        runtime_instance_id="runtime-rtf048",
        source_type="brc_runtime_order_candidate",
        source_id="candidate-rtf048",
        semantic_ids=_semantic_ids(),
        status=(
            RuntimeExecutionExchangeSubmitExecutionStatus
            .EXCHANGE_SUBMIT_ORDERS_SUBMITTED
        ),
        symbol="BNB/USDT:USDT",
        exchange_submit_action_authorization_id="exchange-submit-action-rtf048",
        local_order_ids=["entry-rtf048", "sl-rtf048"],
        entry_order_id="entry-rtf048",
        protection_order_ids=["sl-rtf048"],
        submitted_orders=submitted_orders,
        submitted_local_order_ids=[item.local_order_id for item in submitted_orders],
        submitted_exchange_order_ids=[
            item.exchange_order_id
            for item in submitted_orders
            if item.exchange_order_id is not None
        ],
        entry_exchange_order_id="ex-entry-rtf048",
        protection_exchange_order_ids=["ex-sl-rtf048"],
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
        metadata={"scope": "rtf048_durable_execution_result"},
    )


def _order(
    order_id: str,
    role: OrderRole,
    status: OrderStatus,
    filled_qty: Decimal,
) -> Order:
    return Order(
        id=order_id,
        signal_id="signal-eval-rtf048",
        exchange_order_id=f"ex-{order_id}",
        symbol="BNB/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET if role == OrderRole.ENTRY else OrderType.STOP_MARKET,
        order_role=role,
        price=None,
        trigger_price=Decimal("280") if role == OrderRole.SL else None,
        requested_qty=Decimal("1"),
        filled_qty=filled_qty,
        average_exec_price=Decimal("300") if filled_qty > Decimal("0") else None,
        status=status,
        created_at=NOW_MS,
        updated_at=NOW_MS,
        reduce_only=role != OrderRole.ENTRY,
        runtime_instance_id="runtime-rtf048",
        trial_binding_id="binding-rtf048",
        strategy_family_id="CPM-001",
        strategy_family_version_id="CPM-001-v0",
        signal_evaluation_id="signal-eval-rtf048",
        order_candidate_id="candidate-rtf048",
    )


def _clean_reconciliation_report() -> Any:
    return SimpleNamespace(
        report_id="recon-clean-rtf048",
        symbol="BNB/USDT:USDT",
        checked_at_ms=NOW_MS,
        is_consistent=True,
        severe_count=0,
        warning_count=0,
        is_fetch_failure=False,
        runtime_instance_id="runtime-rtf048",
    )


def _review() -> RuntimeExecutionSubmitOutcomeReview:
    return build_runtime_execution_submit_outcome_review(
        exchange_submit_execution_result=_execution_result(),
        local_orders=[
            _order("entry-rtf048", OrderRole.ENTRY, OrderStatus.CANCELED, Decimal("0")),
            _order("sl-rtf048", OrderRole.SL, OrderStatus.CANCELED, Decimal("0")),
        ],
        post_submit_reconciliation_report=_clean_reconciliation_report(),
        now_ms=NOW_MS,
    )


def _settlement() -> RuntimeExecutionPostSubmitBudgetSettlement:
    return RuntimeExecutionPostSubmitBudgetSettlement(
        settlement_id="runtime-post-submit-budget-settlement-rtf048",
        accounting_id="runtime-first-real-submit-outcome-accounting-rtf048",
        authorization_id="auth-rtf048-consumed",
        execution_intent_id="intent-rtf048",
        runtime_instance_id="runtime-rtf048",
        reservation_id="runtime-attempt-reservation-rtf048",
        mutation_id="runtime-attempt-mutation-rtf048",
        attempt_outcome_policy_id="runtime-attempt-outcome-policy-rtf048",
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
        metadata={"scope": "rtf048_budget_settlement"},
    )


async def _scenario(
    *,
    scenario_id: str,
    execution_result_available: bool,
    active_positions_count: int | None,
    expected_status: RuntimePostSubmitFinalizeStatus | None,
) -> dict[str, Any]:
    runtime = _runtime()
    result = _execution_result() if execution_result_available else None
    review = _review() if execution_result_available else None
    settlement = _settlement() if execution_result_available else None
    result_repo = _LatestExecutionResultRepo(result)
    adapter = _AdapterMustNotRecord()
    service = RuntimePostSubmitFinalizeService(
        adapter_service=adapter,
        exchange_submit_execution_result_repository=result_repo,
        submit_outcome_review_repository=_ReviewRepo(review),
        post_submit_budget_settlement_repository=_SettlementRepo(settlement),
        runtime_service=_RuntimeReader(runtime),
    )
    finalize_artifact = await service.finalize_latest_for_runtime(
        "runtime-rtf048",
        reservation_id="runtime-attempt-reservation-rtf048",
        active_positions_count=active_positions_count,
        closed_review_required=False,
    )
    expected_ok = (
        expected_status is None
        or finalize_artifact.status == expected_status
    )
    checks = {
        "latest_result_resolved_without_manual_authorization": (
            result_repo.latest_calls == ["runtime-rtf048"]
        ),
        "old_authorization_replay_only": (
            finalize_artifact.consumed_authorization_replay_only is True
            and finalize_artifact.old_authorization_submit_retry_allowed is False
        ),
        "pre_submit_rehearsal_retry_disallowed": (
            finalize_artifact.pre_submit_rehearsal_retry_allowed is False
            and finalize_artifact.next_attempt_gate.pre_submit_rehearsal_retry_allowed
            is False
        ),
        "local_created_order_requirement_retired": (
            finalize_artifact.local_created_order_requirement_retired is True
        ),
        "requires_fresh_signal_and_authorization": (
            finalize_artifact.next_attempt_gate.requires_fresh_strategy_signal is True
            and finalize_artifact.next_attempt_gate.requires_fresh_authorization is True
        ),
        "adapter_not_used_to_create_missing_facts": (
            adapter.review_record_calls == 0
            and adapter.settlement_record_calls == 0
        ),
        "no_execution_side_effects": (
            finalize_artifact.execution_intent_created is False
            and finalize_artifact.order_created is False
            and finalize_artifact.order_lifecycle_called is False
            and finalize_artifact.exchange_called is False
            and finalize_artifact.withdrawal_or_transfer_created is False
        ),
        "expected_status": expected_ok,
    }
    return {
        "scenario_id": scenario_id,
        "status": "passed" if all(checks.values()) else "failed",
        "finalize_status": finalize_artifact.status.value,
        "next_attempt_gate_status": finalize_artifact.next_attempt_gate.status.value,
        "blockers": list(finalize_artifact.blockers),
        "next_attempt_blockers": list(finalize_artifact.next_attempt_gate.blockers),
        "warnings": list(finalize_artifact.warnings),
        "checks": checks,
        "finalize_artifact": _json_value(finalize_artifact),
    }


async def build_post_submit_finalize_loop_report() -> dict[str, Any]:
    scenarios = [
        await _scenario(
            scenario_id="latest-result-ready-for-fresh-signal",
            execution_result_available=True,
            active_positions_count=0,
            expected_status=(
                RuntimePostSubmitFinalizeStatus
                .FINALIZED_READY_FOR_NEXT_ATTEMPT
            ),
        ),
        await _scenario(
            scenario_id="latest-result-active-position-blocks-next-attempt",
            execution_result_available=True,
            active_positions_count=1,
            expected_status=(
                RuntimePostSubmitFinalizeStatus
                .FINALIZED_NEXT_ATTEMPT_BLOCKED
            ),
        ),
        await _scenario(
            scenario_id="latest-result-missing-blocks-finalize",
            execution_result_available=False,
            active_positions_count=None,
            expected_status=RuntimePostSubmitFinalizeStatus.BLOCKED,
        ),
    ]
    passed = all(item["status"] == "passed" for item in scenarios)
    return {
        "scope": "rtf048_runtime_post_submit_finalize_loop",
        "status": (
            "rtf048_runtime_post_submit_finalize_loop_passed"
            if passed
            else "rtf048_runtime_post_submit_finalize_loop_failed"
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
        description="Verify local runtime post-submit finalize loop.",
    )
    parser.parse_args()
    report = asyncio.run(build_post_submit_finalize_loop_report())
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(payload)
    return 0 if report["status"].endswith("_passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
