from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa

from src.application.action_time.account_capacity_claim import (
    AccountCapacityClaimConflict,
    insert_or_get_account_capacity_claim,
)
from src.application.action_time.budget_reservation_transition import (
    transition_budget_reservation,
)
from src.domain.account_capacity_claim import AccountCapacityClaimPayload


def test_same_invocation_returns_same_claim() -> None:
    conn = _connection()
    payload = _payload()

    first = insert_or_get_account_capacity_claim(conn, payload=payload)
    second = insert_or_get_account_capacity_claim(conn, payload=payload)

    assert second == first
    assert second.payload.reservation_id == "reservation-1"
    assert second.payload.ticket_id == "ticket-1"
    assert second.payload.exposure_episode_id == "episode-1"
    assert conn.execute(sa.text(
        "SELECT COUNT(*) FROM brc_budget_reservations"
    )).scalar_one() == 1


def test_same_key_different_hash_hard_stops() -> None:
    conn = _connection()
    payload = _payload()
    insert_or_get_account_capacity_claim(conn, payload=payload)

    with pytest.raises(
        AccountCapacityClaimConflict,
        match="account_capacity_claim_idempotency_conflict",
    ):
        insert_or_get_account_capacity_claim(
            conn,
            payload=payload.model_copy(update={"action_time_lane_input_id": "lane-2"}),
        )

    assert conn.execute(sa.text(
        "SELECT COUNT(*) FROM brc_budget_reservations"
    )).scalar_one() == 1


def test_policy_change_does_not_create_second_claim_for_invocation() -> None:
    conn = _connection()
    payload = _payload()
    insert_or_get_account_capacity_claim(conn, payload=payload)

    with pytest.raises(AccountCapacityClaimConflict):
        insert_or_get_account_capacity_claim(
            conn,
            payload=payload.model_copy(
                update={"account_risk_policy_event_id": "policy-event-2"}
            ),
        )

    row = conn.execute(sa.text(
        "SELECT account_risk_policy_event_id, COUNT(*) OVER () AS row_count "
        "FROM brc_budget_reservations"
    )).mappings().one()
    assert row["account_risk_policy_event_id"] == "policy-event-1"
    assert row["row_count"] == 1


def test_transition_cannot_mutate_claim_payload() -> None:
    conn = _connection()
    claim = insert_or_get_account_capacity_claim(conn, payload=_payload())

    result = transition_budget_reservation(
        conn,
        budget_reservation_id="reservation-1",
        to_status="consumed",
        reason="ticket_bound",
        evidence_ref="ticket-1",
        now_ms=1100,
        reservation_updates={"exchange_instrument_id": "instrument-2"},
    )

    row = conn.execute(sa.text(
        "SELECT exchange_instrument_id, capacity_claim_hash, status "
        "FROM brc_budget_reservations"
    )).mappings().one()
    assert result.first_blocker == "budget_reservation_immutable_payload_update_rejected"
    assert row["exchange_instrument_id"] == "instrument-1"
    assert row["capacity_claim_hash"] == claim.capacity_claim_hash
    assert row["status"] == "active"


@pytest.mark.parametrize(
    ("expected_ticket_id", "expected_exposure_episode_id", "expected_capacity_claim_hash"),
    [
        ("ticket-wrong", "episode-1", "unchanged"),
        ("ticket-1", "episode-wrong", "unchanged"),
        ("ticket-1", "episode-1", "wrong-claim-hash"),
    ],
)
def test_consumed_transition_requires_exact_immutable_claim_lineage(
    expected_ticket_id: str,
    expected_exposure_episode_id: str,
    expected_capacity_claim_hash: str,
) -> None:
    conn = _connection()
    claim = insert_or_get_account_capacity_claim(conn, payload=_payload())
    expected_hash = (
        claim.capacity_claim_hash
        if expected_capacity_claim_hash == "unchanged"
        else expected_capacity_claim_hash
    )

    result = transition_budget_reservation(
        conn,
        budget_reservation_id="reservation-1",
        to_status="consumed",
        reason="ticket_bound",
        evidence_ref="ticket-1",
        now_ms=1100,
        expected_ticket_id=expected_ticket_id,
        expected_exposure_episode_id=expected_exposure_episode_id,
        expected_capacity_claim_hash=expected_hash,
    )

    assert result.transitioned is False
    assert result.first_blocker == "budget_reservation_consumed_lineage_mismatch"
    assert conn.execute(
        sa.text(
            "SELECT status, capacity_claim_hash FROM brc_budget_reservations "
            "WHERE budget_reservation_id = 'reservation-1'"
        )
    ).mappings().one() == {
        "status": "active",
        "capacity_claim_hash": claim.capacity_claim_hash,
    }


