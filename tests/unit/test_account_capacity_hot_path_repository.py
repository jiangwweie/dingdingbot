from __future__ import annotations

import sqlalchemy as sa

from src.infrastructure.account_capacity_hot_path_repository import (
    load_current_command_identity_evidence,
    load_effective_reservation_rows,
    load_live_exposure_rows,
)


def test_budget_hot_path_filters_terminal_history_in_sql() -> None:
    conn, statements = _connection()
    for index in range(100):
        _insert_claim(conn, index=index, status="released")
    _insert_claim(conn, index=100, status="active")

    result = load_effective_reservation_rows(
        conn,
        account_id="account-1",
        runtime_profile_id="profile-1",
        max_concurrent_positions=2,
    )

    assert [row.budget_reservation_id for row in result.rows] == ["claim-100"]
    assert result.overflow is False
    assert "status IN ('active', 'consumed')" in statements[-1]


def test_budget_hot_path_overflow_reads_only_policy_limit_plus_one() -> None:
    conn, statements = _connection()
    for index in range(100):
        _insert_claim(conn, index=index, status="active")

    result = load_effective_reservation_rows(
        conn,
        account_id="account-1",
        runtime_profile_id="profile-1",
        max_concurrent_positions=2,
    )

    assert len(result.rows) == 2
    assert result.overflow is True
    assert "LIMIT ?" in statements[-1]


def test_command_evidence_is_scoped_to_current_account_tickets() -> None:
    conn, _ = _connection()
    conn.execute(sa.text("""
      INSERT INTO brc_ticket_bound_exchange_commands VALUES
      ('command-1','account-1','ticket-current','instrument-1','exchange-1','client-1',NULL,
       'ENTRY','confirmed_submitted','operation-1'),
      ('command-2','account-2','ticket-other','instrument-2','exchange-2','client-2',NULL,
       'ENTRY','confirmed_submitted','operation-2'),
      ('command-3','account-1','ticket-current','instrument-1','exchange-3','client-3',NULL,
       'ENTRY','reconciled_absent','operation-3')
    """))

    rows = load_current_command_identity_evidence(
        conn,
        account_id="account-1",
        ticket_ids=("ticket-current",),
    )

    assert [(row.ticket_id, row.exchange_order_id) for row in rows] == [
        ("ticket-current", "exchange-1")
    ]


def test_live_exposure_reader_reports_overflow_without_loading_flat_history() -> None:
    conn, _ = _connection()
    for index in range(100):
        state = "flat" if index < 97 else "open_protected"
        conn.execute(
            sa.text("""
              INSERT INTO brc_account_exposure_current VALUES
              (:id,'account-1',:ticket,:state,1,1,0,'matched',1,NULL)
            """),
            {"id": f"exposure-{index:03d}", "ticket": f"ticket-{index}", "state": state},
        )

    result = load_live_exposure_rows(
        conn,
        account_id="account-1",
        max_concurrent_positions=2,
    )

    assert len(result.rows) == 2
    assert result.overflow is True


def test_hot_path_uses_no_select_star_or_runtime_reflection() -> None:
    conn, statements = _connection()
    _insert_claim(conn, index=1, status="active")
    load_effective_reservation_rows(
        conn,
        account_id="account-1",
        runtime_profile_id="profile-1",
        max_concurrent_positions=2,
    )
    load_live_exposure_rows(
        conn,
        account_id="account-1",
        max_concurrent_positions=2,
    )
    load_current_command_identity_evidence(
        conn,
        account_id="account-1",
        ticket_ids=("ticket-1",),
    )

    sql = "\n".join(statements).lower()
    assert "select *" not in sql
    assert "information_schema" not in sql
    assert "autoload_with" not in sql
    assert "read_control_state" not in sql


def _connection() -> tuple[sa.Connection, list[str]]:
    engine = sa.create_engine("sqlite://")
    statements: list[str] = []
    sa.event.listen(
        engine,
        "before_cursor_execute",
        lambda _conn, _cursor, statement, _parameters, _context, _many: statements.append(statement),
    )
    conn = engine.connect()
    conn.execute(sa.text("""CREATE TABLE brc_budget_reservations (
      budget_reservation_id TEXT PRIMARY KEY, ticket_id TEXT,
      exchange_instrument_id TEXT, exposure_episode_id TEXT, status TEXT,
      risk_at_stop NUMERIC, reserved_margin NUMERIC,
      margin_accounting_state TEXT, account_id TEXT, runtime_profile_id TEXT,
      symbol TEXT, asset_class TEXT, instrument_type TEXT,
      primary_risk_cluster_id TEXT, cluster_membership_snapshot_id TEXT,
      account_source_fact_snapshot_id TEXT, account_fact_schema_version TEXT)"""))
    conn.execute(sa.text("ALTER TABLE brc_budget_reservations ADD COLUMN instrument_rule_snapshot_id TEXT"))
    conn.execute(sa.text("""CREATE TABLE brc_exchange_instruments (
      exchange_instrument_id TEXT PRIMARY KEY, exchange_symbol TEXT)"""))
    conn.execute(sa.text(
        "INSERT INTO brc_exchange_instruments VALUES ('instrument-1','SOLUSDT')"
    ))
    conn.execute(sa.text("CREATE TABLE brc_instrument_rule_snapshots (instrument_rule_snapshot_id TEXT PRIMARY KEY, contract_multiplier NUMERIC NOT NULL)"))
    conn.execute(sa.text("INSERT INTO brc_instrument_rule_snapshots VALUES ('rule-1', 1)"))
    conn.execute(sa.text("""CREATE TABLE brc_account_exposure_current (
      account_exposure_current_id TEXT PRIMARY KEY, account_id TEXT,
      owner_ticket_id TEXT, exposure_state TEXT, actual_directional_risk NUMERIC,
      held_risk NUMERIC, unreflected_pending_margin NUMERIC,
      reconciliation_state TEXT, position_slot_claimed BOOLEAN,
      first_blocker TEXT)"""))
    conn.execute(sa.text("""CREATE TABLE brc_ticket_bound_exchange_commands (
      exchange_command_id TEXT PRIMARY KEY, account_id TEXT, ticket_id TEXT,
      exchange_instrument_id TEXT, exchange_order_id TEXT, client_order_id TEXT,
      parent_order_id TEXT, order_role TEXT, command_state TEXT,
      operation_submit_command_id TEXT)"""))
    statements.clear()
    return conn, statements


def _insert_claim(conn: sa.Connection, *, index: int, status: str) -> None:
    conn.execute(
        sa.text("""
          INSERT INTO brc_budget_reservations VALUES
          (:id,:ticket,'instrument-1',:episode,:status,1,1,
           'reserved_unreflected','account-1','profile-1','SOLUSDT',
           'crypto','perpetual','crypto-beta','membership-1',
           'account-fact-1','v1','rule-1')
        """),
        {
            "id": f"claim-{index:03d}",
            "ticket": f"ticket-{index}",
            "episode": f"episode-{index}",
            "status": status,
        },
    )
