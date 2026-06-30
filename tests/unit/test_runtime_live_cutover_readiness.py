from __future__ import annotations

import json

from scripts import runtime_live_cutover_readiness as script
from scripts import runtime_dry_run_audit_chain as dry_run_audit


def test_live_cutover_readiness_waits_for_fresh_signal_with_no_non_market_blockers(
    tmp_path,
) -> None:
    artifact = script.build_cutover_readiness_artifact(
        output_dir=tmp_path,
        generated_at_ms=1781753000000,
    )

    assert artifact["schema"] == "brc.runtime_live_cutover_readiness.v1"
    assert artifact["scope"] == "runtime_live_cutover_readiness"
    assert artifact["status"] == "live_cutover_waiting_for_fresh_signal"
    assert artifact["owner_state"] == "等待机会"
    assert artifact["next_safe_action"] == (
        "continue_low_noise_watcher_until_fresh_selected_signal"
    )
    assert artifact["non_market_blockers"] == []
    assert artifact["market_dependent_waiting_keys"] == [
        "fresh_signal",
        "candidate_authorization",
        "action_time_finalgate",
        "official_operation_layer",
        "real_exchange_acceptance",
        "post_submit_real_reconciliation",
    ]
    assert artifact["next_fresh_signal_cutover_ready"] is True
    assert artifact["current_real_submit_allowed"] is False
    assert artifact["current_real_submit_blocker"] == (
        "no_live_fresh_signal_in_this_local_artifact"
    )
    assert "source_packets" not in artifact
    assert artifact["source_artifacts"]["dry_run_audit_status"] == "passed"
    assert artifact["safety_invariants"] == {
        "calls_tokyo_api": False,
        "mutates_server_files": False,
        "calls_live_finalgate": False,
        "calls_live_operation_layer": False,
        "exchange_write_called": False,
        "order_lifecycle_called": False,
        "real_order_created": False,
        "withdrawal_or_transfer_created": False,
        "modifies_secret_or_credentials": False,
        "modifies_live_profile": False,
        "modifies_order_sizing_defaults": False,
        "replay_or_synthetic_signal_used_as_live_signal": False,
    }
    assert artifact["legacy_confirmation_regression_checks"] == {
        "disabled_smoke_not_real_execution_proof": True,
        "legacy_local_registration_probe_tolerated_without_blocking_cutover": True,
        "post_submit_outcomes_do_not_require_owner_chat_confirmation": True,
        "standing_reduce_only_recovery_does_not_require_owner_chat_confirmation": True,
    }
    contract = artifact["live_closure_cutover_contract"]
    assert contract["scope"] == "first_bounded_live_order_closure_cutover_contract"
    assert contract["status"] == "ready"
    assert contract["stage_count"] == 9
    assert contract["stage_order"] == [
        "live_fresh_signal",
        "required_facts_ready",
        "candidate_authorization_bound",
        "action_time_finalgate_passed",
        "official_operation_layer_ready",
        "real_exchange_acceptance",
        "exchange_native_protection",
        "post_submit_finalize",
        "reconciliation_settlement_review",
    ]
    for stage in contract["stages"]:
        assert "next_action" not in stage
        assert stage["next_lifecycle_checkpoint"]
    assert contract["required_evidence_keys"] == [
        "live_watcher_signal_packet_id",
        "required_facts_readiness_artifact_id",
        "candidate_id",
        "runtime_grant_id",
        "fresh_submit_authorization_id",
        "action_time_finalgate_packet_id",
        "operation_layer_submit_authorization_id",
        "exchange_submit_execution_result_id",
        "exchange_native_hard_stop_order_id",
        "runtime_post_submit_finalize_payload_id",
        "post_submit_reconciliation_evidence_id",
        "post_submit_budget_settlement_id",
        "submit_outcome_review_id",
    ]
    assert contract["checks"] == {
        "live_closure_contract_defined": True,
        "live_closure_contract_rejects_synthetic_signal": True,
        "live_closure_contract_rejects_disabled_smoke": True,
        "live_closure_contract_requires_live_signal_chain_binding": True,
        "live_closure_contract_requires_pre_submit_authorization_chain_binding": True,
        "live_closure_contract_requires_runtime_boundary_binding": True,
        "live_closure_contract_requires_exchange_acceptance": True,
        "live_closure_contract_requires_live_submit_truth": True,
        "live_closure_contract_requires_exchange_native_protection": True,
        "live_closure_contract_requires_exchange_native_protection_binding": True,
        "live_closure_contract_requires_post_submit_reconciliation": True,
        "live_closure_contract_requires_post_submit_result_binding": True,
        "live_closure_contract_has_no_owner_chat_confirmation_stage": True,
    }
    visibility = artifact["same_tick_product_state_visibility_contract"]
    assert visibility["status"] == "ready"
    assert visibility["events"] == [
        "dry_run",
        "chain_closure",
        "live_closure",
        "goal_status",
        "api:/api/trading-console/strategy-group-live-facts-readiness",
        "api:/api/trading-console/owner-console-source-readiness",
        "api:/api/trading-console/strategygroup-runtime-pilot-status",
    ]
    assert visibility["checks"] == {
        "product_state_refresh_status_ok": True,
        "product_state_live_closure_before_goal_status": True,
        "product_state_goal_status_before_source_readiness": True,
        "product_state_refresh_has_no_dangerous_effects": True,
    }

    check_groups = {item["name"]: item for item in artifact["check_groups"]}
    assert set(check_groups) == {
        "strategy_scope",
        "entry_fast_chain",
        "operation_layer_relay",
        "hard_blocker_policy",
        "exit_protection_recovery",
        "post_submit_close_loop",
        "legacy_confirmation_regression",
        "live_closure_cutover_contract",
        "same_tick_product_state_visibility",
        "dry_run_safety",
    }
    for check_group in check_groups.values():
        assert check_group["status"] == "ready"
        assert check_group["missing_checks"] == []


