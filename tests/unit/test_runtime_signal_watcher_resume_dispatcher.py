from __future__ import annotations

import json
from pathlib import Path

import scripts.runtime_signal_watcher_resume_dispatcher as dispatcher
from scripts.runtime_signal_watcher_resume_dispatcher import build_dispatch_packet, main


def _resume_pack(status: str = "waiting_for_market") -> dict:
    action = {
        "status": status,
        "next_step": "continue_watcher_observation",
        "signal_input_json": None,
        "shadow_candidate_id": None,
        "prepared_authorization_id": None,
        "allowed_auto_actions": ["continue_watcher_observation"],
        "places_order": False,
        "calls_order_lifecycle": False,
        "exchange_write_called": False,
        "withdrawal_or_transfer_requested": False,
    }
    if status == "ready_for_action_time_final_gate":
        action.update(
            {
                "next_step": "run_official_action_time_final_gate_preflight",
                "signal_input_json": "/reports/runtime-mpg-1/signal-input.json",
                "shadow_candidate_id": "shadow-candidate-1",
                "prepared_authorization_id": "auth-ready-1",
                "allowed_auto_actions": [
                    "run_official_action_time_final_gate_preflight"
                ],
                "requires_fresh_action_time_facts": True,
            }
        )
    return {
        "scope": "runtime_signal_watcher_post_signal_resume_pack",
        "status": status,
        "can_continue_steps_5_8": status == "ready_for_action_time_final_gate",
        "selected_runtime_instance_ids": ["runtime-mpg-1"],
        "signal_input_json": action["signal_input_json"],
        "shadow_candidate_id": action["shadow_candidate_id"],
        "prepared_authorization_id": action["prepared_authorization_id"],
        "action_time_resume": action,
        "owner_state": {
            "status": status,
            "blocker_class": "waiting_for_market"
            if status == "waiting_for_market"
            else "none",
        },
        "safety_invariants": {
            "places_order": False,
            "calls_order_lifecycle": False,
            "exchange_write_called": False,
            "mutates_pg": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "forbidden_effect_flags": [],
        },
        "blockers": [],
        "warnings": [],
    }


def _fresh_authorization_resume_pack(tmp_path: Path) -> dict:
    handoff_path = tmp_path / "handoff.json"
    handoff_path.write_text(
        json.dumps(
            {
                "api_payload": {
                    "handoff_id": "handoff-runtime-mpg-1",
                    "runtime_instance_id": "runtime-mpg-1",
                    "readiness_packet_id": "readiness-1",
                    "status": "ready_for_official_submit_call",
                }
            }
        ),
        encoding="utf-8",
    )
    return {
        "scope": "runtime_fresh_attempt_readiness_packet",
        "status": "ready_for_fresh_submit_authorization",
        "runtime_instance_id": "runtime-mpg-1",
        "selected_runtime_instance_ids": ["runtime-mpg-1"],
        "artifact_paths": {
            "readiness_handoff_bridge": str(handoff_path),
        },
        "action_time_resume": {
            "status": "ready_for_fresh_submit_authorization",
            "next_step": "bind_or_resolve_fresh_submit_authorization",
            "allowed_auto_actions": [
                "bind_or_resolve_fresh_submit_authorization"
            ],
            "places_order": False,
            "calls_order_lifecycle": False,
            "exchange_write_called": False,
            "withdrawal_or_transfer_requested": False,
        },
        "owner_state": {
            "status": "ready_for_fresh_submit_authorization",
            "blocker_class": "none",
        },
        "safety_invariants": {
            "places_order": False,
            "calls_order_lifecycle": False,
            "exchange_write_called": False,
            "mutates_pg": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "forbidden_effect_flags": [],
        },
        "blockers": [],
        "warnings": [],
    }


