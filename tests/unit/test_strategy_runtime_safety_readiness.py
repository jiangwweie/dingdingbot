from __future__ import annotations

from decimal import Decimal

import pytest

from src.application.strategy_runtime_safety_readiness_service import (
    StrategyRuntimeSafetyReadinessService,
)
from src.domain.strategy_runtime import (
    StrategyRuntimeBoundary,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)
from src.domain.strategy_runtime_safety_readiness import (
    RuntimeSafetyReadinessStatus,
    evaluate_strategy_runtime_safety_readiness,
)


NOW_MS = 1781000000000


def _runtime(*, complete_boundary: bool = True) -> StrategyRuntimeInstance:
    return StrategyRuntimeInstance(
        runtime_instance_id="runtime-safety-readiness",
        trial_binding_id="trial-safety-readiness",
        admission_decision_id="admission-safety-readiness",
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        symbol="ETH/USDT:USDT",
        side="long",
        status=StrategyRuntimeInstanceStatus.ACTIVE,
        boundary=StrategyRuntimeBoundary(
            max_attempts=3,
            attempts_used=0,
            budget_reserved=Decimal("0"),
            max_active_positions=1 if complete_boundary else 0,
            max_notional_per_attempt=Decimal("10") if complete_boundary else None,
            total_budget=Decimal("3") if complete_boundary else None,
            allowed_symbols=["ETH/USDT:USDT"] if complete_boundary else [],
            allowed_sides=["long"] if complete_boundary else [],
            max_leverage=Decimal("1") if complete_boundary else None,
            max_margin_per_attempt=Decimal("10") if complete_boundary else None,
            min_liquidation_stop_buffer=Decimal("25") if complete_boundary else None,
            requires_protection=complete_boundary,
            requires_review=True,
        ),
        execution_enabled=False,
        shadow_mode=True,
        created_at_ms=NOW_MS,
        updated_at_ms=NOW_MS,
    )


def test_safety_readiness_blocks_missing_runtime_boundary_facts():
    result = evaluate_strategy_runtime_safety_readiness(
        _runtime(complete_boundary=False)
    )

    assert result.status == RuntimeSafetyReadinessStatus.BLOCKED
    assert "symbol_side_boundary_present" in result.blockers
    assert "max_loss_budget_present" in result.blockers
    assert "max_notional_boundary_present" in result.blockers
    assert "max_active_positions_boundary_present" in result.blockers
    assert "max_leverage_boundary_present" in result.blockers
    assert "margin_usage_boundary_present" in result.blockers
    assert "liquidation_buffer_boundary_present" in result.blockers
    assert "protection_required" in result.blockers
    assert "max_loss_budget_confirmed" in result.required_owner_confirmations
    assert "max_active_positions_boundary_confirmed" in (
        result.required_owner_confirmations
    )
    assert result.not_execution_authority is True
    assert result.execution_intent_created is False
    assert result.runtime_state_mutated is False
    assert result.order_created is False
    assert result.exchange_called is False


def test_safety_readiness_does_not_let_notional_or_leverage_compensate_missing_loss_budget():
    complete = _runtime()
    runtime = complete.model_copy(
        update={
            "boundary": complete.boundary.model_copy(
                update={
                    "total_budget": None,
                    "max_margin_per_attempt": None,
                    "min_liquidation_stop_buffer": None,
                }
            )
        }
    )

    result = evaluate_strategy_runtime_safety_readiness(runtime)

    assert result.status == RuntimeSafetyReadinessStatus.BLOCKED
    assert "max_notional_boundary_present" not in result.blockers
    assert "max_leverage_boundary_present" not in result.blockers
    assert "max_loss_budget_present" in result.blockers
    assert "budget_reservation_basis_required" in result.blockers
    assert "margin_usage_boundary_present" in result.blockers
    assert "liquidation_buffer_boundary_present" in result.blockers
    assert "max_loss_budget_present" in result.missing_boundary_facts
    assert "margin_usage_boundary_present" in result.missing_boundary_facts
    assert "liquidation_buffer_boundary_present" in result.missing_boundary_facts
    assert result.not_execution_authority is True
    assert result.execution_intent_created is False
    assert result.runtime_state_mutated is False
    assert result.order_created is False
    assert result.exchange_called is False


def test_safety_readiness_allows_owner_codex_confirmation_when_boundary_complete():
    result = evaluate_strategy_runtime_safety_readiness(_runtime())

    assert result.status == RuntimeSafetyReadinessStatus.READY_FOR_OWNER_CODEX_CONFIRMATION
    assert result.blockers == []
    assert "trusted_fact_sources_required" in result.warnings
    assert "trusted_account_facts_required" in result.warnings
    assert "stale_fact_behavior_required" in result.warnings
    assert set(result.required_owner_confirmations) == {
        "attempt_consumption_rule_confirmed",
        "budget_reservation_rule_confirmed",
        "liquidation_buffer_boundary_confirmed",
        "margin_usage_boundary_confirmed",
        "max_active_positions_boundary_confirmed",
        "max_leverage_boundary_confirmed",
        "max_loss_budget_confirmed",
        "max_notional_boundary_confirmed",
        "protection_readiness_source_confirmed",
        "stale_fact_behavior_confirmed",
        "symbol_side_boundary_confirmed",
        "trusted_account_fact_source_confirmed",
        "trusted_active_position_source_confirmed",
    }
    assert result.not_execution_authority is True
    assert result.execution_intent_created is False
    assert result.runtime_state_mutated is False
    assert result.order_created is False
    assert result.exchange_called is False


async def test_safety_readiness_service_reads_runtime_without_mutation():
    class _RuntimeService:
        async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
            assert runtime_instance_id == "runtime-safety-readiness"
            return _runtime()

    result = await StrategyRuntimeSafetyReadinessService(
        runtime_service=_RuntimeService()
    ).preview(runtime_instance_id="runtime-safety-readiness")

    assert result.status == RuntimeSafetyReadinessStatus.READY_FOR_OWNER_CODEX_CONFIRMATION
    assert result.runtime_state_mutated is False


async def test_trading_console_runtime_safety_readiness_preview(monkeypatch):
    from src.interfaces import api as api_module
    from src.interfaces import api_trading_console

    class _RuntimeService:
        async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
            assert runtime_instance_id == "runtime-safety-readiness"
            return _runtime()

    monkeypatch.setattr(api_module, "_strategy_runtime_service", _RuntimeService(), raising=False)

    result = await api_trading_console.runtime_strategy_safety_readiness_preview(
        runtime_instance_id="runtime-safety-readiness",
    )

    assert result.status == RuntimeSafetyReadinessStatus.READY_FOR_OWNER_CODEX_CONFIRMATION
    assert "max_loss_budget_confirmed" in result.required_owner_confirmations
    assert result.not_execution_authority is True


async def test_trading_console_runtime_safety_readiness_unknown_runtime_is_404(
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
        await api_trading_console.runtime_strategy_safety_readiness_preview(
            runtime_instance_id="missing-runtime",
        )

    assert exc_info.value.status_code == 404
