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

    sections = {item["name"]: item for item in packet["sections"]}
    assert set(sections) == {
        "strategy_scope",
        "entry_fast_chain",
        "operation_layer_relay",
        "hard_blocker_policy",
        "exit_protection_recovery",
        "post_submit_close_loop",
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
