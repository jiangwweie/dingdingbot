"""Current blocking-authority rules for event-scoped runtime process outcomes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.infrastructure.runtime_control_state_repository import (
    is_current_action_time_lane,
    is_current_action_time_ticket,
    is_current_live_signal,
    is_current_promotion_candidate,
    is_current_runtime_safety_state,
)


_BLOCKING_PROCESS_STATES = {
    "business_blocked",
    "retryable_failure",
    "hard_failure",
}
_NON_EVENT_WATERMARKS = {
    "",
    "no_current_fresh_live_signal",
}
_TERMINAL_LIFECYCLE_STATUSES = {
    "lifecycle_closed",
}


def process_outcome_has_current_blocking_authority(
    control_state: Mapping[str, Any],
    outcome: Mapping[str, Any],
) -> bool:
    """Return whether one lane outcome may override current pre-trade readiness.

    Action-Time process outcomes are current projections, but most failures are
    scoped to one signal/Ticket lineage.  Once that lineage has no current
    signal, promotion, lane, Ticket, safety state, or lifecycle object, the row
    remains inspectable as the latest process result without retaining current
    blocker authority.

    Outcomes without an event-scoped watermark fail closed.  They remain
    authoritative until the process+scope current row is superseded by a
    successful outcome.
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

    source_watermark = str(outcome.get("source_watermark") or "").strip()
    if source_watermark in _NON_EVENT_WATERMARKS:
        return True

    return source_watermark in _current_lineage_refs(
        control_state,
        lane_key=lane_key,
        now_ms=_control_state_now_ms(control_state),
    )


def _current_lineage_refs(
    control_state: Mapping[str, Any],
    *,
    lane_key: tuple[str, str, str],
    now_ms: int,
) -> set[str]:
    refs: set[str] = set()
    tickets_by_id: dict[str, Mapping[str, Any]] = {}

    for row in _mapping_rows(control_state.get("live_signal_events")):
        if _row_lane_key(row) == lane_key and is_current_live_signal(dict(row), now_ms):
            _add_refs(refs, row, "signal_event_id")

    for row in _mapping_rows(control_state.get("promotion_candidates")):
        if _row_lane_key(row) == lane_key and is_current_promotion_candidate(
            dict(row), now_ms
        ):
            _add_refs(
                refs,
                row,
                "promotion_candidate_id",
                "signal_event_id",
            )

    for row in _mapping_rows(control_state.get("action_time_lane_inputs")):
        if _row_lane_key(row) == lane_key and is_current_action_time_lane(
            dict(row), now_ms
        ):
            _add_refs(
                refs,
                row,
                "action_time_lane_input_id",
                "promotion_candidate_id",
                "signal_event_id",
            )

    all_tickets = _mapping_rows(control_state.get("action_time_tickets"))
    for row in all_tickets:
        ticket_id = str(row.get("ticket_id") or "")
        if ticket_id:
            tickets_by_id[ticket_id] = row
        if _row_lane_key(row) == lane_key and is_current_action_time_ticket(
            dict(row), now_ms
        ):
            _add_ticket_refs(refs, row)

    for row in _mapping_rows(control_state.get("runtime_safety_state")):
        if not is_current_runtime_safety_state(dict(row), now_ms):
            continue
        trusted_refs = row.get("trusted_fact_refs")
        trusted_refs = trusted_refs if isinstance(trusted_refs, Mapping) else {}
        lane_id = str(
            row.get("action_time_lane_input_id")
            or trusted_refs.get("action_time_lane_input_id")
            or ""
        )
        ticket_id = str(trusted_refs.get("ticket_id") or "")
        if lane_id not in refs and ticket_id not in refs:
            continue
        _add_refs(refs, row, "runtime_safety_snapshot_id", "action_time_lane_input_id")
        _add_refs(
            refs,
            trusted_refs,
            "ticket_id",
            "signal_event_id",
            "promotion_candidate_id",
            "action_time_lane_input_id",
        )

    for row in _mapping_rows(control_state.get("ticket_bound_order_lifecycle_runs")):
        if str(row.get("status") or "") in _TERMINAL_LIFECYCLE_STATUSES:
            continue
        ticket = tickets_by_id.get(str(row.get("ticket_id") or ""))
        if ticket is None or _row_lane_key(ticket) != lane_key:
            continue
        _add_refs(
            refs,
            row,
            "lifecycle_run_id",
            "ticket_id",
            "protected_submit_attempt_id",
        )
        _add_ticket_refs(refs, ticket)

    return refs


def _add_ticket_refs(refs: set[str], ticket: Mapping[str, Any]) -> None:
    _add_refs(
        refs,
        ticket,
        "ticket_id",
        "action_time_lane_input_id",
        "promotion_candidate_id",
        "signal_event_id",
    )


def _add_refs(
    target: set[str],
    row: Mapping[str, Any],
    *keys: str,
) -> None:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            target.add(value)


def _lane_key_from_scope(scope_key: str) -> tuple[str, str, str] | None:
    parts = scope_key.split(":")
    if len(parts) != 4 or parts[0] != "lane" or not all(parts[1:]):
        return None
    return parts[1], parts[2], parts[3]


def _row_lane_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("strategy_group_id") or ""),
        str(row.get("symbol") or ""),
        str(row.get("side") or ""),
    )


def _mapping_rows(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _control_state_now_ms(control_state: Mapping[str, Any]) -> int:
    try:
        return int(control_state.get("read_now_ms") or 0)
    except (TypeError, ValueError):
        return 0
