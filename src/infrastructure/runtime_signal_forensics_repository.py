"""Bounded read-only PG lineage queries for runtime signal forensics."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable

import sqlalchemy as sa

from src.application.runtime_signal_forensics import RuntimeSignalForensicsQuery


TABLES = {
    "live_signal_events": "brc_live_signal_events",
    "promotion_candidates": "brc_promotion_candidates",
    "action_time_lane_inputs": "brc_action_time_lane_inputs",
    "action_time_tickets": "brc_action_time_tickets",
    "ticket_bound_protected_submit_attempts": "brc_ticket_bound_protected_submit_attempts",
    "ticket_bound_exchange_commands": "brc_ticket_bound_exchange_commands",
    "ticket_bound_order_lifecycle_runs": "brc_ticket_bound_order_lifecycle_runs",
    "live_outcome_ledger": "brc_live_outcome_ledger",
    "server_monitor_notifications": "brc_server_monitor_notifications",
    "watcher_runtime_coverage": "brc_watcher_runtime_coverage",
    "server_monitor_runs": "brc_server_monitor_runs",
}


class PgRuntimeSignalForensicsRepository:
    """Query audit lineage without invoking current-state pruning or writes."""

    def __init__(self, conn: sa.engine.Connection) -> None:
        self.conn = conn
        self._existing = set(sa.inspect(conn).get_table_names())

    def query(self, query: RuntimeSignalForensicsQuery) -> dict[str, list[dict[str, Any]]]:
        signals = self._signal_rows(query)
        signal_ids = _texts(row.get("signal_event_id") for row in signals)
        promotions = self._related("promotion_candidates", "signal_event_id", signal_ids, query.limit)
        promotion_ids = _texts(row.get("promotion_candidate_id") for row in promotions)
        lanes = self._related_any(
            "action_time_lane_inputs",
            (("signal_event_id", signal_ids), ("promotion_candidate_id", promotion_ids)),
            query.limit,
        )
        lane_ids = _texts(
            row.get("action_time_lane_input_id") or row.get("lane_input_id")
            for row in lanes
        )
        tickets = self._related_any(
            "action_time_tickets",
            (("signal_event_id", signal_ids), ("action_time_lane_input_id", lane_ids)),
            query.limit,
        )
        ticket_ids = _texts(row.get("ticket_id") for row in tickets)
        correlations = {*(f"signal:{item}" for item in signal_ids), *(f"ticket:{item}" for item in ticket_ids)}
        return {
            "live_signal_events": signals,
            "promotion_candidates": promotions,
            "action_time_lane_inputs": lanes,
            "action_time_tickets": tickets,
            "ticket_bound_exchange_commands": self._related(
                "ticket_bound_exchange_commands", "ticket_id", ticket_ids, query.limit
            ),
            "ticket_bound_protected_submit_attempts": self._related(
                "ticket_bound_protected_submit_attempts",
                "ticket_id",
                ticket_ids,
                query.limit,
            ),
            "ticket_bound_order_lifecycle_runs": self._related(
                "ticket_bound_order_lifecycle_runs", "ticket_id", ticket_ids, query.limit
            ),
            "live_outcome_ledger": self._related(
                "live_outcome_ledger", "ticket_id", ticket_ids, query.limit
            ),
            "server_monitor_notifications": self._related(
                "server_monitor_notifications", "correlation_id", correlations, query.limit
            ),
            "watcher_runtime_coverage": self._coverage_rows(query),
            "server_monitor_runs": self._window_rows(
                "server_monitor_runs", "finished_at_ms", query
            ),
        }

    def _signal_rows(self, query: RuntimeSignalForensicsQuery) -> list[dict[str, Any]]:
        table = self._table("live_signal_events")
        if table is None or "observed_at_ms" not in table.c:
            return []
        statement = (
            sa.select(table)
            .where(table.c.observed_at_ms >= query.start_ms)
            .where(table.c.observed_at_ms <= query.end_ms)
            .order_by(table.c.observed_at_ms.asc())
            .limit(query.limit)
        )
        for column_name, expected in (
            ("strategy_group_id", query.strategy_group_id),
            ("symbol", query.symbol),
            ("side", query.side),
        ):
            if expected is not None and column_name in table.c:
                statement = statement.where(table.c[column_name] == expected)
        return self._execute(statement)

    def _related(
        self,
        logical_key: str,
        column_name: str,
        values: set[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        table = self._table(logical_key)
        if table is None or column_name not in table.c or not values:
            return []
        statement = sa.select(table).where(table.c[column_name].in_(sorted(values))).limit(limit)
        return self._execute(statement)

    def _related_any(
        self,
        logical_key: str,
        identities: tuple[tuple[str, set[str]], ...],
        limit: int,
    ) -> list[dict[str, Any]]:
        table = self._table(logical_key)
        if table is None:
            return []
        clauses = [
            table.c[column].in_(sorted(values))
            for column, values in identities
            if values and column in table.c
        ]
        if not clauses:
            return []
        return self._execute(sa.select(table).where(sa.or_(*clauses)).limit(limit))

    def _coverage_rows(self, query: RuntimeSignalForensicsQuery) -> list[dict[str, Any]]:
        table = self._table("watcher_runtime_coverage")
        if table is None:
            return []
        statement = sa.select(table)
        if "coverage_start_ms" in table.c and "coverage_end_ms" in table.c:
            statement = statement.where(table.c.coverage_start_ms <= query.start_ms).where(
                table.c.coverage_end_ms >= query.end_ms
            )
        return self._execute(statement.limit(query.limit))

    def _window_rows(
        self,
        logical_key: str,
        time_column: str,
        query: RuntimeSignalForensicsQuery,
    ) -> list[dict[str, Any]]:
        table = self._table(logical_key)
        if table is None or time_column not in table.c:
            return []
        statement = (
            sa.select(table)
            .where(table.c[time_column] >= query.start_ms)
            .where(table.c[time_column] <= query.end_ms)
            .order_by(table.c[time_column].asc())
            .limit(query.limit)
        )
        return self._execute(statement)

    def _table(self, logical_key: str) -> sa.Table | None:
        table_name = TABLES[logical_key]
        if table_name not in self._existing:
            return None
        return sa.Table(table_name, sa.MetaData(), autoload_with=self.conn)

    def _execute(self, statement: sa.Select) -> list[dict[str, Any]]:
        return [
            {key: _json_safe(value) for key, value in row.items()}
            for row in self.conn.execute(statement).mappings()
        ]


def _texts(values: Iterable[Any]) -> set[str]:
    return {str(value) for value in values if value is not None and str(value)}


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    return value
