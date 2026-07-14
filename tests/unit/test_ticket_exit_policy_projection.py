from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from src.application.action_time.ticket_exit_policy_projection import (
    claim_ticket_exit_market_watermark,
    record_ticket_exit_market_blocker,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


def _insert_projection(conn, *, ticket_id: str = "ticket-projection-1") -> None:
    conn.execute(
        text(
            "INSERT INTO brc_ticket_exit_policy_current ("
            "ticket_id, exit_policy_id, exit_policy_version, exit_policy_hash, "
            "tp1_cumulative_filled_qty, tp1_completion_state, state, updated_at_ms"
            ") VALUES ("
            ":ticket_id, 'policy-1', '1.0.0', 'hash-1', 0, 'unfilled', "
            "'execution_bound', :now_ms)"
        ),
        {"ticket_id": ticket_id, "now_ms": NOW_MS},
    )


def test_projection_claim_is_compare_and_set_and_watermark_monotonic(
    pg_control_connection,
):
    _insert_projection(pg_control_connection)

    first = claim_ticket_exit_market_watermark(
        pg_control_connection,
        ticket_id="ticket-projection-1",
        expected_previous_watermark_ms=None,
        watermark_ms=NOW_MS + 900_000,
        next_evaluation_not_before_ms=NOW_MS + 1_800_000,
        fact_snapshot_id="fact-1",
        now_ms=NOW_MS + 1,
    )
    duplicate = claim_ticket_exit_market_watermark(
        pg_control_connection,
        ticket_id="ticket-projection-1",
        expected_previous_watermark_ms=None,
        watermark_ms=NOW_MS + 900_000,
        next_evaluation_not_before_ms=NOW_MS + 1_800_000,
        fact_snapshot_id="fact-1",
        now_ms=NOW_MS + 2,
    )

    assert first["status"] == "watermark_claimed"
    assert duplicate["status"] == "watermark_already_claimed"
    row = pg_control_connection.execute(
        text(
            "SELECT last_evaluated_watermark_ms, next_evaluation_not_before_ms, "
            "last_reason_code FROM brc_ticket_exit_policy_current "
            "WHERE ticket_id = 'ticket-projection-1'"
        )
    ).mappings().one()
    assert row["last_evaluated_watermark_ms"] == NOW_MS + 900_000
    assert row["next_evaluation_not_before_ms"] == NOW_MS + 1_800_000
    assert row["last_reason_code"] == "fact-1"


def test_projection_blocker_preserves_existing_runner_and_watermark(
    pg_control_connection,
):
    _insert_projection(pg_control_connection)
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_exit_policy_current SET "
            "last_evaluated_watermark_ms = :watermark, "
            "active_runner_stop = 101, active_runner_generation = 3 "
            "WHERE ticket_id = 'ticket-projection-1'"
        ),
        {"watermark": NOW_MS},
    )

    result = record_ticket_exit_market_blocker(
        pg_control_connection,
        ticket_id="ticket-projection-1",
        blocker="exit_market_fact_stale",
        retry_not_before_ms=NOW_MS + 30_000,
        now_ms=NOW_MS + 1,
    )

    assert result["status"] == "exit_market_fact_blocked"
    row = pg_control_connection.execute(
        text(
            "SELECT first_blocker, last_evaluated_watermark_ms, "
            "active_runner_stop, active_runner_generation "
            "FROM brc_ticket_exit_policy_current "
            "WHERE ticket_id = 'ticket-projection-1'"
        )
    ).mappings().one()
    assert row["first_blocker"] == "exit_market_fact_stale"
    assert row["last_evaluated_watermark_ms"] == NOW_MS
    assert Decimal(str(row["active_runner_stop"])) == Decimal("101")
    assert row["active_runner_generation"] == 3
