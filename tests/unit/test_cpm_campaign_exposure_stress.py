from __future__ import annotations

from decimal import Decimal

from src.domain.cpm_campaign_exposure_stress import (
    DAY_MS,
    CPMCampaignStressMode,
    CPMCampaignStressObservation,
    build_non_overlapping_campaign_windows,
    summarize_campaign_exposure_stress,
)
from src.domain.cpm_campaign_replay import CPMCampaignReplayConfig, CPMCampaignRiskModel


def _config() -> CPMCampaignReplayConfig:
    return CPMCampaignReplayConfig(
        config_id="aggressive_fixed_fraction_5x",
        risk_model=CPMCampaignRiskModel.FIXED_FRACTIONAL,
        risk_per_trade_pct=Decimal("20"),
        target_multiple=Decimal("5"),
    )


def test_exposure_multiplier_sensitivity_and_final_multiple() -> None:
    observations = [
        CPMCampaignStressObservation(timestamp_ms=1, gross_return_pct=Decimal("5"), adverse_proxy_pct=Decimal("1")),
        CPMCampaignStressObservation(timestamp_ms=2, gross_return_pct=Decimal("-2"), adverse_proxy_pct=Decimal("2")),
        CPMCampaignStressObservation(timestamp_ms=3, gross_return_pct=Decimal("8"), adverse_proxy_pct=Decimal("1")),
    ]

    low = summarize_campaign_exposure_stress(
        observations=observations,
        config=_config(),
        exposure_multiplier=Decimal("1"),
        cost_drag_pct=Decimal("0"),
        mode=CPMCampaignStressMode.SINGLE_CHRONOLOGICAL_CAMPAIGN,
    )
    high = summarize_campaign_exposure_stress(
        observations=observations,
        config=_config(),
        exposure_multiplier=Decimal("3"),
        cost_drag_pct=Decimal("0"),
        mode=CPMCampaignStressMode.SINGLE_CHRONOLOGICAL_CAMPAIGN,
    )

    assert low.final_multiple is not None
    assert high.final_multiple is not None
    assert high.final_multiple > low.final_multiple
    assert high.max_drawdown_pct > low.max_drawdown_pct


def test_non_overlapping_campaign_window_construction() -> None:
    observations = [
        CPMCampaignStressObservation(timestamp_ms=0, gross_return_pct=Decimal("1")),
        CPMCampaignStressObservation(timestamp_ms=10 * DAY_MS, gross_return_pct=Decimal("1")),
        CPMCampaignStressObservation(timestamp_ms=35 * DAY_MS, gross_return_pct=Decimal("1")),
        CPMCampaignStressObservation(timestamp_ms=65 * DAY_MS, gross_return_pct=Decimal("1")),
    ]

    windows = build_non_overlapping_campaign_windows(observations, window_days=30)

    assert [len(window) for window in windows] == [2, 1, 1]


def test_intrabar_mae_stress_exceeds_close_drawdown_when_adverse_path_is_larger() -> None:
    observations = [
        CPMCampaignStressObservation(timestamp_ms=1, gross_return_pct=Decimal("2"), adverse_proxy_pct=Decimal("10")),
        CPMCampaignStressObservation(timestamp_ms=2, gross_return_pct=Decimal("2"), adverse_proxy_pct=Decimal("1")),
    ]

    summary = summarize_campaign_exposure_stress(
        observations=observations,
        config=_config(),
        exposure_multiplier=Decimal("2"),
        cost_drag_pct=Decimal("0"),
        mode=CPMCampaignStressMode.SINGLE_CHRONOLOGICAL_CAMPAIGN,
    )

    assert summary.intrabar_stressed_max_drawdown_pct is not None
    assert summary.intrabar_stressed_max_drawdown_pct > summary.max_drawdown_pct


def test_liquidation_proxy_threshold_counting() -> None:
    observations = [
        CPMCampaignStressObservation(timestamp_ms=1, gross_return_pct=Decimal("1"), adverse_proxy_pct=Decimal("1")),
        CPMCampaignStressObservation(timestamp_ms=2, gross_return_pct=Decimal("1"), adverse_proxy_pct=Decimal("3")),
        CPMCampaignStressObservation(timestamp_ms=3, gross_return_pct=Decimal("1"), adverse_proxy_pct=Decimal("6")),
    ]

    summary = summarize_campaign_exposure_stress(
        observations=observations,
        config=_config(),
        exposure_multiplier=Decimal("2"),
        cost_drag_pct=Decimal("0"),
        mode=CPMCampaignStressMode.SINGLE_CHRONOLOGICAL_CAMPAIGN,
    )

    assert summary.liquidation_proxy_breach_counts["3%"] == 2
    assert summary.liquidation_proxy_breach_counts["5%"] == 2
    assert summary.liquidation_proxy_breach_counts["10%"] == 1


def test_cost_stress_reduces_campaign_multiple() -> None:
    observations = [
        CPMCampaignStressObservation(timestamp_ms=1, gross_return_pct=Decimal("2"), adverse_proxy_pct=Decimal("1")),
        CPMCampaignStressObservation(timestamp_ms=2, gross_return_pct=Decimal("2"), adverse_proxy_pct=Decimal("1")),
    ]

    frozen = summarize_campaign_exposure_stress(
        observations=observations,
        config=_config(),
        exposure_multiplier=Decimal("3"),
        cost_drag_pct=Decimal("0.28"),
        mode=CPMCampaignStressMode.SINGLE_CHRONOLOGICAL_CAMPAIGN,
    )
    stressed = summarize_campaign_exposure_stress(
        observations=observations,
        config=_config(),
        exposure_multiplier=Decimal("3"),
        cost_drag_pct=Decimal("0.60"),
        mode=CPMCampaignStressMode.SINGLE_CHRONOLOGICAL_CAMPAIGN,
    )

    assert frozen.final_multiple is not None
    assert stressed.final_multiple is not None
    assert frozen.final_multiple > stressed.final_multiple


def test_stress_review_exposes_no_execution_order_or_trial_intent_methods() -> None:
    summary = summarize_campaign_exposure_stress(
        observations=[
            CPMCampaignStressObservation(timestamp_ms=1, gross_return_pct=Decimal("1"), adverse_proxy_pct=Decimal("1"))
        ],
        config=_config(),
        exposure_multiplier=Decimal("1"),
        cost_drag_pct=Decimal("0.28"),
        mode=CPMCampaignStressMode.SINGLE_CHRONOLOGICAL_CAMPAIGN,
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
