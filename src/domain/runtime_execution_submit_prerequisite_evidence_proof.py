"""Read-only prerequisite evidence proof for first-real-submit review."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_attempt_outcome_policy import (
    RuntimeExecutionAttemptOutcomeKind,
    RuntimeExecutionAttemptOutcomePolicy,
    RuntimeExecutionAttemptOutcomePolicyStatus,
)
from src.domain.runtime_execution_exchange_submit_enablement import (
    RuntimeExecutionExchangeSubmitEnablementDecision,
)
from src.domain.runtime_execution_protection_failure_policy import (
    RuntimeExecutionProtectionFailurePolicy,
    RuntimeExecutionProtectionFailurePolicyStatus,
)
from src.domain.runtime_execution_trusted_submit_facts import (
    RuntimeExecutionTrustedSubmitFactsSnapshot,
    RuntimeExecutionTrustedSubmitFactsStatus,
)


class RuntimeExecutionSubmitPrerequisiteEvidenceProofModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionSubmitPrerequisiteEvidenceProofStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_FIRST_REAL_SUBMIT_PREREQUISITE_REVIEW = (
        "ready_for_first_real_submit_prerequisite_review"
    )


class RuntimeExecutionSubmitPrerequisiteEvidenceProof(
    RuntimeExecutionSubmitPrerequisiteEvidenceProofModel
):
    proof_id: str = Field(min_length=1, max_length=540)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    source_type: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    semantic_ids: BrcSemanticIds
    status: RuntimeExecutionSubmitPrerequisiteEvidenceProofStatus
    trusted_submit_fact_snapshot_id: Optional[str] = Field(
        default=None,
        max_length=240,
    )
    trusted_submit_fact_snapshot_status: Optional[str] = Field(
        default=None,
        max_length=96,
    )
    trusted_submit_facts_ready: bool = False
    trusted_submit_facts_fresh_enough: bool = False
    trusted_submit_facts_read_only_sources_only: bool = False
    trusted_submit_facts_owner_allow_rejected: bool = False
    trusted_submit_facts_missing_or_stale_block: bool = False
    attempt_outcome_policy_id: Optional[str] = Field(default=None, max_length=360)
    attempt_outcome_policy_status: Optional[str] = Field(default=None, max_length=96)
    attempt_outcome_kind: Optional[str] = Field(default=None, max_length=96)
    attempt_outcome_policy_ready: bool = False
    attempt_consumed_on_any_fill: bool = False
    partial_fill_counts_as_attempt: bool = False
    budget_held_until_position_resolved: bool = False
    attempt_policy_blocks_new_entries: bool = False
    attempt_policy_requires_owner_recovery_review: bool = False
    attempt_policy_requires_reduce_only_recovery: bool = False
    attempt_policy_requires_reconciliation: bool = False
    protection_creation_failure_policy_id: Optional[str] = Field(
        default=None,
        max_length=300,
    )
    protection_failure_policy_status: Optional[str] = Field(
        default=None,
        max_length=96,
    )
    protection_failure_policy_ready: bool = False
    protection_failure_blocks_new_entries: bool = False
    protection_failure_marks_unprotected: bool = False
    protection_failure_requires_owner_review: bool = False
    protection_failure_requires_reduce_only: bool = False
    protection_failure_requires_reconciliation: bool = False
    protection_failure_consumes_attempt_on_fill: bool = False
    protection_failure_holds_budget_until_resolved: bool = False
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    not_live_action_authorization: Literal[True] = True
    not_exchange_submit_authority: Literal[True] = True
    not_order_lifecycle_authority: Literal[True] = True
    execution_intent_status_changed: Literal[False] = False
    order_created: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    exchange_called: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    runtime_state_mutated: Literal[False] = False
    withdrawal_or_transfer_created: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_proof(self) -> "RuntimeExecutionSubmitPrerequisiteEvidenceProof":
        _reject_forbidden_execution_fields(
            "submit prerequisite evidence proof",
            {"metadata": self.metadata},
        )
        if (
            self.status
            == (
                RuntimeExecutionSubmitPrerequisiteEvidenceProofStatus
                .READY_FOR_FIRST_REAL_SUBMIT_PREREQUISITE_REVIEW
            )
            and self.blockers
        ):
            raise ValueError("ready prerequisite proof cannot have blockers")
        if (
            self.execution_intent_status_changed
            or self.order_created
            or self.order_lifecycle_called
            or self.exchange_called
            or self.exchange_order_submitted
            or self.owner_bounded_execution_called
            or self.runtime_state_mutated
            or self.withdrawal_or_transfer_created
        ):
            raise ValueError("submit prerequisite proof cannot perform execution")
        return self


def build_runtime_execution_submit_prerequisite_evidence_proof(
    *,
    enablement_decision: RuntimeExecutionExchangeSubmitEnablementDecision,
    trusted_submit_facts: RuntimeExecutionTrustedSubmitFactsSnapshot | None,
    attempt_outcome_policy: RuntimeExecutionAttemptOutcomePolicy | None,
    protection_failure_policy: RuntimeExecutionProtectionFailurePolicy | None,
    trusted_submit_facts_repository_available: bool,
    attempt_outcome_policy_repository_available: bool,
    protection_failure_policy_repository_available: bool,
    now_ms: int,
    additional_blockers: list[str] | None = None,
    additional_warnings: list[str] | None = None,
) -> RuntimeExecutionSubmitPrerequisiteEvidenceProof:
    blockers = list(additional_blockers or [])
    warnings = list(additional_warnings or [])

    _check_trusted_submit_facts(
        enablement_decision,
        trusted_submit_facts,
        trusted_submit_facts_repository_available=(
            trusted_submit_facts_repository_available
        ),
        blockers=blockers,
        warnings=warnings,
    )
    _check_attempt_outcome_policy(
        enablement_decision,
        attempt_outcome_policy,
        attempt_outcome_policy_repository_available=(
            attempt_outcome_policy_repository_available
        ),
        blockers=blockers,
        warnings=warnings,
    )
    _check_protection_failure_policy(
        enablement_decision,
        protection_failure_policy,
        protection_failure_policy_repository_available=(
            protection_failure_policy_repository_available
        ),
        blockers=blockers,
        warnings=warnings,
    )

    blockers = _dedupe(blockers)
    warnings = _dedupe(warnings)
    status = (
        RuntimeExecutionSubmitPrerequisiteEvidenceProofStatus.BLOCKED
        if blockers
        else (
            RuntimeExecutionSubmitPrerequisiteEvidenceProofStatus
            .READY_FOR_FIRST_REAL_SUBMIT_PREREQUISITE_REVIEW
        )
    )

    return RuntimeExecutionSubmitPrerequisiteEvidenceProof(
        proof_id=(
            "runtime-submit-prerequisite-evidence-proof-"
            f"{enablement_decision.authorization_id}"
        ),
        authorization_id=enablement_decision.authorization_id,
        execution_intent_id=enablement_decision.execution_intent_id,
        runtime_instance_id=enablement_decision.runtime_instance_id,
        source_type=enablement_decision.source_type,
        source_id=enablement_decision.source_id,
        semantic_ids=enablement_decision.semantic_ids,
        status=status,
        trusted_submit_fact_snapshot_id=(
            enablement_decision.trusted_submit_fact_snapshot_id
        ),
        trusted_submit_fact_snapshot_status=_enum_value(
            getattr(trusted_submit_facts, "status", None)
        ),
        trusted_submit_facts_ready=_trusted_submit_facts_ready(
            trusted_submit_facts
        ),
        trusted_submit_facts_fresh_enough=bool(
            getattr(trusted_submit_facts, "facts_fresh_enough", False)
        ),
        trusted_submit_facts_read_only_sources_only=bool(
            getattr(trusted_submit_facts, "read_only_sources_only", False)
        ),
        trusted_submit_facts_owner_allow_rejected=bool(
            getattr(trusted_submit_facts, "owner_supplied_allow_facts_rejected", False)
        ),
        trusted_submit_facts_missing_or_stale_block=bool(
            getattr(trusted_submit_facts, "missing_or_stale_facts_block", False)
        ),
        attempt_outcome_policy_id=enablement_decision.attempt_outcome_policy_id,
        attempt_outcome_policy_status=_enum_value(
            getattr(attempt_outcome_policy, "status", None)
        ),
        attempt_outcome_kind=_enum_value(
            getattr(attempt_outcome_policy, "outcome_kind", None)
        ),
        attempt_outcome_policy_ready=_attempt_outcome_policy_ready(
            attempt_outcome_policy
        ),
        attempt_consumed_on_any_fill=bool(
            getattr(attempt_outcome_policy, "attempt_should_be_consumed", False)
        ),
        partial_fill_counts_as_attempt=bool(
            getattr(attempt_outcome_policy, "partial_fill_counts_as_attempt", False)
        ),
        budget_held_until_position_resolved=bool(
            getattr(attempt_outcome_policy, "reserved_budget_should_remain_held", False)
        ),
        attempt_policy_blocks_new_entries=bool(
            getattr(attempt_outcome_policy, "blocks_new_entries_until_resolved", False)
        ),
        attempt_policy_requires_owner_recovery_review=bool(
            getattr(attempt_outcome_policy, "requires_owner_recovery_review", False)
        ),
        attempt_policy_requires_reduce_only_recovery=bool(
            getattr(attempt_outcome_policy, "requires_reduce_only_recovery_mode", False)
        ),
        attempt_policy_requires_reconciliation=bool(
            getattr(attempt_outcome_policy, "requires_reconciliation_before_retry", False)
        ),
        protection_creation_failure_policy_id=(
            enablement_decision.protection_creation_failure_policy_id
        ),
        protection_failure_policy_status=_enum_value(
            getattr(protection_failure_policy, "status", None)
        ),
        protection_failure_policy_ready=_protection_failure_policy_ready(
            protection_failure_policy
        ),
        protection_failure_blocks_new_entries=bool(
            getattr(protection_failure_policy, "block_new_entries_until_resolved", False)
        ),
        protection_failure_marks_unprotected=bool(
            getattr(
                protection_failure_policy,
                "mark_position_unprotected_until_verified",
                False,
            )
        ),
        protection_failure_requires_owner_review=bool(
            getattr(protection_failure_policy, "require_owner_recovery_review", False)
        ),
        protection_failure_requires_reduce_only=bool(
            getattr(protection_failure_policy, "require_reduce_only_recovery_mode", False)
        ),
        protection_failure_requires_reconciliation=bool(
            getattr(protection_failure_policy, "require_reconciliation_before_retry", False)
        ),
        protection_failure_consumes_attempt_on_fill=bool(
            getattr(protection_failure_policy, "consume_attempt_on_any_fill", False)
        ),
        protection_failure_holds_budget_until_resolved=bool(
            getattr(
                protection_failure_policy,
                "hold_or_reconcile_budget_until_position_resolved",
                False,
            )
        ),
        blockers=blockers,
        warnings=warnings,
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_submit_prerequisite_evidence_proof",
            "read_only_prerequisite_evidence_proof": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
            "does_not_create_order": True,
            "does_not_mutate_budget_or_attempts": True,
        },
    )


def _check_trusted_submit_facts(
    decision: RuntimeExecutionExchangeSubmitEnablementDecision,
    facts: RuntimeExecutionTrustedSubmitFactsSnapshot | None,
    *,
    trusted_submit_facts_repository_available: bool,
    blockers: list[str],
    warnings: list[str],
) -> None:
    id_present = _present(decision.trusted_submit_fact_snapshot_id)
    if not trusted_submit_facts_repository_available:
        blockers.append("trusted_submit_fact_snapshot_repository_unavailable")
    if not id_present:
        blockers.append("trusted_submit_fact_snapshot_id_missing")
    if not id_present or not trusted_submit_facts_repository_available:
        return
    if facts is None:
        blockers.append("trusted_submit_fact_snapshot_not_found")
        return
    fact_snapshot_id = getattr(facts, "trusted_submit_fact_snapshot_id", None)
    if fact_snapshot_id and fact_snapshot_id != decision.trusted_submit_fact_snapshot_id:
        blockers.append("trusted_submit_fact_snapshot_id_mismatch")
    if not _trusted_submit_facts_ready(facts):
        blockers.append("trusted_submit_fact_snapshot_not_ready")
    if facts.execution_intent_id != decision.execution_intent_id:
        blockers.append("trusted_submit_fact_snapshot_intent_mismatch")
    if facts.runtime_instance_id and facts.runtime_instance_id != (
        decision.runtime_instance_id
    ):
        blockers.append("trusted_submit_fact_snapshot_runtime_mismatch")
    decision_symbol = _decision_symbol(decision)
    if decision_symbol and facts.symbol != decision_symbol:
        blockers.append("trusted_submit_fact_snapshot_symbol_mismatch")
    if not facts.facts_fresh_enough:
        blockers.append("trusted_submit_fact_snapshot_not_fresh_enough")
    if not facts.read_only_sources_only:
        blockers.append("trusted_submit_fact_snapshot_sources_not_read_only")
    if not facts.owner_supplied_allow_facts_rejected:
        blockers.append("trusted_submit_fact_snapshot_owner_allow_not_rejected")
    if not facts.missing_or_stale_facts_block:
        blockers.append("trusted_submit_fact_snapshot_missing_stale_not_blocking")
    _append_common_side_effect_blockers(
        "trusted_submit_fact_snapshot",
        facts,
        blockers,
    )
    warnings.extend(f"trusted_submit_fact_snapshot:{item}" for item in facts.warnings)


def _check_attempt_outcome_policy(
    decision: RuntimeExecutionExchangeSubmitEnablementDecision,
    policy: RuntimeExecutionAttemptOutcomePolicy | None,
    *,
    attempt_outcome_policy_repository_available: bool,
    blockers: list[str],
    warnings: list[str],
) -> None:
    id_present = _present(decision.attempt_outcome_policy_id)
    if not attempt_outcome_policy_repository_available:
        blockers.append("attempt_outcome_policy_repository_unavailable")
    if not id_present:
        blockers.append("attempt_outcome_policy_id_missing")
    if not id_present or not attempt_outcome_policy_repository_available:
        return
    if policy is None:
        blockers.append("attempt_outcome_policy_not_found")
        return
    policy_id = getattr(policy, "policy_id", None)
    if policy_id and policy_id != decision.attempt_outcome_policy_id:
        blockers.append("attempt_outcome_policy_id_mismatch")
    if not _attempt_outcome_policy_ready(policy):
        blockers.append("attempt_outcome_policy_not_ready")
    if policy.outcome_kind != (
        RuntimeExecutionAttemptOutcomeKind.ENTRY_FILLED_PROTECTION_CREATION_FAILED
    ):
        blockers.append("attempt_outcome_policy_kind_mismatch")
    if policy.authorization_id != decision.authorization_id:
        blockers.append("attempt_outcome_policy_authorization_mismatch")
    if policy.execution_intent_id != decision.execution_intent_id:
        blockers.append("attempt_outcome_policy_intent_mismatch")
    if policy.runtime_instance_id != decision.runtime_instance_id:
        blockers.append("attempt_outcome_policy_runtime_mismatch")
    decision_symbol = _decision_symbol(decision)
    if decision_symbol and policy.symbol != decision_symbol:
        blockers.append("attempt_outcome_policy_symbol_mismatch")
    if not policy.protection_creation_failed:
        blockers.append("attempt_outcome_policy_protection_failure_missing")
    if not policy.attempt_should_be_consumed:
        blockers.append("attempt_outcome_policy_attempt_consumption_missing")
    if not policy.reserved_budget_should_remain_held:
        blockers.append("attempt_outcome_policy_budget_hold_missing")
    if not policy.blocks_new_entries_until_resolved:
        blockers.append("attempt_outcome_policy_blocks_entries_missing")
    if not policy.requires_owner_recovery_review:
        blockers.append("attempt_outcome_policy_owner_recovery_review_missing")
    if not policy.requires_reduce_only_recovery_mode:
        blockers.append("attempt_outcome_policy_reduce_only_recovery_missing")
    if not policy.requires_reconciliation_before_retry:
        blockers.append("attempt_outcome_policy_reconciliation_missing")
    _append_common_side_effect_blockers("attempt_outcome_policy", policy, blockers)
    warnings.extend(f"attempt_outcome_policy:{item}" for item in policy.warnings)


def _check_protection_failure_policy(
    decision: RuntimeExecutionExchangeSubmitEnablementDecision,
    policy: RuntimeExecutionProtectionFailurePolicy | None,
    *,
    protection_failure_policy_repository_available: bool,
    blockers: list[str],
    warnings: list[str],
) -> None:
    id_present = _present(decision.protection_creation_failure_policy_id)
    if not protection_failure_policy_repository_available:
        blockers.append("protection_failure_policy_repository_unavailable")
    if not id_present:
        blockers.append("protection_failure_policy_id_missing")
    if not id_present or not protection_failure_policy_repository_available:
        return
    if policy is None:
        blockers.append("protection_failure_policy_not_found")
        return
    policy_id = getattr(policy, "policy_id", None)
    if policy_id and policy_id != decision.protection_creation_failure_policy_id:
        blockers.append("protection_failure_policy_id_mismatch")
    if not _protection_failure_policy_ready(policy):
        blockers.append("protection_failure_policy_not_ready")
    if policy.execution_intent_id != decision.execution_intent_id:
        blockers.append("protection_failure_policy_intent_mismatch")
    if policy.runtime_instance_id != decision.runtime_instance_id:
        blockers.append("protection_failure_policy_runtime_mismatch")
    decision_symbol = _decision_symbol(decision)
    if decision_symbol and policy.symbol != decision_symbol:
        blockers.append("protection_failure_policy_symbol_mismatch")
    if not policy.block_new_entries_until_resolved:
        blockers.append("protection_failure_policy_blocks_entries_missing")
    if not policy.mark_position_unprotected_until_verified:
        blockers.append("protection_failure_policy_unprotected_mark_missing")
    if not policy.require_owner_recovery_review:
        blockers.append("protection_failure_policy_owner_review_missing")
    if not policy.require_reduce_only_recovery_mode:
        blockers.append("protection_failure_policy_reduce_only_missing")
    if not policy.require_reconciliation_before_retry:
        blockers.append("protection_failure_policy_reconciliation_missing")
    if not policy.consume_attempt_on_any_fill:
        blockers.append("protection_failure_policy_attempt_consumption_missing")
    if not policy.hold_or_reconcile_budget_until_position_resolved:
        blockers.append("protection_failure_policy_budget_hold_missing")
    _append_common_side_effect_blockers("protection_failure_policy", policy, blockers)
    warnings.extend(f"protection_failure_policy:{item}" for item in policy.warnings)


def _trusted_submit_facts_ready(
    facts: RuntimeExecutionTrustedSubmitFactsSnapshot | None,
) -> bool:
    return facts is not None and facts.status == (
        RuntimeExecutionTrustedSubmitFactsStatus.READY_FOR_FIRST_REAL_SUBMIT_CONFIRMATION
    )


def _attempt_outcome_policy_ready(
    policy: RuntimeExecutionAttemptOutcomePolicy | None,
) -> bool:
    return policy is not None and policy.status == (
        RuntimeExecutionAttemptOutcomePolicyStatus
        .READY_FOR_ATTEMPT_BUDGET_OUTCOME_ACCOUNTING
    )


def _protection_failure_policy_ready(
    policy: RuntimeExecutionProtectionFailurePolicy | None,
) -> bool:
    return policy is not None and policy.status == (
        RuntimeExecutionProtectionFailurePolicyStatus
        .READY_FOR_FIRST_REAL_SUBMIT_CONFIRMATION
    )


def _append_common_side_effect_blockers(
    prefix: str,
    artifact: Any,
    blockers: list[str],
) -> None:
    if not getattr(artifact, "not_execution_authority", False):
        blockers.append(f"{prefix}_execution_authority")
    if getattr(artifact, "execution_intent_status_changed", False):
        blockers.append(f"{prefix}_changed_intent_status")
    if getattr(artifact, "runtime_state_mutated", False):
        blockers.append(f"{prefix}_mutated_runtime_state")
    if getattr(artifact, "order_created", False):
        blockers.append(f"{prefix}_created_order")
    if getattr(artifact, "order_lifecycle_called", False):
        blockers.append(f"{prefix}_called_order_lifecycle")
    if getattr(artifact, "exchange_called", False):
        blockers.append(f"{prefix}_called_exchange")
    if getattr(artifact, "exchange_order_submitted", False):
        blockers.append(f"{prefix}_submitted_exchange_order")
    if getattr(artifact, "owner_bounded_execution_called", False):
        blockers.append(f"{prefix}_called_owner_bounded_execution")
    if (
        getattr(artifact, "withdrawal_or_transfer_created", False)
        or getattr(artifact, "withdrawal_instruction_created", False)
        or getattr(artifact, "transfer_instruction_created", False)
    ):
        blockers.append(f"{prefix}_created_withdrawal_or_transfer")


def _reject_forbidden_execution_fields(context: str, value: Any) -> None:
    forbidden = {
        "api_key",
        "api_secret",
        "secret",
        "credential",
        "exchange_payload",
        "place_order",
        "submit_order",
        "withdrawal_payload",
        "transfer_payload",
    }
    for key in _walk_keys(value):
        if key.lower() in forbidden:
            raise ValueError(f"{context} contains forbidden execution field: {key}")


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


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _present(value: str | None) -> bool:
    return bool(str(value or "").strip())


def _decision_symbol(
    decision: RuntimeExecutionExchangeSubmitEnablementDecision,
) -> str | None:
    gate = getattr(decision, "exchange_submit_gate", None)
    return getattr(gate, "symbol", None) or getattr(decision, "symbol", None)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
