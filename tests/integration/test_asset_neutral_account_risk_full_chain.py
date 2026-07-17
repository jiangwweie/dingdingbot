"""Production-shaped, non-executing account-risk chain certification."""

from __future__ import annotations

from decimal import Decimal
import os
import re
from uuid import uuid4

import pytest
import sqlalchemy as sa

from src.application.action_time.account_budget_current import (
    project_account_budget_current,
)
from src.application.action_time.account_capacity_claim import (
    insert_or_get_account_capacity_claim,
)
from src.application.action_time.account_capacity_reservation import (
    AccountCapacityCandidate,
    reserve_account_capacity_for_candidate,
)
from src.application.action_time.budget_reservation_transition import (
    transition_budget_reservation,
)
from src.application.action_time.finalgate_preflight import (
    account_capacity_current_blockers,
)
from src.application.action_time.instrument_risk_facts import InstrumentRiskFacts
from src.domain.account_capacity_claim import AccountCapacityClaimPayload
from src.domain.account_risk import AccountRiskPolicy
from src.domain.action_time_invocation import ActionTimeInvocation
from src.domain.instrument_risk_identity import (
    InstrumentRiskIdentity,
    InstrumentRuleSnapshotRefV2,
    RiskClusterMembershipSnapshotRef,
    instrument_rule_snapshot_v2_semantic_hash,
)
from src.domain.runtime_lane_identity import RuntimeLaneIdentity
from src.infrastructure.binance_usdm_account_risk_snapshot import FullAccountRiskSnapshot
from tests.integration.test_account_capacity_postgres import (
    _atomic_claim_payload,
    _create_atomic_claim_tables,
    _insert_ticket_for_claim_if_missing,
)


NOW_MS = 1_752_480_000_000
_DSN = os.getenv("BRC_LOCAL_TEST_POSTGRES_DSN", "")
_SAFE_SCHEMA = re.compile(r"^brc_asset_neutral_chain_[a-f0-9]{12}$")

pytestmark = pytest.mark.skipif(not _DSN, reason="requires local PostgreSQL DSN")


class _NoWriteGateway:
    exchange_write_called = False


@pytest.fixture()
def chain_connection():
    admin_engine = sa.create_engine(_DSN)
    schema = f"brc_asset_neutral_chain_{uuid4().hex[:12]}"
    assert _SAFE_SCHEMA.fullmatch(schema)
    engine: sa.Engine | None = None
    try:
        with admin_engine.begin() as conn:
            conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        engine = sa.create_engine(
            _DSN, connect_args={"options": f"-c search_path={schema}"}
        )
        _create_atomic_claim_tables(engine)
        with engine.begin() as conn:
            _extend_schema(conn)
            _seed_current_authority(conn)
            yield conn
    finally:
        if engine is not None:
            engine.dispose()
        with admin_engine.begin() as conn:
            conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        admin_engine.dispose()