def _payload() -> AccountCapacityClaimPayload:
    return AccountCapacityClaimPayload(
        capacity_claim_schema_version="v1",
        reservation_id="reservation-1",
        ticket_id="ticket-1",
        exposure_episode_id="episode-1",
        action_time_invocation_id="invocation-1",
        action_time_lane_input_id="lane-1",
        promotion_candidate_id="promotion-1",
        signal_event_id="signal-1",
        event_spec_id="event-spec-1",
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


def _connection() -> sa.Connection:
    conn = sa.create_engine("sqlite://").connect()
    conn.execute(sa.text("""CREATE TABLE brc_budget_reservations (
      budget_reservation_id TEXT PRIMARY KEY, promotion_candidate_id TEXT,
      action_time_lane_input_id TEXT, ticket_id TEXT, signal_event_id TEXT,
      event_spec_id TEXT, runtime_profile_id TEXT, account_id TEXT,
      strategy_group_id TEXT, symbol TEXT, side TEXT, target_notional NUMERIC,
      leverage NUMERIC, selected_leverage INTEGER, reserved_margin NUMERIC,
      entry_reference_price NUMERIC, stop_price NUMERIC, intended_qty NUMERIC,
      risk_at_stop NUMERIC, effective_notional NUMERIC,
      planned_stop_risk_budget NUMERIC, planned_stop_risk NUMERIC,
      risk_reservation_basis TEXT, reserved_at_ms BIGINT, expires_at_ms BIGINT,
      status TEXT, policy_version TEXT, exchange_instrument_id TEXT,
      exposure_episode_id TEXT, action_time_invocation_id TEXT UNIQUE,
      asset_class TEXT, instrument_type TEXT, settlement_asset TEXT,
      margin_asset TEXT, instrument_rule_snapshot_id TEXT,
      instrument_rule_schema_version TEXT, pricing_source_fact_snapshot_id TEXT,
      account_source_fact_snapshot_id TEXT, account_fact_schema_version TEXT,
      primary_risk_cluster_id TEXT, cluster_membership_snapshot_id TEXT,
      capacity_claim_schema_version TEXT, capacity_claim_hash TEXT,
      reservation_idempotency_key TEXT UNIQUE, account_risk_policy_version TEXT,
      account_risk_policy_event_id TEXT, allowed_risk_budget NUMERIC,
      margin_accounting_state TEXT, account_capacity_projection_version BIGINT,
      reconciliation_state TEXT, release_reason TEXT, released_at_ms BIGINT,
      invalidated_at_ms BIGINT, current_first_blocker TEXT)"""))
    conn.execute(sa.text("""CREATE TABLE brc_budget_reservation_events (
      budget_reservation_event_id TEXT PRIMARY KEY, budget_reservation_id TEXT,
      from_status TEXT, to_status TEXT, reason TEXT, evidence_ref TEXT,
      created_at_ms BIGINT)"""))
    conn.execute(sa.text("""CREATE TABLE brc_exchange_instruments (
      exchange_instrument_id TEXT PRIMARY KEY, exchange_id TEXT,
      exchange_symbol TEXT, instrument_identity_schema_version TEXT)"""))
    conn.execute(sa.text("""CREATE TABLE brc_instrument_rule_snapshots (
      instrument_rule_snapshot_id TEXT PRIMARY KEY, price_tick NUMERIC,
      quantity_step NUMERIC, min_qty NUMERIC, min_notional NUMERIC,
      contract_multiplier NUMERIC, exchange_max_leverage_for_claim_notional INTEGER,
      source_fact_snapshot_id TEXT, valid_until_ms BIGINT)"""))
    conn.execute(sa.text("""CREATE TABLE brc_risk_cluster_membership_snapshots (
      cluster_membership_snapshot_id TEXT PRIMARY KEY, semantic_hash TEXT)"""))
    conn.execute(sa.text("INSERT INTO brc_exchange_instruments VALUES ('instrument-1','venue-1','SOLUSDT','v1')"))
    conn.execute(sa.text("INSERT INTO brc_instrument_rule_snapshots VALUES ('rule-1',.01,.001,.001,5,1,20,'rule-source-1',2000)"))
    conn.execute(sa.text("INSERT INTO brc_risk_cluster_membership_snapshots VALUES ('cluster-snapshot-1','cluster-hash-1')"))
    return conn
