"""PG-current Runtime Safety State truth and lineage verification.

Runtime Safety State is necessary but not sufficient for an Owner-facing
``tradable_now`` projection. A consumer must also prove that the snapshot is
time-current and belongs to the current signal -> promotion -> action-time lane
-> ticket -> Operation Layer handoff chain.
"""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

from src.infrastructure.runtime_control_state_repository import (
    is_current_action_time_lane,
    is_current_action_time_ticket,
    is_current_live_signal,
    is_current_promotion_candidate,
    is_current_runtime_safety_state,
    runtime_safety_submit_authorized,
)


@dataclass(frozen=True)
class RuntimeSafetyTruth:
    snapshot: dict[str, Any]
    payload_authorized: bool
    lineage_verified: bool
    failure_reasons: tuple[str, ...]

    @property
    def snapshot_id(self) -> str:
        return str(self.snapshot.get("runtime_safety_snapshot_id") or "")

    @property
    def lane_id(self) -> str:
        return str(self.snapshot.get("action_time_lane_input_id") or "")

    @property
    def strategy_group_id(self) -> str:
        return str(self.snapshot.get("strategy_group_id") or "")

    @property
    def submit_authorized(self) -> bool:
        return self.payload_authorized and self.lineage_verified

    def annotated_snapshot(self) -> dict[str, Any]:
        return {
            **self.snapshot,
            "_submit_payload_authorized": self.payload_authorized,
            "_submit_lineage_verified": self.lineage_verified,
            "_submit_truth_failure_reasons": list(self.failure_reasons),
        }


def control_state_now_ms(control_state: dict[str, Any]) -> int:
    try:
        value = int(control_state.get("read_now_ms") or 0)
    except (TypeError, ValueError):
        value = 0
    return value if value > 0 else int(time.time() * 1000)


def current_runtime_safety_truths(
    control_state: dict[str, Any],
) -> list[RuntimeSafetyTruth]:
    now_ms = control_state_now_ms(control_state)
    signals = {
        str(row.get("signal_event_id") or ""): row
        for row in _rows(control_state.get("live_signal_events"))
        if is_current_live_signal(row, now_ms)
    }
    promotions = {
        str(row.get("promotion_candidate_id") or ""): row
        for row in _rows(control_state.get("promotion_candidates"))
        if is_current_promotion_candidate(row, now_ms)
    }
    lanes = {
        str(row.get("action_time_lane_input_id") or ""): row
        for row in _rows(control_state.get("action_time_lane_inputs"))
        if is_current_action_time_lane(row, now_ms)
    }
    tickets = {
        str(row.get("ticket_id") or ""): row
        for row in _rows(control_state.get("action_time_tickets"))
        if is_current_action_time_ticket(row, now_ms)
    }
    handoffs = {
        str(row.get("operation_layer_handoff_id") or ""): row
        for row in _rows(control_state.get("operation_layer_handoffs"))
        if row.get("status") == "handoff_ready"
    }
    ticket_events = _rows(control_state.get("action_time_ticket_events"))

    truths = [
        _evaluate_truth(
            snapshot=row,
            signals=signals,
            promotions=promotions,
            lanes=lanes,
            tickets=tickets,
            handoffs=handoffs,
            ticket_events=ticket_events,
        )
        for row in _rows(control_state.get("runtime_safety_state"))
        if is_current_runtime_safety_state(row, now_ms)
    ]
    return sorted(
        truths,
        key=lambda truth: int(truth.snapshot.get("observed_at_ms") or 0),
        reverse=True,
    )


def current_runtime_safety_truth_by_lane(
    control_state: dict[str, Any],
) -> dict[str, RuntimeSafetyTruth]:
    result: dict[str, RuntimeSafetyTruth] = {}
    for truth in current_runtime_safety_truths(control_state):
        if truth.lane_id and truth.lane_id not in result:
            result[truth.lane_id] = truth
    return result


def verified_submit_truth_by_strategy(
    control_state: dict[str, Any],
) -> dict[str, RuntimeSafetyTruth]:
    result: dict[str, RuntimeSafetyTruth] = {}
    for truth in current_runtime_safety_truths(control_state):
        if (
            truth.submit_authorized
            and truth.strategy_group_id
            and truth.strategy_group_id not in result
        ):
            result[truth.strategy_group_id] = truth
    return result


