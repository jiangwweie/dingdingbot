from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "audit_tokyo_runtime_quiet_monitor.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "audit_tokyo_runtime_quiet_monitor",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _baseline():
    return {
        "heartbeat_check": "python3 scripts/run_strategygroup_runtime_daily_check.py --auto-cache --heartbeat --output-json output/runtime-monitor/latest-daily-check.json --output-owner-progress output/runtime-monitor/latest-owner-progress.md",
        "goal_progress_audit_check": "python3 scripts/run_strategygroup_runtime_goal_progress_audit.py --owner-progress --output-json output/runtime-monitor/latest-goal-progress.json --output-owner-progress output/runtime-monitor/latest-goal-progress.md",
        "p0_completion_audit_check": "python3 scripts/runtime_first_bounded_live_order_completion_audit.py --owner-progress --output-json output/runtime-monitor/latest-p0-live-order-closure-completion-audit.json --output-owner-progress output/runtime-monitor/latest-p0-live-order-closure-completion-audit.md",
        "local_monitor_sequence_check": "python3 scripts/run_strategygroup_runtime_local_monitor_sequence.py --daily-check-mode cache --owner-progress --output-json output/runtime-monitor/latest-local-monitor-sequence.json --output-owner-progress output/runtime-monitor/latest-local-monitor-sequence.md",
    }


def _prompt_text():
    return (
        "python3 scripts/run_strategygroup_runtime_local_monitor_sequence.py "
        "--daily-check-mode cache --owner-progress "
        "--output-json output/runtime-monitor/latest-local-monitor-sequence.json "
        "--output-owner-progress output/runtime-monitor/latest-local-monitor-sequence.md "
        "DONT_NOTIFY waiting_for_market not_complete_waiting_for_market "
        "blockers none non-market gaps none remote interaction count 0 "
        "fresh/runtime-ready signal "
        "Do not advance frontend or historical-debt cleanup"
    )


def test_quiet_monitor_audit_passes_when_prompt_matches_baseline(tmp_path):
    module = _load_module()

    report = module.build_quiet_monitor_audit(
        baseline=_baseline(),
        automation_text=_prompt_text(),
        automation_path=tmp_path / "automation.toml",
    )

    assert report["status"] == "ready"
    assert report["interaction"]["level"] == "L0_local_automation_audit"
    assert report["interaction"]["remote_interaction_count"] == 0
    assert report["checks"]["blockers"] == []
    assert all(check["status"] == "pass" for check in report["required_checks"])
    checks = {check["id"]: check for check in report["required_checks"]}
    assert checks["p0_completion_audit_check_registered"]["status"] == "pass"
    assert checks["local_monitor_sequence_check_registered"]["status"] == "pass"


def test_quiet_monitor_audit_blocks_when_local_sequence_command_missing(tmp_path):
    module = _load_module()
    text = _prompt_text().replace(
        _baseline()["local_monitor_sequence_check"],
        "python3 missing.py",
    )

    report = module.build_quiet_monitor_audit(
        baseline=_baseline(),
        automation_text=text,
        automation_path=tmp_path / "automation.toml",
    )

    assert report["status"] == "blocked"
    assert "local_monitor_sequence_check" in report["checks"]["blockers"]
    checks = {check["id"]: check for check in report["required_checks"]}
    assert checks["local_monitor_sequence_check"]["status"] == "fail"


def test_quiet_monitor_audit_blocks_when_p0_completion_audit_unregistered(tmp_path):
    module = _load_module()
    baseline = dict(_baseline())
    baseline["p0_completion_audit_check"] = ""

    report = module.build_quiet_monitor_audit(
        baseline=baseline,
        automation_text=_prompt_text(),
        automation_path=tmp_path / "automation.toml",
    )

    assert report["status"] == "blocked"
    assert "p0_completion_audit_check_registered" in report["checks"]["blockers"]
    checks = {check["id"]: check for check in report["required_checks"]}
    assert checks["p0_completion_audit_check_registered"]["status"] == "fail"


def test_quiet_monitor_audit_blocks_when_p0_completion_audit_uses_remote_probe(tmp_path):
    module = _load_module()
    baseline = dict(_baseline())
    baseline["p0_completion_audit_check"] += " && ssh tokyo.example true"

    report = module.build_quiet_monitor_audit(
        baseline=baseline,
        automation_text=_prompt_text(),
        automation_path=tmp_path / "automation.toml",
    )

    assert report["status"] == "blocked"
    assert "p0_completion_audit_check_registered" in report["checks"]["blockers"]


def test_quiet_monitor_owner_progress_is_readable(tmp_path):
    module = _load_module()
    report = module.build_quiet_monitor_audit(
        baseline=_baseline(),
        automation_text=_prompt_text(),
        automation_path=tmp_path / "automation.toml",
    )

    text = module._owner_progress_text(report)

    assert "## Tokyo Runtime Quiet Monitor Audit" in text
    assert "- 当前阶段: 自动化配置已对齐" in text
    assert "- 交互等级: L0_local_automation_audit" in text
    assert "- 远端交互次数: 0" in text
    assert "| local_monitor_sequence_check | pass |" in text


def test_quiet_monitor_cli_writes_json_and_owner_progress(tmp_path):
    module = _load_module()
    baseline_path = tmp_path / "baseline.json"
    automation_path = tmp_path / "automation.toml"
    output_json = tmp_path / "quiet-monitor-audit.json"
    output_md = tmp_path / "quiet-monitor-audit.md"
    baseline_path.write_text(
        json.dumps(_baseline(), ensure_ascii=False),
        encoding="utf-8",
    )
    automation_path.write_text(_prompt_text(), encoding="utf-8")

    exit_code = module.main(
        [
            "--baseline-json",
            str(baseline_path),
            "--automation-toml",
            str(automation_path),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
            "--owner-progress",
        ]
    )

    assert exit_code == 0
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["status"] == "ready"
    assert payload["interaction"]["remote_interaction_count"] == 0
    progress = output_md.read_text(encoding="utf-8")
    assert "## Tokyo Runtime Quiet Monitor Audit" in progress
    assert "- Blockers: none" in progress
