from src.application.action_time.lifecycle_occupancy import (
    LifecycleOccupancyState,
    classify_lifecycle_occupancy,
)


def test_terminally_flat_pg_state_is_clear_for_new_action_time_preflight() -> None:
    snapshot = classify_lifecycle_occupancy(
        pg_active_position_count=0,
        pg_open_order_count=0,
        exchange_position_count=0,
        exchange_open_protection_count=0,
        exchange_facts_requested=True,
        exchange_facts_available=True,
        lifecycle_status="closed_reviewed",
    )

    assert snapshot.state == LifecycleOccupancyState.FLAT_AND_CLEAR
    assert snapshot.permits_new_entry is True


def test_exchange_read_failure_is_unknown_and_fail_closed() -> None:
    snapshot = classify_lifecycle_occupancy(
        pg_active_position_count=0,
        pg_open_order_count=0,
        exchange_position_count=0,
        exchange_open_protection_count=0,
        exchange_facts_requested=True,
        exchange_facts_available=False,
        lifecycle_status="not_started_or_unknown",
    )

    assert snapshot.state == LifecycleOccupancyState.UNKNOWN_FAIL_CLOSED
    assert snapshot.first_blocker == "exchange_occupancy_facts_unavailable"
    assert snapshot.permits_new_entry is False


def test_open_position_and_protection_remains_open_protected() -> None:
    snapshot = classify_lifecycle_occupancy(
        pg_active_position_count=1,
        pg_open_order_count=2,
        exchange_position_count=1,
        exchange_open_protection_count=2,
        exchange_facts_requested=True,
        exchange_facts_available=True,
        lifecycle_status="protected_open_from_pg_orders",
    )

    assert snapshot.state == LifecycleOccupancyState.OPEN_PROTECTED
    assert snapshot.permits_new_entry is False
