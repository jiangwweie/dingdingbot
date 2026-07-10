from __future__ import annotations

from sqlalchemy import text

from src.application.strategy_semantic_admission import (
    materialize_active_strategy_semantic_admissions,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_pg_promotion_action_time_lane_materialization import (
    pg_control_connection,
)


def test_all_active_candidate_scopes_receive_machine_semantic_conclusion(
    pg_control_connection,
):
    payload = materialize_active_strategy_semantic_admissions(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    active_count = pg_control_connection.execute(
        text(
            "SELECT COUNT(*) FROM brc_strategy_group_candidate_scope "
            "WHERE status = 'active'"
        )
    ).scalar_one()
    rows = list(
        pg_control_connection.execute(
            text("SELECT * FROM brc_strategy_semantic_admissions")
        ).mappings()
    )
    assert payload["evaluated_count"] == active_count
    assert len(rows) == active_count
    conclusions_by_group = {
        strategy_group_id: {
            row["conclusion"]
            for row in rows
            if row["strategy_group_id"] == strategy_group_id
        }
        for strategy_group_id in {row["strategy_group_id"] for row in rows}
    }
    certified_groups = {"CPM-RO-001", "MPG-001", "MI-001"}
    assert all(
        conclusions_by_group[group_id] == {"trial_grade_capable"}
        for group_id in certified_groups
    )
    assert {
        conclusion
        for strategy_group_id, conclusions in conclusions_by_group.items()
        if strategy_group_id not in certified_groups
        for conclusion in conclusions
    } == {"observe_only_by_design"}
    assert sum(row["conclusion"] == "trial_grade_capable" for row in rows) == 11
    assert sum(row["conclusion"] == "observe_only_by_design" for row in rows) == 11
    assert all(row["exchange_instrument_id"] for row in rows)
    assert all(row["event_spec_version_id"] for row in rows)


def test_explicit_trial_event_becomes_trial_capable_without_submit_authority(
    pg_control_connection,
):
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_strategy_side_event_specs
            SET declared_signal_grade = 'trial_grade_signal',
                declared_required_execution_mode = 'trial_live',
                execution_eligibility_enabled = true
            WHERE event_spec_id = 'event_spec:SOR-001:SOR-LONG:v1'
            """
        )
    )

    payload = materialize_active_strategy_semantic_admissions(
        pg_control_connection,
        now_ms=NOW_MS,
    )
    conclusions = {
        row["conclusion"]
        for row in pg_control_connection.execute(
            text(
                "SELECT conclusion FROM brc_strategy_semantic_admissions "
                "WHERE event_spec_id = 'event_spec:SOR-001:SOR-LONG:v1'"
            )
        ).mappings()
    }

    assert conclusions == {"trial_grade_capable"}
    assert payload["grants_submit_authority"] is False
