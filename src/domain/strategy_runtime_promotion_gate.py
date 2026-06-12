"""Promotion gate for strategy-runtime execution readiness.

This module is pure domain logic. It evaluates whether a strategy semantics
binding has the Owner/Codex confirmations needed before promotion beyond
shadow/preview runtime governance. It does not create candidates, intents,
orders, exchange payloads, or runtime mutations.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.experimental_runtime_profile_proposal import (
    ExperimentalRuntimeProfileProposal,
    ExperimentalRuntimeProfileProposalStatus,
)
from src.domain.strategy_semantics import (
    StrategyCandidateMode,
    StrategyImplementationBinding,
    StrategyImplementationKind,
)


class StrategyRuntimePromotionGateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StrategyRuntimePromotionScope(str, Enum):
    CONTROLLED_RUNTIME_EXECUTION = "controlled_runtime_execution"
    FIRST_REAL_SUBMIT_GATE_REVIEW = "first_real_submit_gate_review"


class StrategyRuntimePromotionGateStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_CONTROLLED_RUNTIME_EXECUTION_DESIGN = (
        "ready_for_controlled_runtime_execution_design"
    )
    READY_FOR_FIRST_REAL_SUBMIT_GATE_REVIEW = (
        "ready_for_first_real_submit_gate_review"
    )


class StrategySemanticsConfirmationFacts(StrategyRuntimePromotionGateModel):
    strategy_family_confirmed: bool = False
    implementation_source_confirmed: bool = False
    required_facts_confirmed: bool = False
    entry_policy_confirmed: bool = False
    exit_policy_confirmed: bool = False
    protection_policy_confirmed: bool = False
    eligible_for_runtime_execution_confirmed: bool = False
    right_tail_review_metrics_confirmed: bool = False


class RuntimeExecutionConfirmationFacts(StrategyRuntimePromotionGateModel):
    runtime_profile_confirmed: bool = False
    owner_confirmation_mode_confirmed: bool = False
    symbol_side_boundary_confirmed: bool = False
    max_loss_budget_confirmed: bool = False
    max_notional_boundary_confirmed: bool = False
    max_active_positions_boundary_confirmed: bool = False
    max_leverage_boundary_confirmed: bool = False
    margin_usage_boundary_confirmed: bool = False
    liquidation_buffer_boundary_confirmed: bool = False
    protection_readiness_source_confirmed: bool = False
    stale_fact_behavior_confirmed: bool = False
    attempt_consumption_rule_confirmed: bool = False
    budget_reservation_rule_confirmed: bool = False
    trusted_active_position_source_confirmed: bool = False
    trusted_account_fact_source_confirmed: bool = False
    short_side_conservative_profile_confirmed: bool = False


class FirstRealSubmitConfirmationFacts(StrategyRuntimePromotionGateModel):
    budget_release_or_consume_rule_confirmed: bool = False
    post_submit_budget_settlement_persistence_confirmed: bool = False
    post_submit_budget_settlement_persistence_evidence_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=260,
    )
    attempt_outcome_policy_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=360,
    )
    protection_creation_failure_policy_confirmed: bool = False
    protection_creation_failure_policy_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=300,
    )
    duplicate_submit_policy_confirmed: bool = False
    submit_idempotency_policy_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=240,
    )
    trusted_submit_fact_snapshot_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=240,
    )
    local_registration_enablement_decision_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=300,
    )
    exchange_submit_enablement_decision_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=300,
    )
    exchange_submit_execution_result_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=540,
    )
    runtime_submit_rehearsal_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=560,
    )
    deployment_readiness_evidence_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=220,
    )
    owner_real_submit_authorization_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=220,
    )
    deployment_readiness_confirmed: bool = False
    explicit_owner_real_submit_authorization: bool = False


class StrategyRuntimePromotionGateInput(StrategyRuntimePromotionGateModel):
    binding: StrategyImplementationBinding
    scope: StrategyRuntimePromotionScope = (
        StrategyRuntimePromotionScope.CONTROLLED_RUNTIME_EXECUTION
    )
    semantic_confirmations: StrategySemanticsConfirmationFacts = Field(
        default_factory=StrategySemanticsConfirmationFacts
    )
    runtime_confirmations: RuntimeExecutionConfirmationFacts = Field(
        default_factory=RuntimeExecutionConfirmationFacts
    )
    first_real_submit_confirmations: FirstRealSubmitConfirmationFacts = Field(
        default_factory=FirstRealSubmitConfirmationFacts
    )


class StrategyRuntimePromotionGateResult(StrategyRuntimePromotionGateModel):
    status: StrategyRuntimePromotionGateStatus
    scope: StrategyRuntimePromotionScope
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    missing_owner_decisions: list[str] = Field(default_factory=list)
    binding_candidate_mode: StrategyCandidateMode
    implementation_kind: StrategyImplementationKind
    runtime_confirmation_mode: str = Field(min_length=1, max_length=128)
    proven_alpha: bool
    not_execution_authority: Literal[True] = True
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    exchange_called: Literal[False] = False


class StrategyRuntimePromotionGateConfirmationRecord(
    StrategyRuntimePromotionGateModel
):
    """Auditable Owner/Codex confirmation facts for promotion-gate review.

    This record freezes the facts used to evaluate a promotion gate. It is not
    an ExecutionIntent, submit authorization, order, transfer, withdrawal, or
    exchange request.
    """

    confirmation_id: str = Field(min_length=1, max_length=180)
    runtime_instance_id: Optional[str] = Field(default=None, max_length=128)
    strategy_family_id: str = Field(min_length=1, max_length=128)
    strategy_family_version_id: str = Field(min_length=1, max_length=128)
    scope: StrategyRuntimePromotionScope = (
        StrategyRuntimePromotionScope.CONTROLLED_RUNTIME_EXECUTION
    )
    semantic_confirmations: StrategySemanticsConfirmationFacts = Field(
        default_factory=StrategySemanticsConfirmationFacts
    )
    runtime_confirmations: RuntimeExecutionConfirmationFacts = Field(
        default_factory=RuntimeExecutionConfirmationFacts
    )
    first_real_submit_confirmations: FirstRealSubmitConfirmationFacts = Field(
        default_factory=FirstRealSubmitConfirmationFacts
    )
    runtime_profile_proposal_snapshot: Optional[
        ExperimentalRuntimeProfileProposal
    ] = None
    promotion_gate_result_snapshot: Optional[StrategyRuntimePromotionGateResult] = None
    recorded_by: str = Field(default="owner", min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=512)
    evidence_refs: list[str] = Field(default_factory=list)
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    records_promotion_gate_confirmation: Literal[True] = True
    not_execution_authority: Literal[True] = True
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    exchange_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    runtime_mutation_created: Literal[False] = False
    withdrawal_instruction_created: Literal[False] = False
    transfer_instruction_created: Literal[False] = False

    @model_validator(mode="after")
    def _reject_execution_metadata(
        self,
    ) -> "StrategyRuntimePromotionGateConfirmationRecord":
        if self.runtime_profile_proposal_snapshot is not None:
            _validate_runtime_profile_proposal_snapshot(
                self.runtime_profile_proposal_snapshot,
                strategy_family_id=self.strategy_family_id,
                strategy_family_version_id=self.strategy_family_version_id,
            )
        forbidden = {
            "client_order_id",
            "exchange_order_id",
            "exchange_payload",
            "execution_intent_id",
            "order_id",
            "place_order",
            "submit_order",
            "transfer_payload",
            "withdrawal_payload",
        }
        for key in _walk_keys({"metadata": self.metadata}):
            if key.lower() in forbidden:
                raise ValueError(
                    "promotion confirmation contains forbidden execution field: "
                    f"{key}"
                )
        return self

    def to_gate_input(
        self,
        binding: StrategyImplementationBinding,
    ) -> StrategyRuntimePromotionGateInput:
        return StrategyRuntimePromotionGateInput(
            binding=binding,
            scope=self.scope,
            semantic_confirmations=self.semantic_confirmations,
            runtime_confirmations=self.runtime_confirmations,
            first_real_submit_confirmations=self.first_real_submit_confirmations,
        )


def evaluate_strategy_runtime_promotion_gate(
    gate_input: StrategyRuntimePromotionGateInput,
) -> StrategyRuntimePromotionGateResult:
    binding = gate_input.binding
    blockers: list[str] = []
    warnings: list[str] = []
    missing_owner_decisions: list[str] = []

    _check_binding_admission(binding, blockers, warnings)
    _check_semantic_confirmations(
        gate_input.semantic_confirmations,
        blockers,
        missing_owner_decisions,
    )
    _check_runtime_confirmations(
        binding,
        gate_input.runtime_confirmations,
        blockers,
        missing_owner_decisions,
    )
    if gate_input.scope == StrategyRuntimePromotionScope.FIRST_REAL_SUBMIT_GATE_REVIEW:
        _check_first_real_submit_confirmations(
            gate_input.first_real_submit_confirmations,
            blockers,
            missing_owner_decisions,
        )

    if blockers:
        status = StrategyRuntimePromotionGateStatus.BLOCKED
    elif gate_input.scope == StrategyRuntimePromotionScope.FIRST_REAL_SUBMIT_GATE_REVIEW:
        status = StrategyRuntimePromotionGateStatus.READY_FOR_FIRST_REAL_SUBMIT_GATE_REVIEW
    else:
        status = (
            StrategyRuntimePromotionGateStatus.READY_FOR_CONTROLLED_RUNTIME_EXECUTION_DESIGN
        )

    if not binding.proven_alpha:
        warnings.append(
            "strategy_not_proven_alpha_limits_economic_and_autonomy_admission"
        )

    return StrategyRuntimePromotionGateResult(
        status=status,
        scope=gate_input.scope,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        missing_owner_decisions=sorted(set(missing_owner_decisions)),
        binding_candidate_mode=binding.candidate_mode,
        implementation_kind=binding.implementation_kind,
        runtime_confirmation_mode=binding.runtime_confirmation_mode.value,
        proven_alpha=binding.proven_alpha,
    )


def _check_binding_admission(
    binding: StrategyImplementationBinding,
    blockers: list[str],
    warnings: list[str],
) -> None:
    if binding.candidate_mode != StrategyCandidateMode.SHADOW_ORDER_CANDIDATE_ALLOWED:
        blockers.append("strategy_binding_not_trade_candidate")
    if binding.implementation_kind == StrategyImplementationKind.REGIME_CLASSIFIER:
        blockers.append("regime_classifier_not_runtime_trade_strategy")
    if binding.implementation_kind == StrategyImplementationKind.DATA_DEPENDENT_BACKLOG:
        blockers.append("data_backlog_not_runtime_trade_strategy")
    if binding.reference_implementation:
        warnings.append("reference_implementation_not_proven_production_strategy")


def _check_semantic_confirmations(
    facts: StrategySemanticsConfirmationFacts,
    blockers: list[str],
    missing_owner_decisions: list[str],
) -> None:
    required = {
        "strategy_family_confirmed": facts.strategy_family_confirmed,
        "implementation_source_confirmed": facts.implementation_source_confirmed,
        "required_facts_confirmed": facts.required_facts_confirmed,
        "entry_policy_confirmed": facts.entry_policy_confirmed,
        "exit_policy_confirmed": facts.exit_policy_confirmed,
        "protection_policy_confirmed": facts.protection_policy_confirmed,
        "eligible_for_runtime_execution_confirmed": (
            facts.eligible_for_runtime_execution_confirmed
        ),
        "right_tail_review_metrics_confirmed": (
            facts.right_tail_review_metrics_confirmed
        ),
    }
    _append_missing(required, "semantic", blockers, missing_owner_decisions)


def _check_runtime_confirmations(
    binding: StrategyImplementationBinding,
    facts: RuntimeExecutionConfirmationFacts,
    blockers: list[str],
    missing_owner_decisions: list[str],
) -> None:
    required = {
        "runtime_profile_confirmed": facts.runtime_profile_confirmed,
        "owner_confirmation_mode_confirmed": facts.owner_confirmation_mode_confirmed,
        "symbol_side_boundary_confirmed": facts.symbol_side_boundary_confirmed,
        "max_loss_budget_confirmed": facts.max_loss_budget_confirmed,
        "max_notional_boundary_confirmed": facts.max_notional_boundary_confirmed,
        "max_active_positions_boundary_confirmed": (
            facts.max_active_positions_boundary_confirmed
        ),
        "max_leverage_boundary_confirmed": facts.max_leverage_boundary_confirmed,
        "margin_usage_boundary_confirmed": facts.margin_usage_boundary_confirmed,
        "liquidation_buffer_boundary_confirmed": (
            facts.liquidation_buffer_boundary_confirmed
        ),
        "protection_readiness_source_confirmed": (
            facts.protection_readiness_source_confirmed
        ),
        "stale_fact_behavior_confirmed": facts.stale_fact_behavior_confirmed,
        "attempt_consumption_rule_confirmed": facts.attempt_consumption_rule_confirmed,
        "budget_reservation_rule_confirmed": facts.budget_reservation_rule_confirmed,
        "trusted_active_position_source_confirmed": (
            facts.trusted_active_position_source_confirmed
        ),
        "trusted_account_fact_source_confirmed": (
            facts.trusted_account_fact_source_confirmed
        ),
    }
    if _binding_requires_short_side_conservative_profile(binding):
        required["short_side_conservative_profile_confirmed"] = (
            facts.short_side_conservative_profile_confirmed
        )
    _append_missing(required, "runtime", blockers, missing_owner_decisions)


def _check_first_real_submit_confirmations(
    facts: FirstRealSubmitConfirmationFacts,
    blockers: list[str],
    missing_owner_decisions: list[str],
) -> None:
    required = {
        "budget_release_or_consume_rule_confirmed": (
            facts.budget_release_or_consume_rule_confirmed
        ),
        "post_submit_budget_settlement_persistence_confirmed": (
            facts.post_submit_budget_settlement_persistence_confirmed
        ),
        "protection_creation_failure_policy_confirmed": (
            facts.protection_creation_failure_policy_confirmed
        ),
        "duplicate_submit_policy_confirmed": facts.duplicate_submit_policy_confirmed,
        "deployment_readiness_confirmed": facts.deployment_readiness_confirmed,
        "explicit_owner_real_submit_authorization": (
            facts.explicit_owner_real_submit_authorization
        ),
    }
    _append_missing(required, "first_real_submit", blockers, missing_owner_decisions)
    if not facts.post_submit_budget_settlement_persistence_evidence_id:
        blockers.append(
            "first_real_submit_post_submit_budget_settlement_persistence_"
            "evidence_id_missing"
        )
        missing_owner_decisions.append(
            "post_submit_budget_settlement_persistence_evidence_id"
        )
    if not facts.attempt_outcome_policy_id:
        blockers.append("first_real_submit_attempt_outcome_policy_id_missing")
        missing_owner_decisions.append("attempt_outcome_policy_id")
    if not facts.trusted_submit_fact_snapshot_id:
        blockers.append("first_real_submit_trusted_submit_fact_snapshot_id_missing")
        missing_owner_decisions.append("trusted_submit_fact_snapshot_id")
    if not facts.submit_idempotency_policy_id:
        blockers.append("first_real_submit_submit_idempotency_policy_id_missing")
        missing_owner_decisions.append("submit_idempotency_policy_id")
    if not facts.protection_creation_failure_policy_id:
        blockers.append(
            "first_real_submit_protection_creation_failure_policy_id_missing"
        )
        missing_owner_decisions.append("protection_creation_failure_policy_id")
    if not facts.local_registration_enablement_decision_id:
        blockers.append(
            "first_real_submit_local_registration_enablement_decision_id_missing"
        )
        missing_owner_decisions.append("local_registration_enablement_decision_id")
    if not facts.exchange_submit_enablement_decision_id:
        blockers.append(
            "first_real_submit_exchange_submit_enablement_decision_id_missing"
        )
        missing_owner_decisions.append("exchange_submit_enablement_decision_id")
    if (
        not facts.runtime_submit_rehearsal_id
        and not facts.exchange_submit_execution_result_id
    ):
        blockers.append(
            "first_real_submit_runtime_submit_rehearsal_or_execution_result_"
            "id_missing"
        )
        missing_owner_decisions.append(
            "runtime_submit_rehearsal_or_execution_result_id"
        )
    if not facts.deployment_readiness_evidence_id:
        blockers.append("first_real_submit_deployment_readiness_evidence_id_missing")
        missing_owner_decisions.append("deployment_readiness_evidence_id")
    if not facts.owner_real_submit_authorization_id:
        blockers.append(
            "first_real_submit_owner_real_submit_authorization_id_missing"
        )
        missing_owner_decisions.append("owner_real_submit_authorization_id")


def _append_missing(
    required: dict[str, bool],
    prefix: str,
    blockers: list[str],
    missing_owner_decisions: list[str],
) -> None:
    for key, confirmed in required.items():
        if confirmed:
            continue
        blockers.append(f"{prefix}_{key}_missing")
        missing_owner_decisions.append(key)


def _binding_requires_short_side_conservative_profile(
    binding: StrategyImplementationBinding,
) -> bool:
    supported_sides = {side.lower() for side in binding.supported_sides}
    if "short" in supported_sides:
        return True
    return bool(binding.metadata.get("short_side_conservative_profile_required"))


def _validate_runtime_profile_proposal_snapshot(
    proposal: ExperimentalRuntimeProfileProposal,
    *,
    strategy_family_id: str,
    strategy_family_version_id: str,
) -> None:
    if proposal.status != (
        ExperimentalRuntimeProfileProposalStatus.READY_FOR_OWNER_CODEX_CONFIRMATION
    ):
        raise ValueError("runtime profile proposal snapshot is not ready")
    if proposal.strategy_family_id != strategy_family_id:
        raise ValueError("runtime profile proposal strategy_family_id mismatch")
    if proposal.strategy_family_version_id != strategy_family_version_id:
        raise ValueError("runtime profile proposal strategy_family_version_id mismatch")
    if proposal.blockers:
        raise ValueError("runtime profile proposal snapshot has blockers")
    if (
        not proposal.not_execution_authority
        or proposal.creates_runtime
        or proposal.creates_execution_intent
        or proposal.order_created
        or proposal.exchange_called
    ):
        raise ValueError("runtime profile proposal snapshot contains action authority")


def _walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.append(str(key))
            keys.extend(_walk_keys(nested))
    elif isinstance(value, list):
        for item in value:
            keys.extend(_walk_keys(item))
    return keys