def test_asset_neutral_claim_release_and_second_instrument_chain(
    chain_connection: sa.Connection,
) -> None:
    conn = chain_connection
    gateway = _NoWriteGateway()
    lane = _resolve_lane_from_candidate_scope(conn)
    invocation = ActionTimeInvocation(
        action_time_invocation_id="invocation-atomic-1",
        signal_event_id="signal-atomic-1",
        lane_identity=lane,
        source_watermark="pg:signal-atomic-1",
        opened_at_ms=NOW_MS - 1_000,
        expires_at_ms=NOW_MS + 60_000,
    )

    capacity = reserve_account_capacity_for_candidate(
        conn,
        candidate=_capacity_candidate("instrument-1", "rule-1", "cluster-snapshot-1"),
        expected_source_snapshot_id="account-fact-1",
        expected_projection_version=7,
        now_ms=NOW_MS,
    )
    assert capacity.allowed is True
    assert capacity.claimed_projection_version == 8

    first_payload = _claim_payload_for_invocation(invocation)
    first_claim = insert_or_get_account_capacity_claim(conn, payload=first_payload)
    _insert_ticket_for_claim_if_missing(conn, first_claim.payload)
    _seed_owned_exposure(conn, first_claim.payload)
    _set_budget_to_counted_claim(conn, first_claim.payload)

    first_budget = dict(conn.execute(sa.text("""
      SELECT * FROM brc_budget_reservations
      WHERE budget_reservation_id=:reservation_id
    """), {"reservation_id": first_claim.payload.reservation_id}).mappings().one())
    blockers, active = account_capacity_current_blockers(
        conn, budget=first_budget, now_ms=NOW_MS
    )
    assert active is True
    assert blockers == []

    consumed = transition_budget_reservation(
        conn,
        budget_reservation_id=first_claim.payload.reservation_id,
        to_status="consumed",
        reason="production_shaped_ticket_materialized",
        evidence_ref="ticket:ticket-atomic-1",
        now_ms=NOW_MS + 1,
        reservation_updates={"margin_accounting_state": "consumed_by_ticket"},
        expected_ticket_id=first_claim.payload.ticket_id,
        expected_exposure_episode_id=first_claim.payload.exposure_episode_id,
        expected_capacity_claim_hash=first_claim.capacity_claim_hash,
    )
    released = transition_budget_reservation(
        conn,
        budget_reservation_id=first_claim.payload.reservation_id,
        to_status="released",
        reason="certified_flat_lifecycle",
        evidence_ref="exposure:episode-atomic-1:flat",
        now_ms=NOW_MS + 2,
    )
    assert consumed.transitioned is True
    assert released.transitioned is True
    conn.execute(sa.text("""
      UPDATE brc_account_exposure_current
      SET exposure_state='flat', position_slot_claimed=false,
          held_risk=0, actual_directional_risk=0,
          unreflected_pending_margin=0
      WHERE owner_ticket_id=:ticket_id
    """), {"ticket_id": first_claim.payload.ticket_id})
    released_budget = project_account_budget_current(
        conn,
        snapshot=_account_snapshot("account-fact-after-release"),
        runtime_profile_id="profile-1",
        policy=_policy(),
        now_ms=NOW_MS + 3,
    )

    second_payload = _second_instrument_payload(first_payload)
    second_claim = insert_or_get_account_capacity_claim(conn, payload=second_payload)
    _insert_ticket_for_claim_if_missing(conn, second_claim.payload)
    first_ticket = conn.execute(sa.text("""
      SELECT exposure_episode_id FROM brc_action_time_tickets
      WHERE ticket_id=:ticket_id
    """), {"ticket_id": first_claim.payload.ticket_id}).mappings().one()

    assert gateway.exchange_write_called is False
    assert (
        first_claim.payload.instrument.exchange_instrument_id
        != second_claim.payload.instrument.exchange_instrument_id
    )
    assert first_ticket["exposure_episode_id"] == first_claim.payload.exposure_episode_id
    assert released_budget.claimed_position_slots == 0


def _resolve_lane_from_candidate_scope(conn: sa.Connection) -> RuntimeLaneIdentity:
    row = conn.execute(sa.text("""
      SELECT * FROM brc_strategy_group_candidate_scope
      WHERE candidate_scope_id='scope-1' AND status='active'
    """)).mappings().one()
    return RuntimeLaneIdentity(
        candidate_scope_id=row["candidate_scope_id"],
        candidate_scope_event_binding_id="scope-event-binding-1",
        runtime_scope_binding_id="runtime-scope-1",
        runtime_instance_id="runtime-1",
        runtime_profile_id="profile-1",
        policy_current_id="owner-policy-current-1",
        strategy_group_id=row["strategy_group_id"],
        strategy_group_version_id="MPG-001-v1",
        symbol=row["symbol"],
        exchange_instrument_id=row["exchange_instrument_id"],
        asset_class=row["asset_class"],
        side=row["side"],
        event_spec_id="event-spec-atomic-1",
        event_spec_version="v1",
        event_id="MPG-LONG",
        timeframe="1h",
        time_authority="trigger_candle_close_time_ms",
    )


def _claim_payload_for_invocation(
    invocation: ActionTimeInvocation,
) -> AccountCapacityClaimPayload:
    data = _atomic_claim_payload().model_dump(mode="python")
    data.update(
        action_time_invocation_id=invocation.action_time_invocation_id,
        signal_event_id=invocation.signal_event_id,
        account_source_fact_snapshot_id="account-fact-1",
        claimed_budget_projection_version=8,
        reserved_at_ms=NOW_MS,
        expires_at_ms=NOW_MS + 60_000,
    )
    data["rule_snapshot"]["valid_until_ms"] = NOW_MS + 60_000
    return AccountCapacityClaimPayload.model_validate(data)


