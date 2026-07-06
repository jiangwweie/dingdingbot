from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import sqlalchemy as sa

import scripts.runtime_signal_watcher_resume_dispatcher as dispatcher
from scripts.runtime_signal_watcher_resume_dispatcher import build_dispatch_artifact, main


def _captured_stdout_artifact(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def _assert_legacy_operation_layer_submit_blocked(artifact: dict) -> None:
    assert artifact["status"] == "operation_layer_submit_blocked"
    assert artifact["blocker_class"] == "hard_safety_stop"
    assert artifact["dispatch_status"] == (
        "blocked_by_legacy_authorization_operation_layer_submit"
    )
    assert "legacy_authorization_operation_layer_submit_retired" in artifact["blockers"]
    assert "ticket_bound_action_time_submit_required" in artifact["blockers"]
    assert artifact["operation_layer_submit_result"]["called"] is False
    assert artifact["operation_layer_submit_result"]["official_operation_layer_submit_called"] is False
    assert artifact["owner_state"]["next_recover_condition"] == (
        "ticket_bound_action_time_ticket_and_protected_submit_available"
    )
    assert artifact["owner_state"]["non_authority_checkpoint"] == (
        "materialize_action_time_ticket_and_ticket_bound_operation_layer_handoff"
    )
    assert artifact["safety_invariants"]["official_operation_layer_submit_called"] is False
    assert artifact["safety_invariants"]["official_post_submit_finalize_called"] is False
    assert artifact["safety_invariants"]["places_order"] is False
    assert artifact["safety_invariants"]["exchange_write_called"] is False
    assert artifact["safety_invariants"]["calls_order_lifecycle"] is False


def _assert_legacy_finalgate_ready_blocked(artifact: dict) -> None:
    assert artifact["status"] == "blocked"
    assert artifact["blocker_class"] == "hard_safety_stop"
    assert artifact["dispatch_status"] == (
        "blocked_by_legacy_finalgate_authorization_without_ticket"
    )
    assert artifact["dispatch_action"] is None
    assert "legacy_authorization_finalgate_ready_retired" in artifact["blockers"]
    assert "ticket_bound_action_time_ticket_required" in artifact["blockers"]
    assert "ticket_bound_finalgate_command_plan_required" in artifact["blockers"]
    assert "legacy_operation_layer_command_plan_ignored" in artifact["blockers"]
    assert artifact.get("operation_layer_command_plan") is None
    assert "operation_layer_readiness" not in artifact
    assert artifact["owner_state"]["blocked_at"] == "FinalGate"
    assert artifact["owner_state"]["next_recover_condition"] == (
        "pg_action_time_ticket_and_ticket_bound_finalgate_materialized"
    )
    assert artifact["owner_state"]["non_authority_checkpoint"] == (
        "materialize_pg_action_time_ticket"
    )
    assert artifact["safety_invariants"]["official_operation_layer_submit_called"] is False
    assert artifact["safety_invariants"]["places_order"] is False
    assert artifact["safety_invariants"]["exchange_write_called"] is False
    assert artifact["safety_invariants"]["calls_order_lifecycle"] is False


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
                "ticket_id": "ticket-ready-1",
                "signal_input_json": "pg://runtime-control-state/live-signal-events/signal-ready-1",
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
        "ticket_id": action.get("ticket_id"),
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


def _fresh_authorization_resume_pack() -> dict:
    return {
        "scope": "runtime_signal_watcher_post_signal_resume_pack",
        "status": "ready_for_fresh_submit_authorization",
        "ticket_id": "ticket-ready-1",
        "runtime_instance_id": "runtime-mpg-1",
        "selected_runtime_instance_ids": ["runtime-mpg-1"],
        "artifact_paths": {
            "readiness_handoff_evidence": "archive://retired-handoff-json",
        },
        "action_time_resume": {
            "status": "ready_for_fresh_submit_authorization",
            "ticket_id": "ticket-ready-1",
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


def _finalgate_ready_dispatch_artifact() -> dict:
    return {
        **_resume_pack("ready_for_action_time_final_gate"),
        "strategy_group_id": "MPG-001",
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


def _pg_ticket_identity_db(
    tmp_path: Path,
    *,
    lane_count: int = 1,
    ticket_count: int = 1,
    ticket_symbol: str = "ETHUSDT",
) -> str:
    db_path = tmp_path / "runtime-control-state.db"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    """
                    CREATE TABLE brc_action_time_lane_inputs (
                        action_time_lane_input_id TEXT PRIMARY KEY,
                        promotion_candidate_id TEXT,
                        signal_event_id TEXT,
                        strategy_group_id TEXT,
                        symbol TEXT,
                        side TEXT,
                        runtime_profile_id TEXT,
                        lane_scope TEXT,
                        status TEXT,
                        created_at_ms INTEGER
                    )
                    """
                )
            )
            conn.execute(
                sa.text(
                    """
                    CREATE TABLE brc_action_time_tickets (
                        ticket_id TEXT PRIMARY KEY,
                        action_time_lane_input_id TEXT,
                        promotion_candidate_id TEXT,
                        signal_event_id TEXT,
                        strategy_group_id TEXT,
                        symbol TEXT,
                        side TEXT,
                        runtime_profile_id TEXT,
                        status TEXT,
                        created_at_ms INTEGER
                    )
                    """
                )
            )
            for index in range(lane_count):
                suffix = index + 1
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO brc_action_time_lane_inputs (
                            action_time_lane_input_id,
                            promotion_candidate_id,
                            signal_event_id,
                            strategy_group_id,
                            symbol,
                            side,
                            runtime_profile_id,
                            lane_scope,
                            status,
                            created_at_ms
                        ) VALUES (
                            :lane_id,
                            :promotion_id,
                            :signal_id,
                            'SOR-001',
                            'ETHUSDT',
                            'long',
                            'runtime-profile-v0',
                            'real_submit_candidate',
                            'ticket_created',
                            :created_at_ms
                        )
                        """
                    ),
                    {
                        "lane_id": f"lane-{suffix}",
                        "promotion_id": f"promotion-{suffix}",
                        "signal_id": f"signal-{suffix}",
                        "created_at_ms": 1000 + suffix,
                    },
                )
            for index in range(ticket_count):
                suffix = index + 1
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO brc_action_time_tickets (
                            ticket_id,
                            action_time_lane_input_id,
                            promotion_candidate_id,
                            signal_event_id,
                            strategy_group_id,
                            symbol,
                            side,
                            runtime_profile_id,
                            status,
                            created_at_ms
                        ) VALUES (
                            :ticket_id,
                            :lane_id,
                            :promotion_id,
                            :signal_id,
                            'SOR-001',
                            :ticket_symbol,
                            'long',
                            'runtime-profile-v0',
                            'created',
                            :created_at_ms
                        )
                        """
                    ),
                    {
                        "ticket_id": f"ticket-{suffix}",
                        "lane_id": f"lane-{suffix}",
                        "promotion_id": f"promotion-{suffix}",
                        "signal_id": f"signal-{suffix}",
                        "ticket_symbol": ticket_symbol,
                        "created_at_ms": 2000 + suffix,
                    },
                )
    finally:
        engine.dispose()
    return f"sqlite:///{db_path}"


def _finalgate_ready_body() -> dict:
    return {
        "status": "ready_for_controlled_submit_adapter",
        "final_gate_verdict": "pass",
        "ticket_id": "ticket-ready-1",
        "finalgate_pass_id": "finalgate-pass-1",
        "blockers": [],
        "warnings": [],
        "submit_executed": False,
        "order_created": False,
        "exchange_called": False,
        "owner_bounded_execution_called": False,
        "order_lifecycle_called": False,
    }


