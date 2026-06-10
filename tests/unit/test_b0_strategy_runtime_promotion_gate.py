from __future__ import annotations

import pytest

from src.domain.strategy_runtime_promotion_gate import (
    FirstRealSubmitConfirmationFacts,
    RuntimeExecutionConfirmationFacts,
    StrategyRuntimePromotionGateConfirmationRecord,
    StrategyRuntimePromotionGateInput,
    StrategyRuntimePromotionGateStatus,
    StrategyRuntimePromotionScope,
    StrategySemanticsConfirmationFacts,
    evaluate_strategy_runtime_promotion_gate,
)
from src.domain.strategy_semantics import initial_strategy_semantics_catalog


def _catalog_binding(family_id: str, version_id: str):
    return initial_strategy_semantics_catalog().get_binding(
        strategy_family_id=family_id,
        strategy_family_version_id=version_id,
    )


def _semantic_confirmed() -> StrategySemanticsConfirmationFacts:
    return StrategySemanticsConfirmationFacts(
        strategy_family_confirmed=True,
        implementation_source_confirmed=True,
        required_facts_confirmed=True,
        entry_policy_confirmed=True,
        exit_policy_confirmed=True,
        protection_policy_confirmed=True,
        eligible_for_runtime_execution_confirmed=True,
        right_tail_review_metrics_confirmed=True,
    )


def _runtime_confirmed(
    *,
    short_profile: bool = False,
) -> RuntimeExecutionConfirmationFacts:
    return RuntimeExecutionConfirmationFacts(
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
        short_side_conservative_profile_confirmed=short_profile,
    )


def _first_real_submit_confirmed() -> FirstRealSubmitConfirmationFacts:
    return FirstRealSubmitConfirmationFacts(
        budget_release_or_consume_rule_confirmed=True,
        protection_creation_failure_policy_confirmed=True,
        duplicate_submit_policy_confirmed=True,
        deployment_readiness_confirmed=True,
        explicit_owner_real_submit_authorization=True,
    )


def test_cpm_blocks_until_owner_semantic_and_runtime_confirmations_exist():
    result = evaluate_strategy_runtime_promotion_gate(
        StrategyRuntimePromotionGateInput(
            binding=_catalog_binding("CPM-RO-001", "CPM-RO-001-v0"),
        )
    )

    assert result.status == StrategyRuntimePromotionGateStatus.BLOCKED
    assert "semantic_strategy_family_confirmed_missing" in result.blockers
    assert "runtime_symbol_side_boundary_confirmed_missing" in result.blockers
    assert "runtime_max_loss_budget_confirmed_missing" in result.blockers
    assert "runtime_max_active_positions_boundary_confirmed_missing" in (
        result.blockers
    )
    assert "runtime_liquidation_buffer_boundary_confirmed_missing" in result.blockers
    assert "runtime_protection_readiness_source_confirmed_missing" in result.blockers
    assert "runtime_stale_fact_behavior_confirmed_missing" in result.blockers
    assert "runtime_trusted_active_position_source_confirmed_missing" in result.blockers
    assert result.runtime_confirmation_mode == "runtime_bounded_auto_attempts"
    assert result.not_execution_authority is True
    assert result.execution_intent_created is False
    assert result.order_created is False
    assert result.exchange_called is False


def test_cpm_can_be_ready_for_controlled_runtime_design_without_proven_alpha():
    result = evaluate_strategy_runtime_promotion_gate(
        StrategyRuntimePromotionGateInput(
            binding=_catalog_binding("CPM-RO-001", "CPM-RO-001-v0"),
            semantic_confirmations=_semantic_confirmed(),
            runtime_confirmations=_runtime_confirmed(),
        )
    )

    assert (
        result.status
        == StrategyRuntimePromotionGateStatus.READY_FOR_CONTROLLED_RUNTIME_EXECUTION_DESIGN
    )
    assert result.blockers == []
    assert result.runtime_confirmation_mode == "runtime_bounded_auto_attempts"
    assert "strategy_not_proven_alpha_limits_economic_and_autonomy_admission" in (
        result.warnings
    )
    assert result.not_execution_authority is True


def test_brf_requires_short_side_conservative_profile_confirmation():
    result = evaluate_strategy_runtime_promotion_gate(
        StrategyRuntimePromotionGateInput(
            binding=_catalog_binding("BRF-001", "BRF-001-v0"),
            semantic_confirmations=_semantic_confirmed(),
            runtime_confirmations=_runtime_confirmed(short_profile=False),
        )
    )

    assert result.status == StrategyRuntimePromotionGateStatus.BLOCKED
    assert result.runtime_confirmation_mode == "runtime_bounded_auto_attempts"
    assert "runtime_short_side_conservative_profile_confirmed_missing" in (
        result.blockers
    )


