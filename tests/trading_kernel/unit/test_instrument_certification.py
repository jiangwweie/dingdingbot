from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.domain.instrument_certification import (
    InstrumentCertificationFacts,
    classify_instrument_certification,
)


def test_certification_accepts_exact_cross_5x_independent_sides_without_unowned_exposure() -> None:
    result = classify_instrument_certification(
        _facts(),
        required_leverage=5,
        required_margin_mode="cross",
        valid_for_ms=60_000,
    )

    assert result.status == "eligible"
    assert result.blocker_code is None
    assert result.valid_until_ms == 61_000


@pytest.mark.parametrize(
    ("changes", "expected_blocker"),
    (
        ({"configured_leverage": 3}, "configured_leverage_mismatch"),
        ({"margin_mode": "isolated"}, "margin_mode_mismatch"),
        ({"position_mode": "one_way"}, "position_mode_mismatch"),
        ({"product_status": "halted"}, "product_not_trading"),
        ({"unowned_position_qty": Decimal(1)}, "unowned_position"),
        ({"unowned_open_order_count": 1}, "unowned_open_order"),
        ({"tick_size": None}, "missing_order_rule"),
        (
            {"notional_coefficient_certified": False},
            "notional_coefficient_unverified",
        ),
    ),
)
def test_certification_reports_stable_non_mutating_blockers(
    changes: dict[str, object],
    expected_blocker: str,
) -> None:
    result = classify_instrument_certification(
        _facts().model_copy(update=changes),
        required_leverage=5,
        required_margin_mode="cross",
        valid_for_ms=60_000,
    )

    assert result.status == "owner_action_required"
    assert result.blocker_code == expected_blocker


def test_certification_rejects_invalid_required_window() -> None:
    with pytest.raises(ValueError, match="validity"):
        classify_instrument_certification(
            _facts(),
            required_leverage=5,
            required_margin_mode="cross",
            valid_for_ms=0,
        )


def _facts() -> InstrumentCertificationFacts:
    return InstrumentCertificationFacts(
        runtime_profile_id="profile:main",
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        product_status="trading",
        tick_size=Decimal("0.1"),
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal(5),
        position_mode="independent_sides",
        margin_mode="cross",
        configured_leverage=5,
        notional_coefficient_certified=True,
        unowned_position_qty=Decimal(0),
        unowned_open_order_count=0,
        observed_at_ms=1_000,
    )
