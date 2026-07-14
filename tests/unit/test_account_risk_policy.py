from __future__ import annotations

from decimal import Decimal

import sqlalchemy as sa

from src.application.action_time.account_risk_policy import (
    AccountRiskPolicy,
    append_account_risk_policy_event,
    load_account_risk_policy_current,
    load_account_risk_policy_current_projection,
)


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
