from __future__ import annotations

import json

from scripts import build_p0_fresh_signal_cutover_hardening_packet as script


def test_p0_fresh_signal_cutover_hardening_packet_covers_steps_1_to_7() -> None:
    packet = script.build_p0_fresh_signal_cutover_hardening_packet(
        generated_at_ms=1,
        state_authority_commit="state-commit",
        fresh_cutover_commit="fresh-commit",
    )

    assert packet["status"] == "p0_fresh_signal_cutover_hardening_ready"
    assert packet["checks"]["ready"] is True
    assert packet["checks"]["blockers"] == []
    assert set(packet["sections"]) == {
        "state_authority_versioning",
        "fresh_signal_cutover_fixtures",
        "action_time_required_facts",
        "candidate_authorization_finalgate",
        "duplicate_and_conflict_guards",
        "protection_failure_recovery",
        "post_event_review_capture",
    }
    assert packet["sections"]["state_authority_versioning"]["status"] == (
        "ready_versioned_baseline"
    )
    assert packet["checks"]["waiting_to_processing_projection_ready"] is True
    assert packet["checks"]["required_facts_contract_ready"] is True
    assert packet["checks"]["candidate_authorization_finalgate_contract_ready"] is True
    assert packet["checks"]["duplicate_submit_guard_ready"] is True
    assert packet["checks"]["protection_failure_recovery_ready"] is True
    assert packet["checks"]["post_event_review_capture_ready"] is True


def test_fresh_signal_fixture_matrix_preserves_processing_and_fail_closed_paths() -> None:
    packet = script.build_p0_fresh_signal_cutover_hardening_packet(
        generated_at_ms=1,
        state_authority_commit="state-commit",
        fresh_cutover_commit="fresh-commit",
    )
    cases = {
        case["case_id"]: case
        for case in packet["sections"]["fresh_signal_cutover_fixtures"]["cases"]
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
    assert packet["sections"]["fresh_signal_cutover_fixtures"]["waiting_projection"] == {
        "runtime_status": "waiting_for_market",
        "owner_status": "waiting_for_opportunity",
        "notification": "DONT_NOTIFY",
    }


def test_action_time_required_facts_contract_has_minimal_submit_surface() -> None:
    packet = script.build_p0_fresh_signal_cutover_hardening_packet(
        generated_at_ms=1,
        state_authority_commit="state-commit",
        fresh_cutover_commit="fresh-commit",
    )
    facts = {
        fact["fact_key"]: fact
        for fact in packet["sections"]["action_time_required_facts"]["facts"]
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
    assert packet["sections"]["action_time_required_facts"][
        "live_submit_ready_rule"
    ] == "false until action-time FinalGate and official Operation Layer pass"


def test_candidate_finalgate_duplicate_protection_and_review_are_non_authority() -> None:
    packet = script.build_p0_fresh_signal_cutover_hardening_packet(
        generated_at_ms=1,
        state_authority_commit="state-commit",
        fresh_cutover_commit="fresh-commit",
    )
    finalgate = packet["sections"]["candidate_authorization_finalgate"]
    duplicate = packet["sections"]["duplicate_and_conflict_guards"]
    protection = packet["sections"]["protection_failure_recovery"]
    review = packet["sections"]["post_event_review_capture"]

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
    assert review["strategygroup_decision_adapter_shape"][
        "adapter_is_recommendation_only"
    ] is True


def test_hardening_packet_never_grants_live_authority() -> None:
    packet = script.build_p0_fresh_signal_cutover_hardening_packet(
        generated_at_ms=1,
        state_authority_commit="state-commit",
        fresh_cutover_commit="fresh-commit",
    )

    assert packet["safety_invariants"]["live_submit_ready"] is False
    assert packet["safety_invariants"]["actionable_now"] is False
    assert packet["safety_invariants"]["real_order_authority"] is False
    assert packet["interaction"] == {
        "level": "L0_local_hardening_packet",
        "remote_interaction_count": 0,
        "mutates_remote_files": False,
        "approaches_real_order": False,
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "calls_exchange_write": False,
        "places_order": False,
    }


def test_hardening_packet_blocks_missing_version_commits(monkeypatch) -> None:
    monkeypatch.setattr(script, "_commit_for_subject", lambda subject: None)

    packet = script.build_p0_fresh_signal_cutover_hardening_packet(
        generated_at_ms=1,
        state_authority_commit=None,
        fresh_cutover_commit=None,
    )

    assert packet["status"] == "p0_fresh_signal_cutover_hardening_blocked"
    assert "state_authority_versioning:state_authority_commit_missing" in packet[
        "checks"
    ]["blockers"]
    assert (
        "state_authority_versioning:fresh_signal_cutover_rehearsal_commit_missing"
        in packet["checks"]["blockers"]
    )


def test_hardening_packet_cli_writes_json_and_owner_progress(tmp_path, capsys) -> None:
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
