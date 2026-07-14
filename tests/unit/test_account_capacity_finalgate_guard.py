from __future__ import annotations

import sqlalchemy as sa

from src.application.action_time import finalgate_preflight as subject
from src.application.action_time import runtime_safety_state


NOW_MS = 1_752_480_000_000


def test_active_capacity_claim_requires_the_same_fresh_budget_projection() -> None:
    conn = _connection()
    blockers, active = subject.account_capacity_current_blockers(
        conn,
        budget={
            "account_id": "account-1",
            "runtime_profile_id": "profile-1",
            "account_risk_policy_version": "policy-1",
            "account_risk_policy_event_id": "policy-event-activate",
            "account_capacity_projection_version": 2,
        },
        now_ms=NOW_MS,
    )

    assert active is True
    assert blockers == []

    conn.execute(
        sa.text(
            "UPDATE brc_account_budget_current SET projection_version = 3"
        )
    )
    blockers, active = subject.account_capacity_current_blockers(
        conn,
        budget={
            "account_id": "account-1",
            "runtime_profile_id": "profile-1",
            "account_risk_policy_version": "policy-1",
            "account_risk_policy_event_id": "policy-event-activate",
            "account_capacity_projection_version": 2,
        },
        now_ms=NOW_MS,
    )

    assert active is True
    assert blockers == ["account_budget_projection_version_changed"]


def test_active_capacity_claim_is_invalidated_when_owner_policy_event_changes() -> None:
    conn = _connection()
    budget = {
        "account_id": "account-1",
        "runtime_profile_id": "profile-1",
        "account_risk_policy_version": "policy-1",
        "account_risk_policy_event_id": "policy-event-activate",
        "account_capacity_projection_version": 2,
    }

    blockers, active = subject.account_capacity_current_blockers(
        conn,
        budget=budget,
        now_ms=NOW_MS,
    )

    assert active is True
    assert blockers == []

    conn.execute(
        sa.text(
            "UPDATE brc_account_risk_policy_current "
            "SET source_event_id = 'policy-event-rollback'"
        )
    )
    blockers, active = subject.account_capacity_current_blockers(
        conn,
        budget=budget,
        now_ms=NOW_MS,
    )

    assert active is True
    assert blockers == ["account_risk_policy_event_changed"]


def test_legacy_budget_reservation_does_not_opt_into_capacity_gate() -> None:
    blockers, active = subject.account_capacity_current_blockers(
        _connection(),
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


def _connection() -> sa.Connection:
    engine = sa.create_engine("sqlite://")
    conn = engine.connect()
    conn.execute(
        sa.text(
            """CREATE TABLE brc_account_risk_policy_current (
                account_id TEXT, runtime_profile_id TEXT, risk_policy_version TEXT,
                activation_state TEXT, source_event_id TEXT
            )"""
        )
    )
    conn.execute(
        sa.text(
            """CREATE TABLE brc_account_budget_current (
                account_id TEXT, runtime_profile_id TEXT, risk_policy_version TEXT,
                valid_until_ms BIGINT, projection_version BIGINT,
                new_entry_allowed BOOLEAN, first_blocker TEXT
            )"""
        )
    )
    conn.execute(
        sa.text(
            """INSERT INTO brc_account_risk_policy_current VALUES
            ('account-1', 'profile-1', 'policy-1', 'active', 'policy-event-activate')"""
        )
    )
    conn.execute(
        sa.text(
            """INSERT INTO brc_account_budget_current VALUES
            ('account-1', 'profile-1', 'policy-1', 1752480060000, 2, true, NULL)"""
        )
    )
    return conn
