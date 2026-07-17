from __future__ import annotations

from decimal import Decimal

import sqlalchemy as sa

from src.application.action_time import finalgate_preflight as subject
from src.application.action_time import runtime_safety_state
from src.application.action_time.account_capacity_claim import (
    insert_or_get_account_capacity_claim,
)
from src.domain.account_capacity_claim import AccountCapacityClaimPayload
from src.domain.instrument_risk_identity import instrument_rule_snapshot_v2_semantic_hash
from tests.unit.test_account_capacity_claim_persistence import (
    _connection as _claim_connection,
    _payload as _claim_payload,
)


NOW_MS = 1_752_480_000_000


def test_new_snapshot_id_with_same_semantic_capacity_passes() -> None:
    conn, budget = _active_connection()
    conn.execute(
        sa.text(
            "UPDATE brc_account_budget_current "
            "SET source_snapshot_id = 'account-fact-2'"
        )
    )

    blockers, active = subject.account_capacity_current_blockers(
        conn, budget=budget, now_ms=NOW_MS
    )

    assert active is True
    assert blockers == []


def test_post_claim_projection_version_mismatch_blocks() -> None:
    conn, budget = _active_connection()
    conn.execute(
        sa.text(
            "UPDATE brc_account_budget_current SET projection_version = 8"
        )
    )

    blockers, active = subject.account_capacity_current_blockers(
        conn, budget=budget, now_ms=NOW_MS
    )

    assert active is True
    assert blockers == ["account_capacity_post_claim_projection_version_mismatch"]


def test_claim_hash_mismatch_blocks() -> None:
    conn, budget = _active_connection()
    conn.execute(
        sa.text(
            "UPDATE brc_budget_reservations SET intended_qty = intended_qty + .001"
        )
    )

    blockers, active = subject.account_capacity_current_blockers(
        conn, budget=budget, now_ms=NOW_MS
    )

    assert active is True
    assert blockers == ["account_capacity_claim_hash_mismatch"]


def test_claim_counted_zero_or_twice_blocks() -> None:
    conn, budget = _active_connection()
    conn.execute(sa.text("UPDATE brc_budget_reservations SET status = 'released'"))
    zero, _ = subject.account_capacity_current_blockers(
        conn, budget=budget, now_ms=NOW_MS
    )
    assert zero == ["account_capacity_claim_not_counted"]

    conn.execute(sa.text("UPDATE brc_budget_reservations SET status = 'active'"))
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_budget_reservations (
              budget_reservation_id, ticket_id, account_id, runtime_profile_id,
              status, action_time_invocation_id, reservation_idempotency_key
            ) VALUES (
              'reservation-duplicate', 'ticket-1', 'account-1', 'profile-1',
              'active', 'invocation-duplicate', 'idempotency-duplicate'
            )
            """
        )
    )
    twice, _ = subject.account_capacity_current_blockers(
        conn, budget=budget, now_ms=NOW_MS
    )
    assert twice == ["account_capacity_claim_count_mismatch"]


def test_own_claim_is_excluded_before_capacity_recheck() -> None:
    conn, budget = _active_connection()
    conn.execute(
        sa.text(
            """
            UPDATE brc_account_budget_current
            SET claimed_position_slots = 2,
                portfolio_held_risk = 30,
                unreflected_pending_margin = 24
            """
        )
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_account_exposure_current VALUES (
              'exposure-other', 'account-1', 'ticket-other', 'open_protected',
              26, 26, 0, 'matched', true, NULL, 'crypto-beta'
            )
            """
        )
    )

    blockers, active = subject.account_capacity_current_blockers(
        conn, budget=budget, now_ms=NOW_MS
    )

    assert active is True
    assert blockers == []


