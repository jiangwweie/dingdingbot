from decimal import Decimal as D

import pytest

from src.trading_kernel.domain.exit_execution import (
    ExitOrderRules,
    ExitPlanUnexecutable,
    TpQuantityPolicy,
    calculate_exit_quantities,
    calculate_tp_price,
)


def rules(**updates):
    return ExitOrderRules.model_validate(
        dict(
            quantity_step="0.001",
            min_quantity="0.001",
            min_notional="50",
            max_quantity="100",
            min_price=".1",
            max_price="100000000",
            price_tick="0.1",
            runner_quantity_step=".001",
            runner_min_quantity=".001",
            runner_max_quantity="100",
            observed_at_ms=1000,
            valid_until_ms=2000,
            **updates,
        )
    )


@pytest.mark.parametrize(
    ("quantity", "expected"),
    [("0.019", "0.001"), ("0.007", "0.001"), ("0.002", "0.001"), ("1.019", "0.050")],
)
def test_minimum_lift_keeps_entry_size_and_reports_actual_fraction(quantity, expected):
    result = calculate_exit_quantities(
        quantity=D(quantity),
        tp_price=D(65000),
        stop_price=D(60000),
        target_fraction=D(".05"),
        policy=TpQuantityPolicy.TARGET_FLOOR_THEN_MINIMUM,
        max_fraction=D(".50"),
        rules=rules(),
        now_ms=1000,
    )
    assert result.tp_quantity == D(expected)
    assert result.runner_quantity + result.tp_quantity == D(quantity)
    assert result.actual_fraction == D(expected) / D(quantity)
    assert result.minimum_lifted == (D(quantity) < 1)


@pytest.mark.parametrize(
    ("quantity", "price", "reason"),
    [("0.001", "65000", "fraction_cap"), ("0.007", "10000", "fraction_cap")],
)
def test_minimum_exceeding_cap_refuses_instead_of_enlarging_entry(
    quantity, price, reason
):
    with pytest.raises(ExitPlanUnexecutable, match=reason):
        calculate_exit_quantities(
            quantity=D(quantity),
            tp_price=D(price),
            stop_price=D(price),
            target_fraction=D(".05"),
            policy=TpQuantityPolicy.TARGET_FLOOR_THEN_MINIMUM,
            max_fraction=D(".5"),
            rules=rules(),
            now_ms=1000,
        )


def test_sor_keeps_floor_without_lifting():
    with pytest.raises(ExitPlanUnexecutable, match="zero"):
        calculate_exit_quantities(
            quantity=D(".007"),
            tp_price=D(65000),
            stop_price=D(60000),
            target_fraction=D(".05"),
            policy=TpQuantityPolicy.TARGET_FLOOR,
            max_fraction=D(1),
            rules=rules(),
            now_ms=1000,
        )


@pytest.mark.parametrize(
    ("side", "entry", "stop", "multiple", "expected"),
    [
        ("long", "100.05", "90", "1", "110.1"),
        ("short", "100.05", "110", "1.2", "88.1"),
    ],
)
def test_actual_vwap_r_rounds_toward_profit(side, entry, stop, multiple, expected):
    assert calculate_tp_price(
        side=side,
        entry_price=D(entry),
        initial_stop=D(stop),
        multiple=D(multiple),
        price_tick=D(".1"),
    ) == D(expected)


@pytest.mark.parametrize("now_ms", [999, 2000, 2001])
def test_stale_or_future_rules_refuse(now_ms):
    with pytest.raises(ExitPlanUnexecutable, match="rule_stale"):
        calculate_exit_quantities(
            quantity=D(".019"),
            tp_price=D(65000),
            stop_price=D(60000),
            target_fraction=D(".05"),
            policy=TpQuantityPolicy.TARGET_FLOOR_THEN_MINIMUM,
            max_fraction=D(".5"),
            rules=rules(),
            now_ms=now_ms,
        )


def test_v1_profile_serialization_and_hash_are_unchanged():
    from src.trading_kernel.domain.exit_policy import (
        ExitProfile,
        registered_exit_profiles,
    )

    profile = registered_exit_profiles()[0]
    payload = profile.model_dump(mode="json")
    assert "execution" not in payload
    assert (
        ExitProfile.model_validate(payload).semantic_hash() == profile.semantic_hash()
    )


