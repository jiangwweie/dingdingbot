from __future__ import annotations

from decimal import Decimal

import sqlalchemy as sa

from src.application.action_time.account_budget_current import project_account_budget_current
from src.domain.account_risk import AccountRiskPolicy
from src.infrastructure.binance_usdm_account_risk_snapshot import FullAccountRiskSnapshot


NOW_MS = 1_752_480_000_000


def test_consumed_reservation_is_claim_ceiling_not_additive_to_open_exposure() -> None:
    conn = _connection()
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_account_exposure_current VALUES (
                'exposure-1', 'account-1', 'ticket-1', true, 'open_protected',
                '13', '13', '0', '0', 'matched', NULL
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_budget_reservations (
              budget_reservation_id, account_id, runtime_profile_id, ticket_id,
              exchange_instrument_id, exposure_episode_id, status,
              risk_at_stop, reserved_margin, margin_accounting_state,
              symbol, asset_class, instrument_type, primary_risk_cluster_id,
              cluster_membership_snapshot_id, account_source_fact_snapshot_id,
              account_fact_schema_version
            ) VALUES
              ('budget-1', 'account-1', 'profile-1', 'ticket-1',
               'instrument-1', 'episode-1', 'consumed', '15', '30',
               'exchange_reflected', 'SOLUSDT', 'crypto', 'perpetual',
               'crypto-beta', 'membership-1', 'account-fact-1', 'v1'),
              ('budget-2', 'account-1', 'profile-1', 'ticket-2',
               'instrument-2', 'episode-2', 'active', '9', '18',
               'reserved_unreflected', 'SOLUSDT', 'crypto', 'perpetual',
               'crypto-beta', 'membership-1', 'account-fact-1', 'v1')
            """
        )
    )

    budget = project_account_budget_current(
        conn,
        snapshot=_snapshot(),
        runtime_profile_id="profile-1",
        policy=_policy(),
        now_ms=NOW_MS,
    )

    assert budget.open_directional_risk == Decimal("13")
    assert budget.reserved_risk == Decimal("9")
    assert budget.working_entry_risk == Decimal("0")
    assert budget.unknown_held_risk == Decimal("0")
    assert budget.portfolio_held_risk == Decimal("22")
    assert budget.claimed_position_slots == 2
    assert budget.pending_ticket_claims == 1
    assert budget.new_entry_allowed is True


def test_semantically_identical_refresh_preserves_capacity_projection_version() -> None:
    conn = _connection()

    first = project_account_budget_current(
        conn,
        snapshot=_snapshot(),
        runtime_profile_id="profile-1",
        policy=_policy(),
        now_ms=NOW_MS,
    )
    second = project_account_budget_current(
        conn,
        snapshot=_snapshot().model_copy(update={"source_snapshot_id": "snapshot-2"}),
        runtime_profile_id="profile-1",
        policy=_policy(),
        now_ms=NOW_MS + 1,
    )

    assert first.projection_version == 1
    assert second.projection_version == 1


def test_active_unreflected_claim_margin_reduces_account_margin_capacity() -> None:
    conn = _connection()
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_budget_reservations (
              budget_reservation_id, account_id, runtime_profile_id, ticket_id,
              exchange_instrument_id, exposure_episode_id, status,
              risk_at_stop, reserved_margin, margin_accounting_state,
              symbol, asset_class, instrument_type, primary_risk_cluster_id,
              cluster_membership_snapshot_id, account_source_fact_snapshot_id,
              account_fact_schema_version
            ) VALUES
              ('budget-1', 'account-1', 'profile-1', 'ticket-1',
               'instrument-1', 'episode-1', 'active', '9', '100',
               'reserved_unreflected', 'SOLUSDT', 'crypto', 'perpetual',
               'crypto-beta', 'membership-1', 'account-fact-1', 'v1')
            """
        )
    )

    budget = project_account_budget_current(
        conn,
        snapshot=_snapshot(),
        runtime_profile_id="profile-1",
        policy=_policy(),
        now_ms=NOW_MS,
    )

    assert budget.unreflected_pending_margin == Decimal("100")
    assert budget.new_entry_allowed is True
    row = conn.execute(
        sa.text(
            "SELECT portfolio_margin_used, portfolio_margin_remaining "
            "FROM brc_account_budget_current"
        )
    ).mappings().one()
    assert Decimal(str(row["portfolio_margin_used"])) == Decimal("200")
    assert Decimal(str(row["portfolio_margin_remaining"])) == Decimal("340")


