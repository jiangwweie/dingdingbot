from __future__ import annotations

import json

from scripts import runtime_controlled_tiny_live_readiness_to_local_cycle_proof as script


def _readiness_report(**overrides) -> dict:
    report = {
        "scope": "runtime_controlled_tiny_live_readiness_to_preflight_proof",
        "status": "controlled_tiny_live_readiness_to_official_preflight_passed",
        "runtime_instance_id": "runtime-rtf075-cpm-long",
        "signal_evaluation_id": "eval-rtf075-cpm-long",
        "order_candidate_id": "order-candidate-rtf075-contract",
        "authorization_id": "runtime-submit-authorization-intent_rt_test",
        "controlled_submit_preflight_id": "runtime-controlled-submit-preflight-test",
        "readiness_to_official_preflight_artifact": {
            "waiting_path": {
                "projection_status": "controlled_tiny_live_readiness_projection_waiting_for_ready_selector",
                "execute_tiny_live_attempt_now": False,
            },
            "ready_path": {
                "projection_status": "controlled_tiny_live_readiness_projection_ready_for_official_prepare",
            },
            "official_preflight": {
                "status": "official_flat_next_attempt_end_to_end_passed",
                "controlled_submit_preflight": {
                    "status": "ready_for_controlled_submit_adapter",
                },
            },
        },
        "checks": {
            "waiting_projection_blocks_official_route": True,
            "ready_projection_enters_official_prepare": True,
            "readiness_projection_uses_legacy_pre_attempt_as_primary_gate": False,
            "official_preflight_passed": True,
            "right_tail_runner_preserved": True,
            "uses_fake_console_api": False,
        },
        "safety_invariants": {
            "readiness_projection_no_forbidden_live_side_effects": True,
        },
    }
    report.update(overrides)
    return report


def _cycle_report(**overrides) -> dict:
    report = {
        "scope": "runtime_official_fresh_candidate_runtime_cycle_handoff_proof",
        "status": "official_fresh_candidate_runtime_cycle_handoff_passed",
        "runtime_instance_id": "runtime-rtf075-cpm-long",
        "signal_evaluation_id": "eval-rtf075-cpm-long",
        "order_candidate_id": "order-candidate-rtf075-contract",
        "preflight_authorization_id": "runtime-submit-authorization-pre",
        "post_submit_authorization_id": "runtime-submit-authorization-post",
        "exchange_submit_execution_result_id": (
            "runtime-exchange-submit-execution-result-test"
        ),
        "submit_outcome_review_id": "runtime-submit-outcome-review-test",
        "post_submit_budget_settlement_id": (
            "runtime-post-submit-budget-settlement-test"
        ),
        "fresh_candidate_runtime_cycle_artifact": {
            "scope": "runtime_official_fresh_candidate_runtime_cycle_artifact",
            "status": "fresh_candidate_cycle_handoff_completed",
            "controlled_action_side": {
                "exchange_submit_execution_result_status": (
                    "exchange_submit_orders_submitted"
                ),
                "execution_mode": "in_memory_simulation",
            },
            "post_submit_side": {
                "finalize_status": "finalized_next_attempt_blocked",
                "next_attempt_gate_status": "blocked",
                "next_attempt_gate_blockers": [
                    "runtime_active_position_slot_in_use"
                ],
            },
        },
        "checks": {
            "runtime_ids_match": True,
            "candidate_ids_match": True,
            "final_gate_passed": True,
            "controlled_submit_preflight_ready": True,
            "controlled_gateway_action_passed": True,
            "durable_execution_result_reused": True,
            "post_submit_finalize_completed": True,
            "next_attempt_gate_blocked_by_active_position": True,
            "next_attempt_requires_fresh_signal": True,
            "next_attempt_requires_fresh_authorization": True,
            "old_authorization_retry_disallowed": True,
            "pre_submit_rehearsal_retry_disallowed": True,
            "local_created_order_requirement_retired": True,
            "submit_outcome_review_created": True,
            "post_submit_budget_settlement_created": True,
            "right_tail_runner_preserved": True,
            "uses_official_fastapi_routes": True,
            "uses_fake_console_api": False,
        },
        "safety_invariants": {
            "uses_official_fastapi_routes": True,
            "uses_fake_console_api": False,
            "controlled_in_memory_execution_result_recorded": True,
            "controlled_fake_gateway_called": True,
            "controlled_order_lifecycle_submit_called": True,
            "live_exchange_called": False,
            "pg_written": False,
            "post_submit_created_order": False,
            "post_submit_order_lifecycle_called": False,
            "withdrawal_or_transfer_created": False,
        },
    }
    report.update(overrides)
    return report


