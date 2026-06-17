from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DAILY_CHECK_SCRIPT_PATH = REPO_ROOT / "scripts" / "run_strategygroup_runtime_daily_check.py"


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
        "owner_summary": {
            "state": "等待机会",
            "current_action": "继续等待市场机会",
            "runtime": "正常",
            "watcher": "运行中",
            "source_readiness": "正常",
            "dry_run_audit": "审计演练正常",
            "frontend": "已发布",
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
            "frontend_release_present": True,
            "frontend_index_present": True,
        },
        "facts": {
            "reports": {
                "goal_status": {
                    "status": "waiting_for_signal",
                    "fresh_signal_present": False,
                },
            },
        },
    }
    base.update(overrides)
    return base


def test_daily_check_keeps_healthy_waiting_for_market_low_noise():
    module = _load_module()

    report = module.build_daily_check_report(snapshot=_snapshot())

    assert report["status"] == "waiting_for_market"
    assert report["owner_summary"]["state"] == "等待机会"
    assert report["owner_summary"]["current_action"] == "继续等待市场机会"
    assert report["owner_summary"]["owner_intervention_required"] is False
    assert report["owner_summary"]["visibility"]["category"] == "waiting_for_market"
    assert report["interaction"]["level"] == "L1_daily_check_from_snapshot"
    assert report["interaction"]["remote_interaction_count"] == 1
    assert report["interaction"]["mutates_remote_files"] is False
    assert report["interaction"]["approaches_real_order"] is False
    assert report["checks"]["blockers"] == []
    assert report["checks"]["waiting_for_market"] is True
    assert report["checks"]["runtime_dry_run_required_checks_present"] is True
    assert report["checks"]["runtime_dry_run_missing_required_checks"] == []
    assert report["notification"] == {
        "decision": "DONT_NOTIFY",
        "reason": "healthy_waiting_for_market",
        "message": "自动化正常运行，当前没有 fresh signal",
        "owner_intervention_required": False,
    }


def test_daily_check_marks_frontend_gap_as_degraded_not_safety_blocked():
    module = _load_module()
    snapshot = _snapshot(
        checks={
            "blockers": [],
            "product_gaps": ["frontend_release_missing"],
            "backend_active": True,
            "watcher_timer_active": True,
            "source_readiness_ready": True,
            "runtime_dry_run_audit_passed": True,
            "runtime_dry_run_required_checks_present": True,
            "runtime_dry_run_missing_required_checks": [],
            "frontend_release_present": False,
            "frontend_index_present": True,
        }
    )

    report = module.build_daily_check_report(snapshot=snapshot)

    assert report["status"] == "degraded"
    assert report["owner_summary"]["state"] == "工程状态暂不可用"
    assert report["owner_summary"]["visibility"]["category"] == "engineering_blocker"
    assert report["owner_summary"]["current_action"] == (
        "修复 Owner Console 产品发布缺口"
    )
    assert report["owner_summary"]["owner_intervention_required"] is False
    assert report["checks"]["warnings"] == ["product_gap:frontend_release_missing"]
    assert report["checks"]["blockers"] == []
    assert report["notification"]["decision"] == "NOTIFY"
    assert report["notification"]["reason"] == "product_gap_present"


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
            "frontend_release_present": True,
            "frontend_index_present": True,
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
            "frontend_release_present": True,
            "frontend_index_present": True,
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
            "frontend_release_present": True,
            "frontend_index_present": True,
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


def test_daily_check_notifies_when_runtime_is_ready_not_waiting():
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
        facts={
            "reports": {
                "goal_status": {
                    "status": "processing",
                    "fresh_signal_present": True,
                },
            },
        },
    )

    report = module.build_daily_check_report(snapshot=snapshot)

    assert report["status"] == "ready"
    assert report["checks"]["waiting_for_market"] is False
    assert report["notification"]["decision"] == "NOTIFY"
    assert report["notification"]["reason"] == "running"


def test_daily_check_resolves_expected_heads_from_baseline_file(tmp_path):
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

    args = module._parse_args(["--baseline-json", str(baseline)])

    assert module._resolve_expected_heads(args) == {
        "expected_runtime_head": "runtime-head-from-file",
        "expected_frontend_head": "frontend-head-from-file",
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
