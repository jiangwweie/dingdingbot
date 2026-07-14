"""PostgreSQL transaction certification for the account-capacity claim.

The test is intentionally opt-in.  It needs an isolated local schema because
its assertion is the actual PostgreSQL ``SELECT ... FOR UPDATE`` behavior,
which SQLite cannot model.
"""

from __future__ import annotations

from decimal import Decimal
import os
from threading import Event, Thread

import pytest
import sqlalchemy as sa

from src.application.action_time.account_capacity_reservation import (
    AccountCapacityCandidate,
    reserve_account_capacity_for_candidate,
)


_DSN = os.getenv("BRC_LOCAL_TEST_POSTGRES_DSN", "")
_SCHEMA = os.getenv("BRC_LOCAL_TEST_POSTGRES_SCHEMA", "")

pytestmark = pytest.mark.skipif(
    not (_DSN and _SCHEMA),
    reason="requires isolated local PostgreSQL schema",
)


def test_only_one_concurrent_candidate_claims_account_budget_projection() -> None:
    engine = sa.create_engine(
        _DSN,
        connect_args={"options": f"-c search_path={_SCHEMA}"},
    )
    _create_tables(engine)
    _seed(engine)
    candidate = _candidate()
    second_started = Event()
    second_finished = Event()
    second_result: dict[str, object] = {}

    def second_claim() -> None:
        with engine.begin() as conn:
            second_started.set()
            second_result["result"] = reserve_account_capacity_for_candidate(
                conn,
                candidate=candidate,
                expected_source_snapshot_id="snapshot-1",
                expected_projection_version=1,
                now_ms=1_752_480_000_000,
            )
        second_finished.set()

    try:
        with engine.begin() as first_conn:
            first_result = reserve_account_capacity_for_candidate(
                first_conn,
                candidate=candidate,
                expected_source_snapshot_id="snapshot-1",
                expected_projection_version=1,
                now_ms=1_752_480_000_000,
            )
            assert first_result.allowed is True
            worker = Thread(target=second_claim, daemon=True)
            worker.start()
            assert second_started.wait(timeout=2)
            assert second_finished.wait(timeout=0.2) is False

        assert second_finished.wait(timeout=5)
        worker.join(timeout=1)
        result = second_result["result"]
        assert result.allowed is False
        assert result.first_blocker == "account_budget_projection_version_changed"
        with engine.connect() as conn:
            version = conn.execute(
                sa.text("SELECT projection_version FROM brc_account_budget_current")
            ).scalar_one()
        assert version == 2
    finally:
        with engine.begin() as conn:
            for table in (
                "brc_account_exposure_current",
                "brc_budget_reservations",
                "brc_risk_cluster_memberships",
                "brc_account_risk_policy_current",
                "brc_account_budget_current",
            ):
                conn.execute(sa.text(f"DROP TABLE IF EXISTS {table}"))
        engine.dispose()


def _create_tables(engine: sa.Engine) -> None:
    statements = (
        """CREATE TABLE brc_account_budget_current (
            account_budget_current_id TEXT PRIMARY KEY, account_id TEXT NOT NULL,
            runtime_profile_id TEXT NOT NULL, risk_policy_version TEXT NOT NULL,
            total_wallet_balance NUMERIC NOT NULL, available_balance NUMERIC NOT NULL,
            exchange_total_initial_margin NUMERIC NOT NULL,
            portfolio_held_risk NUMERIC NOT NULL,
            unreflected_pending_margin NUMERIC NOT NULL,
            claimed_position_slots INTEGER NOT NULL, new_entry_allowed BOOLEAN NOT NULL,
            first_blocker TEXT, source_snapshot_id TEXT NOT NULL,
            valid_until_ms BIGINT NOT NULL, projection_version BIGINT NOT NULL
        )""",
        """CREATE TABLE brc_account_risk_policy_current (
            account_id TEXT NOT NULL, runtime_profile_id TEXT NOT NULL,
            risk_policy_version TEXT NOT NULL,
            planned_stop_risk_fraction NUMERIC NOT NULL,
            max_concurrent_positions INTEGER NOT NULL,
            max_portfolio_open_risk_fraction NUMERIC NOT NULL,
            max_cluster_open_risk_fraction NUMERIC NOT NULL,
            max_portfolio_initial_margin_fraction NUMERIC NOT NULL,
            max_leverage INTEGER NOT NULL, max_new_action_time_lanes INTEGER NOT NULL,
            automatic_downsize_enabled BOOLEAN NOT NULL,
            unknown_exposure_policy TEXT NOT NULL, activation_state TEXT NOT NULL
        )""",
        """CREATE TABLE brc_risk_cluster_memberships (
            risk_policy_version TEXT NOT NULL, exchange_instrument_id TEXT NOT NULL,
            risk_cluster_id TEXT NOT NULL
        )""",
        """CREATE TABLE brc_account_exposure_current (
            account_id TEXT NOT NULL, exchange_instrument_id TEXT NOT NULL,
            held_risk NUMERIC NOT NULL, position_slot_claimed BOOLEAN NOT NULL
        )""",
        """CREATE TABLE brc_budget_reservations (
            budget_reservation_id TEXT PRIMARY KEY, account_id TEXT NOT NULL,
            status TEXT NOT NULL, ticket_id TEXT, symbol TEXT, side TEXT,
            risk_at_stop NUMERIC, reserved_margin NUMERIC,
            account_risk_policy_version TEXT, risk_cluster_id TEXT
        )""",
    )
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(sa.text(statement))


def _seed(engine: sa.Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """INSERT INTO brc_account_budget_current VALUES
                ('budget-1', 'account-1', 'profile-1', 'policy-1', 600, 500,
                 100, 15, 0, 1, true, NULL, 'snapshot-1', 1752480060000, 1)"""
            )
        )
        conn.execute(
            sa.text(
                """INSERT INTO brc_account_risk_policy_current VALUES
                ('account-1', 'profile-1', 'policy-1', .025, 2, .06, .04, .90,
                 10, 1, true, 'global_fail_closed', 'active')"""
            )
        )
        conn.execute(
            sa.text(
                """INSERT INTO brc_risk_cluster_memberships VALUES
                ('policy-1', 'binance_usdm:SOLUSDT', 'crypto_usd_beta')"""
            )
        )


def _candidate() -> AccountCapacityCandidate:
    return AccountCapacityCandidate(
        account_id="account-1",
        runtime_profile_id="profile-1",
        exchange_instrument_id="binance_usdm:SOLUSDT",
        risk_cluster_id="crypto_usd_beta",
        per_unit_stop_risk=Decimal("3"),
        entry_reference_price=Decimal("150"),
        min_qty=Decimal("0.01"),
        qty_step=Decimal("0.01"),
        min_notional=Decimal("5"),
        exchange_max_leverage=20,
    )
