from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.exit_quantity import (
    ExitQuantityRequest,
    ExitQuantityRule,
    ExitQuantityStatus,
    select_exit_quantities,
)


@pytest.mark.parametrize(
    ("total", "expected", "status"),
    [
        ("0.019", "0.001", "selected"),
        ("0.007", "0.001", "selected"),
        ("0.002", "0.001", "selected"),
        ("0.001", None, "fraction_cap_exceeded"),
    ],
)
def test_minimum_quantity_does_not_expand_entry_and_respects_half_cap(
    total: str,
    expected: str | None,
    status: str,
) -> None:
    result = select_exit_quantities(_request(total_quantity=Decimal(total)))
    assert result.status.value == status
    if expected is None:
        assert result.selected is None
    else:
        assert result.selected is not None
        assert result.selected.tp1_quantity == Decimal(expected)
        assert result.selected.runner_quantity == Decimal(total) - Decimal(expected)
        assert result.selected.actual_fraction == Decimal(expected) / Decimal(total)
        assert result.selected.minimum_raised is True


@pytest.mark.parametrize(
    ("total", "step", "minimum", "notional", "tp_price", "expected"),
    [
        ("1.055", "0.001", "0.001", "20", "2097.88", "0.052"),
        ("2.82", "0.01", "0.01", "5", "671", "0.14"),
        ("1", "0.01", "0.01", "5", "24", "0.21"),
        ("1", "0.01", "0.23", "1", "100", "0.23"),
    ],
)
def test_floor_is_retained_unless_venue_minimum_requires_increase(
    total: str,
    step: str,
    minimum: str,
    notional: str,
    tp_price: str,
    expected: str,
) -> None:
    result = select_exit_quantities(
        _request(
            total_quantity=Decimal(total),
            quantity_step=Decimal(step),
            min_quantity=Decimal(minimum),
            min_notional=Decimal(notional),
            take_profit_price=Decimal(tp_price),
            initial_stop_price=Decimal(100),
        )
    )
    assert result.status is ExitQuantityStatus.SELECTED
    assert result.selected is not None
    assert result.selected.tp1_quantity == Decimal(expected)
    assert result.selected.actual_fraction <= Decimal("0.50")


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"total_quantity": Decimal("0.0195")}, "total_not_step_aligned"),
        ({"take_profit_price": Decimal(1000)}, "fraction_cap_exceeded"),
        ({"initial_stop_price": Decimal(1000)}, "runner_min_notional"),
        (
            {"total_quantity": Decimal("0.002"), "min_quantity": Decimal("0.002")},
            "fraction_cap_exceeded",
        ),
        ({"max_quantity": Decimal("0.0005")}, "tp_max_quantity"),
    ],
)
def test_rejections_are_explicit_and_never_clip_required_quantity(
    changes: dict[str, object],
    expected: str,
) -> None:
    result = select_exit_quantities(_request(**changes))
    assert result.status.value == expected
    assert result.selected is None


def test_strict_existing_fraction_does_not_silently_enable_minimum_raise() -> None:
    result = select_exit_quantities(_request(quantity_rule=None))
    assert result.status is ExitQuantityStatus.TP_MIN_QUANTITY
    assert result.selected is None


@pytest.mark.parametrize("cap", ["0", "0.049", "0.51", "NaN", "Infinity"])
def test_minimum_raise_cap_is_finite_and_at_most_half(cap: str) -> None:
    with pytest.raises(ValidationError):
        _request(quantity_rule=ExitQuantityRule(max_actual_fraction=Decimal(cap)))


@pytest.mark.parametrize(
    "field",
    [
        "total_quantity",
        "quantity_step",
        "take_profit_price",
        "initial_stop_price",
        "min_quantity",
        "min_notional",
    ],
)
@pytest.mark.parametrize("value", ["0", "NaN", "Infinity"])
def test_invalid_numeric_facts_are_rejected(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        _request(**{field: Decimal(value)})


def _request(**changes: object) -> ExitQuantityRequest:
    data: dict[str, object] = {
        "total_quantity": Decimal("0.019"),
        "quantity_step": Decimal("0.001"),
        "min_quantity": Decimal("0.001"),
        "min_notional": Decimal(50),
        "take_profit_price": Decimal(76000),
        "initial_stop_price": Decimal(73000),
        "target_fraction": Decimal("0.05"),
        "quantity_rule": ExitQuantityRule(max_actual_fraction=Decimal("0.50")),
    }
    data.update(changes)
    return ExitQuantityRequest.model_validate(data)
