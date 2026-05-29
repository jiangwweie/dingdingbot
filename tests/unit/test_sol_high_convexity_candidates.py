from __future__ import annotations

from decimal import Decimal

from src.domain.cpm_campaign_exposure_stress import CPMCampaignStressMode
from src.domain.cpm_campaign_replay import CPMCampaignReplayConfig, CPMCampaignRiskModel
from src.domain.sol_high_convexity_candidates import (
    BTCRegime,
    SOLCandidateId,
    SOLCandidateVerdict,
    SOLCandidateSignal,
    SOLForwardOutcome,
    SOLResearchCandle,
    SOLResearchSide,
    apply_btc_regime_filter,
    btc_regime_by_timestamp,
    choose_candidate_verdict,
    compute_forward_outcomes,
    detect_donchian_breakouts,
    detect_volatility_expansion_breakouts,
    random_same_frequency_baseline,
    summarize_campaign_candidate,
    summarize_forward_outcomes,
)


def _candle(index: int, close: str, high: str | None = None, low: str | None = None) -> SOLResearchCandle:
    close_value = Decimal(close)
    return SOLResearchCandle(
        timestamp_ms=index * 3_600_000,
        open=close_value,
        high=Decimal(high) if high is not None else close_value + Decimal("1"),
        low=Decimal(low) if low is not None else close_value - Decimal("1"),
        close=close_value,
        volume=Decimal("100"),
    )


def test_volatility_expansion_signal_detection_on_sample_candles() -> None:
    candles = []
    for index in range(48):
        candles.append(_candle(index, "100", high="120", low="80"))
    for index in range(48, 60):
        candles.append(_candle(index, "100", high="102", low="98"))
    candles.append(_candle(60, "104", high="105", low="99"))

    signals = detect_volatility_expansion_breakouts(
        candles,
        compression_bars=12,
        prior_bars=48,
        compression_threshold=Decimal("0.20"),
    )

    assert signals
    assert signals[-1].side == SOLResearchSide.LONG
    assert signals[-1].candidate_id == SOLCandidateId.VOL_EXPANSION_BREAKOUT


def test_donchian_breakout_signal_detection_on_sample_candles() -> None:
    candles = [_candle(index, "100", high="101", low="99") for index in range(20)]
    candles.append(_candle(20, "103", high="104", low="100"))

    signals = detect_donchian_breakouts(
        candles,
        lookback_bars=20,
        candidate_id=SOLCandidateId.DONCHIAN_20_BREAKOUT,
    )

    assert len(signals) == 1
    assert signals[0].side == SOLResearchSide.LONG


def test_btc_regime_filter_segmentation() -> None:
    btc = [_candle(index, str(100 + index)) for index in range(25)]
    regimes = btc_regime_by_timestamp(btc, sma_bars=20)
    signal = detect_donchian_breakouts(
        [_candle(index, "100", high="101", low="99") for index in range(20)]
        + [_candle(20, "103", high="104", low="100")],
        lookback_bars=20,
        candidate_id=SOLCandidateId.DONCHIAN_20_BREAKOUT,
    )[0]

    filtered = apply_btc_regime_filter(
        [signal],
        regimes,
        filtered_candidate_id=SOLCandidateId.DONCHIAN_20_BTC_FILTERED,
    )

    assert filtered
    assert filtered[0].candidate_id == SOLCandidateId.DONCHIAN_20_BTC_FILTERED
    assert regimes[max(regimes)] in {BTCRegime.UP, BTCRegime.NEUTRAL}


def test_cost_adjusted_replay_calculation() -> None:
    candles = [_candle(index, "100", high="101", low="99") for index in range(20)]
    candles.extend([_candle(20, "103", high="104", low="100")])
    candles.extend([_candle(index, str(103 + index - 20), high=str(104 + index - 20), low="100") for index in range(21, 30)])
    signal = detect_donchian_breakouts(
        candles[:21],
        lookback_bars=20,
        candidate_id=SOLCandidateId.DONCHIAN_20_BREAKOUT,
    )[0]
    outcomes = compute_forward_outcomes(candles=candles, signals=[signal], exit_windows_hours=[4])
    metrics = summarize_forward_outcomes(outcomes, exit_window_hours=4, cost_drag_pct=Decimal("0.28"))

    assert metrics.signal_count == 1
    assert metrics.net_mean_pct is not None
    assert metrics.net_mean_pct == outcomes[0].gross_return_pct - Decimal("0.28")


