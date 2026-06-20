from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DAILY_CHECK_SCRIPT_PATH = REPO_ROOT / "scripts" / "run_strategygroup_runtime_daily_check.py"
RUNTIME_MONITOR_BASELINE_PATH = REPO_ROOT / "docs/current/RUNTIME_MONITOR_BASELINE.json"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "run_strategygroup_runtime_daily_check",
        DAILY_CHECK_SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _snapshot(**overrides):
    base = {
        "status": "ready",
        "interaction": {
            "level": "L1_readonly_snapshot",
            "remote_interaction_count": 1,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_exchange_write": False,
        },
        "inputs": {
            "expected_runtime_head": "runtime-head-1",
            "expected_frontend_head": None,
        },
        "owner_summary": {
            "state": "等待机会",
            "current_action": "继续等待市场机会",
            "runtime": "正常",
            "watcher": "运行中",
            "source_readiness": "正常",
            "dry_run_audit": "审计演练正常",
            "chain_closure": "非市场链路已收口",
            "frontend": "外部项目",
        },
        "checks": {
            "blockers": [],
            "product_gaps": [],
            "backend_active": True,
            "watcher_timer_active": True,
            "source_readiness_ready": True,
            "runtime_dry_run_audit_passed": True,
            "runtime_dry_run_required_checks_present": True,
            "runtime_dry_run_missing_required_checks": [],
            "runtime_execution_chain_closure_status_ready": True,
            "frontend_scope": "externalized",
        },
        "facts": {
            "release": {
                "head": "runtime-head-1",
                "current_realpath": (
                    "/home/ubuntu/brc-deploy/releases/"
                    "brc-runtime-governance-runtime-head-1"
                ),
            },
            "reports": {
                "goal_status": {
                    "status": "waiting_for_signal",
                    "fresh_signal_present": False,
                    "real_order_readiness_summary": {
                        "total": 2,
                        "pass": 1,
                        "waiting": 1,
                        "blocked": 0,
                        "submit_blocker_keys": [],
                        "waiting_keys": ["fresh_signal"],
                    },
                },
                "runtime_dry_run_audit": {
                    "status": "passed",
                    "scenario_count": 14,
                },
                "runtime_execution_chain_closure_status": {
                    "status": "non_market_execution_chain_ready",
                    "ready_segments": [
                        "fresh_signal_fast_auto_chain_checked",
                        "required_facts_readiness_checked",
                        "non_executing_prepare_auto_bridge_checked",
                        "selected_strategygroup_dispatch_guard_checked",
                        "all_selected_strategygroups_reach_finalgate_dispatch_checked",
                        "operation_layer_evidence_relay_checked",
                        "scoped_pipeline_operation_layer_handoff_checked",
                        "operation_layer_authorization_chain_guard_checked",
                        "operation_layer_standing_authorization_relay_checked",
                        "operation_layer_blocker_review_policy_checked",
                        "post_submit_exit_outcome_matrix_checked",
                        "reduce_only_recovery_standing_authorization_checked",
                        "strategygroup_adapter_boundary_checked",
                        "runtime_tier_policy_checked",
                        "new_strategygroups_default_observe_only_checked",
                        "tp1_policy_checked",
                        "runner_exit_policy_checked",
                        "reduce_only_recovery_checked",
                        "entry_filled_protection_ok_checked",
                        "partial_fill_policy_checked",
                        "exchange_submit_failed_before_acceptance_policy_checked",
                        "active_position_remains_open_policy_checked",
                    ],
                    "missing_or_failed_segments": [],
                    "ready_goal_chain_segments": [
                        "fresh_or_mock_signal",
                        "required_facts_readiness",
                        "candidate_authorization_evidence",
                        "action_time_finalgate",
                        "official_operation_layer_evidence_handoff",
                        "disabled_dry_run_proof",
                        "post_submit_exit_outcome_matrix",
                    ],
                    "missing_or_failed_goal_chain_segments": [],
                },
            },
        },
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merged = dict(base[key])
            merged.update(value)
            base[key] = merged
        else:
            base[key] = value
    return base


def test_daily_check_keeps_healthy_waiting_for_market_low_noise():
    module = _load_module()

    report = module.build_daily_check_report(snapshot=_snapshot())

    assert report["schema_version"] == module.DAILY_CHECK_REPORT_SCHEMA_VERSION
    assert report["status"] == "waiting_for_market"
    assert report["owner_summary"]["state"] == "等待机会"
    assert report["owner_summary"]["current_action"] == "继续等待市场机会"
    assert report["owner_summary"]["owner_intervention_required"] is False
    assert report["owner_summary"]["visibility"]["category"] == "waiting_for_market"
    assert report["interaction"]["level"] == "L1_daily_check_from_snapshot"
    assert report["interaction"]["remote_interaction_count"] == 1
    assert report["interaction"]["max_remote_interactions"] == 1
    assert report["interaction"]["mutates_remote_files"] is False
    assert report["interaction"]["approaches_real_order"] is False
    assert report["checks"]["blockers"] == []
    assert report["source"] == {
        "expected_runtime_head": "runtime-head-1",
        "runtime_head": "runtime-head-1",
        "runtime_release_path": (
            "/home/ubuntu/brc-deploy/releases/"
            "brc-runtime-governance-runtime-head-1"
        ),
    }
    assert report["checks"]["waiting_for_market"] is True
    assert report["checks"]["runtime_dry_run_required_checks_present"] is True
    assert report["checks"]["fresh_signal_notification_policy_checked"] is True
    assert report["checks"]["runtime_dry_run_missing_required_checks"] == []
    assert report["checks"]["runtime_dry_run_scenario_count"] == 14
    assert report["checks"]["runtime_live_closure_evidence_status"] == (
        "not_generated"
    )
    assert report["checks"]["first_bounded_real_order_complete"] is False
    assert report["checks"]["real_order_closure_proven"] is False
    assert report["checks"]["runtime_execution_chain_ready_segment_count"] == 22
    assert report["checks"]["entry_fast_chain_boundary_ready"] is True
    assert report["checks"]["exit_hardening_boundary_ready"] is True
    assert report["checks"]["strategygroup_tier_boundary_ready"] is True
    assert report["checks"]["real_order_readiness_summary"] == {
        "total": 2,
        "pass": 1,
        "waiting": 1,
        "blocked": 0,
        "submit_blocker_keys": [],
        "waiting_keys": ["fresh_signal"],
    }
    assert (
        report["checks"]["runtime_execution_chain_missing_or_failed_segments"]
        == []
    )
    assert (
        report["checks"]["runtime_execution_goal_chain_ready_segment_count"]
        == 7
    )
    assert (
        report["checks"]["runtime_execution_goal_chain_missing_or_failed_segments"]
        == []
    )
    assert report["owner_summary"]["progress"]["dry_run_audit_scenarios"] == 14
    assert report["owner_summary"]["progress"]["chain_closure_ready_segments"] == 22
    assert (
        report["owner_summary"]["progress"][
            "chain_closure_missing_or_failed_segments"
        ]
        == []
    )
    assert report["owner_summary"]["progress"]["goal_chain_ready_segments"] == 7
    assert (
        report["owner_summary"]["progress"]["goal_chain_missing_or_failed_segments"]
        == []
    )
    assert report["owner_summary"]["progress"]["entry_fast_chain_boundary"] == "ready"
    assert report["owner_summary"]["progress"]["exit_hardening_boundary"] == "ready"
    assert report["owner_summary"]["progress"]["strategygroup_tier_boundary"] == "ready"
    assert report["owner_summary"]["progress"]["real_order_readiness"] == {
        "total": 2,
        "pass": 1,
        "waiting": 1,
        "blocked": 0,
        "submit_blocker_keys": [],
        "waiting_keys": ["fresh_signal"],
    }
    assert report["notification"] == {
        "decision": "DONT_NOTIFY",
        "reason": "healthy_waiting_for_market",
        "message": "自动化正常运行，当前没有可用市场机会",
        "owner_intervention_required": False,
    }


def test_daily_check_cache_read_reports_l0_and_preserves_cached_collection():
    module = _load_module()

    report = module.build_daily_check_report(snapshot=_snapshot())
    annotated = module._annotate_current_read_interaction(report)

    assert annotated["interaction"]["level"] == "L0_local_cache_read"
    assert annotated["interaction"]["remote_interaction_count"] == 0
    assert annotated["interaction"]["max_remote_interactions"] == 0
    assert annotated["interaction"]["mutates_remote_files"] is False
    assert annotated["interaction"]["approaches_real_order"] is False
    assert annotated["interaction"]["calls_exchange_write"] is False
    assert annotated["current_read_interaction"] == annotated["interaction"]
    assert annotated["cached_report_interaction"]["level"] == (
        "L1_daily_check_from_snapshot"
    )
    assert annotated["cached_report_interaction"]["remote_interaction_count"] == 1
    assert annotated["owner_summary"]["risk_level"] == "L0 local cache only"

    owner_progress = module._owner_progress_text(
        annotated,
        now_utc=datetime.fromisoformat(annotated["generated_at_utc"]),
    )

    assert "- 本次读取等级: L0_local_cache_read" in owner_progress
    assert "- 本次远端交互次数: 0" in owner_progress
    assert "- 报告采集等级: L1_daily_check_from_snapshot" in owner_progress
    assert "- 报告采集远端交互次数: 1" in owner_progress


def test_daily_check_projects_first_bounded_live_closure_completion():
    module = _load_module()

    report = module.build_daily_check_report(
        snapshot=_snapshot(
            checks={
                "runtime_live_closure_evidence_status": "live_closure_complete",
                "first_bounded_real_order_complete": True,
                "real_order_closure_proven": True,
            }
        )
    )

    assert report["status"] == "ready"
    assert report["checks"]["waiting_for_market"] is False
    assert report["checks"]["runtime_live_closure_evidence_status"] == (
        "live_closure_complete"
    )
    assert report["checks"]["first_bounded_real_order_complete"] is True
    assert report["checks"]["real_order_closure_proven"] is True
    assert report["owner_summary"]["progress"]["live_closure"] == (
        "live_closure_complete"
    )


def test_daily_check_normalizes_no_signal_live_closure_in_progress_to_waiting():
    module = _load_module()

    report = module.build_daily_check_report(
        snapshot=_snapshot(
            checks={
                "runtime_live_closure_evidence_status": "live_closure_in_progress",
            }
        )
    )

    assert report["status"] == "waiting_for_market"
    assert report["checks"]["waiting_for_market"] is True
    assert report["checks"]["runtime_live_closure_evidence_status"] == (
        "live_closure_in_progress"
    )
    assert report["owner_summary"]["state"] == "等待机会"
    assert report["owner_summary"]["current_action"] == "继续等待市场机会"
    assert report["owner_summary"]["visibility"]["category"] == "waiting_for_market"
    assert report["notification"] == {
        "decision": "DONT_NOTIFY",
        "reason": "healthy_waiting_for_market",
        "message": "自动化正常运行，当前没有可用市场机会",
        "owner_intervention_required": False,
    }


def test_daily_check_projects_post_signal_live_closure_in_progress_as_processing():
    module = _load_module()
    snapshot = _snapshot(
        checks={
            "runtime_live_closure_evidence_status": "live_closure_in_progress",
        },
        owner_summary={
            "state": "处理中",
        },
    )
    snapshot["facts"]["reports"]["goal_status"] = {
        "status": "signal_ready",
        "fresh_signal_present": True,
        "real_order_readiness_summary": {
            "total": 2,
            "pass": 1,
            "waiting": 1,
            "blocked": 0,
            "submit_blocker_keys": [],
            "waiting_keys": ["action_time_finalgate"],
        },
    }

    report = module.build_daily_check_report(snapshot=snapshot)

    assert report["status"] == "processing"
    assert report["checks"]["waiting_for_market"] is False
    assert report["checks"]["runtime_live_closure_evidence_status"] == (
        "live_closure_in_progress"
    )
    assert report["owner_summary"]["state"] == "处理中"
    assert report["owner_summary"]["current_action"] == "等待系统完成收口"
    assert report["owner_summary"]["visibility"]["category"] == "processing"
    assert report["owner_summary"]["progress"]["live_closure"] == (
        "live_closure_in_progress"
    )
    assert report["notification"] == {
        "decision": "NOTIFY",
        "reason": "processing",
        "message": "系统正在处理真实订单闭环证据",
        "owner_intervention_required": False,
    }


def test_daily_check_preserves_fresh_signal_processing_over_stale_waiting_summary():
    module = _load_module()
    snapshot = _snapshot()
    snapshot["facts"]["reports"]["goal_status"] = {
        "status": "fresh_signal_processing",
        "fresh_signal_present": True,
        "real_order_readiness_summary": {
            "total": 3,
            "pass": 2,
            "waiting": 1,
            "blocked": 0,
            "submit_blocker_keys": [],
            "waiting_keys": ["candidate_authorization"],
        },
    }

    report = module.build_daily_check_report(snapshot=snapshot)

    assert report["status"] == "processing"
    assert report["checks"]["waiting_for_market"] is False
    assert report["checks"]["real_order_readiness_summary"] == {
        "total": 3,
        "pass": 2,
        "waiting": 1,
        "blocked": 0,
        "submit_blocker_keys": [],
        "waiting_keys": ["candidate_authorization"],
    }
    assert report["owner_summary"]["state"] == "处理中"
    assert report["owner_summary"]["current_action"] == "等待系统完成收口"
    assert report["owner_summary"]["visibility"]["category"] == "processing"
    assert report["notification"] == {
        "decision": "NOTIFY",
        "reason": "processing",
        "message": "系统正在处理真实订单闭环证据",
        "owner_intervention_required": False,
    }
    assert report["interaction"]["calls_exchange_write"] is False
    assert report["interaction"]["places_order"] is False


def test_daily_check_projects_rejected_live_closure_as_product_gap():
    module = _load_module()

    report = module.build_daily_check_report(
        snapshot=_snapshot(
            checks={
                "runtime_live_closure_evidence_status": (
                    "blocked_live_closure_rejected"
                ),
                "runtime_live_closure_evidence_reject_reasons": [
                    "official_live_closure_source_missing",
                ],
            }
        )
    )

    assert report["status"] == "degraded"
    assert report["checks"]["waiting_for_market"] is False
    assert report["checks"]["product_gaps"] == [
        "live_closure_evidence:official_live_closure_source_missing"
    ]
    assert report["checks"]["warnings"] == [
        "product_gap:live_closure_evidence:official_live_closure_source_missing"
    ]
    assert report["owner_summary"]["state"] == "工程状态暂不可用"
    assert report["owner_summary"]["current_action"] == "处理真实闭环证据异常"
    assert report["owner_summary"]["visibility"]["detail"] == (
        "真实闭环证据不可用，等待系统处理"
    )
    assert report["notification"]["decision"] == "NOTIFY"
    assert report["notification"]["reason"] == "product_gap_present"


def test_daily_check_does_not_require_frontend_publish_for_quiet_waiting():
    module = _load_module()
    snapshot = _snapshot(
        checks={
            "blockers": [],
            "product_gaps": [],
            "backend_active": True,
            "watcher_timer_active": True,
            "source_readiness_ready": True,
            "runtime_dry_run_audit_passed": True,
            "runtime_dry_run_required_checks_present": True,
            "runtime_dry_run_missing_required_checks": [],
            "frontend_scope": "externalized",
        }
    )

    report = module.build_daily_check_report(snapshot=snapshot)

    assert report["status"] == "waiting_for_market"
    assert report["owner_summary"]["state"] == "等待机会"
    assert report["owner_summary"]["visibility"]["category"] == "waiting_for_market"
    assert report["owner_summary"]["current_action"] == "继续等待市场机会"
    assert report["owner_summary"]["owner_intervention_required"] is False
    assert report["checks"]["warnings"] == []
    assert report["checks"]["blockers"] == []
    assert report["notification"]["decision"] == "DONT_NOTIFY"
    assert report["notification"]["reason"] == "healthy_waiting_for_market"


def test_daily_check_blocks_on_snapshot_runtime_blocker():
    module = _load_module()
    snapshot = _snapshot(
        status="blocked",
        checks={
            "blockers": ["owner_console_backend_inactive"],
            "product_gaps": [],
            "backend_active": False,
            "watcher_timer_active": True,
            "source_readiness_ready": True,
            "runtime_dry_run_audit_passed": True,
            "runtime_dry_run_required_checks_present": True,
            "runtime_dry_run_missing_required_checks": [],
            "frontend_scope": "externalized",
        },
    )

    report = module.build_daily_check_report(snapshot=snapshot)

    assert report["status"] == "blocked"
    assert report["owner_summary"]["state"] == "工程状态暂不可用"
    assert report["owner_summary"]["current_action"] == "处理工程状态阻断"
    assert report["owner_summary"]["owner_intervention_required"] is False
    assert report["owner_summary"]["visibility"]["category"] == "engineering_blocker"
    assert "owner_console_backend_inactive" in report["checks"]["blockers"]
    assert "l1_snapshot_blocked" in report["checks"]["blockers"]
    assert report["notification"]["decision"] == "NOTIFY"
    assert report["notification"]["reason"] == "blocker_present"


def test_daily_check_classifies_safety_blocker_separately():
    module = _load_module()
    snapshot = _snapshot(
        status="blocked",
        checks={
            "blockers": ["active_position_open_order_conflict"],
            "product_gaps": [],
            "backend_active": True,
            "watcher_timer_active": True,
            "source_readiness_ready": True,
            "runtime_dry_run_audit_passed": True,
            "runtime_dry_run_required_checks_present": True,
            "runtime_dry_run_missing_required_checks": [],
            "frontend_scope": "externalized",
        },
    )

    report = module.build_daily_check_report(snapshot=snapshot)

    assert report["status"] == "blocked"
    assert report["owner_summary"]["state"] == "安全边界阻断"
    assert report["owner_summary"]["current_action"] == "等待系统处理安全状态"
    assert report["owner_summary"]["owner_intervention_required"] is True
    assert report["owner_summary"]["visibility"]["category"] == "safety_blocker"
    assert report["owner_summary"]["visibility"]["detail"] == (
        "真实订单保持关闭，等待安全状态恢复"
    )
    assert report["notification"]["decision"] == "NOTIFY"
    assert report["notification"]["reason"] == "blocker_present"
    assert report["notification"]["owner_intervention_required"] is True


def test_daily_check_classifies_missing_budget_as_safety_blocker():
    module = _load_module()
    snapshot = _snapshot(
        status="blocked",
        checks={
            "blockers": ["missing_budget_for_runtime_attempt"],
            "product_gaps": [],
            "backend_active": True,
            "watcher_timer_active": True,
            "source_readiness_ready": True,
            "runtime_dry_run_audit_passed": True,
            "runtime_dry_run_required_checks_present": True,
            "runtime_dry_run_missing_required_checks": [],
            "frontend_scope": "externalized",
        },
    )

    report = module.build_daily_check_report(snapshot=snapshot)

    assert report["status"] == "blocked"
    assert report["owner_summary"]["state"] == "安全边界阻断"
    assert report["owner_summary"]["visibility"]["category"] == "safety_blocker"
    assert report["owner_summary"]["owner_intervention_required"] is True


def test_daily_check_exposes_missing_dry_run_required_checks():
    module = _load_module()
    snapshot = _snapshot(
        status="blocked",
        checks={
            "blockers": [
                "runtime_dry_run_missing_required_check:fresh_signal_fast_auto_chain_checked"
            ],
            "product_gaps": [],
            "backend_active": True,
            "watcher_timer_active": True,
            "source_readiness_ready": True,
            "runtime_dry_run_audit_passed": False,
            "runtime_dry_run_required_checks_present": False,
            "runtime_dry_run_missing_required_checks": [
                "fresh_signal_fast_auto_chain_checked"
            ],
            "frontend_scope": "externalized",
        },
    )

    report = module.build_daily_check_report(snapshot=snapshot)

    assert report["status"] == "blocked"
    assert report["checks"]["runtime_dry_run_audit_passed"] is False
    assert report["checks"]["runtime_dry_run_required_checks_present"] is False
    assert report["checks"]["runtime_dry_run_missing_required_checks"] == [
        "fresh_signal_fast_auto_chain_checked"
    ]
    assert report["notification"]["decision"] == "NOTIFY"
    assert report["notification"]["reason"] == "blocker_present"


def test_daily_check_notifies_when_fresh_signal_is_processing_not_waiting():
    module = _load_module()
    snapshot = _snapshot(
        owner_summary={
            "state": "运行中",
            "current_action": "继续保持监控",
            "runtime": "正常",
            "watcher": "运行中",
            "source_readiness": "正常",
            "dry_run_audit": "审计演练正常",
            "frontend": "已发布",
        },
    )
    snapshot["facts"]["reports"]["goal_status"] = {
        "status": "processing",
        "fresh_signal_present": True,
    }

    report = module.build_daily_check_report(snapshot=snapshot)

    assert report["status"] == "processing"
    assert report["checks"]["waiting_for_market"] is False
    assert report["checks"]["fresh_signal_notification_policy_checked"] is True
    assert report["owner_summary"]["state"] == "处理中"
    assert report["owner_summary"]["current_action"] == "等待系统完成收口"
    assert report["notification"]["decision"] == "NOTIFY"
    assert report["notification"]["reason"] == "processing"


def test_daily_check_blocks_when_remote_interaction_budget_is_exceeded():
    module = _load_module()
    snapshot = _snapshot(
        interaction={
            "level": "L1_readonly_snapshot",
            "remote_interaction_count": 2,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_exchange_write": False,
        }
    )

    report = module.build_daily_check_report(snapshot=snapshot)

    assert report["status"] == "blocked"
    assert report["interaction"]["remote_interaction_count"] == 2
    assert report["interaction"]["max_remote_interactions"] == 1
    assert report["owner_summary"]["state"] == "工程状态暂不可用"
    assert (
        "daily_check_remote_interaction_budget_exceeded:2>1"
        in report["checks"]["blockers"]
    )
    assert report["notification"]["decision"] == "NOTIFY"
    assert report["notification"]["reason"] == "blocker_present"


def test_daily_check_allows_explicitly_larger_remote_interaction_budget():
    module = _load_module()
    snapshot = _snapshot(
        interaction={
            "level": "L1_readonly_snapshot",
            "remote_interaction_count": 2,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_exchange_write": False,
        }
    )

    report = module.build_daily_check_report(
        snapshot=snapshot,
        max_remote_interactions=2,
    )

    assert report["status"] == "waiting_for_market"
    assert report["interaction"]["remote_interaction_count"] == 2
    assert report["interaction"]["max_remote_interactions"] == 2
    assert report["checks"]["blockers"] == []


def test_daily_check_heartbeat_xml_uses_dont_notify_decision():
    module = _load_module()
    report = module.build_daily_check_report(snapshot=_snapshot())

    xml = module._heartbeat_xml(report)

    assert "<automation_id>tokyo-runtime-quiet-monitor</automation_id>" in xml
    assert "<decision>DONT_NOTIFY</decision>" in xml
    assert "<message>自动化正常运行，当前没有可用市场机会</message>" in xml


def test_daily_check_heartbeat_xml_uses_notify_and_escapes_message():
    module = _load_module()
    report = module.build_daily_check_report(
        snapshot=_snapshot(
            status="blocked",
            checks={
                "blockers": ["owner_console_backend_inactive"],
                "product_gaps": [],
                "backend_active": False,
                "watcher_timer_active": True,
                "source_readiness_ready": True,
                "runtime_dry_run_audit_passed": True,
                "runtime_dry_run_required_checks_present": True,
                "runtime_dry_run_missing_required_checks": [],
            "frontend_scope": "externalized",
            },
        )
    )
    report["notification"]["message"] = "A < B & C"

    xml = module._heartbeat_xml(report)

    assert "<decision>NOTIFY</decision>" in xml
    assert "<message>A &lt; B &amp; C</message>" in xml


def test_daily_check_owner_progress_text_keeps_healthy_waiting_readable():
    module = _load_module()
    report = module.build_daily_check_report(snapshot=_snapshot())
    report["generated_at_utc"] = "2026-06-17T00:00:00+00:00"

    text = module._owner_progress_text(
        report,
        now_utc=datetime(2026, 6, 17, 0, 5, tzinfo=timezone.utc),
    )

    assert "## StrategyGroup Runtime Progress" in text
    assert "- 报告时间: 2026-06-17T00:00:00+00:00" in text
    assert "- 缓存年龄: 5m" in text
    assert "- 缓存状态: fresh" in text
    assert "- 当前阶段: 等待机会" in text
    assert "- 当前动作: 继续等待市场机会" in text
    assert "- Owner 介入: 否" in text
    assert "- 通知决策: DONT_NOTIFY" in text
    assert "- 交互等级: L1_daily_check_from_snapshot" in text
    assert "- 交互口径: 只读低交互" in text
    assert "- 远端交互次数: 1" in text
    assert "- 远端交互预算: 1" in text
    assert "- 服务器修改: 否" in text
    assert "- 接近真实订单: 否" in text
    assert "- 交易所写入: 否" in text
    assert "- Runtime: 正常" in text
    assert "- 演练场景: 14" in text
    assert "- 链路段: 22 ready / 0 missing" in text
    assert "- 入场快链: ready" in text
    assert "- 出场硬化: ready" in text
    assert "- 策略组分层: ready" in text
    assert "- Frontend: 外部项目" in text


def test_daily_check_owner_progress_text_surfaces_missing_chain_segments():
    module = _load_module()
    snapshot = _snapshot(
        facts={
            "reports": {
                "goal_status": {
                    "status": "waiting_for_signal",
                    "fresh_signal_present": False,
                },
                "runtime_dry_run_audit": {
                    "status": "passed",
                    "scenario_count": 14,
                },
                "runtime_execution_chain_closure_status": {
                    "status": "non_market_execution_chain_ready",
                    "ready_segments": ["fresh_signal_fast_auto_chain_checked"],
                    "missing_or_failed_segments": [
                        "operation_layer_evidence_relay_checked"
                    ],
                    "ready_goal_chain_segments": ["fresh_or_mock_signal"],
                    "missing_or_failed_goal_chain_segments": [
                        "official_operation_layer_evidence_handoff"
                    ],
                },
            },
        },
    )
    report = module.build_daily_check_report(snapshot=snapshot)

    text = module._owner_progress_text(report)

    assert "- 链路段: 1 ready / 1 missing" in text
    assert "- 目标链路段: 1 ready / 1 missing" in text
    assert "## Missing Chain Segments" in text
    assert "- operation_layer_evidence_relay_checked" in text
    assert "## Missing Goal Chain Segments" in text
    assert "- official_operation_layer_evidence_handoff" in text


def test_daily_check_owner_progress_text_marks_chain_segments_unknown_when_absent():
    module = _load_module()
    report = module.build_daily_check_report(snapshot=_snapshot())
    report["owner_summary"]["progress"]["chain_closure_ready_segments"] = None
    report["owner_summary"]["progress"][
        "chain_closure_missing_or_failed_segments"
    ] = []
    report["owner_summary"]["progress"]["goal_chain_ready_segments"] = None
    report["owner_summary"]["progress"][
        "goal_chain_missing_or_failed_segments"
    ] = []

    text = module._owner_progress_text(report)

    assert "- 链路段: unknown" in text
    assert "- 目标链路段: unknown" in text


def test_daily_check_owner_progress_text_surfaces_safety_blocker():
    module = _load_module()
    report = module.build_daily_check_report(
        snapshot=_snapshot(
            status="blocked",
            checks={
                "blockers": ["active_position_open_order_conflict"],
                "product_gaps": [],
                "backend_active": True,
                "watcher_timer_active": True,
                "source_readiness_ready": True,
                "runtime_dry_run_audit_passed": True,
                "runtime_dry_run_required_checks_present": True,
                "runtime_dry_run_missing_required_checks": [],
            "frontend_scope": "externalized",
            },
        )
    )

    text = module._owner_progress_text(report)

    assert "- 当前阶段: 安全边界阻断" in text
    assert "- 当前动作: 等待系统处理安全状态" in text
    assert "- Owner 介入: 是" in text
    assert "- 通知决策: NOTIFY" in text
    assert "## Blockers" in text
    assert "- active_position_open_order_conflict" in text


def test_daily_check_owner_progress_text_marks_subminute_cache_age():
    module = _load_module()
    report = module.build_daily_check_report(snapshot=_snapshot())
    report["generated_at_utc"] = "2026-06-17T00:00:30+00:00"

    text = module._owner_progress_text(
        report,
        now_utc=datetime(2026, 6, 17, 0, 0, 45, tzinfo=timezone.utc),
    )

    assert "- 缓存年龄: <1m" in text


def test_daily_check_owner_progress_text_marks_stale_hour_cache_age():
    module = _load_module()
    report = module.build_daily_check_report(snapshot=_snapshot())
    report["generated_at_utc"] = "2026-06-17T00:00:00Z"

    text = module._owner_progress_text(
        report,
        now_utc=datetime(2026, 6, 17, 2, 7, tzinfo=timezone.utc),
    )

    assert "- 缓存年龄: 2h7m" in text
    assert "- 缓存状态: stale" in text


def test_daily_check_owner_progress_text_handles_unknown_cache_age():
    module = _load_module()
    report = module.build_daily_check_report(snapshot=_snapshot())
    report["generated_at_utc"] = "not-a-date"

    text = module._owner_progress_text(report)

    assert "- 报告时间: not-a-date" in text
    assert "- 缓存年龄: unknown" in text
    assert "- 缓存状态: unknown" in text


def test_daily_check_owner_progress_text_honors_custom_cache_age_threshold():
    module = _load_module()
    report = module.build_daily_check_report(snapshot=_snapshot())
    report["generated_at_utc"] = "2026-06-17T00:00:00+00:00"

    text = module._owner_progress_text(
        report,
        now_utc=datetime(2026, 6, 17, 0, 10, tzinfo=timezone.utc),
        max_cache_age_minutes=5,
    )

    assert "- 缓存年龄: 10m" in text
    assert "- 缓存状态: stale" in text


def test_daily_check_reads_prebuilt_report_without_snapshot_probe(tmp_path, monkeypatch):
    module = _load_module()
    report = module.build_daily_check_report(snapshot=_snapshot())
    report_path = tmp_path / "daily-check.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False),
        encoding="utf-8",
    )

    def fail_if_called(**_kwargs):
        raise AssertionError("snapshot probe should not run")

    monkeypatch.setattr(module, "_run_snapshot", fail_if_called)
    args = module._parse_args(["--report-json-path", str(report_path)])

    loaded = module._build_or_read_daily_check_report(args)

    assert loaded["status"] == "waiting_for_market"
    assert loaded["interaction"]["remote_interaction_count"] == 1
    assert loaded["notification"]["decision"] == "DONT_NOTIFY"


