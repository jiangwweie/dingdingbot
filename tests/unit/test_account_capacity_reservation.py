from __future__ import annotations

from decimal import Decimal

import sqlalchemy as sa

from src.application.action_time.account_capacity_reservation import (
    AccountCapacityCandidate,
    apply_account_capacity_to_sizing,
    reserve_account_capacity_for_candidate,
)
from src.domain.execution_sizing import ExecutionSizingDecision


def test_second_same_cluster_candidate_downsizes_under_locked_budget_row() -> None:
    conn = _connection()
    result = reserve_account_capacity_for_candidate(
        conn,
        candidate=AccountCapacityCandidate(
            account_id="account-1", runtime_profile_id="profile-1",
            exchange_instrument_id="binance_usdm:SOLUSDT", risk_cluster_id="crypto_usd_beta",
            per_unit_stop_risk=Decimal("3"), entry_reference_price=Decimal("150"),
            min_qty=Decimal("0.01"), qty_step=Decimal("0.01"), min_notional=Decimal("5"),
            exchange_max_leverage=20,
        ),
        expected_source_snapshot_id="snapshot-1",
        expected_projection_version=1,
        now_ms=1_752_480_000_000,
    )
    assert result.allowed is True
    assert result.allocated_risk == Decimal("9")
    assert result.intended_qty == Decimal("3")
    assert result.claimed_projection_version == 2


def test_same_instrument_or_stale_projection_is_blocked_without_claim() -> None:
    conn = _connection()
    conn.execute(sa.text("CREATE TABLE brc_account_exposure_current (account_id TEXT, exchange_instrument_id TEXT, held_risk NUMERIC, position_slot_claimed BOOLEAN)"))
    conn.execute(sa.text("INSERT INTO brc_account_exposure_current VALUES ('account-1','binance_usdm:SOLUSDT','15',true)"))
    candidate = AccountCapacityCandidate(
        account_id="account-1", runtime_profile_id="profile-1", exchange_instrument_id="binance_usdm:SOLUSDT", risk_cluster_id="crypto_usd_beta", per_unit_stop_risk=Decimal("3"), entry_reference_price=Decimal("150"), min_qty=Decimal(".01"), qty_step=Decimal(".01"), min_notional=Decimal("5"), exchange_max_leverage=20,
    )
    same = reserve_account_capacity_for_candidate(conn, candidate=candidate, expected_source_snapshot_id="snapshot-1", expected_projection_version=1, now_ms=1_752_480_000_000)
    stale = reserve_account_capacity_for_candidate(conn, candidate=candidate.model_copy(update={"exchange_instrument_id": "binance_usdm:SOLUSDT"}), expected_source_snapshot_id="snapshot-1", expected_projection_version=99, now_ms=1_752_480_000_000)
    assert same.first_blocker == "account_instrument_already_claimed"
    assert stale.first_blocker == "account_budget_projection_version_changed"


def test_different_cluster_uses_its_own_held_risk_not_portfolio_total() -> None:
    conn = _connection()
    conn.execute(sa.text("CREATE TABLE brc_account_exposure_current (account_id TEXT, exchange_instrument_id TEXT, held_risk NUMERIC, position_slot_claimed BOOLEAN)"))
    conn.execute(sa.text("INSERT INTO brc_account_exposure_current VALUES ('account-1','binance_usdm:ETHUSDT','15',true)"))
    conn.execute(sa.text("INSERT INTO brc_risk_cluster_memberships VALUES ('p1','binance_usdm:ETHUSDT','crypto_usd_beta')"))
    conn.execute(sa.text("UPDATE brc_risk_cluster_memberships SET risk_cluster_id='metals' WHERE exchange_instrument_id='binance_usdm:SOLUSDT'"))
    result = reserve_account_capacity_for_candidate(
        conn,
        candidate=AccountCapacityCandidate(account_id="account-1", runtime_profile_id="profile-1", exchange_instrument_id="binance_usdm:SOLUSDT", risk_cluster_id="metals", per_unit_stop_risk=Decimal("3"), entry_reference_price=Decimal("150"), min_qty=Decimal(".01"), qty_step=Decimal(".01"), min_notional=Decimal("5"), exchange_max_leverage=20),
        expected_source_snapshot_id="snapshot-1", expected_projection_version=1, now_ms=1_752_480_000_000,
    )
    assert result.allowed is True
    assert result.allocated_risk == Decimal("15")


