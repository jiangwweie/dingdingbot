from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_strategygroup_runtime_goal_status import build_goal_status_packet


HEAD = "3e08c037a4990a268d1ee2b61861601d57423223"


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_base_packets(report_dir: Path) -> None:
    report_dir.mkdir(parents=True)
    _write(
        report_dir / "watcher-tick.json",
        {
            "status": "watching_no_signal",
            "blockers": [
                "runtime-mpg-1:strategy_signal_not_ready_for_shadow_candidate_prepare"
            ],
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "withdrawal_or_transfer_created": False,
            },
        },
    )
    _write(
        report_dir / "latest-summary.json",
        {
            "status": "waiting_for_signal",
            "selected_runtime_instance_ids": ["runtime-mpg-1"],
            "blockers": [
                "runtime-mpg-1:strategy_signal_not_ready_for_shadow_candidate_prepare"
            ],
        },
    )
    _write(
        report_dir / "post-signal-resume-pack.json",
        {
            "status": "waiting_for_market",
            "selected_runtime_instance_ids": ["runtime-mpg-1"],
            "blockers": [
                "runtime-mpg-1:strategy_signal_not_ready_for_shadow_candidate_prepare"
            ],
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "withdrawal_or_transfer_created": False,
            },
        },
    )
    _write(
        report_dir / "resume-dispatch-packet.json",
        {
            "status": "waiting_for_market",
            "dispatch_status": "no_action_continue_observation",
            "dispatch_action": "continue_watcher_observation",
            "blocker_class": "waiting_for_market",
            "selected_runtime_instance_ids": ["runtime-mpg-1"],
            "blockers": [],
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "withdrawal_or_transfer_created": False,
            },
        },
    )
    _write(
        report_dir / "runtime-dry-run-audit-chain.json",
        {
            "status": "passed",
            "checks": {
                "scenario_count": 8,
                "required_scenarios_present": True,
                "all_scenarios_passed": True,
                "dangerous_effects_absent": True,
                "disabled_smoke_not_real_execution_proof": True,
                "operation_layer_evidence_relay_checked": True,
                "fresh_signal_fast_auto_chain_checked": True,
                "legacy_local_registration_probe_tolerance_checked": True,
                "mock_operation_layer_closed_loop_checked": True,
                "operation_layer_blocker_review_policy_checked": True,
                "operation_layer_hard_safety_blocker_matrix_checked": True,
                "expanded_watcher_scope_execution_guard_checked": True,
                "shared_runtime_pipeline_checked": True,
                "selected_strategygroup_dispatch_guard_checked": True,
                "all_selected_strategygroups_reach_finalgate_dispatch_checked": True,
            },
            "safety_invariants": {
                "dangerous_effects": [],
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "withdrawal_or_transfer_created": False,
            },
        },
    )
    _write(
        report_dir / "owner-console-source-readiness.json",
        {
            "status": "ready",
            "owner_summary": {
                "market_opportunity": "等待机会",
                "funds": "资金正常",
                "orders": "暂无订单",
                "positions": "暂无持仓",
                "protection": "保护正常",
                "runtime_dry_run_audit": "审计演练正常",
            },
            "blockers": [],
        },
    )
    _write(
        report_dir / "strategygroup-runtime-pilot-status.json",
        {
            "status": "waiting_for_market",
            "blockers": [],
            "watcher_scope_alignment": {
                "status": "aligned",
                "selected_strategy_group_id": "MPG-001",
                "matched_runtime_signal_summaries": [
                    {
                        "runtime_instance_id": "runtime-mpg-1",
                        "strategy_family_id": "MPG-001",
                        "symbol": "MSTR/USDT:USDT",
                        "side": "long",
                        "status": "waiting_for_signal",
                    }
                ],
                "out_of_scope_runtime_signal_summaries": [],
            },
        },
    )
    _write(
        report_dir / "strategy-group-live-facts-readiness.json",
        {
            "status": "strategy_group_live_facts_ready_for_armed_observation",
            "blockers": [],
        },
    )


def _manifest(path: Path, head: str = HEAD) -> Path:
    _write(
        path,
        {
            "local_git": {
                "head": head,
                "short_head": head[:8],
            }
        },
    )
    return path


