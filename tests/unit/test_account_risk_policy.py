from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa

from src.application.action_time.account_risk_policy import (
    AccountRiskPolicy,
    append_account_risk_policy_event,
    load_account_risk_policy_current,
    load_account_risk_policy_current_projection,
    replace_risk_cluster_memberships,
)
from src.domain.account_risk import RiskClusterMembership


def _create_policy_tables(conn: sa.Connection) -> None:
    conn.execute(
        sa.text(
            """
            CREATE TABLE brc_account_risk_policy_events (
              account_risk_policy_event_id TEXT PRIMARY KEY,
              account_id TEXT NOT NULL,
              runtime_profile_id TEXT NOT NULL,
              event_type TEXT NOT NULL,
              risk_policy_version TEXT NOT NULL,
              payload JSON NOT NULL,
              created_at_ms BIGINT NOT NULL,
              created_by TEXT NOT NULL
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE TABLE brc_account_risk_policy_current (
              account_risk_policy_current_id TEXT PRIMARY KEY,
              account_id TEXT NOT NULL,
              runtime_profile_id TEXT NOT NULL,
              risk_policy_version TEXT NOT NULL,
              planned_stop_risk_fraction NUMERIC NOT NULL,
              max_concurrent_positions INTEGER NOT NULL,
              max_portfolio_open_risk_fraction NUMERIC NOT NULL,
              max_cluster_open_risk_fraction NUMERIC NOT NULL,
              max_portfolio_initial_margin_fraction NUMERIC NOT NULL,
              max_leverage INTEGER NOT NULL,
              max_new_action_time_lanes INTEGER NOT NULL,
              automatic_downsize_enabled BOOLEAN NOT NULL,
              unknown_exposure_policy TEXT NOT NULL,
              activation_state TEXT NOT NULL,
              source_event_id TEXT NOT NULL,
              updated_at_ms BIGINT NOT NULL
            )
            """
        )
    )


def _create_membership_tables(conn: sa.Connection) -> None:
    conn.execute(sa.text("""CREATE TABLE brc_risk_cluster_membership_snapshots (
      cluster_membership_snapshot_id TEXT PRIMARY KEY,
      risk_policy_version TEXT NOT NULL, primary_risk_cluster_id TEXT NOT NULL,
      semantic_hash TEXT NOT NULL, status TEXT NOT NULL, created_at_ms BIGINT NOT NULL
    )"""))
    conn.execute(sa.text("""CREATE TABLE brc_risk_cluster_memberships (
      risk_cluster_membership_id TEXT PRIMARY KEY,
      risk_policy_version TEXT NOT NULL, exchange_instrument_id TEXT NOT NULL,
      risk_cluster_id TEXT NOT NULL, cluster_membership_snapshot_id TEXT NOT NULL,
      membership_role TEXT NOT NULL, status TEXT NOT NULL,
      created_at_ms BIGINT NOT NULL, created_by TEXT NOT NULL
    )"""))


def test_membership_replacement_is_append_only_and_semantically_idempotent() -> None:
    conn = sa.create_engine("sqlite://").connect()
    _create_membership_tables(conn)
    first = (
        RiskClusterMembership(
            exchange_instrument_id="instrument-1",
            risk_cluster_id="crypto-beta",
            membership_role="primary",
        ),
        RiskClusterMembership(
            exchange_instrument_id="instrument-1",
            risk_cluster_id="high-volatility",
            membership_role="secondary",
        ),
    )

    replace_risk_cluster_memberships(
        conn,
        risk_policy_version="policy-v1",
        memberships=first,
        created_by="owner",
        now_ms=1,
    )
    replace_risk_cluster_memberships(
        conn,
        risk_policy_version="policy-v1",
        memberships=tuple(reversed(first)),
        created_by="owner",
        now_ms=2,
    )
    unchanged_counts = (
        conn.execute(sa.text("SELECT COUNT(*) FROM brc_risk_cluster_membership_snapshots")).scalar_one(),
        conn.execute(sa.text("SELECT COUNT(*) FROM brc_risk_cluster_memberships")).scalar_one(),
    )
    replace_risk_cluster_memberships(
        conn,
        risk_policy_version="policy-v1",
        memberships=(
            first[0].model_copy(update={"risk_cluster_id": "new-beta"}),
            first[1],
        ),
        created_by="owner",
        now_ms=3,
    )

    snapshot_states = conn.execute(sa.text(
        "SELECT status, COUNT(*) FROM brc_risk_cluster_membership_snapshots GROUP BY status"
    )).all()
    member_states = conn.execute(sa.text(
        "SELECT status, membership_role, risk_cluster_id "
        "FROM brc_risk_cluster_memberships ORDER BY created_at_ms, membership_role"
    )).all()

    assert unchanged_counts == (1, 2)
    assert dict(snapshot_states) == {"current": 1, "superseded": 1}
    assert member_states == [
        ("superseded", "primary", "crypto-beta"),
        ("superseded", "secondary", "high-volatility"),
        ("active", "primary", "new-beta"),
        ("active", "secondary", "high-volatility"),
    ]


