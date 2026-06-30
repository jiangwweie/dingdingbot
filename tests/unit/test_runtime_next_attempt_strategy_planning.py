from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.application.runtime_next_attempt_strategy_planning_service import (
    RuntimeNextAttemptStrategyPlanningService,
    RuntimeNextAttemptStrategyPlanningStatus,
)
from src.application.runtime_strategy_signal_evaluation_service import (
    RuntimeStrategySignalEvaluationResult,
    RuntimeStrategySignalEvaluationStatus,
)
from src.application.runtime_strategy_signal_planning_service import (
    RuntimeStrategySignalCandidatePlanningResult,
    RuntimeStrategySignalCandidatePlanningStatus,
)
from src.domain.runtime_next_attempt_release import (
    RuntimeNextAttemptReleaseStatus,
    build_runtime_next_attempt_release_evidence,
)
from src.domain.runtime_execution_post_submit_budget_settlement import (
    RuntimeExecutionPostSubmitBudgetSettlementStatus,
)
from src.domain.runtime_post_submit_finalize import (
    build_runtime_post_submit_finalize_payload,
)
from src.domain.signal_evaluation import OrderCandidate
from src.domain.strategy_family_signal import (
    AccountFactsSnapshot,
    MarketSnapshot,
    SignalSide,
    StrategyFamilySignalInput,
)
from tests.unit.test_runtime_execution_submit_outcome_review import (
    NOW_MS,
    _runtime,
    _settlement,
    _submitted_result,
)
from tests.unit.test_runtime_post_submit_finalize import (
    _ready_review_no_fill_cancelled,
)
from tests.unit.test_runtime_next_attempt_release import (
    _clear_gate,
    _resolution,
)
from src.domain.runtime_active_position_resolution import (
    RuntimeActivePositionResolutionStatus,
)


def _signal_input(*, evaluation_id: str = "eval-fresh") -> StrategyFamilySignalInput:
    return StrategyFamilySignalInput(
        evaluation_id=evaluation_id,
        strategy_family_id="CPM-001",
        strategy_family_version_id="CPM-001-v0",
        symbol="BNB/USDT:USDT",
        timestamp_ms=NOW_MS,
        primary_timeframe="1h",
        context_timeframes=["4h"],
        market_snapshot=MarketSnapshot(
            symbol="BNB/USDT:USDT",
            timestamp_ms=NOW_MS,
            source="unit_market_read_only",
            freshness="fresh",
            last_price=Decimal("600"),
            mark_price=Decimal("600"),
            atr=Decimal("10"),
            timeframe="1h",
            candle_context={"closed_bar": True, "windows": {"1h": [], "4h": []}},
        ),
        account_facts_snapshot=AccountFactsSnapshot(
            source="unit_account_read_only",
            truth_level="exchange_read",
            timestamp_ms=NOW_MS,
            freshness="fresh",
            account_status="normal",
            available_balance=Decimal("30"),
            positions=[],
            open_orders=[],
            position_count=0,
            open_order_count=0,
            unknown_unmanaged_counts={"positions": 0, "orders": 0},
            reconciliation_status={"status": "clean"},
            read_only_provider="unit_test",
        ),
        position_open_order_summary={
            "active_positions_count": 0,
            "open_order_count": 0,
        },
        reconciliation_status={"status": "clean"},
        runtime_safety_snapshot={"runtime_state": "active"},
        trial_constraints_snapshot={
            "max_attempts": 3,
            "max_loss_budget": "30",
            "max_active_positions": 1,
            "max_notional_per_attempt": "30",
            "allowed_symbols": ["BNB/USDT:USDT"],
            "allowed_sides": ["long"],
            "max_leverage": "1",
        },
        source="unit_test",
        freshness="fresh",
    )


