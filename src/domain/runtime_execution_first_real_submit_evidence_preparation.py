"""Non-executing evidence preparation for first real runtime submit review."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.runtime_execution_first_real_submit_enablement_packet import (
    RuntimeExecutionFirstRealSubmitEnablementPacket,
    RuntimeExecutionFirstRealSubmitEnablementPacketStatus,
)


class RuntimeExecutionFirstRealSubmitEvidencePreparationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionFirstRealSubmitEvidencePreparationStatus(str, Enum):
    BLOCKED_BEFORE_PACKET = "blocked_before_packet"
    PREPARED_PACKET_BLOCKED = "prepared_packet_blocked"
    PREPARED_PACKET_READY_FOR_OWNER_FINAL_REVIEW = (
        "prepared_packet_ready_for_owner_final_review"
    )


class RuntimeExecutionFirstRealSubmitEvidencePreparation(
    RuntimeExecutionFirstRealSubmitEvidencePreparationModel
):
    preparation_id: str = Field(min_length=1, max_length=320)
    authorization_id: str = Field(min_length=1, max_length=220)
    status: RuntimeExecutionFirstRealSubmitEvidencePreparationStatus
    prepared_evidence_ids: dict[str, str] = Field(default_factory=dict)
    available_evidence_ids: dict[str, str] = Field(default_factory=dict)
    skipped_evidence: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    packet: Optional[RuntimeExecutionFirstRealSubmitEnablementPacket] = None
    not_live_action_authorization: Literal[True] = True
    not_exchange_submit_authority: Literal[True] = True
    not_order_lifecycle_authority: Literal[True] = True
    execution_intent_status_changed: Literal[False] = False
    runtime_state_mutated: Literal[False] = False
    order_created: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    exchange_called: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    withdrawal_or_transfer_created: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_preparation(
        self,
    ) -> "RuntimeExecutionFirstRealSubmitEvidencePreparation":
        if (
            self.status
            == (
                RuntimeExecutionFirstRealSubmitEvidencePreparationStatus
                .PREPARED_PACKET_READY_FOR_OWNER_FINAL_REVIEW
            )
            and self.packet is not None
            and self.packet.status
            != (
                RuntimeExecutionFirstRealSubmitEnablementPacketStatus
                .READY_FOR_OWNER_FINAL_REVIEW
            )
        ):
            raise ValueError("ready evidence preparation requires ready packet")
        if (
            self.execution_intent_status_changed
            or self.runtime_state_mutated
            or self.order_created
            or self.order_lifecycle_called
            or self.exchange_called
            or self.exchange_order_submitted
            or self.owner_bounded_execution_called
            or self.withdrawal_or_transfer_created
        ):
            raise ValueError(
                "first-real-submit evidence preparation cannot execute"
            )
        return self


def build_runtime_execution_first_real_submit_evidence_preparation(
    *,
    authorization_id: str,
    packet: RuntimeExecutionFirstRealSubmitEnablementPacket | None,
    prepared_evidence_ids: dict[str, str] | None = None,
    available_evidence_ids: dict[str, str] | None = None,
    skipped_evidence: list[str] | None = None,
    blockers: list[str] | None = None,
    warnings: list[str] | None = None,
    now_ms: int,
) -> RuntimeExecutionFirstRealSubmitEvidencePreparation:
    normalized_blockers = _dedupe(blockers or [])
    if packet is None:
        status = (
            RuntimeExecutionFirstRealSubmitEvidencePreparationStatus
            .BLOCKED_BEFORE_PACKET
        )
    elif packet.status == (
        RuntimeExecutionFirstRealSubmitEnablementPacketStatus
        .READY_FOR_OWNER_FINAL_REVIEW
    ):
        status = (
            RuntimeExecutionFirstRealSubmitEvidencePreparationStatus
            .PREPARED_PACKET_READY_FOR_OWNER_FINAL_REVIEW
        )
    else:
        status = (
            RuntimeExecutionFirstRealSubmitEvidencePreparationStatus
            .PREPARED_PACKET_BLOCKED
        )
    return RuntimeExecutionFirstRealSubmitEvidencePreparation(
        preparation_id=(
            "runtime-first-real-submit-evidence-preparation-"
            f"{authorization_id}"
        ),
        authorization_id=authorization_id,
        status=status,
        prepared_evidence_ids=dict(prepared_evidence_ids or {}),
        available_evidence_ids=dict(available_evidence_ids or {}),
        skipped_evidence=_dedupe(skipped_evidence or []),
        blockers=normalized_blockers,
        warnings=_dedupe(warnings or []),
        packet=packet,
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_first_real_submit_evidence_preparation",
            "machine_evidence_preparation_only": True,
            "does_not_authorize_live_action": True,
            "does_not_create_owner_authorization": True,
            "does_not_create_deployment_readiness": True,
            "does_not_create_exchange_submit_action_authorization": True,
            "does_not_mutate_runtime_attempts": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
        },
    )


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
