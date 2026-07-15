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
from src.application.action_time.account_capacity_claim import (
    insert_or_get_account_capacity_claim,
)
from src.application.action_time.instrument_risk_facts import InstrumentRiskFacts
from src.application.action_time.account_budget_current import (
    project_account_budget_current,
)
from src.domain.account_risk import AccountRiskPolicy
from src.domain.account_capacity_claim import AccountCapacityClaimPayload
from src.domain.instrument_risk_identity import (
    InstrumentRiskIdentity,
    InstrumentRuleSnapshotRef,
    RiskClusterMembershipSnapshotRef,
)
from src.infrastructure.binance_usdm_account_risk_snapshot import FullAccountRiskSnapshot


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
                "brc_risk_cluster_membership_snapshots",
                "brc_instrument_rule_snapshots",
                "brc_exchange_instruments",
                "brc_account_risk_policy_current",
                "brc_account_budget_current",
            ):
                conn.execute(sa.text(f"DROP TABLE IF EXISTS {table}"))
        engine.dispose()


def test_lifecycle_flat_release_updates_account_budget_once() -> None:
    engine = sa.create_engine(
        _DSN,
        connect_args={"options": f"-c search_path={_SCHEMA}"},
    )
    _create_budget_projection_tables(engine)
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    """INSERT INTO brc_account_exposure_current VALUES
                    ('exposure-1', 'account-1', 'ticket-1', true, 'open_protected',
                     15, 15, 15, 0, 'matched', NULL)"""
                )
            )
            conn.execute(
                sa.text(
                    """INSERT INTO brc_exchange_instruments VALUES
                    ('instrument-1', 'SOLUSDT')"""
                )
            )
            conn.execute(
                sa.text(
                    """INSERT INTO brc_budget_reservations (
                        budget_reservation_id, account_id, runtime_profile_id,
                        ticket_id, status, risk_at_stop, reserved_margin,
                        exchange_instrument_id, exposure_episode_id, symbol,
                        asset_class, instrument_type, primary_risk_cluster_id,
                        cluster_membership_snapshot_id,
                        account_source_fact_snapshot_id,
                        account_fact_schema_version, margin_accounting_state
                    ) VALUES (
                        'reservation-1', 'account-1', 'profile-1', 'ticket-1',
                        'consumed', 15, 150, 'instrument-1', 'episode-1',
                        'SOLUSDT', 'crypto', 'perpetual', 'crypto-beta',
                        'cluster-snapshot-1', 'account-snapshot-1', 'v1',
                        'consumed_by_ticket'
                    )"""
                )
            )
            first = project_account_budget_current(
                conn,
                snapshot=_budget_snapshot("snapshot-open"),
                runtime_profile_id="profile-1",
                policy=_policy(),
                now_ms=1_752_480_000_000,
            )
            assert first.portfolio_held_risk == Decimal("15")
            assert first.claimed_position_slots == 1

            conn.execute(
                sa.text(
                    """UPDATE brc_account_exposure_current
                    SET exposure_state = 'flat', position_slot_claimed = false,
                        held_risk = 0, actual_directional_risk = 0"""
                )
            )
            conn.execute(
                sa.text(
                    "UPDATE brc_budget_reservations SET status = 'released'"
                )
            )
            released = project_account_budget_current(
                conn,
                snapshot=_budget_snapshot("snapshot-flat"),
                runtime_profile_id="profile-1",
                policy=_policy(),
                now_ms=1_752_480_000_100,
            )
            repeated = project_account_budget_current(
                conn,
                snapshot=_budget_snapshot("snapshot-flat-repeat"),
                runtime_profile_id="profile-1",
                policy=_policy(),
                now_ms=1_752_480_000_200,
            )

        assert released.portfolio_held_risk == Decimal("0")
        assert released.claimed_position_slots == 0
        assert released.projection_version == first.projection_version + 1
        assert repeated.projection_version == released.projection_version
    finally:
        with engine.begin() as conn:
            for table in (
                "brc_account_exposure_current",
                "brc_budget_reservations",
                "brc_exchange_instruments",
                "brc_account_budget_current",
            ):
                conn.execute(sa.text(f"DROP TABLE IF EXISTS {table}"))
        engine.dispose()