def _second_instrument_payload(
    first: AccountCapacityClaimPayload,
) -> AccountCapacityClaimPayload:
    data = first.model_dump(mode="python")
    data.update(
        reservation_id="reservation-atomic-2",
        ticket_id="ticket-atomic-2",
        exposure_episode_id="episode-atomic-2",
        action_time_invocation_id="invocation-atomic-2",
        action_time_lane_input_id="lane-atomic-2",
        promotion_candidate_id="promotion-atomic-2",
        signal_event_id="signal-atomic-2",
        symbol="XAUUSD",
        entry_reference_price=Decimal("2400"),
        stop_price=Decimal("2395"),
        intended_qty=Decimal("1"),
        target_notional=Decimal("2400"),
        planned_stop_risk=Decimal("5"),
        reserved_margin=Decimal("240"),
    )
    data["instrument"] = {
        "exchange_instrument_id": "instrument-2",
        "exchange_id": "venue-1",
        "exchange_symbol": "XAUUSD",
        "asset_class": "precious_metal",
        "instrument_type": "future",
        "settlement_asset": "USD",
        "margin_asset": "USD",
        "instrument_identity_schema_version": "v1",
    }
    data["rule_snapshot"] = {
        "instrument_rule_snapshot_id": "rule-2",
        "rule_schema_version": "v1",
        "price_tick": Decimal("0.1"),
        "quantity_step": Decimal("1"),
        "min_qty": Decimal("1"),
        "min_notional": Decimal("100"),
        "contract_multiplier": Decimal("1"),
        "exchange_max_leverage_for_claim_notional": 20,
        "source_fact_snapshot_id": "rule-source-2",
        "valid_until_ms": NOW_MS + 60_000,
    }
    data["cluster_snapshot"] = {
        "cluster_membership_snapshot_id": "cluster-snapshot-2",
        "primary_risk_cluster_id": "metals-beta",
        "semantic_hash": "cluster-hash-2",
    }
    return AccountCapacityClaimPayload.model_validate(data)


def _capacity_candidate(
    instrument_id: str, rule_id: str, membership_id: str
) -> AccountCapacityCandidate:
    return AccountCapacityCandidate(
        account_id="account-1",
        runtime_profile_id="profile-1",
        instrument_facts=InstrumentRiskFacts(
            identity=InstrumentRiskIdentity(
                exchange_instrument_id=instrument_id,
                exchange_id="venue-1",
                exchange_symbol="SOLUSDT",
                asset_class="crypto",
                instrument_type="perpetual",
                settlement_asset="USDT",
                margin_asset="USDT",
                instrument_identity_schema_version="v1",
            ),
            rule_snapshot=InstrumentRuleSnapshotRefV2(
                instrument_rule_snapshot_id=rule_id,
                rule_schema_version="v2",
                price_tick=Decimal("0.01"),
                quantity_step=Decimal("0.001"),
                min_qty=Decimal("0.001"),
                min_notional=Decimal("5"),
                contract_multiplier=Decimal("1"),
                exchange_max_leverage_for_claim_notional=20,
                source_fact_snapshot_id="rule-source-1",
                valid_until_ms=NOW_MS + 60_000,
                risk_calculation_kind="linear_quote_settled",
                semantic_hash=instrument_rule_snapshot_v2_semantic_hash({
                    "instrument_rule_snapshot_id": rule_id,
                    "rule_schema_version": "v2",
                    "price_tick": Decimal("0.01"),
                    "quantity_step": Decimal("0.001"),
                    "min_qty": Decimal("0.001"),
                    "min_notional": Decimal("5"),
                    "contract_multiplier": Decimal("1"),
                    "exchange_max_leverage_for_claim_notional": 20,
                    "source_fact_snapshot_id": "rule-source-1",
                    "valid_until_ms": NOW_MS + 60_000,
                    "risk_calculation_kind": "linear_quote_settled",
                }),
            ),
            cluster_snapshot=RiskClusterMembershipSnapshotRef(
                cluster_membership_snapshot_id=membership_id,
                primary_risk_cluster_id="crypto-beta",
                semantic_hash="cluster-hash-1",
            ),
        ),
        per_unit_stop_risk=Decimal("5"),
        entry_reference_price=Decimal("150"),
    )


def _seed_owned_exposure(
    conn: sa.Connection, payload: AccountCapacityClaimPayload
) -> None:
    conn.execute(sa.text("""
      INSERT INTO brc_account_exposure_current VALUES (
        'exposure-1',:account_id,:ticket_id,:instrument_id,'reserved',0,
        :held_risk,:pending_margin,'matched',true,NULL,:cluster_id
      )
    """), {
        "account_id": payload.account_id,
        "ticket_id": payload.ticket_id,
        "instrument_id": payload.instrument.exchange_instrument_id,
        "held_risk": payload.planned_stop_risk,
        "pending_margin": payload.reserved_margin,
        "cluster_id": payload.cluster_snapshot.primary_risk_cluster_id,
    })