def test_daily_check_reads_default_cache_without_snapshot_probe(tmp_path, monkeypatch):
    module = _load_module()
    report = module.build_daily_check_report(snapshot=_snapshot())
    cache_path = tmp_path / "latest-daily-check.json"
    cache_path.write_text(
        json.dumps(report, ensure_ascii=False),
        encoding="utf-8",
    )

    def fail_if_called(**_kwargs):
        raise AssertionError("snapshot probe should not run")

    monkeypatch.setattr(module, "DEFAULT_DAILY_CHECK_CACHE_JSON", cache_path)
    monkeypatch.setattr(module, "_run_snapshot", fail_if_called)
    args = module._parse_args(["--from-cache"])

    loaded = module._build_or_read_daily_check_report(args)

    assert loaded["status"] == "waiting_for_market"
    assert loaded["notification"]["decision"] == "DONT_NOTIFY"


def test_daily_check_from_cache_missing_returns_monitor_refresh_state(tmp_path, monkeypatch):
    module = _load_module()
    missing_cache_path = tmp_path / "missing-daily-check.json"

    def fail_if_called(**_kwargs):
        raise AssertionError("snapshot probe should not run")

    monkeypatch.setattr(module, "DEFAULT_DAILY_CHECK_CACHE_JSON", missing_cache_path)
    monkeypatch.setattr(module, "_run_snapshot", fail_if_called)
    args = module._parse_args(["--from-cache"])

    loaded = module._build_or_read_daily_check_report(args)

    assert loaded["status"] == "needs_refresh"
    assert loaded["interaction"]["level"] == "L0_local_cache_read"
    assert loaded["interaction"]["remote_interaction_count"] == 0
    assert loaded["notification"]["decision"] == "NOTIFY"
    assert loaded["notification"]["reason"] == "runtime_progress_cache_missing"
    assert loaded["checks"]["blockers"] == []
    assert loaded["checks"]["monitor_refresh_needed"] is True
    assert loaded["checks"]["monitor_refresh_reasons"] == [
        "runtime_progress_cache_missing"
    ]
    assert loaded["owner_summary"]["state"] == "监控状态需刷新"


