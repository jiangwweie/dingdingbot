from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.exit_policy import (
    BreakEvenFloorRule,
    EventExitBinding,
    ExitDecisionKind,
    ExitProfile,
    LifecycleMarketFacts,
    PreTp1GuardKind,
    RollingExtremeAtrRunnerRule,
    RunnerKind,
    RunnerRuleKind,
    TakeProfitRule,
    TimeStopMode,
    TimeStopRule,
    build_event_exit_binding,
    build_exit_profile_catalog_digest,
    calculate_cost_adjusted_break_even,
    calculate_rolling_extreme_atr_stop,
    calculate_structural_runner_stop,
    evaluate_exit_policy,
    evaluate_pre_tp1_exit,
    evaluate_profile_pre_tp1_exit,
    evaluate_profile_runner_exit,
    exit_policy_for,
    registered_event_exit_bindings,
    registered_exit_profiles,
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
    assert policy.tp1.reward_multiple == Decimal(1)
    assert policy.tp1.quantity_fraction == Decimal("0.5")
    assert policy.runner.kind is RunnerKind.STRUCTURAL_ATR
    assert policy.runner.timeframe == contract.timeframe
    assert policy.runner.structure_reference_fact == contract.protection_reference_fact
    assert policy.runner.structure_window_bars == 4
    assert policy.runner.atr_period == 14
    assert policy.runner.atr_buffer_multiple == Decimal("0.5")
    assert policy.runner.minimum_improvement_ticks == 2


def test_both_sor_v3_sides_have_registered_96_bar_time_stop() -> None:
    policies = {
        contract.event_id: exit_policy_for(contract.event_spec_id)
        for contract in registered_strategy_contracts()
    }

    assert policies["SOR-LONG"].time_stop is not None
    assert policies["SOR-SHORT"].time_stop is not None
    assert policies["SOR-LONG"].time_stop.max_holding_bars == 96
    assert policies["SOR-SHORT"].time_stop.max_holding_bars == 96
    assert all(
        policy.time_stop is None
        for event_id, policy in policies.items()
        if event_id
        not in {
            "SOR-LONG",
            "SOR-SHORT",
            "SOR-US-LONG-15M",
            "SOR-US-SHORT-15M",
        }
    )


def test_us_equity_sor_uses_eight_bar_pre_tp1_time_stop() -> None:
    policies = {
        contract.event_id: exit_policy_for(contract.event_spec_id)
        for contract in registered_strategy_contracts()
    }

    assert policies["SOR-US-LONG-15M"].time_stop is not None
    assert policies["SOR-US-SHORT-15M"].time_stop is not None
    assert policies["SOR-US-LONG-15M"].time_stop.max_holding_bars == 8
    assert policies["SOR-US-SHORT-15M"].time_stop.max_holding_bars == 8


@pytest.mark.parametrize(
    ("event_id", "latest_close", "reclaim_price", "reason"),
    [
        ("SOR-LONG", Decimal(101), Decimal(102), "failed_breakout_reclaimed"),
        ("SOR-SHORT", Decimal(99), Decimal(98), "failed_breakdown_reclaimed"),
    ],
)
def test_sor_v3_pre_tp1_reclaim_is_side_symmetric(
    event_id: str,
    latest_close: Decimal,
    reclaim_price: Decimal,
    reason: str,
) -> None:
    contract = next(
        item for item in registered_strategy_contracts() if item.event_id == event_id
    )
    decision = evaluate_pre_tp1_exit(
        policy=exit_policy_for(contract.event_spec_id),
        pre_tp1_reclaim_price=reclaim_price,
        exposure_session_end_ms=10_000,
        market_facts=LifecycleMarketFacts(
            watermark_ms=2_000,
            is_final_closed_candle=True,
            latest_close=latest_close,
            structure_reference=Decimal(100),
            atr=Decimal(1),
            holding_bars=10,
        ),
        observed_at_ms=2_000,
    )

    assert decision.kind is ExitDecisionKind.EXIT
    assert decision.reason == reason


def test_sor_v3_pre_tp1_exit_prioritizes_session_then_reclaim_then_time_stop() -> None:
    contract = next(
        item
        for item in registered_strategy_contracts()
        if item.event_id == "SOR-LONG"
    )
    facts = LifecycleMarketFacts(
        watermark_ms=10_000,
        is_final_closed_candle=True,
        latest_close=Decimal(90),
        structure_reference=Decimal(100),
        atr=Decimal(1),
        holding_bars=96,
    )

    decision = evaluate_pre_tp1_exit(
        policy=exit_policy_for(contract.event_spec_id),
        pre_tp1_reclaim_price=Decimal(102),
        exposure_session_end_ms=10_000,
        market_facts=facts,
        observed_at_ms=10_000,
    )

    assert decision.reason == "sor_session_expired"


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
        entry_average_price=Decimal(100),
        runner_quantity=Decimal(1),
        allocated_entry_fee_quote=Decimal("0.1"),
        exit_taker_fee_rate=Decimal("0.001"),
        price_tick=Decimal("0.1"),
        slippage_buffer_ticks=1,
    )

    assert result == expected


