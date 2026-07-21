"""Real-PostgreSQL certification for P0 account-truth convergence."""

from __future__ import annotations

from decimal import Decimal
import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

from src.application.action_time.budget_reservation_transition import (
    reclaim_terminal_presubmit_reservations,
)
from src.application.action_time.ticket_bound_local_order import (
    build_ticket_bound_local_order,
)
from src.domain.models import OrderType
from src.infrastructure.binance_usdm_account_risk_snapshot import (
    FullAccountRiskSnapshot,
)


_DSN = os.getenv("BRC_LOCAL_TEST_POSTGRES_DSN", "")
pytestmark = pytest.mark.skipif(not _DSN, reason="requires disposable PostgreSQL")
NOW_MS = 1_752_480_000_000
ROOT = Path(__file__).resolve().parents[2]
SCHEMA_TRUTH_BUNDLE_PATH = (
    ROOT / "migrations/versions/2026-07-20-141_schema_truth_capability_bundle.py"
)


@pytest.fixture()
def connection():
    admin = sa.create_engine(_DSN)
    schema = f"brc_atc_{uuid4().hex[:12]}"
    with admin.begin() as conn:
        conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    engine = sa.create_engine(_DSN, connect_args={"options": f"-c search_path={schema}"})
    try:
        with engine.begin() as conn:
            yield conn
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        admin.dispose()


def test_migration_140_preserves_ticket_identity_without_evaluation_overflow(connection):
    connection.execute(sa.text("""
        CREATE TABLE orders (
          id varchar(64) PRIMARY KEY, signal_id varchar(64), symbol varchar(64) NOT NULL,
          direction varchar(16) NOT NULL, order_type varchar(32) NOT NULL,
          order_role varchar(16) NOT NULL, status varchar(32) NOT NULL,
          price numeric, trigger_price numeric, requested_qty numeric NOT NULL,
          filled_qty numeric NOT NULL, average_exec_price numeric,
          reduce_only boolean NOT NULL DEFAULT false, parent_order_id varchar(64),
          signal_evaluation_id varchar(128), created_at bigint NOT NULL, updated_at bigint NOT NULL
        )
    """))
    _upgrade_140(connection)
    ticket_id = "t" * 148
    command = _command(ticket_id=ticket_id)
    order = build_ticket_bound_local_order(
        command=command,
        signal_event_id="signal-event-" + "s" * 140,
        now_ms=NOW_MS,
        order_type=OrderType.MARKET,
    )
    orders = sa.Table("orders", sa.MetaData(), autoload_with=connection)
    connection.execute(orders.insert().values(
        id=order.id, signal_id=order.signal_id, symbol=order.symbol,
        direction=order.direction.value, order_type=order.order_type.value,
        order_role=order.order_role.value, status=order.status.value,
        price=order.price, trigger_price=order.trigger_price,
        requested_qty=order.requested_qty, filled_qty=order.filled_qty,
        average_exec_price=order.average_exec_price, reduce_only=order.reduce_only,
        parent_order_id=order.parent_order_id,
        signal_evaluation_id=order.signal_evaluation_id, ticket_id=order.ticket_id,
        exchange_command_id=order.exchange_command_id, account_id=order.account_id,
        exchange_id=order.exchange_id, exchange_instrument_id=order.exchange_instrument_id,
        runtime_profile_id=order.runtime_profile_id,
        strategy_group_id=order.strategy_group_id,
        exposure_episode_id=order.exposure_episode_id,
        created_at=order.created_at, updated_at=order.updated_at,
    ))
    row = connection.execute(sa.text("SELECT signal_id, signal_evaluation_id, ticket_id FROM orders")).mappings().one()
    assert row["signal_id"] == order.signal_id
    assert row["signal_evaluation_id"] is None
    assert row["ticket_id"] == ticket_id