def test_new_external_position_blocks() -> None:
    conn, budget = _active_connection()
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_account_exposure_current VALUES (
              'exposure-external', 'account-1', NULL, 'unknown', 0, 0, 0,
              'unknown', true,
              'account_exchange_position_unknown_global_fail_closed', NULL
            )
            """
        )
    )

    blockers, _ = subject.account_capacity_current_blockers(
        conn, budget=budget, now_ms=NOW_MS
    )

    assert blockers == ["account_exchange_position_unknown_global_fail_closed"]


def test_rule_change_that_keeps_order_legal_passes() -> None:
    conn, budget = _active_connection()
    _replace_current_rule(conn, quantity_step="0.01")

    blockers, _ = subject.account_capacity_current_blockers(
        conn, budget=budget, now_ms=NOW_MS
    )

    assert blockers == []


def test_rule_change_that_invalidates_qty_blocks() -> None:
    conn, budget = _active_connection()
    _replace_current_rule(conn, quantity_step="0.3")

    blockers, _ = subject.account_capacity_current_blockers(
        conn, budget=budget, now_ms=NOW_MS
    )

    assert blockers == ["account_capacity_claim_quantity_rule_invalid"]


def test_active_capacity_claim_is_invalidated_when_owner_policy_event_changes() -> None:
    conn, budget = _active_connection()
    conn.execute(
        sa.text(
            "UPDATE brc_account_risk_policy_current "
            "SET source_event_id = 'policy-event-rollback'"
        )
    )

    blockers, active = subject.account_capacity_current_blockers(
        conn, budget=budget, now_ms=NOW_MS
    )

    assert active is True
    assert blockers == ["account_risk_policy_event_changed"]


def test_primary_cluster_change_invalidates_claim() -> None:
    conn, budget = _active_connection()
    conn.execute(sa.text(
        "UPDATE brc_risk_cluster_membership_snapshots SET status='historical'"
    ))
    conn.execute(sa.text("""
      INSERT INTO brc_risk_cluster_membership_snapshots (
        cluster_membership_snapshot_id, semantic_hash, risk_policy_version,
        primary_risk_cluster_id, status
      ) VALUES (
        'cluster-snapshot-2','cluster-hash-2','risk-policy-v1',
        'crypto-alt-beta','current'
      )
    """))
    conn.execute(sa.text("""INSERT INTO brc_risk_cluster_memberships VALUES
      ('cluster-snapshot-2','primary','active','risk-policy-v1',
       'instrument-1','crypto-alt-beta')
    """))

    blockers, active = subject.account_capacity_current_blockers(
        conn, budget=budget, now_ms=NOW_MS
    )

    assert active is True
    assert blockers == ["account_capacity_primary_cluster_changed"]


def test_legacy_budget_reservation_does_not_opt_into_capacity_gate() -> None:
    blockers, active = subject.account_capacity_current_blockers(
        _legacy_connection(),
        budget={"account_id": "account-1", "runtime_profile_id": "profile-1"},
        now_ms=NOW_MS,
    )

    assert active is False
    assert blockers == []


def test_runtime_safety_replaces_only_flat_position_account_fact_for_active_claim() -> None:
    blockers, fresh, conflict = runtime_safety_state._relax_legacy_account_position_fact_gate(
        facts={
            "public_fact_snapshot_id": {
                "computed": True,
                "satisfied": True,
                "freshness_state": "fresh",
                "valid_until_ms": NOW_MS + 1,
            },
            "account_safe_fact_snapshot_id": {
                "computed": True,
                "satisfied": False,
                "freshness_state": "stale",
                "valid_until_ms": NOW_MS + 1,
                "fact_values": {"account_capacity_base_safe": True},
            },
        },
        blockers=[
            "account_safe_fact_snapshot_id_not_satisfied",
            "account_safe_fact_snapshot_id_not_fresh",
            "account_safe_fact_not_true",
            "open_orders_not_clear",
            "active_position_or_open_order_conflict",
        ],
        now_ms=NOW_MS,
    )

    assert blockers == []
    assert fresh is True
    assert conflict is False


def _active_connection() -> tuple[sa.Connection, dict[str, object]]:
    conn = _claim_connection()
    conn.execute(sa.text("ALTER TABLE brc_exchange_instruments ADD COLUMN asset_class TEXT"))
    conn.execute(sa.text("ALTER TABLE brc_exchange_instruments ADD COLUMN instrument_type TEXT"))
    conn.execute(sa.text("ALTER TABLE brc_exchange_instruments ADD COLUMN settlement_asset TEXT"))
    conn.execute(sa.text("ALTER TABLE brc_exchange_instruments ADD COLUMN margin_asset TEXT"))
    conn.execute(sa.text("ALTER TABLE brc_exchange_instruments ADD COLUMN status TEXT"))
    conn.execute(sa.text("""
      UPDATE brc_exchange_instruments SET asset_class='crypto',
      instrument_type='perpetual', settlement_asset='USDT', margin_asset='USDT',
      status='active'
    """))
    conn.execute(sa.text("ALTER TABLE brc_instrument_rule_snapshots ADD COLUMN exchange_instrument_id TEXT"))
    conn.execute(sa.text("ALTER TABLE brc_instrument_rule_snapshots ADD COLUMN rule_schema_version TEXT"))
    conn.execute(sa.text("ALTER TABLE brc_instrument_rule_snapshots ADD COLUMN status TEXT"))
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
      UPDATE brc_instrument_rule_snapshots SET exchange_instrument_id='instrument-1',
      rule_schema_version='v2', risk_calculation_kind='linear_quote_settled',
      semantic_hash=:semantic_hash, status='current', valid_until_ms=:valid_until_ms
    """), {"valid_until_ms": NOW_MS + 60_000, "semantic_hash": rule_hash})
    conn.execute(sa.text("ALTER TABLE brc_risk_cluster_membership_snapshots ADD COLUMN risk_policy_version TEXT"))
    conn.execute(sa.text("ALTER TABLE brc_risk_cluster_membership_snapshots ADD COLUMN primary_risk_cluster_id TEXT"))
    conn.execute(sa.text("ALTER TABLE brc_risk_cluster_membership_snapshots ADD COLUMN status TEXT"))
    conn.execute(sa.text("""
      UPDATE brc_risk_cluster_membership_snapshots
      SET risk_policy_version='risk-policy-v1', primary_risk_cluster_id='crypto-beta',
          status='current'
    """))
    conn.execute(sa.text("""CREATE TABLE brc_risk_cluster_memberships (
      cluster_membership_snapshot_id TEXT, membership_role TEXT, status TEXT,
      risk_policy_version TEXT, exchange_instrument_id TEXT, risk_cluster_id TEXT
    )"""))
    conn.execute(sa.text("""INSERT INTO brc_risk_cluster_memberships VALUES
      ('cluster-snapshot-1','primary','active','risk-policy-v1','instrument-1','crypto-beta')
    """))
    conn.execute(sa.text("""CREATE TABLE brc_account_risk_policy_current (
      account_id TEXT, runtime_profile_id TEXT, risk_policy_version TEXT,
      activation_state TEXT, source_event_id TEXT, max_concurrent_positions INTEGER,
      max_portfolio_open_risk_fraction NUMERIC, max_cluster_open_risk_fraction NUMERIC,
      max_portfolio_initial_margin_fraction NUMERIC
    )"""))
    conn.execute(sa.text("""INSERT INTO brc_account_risk_policy_current VALUES
      ('account-1','profile-1','risk-policy-v1','active','policy-event-1',2,.06,.05,.90)
    """))
    conn.execute(sa.text("""CREATE TABLE brc_account_budget_current (
      account_budget_current_id TEXT, account_id TEXT, runtime_profile_id TEXT,
      risk_policy_version TEXT, total_wallet_balance NUMERIC, available_balance NUMERIC,
      portfolio_held_risk NUMERIC, unreflected_pending_margin NUMERIC,
      exchange_total_initial_margin NUMERIC, claimed_position_slots INTEGER,
      valid_until_ms BIGINT, reconciliation_state TEXT, first_blocker TEXT,
      projection_version BIGINT, source_snapshot_id TEXT
    )"""))
    conn.execute(sa.text("""INSERT INTO brc_account_budget_current VALUES
      ('budget-current-1','account-1','profile-1','risk-policy-v1',600,500,4,12,0,1,
       :valid_until_ms,'matched',NULL,7,'account-fact-1')
    """), {"valid_until_ms": NOW_MS + 60_000})
    conn.execute(sa.text("""CREATE TABLE brc_account_exposure_current (
      account_exposure_current_id TEXT, account_id TEXT, owner_ticket_id TEXT,
      exposure_state TEXT, actual_directional_risk NUMERIC, held_risk NUMERIC,
      unreflected_pending_margin NUMERIC, reconciliation_state TEXT,
      position_slot_claimed BOOLEAN, first_blocker TEXT,
      primary_risk_cluster_id TEXT
    )"""))
    conn.execute(sa.text("""INSERT INTO brc_account_exposure_current VALUES
      ('exposure-1','account-1','ticket-1','reserved',0,4,12,'matched',true,NULL,'crypto-beta')
    """))
    payload_data = _claim_payload().model_dump(mode="python")
    payload_data["reserved_at_ms"] = NOW_MS - 1_000
    payload_data["expires_at_ms"] = NOW_MS + 60_000
    payload_data["rule_snapshot"]["valid_until_ms"] = NOW_MS + 60_000
    payload = AccountCapacityClaimPayload.model_validate(payload_data)
    insert_or_get_account_capacity_claim(conn, payload=payload)
    budget = dict(conn.execute(sa.text(
        "SELECT * FROM brc_budget_reservations WHERE budget_reservation_id='reservation-1'"
    )).mappings().one())
    return conn, budget


