"""Current blocking-authority rules for event-scoped runtime process outcomes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_BLOCKING_PROCESS_STATES = {
    "business_blocked",
    "retryable_failure",
    "hard_failure",
}
def process_outcome_has_current_blocking_authority(
    control_state: Mapping[str, Any],
    outcome: Mapping[str, Any],
) -> bool:
    """Return whether one lane outcome may override current pre-trade readiness.

    One natural signal expiring must not erase a proven engineering or safety
    blocker.  The process+lane row is the current unresolved outcome and stays
    authoritative until the same lane records a newer successful outcome or a
    newer failed outcome replaces it.  ``source_watermark`` remains lineage
    evidence; it is not a blocker-TTL switch.
    """

    if outcome.get("process_name") != "action_time_ticket_sequence":
        return False
    if outcome.get("process_state") not in _BLOCKING_PROCESS_STATES:
        return False
    if not str(outcome.get("first_blocker") or "").strip():
        return False

    lane_key = _lane_key_from_scope(str(outcome.get("scope_key") or ""))
    if lane_key is None:
        return False

    return True


def _lane_key_from_scope(scope_key: str) -> tuple[str, str, str] | None:
    parts = scope_key.split(":")
    if len(parts) != 4 or parts[0] != "lane" or not all(parts[1:]):
        return None
    return parts[1], parts[2], parts[3]
