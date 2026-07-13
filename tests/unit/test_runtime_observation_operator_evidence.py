from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_runtime_observation_operator_evidence.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_runtime_observation_operator_evidence",
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
    signal_event_ids=None,
):
    return {
        "status": status,
        "latest_status": status,
        "latest_iteration": 2,
        "iterations_completed": 2,
        "iterations_requested": 87,
        "iterations_remaining": 85,
        "artifact_stale": False,
        "stop_reason": "running",
        "active_runtime_count": 1,
        "ticket_id": None,
        "action_time_lane_input_id": None,
        "promotion_candidate_id": None,
        "signal_event_id": None,
        "pg_live_signal_events": {
            "status": (
                "pg_live_signal_events_written"
                if signal_event_ids
                else "pg_live_signal_events_blocked"
            ),
            "written_count": len(signal_event_ids or []),
            "signal_event_ids": list(signal_event_ids or []),
        },
        "runtime_signal_summaries": [
            {
                "runtime_instance_id": "runtime-1",
                "strategy_family_id": "BTPC-001",
                "strategy_family_version_id": "BTPC-001-v0",
                "symbol": "AVAX/USDT:USDT",
                "side": "short",
                "status": status,
                "evaluation_status": "observe_only",
                "signal_type": signal_type,
                "signal_side": "none",
                "confidence": "0.25",
                "reason_codes": ["btpc_no_action_no_bear_pullback_continuation"],
                "human_summary": "No BTPC action.",
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
                "candidate_id": "BTPC-001-AVAX-SHORT",
                "strategy_group_id": "BTPC-001",
                "strategy_family_version_id": "BTPC-001-v0",
                "symbol": "AVAX/USDT:USDT",
                "side": "none",
                "signal_type": "no_action",
                "confidence": "0.25",
                "reason_codes": ["btpc_no_action_no_bear_pullback_continuation"],
                "human_summary": "No BTPC action.",
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


def test_operator_evidence_summarizes_no_signal_without_execution():
    module = _load_module()

    evidence = module.build_operator_evidence(
        active_status_artifact=_status_artifact(),
        strategy_preview_artifact=_strategy_preview(),
    )

    assert evidence["status"] == "observation_running_no_signal"
    assert evidence["watch_status"] == "watching_no_signal"
    assert evidence["diagnostic_status"] == "no_signal_observation_running"
    assert evidence["signal_counts"]["runtime_ready_signal_count"] == 0
    assert "operator_command_plan" not in evidence
    assert evidence["operator_review_plan"]["not_execution_authority"] is True
    assert evidence["operator_review_plan"]["allowed_review_checkpoints"] == [
        "continue_active_runtime_observation"
    ]
    assert evidence["safety_invariants"]["execution_intent_created"] is False
    assert evidence["safety_invariants"]["order_created"] is False
    assert evidence["owner_gate"]["operator_review_only"] is True
    assert evidence["safety_invariants"]["operator_evidence_only"] is True
    assert "operator_packet_only" not in evidence["safety_invariants"]


def test_operator_evidence_classifies_anonymous_runtime_ready_as_identity_gap():
    module = _load_module()

    evidence = module.build_operator_evidence(
        active_status_artifact=_status_artifact(
            status="ready_for_action_time_ticket_materialization",
            signal_type="would_enter",
        ),
        strategy_preview_artifact=_strategy_preview(),
    )

    assert evidence["status"] == "runtime_signal_identity_gap"
    assert evidence["watch_status"] == "runtime_signal_identity_gap"
    assert evidence["operator_review_plan"]["next_step"] == (
        "repair_pg_live_signal_identity_handoff"
    )
    assert evidence["safety_invariants"]["order_created"] is False


def test_operator_evidence_surfaces_named_pg_runtime_ready_attention():
    module = _load_module()

    evidence = module.build_operator_evidence(
        active_status_artifact=_status_artifact(
            status="ready_for_action_time_ticket_materialization",
            signal_type="would_enter",
            signal_event_ids=["signal:unit-btpc-avax"],
        ),
        strategy_preview_artifact=_strategy_preview(),
    )

    assert evidence["status"] == "runtime_signal_attention"
    assert evidence["watch_status"] == "runtime_signal_ready"
    assert evidence["runtime_action_time_context"]["signal_event_ids"] == [
        "signal:unit-btpc-avax"
    ]


def test_operator_evidence_blocks_forbidden_preview_effect():
    module = _load_module()

    evidence = module.build_operator_evidence(
        active_status_artifact=_status_artifact(),
        strategy_preview_artifact=_strategy_preview(forbidden=True),
    )

    assert evidence["status"] == "blocked_forbidden_effect"
    assert (
        "watch_evidence.checks.strategy_preview_artifact.order_created"
        in evidence["safety_invariants"]["forbidden_effects"]
    )
    assert "packet_0.packet_1.order_created" not in evidence["safety_invariants"][
        "forbidden_effects"
    ]
    assert evidence["safety_invariants"]["order_lifecycle_called"] is False
