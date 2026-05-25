from __future__ import annotations

import ast
from pathlib import Path

from src.application.personal_campaign_paper_observation import (
    build_paper_observation_packet,
)
from src.application.personal_campaign_promotion_gate import (
    evaluate_strategy_contract_promotion,
)
from src.application.personal_campaign_runtime_adapter import (
    build_read_only_trade_intent_preview,
)
from src.domain.models import Direction
from src.domain.personal_campaign import (
    FeatureSnapshot,
    PaperObservationReviewStatus,
    StrategyContract,
)


def _preview(*, setup_present: bool = True):
    contract = StrategyContract(
        strategy_contract_id="SQ02_DOWNSIDE_CONT_V0",
        strategy_name="SQ02 downside continuation sandbox skeleton",
        setup_condition_key="setup_present",
        invalidation_condition_key="setup_invalidated",
        direction=Direction.SHORT,
        required_feature_snapshot=["setup_present", "setup_invalidated"],
    )
    snapshot = FeatureSnapshot(
        snapshot_id="snapshot-promotion-001",
        strategy_contract_id="SQ02_DOWNSIDE_CONT_V0",
        feature_timestamp_ms=1000,
        conditions={"setup_present": setup_present, "setup_invalidated": False},
    )
    return build_read_only_trade_intent_preview(
        contract=contract,
        feature_snapshot=snapshot,
        runtime_clock_ms=2000,
    )


def test_reviewed_accept_packet_can_enter_next_non_order_gate():
    packet = build_paper_observation_packet(
        preview=_preview(),
        created_at_ms=3000,
        review_status=PaperObservationReviewStatus.REVIEWED_ACCEPT,
        reviewed_by="owner",
        reviewed_at_ms=4000,
    )

    decision = evaluate_strategy_contract_promotion(
        packet=packet,
        target_stage="testnet",
    )

    assert decision.allowed_for_next_gate is True
    assert decision.authority == "promotion_review_no_order_authority"
    assert decision.rejection_reasons == []
    assert "real_live_trading" in decision.prohibited_actions
    assert decision.required_next_authorization.startswith("Owner must separately authorize")


def test_pending_review_packet_cannot_be_promoted():
    packet = build_paper_observation_packet(
        preview=_preview(),
        created_at_ms=3000,
    )

    decision = evaluate_strategy_contract_promotion(
        packet=packet,
        target_stage="small_scale_rehearsal",
    )

    assert decision.allowed_for_next_gate is False
    assert "paper_observation_not_reviewed_accept" in decision.rejection_reasons
    assert "owner_review_provenance_missing" in decision.rejection_reasons


def test_rejected_preview_cannot_be_promoted_even_after_owner_review():
    packet = build_paper_observation_packet(
        preview=_preview(setup_present=False),
        created_at_ms=3000,
        review_status=PaperObservationReviewStatus.REVIEWED_ACCEPT,
        reviewed_by="owner",
        reviewed_at_ms=4000,
    )

    decision = evaluate_strategy_contract_promotion(
        packet=packet,
        target_stage="testnet",
    )

    assert decision.allowed_for_next_gate is False
    assert "trade_intent_not_allow" in decision.rejection_reasons


def test_promotion_gate_does_not_import_io_frameworks():
    forbidden = {"ccxt", "aiohttp", "requests", "fastapi", "yaml", "sqlalchemy"}
    tree = ast.parse(
        Path("src/application/personal_campaign_promotion_gate.py").read_text(
            encoding="utf-8"
        )
    )
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert imports.isdisjoint(forbidden)
