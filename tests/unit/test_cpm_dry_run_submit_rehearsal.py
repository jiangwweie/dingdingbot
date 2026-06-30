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
