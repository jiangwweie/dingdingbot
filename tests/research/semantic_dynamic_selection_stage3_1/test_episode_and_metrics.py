from decimal import Decimal

from research.semantic_dynamic_selection_stage3_1.core import (
    capture_metrics,
    simulate_hysteresis,
)
from src.trading_kernel.domain.detector import DetectorStatus
from src.trading_kernel.domain.exposure_episode import advance_exposure_episode
from src.trading_kernel.domain.strategy_registry import strategy_contract_for


def test_exposure_episode_is_not_reset_by_unobserved_universe_absence() -> None:
    contract = strategy_contract_for("event_spec:CPM-RO-001:CPM-LONG:v3")
    first = advance_exposure_episode(
        contract=contract,
        current=None,
        detector_status=DetectorStatus.TRIGGERED,
        occurred_at_ms=2_000_000_000_000,
        observed_at_ms=2_000_000_000_000,
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
    )

    reentered = advance_exposure_episode(
        contract=contract,
        current=first.current,
        detector_status=DetectorStatus.TRIGGERED,
        occurred_at_ms=2_000_014_400_000,
        observed_at_ms=2_000_014_400_000,
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
    )

    assert first.created_new_episode is True
    assert reentered.created_new_episode is False
    assert reentered.current.exposure_episode_id == first.current.exposure_episode_id
    assert reentered.current.state == first.current.state


def test_capture_and_bad_rejection_use_all_excluded_events() -> None:
    metrics = capture_metrics(
        all_labels=("TP", "TP", "STOP", "STOP"),
        selected_labels=("TP", "STOP"),
        excluded_labels=("TP", "STOP"),
    )

    assert metrics.good_event_capture == Decimal("0.5")
    assert metrics.bad_event_rejection == Decimal("0.5")
    assert metrics.opportunity_retention == Decimal("0.5")


def test_hysteresis_enters_at_n_and_retains_only_through_rank_16() -> None:
    selected = simulate_hysteresis(
        prior_selected=frozenset({"A", "B"}),
        ranks={"A": 15, "B": 17, "C": 10, "D": 13},
        entry_cardinality=12,
    )

    assert selected == frozenset({"A", "C"})