def test_same_invocation_concurrency_commits_one_claim_ticket_pair() -> None:
    engine = sa.create_engine(
        _DSN,
        connect_args={"options": f"-c search_path={_SCHEMA}"},
    )
    _create_atomic_claim_tables(engine)
    payload = _atomic_claim_payload()
    first_claim_inserted = Event()
    second_started = Event()
    second_finished = Event()
    second_result: dict[str, object] = {}

    def second_materialization() -> None:
        with engine.begin() as conn:
            second_started.set()
            claim = insert_or_get_account_capacity_claim(conn, payload=payload)
            _insert_ticket_for_claim_if_missing(conn, claim.payload)
            second_result["claim"] = claim
        second_finished.set()

    try:
        with engine.begin() as first_conn:
            first_claim = insert_or_get_account_capacity_claim(
                first_conn,
                payload=payload,
            )
            _insert_ticket_for_claim_if_missing(first_conn, first_claim.payload)
            first_claim_inserted.set()
            worker = Thread(target=second_materialization, daemon=True)
            worker.start()
            assert first_claim_inserted.is_set()
            assert second_started.wait(timeout=2)
            assert second_finished.wait(timeout=0.2) is False

        assert second_finished.wait(timeout=5)
        worker.join(timeout=1)
        assert second_result["claim"] == first_claim
        with engine.connect() as conn:
            counts = conn.execute(sa.text("""
              SELECT
                (SELECT COUNT(*) FROM brc_budget_reservations) AS claims,
                (SELECT COUNT(*) FROM brc_action_time_tickets) AS tickets,
                (SELECT COUNT(DISTINCT exposure_episode_id)
                   FROM brc_budget_reservations) AS claim_episodes,
                (SELECT COUNT(DISTINCT exposure_episode_id)
                   FROM brc_action_time_tickets) AS ticket_episodes
            """)).mappings().one()
        assert dict(counts) == {
            "claims": 1,
            "tickets": 1,
            "claim_episodes": 1,
            "ticket_episodes": 1,
        }
    finally:
        with engine.begin() as conn:
            for table in (
                "brc_action_time_tickets",
                "brc_budget_reservations",
                "brc_risk_cluster_membership_snapshots",
                "brc_instrument_rule_snapshots",
                "brc_exchange_instruments",
            ):
                conn.execute(sa.text(f"DROP TABLE IF EXISTS {table}"))
        engine.dispose()