def _matrix_by_key(packet: dict) -> dict[str, dict]:
    return {
        str(item["key"]): item
        for item in packet.get("real_order_readiness_matrix", [])
    }


def test_goal_status_waits_when_runtime_has_no_fresh_signal(tmp_path: Path) -> None:
    report_dir = tmp_path / "reports"
    _write_base_packets(report_dir)

    packet = build_goal_status_packet(
        report_dir=report_dir,
        release_manifest=_manifest(tmp_path / "manifest.json"),
        expected_head=HEAD,
    )

    assert packet["status"] == "waiting_for_signal"
    assert packet["owner_state"]["label"] == "等待机会"
    assert packet["owner_state"]["next_safe_checkpoint"] == (
        "continue_watcher_observation"
    )
    assert packet["checks"]["fresh_signal_present"] is False
    assert packet["checks"]["selected_strategygroup_scope_ready"] is True
    assert packet["real_order_boundary"]["ready_for_real_order_action"] is False
    matrix = _matrix_by_key(packet)
    assert matrix["fresh_signal"]["status"] == "waiting_for_market"
    assert matrix["candidate_authorization"]["status"] == "waiting_for_market"
    assert matrix["official_operation_layer"]["status"] == "waiting_for_chain"
    assert matrix["official_operation_layer"]["blocker_class"] == "waiting_for_market"
    assert matrix["official_operation_layer"]["blocks_real_submit"] is True
    assert matrix["active_position_open_order"]["status"] == "pass"
    assert matrix["protection"]["status"] == "pass"
    assert matrix["budget"]["status"] == "pass"
    assert matrix["duplicate_submit"]["status"] == "pass"
    assert matrix["symbol_side_notional_leverage_scope"]["status"] == "pass"
    assert matrix["hard_safety"]["status"] == "pass"
    assert packet["safety_invariants"]["calls_operation_layer"] is False


def test_goal_status_requires_specific_dry_run_order_chain_checks(
    tmp_path: Path,
) -> None:
    report_dir = tmp_path / "reports"
    _write_base_packets(report_dir)
    _write(
        report_dir / "runtime-dry-run-audit-chain.json",
        {
            "status": "passed",
            "checks": {
                "scenario_count": 5,
                "dangerous_effects_absent": True,
            },
            "safety_invariants": {
                "dangerous_effects": [],
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "withdrawal_or_transfer_created": False,
            },
        },
    )

    packet = build_goal_status_packet(
        report_dir=report_dir,
        release_manifest=_manifest(tmp_path / "manifest.json"),
        expected_head=HEAD,
    )

    assert packet["status"] == "dry_run_audit_degraded"
    assert packet["owner_state"]["next_safe_checkpoint"] == (
        "repair_runtime_dry_run_audit_chain"
    )
    assert packet["real_order_boundary"]["ready_for_real_order_action"] is False
    assert "runtime_dry_run_audit_not_passed" in packet["blockers"]
    assert (
        "runtime_dry_run_missing_required_check:operation_layer_evidence_relay_checked"
        in packet["blockers"]
    )
    assert (
        "runtime_dry_run_missing_required_check:mock_operation_layer_closed_loop_checked"
        in packet["blockers"]
    )
    assert (
        "runtime_dry_run_missing_required_check:shared_runtime_pipeline_checked"
        in packet["blockers"]
    )
    assert (
        "runtime_dry_run_missing_required_check:"
        "selected_strategygroup_dispatch_guard_checked"
    ) in packet["blockers"]
    assert (
        "runtime_dry_run_missing_required_check:"
        "all_selected_strategygroups_reach_finalgate_dispatch_checked"
    ) in packet["blockers"]
    assert (
        "runtime_dry_run_missing_required_check:"
        "operation_layer_hard_safety_blocker_matrix_checked"
    ) in packet["blockers"]
    assert (
        "runtime_dry_run_missing_required_check:"
        "expanded_watcher_scope_execution_guard_checked"
    ) in packet["blockers"]


