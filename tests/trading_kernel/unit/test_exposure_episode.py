from __future__ import annotations

import pytest

from src.trading_kernel.domain.detector import DetectorStatus
from src.trading_kernel.domain.exposure_episode import advance_exposure_episode
from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts

ETH = "binance-usdm:ETHUSDT:perpetual"


def test_continuous_trigger_reuses_one_rising_edge_episode() -> None:
    contract = _contract("CPM-LONG")

    first = advance_exposure_episode(
        contract=contract,
        current=None,
        detector_status=DetectorStatus.TRIGGERED,
        occurred_at_ms=1_000,
        observed_at_ms=1_000,
        exchange_instrument_id=ETH,
    )
    second = advance_exposure_episode(
        contract=contract,
        current=first.current,
        detector_status=DetectorStatus.TRIGGERED,
        occurred_at_ms=2_000,
        observed_at_ms=2_000,
        exchange_instrument_id=ETH,
    )

    assert first.created_new_episode is True
    assert second.created_new_episode is False
    assert second.exposure_episode_id == first.exposure_episode_id
    assert second.current.projection_version == 2
    assert second.current.last_observed_at_ms == 2_000


def test_false_closed_bar_rearms_the_next_trigger() -> None:
    contract = _contract("CPM-LONG")

    first = advance_exposure_episode(
        contract=contract,
        current=None,
        detector_status=DetectorStatus.TRIGGERED,
        occurred_at_ms=1_000,
        observed_at_ms=1_000,
        exchange_instrument_id=ETH,
    )
    armed = advance_exposure_episode(
        contract=contract,
        current=first.current,
        detector_status=DetectorStatus.NOT_TRIGGERED,
        occurred_at_ms=None,
        observed_at_ms=2_000,
        exchange_instrument_id=ETH,
    )
    second = advance_exposure_episode(
        contract=contract,
        current=armed.current,
        detector_status=DetectorStatus.TRIGGERED,
        occurred_at_ms=3_000,
        observed_at_ms=3_000,
        exchange_instrument_id=ETH,
    )

    assert armed.current.state == "armed"
    assert armed.current.exposure_episode_id is None
    assert armed.current.rearmed_at_ms == 2_000
    assert second.created_new_episode is True
    assert second.exposure_episode_id != first.exposure_episode_id


def test_invalid_observation_cannot_mutate_episode_state() -> None:
    contract = _contract("CPM-LONG")

    with pytest.raises(ValueError, match="triggered or not_triggered"):
        advance_exposure_episode(
            contract=contract,
            current=None,
            detector_status=DetectorStatus.INVALID,
            occurred_at_ms=None,
            observed_at_ms=1_000,
            exchange_instrument_id=ETH,
        )


def test_session_reference_contract_does_not_use_rising_edge_reducer() -> None:
    contract = _contract("SOR-LONG")

    with pytest.raises(ValueError, match="rising-edge"):
        advance_exposure_episode(
            contract=contract,
            current=None,
            detector_status=DetectorStatus.TRIGGERED,
            occurred_at_ms=1_000,
            observed_at_ms=1_000,
            exchange_instrument_id=ETH,
        )


def test_event_version_is_part_of_episode_domain_and_identity() -> None:
    contract = _contract("CPM-LONG")
    prior = contract.model_copy(
        update={
            "strategy_version_id": "sgv:CPM-RO-001:v2",
            "event_spec_id": "event_spec:CPM-RO-001:CPM-LONG:v2",
        }
    )

    current = advance_exposure_episode(
        contract=contract,
        current=None,
        detector_status=DetectorStatus.TRIGGERED,
        occurred_at_ms=1_000,
        observed_at_ms=1_000,
        exchange_instrument_id=ETH,
    )
    historical = advance_exposure_episode(
        contract=prior,
        current=None,
        detector_status=DetectorStatus.TRIGGERED,
        occurred_at_ms=1_000,
        observed_at_ms=1_000,
        exchange_instrument_id=ETH,
    )

    assert current.current.episode_domain_key != historical.current.episode_domain_key
    assert current.exposure_episode_id != historical.exposure_episode_id


def _contract(event_id: str):
    return next(
        item for item in registered_strategy_contracts() if item.event_id == event_id
    )
