from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.domain.ticket_exit_policy import (
    ExitDecisionKind,
    ExitEvaluationInput,
    ExitMarketFact,
    PolicyFamily,
    RewardBasis,
    RunnerBreakEvenFloorRule,
    TicketExitExecutionSnapshot,
    TicketExitPolicySnapshot,
    TicketTakeProfitLeg,
    TpExecutionStyle,
    calculate_runner_break_even_floor,
    canonical_payload_hash,
    evaluate_exit_policy,
)


def _policy_payload(*, side: str = "long", family: str = "right_tail_runner") -> dict:
    runner_rule = (
        {
            "kind": "structural_atr",
            "timeframe": "15m",
            "structure_rule": "confirmed_higher_low",
            "structure_window_bars": 4,
            "atr_period": 14,
            "atr_buffer_multiple": "1.5",
            "minimum_improvement_ticks": 2,
        }
        if family == "right_tail_runner"
        else {"kind": "no_runner"}
    )
    take_profit_legs = (
        [
            {
                "role": "TP1",
                "reward_multiple": "1",
                "quantity_fraction": "0.5",
                "execution_style": "limit_gtc",
                "market_fallback_allowed": False,
            }
        ]
        if family != "lifecycle_only"
        else []
    )
    if family == "fixed_targets":
        runner_rule = {"kind": "no_runner"}
        take_profit_legs = [
            {**take_profit_legs[0], "quantity_fraction": "0.5"},
            {
                "role": "TP2",
                "reward_multiple": "2",
                "quantity_fraction": "0.5",
                "execution_style": "passive_limit_gtx",
                "market_fallback_allowed": False,
            },
        ]
    return {
        "exit_policy_id": "sor-right-tail-v1",
        "exit_policy_version": "1.0.0",
        "strategy_group_id": "SOR-001",
        "strategy_version": "1.0.0",
        "event_spec_id": "SOR-LONG" if side == "long" else "SOR-SHORT",
        "event_spec_version": "1.0.0",
        "side": side,
        "policy_family": family,
        "reward_basis": "actual_entry_r",
        "take_profit_legs": take_profit_legs,
        "tp_completion_tolerance_qty_steps": 1,
        "post_tp1_floor_rule": (
            {
                "kind": "runner_leg_cost_adjusted_break_even",
                "trigger": "tp1_target_quantity_complete",
                "exit_fee_basis": "conservative_taker",
                "slippage_buffer_ticks": 2,
                "minimum_improvement_ticks": 2,
            }
            if family == "right_tail_runner"
            else None
        ),
        "invalidation_rules": [
            {
                "kind": "reference_price_cross",
                "rule_id": "opening_range_reclaim_failed",
                "trigger": (
                    "close_below_or_equal" if side == "long" else "close_above_or_equal"
                ),
                "reference_key": "opening_range_boundary",
            }
        ],
        "time_stop_rule": {
            "kind": "max_holding_bars",
            "max_holding_bars": 24,
        },
        "runner_rule": runner_rule,
    }


def _policy(*, side: str = "long", family: str = "right_tail_runner"):
    return TicketExitPolicySnapshot.with_canonical_hash(
        _policy_payload(side=side, family=family)
    )


def _evaluation(
    *,
    side: str = "long",
    position_qty: str = "0.5",
    current_stop: str | None = "95",
    protection_exact: bool = True,
    tp1_completion_state: str = "unfilled",
    immediate_floor: str | None = None,
    market_fact: ExitMarketFact | None = None,
) -> ExitEvaluationInput:
    return ExitEvaluationInput(
        policy=_policy(side=side),
        ticket_id="ticket-1",
        exchange_instrument_id="ETHUSDT",
        venue_id="binance_usdm",
        side=side,
        position_qty=Decimal(position_qty),
        current_runner_stop=(Decimal(current_stop) if current_stop is not None else None),
        active_runner_generation=1 if current_stop is not None else None,
        protection_identity_exact=protection_exact,
        tp1_completion_state=tp1_completion_state,
        immediate_runner_floor=(
            Decimal(immediate_floor) if immediate_floor is not None else None
        ),
        minimum_price_tick=Decimal("0.1"),
        market_fact=market_fact,
        evaluated_watermark_ms=1_720_000_000_000,
    )


