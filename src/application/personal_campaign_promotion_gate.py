"""Strategy Contract promotion gate for Personal Leveraged Campaign.

The gate converts reviewed paper-observation evidence into an eligibility
decision for the next non-real-live review stage. It never grants order,
exchange, account, profile, or real-live authority.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from src.domain.personal_campaign import (
    CampaignDecision,
    PaperObservationPacket,
    PaperObservationReviewStatus,
    TradeIntentAction,
)


PromotionTargetStage = Literal[
    "runtime_read_only",
    "paper",
    "testnet",
    "small_scale_rehearsal",
]


class StrategyContractPromotionDecision(BaseModel):
    """Pure decision record for Strategy Contract promotion review."""

    gate_version: str = "plc_strategy_contract_promotion_gate_v1"
    target_stage: PromotionTargetStage
    allowed_for_next_gate: bool
    authority: Literal["promotion_review_no_order_authority"] = (
        "promotion_review_no_order_authority"
    )
    strategy_contract_id: str
    packet_id: str
    reviewed_by: Optional[str] = None
    reviewed_at_ms: Optional[int] = None
    rejection_reasons: list[str] = Field(default_factory=list)
    required_next_authorization: str = (
        "Owner must separately authorize any runtime, paper, testnet, "
        "small-scale rehearsal, or real-live action."
    )
    prohibited_actions: list[str] = Field(
        default_factory=lambda: [
            "order_placement",
            "order_cancellation",
            "exchange_mutation",
            "real_account_read",
            "runtime_profile_change",
            "real_live_trading",
        ]
    )


def evaluate_strategy_contract_promotion(
    *,
    packet: PaperObservationPacket,
    target_stage: PromotionTargetStage,
) -> StrategyContractPromotionDecision:
    """Evaluate whether a reviewed packet may enter the next review gate."""

    reasons: list[str] = []
    preview = packet.preview
    intent = preview.trade_intent

    if packet.review_status != PaperObservationReviewStatus.REVIEWED_ACCEPT:
        reasons.append("paper_observation_not_reviewed_accept")
    if not packet.reviewed_by or packet.reviewed_at_ms is None:
        reasons.append("owner_review_provenance_missing")
    if not packet.paper_only or packet.authority != "paper_observation_no_order_authority":
        reasons.append("paper_observation_authority_invalid")
    if not packet.no_exchange_side_effect:
        reasons.append("paper_observation_has_exchange_side_effect")
    if preview.rejection_reasons:
        reasons.append("read_only_preview_has_rejections")
    if preview.strategy_contract_status != "frozen":
        reasons.append("strategy_contract_not_frozen")
    if intent.decision != CampaignDecision.ALLOW:
        reasons.append("trade_intent_not_allow")
    if intent.action == TradeIntentAction.NONE:
        reasons.append("trade_intent_has_no_action")
    if not intent.no_exchange_side_effect:
        reasons.append("trade_intent_has_exchange_side_effect")

    return StrategyContractPromotionDecision(
        target_stage=target_stage,
        allowed_for_next_gate=not reasons,
        strategy_contract_id=preview.strategy_contract_id,
        packet_id=packet.packet_id,
        reviewed_by=packet.reviewed_by,
        reviewed_at_ms=packet.reviewed_at_ms,
        rejection_reasons=reasons,
    )
