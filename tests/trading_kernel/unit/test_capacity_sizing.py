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
    """Catches one tight-stop Ticket consuming the full account margin budget."""

    decision = select_capacity_candidate(
        _request(
            configured_leverage=5,
            entry_reference_price=Decimal(100),
            initial_stop_price=Decimal("99.9"),
        )
    )

    assert decision.status is CapacitySizingStatus.SELECTED
    assert decision.selected is not None
    assert decision.selected.ticket_stop_risk_budget == Decimal(30)
    assert decision.selected.ticket_margin_budget == Decimal(450)
    assert decision.selected.reserved_margin == Decimal(450)
    assert decision.selected.quantity == Decimal("22.5")
    assert decision.selected.planned_stop_risk == Decimal("2.25")


@pytest.mark.parametrize(
    ("gross_risk_at_stop", "expected_budget", "expected_status"),
    [
        (Decimal(0), Decimal(30), CapacitySizingStatus.SELECTED),
        (Decimal(30), Decimal(30), CapacitySizingStatus.SELECTED),
        (Decimal(50), Decimal(10), CapacitySizingStatus.SELECTED),
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
        Decimal(450), expected_remaining
    )


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


def _request(**changes: object) -> CapacitySizingRequest:
    payload: dict[str, object] = {
        "total_wallet_balance": Decimal(1000),
        "total_margin_balance": Decimal(1000),
        "total_initial_margin": Decimal(0),
        "current_reserved_margin": Decimal(0),
        "gross_risk_at_stop": Decimal(0),
        "available_margin": Decimal(1000),
        "active_ticket_count": 0,
        "max_concurrent_tickets": 3,
        "max_ticket_stop_risk_fraction": Decimal("0.03"),
        "max_gross_stop_risk_fraction": Decimal("0.06"),
        "max_ticket_initial_margin_fraction": Decimal("0.45"),
        "max_gross_initial_margin_utilization": Decimal("0.90"),
        "permitted_max_leverage": 10,
        "configured_leverage": 1,
        "entry_reference_price": Decimal(100),
        "initial_stop_price": Decimal("97.5"),
        "quantity_step": Decimal("0.1"),
        "min_quantity": Decimal("0.1"),
        "min_notional": Decimal(5),
        "tp1_quantity_fraction": Decimal("0.5"),
    }
    payload.update(changes)
    return CapacitySizingRequest.model_validate(payload)
