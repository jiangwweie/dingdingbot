from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.strategy_registry import (
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


def test_registry_preserves_exact_v2_fact_and_candidate_scope() -> None:
    contracts = {item.event_id: item for item in registered_strategy_contracts()}

    assert contracts["CPM-LONG"].timeframe == "1h"
    assert contracts["CPM-LONG"].required_fact_names == (
        "htf_trend_intact",
        "reclaim_confirmed",
        "pullback_low_reference",
    )
    assert contracts["CPM-LONG"].venue_symbols == (
        "ETHUSDT",
        "SOLUSDT",
        "AVAXUSDT",
        "SUIUSDT",
    )

    assert contracts["MPG-LONG"].required_fact_names == (
        "momentum_persistence_confirmed",
        "leader_strength_confirmed",
        "momentum_floor_reference",
    )
    assert contracts["MPG-LONG"].venue_symbols == (
        "OPUSDT",
        "SOLUSDT",
        "AVAXUSDT",
        "SUIUSDT",
    )

    assert contracts["MI-LONG"].required_fact_names == (
        "impulse_confirmed",
        "relative_strength_confirmed",
        "impulse_invalidation_reference",
    )
    assert contracts["MI-LONG"].venue_symbols == (
        "AVAXUSDT",
        "ETHUSDT",
        "SOLUSDT",
    )

    for event_id in ("SOR-LONG", "SOR-SHORT"):
        assert contracts[event_id].timeframe == "15m"
        assert contracts[event_id].venue_symbols == (
            "ETHUSDT",
            "SOLUSDT",
            "AVAXUSDT",
            "BTCUSDT",
        )

    assert contracts["SOR-LONG"].required_fact_names == (
        "opening_range_defined",
        "breakout_confirmed",
        "opening_range_low_reference",
    )
    assert contracts["SOR-SHORT"].required_fact_names == (
        "opening_range_defined",
        "breakdown_confirmed",
        "opening_range_high_reference",
    )

    assert contracts["BRF2-SHORT"].required_fact_names == (
        "rally_failure_confirmed",
        "short_side_not_disabled",
        "rally_high_reference",
    )
    assert contracts["BRF2-SHORT"].disable_fact_names == (
        "strong_uptrend_disable",
    )
    assert contracts["BRF2-SHORT"].venue_symbols == (
        "BTCUSDT",
        "AVAXUSDT",
        "ETHUSDT",
    )


def test_registry_uses_exact_versioned_identities_and_priority_order() -> None:
    for contract in registered_strategy_contracts():
        assert contract.strategy_version_id == (
            f"sgv:{contract.strategy_group_id}:v2"
        )
        assert contract.event_spec_id == (
            f"event_spec:{contract.strategy_group_id}:{contract.event_id}:v2"
        )
        assert [item.priority_rank for item in contract.candidate_instruments] == list(
            range(1, len(contract.candidate_instruments) + 1)
        )
        assert all(
            item.exchange_instrument_id
            == f"binance-usdm:{item.venue_symbol}:perpetual"
            for item in contract.candidate_instruments
        )


def test_registry_semantic_hash_is_deterministic_and_order_independent() -> None:
    contracts = registered_strategy_contracts()

    assert build_registry_semantic_hash(contracts).startswith("sha256:")
    assert build_registry_semantic_hash(contracts) == build_registry_semantic_hash(
        tuple(reversed(contracts))
    )


def test_registry_contract_is_frozen_and_rejects_unknown_fields() -> None:
    contract = registered_strategy_contracts()[0]

    with pytest.raises(ValidationError):
        RegisteredStrategyContract.model_validate(
            {**contract.model_dump(mode="python"), "legacy_packet_id": "forbidden"}
        )

    with pytest.raises(ValidationError):
        contract.event_id = "changed"  # type: ignore[misc]
