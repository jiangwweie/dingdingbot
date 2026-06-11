from __future__ import annotations

from decimal import Decimal

from src.domain.strategy_runtime import (
    StrategyRuntimeBoundary,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)
from src.domain.strategy_runtime_live_enablement import (
    StrategyRuntimeLiveEnablementMutationStatus,
    StrategyRuntimeLiveEnablementPreviewStatus,
    build_strategy_runtime_live_enablement_mutation,
    build_strategy_runtime_live_enablement_preview,
)
from src.domain.strategy_runtime_promotion_gate import (
    FirstRealSubmitConfirmationFacts,
    RuntimeExecutionConfirmationFacts,
    StrategyRuntimePromotionGateInput,
    StrategyRuntimePromotionGateStatus,
    StrategyRuntimePromotionScope,
    StrategySemanticsConfirmationFacts,
    evaluate_strategy_runtime_promotion_gate,
)
from src.domain.strategy_runtime_safety_readiness import (
    evaluate_strategy_runtime_safety_readiness,
)
from src.domain.strategy_semantics import initial_strategy_semantics_catalog


NOW_MS = 1781079000000


def _runtime(*, complete_boundary: bool = True) -> StrategyRuntimeInstance:
    return StrategyRuntimeInstance(
        runtime_instance_id="runtime-live-enablement-cpm",
        trial_binding_id="trial-live-enablement-cpm",
        admission_decision_id="admission-live-enablement-cpm",
        strategy_family_id="CPM-001",
        strategy_family_version_id="CPM-001-v0",
        symbol="BNB/USDT:USDT",
        side="long",
        status=StrategyRuntimeInstanceStatus.ACTIVE,
        boundary=StrategyRuntimeBoundary(
            max_attempts=3,
            attempts_used=0,
            budget_reserved=Decimal("0"),
            max_active_positions=1 if complete_boundary else 0,
            max_notional_per_attempt=Decimal("10") if complete_boundary else None,
            total_budget=Decimal("3") if complete_boundary else None,
            allowed_symbols=["BNB/USDT:USDT"] if complete_boundary else [],
            allowed_sides=["long"] if complete_boundary else [],
            max_leverage=Decimal("1") if complete_boundary else None,
            max_margin_per_attempt=Decimal("10") if complete_boundary else None,
            min_liquidation_stop_buffer=Decimal("25") if complete_boundary else None,
            requires_protection=complete_boundary,
            requires_review=True,
        ),
        created_at_ms=NOW_MS,
        updated_at_ms=NOW_MS,
    )


def _promotion_result(
    runtime: StrategyRuntimeInstance,
    *,
    confirmed: bool = True,
) -> object:
    binding = initial_strategy_semantics_catalog().get_binding(
        strategy_family_id=runtime.strategy_family_id,
        strategy_family_version_id=runtime.strategy_family_version_id,
    )
    return evaluate_strategy_runtime_promotion_gate(
        StrategyRuntimePromotionGateInput(
            binding=binding,
            scope=StrategyRuntimePromotionScope.FIRST_REAL_SUBMIT_GATE_REVIEW,
            semantic_confirmations=(
                StrategySemanticsConfirmationFacts(
                    strategy_family_confirmed=True,
                    implementation_source_confirmed=True,
                    required_facts_confirmed=True,
                    entry_policy_confirmed=True,
                    exit_policy_confirmed=True,
                    protection_policy_confirmed=True,
                    eligible_for_runtime_execution_confirmed=True,
                    right_tail_review_metrics_confirmed=True,
                )
                if confirmed
                else StrategySemanticsConfirmationFacts()
            ),
            runtime_confirmations=(
                RuntimeExecutionConfirmationFacts(
                    runtime_profile_confirmed=True,
                    owner_confirmation_mode_confirmed=True,
                    symbol_side_boundary_confirmed=True,
                    max_loss_budget_confirmed=True,
                    max_notional_boundary_confirmed=True,
                    max_active_positions_boundary_confirmed=True,
                    max_leverage_boundary_confirmed=True,
                    margin_usage_boundary_confirmed=True,
                    liquidation_buffer_boundary_confirmed=True,
                    protection_readiness_source_confirmed=True,
                    stale_fact_behavior_confirmed=True,
                    attempt_consumption_rule_confirmed=True,
                    budget_reservation_rule_confirmed=True,
                    trusted_active_position_source_confirmed=True,
                    trusted_account_fact_source_confirmed=True,
                )
                if confirmed
                else RuntimeExecutionConfirmationFacts()
            ),
            first_real_submit_confirmations=(
                FirstRealSubmitConfirmationFacts(
                    budget_release_or_consume_rule_confirmed=True,
                    protection_creation_failure_policy_confirmed=True,
                    attempt_outcome_policy_id="runtime-attempt-outcome-policy-test",
                    trusted_submit_fact_snapshot_id=(
                        "trusted-submit-facts-snapshot-test"
                    ),
                    submit_idempotency_policy_id=(
                        "runtime-submit-idempotency-policy-test"
                    ),
                    protection_creation_failure_policy_id=(
                        "runtime-protection-failure-policy-test"
                    ),
                    local_registration_enablement_decision_id=(
                        "runtime-local-registration-enable-test"
                    ),
                    exchange_submit_enablement_decision_id=(
                        "runtime-exchange-submit-enable-test"
                    ),
                    runtime_submit_rehearsal_id="runtime-submit-rehearsal-test",
                    deployment_readiness_evidence_id=(
                        "runtime-exchange-gateway-readiness-test"
                    ),
                    owner_real_submit_authorization_id=(
                        "owner-real-submit-authorization-test"
                    ),
                    duplicate_submit_policy_confirmed=True,
                    deployment_readiness_confirmed=True,
                    explicit_owner_real_submit_authorization=True,
                )
                if confirmed
                else FirstRealSubmitConfirmationFacts()
            ),
        )
    )