def test_goal_status_routes_fresh_signal_to_action_time_finalgate(
    tmp_path: Path,
) -> None:
    report_dir = tmp_path / "reports"
    _write_base_packets(report_dir)
    _write(
        report_dir / "resume-dispatch-packet.json",
        {
            "status": "ready_for_action_time_final_gate",
            "dispatch_status": "official_finalgate_preflight_dispatch_ready",
            "dispatch_action": "run_official_action_time_final_gate_preflight",
            "selected_runtime_instance_ids": ["runtime-mpg-1"],
            "ready_runtime_signals": 1,
            "blockers": [],
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "withdrawal_or_transfer_created": False,
            },
        },
    )

    packet = build_goal_status_packet(
        report_dir=report_dir,
        release_manifest=_manifest(tmp_path / "manifest.json"),
        expected_head=HEAD,
    )

    assert packet["status"] == "action_time_finalgate_ready"
    assert packet["owner_state"]["label"] == "处理中"
    assert packet["owner_state"]["next_safe_checkpoint"] == (
        "run_official_action_time_finalgate"
    )
    assert packet["checks"]["fresh_signal_present"] is True
    assert packet["real_order_boundary"]["ready_for_real_order_action"] is False


def test_goal_status_surfaces_watcher_liveness_blockers(
    tmp_path: Path,
) -> None:
    report_dir = tmp_path / "reports"
    _write_base_packets(report_dir)
    _write(
        report_dir / "watcher-tick.json",
        {
            "status": "owner_attention_pending",
            "blockers": [
                "loop_command_failed:2",
                "runtime-mpg-1:strategy_signal_not_ready_for_shadow_candidate_prepare",
            ],
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "withdrawal_or_transfer_created": False,
            },
        },
    )
    _write(
        report_dir / "latest-summary.json",
        {
            "status": "blocked",
            "active_runtime_count": 11,
            "selected_runtime_instance_ids": [
                "runtime-mpg-1",
                "runtime-teq-1",
                "runtime-fbs-1",
            ],
            "blockers": [
                "runtime-mpg-1:runtime_attempts_exhausted",
                "runtime-mpg-1:order_candidate_id_or_authorization_id_required",
                "runtime-teq-1:strategy_signal_not_ready_for_shadow_candidate_prepare",
            ],
        },
    )

    packet = build_goal_status_packet(
        report_dir=report_dir,
        release_manifest=_manifest(tmp_path / "manifest.json"),
        expected_head=HEAD,
    )

    assert packet["status"] == "runtime_liveness_degraded"
    assert packet["owner_state"]["label"] == "需要介入"
    assert packet["owner_state"]["next_safe_checkpoint"] == (
        "repair_runtime_attempt_renewal_or_scope"
    )
    assert packet["checks"]["watcher_liveness_healthy"] is False
    assert packet["real_order_boundary"]["ready_for_real_order_action"] is False
    assert "watcher_tick:loop_command_failed:2" in packet["blockers"]
    assert (
        "latest_summary:runtime-mpg-1:runtime_attempts_exhausted"
        in packet["blockers"]
    )
    assert (
        "latest_summary:runtime-teq-1:strategy_signal_not_ready_for_shadow_candidate_prepare"
        not in packet["blockers"]
    )
    assert packet["evidence"]["active_runtime_count"] == 11
    assert packet["evidence"]["selected_runtime_instance_count"] == 3