def test_random_baseline_is_deterministic_with_seed() -> None:
    candles = [_candle(index, str(100 + index % 5)) for index in range(80)]
    signals = [
        SOLCandidateSignal(
            candidate_id=SOLCandidateId.DONCHIAN_20_BREAKOUT,
            timestamp_ms=candles[index].timestamp_ms,
            side=SOLResearchSide.LONG,
            entry_close=candles[index].close,
            reason_codes=["unit"],
        )
        for index in [20, 30, 40]
    ]

    first = random_same_frequency_baseline(
        eligible_candles=candles,
        candidate_signals=signals,
        exit_window_hours=4,
        cost_drag_pct=Decimal("0.28"),
        seeds=10,
        base_seed=42,
    )
    second = random_same_frequency_baseline(
        eligible_candles=candles,
        candidate_signals=signals,
        exit_window_hours=4,
        cost_drag_pct=Decimal("0.28"),
        seeds=10,
        base_seed=42,
    )

    assert first == second


def test_campaign_distribution_calculation() -> None:
    candles = [_candle(index, "100", high="101", low="99") for index in range(20)]
    candles.extend([_candle(20, "103", high="104", low="100")])
    candles.extend([_candle(index, str(103 + index - 20), high=str(104 + index - 20), low="100") for index in range(21, 80)])
    signals = [
        SOLCandidateSignal(
            candidate_id=SOLCandidateId.DONCHIAN_20_BREAKOUT,
            timestamp_ms=candles[index].timestamp_ms,
            side=SOLResearchSide.LONG,
            entry_close=candles[index].close,
            reason_codes=["unit"],
        )
        for index in [20, 30, 40]
    ]
    outcomes = compute_forward_outcomes(candles=candles, signals=signals, exit_windows_hours=[4])
    config = CPMCampaignReplayConfig(
        config_id="unit",
        risk_model=CPMCampaignRiskModel.FIXED_FRACTIONAL,
        risk_per_trade_pct=Decimal("20"),
        target_multiple=Decimal("5"),
    )

    summary = summarize_campaign_candidate(
        outcomes=outcomes,
        exit_window_hours=4,
        cost_drag_pct=Decimal("0.28"),
        exposure_multiplier=Decimal("3"),
        campaign_config=config,
        mode=CPMCampaignStressMode.SINGLE_CHRONOLOGICAL_CAMPAIGN,
    )

    assert summary.campaigns >= 1
    assert summary.outcome_distribution


def test_comparison_verdict_logic() -> None:
    metrics = summarize_forward_outcomes(
        [
            *[
                # 30 observations to avoid sample-count parking.
                SOLForwardOutcome(
                    candidate_id=SOLCandidateId.DONCHIAN_20_BREAKOUT,
                    timestamp_ms=index,
                    side=SOLResearchSide.LONG,
                    exit_window_hours=4,
                    gross_return_pct=Decimal("1"),
                    mfe_pct=Decimal("2"),
                    mae_pct=Decimal("-0.5"),
                    follow_through=True,
                    invalidation_hit=False,
                )
                for index in range(30)
            ]
        ],
        exit_window_hours=4,
        cost_drag_pct=Decimal("0.28"),
    )

    verdict = choose_candidate_verdict(
        best_metrics=metrics,
        baseline=None,
        top_campaign_multiple=Decimal("1.8"),
        worst_campaign_multiple=Decimal("1.0"),
        cpm_top_campaign_multiple=Decimal("1.3"),
    )

    assert verdict == SOLCandidateVerdict.CAMPAIGN_CANDIDATE


def test_candidate_pack_exposes_no_execution_order_or_trial_intent_methods() -> None:
    signal = detect_donchian_breakouts(
        [_candle(index, "100", high="101", low="99") for index in range(20)]
        + [_candle(20, "103", high="104", low="100")],
        lookback_bars=20,
        candidate_id=SOLCandidateId.DONCHIAN_20_BREAKOUT,
    )[0]
    payload = signal.model_dump(mode="python")

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

    assert not hasattr(signal, "create_order")
    assert not hasattr(signal, "create_execution_intent")
    assert not hasattr(signal, "write_trial_trade_intent")