def _operation_layer_handoff_ready_body() -> dict:
    return {
        "status": "operation_layer_handoff_ready",
        "operation_layer_verdict": "ready",
        "ticket_id": "ticket-ready-1",
        "finalgate_pass_id": "finalgate-pass-1",
        "operation_layer_handoff_id": "handoff-1",
        "operation_submit_command_id": "operation-submit-1",
        "strategy_group_id": "SOR-001",
        "symbol": "ETHUSDT",
        "side": "long",
        "blockers": [],
        "warnings": [],
        "command_plan": {
            "kind": "ticket_bound_operation_layer_handoff",
            "ticket_id": "ticket-ready-1",
            "finalgate_pass_id": "finalgate-pass-1",
            "operation_submit_command_id": "operation-submit-1",
            "requires_ticket_bound_protected_submit": True,
            "places_order": False,
            "exchange_write_called": False,
            "order_lifecycle_called": False,
        },
        "submit_executed": False,
        "operation_layer_submit_called": False,
        "order_created": False,
        "exchange_called": False,
        "exchange_write_called": False,
        "owner_bounded_execution_called": False,
        "order_lifecycle_called": False,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
    }


def _ticket_bound_finalgate_and_handoff_request(calls: list[dict]):
    def _request_json(**kwargs):
        calls.append(kwargs)
        return {
            "http_status": 200,
            "error": False,
            "body": (
                _operation_layer_handoff_ready_body()
                if kwargs["method"] == "POST"
                else _finalgate_ready_body()
            ),
        }

    return _request_json


def _ticket_bound_finalgate_handoff_and_submit_request(
    calls: list[dict],
    *,
    submit_body: dict,
):
    def _request_json(**kwargs):
        calls.append(kwargs)
        url = str(kwargs.get("url") or "")
        if kwargs["method"] == "GET":
            body = _finalgate_ready_body()
        elif "/runtime-protected-submits/tickets/" in url:
            body = submit_body
        else:
            body = _operation_layer_handoff_ready_body()
        return {"http_status": 200, "error": False, "body": body}

    return _request_json


def _ticket_bound_full_submit_and_closure_request(
    calls: list[dict],
    *,
    submit_body: dict,
    closure_body: dict,
):
    def _request_json(**kwargs):
        calls.append(kwargs)
        url = str(kwargs.get("url") or "")
        if kwargs["method"] == "GET":
            body = _finalgate_ready_body()
        elif "/runtime-post-submit-closures/protected-submit-attempts/" in url:
            body = closure_body
        elif "/runtime-protected-submits/tickets/" in url:
            body = submit_body
        else:
            body = _operation_layer_handoff_ready_body()
        return {"http_status": 200, "error": False, "body": body}

    return _request_json


def _protected_submit_disabled_smoke_body() -> dict:
    return {
        "status": "disabled_smoke_passed",
        "protected_submit_attempt_id": "protected-submit-1",
        "ticket_id": "ticket-ready-1",
        "finalgate_pass_id": "finalgate-pass-1",
        "operation_layer_handoff_id": "handoff-1",
        "operation_submit_command_id": "operation-submit-1",
        "runtime_safety_snapshot_id": "runtime-safety-1",
        "action_time_lane_input_id": "lane-1",
        "strategy_group_id": "SOR-001",
        "symbol": "ETHUSDT",
        "side": "long",
        "submit_mode": "disabled_smoke",
        "submit_allowed": True,
        "blockers": [],
        "warnings": ["disabled_smoke_no_exchange_write"],
        "submit_request": {},
        "submit_result": {"status": "exchange_submit_execution_disabled"},
        "identity_evidence": {},
        "official_operation_layer_submit_called": True,
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
    }


def _protected_submit_submitted_body(**overrides) -> dict:
    body = {
        "status": "submitted",
        "protected_submit_attempt_id": "protected-submit-1",
        "ticket_id": "ticket-ready-1",
        "finalgate_pass_id": "finalgate-pass-1",
        "operation_layer_handoff_id": "handoff-1",
        "operation_submit_command_id": "operation-submit-1",
        "runtime_safety_snapshot_id": "runtime-safety-1",
        "action_time_lane_input_id": "lane-1",
        "strategy_group_id": "SOR-001",
        "symbol": "ETHUSDT",
        "side": "long",
        "submit_mode": "real_gateway_action",
        "submit_allowed": True,
        "blockers": [],
        "warnings": [],
        "submit_request": {},
        "submit_result": {"status": "exchange_submit_orders_submitted"},
        "identity_evidence": {},
        "official_operation_layer_submit_called": True,
        "exchange_write_called": True,
        "order_created": True,
        "order_lifecycle_called": True,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
    }
    body.update(overrides)
    return body


def _post_submit_closure_reconciliation_pending_body(**overrides) -> dict:
    body = {
        "status": "reconciliation_pending",
        "post_submit_closure_id": "post-submit-closure-1",
        "protected_submit_attempt_id": "protected-submit-1",
        "ticket_id": "ticket-ready-1",
        "operation_submit_command_id": "operation-submit-1",
        "strategy_group_id": "SOR-001",
        "symbol": "ETHUSDT",
        "side": "long",
        "protection_state": "submitted",
        "reconciliation_state": "not_checked",
        "settlement_state": "blocked",
        "review_state": "blocked",
        "first_blocker": "post_submit_reconciliation_fact_missing",
        "blockers": ["post_submit_reconciliation_fact_missing"],
        "submitted_order_refs": [{"local_order_id": "entry-1"}],
        "next_action": "run_ticket_bound_post_submit_reconciliation",
        "authority_boundary": "ticket_bound_post_submit_closure",
        "finalgate_called": False,
        "operation_layer_called": False,
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "runtime_budget_mutated": False,
    }
    body.update(overrides)
    return body


def _post_submit_closure_closed_body(**overrides) -> dict:
    body = _post_submit_closure_reconciliation_pending_body(
        status="closed",
        reconciliation_state="matched",
        settlement_state="released",
        review_state="recorded",
        first_blocker=None,
        blockers=[],
        next_action="continue_watcher_observation",
    )
    body.update(overrides)
    return body


def _assert_ticket_bound_operation_layer_ready(artifact: dict) -> None:
    assert artifact["status"] == "operation_layer_ready"
    assert artifact["blocker_class"] == "none"
    assert artifact["dispatch_status"] == "ticket_bound_operation_layer_handoff_ready"
    assert artifact["dispatch_action"] == "prepare_ticket_bound_protected_submit"
    assert artifact["blockers"] == []
    assert artifact["finalgate_preflight_result"]["called"] is True
    assert artifact["operation_layer_handoff_result"]["called"] is True
    assert artifact["ticket_id"] == "ticket-ready-1"
    assert artifact["finalgate_pass_id"] == "finalgate-pass-1"
    assert artifact["operation_layer_handoff_id"] == "handoff-1"
    assert artifact["operation_submit_command_id"] == "operation-submit-1"
    assert artifact["operation_layer_command_plan"]["ticket_id"] == "ticket-ready-1"
    assert artifact["operation_layer_command_plan"]["finalgate_pass_id"] == (
        "finalgate-pass-1"
    )
    assert "authorization_id" not in artifact["operation_layer_command_plan"]
    assert artifact["safety_invariants"]["official_finalgate_preflight_called"] is True
    assert artifact["safety_invariants"]["ticket_bound_operation_layer_handoff_called"]
    assert artifact["safety_invariants"]["official_operation_layer_submit_called"] is False
    assert artifact["safety_invariants"]["places_order"] is False
    assert artifact["safety_invariants"]["exchange_write_called"] is False
    assert artifact["owner_state"]["status"] == "operation_layer_ready"
    assert artifact["owner_state"]["non_authority_checkpoint"] == (
        "prepare_ticket_bound_protected_submit"
    )


