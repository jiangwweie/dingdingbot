from __future__ import annotations

import json

from scripts import build_runtime_supervisor_operator_summary as script


def test_summary_classifies_no_signal_waiting_window(tmp_path):
    artifact = _supervisor_artifact(
        "supervisor_waiting_for_signal",
        stop_reason="max_cycles_reached",
        cycles=[
            _cycle(1, "waiting_for_runtime_compatible_signal"),
            _cycle(2, "waiting_for_runtime_compatible_signal"),
        ],
    )

    summary = script.build_summary(artifact)

    assert summary["status"] == "operator_waiting_for_signal"
    assert "operator_command_plan" not in summary
    assert summary["summary_plan"]["not_execution_authority"] is True
    assert summary["summary_plan"]["next_step"] == (
        "continue_live_signal_operator_supervision"
    )
    assert summary["signal_state"]["no_signal_window"] is True
    assert summary["signal_state"]["selector_status_counts"] == {
        "no_would_enter_signal_available": 2,
    }
    assert summary["signal_state"]["blocker_counts"] == {
        "runtime_strategy_signal_not_found_in_strategy_shelf": 2,
    }
    assert summary["right_tail_objective_context"]["no_signal_is_not_failure"] is True
    assert summary["summary_plan"]["places_order"] is False
    assert summary["safety_invariants"]["summary_evidence_only"] is True
    assert "read_packet_only" not in summary["safety_invariants"]
    assert summary["safety_invariants"]["database_write"] is False
    assert summary["safety_invariants"]["exchange_write_called"] is False


def test_summary_classifies_profile_review_required():
    artifact = _supervisor_artifact(
        "supervisor_profile_review_required",
        stop_reason="review_required:ready_for_owner_runtime_profile_decision",
        cycles=[_cycle(1, "ready_for_owner_runtime_profile_decision", selector="profile")],
    )

    summary = script.build_summary(artifact)

    assert summary["status"] == "operator_profile_review_required"
    assert summary["summary_plan"]["next_step"] == "review_runtime_profile_proposal"
    assert (
        summary["summary_plan"]["requires_owner_runtime_profile_confirmation"]
        is True
    )
    assert summary["summary_plan"]["creates_runtime"] is False
    assert summary["summary_plan"]["mutates_runtime_profile"] is False


def test_summary_classifies_prepare_review_required():
    artifact = _supervisor_artifact(
        "supervisor_prepare_review_required",
        stop_reason="review_required:ready_for_prepare",
        cycles=[
            _cycle(
                1,
                "ready_for_prepare",
                selector="runtime_compatible_would_enter_selected",
            ),
        ],
    )

    summary = script.build_summary(artifact)

    assert summary["status"] == "operator_prepare_review_required"
    assert summary["summary_plan"]["requires_prepare_review"] is True
    assert summary["summary_plan"]["next_step"] == (
        "review_ready_signal_then_rerun_with_allow_prepare_records"
    )
    assert summary["summary_plan"]["creates_shadow_candidate"] is False
    assert summary["summary_plan"]["creates_submit_authorization"] is False


def test_summary_classifies_final_gate_review_required():
    artifact = _supervisor_artifact(
        "supervisor_final_gate_review_required",
        stop_reason="review_required:ready_for_final_gate_preflight",
        cycles=[
            _cycle(
                1,
                "ready_for_final_gate_preflight",
                selector="runtime_compatible_would_enter_selected",
            ),
        ],
        safety={
            "prepare_flow_called": True,
            "prepare_records_created": True,
            "shadow_candidate_created": True,
            "recorded_execution_intent_created": True,
            "submit_authorization_created": True,
        },
    )

    summary = script.build_summary(artifact)

    assert summary["status"] == "operator_final_gate_review_required"
    assert summary["summary_plan"]["requires_final_gate_review"] is True
    assert summary["summary_plan"]["next_step"] == (
        "run_official_final_gate_preview_before_any_submit"
    )
    assert summary["summary_plan"]["executes_real_submit"] is False


