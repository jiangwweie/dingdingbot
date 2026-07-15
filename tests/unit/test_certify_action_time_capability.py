from __future__ import annotations

import sqlalchemy as sa
import pytest
from sqlalchemy import text

from src.application.action_time.capability_certification import (
    certify_action_time_capabilities,
    record_runtime_release_activation,
)
from src.infrastructure.runtime_control_state_repository import (
    PgBackedRuntimeControlStateRepository,
    RuntimeControlStateRepositoryError,
)
from tests.unit.test_action_time_full_chain_impact import pg_control_connection


RUNTIME_HEAD = "c" * 40


def _attach_strategy_runtime_instances(state: dict[str, object]) -> None:
    bindings = {
        candidate["candidate_scope_id"]: binding
        for candidate in state["candidate_scope"]
        if candidate["status"] == "active"
        for binding in state["candidate_scope_event_bindings"]
        if binding["candidate_scope_id"] == candidate["candidate_scope_id"]
        and binding["status"] == "active"
    }
    events = {
        row["event_spec_id"]: row
        for row in state["strategy_side_event_specs"]
        if row["status"] == "current"
    }
    state["strategy_runtime_instances"] = [
        {
            "runtime_instance_id": "runtime:" + candidate["candidate_scope_id"],
            "strategy_family_id": candidate["strategy_group_id"],
            "strategy_family_version_id": events[
                bindings[candidate["candidate_scope_id"]]["event_spec_id"]
            ]["strategy_group_version_id"],
            "symbol": candidate["symbol"],
            "side": candidate["side"],
            "status": "active",
        }
        for candidate in state["candidate_scope"]
        if candidate["status"] == "active"
    ]


def test_deploy_projector_records_one_current_release_activation_without_trade_effects(
    pg_control_connection,
) -> None:
    before = {
        table: _count(pg_control_connection, table)
        for table in (
            "brc_live_signal_events",
            "brc_action_time_tickets",
            "brc_ticket_bound_exchange_commands",
        )
    }

    result = record_runtime_release_activation(
        pg_control_connection,
        runtime_head=RUNTIME_HEAD,
        release_name="brc-runtime-governance-test",
        verification_ref="postdeploy:passed",
        now_ms=1_800_000_000_050,
    )

    assert result["status"] == "runtime_release_activation_completed"
    assert result["runtime_head"] == RUNTIME_HEAD
    assert result["exchange_write_called"] is False
    row = pg_control_connection.execute(
        text(
            "SELECT process_name, scope_key, process_state, runtime_head, "
            "projector_owner FROM brc_runtime_process_outcomes"
        )
    ).mappings().one()
    assert dict(row) == {
        "process_name": "runtime_release_activation",
        "scope_key": "production:tokyo",
        "process_state": "succeeded",
        "runtime_head": RUNTIME_HEAD,
        "projector_owner": "runtime_process_outcome_projector",
    }
    assert before == {
        table: _count(pg_control_connection, table) for table in before
    }


def _count(conn, table: str) -> int:
    return int(conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())