def _assert_ticket_bound_protected_submit_disabled_smoke_passed(
    artifact: dict,
) -> None:
    assert artifact["status"] == "operation_layer_disabled_smoke_passed"
    assert artifact["blocker_class"] == "none"
    assert artifact["dispatch_status"] == (
        "ticket_bound_protected_submit_disabled_smoke_passed"
    )
    assert artifact["blockers"] == []
    assert artifact["operation_layer_handoff_result"]["called"] is True
    assert artifact["operation_layer_command_plan"]["ticket_id"] == "ticket-ready-1"
    assert artifact["operation_layer_command_plan"]["finalgate_pass_id"] == (
        "finalgate-pass-1"
    )
    assert "authorization_id" not in artifact["operation_layer_command_plan"]
    assert artifact["operation_layer_submit_result"]["called"] is True
    assert artifact["operation_layer_submit_result"]["body"]["ticket_id"] == (
        "ticket-ready-1"
    )
    assert artifact["operation_layer_submit_result"]["body"][
        "operation_submit_command_id"
    ] == "operation-submit-1"
    assert artifact["safety_invariants"]["official_operation_layer_submit_called"] is True
    assert artifact["safety_invariants"]["places_order"] is False
    assert artifact["safety_invariants"]["exchange_write_called"] is False


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
                "first_real_submit_evidence_unavailable:"
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
    artifact = build_dispatch_artifact(
        resume_pack=_resume_pack(),
        source_path=Path("pg-ticket-identity"),
        selected_strategy_group_id="MPG-001",
    )

    assert artifact["status"] == "waiting_for_market"
    assert artifact["blocker_class"] == "waiting_for_market"
    assert artifact["dispatch_action"] == "continue_watcher_observation"
    assert artifact["dispatch_status"] == "no_action_continue_observation"
    assert artifact["command_plan"] is None
    assert artifact["selected_strategy_group_id"] == "MPG-001"
    assert artifact["safety_invariants"]["places_order"] is False


