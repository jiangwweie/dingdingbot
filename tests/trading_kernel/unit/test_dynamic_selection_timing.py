from __future__ import annotations

import pytest

from src.trading_kernel.domain.dynamic_selection_timing import (
    DynamicMembershipState,
    build_current_final_close_grant_proof,
    build_dynamic_membership_freshness,
    build_generic_selection_period,
    confirm_dynamic_membership_snapshot,
    record_dynamic_selection_miss,
)


def test_one_hour_membership_allows_one_missed_period_but_not_two() -> None:
    initial_period = build_generic_selection_period(
        feature_cutoff_at_ms=4 * 60 * 60 * 1000,
        cadence_hours=1,
    )
    freshness = build_dynamic_membership_freshness(
        source_snapshot_id="snapshot:04",
        source_member_set_digest="sha256:" + "a" * 64,
        period=initial_period,
    )

    first_miss = record_dynamic_selection_miss(
        current=freshness,
        missed_period=build_generic_selection_period(
            feature_cutoff_at_ms=5 * 60 * 60 * 1000,
            cadence_hours=1,
        ),
    )
    second_miss = record_dynamic_selection_miss(
        current=first_miss,
        missed_period=build_generic_selection_period(
            feature_cutoff_at_ms=6 * 60 * 60 * 1000,
            cadence_hours=1,
        ),
    )

    assert first_miss.state is DynamicMembershipState.GRACE
    assert first_miss.allows_new_entry_at(6 * 60 * 60 * 1000 - 1) is True
    assert second_miss.state is DynamicMembershipState.SELECTION_STALE_PAUSED
    assert second_miss.allows_new_entry_at(7 * 60 * 60 * 1000) is False


def test_fresh_snapshot_cannot_refresh_membership_before_effective_period() -> None:
    current = build_dynamic_membership_freshness(
        source_snapshot_id="snapshot:04",
        source_member_set_digest="sha256:" + "a" * 64,
        period=build_generic_selection_period(
            feature_cutoff_at_ms=4 * 60 * 60 * 1000,
            cadence_hours=1,
        ),
    )
    future = build_generic_selection_period(
        feature_cutoff_at_ms=5 * 60 * 60 * 1000,
        cadence_hours=1,
    )

    with pytest.raises(ValueError, match="effective"):
        confirm_dynamic_membership_snapshot(
            current=current,
            source_snapshot_id="snapshot:05",
            source_member_set_digest="sha256:" + "a" * 64,
            period=future,
            confirmed_at_ms=future.scheduled_effective_at_ms - 1,
        )


def test_four_hour_staleness_uses_absolute_deadline_not_worker_heartbeat() -> None:
    initial = build_dynamic_membership_freshness(
        source_snapshot_id="snapshot:04",
        source_member_set_digest="sha256:" + "a" * 64,
        period=build_generic_selection_period(
            feature_cutoff_at_ms=4 * 60 * 60 * 1000,
            cadence_hours=4,
        ),
    )

    assert initial.membership_valid_until_ms == 13 * 60 * 60 * 1000
    assert initial.allows_new_entry_at(13 * 60 * 60 * 1000 - 1) is True
    assert initial.allows_new_entry_at(13 * 60 * 60 * 1000) is False


def test_current_final_close_requires_precommitted_snapshot_and_unexpired_period() -> None:
    period = build_generic_selection_period(
        feature_cutoff_at_ms=4 * 60 * 60 * 1000,
        cadence_hours=1,
    )

    proof = build_current_final_close_grant_proof(
        selection_snapshot_id="snapshot:04",
        selection_committed_at_ms=4 * 60 * 60 * 1000 + 10,
        source_snapshot_cutoff_at_ms=4 * 60 * 60 * 1000,
        period=period,
        current_final_close_time_ms=5 * 60 * 60 * 1000,
        authority_granted_at_ms=5 * 60 * 60 * 1000 + 8_000,
        observation_cursor_version=7,
    )

    assert proof.current_final_close_time_ms == 5 * 60 * 60 * 1000
    with pytest.raises(ValueError, match="precommitted"):
        build_current_final_close_grant_proof(
            selection_snapshot_id="late",
            selection_committed_at_ms=5 * 60 * 60 * 1000 + 1,
            source_snapshot_cutoff_at_ms=4 * 60 * 60 * 1000,
            period=period,
            current_final_close_time_ms=5 * 60 * 60 * 1000,
            authority_granted_at_ms=5 * 60 * 60 * 1000 + 8_000,
            observation_cursor_version=7,
        )