def test_dispatcher_waiting_for_market_is_no_action():
    packet = build_dispatch_packet(
        resume_pack=_resume_pack(),
        source_path=Path("/tmp/post-signal-resume-pack.json"),
    )

    assert packet["status"] == "waiting_for_market"
    assert packet["blocker_class"] == "waiting_for_market"
    assert packet["dispatch_action"] == "continue_watcher_observation"
    assert packet["dispatch_status"] == "no_action_continue_observation"
    assert packet["command_plan"] is None
    assert packet["safety_invariants"]["places_order"] is False


def test_dispatcher_ready_for_finalgate_emits_official_preflight_plan():
    packet = build_dispatch_packet(
        resume_pack=_resume_pack("ready_for_action_time_final_gate"),
        source_path=Path("/tmp/post-signal-resume-pack.json"),
        api_base="http://127.0.0.1:18080",
    )

    assert packet["status"] == "ready_for_action_time_final_gate"
    assert packet["blocker_class"] == "none"
    assert packet["dispatch_action"] == "run_official_action_time_final_gate_preflight"
    assert packet["dispatch_status"] == "official_finalgate_preflight_dispatch_ready"
    assert packet["blockers"] == []
    command = packet["command_plan"]
    assert command["method"] == "GET"
    assert command["prepared_authorization_id"] == "auth-ready-1"
    assert (
        command["path"]
        == "/api/trading-console/runtime-execution-controlled-submit-preflights/"
        "authorizations/auth-ready-1"
    )
    assert command["places_order"] is False
    assert command["exchange_write_called"] is False


def test_dispatcher_fresh_authorization_emits_binding_plan(tmp_path):
    packet = build_dispatch_packet(
        resume_pack=_fresh_authorization_resume_pack(tmp_path),
        source_path=Path("/tmp/post-signal-resume-pack.json"),
        api_base="http://127.0.0.1:18080",
    )

    assert packet["status"] == "ready_for_fresh_submit_authorization"
    assert packet["blocker_class"] == "none"
    assert packet["dispatch_action"] == (
        "run_official_fresh_submit_authorization_binding"
    )
    assert packet["dispatch_status"] == (
        "official_fresh_authorization_binding_dispatch_ready"
    )
    assert packet["owner_state"]["blocked_at"] == "fresh_submit_authorization"
    command = packet["command_plan"]
    assert command["method"] == "POST"
    assert command["path"] == (
        "/api/trading-console/strategy-runtimes/runtime-mpg-1/"
        "official-submit-handoff-fresh-authorizations/bind"
    )
    assert command["calls_official_submit_endpoint"] is False
    assert command["places_order"] is False
    assert command["exchange_write_called"] is False


def test_dispatcher_accepts_fresh_attempt_readiness_alias_next_step(tmp_path):
    resume = _fresh_authorization_resume_pack(tmp_path)
    resume.pop("action_time_resume")
    resume["status"] = "waiting_for_fresh_authorization"
    resume["operator_command_plan"] = {
        "next_step": "bind_or_resolve_fresh_authorization",
    }

    packet = build_dispatch_packet(
        resume_pack=resume,
        source_path=Path("/tmp/fresh-attempt-readiness.json"),
        api_base="http://127.0.0.1:18080",
    )

    assert packet["status"] == "waiting_for_fresh_authorization"
    assert packet["dispatch_action"] == (
        "run_official_fresh_submit_authorization_binding"
    )
    assert packet["command_plan"]["method"] == "POST"
    assert packet["command_plan"]["places_order"] is False


