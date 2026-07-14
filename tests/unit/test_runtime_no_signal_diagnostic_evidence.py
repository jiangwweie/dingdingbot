from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_runtime_no_signal_diagnostic_evidence.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_runtime_no_signal_diagnostic_evidence",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _watch_evidence(*, status="watching_no_signal", forbidden=False, ready=False):
    return {
        "status": "runtime_signal_ready" if ready else status,
        "active_runtime_observation": {
            "active_runtime_count": 2,
            "latest_iteration": 3,
            "iterations_completed": 3,
            "iterations_remaining": 84,
            "iterations_requested": 87,
            "stop_reason": "running",
            "artifact_stale": False,
        },
        "checks": {
            "runtime_ready_signal_count": 1 if ready else 0,
            "strategy_group_would_enter_signal_count": 0,
            "strategy_group_no_action_signal_count": 2,
            "forbidden_effects": (
                ["strategy_preview_artifact.order_created"] if forbidden else []
            ),
        },
        "runtime_signals": [
            {
                "runtime_instance_id": "runtime-1",
                "strategy_family_id": "CPM-001",
                "symbol": "BNB/USDT:USDT",
                "reason_codes": ["cpm_no_action_no_reclaim"],
            },
            {
                "runtime_instance_id": "runtime-2",
                "strategy_family_id": "BTPC-001",
                "symbol": "AVAX/USDT:USDT",
                "reason_codes": ["btpc_no_action_no_bear_pullback_continuation"],
            },
        ],
        "runtime_ready_signals": [
            {
                "runtime_instance_id": "runtime-ready",
                "strategy_family_id": "BTPC-001",
                "symbol": "AVAX/USDT:USDT",
                "reason_codes": ["btpc_ready"],
            }
        ]
        if ready
        else [],
        "strategy_group_no_action_signals": [
            {
                "strategy_group_id": "CPM-001",
                "symbol": "BNB/USDT:USDT",
                "reason_codes": ["cpm_no_action_no_reclaim"],
            },
            {
                "strategy_group_id": "RBR-001",
                "symbol": "ADA/USDT:USDT",
                "reason_codes": ["rbr_no_action_not_at_range_boundary"],
            },
            {
                "strategy_group_id": "VCB-001",
                "symbol": "LINK/USDT:USDT",
                "reason_codes": ["vcb_no_action_no_compression_breakout"],
            },
        ],
        "strategy_group_would_enter_signals": [],
        "safety_invariants": {
            "read_artifacts_only": True,
            "shadow_candidate_created": False,
            "execution_intent_created": False,
            "order_created": forbidden,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "forbidden_effects": [],
        },
    }


def test_no_signal_diagnostic_summarizes_running_window():
    module = _load_module()

    artifact = module.build_no_signal_diagnostic_evidence(_watch_evidence())

    assert artifact["status"] == "no_signal_observation_running"
    assert artifact["signal_counts"]["runtime_ready_signal_count"] == 0
    assert artifact["coverage"]["active_runtime_strategy_families"] == [
        "BTPC-001",
        "CPM-001",
    ]
    assert artifact["coverage"]["active_runtime_count_less_than_preview_family_count"] is True
    assert artifact["no_action_diagnostics"]["runtime_reason_counts"] == {
        "btpc_no_action_no_bear_pullback_continuation": 1,
        "cpm_no_action_no_reclaim": 1,
    }
    assert "operator_command_plan" not in artifact
    assert artifact["review_plan"]["allowed_review_checkpoints"] == [
        "continue_active_runtime_observation"
    ]
    assert artifact["review_plan"]["not_execution_authority"] is True
    assert artifact["owner_gate"]["diagnostic_only"] is True
    assert artifact["right_tail_objective_context"]["no_signal_is_not_failure"] is True
    assert artifact["safety_invariants"]["diagnostic_evidence_only"] is True
    assert artifact["safety_invariants"]["order_created"] is False
    assert "read_packet_only" not in artifact["safety_invariants"]
    assert "source_watch_safety_flags" in artifact["safety_invariants"]
    assert "source_packet_safety_flags" not in artifact["safety_invariants"]


def test_no_signal_diagnostic_surfaces_ready_signal_as_not_no_signal():
    module = _load_module()

    artifact = module.build_no_signal_diagnostic_evidence(_watch_evidence(ready=True))

    assert artifact["status"] == "runtime_signal_ready_not_no_signal"
    assert artifact["review_plan"]["next_step"] == (
        "review_runtime_ready_signal_prepare_path"
    )
    assert artifact["safety_invariants"]["order_created"] is False


def test_no_signal_diagnostic_blocks_forbidden_source_packet():
    module = _load_module()

    artifact = module.build_no_signal_diagnostic_evidence(
        _watch_evidence(forbidden=True)
    )

    assert artifact["status"] == "blocked_forbidden_effect"
    assert "strategy_preview_artifact.order_created" in artifact["safety_invariants"][
        "source_forbidden_effects"
    ]
    assert "packet_0.order_created" not in artifact["safety_invariants"][
        "source_forbidden_effects"
    ]
    assert "safety.order_created" in artifact["safety_invariants"][
        "source_forbidden_effects"
    ]


def test_no_signal_diagnostic_unknown_watch_status_reviews_evidence_status():
    module = _load_module()

    artifact = module.build_no_signal_diagnostic_evidence(
        _watch_evidence(status="unexpected_watch_status")
    )

    assert artifact["status"] == "watch_evidence_needs_review"
    assert artifact["review_plan"]["next_step"] == "review_watch_evidence_status"
    assert artifact["review_plan"]["allowed_review_checkpoints"] == [
        "review_no_signal_diagnostic_evidence"
    ]
    assert artifact["review_plan"]["next_step"] != "review_watch_packet_status"
