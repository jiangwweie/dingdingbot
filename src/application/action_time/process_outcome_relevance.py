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
    "action_time_ticket_sequence_batch",
    "action_time_refresh_sequence",
}
_SIGNAL_ALREADY_PROCESSED_PREFIXES = (
    "signal_event_already_has_action_time_lane:",
    "signal_event_already_has_action_time_ticket:",
    "signal_event_already_has_protected_submit_attempt:",
)


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
    first_blocker = str(outcome.get("first_blocker") or "").strip()
    if not first_blocker:
        return False
    if first_blocker.startswith(_SIGNAL_ALREADY_PROCESSED_PREFIXES):
        return False
    if not _invocation_outcome_has_typed_lane_identity(outcome):
        return False

    lane_key = _lane_key_from_scope(str(outcome.get("scope_key") or ""))
    if lane_key is None:
        return False
    if not _is_latest_process_lane_outcome(control_state, outcome):
        return False

    return True


def _is_latest_process_lane_outcome(
    control_state: Mapping[str, Any],
    outcome: Mapping[str, Any],
) -> bool:
    """Let newer same-process lane truth supersede historical failures.

    Runtime outcome identity evolved from legacy process+scope rows to typed
    invocation rows.  Their IDs intentionally differ, so current authority
    must be selected by process, lane scope, and update order rather than by
    row identity alone.
    """

    process_name = str(outcome.get("process_name") or "")
    scope_key = str(outcome.get("scope_key") or "")
    outcome_order = (
        int(outcome.get("updated_at_ms") or 0),
        str(outcome.get("process_outcome_id") or ""),
    )
    rows = control_state.get("runtime_process_outcomes")
    if not isinstance(rows, list):
        return True
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("process_name") or "") != process_name:
            continue
        if str(row.get("scope_key") or "") != scope_key:
            continue
        row_order = (
            int(row.get("updated_at_ms") or 0),
            str(row.get("process_outcome_id") or ""),
        )
        if row_order > outcome_order:
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
