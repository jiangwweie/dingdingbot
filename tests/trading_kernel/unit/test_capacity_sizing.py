from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.domain.capacity_sizing import (
    CapacitySizingRequest,
    CapacitySizingStatus,
    MaintenanceMarginBracket,
    select_capacity_candidate,
)


@pytest.mark.parametrize(
    ("active_ticket_count", "remaining_slots"),
    [(0, 3), (1, 2), (2, 1)],
)
def test_ticket_uses_current_remaining_margin_without_reserving_empty_slots(
    active_ticket_count: int,
    remaining_slots: int,
) -> None:
    decision = select_capacity_candidate(
        _request(active_ticket_count=active_ticket_count)
    )

    assert decision.status is CapacitySizingStatus.SELECTED
    assert decision.selected is not None
    assert decision.selected.remaining_slots == remaining_slots
    assert (
        decision.selected.ticket_margin_budget
        == decision.selected.remaining_executable_margin
    )


def test_uses_configured_leverage_without_requesting_a_mutation() -> None:
    decision = select_capacity_candidate(_request(configured_leverage=5))

    assert decision.status is CapacitySizingStatus.SELECTED
    assert decision.selected is not None
    assert decision.selected.selected_leverage == 5
    assert decision.selected.quantity == Decimal("12")
    assert decision.selected.planned_stop_risk == Decimal("30")
    assert decision.selected.leverage_change_required is False


def test_margin_limited_candidate_uses_all_remaining_margin_at_configured_leverage() -> None:
    decision = select_capacity_candidate(
        _request(
            available_margin=Decimal("9.9"),
            total_margin_balance=Decimal("9.9"),
            quantity_step=Decimal("0.1"),
            min_quantity=Decimal("0.1"),
            min_notional=Decimal("5"),
            configured_leverage=5,
        )
    )

    assert decision.status is CapacitySizingStatus.SELECTED
    assert decision.selected is not None
    assert decision.selected.quantity == Decimal("0.4")
    assert decision.selected.planned_stop_risk == Decimal("1.0")
    assert decision.selected.selected_leverage == 5
    assert decision.selected.reserved_margin == Decimal("8")
    assert decision.selected.leverage_change_required is False


def test_existing_opposite_side_adopts_exact_configured_leverage() -> None:
    decision = select_capacity_candidate(
        _request(instrument_has_open_position=True, configured_leverage=3)
    )

    assert decision.status is CapacitySizingStatus.SELECTED
    assert decision.selected is not None
    assert decision.selected.selected_leverage == 3
    assert decision.selected.leverage_change_required is False


def test_refuses_configured_leverage_above_owner_and_exchange_cap_while_flat() -> None:
    decision = select_capacity_candidate(
        _request(
            configured_leverage=11,
            permitted_max_leverage=10,
            instrument_has_open_position=False,
        )
    )

    assert decision.status is CapacitySizingStatus.INVALID_FACTS
    assert decision.selected is None


def test_capacity_refuses_when_all_capital_owning_slots_are_taken() -> None:
    decision = select_capacity_candidate(_request(active_ticket_count=3))

    assert decision.status is CapacitySizingStatus.COUNT_EXHAUSTED
    assert decision.selected is None


def _request(**changes: object) -> CapacitySizingRequest:
    payload: dict[str, object] = {
        "total_wallet_balance": Decimal("1000"),
        "total_margin_balance": Decimal("1000"),
        "total_initial_margin": Decimal("0"),
        "total_maintenance_margin": Decimal("0"),
        "available_margin": Decimal("1000"),
        "active_ticket_count": 0,
        "max_concurrent_tickets": 3,
        "planned_stop_risk_fraction": Decimal("0.03"),
        "max_initial_margin_utilization": Decimal("0.90"),
        "permitted_max_leverage": 10,
        "configured_leverage": 1,
        "instrument_has_open_position": False,
        "entry_reference_price": Decimal("100"),
        "initial_stop_price": Decimal("97.5"),
        "quantity_step": Decimal("0.1"),
        "min_quantity": Decimal("0.1"),
        "min_notional": Decimal("5"),
        "tp1_quantity_fraction": Decimal("0.5"),
        "maintenance_margin_brackets": (
            MaintenanceMarginBracket(
                bracket_id="tier-1",
                notional_floor=Decimal("0"),
                notional_cap=None,
                maintenance_margin_rate=Decimal("0.005"),
                maintenance_amount=Decimal("0"),
            ),
        ),
        "position_side": "long",
        "mark_price": Decimal("100"),
        "min_liquidation_distance_to_stop_distance_ratio": Decimal("2.0"),
    }
    payload.update(changes)
    return CapacitySizingRequest.model_validate(payload)