def test_summary_blocks_when_supervisor_reports_forbidden_effect():
    artifact = _supervisor_artifact(
        "supervisor_blocked",
        stop_reason="forbidden_effect_detected",
        cycles=[
            _cycle(
                1,
                "waiting_for_runtime_compatible_signal",
                forbidden_effects=["order_created"],
            ),
        ],
        blockers=["cycle_1:order_created"],
        safety={"cycles_have_forbidden_effects": True},
    )

    summary = script.build_summary(artifact)

    assert summary["status"] == "operator_supervisor_blocked"
    assert summary["summary_plan"]["next_step"] == (
        "stop_and_review_supervisor_blocker"
    )
    assert summary["safety_invariants"]["source_has_forbidden_effects"] is True
    assert "cycle_1:order_created" in summary["safety_invariants"]["source_forbidden_effects"]
    assert "cycles_have_forbidden_effects" in summary["safety_invariants"][
        "source_forbidden_effects"
    ]


def test_cli_writes_summary_and_returns_blocked_exit_code(tmp_path, capsys):
    supervisor_json = tmp_path / "supervisor.json"
    output_json = tmp_path / "summary.json"
    supervisor_json.write_text(
        json.dumps(
            _supervisor_artifact(
                "supervisor_blocked",
                stop_reason="forbidden_effect_detected",
                cycles=[_cycle(1, "blocked", forbidden_effects=["exchange_write_called"])],
                safety={"cycles_have_forbidden_effects": True},
            )
        ),
        encoding="utf-8",
    )

    exit_code = script._main(
        [
            "--supervisor-json",
            str(supervisor_json),
            "--output-json",
            str(output_json),
        ]
    )

    assert exit_code == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)["status"] == "operator_supervisor_blocked"
    assert json.loads(output_json.read_text())["status"] == "operator_supervisor_blocked"


def _supervisor_artifact(
    status,
    *,
    stop_reason,
    cycles,
    blockers=None,
    safety=None,
):
    source_safety = {
        "cycles_have_forbidden_effects": False,
        "prepare_flow_called": False,
        "prepare_records_created": False,
        "shadow_candidate_created": False,
        "recorded_execution_intent_created": False,
        "submit_authorization_created": False,
        "places_order": False,
        "calls_order_lifecycle": False,
        "executes_real_submit": False,
        "exchange_write_called": False,
        "runtime_budget_mutated": False,
        "position_opened": False,
        "position_closed": False,
        "withdrawal_or_transfer_created": False,
    }
    source_safety.update(safety or {})
    return {
        "scope": "runtime_live_signal_operator_supervisor",
        "status": status,
        "runtime_instance_id": "runtime-1",
        "cycles_completed": len(cycles),
        "stop_reason": stop_reason,
        "latest_cycle_status": cycles[-1]["status"],
        "latest_cycle_path": cycles[-1]["cycle_path"],
        "cycle_summaries": cycles,
        "blockers": blockers or [],
        "warnings": [],
        "summary_plan": {"next_step": "source"},
        "safety_invariants": source_safety,
    }


def _cycle(
    index,
    status,
    *,
    selector="no_would_enter_signal_available",
    forbidden_effects=None,
):
    return {
        "cycle_index": index,
        "cycle_path": f"/tmp/cycle-{index:03d}.json",
        "status": status,
        "routing_status": status,
        "routing_source_selector_status": selector,
        "blockers": []
        if status != "waiting_for_runtime_compatible_signal"
        else ["runtime_strategy_signal_not_found_in_strategy_shelf"],
        "signal_input_json": None,
        "next_step": "source-cycle",
        "prepared_authorization_id": None,
        "requires_owner_runtime_profile_confirmation": False,
        "requires_real_submit_gate": False,
        "prepare_flow_called": False,
        "prepare_records_created": False,
        "shadow_candidate_created": False,
        "recorded_execution_intent_created": False,
        "submit_authorization_created": False,
        "forbidden_effects": forbidden_effects or [],
    }
