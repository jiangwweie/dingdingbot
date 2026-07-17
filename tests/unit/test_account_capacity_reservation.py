from __future__ import annotations

from decimal import Decimal

import sqlalchemy as sa

from src.application.action_time.account_capacity_reservation import (
    AccountCapacityCandidate,
    apply_account_capacity_to_sizing,
    reserve_account_capacity_for_candidate,
)
from src.application.action_time.instrument_risk_facts import (
    load_instrument_risk_facts,
)
from src.domain.execution_sizing import ExecutionSizingDecision
from src.domain.instrument_risk_identity import instrument_rule_snapshot_v2_semantic_hash


def test_second_same_cluster_candidate_downsizes_under_locked_budget_row() -> None:
    conn = _connection()
    result = reserve_account_capacity_for_candidate(
        conn,
        candidate=_candidate(conn),
        expected_source_snapshot_id="snapshot-1",
        expected_projection_version=1,
        now_ms=1_752_480_000_000,
    )
    assert result.allowed is True
    assert result.allocated_risk == Decimal("9")
    assert result.intended_qty == Decimal("3")
    assert result.claimed_projection_version == 2
    assert result.instrument_rule_snapshot_id == "rule-binance_usdm-SOLUSDT"
    assert result.cluster_membership_snapshot_id == (
        "membership-binance_usdm-SOLUSDT-crypto_usd_beta"
    )


def test_secondary_membership_does_not_reduce_v0_capacity() -> None:
    conn = _connection()
    candidate = _candidate(conn)
    snapshot_id = candidate.instrument_facts.cluster_snapshot.cluster_membership_snapshot_id
    conn.execute(sa.text("""INSERT INTO brc_risk_cluster_memberships VALUES (
      'secondary-sol', 'p1', 'binance_usdm:SOLUSDT', 'secondary-volatility',
      :snapshot_id, 'secondary', 'active', 1, 'owner')"""), {
        "snapshot_id": snapshot_id,
    })

    result = reserve_account_capacity_for_candidate(
        conn,
        candidate=candidate,
        expected_source_snapshot_id="snapshot-1",
        expected_projection_version=1,
        now_ms=1_752_480_000_000,
    )

    assert result.allowed is True
    assert result.allocated_risk == Decimal("9")


def test_capacity_rejects_rule_snapshot_superseded_after_fact_load() -> None:
    conn = _connection()
    candidate = _candidate(conn)
    conn.execute(sa.text(
        "UPDATE brc_instrument_rule_snapshots SET status = 'superseded'"
    ))

    result = reserve_account_capacity_for_candidate(
        conn,
        candidate=candidate,
        expected_source_snapshot_id="snapshot-1",
        expected_projection_version=1,
        now_ms=1_752_480_000_000,
    )

    assert result.first_blocker == "instrument_rule_snapshot_missing_or_changed"


def test_same_instrument_or_stale_projection_is_blocked_without_claim() -> None:
    conn = _connection()
    conn.execute(sa.text("CREATE TABLE brc_account_exposure_current (account_id TEXT, exchange_instrument_id TEXT, held_risk NUMERIC, position_slot_claimed BOOLEAN)"))
    conn.execute(sa.text("INSERT INTO brc_account_exposure_current VALUES ('account-1','binance_usdm:SOLUSDT','15',true)"))
    candidate = _candidate(conn)
    same = reserve_account_capacity_for_candidate(conn, candidate=candidate, expected_source_snapshot_id="snapshot-1", expected_projection_version=1, now_ms=1_752_480_000_000)
    stale = reserve_account_capacity_for_candidate(conn, candidate=candidate, expected_source_snapshot_id="snapshot-1", expected_projection_version=99, now_ms=1_752_480_000_000)
    assert same.first_blocker == "account_instrument_already_claimed"
    assert stale.first_blocker == "account_budget_projection_version_changed"


