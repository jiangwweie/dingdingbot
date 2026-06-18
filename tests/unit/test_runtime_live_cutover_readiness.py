from __future__ import annotations

import json

from scripts import runtime_live_cutover_readiness as script
from scripts import runtime_dry_run_audit_chain as dry_run_audit


def test_live_cutover_readiness_waits_for_fresh_signal_with_no_non_market_blockers(
    tmp_path,
) -> None:
    packet = script.build_cutover_readiness_packet(
        output_dir=tmp_path,
        generated_at_ms=1781753000000,
    )

    assert packet["schema"] == "brc.runtime_live_cutover_readiness.v1"
    assert packet["scope"] == "runtime_live_cutover_readiness"
    assert packet["status"] == "live_cutover_waiting_for_fresh_signal"
    assert packet["owner_state"] == "等待机会"
    assert packet["next_safe_action"] == (
        "continue_low_noise_watcher_until_fresh_selected_signal"
    )
    assert packet["non_market_blockers"] == []
    assert packet["market_dependent_waiting_keys"] == [
        "fresh_signal",
        "candidate_authorization",
        "action_time_finalgate",
        "official_operation_layer",
        "real_exchange_acceptance",
        "post_submit_real_reconciliation",
    ]
    assert packet["next_fresh_signal_cutover_ready"] is True
    assert packet["current_real_submit_allowed"] is False
    assert packet["safety_invariants"] == {
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
    assert packet["legacy_confirmation_regression_checks"] == {
        "disabled_smoke_not_real_execution_proof": True,
        "legacy_local_registration_probe_tolerated_without_blocking_cutover": True,
        "post_submit_outcomes_do_not_require_owner_chat_confirmation": True,
        "standing_reduce_only_recovery_does_not_require_owner_chat_confirmation": True,
    }
    contract = packet["live_closure_cutover_contract"]
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
    assert contract["required_evidence_keys"] == [
        "live_watcher_signal_packet_id",
        "required_facts_readiness_packet_id",
        "candidate_id",
        "runtime_grant_id",
        "fresh_submit_authorization_id",
        "action_time_finalgate_packet_id",
        "operation_layer_submit_authorization_id",
        "exchange_submit_execution_result_id",
        "exchange_native_hard_stop_order_id",
        "runtime_post_submit_finalize_packet_id",
        "post_submit_reconciliation_evidence_id",
        "post_submit_budget_settlement_id",
        "submit_outcome_review_id",
    ]
    assert contract["checks"] == {
        "live_closure_contract_defined": True,
        "live_closure_contract_rejects_synthetic_signal": True,
        "live_closure_contract_rejects_disabled_smoke": True,
        "live_closure_contract_requires_exchange_acceptance": True,
        "live_closure_contract_requires_exchange_native_protection": True,
        "live_closure_contract_requires_post_submit_reconciliation": True,
        "live_closure_contract_has_no_owner_chat_confirmation_stage": True,
    }
    visibility = packet["same_tick_product_state_visibility_contract"]
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

    sections = {item["name"]: item for item in packet["sections"]}
    assert set(sections) == {
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
    for section in sections.values():
        assert section["status"] == "ready"
        assert section["missing_checks"] == []


def test_live_cutover_readiness_blocks_non_market_gap(tmp_path) -> None:
    audit_packet = dry_run_audit.build_audit_chain(tmp_path / "audit")
    audit_packet["checks"]["operation_layer_evidence_relay_checked"] = False

    packet = script.build_cutover_readiness_packet(
        output_dir=tmp_path,
        dry_run_packet=audit_packet,
        generated_at_ms=1781753000000,
    )

    assert packet["status"] == "blocked_non_market_cutover_gap"
    assert packet["owner_state"] == "需要介入"
    assert packet["next_fresh_signal_cutover_ready"] is False
    assert packet["current_real_submit_allowed"] is False
    assert packet["non_market_blockers"] == [
        "operation_layer_relay:operation_layer_evidence_relay_checked"
    ]
    section = next(
        item for item in packet["sections"] if item["name"] == "operation_layer_relay"
    )
    assert section["status"] == "blocked"
    assert section["missing_checks"] == ["operation_layer_evidence_relay_checked"]


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
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    owner_text = owner_progress.read_text(encoding="utf-8")
    assert packet["status"] == "live_cutover_waiting_for_fresh_signal"
    assert "- 当前状态: 等待真实 fresh signal" in owner_text
    assert "- 非市场阻断: 无" in owner_text
    assert "- 服务器修改: 否" in owner_text
    assert "- Exchange write: 否" in owner_text
    assert "- 接近真实订单: 否" in owner_text