def _seed_strategy_runtime_instances(conn) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE strategy_runtime_instances (
              runtime_instance_id TEXT PRIMARY KEY,
              strategy_family_id TEXT NOT NULL,
              strategy_family_version_id TEXT NOT NULL,
              symbol TEXT NOT NULL,
              side TEXT NOT NULL,
              status TEXT NOT NULL
            )
            """
        )
    )
    candidates = conn.execute(
        text(
            """
            SELECT c.candidate_scope_id, c.strategy_group_id, c.symbol, c.side,
                   e.strategy_group_version_id
            FROM brc_strategy_group_candidate_scope AS c
            JOIN brc_candidate_scope_event_bindings AS b
              ON b.candidate_scope_id = c.candidate_scope_id
             AND b.status = 'active'
            JOIN brc_strategy_side_event_specs AS e
              ON e.event_spec_id = b.event_spec_id
             AND e.status = 'current'
            WHERE c.status = 'active'
            ORDER BY c.candidate_scope_id
            """
        )
    ).mappings()
    for row in candidates:
        conn.execute(
            text(
                """
                INSERT INTO strategy_runtime_instances (
                  runtime_instance_id, strategy_family_id,
                  strategy_family_version_id, symbol, side, status
                ) VALUES (
                  :runtime_instance_id, :strategy_family_id,
                  :strategy_family_version_id, :symbol, :side, 'active'
                )
                """
            ),
            {
                "runtime_instance_id": "runtime:" + row["candidate_scope_id"],
                "strategy_family_id": row["strategy_group_id"],
                "strategy_family_version_id": row["strategy_group_version_id"],
                "symbol": row["symbol"],
                "side": row["side"],
            },
        )
    conn.commit()


def test_capability_certification_state_uses_identity_driven_bounded_profile(
    pg_control_connection,
) -> None:
    _seed_strategy_runtime_instances(pg_control_connection)
    record_runtime_release_activation(
        pg_control_connection,
        runtime_head=RUNTIME_HEAD,
        release_name="bounded-profile-test",
        verification_ref="postdeploy:bounded-profile",
        now_ms=1_800_000_000_050,
    )
    pg_control_connection.commit()
    statements: list[str] = []

    def capture_sql(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(" ".join(statement.split()))

    sa.event.listen(
        pg_control_connection.engine,
        "before_cursor_execute",
        capture_sql,
    )
    try:
        state = PgBackedRuntimeControlStateRepository(
            pg_control_connection,
            now_ms=1_800_000_000_100,
        ).read_action_time_capability_certification_state()
    finally:
        sa.event.remove(
            pg_control_connection.engine,
            "before_cursor_execute",
            capture_sql,
        )

    assert state["read_profile"] == "action_time_capability_certification"
    assert state["current_runtime_head"] == RUNTIME_HEAD
    assert len(state["candidate_scope"]) == 22
    assert len(state["strategy_runtime_instances"]) == 22
    assert len(state["runtime_process_outcomes"]) == 1
    row_queries = [
        statement
        for statement in statements
        if statement.startswith("SELECT ")
        and (" FROM brc_" in statement or " FROM strategy_runtime_instances" in statement)
    ]
    assert len(row_queries) == 10
    assert all(" WHERE " in statement for statement in row_queries)
    assert all(" LIMIT " in statement for statement in row_queries)
    assert all(".*" not in statement for statement in row_queries)


def test_action_time_fact_digest_reader_requires_exact_bounded_id_set(
    pg_control_connection,
) -> None:
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_runtime_fact_snapshots (
              fact_snapshot_id, strategy_group_id, symbol, side,
              runtime_profile_id, fact_surface, source_kind, source_ref,
              computed, satisfied, freshness_state, failed_facts, fact_values,
              blocker_class, observed_at_ms, valid_until_ms, created_at_ms
            ) VALUES (
              'fact:digest:one', 'SOR-001', 'ETHUSDT', 'long',
              'owner-runtime-console-v1', 'action_time_private', 'live_account',
              'pytest:fact-digest', 1, 1, 'fresh', '[]',
              '{"mark_price":"1888.50"}', NULL,
              1800000000000, 1800000060000, 1800000000000
            )
            """
        )
    )
    pg_control_connection.commit()

    rows = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1_800_000_000_100,
    ).read_action_time_fact_digest_rows(
        expected_fact_snapshot_ids=("fact:digest:one",),
    )

    assert len(rows) == 1
    assert rows[0].fact_snapshot_id == "fact:digest:one"
    assert rows[0].fact_values == {"mark_price": "1888.50"}

    with pytest.raises(
        RuntimeControlStateRepositoryError,
        match="action_time_fact_digest_id_set_mismatch",
    ):
        PgBackedRuntimeControlStateRepository(
            pg_control_connection,
            now_ms=1_800_000_000_100,
        ).read_action_time_fact_digest_rows(
            expected_fact_snapshot_ids=("fact:digest:missing",),
        )