def test_daily_check_require_fresh_cache_marks_stale_report_for_refresh():
    module = _load_module()
    report = module.build_daily_check_report(snapshot=_snapshot())
    report["generated_at_utc"] = "2026-06-17T00:00:00+00:00"

    gated = module._apply_cache_freshness_gate(
        report,
        require_fresh_cache=True,
        now_utc=datetime(2026, 6, 17, 0, 10, tzinfo=timezone.utc),
        max_cache_age_minutes=5,
    )

    assert gated["status"] == "needs_refresh"
    assert gated["notification"]["decision"] == "NOTIFY"
    assert gated["notification"]["reason"] == "runtime_progress_cache_stale"
    assert gated["checks"]["blockers"] == []
    assert gated["checks"]["monitor_refresh_needed"] is True
    assert gated["checks"]["monitor_refresh_reasons"] == [
        "runtime_progress_cache_stale"
    ]
    assert gated["checks"]["waiting_for_market"] is True
    assert gated["owner_summary"]["state"] == "监控状态需刷新"
    assert gated["interaction"]["level"] == "L0_local_cache_gate"
    assert gated["interaction"]["remote_interaction_count"] == 0
    assert gated["cached_report_interaction"]["remote_interaction_count"] == 1


def test_daily_check_require_fresh_cache_marks_stale_schema_for_refresh():
    module = _load_module()
    report = module.build_daily_check_report(snapshot=_snapshot())
    report["schema_version"] = module.DAILY_CHECK_REPORT_SCHEMA_VERSION - 1

    gated = module._apply_cache_freshness_gate(
        report,
        require_fresh_cache=True,
        now_utc=datetime.now(timezone.utc),
        max_cache_age_minutes=module.DEFAULT_MAX_CACHE_AGE_MINUTES,
    )

    assert gated["status"] == "needs_refresh"
    assert gated["notification"]["decision"] == "NOTIFY"
    assert gated["notification"]["reason"] == "runtime_progress_cache_schema_stale"
    assert gated["checks"]["blockers"] == []
    assert gated["checks"]["monitor_refresh_needed"] is True
    assert gated["checks"]["monitor_refresh_reasons"] == [
        "runtime_progress_cache_schema_stale"
    ]
    assert gated["owner_summary"]["state"] == "监控状态需刷新"
    assert gated["owner_summary"]["current_action"] == "刷新本地 runtime monitor 缓存"
    assert gated["interaction"]["level"] == "L0_local_cache_gate"
    assert gated["interaction"]["remote_interaction_count"] == 0
    assert gated["cached_report_interaction"]["remote_interaction_count"] == 1


