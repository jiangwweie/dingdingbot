from __future__ import annotations

import json

from scripts import runtime_readiness_evidence_source_map as script


def test_source_map_marks_missing_fields_before_readiness(tmp_path):
    report = script._build_report(_args(tmp_path))

    assert report["status"] == "readiness_evidence_source_map_ready"
    assert report["summary"]["missing_before_readiness"] > 0
    assert "final_gate_preview_id_missing_before_readiness" in report["blockers"]
    assert "trusted_submit_fact_snapshot_id_missing_before_readiness" in (
        report["blockers"]
    )
    assert report["safety_invariants"]["does_not_call_exchange"] is True


def test_source_map_distinguishes_late_machine_evidence_from_early_input(tmp_path):
    evidence_chain = tmp_path / "evidence-chain.json"
    evidence_chain.write_text(
        json.dumps(
            {
                "ids": {
                    "trusted_submit_fact_snapshot_id": "facts-late",
                    "submit_idempotency_policy_id": "idem-late",
                    "protection_creation_failure_policy_id": "protect-late",
                }
            }
        ),
        encoding="utf-8",
    )

    report = script._build_report(
        _args(tmp_path, evidence_chain_json=str(evidence_chain))
    )

    rows = {row["field"]: row for row in report["rows"]}
    assert rows["trusted_submit_fact_snapshot_id"]["coverage_status"] == (
        "available_only_after_binding"
    )
    assert rows["submit_idempotency_policy_id"]["evidence_id"] == "idem-late"
    assert (
        "trusted_submit_fact_snapshot_id_is_late_machine_evidence_not_early_input"
        in report["warnings"]
    )
    assert report["summary"]["available_only_after_binding"] == 3


def test_source_map_marks_resolver_evidence_as_provided(tmp_path):
    resolver = tmp_path / "resolver.json"
    resolver.write_text(
        json.dumps(
            {
                "evidence": {
                    "final_gate_preview_id": "fg-ready",
                    "final_gate_passed": True,
                    "runtime_grant_authorization_id": "grant-ready",
                    "trusted_submit_fact_snapshot_id": "facts-ready",
                    "duplicate_submit_guard_ready": True,
                }
            }
        ),
        encoding="utf-8",
    )

    report = script._build_report(_args(tmp_path, resolver_report_json=str(resolver)))

    rows = {row["field"]: row for row in report["rows"]}
    assert rows["final_gate_preview_id"]["coverage_status"] == (
        "provided_by_readiness_evidence"
    )
    assert rows["final_gate_passed"]["coverage_status"] == (
        "provided_by_readiness_evidence"
    )
    assert rows["duplicate_submit_guard_ready"]["coverage_status"] == (
        "provided_by_readiness_evidence"
    )
    assert "final_gate_preview_id_missing_before_readiness" not in report["blockers"]


def _args(tmp_path, **overrides):
    values = {
        "runtime_instance_id": "runtime-rtf023",
        "resolver_report_json": None,
        "evidence_chain_json": None,
        "output": None,
    }
    values.update(overrides)
    return type("Args", (), values)()
