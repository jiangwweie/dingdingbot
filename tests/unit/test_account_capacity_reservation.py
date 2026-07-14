from __future__ import annotations

from decimal import Decimal

import sqlalchemy as sa

from src.application.action_time.account_capacity_reservation import (
    AccountCapacityCandidate,
    reserve_account_capacity_for_candidate,
)


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
      unknown_exposure_policy TEXT, activation_state TEXT)"""))
    conn.execute(sa.text("CREATE TABLE brc_risk_cluster_memberships (risk_policy_version TEXT, exchange_instrument_id TEXT, risk_cluster_id TEXT)"))
    conn.execute(sa.text("""CREATE TABLE brc_budget_reservations (
      budget_reservation_id TEXT PRIMARY KEY, account_id TEXT, status TEXT, ticket_id TEXT,
      symbol TEXT, side TEXT, risk_at_stop NUMERIC, reserved_margin NUMERIC)"""))
    conn.execute(sa.text("INSERT INTO brc_account_budget_current VALUES ('b','account-1','profile-1','p1','600','500','100','15','0',1,true,NULL,'snapshot-1',1752480060000,1)"))
    conn.execute(sa.text("INSERT INTO brc_account_risk_policy_current VALUES ('account-1','profile-1','p1','.025',2,'.06','.04','.90',10,1,true,'global_fail_closed','active')"))
    conn.execute(sa.text("INSERT INTO brc_risk_cluster_memberships VALUES ('p1','binance_usdm:SOLUSDT','crypto_usd_beta')"))
    return conn