def test_daily_check_require_fresh_cache_marks_runtime_head_mismatch_for_refresh():
    module = _load_module()
    report = module.build_daily_check_report(snapshot=_snapshot())
    report["generated_at_utc"] = datetime(
        2026,
        6,
        17,
        0,
        0,
        tzinfo=timezone.utc,
    ).isoformat()

    gated = module._apply_cache_freshness_gate(
        report,
        require_fresh_cache=True,
        now_utc=datetime(2026, 6, 17, 0, 1, tzinfo=timezone.utc),
        max_cache_age_minutes=5,
        expected_runtime_head="runtime-head-2",
    )

    assert gated["status"] == "needs_refresh"
    assert gated["notification"]["decision"] == "NOTIFY"
    assert (
        gated["notification"]["reason"]
        == "runtime_progress_cache_runtime_head_stale"
    )
    assert gated["checks"]["blockers"] == []
    assert gated["checks"]["monitor_refresh_needed"] is True
    assert gated["checks"]["monitor_refresh_reasons"] == [
        "runtime_progress_cache_runtime_head_stale"
    ]
    assert gated["interaction"]["level"] == "L0_local_cache_gate"


def test_daily_check_writes_owner_progress_output(tmp_path, capsys):
    module = _load_module()
    snapshot_path = tmp_path / "snapshot.json"
    output_path = tmp_path / "owner-progress.md"
    snapshot_path.write_text(
        json.dumps(_snapshot(), ensure_ascii=False),
        encoding="utf-8",
    )

    exit_code = module.main(
        [
            "--snapshot-json-path",
            str(snapshot_path),
            "--output-owner-progress",
            str(output_path),
            "--owner-progress",
        ]
    )

    captured = capsys.readouterr()
    output_text = output_path.read_text(encoding="utf-8")
    assert exit_code == 0
    assert "- 当前阶段: 等待机会" in output_text
    assert "- 缓存状态: fresh" in output_text
    assert "- 实盘矩阵: 1 pass / 1 waiting / 0 blocked" in output_text
    assert "- 通知决策: DONT_NOTIFY" in output_text
    assert captured.out == output_text


