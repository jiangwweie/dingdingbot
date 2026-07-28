from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.strategy_universe import (
    StrategyUniverseVersion,
    build_strategy_universe,
)


def test_universe_canonicalizes_member_order_without_creating_priority() -> None:
    universe = _universe(
        (
            "binance-usdm:SOLUSDT:perpetual",
            "binance-usdm:BTCUSDT:perpetual",
        )
    )

    assert universe.exchange_instrument_ids == (
        "binance-usdm:BTCUSDT:perpetual",
        "binance-usdm:SOLUSDT:perpetual",
    )
    assert "priority" not in StrategyUniverseVersion.model_fields


def test_universe_digest_is_independent_of_submission_order_and_version_identity() -> None:
    first = _universe(
        (
            "binance-usdm:SOLUSDT:perpetual",
            "binance-usdm:BTCUSDT:perpetual",
        )
    )
    second = build_strategy_universe(
        universe_version_id="universe:SOR-LONG:2",
        strategy_group_id="SOR-001",
        event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
        universe_version=2,
        exchange_instrument_ids=(
            "binance-usdm:BTCUSDT:perpetual",
            "binance-usdm:SOLUSDT:perpetual",
        ),
        installed_at_ms=2_000,
    )

    assert first.universe_version_id != second.universe_version_id
    assert first.semantic_digest == second.semantic_digest


@pytest.mark.parametrize(
    "members",
    (
        (),
        tuple(f"binance-usdm:ASSET{index}USDT:perpetual" for index in range(11)),
        (
            "binance-usdm:BTCUSDT:perpetual",
            "binance-usdm:BTCUSDT:perpetual",
        ),
    ),
)
def test_universe_rejects_invalid_member_cardinality_or_duplicates(
    members: tuple[str, ...],
) -> None:
    with pytest.raises(ValidationError):
        _universe(members)


def test_universe_is_frozen_and_forbids_unknown_fields() -> None:
    universe = _universe(("binance-usdm:BTCUSDT:perpetual",))

    with pytest.raises(ValidationError):
        StrategyUniverseVersion.model_validate(
            {**universe.model_dump(), "priority_rank": 1}
        )
    with pytest.raises(ValidationError):
        universe.universe_version = 3  # type: ignore[misc]


def _universe(members: tuple[str, ...]) -> StrategyUniverseVersion:
    return build_strategy_universe(
        universe_version_id="universe:SOR-LONG:1",
        strategy_group_id="SOR-001",
        event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
        universe_version=1,
        exchange_instrument_ids=members,
        installed_at_ms=1_000,
    )
