from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.build_strategygroup_pre_live_rehearsal_readiness import (
    build_pre_live_rehearsal_readiness,
    validate_artifact,
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
    artifact = _minimal_packet("quality_wave_ready")
    rows = [
        {"strategy_group_id": "BTPC-001", "current_tier": "L2", "current_decision": "revise"},
        {"strategy_group_id": "VCB-001", "current_tier": "L1", "current_decision": "keep_observing"},
        {"strategy_group_id": "LSR-001", "current_tier": "L1", "current_decision": "keep_observing"},
        {"strategy_group_id": "BRF-001", "current_tier": "L1", "current_decision": "keep_observing"},
        {"strategy_group_id": "RBR-001", "current_tier": "L1", "current_decision": "park"},
    ]
    artifact["rows"] = rows
    artifact["strategy_asset_state_provenance"] = {
        "source_role": "quality_evidence_provenance",
        "primary_judgment_source": False,
        "primary_judgment_source_name": "strategy_asset_state",
        "rows": rows,
    }
    return artifact


def _readiness_packet() -> dict:
    return build_pre_live_rehearsal_readiness(
        quality_wave=_quality_wave(),
        handoff_boundary=_minimal_packet("handoff_boundary_closure_ready"),
        btpc_guard=_minimal_packet("btpc_fact_classifier_guard_ready"),
        lifecycle_rehearsal=_minimal_packet("lifecycle_rehearsal_ready"),
    )


def test_pre_live_readiness_separates_rehearsal_from_live_submit() -> None:
    artifact = _readiness_packet()

    assert artifact["status"] == "pre_live_rehearsal_ready"
    assert "decision" not in artifact
    assert validate_artifact(artifact) == []
    readiness = artifact["runtime_readiness_state"]
    assert readiness["state_family"] == "Runtime Readiness State"
    assert readiness["source_role"] == "pre_live_rehearsal_readiness_evidence"
    assert readiness["primary_judgment_source"] is False
    assert readiness["tradeability_decision_source"] is False
    assert readiness["execution_attempt_source"] is False
    assert readiness["pre_live_rehearsal_ready"] is True
    assert readiness["live_submit_ready"] is False
    assert readiness["live_outcome_calibrated"] is False
    assert "actionable_now" not in readiness
    assert "real_order_authority" not in readiness
    assert "actionable_now" not in artifact["safety_invariants"]
    assert "real_order_authority" not in artifact["safety_invariants"]
    assert artifact["remaining_live_submit_dependencies"]
    assert artifact["remaining_live_outcome_calibration_dependencies"]


def test_pre_live_readiness_consumes_quality_wave_as_provenance() -> None:
    artifact = _readiness_packet()

    impacts = artifact["strategygroup_decision_impact"]
    assert len(impacts) == 5
    assert {row["source_role"] for row in impacts} == {
        "quality_evidence_provenance"
    }
    assert all(row["primary_judgment_source"] is False for row in impacts)
    assert all("actionable_now" not in row for row in impacts)
    assert all("real_order_authority" not in row for row in impacts)


def test_pre_live_readiness_rejects_quality_wave_without_strategy_asset_provenance() -> None:
    quality_wave = _quality_wave()
    quality_wave.pop("strategy_asset_state_provenance")

    artifact = build_pre_live_rehearsal_readiness(
        quality_wave=quality_wave,
        handoff_boundary=_minimal_packet("handoff_boundary_closure_ready"),
        btpc_guard=_minimal_packet("btpc_fact_classifier_guard_ready"),
        lifecycle_rehearsal=_minimal_packet("lifecycle_rehearsal_ready"),
    )

    assert artifact["status"] == "pre_live_rehearsal_not_ready"
    assert "quality_wave.strategy_asset_state_provenance_missing" in artifact[
        "validation_errors"
    ]
    assert "quality_wave.strategy_asset_state_provenance_rows_missing" in artifact[
        "validation_errors"
    ]
    assert artifact["strategygroup_decision_impact"] == []


def test_negative_missing_lifecycle_readiness_is_not_ready() -> None:
    artifact = build_pre_live_rehearsal_readiness(
        quality_wave=_quality_wave(),
        handoff_boundary=_minimal_packet("handoff_boundary_closure_ready"),
        btpc_guard=_minimal_packet("btpc_fact_classifier_guard_ready"),
        lifecycle_rehearsal=_minimal_packet("wrong_status"),
    )

    assert artifact["status"] == "pre_live_rehearsal_not_ready"
    assert "lifecycle_rehearsal.unexpected_status:wrong_status" in artifact["validation_errors"]


def test_negative_input_legacy_actionability_mirror_is_not_current_effect() -> None:
    quality_wave = _quality_wave()
    quality_wave["safety_invariants"]["actionable_now"] = True

    artifact = build_pre_live_rehearsal_readiness(
        quality_wave=quality_wave,
        handoff_boundary=_minimal_packet("handoff_boundary_closure_ready"),
        btpc_guard=_minimal_packet("btpc_fact_classifier_guard_ready"),
        lifecycle_rehearsal=_minimal_packet("lifecycle_rehearsal_ready"),
    )

    assert (
        "quality_wave.safety_invariants.legacy_authority_mirror_present:"
        "actionable_now"
    ) in artifact["validation_errors"]
    assert "quality_wave.safety_invariants.actionable_now" not in artifact[
        "validation_errors"
    ]


def test_negative_live_authority_is_rejected() -> None:
    artifact = _readiness_packet()
    artifact["runtime_readiness_state"]["real_order_authority"] = True

    errors = validate_artifact(artifact)

    assert (
        "runtime_readiness_state.legacy_authority_mirror_present:real_order_authority"
        in errors
    )


def test_negative_legacy_actionability_mirrors_are_rejected() -> None:
    artifact = _readiness_packet()
    artifact["runtime_readiness_state"]["actionable_now"] = False
    artifact["runtime_readiness_state"]["real_order_authority"] = False
    artifact["safety_invariants"]["actionable_now"] = False
    artifact["safety_invariants"]["real_order_authority"] = False

    errors = validate_artifact(artifact)

    assert (
        "runtime_readiness_state.legacy_authority_mirror_present:actionable_now"
        in errors
    )
    assert (
        "runtime_readiness_state.legacy_authority_mirror_present:real_order_authority"
        in errors
    )
    assert "safety_invariant.legacy_authority_mirror_present:actionable_now" in errors
    assert (
        "safety_invariant.legacy_authority_mirror_present:real_order_authority"
        in errors
    )


def test_negative_top_level_decision_is_rejected() -> None:
    artifact = _readiness_packet()
    artifact["decision"] = {
        "default_next_step": "legacy_parallel_readiness_judgment_source",
    }

    errors = validate_artifact(artifact)

    assert "top_level_decision_removed" in errors


def test_negative_runtime_readiness_cannot_answer_tradeability() -> None:
    artifact = _readiness_packet()
    artifact["runtime_readiness_state"]["tradeability_decision_source"] = True

    errors = validate_artifact(artifact)

    assert "runtime_readiness_state_must_not_answer_tradeability" in errors


def test_negative_runtime_readiness_cannot_open_execution_attempt() -> None:
    artifact = _readiness_packet()
    artifact["runtime_readiness_state"]["execution_attempt_source"] = True

    errors = validate_artifact(artifact)

    assert "runtime_readiness_state_must_not_open_execution_attempt" in errors


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
