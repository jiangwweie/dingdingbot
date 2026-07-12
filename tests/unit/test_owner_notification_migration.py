from __future__ import annotations

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

from tests.support.runtime_control_state_schema import (
    MIGRATIONS,
    _load_module,
    install_runtime_control_state_revision,
    install_runtime_control_state_schema,
)


def test_migration_117_extends_existing_notification_ledger() -> None:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        install_runtime_control_state_schema(conn, through_revision="086")
        conn.execute(
            sa.text(
                """
                INSERT INTO brc_server_monitor_notifications (
                    notification_id, dedupe_key, automation_id,
                    strategy_group_id, symbol, blocker_class, checkpoint,
                    notification_state, first_seen_at_ms, last_notified_at_ms,
                    last_seen_at_ms, send_attempts, feishu_response,
                    created_at_ms, updated_at_ms
                ) VALUES (
                    'legacy-1', 'legacy-key', 'runtime-monitor',
                    'SOR', 'BTCUSDT', 'none', 'market_wait',
                    'sent', 100, 110, 120, 1, '{}', 100, 120
                )
                """
            )
        )

        install_runtime_control_state_revision(conn, revision="117")

        columns = {
            row["name"]
            for row in sa.inspect(conn).get_columns("brc_server_monitor_notifications")
        }
        assert {
            "notification_kind",
            "severity",
            "correlation_id",
            "template_version",
            "owner_action_required",
            "occurred_at_ms",
            "resolved_at_ms",
        } <= columns
        row = conn.execute(
            sa.text(
                """
                SELECT notification_kind, severity, correlation_id,
                       template_version, owner_action_required, occurred_at_ms
                FROM brc_server_monitor_notifications
                WHERE notification_id = 'legacy-1'
                """
            )
        ).mappings().one()
        assert row["notification_kind"] == "legacy_monitor_event"
        assert row["severity"] == "warning"
        assert row["correlation_id"] == "legacy-key"
        assert row["template_version"] == "legacy-text-v0"
        assert bool(row["owner_action_required"]) is False
        assert row["occurred_at_ms"] == 100
        indexes = {
            item["name"]
            for item in sa.inspect(conn).get_indexes(
                "brc_server_monitor_notifications"
            )
        }
        assert "idx_brc_monitor_notify_correlation_kind" in indexes
        assert "idx_brc_monitor_notify_state" in indexes

        migration = _load_module(MIGRATIONS["117"], "roundtrip_migration_117")
        previous_op = migration.op
        migration.op = Operations(MigrationContext.configure(conn))
        try:
            migration.downgrade()
            downgraded_columns = {
                item["name"]
                for item in sa.inspect(conn).get_columns(
                    "brc_server_monitor_notifications"
                )
            }
            assert "notification_kind" not in downgraded_columns
            migration.upgrade()
        finally:
            migration.op = previous_op
        upgraded_columns = {
            item["name"]
            for item in sa.inspect(conn).get_columns(
                "brc_server_monitor_notifications"
            )
        }
        assert "notification_kind" in upgraded_columns
