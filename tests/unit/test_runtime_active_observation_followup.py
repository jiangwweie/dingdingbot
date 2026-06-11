from __future__ import annotations

from argparse import Namespace

from scripts import runtime_active_observation_followup


def _args(*, allow_disabled_smoke=False):
    return Namespace(
        loop_packet_json="unused.json",
        output_json=None,
        api_base="http://unit",
        env_file=None,
        allow_disabled_smoke=allow_disabled_smoke,
        skip_disabled_smoke_prerequisite_probe=False,
    )


def _loop_packet(
    status="waiting_for_signal",
    *,
    authorization_id="auth-1",
    forbidden: bool = False,
):
    return {
        "status": status,
        "stop_reason": "running",
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
