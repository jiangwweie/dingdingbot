from __future__ import annotations

import json
from pathlib import Path

from src.domain.personal_campaign import (
    CampaignDecision,
    CampaignState,
    FeatureSnapshot,
    HumanArmAction,
    HumanArmDecision,
    ModeAdvice,
    ReadOnlyRuntimeAdapterPreview,
    RiskOrderPlan,
    StrategyContract,
    TradeIntent,
)


EXAMPLE_DIR = Path("docs/schemas/personal_campaign/examples")


def _load_example(filename: str) -> dict:
    with (EXAMPLE_DIR / filename).open(encoding="utf-8") as handle:
        return json.load(handle)


def test_sq02_strategy_contract_example_is_disabled_and_local_only():
    contract = StrategyContract.model_validate(
        _load_example("strategy_contract_sq02_downside_cont_v0.example.json")
    )

    assert contract.strategy_contract_id == "SQ02_DOWNSIDE_CONT_V0"
    assert contract.contract_status == "frozen"
    assert contract.disabled_by_default is True
    assert contract.runtime_label == "LOCAL_SANDBOX_ONLY_DISABLED_BY_DEFAULT"
    assert "lookahead" in contract.forbidden_data
    assert "llm_trade_decision" in contract.forbidden_data
    assert contract.no_lookahead_rule == "closed_or_prior_inputs_only"


def test_sq02_mode_advice_and_human_arm_examples_parse():
    advice = ModeAdvice.model_validate(
        _load_example("mode_advice_sq02_downside_cont_v0.example.json")
    )
    decision = HumanArmDecision.model_validate(
        _load_example("human_arm_decision_arm_sq02.example.json")
    )

    assert advice.strategy_contract_id == decision.strategy_contract_id
    assert advice.llm_role == "explain_audit_suggest_only"
    assert decision.decision == HumanArmAction.ARM
    assert decision.allowed_until_ms > decision.allowed_from_ms


def test_sq02_feature_snapshot_example_is_closed_prior_and_non_llm():
    snapshot = FeatureSnapshot.model_validate(
        _load_example("feature_snapshot_sq02_downside_cont_v0.example.json")
    )

    assert snapshot.strategy_contract_id == "SQ02_DOWNSIDE_CONT_V0"
    assert snapshot.input_scope == "closed_or_prior_inputs_only"
    assert snapshot.conditions == {
        "setup_present": True,
        "setup_invalidated": False,
    }
    assert "lookahead" in snapshot.forbidden_data
    assert "real_account_state" in snapshot.forbidden_data
    assert snapshot.llm_trade_decision_used is False


def test_sq02_trade_intent_example_has_no_exchange_side_effect():
    intent = TradeIntent.model_validate(
        _load_example("trade_intent_allow_sq02.example.json")
    )

    assert intent.decision == CampaignDecision.ALLOW
    assert intent.strategy_contract_id == "SQ02_DOWNSIDE_CONT_V0"
    assert intent.no_exchange_side_effect is True


def test_sq02_risk_order_plan_example_has_required_protection_requirements():
    plan = RiskOrderPlan.model_validate(
        _load_example("risk_order_plan_allow_sq02.example.json")
    )

    assert plan.decision == CampaignDecision.ALLOW
    assert plan.planned_order is not None
    assert plan.rollback_and_cancellation == "local_plan_only_no_exchange_side_effect"
    assert set(plan.protection_requirements) == {
        "protective_stop_required",
        "position_lifecycle_monitor_required",
        "campaign_loss_lock_required",
    }


def test_sq02_campaign_example_preserves_profit_protect_boundary():
    campaign_state = CampaignState.model_validate(
        _load_example("campaign_state_profit_protect_sq02.example.json")
    )

    assert campaign_state.profit_protect_active is True
    assert campaign_state.status == "armed"
    assert "profit-protect:threshold_reached" in campaign_state.invariant_checks
    assert not hasattr(campaign_state, "withdrawal_pending")


def test_sq02_read_only_runtime_adapter_preview_has_no_order_authority():
    preview = ReadOnlyRuntimeAdapterPreview.model_validate(
        _load_example("read_only_runtime_adapter_preview_sq02.example.json")
    )

    assert preview.read_only is True
    assert preview.authority == "read_only_no_order_authority"
    assert preview.trade_intent.no_exchange_side_effect is True
    assert preview.rejection_reasons == []
    assert not hasattr(preview, "order_id")
    assert not hasattr(preview, "exchange_order_id")
