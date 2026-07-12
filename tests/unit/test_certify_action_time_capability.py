from __future__ import annotations

from sqlalchemy import text

from src.application.action_time.capability_certification import (
    certify_action_time_capabilities,
)
from src.infrastructure.runtime_control_state_repository import (
    PgBackedRuntimeControlStateRepository,
)
from tests.unit.test_action_time_full_chain_impact import pg_control_connection


RUNTIME_HEAD = "c" * 40


def _count(conn, table: str) -> int:
    return int(conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())


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
