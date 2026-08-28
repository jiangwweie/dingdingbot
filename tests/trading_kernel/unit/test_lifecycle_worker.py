from __future__ import annotations

from decimal import Decimal

from src.trading_kernel.domain.events import (
    EntryFilled,
    EntryPartiallyFilled,
    VacuumPartialRetained,
)
from src.trading_kernel.domain.post_fill_risk import (
    PostFillDisposition,
    PostFillRiskDecision,
    PostFillRiskStatus,
)
from src.trading_kernel.interfaces.lifecycle_worker import (
    _earliest_nonzero_exposure_started_at_ms,
)


def test_full_fill_uses_entry_filled_time_as_exposure_start() -> None:
    event = EntryFilled.model_construct(
        event_id="event:full",
        ticket_id="ticket:1",
        sequence=2,
        occurred_at_ms=1_100,
        filled_qty=Decimal(1),
        average_fill_price=Decimal(100),
        post_fill_risk=_risk(),
        venue_reported_liquidation_price=None,
        position_observed_at_ms=1_100,
    )

    assert _earliest_nonzero_exposure_started_at_ms((event,)) == 1_100


def test_retained_partial_uses_original_partial_fill_time_and_ignores_retention() -> None:
    partial = EntryPartiallyFilled(
        event_id="event:partial",
        ticket_id="ticket:1",
        sequence=2,
        occurred_at_ms=1_023,
        filled_qty=Decimal("0.6"),
        requested_qty=Decimal(1),
        average_fill_price=Decimal(100),
    )
    retained = VacuumPartialRetained(
        event_id="event:retained",
        ticket_id="ticket:1",
        sequence=6,
        occurred_at_ms=1_200,
        entry_vacuum_id="vacuum:1",
        selection_authority_id="authority:1",
        requested_qty=Decimal(1),
        final_filled_qty=Decimal("0.6"),
        average_fill_price=Decimal(100),
        quantity_step=Decimal("0.1"),
        effective_tp1_qty=Decimal("0.3"),
        effective_runner_qty=Decimal("0.3"),
        post_fill_risk=_risk(),
    )

    assert _earliest_nonzero_exposure_started_at_ms((partial, retained)) == 1_023


def _risk() -> PostFillRiskDecision:
    return PostFillRiskDecision(
        status=PostFillRiskStatus.WITHIN_BUDGET,
        disposition=PostFillDisposition.NORMAL,
        actual_stop_risk=Decimal(1),
    )