def test_dispatcher_execute_fresh_authorization_binding_reaches_finalgate_checkpoint(
    tmp_path,
    monkeypatch,
):
    calls = []
    monkeypatch.setattr(
        dispatcher,
        "_session_cookie",
        lambda: ("brc_operator_session=fake-session", None),
    )

    def _request_json(**kwargs):
        calls.append(kwargs)
        if kwargs["method"] == "GET":
            return {
                "http_status": 200,
                "error": False,
                "body": {
                    "status": "ready_for_controlled_submit_adapter",
                    "final_gate_verdict": "pass",
                    "blockers": [],
                    "warnings": [],
                    "submit_executed": False,
                    "order_created": False,
                    "exchange_called": False,
                    "owner_bounded_execution_called": False,
                    "order_lifecycle_called": False,
                },
            }
        return {
            "http_status": 200,
            "error": False,
            "body": {
                "status": "created_authorization",
                "blockers": [],
                "warnings": [],
                "fresh_submit_authorization_id": "fresh-auth-1",
                "execution_intent_id": "intent-1",
                "runtime_execution_intent_draft_id": "draft-1",
                "ready_for_fresh_authorization_resolution": True,
                "ready_for_disabled_smoke_call": True,
                "binding_source": "existing_intent",
                "creates_execution_intent": False,
                "creates_submit_authorization": True,
                "calls_official_submit_endpoint": False,
                "requests_real_gateway_action": False,
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "runtime_budget_mutated": False,
                "withdrawal_or_transfer_created": False,
            },
        }

    monkeypatch.setattr(dispatcher, "_request_json", _request_json)

    packet = build_dispatch_packet(
        resume_pack=_fresh_authorization_resume_pack(tmp_path),
        source_path=Path("/tmp/post-signal-resume-pack.json"),
        api_base="http://127.0.0.1:18080",
        execute_preflight=True,
    )

    assert packet["status"] == "finalgate_ready"
    assert packet["blocker_class"] == "none"
    assert packet["dispatch_action"] == "prepare_official_operation_layer_submit"
    assert packet["fresh_submit_authorization_id"] == "fresh-auth-1"
    assert packet["fresh_authorization_binding_result"]["called"] is True
    assert packet["owner_state"]["automatic_recovery_action"] == (
        "prepare_official_operation_layer_submit_evidence_from_passed_preflight"
    )
    assert packet["safety_invariants"]["official_fresh_authorization_binding_called"]
    assert packet["safety_invariants"]["official_finalgate_preflight_called"] is True
    assert packet["safety_invariants"]["creates_submit_authorization"] is True
    assert packet["safety_invariants"]["pg_prepare_evidence_mutated"] is True
    assert packet["safety_invariants"]["mutates_pg"] is True
    assert packet["safety_invariants"]["calls_official_submit_endpoint"] is False
    assert packet["safety_invariants"]["places_order"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False
    assert packet["operation_layer_command_plan"]["authorization_id"] == "fresh-auth-1"
    assert len(calls) == 2
    bind_call = calls[0]
    assert bind_call["method"] == "POST"
    assert "runtime-execution-first-real-submit-actions" not in bind_call["url"]
    assert bind_call["body"]["no_exchange_side_effects"] is True
    assert bind_call["body"]["handoff_packet"]["handoff_id"] == (
        "handoff-runtime-mpg-1"
    )
    preflight_call = calls[1]
    assert preflight_call["method"] == "GET"
    assert preflight_call["url"].endswith(
        "/runtime-execution-controlled-submit-preflights/authorizations/fresh-auth-1"
    )


def test_dispatcher_execute_fresh_authorization_binding_blocks_forbidden_effect(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        dispatcher,
        "_session_cookie",
        lambda: ("brc_operator_session=fake-session", None),
    )
    monkeypatch.setattr(
        dispatcher,
        "_request_json",
        lambda **_kwargs: {
            "http_status": 200,
            "error": False,
            "body": {
                "status": "created_authorization",
                "blockers": [],
                "fresh_submit_authorization_id": "fresh-auth-1",
                "ready_for_fresh_authorization_resolution": True,
                "exchange_write_called": True,
            },
        },
    )

    packet = build_dispatch_packet(
        resume_pack=_fresh_authorization_resume_pack(tmp_path),
        source_path=Path("/tmp/post-signal-resume-pack.json"),
        execute_preflight=True,
    )

    assert packet["status"] == "blocked"
    assert packet["blocker_class"] == "hard_safety_stop"
    assert packet["dispatch_status"] == (
        "blocked_by_fresh_authorization_binding_forbidden_effect"
    )
    assert "fresh_authorization_binding_effect:exchange_write_called" in (
        packet["blockers"]
    )
    assert packet["safety_invariants"]["places_order"] is False


def test_dispatcher_blocks_fresh_authorization_without_handoff_json(tmp_path):
    resume = _fresh_authorization_resume_pack(tmp_path)
    resume["artifact_paths"] = {}

    packet = build_dispatch_packet(
        resume_pack=resume,
        source_path=Path("/tmp/post-signal-resume-pack.json"),
    )

    assert packet["status"] == "blocked"
    assert packet["blocker_class"] == "missing_fact"
    assert packet["dispatch_status"] == "blocked_by_missing_handoff_json"
    assert "missing_fact:handoff_json" in packet["blockers"]
    assert packet["owner_state"]["blocked_at"] == "fresh_submit_authorization"


def test_dispatcher_execute_preflight_passes_to_operation_layer_checkpoint(monkeypatch):
    monkeypatch.setattr(
        dispatcher,
        "_session_cookie",
        lambda: ("brc_operator_session=fake-session", None),
    )
    monkeypatch.setattr(
        dispatcher,
        "_request_json",
        lambda **_kwargs: {
            "http_status": 200,
            "error": False,
            "body": {
                "status": "ready_for_controlled_submit_adapter",
                "final_gate_verdict": "pass",
                "blockers": [],
                "warnings": [],
                "submit_executed": False,
                "order_created": False,
                "exchange_called": False,
                "owner_bounded_execution_called": False,
                "order_lifecycle_called": False,
            },
        },
    )

    packet = build_dispatch_packet(
        resume_pack=_resume_pack("ready_for_action_time_final_gate"),
        source_path=Path("/tmp/post-signal-resume-pack.json"),
        api_base="http://127.0.0.1:18080",
        execute_preflight=True,
    )

    assert packet["status"] == "finalgate_ready"
    assert packet["blocker_class"] == "none"
    assert packet["dispatch_status"] == "official_finalgate_preflight_passed"
    assert packet["dispatch_action"] == "prepare_official_operation_layer_submit"
    assert packet["owner_state"]["status"] == "finalgate_ready"
    assert packet["owner_state"]["automatic_recovery_action"] == (
        "prepare_official_operation_layer_submit_evidence_from_passed_preflight"
    )
    assert packet["finalgate_preflight_result"]["called"] is True
    assert packet["operation_layer_command_plan"]["places_order"] is False
    assert packet["operation_layer_command_plan"]["official_endpoint_method"] == "POST"
    assert packet["operation_layer_command_plan"]["official_endpoint_path"] == (
        "/api/trading-console/"
        "runtime-execution-first-real-submit-actions/authorizations/auth-ready-1"
    )
    assert (
        packet["operation_layer_command_plan"][
            "owner_confirmed_for_first_real_submit_action"
        ]
        is True
    )
    assert "exchange_submit_action_authorization_id" in (
        packet["operation_layer_command_plan"]["requires_evidence_ids"]
    )
    assert packet["safety_invariants"]["official_finalgate_preflight_called"] is True
    assert packet["safety_invariants"]["official_operation_layer_submit_called"] is False
    assert packet["safety_invariants"]["places_order"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False


def test_dispatcher_execute_preflight_blocks_finalgate_failure(monkeypatch):
    monkeypatch.setattr(
        dispatcher,
        "_session_cookie",
        lambda: ("brc_operator_session=fake-session", None),
    )
    monkeypatch.setattr(
        dispatcher,
        "_request_json",
        lambda **_kwargs: {
            "http_status": 200,
            "error": False,
            "body": {
                "status": "blocked",
                "final_gate_verdict": "block",
                "blockers": ["active_position_conflict"],
                "warnings": [],
                "submit_executed": False,
                "order_created": False,
                "exchange_called": False,
                "owner_bounded_execution_called": False,
                "order_lifecycle_called": False,
            },
        },
    )

    packet = build_dispatch_packet(
        resume_pack=_resume_pack("ready_for_action_time_final_gate"),
        source_path=Path("/tmp/post-signal-resume-pack.json"),
        execute_preflight=True,
    )

    assert packet["status"] == "blocked"
    assert packet["blocker_class"] == "hard_safety_stop"
    assert packet["dispatch_status"] == "blocked_by_action_time_finalgate"
    assert "active_position_conflict" in packet["blockers"]
    assert packet["owner_state"]["blocked_at"] == "FinalGate"
    assert packet["owner_state"]["downgrade_mode"] == "observe_only_no_submit"
    assert packet["operation_layer_command_plan"] is None
    assert packet["safety_invariants"]["places_order"] is False


def test_dispatcher_execute_preflight_blocks_operator_session_unavailable(monkeypatch):
    called = {"request": False}
    monkeypatch.setattr(
        dispatcher,
        "_session_cookie",
        lambda: (None, "operator_session_unavailable:HTTPException"),
    )

    def _request_json(**_kwargs):
        called["request"] = True
        return {}

    monkeypatch.setattr(dispatcher, "_request_json", _request_json)

    packet = build_dispatch_packet(
        resume_pack=_resume_pack("ready_for_action_time_final_gate"),
        source_path=Path("/tmp/post-signal-resume-pack.json"),
        execute_preflight=True,
    )

    assert packet["status"] == "blocked"
    assert packet["blocker_class"] == "deployment_issue"
    assert packet["dispatch_status"] == "blocked_by_operator_session_unavailable"
    assert packet["owner_state"]["blocked_at"] == "operator_session"
    assert packet["owner_state"]["automatic_recovery_action"] == (
        "restore_operator_session_or_local_session_signing"
    )
    assert called["request"] is False
    assert packet["safety_invariants"]["places_order"] is False


def test_dispatcher_execute_preflight_blocks_forbidden_preflight_effect(monkeypatch):
    monkeypatch.setattr(
        dispatcher,
        "_session_cookie",
        lambda: ("brc_operator_session=fake-session", None),
    )
    monkeypatch.setattr(
        dispatcher,
        "_request_json",
        lambda **_kwargs: {
            "http_status": 200,
            "error": False,
            "body": {
                "status": "ready_for_controlled_submit_adapter",
                "final_gate_verdict": "pass",
                "blockers": [],
                "warnings": [],
                "submit_executed": False,
                "order_created": False,
                "exchange_called": True,
                "owner_bounded_execution_called": False,
                "order_lifecycle_called": False,
            },
        },
    )

    packet = build_dispatch_packet(
        resume_pack=_resume_pack("ready_for_action_time_final_gate"),
        source_path=Path("/tmp/post-signal-resume-pack.json"),
        execute_preflight=True,
    )

    assert packet["status"] == "blocked"
    assert packet["blocker_class"] == "hard_safety_stop"
    assert packet["dispatch_status"] == "blocked_by_finalgate_preflight_forbidden_effect"
    assert "preflight_effect:exchange_called" in packet["blockers"]
    assert packet["owner_state"]["blocked_at"] == "FinalGate"
    assert packet["operation_layer_command_plan"] is None


def test_dispatcher_blocks_ready_without_fresh_evidence():
    resume = _resume_pack("ready_for_action_time_final_gate")
    resume["action_time_resume"]["signal_input_json"] = None
    resume["signal_input_json"] = None

    packet = build_dispatch_packet(
        resume_pack=resume,
        source_path=Path("/tmp/post-signal-resume-pack.json"),
    )

    assert packet["status"] == "blocked"
    assert packet["blocker_class"] == "missing_fact"
    assert packet["dispatch_status"] == "blocked_by_missing_preflight_evidence"
    assert "missing_fact:signal_input_json" in packet["blockers"]
    assert packet["command_plan"] is None


def test_dispatcher_allows_ready_preflight_without_shadow_candidate_id(monkeypatch):
    calls = []
    resume = _resume_pack("ready_for_action_time_final_gate")
    resume["action_time_resume"]["shadow_candidate_id"] = None
    resume["shadow_candidate_id"] = None

    monkeypatch.setattr(
        dispatcher,
        "_session_cookie",
        lambda: ("brc_operator_session=fake-session", None),
    )

    def _request_json(**kwargs):
        calls.append(kwargs)
        return {
            "http_status": 200,
            "error": False,
            "body": {
                "status": "ready_for_controlled_submit_adapter",
                "final_gate_verdict": "pass",
                "blockers": [],
                "warnings": [],
                "submit_executed": False,
                "order_created": False,
                "exchange_called": False,
                "owner_bounded_execution_called": False,
                "order_lifecycle_called": False,
            },
        }

    monkeypatch.setattr(dispatcher, "_request_json", _request_json)

    packet = build_dispatch_packet(
        resume_pack=resume,
        source_path=Path("/tmp/post-signal-resume-pack.json"),
        execute_preflight=True,
    )

    assert packet["status"] == "finalgate_ready"
    assert packet["command_plan"]["shadow_candidate_id"] is None
    assert packet["safety_invariants"]["official_finalgate_preflight_called"] is True
    assert calls[0]["method"] == "GET"
    assert calls[0]["url"].endswith(
        "/runtime-execution-controlled-submit-preflights/authorizations/auth-ready-1"
    )


def test_dispatcher_blocks_unsafe_resume_flags():
    resume = _resume_pack("ready_for_action_time_final_gate")
    resume["action_time_resume"]["exchange_write_called"] = True

    packet = build_dispatch_packet(
        resume_pack=resume,
        source_path=Path("/tmp/post-signal-resume-pack.json"),
    )

    assert packet["status"] == "blocked"
    assert packet["blocker_class"] == "hard_safety_stop"
    assert packet["dispatch_status"] == "blocked_by_unsafe_resume_flags"
    assert "unsafe_flag:exchange_write_called" in packet["blockers"]
    assert packet["command_plan"] is None


def test_dispatcher_cli_writes_packet(tmp_path):
    resume_path = tmp_path / "post-signal-resume-pack.json"
    output_path = tmp_path / "resume-dispatch-packet.json"
    resume_path.write_text(json.dumps(_resume_pack()), encoding="utf-8")

    exit_code = main(
        [
            "--resume-pack-json",
            str(resume_path),
            "--output-json",
            str(output_path),
        ]
    )

    assert exit_code == 0
    packet = json.loads(output_path.read_text(encoding="utf-8"))
    assert packet["status"] == "waiting_for_market"
    assert packet["dispatch_action"] == "continue_watcher_observation"


def test_dispatcher_cli_finalgate_ready_is_success_exit(tmp_path, monkeypatch):
    monkeypatch.setattr(
        dispatcher,
        "_session_cookie",
        lambda: ("brc_operator_session=fake-session", None),
    )
    monkeypatch.setattr(
        dispatcher,
        "_request_json",
        lambda **_kwargs: {
            "http_status": 200,
            "error": False,
            "body": {
                "status": "ready_for_controlled_submit_adapter",
                "final_gate_verdict": "pass",
                "blockers": [],
                "warnings": [],
                "submit_executed": False,
                "order_created": False,
                "exchange_called": False,
                "owner_bounded_execution_called": False,
                "order_lifecycle_called": False,
            },
        },
    )
    resume_path = tmp_path / "post-signal-resume-pack.json"
    output_path = tmp_path / "resume-dispatch-packet.json"
    resume_path.write_text(
        json.dumps(_resume_pack("ready_for_action_time_final_gate")),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--resume-pack-json",
            str(resume_path),
            "--output-json",
            str(output_path),
            "--execute-preflight",
        ]
    )

    assert exit_code == 0
    packet = json.loads(output_path.read_text(encoding="utf-8"))
    assert packet["status"] == "finalgate_ready"
