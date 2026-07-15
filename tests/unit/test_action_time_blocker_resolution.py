from __future__ import annotations

from sqlalchemy import text

from src.application.action_time.blocker_resolution import (
    certify_action_time_blocker_resolution,
)
from src.application.runtime_process_outcome import (
    materialize_runtime_process_outcome,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_pg_promotion_action_time_lane_materialization import (
    pg_control_connection,
)


def _blocked_lane(conn):
    return materialize_runtime_process_outcome(
        conn,
        process_name="action_time_ticket_sequence_batch",
        scope_key="lane:SOR-001:ETHUSDT:long",
        run_id="run:blocked",
        result_status="action_time_ticket_sequence_blocked",
        blockers=["legacy_fixed_notional_prevented_dynamic_sizing"],
        started_at_ms=NOW_MS,
        completed_at_ms=NOW_MS + 1,
        runtime_head="old-head",
        source_watermark="signal:expired",
    )


def test_certified_non_market_repair_resolves_exact_lane_blocker(
    pg_control_connection,
):
    blocked = _blocked_lane(pg_control_connection)

    result = certify_action_time_blocker_resolution(
        pg_control_connection,
        process_outcome_id=str(blocked["process_outcome_id"]),
        expected_first_blocker="legacy_fixed_notional_prevented_dynamic_sizing",
        certification_ref="tests:dynamic-risk-sizing:passed",
        runtime_head="new-head",
        now_ms=NOW_MS + 2,
    )

    assert result["status"] == "blocker_resolution_certified"
    row = pg_control_connection.execute(
        text(
            "SELECT process_state, first_blocker, source_watermark "
            "FROM brc_runtime_process_outcomes "
            "WHERE process_outcome_id = :process_outcome_id"
        ),
        {"process_outcome_id": blocked["process_outcome_id"]},
    ).mappings().one()
    assert row["process_state"] == "succeeded"
    assert row["first_blocker"] is None
    assert row["source_watermark"] == (
        "certification:tests:dynamic-risk-sizing:passed"
    )


def test_resolution_fails_closed_when_expected_blocker_does_not_match(
    pg_control_connection,
):
    blocked = _blocked_lane(pg_control_connection)

    result = certify_action_time_blocker_resolution(
        pg_control_connection,
        process_outcome_id=str(blocked["process_outcome_id"]),
        expected_first_blocker="different_blocker",
        certification_ref="tests:wrong-repair",
        runtime_head="new-head",
        now_ms=NOW_MS + 2,
    )

    assert result["status"] == "blocked"
    assert result["blockers"] == ["process_outcome_first_blocker_mismatch"]