def test_different_cluster_uses_its_own_held_risk_not_portfolio_total() -> None:
    conn = _connection()
    conn.execute(sa.text("CREATE TABLE brc_account_exposure_current (account_id TEXT, exchange_instrument_id TEXT, held_risk NUMERIC, position_slot_claimed BOOLEAN)"))
    conn.execute(sa.text("INSERT INTO brc_account_exposure_current VALUES ('account-1','binance_usdm:ETHUSDT','15',true)"))
    _seed_instrument_facts(conn, "binance_usdm:ETHUSDT", "crypto_usd_beta")
    result = reserve_account_capacity_for_candidate(
        conn,
        candidate=_candidate(conn, cluster_id="metals"),
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
    result = reserve_account_capacity_for_candidate(
        conn,
        candidate=_candidate(conn, instrument_id="binance_usdm:ETHUSDT"),
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
        candidate=_candidate(conn),
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
    _seed_instrument_facts(conn, "binance_usdm:ETHUSDT", "crypto_usd_beta")
    conn.execute(
        sa.text(
            "INSERT INTO brc_budget_reservations VALUES ("
            "'consumed-eth', 'account-1', 'consumed', 'ticket-eth', 'ETHUSDT', 'long', "
            "'15', '150', 'p1', 'crypto_usd_beta')"
        )
    )

    result = reserve_account_capacity_for_candidate(
        conn,
        candidate=_candidate(conn),
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
    _seed_instrument_facts(conn, "binance_usdm:ETHUSDT", "crypto_usd_beta")
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
        candidate=_candidate(conn),
        expected_source_snapshot_id="snapshot-1",
        expected_projection_version=1,
        now_ms=1_752_480_000_000,
    )

    assert result.allowed is True
    assert result.allocated_risk == Decimal("9")


def test_account_capacity_can_only_downsize_existing_ticket_sizing() -> None:
    base = ExecutionSizingDecision(symbol="SOLUSDT", side="long", entry_reference_price=Decimal("150"), protective_stop_price=Decimal("147"), intended_qty=Decimal("5"), effective_notional=Decimal("750"), selected_leverage=3, reserved_margin=Decimal("250"), planned_stop_risk_budget=Decimal("15"), planned_stop_risk=Decimal("15"), minimum_executable_quantity=Decimal(".01"), pricing_source_fact_snapshot_id="price", account_source_fact_snapshot_id="account", policy_version="p1", risk_reservation_basis="basis", valid_until_ms=2)
    conn = _connection()
    capacity = reserve_account_capacity_for_candidate(conn, candidate=_candidate(conn), expected_source_snapshot_id="snapshot-1", expected_projection_version=1, now_ms=1_752_480_000_000)
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
    _seed_instrument_facts(conn, "binance_usdm:ETHUSDT", "crypto_usd_beta")
    capacity = reserve_account_capacity_for_candidate(
        conn,
        candidate=_candidate(
            conn,
            cluster_id="metals",
            per_unit_stop_risk=Decimal("2.87"),
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
    conn.execute(sa.text("""CREATE TABLE brc_exchange_instruments (
      exchange_instrument_id TEXT PRIMARY KEY, exchange_id TEXT, exchange_symbol TEXT,
      asset_class TEXT, instrument_type TEXT, settlement_asset TEXT, margin_asset TEXT,
      instrument_identity_schema_version TEXT, status TEXT)"""))
    conn.execute(sa.text("""CREATE TABLE brc_instrument_rule_snapshots (
      instrument_rule_snapshot_id TEXT PRIMARY KEY, exchange_instrument_id TEXT,
      rule_schema_version TEXT, price_tick NUMERIC, quantity_step NUMERIC,
      min_qty NUMERIC, min_notional NUMERIC, contract_multiplier NUMERIC,
      exchange_max_leverage_for_claim_notional INTEGER, source_fact_snapshot_id TEXT,
      valid_until_ms BIGINT, risk_calculation_kind TEXT, semantic_hash TEXT,
      status TEXT, created_at_ms BIGINT)"""))
    conn.execute(sa.text("""CREATE TABLE brc_risk_cluster_membership_snapshots (
      cluster_membership_snapshot_id TEXT PRIMARY KEY, risk_policy_version TEXT,
      primary_risk_cluster_id TEXT, semantic_hash TEXT, status TEXT,
      created_at_ms BIGINT)"""))
    conn.execute(sa.text("""CREATE TABLE brc_risk_cluster_memberships (
      risk_cluster_membership_id TEXT PRIMARY KEY, risk_policy_version TEXT,
      exchange_instrument_id TEXT, risk_cluster_id TEXT,
      cluster_membership_snapshot_id TEXT, membership_role TEXT, status TEXT,
      created_at_ms BIGINT, created_by TEXT)"""))
    conn.execute(sa.text("""CREATE TABLE brc_budget_reservations (
      budget_reservation_id TEXT PRIMARY KEY, account_id TEXT, status TEXT, ticket_id TEXT,
      symbol TEXT, side TEXT, risk_at_stop NUMERIC, reserved_margin NUMERIC,
      account_risk_policy_version TEXT, risk_cluster_id TEXT)"""))
    conn.execute(sa.text("INSERT INTO brc_account_budget_current VALUES ('b','account-1','profile-1','p1','600','500','100','15','0',1,true,NULL,'snapshot-1',1752480060000,1)"))
    conn.execute(sa.text("INSERT INTO brc_account_risk_policy_current VALUES ('account-1','profile-1','p1','.025',2,'.06','.04','.90',10,1,true,'global_fail_closed','active','policy-event-1')"))
    return conn


def _candidate(
    conn: sa.Connection,
    *,
    instrument_id: str = "binance_usdm:SOLUSDT",
    cluster_id: str = "crypto_usd_beta",
    per_unit_stop_risk: Decimal = Decimal("3"),
) -> AccountCapacityCandidate:
    _seed_instrument_facts(conn, instrument_id, cluster_id)
    return AccountCapacityCandidate(
        account_id="account-1",
        runtime_profile_id="profile-1",
        instrument_facts=load_instrument_risk_facts(
            conn,
            exchange_instrument_id=instrument_id,
            risk_policy_version="p1",
            planned_notional=Decimal("100"),
            now_ms=1_752_480_000_000,
        ),
        per_unit_stop_risk=per_unit_stop_risk,
        entry_reference_price=Decimal("150"),
    )


def _seed_instrument_facts(
    conn: sa.Connection,
    instrument_id: str,
    cluster_id: str,
) -> None:
    suffix = instrument_id.replace(":", "-")
    rule_id = f"rule-{suffix}"
    source_id = f"source-{suffix}"
    if conn.execute(sa.text(
        "SELECT 1 FROM brc_exchange_instruments "
        "WHERE exchange_instrument_id = :instrument_id"
    ), {"instrument_id": instrument_id}).first() is None:
        conn.execute(sa.text("""INSERT INTO brc_exchange_instruments VALUES (
          :instrument_id, 'binance_usdm', :symbol, 'crypto', 'perpetual',
          'USDT', 'USDT', 'v1', 'active')"""), {
            "instrument_id": instrument_id,
            "symbol": instrument_id.split(":")[-1],
        })
        semantic_hash = instrument_rule_snapshot_v2_semantic_hash({
            "instrument_rule_snapshot_id": rule_id, "rule_schema_version": "v2",
            "price_tick": Decimal(".01"), "quantity_step": Decimal(".01"),
            "min_qty": Decimal(".01"), "min_notional": Decimal("5"),
            "contract_multiplier": Decimal("1"),
            "exchange_max_leverage_for_claim_notional": 20,
            "source_fact_snapshot_id": source_id, "valid_until_ms": 1752480060000,
            "risk_calculation_kind": "linear_quote_settled",
        })
        conn.execute(sa.text("""INSERT INTO brc_instrument_rule_snapshots VALUES (
          :rule_id, :instrument_id, 'v2', .01, .01, .01, 5, 1, 20,
          :source_id, 1752480060000, 'linear_quote_settled', :semantic_hash,
          'current', 1)"""), {
            "rule_id": rule_id,
            "instrument_id": instrument_id,
            "source_id": source_id,
            "semantic_hash": semantic_hash,
        })
    existing = conn.execute(sa.text("""
      SELECT snapshot.cluster_membership_snapshot_id
      FROM brc_risk_cluster_membership_snapshots AS snapshot
      JOIN brc_risk_cluster_memberships AS membership
        ON membership.cluster_membership_snapshot_id = snapshot.cluster_membership_snapshot_id
      WHERE membership.exchange_instrument_id = :instrument_id
        AND snapshot.status = 'current' AND membership.status = 'active'
      LIMIT 1
    """), {"instrument_id": instrument_id}).first()
    if existing is not None:
        return
    snapshot_id = f"membership-{suffix}-{cluster_id}"
    conn.execute(sa.text("""INSERT INTO brc_risk_cluster_membership_snapshots VALUES (
      :snapshot_id, 'p1', :cluster_id, :snapshot_id, 'current', 1)"""), {
        "snapshot_id": snapshot_id,
        "cluster_id": cluster_id,
    })
    conn.execute(sa.text("""INSERT INTO brc_risk_cluster_memberships VALUES (
      :member_id, 'p1', :instrument_id, :cluster_id, :snapshot_id,
      'primary', 'active', 1, 'owner')"""), {
        "member_id": f"member-{suffix}-{cluster_id}",
        "instrument_id": instrument_id,
        "cluster_id": cluster_id,
        "snapshot_id": snapshot_id,
    })
