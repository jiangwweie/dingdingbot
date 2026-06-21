from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.build_strategygroup_pre_live_rehearsal_readiness import (
    build_pre_live_rehearsal_readiness,
    validate_packet,
)


def _minimal_packet(status: str) -> dict:
    return {
        "status": status,
        "interaction": {
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "safety_invariants": {
            "actionable_now": False,
            "real_order_authority": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "exchange_write_called": False,
            "order_created": False,
            "live_profile_changed": False,
            "order_sizing_defaults_changed": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _quality_wave() -> dict:
    packet = _minimal_packet("quality_wave_ready")
    packet["rows"] = [
        {"strategy_group_id": "BTPC-001", "current_tier": "L2", "current_decision": "revise"},
        {"strategy_group_id": "VCB-001", "current_tier": "L1", "current_decision": "keep_observing"},
        {"strategy_group_id": "LSR-001", "current_tier": "L1", "current_decision": "keep_observing"},
        {"strategy_group_id": "BRF-001", "current_tier": "L1", "current_decision": "keep_observing"},
        {"strategy_group_id": "RBR-001", "current_tier": "L1", "current_decision": "park"},
    ]
    return packet


def _readiness_packet() -> dict:
    return build_pre_live_rehearsal_readiness(
        quality_wave=_quality_wave(),
        handoff_boundary=_minimal_packet("handoff_boundary_closure_ready"),
        btpc_guard=_minimal_packet("btpc_fact_classifier_guard_ready"),
        lifecycle_rehearsal=_minimal_packet("lifecycle_rehearsal_ready"),
    )


def test_pre_live_readiness_separates_rehearsal_from_live_submit() -> None:
    packet = _readiness_packet()

    assert packet["status"] == "pre_live_rehearsal_ready"
    assert validate_packet(packet) == []
    assert packet["decision"]["pre_live_rehearsal_ready"] is True
    assert packet["decision"]["live_submit_ready"] is False
    assert packet["decision"]["live_outcome_calibrated"] is False
    assert packet["decision"]["real_order_authority"] is False
    assert packet["remaining_live_submit_dependencies"]
    assert packet["remaining_live_outcome_calibration_dependencies"]


def test_negative_missing_lifecycle_readiness_is_not_ready() -> None:
    packet = build_pre_live_rehearsal_readiness(
        quality_wave=_quality_wave(),
        handoff_boundary=_minimal_packet("handoff_boundary_closure_ready"),
        btpc_guard=_minimal_packet("btpc_fact_classifier_guard_ready"),
        lifecycle_rehearsal=_minimal_packet("wrong_status"),
    )

    assert packet["status"] == "pre_live_rehearsal_not_ready"
    assert "lifecycle_rehearsal.unexpected_status:wrong_status" in packet["validation_errors"]


def test_negative_live_authority_is_rejected() -> None:
    packet = _readiness_packet()
    packet["decision"]["real_order_authority"] = True

    errors = validate_packet(packet)

    assert "decision_not_false:real_order_authority" in errors


def test_check_mode_passes_after_real_readiness_generation() -> None:
    required = [
        Path("docs/current/strategy-group-handoffs/strategygroup-quality-wave-current.json"),
        Path("docs/current/strategy-group-handoffs/strategygroup-handoff-boundary-closure-current.json"),
        Path("docs/current/strategy-group-handoffs/strategygroup-btpc-fact-classifier-guard-current.json"),
        Path("docs/current/strategy-group-handoffs/strategygroup-lifecycle-rehearsal-current.json"),
    ]
    if not all(path.exists() for path in required):
        return
    result = subprocess.run(
        [sys.executable, "scripts/build_strategygroup_pre_live_rehearsal_readiness.py"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    check = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_pre_live_rehearsal_readiness.py",
            "--check",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert check.returncode == 0, check.stdout + check.stderr
    assert json.loads(check.stdout)["status"] == "passed"
