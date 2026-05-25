from __future__ import annotations

import ast
from pathlib import Path

from src.application.personal_campaign_runtime_adapter import (
    build_read_only_trade_intent_preview,
)
from src.domain.models import Direction
from src.domain.personal_campaign import (
    CampaignDecision,
    FeatureSnapshot,
    StrategyContract,
    TradeIntentAction,
)


def _contract(**overrides) -> StrategyContract:
    payload = {
        "strategy_contract_id": "SQ02_DOWNSIDE_CONT_V0",
        "strategy_name": "SQ02 downside continuation sandbox skeleton",
        "setup_condition_key": "setup_present",
        "invalidation_condition_key": "setup_invalidated",
        "direction": Direction.SHORT,
        "required_feature_snapshot": ["setup_present", "setup_invalidated"],
    }
    payload.update(overrides)
    return StrategyContract(**payload)


def _feature_snapshot(**overrides) -> FeatureSnapshot:
    payload = {
        "snapshot_id": "snapshot-runtime-preview",
        "strategy_contract_id": "SQ02_DOWNSIDE_CONT_V0",
        "feature_timestamp_ms": 1000,
        "conditions": {
            "setup_present": True,
            "setup_invalidated": False,
        },
    }
    payload.update(overrides)
    return FeatureSnapshot(**payload)


def test_read_only_adapter_builds_allowed_trade_intent_preview():
    preview = build_read_only_trade_intent_preview(
        contract=_contract(),
        feature_snapshot=_feature_snapshot(),
        runtime_clock_ms=2000,
    )

    assert preview.read_only is True
    assert preview.authority == "read_only_no_order_authority"
    assert preview.no_exchange_side_effect is True
    assert preview.rejection_reasons == []
    assert preview.trade_intent.decision == CampaignDecision.ALLOW
    assert preview.trade_intent.action == TradeIntentAction.ENTER
    assert preview.trade_intent.no_exchange_side_effect is True
    assert not hasattr(preview, "order_id")
    assert not hasattr(preview, "exchange_order_id")


def test_read_only_adapter_rejects_future_snapshot():
    preview = build_read_only_trade_intent_preview(
        contract=_contract(),
        feature_snapshot=_feature_snapshot(feature_timestamp_ms=3000),
        runtime_clock_ms=2000,
    )

    assert preview.trade_intent.decision == CampaignDecision.REJECT
    assert preview.rejection_reasons == [
        "feature_snapshot_not_closed_or_prior_to_runtime_clock"
    ]


def test_read_only_adapter_rejects_non_frozen_contract():
    preview = build_read_only_trade_intent_preview(
        contract=_contract(contract_status="draft"),
        feature_snapshot=_feature_snapshot(),
        runtime_clock_ms=2000,
    )

    assert preview.trade_intent.decision == CampaignDecision.REJECT
    assert preview.rejection_reasons == ["strategy_contract_not_frozen"]


def test_read_only_adapter_rejects_contract_snapshot_mismatch():
    preview = build_read_only_trade_intent_preview(
        contract=_contract(),
        feature_snapshot=_feature_snapshot(strategy_contract_id="OTHER"),
        runtime_clock_ms=2000,
    )

    assert preview.trade_intent.decision == CampaignDecision.REJECT
    assert preview.rejection_reasons == ["feature_snapshot_strategy_mismatch"]


def test_read_only_adapter_and_domain_do_not_import_io_frameworks():
    forbidden = {"ccxt", "aiohttp", "requests", "fastapi", "yaml"}
    for path in [
        Path("src/domain/personal_campaign.py"),
        Path("src/application/personal_campaign_runtime_adapter.py"),
    ]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        assert imports.isdisjoint(forbidden)
