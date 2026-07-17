from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa

from src.application.action_time.instrument_risk_facts import (
    InstrumentRiskFactsError,
    load_instrument_risk_facts,
)


NOW_MS = 1_752_480_000_000


def _connection() -> sa.Connection:
    conn = sa.create_engine("sqlite://").connect()
    conn.execute(sa.text("""CREATE TABLE brc_exchange_instruments (
      exchange_instrument_id TEXT PRIMARY KEY, exchange_id TEXT, exchange_symbol TEXT,
      asset_class TEXT, instrument_type TEXT, settlement_asset TEXT, margin_asset TEXT,
      instrument_identity_schema_version TEXT, status TEXT)"""))
    conn.execute(sa.text("""CREATE TABLE brc_instrument_rule_snapshots (
      instrument_rule_snapshot_id TEXT PRIMARY KEY, exchange_instrument_id TEXT,
      rule_schema_version TEXT, price_tick NUMERIC, quantity_step NUMERIC,
      min_qty NUMERIC, min_notional NUMERIC, contract_multiplier NUMERIC,
      exchange_max_leverage_for_claim_notional INTEGER, source_fact_snapshot_id TEXT,
      valid_until_ms BIGINT, semantic_hash TEXT, status TEXT, created_at_ms BIGINT)"""))
    conn.execute(sa.text("""CREATE TABLE brc_risk_cluster_membership_snapshots (
      cluster_membership_snapshot_id TEXT PRIMARY KEY, risk_policy_version TEXT,
      primary_risk_cluster_id TEXT, semantic_hash TEXT, status TEXT,
      created_at_ms BIGINT)"""))
    conn.execute(sa.text("""CREATE TABLE brc_risk_cluster_memberships (
      risk_cluster_membership_id TEXT PRIMARY KEY, risk_policy_version TEXT,
      exchange_instrument_id TEXT, risk_cluster_id TEXT,
      cluster_membership_snapshot_id TEXT, membership_role TEXT, status TEXT,
      created_at_ms BIGINT, created_by TEXT)"""))
    conn.execute(sa.text("""INSERT INTO brc_exchange_instruments VALUES (
      'instrument-1', 'venue-1', 'SOL-PERP', 'crypto', 'perpetual', 'USDT', 'USDT',
      'v1', 'active')"""))
    return conn


def _rule(conn: sa.Connection, rule_id: str = "rule-1", *, valid_until_ms: int = NOW_MS + 1) -> None:
    conn.execute(sa.text("""INSERT INTO brc_instrument_rule_snapshots VALUES (
      :rule_id, 'instrument-1', 'v1', 0.01, 0.001, 0.001, 5, 1, 20,
      'source-fact-1', :valid_until_ms, :rule_id, 'current', 1)"""), {
        "rule_id": rule_id,
        "valid_until_ms": valid_until_ms,
    })


def _cluster(
    conn: sa.Connection,
    snapshot_id: str = "membership-1",
    *,
    role: str = "primary",
    cluster_id: str = "crypto-beta",
) -> None:
    conn.execute(sa.text("""INSERT INTO brc_risk_cluster_membership_snapshots VALUES (
      :snapshot_id, 'policy-v1', :cluster_id, :snapshot_id, 'current', 1)"""), {
        "snapshot_id": snapshot_id,
        "cluster_id": cluster_id,
    })
    conn.execute(sa.text("""INSERT INTO brc_risk_cluster_memberships VALUES (
      :member_id, 'policy-v1', 'instrument-1', :cluster_id, :snapshot_id,
      :role, 'active', 1, 'owner')"""), {
        "member_id": f"member:{snapshot_id}:{role}:{cluster_id}",
        "snapshot_id": snapshot_id,
        "cluster_id": cluster_id,
        "role": role,
    })


def _load(conn: sa.Connection):
    return load_instrument_risk_facts(
        conn,
        exchange_instrument_id="instrument-1",
        risk_policy_version="policy-v1",
        planned_notional=Decimal("100"),
        now_ms=NOW_MS,
    )


def test_loader_requires_one_current_rule_snapshot() -> None:
    conn = _connection()
    _cluster(conn)
    with pytest.raises(InstrumentRiskFactsError, match="instrument_rule_snapshot_invalid"):
        _load(conn)
    _rule(conn, "rule-1")
    _rule(conn, "rule-2")
    with pytest.raises(InstrumentRiskFactsError, match="instrument_rule_snapshot_invalid"):
        _load(conn)


def test_loader_rejects_expired_rule_snapshot() -> None:
    conn = _connection()
    _rule(conn, valid_until_ms=NOW_MS)
    _cluster(conn)
    with pytest.raises(InstrumentRiskFactsError, match="instrument_rule_snapshot_stale"):
        _load(conn)


def test_membership_requires_exactly_one_primary() -> None:
    conn = _connection()
    _rule(conn)
    _cluster(conn, role="secondary")
    with pytest.raises(InstrumentRiskFactsError, match="primary_risk_cluster_membership_invalid"):
        _load(conn)

    conn = _connection()
    _rule(conn)
    _cluster(conn)
    conn.execute(sa.text("""INSERT INTO brc_risk_cluster_memberships VALUES (
      'member-second-primary', 'policy-v1', 'instrument-1', 'alt-beta',
      'membership-1', 'primary', 'active', 2, 'owner')"""))
    with pytest.raises(InstrumentRiskFactsError, match="primary_risk_cluster_membership_invalid"):
        _load(conn)


def test_secondary_membership_does_not_replace_primary() -> None:
    conn = _connection()
    _rule(conn)
    _cluster(conn)
    conn.execute(sa.text("""INSERT INTO brc_risk_cluster_memberships VALUES (
      'member-secondary', 'policy-v1', 'instrument-1', 'secondary-cluster',
      'membership-1', 'secondary', 'active', 1, 'owner')"""))

    facts = _load(conn)

    assert facts.identity.exchange_instrument_id == "instrument-1"
    assert facts.rule_snapshot.quantity_step == Decimal("0.001")
    assert facts.cluster_snapshot.primary_risk_cluster_id == "crypto-beta"


def test_loader_ignores_large_rule_and_membership_history() -> None:
    conn = _connection()
    _rule(conn)
    _cluster(conn)
    conn.execute(sa.text("""
      WITH RECURSIVE history(n) AS (
        SELECT 1 UNION ALL SELECT n + 1 FROM history WHERE n < 100000
      )
      INSERT INTO brc_instrument_rule_snapshots
      SELECT 'old-rule-' || n, 'instrument-1', 'v1', 0.01, 0.001, 0.001, 5,
             1, 20, 'old-source-' || n, :now_ms, 'old-' || n, 'superseded', n
      FROM history
    """), {"now_ms": NOW_MS})

    facts = _load(conn)

    assert facts.rule_snapshot.instrument_rule_snapshot_id == "rule-1"
