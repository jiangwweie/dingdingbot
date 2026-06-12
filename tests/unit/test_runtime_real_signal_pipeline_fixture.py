from __future__ import annotations

import json

from scripts import runtime_real_signal_pipeline_fixture as script


def test_real_signal_pipeline_fixture_builds_end_to_end_report(tmp_path):
    report = script._build_report(_args(tmp_path))

    assert report["status"] == "ready_real_signal_pipeline_fixture"
    assert report["runtime_instance_id"] == "runtime-rtf026"
    assert report["pipeline_report"]["status"] == (
        "ready_for_real_signal_scoped_local_registration_proof"
    )
    assert report["pipeline_report"]["stage_statuses"] == {
        "intent_draft_source": "persisted_ready_intent_draft",
        "early_readiness_fact_collection": "ready_for_readiness_evidence_resolution",
        "readiness": "ready_for_executable_submit",
        "handoff": "ready_for_official_submit_call",
        "binding": "created_intent_and_authorization",
        "evidence_chain": "prepared_machine_evidence_blocked_before_local_order_adapter",
        "scoped_local_registration_proof": (
            "ready_for_scoped_local_registration_proof_dry_run"
        ),
    }
    assert report["safety_invariants"]["uses_fake_api_client"] is True
    assert report["safety_invariants"]["does_not_call_server"] is True
    assert report["safety_invariants"]["does_not_call_exchange"] is True
    assert report["safety_invariants"]["pipeline_exchange_write_called"] is False
    assert report["safety_invariants"]["pipeline_local_registration_attempted"] is False
    assert report["api_call_count"] == 6
    assert any("strategy-signal-intent-draft-sources" in path for path in report["api_paths"])
    assert any("persisted-draft-source-readiness-previews" in path for path in report["api_paths"])
    assert not any("runtime-execution-exchange-submit" in path for path in report["api_paths"])


def test_real_signal_pipeline_fixture_writes_artifacts_and_output(tmp_path):
    output = tmp_path / "fixture-report.json"

    report = script._build_report(_args(tmp_path, output=str(output)))

    assert output.exists()
    written_report = json.loads(output.read_text(encoding="utf-8"))
    assert written_report["status"] == "ready_real_signal_pipeline_fixture"
    artifact_root = tmp_path / "artifacts"
    assert (artifact_root / "fixture-inputs" / "00-signal-input.json").exists()
    assert (
        artifact_root
        / "pipeline"
        / "02-collected-readiness-evidence.json"
    ).exists()
    assert (
        artifact_root
        / "pipeline"
        / "07-scoped-local-registration-proof.json"
    ).exists()
    assert "evidence_chain:preview_disabled_first_real_submit_action_http_404" in (
        report["blockers"]
    )


def _args(tmp_path, **overrides):
    values = {
        "runtime_instance_id": "runtime-rtf026",
        "runtime_grant_authorization_id": "grant-rtf026",
        "api_base": "http://fixture",
        "artifact_dir": str(tmp_path / "artifacts"),
        "output": None,
    }
    values.update(overrides)
    return type("Args", (), values)()