@pytest.mark.parametrize(
    ("side", "structure_reference", "expected"),
    [
        ("long", Decimal(100), Decimal("98.9")),
        ("short", Decimal(100), Decimal("101.1")),
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
        current_stop=Decimal(100),
        break_even_floor=Decimal(100),
        price_tick=Decimal("0.1"),
        last_runner_watermark_ms=1_000,
        market_facts=LifecycleMarketFacts(
            watermark_ms=2_000,
            is_final_closed_candle=True,
            latest_close=Decimal(102),
            structure_reference=Decimal(102),
            atr=Decimal(2),
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
        current_stop=Decimal(100),
        break_even_floor=Decimal(100),
        price_tick=Decimal("0.1"),
        last_runner_watermark_ms=1_000,
        market_facts=LifecycleMarketFacts(
            watermark_ms=2_000,
            is_final_closed_candle=True,
            latest_close=Decimal(102),
            structure_reference=Decimal(102),
            atr=Decimal(2),
            holding_bars=10_000,
        ),
    )

    assert decision.kind is ExitDecisionKind.MOVE_STOP
    assert decision.proposed_stop == Decimal(101)


def test_runner_ignores_open_or_duplicate_candle_and_requires_two_tick_improvement() -> None:
    contract = next(
        item
        for item in registered_strategy_contracts()
        if item.event_id == "SOR-SHORT"
    )
    policy = exit_policy_for(contract.event_spec_id)

    open_candle = evaluate_exit_policy(
        policy=policy,
        current_stop=Decimal(100),
        break_even_floor=Decimal(100),
        price_tick=Decimal("0.1"),
        last_runner_watermark_ms=1_000,
        market_facts=LifecycleMarketFacts(
            watermark_ms=2_000,
            is_final_closed_candle=False,
            latest_close=Decimal(98),
            structure_reference=Decimal(98),
            atr=Decimal(2),
            holding_bars=10,
        ),
    )
    duplicate = evaluate_exit_policy(
        policy=policy,
        current_stop=Decimal(100),
        break_even_floor=Decimal(100),
        price_tick=Decimal("0.1"),
        last_runner_watermark_ms=2_000,
        market_facts=LifecycleMarketFacts(
            watermark_ms=2_000,
            is_final_closed_candle=True,
            latest_close=Decimal(98),
            structure_reference=Decimal(98),
            atr=Decimal(2),
            holding_bars=10,
        ),
    )
    too_small = evaluate_exit_policy(
        policy=policy,
        current_stop=Decimal(100),
        break_even_floor=Decimal(100),
        price_tick=Decimal("0.1"),
        last_runner_watermark_ms=1_000,
        market_facts=LifecycleMarketFacts(
            watermark_ms=2_000,
            is_final_closed_candle=True,
            latest_close=Decimal("99.8"),
            structure_reference=Decimal("99.8"),
            atr=Decimal("0.2"),
            holding_bars=10,
        ),
    )

    assert open_candle.kind is ExitDecisionKind.NO_CHANGE
    assert duplicate.kind is ExitDecisionKind.NO_CHANGE
    assert too_small.kind is ExitDecisionKind.NO_CHANGE


def test_exit_profile_hash_covers_pre_tp1_guards() -> None:
    baseline = _profile(pre_tp1_guards=())
    guarded = _profile(
        pre_tp1_guards=(PreTp1GuardKind.RECLAIM_REFERENCE,)
    )

    assert baseline.semantic_hash() != guarded.semantic_hash()


def test_event_exit_binding_hash_covers_exact_profile_identity() -> None:
    profile = _profile()
    first = build_event_exit_binding(
        exit_binding_id="exit-binding:event:test:v1",
        binding_version=1,
        event_spec_id="event_spec:test:v1",
        exit_profile_id=profile.exit_profile_id,
        exit_profile_semantic_hash=profile.semantic_hash(),
        activation_reason="owner_frozen_v1",
        created_at_ms=1_000,
    )
    changed = build_event_exit_binding(
        exit_binding_id="exit-binding:event:test:v2",
        binding_version=2,
        event_spec_id="event_spec:test:v1",
        exit_profile_id=profile.exit_profile_id,
        exit_profile_semantic_hash="sha256:" + "f" * 64,
        activation_reason="owner_frozen_v1",
        created_at_ms=2_000,
    )

    assert isinstance(first, EventExitBinding)
    assert first.binding_semantic_hash != changed.binding_semantic_hash


def test_exit_profile_is_frozen() -> None:
    profile = _profile()

    with pytest.raises(ValidationError):
        profile.position_side = "short"  # type: ignore[misc]


def test_profile_pre_tp1_precedence_is_session_reclaim_absolute_then_pre_tp1() -> None:
    profile = _profile(
        time_stop=TimeStopRule(
            max_holding_bars=12,
            mode=TimeStopMode.ABSOLUTE,
        ),
        pre_tp1_guards=(
            PreTp1GuardKind.RECLAIM_REFERENCE,
            PreTp1GuardKind.SESSION_EXPIRY,
        ),
    )
    facts = LifecycleMarketFacts(
        watermark_ms=10_000,
        is_final_closed_candle=True,
        latest_close=Decimal(90),
        structure_reference=Decimal(100),
        atr=Decimal(1),
        holding_bars=12,
    )

    decision = evaluate_profile_pre_tp1_exit(
        profile=profile,
        pre_tp1_reclaim_price=Decimal(95),
        exposure_session_end_ms=10_000,
        market_facts=facts,
        observed_at_ms=10_000,
    )

    assert decision.reason == "session_expired"


def test_pre_tp1_time_stop_uses_11_12_boundary() -> None:
    profile = _profile(
        time_stop=TimeStopRule(
            max_holding_bars=12,
            mode=TimeStopMode.PRE_TP1,
        )
    )

    before = evaluate_profile_pre_tp1_exit(
        profile=profile,
        market_facts=_market_facts(holding_bars=11),
        observed_at_ms=2_000,
    )
    hit = evaluate_profile_pre_tp1_exit(
        profile=profile,
        market_facts=_market_facts(holding_bars=12),
        observed_at_ms=2_000,
    )

    assert before.kind is ExitDecisionKind.NO_CHANGE
    assert hit.kind is ExitDecisionKind.EXIT
    assert hit.reason == "pre_tp1_time_stop_hit"


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (TimeStopMode.PRE_TP1, ExitDecisionKind.MOVE_STOP),
        (TimeStopMode.ABSOLUTE, ExitDecisionKind.EXIT),
    ],
)
def test_runner_ignores_pre_tp1_time_stop_but_honors_absolute(
    mode: TimeStopMode,
    expected: ExitDecisionKind,
) -> None:
    profile = _profile(
        time_stop=TimeStopRule(max_holding_bars=12, mode=mode)
    )

    decision = evaluate_profile_runner_exit(
        profile=profile,
        current_stop=Decimal(100),
        break_even_floor=Decimal(100),
        price_tick=Decimal("0.1"),
        last_runner_watermark_ms=1_000,
        market_facts=_market_facts(holding_bars=12),
    )

    assert decision.kind is expected


