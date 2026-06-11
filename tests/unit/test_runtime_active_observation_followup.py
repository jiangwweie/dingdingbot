from __future__ import annotations

from argparse import Namespace

from scripts import runtime_active_observation_followup


def _args(*, allow_arm_preview=False, allow_disabled_smoke=False):
    return Namespace(
        loop_packet_json="unused.json",
        output_json=None,
        api_base="http://unit",
        env_file=None,
        allow_arm_preview=allow_arm_preview,
        allow_disabled_smoke=allow_disabled_smoke,
        skip_disabled_smoke_prerequisite_probe=False,
    )


def _loop_packet(
    status="waiting_for_signal",
    *,
    authorization_id="auth-1",
    forbidden: bool = False,
    stop_reason: str = "running",
):
    return {
        "status": status,
        "stop_reason": stop_reason,
        "latest_summary": {
            "status": status,
            "prepared_authorization_id": authorization_id,
            "exchange_write_called": forbidden,
            "order_created": False,
            "order_lifecycle_called": False,
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
        "safety_invariants": {
            "exchange_write_called": forbidden,
            "order_created": False,
            "order_lifecycle_called": False,
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "executable_execution_intent_created": False,
            "places_order": False,
            "calls_order_lifecycle": False,
        },
    }


def _disabled_smoke_report(*, blockers=None, warnings=None):
    return {
        "script": "runtime_first_real_submit_api_flow",
        "mode": "disabled-smoke",
        "ready_for_real_submit_action": False,
        "ids": {"disabled_first_real_submit_execution_result_id": "exec-disabled-1"},
        "steps": [
            {
                "name": "preview_disabled_first_real_submit_action",
                "path": (
                    "/api/trading-console/"
                    "runtime-execution-first-real-submit-actions/"
                    "authorizations/auth-1"
                ),
                "query_keys": [
                    "owner_confirmed_for_first_real_submit_action",
                ],
            }
        ],
        "blockers": blockers or [],
        "warnings": warnings or [],
        "safety": {
            "no_withdrawal_or_transfer": True,
        },
    }


def _arm_preview_report(*, blockers=None, warnings=None, forbidden=False):
    steps = [
        {
            "name": "hydrate_controlled_submit_plan",
            "path": (
                "/api/trading-console/"
                "runtime-execution-controlled-submit-plans/"
                "authorizations/auth-1"
            ),
        },
        {
            "name": "prepare_machine_evidence",
            "path": (
                "/api/trading-console/"
                "runtime-execution-first-real-submit-evidence-preparations/"
                "authorizations/auth-1"
            ),
        },
    ]
    if forbidden:
        steps.append(
            {
                "name": "apply_attempt_mutation",
                "path": (
                    "/api/trading-console/runtime-execution-attempt-mutations/"
                    "reservations/reserve-1"
                ),
            }
        )
    return {
        "script": "runtime_first_real_submit_api_flow",
        "mode": "arm",
        "ready_for_real_submit_action": False,
        "ids": {"authorization_id": "auth-1"},
        "steps": steps,
        "blockers": blockers
        if blockers is not None
        else ["attempt_consumption_required_before_order_lifecycle_handoff"],
        "warnings": warnings
        if warnings is not None
        else ["attempt_consumption_not_recorded_in_arm_preview"],
    }


def test_followup_waits_when_loop_is_not_ready():
    calls = []

    packet = runtime_active_observation_followup.build_followup_packet(
        _args(allow_disabled_smoke=True),
        loop_packet=_loop_packet(),
        disabled_smoke_runner=lambda auth_id, args: calls.append(auth_id) or {},
    )

    assert packet["status"] == "waiting_for_ready_final_gate_preflight"
    assert packet["prepared_authorization_id"] == "auth-1"
    assert packet["operator_command_plan"]["disabled_smoke_called"] is False
    assert calls == []


def test_followup_marks_completed_no_signal_window_without_running_smoke():
    calls = []

    packet = runtime_active_observation_followup.build_followup_packet(
        _args(allow_arm_preview=True, allow_disabled_smoke=True),
        loop_packet=_loop_packet(
            "waiting_for_signal",
            authorization_id=None,
            stop_reason="max_iterations_exhausted",
        ),
        arm_preview_runner=lambda auth_id, args: calls.append(("arm", auth_id)) or {},
        disabled_smoke_runner=lambda auth_id, args: calls.append(("disabled", auth_id))
        or {},
    )

    assert packet["status"] == "observation_window_complete_no_signal"
    assert packet["source_loop_status"] == "waiting_for_signal"
    assert packet["source_loop_stop_reason"] == "max_iterations_exhausted"
    assert packet["operator_command_plan"]["next_step"] == (
        "review_no_signal_window_or_start_new_observation"
    )
    assert packet["operator_command_plan"]["arm_preview_called"] is False
    assert packet["operator_command_plan"]["disabled_smoke_called"] is False
    assert packet["safety_invariants"]["real_submit_requested"] is False
    assert packet["safety_invariants"]["exchange_order_submitted"] is False
    assert calls == []


def test_followup_surfaces_ready_for_prepare_without_running_smoke():
    calls = []

    packet = runtime_active_observation_followup.build_followup_packet(
        _args(allow_arm_preview=True, allow_disabled_smoke=True),
        loop_packet=_loop_packet("ready_for_prepare"),
        arm_preview_runner=lambda auth_id, args: calls.append(("arm", auth_id)) or {},
        disabled_smoke_runner=lambda auth_id, args: calls.append(("disabled", auth_id))
        or {},
    )

    assert packet["status"] == "ready_for_prepare_records"
    assert packet["operator_command_plan"]["next_step"] == (
        "review_ready_signal_then_continue_prepare_record_path"
    )
    assert packet["operator_command_plan"]["arm_preview_called"] is False
    assert packet["operator_command_plan"]["disabled_smoke_called"] is False
    assert packet["safety_invariants"]["real_submit_requested"] is False
    assert calls == []


def test_followup_requires_explicit_disabled_smoke_flag_when_ready():
    packet = runtime_active_observation_followup.build_followup_packet(
        _args(),
        loop_packet=_loop_packet("ready_for_final_gate_preflight"),
        disabled_smoke_runner=lambda auth_id, args: _disabled_smoke_report(),
    )

    assert packet["status"] == "ready_for_disabled_smoke"
    assert "allow_disabled_smoke_flag_required" in packet["blockers"]
    assert packet["operator_command_plan"]["disabled_smoke_called"] is False


def test_followup_runs_disabled_smoke_only_after_ready_and_allow_flag():
    calls = []

    def runner(auth_id, args):
        calls.append((auth_id, args.api_base))
        return _disabled_smoke_report()

    packet = runtime_active_observation_followup.build_followup_packet(
        _args(allow_disabled_smoke=True),
        loop_packet=_loop_packet("ready_for_final_gate_preflight"),
        disabled_smoke_runner=runner,
    )

    assert packet["status"] == "disabled_smoke_completed"
    assert calls == [("auth-1", "http://unit")]
    assert packet["disabled_smoke_report"]["mode"] == "disabled-smoke"
    assert packet["safety_invariants"]["disabled_smoke_called"] is True
    assert packet["safety_invariants"]["real_submit_requested"] is False
    assert packet["safety_invariants"]["exchange_order_submitted"] is False
    assert packet["safety_invariants"]["attempt_counter_mutated"] is False


def test_followup_runs_arm_preview_before_disabled_smoke_when_allowed():
    calls = []

    def arm_runner(auth_id, args):
        calls.append(("arm", auth_id, args.api_base))
        return _arm_preview_report()

    def disabled_runner(auth_id, args):
        calls.append(("disabled", auth_id, args.api_base))
        return _disabled_smoke_report()

    packet = runtime_active_observation_followup.build_followup_packet(
        _args(allow_arm_preview=True, allow_disabled_smoke=True),
        loop_packet=_loop_packet("ready_for_final_gate_preflight"),
        arm_preview_runner=arm_runner,
        disabled_smoke_runner=disabled_runner,
    )

    assert packet["status"] == "disabled_smoke_completed"
    assert calls == [
        ("arm", "auth-1", "http://unit"),
        ("disabled", "auth-1", "http://unit"),
    ]
    assert packet["operator_command_plan"]["arm_preview_called"] is True
    assert packet["operator_command_plan"]["disabled_smoke_called"] is True
    assert packet["safety_invariants"]["arm_preview_forbidden_effects"] == []
    assert (
        "arm_preview:attempt_consumption_required_before_order_lifecycle_handoff"
        in packet["warnings"]
    )
    assert packet["safety_invariants"]["real_submit_requested"] is False


def test_followup_blocks_when_arm_preview_touches_forbidden_surfaces():
    packet = runtime_active_observation_followup.build_followup_packet(
        _args(allow_arm_preview=True, allow_disabled_smoke=True),
        loop_packet=_loop_packet("ready_for_final_gate_preflight"),
        arm_preview_runner=lambda auth_id, args: _arm_preview_report(forbidden=True),
        disabled_smoke_runner=lambda auth_id, args: _disabled_smoke_report(),
    )

    assert packet["status"] == "disabled_smoke_blocked"
    assert "arm_preview_contains_forbidden_effects" in packet["blockers"]
    assert packet["safety_invariants"]["arm_preview_forbidden_effects"] == [
        "apply_attempt_mutation:attempt_mutation"
    ]


def test_followup_blocks_on_loop_forbidden_effects_before_smoke():
    calls = []

    packet = runtime_active_observation_followup.build_followup_packet(
        _args(allow_disabled_smoke=True),
        loop_packet=_loop_packet("ready_for_final_gate_preflight", forbidden=True),
        disabled_smoke_runner=lambda auth_id, args: calls.append(auth_id) or {},
    )

    assert packet["status"] == "blocked"
    assert "loop_packet_contains_forbidden_effects" in packet["blockers"]
    assert packet["safety_invariants"]["loop_forbidden_effects"]
    assert packet["operator_command_plan"]["disabled_smoke_called"] is False
    assert calls == []


def test_followup_blocks_when_disabled_smoke_touches_forbidden_surfaces():
    report = _disabled_smoke_report()
    report["steps"].append(
        {
            "name": "apply_attempt_mutation",
            "path": (
                "/api/trading-console/runtime-execution-attempt-mutations/"
                "reservations/reserve-1"
            ),
        }
    )

    packet = runtime_active_observation_followup.build_followup_packet(
        _args(allow_disabled_smoke=True),
        loop_packet=_loop_packet("ready_for_final_gate_preflight"),
        disabled_smoke_runner=lambda auth_id, args: report,
    )

    assert packet["status"] == "disabled_smoke_blocked"
    assert "disabled_smoke_contains_forbidden_effects" in packet["blockers"]
    assert packet["safety_invariants"]["disabled_smoke_forbidden_effects"] == [
        "apply_attempt_mutation:attempt_mutation"
    ]