def test_active_reservation_counts_against_its_risk_cluster() -> None:
    conn = _connection()
    conn.execute(
        sa.text(
            """
            ALTER TABLE brc_budget_reservations
            ADD COLUMN exchange_instrument_id TEXT
            """
        )
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_budget_reservations (
              budget_reservation_id, account_id, status, ticket_id, symbol, side,
              risk_at_stop, reserved_margin, account_risk_policy_version,
              risk_cluster_id, exchange_instrument_id
            ) VALUES (
              'existing', 'account-1', 'active', 'ticket-1', 'SOLUSDT', 'long',
              '15', '150', 'p1', 'crypto_usd_beta', 'binance_usdm:SOLUSDT'
            )
            """
        )
    )
    conn.execute(
        sa.text(
            "INSERT INTO brc_risk_cluster_memberships VALUES "
            "('p1', 'binance_usdm:ETHUSDT', 'crypto_usd_beta')"
        )
    )
    result = reserve_account_capacity_for_candidate(
        conn,
        candidate=AccountCapacityCandidate(
            account_id="account-1", runtime_profile_id="profile-1",
            exchange_instrument_id="binance_usdm:ETHUSDT", risk_cluster_id="crypto_usd_beta",
            per_unit_stop_risk=Decimal("3"), entry_reference_price=Decimal("150"),
            min_qty=Decimal("0.01"), qty_step=Decimal("0.01"), min_notional=Decimal("5"),
            exchange_max_leverage=20,
        ),
        expected_source_snapshot_id="snapshot-1",
        expected_projection_version=1,
        now_ms=1_752_480_000_000,
    )
    assert result.allowed is True
    assert result.allocated_risk == Decimal("9")
    assert result.risk_cluster_id == "crypto_usd_beta"
    assert result.account_risk_policy_version == "p1"


def test_active_reservation_for_same_instrument_blocks_second_ticket_claim() -> None:
    conn = _connection()
    conn.execute(
        sa.text(
            "ALTER TABLE brc_budget_reservations "
            "ADD COLUMN exchange_instrument_id TEXT"
        )
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_budget_reservations (
              budget_reservation_id, account_id, status, ticket_id, symbol, side,
              risk_at_stop, reserved_margin, account_risk_policy_version,
              risk_cluster_id, exchange_instrument_id
            ) VALUES (
              'existing-sol', 'account-1', 'active', 'ticket-sol', 'SOLUSDT', 'long',
              '15', '150', 'p1', 'crypto_usd_beta', 'binance_usdm:SOLUSDT'
            )
            """
        )
    )

    result = reserve_account_capacity_for_candidate(
        conn,
        candidate=AccountCapacityCandidate(
            account_id="account-1", runtime_profile_id="profile-1",
            exchange_instrument_id="binance_usdm:SOLUSDT", risk_cluster_id="crypto_usd_beta",
            per_unit_stop_risk=Decimal("3"), entry_reference_price=Decimal("150"),
            min_qty=Decimal("0.01"), qty_step=Decimal("0.01"), min_notional=Decimal("5"),
            exchange_max_leverage=20,
        ),
        expected_source_snapshot_id="snapshot-1",
        expected_projection_version=1,
        now_ms=1_752_480_000_000,
    )

    assert result.first_blocker == "account_instrument_already_claimed"


def test_consumed_reservation_owned_by_exposure_is_not_counted_twice_in_cluster() -> None:
    conn = _connection()
    conn.execute(
        sa.text(
            "CREATE TABLE brc_account_exposure_current ("
            "account_id TEXT, exchange_instrument_id TEXT, held_risk NUMERIC, "
            "position_slot_claimed BOOLEAN, owner_ticket_id TEXT)"
        )
    )
    conn.execute(
        sa.text(
            "INSERT INTO brc_account_exposure_current "
            "(account_id, exchange_instrument_id, held_risk, position_slot_claimed, owner_ticket_id) "
            "VALUES ('account-1', 'binance_usdm:ETHUSDT', '15', true, 'ticket-eth')"
        )
    )
    conn.execute(
        sa.text(
            "INSERT INTO brc_risk_cluster_memberships VALUES "
            "('p1', 'binance_usdm:ETHUSDT', 'crypto_usd_beta')"
        )
    )
    conn.execute(
        sa.text(
            "INSERT INTO brc_budget_reservations VALUES ("
            "'consumed-eth', 'account-1', 'consumed', 'ticket-eth', 'ETHUSDT', 'long', "
            "'15', '150', 'p1', 'crypto_usd_beta')"
        )
    )

    result = reserve_account_capacity_for_candidate(
        conn,
        candidate=AccountCapacityCandidate(
            account_id="account-1", runtime_profile_id="profile-1",
            exchange_instrument_id="binance_usdm:SOLUSDT",
            risk_cluster_id="crypto_usd_beta",
            per_unit_stop_risk=Decimal("3"), entry_reference_price=Decimal("150"),
            min_qty=Decimal("0.01"), qty_step=Decimal("0.01"), min_notional=Decimal("5"),
            exchange_max_leverage=20,
        ),
        expected_source_snapshot_id="snapshot-1",
        expected_projection_version=1,
        now_ms=1_752_480_000_000,
    )

    assert result.allowed is True
    assert result.allocated_risk == Decimal("9")


