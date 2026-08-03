from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.strategy_registry import (
    RegisteredFactRequirement,
    RegisteredStrategyContract,
    build_registry_semantic_hash,
    registered_strategy_contracts,
)

EXPECTED_EVENTS = {
    ("CPM-RO-001", "CPM-LONG", "long"),
    ("MPG-001", "MPG-LONG", "long"),
    ("MI-001", "MI-LONG", "long"),
    ("SOR-001", "SOR-LONG", "long"),
    ("SOR-001", "SOR-SHORT", "short"),
    ("BRF2-001", "BRF2-SHORT", "short"),
}


def test_registry_contains_only_the_six_owner_accepted_events() -> None:
    contracts = registered_strategy_contracts()

    assert {
        (item.strategy_group_id, item.event_id, item.position_side)
        for item in contracts
    } == EXPECTED_EVENTS
    assert len(contracts) == 6


def test_registry_preserves_exact_active_semantic_contracts_without_membership() -> None:
    contracts = {item.event_id: item for item in registered_strategy_contracts()}

    assert contracts["CPM-LONG"].timeframe == "1h"
    assert contracts["CPM-LONG"].required_fact_names == (
        "htf_trend_intact",
        "reclaim_confirmed",
        "pullback_low_reference",
    )

    assert contracts["MPG-LONG"].required_fact_names == (
        "momentum_persistence_confirmed",
        "leader_strength_confirmed",
        "momentum_floor_reference",
    )

    assert contracts["MI-LONG"].required_fact_names == (
        "impulse_confirmed",
        "relative_strength_confirmed",
        "impulse_invalidation_reference",
    )

    for event_id in ("SOR-LONG", "SOR-SHORT"):
        assert contracts[event_id].timeframe == "15m"

    assert contracts["SOR-LONG"].required_fact_names == (
        "opening_range_defined_v3",
        "breakout_edge_crossed_v3",
        "opening_range_high_reference_v3",
        "opening_range_low_reference_v3",
        "session_start_ms_v3",
        "session_end_ms_v3",
    )
    assert contracts["SOR-SHORT"].required_fact_names == (
        "opening_range_defined_v3",
        "breakdown_edge_crossed_v3",
        "opening_range_low_reference_v3",
        "opening_range_high_reference_v3",
        "session_start_ms_v3",
        "session_end_ms_v3",
    )

    assert contracts["BRF2-SHORT"].required_fact_names == (
        "rally_failure_confirmed",
        "short_side_not_disabled",
        "rally_high_reference",
    )
    assert contracts["BRF2-SHORT"].disable_fact_names == (
        "strong_uptrend_disable",
    )
    forbidden_membership_fields = {
        "candidate_instruments",
        "exchange_instrument_id",
        "venue_symbol",
        "priority_rank",
    }
    assert not (
        set(RegisteredStrategyContract.model_fields) & forbidden_membership_fields
    )


def test_registry_uses_exact_versioned_semantic_identities() -> None:
    for contract in registered_strategy_contracts():
        version = 4 if contract.strategy_group_id == "SOR-001" else 3
        assert contract.strategy_version_id == f"sgv:{contract.strategy_group_id}:v{version}"
        assert contract.event_spec_id == f"event_spec:{contract.strategy_group_id}:{contract.event_id}:v{version}"


def test_registry_freezes_episode_family_and_shadow_semantics() -> None:
    contracts = {item.event_id: item for item in registered_strategy_contracts()}

    for event_id in ("CPM-LONG", "MPG-LONG", "MI-LONG"):
        assert contracts[event_id].episode_policy == "rising_edge"
        assert contracts[event_id].exposure_family == "long_continuation"
        assert contracts[event_id].shadow_horizon_bars == 24

    assert contracts["BRF2-SHORT"].episode_policy == "rising_edge"
    assert contracts["BRF2-SHORT"].exposure_family == "rally_failure_short"
    assert contracts["BRF2-SHORT"].shadow_horizon_bars == 24

    for event_id in ("SOR-LONG", "SOR-SHORT"):
        assert contracts[event_id].episode_policy == "session_reference"
        assert contracts[event_id].exposure_family == "opening_range"
        assert contracts[event_id].shadow_horizon_bars == 96


def test_registry_new_event_versions_use_new_exit_policy_identities() -> None:
    contracts = registered_strategy_contracts()

    assert len({item.exit_policy_id for item in contracts}) == len(contracts)
    assert all("portfolio-admission-v1" in item.exit_policy_id for item in contracts)


def test_registry_fact_roles_are_generic_and_type_safe() -> None:
    for role in ("protection_reference", "identity_reference", "lifecycle_reference"):
        fact = RegisteredFactRequirement(
            fact_definition_id=f"fact:{role}:v3",
            fact_name=role,
            value_type="decimal",
            role=role,
            freshness_ms=900_000,
        )
        assert fact.role == role

        with pytest.raises(ValidationError):
            RegisteredFactRequirement.model_validate(
                {**fact.model_dump(mode="python"), "value_type": "boolean"}
            )


def test_registry_status_is_frozen_semantics_and_changes_its_hash() -> None:
    contract = registered_strategy_contracts()[0]

    disabled = RegisteredStrategyContract.model_validate(
        {**contract.model_dump(mode="python"), "status": "disabled"}
    )

    assert contract.status == "active"
    assert disabled.status == "disabled"
    assert build_registry_semantic_hash((contract,)) != build_registry_semantic_hash(
        (disabled,)
    )


def test_registry_semantic_hash_is_deterministic_and_order_independent() -> None:
    contracts = registered_strategy_contracts()

    assert build_registry_semantic_hash(contracts).startswith("sha256:")
    assert build_registry_semantic_hash(contracts) == build_registry_semantic_hash(
        tuple(reversed(contracts))
    )
    assert all(
        "instrument" not in serialized and "symbol" not in serialized
        for serialized in (
            contract.model_dump_json() for contract in contracts
        )
    )


def test_registry_contract_is_frozen_and_rejects_unknown_fields() -> None:
    contract = registered_strategy_contracts()[0]

    with pytest.raises(ValidationError):
        RegisteredStrategyContract.model_validate(
            {**contract.model_dump(mode="python"), "legacy_packet_id": "forbidden"}
        )

    with pytest.raises(ValidationError):
        contract.event_id = "changed"  # type: ignore[misc]
