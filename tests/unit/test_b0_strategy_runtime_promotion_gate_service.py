from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.application.strategy_runtime_promotion_gate_service import (
    StrategyRuntimePromotionGateService,
    StrategyRuntimePromotionGateServiceError,
)
from src.domain.strategy_runtime_promotion_gate import (
    FirstRealSubmitConfirmationFacts,
    RuntimeExecutionConfirmationFacts,
    StrategyRuntimePromotionGateStatus,
    StrategyRuntimePromotionScope,
    StrategySemanticsConfirmationFacts,
)
from src.domain.strategy_runtime import (
    StrategyRuntimeBoundary,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)
from src.domain.strategy_runtime_live_enablement import (
    StrategyRuntimeLiveEnablementPreviewStatus,
)
from src.domain.runtime_execution_exchange_submit_execution_result import (
    RuntimeExecutionExchangeSubmitExecutionStatus,
)


NOW_MS = 1781000000000


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


def _runtime() -> StrategyRuntimeInstance:
    return StrategyRuntimeInstance(
        runtime_instance_id="runtime-cpm-promotion-gate",
        trial_binding_id="trial-cpm-promotion-gate",
        admission_decision_id="admission-cpm-promotion-gate",
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        symbol="ETH/USDT:USDT",
        side="long",
        status=StrategyRuntimeInstanceStatus.ACTIVE,
        boundary=StrategyRuntimeBoundary(
            max_attempts=3,
            attempts_used=0,
            budget_reserved=Decimal("0"),
            max_active_positions=1,
            max_notional_per_attempt=Decimal("10"),
            total_budget=Decimal("9"),
            allowed_symbols=["ETH/USDT:USDT"],
            allowed_sides=["long"],
            max_leverage=Decimal("1"),
            requires_protection=True,
        ),
        execution_enabled=False,
        shadow_mode=True,
        created_at_ms=NOW_MS,
        updated_at_ms=NOW_MS,
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
    assert result.runtime_confirmation_mode == "runtime_bounded_auto_attempts"
    assert result.not_execution_authority is True
    assert result.execution_intent_created is False
    assert result.order_created is False
    assert result.exchange_called is False


async def test_trading_console_live_enablement_preview_defaults_to_blocked(
    monkeypatch,
):
    from src.interfaces import api as api_module
    from src.interfaces import api_trading_console

    class _RuntimeService:
        async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
            assert runtime_instance_id == "runtime-cpm-promotion-gate"
            return _runtime()

    monkeypatch.setattr(
        api_module,
        "_strategy_runtime_promotion_gate_service",
        StrategyRuntimePromotionGateService(),
        raising=False,
    )
    monkeypatch.setattr(api_module, "_strategy_runtime_service", _RuntimeService(), raising=False)

    result = await api_trading_console.runtime_strategy_live_enablement_preview(
        runtime_instance_id="runtime-cpm-promotion-gate",
    )

    assert result.status == StrategyRuntimeLiveEnablementPreviewStatus.BLOCKED
    assert "current_head_not_deployed_to_tokyo" in result.blockers
    assert "owner_live_runtime_enablement_authorization_missing" in result.blockers
    assert "owner_real_submit_authorization_missing" in result.blockers
    assert result.not_execution_authority is True
    assert result.runtime_state_mutated is False
    assert result.execution_intent_created is False
    assert result.order_created is False
    assert result.exchange_called is False
    assert result.order_lifecycle_called is False


async def test_trading_console_live_enablement_preview_can_be_ready(
    monkeypatch,
):
    from src.interfaces import api as api_module
    from src.interfaces import api_trading_console

    base_runtime = _runtime()
    ready_runtime = base_runtime.model_copy(
        update={
            "boundary": base_runtime.boundary.model_copy(
                update={
                    "max_margin_per_attempt": Decimal("10"),
                    "min_liquidation_stop_buffer": Decimal("25"),
                }
            )
        }
    )

    class _RuntimeService:
        async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
            assert runtime_instance_id == "runtime-cpm-promotion-gate"
            return ready_runtime

    monkeypatch.setattr(
        api_module,
        "_strategy_runtime_promotion_gate_service",
        StrategyRuntimePromotionGateService(),
        raising=False,
    )
    monkeypatch.setattr(api_module, "_strategy_runtime_service", _RuntimeService(), raising=False)

    result = await api_trading_console.runtime_strategy_live_enablement_preview(
        runtime_instance_id="runtime-cpm-promotion-gate",
        strategy_family_confirmed=True,
        implementation_source_confirmed=True,
        required_facts_confirmed=True,
        entry_policy_confirmed=True,
        exit_policy_confirmed=True,
        protection_policy_confirmed=True,
        eligible_for_runtime_execution_confirmed=True,
        right_tail_review_metrics_confirmed=True,
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
        budget_release_or_consume_rule_confirmed=True,
        post_submit_budget_settlement_persistence_evidence_id=(
            "runtime-post-submit-budget-settlement-persistence-084"
        ),
        attempt_outcome_policy_id="runtime-attempt-outcome-policy-test",
        protection_creation_failure_policy_confirmed=True,
        protection_creation_failure_policy_id="runtime-protection-failure-policy-test",
        duplicate_submit_policy_confirmed=True,
        submit_idempotency_policy_id="runtime-submit-idempotency-policy-test",
        trusted_submit_fact_snapshot_id="trusted-submit-facts-snapshot-test",
        local_registration_enablement_decision_id="runtime-local-registration-enable-test",
        exchange_submit_enablement_decision_id="runtime-exchange-submit-enable-test",
        runtime_submit_rehearsal_id="runtime-submit-rehearsal-test",
        deployment_readiness_evidence_id="runtime-exchange-gateway-readiness-test",
        owner_real_submit_authorization_id="owner-real-submit-authorization-test",
        deployment_readiness_confirmed=True,
        explicit_owner_real_submit_authorization=True,
        current_head_deployed=True,
        owner_live_runtime_enablement_authorized=True,
        owner_real_submit_authorization_present=True,
        submit_technical_rehearsal_passed=True,
        submit_adapter_implemented=True,
    )

    assert (
        result.status
        == StrategyRuntimeLiveEnablementPreviewStatus.READY_FOR_LIVE_RUNTIME_ENABLEMENT_MUTATION_DESIGN
    )
    assert result.blockers == []
    assert result.not_execution_authority is True
    assert result.runtime_state_mutated is False
    assert result.execution_intent_created is False
    assert result.order_created is False
    assert result.exchange_called is False
    assert result.owner_bounded_execution_called is False


async def test_trading_console_live_enablement_accepts_execution_result_proof(
    monkeypatch,
):
    from src.interfaces import api as api_module
    from src.interfaces import api_trading_console

    base_runtime = _runtime()
    ready_runtime = base_runtime.model_copy(
        update={
            "boundary": base_runtime.boundary.model_copy(
                update={
                    "max_margin_per_attempt": Decimal("10"),
                    "min_liquidation_stop_buffer": Decimal("25"),
                }
            )
        }
    )

    class _RuntimeService:
        async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
            assert runtime_instance_id == "runtime-cpm-promotion-gate"
            return ready_runtime

    class _ExecutionResultRepo:
        async def get(self, execution_result_id: str):
            assert execution_result_id == "runtime-exchange-submit-execution-result-test"
            return SimpleNamespace(
                runtime_instance_id="runtime-cpm-promotion-gate",
                status=(
                    RuntimeExecutionExchangeSubmitExecutionStatus
                    .EXCHANGE_SUBMIT_ORDERS_SUBMITTED
                ),
                blockers=[],
                exchange_submit_execution_enabled=True,
                real_exchange_submit_adapter_executed=True,
                exchange_called=True,
                exchange_order_submitted=True,
                order_lifecycle_submit_called=True,
                execution_intent_status_changed=False,
                owner_bounded_execution_called=False,
                withdrawal_or_transfer_created=False,
                entry_exchange_order_id="entry-ex-1",
                protection_exchange_order_ids=["sl-ex-1"],
            )

    monkeypatch.setattr(
        api_module,
        "_strategy_runtime_promotion_gate_service",
        StrategyRuntimePromotionGateService(),
        raising=False,
    )
    monkeypatch.setattr(api_module, "_strategy_runtime_service", _RuntimeService(), raising=False)
    monkeypatch.setattr(
        api_module,
        "_runtime_exchange_submit_execution_result_repository",
        _ExecutionResultRepo(),
        raising=False,
    )

    result = await api_trading_console.runtime_strategy_live_enablement_preview(
        runtime_instance_id="runtime-cpm-promotion-gate",
        strategy_family_confirmed=True,
        implementation_source_confirmed=True,
        required_facts_confirmed=True,
        entry_policy_confirmed=True,
        exit_policy_confirmed=True,
        protection_policy_confirmed=True,
        eligible_for_runtime_execution_confirmed=True,
        right_tail_review_metrics_confirmed=True,
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
        budget_release_or_consume_rule_confirmed=True,
        post_submit_budget_settlement_persistence_evidence_id=(
            "runtime-post-submit-budget-settlement-persistence-084"
        ),
        attempt_outcome_policy_id="runtime-attempt-outcome-policy-test",
        protection_creation_failure_policy_confirmed=True,
        protection_creation_failure_policy_id="runtime-protection-failure-policy-test",
        duplicate_submit_policy_confirmed=True,
        submit_idempotency_policy_id="runtime-submit-idempotency-policy-test",
        trusted_submit_fact_snapshot_id="trusted-submit-facts-snapshot-test",
        local_registration_enablement_decision_id="runtime-local-registration-enable-test",
        exchange_submit_enablement_decision_id="runtime-exchange-submit-enable-test",
        exchange_submit_execution_result_id=(
            "runtime-exchange-submit-execution-result-test"
        ),
        deployment_readiness_evidence_id="runtime-exchange-gateway-readiness-test",
        owner_real_submit_authorization_id="owner-real-submit-authorization-test",
        deployment_readiness_confirmed=True,
        explicit_owner_real_submit_authorization=True,
        current_head_deployed=True,
        owner_live_runtime_enablement_authorized=True,
        owner_real_submit_authorization_present=True,
        submit_adapter_implemented=True,
    )

    assert (
        result.status
        == StrategyRuntimeLiveEnablementPreviewStatus.READY_FOR_LIVE_RUNTIME_ENABLEMENT_MUTATION_DESIGN
    )
    assert result.submit_technical_rehearsal_passed is True
    assert result.blockers == []
    assert "exchange_submit_execution_result_used_as_submit_proof" in (
        result.warnings
    )
    assert result.runtime_state_mutated is False
    assert result.exchange_called is False
    assert result.order_lifecycle_called is False


def test_promotion_gate_service_keeps_brf_blocked_without_short_profile():
    result = StrategyRuntimePromotionGateService().preview(
        strategy_family_id="BRF-001",
        strategy_family_version_id="BRF-001-v0",
        semantic_confirmations=_semantic_confirmed(),
        runtime_confirmations=_runtime_confirmed(short_profile=False),
    )

    assert result.status == StrategyRuntimePromotionGateStatus.BLOCKED
    assert result.runtime_confirmation_mode == "runtime_bounded_auto_attempts"
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


async def test_trading_console_promotion_gate_preview_defaults_to_blocked(monkeypatch):
    from src.interfaces import api as api_module
    from src.interfaces import api_trading_console

    monkeypatch.setattr(
        api_module,
        "_strategy_runtime_promotion_gate_service",
        StrategyRuntimePromotionGateService(),
        raising=False,
    )

    result = await api_trading_console.runtime_strategy_promotion_gate_preview(
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
    )

    assert result.status == StrategyRuntimePromotionGateStatus.BLOCKED
    assert "semantic_strategy_family_confirmed_missing" in result.blockers
    assert result.not_execution_authority is True
    assert result.execution_intent_created is False
    assert result.order_created is False
    assert result.exchange_called is False


async def test_trading_console_promotion_gate_preview_returns_ready_when_confirmed(monkeypatch):
    from src.interfaces import api as api_module
    from src.interfaces import api_trading_console

    monkeypatch.setattr(
        api_module,
        "_strategy_runtime_promotion_gate_service",
        StrategyRuntimePromotionGateService(),
        raising=False,
    )

    result = await api_trading_console.runtime_strategy_promotion_gate_preview(
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        strategy_family_confirmed=True,
        implementation_source_confirmed=True,
        required_facts_confirmed=True,
        entry_policy_confirmed=True,
        exit_policy_confirmed=True,
        protection_policy_confirmed=True,
        eligible_for_runtime_execution_confirmed=True,
        right_tail_review_metrics_confirmed=True,
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

    assert (
        result.status
        == StrategyRuntimePromotionGateStatus.READY_FOR_CONTROLLED_RUNTIME_EXECUTION_DESIGN
    )
    assert result.blockers == []
    assert result.runtime_confirmation_mode == "runtime_bounded_auto_attempts"
    assert result.not_execution_authority is True


async def test_trading_console_promotion_gate_preview_unknown_binding_is_404(monkeypatch):
    from fastapi import HTTPException

    from src.interfaces import api as api_module
    from src.interfaces import api_trading_console

    monkeypatch.setattr(
        api_module,
        "_strategy_runtime_promotion_gate_service",
        StrategyRuntimePromotionGateService(),
        raising=False,
    )

    with pytest.raises(HTTPException) as exc_info:
        await api_trading_console.runtime_strategy_promotion_gate_preview(
            strategy_family_id="UNKNOWN",
            strategy_family_version_id="UNKNOWN-v0",
        )

    assert exc_info.value.status_code == 404


async def test_trading_console_promotion_gate_preview_for_runtime_uses_runtime_binding(
    monkeypatch,
):
    from src.interfaces import api as api_module
    from src.interfaces import api_trading_console

    class _RuntimeService:
        async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
            assert runtime_instance_id == "runtime-cpm-promotion-gate"
            return _runtime()

    monkeypatch.setattr(
        api_module,
        "_strategy_runtime_promotion_gate_service",
        StrategyRuntimePromotionGateService(),
        raising=False,
    )
    monkeypatch.setattr(api_module, "_strategy_runtime_service", _RuntimeService(), raising=False)

    result = await api_trading_console.runtime_strategy_promotion_gate_preview_for_runtime(
        runtime_instance_id="runtime-cpm-promotion-gate",
        strategy_family_confirmed=True,
        implementation_source_confirmed=True,
        required_facts_confirmed=True,
        entry_policy_confirmed=True,
        exit_policy_confirmed=True,
        protection_policy_confirmed=True,
        eligible_for_runtime_execution_confirmed=True,
        right_tail_review_metrics_confirmed=True,
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

    assert (
        result.status
        == StrategyRuntimePromotionGateStatus.READY_FOR_CONTROLLED_RUNTIME_EXECUTION_DESIGN
    )
    assert result.blockers == []
    assert result.not_execution_authority is True


async def test_trading_console_promotion_gate_preview_for_runtime_unknown_runtime_is_404(
    monkeypatch,
):
    from fastapi import HTTPException

    from src.interfaces import api as api_module
    from src.interfaces import api_trading_console

    class _RuntimeService:
        async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
            raise ValueError(f"runtime not found: {runtime_instance_id}")

    monkeypatch.setattr(api_module, "_strategy_runtime_service", _RuntimeService(), raising=False)

    with pytest.raises(HTTPException) as exc_info:
        await api_trading_console.runtime_strategy_promotion_gate_preview_for_runtime(
            runtime_instance_id="missing-runtime",
        )

    assert exc_info.value.status_code == 404


async def test_trading_console_first_real_submit_scope_blocks_missing_submit_confirmations(
    monkeypatch,
):
    from src.interfaces import api as api_module
    from src.interfaces import api_trading_console

    class _RuntimeService:
        async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
            assert runtime_instance_id == "runtime-cpm-promotion-gate"
            return _runtime()

    monkeypatch.setattr(
        api_module,
        "_strategy_runtime_promotion_gate_service",
        StrategyRuntimePromotionGateService(),
        raising=False,
    )
    monkeypatch.setattr(api_module, "_strategy_runtime_service", _RuntimeService(), raising=False)

    result = await api_trading_console.runtime_strategy_promotion_gate_preview_for_runtime(
        runtime_instance_id="runtime-cpm-promotion-gate",
        scope=StrategyRuntimePromotionScope.FIRST_REAL_SUBMIT_GATE_REVIEW,
        strategy_family_confirmed=True,
        implementation_source_confirmed=True,
        required_facts_confirmed=True,
        entry_policy_confirmed=True,
        exit_policy_confirmed=True,
        protection_policy_confirmed=True,
        eligible_for_runtime_execution_confirmed=True,
        right_tail_review_metrics_confirmed=True,
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

    assert result.status == StrategyRuntimePromotionGateStatus.BLOCKED
    assert "first_real_submit_duplicate_submit_policy_confirmed_missing" in (
        result.blockers
    )
    assert "first_real_submit_explicit_owner_real_submit_authorization_missing" in (
        result.blockers
    )
    assert result.not_execution_authority is True
    assert result.execution_intent_created is False
    assert result.order_created is False
    assert result.exchange_called is False


async def test_trading_console_first_real_submit_scope_can_reach_gate_review_only(
    monkeypatch,
):
    from src.interfaces import api as api_module
    from src.interfaces import api_trading_console

    class _RuntimeService:
        async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
            assert runtime_instance_id == "runtime-cpm-promotion-gate"
            return _runtime()

    monkeypatch.setattr(
        api_module,
        "_strategy_runtime_promotion_gate_service",
        StrategyRuntimePromotionGateService(),
        raising=False,
    )
    monkeypatch.setattr(api_module, "_strategy_runtime_service", _RuntimeService(), raising=False)

    result = await api_trading_console.runtime_strategy_promotion_gate_preview_for_runtime(
        runtime_instance_id="runtime-cpm-promotion-gate",
        scope=StrategyRuntimePromotionScope.FIRST_REAL_SUBMIT_GATE_REVIEW,
        strategy_family_confirmed=True,
        implementation_source_confirmed=True,
        required_facts_confirmed=True,
        entry_policy_confirmed=True,
        exit_policy_confirmed=True,
        protection_policy_confirmed=True,
        eligible_for_runtime_execution_confirmed=True,
        right_tail_review_metrics_confirmed=True,
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
        budget_release_or_consume_rule_confirmed=True,
        post_submit_budget_settlement_persistence_evidence_id=(
            "runtime-post-submit-budget-settlement-persistence-084"
        ),
        attempt_outcome_policy_id="runtime-attempt-outcome-policy-test",
        trusted_submit_fact_snapshot_id="trusted-submit-facts-snapshot-test",
        submit_idempotency_policy_id="runtime-submit-idempotency-policy-test",
        protection_creation_failure_policy_confirmed=True,
        protection_creation_failure_policy_id="runtime-protection-failure-policy-test",
        local_registration_enablement_decision_id="runtime-local-registration-enable-test",
        exchange_submit_enablement_decision_id="runtime-exchange-submit-enable-test",
        runtime_submit_rehearsal_id="runtime-submit-rehearsal-test",
        deployment_readiness_evidence_id="runtime-exchange-gateway-readiness-test",
        owner_real_submit_authorization_id="owner-real-submit-authorization-test",
        duplicate_submit_policy_confirmed=True,
        deployment_readiness_confirmed=True,
        explicit_owner_real_submit_authorization=True,
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


def test_first_real_submit_scope_accepts_durable_execution_result_proof():
    result = StrategyRuntimePromotionGateService().preview(
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        scope=StrategyRuntimePromotionScope.FIRST_REAL_SUBMIT_GATE_REVIEW,
        semantic_confirmations=_semantic_confirmed(),
        runtime_confirmations=_runtime_confirmed(),
        first_real_submit_confirmations=FirstRealSubmitConfirmationFacts(
            budget_release_or_consume_rule_confirmed=True,
            post_submit_budget_settlement_persistence_confirmed=True,
            post_submit_budget_settlement_persistence_evidence_id=(
                "runtime-post-submit-budget-settlement-persistence-084"
            ),
            attempt_outcome_policy_id="runtime-attempt-outcome-policy-test",
            trusted_submit_fact_snapshot_id="trusted-submit-facts-snapshot-test",
            submit_idempotency_policy_id="runtime-submit-idempotency-policy-test",
            protection_creation_failure_policy_confirmed=True,
            protection_creation_failure_policy_id=(
                "runtime-protection-failure-policy-test"
            ),
            local_registration_enablement_decision_id=(
                "runtime-local-registration-enable-test"
            ),
            exchange_submit_enablement_decision_id=(
                "runtime-exchange-submit-enable-test"
            ),
            exchange_submit_execution_result_id=(
                "runtime-exchange-submit-execution-result-test"
            ),
            deployment_readiness_evidence_id=(
                "runtime-exchange-gateway-readiness-test"
            ),
            owner_real_submit_authorization_id=(
                "owner-real-submit-authorization-test"
            ),
            duplicate_submit_policy_confirmed=True,
            deployment_readiness_confirmed=True,
            explicit_owner_real_submit_authorization=True,
        ),
    )

    assert (
        result.status
        == StrategyRuntimePromotionGateStatus.READY_FOR_FIRST_REAL_SUBMIT_GATE_REVIEW
    )
    assert "first_real_submit_runtime_submit_rehearsal_id_missing" not in (
        result.blockers
    )
    assert result.exchange_called is False