def test_v2_profile_requires_explicit_execution_contract():
    from src.trading_kernel.domain.exit_policy import (
        ExitProfile,
        registered_exit_profiles,
    )

    payload = registered_exit_profiles()[0].model_dump(mode="json")
    payload["profile_schema_version"] = "exit_profile_v2"
    with pytest.raises(ValueError, match="execution"):
        ExitProfile.model_validate(payload)
    payload["execution"] = {
        "price_basis": "complete_entry_vwap",
        "quantity_policy": "target_floor_then_minimum",
        "max_actual_fraction": ".50",
    }
    profile = ExitProfile.model_validate(payload)
    assert (
        profile.execution.quantity_policy is TpQuantityPolicy.TARGET_FLOOR_THEN_MINIMUM
    )
    assert (
        profile.model_dump(mode="json")["execution"]["price_basis"]
        == "complete_entry_vwap"
    )


def test_postfill_plan_uses_deduplicated_entry_vwap_and_freezes_identities():
    from src.trading_kernel.domain.exit_execution import (
        CompleteEntryFills,
        EntryFill,
        build_post_fill_exit_plan,
    )
    from src.trading_kernel.domain.exit_policy import (
        ExitProfile,
        registered_exit_profiles,
    )

    payload = registered_exit_profiles()[0].model_dump(mode="json")
    payload.update(
        profile_schema_version="exit_profile_v2",
        execution={
            "price_basis": "complete_entry_vwap",
            "quantity_policy": "target_floor_then_minimum",
            "max_actual_fraction": ".5",
        },
        position_side="long",
    )
    payload["tp1"] = {"reward_multiple": "1", "quantity_fraction": ".05"}
    profile = ExitProfile.model_validate(payload)
    fills = CompleteEntryFills(
        command_id="cmd",
        exchange_order_id="123",
        fills=(
            EntryFill(trade_id="2", quantity=D(".004"), price=D(65010)),
            EntryFill(trade_id="1", quantity=D(".003"), price=D(64990)),
        ),
        observed_at_ms=1000,
    )
    plan = build_post_fill_exit_plan(
        ticket_id="ticket",
        entry_fills=fills,
        quantity=D(".007"),
        initial_stop=D(64000),
        profile=profile,
        binding_id="binding",
        binding_revision=3,
        management_revision=1,
        rules=rules(),
        now_ms=1000,
    )
    assert plan.entry_price == (D(".004") * 65010 + D(".003") * 64990) / D(".007")
    assert plan.quantities.tp_quantity == D(".001")
    assert plan.tp_price != D(66000)
    assert plan.initial_r_quote == D(".007") * (plan.entry_price - D(64000))
    reverse = fills.model_copy(update={"fills": tuple(reversed(fills.fills))})
    assert (
        build_post_fill_exit_plan(
            ticket_id="ticket",
            entry_fills=reverse,
            quantity=D(".007"),
            initial_stop=D(64000),
            profile=profile,
            binding_id="binding",
            binding_revision=3,
            management_revision=1,
            rules=rules(),
            now_ms=1000,
        )
        == plan
    )


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"max_quantity": "0.0005"}, "max_quantity"),
        ({"runner_min_quantity": "0.019"}, "runner_size"),
        ({"min_notional": "1000"}, "fraction_cap"),
        ({"min_price": "66000"}, "price_range"),
    ],
)
def test_current_limits_are_applied_without_enlarging_original_quantity(
    changes, reason
):
    original = rules().model_dump(mode="python")
    original.update(changes)
    if changes.get("max_quantity") == "0.0005":
        original["min_quantity"] = ".0001"
    rule = ExitOrderRules.model_validate(original)
    with pytest.raises(ExitPlanUnexecutable, match=reason):
        calculate_exit_quantities(
            quantity=D(".019"),
            tp_price=D(65000),
            stop_price=D(60000),
            target_fraction=D(".05"),
            policy=TpQuantityPolicy.TARGET_FLOOR_THEN_MINIMUM,
            max_fraction=D(".5"),
            rules=rule,
            now_ms=1000,
        )
