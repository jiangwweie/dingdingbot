from decimal import Decimal

import pytest

from src.application.opportunity_feedback_calibration_service import (
    EventSpecCalibrationIdentity,
    evaluate_calibration_observation,
)
from src.application.runtime_strategy_signal_evaluation_service import (
    RuntimeStrategySignalEvaluationResult,
    RuntimeStrategySignalEvaluationService,
    RuntimeStrategySignalEvaluationStatus,
)
from src.domain.opportunity_feedback_calibration import (
    OpportunityResult,
    OpportunitySource,
)
from src.domain.strategy_family_signal import (
    AccountFactsSnapshot,
    MarketSnapshot,
    SignalSide,
    SignalType,
    StrategyFactObservation,
    StrategyFamilySignalInput,
    StrategyFamilySignalOutput,
)
from scripts.seed_runtime_control_state_foundation import build_seed_rows


NOW_MS = 1_800_000_000_000


def _event_spec() -> EventSpecCalibrationIdentity:
    return EventSpecCalibrationIdentity.from_pg_event_spec(
        {
            "strategy_group_id": "CPM-RO-001",
            "strategy_group_version_id": "sgv:CPM-RO-001:v2",
            "event_spec_id": "event_spec:CPM-RO-001:CPM-LONG:v2",
            "event_spec_version": "v2",
            "event_id": "CPM-LONG",
            "side": "long",
            "timeframe": "1h",
        },
        evaluator_version_id="CPM-RO-001-v0",
    )


def _input(*, family: str = "CPM-RO-001", version: str = "CPM-RO-001-v0") -> StrategyFamilySignalInput:
    return StrategyFamilySignalInput(
        evaluation_id="ofc-evaluation",
        strategy_family_id=family,
        strategy_family_version_id=version,
        symbol="ETHUSDT",
        timestamp_ms=NOW_MS,
        trigger_candle_close_time_ms=NOW_MS,
        primary_timeframe="1h",
        market_snapshot=MarketSnapshot(
            symbol="ETHUSDT",
            timestamp_ms=NOW_MS,
            source="unit_read_only",
            freshness="fresh",
            timeframe="1h",
            candle_context={"closed_bar": True},
        ),
        account_facts_snapshot=AccountFactsSnapshot(
            source="unit_read_only",
            truth_level="exchange_read",
            timestamp_ms=NOW_MS,
            freshness="fresh",
        ),
        source="unit_replay",
        freshness="fresh",
    )


def _output(*, signal_type: SignalType, fact_value: bool) -> StrategyFamilySignalOutput:
    return StrategyFamilySignalOutput(
        signal_id="ofc-signal",
        evaluation_id="ofc-evaluation",
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        symbol="ETHUSDT",
        timestamp_ms=NOW_MS,
        trigger_candle_close_time_ms=NOW_MS,
        timeframe="1h",
        signal_type=signal_type,
        side=SignalSide.LONG if signal_type == SignalType.WOULD_ENTER else SignalSide.NONE,
        confidence=Decimal("0.7") if signal_type == SignalType.WOULD_ENTER else Decimal("0.2"),
        reason_codes=["cpm_reclaim_confirmed" if fact_value else "cpm_no_action_no_reclaim"],
        human_summary="unit calibration output",
        fact_observations=[
            StrategyFactObservation(
                fact_key="reclaim_confirmed",
                observed_value=fact_value,
                observed_at_ms=NOW_MS,
                valid_until_ms=NOW_MS + 3_600_000,
                source_ref="unit:reclaim",
            )
        ],
    )


class _EvaluationService:
    def __init__(self, output: StrategyFamilySignalOutput) -> None:
        self.output = output
        self.calls = 0

    def evaluate(self, signal_input: StrategyFamilySignalInput) -> RuntimeStrategySignalEvaluationResult:
        self.calls += 1
        status = (
            RuntimeStrategySignalEvaluationStatus.READY_FOR_SEMANTIC_BINDING
            if self.output.signal_type == SignalType.WOULD_ENTER
            else RuntimeStrategySignalEvaluationStatus.OBSERVE_ONLY
        )
        return RuntimeStrategySignalEvaluationResult(
            evaluation_id=signal_input.evaluation_id,
            strategy_family_id=signal_input.strategy_family_id,
            strategy_family_version_id=signal_input.strategy_family_version_id,
            symbol=signal_input.symbol,
            status=status,
            output=self.output,
            evaluator_called=True,
        )