def test_certification_upserts_22_bounded_rows_without_trading_authority(
    pg_control_connection,
) -> None:
    before = {
        table: _count(pg_control_connection, table)
        for table in (
            "brc_live_signal_events",
            "brc_promotion_candidates",
            "brc_action_time_lane_inputs",
            "brc_action_time_tickets",
            "brc_runtime_safety_state_snapshots",
            "brc_ticket_bound_exchange_commands",
        )
    }
    state = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1_800_000_000_000,
    ).read_control_state()
    _attach_strategy_runtime_instances(state)
    state["current_runtime_head"] = RUNTIME_HEAD

    result = certify_action_time_capabilities(
        pg_control_connection,
        control_state=state,
        runtime_head=RUNTIME_HEAD,
        certification_ref="pytest:22-scope-disabled-smoke",
        expected_lane_count=22,
        now_ms=1_800_000_000_100,
    )

    assert result["status"] == "action_time_capability_certified"
    assert result["certified_lane_count"] == 22
    assert result["first_blocker"] is None
    assert result["exchange_write_called"] is False
    assert result["signal_created"] is False
    assert result["ticket_created"] is False
    assert result["runtime_authority_created"] is False
    rows = pg_control_connection.execute(
        text(
            "SELECT process_name, process_state, runtime_head, source_watermark, "
            "projector_owner FROM brc_runtime_process_outcomes "
            "WHERE process_name = 'action_time_capability_certification'"
        )
    ).mappings().all()
    assert len(rows) == 22
    assert {row["process_state"] for row in rows} == {"succeeded"}
    assert {row["runtime_head"] for row in rows} == {RUNTIME_HEAD}
    assert all(str(row["source_watermark"]).startswith("action_time_capability:") for row in rows)
    assert {row["projector_owner"] for row in rows} == {
        "runtime_process_outcome_projector"
    }
    assert before == {table: _count(pg_control_connection, table) for table in before}

    second_state = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1_800_000_000_200,
    ).read_control_state()
    _attach_strategy_runtime_instances(second_state)
    second_state["current_runtime_head"] = RUNTIME_HEAD
    second = certify_action_time_capabilities(
        pg_control_connection,
        control_state=second_state,
        runtime_head=RUNTIME_HEAD,
        certification_ref="pytest:22-scope-disabled-smoke:rerun",
        expected_lane_count=22,
        now_ms=1_800_000_000_200,
    )
    assert second["certified_lane_count"] == 22
    assert _count(pg_control_connection, "brc_runtime_process_outcomes") == 22


def test_certification_fails_before_write_when_runtime_head_is_missing(
    pg_control_connection,
) -> None:
    state = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1_800_000_000_000,
    ).read_control_state()
    _attach_strategy_runtime_instances(state)
    state["current_runtime_head"] = RUNTIME_HEAD

    result = certify_action_time_capabilities(
        pg_control_connection,
        control_state=state,
        runtime_head="",
        certification_ref="pytest:invalid",
        expected_lane_count=22,
        now_ms=1_800_000_000_100,
    )

    assert result["status"] == "blocked"
    assert result["first_blocker"] == "runtime_head_required"
    assert _count(pg_control_connection, "brc_runtime_process_outcomes") == 0


def test_certification_fails_atomically_when_one_lane_identity_is_incomplete(
    pg_control_connection,
) -> None:
    state = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1_800_000_000_000,
    ).read_control_state()
    _attach_strategy_runtime_instances(state)
    state["current_runtime_head"] = RUNTIME_HEAD
    state["runtime_scope_bindings"] = state["runtime_scope_bindings"][:-1]

    result = certify_action_time_capabilities(
        pg_control_connection,
        control_state=state,
        runtime_head=RUNTIME_HEAD,
        certification_ref="pytest:incomplete",
        expected_lane_count=22,
        now_ms=1_800_000_000_100,
    )

    assert result["status"] == "blocked"
    assert "runtime_scope_binding_missing" in result["first_blocker"]
    assert _count(pg_control_connection, "brc_runtime_process_outcomes") == 0


def test_certification_rejects_runtime_head_or_lane_count_mismatch_before_write(
    pg_control_connection,
) -> None:
    state = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1_800_000_000_000,
    ).read_control_state()
    _attach_strategy_runtime_instances(state)
    state["current_runtime_head"] = "observed-head"

    head_mismatch = certify_action_time_capabilities(
        pg_control_connection,
        control_state=state,
        runtime_head=RUNTIME_HEAD,
        certification_ref="pytest:wrong-head",
        expected_lane_count=22,
        now_ms=1_800_000_000_100,
    )
    count_mismatch = certify_action_time_capabilities(
        pg_control_connection,
        control_state={**state, "current_runtime_head": RUNTIME_HEAD},
        runtime_head=RUNTIME_HEAD,
        certification_ref="pytest:wrong-count",
        expected_lane_count=23,
        now_ms=1_800_000_000_100,
    )

    assert head_mismatch["first_blocker"] == "runtime_head_mismatch"
    assert count_mismatch["first_blocker"] == "certified_lane_count_mismatch"
    assert _count(pg_control_connection, "brc_runtime_process_outcomes") == 0