def test_goal_status_prioritizes_operation_layer_missing_fact_after_prepare(
    tmp_path: Path,
) -> None:
    report_dir = tmp_path / "reports"
    _write_base_packets(report_dir)
    _write(
        report_dir / "strategygroup-runtime-pilot-status.json",
        {
            "status": "ready_for_action_time_final_gate",
            "blockers": [],
            "watcher_scope_alignment": {
                "status": "aligned",
                "selected_strategy_group_id": "MPG-001",
                "matched_runtime_signal_summaries": [
                    {
                        "runtime_instance_id": "runtime-fresh-1",
                        "strategy_family_id": "MPG-001",
                        "symbol": "MSTR/USDT:USDT",
                        "side": "long",
                        "status": "ready_for_action_time_final_gate",
                    }
                ],
                "out_of_scope_runtime_signal_summaries": [],
            },
        },
    )
    _write(
        report_dir / "watcher-tick.json",
        {
            "status": "watcher_attention",
            "blockers": [
                "disabled_smoke:preview_disabled_first_real_submit_action_http_404",
                "runtime-old-1:runtime_attempts_exhausted",
                "runtime-old-1:order_candidate_id_or_authorization_id_required",
                "runtime-waiting-1:strategy_signal_not_ready_for_shadow_candidate_prepare",
            ],
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "withdrawal_or_transfer_created": False,
            },
        },
    )
    _write(
        report_dir / "latest-summary.json",
        {
            "status": "ready_for_final_gate_preflight",
            "active_runtime_count": 12,
            "selected_runtime_instance_ids": [
                "runtime-fresh-1",
                "runtime-old-1",
                "runtime-waiting-1",
            ],
            "blockers": [
                "runtime-old-1:runtime_attempts_exhausted",
                "runtime-old-1:order_candidate_id_or_authorization_id_required",
                "runtime-waiting-1:strategy_signal_not_ready_for_shadow_candidate_prepare",
            ],
        },
    )
    _write(
        report_dir / "post-signal-resume-pack.json",
        {
            "status": "ready_for_action_time_final_gate",
            "selected_runtime_instance_ids": ["runtime-fresh-1"],
            "ready_runtime_signals": 1,
            "action_time_resume": {
                "prepared_authorization_id": "auth-1",
                "status": "ready_for_action_time_final_gate",
            },
        },
    )
    _write(
        report_dir / "resume-dispatch-packet.json",
        {
            "status": "operation_layer_submit_blocked",
            "dispatch_status": "operation_layer_submit_blocked",
            "blocker_class": "missing_fact",
            "selected_runtime_instance_ids": ["runtime-fresh-1"],
            "ready_runtime_signals": 1,
            "blockers": [
                "operation_layer_not_ready:operation_layer_blocked",
                "missing_evidence_id:exchange_submit_action_authorization_id",
            ],
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "withdrawal_or_transfer_created": False,
            },
        },
    )

    packet = build_goal_status_packet(
        report_dir=report_dir,
        release_manifest=_manifest(tmp_path / "manifest.json"),
        expected_head=HEAD,
    )

    assert packet["status"] == "missing_fact"
    assert packet["owner_state"]["label"] == "需要介入"
    assert packet["owner_state"]["next_safe_checkpoint"] == (
        "repair_missing_operation_layer_evidence"
    )
    assert packet["checks"]["fresh_signal_present"] is True
    assert packet["checks"]["watcher_liveness_healthy"] is False
    assert "watcher_tick:runtime-old-1:runtime_attempts_exhausted" in packet["blockers"]
    assert packet["real_order_boundary"]["ready_for_real_order_action"] is False


def test_goal_status_marks_operation_layer_ready_only_after_required_evidence(
    tmp_path: Path,
) -> None:
    report_dir = tmp_path / "reports"
    _write_base_packets(report_dir)
    _write(
        report_dir / "resume-dispatch-packet.json",
        {
            "status": "ready_for_operation_layer",
            "dispatch_status": "official_operation_layer_evidence_ready",
            "dispatch_action": "call_official_operation_layer_submit",
            "blocker_class": "none",
            "selected_runtime_instance_ids": ["runtime-mpg-1"],
            "ready_runtime_signals": 1,
            "blockers": [],
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "withdrawal_or_transfer_created": False,
            },
        },
    )

    packet = build_goal_status_packet(
        report_dir=report_dir,
        release_manifest=_manifest(tmp_path / "manifest.json"),
        expected_head=HEAD,
    )

    assert packet["status"] == "operation_layer_ready"
    assert packet["owner_state"]["label"] == "处理中"
    assert packet["checks"]["selected_strategygroup_scope_ready"] is True
    assert packet["real_order_boundary"]["ready_for_real_order_action"] is True
    matrix = _matrix_by_key(packet)
    assert matrix["fresh_signal"]["status"] == "pass"
    assert matrix["candidate_authorization"]["status"] == "pass"
    assert matrix["action_time_finalgate"]["status"] == "pass"
    assert matrix["official_operation_layer"]["status"] == "pass"
    assert not [
        item
        for item in matrix.values()
        if item["status"] == "blocked" or item["blocks_real_submit"] is True
    ]


