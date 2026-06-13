from __future__ import annotations

import json

from scripts import runtime_official_post_submit_finalize_proof as script


def test_official_post_submit_finalize_passes(tmp_path):
    report = script.build_proof_report(tmp_path / "rtf088")

    assert report["status"] == "official_post_submit_finalize_passed"
    assert report["order_candidate_id"] == "order-candidate-rtf075-contract"
    assert report["authorization_id"].startswith("runtime-submit-authorization-")
    assert report["exchange_submit_execution_result_id"].startswith(
        "runtime-exchange-submit-execution-result-"
    )
    assert report["submit_outcome_review_id"].startswith(
        "runtime-submit-outcome-review-"
    )
    assert report["post_submit_budget_settlement_id"].startswith(
        "runtime-post-submit-budget-settlement-"
    )

    checks = report["checks"]
    assert checks["controlled_gateway_action_passed"] is True
    assert checks["post_submit_finalize_http_ok"] is True
    assert checks["post_submit_finalize_next_attempt_blocked"] is True
    assert checks["next_attempt_gate_blocked"] is True
    assert checks["next_attempt_blocked_by_active_position"] is True
    assert checks["active_position_fact_resolved"] is True
    assert checks["old_authorization_replay_only"] is True
    assert checks["old_authorization_submit_retry_disallowed"] is True
    assert checks["pre_submit_rehearsal_retry_disallowed"] is True
    assert checks["local_created_order_requirement_retired"] is True
    assert checks["submit_outcome_review_created"] is True
    assert checks["submit_outcome_review_policy_ready"] is True
    assert checks["submit_outcome_review_full_fill"] is True
    assert checks["post_submit_budget_settlement_created"] is True
    assert checks["post_submit_budget_consumed_recorded"] is True
    assert checks["runtime_budget_settlement_applied_once"] is True
    assert checks["durable_execution_result_reused"] is True
    assert checks["active_position_source_called"] is True
    assert checks["uses_official_fastapi_routes"] is True
    assert checks["uses_fake_console_api"] is False
    assert checks["pg_written"] is False
    assert checks["live_exchange_called"] is False
    assert checks["post_submit_created_order"] is False
    assert checks["post_submit_order_lifecycle_called"] is False
    assert checks["execution_intent_status_changed"] is False
    assert checks["withdrawal_or_transfer_created"] is False


def test_official_post_submit_finalize_outputs_packet(tmp_path):
    output_dir = tmp_path / "rtf088"

    report = script.build_proof_report(output_dir)

    expected_files = [
        "contract-report.json",
        "controlled-gateway-action-packet.json",
        "post-submit-finalize.json",
        "post-submit-finalize-proof-packet.json",
    ]
    for name in expected_files:
        assert (output_dir / name).exists()

    assert json.loads((output_dir / "contract-report.json").read_text())[
        "status"
    ] == report["status"]
    packet = json.loads(
        (output_dir / "post-submit-finalize-proof-packet.json").read_text()
    )
    assert packet["status"] == "post_submit_finalize_completed_next_attempt_blocked"
    assert packet["statuses"]["exchange_submit_execution_result"] == (
        "exchange_submit_orders_submitted"
    )
    assert packet["statuses"]["post_submit_finalize"] == (
        "finalized_next_attempt_blocked"
    )
    assert packet["statuses"]["next_attempt_gate"] == "blocked"
    assert packet["statuses"]["submit_outcome_review"] == (
        "classified_ready_for_attempt_outcome_policy"
    )
    assert packet["statuses"]["post_submit_budget_settlement"] == (
        "recorded_reserved_budget_consumed"
    )
    finalize = packet["post_submit_finalize"]
    assert finalize["old_authorization_submit_retry_allowed"] is False
    assert finalize["pre_submit_rehearsal_retry_allowed"] is False
    assert finalize["local_created_order_requirement_retired"] is True
    assert finalize["submit_result_status"] == "exchange_submit_orders_submitted"
    gate = packet["next_attempt_gate"]
    assert gate["status"] == "blocked"
    assert gate["active_positions_count"] == 1
    assert "runtime_active_position_slot_in_use" in gate["blockers"]
    assert gate["requires_fresh_strategy_signal"] is True
    assert gate["requires_fresh_authorization"] is True
    assert packet["review"]["observed_outcome"] == "submitted_full_fill"
    assert packet["review"]["recommended_attempt_outcome_kind"] == (
        "submitted_full_fill"
    )
    assert packet["settlement"]["status"] == "recorded_reserved_budget_consumed"
    assert packet["settlement"]["budget_action"] == (
        "confirm_reserved_budget_consumed"
    )
    assert packet["safety_invariants"]["live_exchange_called"] is False
    assert packet["safety_invariants"]["post_submit_created_order"] is False
    assert packet["safety_invariants"]["post_submit_order_lifecycle_called"] is False
    assert packet["safety_invariants"]["withdrawal_or_transfer_created"] is False


def test_official_post_submit_finalize_cli_stdout_is_json_only(
    capsys,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        script.sys,
        "argv",
        [
            "runtime_official_post_submit_finalize_proof.py",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert script.main() == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["status"] == "official_post_submit_finalize_passed"
    assert captured.err == ""
