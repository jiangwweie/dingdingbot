"""Application service for StrategyRuntimeInstance shadow governance."""

from __future__ import annotations

import time
import uuid
from decimal import Decimal
from typing import Any, Optional, Protocol

from src.domain.brc_admission import AdmissionTrialBinding, StrategyFamilyVersion
from src.domain.strategy_runtime import (
    StrategyRuntimeBoundary,
    StrategyRuntimeEvent,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
    StrategyRuntimePolicySnapshot,
)
from src.domain.runtime_execution_attempt_mutation import (
    RuntimeExecutionAttemptMutation,
    RuntimeExecutionAttemptMutationStatus,
)
from src.domain.runtime_execution_post_submit_budget_settlement import (
    RuntimeExecutionPostSubmitBudgetSettlement,
    RuntimeExecutionPostSubmitBudgetSettlementStatus,
)
from src.domain.strategy_runtime_live_enablement import (
    StrategyRuntimeLiveEnablementMutation,
    StrategyRuntimeLiveEnablementMutationStatus,
    StrategyRuntimeLiveEnablementPreview,
    build_strategy_runtime_live_enablement_mutation,
)
from src.domain.strategy_runtime_promotion_gate import (
    StrategyRuntimePromotionGateConfirmationRecord,
    StrategyRuntimePromotionGateStatus,
)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class StrategyRuntimeError(ValueError):
    """Raised when a runtime shadow operation violates governance rules."""


class StrategyRuntimeRepositoryPort(Protocol):
    async def initialize(self) -> None:
        ...

    async def create(self, runtime: StrategyRuntimeInstance) -> StrategyRuntimeInstance:
        ...

    async def get(self, runtime_instance_id: str) -> Optional[StrategyRuntimeInstance]:
        ...

    async def list(self, *, status: Optional[StrategyRuntimeInstanceStatus] = None, limit: int = 100) -> list[StrategyRuntimeInstance]:
        ...

    async def update_status(self, runtime: StrategyRuntimeInstance) -> StrategyRuntimeInstance:
        ...

    async def record_event(self, event: StrategyRuntimeEvent) -> StrategyRuntimeEvent:
        ...

    async def find_by_trial_binding_id(self, trial_binding_id: str) -> Optional[StrategyRuntimeInstance]:
        ...


class StrategyRuntimeAdmissionRepositoryPort(Protocol):
    async def get_admission_trial_binding(self, binding_id: str) -> Optional[AdmissionTrialBinding]:
        ...

    async def get_strategy_family_version(self, strategy_family_version_id: str) -> Optional[StrategyFamilyVersion]:
        ...


