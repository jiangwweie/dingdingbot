from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.domain.capacity_sizing import (
    CapacitySizingRequest,
    CapacitySizingSelection,
    CapacitySizingStatus,
    select_capacity_candidate,
)


def test_sizing_models_contain_no_exchange_stress_authority() -> None:
    retired_fragments = ("liquidation", "maintenance_margin", "mark_price")

    assert not any(
        fragment in field_name
        for field_name in CapacitySizingRequest.model_fields
        for fragment in retired_fragments
    )
    assert not any(
        fragment in field_name
        for field_name in CapacitySizingSelection.model_fields
        for fragment in retired_fragments
    )


def test_tight_stop_is_capped_by_per_ticket_initial_margin() -> None:
    """Rejects a margin-capped Ticket below the minimum materialization."""

    decision = select_capacity_candidate(
        _request(
            configured_leverage=5,
            entry_reference_price=Decimal(100),
            initial_stop_price=Decimal("99.9"),
        )
    )

    assert decision.status is CapacitySizingStatus.MINIMUM_MATERIALIZATION_UNMET
    assert decision.selected is None


@pytest.mark.parametrize(
    ("gross_risk_at_stop", "expected_budget", "expected_status"),
    [
        (Decimal(0), Decimal(20), CapacitySizingStatus.SELECTED),
        (Decimal(30), Decimal(20), CapacitySizingStatus.SELECTED),
        (Decimal(50), Decimal(10), CapacitySizingStatus.SELECTED),
        (
            Decimal("50.01"),
            None,
            CapacitySizingStatus.MINIMUM_MATERIALIZATION_UNMET,
        ),
        (Decimal(60), None, CapacitySizingStatus.STOP_RISK_EXHAUSTED),
    ],
)
def test_gross_stop_risk_limits_each_new_ticket(
    gross_risk_at_stop: Decimal,
    expected_budget: Decimal | None,
    expected_status: CapacitySizingStatus,
) -> None:
    decision = select_capacity_candidate(
        _request(gross_risk_at_stop=gross_risk_at_stop)
    )

    assert decision.status is expected_status
    if expected_budget is None:
        assert decision.selected is None
    else:
        assert decision.selected is not None
        assert decision.selected.ticket_stop_risk_budget == expected_budget


@pytest.mark.parametrize(
    ("total_initial_margin", "current_reserved_margin", "expected_remaining"),
    [
        (Decimal(0), Decimal(0), Decimal(900)),
        (Decimal(600), Decimal(0), Decimal(300)),
        (Decimal(100), Decimal(600), Decimal(300)),
    ],
)
def test_gross_margin_uses_greater_of_exchange_and_internal_reservations(
    total_initial_margin: Decimal,
    current_reserved_margin: Decimal,
    expected_remaining: Decimal,
) -> None:
    decision = select_capacity_candidate(
        _request(
            total_initial_margin=total_initial_margin,
            current_reserved_margin=current_reserved_margin,
        )
    )

    assert decision.status is CapacitySizingStatus.SELECTED
    assert decision.selected is not None
    assert decision.selected.remaining_gross_margin == expected_remaining
    assert decision.selected.ticket_margin_budget == min(
        Decimal(300), expected_remaining
    )


def test_directional_stop_risk_caps_the_new_ticket() -> None:
    selected = select_capacity_candidate(
        _request(directional_risk_at_stop=Decimal(30))
    )
    exhausted = select_capacity_candidate(
        _request(directional_risk_at_stop=Decimal(40))
    )

    assert selected.status is CapacitySizingStatus.SELECTED
    assert selected.selected is not None
    assert selected.selected.ticket_stop_risk_budget == Decimal(10)
    assert exhausted.status is CapacitySizingStatus.DIRECTIONAL_RISK_EXHAUSTED
    assert exhausted.selected is None


def test_cap_004_opposite_direction_ignores_exhausted_long_direction() -> None:
    decision = select_capacity_candidate(
        _request(
            gross_risk_at_stop=Decimal(40),
            directional_risk_at_stop=Decimal(0),
        )
    )

    assert decision.status is CapacitySizingStatus.SELECTED
    assert decision.selected is not None
    assert decision.selected.ticket_stop_risk_budget == Decimal(20)


