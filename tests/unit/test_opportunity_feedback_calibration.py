from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.domain.opportunity_feedback_calibration import (
    CalibrationProposal,
    OpportunityEvaluation,
    OpportunityResult,
    OpportunitySource,
    calibrate_opportunity_feedback,
)


DAY_MS = 86_400_000
AS_OF_MS = 400 * DAY_MS


def _evaluation(
    *,
    source: OpportunitySource,
    event_time_ms: int,
    result: OpportunityResult,
    fact_results: dict[str, object] | None = None,
    failed_facts: list[str] | None = None,
    parity_expected: bool = True,
    event_id: str = "CPM-LONG",
) -> OpportunityEvaluation:
    return OpportunityEvaluation(
        strategy_group_id="CPM-RO-001",
        strategy_group_version_id="sgv:CPM-RO-001:v2",
        evaluator_version_id="CPM-RO-001-v0",
        event_spec_id="event_spec:CPM-RO-001:CPM-LONG:v2",
        event_spec_version_id="event_spec:CPM-RO-001:CPM-LONG:v2:v2",
        event_id=event_id,
        symbol="ETHUSDT",
        side="long",
        timeframe="1h",
        trigger_candle_close_time_ms=event_time_ms,
        observed_at_ms=event_time_ms + 1,
        source=source,
        result=result,
        fact_results=fact_results or {},
        failed_facts=failed_facts or [],
        parity_expected=parity_expected,
    )


def test_calibration_aggregates_90_and_365_day_windows_and_near_misses() -> None:
    observations = [
        _evaluation(
            source=OpportunitySource.REPLAY,
            event_time_ms=AS_OF_MS - 10 * DAY_MS,
            result=OpportunityResult.NEAR_MISS,
            fact_results={"reclaim_confirmed": False},
            failed_facts=["reclaim_confirmed"],
            parity_expected=False,
        ),
        _evaluation(
            source=OpportunitySource.REPLAY,
            event_time_ms=AS_OF_MS - 120 * DAY_MS,
            result=OpportunityResult.SIGNAL,
            fact_results={"reclaim_confirmed": True},
            parity_expected=False,
        ),
    ]

    result = calibrate_opportunity_feedback(observations, as_of_ms=AS_OF_MS)

    by_days = {window.window_days: window for window in result.windows}
    assert by_days[90].replay.total_evaluations == 1
    assert by_days[90].replay.near_miss_count == 1
    assert by_days[90].replay.failed_fact_counts == {"reclaim_confirmed": 1}
    assert by_days[90].replay.observations_per_30_days == Decimal("0.333333")
    assert by_days[90].replay.signals_per_30_days == Decimal("0")
    assert by_days[90].replay.near_misses_per_30_days == Decimal("0.333333")
    assert by_days[365].replay.total_evaluations == 2
    assert by_days[365].replay.signal_count == 1
    assert by_days[365].replay.near_miss_count == 1
    assert by_days[365].replay.signals_per_30_days == Decimal("0.082192")
    assert by_days[365].replay.near_misses_per_30_days == Decimal("0.082192")
    assert result.proposal == CalibrationProposal.KEEP_OBSERVING


def test_calibration_reports_result_and_fact_parity_mismatch() -> None:
    event_time_ms = AS_OF_MS - DAY_MS
    observations = [
        _evaluation(
            source=OpportunitySource.REPLAY,
            event_time_ms=event_time_ms,
            result=OpportunityResult.SIGNAL,
            fact_results={"reclaim_confirmed": True, "htf_trend_intact": True},
        ),
        _evaluation(
            source=OpportunitySource.LIVE,
            event_time_ms=event_time_ms,
            result=OpportunityResult.NEAR_MISS,
            fact_results={"reclaim_confirmed": False, "htf_trend_intact": True},
            failed_facts=["reclaim_confirmed"],
        ),
    ]

    result = calibrate_opportunity_feedback(observations, as_of_ms=AS_OF_MS)

    assert result.proposal == CalibrationProposal.REPAIR_REPLAY_LIVE_PARITY
    assert result.next_action == "repair_replay_live_parity_before_strategy_review"
    assert len(result.parity_mismatches) == 1
    mismatch = result.parity_mismatches[0]
    assert mismatch.result_mismatch is True
    assert mismatch.mismatched_fact_keys == ["reclaim_confirmed"]
    assert mismatch.replay_result == OpportunityResult.SIGNAL
    assert mismatch.live_result == OpportunityResult.NEAR_MISS


def test_calibration_reports_missing_expected_live_counterpart_as_coverage_gap() -> None:
    observation = _evaluation(
        source=OpportunitySource.REPLAY,
        event_time_ms=AS_OF_MS - DAY_MS,
        result=OpportunityResult.NO_SIGNAL,
        fact_results={"reclaim_confirmed": False},
        parity_expected=True,
    )

    result = calibrate_opportunity_feedback([observation], as_of_ms=AS_OF_MS)

    assert result.proposal == CalibrationProposal.REPAIR_LIVE_COVERAGE
    assert result.missing_live_identities == [observation.comparison_identity]
    assert result.missing_replay_identities == []


def test_calibration_needs_more_samples_when_no_window_contains_observations() -> None:
    old = _evaluation(
        source=OpportunitySource.REPLAY,
        event_time_ms=AS_OF_MS - 366 * DAY_MS,
        result=OpportunityResult.NO_SIGNAL,
        parity_expected=False,
    )

    result = calibrate_opportunity_feedback([old], as_of_ms=AS_OF_MS)

    assert result.proposal == CalibrationProposal.NEEDS_MORE_SAMPLES
    assert result.next_action == "collect_more_version_pinned_observations"


def test_opportunity_evaluation_rejects_execution_authority_claims() -> None:
    payload = _evaluation(
        source=OpportunitySource.REPLAY,
        event_time_ms=AS_OF_MS - DAY_MS,
        result=OpportunityResult.NO_SIGNAL,
    ).model_dump(mode="python")
    payload["exchange_write_allowed"] = True

    with pytest.raises(ValidationError):
        OpportunityEvaluation.model_validate(payload)


def test_opportunity_evaluation_identity_includes_event_version_side_and_time() -> None:
    observation = _evaluation(
        source=OpportunitySource.LIVE,
        event_time_ms=AS_OF_MS - DAY_MS,
        result=OpportunityResult.SIGNAL,
        event_id="SOR-SHORT",
    ).model_copy(
        update={
            "strategy_group_id": "SOR-001",
            "strategy_group_version_id": "sgv:SOR-001:v2",
            "evaluator_version_id": "SOR-001-v0",
            "event_spec_id": "event_spec:SOR-001:SOR-SHORT:v2",
            "event_spec_version_id": "event_spec:SOR-001:SOR-SHORT:v2:v2",
            "symbol": "BTCUSDT",
            "side": "short",
            "timeframe": "15m",
        }
    )

    assert observation.comparison_identity == (
        "SOR-001|sgv:SOR-001:v2|SOR-001-v0|event_spec:SOR-001:SOR-SHORT:v2|"
        "event_spec:SOR-001:SOR-SHORT:v2:v2|SOR-SHORT|BTCUSDT|short|15m|"
        f"{AS_OF_MS - DAY_MS}"
    )
    payload = observation.model_dump(mode="python")
    assert payload["calibration_only"] is True
    assert "replay_only" not in payload
