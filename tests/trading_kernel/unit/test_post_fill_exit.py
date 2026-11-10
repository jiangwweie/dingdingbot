from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.exit_policy import ExitProfile, registered_exit_profiles
from src.trading_kernel.domain.post_fill_exit import (
    PostFillExitPlan,
    PostFillExitRequest,
    build_post_fill_exit_plan,
)


@pytest.mark.parametrize(
    ("side", "entry", "stop", "expected"),
    [
        ("long", "101.03", "99", "103.5"),
        ("short", "98.97", "101", "96.5"),
    ],
)
def test_target_uses_actual_fill_and_profit_direction_tick(
    side: str,
    entry: str,
    stop: str,
    expected: str,
) -> None:
    result = build_post_fill_exit_plan(
        _request(
            side=side,
            average_fill_price=Decimal(entry),
            initial_stop_price=Decimal(stop),
        )
    )
    assert result.plan is not None
    assert result.plan.take_profit_price == Decimal(expected)
    assert result.plan.risk_quote == Decimal("20.30")
    assert result.plan.effective_reward_multiple >= Decimal("1.2")
    assert result.plan.tp1_quantity == Decimal("0.5")
    assert (
        PostFillExitPlan.model_validate_json(result.plan.model_dump_json())
        == result.plan
    )


def test_post_fill_plan_contains_exact_profile_rules_and_binding_lineage() -> None:
    request = _request()
    result = build_post_fill_exit_plan(request)
    assert result.plan is not None
    assert result.plan.request == request
    assert (
        result.plan.request.profile.semantic_hash() == request.profile.semantic_hash()
    )
    assert result.plan.request.rules_digest == "sha256:" + "a" * 64
    data = result.plan.model_dump(mode="json")
    data["take_profit_price"] = "999"
    with pytest.raises(ValidationError):
        PostFillExitPlan.model_validate(data)


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"initial_stop_price": Decimal(101)}, "stop_direction_invalid"),
        (
            {"quantity": Decimal("0.1"), "min_notional": Decimal(50)},
            "exit_quantity_unexecutable",
        ),
        (
            {
                "side": "short",
                "average_fill_price": Decimal(1),
                "initial_stop_price": Decimal(100),
            },
            "target_price_invalid",
        ),
    ],
)
def test_invalid_post_fill_plan_has_explicit_failure(
    changes: dict, reason: str
) -> None:
    result = build_post_fill_exit_plan(_request(**changes))
    assert result.plan is None
    assert result.status == reason


def test_stale_rule_facts_cannot_freeze_an_execution_plan() -> None:
    with pytest.raises(ValidationError):
        _request(created_at_ms=2000)


def _request(*, side: str = "long", **changes: object) -> PostFillExitRequest:
    profile = next(p for p in registered_exit_profiles() if p.position_side == side)
    payload = profile.model_dump(mode="json")
    payload["tp1"].update(
        reward_multiple="1.2",
        quantity_fraction="0.05",
        price_basis="actual_fill",
        quantity_rule={"max_actual_fraction": "0.50"},
    )
    request: dict[str, object] = {
        "ticket_id": "ticket:post-fill",
        "exit_binding_id": "binding:1",
        "profile": ExitProfile.model_validate(payload),
        "quantity": Decimal(10),
        "average_fill_price": Decimal(100),
        "initial_stop_price": Decimal(99 if side == "long" else 101),
        "quantity_step": Decimal("0.01"),
        "price_tick": Decimal("0.1"),
        "min_quantity": Decimal("0.01"),
        "min_notional": Decimal(5),
        "rules_digest": "sha256:" + "a" * 64,
        "rules_observed_at_ms": 1000,
        "rules_valid_until_ms": 2000,
        "created_at_ms": 1100,
    }
    request.update(changes)
    return PostFillExitRequest.model_validate(request)


def test_reference_profile_preserves_its_frozen_quantity_without_ratio_rounding() -> (
    None
):
    request = _request(
        quantity=Decimal(3),
        quantity_step=Decimal(1),
        min_quantity=Decimal(1),
        min_notional=Decimal(1),
    )
    data = request.model_dump(mode="python")
    data["profile"]["tp1"]["price_basis"] = "entry_reference"
    data["reference_tp1_quantity"] = Decimal(1)
    data["reference_take_profit_price"] = Decimal(102)
    result = build_post_fill_exit_plan(PostFillExitRequest.model_validate(data))
    assert result.plan is not None
    assert result.plan.tp1_quantity == Decimal(1)


def test_persisted_plan_is_independent_of_callers_decimal_context() -> None:
    from decimal import ROUND_FLOOR, localcontext

    request = _request(
        average_fill_price=Decimal("101.03"), initial_stop_price=Decimal(99)
    )
    original = build_post_fill_exit_plan(request).plan
    assert original is not None
    with localcontext() as context:
        context.prec = 12
        context.rounding = ROUND_FLOOR
        assert (
            PostFillExitPlan.model_validate_json(original.model_dump_json()) == original
        )
