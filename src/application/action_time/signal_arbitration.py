"""Deterministic, bounded arbitration for fresh Action-Time signals.

This module intentionally does not create Tickets, Claims or exchange effects.
It provides the one repeatable selection decision that the PG intake service
persists against already-conserved Signal/Invocation identities.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum


MAX_ACTION_TIME_SIGNAL_BATCH = 64


class ArbitrationDisposition(str, Enum):
    SELECTED = "selected"
    NOT_SELECTED_THIS_ROUND = "not_selected_this_round"
    EXPIRED = "expired"
    CANDIDATE_BLOCKED = "candidate_blocked"
    GLOBAL_BLOCKED = "global_blocked"


@dataclass(frozen=True)
class FreshSignalArbitrationCandidate:
    """Only immutable ordering facts required before Claim/Ticket authority."""

    signal_event_id: str
    owner_policy_priority: int
    candidate_scope_priority: int
    event_time_ms: int
    observed_at_ms: int
    expires_at_ms: int

    def __post_init__(self) -> None:
        if not self.signal_event_id:
            raise ValueError("signal_arbitration_signal_event_id_required")
        if self.expires_at_ms <= 0:
            raise ValueError("signal_arbitration_expiry_required")

    @property
    def sort_key(self) -> tuple[int, int, int, int, str]:
        return (
            self.owner_policy_priority,
            self.candidate_scope_priority,
            self.event_time_ms,
            self.observed_at_ms,
            self.signal_event_id,
        )


@dataclass(frozen=True)
class SignalArbitrationDecision:
    signal_event_id: str
    rank: int
    disposition: ArbitrationDisposition
    reason_code: str = ""
    winner_signal_event_id: str | None = None


CandidateBlocker = Callable[[FreshSignalArbitrationCandidate], str | None]


def deterministically_rank_fresh_signals(
    candidates: Iterable[FreshSignalArbitrationCandidate],
) -> tuple[FreshSignalArbitrationCandidate, ...]:
    """Return exactly the documented ordering, independent of source row order."""

    values = tuple(candidates)
    if len(values) > MAX_ACTION_TIME_SIGNAL_BATCH:
        raise ValueError("action_time_signal_batch_limit_exceeded")
    ids = [candidate.signal_event_id for candidate in values]
    if len(ids) != len(set(ids)):
        raise ValueError("action_time_signal_batch_duplicate_identity")
    return tuple(sorted(values, key=lambda candidate: candidate.sort_key))


def arbitrate_fresh_signals(
    candidates: Iterable[FreshSignalArbitrationCandidate],
    *,
    now_ms: int,
    global_blocker: str | None = None,
    candidate_blocker: CandidateBlocker | None = None,
) -> tuple[SignalArbitrationDecision, ...]:
    """Select at most one candidate and explicitly close every other input.

    A candidate-local failure does not consume the round: arbitration continues
    while time remains.  A global blocker ends the round before a Claim may be
    attempted, retaining the same root cause on every still-fresh candidate.
    """

    ranked = deterministically_rank_fresh_signals(candidates)
    decisions: list[SignalArbitrationDecision] = []
    selected_signal_id: str | None = None
    normalized_global_blocker = str(global_blocker or "").strip()

    for index, candidate in enumerate(ranked, start=1):
        if candidate.expires_at_ms <= int(now_ms):
            decisions.append(
                SignalArbitrationDecision(
                    signal_event_id=candidate.signal_event_id,
                    rank=index,
                    disposition=ArbitrationDisposition.EXPIRED,
                    reason_code="action_time_signal_expired",
                )
            )
            continue
        if normalized_global_blocker:
            decisions.append(
                SignalArbitrationDecision(
                    signal_event_id=candidate.signal_event_id,
                    rank=index,
                    disposition=ArbitrationDisposition.GLOBAL_BLOCKED,
                    reason_code=normalized_global_blocker,
                )
            )
            continue
        if selected_signal_id is not None:
            decisions.append(
                SignalArbitrationDecision(
                    signal_event_id=candidate.signal_event_id,
                    rank=index,
                    disposition=ArbitrationDisposition.NOT_SELECTED_THIS_ROUND,
                    reason_code="action_time_arbitration_winner_selected",
                    winner_signal_event_id=selected_signal_id,
                )
            )
            continue
        blocker = str(candidate_blocker(candidate) or "").strip() if candidate_blocker else ""
        if blocker:
            decisions.append(
                SignalArbitrationDecision(
                    signal_event_id=candidate.signal_event_id,
                    rank=index,
                    disposition=ArbitrationDisposition.CANDIDATE_BLOCKED,
                    reason_code=blocker,
                )
            )
            continue
        selected_signal_id = candidate.signal_event_id
        decisions.append(
            SignalArbitrationDecision(
                signal_event_id=candidate.signal_event_id,
                rank=index,
                disposition=ArbitrationDisposition.SELECTED,
            )
        )
    return tuple(decisions)