@pytest.mark.parametrize(
    (
        "blocker",
        "expected_status",
        "expected_next_checkpoint",
        "expected_matrix_key",
    ),
    [
        (
            "conflicting_active_position",
            "active_position_resolution",
            "record_submit_blocker_review_and_resolve_active_position",
            "active_position_open_order",
        ),
        (
            "conflicting_open_order",
            "active_position_resolution",
            "record_submit_blocker_review_and_resolve_active_position",
            "active_position_open_order",
        ),
        (
            "protection_missing",
            "missing_fact",
            "record_submit_blocker_review_and_refresh_required_facts",
            "protection",
        ),
        (
            "budget_missing",
            "missing_fact",
            "record_submit_blocker_review_and_refresh_required_facts",
            "budget",
        ),
        (
            "duplicate_submit_risk",
            "hard_safety_stop",
            "record_submit_blocker_review_packet",
            "duplicate_submit",
        ),
        (
            "symbol_scope_mismatch",
            "hard_safety_stop",
            "record_submit_blocker_review_packet",
            "symbol_side_notional_leverage_scope",
        ),
        (
            "side_scope_mismatch",
            "hard_safety_stop",
            "record_submit_blocker_review_packet",
            "symbol_side_notional_leverage_scope",
        ),
        (
            "notional_scope_mismatch",
            "hard_safety_stop",
            "record_submit_blocker_review_packet",
            "symbol_side_notional_leverage_scope",
        ),
        (
            "leverage_scope_mismatch",
            "hard_safety_stop",
            "record_submit_blocker_review_packet",
            "symbol_side_notional_leverage_scope",
        ),
    ],
)
def test_goal_status_never_opens_real_order_when_matrix_has_submit_blocker(
    blocker: str,
    expected_status: str,
    expected_next_checkpoint: str,
    expected_matrix_key: str,
    tmp_path: Path,
) -> None:
    report_dir = tmp_path / "reports"
    _write_base_packets(report_dir)
    _write(
        report_dir / "resume-dispatch-packet.json",
        {
            "status": "ready_for_operation_layer",
            "dispatch_status": "official_operation_layer_evidence_ready",
            "dispatch_action": "call_official_operation_layer_submit",
            "blocker_class": "none",
            "selected_runtime_instance_ids": ["runtime-mpg-1"],
            "ready_runtime_signals": 1,
            "blockers": [blocker],
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "withdrawal_or_transfer_created": False,
            },
        },
    )

    packet = build_goal_status_packet(
        report_dir=report_dir,
        release_manifest=_manifest(tmp_path / "manifest.json"),
        expected_head=HEAD,
    )

    assert packet["status"] == expected_status
    assert packet["owner_state"]["next_safe_checkpoint"] == expected_next_checkpoint
    assert packet["real_order_boundary"]["ready_for_real_order_action"] is False
    assert f"matrix_submit_blocker:{expected_matrix_key}" in packet["blockers"]
    assert packet["evidence"]["matrix_submit_blockers"] == [expected_matrix_key]
    matrix = _matrix_by_key(packet)
    assert matrix["official_operation_layer"]["status"] == "waiting_for_chain"
    assert matrix["official_operation_layer"]["blocks_real_submit"] is True
    assert matrix[expected_matrix_key]["status"] == "blocked"
    assert matrix[expected_matrix_key]["blocks_real_submit"] is True


def test_goal_status_blocks_operation_layer_ready_for_out_of_scope_runtime(
    tmp_path: Path,
) -> None:
    report_dir = tmp_path / "reports"
    _write_base_packets(report_dir)
    _write(
        report_dir / "resume-dispatch-packet.json",
        {
            "status": "ready_for_operation_layer",
            "dispatch_status": "official_operation_layer_evidence_ready",
            "dispatch_action": "call_official_operation_layer_submit",
            "blocker_class": "none",
            "selected_runtime_instance_ids": ["runtime-teq-1"],
            "ready_runtime_signals": 1,
            "blockers": [],
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "withdrawal_or_transfer_created": False,
            },
        },
    )

    packet = build_goal_status_packet(
        report_dir=report_dir,
        release_manifest=_manifest(tmp_path / "manifest.json"),
        expected_head=HEAD,
    )

    assert packet["status"] == "runtime_scope_mismatch"
    assert packet["owner_state"]["label"] == "需要介入"
    assert packet["owner_state"]["next_safe_checkpoint"] == (
        "ignore_out_of_scope_signal_and_continue_selected_scope_observation"
    )
    assert packet["checks"]["fresh_signal_present"] is True
    assert packet["checks"]["selected_strategygroup_scope_ready"] is False
    assert (
        "fresh_signal_outside_selected_strategygroup_scope:runtime-teq-1"
        in packet["blockers"]
    )
    assert packet["real_order_boundary"]["ready_for_real_order_action"] is False
    assert packet["real_order_boundary"]["selected_strategygroup_scope_ready"] is False
    matrix = _matrix_by_key(packet)
    assert matrix["selected_strategygroup_scope"]["status"] == "blocked"
    assert matrix["selected_strategygroup_scope"]["blocks_real_submit"] is True
    assert matrix["symbol_side_notional_leverage_scope"]["status"] == "blocked"
    assert (
        matrix["symbol_side_notional_leverage_scope"]["blocker_class"]
        == "hard_safety_stop"
    )


