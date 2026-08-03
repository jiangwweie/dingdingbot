from __future__ import annotations

from src.trading_kernel.application.ports import RuntimeScopeSnapshot
from src.trading_kernel.application.produce_strategy_signal import (
    evaluate_strategy_snapshot,
    produce_strategy_signal,
)
from src.trading_kernel.domain.detector import DetectorStatus
from src.trading_kernel.domain.exposure_episode import (
    advance_exposure_episode,
    build_exposure_episode_id,
)
from src.trading_kernel.domain.market import MarketSnapshot
from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts
from tests.trading_kernel.unit.detectors.fixtures import cpm_long_snapshot, sor_snapshot


def test_live_and_replay_use_the_same_detector_result() -> None:
    contract = next(
        item
        for item in registered_strategy_contracts()
        if item.event_id == "CPM-LONG"
    )
    live_snapshot = cpm_long_snapshot()
    replay_snapshot = MarketSnapshot.model_validate(
        live_snapshot.model_dump(mode="python")
    )

    live = evaluate_strategy_snapshot(contract, live_snapshot)
    replay = evaluate_strategy_snapshot(contract, replay_snapshot)

    assert live == replay
    assert live.triggered is True


def test_signal_identity_is_stable_for_the_same_scope_event_and_fact_bundle() -> None:
    contract = next(
        item
        for item in registered_strategy_contracts()
        if item.event_id == "CPM-LONG"
    )
    snapshot = cpm_long_snapshot()
    result = evaluate_strategy_snapshot(contract, snapshot)
    scope = RuntimeScopeSnapshot(
        runtime_scope_id="scope-cpm-eth-long",
        strategy_group_id=contract.strategy_group_id,
        strategy_version_id=contract.strategy_version_id,
        event_spec_id=contract.event_spec_id,
        runtime_profile_id="profile-observation-only",
        owner_policy_id="policy-observation-only",
        exchange_instrument_id=snapshot.exchange_instrument_id,
        position_side="long",
        universe_version_id="universe:CPM-LONG:3",
        universe_semantic_digest="sha256:" + "a" * 64,
        lifecycle_state="active",
        observation_enabled=True,
        entry_enabled=True,
        scope_version=1,
        observation_generation=0,
    )
    episode_id = build_exposure_episode_id(
        event_spec_id=contract.event_spec_id,
        exchange_instrument_id=snapshot.exchange_instrument_id,
        position_side=contract.position_side,
        occurred_at_ms=result.occurred_at_ms or 0,
    )

    first = produce_strategy_signal(
        contract=contract,
        scope=scope,
        detector_result=result,
        persisted_facts=result.facts,
        exposure_episode_id=episode_id,
    )
    second = produce_strategy_signal(
        contract=contract,
        scope=scope,
        detector_result=result,
        persisted_facts=result.facts,
        exposure_episode_id=episode_id,
    )

    assert first == second
    assert first.signal_event_id.startswith("signal:")
    assert first.exposure_episode_id.startswith("episode:")
    assert first.facts == result.facts


def test_rising_edge_signal_rejects_implicit_occurrence_time_episode() -> None:
    contract = next(
        item
        for item in registered_strategy_contracts()
        if item.event_id == "CPM-LONG"
    )
    snapshot = cpm_long_snapshot()
    result = evaluate_strategy_snapshot(contract, snapshot)
    scope = RuntimeScopeSnapshot(
        runtime_scope_id="scope-cpm-eth-long",
        strategy_group_id=contract.strategy_group_id,
        strategy_version_id=contract.strategy_version_id,
        event_spec_id=contract.event_spec_id,
        runtime_profile_id="profile-observation-only",
        owner_policy_id="policy-observation-only",
        exchange_instrument_id=snapshot.exchange_instrument_id,
        position_side="long",
        universe_version_id="universe:CPM-LONG:3",
        universe_semantic_digest="sha256:" + "a" * 64,
        lifecycle_state="active",
        observation_enabled=True,
        entry_enabled=True,
        scope_version=1,
        observation_generation=0,
    )

    try:
        produce_strategy_signal(
            contract=contract,
            scope=scope,
            detector_result=result,
            persisted_facts=result.facts,
        )
    except ValueError as exc:
        assert "explicit Episode identity" in str(exc)
    else:
        raise AssertionError("rising-edge Signal accepted an implicit Episode")


