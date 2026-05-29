from __future__ import annotations

from decimal import Decimal

from src.domain.cpm_campaign_replay import (
    CPMCampaignReplayConfig,
    CPMCampaignRiskModel,
    CPMCampaignStatus,
    replay_and_summarize_campaigns,
    replay_campaigns,
)


def test_campaign_transitions_to_ruined_without_top_up() -> None:
    config = CPMCampaignReplayConfig(
        config_id="unit_ruin",
        risk_model=CPMCampaignRiskModel.FIXED_UNIT,
        fixed_risk_unit=Decimal("100"),
        target_multiple=Decimal("2"),
    )

    runs = replay_campaigns(
        net_returns_pct=[Decimal("-120")],
        config=config,
        exposure_multiplier=Decimal("1"),
    )

    assert len(runs) == 1
    assert runs[0].status == CPMCampaignStatus.RUINED
    assert runs[0].final_equity == Decimal("0")
    assert runs[0].retained_capital == Decimal("0")


def test_campaign_transitions_to_target_hit() -> None:
    config = CPMCampaignReplayConfig(
        config_id="unit_target",
        risk_model=CPMCampaignRiskModel.FIXED_UNIT,
        fixed_risk_unit=Decimal("100"),
        target_multiple=Decimal("2"),
    )

    runs = replay_campaigns(
        net_returns_pct=[Decimal("120")],
        config=config,
        exposure_multiplier=Decimal("1"),
    )

    assert runs[0].status == CPMCampaignStatus.TARGET_HIT
    assert runs[0].target_hit_2x is True
    assert runs[0].final_multiple >= Decimal("2")


def test_withdrawal_rule_withdraws_initial_capital_and_continues_profit_capital() -> None:
    config = CPMCampaignReplayConfig(
        config_id="withdrawal",
        risk_model=CPMCampaignRiskModel.FIXED_UNIT,
        fixed_risk_unit=Decimal("100"),
        target_multiple=Decimal("5"),
        withdraw_initial_at_2x=True,
    )

    runs = replay_campaigns(
        net_returns_pct=[Decimal("120"), Decimal("10")],
        config=config,
        exposure_multiplier=Decimal("1"),
    )

    assert runs[0].retained_capital == Decimal("100")
    assert runs[0].final_equity > Decimal("100")
    assert runs[0].final_multiple > Decimal("2")


def test_deterministic_replay_and_exposure_multiplier_sensitivity() -> None:
    config = CPMCampaignReplayConfig(
        config_id="fractional",
        risk_model=CPMCampaignRiskModel.FIXED_FRACTIONAL,
        risk_per_trade_pct=Decimal("20"),
        target_multiple=Decimal("2"),
    )
    returns = [Decimal("10"), Decimal("-5"), Decimal("20")]

    low = replay_and_summarize_campaigns(
        net_returns_pct=returns,
        config=config,
        exposure_multiplier=Decimal("1"),
    )
    high = replay_and_summarize_campaigns(
        net_returns_pct=returns,
        config=config,
        exposure_multiplier=Decimal("3"),
    )

    assert low.campaigns_simulated == high.campaigns_simulated
    assert high.mean_final_multiple is not None
    assert low.mean_final_multiple is not None
    assert high.mean_final_multiple > low.mean_final_multiple


def test_fixed_unit_risk_caps_risk_unit_to_remaining_equity() -> None:
    config = CPMCampaignReplayConfig(
        config_id="fixed_unit_cap",
        risk_model=CPMCampaignRiskModel.FIXED_UNIT,
        fixed_risk_unit=Decimal("10"),
        target_multiple=Decimal("2"),
    )

    runs = replay_campaigns(
        net_returns_pct=[Decimal("-1000")],
        config=config,
        exposure_multiplier=Decimal("1"),
    )

    assert runs[0].final_equity == Decimal("0")
    assert runs[0].status == CPMCampaignStatus.RUINED


def test_campaign_replay_exposes_no_execution_order_or_trial_intent_methods() -> None:
    config = CPMCampaignReplayConfig(
        config_id="boundary",
        risk_model=CPMCampaignRiskModel.FIXED_FRACTIONAL,
        risk_per_trade_pct=Decimal("10"),
        target_multiple=Decimal("2"),
    )
    summary = replay_and_summarize_campaigns(
        net_returns_pct=[Decimal("1"), Decimal("-1")],
        config=config,
        exposure_multiplier=Decimal("1"),
    )
    payload = summary.model_dump(mode="python")

    for forbidden in [
        "quantity",
        "notional",
        "leverage",
        "order_type",
        "client_order_id",
        "order_id",
        "venue",
        "reduce_only",
        "router_target",
        "cancel_instruction",
        "close_instruction",
        "flatten_instruction",
    ]:
        assert forbidden not in payload

    assert not hasattr(summary, "create_order")
    assert not hasattr(summary, "create_execution_intent")
    assert not hasattr(summary, "write_trial_trade_intent")
