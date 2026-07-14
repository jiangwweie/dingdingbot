from __future__ import annotations

from pathlib import Path


def test_runtime_monitor_timer_uses_low_frequency_server_side_pg_monitor() -> None:
    service = Path("deploy/systemd/brc-runtime-monitor.service").read_text(
        encoding="utf-8"
    )
    timer = Path("deploy/systemd/brc-runtime-monitor.timer").read_text(
        encoding="utf-8"
    )

    assert "ExecStart=" in service
    assert "scripts/run_tokyo_runtime_server_monitor.py" in service
    assert "--require-database-url" in service
    assert "--dedupe-state-json" not in service
    assert "--candidate-pool-json" not in service
    assert "--daily-table-json" not in service
    assert "OnUnitActiveSec=10min" in timer
    assert "Unit=brc-runtime-monitor.service" in timer
    assert "--baseline-json" not in service
    assert "--baseline-json" not in timer
    assert "--systemd-unit brc-ticket-lifecycle-maintenance.timer" in service
    assert "--systemd-unit brc-ticket-lifecycle-maintenance.service" in service
    for removed_key in [
        "default_check",
        "heartbeat_check",
        "routine_status_check",
        "strict_no_server_check",
        "forced_refresh_check",
        "local_monitor_sequence_check",
        "quiet_monitor_audit_check",
    ]:
        assert removed_key not in service


def test_runtime_monitor_health_checks_remain_readonly() -> None:
    source = Path("scripts/run_tokyo_runtime_server_monitor.py").read_text(
        encoding="utf-8"
    )
    service = Path("deploy/systemd/brc-runtime-monitor.service").read_text(
        encoding="utf-8"
    )

    for action in ("start", "stop", "restart", "enable", "disable"):
        assert f"systemctl {action}" not in source
        assert f"systemctl {action}" not in service