def test_terminal_absent_releases_only_reservation_only_slot_and_is_idempotent(connection):
    _create_reclaim_tables(connection)
    connection.execute(sa.text("""
      INSERT INTO brc_budget_reservations VALUES ('reservation-1', 'consumed', 'ticket-1', NULL);
      INSERT INTO brc_action_time_tickets VALUES ('ticket-1', 'expired');
      INSERT INTO brc_ticket_bound_protected_submit_attempts VALUES ('ticket-1', false, 'submit_failed');
      INSERT INTO brc_ticket_bound_exchange_commands VALUES ('command-1', 'ticket-1', 'reconciled_absent', NULL, NULL, 'BTCUSDT', 'client-1');
      INSERT INTO brc_account_exposure_current VALUES ('ticket-1', true, 'reserved', 0, 0);
      INSERT INTO brc_ticket_bound_order_lifecycle_runs VALUES ('lifecycle-1', 'ticket-1', 'attempt-1', 'submit_failed', 'failed', '[]', 1);
    """))
    snapshot = _snapshot()
    assert reclaim_terminal_presubmit_reservations(
        connection, now_ms=NOW_MS, evidence_ref_prefix="test", snapshot=snapshot
    ) == 1
    assert connection.execute(sa.text("SELECT status FROM brc_budget_reservations")).scalar_one() == "released"
    assert connection.execute(sa.text("SELECT status FROM brc_ticket_bound_order_lifecycle_runs")).scalar_one() == "presubmit_reconciled_absent"
    assert reclaim_terminal_presubmit_reservations(
        connection, now_ms=NOW_MS + 1, evidence_ref_prefix="test", snapshot=snapshot
    ) == 0
    assert connection.execute(sa.text("SELECT count(*) FROM brc_ticket_bound_lifecycle_events")).scalar_one() == 1


def test_expired_ticket_without_submit_attempt_releases_proven_absent_reservation(connection):
    _create_reclaim_tables(connection)
    connection.execute(sa.text("""
      INSERT INTO brc_budget_reservations VALUES ('reservation-1', 'consumed', 'ticket-1', NULL);
      INSERT INTO brc_action_time_tickets VALUES ('ticket-1', 'expired');
      INSERT INTO brc_account_exposure_current VALUES ('ticket-1', true, 'reserved', 0, 0);
    """))

    assert reclaim_terminal_presubmit_reservations(
        connection, now_ms=NOW_MS, evidence_ref_prefix="test", snapshot=_snapshot()
    ) == 1
    assert connection.execute(
        sa.text("SELECT status FROM brc_budget_reservations")
    ).scalar_one() == "released"


def test_expired_ticket_without_attempt_keeps_reservation_when_command_was_dispatched(connection):
    _create_reclaim_tables(connection)
    connection.execute(sa.text("""
      INSERT INTO brc_budget_reservations VALUES ('reservation-1', 'consumed', 'ticket-1', NULL);
      INSERT INTO brc_action_time_tickets VALUES ('ticket-1', 'expired');
      INSERT INTO brc_ticket_bound_exchange_commands VALUES ('command-1', 'ticket-1', 'submitted', 1, NULL, 'BTCUSDT', 'client-1');
      INSERT INTO brc_account_exposure_current VALUES ('ticket-1', true, 'reserved', 0, 0);
    """))

    assert reclaim_terminal_presubmit_reservations(
        connection, now_ms=NOW_MS, evidence_ref_prefix="test", snapshot=_snapshot()
    ) == 0
    assert connection.execute(
        sa.text("SELECT status FROM brc_budget_reservations")
    ).scalar_one() == "consumed"


def test_schema_truth_bundle_enforces_current_identity_and_converges_netting_keys(
    connection,
):
    connection.execute(
        sa.text(
            """
            CREATE TABLE brc_account_budget_current (
              account_budget_current_id text primary key,
              account_id text not null,
              runtime_profile_id text not null,
              risk_policy_version text not null,
              CONSTRAINT uq_brc_account_budget_current_scope
                UNIQUE (account_id, runtime_profile_id, risk_policy_version)
            )
            """
        )
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO brc_account_budget_current VALUES
              ('budget-1', 'account-1', 'profile-1', 'policy-v1')
            """
        )
    )
    connection.execute(
        sa.text(
            """
            CREATE TABLE brc_runtime_fact_snapshots (
              fact_snapshot_id text primary key,
              fact_surface text not null
            )
            """
        )
    )
    for table_name, state_column in (
        ("brc_account_exposure_current", "exposure_state"),
        ("brc_ticket_bound_exchange_commands", "command_state"),
        ("brc_ticket_bound_scope_freezes", "status"),
    ):
        connection.execute(
            sa.text(
                f"""
                CREATE TABLE {table_name} (
                  account_id text not null,
                  exchange_instrument_id text not null,
                  position_mode text not null,
                  position_bucket text not null,
                  netting_domain_key text not null,
                  {state_column} text not null,
                  source_kind text,
                  source_id text
                )
                """
            )
        )
        connection.execute(
            sa.text(
                f"""
                INSERT INTO {table_name} (
                  account_id, exchange_instrument_id, position_mode,
                  position_bucket, netting_domain_key, {state_column},
                  source_kind, source_id
                ) VALUES (
                  'account-1', 'binance_usdm:ETHUSDT', 'one_way', 'BOTH',
                  'legacy-drifted-key', 'active', 'source', '{table_name}'
                )
                """
            )
        )

    _upgrade_141(connection)

    savepoint = connection.begin_nested()
    try:
        with pytest.raises(sa.exc.IntegrityError):
            connection.execute(
                sa.text(
                    """
                    INSERT INTO brc_account_budget_current VALUES
                      ('budget-2', 'account-1', 'profile-1', 'policy-v2')
                    """
                )
            )
    finally:
        savepoint.rollback()

    expected = "account-1|binance_usdm:ETHUSDT|one_way|BOTH"
    for table_name in (
        "brc_account_exposure_current",
        "brc_ticket_bound_exchange_commands",
        "brc_ticket_bound_scope_freezes",
    ):
        assert connection.execute(
            sa.text(f"SELECT netting_domain_key FROM {table_name}")
        ).scalar_one() == expected
    typed_columns = {
        row["column_name"]
        for row in connection.execute(
            sa.text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'brc_runtime_fact_snapshots'
                """
            )
        ).mappings()
    }
    assert {
        "lane_identity_key",
        "event_spec_id",
        "event_spec_version",
        "detector_key",
        "decision_identity",
        "source_watermark",
        "producer_runtime_head",
    } <= typed_columns