@pytest.mark.parametrize(
    ("side", "expected"),
    [("long", Decimal("98.9")), ("short", Decimal("101.1"))],
)
def test_rolling_extreme_atr_rule_has_truthful_identity(
    side: str,
    expected: Decimal,
) -> None:
    assert RunnerRuleKind.ROLLING_EXTREME_ATR.value == "rolling_extreme_atr"
    assert calculate_rolling_extreme_atr_stop(
        side=side,
        rolling_extreme=Decimal(100),
        atr=Decimal("2.1"),
        atr_buffer_multiple=Decimal("0.5"),
        price_tick=Decimal("0.1"),
    ) == expected


def test_owner_frozen_v1_catalog_is_complete_and_explicit() -> None:
    profiles = registered_exit_profiles()
    bindings = registered_event_exit_bindings()

    assert len(profiles) == 8
    assert len({item.exit_profile_id for item in profiles}) == 8
    assert len(bindings) == 8
    assert len({item.event_spec_id for item in bindings}) == 8
    assert {item.exit_profile_id for item in bindings} == {
        item.exit_profile_id for item in profiles
    }
    assert all(item.profile_schema_version == "exit_profile_v1" for item in profiles)
    assert all(item.tp1.reward_multiple == Decimal(1) for item in profiles)
    assert all(item.tp1.execution_style == "limit_gtc" for item in profiles)
    assert all(item.tp1.market_fallback_allowed is False for item in profiles)
    assert all(item.break_even_floor.slippage_buffer_ticks == 2 for item in profiles)
    assert all(
        item.break_even_floor.minimum_improvement_ticks == 2 for item in profiles
    )
    assert all(item.runner.atr_period == 14 for item in profiles)
    assert all(item.runner.minimum_improvement_ticks == 2 for item in profiles)

    momentum = next(
        item for item in profiles if "momentum-tail" in item.exit_profile_id
    )
    assert momentum.tp1.quantity_fraction == Decimal("0.33")
    assert momentum.runner.lookback_bars == 5
    assert momentum.runner.atr_buffer_multiple == Decimal("0.75")


