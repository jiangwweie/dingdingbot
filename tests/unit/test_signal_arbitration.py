from __future__ import annotations

import random

import pytest

from src.application.action_time.signal_arbitration import (
    MAX_ACTION_TIME_SIGNAL_BATCH,
    ArbitrationDisposition,
    FreshSignalArbitrationCandidate,
    arbitrate_fresh_signals,
    deterministically_rank_fresh_signals,
)


def _candidate(
    signal_event_id: str,
    *,
    policy: int = 1,
    scope: int = 1,
    event_time_ms: int = 100,
    observed_at_ms: int = 101,
    expires_at_ms: int = 10_000,
) -> FreshSignalArbitrationCandidate:
    return FreshSignalArbitrationCandidate(
        signal_event_id=signal_event_id,
        owner_policy_priority=policy,
        candidate_scope_priority=scope,
        event_time_ms=event_time_ms,
        observed_at_ms=observed_at_ms,
        expires_at_ms=expires_at_ms,
    )


def test_eight_same_timestamp_signals_have_one_stable_winner_regardless_of_input_order():
    candidates = [_candidate(f"signal-{index:02d}") for index in range(8)]
    random.Random(7).shuffle(candidates)

    decisions = arbitrate_fresh_signals(candidates, now_ms=200)

    assert [decision.signal_event_id for decision in decisions] == [
        f"signal-{index:02d}" for index in range(8)
    ]
    assert decisions[0].disposition is ArbitrationDisposition.SELECTED
    assert all(
        decision.disposition is ArbitrationDisposition.NOT_SELECTED_THIS_ROUND
        for decision in decisions[1:]
    )
    assert {decision.winner_signal_event_id for decision in decisions[1:]} == {
        "signal-00"
    }


def test_candidate_specific_blocker_falls_through_to_next_candidate():
    decisions = arbitrate_fresh_signals(
        [_candidate("first"), _candidate("second", scope=2)],
        now_ms=200,
        candidate_blocker=lambda candidate: "missing_price" if candidate.signal_event_id == "first" else None,
    )

    assert decisions[0].disposition is ArbitrationDisposition.CANDIDATE_BLOCKED
    assert decisions[0].reason_code == "missing_price"
    assert decisions[1].disposition is ArbitrationDisposition.SELECTED


def test_global_capacity_blocker_closes_all_fresh_candidates_without_winner():
    decisions = arbitrate_fresh_signals(
        [_candidate("first"), _candidate("second")],
        now_ms=200,
        global_blocker="account_capacity_2_of_2",
    )

    assert [decision.disposition for decision in decisions] == [
        ArbitrationDisposition.GLOBAL_BLOCKED,
        ArbitrationDisposition.GLOBAL_BLOCKED,
    ]
    assert {decision.reason_code for decision in decisions} == {"account_capacity_2_of_2"}


def test_expired_signal_is_explicit_and_does_not_block_next_fresh_signal():
    decisions = arbitrate_fresh_signals(
        [_candidate("expired", expires_at_ms=200), _candidate("fresh", scope=2)],
        now_ms=200,
    )

    assert decisions[0].disposition is ArbitrationDisposition.EXPIRED
    assert decisions[1].disposition is ArbitrationDisposition.SELECTED


def test_batch_is_bounded_and_duplicate_ids_fail_closed():
    with pytest.raises(ValueError, match="action_time_signal_batch_limit_exceeded"):
        deterministically_rank_fresh_signals(
            [_candidate(f"signal-{index}") for index in range(MAX_ACTION_TIME_SIGNAL_BATCH + 1)]
        )
    with pytest.raises(ValueError, match="action_time_signal_batch_duplicate_identity"):
        deterministically_rank_fresh_signals([_candidate("duplicate"), _candidate("duplicate")])
