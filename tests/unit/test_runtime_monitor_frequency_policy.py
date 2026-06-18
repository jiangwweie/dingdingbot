from __future__ import annotations

import json
from pathlib import Path


def test_runtime_monitor_baseline_uses_low_frequency_for_healthy_waiting_market() -> None:
    baseline = json.loads(
        Path("docs/current/RUNTIME_MONITOR_BASELINE.json").read_text(encoding="utf-8")
    )

    frequency = baseline["quiet_monitor_frequency_policy"]
    assert frequency["healthy_waiting_for_market_interval_minutes"] == 120
    assert frequency["healthy_waiting_for_market_interaction_level"] == (
        "L0_local_cache_read"
    )
    assert frequency["healthy_waiting_for_market_remote_interaction_count"] == 0
    assert frequency["fresh_signal_short_window_interval_minutes"] in [5, 10]
    assert frequency["fresh_signal_short_window_enabled"] is True
    assert frequency["cache_first_routine_checks"] is True
    assert frequency["non_quiet_summary_required_fields"] == [
        "interaction_level",
        "remote_interaction_count",
        "mutates_remote_files",
        "approaches_real_order",
    ]
    p0_completion_audit_check = baseline["p0_completion_audit_check"]
    assert p0_completion_audit_check.startswith(
        "python3 scripts/runtime_first_bounded_live_order_completion_audit.py "
    )
    assert (
        "--output-json "
        "output/runtime-monitor/latest-p0-live-order-closure-completion-audit.json"
    ) in p0_completion_audit_check
    assert "run_tokyo" not in p0_completion_audit_check