def test_projection_to_local_cycle_passes_with_composed_reports(tmp_path):
    report = script.build_proof_report(
        tmp_path / "rtf102",
        readiness_preflight_builder=lambda _path: _readiness_report(),
        runtime_cycle_builder=lambda _path: _cycle_report(),
    )

    assert report["status"] == "controlled_tiny_live_readiness_to_local_cycle_passed"
    checks = report["checks"]
    assert checks["rtf101_readiness_preflight_passed"] is True
    assert checks["waiting_projection_blocks_official_route"] is True
    assert checks["ready_projection_enters_official_prepare"] is True
    assert checks["readiness_projection_uses_legacy_pre_attempt_as_primary_gate"] is False
    assert checks["rtf091_runtime_cycle_passed"] is True
    assert checks["runtime_cycle_current_artifact_present"] is True
    assert checks["runtime_ids_match"] is True
    assert checks["candidate_ids_match"] is True
    assert checks["controlled_in_memory_execution_result_recorded"] is True
    assert checks["durable_execution_result_reused"] is True
    assert checks["post_submit_finalize_completed"] is True
    assert checks["next_attempt_gate_blocked_by_active_position"] is True
    assert checks["next_attempt_requires_fresh_signal"] is True
    assert checks["next_attempt_requires_fresh_authorization"] is True
    assert checks["old_authorization_retry_disallowed"] is True
    assert checks["pre_submit_rehearsal_retry_disallowed"] is True
    assert checks["local_created_order_requirement_retired"] is True
    assert checks["submit_outcome_review_created"] is True
    assert checks["post_submit_budget_settlement_created"] is True
    assert checks["controlled_fake_gateway_called"] is True
    assert checks["controlled_order_lifecycle_submit_called"] is True
    assert checks["live_exchange_called"] is False
    assert checks["pg_written"] is False
    assert checks["withdrawal_or_transfer_created"] is False
    assert "operator_command_plan" not in report
    assert report["readiness_to_local_cycle_plan"]["executes_real_submit"] is False
    assert report["readiness_to_local_cycle_plan"]["calls_live_exchange"] is False


def test_projection_to_local_cycle_outputs_expected_artifacts(tmp_path):
    output_dir = tmp_path / "rtf102"

    report = script.build_proof_report(
        output_dir,
        readiness_preflight_builder=lambda _path: _readiness_report(),
        runtime_cycle_builder=lambda _path: _cycle_report(),
    )

    expected_files = [
        "contract-report.json",
        "rtf101-readiness-preflight-report.json",
        "rtf091-runtime-cycle-report.json",
        "readiness-to-local-runtime-cycle-artifact.json",
    ]
    for name in expected_files:
        assert (output_dir / name).exists()

    artifact = json.loads(
        (output_dir / "readiness-to-local-runtime-cycle-artifact.json").read_text()
    )
    assert (
        artifact["status"]
        == "readiness_projection_ready_local_runtime_cycle_completed"
    )
    assert artifact["readiness_preflight_side"]["ready_projection_status"] == (
        "controlled_tiny_live_readiness_projection_ready_for_official_prepare"
    )
    assert artifact["runtime_cycle_side"]["cycle_status"] == (
        "fresh_candidate_cycle_handoff_completed"
    )
    assert artifact["runtime_cycle_side"]["post_submit_side"][
        "finalize_status"
    ] == "finalized_next_attempt_blocked"
    assert json.loads((output_dir / "contract-report.json").read_text())[
        "status"
    ] == report["status"]


def test_projection_to_local_cycle_blocks_when_cycle_fails(tmp_path):
    report = script.build_proof_report(
        tmp_path / "rtf102",
        readiness_preflight_builder=lambda _path: _readiness_report(),
        runtime_cycle_builder=lambda _path: _cycle_report(status="blocked"),
    )

    assert report["status"] == "blocked"
    assert report["checks"]["rtf091_runtime_cycle_passed"] is False


def test_projection_to_local_cycle_blocks_legacy_packet_only_cycle_report(tmp_path):
    legacy_cycle_report = _cycle_report()
    legacy_cycle_report["fresh_candidate_runtime_cycle_packet"] = (
        legacy_cycle_report.pop("fresh_candidate_runtime_cycle_artifact")
    )

    report = script.build_proof_report(
        tmp_path / "rtf102",
        readiness_preflight_builder=lambda _path: _readiness_report(),
        runtime_cycle_builder=lambda _path: legacy_cycle_report,
    )

    assert report["status"] == "blocked"
    assert report["checks"]["rtf091_runtime_cycle_passed"] is True
    assert report["checks"]["runtime_cycle_current_artifact_present"] is False
    artifact = report["readiness_to_local_runtime_cycle_artifact"]
    assert artifact["runtime_cycle_side"]["cycle_status"] is None
    assert artifact["runtime_cycle_side"]["controlled_action_side"] == {}
    assert artifact["runtime_cycle_side"]["post_submit_side"] == {}


def test_projection_to_local_cycle_cli_stdout_is_json_only(
    capsys,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        script.rtf101,
        "build_proof_report",
        lambda _path: _readiness_report(),
    )
    monkeypatch.setattr(
        script.rtf091,
        "build_proof_report",
        lambda _path: _cycle_report(),
    )
    monkeypatch.setattr(
        script.sys,
        "argv",
        [
            "runtime_controlled_tiny_live_readiness_to_local_cycle_proof.py",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert script.main() == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["status"] == "controlled_tiny_live_readiness_to_local_cycle_passed"
    assert captured.err == ""