def test_membership_replacement_requires_exactly_one_primary_per_instrument() -> None:
    conn = sa.create_engine("sqlite://").connect()
    _create_membership_tables(conn)
    secondary = RiskClusterMembership(
        exchange_instrument_id="instrument-1",
        risk_cluster_id="secondary-only",
        membership_role="secondary",
    )
    with pytest.raises(ValueError, match="exactly one primary"):
        replace_risk_cluster_memberships(
            conn,
            risk_policy_version="policy-v1",
            memberships=(secondary,),
            created_by="owner",
            now_ms=1,
        )
    with pytest.raises(ValueError, match="exactly one primary"):
        replace_risk_cluster_memberships(
            conn,
            risk_policy_version="policy-v1",
            memberships=(
                secondary.model_copy(update={
                    "risk_cluster_id": "primary-a", "membership_role": "primary"
                }),
                secondary.model_copy(update={
                    "risk_cluster_id": "primary-b", "membership_role": "primary"
                }),
            ),
            created_by="owner",
            now_ms=1,
        )


def test_membership_replacement_supersedes_instrument_removed_from_new_set() -> None:
    conn = sa.create_engine("sqlite://").connect()
    _create_membership_tables(conn)
    membership = RiskClusterMembership(
        exchange_instrument_id="instrument-1",
        risk_cluster_id="crypto-beta",
    )
    replace_risk_cluster_memberships(
        conn,
        risk_policy_version="policy-v1",
        memberships=(membership,),
        created_by="owner",
        now_ms=1,
    )

    replace_risk_cluster_memberships(
        conn,
        risk_policy_version="policy-v1",
        memberships=(),
        created_by="owner",
        now_ms=2,
    )

    assert conn.execute(sa.text(
        "SELECT status FROM brc_risk_cluster_membership_snapshots"
    )).scalar_one() == "superseded"
    assert conn.execute(sa.text(
        "SELECT status FROM brc_risk_cluster_memberships"
    )).scalar_one() == "superseded"


def test_append_policy_projects_account_scoped_owner_values_without_strategy_scope_mutation() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        _create_policy_tables(conn)
        policy = append_account_risk_policy_event(
            conn,
            account_id="binance-subaccount-1",
            runtime_profile_id="runtime-order-capable",
            event_type="activate_dual_position_v0",
            policy=AccountRiskPolicy(
                risk_policy_version="account-risk-v0-owner-20260714",
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
            ),
            created_by="owner_decision_20260714",
            now_ms=1_752_480_000_000,
        )

        loaded = load_account_risk_policy_current(
            conn,
            account_id="binance-subaccount-1",
            runtime_profile_id="runtime-order-capable",
        )

    assert policy.planned_stop_risk_fraction == Decimal("0.025")
    assert policy.max_concurrent_positions == 2
    assert loaded == policy


def test_distinct_owner_operations_append_immutable_events_and_replace_current_epoch() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        _create_policy_tables(conn)
        activate = AccountRiskPolicy(
            risk_policy_version="account-risk-v0-owner-20260714",
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
        rollback = activate.model_copy(update={"max_concurrent_positions": 1})
        append_account_risk_policy_event(
            conn,
            account_id="binance-subaccount-1",
            runtime_profile_id="runtime-order-capable",
            event_type="activate_dual_position_v0",
            policy=activate,
            created_by="owner",
            operation_id="owner-operation-activate",
            now_ms=1_752_480_000_000,
        )
        first = load_account_risk_policy_current_projection(
            conn,
            account_id="binance-subaccount-1",
            runtime_profile_id="runtime-order-capable",
        )
        append_account_risk_policy_event(
            conn,
            account_id="binance-subaccount-1",
            runtime_profile_id="runtime-order-capable",
            event_type="rollback_single_position",
            policy=rollback,
            created_by="owner",
            operation_id="owner-operation-rollback",
            now_ms=1_752_480_001_000,
        )
        second = load_account_risk_policy_current_projection(
            conn,
            account_id="binance-subaccount-1",
            runtime_profile_id="runtime-order-capable",
        )

        event_count = conn.execute(
            sa.text("SELECT COUNT(*) FROM brc_account_risk_policy_events")
        ).scalar_one()

    assert first is not None
    assert second is not None
    assert first.source_event_id != second.source_event_id
    assert second.policy.max_concurrent_positions == 1
    assert event_count == 2
