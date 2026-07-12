from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import sqlalchemy as sa

from tests.support.runtime_control_state_schema import (
    install_runtime_control_state_revision,
    install_runtime_control_state_schema,
)


SCRIPT = Path("scripts/run_tokyo_runtime_server_monitor.py")


def _load_monitor():
    spec = importlib.util.spec_from_file_location("owner_delivery_monitor", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _connection():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    conn = engine.connect()
    transaction = conn.begin()
    install_runtime_control_state_schema(conn, through_revision="086")
    install_runtime_control_state_revision(conn, revision="117")
    return engine, conn, transaction


def _fresh_signal(now_ms: int) -> dict:
    return {
        "live_signal_events": [
            {
                "signal_event_id": "signal-1",
                "strategy_group_id": "SOR-001",
                "symbol": "BTCUSDT",
                "side": "long",
                "source_kind": "live_market",
                "status": "facts_validated",
                "freshness_state": "fresh",
                "observed_at_ms": now_ms - 1_000,
                "expires_at_ms": now_ms + 60_000,
            }
        ]
    }


def test_owner_notification_delivery_sends_static_card_and_persists_typed_row() -> None:
    module = _load_monitor()
    engine, conn, transaction = _connection()
    calls: list[dict] = []
    try:
        summary = module._apply_pg_owner_notifications(
            conn=conn,
            automation_id="runtime-monitor",
            control_state=_fresh_signal(10_000),
            now_ms=10_000,
            webhook_url="https://example.test/webhook",
            webhook_secret=None,
            notification_timeout_seconds=3,
            notification_dry_run=False,
            notifier=lambda _url, _secret, body, _timeout: (
                calls.append(body) or {"sent": True, "status_code": 200}
            ),
        )

        assert summary["sent_count"] == 1
        assert calls[0]["msg_type"] == "interactive"
        assert all(
            element.get("tag") != "action"
            for element in calls[0]["card"]["elements"]
        )
        row = conn.execute(
            sa.text(
                """
                SELECT notification_kind, severity, correlation_id,
                       template_version, owner_action_required, send_attempts
                FROM brc_server_monitor_notifications
                """
            )
        ).mappings().one()
        assert row["notification_kind"] == "opportunity_detected"
        assert row["severity"] == "info"
        assert row["correlation_id"] == "signal:signal-1"
        assert row["template_version"] == "owner-notification-v1"
        assert bool(row["owner_action_required"]) is False
        assert row["send_attempts"] == 1
    finally:
        transaction.rollback()
        conn.close()
        engine.dispose()


def test_owner_notification_stops_retrying_after_three_attempts() -> None:
    module = _load_monitor()
    engine, conn, transaction = _connection()
    calls: list[dict] = []
    try:
        for _ in range(4):
            summary = module._apply_pg_owner_notifications(
                conn=conn,
                automation_id="runtime-monitor",
                control_state=_fresh_signal(10_000),
                now_ms=10_000,
                webhook_url="https://example.test/webhook",
                webhook_secret=None,
                notification_timeout_seconds=3,
                notification_dry_run=False,
                notifier=lambda _url, _secret, body, _timeout: (
                    calls.append(body) or {"sent": False, "status_code": 500}
                ),
            )

        assert len(calls) == 3
        assert summary["retry_exhausted_count"] == 1
        row = conn.execute(
            sa.text(
                "SELECT notification_state, send_attempts FROM brc_server_monitor_notifications"
            )
        ).mappings().one()
        assert row["notification_state"] == "failed"
        assert row["send_attempts"] == 3
    finally:
        transaction.rollback()
        conn.close()
        engine.dispose()


def test_persistent_monitor_incident_does_not_emit_false_recovery() -> None:
    module = _load_monitor()
    engine, conn, transaction = _connection()
    decision = {
        "notify": True,
        "automation_id": "runtime-monitor",
        "strategy_group_id": "runtime",
        "symbol": "all",
        "blocker_class": "watcher_or_service_failure",
        "checkpoint": "systemd",
        "reasons": ["systemd_unit_failed:brc-runtime-monitor.service"],
    }
    calls: list[dict] = []
    try:
        first = module._apply_pg_owner_notifications(
            conn=conn,
            automation_id="runtime-monitor",
            control_state={},
            now_ms=10_000,
            webhook_url="https://example.test/webhook",
            webhook_secret=None,
            notification_timeout_seconds=3,
            notification_dry_run=False,
            notifier=lambda _url, _secret, body, _timeout: (
                calls.append(body) or {"sent": True, "status_code": 200}
            ),
            decision=decision,
        )
        notifications = [dict(row) for row in conn.execute(
            sa.text("SELECT * FROM brc_server_monitor_notifications")
        ).mappings()]
        second = module._apply_pg_owner_notifications(
            conn=conn,
            automation_id="runtime-monitor",
            control_state={"server_monitor_notifications": notifications},
            now_ms=20_000,
            webhook_url="https://example.test/webhook",
            webhook_secret=None,
            notification_timeout_seconds=3,
            notification_dry_run=False,
            notifier=lambda _url, _secret, body, _timeout: (
                calls.append(body) or {"sent": True, "status_code": 200}
            ),
            decision=decision,
        )

        assert first["sent_count"] == 1
        assert second["sent_count"] == 0
        assert second["results"][0]["notification_kind"] == "system_temporarily_unavailable"
        assert len(calls) == 1
        content = calls[0]["card"]["elements"][0]["content"]
        assert "systemd" not in content
        assert "blocker" not in content
    finally:
        transaction.rollback()
        conn.close()
        engine.dispose()