class StrategyRuntimeInstanceService:
    def __init__(
        self,
        *,
        runtime_repository: StrategyRuntimeRepositoryPort,
        admission_repository: StrategyRuntimeAdmissionRepositoryPort,
    ) -> None:
        self._runtime_repo = runtime_repository
        self._admission_repo = admission_repository

    async def initialize(self) -> None:
        await self._runtime_repo.initialize()

    async def create_draft_from_trial_binding(
        self,
        trial_binding_id: str,
        *,
        symbol: Optional[str] = None,
        side: Optional[str] = None,
        carrier_id: Optional[str] = None,
        max_attempts: int = 1,
        max_active_positions: int = 1,
        max_notional_per_attempt: Optional[Decimal] = None,
        total_budget: Optional[Decimal] = None,
        max_leverage: Optional[Decimal] = None,
        expires_at_ms: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> StrategyRuntimeInstance:
        existing = await self._runtime_repo.find_by_trial_binding_id(trial_binding_id)
        if existing is not None:
            raise StrategyRuntimeError(
                f"strategy runtime already exists for trial binding: {trial_binding_id}"
            )
        binding = await self._admission_repo.get_admission_trial_binding(trial_binding_id)
        if binding is None:
            raise StrategyRuntimeError(f"admission trial binding not found: {trial_binding_id}")
        version = await self._admission_repo.get_strategy_family_version(
            binding.strategy_family_version_id
        )
        if version is None:
            raise StrategyRuntimeError(
                f"strategy family version not found: {binding.strategy_family_version_id}"
            )

        selected_symbol = symbol or _first_nonempty(version.supported_symbols) or "unresolved"
        selected_side = (side or "shadow").lower()
        now_ms = _now_ms()
        boundary = StrategyRuntimeBoundary(
            max_attempts=max_attempts,
            attempts_used=0,
            max_active_positions=max_active_positions,
            max_notional_per_attempt=max_notional_per_attempt,
            total_budget=total_budget,
            allowed_symbols=[selected_symbol],
            allowed_sides=[selected_side],
            max_leverage=max_leverage,
            requires_protection=True,
            requires_review=True,
        )
        policy_snapshot = StrategyRuntimePolicySnapshot(
            risk_policy_snapshot={},
            playbook_id=binding.playbook_id,
            playbook_snapshot=dict(binding.playbook_catalog_snapshot_json),
            admission_execution_mode=binding.execution_mode.value,
            source="admission_trial_binding",
        )
        runtime = StrategyRuntimeInstance(
            runtime_instance_id=_id("strategy-runtime"),
            trial_binding_id=binding.binding_id,
            admission_decision_id=binding.admission_decision_id,
            strategy_family_id=version.strategy_family_id,
            strategy_family_version_id=binding.strategy_family_version_id,
            owner_risk_acceptance_id=binding.owner_risk_acceptance_id,
            carrier_id=carrier_id or binding.runtime_carrier_id,
            symbol=selected_symbol,
            side=selected_side,
            status=StrategyRuntimeInstanceStatus.DRAFT,
            boundary=boundary,
            policy_snapshot=policy_snapshot,
            execution_enabled=False,
            shadow_mode=True,
            created_at_ms=now_ms,
            updated_at_ms=now_ms,
            expires_at_ms=expires_at_ms,
            metadata={
                "source_binding_status": binding.binding_status.value,
                "source_trial_env": binding.trial_env.value,
                "source_trial_stage": binding.trial_stage.value,
                **(metadata or {}),
            },
        )
        saved = await self._runtime_repo.create(runtime)
        await self._record_event(
            saved,
            previous_status=None,
            reason="runtime draft created from admission trial binding",
        )
        return saved

    async def create_draft_from_profile_confirmation(
        self,
        trial_binding_id: str,
        *,
        confirmation: StrategyRuntimePromotionGateConfirmationRecord,
        carrier_id: Optional[str] = None,
        expires_at_ms: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> StrategyRuntimeInstance:
        existing = await self._runtime_repo.find_by_trial_binding_id(trial_binding_id)
        if existing is not None:
            raise StrategyRuntimeError(
                f"strategy runtime already exists for trial binding: {trial_binding_id}"
            )
        if confirmation.runtime_instance_id is not None:
            existing_by_id = await self._runtime_repo.get(confirmation.runtime_instance_id)
            if existing_by_id is not None:
                raise StrategyRuntimeError(
                    "strategy runtime already exists for confirmation runtime id: "
                    f"{confirmation.runtime_instance_id}"
                )
        _require_profile_confirmation_ready(confirmation)
        proposal = confirmation.runtime_profile_proposal_snapshot
        if proposal is None:
            raise StrategyRuntimeError("runtime profile proposal snapshot is required")

        binding = await self._admission_repo.get_admission_trial_binding(trial_binding_id)
        if binding is None:
            raise StrategyRuntimeError(f"admission trial binding not found: {trial_binding_id}")
        version = await self._admission_repo.get_strategy_family_version(
            binding.strategy_family_version_id
        )
        if version is None:
            raise StrategyRuntimeError(
                f"strategy family version not found: {binding.strategy_family_version_id}"
            )
        if binding.strategy_family_version_id != confirmation.strategy_family_version_id:
            raise StrategyRuntimeError("confirmation strategy version does not match binding")
        if version.strategy_family_id != confirmation.strategy_family_id:
            raise StrategyRuntimeError("confirmation strategy family does not match version")
        if proposal.strategy_family_id != version.strategy_family_id:
            raise StrategyRuntimeError("profile proposal strategy family does not match version")
        if proposal.strategy_family_version_id != binding.strategy_family_version_id:
            raise StrategyRuntimeError(
                "profile proposal strategy version does not match binding"
            )

        now_ms = _now_ms()
        boundary = proposal.boundary.model_copy(
            deep=True,
            update={
                "attempts_used": 0,
                "budget_reserved": Decimal("0"),
            },
        )
        policy_snapshot = StrategyRuntimePolicySnapshot(
            risk_policy_snapshot={
                "source": "runtime_profile_promotion_confirmation",
                "confirmation_id": confirmation.confirmation_id,
                "proposal_id": proposal.proposal_id,
                "profile_kind": proposal.profile_kind.value,
                "capital_base": str(proposal.capital_base),
                "total_loss_budget": str(proposal.total_loss_budget),
                "max_loss_per_attempt": str(proposal.max_loss_per_attempt),
                "max_notional_per_attempt": str(proposal.max_notional_per_attempt),
                "max_leverage": str(proposal.max_leverage),
                "max_margin_per_attempt": str(proposal.max_margin_per_attempt),
            },
            playbook_id=binding.playbook_id,
            playbook_snapshot=dict(binding.playbook_catalog_snapshot_json),
            admission_execution_mode=binding.execution_mode.value,
            source="runtime_profile_promotion_confirmation",
        )
        runtime = StrategyRuntimeInstance(
            runtime_instance_id=confirmation.runtime_instance_id or _id("strategy-runtime"),
            trial_binding_id=binding.binding_id,
            admission_decision_id=binding.admission_decision_id,
            strategy_family_id=version.strategy_family_id,
            strategy_family_version_id=binding.strategy_family_version_id,
            owner_risk_acceptance_id=binding.owner_risk_acceptance_id,
            carrier_id=carrier_id or binding.runtime_carrier_id,
            symbol=proposal.symbol,
            side=proposal.side,
            status=StrategyRuntimeInstanceStatus.DRAFT,
            boundary=boundary,
            policy_snapshot=policy_snapshot,
            execution_enabled=False,
            shadow_mode=True,
            created_at_ms=now_ms,
            updated_at_ms=now_ms,
            expires_at_ms=expires_at_ms,
            metadata={
                "source": "runtime_profile_promotion_confirmation",
                "confirmation_id": confirmation.confirmation_id,
                "proposal_id": proposal.proposal_id,
                "proposal_profile_kind": proposal.profile_kind.value,
                "runtime_confirmation_mode": proposal.runtime_confirmation_mode.value,
                "loss_inside_budget_is_accepted": True,
                "runaway_behavior_is_forbidden": True,
                "creates_execution_intent": False,
                "order_created": False,
                "exchange_called": False,
                **(metadata or {}),
            },
        )
        saved = await self._runtime_repo.create(runtime)
        await self._record_event(
            saved,
            previous_status=None,
            reason="runtime draft created from confirmed profile proposal",
            event_type="created_from_profile_confirmation",
            metadata={
                "confirmation_id": confirmation.confirmation_id,
                "proposal_id": proposal.proposal_id,
                "execution_enabled": saved.execution_enabled,
                "shadow_mode": saved.shadow_mode,
                "creates_execution_intent": False,
                "order_created": False,
                "exchange_called": False,
            },
        )
        return saved

    async def activate_runtime(self, runtime_instance_id: str, *, actor: str = "owner") -> StrategyRuntimeInstance:
        runtime = await self._require_runtime(runtime_instance_id)
        if runtime.status in {StrategyRuntimeInstanceStatus.EXPIRED, StrategyRuntimeInstanceStatus.REVOKED}:
            raise StrategyRuntimeError(f"{runtime.status.value} runtime cannot activate")
        updated = runtime.transition_to(
            StrategyRuntimeInstanceStatus.ACTIVE,
            now_ms=_now_ms(),
            reason="shadow runtime activated; execution remains disabled",
        )
        saved = await self._runtime_repo.update_status(updated)
        await self._record_event(
            saved,
            previous_status=runtime.status,
            actor=actor,
            reason="shadow runtime activated; no execution intent, FinalGate, or order created",
        )
        return saved

    async def pause_runtime(self, runtime_instance_id: str, *, actor: str = "owner") -> StrategyRuntimeInstance:
        return await self._transition(
            runtime_instance_id,
            StrategyRuntimeInstanceStatus.PAUSED,
            actor=actor,
            reason="shadow runtime paused",
        )

    async def revoke_runtime(self, runtime_instance_id: str, *, actor: str = "owner") -> StrategyRuntimeInstance:
        return await self._transition(
            runtime_instance_id,
            StrategyRuntimeInstanceStatus.REVOKED,
            actor=actor,
            reason="shadow runtime revoked",
        )

    async def expire_runtime(self, runtime_instance_id: str, *, actor: str = "system") -> StrategyRuntimeInstance:
        return await self._transition(
            runtime_instance_id,
            StrategyRuntimeInstanceStatus.EXPIRED,
            actor=actor,
            reason="shadow runtime expired",
        )

    async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
        return await self._require_runtime(runtime_instance_id)

    async def list_runtimes(
        self,
        *,
        status: Optional[StrategyRuntimeInstanceStatus] = None,
        limit: int = 100,
    ) -> list[StrategyRuntimeInstance]:
        return await self._runtime_repo.list(status=status, limit=limit)

    async def apply_runtime_attempt_mutation(
        self,
        *,
        previous_runtime: StrategyRuntimeInstance,
        updated_runtime: StrategyRuntimeInstance,
        mutation: RuntimeExecutionAttemptMutation,
    ) -> StrategyRuntimeInstance:
        if mutation.status != RuntimeExecutionAttemptMutationStatus.APPLIED:
            raise StrategyRuntimeError("only applied attempt mutation can update runtime")
        if previous_runtime.runtime_instance_id != updated_runtime.runtime_instance_id:
            raise StrategyRuntimeError("runtime mutation previous/updated runtime mismatch")
        if mutation.runtime_instance_id != updated_runtime.runtime_instance_id:
            raise StrategyRuntimeError("runtime mutation target mismatch")
        if updated_runtime.execution_enabled or not updated_runtime.shadow_mode:
            raise StrategyRuntimeError("runtime mutation cannot enable execution")
        saved = await self._runtime_repo.update_status(updated_runtime)
        await self._record_event(
            saved,
            previous_status=previous_runtime.status,
            actor="system",
            reason="runtime attempt and budget reserved from controlled reservation",
            event_type="runtime_attempt_mutated",
            metadata={
                "mutation_id": mutation.mutation_id,
                "reservation_id": mutation.reservation_id,
                "authorization_id": mutation.authorization_id,
                "attempts_used_before": mutation.attempts_used_before,
                "attempts_used_after": mutation.attempts_used_after,
                "budget_reserved_before": str(mutation.budget_reserved_before),
                "budget_reserved_after": str(mutation.budget_reserved_after),
                "runtime_budget_mutated": mutation.runtime_budget_mutated,
                "attempt_consumed": mutation.attempt_consumed,
                "order_created": mutation.order_created,
                "exchange_called": mutation.exchange_called,
            },
        )
        return saved

    async def apply_runtime_post_submit_budget_settlement(
        self,
        *,
        previous_runtime: StrategyRuntimeInstance,
        updated_runtime: StrategyRuntimeInstance,
        settlement: RuntimeExecutionPostSubmitBudgetSettlement,
    ) -> StrategyRuntimeInstance:
        if settlement.status == RuntimeExecutionPostSubmitBudgetSettlementStatus.BLOCKED:
            raise StrategyRuntimeError("blocked budget settlement cannot update runtime")
        if previous_runtime.runtime_instance_id != updated_runtime.runtime_instance_id:
            raise StrategyRuntimeError("budget settlement previous/updated runtime mismatch")
        if settlement.runtime_instance_id != updated_runtime.runtime_instance_id:
            raise StrategyRuntimeError("budget settlement target mismatch")
        if updated_runtime.execution_enabled or not updated_runtime.shadow_mode:
            raise StrategyRuntimeError("budget settlement cannot enable execution")
        if updated_runtime.boundary.attempts_used != previous_runtime.boundary.attempts_used:
            raise StrategyRuntimeError("budget settlement cannot mutate attempt count")
        saved = await self._runtime_repo.update_status(updated_runtime)
        await self._record_event(
            saved,
            previous_status=previous_runtime.status,
            actor="system",
            reason="runtime post-submit budget settlement recorded",
            event_type="runtime_post_submit_budget_settled",
            metadata={
                "settlement_id": settlement.settlement_id,
                "accounting_id": settlement.accounting_id,
                "reservation_id": settlement.reservation_id,
                "authorization_id": settlement.authorization_id,
                "budget_action": (
                    settlement.budget_action.value
                    if settlement.budget_action is not None
                    else None
                ),
                "outcome_kind": settlement.outcome_kind,
                "budget_reserved_before": str(settlement.budget_reserved_before),
                "budget_reserved_after": str(settlement.budget_reserved_after),
                "budget_release_amount": str(settlement.budget_release_amount),
                "runtime_budget_mutated": settlement.runtime_budget_mutated,
                "attempt_counter_mutated": settlement.attempt_counter_mutated,
                "order_created": settlement.order_created,
                "exchange_called": settlement.exchange_called,
            },
        )
        return saved

    async def enable_live_runtime_from_preview(
        self,
        runtime_instance_id: str,
        *,
        preview: StrategyRuntimeLiveEnablementPreview,
        owner_live_runtime_enablement_authorization_id: str,
        owner_real_submit_authorization_id: str,
        actor: str = "owner",
    ) -> StrategyRuntimeLiveEnablementMutation:
        runtime = await self._require_runtime(runtime_instance_id)
        mutation = build_strategy_runtime_live_enablement_mutation(
            runtime=runtime,
            preview=preview,
            mutation_id=_id("strategy-runtime-live-enable"),
            owner_live_runtime_enablement_authorization_id=(
                owner_live_runtime_enablement_authorization_id
            ),
            owner_real_submit_authorization_id=owner_real_submit_authorization_id,
            now_ms=_now_ms(),
        )
        if mutation.status != StrategyRuntimeLiveEnablementMutationStatus.APPLIED:
            raise StrategyRuntimeError(
                "live runtime enablement blocked: "
                + ", ".join(mutation.blockers)
            )
        if mutation.updated_runtime_snapshot is None:
            raise StrategyRuntimeError("live runtime enablement missing updated runtime")
        saved = await self._runtime_repo.update_status(
            mutation.updated_runtime_snapshot
        )
        mutation = mutation.model_copy(update={"updated_runtime_snapshot": saved})
        await self._record_event(
            saved,
            previous_status=runtime.status,
            actor=actor,
            reason=(
                "live runtime enabled after Owner/Codex gates; no order submitted"
            ),
            event_type="live_runtime_enabled",
            metadata={
                "mutation_id": mutation.mutation_id,
                "owner_live_runtime_enablement_authorization_id": (
                    owner_live_runtime_enablement_authorization_id
                ),
                "owner_real_submit_authorization_id": owner_real_submit_authorization_id,
                "runtime_state_mutated": mutation.runtime_state_mutated,
                "execution_intent_created": mutation.execution_intent_created,
                "order_created": mutation.order_created,
                "exchange_called": mutation.exchange_called,
                "owner_bounded_execution_called": (
                    mutation.owner_bounded_execution_called
                ),
                "order_lifecycle_called": mutation.order_lifecycle_called,
                "not_order_authority": mutation.not_order_authority,
            },
        )
        return mutation

    async def _transition(
        self,
        runtime_instance_id: str,
        target_status: StrategyRuntimeInstanceStatus,
        *,
        actor: str,
        reason: str,
    ) -> StrategyRuntimeInstance:
        runtime = await self._require_runtime(runtime_instance_id)
        updated = runtime.transition_to(target_status, now_ms=_now_ms(), reason=reason)
        saved = await self._runtime_repo.update_status(updated)
        await self._record_event(saved, previous_status=runtime.status, actor=actor, reason=reason)
        return saved

    async def _require_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
        runtime = await self._runtime_repo.get(runtime_instance_id)
        if runtime is None:
            raise StrategyRuntimeError(f"strategy runtime not found: {runtime_instance_id}")
        return runtime

    async def _record_event(
        self,
        runtime: StrategyRuntimeInstance,
        *,
        previous_status: Optional[StrategyRuntimeInstanceStatus],
        actor: str = "system",
        reason: str,
        event_type: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        event = StrategyRuntimeEvent(
            event_id=_id("strategy-runtime-event"),
            runtime_instance_id=runtime.runtime_instance_id,
            event_type=event_type
            or ("status_transition" if previous_status is not None else "created"),
            previous_status=previous_status,
            next_status=runtime.status,
            actor=actor,
            reason=reason,
            metadata={
                "execution_enabled": runtime.execution_enabled,
                "shadow_mode": runtime.shadow_mode,
                **(metadata or {}),
            },
            created_at_ms=_now_ms(),
        )
        await self._runtime_repo.record_event(event)


def _first_nonempty(items: list[str]) -> Optional[str]:
    for item in items:
        value = str(item).strip()
        if value:
            return value
    return None


def _require_profile_confirmation_ready(
    confirmation: StrategyRuntimePromotionGateConfirmationRecord,
) -> None:
    if (
        confirmation.promotion_gate_result_snapshot is not None
        and confirmation.promotion_gate_result_snapshot.status
        == StrategyRuntimePromotionGateStatus.BLOCKED
    ):
        raise StrategyRuntimeError("blocked promotion confirmation cannot create runtime")
    semantic = confirmation.semantic_confirmations
    semantic_checks = {
        "strategy_family_confirmed": semantic.strategy_family_confirmed,
        "implementation_source_confirmed": semantic.implementation_source_confirmed,
        "required_facts_confirmed": semantic.required_facts_confirmed,
        "entry_policy_confirmed": semantic.entry_policy_confirmed,
        "exit_policy_confirmed": semantic.exit_policy_confirmed,
        "protection_policy_confirmed": semantic.protection_policy_confirmed,
        "eligible_for_runtime_execution_confirmed": (
            semantic.eligible_for_runtime_execution_confirmed
        ),
        "right_tail_review_metrics_confirmed": (
            semantic.right_tail_review_metrics_confirmed
        ),
    }
    runtime = confirmation.runtime_confirmations
    runtime_checks = {
        "runtime_profile_confirmed": runtime.runtime_profile_confirmed,
        "owner_confirmation_mode_confirmed": (
            runtime.owner_confirmation_mode_confirmed
        ),
        "symbol_side_boundary_confirmed": runtime.symbol_side_boundary_confirmed,
        "max_loss_budget_confirmed": runtime.max_loss_budget_confirmed,
        "max_notional_boundary_confirmed": runtime.max_notional_boundary_confirmed,
        "max_active_positions_boundary_confirmed": (
            runtime.max_active_positions_boundary_confirmed
        ),
        "max_leverage_boundary_confirmed": runtime.max_leverage_boundary_confirmed,
        "margin_usage_boundary_confirmed": runtime.margin_usage_boundary_confirmed,
        "liquidation_buffer_boundary_confirmed": (
            runtime.liquidation_buffer_boundary_confirmed
        ),
        "protection_readiness_source_confirmed": (
            runtime.protection_readiness_source_confirmed
        ),
        "stale_fact_behavior_confirmed": runtime.stale_fact_behavior_confirmed,
        "attempt_consumption_rule_confirmed": (
            runtime.attempt_consumption_rule_confirmed
        ),
        "budget_reservation_rule_confirmed": (
            runtime.budget_reservation_rule_confirmed
        ),
        "trusted_active_position_source_confirmed": (
            runtime.trusted_active_position_source_confirmed
        ),
        "trusted_account_fact_source_confirmed": (
            runtime.trusted_account_fact_source_confirmed
        ),
    }
    missing = [
        key
        for key, confirmed in {**semantic_checks, **runtime_checks}.items()
        if not confirmed
    ]
    if missing:
        raise StrategyRuntimeError(
            "profile confirmation missing required confirmations: "
            + ", ".join(sorted(missing))
        )
    proposal = confirmation.runtime_profile_proposal_snapshot
    if proposal is None:
        raise StrategyRuntimeError("runtime profile proposal snapshot is required")
    if proposal.side == "short" and not runtime.short_side_conservative_profile_confirmed:
        raise StrategyRuntimeError(
            "short-side runtime profile confirmation is required"
        )
