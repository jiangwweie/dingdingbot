from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_runtime_strategy_signal_watch_evidence.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_runtime_strategy_signal_watch_evidence",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _status_artifact(
    *,
    status="waiting_for_signal",
    signal_type="no_action",
    prepared_authorization_id=None,
    shadow_candidate_id=None,
):
    return {
        "status": status,
        "latest_status": status,
        "latest_iteration": 6,
        "iterations_completed": 6,
        "artifact_stale": False,
        "stop_reason": "running",
        "active_runtime_count": 1,
        "monitored_runtime_count": 1,
        "selected_runtime_instance_ids": ["runtime-1"],
        "prepared_authorization_id": prepared_authorization_id,
        "shadow_candidate_id": shadow_candidate_id,
        "runtime_signal_summaries": [
            {
                "runtime_instance_id": "runtime-1",
                "strategy_family_id": "CPM-001",
                "strategy_family_version_id": "CPM-001-v0",
                "symbol": "BNB/USDT:USDT",
                "side": "long",
                "status": status,
                "evaluation_status": "observe_only",
                "signal_type": signal_type,
                "signal_side": "none",
                "confidence": "0.25",
                "reason_codes": ["cpm_no_action_no_reclaim"],
                "human_summary": "No CPM action.",
            }
        ],
        "safety_invariants": {
            "places_order": False,
            "calls_order_lifecycle": False,
            "creates_execution_intent": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _strategy_preview(*, would_enter=False, forbidden=False):
    return {
        "status": "preview_built",
        "source_requested": "sample",
        "market_source": "sample_source",
        "checks": {
            "candidate_count": 1,
            "current_signal_count": 1,
            "would_enter_signal_count": 1 if would_enter else 0,
            "no_action_signal_count": 0 if would_enter else 1,
            "forbidden_effects": [],
        },
        "would_enter_signals": [
            {
                "candidate_id": "BRF-001-BTC-SHORT",
                "strategy_group_id": "BRF-001",
                "strategy_family_version_id": "BRF-001-v0",
                "symbol": "BTC/USDT:USDT",
                "side": "short",
                "signal_type": "would_enter",
                "confidence": "0.65",
                "reason_codes": ["brf_rejection_close"],
                "human_summary": "BRF would enter.",
                "not_order": True,
                "not_execution_intent": True,
                "no_execution_permission": True,
                "no_order_permission": True,
                "no_runtime_start": True,
            }
        ]
        if would_enter
        else [],
        "no_action_signals": []
        if would_enter
        else [
            {
                "candidate_id": "CPM-RO-001",
                "strategy_group_id": "CPM-RO-001",
                "strategy_family_version_id": "CPM-RO-001-v0",
                "symbol": "ETH/USDT:USDT",
                "side": "long",
                "signal_type": "no_action",
                "confidence": "0.25",
                "reason_codes": ["cpm_no_action_no_reclaim"],
                "human_summary": "No CPM action.",
                "not_order": True,
                "not_execution_intent": True,
                "no_execution_permission": True,
                "no_order_permission": True,
                "no_runtime_start": True,
            }
        ],
        "safety_invariants": {
            "preview_only": True,
            "pg_observation_written": False,
            "execution_intent_created": False,
            "order_created": forbidden,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
        },
    }


def test_watch_evidence_summarizes_waiting_no_signal():
    module = _load_module()

    artifact = module.build_watch_evidence(
        active_status_artifact=_status_artifact(),
        strategy_preview_artifact=_strategy_preview(),
    )

    assert artifact["status"] == "watching_no_signal"
    assert artifact["active_runtime_observation"]["monitored_runtime_count"] == 1
    assert artifact["active_runtime_observation"]["selected_runtime_instance_ids"] == [
        "runtime-1"
    ]
    assert artifact["checks"]["runtime_ready_signal_count"] == 0
    assert artifact["checks"]["strategy_group_would_enter_signal_count"] == 0
    assert "operator_command_plan" not in artifact
    assert artifact["watch_evidence_plan"]["next_step"] == (
        "continue_active_runtime_observation"
    )
    assert artifact["watch_evidence_plan"]["allowed_review_checkpoints"] == [
        "continue_active_runtime_observation"
    ]
    assert artifact["safety_invariants"]["order_created"] is False
    assert artifact["safety_invariants"]["execution_intent_created"] is False


def test_watch_evidence_surfaces_runtime_ready_prepare_context():
    module = _load_module()

    artifact = module.build_watch_evidence(
        active_status_artifact=_status_artifact(
            status="ready_for_prepare",
            signal_type="would_enter",
        ),
        strategy_preview_artifact=_strategy_preview(),
    )

    assert artifact["status"] == "runtime_signal_ready"
    assert artifact["checks"]["runtime_ready_signal_count"] == 1
    assert artifact["runtime_action_time_context"]["ready_for_prepare_count"] == 1
    assert "prepared_authorization_id" not in artifact["runtime_action_time_context"]
    assert "shadow_candidate_id" not in artifact["runtime_action_time_context"]
    assert (
        artifact["watch_evidence_plan"]["next_step"]
        == "materialize_pg_action_time_ticket"
    )
    assert artifact["watch_evidence_plan"]["allowed_review_checkpoints"] == [
        "review_runtime_ready_signal",
        "materialize_pg_action_time_ticket",
    ]
    assert "place_exchange_order" in artifact["runtime_action_time_context"]["forbidden_followups"]
    assert artifact["watch_evidence_plan"]["places_order"] is False


def test_watch_evidence_surfaces_prepared_records_preview_only_context():
    module = _load_module()

    artifact = module.build_watch_evidence(
        active_status_artifact=_status_artifact(
            status="ready_for_final_gate_preflight",
            signal_type="would_enter",
            prepared_authorization_id="prep-auth-1",
            shadow_candidate_id="shadow-candidate-1",
        ),
        strategy_preview_artifact=_strategy_preview(),
    )

    assert artifact["status"] == "runtime_signal_ready_for_action_time_ticket"
    assert (
        artifact["runtime_action_time_context"]["ready_for_final_gate_preflight_count"] == 1
    )
    assert "prepared_authorization_id" not in artifact["runtime_action_time_context"]
    assert "shadow_candidate_id" not in artifact["runtime_action_time_context"]
    assert artifact["watch_evidence_plan"]["allowed_review_checkpoints"] == [
        "materialize_pg_action_time_ticket",
        "run_ticket_bound_finalgate_preflight",
        "prepare_ticket_bound_operation_layer_handoff",
    ]
    assert "execute_first_real_submit" in artifact["runtime_action_time_context"]["forbidden_followups"]
    assert artifact["watch_evidence_plan"]["creates_execution_intent"] is False


def test_watch_evidence_surfaces_strategy_group_would_enter_without_execution():
    module = _load_module()

    artifact = module.build_watch_evidence(
        active_status_artifact=_status_artifact(),
        strategy_preview_artifact=_strategy_preview(would_enter=True),
    )

    assert artifact["status"] == "strategy_group_signal_review_available"
    assert artifact["checks"]["strategy_group_would_enter_signal_count"] == 1
    assert artifact["watch_evidence_plan"]["next_step"] == (
        "review_would_enter_strategy_group_without_execution"
    )
    assert artifact["strategy_group_would_enter_signals"][0]["not_order"] is True
    assert artifact["watch_evidence_plan"]["places_order"] is False


def test_watch_evidence_blocks_forbidden_effects():
    module = _load_module()

    artifact = module.build_watch_evidence(
        active_status_artifact=_status_artifact(),
        strategy_preview_artifact=_strategy_preview(forbidden=True),
    )

    assert artifact["status"] == "blocked_forbidden_effect"
    assert artifact["checks"]["forbidden_effects"] == [
        "strategy_preview_artifact.order_created"
    ]
    assert artifact["watch_evidence_plan"]["next_step"] == (
        "resolve_signal_watch_forbidden_effects"
    )
