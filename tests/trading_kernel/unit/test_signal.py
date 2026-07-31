from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.signal import (
    SignalFactSnapshot,
    StrategySignal,
    build_signal_fact_digest,
)


def test_strategy_signal_is_immutable_and_rejects_capital_or_order_terms() -> None:
    signal = _signal()

    with pytest.raises(ValidationError):
        signal.signal_event_id = "changed"  # type: ignore[misc]

    forbidden = {
        "quantity": "0.01",
        "notional": "100",
        "leverage": "5",
        "risk_at_stop": "2.5",
        "entry_order_type": "market",
        "entry_limit_price": "100",
        "initial_stop_price": "99",
        "take_profit_prices": ["105"],
        "terms": {"quantity": "0.01"},
    }
    payload = signal.model_dump(mode="json")
    for field_name, value in forbidden.items():
        with pytest.raises(ValidationError):
            StrategySignal.model_validate({**payload, field_name: value})


def test_strategy_signal_rejects_blank_identity_and_invalid_deadline() -> None:
    with pytest.raises(ValidationError):
        _signal(signal_event_id=" ")
    with pytest.raises(ValidationError):
        _signal(runtime_scope_version=0)
    with pytest.raises(ValidationError):
        _signal(occurred_at_ms=1_000, expires_at_ms=1_000)
    with pytest.raises(ValidationError):
        _signal(occurred_at_ms=1_000, observed_at_ms=999)
    with pytest.raises(ValidationError):
        _signal(observed_at_ms=2_000, expires_at_ms=2_000)


def test_strategy_signal_requires_exact_universe_lineage() -> None:
    signal = _signal()

    assert signal.universe_version_id == "universe:SOR-SHORT:3"
    assert signal.universe_semantic_digest == "sha256:" + "a" * 64

    payload = signal.model_dump(mode="python")
    payload.pop("universe_version_id")
    with pytest.raises(ValidationError):
        StrategySignal.model_validate(payload)

    with pytest.raises(ValidationError):
        _signal(universe_version_id=" ")
    with pytest.raises(ValidationError):
        _signal(universe_semantic_digest="sha256:" + "A" * 64)


def test_strategy_signal_requires_an_immutable_exposure_episode() -> None:
    signal = _signal()

    assert signal.exposure_episode_id == "episode:" + "b" * 64
    with pytest.raises(ValidationError):
        _signal(exposure_episode_id=" ")


def test_strategy_signal_requires_exact_nonduplicate_fact_bundle() -> None:
    facts = _facts()
    signal = _signal(facts=facts)

    assert signal.fact_digest == build_signal_fact_digest(facts)
    assert signal.facts == tuple(sorted(facts, key=lambda item: item.fact_definition_id))

    duplicate_payload = signal.model_dump(mode="python")
    duplicate_payload["facts"] = (facts[0], facts[0], facts[2])
    with pytest.raises(ValidationError):
        StrategySignal.model_validate(duplicate_payload)
    with pytest.raises(ValidationError):
        _signal(fact_digest="sha256:" + "0" * 64)
    with pytest.raises(ValidationError):
        _signal(facts=())


def test_fact_roles_fail_closed_for_condition_and_reference_semantics() -> None:
    facts = _facts()

    with pytest.raises(ValidationError):
        _signal(
            facts=(facts[0].model_copy(update={"satisfied": False}), *facts[1:])
        )
    with pytest.raises(ValidationError):
        _signal(
            facts=(*facts[:3], facts[3].model_copy(update={"satisfied": False}))
        )
    with pytest.raises(ValidationError):
        _signal(facts=facts[:3])


def test_identity_and_lifecycle_reference_facts_are_decimal_and_not_conditions() -> None:
    facts = _facts()
    signal = _signal(facts=facts)

    assert {fact.role for fact in signal.facts} >= {
        "identity_reference",
        "lifecycle_reference",
    }

    identity_fact = next(fact for fact in facts if fact.role == "identity_reference")
    with pytest.raises(ValidationError):
        SignalFactSnapshot.model_validate(
            {**identity_fact.model_dump(mode="python"), "value": True}
        )
    with pytest.raises(ValidationError):
        SignalFactSnapshot.model_validate(
            {**facts[0].model_dump(mode="python"), "value": "1"}
        )


def test_fact_digest_is_canonical_across_input_order() -> None:
    facts = _facts()

    assert build_signal_fact_digest(facts) == build_signal_fact_digest(
        tuple(reversed(facts))
    )
    assert len(build_signal_fact_digest(facts)) == 71


def _signal(
    *,
    signal_event_id: str = "signal-1",
    runtime_scope_version: int = 1,
    occurred_at_ms: int = 1_000,
    observed_at_ms: int = 1_001,
    expires_at_ms: int = 2_000,
    facts: tuple[SignalFactSnapshot, ...] | None = None,
    fact_digest: str | None = None,
    universe_version_id: str = "universe:SOR-SHORT:3",
    universe_semantic_digest: str = "sha256:" + "a" * 64,
    exposure_episode_id: str = "episode:" + "b" * 64,
) -> StrategySignal:
    selected_facts = _facts() if facts is None else facts
    return StrategySignal(
        signal_event_id=signal_event_id,
        exposure_episode_id=exposure_episode_id,
        runtime_scope_id="scope-sor-btc-short",
        runtime_scope_version=runtime_scope_version,
        strategy_group_id="SOR-001",
        strategy_version_id="sgv:SOR-001:v3",
        event_spec_id="event_spec:SOR-001:SOR-SHORT:v3",
        universe_version_id=universe_version_id,
        universe_semantic_digest=universe_semantic_digest,
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side="short",
        fact_digest=fact_digest or build_signal_fact_digest(selected_facts),
        occurred_at_ms=occurred_at_ms,
        observed_at_ms=observed_at_ms,
        expires_at_ms=expires_at_ms,
        facts=selected_facts,
    )


def _facts() -> tuple[SignalFactSnapshot, ...]:
    return (
        SignalFactSnapshot(
            fact_definition_id="fact:breakdown_confirmed:v1",
            role="condition",
            value=True,
            satisfied=True,
            observed_at_ms=1_000,
            valid_until_ms=2_000,
            projection_version=1,
        ),
        SignalFactSnapshot(
            fact_definition_id="fact:session_start_ms_v3:v3",
            role="identity_reference",
            value="1000",
            satisfied=True,
            observed_at_ms=1_000,
            valid_until_ms=2_000,
            projection_version=1,
        ),
        SignalFactSnapshot(
            fact_definition_id="fact:session_end_ms_v3:v3",
            role="lifecycle_reference",
            value="86401000",
            satisfied=True,
            observed_at_ms=1_000,
            valid_until_ms=2_000,
            projection_version=1,
        ),
        SignalFactSnapshot(
            fact_definition_id="fact:opening_range_high_reference_v3:v3",
            role="protection_reference",
            value="10100.0",
            satisfied=True,
            observed_at_ms=1_000,
            valid_until_ms=2_000,
            projection_version=1,
        ),
    )
