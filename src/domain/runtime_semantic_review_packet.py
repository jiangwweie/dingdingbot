"""Runtime semantic review packets for closed-trade analysis.

This module is pure review logic. It converts a live lifecycle review record
into an auditable, non-executing packet and only evaluates explicit trade-path
facts supplied in review metadata.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.domain.live_lifecycle_review import BrcLiveLifecycleReviewRecord
from src.domain.right_tail_review import (
    RightTailTradePathFacts,
    RightTailTradeReviewResult,
    review_right_tail_trade_path,
)


REQUIRED_RUNTIME_SEMANTIC_IDS: tuple[str, ...] = (
    "strategy_family_id",
    "strategy_family_version_id",
    "runtime_instance_id",
    "trial_binding_id",
    "signal_evaluation_id",
    "order_candidate_id",
    "execution_intent_id",
)


class RuntimeSemanticReviewPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    packet_id: str
    source_policy: Literal[
        "live_lifecycle_review_explicit_metadata_only"
    ] = "live_lifecycle_review_explicit_metadata_only"
    source_review_id: str
    authorization_id: str
    carrier_id: str
    strategy_family_id: Optional[str] = None
    strategy_family_version_id: Optional[str] = None
    runtime_instance_id: Optional[str] = None
    trial_binding_id: Optional[str] = None
    signal_evaluation_id: Optional[str] = None
    order_candidate_id: Optional[str] = None
    execution_intent_id: Optional[str] = None
    symbol: str
    side: Literal["long", "short"]
    lifecycle_status: str
    review_status: str
    final_gate_result: Optional[str] = None
    protection_status: Optional[str] = None
    semantic_trace_complete: bool
    missing_semantic_ids: list[str] = Field(default_factory=list)
    right_tail_review_status: Literal["reviewed", "review_inputs_required"]
    right_tail_review: Optional[RightTailTradeReviewResult] = None
    required_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    not_order: Literal[True] = True
    not_execution_intent: Literal[True] = True
    not_trading_authority: Literal[True] = True
    places_order: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    calls_exchange: Literal[False] = False
    mutates_exchange: Literal[False] = False
    mutates_runtime_budget: Literal[False] = False
    mutates_strategy_pnl: Literal[False] = False
    creates_withdrawal_instruction: Literal[False] = False


class RuntimeSemanticReviewPacketSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["empty", "reviewed", "review_inputs_required"]
    source_policy: Literal[
        "live_lifecycle_review_explicit_metadata_only"
    ] = "live_lifecycle_review_explicit_metadata_only"
    packet_count: int = 0
    reviewed_packet_count: int = 0
    missing_input_packet_count: int = 0
    semantic_trace_complete_count: int = 0
    packets: list[RuntimeSemanticReviewPacket] = Field(default_factory=list)
    required_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    no_action_guarantee: dict[str, bool] = Field(
        default_factory=lambda: {
            "places_order": False,
            "creates_execution_intent": False,
            "calls_exchange": False,
            "mutates_exchange": False,
            "mutates_runtime_budget": False,
            "mutates_strategy_pnl": False,
            "creates_withdrawal_instruction": False,
        }
    )


def build_runtime_semantic_review_packet(
    record: BrcLiveLifecycleReviewRecord,
) -> RuntimeSemanticReviewPacket:
    missing_semantic_ids = [
        key for key in REQUIRED_RUNTIME_SEMANTIC_IDS if not getattr(record, key)
    ]
    warnings: list[str] = []
    if (
        record.lifecycle_status != "closed_reviewed"
        or record.review_status != "closed_reviewed"
    ):
        warnings.append("runtime_semantic_packet_source_not_closed_reviewed")
    if missing_semantic_ids:
        warnings.append("runtime_semantic_trace_incomplete")

    metadata = record.metadata
    raw_facts = metadata.get("right_tail_trade_path")
    if raw_facts is None:
        return _packet(
            record=record,
            missing_semantic_ids=missing_semantic_ids,
            right_tail_review_status="review_inputs_required",
            required_inputs=["live_lifecycle_review.metadata.right_tail_trade_path"],
            warnings=warnings + ["right_tail_trade_path_missing"],
        )
    if not isinstance(raw_facts, dict):
        return _packet(
            record=record,
            missing_semantic_ids=missing_semantic_ids,
            right_tail_review_status="review_inputs_required",
            required_inputs=["live_lifecycle_review.metadata.right_tail_trade_path"],
            warnings=warnings + ["right_tail_trade_path_not_object"],
        )

    fact_payload = dict(raw_facts)
    _fill_missing_fact_context(fact_payload, record)
    conflict_warnings = _fact_context_conflicts(raw_facts, record)
    try:
        facts = RightTailTradePathFacts.model_validate(fact_payload)
    except Exception as exc:
        return _packet(
            record=record,
            missing_semantic_ids=missing_semantic_ids,
            right_tail_review_status="review_inputs_required",
            required_inputs=["live_lifecycle_review.metadata.right_tail_trade_path"],
            warnings=warnings
            + conflict_warnings
            + ["right_tail_trade_path_invalid", str(exc)],
        )

    result = review_right_tail_trade_path(facts)
    return _packet(
        record=record,
        missing_semantic_ids=missing_semantic_ids,
        right_tail_review_status=result.status,
        right_tail_review=result,
        required_inputs=result.required_inputs,
        warnings=warnings + conflict_warnings + result.warnings,
    )


def summarize_runtime_semantic_review_packets(
    records: list[BrcLiveLifecycleReviewRecord],
) -> RuntimeSemanticReviewPacketSummary:
    packets = [build_runtime_semantic_review_packet(record) for record in records]
    if not packets:
        return RuntimeSemanticReviewPacketSummary(
            status="empty",
            required_inputs=["live_lifecycle_review"],
            warnings=["no_live_lifecycle_review_records"],
        )

    missing = [
        packet for packet in packets
        if packet.right_tail_review_status != "reviewed"
    ]
    required_inputs = sorted(
        {
            item
            for packet in packets
            for item in packet.required_inputs
        }
    )
    warnings = sorted(
        {
            warning
            for packet in packets
            for warning in packet.warnings
        }
    )
    return RuntimeSemanticReviewPacketSummary(
        status="review_inputs_required" if missing else "reviewed",
        packet_count=len(packets),
        reviewed_packet_count=len(packets) - len(missing),
        missing_input_packet_count=len(missing),
        semantic_trace_complete_count=sum(
            1 for packet in packets if packet.semantic_trace_complete
        ),
        packets=packets,
        required_inputs=required_inputs,
        warnings=warnings,
    )


def _packet(
    *,
    record: BrcLiveLifecycleReviewRecord,
    missing_semantic_ids: list[str],
    right_tail_review_status: Literal["reviewed", "review_inputs_required"],
    right_tail_review: Optional[RightTailTradeReviewResult] = None,
    required_inputs: list[str],
    warnings: list[str],
) -> RuntimeSemanticReviewPacket:
    return RuntimeSemanticReviewPacket(
        packet_id=f"runtime-semantic-review-packet:{record.review_id}",
        source_review_id=record.review_id,
        authorization_id=record.authorization_id,
        carrier_id=record.carrier_id,
        strategy_family_id=record.strategy_family_id,
        strategy_family_version_id=record.strategy_family_version_id,
        runtime_instance_id=record.runtime_instance_id,
        trial_binding_id=record.trial_binding_id,
        signal_evaluation_id=record.signal_evaluation_id,
        order_candidate_id=record.order_candidate_id,
        execution_intent_id=record.execution_intent_id,
        symbol=record.symbol,
        side=record.side,
        lifecycle_status=record.lifecycle_status,
        review_status=record.review_status,
        final_gate_result=record.final_gate_result,
        protection_status=record.protection_status,
        semantic_trace_complete=not missing_semantic_ids,
        missing_semantic_ids=missing_semantic_ids,
        right_tail_review_status=right_tail_review_status,
        right_tail_review=right_tail_review,
        required_inputs=required_inputs,
        warnings=warnings,
        evidence_refs=record.evidence_refs,
    )


def _fill_missing_fact_context(
    payload: dict[str, Any],
    record: BrcLiveLifecycleReviewRecord,
) -> None:
    defaults: dict[str, Any] = {
        "trade_id": record.review_id,
        "source_review_id": record.review_id,
        "symbol": record.symbol,
        "side": record.side,
        "strategy_family_id": record.strategy_family_id,
        "strategy_family_version_id": record.strategy_family_version_id,
        "runtime_instance_id": record.runtime_instance_id,
        "order_candidate_id": record.order_candidate_id,
    }
    for key, value in defaults.items():
        if key not in payload or payload[key] in (None, ""):
            payload[key] = value


def _fact_context_conflicts(
    raw_facts: dict[str, Any],
    record: BrcLiveLifecycleReviewRecord,
) -> list[str]:
    warnings: list[str] = []
    for key in [
        "symbol",
        "side",
        "strategy_family_id",
        "strategy_family_version_id",
        "runtime_instance_id",
        "order_candidate_id",
    ]:
        record_value = getattr(record, key)
        raw_value = raw_facts.get(key)
        if raw_value not in (None, "") and record_value not in (None, ""):
            if str(raw_value) != str(record_value):
                warnings.append(
                    f"right_tail_trade_path_{key}_conflicts_lifecycle_record"
                )
    return warnings
