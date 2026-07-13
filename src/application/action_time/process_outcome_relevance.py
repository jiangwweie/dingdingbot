"""Current blocking-authority rules for event-scoped runtime process outcomes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.domain.runtime_lane_identity import RuntimeLaneIdentity

_BLOCKING_PROCESS_STATES = {
    "business_blocked",
    "retryable_failure",
    "hard_failure",
}
_ACTION_TIME_PROCESS_NAMES = {
    "action_time_ticket_sequence",
    "action_time_refresh_sequence",
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

    if outcome.get("process_name") not in _ACTION_TIME_PROCESS_NAMES:
        return False
    if outcome.get("process_state") not in _BLOCKING_PROCESS_STATES:
        return False
    if not str(outcome.get("first_blocker") or "").strip():
        return False
    if not _invocation_outcome_has_typed_lane_identity(outcome):
        return False

    lane_key = _lane_key_from_scope(str(outcome.get("scope_key") or ""))
    if lane_key is None:
        return False

    return True


def _invocation_outcome_has_typed_lane_identity(
    outcome: Mapping[str, Any],
) -> bool:
    """Require full immutable lane identity on invocation-backed outcomes.

    Historical pre-migration outcomes remain readable for forensic continuity,
    but any row that declares an ActionTimeInvocation is a new hot-path fact.
    It must therefore be typed enough to prevent one lane's blocker from being
    projected onto another lane with the same strategy/symbol display fields.
    """

    if not str(outcome.get("action_time_invocation_id") or "").strip():
        return True
    if str(outcome.get("scope_kind") or "") != "runtime_lane":
        return False
    try:
        identity = RuntimeLaneIdentity.model_validate(
            {
                field: outcome.get(field)
                for field in RuntimeLaneIdentity.model_fields
            }
        )
    except (TypeError, ValueError):
        return False
    return (
        str(outcome.get("lane_identity_key") or "") == identity.identity_key
        and bool(str(outcome.get("source_watermark") or "").strip())
    )


def _lane_key_from_scope(scope_key: str) -> tuple[str, str, str] | None:
    parts = scope_key.split(":")
    if len(parts) != 4 or parts[0] != "lane" or not all(parts[1:]):
        return None
    return parts[1], parts[2], parts[3]