def _set_budget_to_counted_claim(
    conn: sa.Connection, payload: AccountCapacityClaimPayload
) -> None:
    conn.execute(sa.text("""
      UPDATE brc_account_budget_current SET
        projection_version=8, portfolio_held_risk=:risk,
        unreflected_pending_margin=:margin, claimed_position_slots=1
      WHERE account_id=:account_id AND runtime_profile_id=:runtime_profile_id
    """), {
        "risk": payload.planned_stop_risk,
        "margin": payload.reserved_margin,
        "account_id": payload.account_id,
        "runtime_profile_id": payload.runtime_profile_id,
    })


def _account_snapshot(snapshot_id: str) -> FullAccountRiskSnapshot:
    return FullAccountRiskSnapshot(
        snapshot_ready=True,
        account_id="account-1",
        exchange_id="venue-1",
        total_wallet_balance=Decimal("600"),
        available_balance=Decimal("600"),
        exchange_total_initial_margin=Decimal("0"),
        can_trade=True,
        position_mode="one_way",
        source_snapshot_id=snapshot_id,
        observed_at_ms=NOW_MS,
        valid_until_ms=NOW_MS + 60_000,
    )


def _policy() -> AccountRiskPolicy:
    return AccountRiskPolicy(
        risk_policy_version="risk-policy-v1",
        planned_stop_risk_fraction=Decimal("0.025"),
        max_concurrent_positions=2,
        max_portfolio_open_risk_fraction=Decimal("0.06"),
        max_cluster_open_risk_fraction=Decimal("0.05"),
        max_portfolio_initial_margin_fraction=Decimal("0.90"),
        max_leverage=10,
        max_new_action_time_lanes=1,
        automatic_downsize_enabled=True,
        unknown_exposure_policy="global_fail_closed",
        activation_state="active",
    )


