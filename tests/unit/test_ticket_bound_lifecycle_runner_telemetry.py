from __future__ import annotations

import inspect
from pathlib import Path

from scripts import run_ticket_bound_lifecycle_maintenance_once as lifecycle_cli


ROOT = Path(__file__).resolve().parents[2]


def test_stage_telemetry_records_bounded_runtime_metrics(monkeypatch):
    ticks = iter((10.0, 10.1, 10.4, 10.7))
    monkeypatch.setattr(lifecycle_cli.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(lifecycle_cli, "_peak_rss_kib", lambda: 123_456)

    telemetry = lifecycle_cli.LifecycleStageTelemetry()
    telemetry.start_stage("pg_scope_selection")
    telemetry.finish_stage("pg_scope_selection")
    telemetry.exchange_request_count += 1
    telemetry.pg_transaction_count += 2

    result = telemetry.snapshot(deadline_at=11.0)

    assert result == {
        "stage_durations_ms": {"pg_scope_selection": 300},
        "total_duration_ms": 700,
        "exchange_request_count": 1,
        "pg_transaction_count": 2,
        "peak_rss_kib": 123_456,
        "deadline_remaining_seconds": 0.3,
    }


def test_systemd_timeout_hierarchy_leaves_structured_failure_margin():
    unit = (ROOT / "deploy/systemd/brc-ticket-lifecycle-maintenance.service").read_text()

    assert "--global-deadline-seconds 28" in unit
    assert "/usr/bin/timeout --foreground --signal=TERM --kill-after=2s 36s" in unit
    assert "TimeoutStartSec=45s" in unit
    assert "/usr/bin/time -f" not in unit


def test_lifecycle_runner_uses_lightweight_gateway_binding():
    source = inspect.getsource(lifecycle_cli._runtime_exchange_gateway_binding)

    assert "src.infrastructure.runtime_exchange_gateway_binding" in source
    assert "src.interfaces" not in source
