from __future__ import annotations

import argparse
import json

from scripts import runtime_active_position_resolution_from_reports
from tests.unit.test_runtime_active_position_resolution import (
    NOW_MS,
    _exit_plan,
    _followup,
    _monitor,
)


def test_resolution_from_reports_handles_noisy_json_prefix(tmp_path):
    monitor_path = tmp_path / "monitor.json"
    exit_path = tmp_path / "exit.json"
    followup_path = tmp_path / "followup.json"
    monitor_path.write_text(
        json.dumps({"artifact": _monitor().model_dump(mode="json")}),
        encoding="utf-8",
    )
    exit_path.write_text(
        "[2026-06-12] [INFO] noisy log line\n"
        + json.dumps({"plan": _exit_plan().model_dump(mode="json")}),
        encoding="utf-8",
    )
    followup_path.write_text(
        json.dumps({"artifact": _followup().model_dump(mode="json")}),
        encoding="utf-8",
    )

    artifact = runtime_active_position_resolution_from_reports._build_artifact(
        argparse.Namespace(
            live_position_monitor_json=str(monitor_path),
            position_exit_plan_json=str(exit_path),
            post_close_followup_json=str(followup_path),
            now_ms=NOW_MS,
        )
    )

    assert artifact["status"] == "hold_with_hard_stop"
    assert artifact["artifact"]["next_attempt_blocked_by_active_position"] is True
    assert artifact["artifact"]["full_reduce_only_close_feasible"] is True
    assert artifact["safety_invariants"]["exchange_called"] is False
    assert artifact["safety_invariants"]["order_lifecycle_called"] is False
