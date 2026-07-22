from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.domain.exit_policy import (
    ExitDecisionKind,
    LifecycleMarketFacts,
    RunnerKind,
    calculate_cost_adjusted_break_even,
    calculate_structural_runner_stop,
    exit_policy_for,
    evaluate_exit_policy,
    split_tp1_quantity,
)
from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts


@pytest.mark.parametrize(
    "event_id",
    [
        "CPM-LONG",
        "MPG-LONG",
        "MI-LONG",
        "SOR-LONG",
        "SOR-SHORT",
        "BRF2-SHORT",
    ],
)
def test_each_registered_event_has_one_current_exit_policy(event_id: str) -> None:
    contract = next(
        item for item in registered_strategy_contracts() if item.event_id == event_id
    )

    policy = exit_policy_for(contract.event_spec_id)

    assert policy.exit_policy_id == contract.exit_policy_id
    assert policy.event_spec_id == contract.event_spec_id
    assert policy.position_side == contract.position_side
    assert policy.tp1.reward_multiple == Decimal("1")
    assert policy.tp1.quantity_fraction == Decimal("0.5")
    assert policy.runner.kind is RunnerKind.STRUCTURAL_ATR
    assert policy.runner.timeframe == contract.timeframe
    assert policy.runner.structure_reference_fact == contract.protection_reference_fact
    assert policy.runner.structure_window_bars == 4
    assert policy.runner.atr_period == 14
    assert policy.runner.atr_buffer_multiple == Decimal("0.5")
    assert policy.runner.minimum_improvement_ticks == 2


def test_only_sor_long_retains_registered_96_bar_time_stop() -> None:
    policies = {
        contract.event_id: exit_policy_for(contract.event_spec_id)
        for contract in registered_strategy_contracts()
    }

    assert policies["SOR-LONG"].time_stop is not None
    assert policies["SOR-LONG"].time_stop.max_holding_bars == 96
    assert all(
        policy.time_stop is None
        for event_id, policy in policies.items()
        if event_id != "SOR-LONG"
    )


def test_tp1_split_is_step_aligned_and_preserves_runner_quantity() -> None:
    split = split_tp1_quantity(
        total_quantity=Decimal("0.005"),
        quantity_step=Decimal("0.001"),
        quantity_fraction=Decimal("0.5"),
    )

    assert split.tp1_quantity == Decimal("0.002")
    assert split.runner_quantity == Decimal("0.003")


@pytest.mark.parametrize(
    ("side", "expected"),
    [
        ("long", Decimal("100.4")),
        ("short", Decimal("99.7")),
    ],
)
def test_cost_adjusted_break_even_covers_entry_fee_exit_fee_and_slippage(
    side: str,
    expected: Decimal,
) -> None:
    result = calculate_cost_adjusted_break_even(
        side=side,
        entry_average_price=Decimal("100"),
        runner_quantity=Decimal("1"),
        allocated_entry_fee_quote=Decimal("0.1"),
        exit_taker_fee_rate=Decimal("0.001"),
        price_tick=Decimal("0.1"),
        slippage_buffer_ticks=1,
    )

    assert result == expected


@pytest.mark.parametrize(
    ("side", "structure_reference", "expected"),
    [
        ("long", Decimal("100"), Decimal("98.9")),
        ("short", Decimal("100"), Decimal("101.1")),
    ],
)
def test_structural_atr_runner_stop_uses_side_safe_tick_rounding(
    side: str,
    structure_reference: Decimal,
    expected: Decimal,
) -> None:
    result = calculate_structural_runner_stop(
        side=side,
        structure_reference=structure_reference,
        atr=Decimal("2.1"),
        atr_buffer_multiple=Decimal("0.5"),
        price_tick=Decimal("0.1"),
    )

    assert result == expected


def test_sor_long_time_stop_closes_runner_at_96_final_bars() -> None:
    contract = next(
        item
        for item in registered_strategy_contracts()
        if item.event_id == "SOR-LONG"
    )
    decision = evaluate_exit_policy(
        policy=exit_policy_for(contract.event_spec_id),
        current_stop=Decimal("100"),
        break_even_floor=Decimal("100"),
        price_tick=Decimal("0.1"),
        last_runner_watermark_ms=1_000,
        market_facts=LifecycleMarketFacts(
            watermark_ms=2_000,
            is_final_closed_candle=True,
            structure_reference=Decimal("102"),
            atr=Decimal("2"),
            holding_bars=96,
        ),
    )

    assert decision.kind is ExitDecisionKind.EXIT
    assert decision.reason == "time_stop_hit"


def test_non_sor_event_does_not_invent_time_stop() -> None:
    contract = next(
        item
        for item in registered_strategy_contracts()
        if item.event_id == "CPM-LONG"
    )
    decision = evaluate_exit_policy(
        policy=exit_policy_for(contract.event_spec_id),
        current_stop=Decimal("100"),
        break_even_floor=Decimal("100"),
        price_tick=Decimal("0.1"),
        last_runner_watermark_ms=1_000,
        market_facts=LifecycleMarketFacts(
            watermark_ms=2_000,
            is_final_closed_candle=True,
            structure_reference=Decimal("102"),
            atr=Decimal("2"),
            holding_bars=10_000,
        ),
    )

    assert decision.kind is ExitDecisionKind.MOVE_STOP
    assert decision.proposed_stop == Decimal("101")


def test_runner_ignores_open_or_duplicate_candle_and_requires_two_tick_improvement() -> None:
    contract = next(
        item
        for item in registered_strategy_contracts()
        if item.event_id == "SOR-SHORT"
    )
    policy = exit_policy_for(contract.event_spec_id)

    open_candle = evaluate_exit_policy(
        policy=policy,
        current_stop=Decimal("100"),
        break_even_floor=Decimal("100"),
        price_tick=Decimal("0.1"),
        last_runner_watermark_ms=1_000,
        market_facts=LifecycleMarketFacts(
            watermark_ms=2_000,
            is_final_closed_candle=False,
            structure_reference=Decimal("98"),
            atr=Decimal("2"),
            holding_bars=10,
        ),
    )
    duplicate = evaluate_exit_policy(
        policy=policy,
        current_stop=Decimal("100"),
        break_even_floor=Decimal("100"),
        price_tick=Decimal("0.1"),
        last_runner_watermark_ms=2_000,
        market_facts=LifecycleMarketFacts(
            watermark_ms=2_000,
            is_final_closed_candle=True,
            structure_reference=Decimal("98"),
            atr=Decimal("2"),
            holding_bars=10,
        ),
    )
    too_small = evaluate_exit_policy(
        policy=policy,
        current_stop=Decimal("100"),
        break_even_floor=Decimal("100"),
        price_tick=Decimal("0.1"),
        last_runner_watermark_ms=1_000,
        market_facts=LifecycleMarketFacts(
            watermark_ms=2_000,
            is_final_closed_candle=True,
            structure_reference=Decimal("99.8"),
            atr=Decimal("0.2"),
            holding_bars=10,
        ),
    )

    assert open_candle.kind is ExitDecisionKind.NO_CHANGE
    assert duplicate.kind is ExitDecisionKind.NO_CHANGE
    assert too_small.kind is ExitDecisionKind.NO_CHANGE
