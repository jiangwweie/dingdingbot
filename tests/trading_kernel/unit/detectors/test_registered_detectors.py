from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.domain.detector import DetectorStatus, detector_for
from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts
from tests.trading_kernel.unit.detectors.fixtures import (
    brf2_short_snapshot,
    cpm_long_snapshot,
    mi_long_snapshot,
    mpg_long_snapshot,
    sor_snapshot,
)


def test_every_registered_event_has_one_deterministic_detector() -> None:
    for contract in registered_strategy_contracts():
        detector = detector_for(contract.event_spec_id)
        assert detector.event_spec_id == contract.event_spec_id

    detector = detector_for(
        "event_spec:SOR-001:SOR-LONG:v2"
    )
    snapshot = sor_snapshot(side="long")
    assert detector.evaluate(snapshot) == detector.evaluate(snapshot)


@pytest.mark.parametrize(
    ("event_spec_id", "snapshot_factory", "protection_fact"),
    [
        (
            "event_spec:CPM-RO-001:CPM-LONG:v2",
            cpm_long_snapshot,
            "pullback_low_reference",
        ),
        (
            "event_spec:MPG-001:MPG-LONG:v2",
            mpg_long_snapshot,
            "momentum_floor_reference",
        ),
        (
            "event_spec:MI-001:MI-LONG:v2",
            mi_long_snapshot,
            "impulse_invalidation_reference",
        ),
        (
            "event_spec:SOR-001:SOR-LONG:v2",
            lambda: sor_snapshot(side="long"),
            "opening_range_low_reference",
        ),
        (
            "event_spec:SOR-001:SOR-SHORT:v2",
            lambda: sor_snapshot(side="short"),
            "opening_range_high_reference",
        ),
        (
            "event_spec:BRF2-001:BRF2-SHORT:v2",
            brf2_short_snapshot,
            "rally_high_reference",
        ),
    ],
)
def test_each_registered_event_emits_exact_triggered_fact_bundle(
    event_spec_id: str,
    snapshot_factory,
    protection_fact: str,
) -> None:
    contract = next(
        item
        for item in registered_strategy_contracts()
        if item.event_spec_id == event_spec_id
    )
    snapshot = snapshot_factory()

    result = detector_for(event_spec_id).evaluate(snapshot)

    assert result.status is DetectorStatus.TRIGGERED
    assert result.occurred_at_ms == snapshot.trigger_candle_close_time_ms
    assert {item.fact_definition_id for item in result.facts} == {
        item.fact_definition_id
        for item in (*contract.required_facts, *contract.disable_facts)
    }
    assert result.facts_by_name[protection_fact].role == "protection_reference"
    assert Decimal(str(result.facts_by_name[protection_fact].value)) > 0
    assert all(
        fact.satisfied
        for fact in result.facts
        if fact.role != "disable"
    )
    assert all(
        not fact.satisfied
        for fact in result.facts
        if fact.role == "disable"
    )
