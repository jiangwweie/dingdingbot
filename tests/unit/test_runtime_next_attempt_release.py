from __future__ import annotations

from decimal import Decimal

import pytest

from tests.unit.test_runtime_active_position_resolution import _followup, _monitor

from src.domain.runtime_active_position_resolution import (
    RuntimeActivePositionResolutionStatus,
    build_runtime_active_position_resolution_artifact,
)
from src.domain.runtime_live_position_monitor import (
    RuntimeLivePositionMonitorStatus,
    RuntimeLiveProtectionStatus,
)
from src.domain.runtime_next_attempt_release import (
    RuntimeNextAttemptReleaseEvidence,
    RuntimeNextAttemptReleaseStatus,
    build_runtime_next_attempt_release_evidence,
)
from src.domain.runtime_post_close_followup import RuntimePostCloseFollowupStatus


NOW_MS = 1781256000000


def _flat_monitor(**overrides):
    values = {
        "status": RuntimeLivePositionMonitorStatus.FLAT_REVIEW_REQUIRED,
        "protection_status": RuntimeLiveProtectionStatus.NO_ACTIVE_POSITION,
        "active_position_present": False,
        "local_active_position_count": 0,
        "exchange_active_position_count": 0,
        "local_open_order_count": 0,
        "exchange_open_stop_order_count": 0,
        "current_qty": None,
        "entry_price": None,
        "mark_price": None,
        "unrealized_pnl": None,
        "hard_stop_boundary_present": False,
        "sl_protection_present": False,
        "tp_protection_present": False,
        "budget_reserved": Decimal("0"),
        "budget_remaining": Decimal("24"),
        "blocks_new_entries_until_resolved": True,
        "can_continue_holding": False,
        "review_required_before_next_attempt": True,
        "owner_action_required": True,
        "blockers": [],
        "warnings": [],
    }
    values.update(overrides)
    return _monitor(**values)


def _resolution(status: RuntimeActivePositionResolutionStatus):
    if status == RuntimeActivePositionResolutionStatus.HOLD_WITH_HARD_STOP:
        return build_runtime_active_position_resolution_artifact(
            monitor=_monitor(),
            exit_plan=None,
            post_close_followup=_followup(),
            now_ms=NOW_MS,
        )
    if status == RuntimeActivePositionResolutionStatus.READY_FOR_CLOSED_REVIEW:
        return build_runtime_active_position_resolution_artifact(
            monitor=_flat_monitor(),
            exit_plan=None,
            post_close_followup=_followup(
                status=RuntimePostCloseFollowupStatus.READY_FOR_CLOSED_REVIEW,
                active_position_present=False,
                owner_close_evidence_status=None,
                owner_close_approval_env=None,
                owner_close_approval_value=None,
                closed_review_facts_status="ready_for_closed_review",
                closed_review_recorded=False,
                required_steps=[
                    "use_resolved_closed_review_order_ids",
                    "record_runtime_closed_trade_review",
                    "verify_next_attempt_gate",
                ],
                completed_steps=[
                    "runtime_flat_observed",
                    "closed_review_facts_resolved",
                ],
                recommended_review_checkpoint=(
                    "run_closed_trade_review_from_resolved_order_facts"
                ),
            ),
            now_ms=NOW_MS,
        )
    if status == RuntimeActivePositionResolutionStatus.READY_FOR_NEXT_ATTEMPT_GATE:
        return build_runtime_active_position_resolution_artifact(
            monitor=_flat_monitor(
                status=RuntimeLivePositionMonitorStatus.FLAT_NO_REVIEW_REQUIRED,
                blocks_new_entries_until_resolved=False,
                review_required_before_next_attempt=False,
                owner_action_required=False,
            ),
            exit_plan=None,
            post_close_followup=_followup(
                status=RuntimePostCloseFollowupStatus.POST_CLOSE_COMPLETE,
                active_position_present=False,
                owner_close_evidence_status=None,
                owner_close_approval_env=None,
                owner_close_approval_value=None,
                closed_review_facts_status="ready_for_closed_review",
                closed_review_recorded=True,
                closed_review_id="review-1",
                required_steps=["verify_next_attempt_gate"],
                completed_steps=[
                    "runtime_flat_observed",
                    "closed_review_recorded",
                    "closed_review_facts_resolved",
                ],
                recommended_review_checkpoint=(
                    "closed_review_recorded_verify_next_attempt_gate"
                ),
            ),
            now_ms=NOW_MS,
        )
    raise AssertionError(status)


def _clear_gate():
    return {
        "status": "clear_for_next_attempt_preflight",
        "next_attempt_gate": {
            "status": "clear_for_preflight",
            "gate": "clear_for_next_preflight",
            "next_attempt_allowed_by_lifecycle": True,
            "blockers": [],
            "warnings": [],
        },
        "blockers": [],
        "warnings": [],
    }