def test_daily_check_writes_outputs_atomically(tmp_path, capsys):
    module = _load_module()
    snapshot_path = tmp_path / "snapshot.json"
    output_json = tmp_path / "latest-daily-check.json"
    output_md = tmp_path / "latest-owner-progress.md"
    snapshot_path.write_text(
        json.dumps(_snapshot(), ensure_ascii=False),
        encoding="utf-8",
    )

    exit_code = module.main(
        [
            "--snapshot-json-path",
            str(snapshot_path),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
            "--owner-progress",
        ]
    )

    capsys.readouterr()
    assert exit_code == 0
    assert json.loads(output_json.read_text(encoding="utf-8"))["status"] == (
        "waiting_for_market"
    )
    assert "目标链路段: 7 ready / 0 missing" in output_md.read_text(
        encoding="utf-8"
    )
    assert list(tmp_path.glob(".latest-daily-check.json.*.tmp")) == []
    assert list(tmp_path.glob(".latest-owner-progress.md.*.tmp")) == []


def test_daily_check_from_cache_owner_progress_separates_read_from_collection(
    tmp_path, monkeypatch, capsys
):
    module = _load_module()
    cache_path = tmp_path / "latest-daily-check.json"
    report = module.build_daily_check_report(snapshot=_snapshot())
    cache_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("cache-only progress must not probe Tokyo")

    monkeypatch.setattr(module, "DEFAULT_DAILY_CHECK_CACHE_JSON", cache_path)
    monkeypatch.setattr(module, "_run_snapshot", fail_if_called)

    exit_code = module.main(
        [
            "--from-cache",
            "--require-fresh-cache",
            "--owner-progress",
            "--expected-runtime-head",
            "runtime-head-1",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "- 本次读取等级: L0_local_cache_read" in captured.out
    assert "- 本次读取口径: 本地读取" in captured.out
    assert "- 本次远端交互次数: 0" in captured.out
    assert "- 报告采集等级: L1_daily_check_from_snapshot" in captured.out
    assert "- 报告采集口径: 只读低交互" in captured.out
    assert "- 报告采集远端交互次数: 1" in captured.out
    assert "- 远端交互次数: 1" not in captured.out


def test_daily_check_auto_cache_uses_fresh_cache_without_snapshot_probe(
    tmp_path, monkeypatch, capsys
):
    module = _load_module()
    cache_path = tmp_path / "latest-daily-check.json"
    owner_progress_path = tmp_path / "latest-owner-progress.md"
    report = module.build_daily_check_report(snapshot=_snapshot())
    report["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    cache_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("fresh auto-cache progress must not probe Tokyo")

    monkeypatch.setattr(module, "DEFAULT_DAILY_CHECK_CACHE_JSON", cache_path)
    monkeypatch.setattr(
        module,
        "DEFAULT_DAILY_CHECK_OWNER_PROGRESS_MD",
        owner_progress_path,
    )
    monkeypatch.setattr(module, "_run_snapshot", fail_if_called)

    exit_code = module.main(
        [
            "--auto-cache",
            "--owner-progress",
            "--expected-runtime-head",
            "runtime-head-1",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "- 本次读取等级: L0_local_cache_read" in captured.out
    assert "- 本次远端交互次数: 0" in captured.out
    assert "- 报告采集远端交互次数: 1" in captured.out
    assert not owner_progress_path.exists()


def test_daily_check_auto_cache_refreshes_fresh_monitor_refresh_report(
    tmp_path, monkeypatch, capsys
):
    module = _load_module()
    cache_path = tmp_path / "latest-daily-check.json"
    owner_progress_path = tmp_path / "latest-owner-progress.md"
    refresh_report = module._cache_unavailable_report(
        reason="runtime_progress_cache_missing",
        detail="cache not found",
    )
    refresh_report["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    cache_path.write_text(
        json.dumps(refresh_report, ensure_ascii=False),
        encoding="utf-8",
    )
    calls = []

    def one_snapshot(**kwargs):
        calls.append(kwargs)
        return _snapshot()

    monkeypatch.setattr(module, "DEFAULT_DAILY_CHECK_CACHE_JSON", cache_path)
    monkeypatch.setattr(
        module,
        "DEFAULT_DAILY_CHECK_OWNER_PROGRESS_MD",
        owner_progress_path,
    )
    monkeypatch.setattr(module, "_run_snapshot", one_snapshot)

    exit_code = module.main(["--auto-cache", "--owner-progress"])

    captured = capsys.readouterr()
    refreshed = json.loads(cache_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert len(calls) == 1
    assert refreshed["status"] == "waiting_for_market"
    assert refreshed["checks"].get("monitor_refresh_needed") is not True
    assert "- 交互等级: L1_daily_check_from_snapshot" in captured.out
    assert owner_progress_path.exists()


def test_daily_check_auto_cache_refreshes_stale_cache_once_and_writes_outputs(
    tmp_path, monkeypatch, capsys
):
    module = _load_module()
    cache_path = tmp_path / "latest-daily-check.json"
    owner_progress_path = tmp_path / "latest-owner-progress.md"
    stale_report = module.build_daily_check_report(snapshot=_snapshot())
    stale_report["generated_at_utc"] = "2026-06-17T00:00:00+00:00"
    cache_path.write_text(
        json.dumps(stale_report, ensure_ascii=False),
        encoding="utf-8",
    )
    calls = []

    def one_snapshot(**kwargs):
        calls.append(kwargs)
        return _snapshot()

    monkeypatch.setattr(module, "DEFAULT_DAILY_CHECK_CACHE_JSON", cache_path)
    monkeypatch.setattr(
        module,
        "DEFAULT_DAILY_CHECK_OWNER_PROGRESS_MD",
        owner_progress_path,
    )
    monkeypatch.setattr(module, "_run_snapshot", one_snapshot)

    exit_code = module.main(
        ["--auto-cache", "--owner-progress", "--max-cache-age-minutes", "5"]
    )

    captured = capsys.readouterr()
    refreshed = json.loads(cache_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert len(calls) == 1
    assert refreshed["status"] == "waiting_for_market"
    assert refreshed["interaction"]["remote_interaction_count"] == 1
    assert "- 交互等级: L1_daily_check_from_snapshot" in captured.out
    assert "- 本次读取等级: L0_local_cache_read" not in captured.out
    assert owner_progress_path.exists()
    assert "- 当前阶段: 等待机会" in owner_progress_path.read_text(
        encoding="utf-8"
    )


def test_daily_check_auto_cache_refreshes_runtime_head_mismatch_once(
    tmp_path, monkeypatch, capsys
):
    module = _load_module()
    cache_path = tmp_path / "latest-daily-check.json"
    owner_progress_path = tmp_path / "latest-owner-progress.md"
    stale_head_report = module.build_daily_check_report(snapshot=_snapshot())
    stale_head_report["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    cache_path.write_text(
        json.dumps(stale_head_report, ensure_ascii=False),
        encoding="utf-8",
    )
    calls = []

    def one_snapshot(**kwargs):
        calls.append(kwargs)
        assert kwargs["expected_runtime_head"] == "runtime-head-2"
        return _snapshot(
            inputs={
                "expected_runtime_head": "runtime-head-2",
                "expected_frontend_head": None,
            },
            facts={
                "release": {
                    "head": "runtime-head-2",
                    "current_realpath": (
                        "/home/ubuntu/brc-deploy/releases/"
                        "brc-runtime-governance-runtime-head-2"
                    ),
                },
                "reports": _snapshot()["facts"]["reports"],
            },
        )

    monkeypatch.setattr(module, "DEFAULT_DAILY_CHECK_CACHE_JSON", cache_path)
    monkeypatch.setattr(
        module,
        "DEFAULT_DAILY_CHECK_OWNER_PROGRESS_MD",
        owner_progress_path,
    )
    monkeypatch.setattr(module, "_run_snapshot", one_snapshot)

    exit_code = module.main(
        [
            "--auto-cache",
            "--owner-progress",
            "--expected-runtime-head",
            "runtime-head-2",
        ]
    )

    captured = capsys.readouterr()
    refreshed = json.loads(cache_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert len(calls) == 1
    assert refreshed["source"]["runtime_head"] == "runtime-head-2"
    assert refreshed["source"]["expected_runtime_head"] == "runtime-head-2"
    assert "- 交互等级: L1_daily_check_from_snapshot" in captured.out
    assert "- 本次读取等级: L0_local_cache_read" not in captured.out
    assert owner_progress_path.exists()


def test_daily_check_resolves_expected_heads_from_baseline_file(tmp_path):
    module = _load_module()
    baseline = tmp_path / "runtime-monitor-baseline.json"
    baseline.write_text(
        """
{
  "expected_runtime_head": "runtime-head-from-file"
}
""".strip(),
        encoding="utf-8",
    )

    args = module._parse_args(["--baseline-json", str(baseline)])

    assert module._resolve_expected_heads(args) == {
        "expected_runtime_head": "runtime-head-from-file",
        "expected_frontend_head": None,
    }


def test_daily_check_resolves_local_git_head_sentinel_from_baseline_file(
    tmp_path, monkeypatch
):
    module = _load_module()
    baseline = tmp_path / "runtime-monitor-baseline.json"
    baseline.write_text(
        """
{
  "expected_runtime_head": "LOCAL_GIT_HEAD"
}
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "_local_git_head", lambda: "runtime-head-from-git")

    args = module._parse_args(["--baseline-json", str(baseline)])

    assert module._resolve_expected_heads(args) == {
        "expected_runtime_head": "runtime-head-from-git",
        "expected_frontend_head": None,
    }


def test_daily_check_explicit_expected_heads_override_baseline_file(tmp_path):
    module = _load_module()
    baseline = tmp_path / "runtime-monitor-baseline.json"
    baseline.write_text(
        """
{
  "expected_runtime_head": "runtime-head-from-file",
  "expected_frontend_head": "frontend-head-from-file"
}
""".strip(),
        encoding="utf-8",
    )

    args = module._parse_args(
        [
            "--baseline-json",
            str(baseline),
            "--expected-runtime-head",
            "runtime-head-from-cli",
            "--expected-frontend-head",
            "frontend-head-from-cli",
        ]
    )

    assert module._resolve_expected_heads(args) == {
        "expected_runtime_head": "runtime-head-from-cli",
        "expected_frontend_head": "frontend-head-from-cli",
    }


def test_runtime_monitor_baseline_defaults_to_low_interaction_auto_cache():
    baseline = json.loads(RUNTIME_MONITOR_BASELINE_PATH.read_text(encoding="utf-8"))

    assert baseline["default_check"].endswith(
        "run_strategygroup_runtime_daily_check.py --auto-cache --json"
    )
    assert baseline["heartbeat_check"].endswith(
        "run_strategygroup_runtime_daily_check.py "
        "--auto-cache --heartbeat "
        "--output-json output/runtime-monitor/latest-daily-check.json "
        "--output-owner-progress output/runtime-monitor/latest-owner-progress.md"
    )
    assert baseline["routine_status_check"].endswith(
        "run_strategygroup_runtime_daily_check.py --auto-cache --owner-progress"
    )
    assert baseline["strict_no_server_check"].endswith(
        "run_strategygroup_runtime_daily_check.py "
        "--from-cache --require-fresh-cache --owner-progress"
    )
    assert baseline["forced_refresh_check"].endswith(
        "run_strategygroup_runtime_daily_check.py --json"
    )
    assert baseline["deploy_session_postdeploy_check"].endswith(
        "run_tokyo_runtime_deploy_session.py "
        "--run-daily-check --daily-check-mode fresh --json"
    )
    assert baseline["deploy_session_routine_check"].endswith(
        "run_tokyo_runtime_deploy_session.py "
        "--run-daily-check --daily-check-mode auto-cache --json"
    )
    assert baseline["deploy_session_owner_progress_check"].endswith(
        "run_tokyo_runtime_deploy_session.py "
        "--run-daily-check --daily-check-mode cache --owner-progress"
    )
    assert baseline["goal_progress_audit_check"].endswith(
        "run_strategygroup_runtime_goal_progress_audit.py "
        "--owner-progress "
        "--output-json output/runtime-monitor/latest-goal-progress.json "
        "--output-owner-progress output/runtime-monitor/latest-goal-progress.md"
    )
    assert baseline["local_monitor_sequence_check"].endswith(
        "run_strategygroup_runtime_local_monitor_sequence.py "
        "--daily-check-mode cache "
        "--owner-progress "
        "--output-json output/runtime-monitor/latest-local-monitor-sequence.json "
        "--output-owner-progress output/runtime-monitor/latest-local-monitor-sequence.md"
    )
    assert baseline["quiet_monitor_audit_check"].endswith(
        "audit_tokyo_runtime_quiet_monitor.py "
        "--owner-progress "
        "--output-json output/runtime-monitor/latest-quiet-monitor-audit.json "
        "--output-owner-progress output/runtime-monitor/latest-quiet-monitor-audit.md"
    )
    assert baseline["signal_detection_source"] == (
        "tokyo_runtime_signal_watcher_feishu_webhook"
    )
    assert baseline["interaction_policy"]["default_level"] == "L0_local_cache_read"
    assert baseline["interaction_policy"]["remote_interaction_count"] == 0
    assert baseline["interaction_policy"]["refresh_level"] == (
        "L1_daily_check_from_snapshot"
    )
    assert baseline["interaction_policy"]["refresh_remote_interaction_count"] == 1
    assert baseline["interaction_policy"][
        "deploy_postdeploy_daily_check_remote_interaction_count"
    ] == 1
    assert baseline["interaction_policy"]["goal_progress_audit_remote_interaction_count"] == 0
    assert baseline["interaction_policy"]["local_monitor_sequence_remote_interaction_count"] == 0
    assert baseline["interaction_policy"]["quiet_monitor_audit_remote_interaction_count"] == 0
