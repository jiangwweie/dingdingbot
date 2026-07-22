from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.detector import DetectorStatus, detector_for
from src.trading_kernel.domain.market import MarketSnapshot
from tests.trading_kernel.unit.detectors.fixtures import (
    ETH,
    NOW_MS,
    brf2_short_snapshot,
    cpm_flat_snapshot,
    cpm_long_snapshot,
    mi_flat_snapshot,
    mi_long_snapshot,
    mpg_flat_snapshot,
    mpg_long_snapshot,
    sor_snapshot,
)


def test_insufficient_market_windows_are_invalid_not_no_action() -> None:
    source = cpm_long_snapshot()
    insufficient = source.model_copy(update={"candles_1h": source.candles_1h[1:]})

    result = detector_for(
        "event_spec:CPM-RO-001:CPM-LONG:v2"
    ).evaluate(insufficient)

    assert result.status is DetectorStatus.INVALID
    assert result.reason_code == "cpm_invalid_insufficient_candles"
    assert result.facts == ()


def test_cpm_computed_false_facts_are_not_triggered() -> None:
    result = detector_for(
        "event_spec:CPM-RO-001:CPM-LONG:v2"
    ).evaluate(cpm_flat_snapshot())

    assert result.status is DetectorStatus.NOT_TRIGGERED
    assert result.facts_by_name["htf_trend_intact"].satisfied is False
    assert result.facts_by_name["reclaim_confirmed"].satisfied is False


def test_mpg_missing_or_stale_comparative_strength_is_invalid() -> None:
    event_spec_id = "event_spec:MPG-001:MPG-LONG:v2"
    missing = mpg_long_snapshot().model_copy(update={"comparative_strength": None})
    stale = mpg_long_snapshot(comparative_valid_until_ms=NOW_MS)

    assert detector_for(event_spec_id).evaluate(missing).reason_code == (
        "mpg_invalid_comparative_strength_missing"
    )
    assert detector_for(event_spec_id).evaluate(stale).reason_code == (
        "mpg_invalid_comparative_strength_stale"
    )


def test_mpg_market_no_action_does_not_require_comparative_snapshot() -> None:
    result = detector_for(
        "event_spec:MPG-001:MPG-LONG:v2"
    ).evaluate(mpg_flat_snapshot())

    assert result.status is DetectorStatus.NOT_TRIGGERED
    assert result.facts_by_name["momentum_persistence_confirmed"].satisfied is False


def test_mpg_nonleader_is_computed_not_triggered() -> None:
    result = detector_for(
        "event_spec:MPG-001:MPG-LONG:v2"
    ).evaluate(mpg_long_snapshot(candidate_rank=2))

    assert result.status is DetectorStatus.NOT_TRIGGERED
    assert result.facts_by_name["momentum_persistence_confirmed"].satisfied is True
    assert result.facts_by_name["leader_strength_confirmed"].satisfied is False


def test_mi_below_threshold_and_nonleader_are_not_triggered() -> None:
    event_spec_id = "event_spec:MI-001:MI-LONG:v2"
    below = detector_for(event_spec_id).evaluate(mi_flat_snapshot())
    nonleader = detector_for(event_spec_id).evaluate(
        mi_long_snapshot(candidate_rank=2)
    )

    assert below.status is DetectorStatus.NOT_TRIGGERED
    assert below.facts_by_name["impulse_confirmed"].satisfied is False
    assert nonleader.status is DetectorStatus.NOT_TRIGGERED
    assert nonleader.facts_by_name["relative_strength_confirmed"].satisfied is False


def test_mi_comparative_return_mismatch_is_invalid() -> None:
    result = detector_for(
        "event_spec:MI-001:MI-LONG:v2"
    ).evaluate(mi_long_snapshot(candidate_return_pct=Decimal("99")))

    assert result.status is DetectorStatus.INVALID
    assert result.reason_code == "mi_invalid_comparative_return_mismatch"


@pytest.mark.parametrize(
    ("event_spec_id", "event_fact"),
    [
        ("event_spec:SOR-001:SOR-LONG:v2", "breakout_confirmed"),
        ("event_spec:SOR-001:SOR-SHORT:v2", "breakdown_confirmed"),
    ],
)
def test_sor_intact_range_is_not_triggered(
    event_spec_id: str,
    event_fact: str,
) -> None:
    result = detector_for(event_spec_id).evaluate(sor_snapshot(side=None))

    assert result.status is DetectorStatus.NOT_TRIGGERED
    assert result.facts_by_name["opening_range_defined"].satisfied is True
    assert result.facts_by_name[event_fact].satisfied is False


def test_brf2_strong_uptrend_disable_prevents_short_signal() -> None:
    result = detector_for(
        "event_spec:BRF2-001:BRF2-SHORT:v2"
    ).evaluate(brf2_short_snapshot(strong_uptrend=True))

    assert result.status is DetectorStatus.NOT_TRIGGERED
    assert result.facts_by_name["strong_uptrend_disable"].satisfied is True
    assert result.facts_by_name["short_side_not_disabled"].satisfied is False


def test_market_snapshot_rejects_open_or_future_candles() -> None:
    candle = sor_snapshot(side="long").candles_15m[-1]
    future = candle.model_copy(update={"close_time_ms": NOW_MS + 1})

    with pytest.raises(ValidationError):
        MarketSnapshot(
            exchange_instrument_id=ETH,
            trigger_candle_close_time_ms=NOW_MS,
            candles_15m=(future,),
        )


def test_unknown_event_spec_has_no_detector() -> None:
    with pytest.raises(KeyError, match="unknown Event Spec"):
        detector_for("event_spec:unknown")
