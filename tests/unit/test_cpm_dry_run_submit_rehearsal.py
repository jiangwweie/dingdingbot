from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_cpm_dry_run_submit_rehearsal.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_cpm_dry_run_submit_rehearsal",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _required_facts_mapping_ready() -> dict:
    return {
        "status": "cpm_required_facts_mapping_ready",
        "required_facts_mapping_ready": True,
    }


def _runtime_signal_capture(signal_state: str) -> dict:
    return {
        "status": "cpm_runtime_signal_capture_ready",
        "signal_detector_preview": {
            "current_signal_state": signal_state,
            "fresh_signal_present": signal_state == "fresh_signal_present",
        },
    }


def _shadow_candidate_evidence(*, ready: bool) -> dict:
    return {
        "status": (
            "cpm_shadow_candidate_evidence_ready"
            if ready
            else "cpm_shadow_candidate_evidence_waiting_for_fresh_signal"
        ),
        "shadow_candidate_evidence_ready": ready,
    }


def _synthetic_fresh_signal_fixture() -> dict:
    return {
        "status": "cpm_synthetic_fresh_signal_fixture_ready",
        "fixture_id": "cpm-long-synthetic-fresh-signal-v1",
        "source_signal": {
            "fresh_signal_present": True,
            "not_live_market_signal": True,
            "not_execution_authority": True,
        },
        "shadow_candidate_evidence": {
            "shadow_candidate_evidence_ready": True,
            "candidate_authorization_evidence_shape_ready": True,
        },
        "action_time_required_facts": {
            "declared": True,
            "fact_keys": [
                "active_position_or_open_order_clear",
                "action_time_available_balance",
            ],
        },
        "finalgate_dry_run": {"input_shape_complete": True, "passed": True},
        "operation_layer_paper": {"input_shape_complete": True, "passed": True},
        "execution_attempt_rehearsal": {"shape_ready": True},
        "review_outcome_shape": {"shape_ready": True},
        "authority_boundary": {
            "not_live_market_signal": True,
            "not_execution_authority": True,
        },
    }


def test_cpm_dry_run_shape_ready_does_not_claim_finalgate_without_fresh_signal():
    module = _load_module()

    artifact = module.build_cpm_dry_run_submit_rehearsal(
        required_facts_mapping=_required_facts_mapping_ready(),
        runtime_signal_capture=_runtime_signal_capture("fresh_signal_absent"),
        shadow_candidate_evidence=_shadow_candidate_evidence(ready=False),
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    assert artifact["status"] == "cpm_dry_run_submit_rehearsal_shape_ready"
    assert artifact["dry_run_submit_rehearsal"] == "shape_ready"
    assert artifact["armed_observation_ready"] is True
    assert artifact["submit_rehearsal_shape_ready"] is True
    assert artifact["fresh_signal_submit_rehearsal_passed"] is False
    checks = artifact["checks"]
    assert checks["fresh_signal_present"] is False
    assert checks["candidate_authorization_evidence_ready"] is False
    assert checks["finalgate_dry_run_passed"] is False
    assert checks["operation_layer_paper_passed"] is False
    assert checks["exchange_write"] is False
    assert checks["order_created"] is False


def test_cpm_synthetic_fresh_signal_rehearses_submit_shape_without_live_authority():
    module = _load_module()

    artifact = module.build_cpm_dry_run_submit_rehearsal(
        required_facts_mapping=_required_facts_mapping_ready(),
        runtime_signal_capture={
            "status": "cpm_runtime_signal_capture_ready",
            "signal_detector_preview": {
                "current_signal_state": "fresh_signal_absent",
                "fresh_signal_present": False,
                "action_time_pending_fact_keys": [
                    "active_position_or_open_order_clear",
                    "action_time_available_balance",
                ],
            },
        },
        shadow_candidate_evidence=_shadow_candidate_evidence(ready=False),
        synthetic_fresh_signal_fixture=_synthetic_fresh_signal_fixture(),
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    assert artifact["status"] == "cpm_dry_run_submit_rehearsal_shape_ready"
    assert artifact["fresh_signal_submit_rehearsal_passed"] is False
    checks = artifact["checks"]
    assert checks["finalgate_dry_run_passed"] is False
    assert checks["operation_layer_paper_passed"] is False
    assert checks["synthetic_fresh_signal_fixture_ready"] is True
    assert checks["synthetic_fresh_signal_present"] is True
    assert checks["synthetic_shadow_candidate_evidence_ready"] is True
    assert checks["synthetic_candidate_authorization_evidence_shape_ready"] is True
    assert checks["synthetic_action_time_required_facts_declared"] is True
    assert checks["synthetic_finalgate_dry_run_passed"] is True
    assert checks["synthetic_operation_layer_paper_passed"] is True
    assert checks["synthetic_execution_attempt_rehearsal_ready"] is True
    synthetic = artifact["synthetic_fresh_signal_rehearsal"]
    assert synthetic["fresh_signal_submit_rehearsal_passed"] is True
    assert synthetic["not_live_market_signal"] is True
    assert synthetic["not_execution_authority"] is True
    assert synthetic["calls_finalgate"] is False
    assert synthetic["calls_operation_layer"] is False
    assert synthetic["exchange_write"] is False
    assert synthetic["order_created"] is False
    assert "real_order_authority" not in checks
    assert "real_order_authority" not in artifact["safety_invariants"]


def test_cpm_dry_run_passes_only_with_fresh_signal_and_shadow_evidence_ready():
    module = _load_module()

    artifact = module.build_cpm_dry_run_submit_rehearsal(
        required_facts_mapping=_required_facts_mapping_ready(),
        runtime_signal_capture=_runtime_signal_capture("fresh_signal_present"),
        shadow_candidate_evidence=_shadow_candidate_evidence(ready=True),
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    assert artifact["status"] == "cpm_dry_run_submit_rehearsal_passed"
    assert artifact["dry_run_submit_rehearsal"] == "fresh_signal_passed"
    assert artifact["submit_rehearsal_shape_ready"] is True
    assert artifact["fresh_signal_submit_rehearsal_passed"] is True
    checks = artifact["checks"]
    assert checks["candidate_authorization_evidence_ready"] is True
    assert checks["finalgate_dry_run_passed"] is True
    assert checks["operation_layer_paper_passed"] is True
    assert checks["exchange_write"] is False
    assert checks["order_created"] is False
