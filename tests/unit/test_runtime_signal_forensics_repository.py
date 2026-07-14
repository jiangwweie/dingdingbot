from __future__ import annotations

import sqlalchemy as sa

from src.application.runtime_signal_forensics import RuntimeSignalForensicsQuery
from src.infrastructure.runtime_signal_forensics_repository import (
    PgRuntimeSignalForensicsRepository,
)


def test_repository_is_window_bounded_filter_aware_limited_and_read_only() -> None:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    signals = sa.Table(
        "brc_live_signal_events",
        metadata,
        sa.Column("signal_event_id", sa.String, primary_key=True),
        sa.Column("strategy_group_id", sa.String),
        sa.Column("symbol", sa.String),
        sa.Column("side", sa.String),
        sa.Column("observed_at_ms", sa.BigInteger),
    )
    promotions = sa.Table(
        "brc_promotion_candidates",
        metadata,
        sa.Column("promotion_candidate_id", sa.String, primary_key=True),
        sa.Column("signal_event_id", sa.String),
    )
    tickets = sa.Table(
        "brc_action_time_tickets",
        metadata,
        sa.Column("ticket_id", sa.String, primary_key=True),
        sa.Column("signal_event_id", sa.String),
    )
    attempts = sa.Table(
        "brc_ticket_bound_protected_submit_attempts",
        metadata,
        sa.Column("protected_submit_attempt_id", sa.String, primary_key=True),
        sa.Column("ticket_id", sa.String),
        sa.Column("status", sa.String),
        sa.Column("exchange_write_called", sa.Boolean),
    )
    notifications = sa.Table(
        "brc_server_monitor_notifications",
        metadata,
        sa.Column("notification_id", sa.String, primary_key=True),
        sa.Column("correlation_id", sa.String),
    )
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            signals.insert(),
            [
                {"signal_event_id": "before", "strategy_group_id": "SOR", "symbol": "BTCUSDT", "side": "long", "observed_at_ms": 999},
                {"signal_event_id": "signal:match", "strategy_group_id": "SOR", "symbol": "BTCUSDT", "side": "long", "observed_at_ms": 2_000},
                {"signal_event_id": "wrong", "strategy_group_id": "CPM", "symbol": "ETHUSDT", "side": "long", "observed_at_ms": 2_100},
            ],
        )
        conn.execute(
            promotions.insert(),
            [
                {"promotion_candidate_id": "p-match", "signal_event_id": "signal:match"},
                {"promotion_candidate_id": "p-wrong", "signal_event_id": "wrong"},
            ],
        )
        conn.execute(
            tickets.insert(),
            [{"ticket_id": "ticket-match", "signal_event_id": "signal:match"}],
        )
        conn.execute(
            attempts.insert(),
            [
                {
                    "protected_submit_attempt_id": "attempt-match",
                    "ticket_id": "ticket-match",
                    "status": "submit_failed",
                    "exchange_write_called": False,
                }
            ],
        )
        conn.execute(
            notifications.insert(),
            [
                {
                    "notification_id": "notification-match",
                    "correlation_id": "signal:match",
                }
            ],
        )
        statements: list[str] = []

        def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
            statements.append(statement.strip().upper())

        sa.event.listen(engine, "before_cursor_execute", capture)
        try:
            rows = PgRuntimeSignalForensicsRepository(conn).query(
                RuntimeSignalForensicsQuery(
                    start_ms=1_000,
                    end_ms=3_000,
                    strategy_group_id="SOR",
                    symbol="BTCUSDT",
                    limit=1,
                )
            )
        finally:
            sa.event.remove(engine, "before_cursor_execute", capture)

        assert [row["signal_event_id"] for row in rows["live_signal_events"]] == ["signal:match"]
        assert [row["promotion_candidate_id"] for row in rows["promotion_candidates"]] == ["p-match"]
        assert [
            row["protected_submit_attempt_id"]
            for row in rows["ticket_bound_protected_submit_attempts"]
        ] == ["attempt-match"]
        assert [
            row["notification_id"]
            for row in rows["server_monitor_notifications"]
        ] == ["notification-match"]
        assert all(len(value) <= 1 for value in rows.values())
        assert not any(
            statement.startswith(("INSERT", "UPDATE", "DELETE", "ALTER", "DROP"))
            for statement in statements
        )
