"""Non-executing live-runtime enablement preview gate.

This module answers one narrow question: what still blocks a shadow
StrategyRuntimeInstance from being promoted toward a live-runtime enablement
mutation? It does not perform that mutation and does not create intents,
orders, exchange calls, transfers, or withdrawals.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.domain.strategy_runtime import (
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)
from src.domain.strategy_runtime_promotion_gate import (
    StrategyRuntimePromotionGateResult,
    StrategyRuntimePromotionGateStatus,
)
from src.domain.strategy_runtime_safety_readiness import (
    RuntimeSafetyReadinessStatus,
    StrategyRuntimeSafetyReadiness,
)


class StrategyRuntimeLiveEnablementModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StrategyRuntimeLiveEnablementPreviewStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_LIVE_RUNTIME_ENABLEMENT_MUTATION_DESIGN = (
        "ready_for_live_runtime_enablement_mutation_design"
    )


class StrategyRuntimeLiveEnablementMutationStatus(str, Enum):
    BLOCKED = "blocked"
    APPLIED = "applied"


class StrategyRuntimeLiveEnablementPreview(StrategyRuntimeLiveEnablementModel):
    runtime_instance_id: str
    strategy_family_id: str
    strategy_family_version_id: str
    symbol: str
    side: str
    status: StrategyRuntimeLiveEnablementPreviewStatus
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    safety_readiness_status: RuntimeSafetyReadinessStatus
    promotion_gate_status: StrategyRuntimePromotionGateStatus
    current_runtime_status: StrategyRuntimeInstanceStatus
    current_runtime_shadow_mode: bool
    current_runtime_execution_enabled: bool
    current_head_deployed: bool
    owner_live_runtime_enablement_authorized: bool
    owner_real_submit_authorization_present: bool
    submit_technical_rehearsal_passed: bool
    submit_adapter_implemented: bool
    forbidden_execution_flags: list[str] = Field(default_factory=list)
    not_execution_authority: Literal[True] = True
    runtime_state_mutated: Literal[False] = False
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    exchange_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    withdrawal_instruction_created: Literal[False] = False
    transfer_instruction_created: Literal[False] = False


class StrategyRuntimeLiveEnablementMutation(StrategyRuntimeLiveEnablementModel):
    mutation_id: str = Field(min_length=1, max_length=180)
    runtime_instance_id: str
    strategy_family_id: str
    strategy_family_version_id: str
    symbol: str
    side: str
    status: StrategyRuntimeLiveEnablementMutationStatus
    blockers: list[str] = Field(default_factory=list)
    previous_runtime_snapshot: StrategyRuntimeInstance
    updated_runtime_snapshot: StrategyRuntimeInstance | None = None
    preview_snapshot: StrategyRuntimeLiveEnablementPreview
    owner_live_runtime_enablement_authorization_id: str | None = Field(
        default=None,
        max_length=180,
    )
    owner_real_submit_authorization_id: str | None = Field(
        default=None,
        max_length=180,
    )
    created_at_ms: int = Field(ge=0)
    runtime_state_mutated: bool = False
    not_order_authority: Literal[True] = True
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    exchange_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    withdrawal_instruction_created: Literal[False] = False
    transfer_instruction_created: Literal[False] = False


def build_strategy_runtime_live_enablement_preview(
    *,
    runtime: StrategyRuntimeInstance,
    safety_readiness: StrategyRuntimeSafetyReadiness,
    promotion_gate_result: StrategyRuntimePromotionGateResult,
    current_head_deployed: bool,
    owner_live_runtime_enablement_authorized: bool,
    owner_real_submit_authorization_present: bool,
    submit_technical_rehearsal_passed: bool,
    submit_adapter_implemented: bool,
    forbidden_execution_flags: list[str] | None = None,
) -> StrategyRuntimeLiveEnablementPreview:
    blockers: list[str] = []
    warnings: list[str] = []
    forbidden_flags = list(forbidden_execution_flags or [])

    if runtime.status != StrategyRuntimeInstanceStatus.ACTIVE:
        blockers.append("runtime_not_active")
    if not runtime.shadow_mode or runtime.execution_enabled:
        blockers.append("runtime_source_state_not_shadow_execution_disabled")

    if safety_readiness.status != (
        RuntimeSafetyReadinessStatus.READY_FOR_OWNER_CODEX_CONFIRMATION
    ):
        blockers.append("runtime_safety_readiness_not_ready")
        blockers.extend(
            f"runtime_safety_{blocker}" for blocker in safety_readiness.blockers
        )
    warnings.extend(
        f"runtime_safety_warning_{warning}"
        for warning in safety_readiness.warnings
    )

    if promotion_gate_result.status != (
        StrategyRuntimePromotionGateStatus.READY_FOR_FIRST_REAL_SUBMIT_GATE_REVIEW
    ):
        blockers.append("promotion_gate_not_ready_for_first_real_submit")
        blockers.extend(
            f"promotion_gate_{blocker}" for blocker in promotion_gate_result.blockers
        )
    warnings.extend(
        f"promotion_gate_warning_{warning}"
        for warning in promotion_gate_result.warnings
    )

    if not current_head_deployed:
        blockers.append("current_head_not_deployed_to_tokyo")
    if not owner_live_runtime_enablement_authorized:
        blockers.append("owner_live_runtime_enablement_authorization_missing")
    if not owner_real_submit_authorization_present:
        blockers.append("owner_real_submit_authorization_missing")
    if not submit_technical_rehearsal_passed:
        blockers.append("submit_technical_rehearsal_not_passed")
    if not submit_adapter_implemented:
        blockers.append("controlled_submit_adapter_not_implemented")
    if forbidden_flags:
        blockers.append("forbidden_execution_flags_present")
        blockers.extend(f"forbidden_{flag}" for flag in forbidden_flags)

    status = (
        StrategyRuntimeLiveEnablementPreviewStatus.BLOCKED
        if blockers
        else StrategyRuntimeLiveEnablementPreviewStatus.READY_FOR_LIVE_RUNTIME_ENABLEMENT_MUTATION_DESIGN
    )
    return StrategyRuntimeLiveEnablementPreview(
        runtime_instance_id=runtime.runtime_instance_id,
        strategy_family_id=runtime.strategy_family_id,
        strategy_family_version_id=runtime.strategy_family_version_id,
        symbol=runtime.symbol,
        side=runtime.side,
        status=status,
        blockers=_dedupe_sorted(blockers),
        warnings=_dedupe_sorted(warnings),
        safety_readiness_status=safety_readiness.status,
        promotion_gate_status=promotion_gate_result.status,
        current_runtime_status=runtime.status,
        current_runtime_shadow_mode=runtime.shadow_mode,
        current_runtime_execution_enabled=runtime.execution_enabled,
        current_head_deployed=current_head_deployed,
        owner_live_runtime_enablement_authorized=owner_live_runtime_enablement_authorized,
        owner_real_submit_authorization_present=owner_real_submit_authorization_present,
        submit_technical_rehearsal_passed=submit_technical_rehearsal_passed,
        submit_adapter_implemented=submit_adapter_implemented,
        forbidden_execution_flags=forbidden_flags,
    )


def build_strategy_runtime_live_enablement_mutation(
    *,
    runtime: StrategyRuntimeInstance,
    preview: StrategyRuntimeLiveEnablementPreview,
    mutation_id: str,
    owner_live_runtime_enablement_authorization_id: str,
    owner_real_submit_authorization_id: str,
    now_ms: int,
) -> StrategyRuntimeLiveEnablementMutation:
    blockers: list[str] = []
    if preview.runtime_instance_id != runtime.runtime_instance_id:
        blockers.append("live_enablement_preview_runtime_mismatch")
    if preview.status != (
        StrategyRuntimeLiveEnablementPreviewStatus.READY_FOR_LIVE_RUNTIME_ENABLEMENT_MUTATION_DESIGN
    ):
        blockers.append("live_enablement_preview_not_ready")
        blockers.extend(preview.blockers)
    if (
        preview.current_runtime_shadow_mode != runtime.shadow_mode
        or preview.current_runtime_execution_enabled != runtime.execution_enabled
        or preview.current_runtime_status != runtime.status
    ):
        blockers.append("live_enablement_preview_stale_runtime_state")
    if not owner_live_runtime_enablement_authorization_id.strip():
        blockers.append("owner_live_runtime_enablement_authorization_id_missing")
    if not owner_real_submit_authorization_id.strip():
        blockers.append("owner_real_submit_authorization_id_missing")

    updated_runtime: StrategyRuntimeInstance | None = None
    if not blockers:
        try:
            updated_runtime = runtime.enable_live_execution(
                now_ms=now_ms,
                mutation_id=mutation_id,
                owner_live_runtime_enablement_authorization_id=(
                    owner_live_runtime_enablement_authorization_id
                ),
                owner_real_submit_authorization_id=owner_real_submit_authorization_id,
            )
        except ValueError as exc:
            blockers.append(f"runtime_live_enablement_model_rejected:{exc}")

    status = (
        StrategyRuntimeLiveEnablementMutationStatus.APPLIED
        if updated_runtime is not None and not blockers
        else StrategyRuntimeLiveEnablementMutationStatus.BLOCKED
    )
    return StrategyRuntimeLiveEnablementMutation(
        mutation_id=mutation_id,
        runtime_instance_id=runtime.runtime_instance_id,
        strategy_family_id=runtime.strategy_family_id,
        strategy_family_version_id=runtime.strategy_family_version_id,
        symbol=runtime.symbol,
        side=runtime.side,
        status=status,
        blockers=_dedupe_sorted(blockers),
        previous_runtime_snapshot=runtime,
        updated_runtime_snapshot=updated_runtime,
        preview_snapshot=preview,
        owner_live_runtime_enablement_authorization_id=(
            owner_live_runtime_enablement_authorization_id or None
        ),
        owner_real_submit_authorization_id=owner_real_submit_authorization_id or None,
        created_at_ms=now_ms,
        runtime_state_mutated=status == StrategyRuntimeLiveEnablementMutationStatus.APPLIED,
    )


def _dedupe_sorted(items: list[str]) -> list[str]:
    return sorted(set(items))
