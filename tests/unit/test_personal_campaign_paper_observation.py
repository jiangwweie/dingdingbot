from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.application.personal_campaign_paper_observation import (
    build_paper_observation_packet,
    export_paper_observation_packet,
)
from src.application.personal_campaign_runtime_adapter import (
    build_read_only_trade_intent_preview,
)
from src.domain.models import Direction
from src.domain.personal_campaign import (
    FeatureSnapshot,
    PaperObservationPacket,
    PaperObservationReviewStatus,
    StrategyContract,
)


def _preview():
    contract = StrategyContract(
        strategy_contract_id="SQ02_DOWNSIDE_CONT_V0",
        strategy_name="SQ02 downside continuation sandbox skeleton",
        setup_condition_key="setup_present",
        invalidation_condition_key="setup_invalidated",
        direction=Direction.SHORT,
        required_feature_snapshot=["setup_present", "setup_invalidated"],
    )
    snapshot = FeatureSnapshot(
        snapshot_id="snapshot-paper-001",
        strategy_contract_id="SQ02_DOWNSIDE_CONT_V0",
        feature_timestamp_ms=1000,
        conditions={"setup_present": True, "setup_invalidated": False},
    )
    return build_read_only_trade_intent_preview(
        contract=contract,
        feature_snapshot=snapshot,
        runtime_clock_ms=2000,
    )


def test_build_paper_observation_packet_keeps_no_order_authority():
    packet = build_paper_observation_packet(
        preview=_preview(),
        created_at_ms=3000,
        operator_notes=["observe_only"],
    )

    assert packet.paper_only is True
    assert packet.authority == "paper_observation_no_order_authority"
    assert packet.review_status == PaperObservationReviewStatus.PENDING_REVIEW
    assert packet.operator_notes == ["observe_only"]
    assert "order_placement" in packet.prohibited_actions
    assert "exchange_mutation" in packet.prohibited_actions
    assert packet.no_exchange_side_effect is True
    assert not hasattr(packet, "order_id")
    assert not hasattr(packet, "exchange_order_id")


def test_reviewed_paper_packet_requires_review_provenance():
    with pytest.raises(ValidationError, match="reviewed packets require"):
        build_paper_observation_packet(
            preview=_preview(),
            created_at_ms=3000,
            review_status=PaperObservationReviewStatus.REVIEWED_ACCEPT,
        )

    packet = build_paper_observation_packet(
        preview=_preview(),
        created_at_ms=3000,
        review_status=PaperObservationReviewStatus.REVIEWED_ACCEPT,
        reviewed_by="owner",
        reviewed_at_ms=4000,
    )

    assert packet.reviewed_by == "owner"
    assert packet.reviewed_at_ms == 4000


def test_export_paper_observation_packet_returns_json_ready_dict():
    packet = build_paper_observation_packet(
        preview=_preview(),
        created_at_ms=3000,
        operator_notes=["operator_note_safe"],
    )

    exported = export_paper_observation_packet(packet)

    assert exported["packet_version"] == "plc_paper_observation_packet_v1"
    assert exported["preview"]["read_only"] is True
    assert exported["preview"]["trade_intent"]["no_exchange_side_effect"] is True
    assert exported["review_status"] == "pending_review"

    reparsed = PaperObservationPacket.model_validate(exported)
    assert reparsed.packet_id == packet.packet_id


def test_paper_observation_code_does_not_import_io_frameworks():
    forbidden = {"ccxt", "aiohttp", "requests", "fastapi", "yaml", "sqlalchemy"}
    for path in [
        Path("src/domain/personal_campaign.py"),
        Path("src/application/personal_campaign_paper_observation.py"),
    ]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        assert imports.isdisjoint(forbidden)
