"""Typed lifecycle/account occupancy fact for Action-Time safety.

This boundary deliberately answers only whether a new entry may be considered.
It is never an observation gate and never carries order-creation authority.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class LifecycleOccupancyState(str, Enum):
    FLAT_AND_CLEAR = "flat_and_clear"
    OPEN_PROTECTED = "open_protected"
    RECOVERY_REQUIRED = "recovery_required"
    UNKNOWN_FAIL_CLOSED = "unknown_fail_closed"


class LifecycleOccupancySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: LifecycleOccupancyState
    pg_active_position_count: int = Field(ge=0)
    pg_open_order_count: int = Field(ge=0)
    exchange_position_count: int = Field(ge=0)
    exchange_open_protection_count: int = Field(ge=0)
    exchange_facts_requested: bool
    exchange_facts_available: bool
    lifecycle_status: str
    first_blocker: str | None = None

    @property
    def permits_new_entry(self) -> bool:
        return self.state == LifecycleOccupancyState.FLAT_AND_CLEAR


def classify_lifecycle_occupancy(
    *,
    pg_active_position_count: int,
    pg_open_order_count: int,
    exchange_position_count: int,
    exchange_open_protection_count: int,
    exchange_facts_requested: bool,
    exchange_facts_available: bool,
    lifecycle_status: str,
) -> LifecycleOccupancySnapshot:
    """Classify current occupancy without weakening submit safety.

    A read-only caller which did not request exchange facts can still form a
    PG-only readiness view.  Once exchange facts are requested, an unavailable
    result is unknown and therefore fail-closed for Action-Time progression.
    """

    if exchange_facts_requested and not exchange_facts_available:
        state = LifecycleOccupancyState.UNKNOWN_FAIL_CLOSED
        first_blocker = "exchange_occupancy_facts_unavailable"
    elif not (
        pg_active_position_count
        or pg_open_order_count
        or exchange_position_count
        or exchange_open_protection_count
    ):
        state = LifecycleOccupancyState.FLAT_AND_CLEAR
        first_blocker = None
    elif (
        pg_active_position_count
        and pg_open_order_count
        and (
            not exchange_facts_requested
            or (exchange_position_count and exchange_open_protection_count)
        )
    ):
        state = LifecycleOccupancyState.OPEN_PROTECTED
        first_blocker = "current_lifecycle_open_protected"
    else:
        state = LifecycleOccupancyState.RECOVERY_REQUIRED
        first_blocker = "active_position_resolution"
    return LifecycleOccupancySnapshot(
        state=state,
        pg_active_position_count=pg_active_position_count,
        pg_open_order_count=pg_open_order_count,
        exchange_position_count=exchange_position_count,
        exchange_open_protection_count=exchange_open_protection_count,
        exchange_facts_requested=exchange_facts_requested,
        exchange_facts_available=exchange_facts_available,
        lifecycle_status=lifecycle_status,
        first_blocker=first_blocker,
    )