def test_policy_families_and_tp_execution_styles_are_typed():
    assert _policy().policy_family is PolicyFamily.RIGHT_TAIL_RUNNER
    assert _policy(family="fixed_targets").policy_family is PolicyFamily.FIXED_TARGETS
    assert _policy(family="lifecycle_only").policy_family is PolicyFamily.LIFECYCLE_ONLY
    assert _policy().reward_basis is RewardBasis.ACTUAL_ENTRY_R
    assert _policy().take_profit_legs[0].execution_style is TpExecutionStyle.LIMIT_GTC
    assert (
        _policy(family="fixed_targets").take_profit_legs[1].execution_style
        is TpExecutionStyle.PASSIVE_LIMIT_GTX
    )


def test_policy_hash_is_canonical_and_mapping_order_independent():
    left = {"b": Decimal("1.00"), "a": {"z": 2, "y": 1}}
    right = {"a": {"y": 1, "z": 2}, "b": Decimal("1.0")}

    assert canonical_payload_hash(left) == canonical_payload_hash(right)
    assert _policy().payload_hash == _policy().payload_hash


@pytest.mark.parametrize(
    ("field_path", "value"),
    [
        (("take_profit_legs", 0, "reward_multiple"), "0"),
        (("take_profit_legs", 0, "quantity_fraction"), "0"),
        (("runner_rule", "timeframe"), "15minutes"),
        (("runner_rule", "minimum_improvement_ticks"), 0),
        (("post_tp1_floor_rule", "slippage_buffer_ticks"), -1),
        (("post_tp1_floor_rule", "minimum_improvement_ticks"), 0),
    ],
)
def test_invalid_policy_values_are_rejected(field_path, value):
    payload = _policy_payload()
    target = payload
    for key in field_path[:-1]:
        target = target[key]
    target[field_path[-1]] = value

    with pytest.raises(ValidationError):
        TicketExitPolicySnapshot.with_canonical_hash(payload)


def test_invalid_fraction_totals_and_market_fallback_are_rejected():
    payload = _policy_payload(family="fixed_targets")
    payload["take_profit_legs"][1]["quantity_fraction"] = "0.6"
    with pytest.raises(ValidationError):
        TicketExitPolicySnapshot.with_canonical_hash(payload)

    with pytest.raises(ValidationError):
        TicketTakeProfitLeg(
            role="TP1",
            reward_multiple=Decimal("1"),
            quantity_fraction=Decimal("0.5"),
            execution_style=TpExecutionStyle.LIMIT_GTC,
            market_fallback_allowed=True,
        )


def test_runner_break_even_floor_uses_runner_leg_costs_and_conservative_exit_fee():
    long_floor = calculate_runner_break_even_floor(
        side="long",
        entry_avg_fill_price=Decimal("100"),
        runner_qty=Decimal("0.5"),
        allocated_entry_fee_quote=Decimal("0.02"),
        certified_exit_taker_fee_rate=Decimal("0.0005"),
        slippage_buffer_quote=Decimal("0.03"),
        minimum_price_tick=Decimal("0.1"),
    )
    short_floor = calculate_runner_break_even_floor(
        side="short",
        entry_avg_fill_price=Decimal("100"),
        runner_qty=Decimal("0.5"),
        allocated_entry_fee_quote=Decimal("0.02"),
        certified_exit_taker_fee_rate=Decimal("0.0005"),
        slippage_buffer_quote=Decimal("0.03"),
        minimum_price_tick=Decimal("0.1"),
    )

    assert long_floor == Decimal("100.2")
    assert short_floor == Decimal("99.8")


@pytest.mark.parametrize(
    "overrides",
    [
        {"runner_qty": Decimal("0")},
        {"runner_qty": Decimal("-1")},
        {"allocated_entry_fee_quote": None},
        {"certified_exit_taker_fee_rate": Decimal("1")},
        {"certified_exit_taker_fee_rate": Decimal("-0.1")},
        {"slippage_buffer_quote": Decimal("-0.01")},
        {"minimum_price_tick": Decimal("0")},
    ],
)
def test_invalid_runner_floor_inputs_are_rejected(overrides):
    values = {
        "side": "long",
        "entry_avg_fill_price": Decimal("100"),
        "runner_qty": Decimal("0.5"),
        "allocated_entry_fee_quote": Decimal("0.02"),
        "certified_exit_taker_fee_rate": Decimal("0.0005"),
        "slippage_buffer_quote": Decimal("0.03"),
        "minimum_price_tick": Decimal("0.1"),
    }
    values.update(overrides)
    with pytest.raises(ValueError):
        calculate_runner_break_even_floor(**values)