def test_live_cutover_readiness_blocks_non_market_gap(tmp_path) -> None:
    audit_artifact = dry_run_audit.build_audit_artifact(tmp_path / "audit")
    audit_artifact["checks"]["operation_layer_evidence_relay_checked"] = False

    artifact = script.build_cutover_readiness_artifact(
        output_dir=tmp_path,
        dry_run_artifact=audit_artifact,
        generated_at_ms=1781753000000,
    )

    assert artifact["status"] == "blocked_non_market_cutover_gap"
    assert artifact["owner_state"] == "需要介入"
    assert artifact["next_fresh_signal_cutover_ready"] is False
    assert artifact["current_real_submit_allowed"] is False
    assert artifact["non_market_blockers"] == [
        "operation_layer_relay:operation_layer_evidence_relay_checked"
    ]
    check_group = next(
        item
        for item in artifact["check_groups"]
        if item["name"] == "operation_layer_relay"
    )
    assert check_group["status"] == "blocked"
    assert check_group["missing_checks"] == ["operation_layer_evidence_relay_checked"]


def test_live_cutover_cli_writes_owner_summary(tmp_path) -> None:
    output_json = tmp_path / "live-cutover-readiness.json"
    owner_progress = tmp_path / "live-cutover-readiness.md"

    exit_code = script.main(
        [
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(owner_progress),
            "--output-dir",
            str(tmp_path / "artifacts"),
        ]
    )

    assert exit_code == 0
    artifact = json.loads(output_json.read_text(encoding="utf-8"))
    owner_text = owner_progress.read_text(encoding="utf-8")
    assert artifact["status"] == "live_cutover_waiting_for_fresh_signal"
    assert "- 当前状态: 等待真实 fresh signal" in owner_text
    assert "- 非市场阻断: 无" in owner_text
    assert "- 服务器修改: 否" in owner_text
    assert "- Exchange write: 否" in owner_text
    assert "- 接近真实订单: 否" in owner_text