def _ready_post_submit_payload():
    return build_runtime_post_submit_finalize_payload(
        authorization_id="auth-1",
        runtime=_runtime(boundary={"budget_reserved": Decimal("0")}),
        exchange_submit_execution_result=_submitted_result(),
        submit_outcome_review=_ready_review_no_fill_cancelled(),
        post_submit_budget_settlement=_settlement(
            status=(
                RuntimeExecutionPostSubmitBudgetSettlementStatus
                .RELEASED_RESERVED_BUDGET
            ),
            budget_reserved_after=Decimal("0"),
            budget_remaining_after=Decimal("30"),
            budget_released=True,
            reserved_budget_remains_held=False,
            requires_reconciliation_before_retry=True,
            blocks_new_entries_until_resolved=False,
        ),
        active_positions_count=0,
        closed_review_required=False,
        now_ms=NOW_MS,
    )


def _blocked_post_submit_payload():
    return build_runtime_post_submit_finalize_payload(
        authorization_id="auth-1",
        runtime=_runtime(),
        exchange_submit_execution_result=_submitted_result(),
        submit_outcome_review=_ready_review_no_fill_cancelled(),
        post_submit_budget_settlement=_settlement(),
        active_positions_count=1,
        closed_review_required=False,
        now_ms=NOW_MS,
    )


def _ready_release_evidence():
    return build_runtime_next_attempt_release_evidence(
        active_position_resolution=_resolution(
            RuntimeActivePositionResolutionStatus.READY_FOR_NEXT_ATTEMPT_GATE,
        ),
        next_attempt_gate_evidence=_clear_gate(),
        now_ms=NOW_MS,
    )


def _blocked_release_evidence():
    return build_runtime_next_attempt_release_evidence(
        active_position_resolution=_resolution(
            RuntimeActivePositionResolutionStatus.HOLD_WITH_HARD_STOP,
        ),
        next_attempt_gate_evidence=None,
        now_ms=NOW_MS,
    )


def _evaluation_result(
    *,
    signal_input: StrategyFamilySignalInput,
    status: RuntimeStrategySignalEvaluationStatus,
) -> RuntimeStrategySignalEvaluationResult:
    return RuntimeStrategySignalEvaluationResult(
        evaluation_id=signal_input.evaluation_id,
        strategy_family_id=signal_input.strategy_family_id,
        strategy_family_version_id=signal_input.strategy_family_version_id,
        symbol=signal_input.symbol,
        status=status,
        output=None,
        blockers=[],
        warnings=[],
        semantics_binding_found=True,
        strategy_candidate_mode="shadow_order_candidate_allowed",
        runtime_confirmation_mode="owner_confirm_each_attempt_initially",
        evaluator_id="UnitEvaluator",
        evaluator_called=True,
        can_call_semantic_binding=(
            status == RuntimeStrategySignalEvaluationStatus.READY_FOR_SEMANTIC_BINDING
        ),
    )


def _candidate(signal_input: StrategyFamilySignalInput) -> OrderCandidate:
    return OrderCandidate(
        order_candidate_id=f"order-candidate-{signal_input.evaluation_id}",
        signal_evaluation_id=signal_input.evaluation_id,
        runtime_instance_id="runtime-1",
        trial_binding_id="binding-1",
        strategy_family_id=signal_input.strategy_family_id,
        strategy_family_version_id=signal_input.strategy_family_version_id,
        symbol=signal_input.symbol,
        side=SignalSide.LONG.value,
        created_at_ms=NOW_MS,
        updated_at_ms=NOW_MS,
        metadata={"unit_shadow_candidate": True},
    )