def _replace_current_rule(conn: sa.Connection, *, quantity_step: str) -> None:
    conn.execute(sa.text(
        "UPDATE brc_instrument_rule_snapshots SET status='historical' WHERE status='current'"
    ))
    rule_hash = instrument_rule_snapshot_v2_semantic_hash({
        "instrument_rule_snapshot_id": "rule-2", "rule_schema_version": "v2",
        "price_tick": Decimal(".01"), "quantity_step": Decimal(quantity_step),
        "min_qty": Decimal(".001"), "min_notional": Decimal("5"),
        "contract_multiplier": Decimal("1"),
        "exchange_max_leverage_for_claim_notional": 20,
        "source_fact_snapshot_id": "rule-source-2",
        "valid_until_ms": NOW_MS + 60_000,
        "risk_calculation_kind": "linear_quote_settled",
    })
    conn.execute(sa.text("""
      INSERT INTO brc_instrument_rule_snapshots (
        instrument_rule_snapshot_id, price_tick, quantity_step, min_qty,
        min_notional, contract_multiplier,
        exchange_max_leverage_for_claim_notional, source_fact_snapshot_id,
        valid_until_ms, exchange_instrument_id, rule_schema_version,
        risk_calculation_kind, semantic_hash, status
      ) VALUES (
        'rule-2', .01, :quantity_step, .001, 5, 1, 20, 'rule-source-2',
        :valid_until_ms, 'instrument-1', 'v2', 'linear_quote_settled',
        :semantic_hash, 'current'
      )
    """), {"quantity_step": quantity_step, "valid_until_ms": NOW_MS + 60_000, "semantic_hash": rule_hash})


def _legacy_connection() -> sa.Connection:
    return sa.create_engine("sqlite://").connect()