def _create_atomic_claim_tables(engine: sa.Engine) -> None:
    statements = (
        """CREATE TABLE brc_exchange_instruments (
            exchange_instrument_id TEXT PRIMARY KEY, exchange_id TEXT NOT NULL,
            exchange_symbol TEXT NOT NULL,
            instrument_identity_schema_version TEXT NOT NULL
        )""",
        """CREATE TABLE brc_instrument_rule_snapshots (
            instrument_rule_snapshot_id TEXT PRIMARY KEY,
            price_tick NUMERIC NOT NULL, quantity_step NUMERIC NOT NULL,
            min_qty NUMERIC NOT NULL, min_notional NUMERIC NOT NULL,
            contract_multiplier NUMERIC NOT NULL,
            exchange_max_leverage_for_claim_notional INTEGER NOT NULL,
            source_fact_snapshot_id TEXT NOT NULL, valid_until_ms BIGINT NOT NULL
        )""",
        """CREATE TABLE brc_risk_cluster_membership_snapshots (
            cluster_membership_snapshot_id TEXT PRIMARY KEY,
            semantic_hash TEXT NOT NULL
        )""",
        """CREATE TABLE brc_budget_reservations (
            budget_reservation_id TEXT PRIMARY KEY,
            promotion_candidate_id TEXT NOT NULL,
            action_time_lane_input_id TEXT NOT NULL,
            ticket_id TEXT NOT NULL,
            signal_event_id TEXT NOT NULL,
            event_spec_id TEXT NOT NULL,
            runtime_profile_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            strategy_group_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            target_notional NUMERIC NOT NULL,
            leverage NUMERIC NOT NULL,
            selected_leverage INTEGER NOT NULL,
            reserved_margin NUMERIC NOT NULL,
            entry_reference_price NUMERIC NOT NULL,
            stop_price NUMERIC NOT NULL,
            intended_qty NUMERIC NOT NULL,
            risk_at_stop NUMERIC NOT NULL,
            effective_notional NUMERIC NOT NULL,
            planned_stop_risk_budget NUMERIC NOT NULL,
            planned_stop_risk NUMERIC NOT NULL,
            risk_reservation_basis TEXT NOT NULL,
            reserved_at_ms BIGINT NOT NULL,
            expires_at_ms BIGINT NOT NULL,
            status TEXT NOT NULL,
            policy_version TEXT NOT NULL,
            exchange_instrument_id TEXT NOT NULL,
            exposure_episode_id TEXT NOT NULL,
            action_time_invocation_id TEXT NOT NULL UNIQUE,
            asset_class TEXT NOT NULL,
            instrument_type TEXT NOT NULL,
            settlement_asset TEXT NOT NULL,
            margin_asset TEXT NOT NULL,
            instrument_rule_snapshot_id TEXT NOT NULL,
            instrument_rule_schema_version TEXT NOT NULL,
            pricing_source_fact_snapshot_id TEXT NOT NULL,
            account_source_fact_snapshot_id TEXT NOT NULL,
            account_fact_schema_version TEXT NOT NULL,
            primary_risk_cluster_id TEXT NOT NULL,
            cluster_membership_snapshot_id TEXT NOT NULL,
            capacity_claim_schema_version TEXT NOT NULL,
            capacity_claim_hash TEXT NOT NULL,
            reservation_idempotency_key TEXT NOT NULL UNIQUE,
            account_risk_policy_version TEXT NOT NULL,
            account_risk_policy_event_id TEXT NOT NULL,
            allowed_risk_budget NUMERIC NOT NULL,
            margin_accounting_state TEXT NOT NULL,
            account_capacity_projection_version BIGINT NOT NULL,
            reconciliation_state TEXT NOT NULL,
            UNIQUE (budget_reservation_id, ticket_id, exposure_episode_id)
        )""",
        """CREATE TABLE brc_action_time_tickets (
            ticket_id TEXT PRIMARY KEY,
            budget_reservation_id TEXT NOT NULL,
            exposure_episode_id TEXT NOT NULL,
            action_time_invocation_id TEXT NOT NULL UNIQUE,
            capacity_claim_hash TEXT NOT NULL,
            FOREIGN KEY (budget_reservation_id, ticket_id, exposure_episode_id)
              REFERENCES brc_budget_reservations
                (budget_reservation_id, ticket_id, exposure_episode_id)
        )""",
    )
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(sa.text(statement))
        conn.execute(sa.text(
            "INSERT INTO brc_exchange_instruments VALUES "
            "('instrument-1','venue-1','SOLUSDT','v1')"
        ))
        conn.execute(sa.text(
            "INSERT INTO brc_instrument_rule_snapshots VALUES "
            "('rule-1',.01,.001,.001,5,1,20,'rule-source-1',2000)"
        ))
        conn.execute(sa.text(
            "INSERT INTO brc_risk_cluster_membership_snapshots VALUES "
            "('cluster-snapshot-1','cluster-hash-1')"
        ))


def _insert_ticket_for_claim_if_missing(
    conn: sa.Connection,
    payload: AccountCapacityClaimPayload,
) -> None:
    existing = conn.execute(
        sa.text(
            "SELECT ticket_id FROM brc_action_time_tickets "
            "WHERE action_time_invocation_id = :invocation_id"
        ),
        {"invocation_id": payload.action_time_invocation_id},
    ).scalar_one_or_none()
    if existing is not None:
        assert existing == payload.ticket_id
        return
    conn.execute(
        sa.text("""
          INSERT INTO brc_action_time_tickets (
            ticket_id, budget_reservation_id, exposure_episode_id,
            action_time_invocation_id, capacity_claim_hash
          ) VALUES (
            :ticket_id, :reservation_id, :exposure_episode_id,
            :action_time_invocation_id, :capacity_claim_hash
          )
        """),
        {
            "ticket_id": payload.ticket_id,
            "reservation_id": payload.reservation_id,
            "exposure_episode_id": payload.exposure_episode_id,
            "action_time_invocation_id": payload.action_time_invocation_id,
            "capacity_claim_hash": insert_or_get_account_capacity_claim(
                conn,
                payload=payload,
            ).capacity_claim_hash,
        },
    )