def test_flat_exposure_does_not_release_consumed_cluster_reservation_early() -> None:
    conn = _connection()
    conn.execute(
        sa.text(
            "CREATE TABLE brc_account_exposure_current ("
            "account_id TEXT, exchange_instrument_id TEXT, held_risk NUMERIC, "
            "position_slot_claimed BOOLEAN, owner_ticket_id TEXT, exposure_state TEXT)"
        )
    )
    conn.execute(
        sa.text(
            "ALTER TABLE brc_budget_reservations "
            "ADD COLUMN exchange_instrument_id TEXT"
        )
    )
    conn.execute(
        sa.text(
            "INSERT INTO brc_account_exposure_current VALUES "
            "('account-1', 'binance_usdm:ETHUSDT', '0', false, 'ticket-eth', 'flat')"
        )
    )
    conn.execute(
        sa.text(
            "INSERT INTO brc_risk_cluster_memberships VALUES "
            "('p1', 'binance_usdm:ETHUSDT', 'crypto_usd_beta')"
        )
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_budget_reservations (
              budget_reservation_id, account_id, status, ticket_id, symbol, side,
              risk_at_stop, reserved_margin, account_risk_policy_version,
              risk_cluster_id, exchange_instrument_id
            ) VALUES (
              'consumed-eth', 'account-1', 'consumed', 'ticket-eth', 'ETHUSDT', 'long',
              '15', '150', 'p1', 'crypto_usd_beta', 'binance_usdm:ETHUSDT'
            )
            """
        )
    )

    result = reserve_account_capacity_for_candidate(
        conn,
        candidate=AccountCapacityCandidate(
            account_id="account-1", runtime_profile_id="profile-1",
            exchange_instrument_id="binance_usdm:SOLUSDT", risk_cluster_id="crypto_usd_beta",
            per_unit_stop_risk=Decimal("3"), entry_reference_price=Decimal("150"),
            min_qty=Decimal("0.01"), qty_step=Decimal("0.01"), min_notional=Decimal("5"),
            exchange_max_leverage=20,
        ),
        expected_source_snapshot_id="snapshot-1",
        expected_projection_version=1,
        now_ms=1_752_480_000_000,
    )

    assert result.allowed is True
    assert result.allocated_risk == Decimal("9")


def test_account_capacity_can_only_downsize_existing_ticket_sizing() -> None:
    base = ExecutionSizingDecision(symbol="SOLUSDT", side="long", entry_reference_price=Decimal("150"), protective_stop_price=Decimal("147"), intended_qty=Decimal("5"), effective_notional=Decimal("750"), selected_leverage=3, reserved_margin=Decimal("250"), planned_stop_risk_budget=Decimal("15"), planned_stop_risk=Decimal("15"), minimum_executable_quantity=Decimal(".01"), pricing_source_fact_snapshot_id="price", account_source_fact_snapshot_id="account", policy_version="p1", risk_reservation_basis="basis", valid_until_ms=2)
    capacity = reserve_account_capacity_for_candidate(_connection(), candidate=AccountCapacityCandidate(account_id="account-1", runtime_profile_id="profile-1", exchange_instrument_id="binance_usdm:SOLUSDT", risk_cluster_id="crypto_usd_beta", per_unit_stop_risk=Decimal("3"), entry_reference_price=Decimal("150"), min_qty=Decimal(".01"), qty_step=Decimal(".01"), min_notional=Decimal("5"), exchange_max_leverage=20), expected_source_snapshot_id="snapshot-1", expected_projection_version=1, now_ms=1_752_480_000_000)
    adapted = apply_account_capacity_to_sizing(base, capacity)
    assert adapted.intended_qty == Decimal("3")
    assert adapted.planned_stop_risk == Decimal("9")
    assert adapted.effective_notional == Decimal("450")


def test_capacity_downsize_records_actual_rounded_stop_risk_and_keeps_ticket_basis() -> None:
    conn = _connection()
    conn.execute(
        sa.text(
            "CREATE TABLE brc_account_exposure_current ("
            "account_id TEXT, exchange_instrument_id TEXT, held_risk NUMERIC, "
            "position_slot_claimed BOOLEAN)"
        )
    )
    conn.execute(
        sa.text(
            "INSERT INTO brc_account_exposure_current VALUES "
            "('account-1', 'binance_usdm:ETHUSDT', '15', true)"
        )
    )
    conn.execute(
        sa.text(
            "INSERT INTO brc_risk_cluster_memberships VALUES "
            "('p1', 'binance_usdm:ETHUSDT', 'crypto_usd_beta')"
        )
    )
    conn.execute(
        sa.text(
            "UPDATE brc_risk_cluster_memberships "
            "SET risk_cluster_id = 'metals' "
            "WHERE exchange_instrument_id = 'binance_usdm:SOLUSDT'"
        )
    )
    capacity = reserve_account_capacity_for_candidate(
        conn,
        candidate=AccountCapacityCandidate(
            account_id="account-1",
            runtime_profile_id="profile-1",
            exchange_instrument_id="binance_usdm:SOLUSDT",
            risk_cluster_id="metals",
            per_unit_stop_risk=Decimal("2.87"),
            entry_reference_price=Decimal("150"),
            min_qty=Decimal("0.01"),
            qty_step=Decimal("0.01"),
            min_notional=Decimal("5"),
            exchange_max_leverage=20,
        ),
        expected_source_snapshot_id="snapshot-1",
        expected_projection_version=1,
        now_ms=1_752_480_000_000,
    )
    base = ExecutionSizingDecision(
        symbol="SOLUSDT",
        side="long",
        entry_reference_price=Decimal("150"),
        protective_stop_price=Decimal("147.13"),
        intended_qty=Decimal("6"),
        effective_notional=Decimal("900"),
        selected_leverage=3,
        reserved_margin=Decimal("300"),
        planned_stop_risk_budget=Decimal("17.22"),
        planned_stop_risk=Decimal("17.22"),
        minimum_executable_quantity=Decimal("0.01"),
        pricing_source_fact_snapshot_id="price",
        account_source_fact_snapshot_id="account",
        policy_version="p1",
        risk_reservation_basis="entry_reference_stop_distance_v0",
        valid_until_ms=2,
    )

    adapted = apply_account_capacity_to_sizing(base, capacity)

    assert capacity.allowed is True
    assert capacity.allocated_risk == Decimal("15")
    assert adapted.intended_qty == Decimal("5.22")
    assert adapted.planned_stop_risk_budget == Decimal("15")
    assert adapted.planned_stop_risk == Decimal("14.9814")
    assert adapted.risk_reservation_basis == "entry_reference_stop_distance_v0"


def _connection() -> sa.Connection:
    engine = sa.create_engine("sqlite://")
    conn = engine.connect()
    conn.execute(sa.text("""CREATE TABLE brc_account_budget_current (
      account_budget_current_id TEXT PRIMARY KEY, account_id TEXT, runtime_profile_id TEXT,
      risk_policy_version TEXT, total_wallet_balance NUMERIC, available_balance NUMERIC,
      exchange_total_initial_margin NUMERIC, portfolio_held_risk NUMERIC,
      unreflected_pending_margin NUMERIC, claimed_position_slots INTEGER,
      new_entry_allowed BOOLEAN, first_blocker TEXT, source_snapshot_id TEXT,
      valid_until_ms BIGINT, projection_version BIGINT)"""))
    conn.execute(sa.text("""CREATE TABLE brc_account_risk_policy_current (
      account_id TEXT, runtime_profile_id TEXT, risk_policy_version TEXT,
      planned_stop_risk_fraction NUMERIC, max_concurrent_positions INTEGER,
      max_portfolio_open_risk_fraction NUMERIC, max_cluster_open_risk_fraction NUMERIC,
      max_portfolio_initial_margin_fraction NUMERIC, max_leverage INTEGER,
      max_new_action_time_lanes INTEGER, automatic_downsize_enabled BOOLEAN,
      unknown_exposure_policy TEXT, activation_state TEXT, source_event_id TEXT)"""))
    conn.execute(sa.text("CREATE TABLE brc_risk_cluster_memberships (risk_policy_version TEXT, exchange_instrument_id TEXT, risk_cluster_id TEXT)"))
    conn.execute(sa.text("""CREATE TABLE brc_budget_reservations (
      budget_reservation_id TEXT PRIMARY KEY, account_id TEXT, status TEXT, ticket_id TEXT,
      symbol TEXT, side TEXT, risk_at_stop NUMERIC, reserved_margin NUMERIC,
      account_risk_policy_version TEXT, risk_cluster_id TEXT)"""))
    conn.execute(sa.text("INSERT INTO brc_account_budget_current VALUES ('b','account-1','profile-1','p1','600','500','100','15','0',1,true,NULL,'snapshot-1',1752480060000,1)"))
    conn.execute(sa.text("INSERT INTO brc_account_risk_policy_current VALUES ('account-1','profile-1','p1','.025',2,'.06','.04','.90',10,1,true,'global_fail_closed','active','policy-event-1')"))
    conn.execute(sa.text("INSERT INTO brc_risk_cluster_memberships VALUES ('p1','binance_usdm:SOLUSDT','crypto_usd_beta')"))
    return conn