def _extend_schema(conn: sa.Connection) -> None:
    statements = (
        "ALTER TABLE brc_exchange_instruments ADD COLUMN asset_class TEXT",
        "ALTER TABLE brc_exchange_instruments ADD COLUMN instrument_type TEXT",
        "ALTER TABLE brc_exchange_instruments ADD COLUMN settlement_asset TEXT",
        "ALTER TABLE brc_exchange_instruments ADD COLUMN margin_asset TEXT",
        "ALTER TABLE brc_exchange_instruments ADD COLUMN status TEXT",
        "ALTER TABLE brc_instrument_rule_snapshots ADD COLUMN exchange_instrument_id TEXT",
        "ALTER TABLE brc_instrument_rule_snapshots ADD COLUMN rule_schema_version TEXT",
        "ALTER TABLE brc_instrument_rule_snapshots ADD COLUMN status TEXT",
        "ALTER TABLE brc_instrument_rule_snapshots ADD COLUMN IF NOT EXISTS risk_calculation_kind TEXT",
        "ALTER TABLE brc_instrument_rule_snapshots ADD COLUMN IF NOT EXISTS semantic_hash TEXT",
        "ALTER TABLE brc_risk_cluster_membership_snapshots ADD COLUMN risk_policy_version TEXT",
        "ALTER TABLE brc_risk_cluster_membership_snapshots ADD COLUMN primary_risk_cluster_id TEXT",
        "ALTER TABLE brc_risk_cluster_membership_snapshots ADD COLUMN status TEXT",
        "ALTER TABLE brc_budget_reservations ADD COLUMN release_reason TEXT",
        "ALTER TABLE brc_budget_reservations ADD COLUMN released_at_ms BIGINT",
        """CREATE TABLE brc_risk_cluster_memberships (
          risk_cluster_membership_id TEXT PRIMARY KEY,
          cluster_membership_snapshot_id TEXT, membership_role TEXT, status TEXT,
          risk_policy_version TEXT, exchange_instrument_id TEXT, risk_cluster_id TEXT
        )""",
        """CREATE TABLE brc_account_risk_policy_current (
          account_id TEXT, runtime_profile_id TEXT, risk_policy_version TEXT,
          planned_stop_risk_fraction NUMERIC, max_concurrent_positions INTEGER,
          max_portfolio_open_risk_fraction NUMERIC,
          max_cluster_open_risk_fraction NUMERIC,
          max_portfolio_initial_margin_fraction NUMERIC, max_leverage INTEGER,
          max_new_action_time_lanes INTEGER, automatic_downsize_enabled BOOLEAN,
          unknown_exposure_policy TEXT, activation_state TEXT, source_event_id TEXT
        )""",
        """CREATE TABLE brc_account_exposure_current (
          account_exposure_current_id TEXT PRIMARY KEY, account_id TEXT,
          owner_ticket_id TEXT, exchange_instrument_id TEXT, exposure_state TEXT,
          actual_directional_risk NUMERIC, held_risk NUMERIC,
          unreflected_pending_margin NUMERIC, reconciliation_state TEXT,
          position_slot_claimed BOOLEAN, first_blocker TEXT,
          primary_risk_cluster_id TEXT
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
        """CREATE TABLE brc_budget_reservation_events (
          budget_reservation_event_id TEXT PRIMARY KEY,
          budget_reservation_id TEXT, from_status TEXT, to_status TEXT,
          reason TEXT, evidence_ref TEXT, created_at_ms BIGINT
        )""",
        """CREATE TABLE brc_strategy_group_candidate_scope (
          candidate_scope_id TEXT PRIMARY KEY, strategy_group_id TEXT,
          symbol TEXT, exchange_instrument_id TEXT, asset_class TEXT,
          side TEXT, status TEXT
        )""",
    )
    for statement in statements:
        conn.execute(sa.text(statement))


def _seed_current_authority(conn: sa.Connection) -> None:
    rule_hash = instrument_rule_snapshot_v2_semantic_hash({
        "instrument_rule_snapshot_id": "rule-1", "rule_schema_version": "v2",
        "price_tick": Decimal(".01"), "quantity_step": Decimal(".001"),
        "min_qty": Decimal(".001"), "min_notional": Decimal("5"),
        "contract_multiplier": Decimal("1"),
        "exchange_max_leverage_for_claim_notional": 20,
        "source_fact_snapshot_id": "rule-source-1",
        "valid_until_ms": NOW_MS + 60_000,
        "risk_calculation_kind": "linear_quote_settled",
    })
    conn.execute(sa.text("""
      UPDATE brc_exchange_instruments SET asset_class='crypto',
        instrument_type='perpetual', settlement_asset='USDT', margin_asset='USDT',
        status='active' WHERE exchange_instrument_id='instrument-1'
    """))
    conn.execute(sa.text("""
      UPDATE brc_instrument_rule_snapshots SET exchange_instrument_id='instrument-1',
        rule_schema_version='v2', risk_calculation_kind='linear_quote_settled',
        semantic_hash=:semantic_hash, status='current', valid_until_ms=:valid_until_ms
      WHERE instrument_rule_snapshot_id='rule-1'
    """), {"valid_until_ms": NOW_MS + 60_000, "semantic_hash": rule_hash})
    conn.execute(sa.text("""
      UPDATE brc_risk_cluster_membership_snapshots
      SET risk_policy_version='risk-policy-v1', primary_risk_cluster_id='crypto-beta',
          status='current' WHERE cluster_membership_snapshot_id='cluster-snapshot-1'
    """))
    conn.execute(sa.text("""INSERT INTO brc_risk_cluster_memberships VALUES
      ('membership-1','cluster-snapshot-1','primary','active','risk-policy-v1',
       'instrument-1','crypto-beta')"""))
    conn.execute(sa.text("""INSERT INTO brc_account_risk_policy_current VALUES
      ('account-1','profile-1','risk-policy-v1',.025,2,.06,.05,.90,10,1,true,
       'global_fail_closed','active','policy-event-1')"""))
    conn.execute(sa.text("""INSERT INTO brc_account_budget_current VALUES
      ('budget-current-1','account-1','profile-1','risk-policy-v1',600,600,0,
       0,0,0,0,0,0,0,15,36,36,540,540,0,0,2,'matched',true,NULL,
       'account-fact-1','account-fact-1',:valid_until_ms,7,:updated_at_ms)"""),
      {"valid_until_ms": NOW_MS + 60_000, "updated_at_ms": NOW_MS})
    conn.execute(sa.text("""INSERT INTO brc_strategy_group_candidate_scope VALUES
      ('scope-1','MPG-001','SOLUSDT','instrument-1','crypto','long','active')"""))
    conn.execute(sa.text("""INSERT INTO brc_exchange_instruments VALUES
      ('instrument-2','venue-1','XAUUSD','v1','precious_metal','future','USD','USD','active')"""))
    conn.execute(sa.text("""INSERT INTO brc_instrument_rule_snapshots VALUES
      ('rule-2',.1,1,1,100,1,20,'rule-source-2',:valid_until_ms,
       'instrument-2','v1','current')"""), {"valid_until_ms": NOW_MS + 60_000})
    conn.execute(sa.text("""INSERT INTO brc_risk_cluster_membership_snapshots VALUES
      ('cluster-snapshot-2','cluster-hash-2','risk-policy-v1','metals-beta','current')"""))
    conn.execute(sa.text("""INSERT INTO brc_risk_cluster_memberships VALUES
      ('membership-2','cluster-snapshot-2','primary','active','risk-policy-v1',
       'instrument-2','metals-beta')"""))
