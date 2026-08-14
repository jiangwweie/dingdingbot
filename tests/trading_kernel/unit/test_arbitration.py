from __future__ import annotations

import pytest

from src.trading_kernel.domain.arbitration import (
    EntryCandidate,
    freeze_candidate_set,
    rank_candidates,
)
from tests.trading_kernel.support.signals import make_signal as _signal


def test_arbitration_uses_the_complete_owner_accepted_ordering() -> None:
    candidates = (
        _candidate("signal:z", owner=2, event=1_000, observed=1_100),
        _candidate("signal:y", owner=1, event=1_003, observed=1_100),
        _candidate("signal:x", owner=1, event=1_002, observed=1_100),
        _candidate("signal:b", owner=1, event=1_000, observed=1_102),
        _candidate("signal:a", owner=1, event=1_000, observed=1_102),
        _candidate("signal:c", owner=1, event=1_000, observed=1_101),
    )

    ranked = rank_candidates(candidates)

    assert [item.signal.signal_event_id for item in ranked] == [
        "signal:c",
        "signal:a",
        "signal:b",
        "signal:x",
        "signal:y",
        "signal:z",
    ]


def test_arbitration_rejects_unbounded_candidate_batches() -> None:
    candidates = tuple(
        _candidate(
            f"signal:{index:02d}",
            owner=1,
            event=1_000 + index,
            observed=1_100 + index,
        )
        for index in range(65)
    )

    with pytest.raises(ValueError, match="64"):
        rank_candidates(candidates)


def test_candidate_digest_is_input_order_independent_after_ranking() -> None:
    candidate_a = _candidate(
        "signal:a",
        owner=1,
        event=1_001,
        observed=1_002,
    )
    candidate_b = _candidate(
        "signal:b",
        owner=2,
        event=1_000,
        observed=1_001,
    )

    left = freeze_candidate_set((candidate_b, candidate_a))
    right = freeze_candidate_set((candidate_a, candidate_b))

    assert left == right
    assert left.ranked_signal_event_ids == ("signal:a", "signal:b")
    assert left.candidate_count == 2
    assert left.candidate_set_digest.startswith("sha256:")


def _candidate(
    signal_event_id: str,
    *,
    owner: int,
    event: int,
    observed: int,
) -> EntryCandidate:
    return EntryCandidate(
        signal=_signal(
            signal_event_id=signal_event_id,
            occurred_at_ms=event,
            observed_at_ms=observed,
            expires_at_ms=2_000,
        ),
        owner_policy_priority=owner,
    )