def _evaluate_truth(
    *,
    snapshot: dict[str, Any],
    signals: dict[str, dict[str, Any]],
    promotions: dict[str, dict[str, Any]],
    lanes: dict[str, dict[str, Any]],
    tickets: dict[str, dict[str, Any]],
    handoffs: dict[str, dict[str, Any]],
    ticket_events: list[dict[str, Any]],
) -> RuntimeSafetyTruth:
    payload_authorized = runtime_safety_submit_authorized(snapshot)
    reasons: list[str] = []
    if not payload_authorized:
        reasons.append("runtime_safety_payload_not_submit_authorized")

    trusted_refs = _dict(snapshot.get("trusted_fact_refs"))
    lane_id = str(snapshot.get("action_time_lane_input_id") or "")
    lane = lanes.get(lane_id, {})
    if not lane:
        reasons.append("current_action_time_lane_missing")

    snapshot_id = str(snapshot.get("runtime_safety_snapshot_id") or "")
    if lane and str(lane.get("runtime_safety_snapshot_id") or "") != snapshot_id:
        reasons.append("lane_runtime_safety_snapshot_mismatch")

    ticket_id = str(trusted_refs.get("ticket_id") or "")
    ticket = tickets.get(ticket_id, {})
    if not ticket:
        reasons.append("current_action_time_ticket_missing")
    elif str(ticket.get("action_time_lane_input_id") or "") != lane_id:
        reasons.append("ticket_lane_mismatch")
    elif ticket.get("status") != "finalgate_ready":
        reasons.append("ticket_not_finalgate_ready")
    elif str(ticket.get("ticket_hash") or "") != str(
        trusted_refs.get("ticket_hash") or ""
    ):
        reasons.append("ticket_hash_reference_mismatch")

    signal_id = str(trusted_refs.get("signal_event_id") or "")
    signal = signals.get(signal_id, {})
    if not signal:
        reasons.append("current_live_signal_missing")
    if lane and str(lane.get("signal_event_id") or "") != signal_id:
        reasons.append("lane_signal_mismatch")
    if ticket and str(ticket.get("signal_event_id") or "") != signal_id:
        reasons.append("ticket_signal_mismatch")

    promotion_id = str(lane.get("promotion_candidate_id") or "") if lane else ""
    promotion = promotions.get(promotion_id, {})
    if not promotion:
        reasons.append("current_promotion_candidate_missing")
    elif str(promotion.get("signal_event_id") or "") != signal_id:
        reasons.append("promotion_signal_mismatch")
    elif promotion.get("status") != "arbitration_won":
        reasons.append("promotion_not_arbitration_won")

    handoff_id = str(trusted_refs.get("operation_layer_handoff_id") or "")
    handoff = handoffs.get(handoff_id, {})
    if not handoff:
        reasons.append("current_operation_layer_handoff_missing")
    else:
        if str(handoff.get("ticket_id") or "") != ticket_id:
            reasons.append("operation_layer_handoff_ticket_mismatch")
        if str(handoff.get("action_time_lane_input_id") or "") != lane_id:
            reasons.append("operation_layer_handoff_lane_mismatch")
        if str(handoff.get("operation_submit_command_id") or "") != str(
            trusted_refs.get("operation_submit_command_id") or ""
        ):
            reasons.append("operation_submit_command_mismatch")
        finalgate_pass_id = str(trusted_refs.get("finalgate_pass_id") or "")
        if str(handoff.get("finalgate_pass_id") or "") != finalgate_pass_id:
            reasons.append("operation_layer_handoff_finalgate_pass_mismatch")
        if str(_dict(handoff.get("command_plan")).get("finalgate_pass_id") or "") != (
            finalgate_pass_id
        ):
            reasons.append("operation_command_finalgate_pass_mismatch")

    finalgate_pass_id = str(trusted_refs.get("finalgate_pass_id") or "")
    if ticket and not any(
        str(event.get("ticket_id") or "") == ticket_id
        and event.get("to_status") == "finalgate_ready"
        and str(_dict(event.get("event_payload")).get("finalgate_pass_id") or "")
        == finalgate_pass_id
        for event in ticket_events
    ):
        reasons.append("finalgate_pass_ticket_event_missing_or_mismatched")

    if ticket:
        for key in (
            "budget_reservation_id",
            "protection_ref_id",
            "public_fact_snapshot_id",
            "action_time_fact_snapshot_id",
            "account_safe_fact_snapshot_id",
            "account_mode_snapshot_id",
        ):
            if str(ticket.get(key) or "") != str(trusted_refs.get(key) or ""):
                reasons.append(f"ticket_{key}_reference_mismatch")

    for label, row in (
        ("lane", lane),
        ("ticket", ticket),
        ("signal", signal),
        ("promotion", promotion),
        ("operation_layer_handoff", handoff),
    ):
        if row:
            _append_scope_mismatches(reasons, label=label, snapshot=snapshot, row=row)

    return RuntimeSafetyTruth(
        snapshot=snapshot,
        payload_authorized=payload_authorized,
        lineage_verified=not reasons,
        failure_reasons=tuple(_dedupe(reasons)),
    )


def _append_scope_mismatches(
    reasons: list[str],
    *,
    label: str,
    snapshot: dict[str, Any],
    row: dict[str, Any],
) -> None:
    for key in ("strategy_group_id", "symbol", "side", "runtime_profile_id"):
        expected = str(snapshot.get(key) or "")
        actual = str(row.get(key) or "")
        if expected and actual and expected != actual:
            reasons.append(f"{label}_{key}_mismatch")


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