def test_adapter_calls_production_evaluator_and_maps_trial_signal_facts() -> None:
    service = _EvaluationService(_output(signal_type=SignalType.WOULD_ENTER, fact_value=True))

    observation = evaluate_calibration_observation(
        signal_input=_input(),
        event_spec=_event_spec(),
        source=OpportunitySource.REPLAY,
        evaluator_service=service,
        parity_expected=True,
    )

    assert service.calls == 1
    assert observation.result == OpportunityResult.SIGNAL
    assert observation.fact_results == {"reclaim_confirmed": True}
    assert observation.failed_facts == []
    assert observation.exchange_write_allowed is False
    assert observation.owner_policy_mutation_allowed is False


def test_adapter_maps_false_observed_fact_to_near_miss() -> None:
    service = _EvaluationService(_output(signal_type=SignalType.NO_ACTION, fact_value=False))

    observation = evaluate_calibration_observation(
        signal_input=_input(),
        event_spec=_event_spec(),
        source=OpportunitySource.LIVE,
        evaluator_service=service,
    )

    assert observation.result == OpportunityResult.NEAR_MISS
    assert observation.failed_facts == ["reclaim_confirmed"]
    assert observation.fact_results == {"reclaim_confirmed": False}


def test_adapter_projects_opposite_side_signal_as_event_side_near_miss() -> None:
    output = _output(
        signal_type=SignalType.WOULD_ENTER,
        fact_value=True,
    ).model_copy(update={"side": SignalSide.SHORT})
    service = _EvaluationService(output)

    observation = evaluate_calibration_observation(
        signal_input=_input(),
        event_spec=_event_spec(),
        source=OpportunitySource.REPLAY,
        evaluator_service=service,
    )

    assert observation.result == OpportunityResult.NEAR_MISS
    assert observation.fact_results["event_side_matched"] is False
    assert observation.failed_facts == ["event_side_matched"]
    assert observation.exchange_write_allowed is False


def test_adapter_rejects_event_spec_and_signal_input_semantic_mismatch() -> None:
    service = _EvaluationService(_output(signal_type=SignalType.WOULD_ENTER, fact_value=True))

    with pytest.raises(ValueError, match="event_spec_strategy_group_mismatch"):
        evaluate_calibration_observation(
            signal_input=_input(family="MPG-001", version="MPG-001-v0"),
            event_spec=_event_spec(),
            source=OpportunitySource.REPLAY,
            evaluator_service=service,
        )


def test_current_six_event_specs_reuse_configured_production_routes() -> None:
    rows = build_seed_rows(now_ms=NOW_MS)["brc_strategy_side_event_specs"]
    evaluator_versions = {
        "CPM-RO-001": "CPM-RO-001-v0",
        "MPG-001": "MPG-001-v0",
        "MI-001": "MI-001-v0",
        "SOR-001": "SOR-001-v0",
        "BRF2-001": "BRF2-001-v0",
    }
    identities = [
        EventSpecCalibrationIdentity.from_pg_event_spec(
            row,
            evaluator_version_id=evaluator_versions[row["strategy_group_id"]],
        )
        for row in rows
    ]
    assert [item.event_id for item in identities] == [
        "CPM-LONG",
        "MPG-LONG",
        "MI-LONG",
        "SOR-LONG",
        "SOR-SHORT",
        "BRF2-SHORT",
    ]
    assert identities[0].strategy_group_version_id == (
        "sgv:CPM-RO-001:v2"
    )
    assert identities[0].evaluator_version_id == (
        "CPM-RO-001-v0"
    )
    assert identities[0].event_spec_version_id == (
        "event_spec:CPM-RO-001:CPM-LONG:v2:v2"
    )
    service = RuntimeStrategySignalEvaluationService()
    assert all(
        service.route_configured(
            strategy_family_id=item.strategy_group_id,
            strategy_family_version_id=item.evaluator_version_id,
        )
        for item in identities
    )


def test_event_spec_identity_rejects_version_identity_not_owned_by_pg_row() -> None:
    with pytest.raises(ValueError, match="event_spec_identity_mismatch"):
        EventSpecCalibrationIdentity.from_pg_event_spec(
            {
                "strategy_group_id": "CPM-RO-001",
                "strategy_group_version_id": "sgv:CPM-RO-001:v2",
                "event_spec_id": "event_spec:CPM-RO-001:CPM-LONG:v2",
                "event_spec_version": "v1",
                "event_id": "CPM-LONG",
                "side": "long",
                "timeframe": "1h",
            },
            evaluator_version_id="CPM-RO-001-v0",
        )
