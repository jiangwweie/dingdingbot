from __future__ import annotations

import pytest

from src.trading_kernel.domain.detector import DetectorStatus
from src.trading_kernel.domain.exposure_episode import (
    ComparisonBindingEpisodeCheckpoint,
    ComparisonBindingEpisodeState,
    advance_comparison_bound_exposure_episode,
    advance_exposure_episode,
    build_episode_domain_key,
)
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


def test_epi_005_universe_replacement_preserves_continuous_episode() -> None:
    contract = _contract("CPM-LONG")
    before_replacement = advance_exposure_episode(
        contract=contract,
        current=None,
        detector_status=DetectorStatus.TRIGGERED,
        occurred_at_ms=1_000,
        observed_at_ms=1_000,
        exchange_instrument_id=ETH,
    )

    after_replacement = advance_exposure_episode(
        contract=contract,
        current=before_replacement.current,
        detector_status=DetectorStatus.TRIGGERED,
        occurred_at_ms=2_000,
        observed_at_ms=2_000,
        exchange_instrument_id=ETH,
    )

    assert after_replacement.created_new_episode is False
    assert (
        after_replacement.exposure_episode_id
        == before_replacement.exposure_episode_id
    )
    assert after_replacement.current.projection_version == 2


def test_comparison_switch_first_trigger_is_suppressed_until_new_binding_arms() -> None:
    contract = _contract("MPG-LONG")
    armed_static = advance_exposure_episode(
        contract=contract,
        current=None,
        detector_status=DetectorStatus.NOT_TRIGGERED,
        occurred_at_ms=None,
        observed_at_ms=1_000,
        exchange_instrument_id=ETH,
    ).current
    static_checkpoint = _checkpoint(
        contract=contract,
        comparison_digest="sha256:" + "a" * 64,
        transition_revision=1,
        state=ComparisonBindingEpisodeState.ARMED_UNDER_BINDING,
        armed_at_ms=1_000,
        last_observed_at_ms=1_000,
        last_detector_status=DetectorStatus.NOT_TRIGGERED,
    )

    switched_trigger = advance_comparison_bound_exposure_episode(
        contract=contract,
        current_episode=armed_static,
        current_checkpoint=static_checkpoint,
        detector_status=DetectorStatus.TRIGGERED,
        occurred_at_ms=2_000,
        observed_at_ms=2_000,
        exchange_instrument_id=ETH,
        comparison_binding_digest="sha256:" + "b" * 64,
        comparison_transition_revision=2,
    )

    assert switched_trigger.signal_eligible is False
    assert switched_trigger.suppression_reason == "COMPARISON_REBASE_REQUIRED"
    assert switched_trigger.episode_transition is None
    assert switched_trigger.checkpoint.state is ComparisonBindingEpisodeState.REBASE_REQUIRED

    rearmed = advance_comparison_bound_exposure_episode(
        contract=contract,
        current_episode=armed_static,
        current_checkpoint=switched_trigger.checkpoint,
        detector_status=DetectorStatus.NOT_TRIGGERED,
        occurred_at_ms=None,
        observed_at_ms=3_000,
        exchange_instrument_id=ETH,
        comparison_binding_digest="sha256:" + "b" * 64,
        comparison_transition_revision=2,
    )
    assert rearmed.signal_eligible is False
    assert rearmed.episode_transition is not None
    assert rearmed.episode_transition.current.state == "armed"
    assert rearmed.checkpoint.state is ComparisonBindingEpisodeState.ARMED_UNDER_BINDING
    assert rearmed.checkpoint.armed_at_ms == 3_000

    natural_trigger = advance_comparison_bound_exposure_episode(
        contract=contract,
        current_episode=rearmed.episode_transition.current,
        current_checkpoint=rearmed.checkpoint,
        detector_status=DetectorStatus.TRIGGERED,
        occurred_at_ms=4_000,
        observed_at_ms=4_000,
        exchange_instrument_id=ETH,
        comparison_binding_digest="sha256:" + "b" * 64,
        comparison_transition_revision=2,
    )
    assert natural_trigger.signal_eligible is True
    assert natural_trigger.episode_transition is not None
    assert natural_trigger.episode_transition.created_new_episode is True


def test_comparison_a_to_b_to_a_requires_fresh_rearm_for_second_a_revision() -> None:
    contract = _contract("MI-LONG")
    checkpoint_a = _checkpoint(
        contract=contract,
        comparison_digest="sha256:" + "a" * 64,
        transition_revision=1,
        state=ComparisonBindingEpisodeState.ARMED_UNDER_BINDING,
        armed_at_ms=1_000,
        last_observed_at_ms=1_000,
        last_detector_status=DetectorStatus.NOT_TRIGGERED,
    )

    first_switch = advance_comparison_bound_exposure_episode(
        contract=contract,
        current_episode=None,
        current_checkpoint=checkpoint_a,
        detector_status=DetectorStatus.TRIGGERED,
        occurred_at_ms=2_000,
        observed_at_ms=2_000,
        exchange_instrument_id=ETH,
        comparison_binding_digest="sha256:" + "b" * 64,
        comparison_transition_revision=2,
    )
    rollback_trigger = advance_comparison_bound_exposure_episode(
        contract=contract,
        current_episode=None,
        current_checkpoint=first_switch.checkpoint,
        detector_status=DetectorStatus.TRIGGERED,
        occurred_at_ms=3_000,
        observed_at_ms=3_000,
        exchange_instrument_id=ETH,
        comparison_binding_digest="sha256:" + "a" * 64,
        comparison_transition_revision=3,
    )

    assert rollback_trigger.signal_eligible is False
    assert rollback_trigger.episode_transition is None
    assert rollback_trigger.checkpoint.comparison_transition_revision == 3
    assert rollback_trigger.checkpoint.state is ComparisonBindingEpisodeState.REBASE_REQUIRED


