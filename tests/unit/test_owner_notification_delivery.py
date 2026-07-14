from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest
import sqlalchemy as sa

from src.application.owner_notification import (
    OwnerNotificationIntent,
    OwnerNotificationKind,
    OwnerNotificationSeverity,
    owner_notification_delivery_identity,
    project_owner_notification_intents,
    select_owner_notification_delivery_batch,
)
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
                "execution_eligible": True,
                "required_execution_mode": "trial_live",
                "observed_at_ms": now_ms - 1_000,
                "expires_at_ms": now_ms + 60_000,
            }
        ]
    }


def _fresh_signals(now_ms: int, count: int) -> dict:
    return {
        "live_signal_events": [
            {
                **_fresh_signal(now_ms)["live_signal_events"][0],
                "signal_event_id": f"signal-{index}",
                "observed_at_ms": now_ms - index,
            }
            for index in range(1, count + 1)
        ]
    }


def _intent(
    identity: str,
    *,
    kind: OwnerNotificationKind = OwnerNotificationKind.OPPORTUNITY_DETECTED,
    severity: OwnerNotificationSeverity = OwnerNotificationSeverity.INFO,
    occurred_at_ms: int = 10_000,
) -> OwnerNotificationIntent:
    return OwnerNotificationIntent(
        notification_kind=kind,
        severity=severity,
        correlation_id=f"test:{identity}",
        strategy_group_id="SOR-001",
        symbol="BTCUSDT",
        side="long",
        occurred_at_ms=occurred_at_ms,
        headline="测试通知",
        current_state="测试状态",
        result_summary="测试结果",
        plain_reason="测试原因",
        next_system_action="测试下一步",
        owner_action_required=False,
    )


def _insert_ledger_row(
    conn: sa.engine.Connection,
    *,
    dedupe_key: str,
    intent: OwnerNotificationIntent,
    notification_state: str,
    send_attempts: int,
    resolved_at_ms: int | None = None,
) -> None:
    conn.execute(
        _table(conn).insert().values(
            notification_id=f"row:{dedupe_key[-16:]}",
            dedupe_key=dedupe_key,
            automation_id="runtime-monitor",
            strategy_group_id=intent.strategy_group_id,
            symbol=intent.symbol,
            blocker_class=intent.notification_kind.value,
            checkpoint="owner_notification",
            notification_state=notification_state,
            first_seen_at_ms=9_000,
            last_notified_at_ms=9_000,
            last_seen_at_ms=9_000,
            send_attempts=send_attempts,
            feishu_response={},
            created_at_ms=9_000,
            updated_at_ms=9_000,
            notification_kind=intent.notification_kind.value,
            severity=intent.severity.value,
            correlation_id=intent.correlation_id,
            template_version=intent.template_version,
            owner_action_required=intent.owner_action_required,
            occurred_at_ms=intent.occurred_at_ms,
            resolved_at_ms=resolved_at_ms,
        )
    )


def _table(conn: sa.engine.Connection) -> sa.Table:
    return sa.Table(
        "brc_server_monitor_notifications",
        sa.MetaData(),
        autoload_with=conn,
    )


def test_owner_notification_projection_keeps_more_than_five_candidates_for_delivery() -> None:
    intents = project_owner_notification_intents(
        _fresh_signals(10_000, 6),
        now_ms=10_000,
    )

    assert len(intents) == 6


def test_delivery_selection_ignores_sent_and_exhausted_rows_before_five_card_limit() -> None:
    intents = [
        _intent(str(index), occurred_at_ms=10_000 - index)
        for index in range(1, 7)
    ]
    sent_and_exhausted = {
        owner_notification_delivery_identity(intent): {
            "notification_state": "sent" if index <= 5 else "failed",
            "send_attempts": 1 if index <= 5 else 3,
        }
        for index, intent in enumerate(intents, start=1)
    }
    fresh = _intent("fresh", severity=OwnerNotificationSeverity.CRITICAL)

    selection = select_owner_notification_delivery_batch(
        [*intents, fresh],
        sent_and_exhausted,
        limit=5,
    )

    assert selection.selected == (fresh,)
    assert selection.suppressed_count == 5
    assert selection.retry_exhausted_count == 1