class _Planner:
    def __init__(
        self,
        *,
        planning_status: RuntimeStrategySignalCandidatePlanningStatus,
    ) -> None:
        self.planning_status = planning_status
        self.calls = 0
        self.last_metadata = None

    async def plan_shadow_candidate_from_signal_input(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        runtime,
        context_id=None,
        expires_at_ms=None,
        metadata=None,
    ) -> RuntimeStrategySignalCandidatePlanningResult:
        self.calls += 1
        self.last_metadata = metadata
        candidate = (
            _candidate(signal_input)
            if self.planning_status
            == RuntimeStrategySignalCandidatePlanningStatus.SHADOW_CANDIDATE_CREATED
            else None
        )
        evaluation_status = (
            RuntimeStrategySignalEvaluationStatus.READY_FOR_SEMANTIC_BINDING
            if candidate is not None
            else RuntimeStrategySignalEvaluationStatus.OBSERVE_ONLY
        )
        return RuntimeStrategySignalCandidatePlanningResult(
            planning_id=f"planning-{signal_input.evaluation_id}",
            runtime_instance_id=runtime.runtime_instance_id,
            strategy_family_id=signal_input.strategy_family_id,
            strategy_family_version_id=signal_input.strategy_family_version_id,
            symbol=signal_input.symbol,
            status=self.planning_status,
            evaluation_result=_evaluation_result(
                signal_input=signal_input,
                status=evaluation_status,
            ),
            candidate=candidate,
            blockers=(
                ["strategy_signal_not_would_enter"]
                if self.planning_status
                != RuntimeStrategySignalCandidatePlanningStatus.SHADOW_CANDIDATE_CREATED
                else []
            ),
            warnings=[],
            signal_evaluation_created=candidate is not None,
            order_candidate_created=candidate is not None,
        )


async def test_next_attempt_strategy_planning_calls_shadow_planner_only_after_ready_gate():
    signal_input = _signal_input()
    planner = _Planner(
        planning_status=(
            RuntimeStrategySignalCandidatePlanningStatus.SHADOW_CANDIDATE_CREATED
        ),
    )
    service = RuntimeNextAttemptStrategyPlanningService(
        strategy_signal_planner=planner,
    )

    artifact = await service.plan_from_post_submit_gate(
        post_submit_finalize_payload=_ready_post_submit_payload(),
        signal_input=signal_input,
        runtime=_runtime(boundary={"budget_reserved": Decimal("0")}),
        context_id="context-1",
    )

    assert artifact.status == (
        RuntimeNextAttemptStrategyPlanningStatus.READY_FOR_FINAL_GATE_PREFLIGHT
    )
    assert planner.calls == 1
    assert artifact.order_candidate_id == "order-candidate-eval-fresh"
    assert artifact.strategy_planning_plan["creates_shadow_candidate"] is True
    assert artifact.strategy_planning_plan["creates_executable_execution_intent"] is False
    assert artifact.strategy_planning_plan["requires_official_final_gate"] is True
    assert planner.last_metadata["source_post_submit_finalize_payload_id"] == (
        artifact.source_post_submit_finalize_payload_id
    )
    assert "source_post_submit_finalize_packet_id" not in planner.last_metadata
    assert planner.last_metadata["consumed_authorization_replay_only"] is True
    assert planner.last_metadata["requires_fresh_authorization_before_submit"] is True
    payload = artifact.model_dump(mode="json")
    assert "source_post_submit_finalize_payload_id" in payload
    assert "post_submit_finalize_packet_id" not in payload
    assert artifact.exchange_called is False
    assert artifact.order_lifecycle_called is False
    assert artifact.exchange_order_submitted is False


async def test_next_attempt_strategy_planning_does_not_call_planner_when_gate_blocked():
    signal_input = _signal_input()
    planner = _Planner(
        planning_status=(
            RuntimeStrategySignalCandidatePlanningStatus.SHADOW_CANDIDATE_CREATED
        ),
    )
    service = RuntimeNextAttemptStrategyPlanningService(
        strategy_signal_planner=planner,
    )

    artifact = await service.plan_from_post_submit_gate(
        post_submit_finalize_payload=_blocked_post_submit_payload(),
        signal_input=signal_input,
        runtime=_runtime(),
    )

    assert artifact.status == (
        RuntimeNextAttemptStrategyPlanningStatus.BLOCKED_BY_POST_SUBMIT_GATE
    )
    assert planner.calls == 0
    assert "post_submit_finalize_not_ready_for_next_attempt" in artifact.blockers
    assert "runtime_active_position_slot_in_use" in artifact.blockers
    assert artifact.strategy_planning_plan["creates_shadow_candidate"] is False
    assert artifact.exchange_order_submitted is False


