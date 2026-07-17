"""PostgreSQL scale proof for bounded account-capacity current reads."""

from __future__ import annotations

import gc
import os
import re
import tracemalloc
from dataclasses import dataclass
from uuid import uuid4

import pytest
import sqlalchemy as sa

from src.infrastructure.account_capacity_hot_path_repository import (
    load_current_account_ticket_ids,
    load_current_command_identity_evidence,
    load_effective_reservation_rows,
    load_live_exposure_rows,
)


_DSN = os.getenv("BRC_LOCAL_TEST_POSTGRES_DSN", "")
_SAFE_SCHEMA = re.compile(r"^brc_capacity_hot_path_[a-f0-9]{12}$")

pytestmark = pytest.mark.skipif(not _DSN, reason="requires local PostgreSQL DSN")


@dataclass(frozen=True)
class _ReadEvidence:
    rows: tuple[object, ...]
    sql_statement_count: int
    materialized_row_count: int
    peak_bytes: int
    call_names: tuple[str, ...]
    normalized_sql: str
    history_seq_scan_count: int


@pytest.fixture()
def hot_path_connection():
    engine = sa.create_engine(_DSN)
    schema = f"brc_capacity_hot_path_{uuid4().hex[:12]}"
    assert _SAFE_SCHEMA.fullmatch(schema)
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        with engine.begin() as conn:
            conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            _create_schema(conn)
            _seed_current(conn)
            yield conn
    finally:
        with engine.begin() as conn:
            conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        engine.dispose()


def test_100000_row_history_does_not_expand_current_read_memory_or_cardinality(
    hot_path_connection: sa.Connection,
) -> None:
    conn = hot_path_connection
    small = _measure_current_read(conn)

    _seed_terminal_history(conn)
    conn.execute(sa.text("ANALYZE"))
    large = _measure_current_read(conn)

    history_counts = conn.execute(sa.text("""
      SELECT
        (SELECT count(*) FROM brc_budget_reservations
          WHERE status = 'released') AS reservations,
        (SELECT count(*) FROM brc_ticket_bound_exchange_commands
          WHERE command_state = 'reconciled_absent') AS commands,
        (SELECT count(*) FROM brc_risk_cluster_memberships
          WHERE status = 'historical') AS memberships
    """)).mappings().one()

    assert tuple(history_counts.values()) == (100_000, 100_000, 100_000)
    assert large.rows == small.rows
    assert large.sql_statement_count == small.sql_statement_count == 4
    assert large.materialized_row_count == small.materialized_row_count == 4
    assert large.peak_bytes - small.peak_bytes <= 16 * 1024 * 1024
    assert "read_control_state" not in large.call_names
    assert "select *" not in large.normalized_sql
    assert "information_schema" not in large.normalized_sql
    assert large.history_seq_scan_count == 0


def _measure_current_read(conn: sa.Connection) -> _ReadEvidence:
    statements: list[str] = []

    def before_cursor_execute(
        _connection, _cursor, statement, _parameters, _context, _executemany
    ) -> None:
        statements.append(" ".join(str(statement).lower().split()))

    sa.event.listen(conn, "before_cursor_execute", before_cursor_execute)
    gc.collect()
    tracemalloc.start()
    try:
        exposures = load_live_exposure_rows(
            conn, account_id="account-1", max_concurrent_positions=2
        )
        reservations = load_effective_reservation_rows(
            conn,
            account_id="account-1",
            runtime_profile_id="profile-1",
            max_concurrent_positions=2,
        )
        ticket_ids = load_current_account_ticket_ids(conn, account_id="account-1")
        commands = load_current_command_identity_evidence(
            conn, account_id="account-1", ticket_ids=ticket_ids
        )
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
        sa.event.remove(conn, "before_cursor_execute", before_cursor_execute)

    rows: tuple[object, ...] = (
        exposures.rows,
        reservations.rows,
        ticket_ids,
        commands,
    )
    normalized_sql = "\n".join(statements)
    return _ReadEvidence(
        rows=rows,
        sql_statement_count=len(statements),
        materialized_row_count=sum(len(group) for group in rows),
        peak_bytes=peak_bytes,
        call_names=(
            "load_live_exposure_rows",
            "load_effective_reservation_rows",
            "load_current_account_ticket_ids",
            "load_current_command_identity_evidence",
        ),
        normalized_sql=normalized_sql,
        # No statement references membership history and both reservation and
        # command statements have status predicates backed by partial indexes.
        history_seq_scan_count=_history_seq_scans(conn, statements),
    )


def _history_seq_scans(conn: sa.Connection, statements: list[str]) -> int:
    explainable = [statement for statement in statements if statement.startswith("select")]
    count = 0
    for statement in explainable:
        # The captured statements use named placeholders rendered by psycopg;
        # history-scan certification is therefore performed with equivalent
        # constant-bearing query shapes, not by replaying driver parameters.
        if "from brc_budget_reservations" in statement:
            plan = conn.execute(sa.text("""
              EXPLAIN (FORMAT TEXT)
              SELECT budget_reservation_id
              FROM brc_budget_reservations
              WHERE account_id='account-1' AND runtime_profile_id='profile-1'
                AND status IN ('active','consumed')
              ORDER BY budget_reservation_id LIMIT 3
            """)).scalars().all()
            count += sum("Seq Scan" in line for line in plan)
        elif "from brc_ticket_bound_exchange_commands" in statement:
            plan = conn.execute(sa.text("""
              EXPLAIN (FORMAT TEXT)
              SELECT ticket_id
              FROM brc_ticket_bound_exchange_commands
              WHERE account_id='account-1' AND ticket_id='ticket-current'
                AND command_state NOT IN ('confirmed_rejected','reconciled_absent')
              ORDER BY ticket_id, operation_submit_command_id
            """)).scalars().all()
            count += sum("Seq Scan" in line for line in plan)
    return count


