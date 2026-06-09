from __future__ import annotations

import pytest

from src.application.strategy_runtime_promotion_gate_service import (
    StrategyRuntimePromotionGateService,
    StrategyRuntimePromotionGateServiceError,
)
from src.domain.strategy_runtime_promotion_gate import (
    RuntimeExecutionConfirmationFacts,
    StrategyRuntimePromotionGateStatus,
    StrategySemanticsConfirmationFacts,
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
        attempt_consumption_rule_confirmed=True,
        budget_reservation_rule_confirmed=True,
        trusted_active_position_source_confirmed=True,
        trusted_account_fact_source_confirmed=True,
        short_side_conservative_profile_confirmed=short_profile,
    )


def test_promotion_gate_service_previews_cpm_by_strategy_version():
    result = StrategyRuntimePromotionGateService().preview(
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        semantic_confirmations=_semantic_confirmed(),
        runtime_confirmations=_runtime_confirmed(),
    )

    assert (
        result.status
        == StrategyRuntimePromotionGateStatus.READY_FOR_CONTROLLED_RUNTIME_EXECUTION_DESIGN
    )
    assert result.not_execution_authority is True
    assert result.execution_intent_created is False
    assert result.order_created is False
    assert result.exchange_called is False


def test_promotion_gate_service_keeps_brf_blocked_without_short_profile():
    result = StrategyRuntimePromotionGateService().preview(
        strategy_family_id="BRF-001",
        strategy_family_version_id="BRF-001-v0",
        semantic_confirmations=_semantic_confirmed(),
        runtime_confirmations=_runtime_confirmed(short_profile=False),
    )

    assert result.status == StrategyRuntimePromotionGateStatus.BLOCKED
    assert "runtime_short_side_conservative_profile_confirmed_missing" in (
        result.blockers
    )


def test_promotion_gate_service_does_not_guess_unknown_strategy_binding():
    with pytest.raises(
        StrategyRuntimePromotionGateServiceError,
        match="strategy semantics binding not found",
    ):
        StrategyRuntimePromotionGateService().preview(
            strategy_family_id="UNKNOWN",
            strategy_family_version_id="UNKNOWN-v0",
        )
