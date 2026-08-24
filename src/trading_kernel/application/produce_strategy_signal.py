"""Shared live/replay evaluation and deterministic StrategySignal production."""

from __future__ import annotations

import json
from decimal import Decimal
from hashlib import sha256

from src.trading_kernel.application.ports import RuntimeScopeSnapshot
from src.trading_kernel.domain.detector import DetectorResult, detector_for
from src.trading_kernel.domain.market import MarketSnapshot
from src.trading_kernel.domain.signal import (
    SignalFactSnapshot,
    StrategySignal,
    build_signal_fact_digest,
)
from src.trading_kernel.domain.strategy_registry import RegisteredStrategyContract


def evaluate_strategy_snapshot(
    contract: RegisteredStrategyContract,
    snapshot: MarketSnapshot,
) -> DetectorResult:
    return detector_for(contract.event_spec_id).evaluate(snapshot)


def produce_strategy_signal(
    *,
    contract: RegisteredStrategyContract,
    scope: RuntimeScopeSnapshot,
    detector_result: DetectorResult,
    persisted_facts: tuple[SignalFactSnapshot, ...],
    exposure_episode_id: str | None = None,
    selection_authority_id: str | None = None,
) -> StrategySignal:
    if not detector_result.triggered or detector_result.occurred_at_ms is None:
        raise ValueError("StrategySignal requires a triggered detector result")
    if (
        detector_result.event_spec_id != contract.event_spec_id
        or scope.strategy_group_id != contract.strategy_group_id
        or scope.strategy_version_id != contract.strategy_version_id
        or scope.event_spec_id != contract.event_spec_id
        or scope.position_side != contract.position_side
        or scope.lifecycle_state != "active"
        or not scope.observation_enabled
        or not scope.entry_enabled
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
    identity_references = tuple(
        _canonical_decimal(fact.value)
        for fact in facts
        if fact.role == "identity_reference"
    )
    if contract.episode_policy == "rising_edge":
        normalized_episode_id = str(exposure_episode_id or "").strip()
        if not normalized_episode_id.startswith("episode:"):
            raise ValueError("rising-edge Signal requires an explicit Episode identity")
        if identity_references:
            raise ValueError("rising-edge Signal forbids identity-reference facts")
        resolved_episode_id = normalized_episode_id
    else:
        if exposure_episode_id is not None:
            raise ValueError("session-reference Signal owns its Episode identity")
        if not identity_references:
            raise ValueError("session-reference Signal requires identity facts")
        episode_payload = {
            "event_spec_id": contract.event_spec_id,
            "exchange_instrument_id": scope.exchange_instrument_id,
            "position_side": contract.position_side,
            "identity_references": identity_references,
        }
        episode_canonical = json.dumps(
            episode_payload,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        resolved_episode_id = f"episode:{sha256(episode_canonical).hexdigest()}"
    identity_payload = {
        "exposure_episode_id": resolved_episode_id,
    }
    canonical = json.dumps(
        identity_payload,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    signal_event_id = f"signal:{sha256(canonical).hexdigest()}"
    return StrategySignal(
        signal_event_id=signal_event_id,
        exposure_episode_id=resolved_episode_id,
        runtime_scope_id=scope.runtime_scope_id,
        runtime_scope_version=scope.scope_version,
        strategy_group_id=contract.strategy_group_id,
        strategy_version_id=contract.strategy_version_id,
        event_spec_id=contract.event_spec_id,
        universe_version_id=scope.universe_version_id,
        universe_semantic_digest=scope.universe_semantic_digest,
        exchange_instrument_id=scope.exchange_instrument_id,
        position_side=contract.position_side,
        fact_digest=fact_digest,
        occurred_at_ms=occurred_at_ms,
        observed_at_ms=max(item.observed_at_ms for item in facts),
        expires_at_ms=expires_at_ms,
        facts=facts,
        selection_authority_id=selection_authority_id,
    )


def _canonical_decimal(value: object) -> str:
    decimal_value = Decimal(str(value))
    return format(decimal_value.normalize(), "f")