def test_delivery_selection_limits_eligible_attempts_and_prioritizes_retryable_failures() -> None:
    retry_one = _intent("retry-one", severity=OwnerNotificationSeverity.CRITICAL)
    retry_two = _intent("retry-two", severity=OwnerNotificationSeverity.WARNING)
    fresh = [_intent(f"fresh-{index}") for index in range(1, 5)]
    ledger = {
        owner_notification_delivery_identity(retry_one): {
            "notification_state": "failed",
            "send_attempts": 1,
        },
        owner_notification_delivery_identity(retry_two): {
            "notification_state": "failed",
            "send_attempts": 2,
        },
    }

    selection = select_owner_notification_delivery_batch(
        [retry_one, retry_two, *fresh],
        ledger,
        limit=5,
    )

    assert selection.selected == (retry_one, retry_two, *fresh[:3])
    assert len(selection.selected) == 5


def test_active_resolved_incident_starts_a_new_delivery_episode() -> None:
    incident = _intent(
        "incident-1",
        kind=OwnerNotificationKind.INTERVENTION_REQUIRED,
        severity=OwnerNotificationSeverity.CRITICAL,
    )
    key = owner_notification_delivery_identity(incident)

    selection = select_owner_notification_delivery_batch(
        [incident],
        {
            key: {
                "notification_state": "resolved",
                "send_attempts": 3,
                "resolved_at_ms": 9_000,
            }
        },
        limit=5,
    )

    assert selection.selected == (incident,)
    assert selection.reopened_dedupe_keys == frozenset({key})
    assert selection.reopened_incident_count == 1


@pytest.mark.parametrize(
    ("status_code", "response_body", "sent", "business_code"),
    [
        (200, '{"code": 0, "msg": "success"}', True, 0),
        (200, '{"code": 19001, "msg": "invalid"}', False, 19001),
        (200, '{"StatusCode": 0, "StatusMessage": "success"}', True, 0),
        (200, '{"StatusCode": 1, "StatusMessage": "failed"}', False, 1),
        (200, "not-json", False, None),
        (200, "{}", False, None),
        (500, '{"code": 0, "msg": "success"}', False, 0),
    ],
)
def test_feishu_business_acknowledgement_requires_transport_and_business_success(
    status_code: int,
    response_body: str,
    sent: bool,
    business_code: int | None,
) -> None:
    module = _load_monitor()

    acknowledgement = module.parse_feishu_robot_ack(
        status_code=status_code,
        response_body=response_body,
    )

    assert acknowledgement["sent"] is sent
    assert acknowledgement["business_code"] == business_code
    assert acknowledgement["status_code"] == status_code
    assert len(str(acknowledgement["response_body_preview"])) <= 500


def test_business_error_is_persisted_as_retryable_failed_delivery() -> None:
    module = _load_monitor()
    engine, conn, transaction = _connection()
    try:
        response = module.parse_feishu_robot_ack(
            status_code=200,
            response_body='{"code": 19001, "msg": "invalid"}',
        )
        summary = module._apply_pg_owner_notifications(
            conn=conn,
            automation_id="runtime-monitor",
            control_state=_fresh_signal(10_000),
            now_ms=10_000,
            webhook_url="https://example.test/webhook",
            webhook_secret=None,
            notification_timeout_seconds=3,
            notification_dry_run=False,
            notifier=lambda *_args: response,
        )

        row = conn.execute(
            sa.text(
                """
                SELECT notification_state, send_attempts, feishu_response
                FROM brc_server_monitor_notifications
                """
            )
        ).mappings().one()
        persisted = row["feishu_response"]
        if isinstance(persisted, str):
            import json

            persisted = json.loads(persisted)

        assert summary["sent_count"] == 0
        assert row["notification_state"] == "failed"
        assert row["send_attempts"] == 1
        assert persisted["business_code"] == 19001
        assert persisted["business_message"] == "invalid"
    finally:
        transaction.rollback()
        conn.close()
        engine.dispose()