def _upgrade_140(conn) -> None:
    path = ROOT / "migrations/versions/2026-07-20-140_account_truth_convergence.py"
    spec = importlib.util.spec_from_file_location("migration_140_atc", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    old = module.op
    module.op = Operations(MigrationContext.configure(conn))
    try:
        module.upgrade()
    finally:
        module.op = old


def _upgrade_141(conn) -> None:
    spec = importlib.util.spec_from_file_location(
        "migration_141_schema_truth_bundle", SCHEMA_TRUTH_BUNDLE_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    old = module.op
    module.op = Operations(MigrationContext.configure(conn))
    try:
        module.upgrade()
    finally:
        module.op = old


def _command(*, ticket_id: str) -> dict[str, object]:
    return {
        "local_order_id": "order-1", "exchange_command_id": "command-1", "ticket_id": ticket_id,
        "account_id": "account-1", "exchange_id": "binance_usdm", "exchange_instrument_id": "instrument-1",
        "runtime_profile_id": "profile-1", "strategy_group_id": "SOR-001", "exposure_episode_id": "episode-1",
        "gateway_symbol": "BTCUSDT", "side": "long", "order_role": "ENTRY", "amount": "0.01",
        "price": None, "stop_price": None, "reduce_only": False, "parent_order_id": None,
    }


def _snapshot() -> FullAccountRiskSnapshot:
    return FullAccountRiskSnapshot(snapshot_ready=True, account_id="account-1", exchange_id="binance_usdm", total_wallet_balance=Decimal("600"), available_balance=Decimal("600"), exchange_total_initial_margin=Decimal("0"), can_trade=True, position_mode="one_way", source_snapshot_id="snapshot-1", observed_at_ms=NOW_MS, valid_until_ms=NOW_MS + 60_000)


def _create_reclaim_tables(conn) -> None:
    for statement in (
        "CREATE TABLE brc_budget_reservations (budget_reservation_id text primary key, status text, ticket_id text, release_reason text)",
        "CREATE TABLE brc_budget_reservation_events (budget_reservation_event_id text primary key, budget_reservation_id text, from_status text, to_status text, reason text, evidence_ref text, created_at_ms bigint)",
        "CREATE TABLE brc_action_time_tickets (ticket_id text primary key, status text)",
        "CREATE TABLE brc_ticket_bound_protected_submit_attempts (ticket_id text, exchange_write_called boolean, status text)",
        "CREATE TABLE brc_ticket_bound_exchange_commands (exchange_command_id text, ticket_id text, command_state text, dispatch_started_at_ms bigint, exchange_order_id text, gateway_symbol text, client_order_id text)",
        "CREATE TABLE brc_account_exposure_current (owner_ticket_id text, position_slot_claimed boolean, exposure_state text, position_qty numeric, working_entry_qty numeric)",
        "CREATE TABLE brc_ticket_bound_order_lifecycle_runs (lifecycle_run_id text primary key, ticket_id text, protected_submit_attempt_id text, status text, first_blocker text, blockers jsonb, updated_at_ms bigint)",
        "CREATE TABLE brc_ticket_bound_lifecycle_events (lifecycle_event_id text primary key, lifecycle_run_id text, ticket_id text, protected_submit_attempt_id text, event_type text, event_payload jsonb, created_at_ms bigint)",
    ):
        conn.execute(sa.text(statement))
