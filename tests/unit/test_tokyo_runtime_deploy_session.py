from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_tokyo_runtime_deploy_session.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "run_tokyo_runtime_deploy_session",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _deploy_report(**overrides):
    base = {
        "status": "applied",
        "scope": "tokyo_runtime_governance_git_deploy_execution",
        "interaction": {
            "level": "L3_bounded_deploy_apply",
            "remote_interaction_count": 7,
            "mutates_remote_files": True,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "owner_summary": {
            "state": "部署完成",
            "current_action": "运行 L1 快照核验",
        },
        "checks": {
            "blockers": [],
            "warnings": [],
            "product_gaps": [],
        },
        "effects": {
            "remote_files_modified": True,
            "exchange_write_called": False,
            "order_created": False,
        },
    }
    base.update(overrides)
    return base


def _frontend_report(**overrides):
    base = {
        "status": "applied",
        "scope": "owner_console_frontend_homepage_publish",
        "interaction": {
            "level": "L3_frontend_static_publish",
            "remote_interaction_count": 1,
            "mutates_remote_files": True,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "owner_summary": {
            "state": "首页已发布",
            "current_action": "运行 L1 快照核验 frontend-release.json",
        },
        "checks": {
            "blockers": [],
            "warnings": [],
            "product_gaps": [],
        },
    }
    base.update(overrides)
    return base


def _daily_check_report(**overrides):
    base = {
        "status": "waiting_for_market",
        "scope": "strategygroup_runtime_daily_check",
        "interaction": {
            "level": "L1_daily_check_from_snapshot",
            "remote_interaction_count": 1,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "owner_summary": {
            "state": "等待机会",
            "current_action": "继续等待市场机会",
        },
        "checks": {
            "blockers": [],
            "warnings": [],
            "product_gaps": [],
            "waiting_for_market": True,
        },
    }
    base.update(overrides)
    return base


def test_deploy_session_summarizes_l3_deploy_plus_l1_check():
    module = _load_module()

    report = module.build_deploy_session_report(
        reports=[
            ("runtime_deploy", _deploy_report()),
            ("frontend_publish", _frontend_report()),
            ("postdeploy_daily_check", _daily_check_report()),
        ]
    )

    assert report["status"] == "waiting_for_market"
    assert report["interaction"]["level"] == "L3_bounded_deploy_apply"
    assert report["interaction"]["policy"]["owner_label"] == "有界服务器变更"
    assert report["interaction"]["policy"]["remote_mutation_allowed"] is True
    assert report["interaction"]["policy"]["exchange_write_allowed"] is False
    assert report["interaction"]["remote_interaction_count"] == 9
    assert report["interaction"]["mutates_remote_files"] is True
    assert report["interaction"]["approaches_real_order"] is False
    assert report["interaction"]["calls_exchange_write"] is False
    assert report["interaction"]["places_order"] is False
    assert report["owner_summary"]["state"] == "等待机会"
    assert report["owner_summary"]["server_mutation"] == "yes"
    assert report["owner_summary"]["real_order_approach"] == "no"
    assert report["checks"]["all_steps_safe_for_deploy_session_summary"] is True


def test_deploy_session_surfaces_product_gap_without_safety_blocking():
    module = _load_module()

    report = module.build_deploy_session_report(
        reports=[
            (
                "frontend_publish",
                _frontend_report(
                    status="dry_run_ready",
                    interaction={
                        "level": "L1_publish_plan_only",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                    checks={
                        "blockers": [],
                        "warnings": [],
                        "product_gaps": ["frontend_release_missing"],
                    },
                ),
            ),
        ]
    )

    assert report["status"] == "degraded"
    assert report["owner_summary"]["owner_intervention_required"] is False
    assert report["owner_summary"]["current_action"] == (
        "修复 Owner Console 首页发布缺口"
    )
    assert report["checks"]["product_gaps"] == ["frontend_release_missing"]
    assert report["checks"]["blockers"] == []


def test_deploy_session_blocks_if_any_step_blocks():
    module = _load_module()

    report = module.build_deploy_session_report(
        reports=[
            (
                "postdeploy_daily_check",
                _daily_check_report(
                    status="blocked",
                    checks={
                        "blockers": ["source_readiness_not_ready"],
                        "warnings": [],
                        "product_gaps": [],
                    },
                ),
            )
        ]
    )

    assert report["status"] == "blocked"
    assert report["owner_summary"]["state"] == "暂不可用"
    assert report["owner_summary"]["owner_intervention_required"] is True
    assert report["checks"]["blockers"] == ["source_readiness_not_ready"]


def test_deploy_session_uses_current_read_interaction_for_cache_only_status():
    module = _load_module()
    cached_daily_check = _daily_check_report(
        current_read_interaction={
            "level": "L0_local_cache_read",
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_exchange_write": False,
            "places_order": False,
        }
    )

    report = module.build_deploy_session_report(
        reports=[("postdeploy_daily_check", cached_daily_check)]
    )

    assert report["status"] == "waiting_for_market"
    assert report["interaction"]["level"] == "L0_local_cache_read"
    assert report["interaction"]["policy"]["owner_label"] == "本地读取"
    assert report["interaction"]["remote_interaction_count"] == 0
    assert report["steps"][0]["interaction_level"] == "L0_local_cache_read"
    assert report["steps"][0]["collected_interaction_level"] == (
        "L1_daily_check_from_snapshot"
    )


def test_deploy_session_owner_progress_text_is_owner_readable():
    module = _load_module()
    cached_daily_check = _daily_check_report(
        current_read_interaction={
            "level": "L0_local_cache_read",
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_exchange_write": False,
            "places_order": False,
        }
    )
    report = module.build_deploy_session_report(
        reports=[("postdeploy_daily_check", cached_daily_check)]
    )

    text = module._owner_progress_text(report)

    assert "## Tokyo Runtime Deploy Session Progress" in text
    assert "- 当前阶段: 等待机会" in text
    assert "- 当前动作: 继续等待市场机会" in text
    assert "- 交互等级: L0_local_cache_read" in text
    assert "- 远端交互次数: 0" in text
    assert "- 服务器修改: 否" in text
    assert "- 接近真实订单: 否" in text
    assert "| postdeploy_daily_check | waiting_for_market | L0_local_cache_read | 0 | 否 | 否 | 继续等待市场机会 |" in text


def test_run_daily_check_defaults_to_fresh_snapshot(monkeypatch):
    module = _load_module()
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(_daily_check_report()),
            stderr="",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    report = module._run_daily_check(
        expected_runtime_head="runtime-head",
        expected_frontend_head="frontend-head",
        mode="fresh",
    )

    assert report["status"] == "waiting_for_market"
    assert "--auto-cache" not in calls[0]
    assert "--from-cache" not in calls[0]
    assert "--expected-runtime-head" in calls[0]
    assert "--expected-frontend-head" in calls[0]


def test_run_daily_check_can_use_auto_cache_for_routine_status(monkeypatch):
    module = _load_module()
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(_daily_check_report()),
            stderr="",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    report = module._run_daily_check(
        expected_runtime_head=None,
        expected_frontend_head=None,
        mode="auto-cache",
    )

    assert report["status"] == "waiting_for_market"
    assert "--auto-cache" in calls[0]
    assert "--from-cache" not in calls[0]


def test_run_daily_check_can_use_strict_cache_without_server(monkeypatch):
    module = _load_module()
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(_daily_check_report()),
            stderr="",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    report = module._run_daily_check(
        expected_runtime_head=None,
        expected_frontend_head=None,
        mode="cache",
    )

    assert report["status"] == "waiting_for_market"
    assert "--from-cache" in calls[0]
    assert "--require-fresh-cache" in calls[0]
    assert "--auto-cache" not in calls[0]