def _atomic_claim_payload() -> AccountCapacityClaimPayload:
    return AccountCapacityClaimPayload(
        capacity_claim_schema_version="v1",
        reservation_id="reservation-atomic-1",
        ticket_id="ticket-atomic-1",
        exposure_episode_id="episode-atomic-1",
        action_time_invocation_id="invocation-atomic-1",
        action_time_lane_input_id="lane-atomic-1",
        promotion_candidate_id="promotion-atomic-1",
        signal_event_id="signal-atomic-1",
        event_spec_id="event-spec-atomic-1",
        account_id="account-1",
        runtime_profile_id="profile-1",
        strategy_group_id="MPG-001",
        symbol="SOLUSDT",
        side="long",
        instrument={
            "exchange_instrument_id": "instrument-1",
            "exchange_id": "venue-1",
            "exchange_symbol": "SOLUSDT",
            "asset_class": "crypto",
            "instrument_type": "perpetual",
            "settlement_asset": "USDT",
            "margin_asset": "USDT",
            "instrument_identity_schema_version": "v1",
        },
        rule_snapshot={
            "instrument_rule_snapshot_id": "rule-1",
            "rule_schema_version": "v1",
            "price_tick": Decimal(".01"),
            "quantity_step": Decimal(".001"),
            "min_qty": Decimal(".001"),
            "min_notional": Decimal("5"),
            "contract_multiplier": Decimal("1"),
            "exchange_max_leverage_for_claim_notional": 20,
            "source_fact_snapshot_id": "rule-source-1",
            "valid_until_ms": 2000,
        },
        cluster_snapshot={
            "cluster_membership_snapshot_id": "cluster-snapshot-1",
            "primary_risk_cluster_id": "crypto-beta",
            "semantic_hash": "cluster-hash-1",
        },
        pricing_source_fact_snapshot_id="pricing-1",
        account_source_fact_snapshot_id="account-fact-1",
        account_fact_schema_version="v1",
        account_risk_policy_version="risk-policy-v1",
        account_risk_policy_event_id="policy-event-1",
        owner_policy_version="owner-policy-v1",
        claimed_budget_projection_version=7,
        entry_reference_price=Decimal("150"),
        stop_price=Decimal("145"),
        intended_qty=Decimal(".8"),
        target_notional=Decimal("120"),
        allowed_risk_budget=Decimal("15"),
        planned_stop_risk=Decimal("4"),
        reserved_margin=Decimal("12"),
        selected_leverage=10,
        reserved_at_ms=1000,
        expires_at_ms=2000,
    )


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
            , source_event_id TEXT NOT NULL
        )""",
        """CREATE TABLE brc_risk_cluster_memberships (
            risk_cluster_membership_id TEXT PRIMARY KEY,
            risk_policy_version TEXT NOT NULL, exchange_instrument_id TEXT NOT NULL,
            risk_cluster_id TEXT NOT NULL, cluster_membership_snapshot_id TEXT NOT NULL,
            membership_role TEXT NOT NULL, status TEXT NOT NULL
        )""",
        """CREATE TABLE brc_risk_cluster_membership_snapshots (
            cluster_membership_snapshot_id TEXT PRIMARY KEY,
            risk_policy_version TEXT NOT NULL, primary_risk_cluster_id TEXT NOT NULL,
            semantic_hash TEXT NOT NULL, status TEXT NOT NULL
        )""",
        """CREATE TABLE brc_exchange_instruments (
            exchange_instrument_id TEXT PRIMARY KEY, exchange_id TEXT NOT NULL,
            exchange_symbol TEXT NOT NULL, asset_class TEXT NOT NULL,
            instrument_type TEXT NOT NULL, settlement_asset TEXT NOT NULL,
            margin_asset TEXT NOT NULL, instrument_identity_schema_version TEXT NOT NULL,
            status TEXT NOT NULL
        )""",
        """CREATE TABLE brc_instrument_rule_snapshots (
            instrument_rule_snapshot_id TEXT PRIMARY KEY,
            exchange_instrument_id TEXT NOT NULL, rule_schema_version TEXT NOT NULL,
            price_tick NUMERIC NOT NULL, quantity_step NUMERIC NOT NULL,
            min_qty NUMERIC NOT NULL, min_notional NUMERIC NOT NULL,
            contract_multiplier NUMERIC NOT NULL,
            exchange_max_leverage_for_claim_notional INTEGER NOT NULL,
            source_fact_snapshot_id TEXT NOT NULL, valid_until_ms BIGINT NOT NULL,
            status TEXT NOT NULL
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
                 10, 1, true, 'global_fail_closed', 'active', 'policy-event-1')"""
            )
        )
        conn.execute(
            sa.text(
                """INSERT INTO brc_risk_cluster_memberships VALUES
                ('member-sol', 'policy-1', 'binance_usdm:SOLUSDT',
                 'crypto_usd_beta', 'membership-sol', 'primary', 'active')"""
            )
        )
        conn.execute(sa.text("""INSERT INTO brc_risk_cluster_membership_snapshots
            VALUES ('membership-sol', 'policy-1', 'crypto_usd_beta',
                    'membership-sol', 'current')"""))
        conn.execute(sa.text("""INSERT INTO brc_exchange_instruments VALUES (
            'binance_usdm:SOLUSDT', 'binance_usdm', 'SOLUSDT', 'crypto',
            'perpetual', 'USDT', 'USDT', 'v1', 'active')"""))
        conn.execute(sa.text("""INSERT INTO brc_instrument_rule_snapshots VALUES (
            'rule-sol', 'binance_usdm:SOLUSDT', 'v1', .01, .01, .01, 5, 1,
            20, 'source-sol', 1752480060000, 'current')"""))


def _create_budget_projection_tables(engine: sa.Engine) -> None:
    statements = (
        """CREATE TABLE brc_exchange_instruments (
            exchange_instrument_id TEXT PRIMARY KEY,
            exchange_symbol TEXT NOT NULL
        )""",
        """CREATE TABLE brc_account_exposure_current (
            account_exposure_current_id TEXT PRIMARY KEY, account_id TEXT,
            owner_ticket_id TEXT, position_slot_claimed BOOLEAN, exposure_state TEXT,
            actual_directional_risk NUMERIC, held_risk NUMERIC,
            planned_reserved_risk NUMERIC, unreflected_pending_margin NUMERIC,
            reconciliation_state TEXT, first_blocker TEXT
        )""",
        """CREATE TABLE brc_budget_reservations (
            budget_reservation_id TEXT PRIMARY KEY, account_id TEXT, ticket_id TEXT,
            runtime_profile_id TEXT, status TEXT, risk_at_stop NUMERIC,
            reserved_margin NUMERIC, exchange_instrument_id TEXT,
            exposure_episode_id TEXT, symbol TEXT, asset_class TEXT,
            instrument_type TEXT, primary_risk_cluster_id TEXT,
            cluster_membership_snapshot_id TEXT,
            account_source_fact_snapshot_id TEXT,
            account_fact_schema_version TEXT, margin_accounting_state TEXT
        )""",
        """CREATE TABLE brc_account_budget_current (
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
        )""",
    )
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(sa.text(statement))


def _budget_snapshot(snapshot_id: str) -> FullAccountRiskSnapshot:
    return FullAccountRiskSnapshot(
        snapshot_ready=True,
        account_id="account-1",
        exchange_id="binance_usdm",
        total_wallet_balance=Decimal("600"),
        available_balance=Decimal("500"),
        exchange_total_initial_margin=Decimal("100"),
        can_trade=True,
        position_mode="one_way",
        source_snapshot_id=snapshot_id,
        observed_at_ms=1_752_480_000_000,
        valid_until_ms=1_752_480_060_000,
    )


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
        activation_state="active",
    )


def _candidate() -> AccountCapacityCandidate:
    return AccountCapacityCandidate(
        account_id="account-1",
        runtime_profile_id="profile-1",
        instrument_facts=InstrumentRiskFacts(
            identity=InstrumentRiskIdentity(
                exchange_instrument_id="binance_usdm:SOLUSDT",
                exchange_id="binance_usdm",
                exchange_symbol="SOLUSDT",
                asset_class="crypto",
                instrument_type="perpetual",
                settlement_asset="USDT",
                margin_asset="USDT",
                instrument_identity_schema_version="v1",
            ),
            rule_snapshot=InstrumentRuleSnapshotRef(
                instrument_rule_snapshot_id="rule-sol",
                rule_schema_version="v1",
                price_tick=Decimal(".01"),
                quantity_step=Decimal(".01"),
                min_qty=Decimal(".01"),
                min_notional=Decimal("5"),
                contract_multiplier=Decimal("1"),
                exchange_max_leverage_for_claim_notional=20,
                source_fact_snapshot_id="source-sol",
                valid_until_ms=1_752_480_060_000,
            ),
            cluster_snapshot=RiskClusterMembershipSnapshotRef(
                cluster_membership_snapshot_id="membership-sol",
                primary_risk_cluster_id="crypto_usd_beta",
                semantic_hash="membership-sol",
            ),
        ),
        per_unit_stop_risk=Decimal("3"),
        entry_reference_price=Decimal("150"),
    )