def test_live_enablement_preview_can_be_ready_without_runtime_mutation():
    runtime = _runtime()
    preview = build_strategy_runtime_live_enablement_preview(
        runtime=runtime,
        safety_readiness=evaluate_strategy_runtime_safety_readiness(runtime),
        promotion_gate_result=_promotion_result(runtime),
        current_head_deployed=True,
        owner_live_runtime_enablement_authorized=True,
        owner_real_submit_authorization_present=True,
        submit_technical_rehearsal_passed=True,
        submit_adapter_implemented=True,
        forbidden_execution_flags=[],
    )

    assert (
        preview.status
        == StrategyRuntimeLiveEnablementPreviewStatus.READY_FOR_LIVE_RUNTIME_ENABLEMENT_MUTATION_DESIGN
    )
    assert preview.blockers == []
    assert (
        preview.promotion_gate_status
        == StrategyRuntimePromotionGateStatus.READY_FOR_FIRST_REAL_SUBMIT_GATE_REVIEW
    )
    assert preview.current_runtime_shadow_mode is True
    assert preview.current_runtime_execution_enabled is False
    assert preview.not_execution_authority is True
    assert preview.runtime_state_mutated is False
    assert preview.execution_intent_created is False
    assert preview.order_created is False
    assert preview.exchange_called is False
    assert preview.owner_bounded_execution_called is False
    assert preview.order_lifecycle_called is False


def test_live_enablement_mutation_applies_only_after_ready_preview():
    runtime = _runtime()
    preview = build_strategy_runtime_live_enablement_preview(
        runtime=runtime,
        safety_readiness=evaluate_strategy_runtime_safety_readiness(runtime),
        promotion_gate_result=_promotion_result(runtime),
        current_head_deployed=True,
        owner_live_runtime_enablement_authorized=True,
        owner_real_submit_authorization_present=True,
        submit_technical_rehearsal_passed=True,
        submit_adapter_implemented=True,
        forbidden_execution_flags=[],
    )

    mutation = build_strategy_runtime_live_enablement_mutation(
        runtime=runtime,
        preview=preview,
        mutation_id="live-enable-mutation-1",
        owner_live_runtime_enablement_authorization_id="owner-live-runtime-auth-1",
        owner_real_submit_authorization_id="owner-real-submit-auth-1",
        now_ms=NOW_MS + 1,
    )

    assert mutation.status == StrategyRuntimeLiveEnablementMutationStatus.APPLIED
    assert mutation.blockers == []
    assert mutation.runtime_state_mutated is True
    assert mutation.updated_runtime_snapshot is not None
    assert mutation.updated_runtime_snapshot.execution_enabled is True
    assert mutation.updated_runtime_snapshot.shadow_mode is False
    assert mutation.updated_runtime_snapshot.metadata[
        "owner_live_runtime_enablement_authorization_id"
    ] == "owner-live-runtime-auth-1"
    assert mutation.not_order_authority is True
    assert mutation.execution_intent_created is False
    assert mutation.order_created is False
    assert mutation.exchange_called is False
    assert mutation.owner_bounded_execution_called is False
    assert mutation.order_lifecycle_called is False


