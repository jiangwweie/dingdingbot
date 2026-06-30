from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_runtime_coverage_review_evidence.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_runtime_coverage_review_evidence",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _operator_evidence(
    *,
    status: str = "observation_running_no_signal",
    stop_reason: str = "running",
    ready_count: int = 0,
    would_enter_count: int = 0,
    forbidden: bool = False,
) -> dict:
    return {
        "scope": "runtime_observation_operator_evidence",
        "status": status,
        "active_runtime_observation": {
            "active_runtime_count": 2,
            "latest_iteration": 20,
            "iterations_completed": 20,
            "iterations_remaining": 57,
            "stop_reason": stop_reason,
        },
        "signal_counts": {
            "runtime_ready_signal_count": ready_count,
            "strategy_group_would_enter_signal_count": would_enter_count,
            "strategy_group_no_action_signal_count": 8,
        },
        "coverage": {
            "active_runtime_strategy_families": ["BTPC-001", "CPM-001"],
            "strategy_group_preview_families": [
                "BRF-001",
                "BTPC-001",
                "CPM-001",
                "LSR-001",
                "RBR-001",
            ],
            "active_runtime_symbols": ["AVAX/USDT:USDT", "BNB/USDT:USDT"],
            "strategy_group_preview_symbols": [
                "ADA/USDT:USDT",
                "AVAX/USDT:USDT",
                "BNB/USDT:USDT",
                "BTC/USDT:USDT",
                "XRP/USDT:USDT",
            ],
            "active_runtime_count_less_than_preview_family_count": True,
        },
        "no_action_diagnostics": {
            "dominant_runtime_reasons": [
                {"reason_code": "btpc_no_action_no_bear_pullback_continuation", "count": 1}
            ],
            "dominant_strategy_group_reasons": [
                {"reason_code": "brf_no_action_no_rejection_close", "count": 1}
            ],
            "runtime_reason_counts": {
                "btpc_no_action_no_bear_pullback_continuation": 1
            },
            "strategy_group_reason_counts": {
                "brf_no_action_no_rejection_close": 1
            },
        },
        "operator_review_plan": {
            "not_execution_authority": True,
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
            "places_order": forbidden,
            "calls_order_lifecycle": False,
            "withdrawal_or_transfer_requested": False,
        },
        "safety_invariants": {
            "operator_evidence_only": True,
            "forbidden_effects": ["order_created"] if forbidden else [],
            "shadow_candidate_created": False,
            "execution_intent_created": False,
            "order_created": forbidden,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def test_coverage_review_surfaces_running_narrow_coverage_without_execution():
    module = _load_module()

    artifact = module.build_coverage_review_evidence(_operator_evidence())

    assert artifact["status"] == "coverage_review_observation_running"
    assert artifact["summary"]["coverage_ratio"] == "2/5"
    assert artifact["coverage"]["uncovered_preview_families"] == [
        "BRF-001",
        "LSR-001",
        "RBR-001",
    ]
    assert "operator_command_plan" not in artifact
    assert artifact["review_plan"]["not_execution_authority"] is True
    assert artifact["owner_gate"]["coverage_review_only"] is True
    assert artifact["safety_invariants"]["coverage_evidence_only"] is True
    assert artifact["safety_invariants"]["runtime_started"] is False
    assert artifact["safety_invariants"]["strategy_parameters_changed"] is False
    assert artifact["safety_invariants"]["order_created"] is False
    assert artifact["safety_invariants"]["source_operator_evidence_read_only"] is True
    assert "operator_evidence_only" not in artifact["safety_invariants"]
    assert "coverage_packet_only" not in artifact["safety_invariants"]
    assert "source_packet_read_only" not in artifact["safety_invariants"]


def test_coverage_review_after_window_requests_owner_review_not_runtime_start():
    module = _load_module()

    artifact = module.build_coverage_review_evidence(
        _operator_evidence(stop_reason="max_iterations_reached")
    )

    assert artifact["status"] == "coverage_review_needed_after_no_signal_window"
    assert artifact["review_plan"]["allowed_review_checkpoints"] == [
        "review_active_runtime_coverage",
        "review_no_action_reason_codes",
        "decide_future_runtime_profile_changes_with_owner",
    ]
    assert "new runtime activation" in artifact["owner_gate"]["does_not_authorize"]


def test_coverage_review_defers_to_ready_signal():
    module = _load_module()

    artifact = module.build_coverage_review_evidence(
        _operator_evidence(status="runtime_signal_attention", ready_count=1)
    )

    assert artifact["status"] == "runtime_signal_ready_not_coverage_review"
    assert artifact["review_plan"]["allowed_review_checkpoints"] == [
        "review_runtime_ready_signal_prepare_path"
    ]
    assert artifact["safety_invariants"]["shadow_candidate_created"] is False


def test_coverage_review_blocks_forbidden_source_effect():
    module = _load_module()

    artifact = module.build_coverage_review_evidence(_operator_evidence(forbidden=True))

    assert artifact["status"] == "blocked_forbidden_effect"
    assert artifact["review_plan"]["allowed_review_checkpoints"] == []
    assert "order_created" in artifact["safety_invariants"]["source_forbidden_effects"]
    assert "operator_review_plan.places_order" in artifact["safety_invariants"][
        "source_forbidden_effects"
    ]


def test_coverage_review_cli_reads_and_writes_json(tmp_path, capsys):
    module = _load_module()
    input_path = tmp_path / "operator.json"
    output_path = tmp_path / "coverage.json"
    input_path.write_text(json.dumps(_operator_evidence()), encoding="utf-8")

    exit_code = module.main(
        [
            "--operator-evidence-json",
            str(input_path),
            "--output-json",
            str(output_path),
        ]
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_payload == file_payload
    assert file_payload["scope"] == "runtime_coverage_review_evidence"