def _policy() -> AccountRiskPolicy:
    return AccountRiskPolicy(
        risk_policy_version="policy-1",
        planned_stop_risk_fraction=Decimal("0.025"),
        max_concurrent_positions=2,
        max_portfolio_open_risk_fraction=Decimal("0.06"),
        max_cluster_open_risk_fraction=Decimal("0.04"),
        max_portfolio_initial_margin_fraction=Decimal("0.90"),
        max_leverage=10,
        max_new_action_time_lanes=1,
        automatic_downsize_enabled=True,
        unknown_exposure_policy="global_fail_closed",
        activation_state="shadow",
    )


def _snapshot() -> FullAccountRiskSnapshot:
    return FullAccountRiskSnapshot(
        snapshot_ready=True,
        account_id="account-1",
        exchange_id="binance_usdm",
        total_wallet_balance=Decimal("600"),
        available_balance=Decimal("500"),
        exchange_total_initial_margin=Decimal("100"),
        can_trade=True,
        position_mode="one_way",
        source_snapshot_id="snapshot-1",
        observed_at_ms=NOW_MS,
        valid_until_ms=NOW_MS + 60_000,
    )


def _connection() -> sa.Connection:
    engine = sa.create_engine("sqlite://")
    conn = engine.connect()
    conn.execute(
        sa.text(
            """
            CREATE TABLE brc_account_exposure_current (
                account_exposure_current_id TEXT PRIMARY KEY, account_id TEXT,
                owner_ticket_id TEXT, position_slot_claimed BOOLEAN, exposure_state TEXT,
                actual_directional_risk NUMERIC, held_risk NUMERIC, planned_reserved_risk NUMERIC,
                unreflected_pending_margin NUMERIC, reconciliation_state TEXT,
                first_blocker TEXT
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE TABLE brc_budget_reservations (
                budget_reservation_id TEXT PRIMARY KEY, account_id TEXT,
                runtime_profile_id TEXT, ticket_id TEXT,
                exchange_instrument_id TEXT, exposure_episode_id TEXT,
                status TEXT, risk_at_stop NUMERIC, reserved_margin NUMERIC,
                margin_accounting_state TEXT, symbol TEXT, asset_class TEXT,
                instrument_type TEXT, primary_risk_cluster_id TEXT,
                cluster_membership_snapshot_id TEXT,
                account_source_fact_snapshot_id TEXT,
                account_fact_schema_version TEXT
            )
            """
        )
    )
    conn.execute(
        sa.text(
            "CREATE TABLE brc_exchange_instruments ("
            "exchange_instrument_id TEXT PRIMARY KEY, exchange_symbol TEXT)"
        )
    )
    conn.execute(
        sa.text(
            "INSERT INTO brc_exchange_instruments VALUES "
            "('instrument-1','SOLUSDT'),('instrument-2','ETHUSDT')"
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE TABLE brc_account_budget_current (
                account_budget_current_id TEXT PRIMARY KEY, account_id TEXT,
                runtime_profile_id TEXT, risk_policy_version TEXT,
                total_wallet_balance NUMERIC, available_balance NUMERIC,
                exchange_total_initial_margin NUMERIC, reserved_risk NUMERIC,
                working_entry_risk NUMERIC, open_directional_risk NUMERIC,
                unknown_held_risk NUMERIC, portfolio_held_risk NUMERIC,
                unreflected_pending_margin NUMERIC, portfolio_margin_used NUMERIC,
                ticket_risk_limit NUMERIC, portfolio_risk_limit NUMERIC,
                portfolio_risk_remaining NUMERIC, portfolio_margin_limit NUMERIC,
                portfolio_margin_remaining NUMERIC, claimed_position_slots INTEGER,
                pending_ticket_claims INTEGER, max_concurrent_positions INTEGER,
                reconciliation_state TEXT, new_entry_allowed BOOLEAN, first_blocker TEXT,
                source_snapshot_id TEXT, source_watermark TEXT, valid_until_ms BIGINT,
                projection_version BIGINT, updated_at_ms BIGINT
            )
            """
        )
    )
    return conn