async def test_next_attempt_strategy_planning_waits_when_fresh_signal_is_observe_only():
    signal_input = _signal_input(evaluation_id="eval-observe")
    planner = _Planner(
        planning_status=RuntimeStrategySignalCandidatePlanningStatus.OBSERVE_ONLY,
    )
    service = RuntimeNextAttemptStrategyPlanningService(
        strategy_signal_planner=planner,
    )

    artifact = await service.plan_from_post_submit_gate(
        post_submit_finalize_payload=_ready_post_submit_payload(),
        signal_input=signal_input,
        runtime=_runtime(boundary={"budget_reserved": Decimal("0")}),
    )

    assert artifact.status == RuntimeNextAttemptStrategyPlanningStatus.WAITING_FOR_SIGNAL
    assert planner.calls == 1
    assert artifact.order_candidate_id is None
    assert artifact.strategy_planning_plan["next_step"] == (
        "observe_only_or_wait_for_next_closed_bar"
    )
    assert artifact.strategy_planning_plan["creates_shadow_candidate"] is False
    assert artifact.execution_intent_created is False


async def test_next_attempt_strategy_planning_blocks_runtime_mismatch_before_planner():
    signal_input = _signal_input()
    planner = _Planner(
        planning_status=(
            RuntimeStrategySignalCandidatePlanningStatus.SHADOW_CANDIDATE_CREATED
        ),
    )
    service = RuntimeNextAttemptStrategyPlanningService(
        strategy_signal_planner=planner,
    )

    artifact = await service.plan_from_post_submit_gate(
        post_submit_finalize_payload=_ready_post_submit_payload(),
        signal_input=signal_input,
        runtime=_runtime(runtime_instance_id="runtime-other"),
    )

    assert artifact.status == (
        RuntimeNextAttemptStrategyPlanningStatus.BLOCKED_BY_POST_SUBMIT_GATE
    )
    assert planner.calls == 0
    assert "post_submit_runtime_mismatch" in artifact.blockers


async def test_next_attempt_strategy_planning_calls_shadow_planner_after_release_ready():
    signal_input = _signal_input()
    planner = _Planner(
        planning_status=(
            RuntimeStrategySignalCandidatePlanningStatus.SHADOW_CANDIDATE_CREATED
        ),
    )
    service = RuntimeNextAttemptStrategyPlanningService(
        strategy_signal_planner=planner,
    )
    release_evidence = _ready_release_evidence()

    assert release_evidence.status == RuntimeNextAttemptReleaseStatus.READY_FOR_STRATEGY_SIGNAL

    packet = await service.plan_from_release_gate(
        next_attempt_release_evidence=release_evidence,
        signal_input=signal_input,
        runtime=_runtime(boundary={"budget_reserved": Decimal("0")}),
        context_id="release-context-1",
    )

    assert packet.status == (
        RuntimeNextAttemptStrategyPlanningStatus.READY_FOR_FINAL_GATE_PREFLIGHT
    )
    assert planner.calls == 1
    assert (
        packet.source_release_evidence_id
        == release_evidence.release_evidence_id
    )
    payload = packet.model_dump(mode="json")
    assert (
        payload["source_release_evidence_id"]
        == release_evidence.release_evidence_id
    )
    assert "source_release_packet_id" not in payload
    assert packet.order_candidate_id == "order-candidate-eval-fresh"
    assert packet.strategy_planning_plan["creates_shadow_candidate"] is True
    assert packet.strategy_planning_plan["creates_executable_execution_intent"] is False
    assert packet.strategy_planning_plan["live_submit_allowed"] is False
    assert packet.strategy_planning_plan["requires_official_final_gate"] is True
    assert planner.last_metadata["source_next_attempt_release_evidence_id"] == (
        release_evidence.release_evidence_id
    )
    assert "source_next_attempt_release_packet_id" not in planner.last_metadata
    assert planner.last_metadata["release_ready_for_strategy_signal"] is True
    assert planner.last_metadata["requires_fresh_authorization_before_submit"] is True
    assert packet.exchange_order_submitted is False
    assert packet.order_lifecycle_called is False