def test_goal_status_does_not_open_operation_layer_when_live_facts_are_blocked(
    tmp_path: Path,
) -> None:
    report_dir = tmp_path / "reports"
    _write_base_packets(report_dir)
    _write(
        report_dir / "strategy-group-live-facts-readiness.json",
        {
            "status": "strategy_group_live_facts_blocked",
            "blockers": ["open_order_facts_stale"],
        },
    )
    _write(
        report_dir / "resume-dispatch-packet.json",
        {
            "status": "ready_for_operation_layer",
            "dispatch_status": "official_operation_layer_evidence_ready",
            "dispatch_action": "call_official_operation_layer_submit",
            "blocker_class": "none",
            "ready_runtime_signals": 1,
            "blockers": [],
        },
    )

    packet = build_goal_status_packet(
        report_dir=report_dir,
        release_manifest=_manifest(tmp_path / "manifest.json"),
        expected_head=HEAD,
    )

    assert packet["status"] == "missing_fact"
    assert packet["owner_state"]["next_safe_checkpoint"] == (
        "refresh_strategy_group_live_facts_readiness"
    )
    assert packet["real_order_boundary"]["ready_for_real_order_action"] is False
    assert "live_facts_not_ready" in packet["blockers"]
    matrix = _matrix_by_key(packet)
    assert matrix["required_facts"]["status"] == "blocked"
    assert matrix["required_facts"]["blocker_class"] == "missing_fact"
    assert matrix["required_facts"]["blocks_real_submit"] is True
    assert matrix["active_position_open_order"]["status"] == "pass"
    assert matrix["active_position_open_order"]["blocks_real_submit"] is False


def test_goal_status_open_order_facts_stale_does_not_block_active_position_open_order(
    tmp_path: Path,
) -> None:
    report_dir = tmp_path / "reports"
    _write_base_packets(report_dir)
    _write(
        report_dir / "strategy-group-live-facts-readiness.json",
        {
            "status": "strategy_group_live_facts_blocked",
            "blockers": ["open_order_facts_stale"],
        },
    )

    packet = build_goal_status_packet(
        report_dir=report_dir,
        release_manifest=_manifest(tmp_path / "manifest.json"),
        expected_head=HEAD,
    )

    matrix = _matrix_by_key(packet)
    assert packet["status"] == "missing_fact"
    assert matrix["required_facts"]["status"] == "blocked"
    assert matrix["required_facts"]["blocker_class"] == "missing_fact"
    assert matrix["active_position_open_order"]["status"] == "pass"
    assert matrix["active_position_open_order"]["blocker_class"] == "none"
    assert matrix["active_position_open_order"]["blocks_real_submit"] is False


def test_goal_status_scope_matching_ignores_benign_symbol_read_errors(
    tmp_path: Path,
) -> None:
    report_dir = tmp_path / "reports"
    _write_base_packets(report_dir)
    _write(
        report_dir / "resume-dispatch-packet.json",
        {
            "status": "waiting_for_market",
            "dispatch_status": "no_action_continue_observation",
            "dispatch_action": "continue_watcher_observation",
            "blocker_class": "waiting_for_market",
            "selected_runtime_instance_ids": ["runtime-mpg-1"],
            "blockers": ["symbol_read_error"],
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "withdrawal_or_transfer_created": False,
            },
        },
    )

    packet = build_goal_status_packet(
        report_dir=report_dir,
        release_manifest=_manifest(tmp_path / "manifest.json"),
        expected_head=HEAD,
    )

    matrix = _matrix_by_key(packet)
    assert matrix["symbol_side_notional_leverage_scope"]["status"] == "pass"
    assert matrix["symbol_side_notional_leverage_scope"]["blocks_real_submit"] is False