def test_dispatcher_blocks_retired_non_executing_prepare_file_authority():
    resume = _with_runtime_summary(_resume_pack("ready_for_non_executing_prepare"))
    resume["signal_input_json"] = "pg://runtime-control-state/live-signal-events/signal-mpg-1"
    resume["action_time_resume"].update(
        {
            "next_step": "prepare_fresh_candidate_grant_authorization_evidence",
            "signal_input_json": "pg://runtime-control-state/live-signal-events/signal-mpg-1",
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

    artifact = build_dispatch_artifact(
        resume_pack=resume,
        source_path=Path("pg-ticket-identity"),
        api_base="http://127.0.0.1:18080",
        selected_strategy_group_id="MPG-001",
    )

    assert artifact["status"] == "blocked"
    assert artifact["blocker_class"] == "hard_safety_stop"
    assert artifact["dispatch_action"] is None
    assert artifact["dispatch_status"] == (
        "blocked_by_retired_non_executing_prepare_file_authority"
    )
    assert artifact["command_plan"] is None
    assert (
        "retired_file_authority_scope:non_executing_prepare_signal_input_json"
        in artifact["blockers"]
    )
    assert "pg_promotion_candidate_required" in artifact["blockers"]
    assert "pg_action_time_ticket_required" in artifact["blockers"]
    assert artifact["owner_state"]["non_authority_checkpoint"] == (
        "materialize_pg_action_time_ticket"
    )


def test_dispatcher_ready_for_finalgate_emits_official_preflight_plan():
    artifact = build_dispatch_artifact(
        resume_pack=_with_runtime_summary(
            _resume_pack("ready_for_action_time_final_gate")
        ),
        source_path=Path("pg-ticket-identity"),
        api_base="http://127.0.0.1:18080",
        selected_strategy_group_id="MPG-001",
    )

    assert artifact["status"] == "ready_for_action_time_final_gate"
    assert artifact["blocker_class"] == "none"
    assert artifact["dispatch_action"] == "run_official_action_time_final_gate_preflight"
    assert artifact["dispatch_status"] == "official_finalgate_preflight_dispatch_ready"
    assert artifact["blockers"] == []
    command = artifact["command_plan"]
    assert command["method"] == "GET"
    assert command["ticket_id"] == "ticket-ready-1"
    assert "prepared_authorization_id" not in command
    assert "signal_input_json" not in command
    assert "shadow_candidate_id" not in command
    assert (
        command["path"]
        == "/api/trading-console/runtime-action-time-finalgate-preflights/"
        "tickets/ticket-ready-1"
    )
    assert command["places_order"] is False
    assert command["exchange_write_called"] is False


def test_dispatcher_blocks_finalgate_auth_only_without_ticket_id():
    resume = _with_runtime_summary(_resume_pack("ready_for_action_time_final_gate"))
    resume.pop("ticket_id", None)
    resume["action_time_resume"].pop("ticket_id", None)

    artifact = build_dispatch_artifact(
        resume_pack=resume,
        source_path=Path("pg-ticket-identity"),
        api_base="http://127.0.0.1:18080",
        selected_strategy_group_id="MPG-001",
    )

    assert artifact["status"] == "blocked"
    assert artifact["blocker_class"] == "missing_fact"
    assert artifact["dispatch_status"] == "blocked_by_missing_preflight_evidence"
    assert "missing_fact:ticket_id" in artifact["blockers"]
    assert artifact["command_plan"] is None
    assert artifact["safety_invariants"]["official_finalgate_preflight_called"] is False


def test_dispatcher_blocks_actionable_resume_outside_selected_strategygroup_scope():
    resume = _with_runtime_summary(
        _resume_pack("ready_for_action_time_final_gate"),
        strategy_group_id="SOR-001",
        runtime_instance_id="runtime-sor-1",
    )

    artifact = build_dispatch_artifact(
        resume_pack=resume,
        source_path=Path("pg-ticket-identity"),
        selected_strategy_group_id="MPG-001",
        execute_preflight=True,
    )

    assert artifact["status"] == "blocked"
    assert artifact["dispatch_status"] == "blocked_by_selected_strategygroup_scope"
    assert artifact["command_plan"] is None
    assert artifact["selected_strategy_group_id"] == "MPG-001"
    assert artifact["owner_state"]["blocked_at"] == "selected_strategygroup_scope"
    assert "next_safe_checkpoint" not in artifact["owner_state"]
    assert artifact["owner_state"]["non_authority_checkpoint"] == (
        "review_selected_strategygroup_scope"
    )
    assert artifact["safety_invariants"]["places_order"] is False
    assert artifact["safety_invariants"]["official_finalgate_preflight_called"] is False
    assert artifact["blockers"] == [
        "selected_strategy_group_mismatch:expected=MPG-001:actual=SOR-001"
    ]


def test_dispatcher_blocks_actionable_resume_when_selected_scope_cannot_be_proven():
    resume = _resume_pack("ready_for_action_time_final_gate")
    resume["runtime_instance_id"] = None
    resume["selected_runtime_instance_ids"] = ["runtime-mpg-1", "runtime-sor-1"]

    artifact = build_dispatch_artifact(
        resume_pack=resume,
        source_path=Path("pg-ticket-identity"),
        selected_strategy_group_id="MPG-001",
    )

    assert artifact["status"] == "blocked"
    assert artifact["dispatch_status"] == "blocked_by_selected_strategygroup_scope"
    assert artifact["blockers"] == ["missing_fact:selected_strategy_group_id_for_action"]
    assert artifact["command_plan"] is None
    assert "next_safe_checkpoint" not in artifact["owner_state"]
    assert artifact["owner_state"]["non_authority_checkpoint"] == (
        "review_selected_strategygroup_scope"
    )


def test_dispatcher_blocks_real_submit_when_unselected_scope_cannot_be_proven():
    resume = _finalgate_ready_dispatch_artifact()
    resume.pop("strategy_group_id", None)

    artifact = build_dispatch_artifact(
        resume_pack=resume,
        source_path=Path("pg-ticket-dispatch-identity"),
        operation_layer_evidence_report=_operation_layer_ready_report(),
        execute_operation_layer_submit=True,
    )

    assert artifact["status"] == "blocked"
    assert artifact["dispatch_status"] == "blocked_by_selected_strategygroup_scope"
    assert artifact["command_plan"] is None
    assert artifact["blockers"] == ["missing_fact:unique_strategy_group_for_action"]
    assert artifact["safety_invariants"]["official_operation_layer_submit_called"] is False
    assert artifact["safety_invariants"]["places_order"] is False


def test_dispatcher_blocks_real_submit_when_unselected_scope_is_ambiguous():
    resume = _finalgate_ready_dispatch_artifact()
    resume.pop("strategy_group_id", None)
    resume["selected_runtime_instance_ids"] = ["runtime-mpg-1", "runtime-sor-1"]
    resume["runtime_signal_summaries"] = [
        {
            "runtime_instance_id": "runtime-mpg-1",
            "strategy_group_id": "MPG-001",
            "signal_input_json": resume.get("signal_input_json"),
            "shadow_candidate_id": resume.get("shadow_candidate_id"),
            "prepared_authorization_id": resume.get("prepared_authorization_id"),
        },
        {
            "runtime_instance_id": "runtime-sor-1",
            "strategy_group_id": "SOR-001",
            "signal_input_json": resume.get("signal_input_json"),
            "shadow_candidate_id": resume.get("shadow_candidate_id"),
            "prepared_authorization_id": resume.get("prepared_authorization_id"),
        },
    ]

    artifact = build_dispatch_artifact(
        resume_pack=resume,
        source_path=Path("pg-ticket-dispatch-identity"),
        operation_layer_evidence_report=_operation_layer_ready_report(),
        execute_operation_layer_submit=True,
    )

    assert artifact["status"] == "blocked"
    assert artifact["dispatch_status"] == "blocked_by_selected_strategygroup_scope"
    assert artifact["command_plan"] is None
    assert artifact["blockers"] == [
        "ambiguous_strategy_group_for_action:MPG-001,SOR-001"
    ]
    assert artifact["safety_invariants"]["official_operation_layer_submit_called"] is False
    assert artifact["safety_invariants"]["places_order"] is False


def test_dispatcher_blocks_retired_fresh_authorization_handoff_file_authority():
    artifact = build_dispatch_artifact(
        resume_pack=_fresh_authorization_resume_pack(),
        source_path=Path("pg-ticket-identity"),
        api_base="http://127.0.0.1:18080",
        selected_strategy_group_id="MPG-001",
    )

    assert artifact["status"] == "blocked"
    assert artifact["blocker_class"] == "hard_safety_stop"
    assert artifact["dispatch_action"] is None
    assert artifact["command_plan"] is None
    assert artifact["dispatch_status"] == (
        "blocked_by_retired_fresh_authorization_file_authority"
    )
    assert artifact["blockers"] == [
        "retired_file_authority_scope:fresh_authorization_handoff_json",
        "pg_action_time_ticket_required",
        "ticket_bound_operation_layer_handoff_required",
    ]
    assert artifact["owner_state"]["blocked_at"] == "file_authority_retired"
    assert artifact["owner_state"]["non_authority_checkpoint"] == (
        "materialize_pg_action_time_ticket"
    )
    assert (
        artifact["safety_invariants"].get("official_fresh_authorization_binding_called")
        is not True
    )
    assert artifact["safety_invariants"]["places_order"] is False


def test_dispatcher_blocks_retired_fresh_attempt_readiness_projection_alias(
    tmp_path,
):
    resume = _fresh_authorization_resume_pack()
    resume["scope"] = "runtime_fresh_attempt_readiness_projection"
    resume.pop("action_time_resume")
    resume["status"] = "waiting_for_fresh_authorization"
    resume["allowed_auto_actions"] = ["bind_or_resolve_fresh_authorization"]
    resume["operator_command_plan"] = {
        "next_step": "bind_or_resolve_fresh_authorization",
    }

    artifact = build_dispatch_artifact(
        resume_pack=resume,
        source_path=Path("archive://fresh-attempt-readiness.json"),
        api_base="http://127.0.0.1:18080",
    )

    assert artifact["status"] == "blocked"
    assert artifact["blocker_class"] == "hard_safety_stop"
    assert artifact["dispatch_status"] == "blocked_by_retired_file_authority_projection"
    assert artifact["dispatch_action"] is None
    assert artifact["command_plan"] is None
    assert artifact["blockers"] == [
        "retired_file_authority_scope:runtime_fresh_attempt_readiness_projection"
    ]
    assert artifact["owner_state"]["blocked_at"] == "file_authority_retired"
    assert artifact["owner_state"]["non_authority_checkpoint"] == (
        "materialize_pg_action_time_ticket"
    )
    assert artifact["safety_invariants"]["places_order"] is False


def test_dispatcher_execute_preflight_passes_to_operation_layer_checkpoint(monkeypatch):
    monkeypatch.setattr(
        dispatcher,
        "_session_cookie",
        lambda: ("brc_operator_session=fake-session", None),
    )
    calls: list[dict] = []
    monkeypatch.setattr(
        dispatcher,
        "_request_json",
        _ticket_bound_finalgate_handoff_and_submit_request(
            calls,
            submit_body=_protected_submit_disabled_smoke_body(),
        ),
    )

    artifact = build_dispatch_artifact(
        resume_pack=_with_runtime_summary(
            _resume_pack("ready_for_action_time_final_gate")
        ),
        source_path=Path("pg-ticket-identity"),
        api_base="http://127.0.0.1:18080",
        execute_preflight=True,
    )

    _assert_ticket_bound_operation_layer_ready(artifact)
    assert artifact["owner_state"]["status"] == "operation_layer_ready"
    assert "automatic_recovery_action" not in artifact["owner_state"]
    assert artifact["owner_state"]["non_authority_checkpoint"] == (
        "prepare_ticket_bound_protected_submit"
    )
    assert artifact["owner_state"]["checkpoint_source"] == "owner_state"
    assert artifact["finalgate_preflight_result"]["called"] is True
    assert artifact["operation_layer_command_plan"]["ticket_id"] == "ticket-ready-1"
    assert artifact["safety_invariants"]["official_finalgate_preflight_called"] is True
    assert artifact["safety_invariants"]["official_operation_layer_submit_called"] is False
    assert artifact["safety_invariants"]["places_order"] is False
    assert artifact["safety_invariants"]["exchange_write_called"] is False


def test_dispatcher_finalgate_rejects_legacy_action_fallback_without_allowed_actions():
    resume = _resume_pack("ready_for_action_time_final_gate")
    resume["action_time_resume"].pop("allowed_auto_actions", None)
    resume["action_time_resume"]["next_step"] = (
        "run_official_action_time_final_gate_preflight"
    )
    resume["action_time_resume"]["automatic_recovery_action"] = (
        "run_official_action_time_final_gate_preflight"
    )
    resume["automatic_recovery_action"] = (
        "run_official_action_time_final_gate_preflight"
    )
    resume["operator_command_plan"] = {
        "next_step": "run_official_action_time_final_gate_preflight"
    }

    artifact = build_dispatch_artifact(
        resume_pack=resume,
        source_path=Path("pg-ticket-identity"),
    )

    assert artifact["status"] == "blocked"
    assert artifact["blocker_class"] == "hard_safety_stop"
    assert artifact["dispatch_status"] == "blocked_by_resume_allowed_actions"
    assert "allowed_auto_actions_missing_finalgate_preflight" in artifact["blockers"]
    assert artifact["command_plan"] is None


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

    monkeypatch.setattr(
        dispatcher,
        "_request_json",
        _ticket_bound_finalgate_handoff_and_submit_request(
            calls,
            submit_body=_protected_submit_disabled_smoke_body(),
        ),
    )

    def _prepare_evidence(authorization_id, command_plan):
        prepared.append((authorization_id, command_plan))
        report = _operation_layer_ready_report()
        report["safety"] = {
            "attempt_counter_mutated": True,
            "runtime_budget_mutated": True,
            "exchange_order_submitted": False,
        }
        return report

    artifact = build_dispatch_artifact(
        resume_pack=_with_runtime_summary(
            _resume_pack("ready_for_action_time_final_gate")
        ),
        source_path=Path("pg-ticket-identity"),
        api_base="http://127.0.0.1:18080",
        execute_preflight=True,
        execute_operation_layer_submit=True,
        operation_layer_submit_mode="disabled_smoke",
        operation_layer_evidence_report=_operation_layer_blocked_report(),
        operation_layer_evidence_preparer=_prepare_evidence,
    )

    assert prepared == []
    _assert_ticket_bound_protected_submit_disabled_smoke_passed(artifact)
    assert len(calls) == 3
    assert calls[0]["method"] == "GET"
    assert calls[1]["method"] == "POST"
    assert calls[2]["method"] == "POST"
    assert "/runtime-protected-submits/tickets/ticket-ready-1/" in calls[2]["url"]
    assert "submit_mode=disabled_smoke" in calls[2]["url"]


def test_dispatcher_records_ticket_bound_post_submit_closure_after_real_submit(
    monkeypatch,
):
    monkeypatch.setattr(
        dispatcher,
        "_session_cookie",
        lambda: ("brc_operator_session=fake-session", None),
    )
    calls: list[dict] = []
    monkeypatch.setattr(
        dispatcher,
        "_request_json",
        _ticket_bound_full_submit_and_closure_request(
            calls,
            submit_body=_protected_submit_submitted_body(),
            closure_body=_post_submit_closure_reconciliation_pending_body(),
        ),
    )

    artifact = build_dispatch_artifact(
        resume_pack=_with_runtime_summary(
            _resume_pack("ready_for_action_time_final_gate")
        ),
        source_path=Path("pg-ticket-identity"),
        api_base="http://127.0.0.1:18080",
        execute_preflight=True,
        execute_operation_layer_submit=True,
        execute_post_submit_finalize=True,
    )

    assert artifact["status"] == "post_submit_reconciliation_pending"
    assert artifact["blocker_class"] == "missing_fact"
    assert artifact["dispatch_status"] == (
        "ticket_bound_post_submit_closure_reconciliation_pending"
    )
    assert artifact["blockers"] == ["post_submit_reconciliation_fact_missing"]
    assert artifact["dispatch_action"] is None
    assert artifact["ticket_bound_post_submit_closure_result"]["called"] is True
    assert artifact["ticket_bound_post_submit_closure_result"]["body"][
        "post_submit_closure_id"
    ] == "post-submit-closure-1"
    assert artifact["safety_invariants"]["official_operation_layer_submit_called"] is True
    assert artifact["safety_invariants"]["ticket_bound_post_submit_closure_called"] is True
    assert artifact["safety_invariants"]["official_post_submit_finalize_called"] is False
    assert artifact["safety_invariants"]["post_submit_budget_settlement_called"] is False
    assert artifact["safety_invariants"]["runtime_budget_mutated"] is False
    assert artifact["safety_invariants"]["places_order"] is True
    assert artifact["safety_invariants"]["exchange_write_called"] is True
    assert len(calls) == 4
    assert calls[0]["method"] == "GET"
    assert calls[1]["method"] == "POST"
    assert calls[2]["method"] == "POST"
    assert calls[3]["method"] == "POST"
    assert "/runtime-protected-submits/tickets/ticket-ready-1/" in calls[2]["url"]
    assert (
        "/runtime-post-submit-closures/protected-submit-attempts/protected-submit-1"
        in calls[3]["url"]
    )
    assert "post-submit-finalize-payloads" not in calls[3]["url"]


def test_dispatcher_blocks_ticket_bound_closed_closure_without_settlement_release(
    monkeypatch,
):
    monkeypatch.setattr(
        dispatcher,
        "_session_cookie",
        lambda: ("brc_operator_session=fake-session", None),
    )
    calls: list[dict] = []
    monkeypatch.setattr(
        dispatcher,
        "_request_json",
        _ticket_bound_full_submit_and_closure_request(
            calls,
            submit_body=_protected_submit_submitted_body(),
            closure_body=_post_submit_closure_closed_body(settlement_state="blocked"),
        ),
    )

    artifact = build_dispatch_artifact(
        resume_pack=_with_runtime_summary(
            _resume_pack("ready_for_action_time_final_gate")
        ),
        source_path=Path("pg-ticket-identity"),
        api_base="http://127.0.0.1:18080",
        execute_preflight=True,
        execute_operation_layer_submit=True,
        execute_post_submit_finalize=True,
    )

    assert artifact["status"] == "post_submit_closure_blocked"
    assert artifact["dispatch_status"] == (
        "ticket_bound_post_submit_closure_closed_truth_mismatch"
    )
    assert artifact["dispatch_action"] is None
    assert (
        "ticket_bound_post_submit_closure_closed_truth:settlement_state:"
        "expected=released:actual=blocked"
    ) in artifact["blockers"]
    assert artifact["safety_invariants"]["official_post_submit_finalize_called"] is False
    assert artifact["safety_invariants"]["post_submit_budget_settlement_called"] is False


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

    monkeypatch.setattr(
        dispatcher,
        "_request_json",
        _ticket_bound_finalgate_handoff_and_submit_request(
            calls,
            submit_body=_protected_submit_submitted_body(symbol="SOLUSDT"),
        ),
    )

    artifact = build_dispatch_artifact(
        resume_pack=_with_runtime_summary(
            _resume_pack("ready_for_action_time_final_gate")
        ),
        source_path=Path("pg-ticket-identity"),
        api_base="http://127.0.0.1:18080",
        execute_preflight=True,
        execute_operation_layer_submit=True,
        operation_layer_evidence_report=_operation_layer_shadow_boundary_report(),
        operation_layer_evidence_preparer=_prepare_evidence,
        runtime_live_enabler=_live_enable_runtime,
    )

    assert prepared == []
    assert live_enablement_calls == []
    assert artifact["status"] == "operation_layer_submit_failed"
    assert artifact["dispatch_status"] == "ticket_bound_submit_result_identity_mismatch"
    assert artifact["blocker_class"] == "hard_safety_stop"
    assert artifact["blockers"] == [
        "ticket_bound_submit_result_mismatch:symbol:"
        "expected=ETHUSDT:actual=SOLUSDT"
    ]
    assert "runtime_live_enablement_result" not in artifact
    assert artifact["operation_layer_submit_result"]["called"] is True
    assert artifact["safety_invariants"]["places_order"] is True
    assert artifact["safety_invariants"]["exchange_write_called"] is True
    assert artifact["safety_invariants"]["withdrawal_or_transfer_created"] is False


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


def test_dispatcher_blocks_legacy_finalgate_ready_before_operation_layer_evidence_blocker():
    artifact = build_dispatch_artifact(
        resume_pack=_finalgate_ready_dispatch_artifact(),
        source_path=Path("pg-ticket-dispatch-identity"),
        operation_layer_evidence_report=_operation_layer_blocked_report(),
        operation_layer_evidence_report_path=(
            "pg://runtime-control-state/operation-layer-handoff/evidence"
        ),
    )

    _assert_legacy_finalgate_ready_blocked(artifact)
    assert "persistent_duplicate_submit_lock_required" not in artifact["blockers"]


def test_dispatcher_blocks_legacy_finalgate_ready_before_operation_layer_evidence_ready():
    artifact = build_dispatch_artifact(
        resume_pack=_finalgate_ready_dispatch_artifact(),
        source_path=Path("pg-ticket-dispatch-identity"),
        operation_layer_evidence_report=_operation_layer_ready_report(),
        operation_layer_evidence_report_path=(
            "pg://runtime-control-state/operation-layer-handoff/evidence"
        ),
    )

    _assert_legacy_finalgate_ready_blocked(artifact)


def test_dispatcher_blocks_real_submit_if_standing_authorization_semantics_regress(
    monkeypatch,
):
    monkeypatch.setattr(
        dispatcher,
        "_session_cookie",
        lambda: ("brc_operator_session=fake-session", None),
    )

    resume_pack = _finalgate_ready_dispatch_artifact()
    operation_layer_command_plan = dict(resume_pack["operation_layer_command_plan"])
    operation_layer_command_plan["standing_authorized_first_real_submit"] = False
    operation_layer_command_plan["owner_chat_confirmation_required_for_real_submit"] = True
    operation_layer_command_plan["legacy_owner_confirmation_env_required"] = True
    resume_pack["operation_layer_command_plan"] = operation_layer_command_plan

    artifact = build_dispatch_artifact(
        resume_pack=resume_pack,
        source_path=Path("pg-ticket-dispatch-identity"),
        operation_layer_evidence_report=_operation_layer_ready_report(),
        operation_layer_evidence_report_path=(
            "pg://runtime-control-state/operation-layer-handoff/evidence"
        ),
        execute_operation_layer_submit=True,
    )

    _assert_legacy_finalgate_ready_blocked(artifact)


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

    artifact = build_dispatch_artifact(
        resume_pack=_finalgate_ready_dispatch_artifact(),
        source_path=Path("pg-ticket-dispatch-identity"),
        operation_layer_evidence_report=_operation_layer_ready_report(),
        operation_layer_evidence_report_path=(
            "pg://runtime-control-state/operation-layer-handoff/evidence"
        ),
        execute_operation_layer_submit=True,
    )

    _assert_legacy_finalgate_ready_blocked(artifact)
    assert calls == []


def test_dispatcher_executes_operation_layer_disabled_smoke_when_requested(
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
        return {
            "http_status": 200,
            "error": False,
            "body": {
                "status": "exchange_submit_execution_disabled",
                "exchange_submit_execution_enabled": False,
                "exchange_submit_execution_mode": "disabled",
                "exchange_called": False,
                "exchange_order_submitted": False,
                "order_lifecycle_submit_called": False,
                "owner_bounded_execution_called": False,
                "execution_intent_status_changed": False,
                "withdrawal_or_transfer_created": False,
            },
        }

    monkeypatch.setattr(dispatcher, "_request_json", _request_json)

    artifact = build_dispatch_artifact(
        resume_pack=_finalgate_ready_dispatch_artifact(),
        source_path=Path("pg-ticket-dispatch-identity"),
        operation_layer_evidence_report=_operation_layer_ready_report(),
        operation_layer_evidence_report_path=(
            "pg://runtime-control-state/operation-layer-handoff/evidence"
        ),
        execute_operation_layer_submit=True,
        operation_layer_submit_mode="disabled_smoke",
    )

    _assert_legacy_finalgate_ready_blocked(artifact)
    assert calls == []


def test_dispatcher_executes_post_submit_finalize_after_submit(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(
        dispatcher,
        "_session_cookie",
        lambda: ("brc_operator_session=fake-session", None),
    )

    def _request_json(**kwargs):
        calls.append(kwargs)
        if "post-submit-finalize-payloads" in kwargs["url"]:
            return {
                "http_status": 200,
                "error": False,
                "body": {
                    "status": "finalized_ready_for_next_attempt",
                    "authorization_id": "auth-ready-1",
                    "runtime_instance_id": "runtime-mpg-1",
                    "exchange_submit_execution_result_id": "submit-result-1",
                    "post_submit_reconciliation_evidence_id": (
                        "reconciliation-1"
                    ),
                    "submit_outcome_review_id": "review-1",
                    "post_submit_budget_settlement_id": "settlement-1",
                    "post_submit_finalize_complete": True,
                    "post_submit_reconciliation_matched": True,
                    "post_submit_budget_settled": True,
                    "submit_outcome_review_recorded": True,
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

    artifact = build_dispatch_artifact(
        resume_pack=_finalgate_ready_dispatch_artifact(),
        source_path=Path("pg-ticket-dispatch-identity"),
        operation_layer_evidence_report=_operation_layer_ready_report(),
        operation_layer_evidence_report_path=(
            "pg://runtime-control-state/operation-layer-handoff/evidence"
        ),
        execute_operation_layer_submit=True,
        execute_post_submit_finalize=True,
    )

    _assert_legacy_finalgate_ready_blocked(artifact)
    assert "post_submit_finalize_result" not in artifact
    assert calls == []


def test_dispatcher_blocks_incomplete_post_submit_closed_loop(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(
        dispatcher,
        "_session_cookie",
        lambda: ("brc_operator_session=fake-session", None),
    )

    def _request_json(**kwargs):
        calls.append(kwargs)
        if "post-submit-finalize-payloads" in kwargs["url"]:
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

    artifact = build_dispatch_artifact(
        resume_pack=_finalgate_ready_dispatch_artifact(),
        source_path=Path("pg-ticket-dispatch-identity"),
        operation_layer_evidence_report=_operation_layer_ready_report(),
        operation_layer_evidence_report_path=(
            "pg://runtime-control-state/operation-layer-handoff/evidence"
        ),
        execute_operation_layer_submit=True,
        execute_post_submit_finalize=True,
    )

    _assert_legacy_finalgate_ready_blocked(artifact)
    assert "post_submit_finalize_result" not in artifact
    assert calls == []


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

    artifact = build_dispatch_artifact(
        resume_pack=_finalgate_ready_dispatch_artifact(),
        source_path=Path("pg-ticket-dispatch-identity"),
        operation_layer_evidence_report=_operation_layer_ready_report(),
        operation_layer_evidence_report_path=(
            "pg://runtime-control-state/operation-layer-handoff/evidence"
        ),
        execute_operation_layer_submit=True,
        execute_post_submit_finalize=True,
    )

    _assert_legacy_finalgate_ready_blocked(artifact)
    assert "post_submit_finalize_result" not in artifact
    assert artifact["safety_invariants"]["official_post_submit_finalize_called"] is False
    assert artifact["safety_invariants"]["withdrawal_or_transfer_created"] is False
    assert calls == []


def test_dispatcher_blocks_post_submit_finalize_runtime_mismatch(monkeypatch):
    monkeypatch.setattr(
        dispatcher,
        "_session_cookie",
        lambda: ("brc_operator_session=fake-session", None),
    )

    def _request_json(**kwargs):
        if "post-submit-finalize-payloads" in kwargs["url"]:
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

    artifact = build_dispatch_artifact(
        resume_pack=_finalgate_ready_dispatch_artifact(),
        source_path=Path("pg-ticket-dispatch-identity"),
        operation_layer_evidence_report=_operation_layer_ready_report(),
        operation_layer_evidence_report_path=(
            "pg://runtime-control-state/operation-layer-handoff/evidence"
        ),
        execute_operation_layer_submit=True,
        execute_post_submit_finalize=True,
    )

    _assert_legacy_finalgate_ready_blocked(artifact)
    assert "post_submit_finalize_result" not in artifact
    assert artifact["safety_invariants"]["official_post_submit_finalize_called"] is False


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
    resume = _finalgate_ready_dispatch_artifact()
    resume["finalgate_preflight_result"] = {"called": False}

    artifact = build_dispatch_artifact(
        resume_pack=resume,
        source_path=Path("pg-ticket-dispatch-identity"),
        operation_layer_evidence_report=_operation_layer_ready_report(),
        operation_layer_evidence_report_path=(
            "pg://runtime-control-state/operation-layer-handoff/evidence"
        ),
        execute_operation_layer_submit=True,
    )

    _assert_legacy_finalgate_ready_blocked(artifact)
    assert called["request"] is False


def test_dispatcher_blocks_legacy_finalgate_ready_before_stale_authorization_evidence():
    report = _operation_layer_ready_report()
    report["ids"]["authorization_id"] = "old-auth-1"

    artifact = build_dispatch_artifact(
        resume_pack=_finalgate_ready_dispatch_artifact(),
        source_path=Path("pg-ticket-dispatch-identity"),
        operation_layer_evidence_report=report,
        operation_layer_evidence_report_path=(
            "pg://runtime-control-state/operation-layer-handoff/evidence"
        ),
    )

    _assert_legacy_finalgate_ready_blocked(artifact)
    assert not any(
        blocker.startswith("operation_layer_authorization_id_mismatch:")
        for blocker in artifact["blockers"]
    )


def test_dispatcher_blocks_legacy_finalgate_ready_before_local_registration_probe():
    artifact = build_dispatch_artifact(
        resume_pack=_finalgate_ready_dispatch_artifact(),
        source_path=Path("pg-ticket-dispatch-identity"),
        operation_layer_evidence_report=(
            _operation_layer_report_with_satisfied_legacy_probe_blocker()
        ),
        operation_layer_evidence_report_path=(
            "pg://runtime-control-state/operation-layer-handoff/evidence"
        ),
    )

    _assert_legacy_finalgate_ready_blocked(artifact)
    assert "operation_layer_readiness" not in artifact


def test_dispatcher_blocks_legacy_finalgate_ready_before_unsatisfied_local_registration_probe():
    report = _operation_layer_report_with_satisfied_legacy_probe_blocker()
    report["ids"].pop("local_registration_adapter_result_id")

    artifact = build_dispatch_artifact(
        resume_pack=_finalgate_ready_dispatch_artifact(),
        source_path=Path("pg-ticket-dispatch-identity"),
        operation_layer_evidence_report=report,
        operation_layer_evidence_report_path=(
            "pg://runtime-control-state/operation-layer-handoff/evidence"
        ),
    )

    _assert_legacy_finalgate_ready_blocked(artifact)
    assert not any(
        "runtimeexecutionorderlifecycleadapterresult_not_found" in blocker
        for blocker in artifact["blockers"]
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

    artifact = build_dispatch_artifact(
        resume_pack=_resume_pack("ready_for_action_time_final_gate"),
        source_path=Path("pg-ticket-identity"),
        execute_preflight=True,
    )

    assert artifact["status"] == "blocked"
    assert artifact["blocker_class"] == "hard_safety_stop"
    assert artifact["dispatch_status"] == "blocked_by_action_time_finalgate"
    assert "active_position_conflict" in artifact["blockers"]
    assert artifact["owner_state"]["blocked_at"] == "FinalGate"
    assert artifact["owner_state"]["downgrade_mode"] == "observe_only_no_submit"
    assert artifact["operation_layer_command_plan"] is None
    assert artifact["safety_invariants"]["places_order"] is False


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

    artifact = build_dispatch_artifact(
        resume_pack=_resume_pack("ready_for_action_time_final_gate"),
        source_path=Path("pg-ticket-identity"),
        execute_preflight=True,
    )

    assert artifact["status"] == "blocked"
    assert artifact["blocker_class"] == "deployment_issue"
    assert artifact["dispatch_status"] == "blocked_by_operator_session_unavailable"
    assert artifact["owner_state"]["blocked_at"] == "operator_session"
    assert "automatic_recovery_action" not in artifact["owner_state"]
    assert artifact["owner_state"]["non_authority_checkpoint"] == (
        "restore_operator_session_or_local_session_signing"
    )
    assert artifact["owner_state"]["checkpoint_source"] == "owner_state"
    assert called["request"] is False
    assert artifact["safety_invariants"]["places_order"] is False


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

    artifact = build_dispatch_artifact(
        resume_pack=_resume_pack("ready_for_action_time_final_gate"),
        source_path=Path("pg-ticket-identity"),
        execute_preflight=True,
    )

    assert artifact["status"] == "blocked"
    assert artifact["blocker_class"] == "hard_safety_stop"
    assert artifact["dispatch_status"] == "blocked_by_finalgate_preflight_forbidden_effect"
    assert "preflight_effect:exchange_called" in artifact["blockers"]
    assert artifact["owner_state"]["blocked_at"] == "FinalGate"
    assert artifact["operation_layer_command_plan"] is None


def test_dispatcher_allows_ticket_bound_ready_without_signal_json():
    resume = _resume_pack("ready_for_action_time_final_gate")
    resume["action_time_resume"]["signal_input_json"] = None
    resume["signal_input_json"] = None

    artifact = build_dispatch_artifact(
        resume_pack=resume,
        source_path=Path("pg-ticket-identity"),
    )

    assert artifact["status"] == "ready_for_action_time_final_gate"
    assert artifact["blocker_class"] == "none"
    assert artifact["dispatch_status"] == "official_finalgate_preflight_dispatch_ready"
    assert artifact["blockers"] == []
    assert artifact["command_plan"]["ticket_id"] == "ticket-ready-1"
    assert "signal_input_json" not in artifact["command_plan"]


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

    monkeypatch.setattr(
        dispatcher,
        "_request_json",
        _ticket_bound_finalgate_and_handoff_request(calls),
    )

    artifact = build_dispatch_artifact(
        resume_pack=resume,
        source_path=Path("pg-ticket-identity"),
        execute_preflight=True,
    )

    _assert_ticket_bound_operation_layer_ready(artifact)
    assert "shadow_candidate_id" not in artifact["command_plan"]
    assert calls[0]["method"] == "GET"
    assert calls[0]["url"].endswith(
        "/runtime-action-time-finalgate-preflights/tickets/ticket-ready-1"
    )
    assert calls[1]["method"] == "POST"
    assert calls[1]["url"].endswith(
        "/runtime-operation-layer-handoffs/tickets/ticket-ready-1/"
        "finalgate-passes/finalgate-pass-1"
    )


def test_dispatcher_blocks_ticket_bound_handoff_forbidden_effects(monkeypatch):
    calls = []
    handoff_body = _operation_layer_handoff_ready_body()
    handoff_body["live_profile_changed"] = True
    handoff_body["command_plan"]["authorization_id"] = "legacy-auth-1"

    def _request_json(**kwargs):
        calls.append(kwargs)
        return {
            "http_status": 200,
            "error": False,
            "body": handoff_body if kwargs["method"] == "POST" else _finalgate_ready_body(),
        }

    monkeypatch.setattr(
        dispatcher,
        "_session_cookie",
        lambda: ("brc_operator_session=fake-session", None),
    )
    monkeypatch.setattr(dispatcher, "_request_json", _request_json)

    artifact = build_dispatch_artifact(
        resume_pack=_resume_pack("ready_for_action_time_final_gate"),
        source_path=Path("pg-ticket-identity"),
        execute_preflight=True,
    )

    assert artifact["status"] == "blocked"
    assert artifact["blocker_class"] == "hard_safety_stop"
    assert artifact["dispatch_status"] == (
        "blocked_by_operation_layer_handoff_forbidden_effect"
    )
    assert "operation_layer_handoff_effect:live_profile_changed" in artifact["blockers"]
    assert (
        "operation_layer_handoff_legacy_input:authorization_id"
        in artifact["blockers"]
    )
    assert artifact["operation_layer_command_plan"] is None
    assert [call["method"] for call in calls] == ["GET", "POST"]


def test_dispatcher_blocks_ticket_bound_handoff_identity_mismatch(monkeypatch):
    calls = []
    handoff_body = _operation_layer_handoff_ready_body()
    handoff_body["ticket_id"] = "ticket-other"
    handoff_body["command_plan"]["finalgate_pass_id"] = "finalgate-pass-other"

    def _request_json(**kwargs):
        calls.append(kwargs)
        return {
            "http_status": 200,
            "error": False,
            "body": handoff_body if kwargs["method"] == "POST" else _finalgate_ready_body(),
        }

    monkeypatch.setattr(
        dispatcher,
        "_session_cookie",
        lambda: ("brc_operator_session=fake-session", None),
    )
    monkeypatch.setattr(dispatcher, "_request_json", _request_json)

    artifact = build_dispatch_artifact(
        resume_pack=_resume_pack("ready_for_action_time_final_gate"),
        source_path=Path("pg-ticket-identity"),
        execute_preflight=True,
    )

    assert artifact["status"] == "blocked"
    assert artifact["blocker_class"] == "hard_safety_stop"
    assert artifact["dispatch_status"] == (
        "blocked_by_ticket_bound_operation_layer_handoff_identity"
    )
    assert (
        "operation_layer_handoff_body_mismatch:ticket_id:"
        "expected=ticket-ready-1:actual=ticket-other"
    ) in artifact["blockers"]
    assert (
        "operation_layer_handoff_command_mismatch:finalgate_pass_id:"
        "expected=finalgate-pass-1:actual=finalgate-pass-other"
    ) in artifact["blockers"]
    assert artifact["operation_layer_command_plan"] is None
    assert artifact["safety_invariants"]["official_operation_layer_submit_called"] is False
    assert artifact["safety_invariants"]["exchange_write_called"] is False
    assert [call["method"] for call in calls] == ["GET", "POST"]


def test_dispatcher_blocks_unsafe_resume_flags():
    resume = _resume_pack("ready_for_action_time_final_gate")
    resume["action_time_resume"]["exchange_write_called"] = True

    artifact = build_dispatch_artifact(
        resume_pack=resume,
        source_path=Path("pg-ticket-identity"),
    )

    assert artifact["status"] == "blocked"
    assert artifact["blocker_class"] == "hard_safety_stop"
    assert artifact["dispatch_status"] == "blocked_by_unsafe_resume_flags"
    assert "unsafe_flag:exchange_write_called" in artifact["blockers"]
    assert artifact["command_plan"] is None


def test_dispatcher_pg_ticket_identity_missing_fails_closed(tmp_path):
    database_url = _pg_ticket_identity_db(tmp_path, lane_count=0, ticket_count=0)

    resume_pack, _source_path = dispatcher._pg_ticket_resume_pack(
        database_url=database_url,
        api_base="http://127.0.0.1:18080",
    )

    assert resume_pack["status"] == "blocked"
    assert resume_pack["pg_ticket_identity_dispatch_status"] == (
        "blocked_by_missing_pg_ticket_identity"
    )
    assert resume_pack["owner_state"]["blocker_class"] == "runtime_data_gap"
    assert resume_pack["owner_state"]["owner_action_required"] is False
    assert resume_pack["safety_invariants"]["exchange_write_called"] is False


def test_dispatcher_pg_ticket_identity_multiple_fails_closed(tmp_path):
    database_url = _pg_ticket_identity_db(tmp_path, lane_count=2, ticket_count=2)

    resume_pack, _source_path = dispatcher._pg_ticket_resume_pack(
        database_url=database_url,
        api_base="http://127.0.0.1:18080",
    )

    assert resume_pack["status"] == "blocked"
    assert resume_pack["pg_ticket_identity_dispatch_status"] == (
        "blocked_by_ambiguous_pg_ticket_identity"
    )
    assert "ambiguous_open_pg_action_time_ticket:ticket-1,ticket-2" in resume_pack[
        "blockers"
    ]


def test_dispatcher_pg_ticket_identity_mismatch_fails_closed(tmp_path):
    database_url = _pg_ticket_identity_db(
        tmp_path,
        lane_count=1,
        ticket_count=1,
        ticket_symbol="BTCUSDT",
    )

    resume_pack, _source_path = dispatcher._pg_ticket_resume_pack(
        database_url=database_url,
        api_base="http://127.0.0.1:18080",
    )

    assert resume_pack["status"] == "blocked"
    assert resume_pack["pg_ticket_identity_dispatch_status"] == (
        "blocked_by_inconsistent_pg_ticket_identity"
    )
    assert resume_pack["blockers"] == [
        "inconsistent_pg_action_time_ticket_identity:ticket-1:symbol"
    ]


def test_dispatcher_pg_ticket_identity_emits_ticket_bound_preflight_plan(tmp_path):
    database_url = _pg_ticket_identity_db(tmp_path)

    resume_pack, _source_path = dispatcher._pg_ticket_resume_pack(
        database_url=database_url,
        api_base="http://127.0.0.1:18080",
    )

    assert resume_pack["scope"] == "pg_ticket_bound_resume_identity"
    assert resume_pack["source_mode"] == "db_backed"
    assert resume_pack["ticket_id"] == "ticket-1"
    assert resume_pack["action_time_lane_input_id"] == "lane-1"
    assert resume_pack["promotion_candidate_id"] == "promotion-1"
    assert resume_pack["signal_event_id"] == "signal-1"
    assert resume_pack["strategy_group_id"] == "SOR-001"
    assert resume_pack["symbol"] == "ETHUSDT"
    assert resume_pack["side"] == "long"
    assert resume_pack["command_plan"]["path"].endswith(
        "/runtime-action-time-finalgate-preflights/tickets/ticket-1"
    )
    assert resume_pack["safety_invariants"]["exchange_write_called"] is False


def test_dispatcher_cli_pg_ticket_identity_emits_ticket_bound_artifact_stdout(
    tmp_path,
    capsys,
):
    database_url = _pg_ticket_identity_db(tmp_path)

    exit_code = main(
        [
            "--identity-source",
            "pg_ticket",
            "--database-url",
            database_url,
        ]
    )

    assert exit_code == 0
    artifact = _captured_stdout_artifact(capsys)
    assert artifact["status"] == "ready_for_action_time_final_gate"
    assert artifact["dispatch_action"] == "run_official_action_time_final_gate_preflight"
    assert artifact["command_plan"]["ticket_id"] == "ticket-1"
    assert not (tmp_path / "resume-dispatch-artifact.json").exists()


def test_dispatcher_cli_rejects_removed_resume_pack_json_identity():
    with pytest.raises(SystemExit) as exc:
        main(["--identity-source", "resume_pack_json"])

    assert exc.value.code == 2


def test_dispatcher_cli_finalgate_ready_is_success_exit(
    tmp_path,
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        dispatcher,
        "_session_cookie",
        lambda: ("brc_operator_session=fake-session", None),
    )
    calls = []
    monkeypatch.setattr(
        dispatcher,
        "_request_json",
        _ticket_bound_finalgate_and_handoff_request(calls),
    )
    database_url = _pg_ticket_identity_db(tmp_path)

    exit_code = main(
        [
            "--identity-source",
            "pg_ticket",
            "--database-url",
            database_url,
            "--execute-preflight",
        ]
    )

    assert exit_code == 0
    artifact = _captured_stdout_artifact(capsys)
    _assert_ticket_bound_operation_layer_ready(artifact)
    assert [call["method"] for call in calls] == ["GET", "POST"]
    assert not (tmp_path / "resume-dispatch-artifact.json").exists()
