from __future__ import annotations

from src.trading_kernel.application.ports import RuntimeScopeSnapshot
from src.trading_kernel.application.produce_strategy_signal import (
    evaluate_strategy_snapshot,
    produce_strategy_signal,
)
from src.trading_kernel.domain.market import MarketSnapshot
from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts
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
        scope_version=1,
    )

    first = produce_strategy_signal(
        contract=contract,
        scope=scope,
        detector_result=result,
        persisted_facts=result.facts,
    )
    second = produce_strategy_signal(
        contract=contract,
        scope=scope,
        detector_result=result,
        persisted_facts=result.facts,
    )

    assert first == second
    assert first.signal_event_id.startswith("signal:")
    assert first.facts == result.facts
