from __future__ import annotations

from src.trading_kernel.application.ports import RuntimeScopeSnapshot
from src.trading_kernel.application.produce_strategy_signal import (
    evaluate_strategy_snapshot,
    produce_strategy_signal,
)
from src.trading_kernel.domain.exposure_episode import build_exposure_episode_id
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
