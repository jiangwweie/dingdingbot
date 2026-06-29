from __future__ import annotations

import json

from scripts import build_p0_fresh_signal_cutover_hardening_artifact as script


def test_p0_fresh_signal_cutover_hardening_artifact_covers_steps_1_to_7() -> None:
    artifact = script.build_p0_fresh_signal_cutover_hardening_artifact(
        generated_at_ms=1,
        state_authority_commit="state-commit",
        fresh_cutover_commit="fresh-commit",
    )

    assert artifact["status"] == "p0_fresh_signal_cutover_hardening_ready"
    assert artifact["checks"]["ready"] is True
    assert artifact["checks"]["blockers"] == []
    assert "sections" not in artifact
    assert set(artifact["evidence_groups"]) == {
        "state_authority_versioning",
        "fresh_signal_cutover_fixtures",
        "action_time_required_facts",
        "candidate_authorization_finalgate",
        "duplicate_and_conflict_guards",
        "protection_failure_recovery",
        "post_event_review_capture",
    }
    assert artifact["evidence_groups"]["state_authority_versioning"]["status"] == (
        "ready_versioned_baseline"
    )
    assert artifact["checks"]["waiting_to_processing_projection_ready"] is True
    assert artifact["checks"]["required_facts_contract_ready"] is True
    assert artifact["checks"]["candidate_authorization_finalgate_contract_ready"] is True
    assert artifact["checks"]["duplicate_submit_guard_ready"] is True
    assert artifact["checks"]["protection_failure_recovery_ready"] is True
    assert artifact["checks"]["post_event_review_capture_ready"] is True


def test_fresh_signal_fixture_matrix_preserves_processing_and_fail_closed_paths() -> None:
    artifact = script.build_p0_fresh_signal_cutover_hardening_artifact(
        generated_at_ms=1,
        state_authority_commit="state-commit",
        fresh_cutover_commit="fresh-commit",
    )
    cases = {
        case["case_id"]: case
        for case in artifact["evidence_groups"]["fresh_signal_cutover_fixtures"][
            "cases"
        ]
    }

    assert cases["fresh_selected_strategygroup_signal"]["expected_runtime_status"] == (
        "processing"
    )
    assert cases["fresh_selected_strategygroup_signal"]["expected_notification"] == (
        "NOTIFY"
    )
    assert cases["stale_signal"]["blocker_class"] == "missing_fact"
    assert cases["wrong_scope_signal"]["blocker_class"] == "hard_safety_stop"
    assert cases["missing_action_time_fact"]["blocker_class"] == "missing_fact"
    assert cases["active_position_or_open_order_conflict"]["blocker_class"] == (
        "active_position_resolution"
    )
    assert artifact["evidence_groups"]["fresh_signal_cutover_fixtures"][
        "waiting_projection"
    ] == {
        "runtime_status": "waiting_for_market",
        "owner_status": "waiting_for_opportunity",
        "notification": "DONT_NOTIFY",
    }


def test_action_time_required_facts_contract_has_minimal_submit_surface() -> None:
    artifact = script.build_p0_fresh_signal_cutover_hardening_artifact(
        generated_at_ms=1,
        state_authority_commit="state-commit",
        fresh_cutover_commit="fresh-commit",
    )
    facts = {
        fact["fact_key"]: fact
        for fact in artifact["evidence_groups"]["action_time_required_facts"]["facts"]
    }

    assert set(facts) == {
        "account_facts",
        "position_and_open_order_conflict",
        "allocated_budget",
        "protection_template",
        "exchange_rules",
        "signal_freshness",
    }
    assert facts["account_facts"]["states"] == ["ready", "stale", "missing"]
    assert facts["position_and_open_order_conflict"]["states"] == [
        "clear",
        "conflict",
    ]
    assert artifact["evidence_groups"]["action_time_required_facts"][
        "live_submit_ready_rule"
    ] == "false until action-time FinalGate and official Operation Layer pass"


