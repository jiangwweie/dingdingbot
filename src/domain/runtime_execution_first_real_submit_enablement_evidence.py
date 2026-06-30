"""First-real-submit enablement review evidence.

The evidence is a read-only aggregation for Owner/Codex review. It combines the
submit rehearsal evidence and the strategy-runtime promotion gate result before
any future real submit enablement decision. It does not create orders, mutate
ExecutionIntent state, call OrderLifecycle, call exchange, or authorize live
action by itself.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_submit_rehearsal import (
    RuntimeExecutionSubmitRehearsal,
    RuntimeExecutionSubmitRehearsalStatus,
)
from src.domain.runtime_execution_duplicate_submit_replay_proof import (
    RuntimeExecutionDuplicateSubmitReplayProof,
    RuntimeExecutionDuplicateSubmitReplayProofStatus,
)
from src.domain.runtime_execution_submit_prerequisite_evidence_proof import (
    RuntimeExecutionSubmitPrerequisiteEvidenceProof,
    RuntimeExecutionSubmitPrerequisiteEvidenceProofStatus,
)
from src.domain.strategy_runtime_promotion_gate import (
    FirstRealSubmitConfirmationFacts,
    StrategyRuntimePromotionGateResult,
    StrategyRuntimePromotionGateStatus,
)


class RuntimeExecutionFirstRealSubmitEnablementEvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionFirstRealSubmitEnablementEvidenceStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_OWNER_FINAL_REVIEW = "ready_for_owner_final_review"


class RuntimeExecutionFirstRealSubmitEnablementEvidence(
    RuntimeExecutionFirstRealSubmitEnablementEvidenceModel
):
    evidence_id: str = Field(min_length=1, max_length=620)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    source_type: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    semantic_ids: BrcSemanticIds
    status: RuntimeExecutionFirstRealSubmitEnablementEvidenceStatus
    first_real_submit_confirmations: FirstRealSubmitConfirmationFacts
    promotion_gate_result: Optional[StrategyRuntimePromotionGateResult] = None
    submit_rehearsal: RuntimeExecutionSubmitRehearsal
    duplicate_submit_replay_proof: Optional[
        RuntimeExecutionDuplicateSubmitReplayProof
    ] = None
    prerequisite_evidence_proof: Optional[
        RuntimeExecutionSubmitPrerequisiteEvidenceProof
    ] = None
    promotion_gate_ready: bool = False
    submit_rehearsal_ready: bool = False
    duplicate_submit_replay_proof_ready: bool = False
    prerequisite_evidence_proof_ready: bool = False
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
    def _validate_evidence(
        self,
    ) -> "RuntimeExecutionFirstRealSubmitEnablementEvidence":
        _reject_forbidden_execution_fields(
            "first real submit enablement evidence",
            {"metadata": self.metadata},
        )
        if (
            self.status
            == RuntimeExecutionFirstRealSubmitEnablementEvidenceStatus
            .READY_FOR_OWNER_FINAL_REVIEW
            and self.blockers
        ):
            raise ValueError("ready first-real-submit evidence cannot have blockers")
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
            raise ValueError("first-real-submit evidence cannot perform execution")
        return self


def build_runtime_execution_first_real_submit_enablement_evidence(
    *,
    submit_rehearsal: RuntimeExecutionSubmitRehearsal,
    first_real_submit_confirmations: FirstRealSubmitConfirmationFacts,
    promotion_gate_result: StrategyRuntimePromotionGateResult | None,
    duplicate_submit_replay_proof: (
        RuntimeExecutionDuplicateSubmitReplayProof | None
    ) = None,
    prerequisite_evidence_proof: (
        RuntimeExecutionSubmitPrerequisiteEvidenceProof | None
    ) = None,
    promotion_gate_error: str | None = None,
    additional_blockers: list[str] | None = None,
    additional_warnings: list[str] | None = None,
    now_ms: int,
) -> RuntimeExecutionFirstRealSubmitEnablementEvidence:
    blockers: list[str] = []
    warnings: list[str] = []

    submit_rehearsal_ready = (
        submit_rehearsal.status
        == RuntimeExecutionSubmitRehearsalStatus.READY_FOR_OWNER_LIVE_ACTION_REVIEW
    )
    if not submit_rehearsal_ready:
        blockers.append("submit_rehearsal_not_ready")
    blockers.extend(f"submit_rehearsal:{item}" for item in submit_rehearsal.blockers)
    warnings.extend(f"submit_rehearsal:{item}" for item in submit_rehearsal.warnings)
    _append_forbidden_side_effect_blockers(
        "submit_rehearsal",
        submit_rehearsal,
        blockers,
    )

    duplicate_submit_replay_proof_ready = False
    if duplicate_submit_replay_proof is None:
        blockers.append("duplicate_submit_replay_proof_missing")
    else:
        duplicate_submit_replay_proof_ready = (
            duplicate_submit_replay_proof.status
            == (
                RuntimeExecutionDuplicateSubmitReplayProofStatus
                .READY_FOR_FIRST_REAL_SUBMIT_REPLAY_GUARD
            )
        )
        if not duplicate_submit_replay_proof_ready:
            blockers.append("duplicate_submit_replay_proof_not_ready")
        blockers.extend(
            f"duplicate_submit_replay_proof:{item}"
            for item in duplicate_submit_replay_proof.blockers
        )
        warnings.extend(
            f"duplicate_submit_replay_proof:{item}"
            for item in duplicate_submit_replay_proof.warnings
        )
        _append_forbidden_side_effect_blockers(
            "duplicate_submit_replay_proof",
            duplicate_submit_replay_proof,
            blockers,
        )

    prerequisite_evidence_proof_ready = False
    if prerequisite_evidence_proof is None:
        blockers.append("prerequisite_evidence_proof_missing")
    else:
        prerequisite_evidence_proof_ready = (
            prerequisite_evidence_proof.status
            == (
                RuntimeExecutionSubmitPrerequisiteEvidenceProofStatus
                .READY_FOR_FIRST_REAL_SUBMIT_PREREQUISITE_REVIEW
            )
        )
        if not prerequisite_evidence_proof_ready:
            blockers.append("prerequisite_evidence_proof_not_ready")
        blockers.extend(
            f"prerequisite_evidence_proof:{item}"
            for item in prerequisite_evidence_proof.blockers
        )
        warnings.extend(
            f"prerequisite_evidence_proof:{item}"
            for item in prerequisite_evidence_proof.warnings
        )
        _append_forbidden_side_effect_blockers(
            "prerequisite_evidence_proof",
            prerequisite_evidence_proof,
            blockers,
        )

    promotion_gate_ready = False
    if promotion_gate_result is None:
        blockers.append("promotion_gate_result_missing")
        if promotion_gate_error:
            blockers.append("promotion_gate_preview_unavailable")
            warnings.append(f"promotion_gate_preview_error:{promotion_gate_error}")
    else:
        promotion_gate_ready = (
            promotion_gate_result.status
            == StrategyRuntimePromotionGateStatus.READY_FOR_FIRST_REAL_SUBMIT_GATE_REVIEW
        )
        if not promotion_gate_ready:
            blockers.append("promotion_gate_not_ready")
        blockers.extend(
            f"promotion_gate:{item}" for item in promotion_gate_result.blockers
        )
        warnings.extend(
            f"promotion_gate:{item}" for item in promotion_gate_result.warnings
        )
        _append_forbidden_side_effect_blockers(
            "promotion_gate",
            promotion_gate_result,
            blockers,
        )
    blockers.extend(additional_blockers or [])
    warnings.extend(additional_warnings or [])

    status = (
        RuntimeExecutionFirstRealSubmitEnablementEvidenceStatus
        .READY_FOR_OWNER_FINAL_REVIEW
        if (
            submit_rehearsal_ready
            and duplicate_submit_replay_proof_ready
            and prerequisite_evidence_proof_ready
            and promotion_gate_ready
            and not blockers
        )
        else RuntimeExecutionFirstRealSubmitEnablementEvidenceStatus.BLOCKED
    )
    return RuntimeExecutionFirstRealSubmitEnablementEvidence(
        evidence_id=(
            "runtime-first-real-submit-enablement-evidence-"
            f"{submit_rehearsal.authorization_id}"
        ),
        authorization_id=submit_rehearsal.authorization_id,
        execution_intent_id=submit_rehearsal.execution_intent_id,
        runtime_instance_id=submit_rehearsal.runtime_instance_id,
        source_type=submit_rehearsal.source_type,
        source_id=submit_rehearsal.source_id,
        semantic_ids=submit_rehearsal.semantic_ids,
        status=status,
        first_real_submit_confirmations=first_real_submit_confirmations,
        promotion_gate_result=promotion_gate_result,
        submit_rehearsal=submit_rehearsal,
        duplicate_submit_replay_proof=duplicate_submit_replay_proof,
        prerequisite_evidence_proof=prerequisite_evidence_proof,
        promotion_gate_ready=promotion_gate_ready,
        submit_rehearsal_ready=submit_rehearsal_ready,
        duplicate_submit_replay_proof_ready=duplicate_submit_replay_proof_ready,
        prerequisite_evidence_proof_ready=prerequisite_evidence_proof_ready,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_first_real_submit_enablement_evidence",
            "read_only_aggregation": True,
            "first_real_submit_owner_codex_review_evidence": True,
            "submit_rehearsal_id": submit_rehearsal.rehearsal_id,
            "duplicate_submit_replay_proof_id": (
                duplicate_submit_replay_proof.proof_id
                if duplicate_submit_replay_proof is not None
                else None
            ),
            "prerequisite_evidence_proof_id": (
                prerequisite_evidence_proof.proof_id
                if prerequisite_evidence_proof is not None
                else None
            ),
            "promotion_gate_status": (
                promotion_gate_result.status.value
                if promotion_gate_result is not None
                else None
            ),
            "evidence_checklist_keys": [
                item.key for item in submit_rehearsal.evidence_checklist
            ],
            "does_not_authorize_live_action": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
            "does_not_create_order": True,
        },
    )


def _append_forbidden_side_effect_blockers(
    prefix: str,
    artifact: Any,
    blockers: list[str],
) -> None:
    side_effect_flags = {
        "execution_intent_status_changed": "changed_intent_status",
        "order_created": "created_order",
        "order_lifecycle_called": "called_order_lifecycle",
        "exchange_called": "called_exchange",
        "exchange_order_submitted": "submitted_exchange_order",
        "owner_bounded_execution_called": "called_owner_bounded_execution",
        "runtime_state_mutated": "mutated_runtime_state",
        "withdrawal_or_transfer_created": "created_withdrawal_or_transfer",
    }
    for attr, suffix in side_effect_flags.items():
        if getattr(artifact, attr, False):
            blockers.append(f"{prefix}_{suffix}")


def _reject_forbidden_execution_fields(context: str, value: Any) -> None:
    forbidden = {
        "client_order_id",
        "exchange_order_id",
        "exchange_payload",
        "order_id",
        "place_order",
        "submit_order",
        "transfer_payload",
        "withdrawal_payload",
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


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
