from __future__ import annotations

import json
from pathlib import Path


SCHEMA_DIR = Path("docs/schemas/personal_campaign")


EXPECTED_SCHEMAS = {
    "mode_advice.schema.json": "ModeAdvice",
    "human_arm_decision.schema.json": "HumanArmDecision",
    "feature_snapshot.schema.json": "FeatureSnapshot",
    "strategy_contract.schema.json": "StrategyContract",
    "trade_intent.schema.json": "TradeIntent",
    "risk_order_plan.schema.json": "RiskOrderPlan",
    "execution_receipt.schema.json": "ExecutionReceipt",
    "position_lifecycle_state.schema.json": "PositionLifecycleState",
    "campaign_state.schema.json": "CampaignState",
}


def _load_schema(filename: str) -> dict:
    with (SCHEMA_DIR / filename).open(encoding="utf-8") as handle:
        return json.load(handle)


def test_personal_campaign_schema_files_exist_and_parse():
    for filename, title in EXPECTED_SCHEMAS.items():
        schema = _load_schema(filename)

        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["title"] == title
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert schema["required"]


def test_strategy_contract_schema_enforces_disabled_local_contract_boundary():
    schema = _load_schema("strategy_contract.schema.json")
    properties = schema["properties"]

    assert "disabled_by_default" in schema["required"]
    assert properties["disabled_by_default"]["const"] is True
    assert properties["runtime_label"]["const"] == "LOCAL_SANDBOX_ONLY_DISABLED_BY_DEFAULT"
    assert properties["no_lookahead_rule"]["const"] == "closed_or_prior_inputs_only"
    assert properties["forbidden_data"]["contains"] == {"const": "lookahead"}


def test_trade_intent_schema_keeps_exchange_side_effect_forbidden():
    schema = _load_schema("trade_intent.schema.json")

    assert "no_exchange_side_effect" in schema["required"]
    assert schema["properties"]["no_exchange_side_effect"]["const"] is True


def test_feature_snapshot_schema_enforces_closed_prior_non_llm_boundary():
    schema = _load_schema("feature_snapshot.schema.json")
    properties = schema["properties"]

    assert properties["source"]["const"] == "local_sandbox_closed_or_prior"
    assert properties["input_scope"]["const"] == "closed_or_prior_inputs_only"
    assert properties["llm_trade_decision_used"]["const"] is False
    forbidden_contains = [
        item["contains"]["const"] for item in properties["forbidden_data"]["allOf"]
    ]
    assert forbidden_contains == [
        "lookahead",
        "llm_trade_decision",
        "real_account_state",
        "exchange_api_state",
    ]


def test_risk_order_plan_schema_preserves_owner_caps_and_local_rollback():
    schema = _load_schema("risk_order_plan.schema.json")
    properties = schema["properties"]

    assert "owner_fixed_caps_used" in schema["required"]
    assert properties["rollback_and_cancellation"]["const"] == (
        "local_plan_only_no_exchange_side_effect"
    )
    assert properties["owner_fixed_caps_used"]["required"] == [
        "risk_capital",
        "max_order_loss",
        "max_campaign_loss",
        "max_notional",
        "max_leverage",
        "profit_protect_threshold",
    ]
