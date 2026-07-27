from __future__ import annotations

from src.trading_kernel.application.ports import RuntimeScopeSnapshot
from src.trading_kernel.application.produce_strategy_signal import (
    evaluate_strategy_snapshot,
    produce_strategy_signal,
)
from src.trading_kernel.domain.market import MarketSnapshot
from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts
from src.trading_kernel.domain.strategy_universe import universe_for_event_spec
from tests.trading_kernel.unit.detectors.fixtures import cpm_long_snapshot


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
    universe = universe_for_event_spec(contract.event_spec_id)
    scope = RuntimeScopeSnapshot(
        runtime_scope_id="scope-cpm-eth-long",
        strategy_group_id=contract.strategy_group_id,
        strategy_version_id=contract.strategy_version_id,
        event_spec_id=contract.event_spec_id,
        runtime_profile_id="profile-observation-only",
        owner_policy_id="policy-observation-only",
        exchange_instrument_id=snapshot.exchange_instrument_id,
        position_side="long",
        enabled=True,
        universe_version_id=universe.universe_version_id,
        universe_digest=universe.semantic_digest(),
        scope_version=1,
    )

    first = produce_strategy_signal(
        contract=contract,
        scope=scope,
        snapshot=snapshot,
        detector_result=result,
        persisted_facts=result.facts,
        universe=universe,
    )
    second = produce_strategy_signal(
        contract=contract,
        scope=scope,
        snapshot=snapshot,
        detector_result=result,
        persisted_facts=result.facts,
        universe=universe,
    )

    assert first == second
    assert first.signal_event_id.startswith("signal:")
    assert first.facts == result.facts