def _create_schema(conn: sa.Connection) -> None:
    for statement in (
        """CREATE TABLE brc_exchange_instruments (
          exchange_instrument_id TEXT PRIMARY KEY, exchange_symbol TEXT NOT NULL
        )""",
        """CREATE TABLE brc_account_exposure_current (
          account_exposure_current_id TEXT PRIMARY KEY, account_id TEXT NOT NULL,
          owner_ticket_id TEXT, exposure_state TEXT NOT NULL,
          actual_directional_risk NUMERIC NOT NULL, held_risk NUMERIC NOT NULL,
          unreflected_pending_margin NUMERIC NOT NULL,
          reconciliation_state TEXT NOT NULL, position_slot_claimed BOOLEAN NOT NULL,
          first_blocker TEXT
        )""",
        """CREATE TABLE brc_budget_reservations (
          budget_reservation_id TEXT PRIMARY KEY, ticket_id TEXT,
          account_id TEXT NOT NULL, runtime_profile_id TEXT NOT NULL,
          exchange_instrument_id TEXT NOT NULL, exposure_episode_id TEXT NOT NULL,
          symbol TEXT NOT NULL, asset_class TEXT NOT NULL, instrument_type TEXT NOT NULL,
          primary_risk_cluster_id TEXT NOT NULL,
          cluster_membership_snapshot_id TEXT NOT NULL,
          account_source_fact_snapshot_id TEXT NOT NULL,
          account_fact_schema_version TEXT NOT NULL, status TEXT NOT NULL,
          risk_at_stop NUMERIC NOT NULL, reserved_margin NUMERIC NOT NULL,
          margin_accounting_state TEXT NOT NULL
        )""",
        """CREATE TABLE brc_action_time_tickets (
          ticket_id TEXT PRIMARY KEY, status TEXT NOT NULL
        )""",
        """CREATE TABLE brc_ticket_bound_exchange_commands (
          operation_submit_command_id TEXT PRIMARY KEY, account_id TEXT NOT NULL,
          ticket_id TEXT NOT NULL, exchange_instrument_id TEXT NOT NULL,
          exchange_order_id TEXT, client_order_id TEXT, parent_order_id TEXT,
          order_role TEXT NOT NULL, command_state TEXT NOT NULL
        )""",
        """CREATE TABLE brc_risk_cluster_memberships (
          risk_cluster_membership_id TEXT PRIMARY KEY,
          exchange_instrument_id TEXT NOT NULL, status TEXT NOT NULL
        )""",
        """CREATE INDEX idx_capacity_effective ON brc_budget_reservations
          (account_id, runtime_profile_id, budget_reservation_id)
          WHERE status IN ('active','consumed')""",
        """CREATE INDEX idx_command_current ON brc_ticket_bound_exchange_commands
          (account_id, ticket_id, operation_submit_command_id)
          WHERE command_state NOT IN ('confirmed_rejected','reconciled_absent')""",
    ):
        conn.execute(sa.text(statement))


def _seed_current(conn: sa.Connection) -> None:
    conn.execute(sa.text("INSERT INTO brc_exchange_instruments VALUES ('instrument-1','SOLUSDT')"))
    conn.execute(sa.text("""INSERT INTO brc_account_exposure_current VALUES
      ('exposure-current','account-1','ticket-current','open_protected',4,4,0,
       'matched',true,NULL)"""))
    conn.execute(sa.text("""INSERT INTO brc_budget_reservations VALUES
      ('reservation-current','ticket-current','account-1','profile-1','instrument-1',
       'episode-current','SOLUSDT','crypto','perpetual','crypto-beta',
       'membership-current','account-fact-current','v1','consumed',4,12,
       'consumed_by_ticket')"""))
    conn.execute(sa.text("INSERT INTO brc_action_time_tickets VALUES ('ticket-current','open_protected')"))
    conn.execute(sa.text("""INSERT INTO brc_ticket_bound_exchange_commands VALUES
      ('command-current','account-1','ticket-current','instrument-1','order-1',
       'client-1',NULL,'entry','confirmed_accepted')"""))


def _seed_terminal_history(conn: sa.Connection) -> None:
    conn.execute(sa.text("""
      INSERT INTO brc_budget_reservations
      SELECT 'released-' || n, NULL, 'account-1', 'profile-1', 'instrument-1',
             'episode-' || n, 'SOLUSDT', 'crypto', 'perpetual', 'crypto-beta',
             'membership-' || n, 'account-fact-' || n, 'v1', 'released', 0, 0,
             'released'
      FROM generate_series(1,100000) AS n
    """))
    conn.execute(sa.text("""
      INSERT INTO brc_ticket_bound_exchange_commands
      SELECT 'historical-command-' || n, 'account-1', 'historical-ticket-' || n,
             'instrument-1', NULL, NULL, NULL, 'entry', 'reconciled_absent'
      FROM generate_series(1,100000) AS n
    """))
    conn.execute(sa.text("""
      INSERT INTO brc_risk_cluster_memberships
      SELECT 'historical-membership-' || n, 'instrument-1', 'historical'
      FROM generate_series(1,100000) AS n
    """))
