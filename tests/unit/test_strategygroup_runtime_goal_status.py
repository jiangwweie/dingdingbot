from __future__ import annotations

import json
from pathlib import Path

from scripts.build_strategygroup_runtime_goal_status import build_goal_status_packet


HEAD = "3e08c037a4990a268d1ee2b61861601d57423223"


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_base_packets(report_dir: Path) -> None:
    report_dir.mkdir(parents=True)
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
                "scenario_count": 5,
                "required_scenarios_present": True,
                "all_scenarios_passed": True,
                "dangerous_effects_absent": True,
                "disabled_smoke_not_real_execution_proof": True,
                "operation_layer_evidence_relay_checked": True,
                "legacy_local_registration_probe_tolerance_checked": True,
                "mock_operation_layer_closed_loop_checked": True,
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
        {"status": "waiting_for_market", "blockers": []},
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
    assert packet["real_order_boundary"]["ready_for_real_order_action"] is False
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
    assert packet["real_order_boundary"]["ready_for_real_order_action"] is True


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