def test_brf_can_reach_runtime_design_after_short_profile_confirmation_without_per_entry_owner_mode():
    result = evaluate_strategy_runtime_promotion_gate(
        StrategyRuntimePromotionGateInput(
            binding=_catalog_binding("BRF-001", "BRF-001-v0"),
            semantic_confirmations=_semantic_confirmed(),
            runtime_confirmations=_runtime_confirmed(short_profile=True),
        )
    )

    assert (
        result.status
        == StrategyRuntimePromotionGateStatus.READY_FOR_CONTROLLED_RUNTIME_EXECUTION_DESIGN
    )
    assert result.blockers == []
    assert result.runtime_confirmation_mode == "runtime_bounded_auto_attempts"


def test_rmr_regime_classifier_cannot_promote_as_runtime_trade_strategy():
    result = evaluate_strategy_runtime_promotion_gate(
        StrategyRuntimePromotionGateInput(
            binding=_catalog_binding("RMR-001", "RMR-001-v0"),
            semantic_confirmations=_semantic_confirmed(),
            runtime_confirmations=_runtime_confirmed(),
        )
    )

    assert result.status == StrategyRuntimePromotionGateStatus.BLOCKED
    assert "strategy_binding_not_trade_candidate" in result.blockers
    assert "regime_classifier_not_runtime_trade_strategy" in result.blockers
    assert result.runtime_confirmation_mode == "observe_only"


def test_first_real_submit_scope_requires_extra_submit_confirmations():
    result = evaluate_strategy_runtime_promotion_gate(
        StrategyRuntimePromotionGateInput(
            binding=_catalog_binding("CPM-RO-001", "CPM-RO-001-v0"),
            scope=StrategyRuntimePromotionScope.FIRST_REAL_SUBMIT_GATE_REVIEW,
            semantic_confirmations=_semantic_confirmed(),
            runtime_confirmations=_runtime_confirmed(),
        )
    )

    assert result.status == StrategyRuntimePromotionGateStatus.BLOCKED
    assert "first_real_submit_duplicate_submit_policy_confirmed_missing" in (
        result.blockers
    )
    assert "first_real_submit_explicit_owner_real_submit_authorization_missing" in (
        result.blockers
    )


def test_first_real_submit_scope_can_reach_gate_review_but_not_execution_authority():
    result = evaluate_strategy_runtime_promotion_gate(
        StrategyRuntimePromotionGateInput(
            binding=_catalog_binding("CPM-RO-001", "CPM-RO-001-v0"),
            scope=StrategyRuntimePromotionScope.FIRST_REAL_SUBMIT_GATE_REVIEW,
            semantic_confirmations=_semantic_confirmed(),
            runtime_confirmations=_runtime_confirmed(),
            first_real_submit_confirmations=_first_real_submit_confirmed(),
        )
    )

    assert (
        result.status
        == StrategyRuntimePromotionGateStatus.READY_FOR_FIRST_REAL_SUBMIT_GATE_REVIEW
    )
    assert result.blockers == []
    assert result.not_execution_authority is True
    assert result.execution_intent_created is False
    assert result.order_created is False
    assert result.exchange_called is False


def test_promotion_confirmation_record_replays_gate_facts_without_execution_authority():
    confirmation = StrategyRuntimePromotionGateConfirmationRecord(
        confirmation_id="promotion-confirmation-cpm-1",
        runtime_instance_id="runtime-cpm-1",
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        semantic_confirmations=_semantic_confirmed(),
        runtime_confirmations=_runtime_confirmed(),
        reason="Owner accepts bounded 30U experimental capital semantics.",
        created_at_ms=1781000000000,
        metadata={"risk_capital_objective": "bounded_loss_right_tail_capture"},
    )

    result = evaluate_strategy_runtime_promotion_gate(
        confirmation.to_gate_input(_catalog_binding("CPM-RO-001", "CPM-RO-001-v0"))
    )

    assert (
        result.status
        == StrategyRuntimePromotionGateStatus.READY_FOR_CONTROLLED_RUNTIME_EXECUTION_DESIGN
    )
    assert confirmation.records_promotion_gate_confirmation is True
    assert confirmation.not_execution_authority is True
    assert confirmation.execution_intent_created is False
    assert confirmation.order_created is False
    assert confirmation.exchange_called is False
    assert confirmation.owner_bounded_execution_called is False
    assert confirmation.order_lifecycle_called is False
    assert confirmation.runtime_mutation_created is False
    assert confirmation.withdrawal_instruction_created is False
    assert confirmation.transfer_instruction_created is False


def test_promotion_confirmation_record_rejects_execution_metadata():
    with pytest.raises(ValueError, match="forbidden execution field"):
        StrategyRuntimePromotionGateConfirmationRecord(
            confirmation_id="promotion-confirmation-forbidden-1",
            strategy_family_id="CPM-RO-001",
            strategy_family_version_id="CPM-RO-001-v0",
            semantic_confirmations=_semantic_confirmed(),
            runtime_confirmations=_runtime_confirmed(),
            reason="Should reject exchange payload metadata.",
            created_at_ms=1781000000000,
            metadata={"nested": {"exchange_order_id": "should-not-exist"}},
        )