def _blocked_gate():
    return {
        "status": "blocked",
        "next_attempt_gate": {
            "status": "blocked",
            "gate": "closed_trade_review_required",
            "next_attempt_allowed_by_lifecycle": False,
            "blockers": [
                {
                    "id": "NEXT-ATTEMPT-CLOSED-TRADE-REVIEW-REQUIRED",
                    "evidence": "closed review missing",
                },
            ],
            "warnings": [],
        },
        "required_next_step": "record_runtime_closed_trade_review",
        "blockers": [],
        "warnings": [],
    }


def test_release_waits_while_position_is_holdable_but_active():
    evidence = build_runtime_next_attempt_release_evidence(
        active_position_resolution=_resolution(
            RuntimeActivePositionResolutionStatus.HOLD_WITH_HARD_STOP,
        ),
        next_attempt_gate_evidence=None,
        now_ms=NOW_MS,
    )

    assert evidence.status == RuntimeNextAttemptReleaseStatus.WAITING_FOR_POSITION_RESOLUTION
    assert evidence.active_position_present is True
    assert evidence.next_attempt_blocked_by_active_position is True
    assert evidence.strategy_signal_observation_allowed is False
    assert evidence.executable_submit_allowed is False


def test_release_waits_for_closed_review_before_next_gate():
    evidence = build_runtime_next_attempt_release_evidence(
        active_position_resolution=_resolution(
            RuntimeActivePositionResolutionStatus.READY_FOR_CLOSED_REVIEW,
        ),
        next_attempt_gate_evidence=None,
        now_ms=NOW_MS,
    )

    assert evidence.status == RuntimeNextAttemptReleaseStatus.WAITING_FOR_CLOSED_REVIEW
    assert "record_runtime_closed_trade_review" in evidence.required_steps
    assert evidence.shadow_candidate_planning_allowed is False


def test_release_waits_for_next_attempt_gate_when_post_close_complete():
    evidence = build_runtime_next_attempt_release_evidence(
        active_position_resolution=_resolution(
            RuntimeActivePositionResolutionStatus.READY_FOR_NEXT_ATTEMPT_GATE,
        ),
        next_attempt_gate_evidence=None,
        now_ms=NOW_MS,
    )

    assert evidence.status == RuntimeNextAttemptReleaseStatus.WAITING_FOR_NEXT_ATTEMPT_GATE
    assert evidence.required_steps == ["verify_next_attempt_gate"]
    assert evidence.strategy_signal_observation_allowed is False


def test_release_allows_strategy_signal_after_flat_review_and_clear_gate():
    evidence = build_runtime_next_attempt_release_evidence(
        active_position_resolution=_resolution(
            RuntimeActivePositionResolutionStatus.READY_FOR_NEXT_ATTEMPT_GATE,
        ),
        next_attempt_gate_evidence=_clear_gate(),
        now_ms=NOW_MS,
    )

    assert evidence.status == RuntimeNextAttemptReleaseStatus.READY_FOR_STRATEGY_SIGNAL
    assert evidence.strategy_signal_observation_allowed is True
    assert evidence.shadow_candidate_planning_allowed is True
    assert evidence.executable_submit_allowed is False
    assert evidence.requires_official_final_gate is True
    assert "wait_for_fresh_strategy_signal" in evidence.required_steps
    payload = evidence.model_dump(mode="json")
    assert payload["next_attempt_release_evidence_only"] is True
    assert "packet_only" not in payload


def test_release_blocks_when_next_gate_blocks():
    evidence = build_runtime_next_attempt_release_evidence(
        active_position_resolution=_resolution(
            RuntimeActivePositionResolutionStatus.READY_FOR_NEXT_ATTEMPT_GATE,
        ),
        next_attempt_gate_evidence=_blocked_gate(),
        now_ms=NOW_MS,
    )

    assert evidence.status == RuntimeNextAttemptReleaseStatus.BLOCKED
    assert (
        "NEXT-ATTEMPT-CLOSED-TRADE-REVIEW-REQUIRED"
        in evidence.blockers
    )
    assert evidence.recommended_review_checkpoint == "record_runtime_closed_trade_review"
    assert evidence.strategy_signal_observation_allowed is False


def test_release_rejects_legacy_packet_only_input():
    evidence = build_runtime_next_attempt_release_evidence(
        active_position_resolution=_resolution(
            RuntimeActivePositionResolutionStatus.READY_FOR_NEXT_ATTEMPT_GATE,
        ),
        next_attempt_gate_evidence=_clear_gate(),
        now_ms=NOW_MS,
    )
    legacy_payload = evidence.model_dump(mode="json")
    legacy_payload["packet_only"] = legacy_payload.pop(
        "next_attempt_release_evidence_only",
    )

    with pytest.raises(ValueError):
        RuntimeNextAttemptReleaseEvidence.model_validate(legacy_payload)