def test_sor_live_and_replay_share_one_session_episode_and_fifteen_minute_expiry() -> None:
    contract = next(
        item for item in registered_strategy_contracts() if item.event_id == "SOR-LONG"
    )
    snapshot = sor_snapshot(side="long")
    result = evaluate_strategy_snapshot(contract, snapshot)
    scope = RuntimeScopeSnapshot(
        runtime_scope_id="scope-sor-eth-long",
        strategy_group_id=contract.strategy_group_id,
        strategy_version_id=contract.strategy_version_id,
        event_spec_id=contract.event_spec_id,
        runtime_profile_id="profile-observation-only",
        owner_policy_id="policy-observation-only",
        exchange_instrument_id=snapshot.exchange_instrument_id,
        position_side="long",
        universe_version_id="universe:SOR-LONG:3",
        universe_semantic_digest="sha256:" + "a" * 64,
        lifecycle_state="active",
        observation_enabled=True,
        entry_enabled=True,
        scope_version=1,
        observation_generation=0,
    )

    live = produce_strategy_signal(
        contract=contract,
        scope=scope,
        detector_result=result,
        persisted_facts=result.facts,
    )
    replay = produce_strategy_signal(
        contract=contract,
        scope=scope,
        detector_result=evaluate_strategy_snapshot(
            contract,
            MarketSnapshot.model_validate(snapshot.model_dump(mode="python")),
        ),
        persisted_facts=result.facts,
    )

    assert live == replay
    assert live.expires_at_ms == live.occurred_at_ms + 900_000


def test_epi_008_sor_new_session_creates_new_episode_identity() -> None:
    contract = next(
        item for item in registered_strategy_contracts() if item.event_id == "SOR-LONG"
    )
    first_snapshot = sor_snapshot(side="long")
    first = evaluate_strategy_snapshot(contract, first_snapshot)
    one_day_ms = 86_400_000
    next_snapshot = first_snapshot.model_copy(
        update={
            "trigger_candle_close_time_ms": (
                first_snapshot.trigger_candle_close_time_ms + one_day_ms
            ),
            "candles_15m": tuple(
                candle.model_copy(
                    update={
                        "open_time_ms": candle.open_time_ms + one_day_ms,
                        "close_time_ms": candle.close_time_ms + one_day_ms,
                    }
                )
                for candle in first_snapshot.candles_15m
            ),
        }
    )
    second = evaluate_strategy_snapshot(contract, next_snapshot)
    scope = RuntimeScopeSnapshot(
        runtime_scope_id="scope-sor-eth-long",
        strategy_group_id=contract.strategy_group_id,
        strategy_version_id=contract.strategy_version_id,
        event_spec_id=contract.event_spec_id,
        runtime_profile_id="profile-observation-only",
        owner_policy_id="policy-observation-only",
        exchange_instrument_id=first_snapshot.exchange_instrument_id,
        position_side="long",
        universe_version_id="universe:SOR-LONG:3",
        universe_semantic_digest="sha256:" + "a" * 64,
        lifecycle_state="active",
        observation_enabled=True,
        entry_enabled=True,
        scope_version=1,
        observation_generation=0,
    )

    first_signal = produce_strategy_signal(
        contract=contract,
        scope=scope,
        detector_result=first,
        persisted_facts=first.facts,
    )
    second_signal = produce_strategy_signal(
        contract=contract,
        scope=scope,
        detector_result=second,
        persisted_facts=second.facts,
    )

    assert second_signal.occurred_at_ms == first_signal.occurred_at_ms + one_day_ms
    assert second_signal.exposure_episode_id != first_signal.exposure_episode_id


def test_epi_009_live_and_replay_reduce_identical_episode_sequence() -> None:
    contract = next(
        item for item in registered_strategy_contracts() if item.event_id == "CPM-LONG"
    )
    sequence = (
        (DetectorStatus.TRIGGERED, 1_000),
        (DetectorStatus.TRIGGERED, 2_000),
        (DetectorStatus.NOT_TRIGGERED, 3_000),
        (DetectorStatus.TRIGGERED, 4_000),
    )

    def reduce_sequence():
        current = None
        results = []
        for status, observed_at_ms in sequence:
            result = advance_exposure_episode(
                contract=contract,
                current=current,
                detector_status=status,
                occurred_at_ms=(
                    observed_at_ms if status is DetectorStatus.TRIGGERED else None
                ),
                observed_at_ms=observed_at_ms,
                exchange_instrument_id="binance-usdm:ETHUSDT:perpetual",
            )
            current = result.current
            results.append(result)
        return tuple(results)

    live = reduce_sequence()
    replay = reduce_sequence()

    assert replay == live
    assert replay[-1].exposure_episode_id != replay[0].exposure_episode_id
    assert replay[-1].current.projection_version == 4
