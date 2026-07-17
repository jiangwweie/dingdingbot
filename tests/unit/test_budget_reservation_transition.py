from __future__ import annotations

import pytest
import sqlalchemy as sa

from src.application.action_time.budget_reservation_transition import (
    transition_budget_reservation,
)


def _connection(status: str) -> sa.Connection:
    engine = sa.create_engine("sqlite://")
    conn = engine.connect()
    conn.execute(
        sa.text(
            """
            CREATE TABLE brc_budget_reservations (
              budget_reservation_id TEXT PRIMARY KEY,
              status TEXT NOT NULL,
              release_reason TEXT,
              ticket_id TEXT
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE TABLE brc_budget_reservation_events (
              budget_reservation_event_id TEXT PRIMARY KEY,
              budget_reservation_id TEXT NOT NULL,
              from_status TEXT,
              to_status TEXT NOT NULL,
              reason TEXT NOT NULL,
              evidence_ref TEXT NOT NULL,
              created_at_ms BIGINT NOT NULL
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_budget_reservations (
              budget_reservation_id, status, ticket_id
            ) VALUES ('budget-1', :status, 'ticket-1')
            """
        ),
        {"status": status},
    )
    return conn


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("active", "consumed"),
        ("active", "expired"),
        ("active", "invalidated"),
        ("consumed", "released"),
    ],
)
def test_allowed_reservation_transitions_append_a_single_audit_event(
    before: str,
    after: str,
) -> None:
    conn = _connection(before)

    result = transition_budget_reservation(
        conn,
        budget_reservation_id="budget-1",
        to_status=after,
        reason="unit_test",
        evidence_ref="evidence-1",
        now_ms=1_752_480_000_000,
    )

    assert result.status == after
    assert result.transitioned is True
    assert conn.execute(
        sa.text("SELECT status FROM brc_budget_reservations WHERE budget_reservation_id = 'budget-1'")
    ).scalar_one() == after
    assert conn.execute(sa.text("SELECT COUNT(*) FROM brc_budget_reservation_events")).scalar_one() == 1
    conn.close()


@pytest.mark.parametrize(
    ("before", "after"),
    [("released", "consumed"), ("expired", "active"), ("consumed", "active")],
)
def test_invalid_reservation_transition_does_not_mutate_current_row(
    before: str,
    after: str,
) -> None:
    conn = _connection(before)

    result = transition_budget_reservation(
        conn,
        budget_reservation_id="budget-1",
        to_status=after,
        reason="unit_test",
        evidence_ref="evidence-1",
        now_ms=1_752_480_000_000,
    )

    assert result.status == before
    assert result.first_blocker == "budget_reservation_transition_invalid"
    assert result.transitioned is False
    assert conn.execute(
        sa.text("SELECT status FROM brc_budget_reservations WHERE budget_reservation_id = 'budget-1'")
    ).scalar_one() == before
    assert conn.execute(sa.text("SELECT COUNT(*) FROM brc_budget_reservation_events")).scalar_one() == 0
    conn.close()
