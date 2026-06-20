from __future__ import annotations

import json
import subprocess
import sys

from scripts.build_strategygroup_live_submit_readiness_bridge import (
    build_live_submit_readiness_bridge,
    validate_packet,
)


def _pre_live_ready() -> dict:
    return {
        "status": "pre_live_rehearsal_ready",
        "decision": {
            "pre_live_rehearsal_ready": True,
            "live_submit_ready": False,
            "real_order_authority": False,
        },
        "interaction": {"calls_finalgate": False, "calls_operation_layer": False},
        "safety_invariants": {"actionable_now": False, "real_order_authority": False},
    }


def _daily(status: str = "waiting_for_market") -> dict:
    return {"status": status}


def _cutover(status: str = "live_cutover_waiting_for_fresh_signal") -> dict:
    return {"status": status}


def _goal(status: str = "waiting_for_market") -> dict:
    return {"status": status}


def _completion(status: str = "not_complete_waiting_for_market") -> dict:
    return {"status": status}


def _ready_fact_sources() -> dict:
    return {
        "account_facts": {"status": "fresh"},
        "position_open_order_conflict": {"status": "clear"},
        "budget_coverage": {"status": "sufficient"},
        "protection_template": {"status": "ready"},
        "exchange_rules": {"status": "pass"},
    }


def test_no_signal_pre_live_ready_becomes_owner_waiting_without_blockers() -> None:
    packet = build_live_submit_readiness_bridge(
        pre_live_readiness=_pre_live_ready(),
        daily_check=_daily(),
        live_cutover=_cutover(),
        goal_progress=_goal(),
        completion_audit=_completion(),
    )

    assert packet["status"] == "live_submit_standby_waiting_for_market"
    assert validate_packet(packet) == []
    assert packet["checks"]["blockers"] == []
    assert packet["checks"]["owner_intervention_required"] is False
    assert packet["runtime_consumption"]["pre_live_rehearsal_ready_visible"] is True
    assert packet["runtime_consumption"]["live_submit_ready_false_reason"] == "no_fresh_signal"
    assert packet["owner_state"]["owner_status"] == "waiting_for_opportunity"


def test_fresh_signal_transitions_to_processing_requiredfacts_chain() -> None:
    packet = build_live_submit_readiness_bridge(
        pre_live_readiness=_pre_live_ready(),
        daily_check=_daily("processing"),
        live_cutover=_cutover(),
        goal_progress=_goal("processing"),
        completion_audit=_completion(),
        fact_sources=_ready_fact_sources(),
        signal_status_override="fresh",
    )

    assert packet["status"] == "processing_ready_for_finalgate_checkpoint"
    assert packet["fresh_signal_transition"]["current_state"] == "processing"
    assert packet["fresh_signal_transition"]["next_chain"] == [
        "RequiredFacts",
        "candidate/auth",
        "FinalGate",
        "Operation Layer",
    ]
    assert packet["fresh_signal_transition"]["p05_work_preempted_on_fresh_signal"] is True
    assert packet["owner_state"]["owner_status"] == "processing"
    assert packet["checks"]["ready_for_finalgate_checkpoint"] is True
    assert packet["decision"]["ready_for_finalgate_checkpoint"] is True
    assert packet["decision"]["live_submit_ready"] is False
    assert (
        packet["decision"]["live_submit_ready_false_reason"]
        == "awaiting_finalgate_and_operation_layer"
    )
    assert packet["decision"]["actionable_now"] is False


def test_missing_action_time_fact_is_localized_without_owner_packet_operation() -> None:
    facts = _ready_fact_sources()
    facts["budget_coverage"] = {"status": "insufficient"}
    packet = build_live_submit_readiness_bridge(
        pre_live_readiness=_pre_live_ready(),
        daily_check=_daily("processing"),
        live_cutover=_cutover(),
        goal_progress=_goal("processing"),
        completion_audit=_completion(),
        fact_sources=facts,
        signal_status_override="fresh",
    )

    assert packet["status"] == "processing_action_time_facts_blocked"
    assert "budget_coverage:insufficient" in packet["checks"]["hard_fact_blockers"]
    assert packet["owner_state"]["owner_status"] == "temporarily_unavailable"
    assert packet["owner_state"]["owner_manual_packet_read_required"] is False
    assert packet["decision"]["live_submit_ready"] is False


def test_operation_layer_input_boundary_is_ready_but_still_gated() -> None:
    packet = build_live_submit_readiness_bridge(
        pre_live_readiness=_pre_live_ready(),
        daily_check=_daily(),
        live_cutover=_cutover(),
        goal_progress=_goal(),
        completion_audit=_completion(),
    )
    boundary = packet["operation_layer_input_boundary"]

    assert boundary["input_shape_ready"] is True
    assert boundary["protection_params_shape_ready"] is True
    assert boundary["budget_context_shape_ready"] is True
    assert boundary["idempotency_key_shape_ready"] is True
    assert boundary["recovery_path_shape_ready"] is True
    assert boundary["finalgate_pass_required_before_submit"] is True
    assert boundary["live_submit_still_gated"] is True
    assert boundary["calls_operation_layer"] is False
    assert boundary["places_order"] is False
    assert boundary["real_order_authority"] is False


def test_negative_actionable_now_true_is_rejected() -> None:
    packet = build_live_submit_readiness_bridge(
        pre_live_readiness=_pre_live_ready(),
        daily_check=_daily(),
        live_cutover=_cutover(),
        goal_progress=_goal(),
        completion_audit=_completion(),
    )
    packet["decision"]["actionable_now"] = True

    errors = validate_packet(packet)

    assert "forbidden_true:decision.actionable_now" in errors


def test_negative_live_submit_ready_true_is_rejected_at_bridge_layer() -> None:
    packet = build_live_submit_readiness_bridge(
        pre_live_readiness=_pre_live_ready(),
        daily_check=_daily("processing"),
        live_cutover=_cutover(),
        goal_progress=_goal("processing"),
        completion_audit=_completion(),
        fact_sources=_ready_fact_sources(),
        signal_status_override="fresh",
    )
    packet["decision"]["live_submit_ready"] = True
    packet["checks"]["live_submit_ready"] = True

    errors = validate_packet(packet)

    assert "live_submit_ready_requires_official_chain" in errors
    assert "checks_live_submit_ready_requires_official_chain" in errors


def test_cli_check_mode_passes_after_generation() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_strategygroup_live_submit_readiness_bridge.py"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    check = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_live_submit_readiness_bridge.py",
            "--check",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert check.returncode == 0, check.stdout + check.stderr
    assert json.loads(check.stdout)["status"] == "passed"
