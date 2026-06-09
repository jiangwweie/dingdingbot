"""Runtime safety readiness facts for promotion-gate review.

This module is pure, non-executing domain logic. It inspects a
StrategyRuntimeInstance boundary and reports whether required safety facts are
present before Owner/Codex confirmation. It does not confirm the facts by
itself and does not create candidates, intents, orders, runtime mutations, or
exchange calls.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.domain.strategy_runtime import (
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)


class StrategyRuntimeSafetyReadinessModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeSafetyReadinessStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_OWNER_CODEX_CONFIRMATION = "ready_for_owner_codex_confirmation"


class RuntimeSafetyRequirementStatus(str, Enum):
    PASS = "pass"
    BLOCK = "block"
    WARN = "warn"


class RuntimeSafetyRequirement(StrategyRuntimeSafetyReadinessModel):
    code: str = Field(min_length=1, max_length=128)
    status: RuntimeSafetyRequirementStatus
    confirmation_key: str | None = Field(default=None, max_length=128)
    message: str = Field(default="", max_length=1024)
    facts: dict[str, Any] = Field(default_factory=dict)


class StrategyRuntimeSafetyReadiness(StrategyRuntimeSafetyReadinessModel):
    runtime_instance_id: str
    strategy_family_id: str
    strategy_family_version_id: str
    symbol: str
    side: str
    status: RuntimeSafetyReadinessStatus
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    missing_boundary_facts: list[str] = Field(default_factory=list)
    required_owner_confirmations: list[str] = Field(default_factory=list)
    requirements: list[RuntimeSafetyRequirement] = Field(default_factory=list)
    not_execution_authority: Literal[True] = True
    execution_intent_created: Literal[False] = False
    runtime_state_mutated: Literal[False] = False
    order_created: Literal[False] = False
    exchange_called: Literal[False] = False


def evaluate_strategy_runtime_safety_readiness(
    runtime: StrategyRuntimeInstance,
) -> StrategyRuntimeSafetyReadiness:
    requirements: list[RuntimeSafetyRequirement] = []

    def add(
        code: str,
        status: RuntimeSafetyRequirementStatus,
        *,
        confirmation_key: str | None = None,
        message: str = "",
        facts: dict[str, Any] | None = None,
    ) -> None:
        requirements.append(
            RuntimeSafetyRequirement(
                code=code,
                status=status,
                confirmation_key=confirmation_key,
                message=message,
                facts=facts or {},
            )
        )

    boundary = runtime.boundary
    add(
        "runtime_status_active",
        RuntimeSafetyRequirementStatus.PASS
        if runtime.status == StrategyRuntimeInstanceStatus.ACTIVE
        else RuntimeSafetyRequirementStatus.BLOCK,
        message="Runtime must be active before promotion review.",
        facts={"status": runtime.status.value},
    )
    add(
        "runtime_remains_non_executing_preview",
        RuntimeSafetyRequirementStatus.PASS
        if runtime.shadow_mode and not runtime.execution_enabled
        else RuntimeSafetyRequirementStatus.BLOCK,
        message="Current promotion review is non-executing and must not enable runtime execution.",
        facts={
            "shadow_mode": runtime.shadow_mode,
            "execution_enabled": runtime.execution_enabled,
        },
    )
    add(
        "symbol_side_boundary_present",
        RuntimeSafetyRequirementStatus.PASS
        if boundary.allowed_symbols and boundary.allowed_sides
        else RuntimeSafetyRequirementStatus.BLOCK,
        confirmation_key="symbol_side_boundary_confirmed",
        message="Allowed symbol and side boundaries must be explicit.",
        facts={
            "symbol": runtime.symbol,
            "side": runtime.side,
            "allowed_symbols": list(boundary.allowed_symbols),
            "allowed_sides": list(boundary.allowed_sides),
        },
    )
    add(
        "attempt_limit_available",
        RuntimeSafetyRequirementStatus.PASS
        if boundary.max_attempts > 0 and boundary.attempts_remaining > 0
        else RuntimeSafetyRequirementStatus.BLOCK,
        confirmation_key="attempt_consumption_rule_confirmed",
        message="Runtime must have a bounded attempt limit with remaining attempts.",
        facts={
            "max_attempts": boundary.max_attempts,
            "attempts_used": boundary.attempts_used,
            "attempts_remaining": boundary.attempts_remaining,
        },
    )
    add(
        "max_loss_budget_present",
        RuntimeSafetyRequirementStatus.PASS
        if _positive(boundary.total_budget)
        else RuntimeSafetyRequirementStatus.BLOCK,
        confirmation_key="max_loss_budget_confirmed",
        message="Total loss budget must be explicit and positive.",
        facts={
            "total_budget": boundary.total_budget,
            "budget_reserved": boundary.budget_reserved,
            "budget_remaining": boundary.budget_remaining,
        },
    )
    add(
        "budget_reservation_basis_required",
        RuntimeSafetyRequirementStatus.PASS
        if _positive(boundary.total_budget)
        else RuntimeSafetyRequirementStatus.BLOCK,
        confirmation_key="budget_reservation_rule_confirmed",
        message="Budget reservation must be confirmed against max-loss-first semantics.",
        facts={"budget_basis": "max_loss_first_required"},
    )
    add(
        "max_notional_boundary_present",
        RuntimeSafetyRequirementStatus.PASS
        if _positive(boundary.max_notional_per_attempt)
        else RuntimeSafetyRequirementStatus.BLOCK,
        confirmation_key="max_notional_boundary_confirmed",
        message="Per-attempt notional boundary must be explicit and positive.",
        facts={"max_notional_per_attempt": boundary.max_notional_per_attempt},
    )
    add(
        "max_active_positions_boundary_present",
        RuntimeSafetyRequirementStatus.PASS
        if boundary.max_active_positions > 0
        else RuntimeSafetyRequirementStatus.BLOCK,
        confirmation_key="max_active_positions_boundary_confirmed",
        message="Runtime must explicitly allow a bounded positive active-position count.",
        facts={"max_active_positions": boundary.max_active_positions},
    )
    add(
        "max_leverage_boundary_present",
        RuntimeSafetyRequirementStatus.PASS
        if _positive(boundary.max_leverage)
        else RuntimeSafetyRequirementStatus.BLOCK,
        confirmation_key="max_leverage_boundary_confirmed",
        message="Max leverage boundary must be explicit and positive.",
        facts={"max_leverage": boundary.max_leverage},
    )
    add(
        "margin_usage_boundary_present",
        RuntimeSafetyRequirementStatus.PASS
        if _positive(boundary.max_margin_per_attempt)
        else RuntimeSafetyRequirementStatus.BLOCK,
        confirmation_key="margin_usage_boundary_confirmed",
        message="Max margin per attempt must be explicit; leverage cannot expand loss budget.",
        facts={"max_margin_per_attempt": boundary.max_margin_per_attempt},
    )
    add(
        "liquidation_buffer_boundary_present",
        RuntimeSafetyRequirementStatus.PASS
        if _positive(boundary.min_liquidation_stop_buffer)
        else RuntimeSafetyRequirementStatus.BLOCK,
        confirmation_key="liquidation_buffer_boundary_confirmed",
        message="Liquidation-vs-stop buffer must be explicit before leverage promotion.",
        facts={"min_liquidation_stop_buffer": boundary.min_liquidation_stop_buffer},
    )
    add(
        "protection_required",
        RuntimeSafetyRequirementStatus.PASS
        if boundary.requires_protection
        else RuntimeSafetyRequirementStatus.BLOCK,
        confirmation_key="protection_readiness_source_confirmed",
        message="Hard protection must be required before any controlled execution path.",
        facts={"requires_protection": boundary.requires_protection},
    )
    add(
        "review_required",
        RuntimeSafetyRequirementStatus.PASS
        if boundary.requires_review
        else RuntimeSafetyRequirementStatus.WARN,
        message="Owner/Codex review should remain required for first controlled execution.",
        facts={"requires_review": boundary.requires_review},
    )
    add(
        "trusted_fact_sources_required",
        RuntimeSafetyRequirementStatus.WARN,
        confirmation_key="trusted_active_position_source_confirmed",
        message="Trusted active-position facts must be confirmed outside the runtime boundary.",
        facts={"required_source": "local_projection_or_reconciliation"},
    )
    add(
        "trusted_account_facts_required",
        RuntimeSafetyRequirementStatus.WARN,
        confirmation_key="trusted_account_fact_source_confirmed",
        message="Trusted account freshness must be confirmed outside the runtime boundary.",
        facts={"required_source": "account_fact_readmodel_or_exchange_read_only"},
    )
    add(
        "stale_fact_behavior_required",
        RuntimeSafetyRequirementStatus.WARN,
        confirmation_key="stale_fact_behavior_confirmed",
        message="Unavailable or stale account/position/protection facts must block execution.",
        facts={"missing_or_stale_behavior": "block"},
    )

    blockers = sorted(
        requirement.code
        for requirement in requirements
        if requirement.status == RuntimeSafetyRequirementStatus.BLOCK
    )
    warnings = sorted(
        requirement.code
        for requirement in requirements
        if requirement.status == RuntimeSafetyRequirementStatus.WARN
    )
    missing_boundary_facts = sorted(
        requirement.code
        for requirement in requirements
        if requirement.status == RuntimeSafetyRequirementStatus.BLOCK
        and requirement.confirmation_key is not None
    )
    required_owner_confirmations = sorted(
        {
            requirement.confirmation_key
            for requirement in requirements
            if requirement.confirmation_key is not None
        }
    )
    status = (
        RuntimeSafetyReadinessStatus.BLOCKED
        if blockers
        else RuntimeSafetyReadinessStatus.READY_FOR_OWNER_CODEX_CONFIRMATION
    )
    return StrategyRuntimeSafetyReadiness(
        runtime_instance_id=runtime.runtime_instance_id,
        strategy_family_id=runtime.strategy_family_id,
        strategy_family_version_id=runtime.strategy_family_version_id,
        symbol=runtime.symbol,
        side=runtime.side,
        status=status,
        blockers=blockers,
        warnings=warnings,
        missing_boundary_facts=missing_boundary_facts,
        required_owner_confirmations=required_owner_confirmations,
        requirements=requirements,
    )


def _positive(value: Decimal | None) -> bool:
    return value is not None and value > Decimal("0")
