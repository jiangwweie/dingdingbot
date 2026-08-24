from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.signal import (
    SignalFactSnapshot,
    StrategySignal,
    build_signal_fact_digest,
)
from tests.trading_kernel.support.signals import make_signal, make_signal_facts


def test_strategy_signal_is_immutable_and_rejects_capital_or_order_terms() -> None:
    signal = make_signal()

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
        make_signal(signal_event_id=" ")
    with pytest.raises(ValidationError):
        make_signal(runtime_scope_version=0)
    with pytest.raises(ValidationError):
        make_signal(occurred_at_ms=1_000, expires_at_ms=1_000)
    with pytest.raises(ValidationError):
        make_signal(occurred_at_ms=1_000, observed_at_ms=999)
    with pytest.raises(ValidationError):
        make_signal(observed_at_ms=2_000, expires_at_ms=2_000)


def test_strategy_signal_requires_exact_universe_lineage() -> None:
    signal = make_signal()

    assert signal.universe_version_id == "universe:SOR-SHORT:3"
    assert signal.universe_semantic_digest == "sha256:" + "a" * 64

    payload = signal.model_dump(mode="python")
    payload.pop("universe_version_id")
    with pytest.raises(ValidationError):
        StrategySignal.model_validate(payload)

    with pytest.raises(ValidationError):
        make_signal(universe_version_id=" ")
    with pytest.raises(ValidationError):
        make_signal(universe_semantic_digest="sha256:" + "A" * 64)


def test_strategy_signal_requires_an_immutable_exposure_episode() -> None:
    signal = make_signal()

    assert signal.exposure_episode_id == "episode:" + "b" * 64
    with pytest.raises(ValidationError):
        make_signal(exposure_episode_id=" ")


def test_strategy_signal_accepts_optional_selection_authority_lineage() -> None:
    signal = make_signal(selection_authority_id="authority:test:1")

    assert signal.selection_authority_id == "authority:test:1"
    assert make_signal(selection_authority_id=" ").selection_authority_id is None


def test_strategy_signal_requires_exact_nonduplicate_fact_bundle() -> None:
    facts = make_signal_facts()
    signal = make_signal(facts=facts)

    assert signal.fact_digest == build_signal_fact_digest(facts)
    assert signal.facts == tuple(sorted(facts, key=lambda item: item.fact_definition_id))

    duplicate_payload = signal.model_dump(mode="python")
    duplicate_payload["facts"] = (facts[0], facts[0], facts[2])
    with pytest.raises(ValidationError):
        StrategySignal.model_validate(duplicate_payload)
    with pytest.raises(ValidationError):
        make_signal(fact_digest="sha256:" + "0" * 64)
    with pytest.raises(ValidationError):
        make_signal(facts=())


def test_fact_roles_fail_closed_for_condition_and_reference_semantics() -> None:
    facts = make_signal_facts()

    with pytest.raises(ValidationError):
        make_signal(
            facts=(facts[0].model_copy(update={"satisfied": False}), *facts[1:])
        )
    with pytest.raises(ValidationError):
        make_signal(
            facts=(*facts[:3], facts[3].model_copy(update={"satisfied": False}))
        )
    with pytest.raises(ValidationError):
        make_signal(facts=facts[:3])


def test_identity_and_lifecycle_reference_facts_are_decimal_and_not_conditions() -> None:
    facts = make_signal_facts()
    signal = make_signal(facts=facts)

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
    facts = make_signal_facts()

    assert build_signal_fact_digest(facts) == build_signal_fact_digest(
        tuple(reversed(facts))
    )
    assert len(build_signal_fact_digest(facts)) == 71