def test_candidate_finalgate_duplicate_protection_and_review_are_non_authority() -> None:
    artifact = script.build_p0_fresh_signal_cutover_hardening_artifact(
        generated_at_ms=1,
        state_authority_commit="state-commit",
        fresh_cutover_commit="fresh-commit",
    )
    finalgate = artifact["evidence_groups"]["candidate_authorization_finalgate"]
    duplicate = artifact["evidence_groups"]["duplicate_and_conflict_guards"]
    protection = artifact["evidence_groups"]["protection_failure_recovery"]
    review = artifact["evidence_groups"]["post_event_review_capture"]

    assert finalgate["finalgate_dry_run_input"]["calls_finalgate"] is False
    assert finalgate["finalgate_dry_run_input"]["cannot_set_live_submit_ready"] is True
    assert finalgate["no_bypass_guard"] == {
        "finalgate_required": True,
        "operation_layer_required": True,
        "prepare_records_are_not_submit_authority": True,
    }
    assert {guard["guard"] for guard in duplicate["guards"]} == {
        "duplicate_submit",
        "open_order_conflict",
        "active_position_conflict",
    }
    assert protection["protection_failure_policy"][
        "missing_protection_blocks_new_entries"
    ] is True
    assert review["post_event_review_builder"]["negative_evidence_captured"] is True
    assert "candidate_authorization_required_fields" in finalgate
    assert "candidate_packet_required_fields" not in finalgate
    assert "finalgate_evidence_id" in review["review_ledger_fields"]
    assert "finalgate_packet_id" not in review["review_ledger_fields"]
    assert "live_closure_evidence_artifact" in review["post_event_review_builder"][
        "input_artifacts"
    ]
    assert "live_closure_evidence_packet" not in review["post_event_review_builder"][
        "input_artifacts"
    ]
    assert review["strategygroup_decision_adapter_shape"][
        "adapter_is_recommendation_only"
    ] is True


def test_hardening_artifact_never_grants_live_authority() -> None:
    artifact = script.build_p0_fresh_signal_cutover_hardening_artifact(
        generated_at_ms=1,
        state_authority_commit="state-commit",
        fresh_cutover_commit="fresh-commit",
    )

    assert artifact["safety_invariants"]["live_submit_ready"] is False
    assert (
        artifact["safety_invariants"]["p0_fresh_signal_hardening_projection_only"]
        is True
    )
    assert "packet_only" not in artifact["safety_invariants"]
    assert "actionable_now" not in artifact["safety_invariants"]
    assert "real_order_authority" not in artifact["safety_invariants"]
    assert artifact["interaction"] == {
        "level": "L0_local_hardening_artifact",
        "remote_interaction_count": 0,
        "mutates_remote_files": False,
        "approaches_real_order": False,
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "calls_exchange_write": False,
        "places_order": False,
    }


def test_hardening_owner_progress_reads_artifact_without_legacy_authority_terms() -> None:
    artifact = script.build_p0_fresh_signal_cutover_hardening_artifact(
        generated_at_ms=1,
        state_authority_commit="state-commit",
        fresh_cutover_commit="fresh-commit",
    )

    text = script._owner_progress_text(artifact)

    assert "- Status: p0_fresh_signal_cutover_hardening_ready" in text
    assert "- Runtime transition ready: yes" in text
    assert "- Calls FinalGate: no" in text
    assert "- Calls Operation Layer: no" in text
    assert "packet_only" not in text
    assert "actionable_now" not in text
    assert "real_order_authority" not in text


def test_hardening_artifact_blocks_missing_version_commits(monkeypatch) -> None:
    monkeypatch.setattr(script, "_commit_for_subject", lambda subject: None)

    artifact = script.build_p0_fresh_signal_cutover_hardening_artifact(
        generated_at_ms=1,
        state_authority_commit=None,
        fresh_cutover_commit=None,
    )

    assert artifact["status"] == "p0_fresh_signal_cutover_hardening_blocked"
    assert "state_authority_versioning:state_authority_commit_missing" in artifact[
        "checks"
    ]["blockers"]
    assert (
        "state_authority_versioning:fresh_signal_cutover_rehearsal_commit_missing"
        in artifact["checks"]["blockers"]
    )


def test_hardening_artifact_cli_writes_json_and_owner_progress(tmp_path, capsys) -> None:
    output_json = tmp_path / "hardening.json"
    output_md = tmp_path / "hardening.md"

    exit_code = script.main(
        [
            "--generated-at-ms",
            "1",
            "--state-authority-commit",
            "state-commit",
            "--fresh-cutover-commit",
            "fresh-commit",
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
            "--json",
        ]
    )

    assert exit_code == 0
    stdout = json.loads(capsys.readouterr().out)
    written = json.loads(output_json.read_text(encoding="utf-8"))
    assert stdout["status"] == "p0_fresh_signal_cutover_hardening_ready"
    assert written["status"] == "p0_fresh_signal_cutover_hardening_ready"
    assert "P0 Fresh Signal Cutover Hardening" in output_md.read_text(
        encoding="utf-8"
    )
