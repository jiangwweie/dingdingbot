"""Shared live/replay evaluation and deterministic StrategySignal production."""

from __future__ import annotations

from hashlib import sha256
import json

from src.trading_kernel.application.ports import RuntimeScopeSnapshot
from src.trading_kernel.domain.detector import DetectorResult, detector_for
from src.trading_kernel.domain.market import MarketSnapshot
from src.trading_kernel.domain.signal import (
    SignalFactSnapshot,
    StrategySignal,
    build_signal_fact_digest,
)
from src.trading_kernel.domain.strategy_registry import RegisteredStrategyContract
from src.trading_kernel.domain.strategy_universe import StrategyUniverseVersion


def evaluate_strategy_snapshot(
    contract: RegisteredStrategyContract,
    snapshot: MarketSnapshot,
) -> DetectorResult:
    return detector_for(contract.event_spec_id).evaluate(snapshot)


def produce_strategy_signal(
    *,
    contract: RegisteredStrategyContract,
    scope: RuntimeScopeSnapshot,
    snapshot: MarketSnapshot,
    detector_result: DetectorResult,
    persisted_facts: tuple[SignalFactSnapshot, ...],
    universe: StrategyUniverseVersion,
) -> StrategySignal:
    if not detector_result.triggered or detector_result.occurred_at_ms is None:
        raise ValueError("StrategySignal requires a triggered detector result")
    if (
        detector_result.event_spec_id != contract.event_spec_id
        or scope.strategy_group_id != contract.strategy_group_id
        or scope.strategy_version_id != contract.strategy_version_id
        or scope.event_spec_id != contract.event_spec_id
        or scope.position_side != contract.position_side
    ):
        raise ValueError("Signal contract and runtime scope identity differ")
    expected_fact_ids = {
        item.fact_definition_id
        for item in (*contract.required_facts, *contract.disable_facts)
    }
    if {item.fact_definition_id for item in persisted_facts} != expected_fact_ids:
        raise ValueError("persisted Signal facts differ from Registry contract")

    facts = tuple(
        sorted(persisted_facts, key=lambda item: item.fact_definition_id)
    )
    fact_digest = build_signal_fact_digest(facts)
    occurred_at_ms = detector_result.occurred_at_ms
    expires_at_ms = min(item.valid_until_ms for item in facts)
    identity_payload = {
        "event_spec_id": contract.event_spec_id,
        "fact_digest": fact_digest,
        "occurred_at_ms": occurred_at_ms,
        "runtime_scope_id": scope.runtime_scope_id,
        "runtime_scope_version": scope.scope_version,
        "universe_version_id": scope.universe_version_id,
    }
    canonical = json.dumps(
        identity_payload,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    signal_event_id = f"signal:{sha256(canonical).hexdigest()}"
    if (
        universe.event_spec_id != contract.event_spec_id
        or not universe.contains_candidate(scope.exchange_instrument_id)
        or scope.universe_version_id != universe.universe_version_id
        or scope.universe_digest != universe.semantic_digest()
    ):
        raise ValueError("Signal scope does not bind the loaded Universe")
    projection_run_id = None
    armed_structure_id = None
    if snapshot_context := snapshot.rsr_vcb:
        projection_run_id = snapshot_context.projection_run_id
        armed_structure_id = snapshot_context.armed_structure_id
    return StrategySignal(
        signal_event_id=signal_event_id,
        runtime_scope_id=scope.runtime_scope_id,
        runtime_scope_version=scope.scope_version,
        strategy_group_id=contract.strategy_group_id,
        strategy_version_id=contract.strategy_version_id,
        event_spec_id=contract.event_spec_id,
        exchange_instrument_id=scope.exchange_instrument_id,
        position_side=contract.position_side,
        fact_digest=fact_digest,
        universe_version_id=universe.universe_version_id,
        universe_digest=universe.semantic_digest(),
        projection_run_id=projection_run_id,
        armed_structure_id=armed_structure_id,
        occurred_at_ms=occurred_at_ms,
        observed_at_ms=max(item.observed_at_ms for item in facts),
        expires_at_ms=expires_at_ms,
        facts=facts,
    )