@pytest.mark.parametrize(
    ("gross_risk_at_stop", "expected_status"),
    [
        (Decimal("50.01"), CapacitySizingStatus.MINIMUM_MATERIALIZATION_UNMET),
        (Decimal("50.00"), CapacitySizingStatus.SELECTED),
    ],
)
def test_minimum_materialization_binds_after_risk_rounding(
    gross_risk_at_stop: Decimal,
    expected_status: CapacitySizingStatus,
) -> None:
    decision = select_capacity_candidate(
        _request(
            gross_risk_at_stop=gross_risk_at_stop,
            entry_reference_price=Decimal(100),
            initial_stop_price=Decimal(99),
            quantity_step=Decimal("0.01"),
            min_quantity=Decimal("0.01"),
        )
    )

    assert decision.status is expected_status
    if decision.selected is not None:
        assert decision.selected.planned_stop_risk == Decimal(10)
        assert decision.selected.minimum_stop_risk_budget == Decimal(10)


def test_gross_margin_exhaustion_is_fail_closed() -> None:
    decision = select_capacity_candidate(
        _request(current_reserved_margin=Decimal(900))
    )

    assert decision.status is CapacitySizingStatus.MARGIN_EXHAUSTED
    assert decision.selected is None


@pytest.mark.parametrize(
    ("active_ticket_count", "remaining_slots"),
    [(0, 3), (1, 2), (2, 1)],
)
def test_first_three_ticket_counts_can_use_remaining_policy_capacity(
    active_ticket_count: int,
    remaining_slots: int,
) -> None:
    decision = select_capacity_candidate(
        _request(active_ticket_count=active_ticket_count)
    )

    assert decision.status is CapacitySizingStatus.SELECTED
    assert decision.selected is not None
    assert decision.selected.remaining_slots == remaining_slots


def test_fourth_ticket_is_rejected_by_count_gate() -> None:
    decision = select_capacity_candidate(_request(active_ticket_count=3))

    assert decision.status is CapacitySizingStatus.COUNT_EXHAUSTED
    assert decision.selected is None


def test_sizing_adopts_exact_configured_leverage_without_mutation() -> None:
    decision = select_capacity_candidate(_request(configured_leverage=5))

    assert decision.status is CapacitySizingStatus.SELECTED
    assert decision.selected is not None
    assert decision.selected.selected_leverage == 5
    assert decision.selected.leverage_change_required is False


def test_configured_leverage_above_policy_is_invalid() -> None:
    decision = select_capacity_candidate(
        _request(configured_leverage=11, permitted_max_leverage=10)
    )

    assert decision.status is CapacitySizingStatus.INVALID_FACTS
    assert decision.selected is None


def test_current_sizing_does_not_validate_each_exit_leg_min_notional() -> None:
    """Characterizes the EX-05 gap without changing current admission semantics."""

    request = _request(
        total_wallet_balance=Decimal("12.5"),
        total_margin_balance=Decimal("12.5"),
        available_margin=Decimal("12.5"),
        quantity_step=Decimal("0.01"),
        min_quantity=Decimal("0.01"),
        tp1_quantity_fraction=Decimal("0.5"),
    )
    decision = select_capacity_candidate(request)

    assert decision.status is CapacitySizingStatus.SELECTED
    assert decision.selected is not None
    assert decision.selected.quantity == Decimal("0.10")
    assert decision.selected.tp1_quantity == Decimal("0.05")
    assert decision.selected.runner_quantity == Decimal("0.05")
    assert (
        decision.selected.runner_quantity * request.initial_stop_price
        < request.min_notional
    )


def _request(**changes: object) -> CapacitySizingRequest:
    payload: dict[str, object] = {
        "total_wallet_balance": Decimal(1000),
        "total_margin_balance": Decimal(1000),
        "total_initial_margin": Decimal(0),
        "current_reserved_margin": Decimal(0),
        "gross_risk_at_stop": Decimal(0),
        "directional_risk_at_stop": Decimal(0),
        "available_margin": Decimal(1000),
        "active_ticket_count": 0,
        "max_concurrent_tickets": 3,
        "max_ticket_stop_risk_fraction": Decimal("0.02"),
        "max_gross_stop_risk_fraction": Decimal("0.06"),
        "max_ticket_initial_margin_fraction": Decimal("0.30"),
        "max_gross_initial_margin_utilization": Decimal("0.90"),
        "directional_stop_risk_limit_fraction": Decimal("0.04"),
        "min_materialization_ratio": Decimal("0.50"),
        "permitted_max_leverage": 10,
        "configured_leverage": 5,
        "entry_reference_price": Decimal(100),
        "initial_stop_price": Decimal("97.5"),
        "quantity_step": Decimal("0.1"),
        "min_quantity": Decimal("0.1"),
        "min_notional": Decimal(5),
        "tp1_quantity_fraction": Decimal("0.5"),
    }
    payload.update(changes)
    return CapacitySizingRequest.model_validate(payload)
