from __future__ import annotations

import json
from pathlib import Path


def test_runtime_monitor_baseline_uses_low_frequency_for_healthy_waiting_market() -> None:
    baseline = json.loads(
        Path("docs/current/RUNTIME_MONITOR_BASELINE.json").read_text(encoding="utf-8")
    )

    frequency = baseline["quiet_monitor_frequency_policy"]
    assert frequency["healthy_waiting_for_market_interval_minutes"] == 10
    assert frequency["healthy_waiting_for_market_interaction_level"] == (
        "L1_tokyo_server_readonly_monitor"
    )
    assert frequency["healthy_waiting_for_market_remote_interaction_count"] == 0
    assert frequency["fresh_signal_short_window_interval_minutes"] in [5, 10]
    assert frequency["fresh_signal_short_window_enabled"] is True
    assert frequency["server_side_timer_is_production_owner"] is True
    assert frequency["non_quiet_summary_required_fields"] == [
        "interaction_level",
        "remote_interaction_count",
        "mutates_remote_files",
        "approaches_real_order",
    ]
    server_side_monitor_check = baseline["server_side_runtime_monitor_check"]
    assert server_side_monitor_check.startswith(
        "python3 scripts/run_tokyo_runtime_server_monitor.py "
    )
    assert "--require-database-url" in server_side_monitor_check
    assert "--dedupe-state-json" not in server_side_monitor_check
    assert "--candidate-pool-json" not in server_side_monitor_check
    assert "--daily-table-json" not in server_side_monitor_check
    assert baseline["server_side_runtime_monitor_service"] == (
        "brc-runtime-monitor.service"
    )
    assert baseline["server_side_runtime_monitor_timer"] == (
        "brc-runtime-monitor.timer"
    )
    assert baseline["signal_detection_source"] == "tokyo_server_side_runtime_monitor_feishu"
    for removed_key in [
        "default_check",
        "heartbeat_check",
        "routine_status_check",
        "strict_no_server_check",
        "forced_refresh_check",
        "local_monitor_sequence_check",
        "quiet_monitor_audit_check",
    ]:
        assert removed_key not in baseline