def test_already_sent_candidates_do_not_starve_a_new_critical_card() -> None:
    module = _load_monitor()
    engine, conn, transaction = _connection()
    calls: list[dict] = []
    state = _fresh_signals(10_000, 6)
    try:
        projected = project_owner_notification_intents(state, now_ms=10_000)
        for intent in projected[:5]:
            _insert_ledger_row(
                conn,
                dedupe_key=module.owner_notification_dedupe_key(
                    "runtime-monitor",
                    intent,
                ),
                intent=intent,
                notification_state="sent",
                send_attempts=1,
            )

        summary = module._apply_pg_owner_notifications(
            conn=conn,
            automation_id="runtime-monitor",
            control_state=state,
            now_ms=10_000,
            webhook_url="https://example.test/webhook",
            webhook_secret=None,
            notification_timeout_seconds=3,
            notification_dry_run=False,
            notifier=lambda _url, _secret, body, _timeout: (
                calls.append(body) or {"sent": True, "status_code": 200}
            ),
        )

        assert summary["suppressed_count"] == 5
        assert summary["sent_count"] == 1
        assert len(calls) == 1
    finally:
        transaction.rollback()
        conn.close()
        engine.dispose()


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


def test_fresh_signal_monitor_decision_has_no_intervention_fallback() -> None:
    module = _load_monitor()

    assert module._monitor_decision_owner_intent(
        {
            "notify": True,
            "blocker_class": "fresh_signal",
            "checkpoint": "live_signal_event",
        },
        now_ms=10_000,
    ) is None


def test_normalized_signal_identity_suppresses_pre_fix_double_prefix_row() -> None:
    module = _load_monitor()
    engine, conn, transaction = _connection()
    calls: list[dict] = []
    try:
        conn.execute(
            sa.text(
                """
                INSERT INTO brc_server_monitor_notifications (
                    notification_id, dedupe_key, automation_id,
                    strategy_group_id, symbol, blocker_class, checkpoint,
                    notification_state, first_seen_at_ms, last_notified_at_ms,
                    last_seen_at_ms, send_attempts, feishu_response,
                    created_at_ms, updated_at_ms, notification_kind, severity,
                    correlation_id, template_version, owner_action_required,
                    occurred_at_ms
                ) VALUES (
                    'old-row', 'old-double-key', 'runtime-monitor',
                    'SOR-001', 'BTCUSDT', 'opportunity_detected',
                    'owner_notification', 'sent', 9000, 9000, 9000, 1, '{}',
                    9000, 9000, 'opportunity_detected', 'info',
                    'signal:signal:signal-1', 'owner-notification-v1', 0, 9000
                )
                """
            )
        )
        state = _fresh_signal(10_000)
        state["live_signal_events"][0]["signal_event_id"] = "signal:signal-1"

        summary = module._apply_pg_owner_notifications(
            conn=conn,
            automation_id="runtime-monitor",
            control_state=state,
            now_ms=10_000,
            webhook_url="https://example.test/webhook",
            webhook_secret=None,
            notification_timeout_seconds=3,
            notification_dry_run=False,
            notifier=lambda _url, _secret, body, _timeout: (
                calls.append(body) or {"sent": True, "status_code": 200}
            ),
        )

        assert summary["sent_count"] == 0
        assert summary["suppressed_count"] == 1
        assert calls == []
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


def test_notification_dry_run_creates_no_delivery_ledger_rows() -> None:
    module = _load_monitor()
    engine, conn, transaction = _connection()
    try:
        summary = module._apply_pg_owner_notifications(
            conn=conn,
            automation_id="runtime-monitor",
            control_state=_fresh_signal(10_000),
            now_ms=10_000,
            webhook_url="https://example.test/webhook",
            webhook_secret=None,
            notification_timeout_seconds=3,
            notification_dry_run=True,
            notifier=None,
        )

        assert summary["results"][0]["skipped_reason"] == "notification_dry_run"
        assert conn.execute(
            sa.text("SELECT COUNT(*) FROM brc_server_monitor_notifications")
        ).scalar_one() == 0
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
        assert second["suppressed_count"] == 1
        assert second["results"] == []
        assert len(calls) == 1
        content = calls[0]["card"]["elements"][0]["content"]
        assert "systemd" not in content
        assert "blocker" not in content
    finally:
        transaction.rollback()
        conn.close()
        engine.dispose()