async def test_next_attempt_strategy_planning_does_not_call_planner_when_release_blocks():
    signal_input = _signal_input()
    planner = _Planner(
        planning_status=(
            RuntimeStrategySignalCandidatePlanningStatus.SHADOW_CANDIDATE_CREATED
        ),
    )
    service = RuntimeNextAttemptStrategyPlanningService(
        strategy_signal_planner=planner,
    )
    release_evidence = _blocked_release_evidence()

    packet = await service.plan_from_release_gate(
        next_attempt_release_evidence=release_evidence,
        signal_input=signal_input,
        runtime=_runtime(),
    )

    assert packet.status == (
        RuntimeNextAttemptStrategyPlanningStatus.BLOCKED_BY_RELEASE_GATE
    )
    assert planner.calls == 0
    assert "next_attempt_release_not_ready_for_strategy_signal" in packet.blockers
    assert "strategy_signal_observation_not_allowed_by_release" in packet.blockers
    assert "shadow_candidate_planning_not_allowed_by_release" in packet.blockers
    assert packet.strategy_planning_plan["creates_shadow_candidate"] is False
    assert packet.exchange_order_submitted is False


async def test_trading_console_next_attempt_strategy_plan_endpoint_uses_injected_service(
    monkeypatch,
):
    from src.interfaces import api as api_module
    from src.interfaces.api_trading_console import (
        RuntimeNextAttemptStrategyPlanningRequest,
        runtime_next_attempt_strategy_plan_from_post_submit_payload,
    )

    runtime = _runtime(boundary={"budget_reserved": Decimal("0")})
    signal_input = _signal_input()
    post_submit_payload = _ready_post_submit_payload()
    planner = _Planner(
        planning_status=(
            RuntimeStrategySignalCandidatePlanningStatus.SHADOW_CANDIDATE_CREATED
        ),
    )
    service = RuntimeNextAttemptStrategyPlanningService(
        strategy_signal_planner=planner,
    )

    class _RuntimeService:
        async def get_runtime(self, runtime_instance_id):
            assert runtime_instance_id == runtime.runtime_instance_id
            return runtime

    monkeypatch.setattr(
        api_module,
        "_strategy_runtime_service",
        _RuntimeService(),
        raising=False,
    )
    monkeypatch.setattr(
        api_module,
        "_runtime_next_attempt_strategy_planning_service",
        service,
        raising=False,
    )

    response = await runtime_next_attempt_strategy_plan_from_post_submit_payload(
        runtime.runtime_instance_id,
        RuntimeNextAttemptStrategyPlanningRequest(
            post_submit_finalize_payload=post_submit_payload,
            signal_input=signal_input,
            metadata={"unit_endpoint": True},
        ),
    )

    assert response.status == (
        RuntimeNextAttemptStrategyPlanningStatus.READY_FOR_FINAL_GATE_PREFLIGHT
    )
    assert planner.calls == 1
    assert response.order_candidate_id == "order-candidate-eval-fresh"
    assert response.metadata["unit_endpoint"] is True
    assert response.exchange_order_submitted is False


def test_trading_console_next_attempt_strategy_plan_rejects_legacy_packet_field():
    from src.interfaces.api_trading_console import (
        RuntimeNextAttemptStrategyPlanningRequest,
    )

    with pytest.raises(ValidationError):
        RuntimeNextAttemptStrategyPlanningRequest(
            post_submit_finalize_packet=_ready_post_submit_payload(),
            signal_input=_signal_input(),
        )
