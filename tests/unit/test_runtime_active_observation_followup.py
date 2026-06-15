from __future__ import annotations

import json
from argparse import Namespace

from scripts import runtime_active_observation_followup


def _args(
    *,
    allow_arm_preview=False,
    allow_attempt_policy_prepare=False,
    allow_disabled_smoke=False,
    arm_report_json=None,
    operation_layer_arm_evidence_json=None,
):
    return Namespace(
        loop_packet_json="unused.json",
        output_json=None,
        api_base="http://unit",
        env_file=None,
        allow_arm_preview=allow_arm_preview,
        allow_attempt_policy_prepare=allow_attempt_policy_prepare,
        arm_report_json=arm_report_json,
        operation_layer_arm_evidence_json=operation_layer_arm_evidence_json,
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
        "ids": {
            "authorization_id": "auth-1",
            "disabled_first_real_submit_execution_result_id": "exec-disabled-1",
        },
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


def _attempt_policy_report():
    return {
        "scope": "runtime_attempt_policy_preparation",
        "status": "attempt_policy_prepared",
        "authorization_id": "auth-1",
        "ids": {
            "reservation_id": "reserve-1",
            "attempt_mutation_id": "mutation-1",
            "attempt_outcome_policy_id": "policy-1",
        },
        "steps": [],
        "blockers": [],
        "warnings": [],
        "safety": {
            "mutates_attempt_counter": True,
            "mutates_runtime_budget": True,
            "exchange_write_called": False,
            "exchange_order_submitted": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _attempt_policy_preflight_report(status="pass", blockers=None):
    return {
        "scope": "runtime_attempt_policy_preflight",
        "status": status,
        "authorization_id": "auth-1",
        "http_status": 200,
        "body_status": (
            "ready_for_controlled_submit_adapter"
            if status == "pass"
            else "blocked"
        ),
        "final_gate_verdict": "PASS" if status == "pass" else "BLOCK",
        "blockers": blockers or [],
        "warnings": [],
        "safety": {
            "mutates_attempt_counter": False,
            "mutates_runtime_budget": False,
            "exchange_write_called": False,
            "exchange_order_submitted": False,
            "withdrawal_or_transfer_created": False,
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


def test_followup_cli_exits_zero_for_ready_prepare_review(tmp_path, capsys):
    loop_path = tmp_path / "loop-packet.json"
    output_path = tmp_path / "followup-packet.json"
    loop_path.write_text(
        json.dumps(_loop_packet("ready_for_prepare")),
        encoding="utf-8",
    )

    exit_code = runtime_active_observation_followup.main(
        [
            "--loop-packet-json",
            str(loop_path),
            "--output-json",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["status"] == (
        "ready_for_prepare_records"
    )
    stdout = capsys.readouterr().out
    assert "ready_for_prepare_records" in stdout


def test_followup_cli_refreshes_arm_evidence_when_no_current_arm(tmp_path):
    loop_path = tmp_path / "loop-packet.json"
    output_path = tmp_path / "followup-packet.json"
    arm_evidence_path = tmp_path / "operation-layer-arm-evidence.json"
    loop_path.write_text(
        json.dumps(
            _loop_packet(
                "waiting_for_signal",
                authorization_id=None,
                stop_reason="max_iterations_exhausted",
            )
        ),
        encoding="utf-8",
    )
    arm_evidence_path.write_text(
        json.dumps(
            {
                "status": "stale_blocked",
                "blockers": ["attempts_exhausted"],
                "safety": {"exchange_called": False},
            }
        ),
        encoding="utf-8",
    )

    exit_code = runtime_active_observation_followup.main(
        [
            "--loop-packet-json",
            str(loop_path),
            "--output-json",
            str(output_path),
            "--operation-layer-arm-evidence-json",
            str(arm_evidence_path),
        ]
    )

    arm_evidence = json.loads(arm_evidence_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert arm_evidence["status"] == "no_current_arm_preview"
    assert arm_evidence["source_followup_status"] == (
        "observation_window_complete_no_signal"
    )
    assert arm_evidence["blockers"] == []
    assert arm_evidence["safety"]["stale_arm_evidence_cleared"] is True


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
    assert packet["local_registration_readiness"]["classification"] == (
        "not_ready_for_local_registration_authorization_packet"
    )
    assert packet["safety_invariants"]["real_submit_requested"] is False


def test_followup_prepares_attempt_policy_before_arm_when_allowed():
    calls = []

    def attempt_preparer(auth_id, args):
        calls.append(("attempt", auth_id, args.api_base))
        return _attempt_policy_report()

    def arm_runner(auth_id, args):
        calls.append(("arm", auth_id, args.api_base))
        return _arm_preview_report(blockers=[], warnings=[])

    def disabled_runner(auth_id, args):
        calls.append(("disabled", auth_id, args.api_base))
        return _disabled_smoke_report()

    packet = runtime_active_observation_followup.build_followup_packet(
        _args(
            allow_arm_preview=True,
            allow_attempt_policy_prepare=True,
            allow_disabled_smoke=True,
        ),
        loop_packet=_loop_packet("ready_for_final_gate_preflight"),
        attempt_policy_preflight_runner=lambda auth_id, args: (
            calls.append(("preflight", auth_id, args.api_base))
            or _attempt_policy_preflight_report()
        ),
        attempt_policy_preparer=attempt_preparer,
        arm_preview_runner=arm_runner,
        disabled_smoke_runner=disabled_runner,
    )

    assert packet["status"] == "disabled_smoke_completed"
    assert calls == [
        ("preflight", "auth-1", "http://unit"),
        ("attempt", "auth-1", "http://unit"),
        ("arm", "auth-1", "http://unit"),
        ("disabled", "auth-1", "http://unit"),
    ]
    assert packet["operator_command_plan"]["attempt_policy_preflight_called"] is True
    assert packet["operator_command_plan"]["attempt_policy_prepare_called"] is True
    assert (
        packet["operator_command_plan"][
            "mutating_attempt_consumption_allowed_by_this_packet"
        ]
        is True
    )
    assert packet["safety_invariants"]["attempt_counter_mutated"] is True
    assert packet["safety_invariants"]["runtime_budget_mutated"] is True
    assert packet["safety_invariants"]["exchange_order_submitted"] is False


def test_followup_blocks_attempt_policy_prepare_when_preflight_blocks():
    calls = []

    def attempt_preparer(auth_id, args):
        calls.append(("attempt", auth_id))
        return _attempt_policy_report()

    def arm_runner(auth_id, args):
        calls.append(("arm", auth_id))
        return _arm_preview_report(blockers=[], warnings=[])

    packet = runtime_active_observation_followup.build_followup_packet(
        _args(
            allow_arm_preview=True,
            allow_attempt_policy_prepare=True,
            allow_disabled_smoke=True,
        ),
        loop_packet=_loop_packet("ready_for_final_gate_preflight"),
        attempt_policy_preflight_runner=lambda auth_id, args: (
            calls.append(("preflight", auth_id))
            or _attempt_policy_preflight_report(
                status="blocked",
                blockers=["attempts_exhausted"],
            )
        ),
        attempt_policy_preparer=attempt_preparer,
        arm_preview_runner=arm_runner,
        disabled_smoke_runner=lambda auth_id, args: calls.append(("disabled", auth_id))
        or _disabled_smoke_report(),
    )

    assert packet["status"] == "disabled_smoke_blocked"
    assert calls == [("preflight", "auth-1")]
    assert "attempt_policy_preflight_not_passed" in packet["blockers"]
    assert "attempt_policy_preflight:attempts_exhausted" in packet["blockers"]
    assert packet["operator_command_plan"]["attempt_policy_preflight_called"] is True
    assert packet["operator_command_plan"]["attempt_policy_prepare_called"] is False
    assert packet["safety_invariants"]["attempt_counter_mutated"] is False
    assert packet["safety_invariants"]["runtime_budget_mutated"] is False


def test_followup_classifies_expected_local_registration_boundary():
    disabled_report = _disabled_smoke_report(
        blockers=["preview_disabled_first_real_submit_action_http_404"],
        warnings=["RuntimeExecutionOrderLifecycleAdapterResult not found"],
    )
    disabled_report["ids"].update(
        {
            "trusted_submit_fact_snapshot_id": "facts-1",
            "submit_idempotency_policy_id": "idem-1",
            "protection_creation_failure_policy_id": "protection-policy-1",
        }
    )

    packet = runtime_active_observation_followup.build_followup_packet(
        _args(allow_arm_preview=True, allow_disabled_smoke=True),
        loop_packet=_loop_packet("ready_for_final_gate_preflight"),
        arm_preview_runner=lambda auth_id, args: _arm_preview_report(),
        disabled_smoke_runner=lambda auth_id, args: disabled_report,
    )

    assert packet["status"] == "disabled_smoke_blocked"
    assert packet["local_registration_readiness"]["classification"] == (
        "ready_for_owner_local_registration_authorization_packet"
    )
    assert packet["local_registration_readiness"][
        "expected_non_mutating_preview_stop"
    ] is True
    assert packet["local_registration_readiness"][
        "ready_for_local_registration_authorization_packet"
    ] is True
    assert packet["local_registration_readiness"][
        "requires_fresh_real_signal_revalidation"
    ] is True
    assert packet["local_registration_readiness"][
        "must_not_consume_attempt_for_sample_or_stale_signal"
    ] is True
    assert packet["local_registration_readiness"]["missing_evidence_ids"] == []
    assert packet["operator_command_plan"]["next_step"] == (
        "for_fresh_real_signal_build_local_registration_authorization_packet_"
        "then_owner_confirm_attempt_consumption"
    )
    assert packet["operator_command_plan"][
        "local_registration_authorization_packet_script"
    ] == (
        "scripts/build_runtime_first_real_submit_"
        "local_registration_authorization_packet.py"
    )
    assert packet["operator_command_plan"][
        "mutating_attempt_consumption_allowed_by_this_packet"
    ] is False
    assert packet["operator_command_plan"][
        "requires_fresh_real_signal_revalidation_before_mutation"
    ] is True
    assert packet["safety_invariants"]["attempt_counter_mutated"] is False
    assert packet["safety_invariants"]["runtime_budget_mutated"] is False
    assert packet["safety_invariants"]["exchange_order_submitted"] is False


def test_followup_marks_expected_local_registration_boundary_missing_evidence():
    disabled_report = _disabled_smoke_report(
        blockers=["preview_disabled_first_real_submit_action_http_404"],
        warnings=["RuntimeExecutionOrderLifecycleAdapterResult not found"],
    )

    packet = runtime_active_observation_followup.build_followup_packet(
        _args(allow_arm_preview=True, allow_disabled_smoke=True),
        loop_packet=_loop_packet("ready_for_final_gate_preflight"),
        arm_preview_runner=lambda auth_id, args: _arm_preview_report(),
        disabled_smoke_runner=lambda auth_id, args: disabled_report,
    )

    assert packet["status"] == "disabled_smoke_blocked"
    assert packet["local_registration_readiness"]["classification"] == (
        "expected_non_mutating_preview_stop_missing_evidence"
    )
    assert packet["local_registration_readiness"][
        "ready_for_local_registration_authorization_packet"
    ] is False
    assert packet["local_registration_readiness"]["missing_evidence_ids"] == [
        "trusted_submit_fact_snapshot_id",
        "submit_idempotency_policy_id",
        "protection_creation_failure_policy_id",
    ]
    assert packet["operator_command_plan"]["next_step"] == (
        "resolve_missing_evidence_before_local_registration_authorization_packet"
    )


def test_followup_extracts_ready_authorization_from_multi_runtime_monitor_packet():
    calls = []
    loop_packet = {
        "status": "ready_for_final_gate_preflight",
        "runtime_summaries": [
            {
                "runtime_instance_id": "runtime-blocked",
                "status": "blocked",
                "ready_for_final_gate_preflight": False,
                "prepared_authorization_id": None,
                "blockers": ["next_attempt_gate_blocked"],
            },
            {
                "runtime_instance_id": "runtime-ready",
                "status": "ready_for_final_gate_preflight",
                "ready_for_final_gate_preflight": True,
                "prepared_authorization_id": "auth-ready",
                "blockers": [],
            },
        ],
        "safety_invariants": {
            "exchange_write_called": False,
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

    def arm_runner(auth_id, args):
        calls.append(("arm", auth_id, args.api_base))
        return _arm_preview_report(blockers=[], warnings=[])

    def disabled_runner(auth_id, args):
        calls.append(("disabled", auth_id, args.api_base))
        return _disabled_smoke_report()

    packet = runtime_active_observation_followup.build_followup_packet(
        _args(allow_arm_preview=True, allow_disabled_smoke=True),
        loop_packet=loop_packet,
        arm_preview_runner=arm_runner,
        disabled_smoke_runner=disabled_runner,
    )

    assert packet["source_loop_status"] == "ready_for_final_gate_preflight"
    assert packet["prepared_authorization_id"] == "auth-ready"
    assert packet["status"] == "disabled_smoke_completed"
    assert calls == [
        ("arm", "auth-ready", "http://unit"),
        ("disabled", "auth-ready", "http://unit"),
    ]


def test_followup_reuses_arm_report_json_for_disabled_smoke(tmp_path):
    calls = []
    arm_report = _arm_preview_report(
        blockers=[],
        warnings=["arm-ready"],
        forbidden=True,
    )
    arm_report["ids"] = {
        "trusted_submit_fact_snapshot_id": "facts-1",
        "submit_idempotency_policy_id": "idem-1",
        "local_registration_enablement_decision_id": "local-enable-1",
    }
    arm_path = tmp_path / "arm-report.json"
    arm_path.write_text(json.dumps(arm_report), encoding="utf-8")

    def arm_runner(auth_id, args):
        calls.append(("arm", auth_id))
        return _arm_preview_report()

    def disabled_runner(auth_id, args):
        calls.append(("disabled", auth_id))
        return _disabled_smoke_report()

    packet = runtime_active_observation_followup.build_followup_packet(
        _args(
            allow_arm_preview=True,
            allow_disabled_smoke=True,
            arm_report_json=str(arm_path),
        ),
        loop_packet=_loop_packet("ready_for_final_gate_preflight"),
        arm_preview_runner=arm_runner,
        disabled_smoke_runner=disabled_runner,
    )

    assert packet["status"] == "disabled_smoke_completed"
    assert calls == [("disabled", "auth-1")]
    assert packet["arm_preview_report"]["ids"]["trusted_submit_fact_snapshot_id"] == (
        "facts-1"
    )
    assert packet["operator_command_plan"]["arm_preview_called"] is False
    assert packet["operator_command_plan"]["arm_report_attached"] is True
    assert packet["operator_command_plan"]["arm_report_json_used"] is True
    assert packet["safety_invariants"]["arm_preview_called"] is False
    assert packet["safety_invariants"]["arm_report_json_used"] is True
    assert packet["safety_invariants"]["arm_preview_forbidden_effects"] == []
    assert "arm_report:arm-ready" in packet["warnings"]


def test_followup_blocks_attached_arm_report_with_real_order_safety_flag(tmp_path):
    arm_report = _arm_preview_report(blockers=[], warnings=[])
    arm_report["safety"] = {"exchange_order_submitted": True}
    arm_path = tmp_path / "arm-report.json"
    arm_path.write_text(json.dumps(arm_report), encoding="utf-8")

    packet = runtime_active_observation_followup.build_followup_packet(
        _args(
            allow_disabled_smoke=True,
            arm_report_json=str(arm_path),
        ),
        loop_packet=_loop_packet("ready_for_final_gate_preflight"),
        disabled_smoke_runner=lambda auth_id, args: _disabled_smoke_report(),
    )

    assert packet["status"] == "disabled_smoke_blocked"
    assert "arm_report_contains_forbidden_effects" in packet["blockers"]
    assert packet["safety_invariants"]["arm_preview_forbidden_effects"] == [
        "arm_report.exchange_order_submitted"
    ]


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
        "apply_attempt_mutation:unexpected_attempt_mutation_in_arm_preview"
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


def test_builtin_disabled_smoke_reuses_arm_evidence_ids(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, *, api_base):
            captured["api_base"] = api_base

    class FakeFlow:
        def __init__(self, *, client, config):
            captured["config"] = config

        def run(self):
            return _disabled_smoke_report()

    monkeypatch.setattr(runtime_active_observation_followup, "_load_env_file", lambda path: None)
    monkeypatch.setattr(runtime_active_observation_followup, "UrlLibApiClient", FakeClient)
    monkeypatch.setattr(runtime_active_observation_followup, "FirstRealSubmitApiFlow", FakeFlow)

    runtime_active_observation_followup._run_disabled_smoke(
        authorization_id="auth-1",
        args=_args(allow_disabled_smoke=True),
        evidence_ids={
            "trusted_submit_fact_snapshot_id": "facts-1",
            "submit_idempotency_policy_id": "idem-1",
            "attempt_outcome_policy_id": "attempt-policy-1",
            "protection_creation_failure_policy_id": "protection-policy-1",
            "local_registration_enablement_decision_id": "local-enable-1",
            "owner_real_submit_authorization_id": "owner-auth-1",
            "order_lifecycle_submit_enablement_id": "ol-submit-1",
            "exchange_submit_adapter_enablement_id": "exchange-enable-1",
            "exchange_submit_action_authorization_id": "exchange-action-1",
            "deployment_readiness_evidence_id": "deploy-1",
            "exchange_submit_adapter_result_id": "exchange-result-1",
        },
    )

    config = captured["config"]
    assert config.trusted_submit_fact_snapshot_id == "facts-1"
    assert config.submit_idempotency_policy_id == "idem-1"
    assert config.attempt_outcome_policy_id == "attempt-policy-1"
    assert config.protection_creation_failure_policy_id == "protection-policy-1"
    assert config.local_registration_enablement_decision_id == "local-enable-1"
    assert config.owner_real_submit_authorization_id == "owner-auth-1"
    assert config.order_lifecycle_submit_enablement_id == "ol-submit-1"
    assert config.exchange_submit_adapter_enablement_id == "exchange-enable-1"
    assert config.exchange_submit_action_authorization_id == "exchange-action-1"
    assert config.deployment_readiness_evidence_id == "deploy-1"
    assert config.exchange_submit_adapter_result_id == "exchange-result-1"
