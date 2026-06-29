from __future__ import annotations

import json
import sys

from scripts import runtime_live_signal_operator_supervisor as script


def test_supervisor_continues_waiting_until_max_cycles(tmp_path):
    calls = {"count": 0}

    async def cycle_builder(args):
        calls["count"] += 1
        return _cycle_artifact("waiting_for_runtime_compatible_signal")

    artifact = _run_supervisor(tmp_path, ["--max-cycles", "3"], cycle_builder)

    assert calls["count"] == 3
    assert artifact["status"] == "supervisor_waiting_for_signal"
    assert artifact["cycles_completed"] == 3
    assert artifact["live_operator_supervisor_plan"]["continue_observation_allowed"] is True
    assert artifact["safety_invariants"]["prepare_flow_called"] is False
    assert artifact["safety_invariants"]["places_order"] is False
    assert artifact["safety_invariants"]["exchange_write_called"] is False


def test_supervisor_stops_for_profile_review(tmp_path):
    async def cycle_builder(args):
        return _cycle_artifact(
            "ready_for_owner_runtime_profile_decision",
            profile_proposal_artifact={
                "status": "ready_for_owner_runtime_profile_decision",
                "experimental_runtime_profile_proposal": {
                    "strategy_family_id": "RBR-001",
                },
            },
        )

    artifact = _run_supervisor(tmp_path, ["--max-cycles", "5"], cycle_builder)

    assert artifact["status"] == "supervisor_profile_review_required"
    assert artifact["cycles_completed"] == 1
    assert artifact["live_operator_supervisor_plan"]["requires_owner_runtime_profile_confirmation"] is True
    assert artifact["live_operator_supervisor_plan"]["places_order"] is False
    assert artifact["safety_invariants"]["prepare_records_created"] is False


def test_supervisor_stops_for_prepare_review_without_prepare_records(tmp_path):
    async def cycle_builder(args):
        return _cycle_artifact(
            "ready_for_prepare",
            signal_input_json=str(tmp_path / "ready-signal.json"),
        )

    artifact = _run_supervisor(tmp_path, ["--max-cycles", "5"], cycle_builder)

    assert artifact["status"] == "supervisor_prepare_review_required"
    assert artifact["cycle_summaries"][0]["signal_input_json"].endswith("ready-signal.json")
    assert artifact["live_operator_supervisor_plan"]["requires_prepare_review"] is True
    assert artifact["safety_invariants"]["prepare_flow_called"] is False


def test_supervisor_stops_for_final_gate_after_explicit_prepare_records(tmp_path):
    async def cycle_builder(args):
        return _cycle_artifact(
            "ready_for_final_gate_preflight",
            prepare_flow_called=True,
            prepare_records_created=True,
            shadow_candidate_created=True,
            execution_intent_created=True,
            submit_authorization_created=True,
        )

    artifact = _run_supervisor(
        tmp_path,
        ["--max-cycles", "5", "--allow-prepare-records"],
        cycle_builder,
    )

    assert artifact["status"] == "supervisor_final_gate_review_required"
    assert artifact["live_operator_supervisor_plan"]["requires_final_gate_review"] is True
    assert artifact["safety_invariants"]["prepare_flow_called"] is True
    assert artifact["safety_invariants"]["prepare_records_created"] is True
    assert artifact["safety_invariants"]["shadow_candidate_created"] is True
    assert artifact["safety_invariants"]["recorded_execution_intent_created"] is True
    assert artifact["safety_invariants"]["submit_authorization_created"] is True
    assert artifact["safety_invariants"]["executes_real_submit"] is False


def test_supervisor_blocks_for_forbidden_effect(tmp_path):
    async def cycle_builder(args):
        return _cycle_artifact(
            "waiting_for_runtime_compatible_signal",
            forbidden={"order_created": True},
        )

    artifact = _run_supervisor(tmp_path, ["--max-cycles", "3"], cycle_builder, ok=False)

    assert artifact["status"] == "supervisor_blocked"
    assert artifact["stop_reason"] == "forbidden_effect_detected"
    assert "cycle_1:order_created" in artifact["blockers"]
    assert artifact["live_operator_supervisor_plan"]["next_step"] == "stop_and_review_forbidden_effect"


def test_supervisor_cli_stdout_is_json_only(monkeypatch, capsys, tmp_path):
    async def cycle_builder(args):
        print("inner noisy supervisor")
        return _cycle_artifact("waiting_for_runtime_compatible_signal")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_live_signal_operator_supervisor.py",
            "--runtime-instance-id",
            "runtime-1",
            "--output-dir",
            str(tmp_path / "supervisor"),
            "--max-cycles",
            "1",
        ],
    )

    assert script.main_with_builder_for_test(cycle_builder) == 0

    captured = capsys.readouterr()
    assert json.loads(captured.out)["status"] == "supervisor_waiting_for_signal"
    assert "inner noisy supervisor" not in captured.out
    assert "inner noisy supervisor" in captured.err


def _run_supervisor(tmp_path, extra_args, cycle_builder, *, ok=True):
    output_json = tmp_path / "supervisor.json"
    argv = [
        "--runtime-instance-id",
        "runtime-1",
        "--output-dir",
        str(tmp_path / "cycles"),
        "--output-json",
        str(output_json),
        *extra_args,
    ]
    exit_code = script._main(argv, cycle_builder=cycle_builder)
    assert (exit_code == 0) is ok
    return json.loads(output_json.read_text())


def _cycle_artifact(
    status,
    *,
    signal_input_json=None,
    profile_proposal_artifact=None,
    prepare_flow_called=False,
    prepare_records_created=False,
    shadow_candidate_created=False,
    execution_intent_created=False,
    submit_authorization_created=False,
    forbidden=None,
):
    safety = {
        "prepare_flow_called": prepare_flow_called,
        "prepare_records_created": prepare_records_created,
        "shadow_candidate_created": shadow_candidate_created,
        "recorded_execution_intent_created": execution_intent_created,
        "submit_authorization_created": submit_authorization_created,
        "runtime_created": False,
        "runtime_profile_mutated": False,
        "local_registration_armed": False,
        "exchange_submit_armed": False,
        "execute_real_submit": False,
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "attempt_counter_mutated": False,
        "runtime_budget_mutated": False,
        "position_opened": False,
        "position_closed": False,
        "withdrawal_or_transfer_created": False,
    }
    safety.update(forbidden or {})
    return {
        "scope": "runtime_live_signal_operator_cycle",
        "status": status,
        "runtime_instance_id": "runtime-1",
        "routing_evidence": {
            "status": status
            if status != "ready_for_prepare"
            else "ready_for_current_runtime_signal_prepare",
            "source_selector_status": "runtime_compatible_would_enter_selected"
            if status in {"ready_for_prepare", "ready_for_final_gate_preflight"}
            else "no_would_enter_signal_available",
        },
        "signal_input_json": signal_input_json,
        "runtime_profile_proposal": profile_proposal_artifact,
        "blockers": []
        if status != "waiting_for_runtime_compatible_signal"
        else ["runtime_strategy_signal_not_found_in_strategy_shelf"],
        "live_operator_plan": {
            "next_step": "unit",
            "prepared_authorization_id": (
                "auth-1" if submit_authorization_created else None
            ),
            "requires_real_submit_gate": status == "ready_for_final_gate_preflight",
        },
        "safety_invariants": safety,
    }