def test_goal_status_scope_matching_preserves_true_scope_mismatch_blocker(
    tmp_path: Path,
) -> None:
    report_dir = tmp_path / "reports"
    _write_base_packets(report_dir)
    _write(
        report_dir / "resume-dispatch-packet.json",
        {
            "status": "waiting_for_market",
            "dispatch_status": "no_action_continue_observation",
            "dispatch_action": "continue_watcher_observation",
            "blocker_class": "waiting_for_market",
            "selected_runtime_instance_ids": ["runtime-mpg-1"],
            "blockers": ["scope_mismatch"],
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "withdrawal_or_transfer_created": False,
            },
        },
    )

    packet = build_goal_status_packet(
        report_dir=report_dir,
        release_manifest=_manifest(tmp_path / "manifest.json"),
        expected_head=HEAD,
    )

    matrix = _matrix_by_key(packet)
    assert matrix["symbol_side_notional_leverage_scope"]["status"] == "blocked"
    assert (
        matrix["symbol_side_notional_leverage_scope"]["blocker_class"]
        == "hard_safety_stop"
    )
    assert matrix["symbol_side_notional_leverage_scope"]["blocks_real_submit"] is True


def test_goal_status_blocks_active_position_conflict_before_real_order_boundary(
    tmp_path: Path,
) -> None:
    report_dir = tmp_path / "reports"
    _write_base_packets(report_dir)
    _write(
        report_dir / "resume-dispatch-packet.json",
        {
            "status": "blocked_active_position_resolution",
            "dispatch_status": "blocked_before_operation_layer",
            "dispatch_action": "resolve_active_position_first",
            "blocker_class": "active_position_resolution",
            "ready_runtime_signals": 1,
            "blockers": ["conflicting_open_order"],
        },
    )

    packet = build_goal_status_packet(
        report_dir=report_dir,
        release_manifest=_manifest(tmp_path / "manifest.json"),
        expected_head=HEAD,
    )

    assert packet["status"] == "active_position_resolution"
    assert packet["owner_state"]["next_safe_checkpoint"] == (
        "resolve_active_position_or_open_order_conflict"
    )
    assert packet["real_order_boundary"]["ready_for_real_order_action"] is False
    matrix = _matrix_by_key(packet)
    assert matrix["active_position_open_order"]["status"] == "blocked"
    assert (
        matrix["active_position_open_order"]["blocker_class"]
        == "active_position_resolution"
    )
    assert matrix["active_position_open_order"]["blocks_real_submit"] is True


def test_goal_status_blocks_when_required_packet_is_missing(
    tmp_path: Path,
) -> None:
    report_dir = tmp_path / "reports"
    _write_base_packets(report_dir)
    (report_dir / "owner-console-source-readiness.json").unlink()

    packet = build_goal_status_packet(
        report_dir=report_dir,
        release_manifest=_manifest(tmp_path / "manifest.json"),
        expected_head=HEAD,
    )

    assert packet["status"] == "missing_fact"
    assert packet["owner_state"]["next_safe_checkpoint"] == (
        "refresh_required_runtime_packets"
    )
    assert packet["real_order_boundary"]["ready_for_real_order_action"] is False
    assert "missing_packet:source_readiness" in packet["blockers"]


def test_goal_status_blocks_when_deployed_head_is_not_expected(
    tmp_path: Path,
) -> None:
    report_dir = tmp_path / "reports"
    _write_base_packets(report_dir)

    packet = build_goal_status_packet(
        report_dir=report_dir,
        release_manifest=_manifest(tmp_path / "manifest.json", head="old"),
        expected_head=HEAD,
    )

    assert packet["status"] == "deployment_issue"
    assert packet["blockers"] == ["deployed_head_mismatch"]
    assert packet["owner_state"]["next_safe_checkpoint"] == (
        "align_tokyo_deployment_before_runtime_action"
    )
    assert packet["real_order_boundary"]["ready_for_real_order_action"] is False
