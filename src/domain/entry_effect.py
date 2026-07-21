"""Pure classification of the durable effect of an ENTRY exchange command."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class EntryEffectState(str, Enum):
    NOT_CALLED = "not_called"
    ACCEPTED_ZERO_FILL = "accepted_zero_fill"
    ACCEPTED_FILLED = "accepted_filled"
    OUTCOME_UNKNOWN = "outcome_unknown"
    REJECTED = "rejected"
    RECONCILED_ABSENT = "reconciled_absent"


class ProtectionBarrierState(str, Enum):
    NOT_STARTED = "not_started"
    FILL_PENDING = "fill_pending"
    INITIAL_STOP_PENDING = "initial_stop_pending"
    INITIAL_STOP_CONFIRMED = "initial_stop_confirmed"
    DEGRADED = "degraded"
    HARD_STOPPED = "hard_stopped"
    CLOSED = "closed"


@dataclass(frozen=True)
class EntryEffectDecision:
    entry_effect_state: EntryEffectState
    protection_barrier_state: ProtectionBarrierState
    lifecycle_status: str | None
    lifecycle_event_type: str | None
    protection_quantity: Decimal | None
    effect_possible: bool


def classify_entry_effect(
    *,
    command_state: str,
    result_facts_complete: bool,
    executed_qty: Decimal | None,
    average_exec_price: Decimal | None,
    order_role: str = "ENTRY",
) -> EntryEffectDecision | None:
    """Classify only typed command columns; exchange JSON is not authority."""

    if str(order_role or "").upper() != "ENTRY":
        return None
    state = str(command_state or "")
    if state == "confirmed_rejected":
        return EntryEffectDecision(
            EntryEffectState.REJECTED,
            ProtectionBarrierState.NOT_STARTED,
            None,
            None,
            None,
            False,
        )
    if state == "outcome_unknown":
        return _unknown()
    if state != "confirmed_submitted":
        return None
    qty = Decimal(str(executed_qty)) if executed_qty is not None else None
    price = (
        Decimal(str(average_exec_price))
        if average_exec_price is not None
        else None
    )
    if not result_facts_complete or qty is None:
        return _unknown()
    if qty == 0:
        return EntryEffectDecision(
            EntryEffectState.ACCEPTED_ZERO_FILL,
            ProtectionBarrierState.FILL_PENDING,
            "entry_fill_pending",
            "entry_fill_pending",
            None,
            True,
        )
    if qty > 0 and price is not None and price > 0:
        return EntryEffectDecision(
            EntryEffectState.ACCEPTED_FILLED,
            ProtectionBarrierState.INITIAL_STOP_PENDING,
            "entry_filled",
            "entry_filled",
            qty,
            True,
        )
    return _unknown()


def _unknown() -> EntryEffectDecision:
    return EntryEffectDecision(
        EntryEffectState.OUTCOME_UNKNOWN,
        ProtectionBarrierState.HARD_STOPPED,
        "entry_unknown",
        "entry_unknown",
        None,
        True,
    )
