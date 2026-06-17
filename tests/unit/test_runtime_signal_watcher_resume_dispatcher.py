from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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


def _with_runtime_summary(
    resume: dict,
    *,
    strategy_group_id: str = "MPG-001",
    runtime_instance_id: str = "runtime-mpg-1",
) -> dict:
    resume["runtime_instance_id"] = runtime_instance_id
    resume["runtime_signal_summaries"] = [
        {
            "runtime_instance_id": runtime_instance_id,
            "strategy_family_id": strategy_group_id,
            "strategy_family_version_id": f"{strategy_group_id}-v0",
            "signal_input_json": resume.get("signal_input_json"),
            "shadow_candidate_id": resume.get("shadow_candidate_id"),
            "prepared_authorization_id": resume.get("prepared_authorization_id"),
            "status": resume.get("status"),
        }
    ]
    return resume


def _fresh_authorization_resume_pack(tmp_path: Path) -> dict:
    handoff_path = tmp_path / "handoff.json"
    handoff_path.write_text(
        json.dumps(
            {
                "api_payload": {
                    "handoff_id": "handoff-runtime-mpg-1",
                    "runtime_instance_id": "runtime-mpg-1",
                    "strategy_family_id": "MPG-001",
                    "strategy_group_id": "MPG-001",
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


def _finalgate_ready_dispatch_packet() -> dict:
    return {
        **_resume_pack("ready_for_action_time_final_gate"),
        "status": "finalgate_ready",
        "dispatch_status": "official_finalgate_preflight_passed",
        "dispatch_action": "prepare_official_operation_layer_submit",
        "command_plan": {
            "prepared_authorization_id": "auth-ready-1",
        },
        "finalgate_preflight_result": {
            "called": True,
            "http_status": 200,
            "body": {
                "status": "ready_for_controlled_submit_adapter",
                "final_gate_verdict": "PASS",
                "blockers": [],
            },
        },
        "operation_layer_command_plan": {
            **dispatcher._operation_layer_command_plan(
                authorization_id="auth-ready-1",
            ),
        },
    }


def _operation_layer_ready_report() -> dict:
    ids = {
        key: f"{key}-value"
        for key in dispatcher.OPERATION_LAYER_REQUIRED_EVIDENCE_IDS
    }
    ids["authorization_id"] = "auth-ready-1"
    ids["attempt_reservation_id"] = "runtime-attempt-reservation-auth-ready-1"
    return {
        "ids": ids,
        "blockers": [],
        "warnings": [],
        "steps": [],
    }


def _operation_layer_blocked_report() -> dict:
    report = _operation_layer_ready_report()
    report["ids"].pop("exchange_submit_action_authorization_id")
    report["ids"].pop("deployment_readiness_evidence_id")
    report["blockers"] = [
        "trusted_submit_fact_snapshot_not_fresh_enough",
        "persistent_duplicate_submit_lock_required",
    ]
    report["warnings"] = ["deployment_readiness_evidence_id_missing"]
    report["steps"] = [
        {
            "name": "preview_local_registration_enablement",
            "id_summary": {},
            "blockers": ["local_registration_enablement_decision_not_ready"],
            "warnings": [],
        }
    ]
    return report


def _operation_layer_shadow_boundary_report() -> dict:
    ids = {
        "authorization_id": "auth-ready-1",
        "runtime_instance_id": "runtime-mpg-1",
        "trusted_submit_fact_snapshot_id": "trusted-facts-1",
        "submit_idempotency_policy_id": "submit-idempotency-1",
        "protection_creation_failure_policy_id": "protection-policy-1",
    }
    return {
        "ids": ids,
        "blockers": [
            "pre_attempt_evidence_not_ready:"
            "runtime_execution_enabled_false_current_shadow_boundary",
            "pre_attempt_evidence_not_ready:runtime_shadow_mode_current_boundary",
        ],
        "warnings": [],
        "steps": [],
        "safety": {
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "exchange_order_submitted": False,
        },
    }


def _operation_layer_report_with_satisfied_legacy_probe_blocker() -> dict:
    report = _operation_layer_ready_report()
    report["ids"]["local_registration_adapter_result_id"] = "local-result-1"
    report["steps"] = [
        {
            "name": "prepare_machine_evidence",
            "id_summary": {"authorization_id": "auth-ready-1"},
            "blockers": [
                "first_real_submit_packet_unavailable:"
                "runtimeexecutionorderlifecycleadapterresult_not_found"
            ],
            "warnings": [],
        },
        {
            "name": "record_local_order_registration_result",
            "id_summary": {
                "adapter_result_id": "local-result-1",
                "authorization_id": "auth-ready-1",
            },
            "blockers": [],
            "warnings": [],
        },
    ]
    return report


def test_dispatcher_waiting_for_market_is_no_action():
    packet = build_dispatch_packet(
        resume_pack=_resume_pack(),
        source_path=Path("/tmp/post-signal-resume-pack.json"),
        selected_strategy_group_id="MPG-001",
    )

    assert packet["status"] == "waiting_for_market"
    assert packet["blocker_class"] == "waiting_for_market"
    assert packet["dispatch_action"] == "continue_watcher_observation"
    assert packet["dispatch_status"] == "no_action_continue_observation"
    assert packet["command_plan"] is None
    assert packet["selected_strategy_group_id"] == "MPG-001"
    assert packet["safety_invariants"]["places_order"] is False


def test_dispatcher_non_executing_prepare_emits_common_chain_prepare_plan():
    resume = _with_runtime_summary(_resume_pack("ready_for_non_executing_prepare"))
    resume["signal_input_json"] = "/reports/runtime-mpg-1/signal-input.json"
    resume["action_time_resume"].update(
        {
            "next_step": "prepare_fresh_candidate_grant_authorization_evidence",
            "signal_input_json": "/reports/runtime-mpg-1/signal-input.json",
            "allowed_auto_actions": [
                "prepare_fresh_candidate_authorization_evidence"
            ],
            "requires_fresh_candidate_authorization_evidence": True,
        }
    )
    resume["owner_state"] = {
        "status": "ready_for_non_executing_prepare",
        "blocker_class": "none",
    }

    packet = build_dispatch_packet(
        resume_pack=resume,
        source_path=Path("/tmp/post-signal-resume-pack.json"),
        api_base="http://127.0.0.1:18080",
        selected_strategy_group_id="MPG-001",
    )

    assert packet["status"] == "ready_for_non_executing_prepare"
    assert packet["blocker_class"] == "none"
    assert packet["dispatch_action"] == (
        "prepare_fresh_candidate_authorization_evidence"
    )
    assert packet["dispatch_status"] == "non_executing_prepare_dispatch_ready"
    assert packet["owner_state"]["automatic_recovery_action"] == (
        "prepare_fresh_candidate_authorization_evidence"
    )
    command = packet["command_plan"]
    assert command["kind"] == "fresh_candidate_authorization_evidence_preparation"
    assert command["requires_runtime_instance_id"] is True
    assert command["requires_readiness_handoff_bridge"] is True
    assert command["signal_input_json"] == "/reports/runtime-mpg-1/signal-input.json"
    assert command["calls_official_submit_endpoint"] is False
    assert command["places_order"] is False
    assert command["exchange_write_called"] is False
    assert packet["safety_invariants"]["places_order"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False


def test_dispatcher_non_executing_prepare_requires_allowed_auto_action():
    resume = _with_runtime_summary(_resume_pack("ready_for_non_executing_prepare"))
    resume["action_time_resume"]["allowed_auto_actions"] = [
        "continue_watcher_observation"
    ]

    packet = build_dispatch_packet(
        resume_pack=resume,
        source_path=Path("/tmp/post-signal-resume-pack.json"),
        selected_strategy_group_id="MPG-001",
    )

    assert packet["status"] == "blocked"
    assert packet["blocker_class"] == "hard_safety_stop"
    assert packet["dispatch_status"] == "blocked_by_resume_allowed_actions"
    assert "allowed_auto_actions_missing_non_executing_prepare" in packet["blockers"]
    assert packet["command_plan"] is None


def test_dispatcher_ready_for_finalgate_emits_official_preflight_plan():
    packet = build_dispatch_packet(
        resume_pack=_with_runtime_summary(
            _resume_pack("ready_for_action_time_final_gate")
        ),
        source_path=Path("/tmp/post-signal-resume-pack.json"),
        api_base="http://127.0.0.1:18080",
        selected_strategy_group_id="MPG-001",
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


def test_dispatcher_blocks_actionable_resume_outside_selected_strategygroup_scope():
    resume = _with_runtime_summary(
        _resume_pack("ready_for_action_time_final_gate"),
        strategy_group_id="SOR-001",
        runtime_instance_id="runtime-sor-1",
    )

    packet = build_dispatch_packet(
        resume_pack=resume,
        source_path=Path("/tmp/post-signal-resume-pack.json"),
        selected_strategy_group_id="MPG-001",
        execute_preflight=True,
    )

    assert packet["status"] == "blocked"
    assert packet["dispatch_status"] == "blocked_by_selected_strategygroup_scope"
    assert packet["command_plan"] is None
    assert packet["selected_strategy_group_id"] == "MPG-001"
    assert packet["owner_state"]["blocked_at"] == "selected_strategygroup_scope"
    assert packet["safety_invariants"]["places_order"] is False
    assert packet["safety_invariants"]["official_finalgate_preflight_called"] is False
    assert packet["blockers"] == [
        "selected_strategy_group_mismatch:expected=MPG-001:actual=SOR-001"
    ]


def test_dispatcher_blocks_actionable_resume_when_selected_scope_cannot_be_proven():
    resume = _resume_pack("ready_for_action_time_final_gate")
    resume["runtime_instance_id"] = None
    resume["selected_runtime_instance_ids"] = ["runtime-mpg-1", "runtime-sor-1"]

    packet = build_dispatch_packet(
        resume_pack=resume,
        source_path=Path("/tmp/post-signal-resume-pack.json"),
        selected_strategy_group_id="MPG-001",
    )

    assert packet["status"] == "blocked"
    assert packet["dispatch_status"] == "blocked_by_selected_strategygroup_scope"
    assert packet["blockers"] == ["missing_fact:selected_strategy_group_id_for_action"]
    assert packet["command_plan"] is None


def test_dispatcher_fresh_authorization_emits_binding_plan(tmp_path):
    packet = build_dispatch_packet(
        resume_pack=_fresh_authorization_resume_pack(tmp_path),
        source_path=Path("/tmp/post-signal-resume-pack.json"),
        api_base="http://127.0.0.1:18080",
        selected_strategy_group_id="MPG-001",
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
                    "final_gate_verdict": "PASS",
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


def test_dispatcher_prepares_operation_layer_evidence_after_finalgate_pass(
    monkeypatch,
):
    calls: list[dict] = []
    prepared: list[tuple[str, dict]] = []

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
                    "final_gate_verdict": "PASS",
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
                "status": "exchange_submit_orders_submitted",
                "authorization_id": "auth-ready-1",
                "runtime_instance_id": "runtime-mpg-1",
                "reservation_id": "runtime-attempt-reservation-auth-ready-1",
                "execution_mode": "real_gateway_action",
                "blockers": [],
                "warnings": [],
                "exchange_called": True,
                "exchange_order_submitted": True,
                "order_lifecycle_submit_called": True,
                "owner_bounded_execution_called": False,
                "execution_intent_status_changed": False,
                "withdrawal_or_transfer_created": False,
            },
        }

    def _prepare_evidence(authorization_id, command_plan):
        prepared.append((authorization_id, command_plan))
        report = _operation_layer_ready_report()
        report["safety"] = {
            "attempt_counter_mutated": True,
            "runtime_budget_mutated": True,
            "exchange_order_submitted": False,
        }
        return report

    monkeypatch.setattr(dispatcher, "_request_json", _request_json)

    packet = build_dispatch_packet(
        resume_pack=_resume_pack("ready_for_action_time_final_gate"),
        source_path=Path("/tmp/post-signal-resume-pack.json"),
        api_base="http://127.0.0.1:18080",
        execute_preflight=True,
        execute_operation_layer_submit=True,
        operation_layer_evidence_report=_operation_layer_blocked_report(),
        operation_layer_evidence_preparer=_prepare_evidence,
    )

    assert prepared == [
        (
            "auth-ready-1",
            {
                **dispatcher._operation_layer_command_plan(
                    authorization_id="auth-ready-1"
                )
            },
        )
    ]
    assert packet["status"] == "submitted"
    assert packet["operation_layer_readiness"]["missing_evidence_ids"] == []
    assert packet["operation_layer_submit_result"]["called"] is True
    assert packet["safety_invariants"]["official_finalgate_preflight_called"] is True
    assert packet["safety_invariants"]["official_operation_layer_submit_called"] is True
    assert packet["safety_invariants"][
        "operation_layer_evidence_attempt_counter_mutated"
    ] is True
    assert packet["safety_invariants"][
        "operation_layer_evidence_runtime_budget_mutated"
    ] is True
    assert len(calls) == 2
    assert calls[0]["method"] == "GET"
    assert calls[1]["method"] == "POST"
    submit_query = parse_qs(urlparse(calls[1]["url"]).query)
    assert submit_query["attempt_outcome_policy_id"] == [
        "attempt_outcome_policy_id-value"
    ]
    assert submit_query["exchange_submit_action_authorization_id"] == [
        "exchange_submit_action_authorization_id-value"
    ]


def test_dispatcher_live_enables_runtime_when_only_shadow_boundary_blocks_operation_layer(
    monkeypatch,
):
    calls: list[dict] = []
    prepared: list[tuple[str, dict]] = []
    live_enablement_calls: list[dict] = []

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
                    "final_gate_verdict": "PASS",
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
                "status": "exchange_submit_orders_submitted",
                "authorization_id": "auth-ready-1",
                "runtime_instance_id": "runtime-mpg-1",
                "reservation_id": "runtime-attempt-reservation-auth-ready-1",
                "execution_mode": "real_gateway_action",
                "blockers": [],
                "warnings": [],
                "exchange_called": True,
                "exchange_order_submitted": True,
                "order_lifecycle_submit_called": True,
                "owner_bounded_execution_called": False,
                "execution_intent_status_changed": False,
                "withdrawal_or_transfer_created": False,
            },
        }

    def _prepare_evidence(authorization_id, command_plan):
        prepared.append((authorization_id, command_plan))
        return (
            _operation_layer_shadow_boundary_report()
            if len(prepared) == 1
            else _operation_layer_ready_report()
        )

    def _live_enable_runtime(**kwargs):
        live_enablement_calls.append(kwargs)
        return {
            "called": True,
            "status": "live_runtime_enablement_mutation_applied",
            "blockers": [],
            "mutation_applied": True,
            "runtime_state_mutated": True,
            "order_created": False,
            "exchange_called": False,
            "order_lifecycle_called": False,
            "withdrawal_or_transfer_created": False,
        }

    monkeypatch.setattr(dispatcher, "_request_json", _request_json)

    packet = build_dispatch_packet(
        resume_pack=_resume_pack("ready_for_action_time_final_gate"),
        source_path=Path("/tmp/post-signal-resume-pack.json"),
        api_base="http://127.0.0.1:18080",
        execute_preflight=True,
        execute_operation_layer_submit=True,
        operation_layer_evidence_report=_operation_layer_shadow_boundary_report(),
        operation_layer_evidence_preparer=_prepare_evidence,
        runtime_live_enabler=_live_enable_runtime,
    )

    assert len(prepared) == 2
    assert len(live_enablement_calls) == 1
    assert live_enablement_calls[0]["runtime_instance_id"] == "runtime-mpg-1"
    assert live_enablement_calls[0]["authorization_id"] == "auth-ready-1"
    assert packet["status"] == "submitted"
    assert packet["runtime_live_enablement_result"]["mutation_applied"] is True
    assert packet["operation_layer_readiness"]["missing_evidence_ids"] == []
    assert packet["operation_layer_submit_result"]["called"] is True
    assert packet["safety_invariants"]["runtime_live_enablement_called"] is True
    assert packet["safety_invariants"]["runtime_live_enablement_mutation_applied"] is True
    assert packet["safety_invariants"]["runtime_state_mutated"] is True
    assert packet["safety_invariants"]["official_operation_layer_submit_called"] is True
    assert packet["safety_invariants"]["places_order"] is True
    assert packet["safety_invariants"]["exchange_write_called"] is True
    assert packet["safety_invariants"]["withdrawal_or_transfer_created"] is False


def test_runtime_live_enablement_query_omits_missing_optional_evidence_ids(
    monkeypatch,
):
    calls: list[dict] = []
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
                    "status": "ready_for_live_runtime_enablement_mutation_design",
                    "blockers": [],
                    "warnings": [],
                    "execution_intent_created": False,
                    "order_created": False,
                    "exchange_called": False,
                    "owner_bounded_execution_called": False,
                    "order_lifecycle_called": False,
                    "withdrawal_instruction_created": False,
                    "transfer_instruction_created": False,
                },
            }
        return {
            "http_status": 200,
            "error": False,
            "body": {
                "status": "applied",
                "blockers": [],
                "warnings": [],
                "runtime_state_mutated": True,
                "execution_intent_created": False,
                "order_created": False,
                "exchange_called": False,
                "owner_bounded_execution_called": False,
                "order_lifecycle_called": False,
                "withdrawal_instruction_created": False,
                "transfer_instruction_created": False,
            },
        }

    monkeypatch.setattr(dispatcher, "_request_json", _request_json)

    result = dispatcher._run_runtime_live_enablement(
        runtime_instance_id="runtime-mpg-1",
        authorization_id="auth-ready-1",
        command_plan=dispatcher._operation_layer_command_plan(
            authorization_id="auth-ready-1",
        ),
        evidence_report=_operation_layer_shadow_boundary_report(),
        timeout_seconds=30,
    )

    assert result["mutation_applied"] is True
    preview_query = parse_qs(urlparse(calls[0]["url"]).query)
    assert "exchange_submit_execution_result_id" not in preview_query
    assert "runtime_submit_rehearsal_id" not in preview_query
    assert "deployment_readiness_evidence_id" not in preview_query
    assert preview_query["trusted_submit_fact_snapshot_id"] == ["trusted-facts-1"]
    assert calls[1]["method"] == "POST"
    assert calls[1]["body"]["owner_real_submit_authorization_id"] == "auth-ready-1"


def test_dispatcher_translates_operation_layer_evidence_blocker():
    packet = build_dispatch_packet(
        resume_pack=_finalgate_ready_dispatch_packet(),
        source_path=Path("/tmp/resume-dispatch-packet.json"),
        operation_layer_evidence_report=_operation_layer_blocked_report(),
        operation_layer_evidence_report_path=(
            "/reports/runtime-signal-watcher/operation-layer-arm-evidence.json"
        ),
    )

    assert packet["status"] == "operation_layer_blocked"
    assert packet["blocker_class"] == "hard_safety_stop"
    assert packet["dispatch_status"] == "blocked_by_operation_layer_evidence"
    assert packet["dispatch_action"] is None
    assert packet["owner_state"]["blocked_at"] == "OperationLayerEvidence"
    assert packet["owner_state"]["downgrade_mode"] == (
        "continue_watcher_observation_no_submit"
    )
    readiness = packet["operation_layer_readiness"]
    assert readiness["status"] == "blocked"
    assert readiness["ready_for_official_operation_layer_submit"] is False
    assert "exchange_submit_action_authorization_id" in (
        readiness["missing_evidence_ids"]
    )
    assert "deployment_readiness_evidence_id" in readiness["missing_evidence_ids"]
    assert "persistent_duplicate_submit_lock_required" in packet["blockers"]
    assert packet["safety_invariants"]["official_operation_layer_submit_called"] is False
    assert packet["safety_invariants"]["places_order"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False


def test_dispatcher_translates_operation_layer_evidence_ready():
    packet = build_dispatch_packet(
        resume_pack=_finalgate_ready_dispatch_packet(),
        source_path=Path("/tmp/resume-dispatch-packet.json"),
        operation_layer_evidence_report=_operation_layer_ready_report(),
        operation_layer_evidence_report_path=(
            "/reports/runtime-signal-watcher/operation-layer-arm-evidence.json"
        ),
    )

    assert packet["status"] == "operation_layer_ready"
    assert packet["blocker_class"] == "none"
    assert packet["dispatch_status"] == "official_operation_layer_evidence_ready"
    assert packet["dispatch_action"] == "prepare_official_operation_layer_submit"
    assert packet["blockers"] == []
    assert packet["owner_state"]["status"] == "operation_layer_ready"
    assert packet["operation_layer_readiness"]["missing_evidence_ids"] == []
    assert packet["operation_layer_readiness"][
        "ready_for_official_operation_layer_submit"
    ] is True
    assert packet["safety_invariants"]["official_operation_layer_submit_called"] is False
    assert packet["safety_invariants"]["places_order"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False


def test_dispatcher_executes_official_operation_layer_submit_when_ready(monkeypatch):
    calls: list[dict] = []
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
                "status": "exchange_submit_orders_submitted",
                "authorization_id": "auth-ready-1",
                "runtime_instance_id": "runtime-mpg-1",
                "reservation_id": "runtime-attempt-reservation-auth-ready-1",
                "execution_mode": "real_gateway_action",
                "blockers": [],
                "warnings": [],
                "exchange_called": True,
                "exchange_order_submitted": True,
                "order_lifecycle_submit_called": True,
                "owner_bounded_execution_called": False,
                "execution_intent_status_changed": False,
                "withdrawal_or_transfer_created": False,
                "submitted_exchange_order_ids": ["ex-entry-1", "ex-stop-1"],
                "entry_exchange_order_id": "ex-entry-1",
                "protection_exchange_order_ids": ["ex-stop-1"],
            },
        }

    monkeypatch.setattr(dispatcher, "_request_json", _request_json)

    packet = build_dispatch_packet(
        resume_pack=_finalgate_ready_dispatch_packet(),
        source_path=Path("/tmp/resume-dispatch-packet.json"),
        operation_layer_evidence_report=_operation_layer_ready_report(),
        operation_layer_evidence_report_path=(
            "/reports/runtime-signal-watcher/operation-layer-arm-evidence.json"
        ),
        execute_operation_layer_submit=True,
    )

    assert packet["status"] == "submitted"
    assert packet["blocker_class"] == "none"
    assert packet["dispatch_status"] == "official_operation_layer_submit_completed"
    assert packet["dispatch_action"] == (
        "post_submit_finalize_reconciliation_budget_settlement"
    )
    assert packet["owner_state"]["status"] == "submitted"
    assert packet["operation_layer_submit_result"]["called"] is True
    assert packet["safety_invariants"]["official_operation_layer_submit_called"] is True
    assert packet["safety_invariants"]["places_order"] is True
    assert packet["safety_invariants"]["exchange_write_called"] is True
    assert packet["safety_invariants"]["calls_order_lifecycle"] is True
    assert packet["safety_invariants"]["withdrawal_or_transfer_created"] is False
    assert len(calls) == 1
    call = calls[0]
    assert call["method"] == "POST"
    parsed = urlparse(call["url"])
    assert parsed.path.endswith(
        "/runtime-execution-first-real-submit-actions/authorizations/auth-ready-1"
    )
    query = parse_qs(parsed.query)
    assert query["owner_confirmed_for_first_real_submit_action"] == ["true"]
    for name in dispatcher.OPERATION_LAYER_REQUIRED_EVIDENCE_IDS:
        assert query[name] == [f"{name}-value"]


def test_dispatcher_executes_post_submit_finalize_after_submit(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(
        dispatcher,
        "_session_cookie",
        lambda: ("brc_operator_session=fake-session", None),
    )

    def _request_json(**kwargs):
        calls.append(kwargs)
        if "post-submit-finalize-packets" in kwargs["url"]:
            return {
                "http_status": 200,
                "error": False,
                "body": {
                    "status": "finalized_ready_for_next_attempt",
                    "authorization_id": "auth-ready-1",
                    "runtime_instance_id": "runtime-mpg-1",
                    "exchange_submit_execution_result_id": "submit-result-1",
                    "submit_outcome_review_id": "review-1",
                    "post_submit_budget_settlement_id": "settlement-1",
                    "blockers": [],
                    "warnings": ["reservation_id_resolved_from_attempt_reservation"],
                    "next_attempt_gate": {
                        "status": "ready_for_fresh_signal",
                        "blockers": [],
                    },
                    "exchange_called": False,
                    "exchange_order_submitted": False,
                    "order_lifecycle_called": False,
                    "owner_bounded_execution_called": False,
                    "withdrawal_or_transfer_created": False,
                    "position_closed": False,
                    "order_cancelled": False,
                    "order_created": False,
                },
            }
        return {
            "http_status": 200,
            "error": False,
            "body": {
                "status": "exchange_submit_orders_submitted",
                "authorization_id": "auth-ready-1",
                "runtime_instance_id": "runtime-mpg-1",
                "execution_mode": "real_gateway_action",
                "blockers": [],
                "warnings": [],
                "exchange_called": True,
                "exchange_order_submitted": True,
                "order_lifecycle_submit_called": True,
                "owner_bounded_execution_called": False,
                "execution_intent_status_changed": False,
                "withdrawal_or_transfer_created": False,
                "submitted_exchange_order_ids": ["ex-entry-1", "ex-stop-1"],
                "entry_exchange_order_id": "ex-entry-1",
                "protection_exchange_order_ids": ["ex-stop-1"],
            },
        }

    monkeypatch.setattr(dispatcher, "_request_json", _request_json)

    packet = build_dispatch_packet(
        resume_pack=_finalgate_ready_dispatch_packet(),
        source_path=Path("/tmp/resume-dispatch-packet.json"),
        operation_layer_evidence_report=_operation_layer_ready_report(),
        operation_layer_evidence_report_path=(
            "/reports/runtime-signal-watcher/operation-layer-arm-evidence.json"
        ),
        execute_operation_layer_submit=True,
        execute_post_submit_finalize=True,
    )

    assert packet["status"] == "settled"
    assert packet["blocker_class"] == "none"
    assert packet["dispatch_status"] == (
        "post_submit_finalize_completed_next_attempt_ready"
    )
    assert packet["dispatch_action"] == "continue_watcher_observation"
    assert packet["owner_state"]["status"] == "settled"
    assert packet["owner_state"]["automatic_recovery_action"] == (
        "continue_watcher_observation"
    )
    assert packet["post_submit_finalize_result"]["called"] is True
    assert packet["post_submit_finalize_result"]["authorization_id"] == "auth-ready-1"
    assert packet["post_submit_finalize_result"]["runtime_instance_id"] == (
        "runtime-mpg-1"
    )
    assert packet["post_submit_finalize_result"]["reservation_id"] == (
        "runtime-attempt-reservation-auth-ready-1"
    )
    assert packet["safety_invariants"]["official_operation_layer_submit_called"] is True
    assert packet["safety_invariants"]["official_post_submit_finalize_called"] is True
    assert packet["safety_invariants"]["post_submit_budget_settlement_called"] is True
    assert packet["safety_invariants"]["runtime_budget_mutated"] is True
    assert packet["safety_invariants"]["places_order"] is True
    assert packet["safety_invariants"]["exchange_write_called"] is True
    assert packet["safety_invariants"]["withdrawal_or_transfer_created"] is False
    assert len(calls) == 2
    submit_call, finalize_call = calls
    assert submit_call["method"] == "POST"
    assert finalize_call["method"] == "POST"
    assert finalize_call["url"].endswith(
        "/api/trading-console/strategy-runtimes/runtime-mpg-1/"
        "post-submit-finalize-packets"
    )
    assert finalize_call["body"]["authorization_id"] == "auth-ready-1"
    assert finalize_call["body"]["reservation_id"] == (
        "runtime-attempt-reservation-auth-ready-1"
    )
    assert finalize_call["body"]["non_executing"] is True


def test_dispatcher_blocks_incomplete_post_submit_closed_loop(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(
        dispatcher,
        "_session_cookie",
        lambda: ("brc_operator_session=fake-session", None),
    )

    def _request_json(**kwargs):
        calls.append(kwargs)
        if "post-submit-finalize-packets" in kwargs["url"]:
            return {
                "http_status": 200,
                "error": False,
                "body": {
                    "status": "finalized_ready_for_next_attempt",
                    "authorization_id": "auth-ready-1",
                    "runtime_instance_id": "runtime-mpg-1",
                    "exchange_submit_execution_result_id": "submit-result-1",
                    "blockers": [],
                    "warnings": ["dry_run_missing_closed_loop_evidence"],
                    "next_attempt_gate": {
                        "status": "ready_for_fresh_signal",
                        "blockers": [],
                    },
                    "exchange_called": False,
                    "exchange_order_submitted": False,
                    "order_lifecycle_called": False,
                    "owner_bounded_execution_called": False,
                    "withdrawal_or_transfer_created": False,
                    "position_closed": False,
                    "order_cancelled": False,
                    "order_created": False,
                },
            }
        return {
            "http_status": 200,
            "error": False,
            "body": {
                "status": "exchange_submit_orders_submitted",
                "authorization_id": "auth-ready-1",
                "runtime_instance_id": "runtime-mpg-1",
                "execution_mode": "real_gateway_action",
                "blockers": [],
                "warnings": [],
                "exchange_called": True,
                "exchange_order_submitted": True,
                "order_lifecycle_submit_called": True,
                "owner_bounded_execution_called": False,
                "execution_intent_status_changed": False,
                "withdrawal_or_transfer_created": False,
                "submitted_exchange_order_ids": ["ex-entry-1", "ex-stop-1"],
                "entry_exchange_order_id": "ex-entry-1",
                "protection_exchange_order_ids": ["ex-stop-1"],
            },
        }

    monkeypatch.setattr(dispatcher, "_request_json", _request_json)

    packet = build_dispatch_packet(
        resume_pack=_finalgate_ready_dispatch_packet(),
        source_path=Path("/tmp/resume-dispatch-packet.json"),
        operation_layer_evidence_report=_operation_layer_ready_report(),
        operation_layer_evidence_report_path=(
            "/reports/runtime-signal-watcher/operation-layer-arm-evidence.json"
        ),
        execute_operation_layer_submit=True,
        execute_post_submit_finalize=True,
    )

    assert packet["status"] == "post_submit_finalize_blocked"
    assert packet["blocker_class"] == "missing_fact"
    assert packet["dispatch_status"] == (
        "blocked_by_post_submit_finalize_incomplete_closed_loop"
    )
    assert "post_submit_finalize_budget_settlement_id_missing" in packet["blockers"]
    assert "post_submit_finalize_review_id_missing" in packet["blockers"]
    assert packet["dispatch_action"] is None
    assert packet["owner_state"]["status"] == "post_submit_finalize_blocked"
    assert packet["owner_state"]["downgrade_mode"] == (
        "halt_new_entries_until_post_submit_settled"
    )
    assert packet["post_submit_finalize_result"]["called"] is True
    assert packet["safety_invariants"]["official_post_submit_finalize_called"] is True
    assert packet["safety_invariants"]["post_submit_budget_settlement_called"] is False
    assert packet["safety_invariants"]["withdrawal_or_transfer_created"] is False
    assert len(calls) == 2


def test_dispatcher_blocks_submit_result_identity_mismatch_before_finalize(monkeypatch):
    calls: list[dict] = []
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
                "status": "exchange_submit_orders_submitted",
                "authorization_id": "other-auth",
                "runtime_instance_id": "runtime-mpg-1",
                "reservation_id": "runtime-attempt-reservation-auth-ready-1",
                "execution_mode": "real_gateway_action",
                "blockers": [],
                "warnings": [],
                "exchange_called": True,
                "exchange_order_submitted": True,
                "order_lifecycle_submit_called": True,
                "owner_bounded_execution_called": False,
                "execution_intent_status_changed": False,
                "withdrawal_or_transfer_created": False,
                "submitted_exchange_order_ids": ["ex-entry-1", "ex-stop-1"],
                "entry_exchange_order_id": "ex-entry-1",
                "protection_exchange_order_ids": ["ex-stop-1"],
            },
        }

    monkeypatch.setattr(dispatcher, "_request_json", _request_json)

    packet = build_dispatch_packet(
        resume_pack=_finalgate_ready_dispatch_packet(),
        source_path=Path("/tmp/resume-dispatch-packet.json"),
        operation_layer_evidence_report=_operation_layer_ready_report(),
        operation_layer_evidence_report_path=(
            "/reports/runtime-signal-watcher/operation-layer-arm-evidence.json"
        ),
        execute_operation_layer_submit=True,
        execute_post_submit_finalize=True,
    )

    assert packet["status"] == "operation_layer_submit_failed"
    assert packet["blocker_class"] == "hard_safety_stop"
    assert packet["dispatch_status"] == (
        "official_operation_layer_submit_result_identity_mismatch"
    )
    assert (
        "operation_layer_submit_authorization_id_mismatch:"
        "expected=auth-ready-1:actual=other-auth"
    ) in packet["blockers"]
    assert packet["dispatch_action"] is None
    assert packet["owner_state"]["downgrade_mode"] == (
        "halt_new_entries_until_reconciled"
    )
    assert "post_submit_finalize_result" not in packet
    assert packet["safety_invariants"]["official_operation_layer_submit_called"] is True
    assert packet["safety_invariants"]["official_post_submit_finalize_called"] is False
    assert packet["safety_invariants"]["withdrawal_or_transfer_created"] is False
    assert len(calls) == 1


def test_dispatcher_blocks_post_submit_finalize_runtime_mismatch(monkeypatch):
    monkeypatch.setattr(
        dispatcher,
        "_session_cookie",
        lambda: ("brc_operator_session=fake-session", None),
    )

    def _request_json(**kwargs):
        if "post-submit-finalize-packets" in kwargs["url"]:
            return {
                "http_status": 200,
                "error": False,
                "body": {
                    "status": "finalized_ready_for_next_attempt",
                    "authorization_id": "auth-ready-1",
                    "runtime_instance_id": "other-runtime",
                    "exchange_submit_execution_result_id": "submit-result-1",
                    "submit_outcome_review_id": "review-1",
                    "post_submit_budget_settlement_id": "settlement-1",
                    "blockers": [],
                    "next_attempt_gate": {
                        "status": "ready_for_fresh_signal",
                        "blockers": [],
                    },
                    "exchange_called": False,
                    "exchange_order_submitted": False,
                    "order_lifecycle_called": False,
                    "owner_bounded_execution_called": False,
                    "withdrawal_or_transfer_created": False,
                    "position_closed": False,
                    "order_cancelled": False,
                    "order_created": False,
                },
            }
        return {
            "http_status": 200,
            "error": False,
            "body": {
                "status": "exchange_submit_orders_submitted",
                "authorization_id": "auth-ready-1",
                "runtime_instance_id": "runtime-mpg-1",
                "reservation_id": "runtime-attempt-reservation-auth-ready-1",
                "execution_mode": "real_gateway_action",
                "blockers": [],
                "exchange_called": True,
                "exchange_order_submitted": True,
                "order_lifecycle_submit_called": True,
                "owner_bounded_execution_called": False,
                "execution_intent_status_changed": False,
                "withdrawal_or_transfer_created": False,
            },
        }

    monkeypatch.setattr(dispatcher, "_request_json", _request_json)

    packet = build_dispatch_packet(
        resume_pack=_finalgate_ready_dispatch_packet(),
        source_path=Path("/tmp/resume-dispatch-packet.json"),
        operation_layer_evidence_report=_operation_layer_ready_report(),
        operation_layer_evidence_report_path=(
            "/reports/runtime-signal-watcher/operation-layer-arm-evidence.json"
        ),
        execute_operation_layer_submit=True,
        execute_post_submit_finalize=True,
    )

    assert packet["status"] == "post_submit_finalize_blocked"
    assert packet["blocker_class"] == "hard_safety_stop"
    assert packet["dispatch_status"] == "post_submit_finalize_result_identity_mismatch"
    assert any(
        blocker.startswith("post_submit_finalize_runtime_instance_id_mismatch:")
        for blocker in packet["blockers"]
    )
    assert packet["post_submit_finalize_result"]["called"] is True
    assert packet["safety_invariants"]["official_post_submit_finalize_called"] is True


def test_dispatcher_refuses_operation_layer_submit_without_same_run_finalgate(
    monkeypatch,
):
    called = {"request": False}
    monkeypatch.setattr(
        dispatcher,
        "_session_cookie",
        lambda: ("brc_operator_session=fake-session", None),
    )

    def _request_json(**_kwargs):
        called["request"] = True
        return {}

    monkeypatch.setattr(dispatcher, "_request_json", _request_json)
    resume = _finalgate_ready_dispatch_packet()
    resume["finalgate_preflight_result"] = {"called": False}

    packet = build_dispatch_packet(
        resume_pack=resume,
        source_path=Path("/tmp/resume-dispatch-packet.json"),
        operation_layer_evidence_report=_operation_layer_ready_report(),
        operation_layer_evidence_report_path=(
            "/reports/runtime-signal-watcher/operation-layer-arm-evidence.json"
        ),
        execute_operation_layer_submit=True,
    )

    assert packet["status"] == "operation_layer_submit_blocked"
    assert packet["dispatch_status"] == "blocked_before_official_operation_layer_submit"
    assert "action_time_finalgate_preflight_not_called" in packet["blockers"]
    assert called["request"] is False
    assert packet["safety_invariants"]["official_operation_layer_submit_called"] is False
    assert packet["safety_invariants"]["places_order"] is False


def test_dispatcher_blocks_stale_operation_layer_authorization_evidence():
    report = _operation_layer_ready_report()
    report["ids"]["authorization_id"] = "old-auth-1"

    packet = build_dispatch_packet(
        resume_pack=_finalgate_ready_dispatch_packet(),
        source_path=Path("/tmp/resume-dispatch-packet.json"),
        operation_layer_evidence_report=report,
        operation_layer_evidence_report_path=(
            "/reports/runtime-signal-watcher/operation-layer-arm-evidence.json"
        ),
    )

    assert packet["status"] == "operation_layer_blocked"
    assert packet["blocker_class"] == "hard_safety_stop"
    assert packet["dispatch_status"] == "blocked_by_operation_layer_evidence"
    assert any(
        blocker.startswith("operation_layer_authorization_id_mismatch:")
        for blocker in packet["blockers"]
    )
    assert packet["safety_invariants"]["official_operation_layer_submit_called"] is False


def test_dispatcher_tolerates_legacy_local_registration_probe_when_result_exists():
    packet = build_dispatch_packet(
        resume_pack=_finalgate_ready_dispatch_packet(),
        source_path=Path("/tmp/resume-dispatch-packet.json"),
        operation_layer_evidence_report=(
            _operation_layer_report_with_satisfied_legacy_probe_blocker()
        ),
        operation_layer_evidence_report_path=(
            "/reports/runtime-signal-watcher/operation-layer-arm-evidence.json"
        ),
    )

    assert packet["status"] == "operation_layer_ready"
    assert packet["blockers"] == []
    assert packet["operation_layer_readiness"]["blockers"] == []
    assert (
        "legacy_prepare_machine_evidence_probe_blocker_satisfied_by_"
        "local_registration_adapter_result"
    ) in packet["warnings"]


def test_dispatcher_keeps_legacy_local_registration_probe_without_result():
    report = _operation_layer_report_with_satisfied_legacy_probe_blocker()
    report["ids"].pop("local_registration_adapter_result_id")

    packet = build_dispatch_packet(
        resume_pack=_finalgate_ready_dispatch_packet(),
        source_path=Path("/tmp/resume-dispatch-packet.json"),
        operation_layer_evidence_report=report,
        operation_layer_evidence_report_path=(
            "/reports/runtime-signal-watcher/operation-layer-arm-evidence.json"
        ),
    )

    assert packet["status"] == "operation_layer_blocked"
    assert packet["blocker_class"] == "missing_fact"
    assert any(
        "runtimeexecutionorderlifecycleadapterresult_not_found" in blocker
        for blocker in packet["blockers"]
    )


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
