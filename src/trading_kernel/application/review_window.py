"""Exact exposure window shared by initial and revised terminal Review."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from src.trading_kernel.domain.events import (
    EntryFilled,
    EntryPartiallyFilled,
    ExternalFlatDetected,
    ManualPositionObserved,
    PositionFlatConfirmed,
    TradeEvent,
)


class _ReviewWindow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entry_time_ms: int
    exit_time_ms: int
    executed_entry_quantity: Decimal
    external_flat: bool


def _review_window(
    events: list[TradeEvent],
    *,
    exposure_started_at_ms: int,
) -> _ReviewWindow | None:
    if exposure_started_at_ms <= 0:
        raise ValueError("review exposure start time must be positive")
    entry_events = [
        event
        for event in events
        if isinstance(event, (EntryFilled, EntryPartiallyFilled))
    ]
    flat_events = [
        event
        for event in events
        if isinstance(event, (PositionFlatConfirmed, ExternalFlatDetected)) or (isinstance(event,ManualPositionObserved) and event.quantity==0 and not event.orders and event.facts_complete and event.commands_resolved)
    ]
    if len(entry_events) != 1 or not flat_events:
        return None
    entry = entry_events[0]
    exit_event = min(
        (event for event in flat_events if event.occurred_at_ms >= entry.occurred_at_ms),
        key=lambda event: event.occurred_at_ms,
        default=None,
    )
    if exit_event is None:
        return None
    return _ReviewWindow(
        entry_time_ms=exposure_started_at_ms,
        exit_time_ms=exit_event.occurred_at_ms,
        executed_entry_quantity=entry.filled_qty,
        external_flat=isinstance(exit_event, (ExternalFlatDetected,ManualPositionObserved)),
    )