def test_execution_snapshot_rejects_zero_r_and_hash_mismatch():
    payload = {
        "ticket_id": "ticket-1",
        "exit_policy_id": "sor-right-tail-v1",
        "exit_policy_version": "1.0.0",
        "entry_avg_fill_price": "100",
        "entry_filled_qty": "1",
        "initial_stop_price": "95",
        "actual_r_per_unit": "5",
        "resolved_tp1_price": "105",
        "resolved_tp1_target_qty": "0.5",
        "runner_target_qty": "0.5",
        "entry_fee_quote": "0.04",
        "certified_exit_taker_fee_rate": "0.0005",
        "slippage_buffer_quote": "0.03",
    }
    snapshot = TicketExitExecutionSnapshot.with_canonical_hash(payload)
    assert snapshot.actual_r_per_unit == Decimal("5")

    with pytest.raises(ValidationError):
        TicketExitExecutionSnapshot(**{**snapshot.model_dump(), "payload_hash": "bad"})
    with pytest.raises(ValidationError):
        TicketExitExecutionSnapshot.with_canonical_hash(
            {**payload, "actual_r_per_unit": "0"}
        )


def test_evaluator_noop_blocked_invalidation_and_time_stop_priority():
    assert evaluate_exit_policy(_evaluation(position_qty="0")).kind is ExitDecisionKind.NOOP
    assert (
        evaluate_exit_policy(_evaluation(protection_exact=False)).kind
        is ExitDecisionKind.BLOCKED
    )

    invalidation_fact = ExitMarketFact(
        watermark_ms=1_720_000_000_000,
        is_final_closed_candle=True,
        close_price=Decimal("94"),
        holding_bars=30,
        invalidation_rule_ids_hit=("opening_range_reclaim_failed",),
        structural_stop_candidate=Decimal("98"),
    )
    invalidated = evaluate_exit_policy(_evaluation(market_fact=invalidation_fact))
    assert invalidated.kind is ExitDecisionKind.CLOSE_RUNNER
    assert invalidated.reason_code == "strategy_invalidation_hit"

    time_fact = invalidation_fact.model_copy(
        update={"invalidation_rule_ids_hit": (), "structural_stop_candidate": None}
    )
    timed = evaluate_exit_policy(_evaluation(market_fact=time_fact))
    assert timed.kind is ExitDecisionKind.CLOSE_RUNNER
    assert timed.reason_code == "time_stop_hit"


def test_tp1_completion_floor_is_immediate_and_monotonic_for_long_and_short():
    long_decision = evaluate_exit_policy(
        _evaluation(tp1_completion_state="complete", immediate_floor="100.2")
    )
    short_decision = evaluate_exit_policy(
        _evaluation(
            side="short",
            current_stop="105",
            tp1_completion_state="complete",
            immediate_floor="99.8",
        )
    )
    no_improvement = evaluate_exit_policy(
        _evaluation(tp1_completion_state="complete", immediate_floor="95.1")
    )

    assert long_decision.kind is ExitDecisionKind.MOVE_RUNNER_STOP
    assert long_decision.proposed_stop > Decimal("95")
    assert short_decision.kind is ExitDecisionKind.MOVE_RUNNER_STOP
    assert short_decision.proposed_stop < Decimal("105")
    assert no_improvement.kind is ExitDecisionKind.NOOP


def test_structural_and_reference_trails_only_move_on_closed_improving_fact():
    fact = ExitMarketFact(
        watermark_ms=1_720_000_000_000,
        is_final_closed_candle=True,
        close_price=Decimal("101"),
        holding_bars=10,
        structural_stop_candidate=Decimal("98"),
    )
    decision = evaluate_exit_policy(_evaluation(market_fact=fact))
    assert decision.kind is ExitDecisionKind.MOVE_RUNNER_STOP
    assert decision.proposed_stop == Decimal("98")

    open_fact = fact.model_copy(update={"is_final_closed_candle": False})
    assert evaluate_exit_policy(_evaluation(market_fact=open_fact)).kind is ExitDecisionKind.BLOCKED


def test_named_floor_rule_is_frozen_and_forbids_extra_fields():
    rule = RunnerBreakEvenFloorRule(
        kind="runner_leg_cost_adjusted_break_even",
        trigger="tp1_target_quantity_complete",
        exit_fee_basis="conservative_taker",
        slippage_buffer_ticks=2,
        minimum_improvement_ticks=2,
    )
    with pytest.raises(ValidationError):
        rule.slippage_buffer_ticks = 3
    with pytest.raises(ValidationError):
        RunnerBreakEvenFloorRule(
            **rule.model_dump(),
            hidden_parameter=1,
        )