def test_comparison_switch_from_triggered_state_requires_target_rearm() -> None:
    contract = _contract("MPG-LONG")
    old_trigger = advance_exposure_episode(
        contract=contract,
        current=None,
        detector_status=DetectorStatus.TRIGGERED,
        occurred_at_ms=1_000,
        observed_at_ms=1_000,
        exchange_instrument_id=ETH,
    )
    checkpoint = _checkpoint(
        contract=contract,
        comparison_digest="sha256:" + "a" * 64,
        transition_revision=1,
        state=ComparisonBindingEpisodeState.ARMED_UNDER_BINDING,
        armed_at_ms=500,
        last_observed_at_ms=1_000,
        last_detector_status=DetectorStatus.TRIGGERED,
    )

    suppressed = advance_comparison_bound_exposure_episode(
        contract=contract,
        current_episode=old_trigger.current,
        current_checkpoint=checkpoint,
        detector_status=DetectorStatus.TRIGGERED,
        occurred_at_ms=2_000,
        observed_at_ms=2_000,
        exchange_instrument_id=ETH,
        comparison_binding_digest="sha256:" + "b" * 64,
        comparison_transition_revision=2,
    )
    assert suppressed.signal_eligible is False
    assert suppressed.episode_transition is None

    rearmed = advance_comparison_bound_exposure_episode(
        contract=contract,
        current_episode=old_trigger.current,
        current_checkpoint=suppressed.checkpoint,
        detector_status=DetectorStatus.NOT_TRIGGERED,
        occurred_at_ms=None,
        observed_at_ms=3_000,
        exchange_instrument_id=ETH,
        comparison_binding_digest="sha256:" + "b" * 64,
        comparison_transition_revision=2,
    )
    new_trigger = advance_comparison_bound_exposure_episode(
        contract=contract,
        current_episode=rearmed.episode_transition.current,
        current_checkpoint=rearmed.checkpoint,
        detector_status=DetectorStatus.TRIGGERED,
        occurred_at_ms=4_000,
        observed_at_ms=4_000,
        exchange_instrument_id=ETH,
        comparison_binding_digest="sha256:" + "b" * 64,
        comparison_transition_revision=2,
    )

    assert new_trigger.episode_transition.created_new_episode is True
    assert (
        new_trigger.episode_transition.exposure_episode_id
        != old_trigger.exposure_episode_id
    )


def test_comparison_rebase_rejects_same_close_contradiction() -> None:
    contract = _contract("MPG-LONG")
    checkpoint = _checkpoint(
        contract=contract,
        comparison_digest="sha256:" + "b" * 64,
        transition_revision=2,
        state=ComparisonBindingEpisodeState.REBASE_REQUIRED,
        armed_at_ms=None,
        last_observed_at_ms=2_000,
        last_detector_status=DetectorStatus.TRIGGERED,
    )

    with pytest.raises(ValueError, match="contradictory"):
        advance_comparison_bound_exposure_episode(
            contract=contract,
            current_episode=None,
            current_checkpoint=checkpoint,
            detector_status=DetectorStatus.NOT_TRIGGERED,
            occurred_at_ms=None,
            observed_at_ms=2_000,
            exchange_instrument_id=ETH,
            comparison_binding_digest="sha256:" + "b" * 64,
            comparison_transition_revision=2,
        )


def _checkpoint(
    *,
    contract,
    comparison_digest: str,
    transition_revision: int,
    state: ComparisonBindingEpisodeState,
    armed_at_ms: int | None,
    last_observed_at_ms: int,
    last_detector_status: DetectorStatus,
) -> ComparisonBindingEpisodeCheckpoint:
    return ComparisonBindingEpisodeCheckpoint(
        episode_domain_key=build_episode_domain_key(
            event_spec_id=contract.event_spec_id,
            exchange_instrument_id=ETH,
            position_side=contract.position_side,
        ),
        comparison_binding_digest=comparison_digest,
        comparison_transition_revision=transition_revision,
        state=state,
        armed_at_ms=armed_at_ms,
        last_observed_at_ms=last_observed_at_ms,
        last_detector_status=last_detector_status,
        projection_version=1,
    )


def _contract(event_id: str):
    return next(
        item for item in registered_strategy_contracts() if item.event_id == event_id
    )