def test_live_enablement_mutation_blocks_when_preview_not_ready():
    runtime = _runtime()
    preview = build_strategy_runtime_live_enablement_preview(
        runtime=runtime,
        safety_readiness=evaluate_strategy_runtime_safety_readiness(runtime),
        promotion_gate_result=_promotion_result(runtime),
        current_head_deployed=False,
        owner_live_runtime_enablement_authorized=False,
        owner_real_submit_authorization_present=False,
        submit_technical_rehearsal_passed=True,
        submit_adapter_implemented=False,
        forbidden_execution_flags=[],
    )

    mutation = build_strategy_runtime_live_enablement_mutation(
        runtime=runtime,
        preview=preview,
        mutation_id="live-enable-mutation-blocked",
        owner_live_runtime_enablement_authorization_id="",
        owner_real_submit_authorization_id="",
        now_ms=NOW_MS + 1,
    )

    assert mutation.status == StrategyRuntimeLiveEnablementMutationStatus.BLOCKED
    assert mutation.updated_runtime_snapshot is None
    assert mutation.runtime_state_mutated is False
    assert "live_enablement_preview_not_ready" in mutation.blockers
    assert "owner_live_runtime_enablement_authorization_id_missing" in (
        mutation.blockers
    )
    assert "owner_real_submit_authorization_id_missing" in mutation.blockers
    assert mutation.order_created is False
    assert mutation.exchange_called is False


def test_live_enablement_preview_blocks_missing_operational_owner_and_adapter_gates():
    runtime = _runtime()
    preview = build_strategy_runtime_live_enablement_preview(
        runtime=runtime,
        safety_readiness=evaluate_strategy_runtime_safety_readiness(runtime),
        promotion_gate_result=_promotion_result(runtime, confirmed=False),
        current_head_deployed=False,
        owner_live_runtime_enablement_authorized=False,
        owner_real_submit_authorization_present=False,
        submit_technical_rehearsal_passed=True,
        submit_adapter_implemented=False,
        forbidden_execution_flags=[],
    )

    assert preview.status == StrategyRuntimeLiveEnablementPreviewStatus.BLOCKED
    assert "current_head_not_deployed_to_tokyo" in preview.blockers
    assert "owner_live_runtime_enablement_authorization_missing" in preview.blockers
    assert "owner_real_submit_authorization_missing" in preview.blockers
    assert "controlled_submit_adapter_not_implemented" in preview.blockers
    assert "promotion_gate_not_ready_for_first_real_submit" in preview.blockers
    assert "promotion_gate_semantic_strategy_family_confirmed_missing" in (
        preview.blockers
    )
    assert preview.runtime_state_mutated is False
    assert preview.exchange_called is False


def test_live_enablement_preview_blocks_missing_runtime_safety_facts():
    runtime = _runtime(complete_boundary=False)
    preview = build_strategy_runtime_live_enablement_preview(
        runtime=runtime,
        safety_readiness=evaluate_strategy_runtime_safety_readiness(runtime),
        promotion_gate_result=_promotion_result(runtime),
        current_head_deployed=True,
        owner_live_runtime_enablement_authorized=True,
        owner_real_submit_authorization_present=True,
        submit_technical_rehearsal_passed=True,
        submit_adapter_implemented=True,
        forbidden_execution_flags=[],
    )

    assert preview.status == StrategyRuntimeLiveEnablementPreviewStatus.BLOCKED
    assert "runtime_safety_readiness_not_ready" in preview.blockers
    assert "runtime_safety_max_loss_budget_present" in preview.blockers
    assert "runtime_safety_protection_required" in preview.blockers
    assert preview.not_execution_authority is True
