from decimal import Decimal

from src.application.protection_order_planner import plan_precision_aware_protection_orders


def test_bnb_min_size_falls_back_from_split_tp_to_single_tp_plus_sl():
    plan = plan_precision_aware_protection_orders(
        entry_quantity=Decimal("0.01"),
        entry_price=Decimal("705.43"),
        min_amount=Decimal("0.01"),
        amount_step=Decimal("0.01"),
        min_notional=Decimal("5"),
        min_notional_source="test",
    )

    assert plan.status == "valid"
    assert plan.plan_type == "single_tp_plus_sl"
    assert plan.planned_tp_quantities == (Decimal("0.01"),)
    assert plan.planned_sl_quantity == Decimal("0.01")
    assert plan.fallback_reason == "split_tp_quantity_below_min_amount"
    assert plan.amount_precision == 2


def test_planner_uses_multi_tp_when_all_split_quantities_are_valid():
    plan = plan_precision_aware_protection_orders(
        entry_quantity=Decimal("0.02"),
        entry_price=Decimal("705.43"),
        min_amount=Decimal("0.01"),
        amount_step=Decimal("0.01"),
        min_notional=Decimal("5"),
        min_notional_source="test",
    )

    assert plan.status == "valid"
    assert plan.plan_type == "multi_tp_plus_sl"
    assert plan.planned_tp_quantities == (Decimal("0.010"), Decimal("0.010"))


def test_planner_blocks_when_even_sl_quantity_is_unprotectable():
    plan = plan_precision_aware_protection_orders(
        entry_quantity=Decimal("0.009"),
        entry_price=Decimal("705.43"),
        min_amount=Decimal("0.01"),
        amount_step=Decimal("0.01"),
        min_notional=Decimal("5"),
        min_notional_source="test",
    )

    assert plan.status == "blocked"
    assert plan.plan_type == "blocked_unprotectable_size"
    assert plan.blocked_reason == "entry_quantity_cannot_create_valid_sl"


def test_planner_blocks_when_min_amount_is_unavailable():
    plan = plan_precision_aware_protection_orders(
        entry_quantity=Decimal("0.01"),
        entry_price=Decimal("705.43"),
        min_amount=None,
        amount_step=None,
        min_notional=Decimal("5"),
        min_notional_source="test",
    )

    assert plan.status == "blocked"
    assert plan.blocked_reason == "protection_min_amount_unavailable"