def test_registered_binding_hashes_exact_profile_payloads() -> None:
    profiles = {item.exit_profile_id: item for item in registered_exit_profiles()}

    for binding in registered_event_exit_bindings():
        assert (
            binding.exit_profile_semantic_hash
            == profiles[binding.exit_profile_id].semantic_hash()
        )


def test_exit_profile_catalog_digest_is_deterministic() -> None:
    assert build_exit_profile_catalog_digest() == build_exit_profile_catalog_digest()
    assert build_exit_profile_catalog_digest().startswith("sha256:")


def _profile(
    *,
    time_stop: TimeStopRule | None = None,
    pre_tp1_guards: tuple[PreTp1GuardKind, ...] = (),
) -> ExitProfile:
    return ExitProfile(
        exit_profile_id="exit-profile:test:1h:long:v1",
        exit_profile_version=1,
        profile_schema_version="exit_profile_v1",
        position_side="long",
        tp1=TakeProfitRule(
            reward_multiple=Decimal(1),
            quantity_fraction=Decimal("0.5"),
        ),
        break_even_floor=BreakEvenFloorRule(
            slippage_buffer_ticks=2,
            minimum_improvement_ticks=2,
        ),
        runner=RollingExtremeAtrRunnerRule(
            timeframe="1h",
            lookback_bars=4,
            atr_period=14,
            atr_buffer_multiple=Decimal("0.5"),
            minimum_improvement_ticks=2,
        ),
        time_stop=time_stop,
        pre_tp1_guards=pre_tp1_guards,
    )


def _market_facts(*, holding_bars: int) -> LifecycleMarketFacts:
    return LifecycleMarketFacts(
        watermark_ms=2_000,
        is_final_closed_candle=True,
        latest_close=Decimal(102),
        structure_reference=Decimal(102),
        atr=Decimal(2),
        holding_bars=holding_bars,
    )
