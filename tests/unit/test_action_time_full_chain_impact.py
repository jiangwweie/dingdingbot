from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from scripts import materialize_action_time_fact_snapshots as fact_materializer
from scripts import materialize_action_time_finalgate_preflight as finalgate
from scripts import materialize_action_time_operation_layer_handoff as handoff
from scripts import materialize_action_time_ticket as ticket_materializer
from scripts import materialize_pg_promotion_action_time_lane as lane_materializer
from scripts import materialize_ticket_bound_protected_submit_attempt as protected_submit
from scripts import materialize_ticket_bound_runtime_safety_state as safety_state
from scripts import publish_runtime_control_current_projections as publisher
from scripts import runtime_active_observation_monitor
from tests.unit.test_pg_promotion_action_time_lane_materialization import (
    NOW_MS,
    _insert_ready_fresh_signal,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py"
)
SEED_PATH = REPO_ROOT / "scripts/seed_runtime_control_state_foundation.py"

ACTIVE_CANDIDATE_SCOPES = [
    ("BRF2-001", "BTCUSDT", "short"),
    ("BRF2-001", "AVAXUSDT", "short"),
    ("BRF2-001", "ETHUSDT", "short"),
    ("CPM-RO-001", "ETHUSDT", "long"),
    ("CPM-RO-001", "SOLUSDT", "long"),
    ("CPM-RO-001", "AVAXUSDT", "long"),
    ("CPM-RO-001", "SUIUSDT", "long"),
    ("MI-001", "AVAXUSDT", "long"),
    ("MI-001", "ETHUSDT", "long"),
    ("MI-001", "SOLUSDT", "long"),
    ("MPG-001", "OPUSDT", "long"),
    ("MPG-001", "SOLUSDT", "long"),
    ("MPG-001", "AVAXUSDT", "long"),
    ("MPG-001", "SUIUSDT", "long"),
    ("SOR-001", "ETHUSDT", "long"),
    ("SOR-001", "ETHUSDT", "short"),
    ("SOR-001", "SOLUSDT", "long"),
    ("SOR-001", "SOLUSDT", "short"),
    ("SOR-001", "AVAXUSDT", "long"),
    ("SOR-001", "AVAXUSDT", "short"),
    ("SOR-001", "BTCUSDT", "long"),
    ("SOR-001", "BTCUSDT", "short"),
]


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def pg_control_connection():
    migration = _load_module(MIGRATION_PATH, "migration_086_action_time_full_chain")
    seed = _load_module(SEED_PATH, "seed_action_time_full_chain")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        old_op = migration.op
        migration.op = Operations(MigrationContext.configure(conn))
        try:
            migration.upgrade()
        finally:
            migration.op = old_op
        seed.seed_runtime_control_state_foundation(conn)
    with engine.connect() as conn:
        yield conn
    engine.dispose()


def test_seed_contains_exact_active_candidate_scope_contract(pg_control_connection):
    rows = pg_control_connection.execute(
        text(
            """
            SELECT strategy_group_id, symbol, side
            FROM brc_strategy_group_candidate_scope
            WHERE status = 'active'
            ORDER BY strategy_group_id, priority_rank, symbol, side
            """
        )
    ).all()

    assert set(rows) == set(ACTIVE_CANDIDATE_SCOPES)
    assert len(rows) == 22
    assert {
        row["strategy_group_id"]
        for row in pg_control_connection.execute(
            text(
                """
                SELECT DISTINCT strategy_group_id
                FROM brc_strategy_group_candidate_scope
                WHERE status = 'active'
                """
            )
        ).mappings()
    } == {"BRF2-001", "CPM-RO-001", "MI-001", "MPG-001", "SOR-001"}


@pytest.mark.parametrize(
    ("strategy_group_id", "symbol", "side"),
    ACTIVE_CANDIDATE_SCOPES,
)
def test_each_active_candidate_scope_reaches_disabled_smoke_from_raw_pg_input(
    pg_control_connection,
    monkeypatch,
    strategy_group_id: str,
    symbol: str,
    side: str,
):
    _insert_ready_fresh_signal(
        pg_control_connection,
        strategy_group_id,
        symbol,
        side,
        insert_action_time_fact=False,
        insert_signal=False,
    )
    signal_payload = _write_monitor_signal_summary_to_pg(
        pg_control_connection,
        strategy_group_id=strategy_group_id,
        symbol=symbol,
        side=side,
    )
    assert signal_payload["status"] == "pg_live_signal_events_written"
    assert signal_payload["written_count"] == 1
    pg_control_connection.execute(text("DELETE FROM brc_pretrade_readiness_rows"))

    fact_payload = fact_materializer.materialize_action_time_fact_snapshots(
        pg_control_connection,
        now_ms=NOW_MS,
    )
    assert fact_payload["status"] == "action_time_fact_snapshots_materialized"
    assert fact_payload["materialized_count"] == 1
    assert fact_payload["blocked_count"] == 0

    monkeypatch.setattr(publisher.time, "time", lambda: NOW_MS / 1000)
    projection_payload = publisher.publish_runtime_control_current_projections(
        pg_control_connection,
    )
    assert projection_payload["status"] == "current_projections_published"

    lane_payload = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS + 1,
    )
    assert lane_payload["status"] == "promotion_action_time_lane_created"
    assert lane_payload["strategy_group_id"] == strategy_group_id
    assert lane_payload["symbol"] == symbol
    assert lane_payload["side"] == side
    assert lane_payload["forbidden_effects"] == lane_materializer.FORBIDDEN_EFFECTS

    ticket_payload = ticket_materializer.materialize_action_time_ticket(
        pg_control_connection,
        now_ms=NOW_MS + 2,
    )
    assert ticket_payload["status"] == "action_time_ticket_created"
    assert ticket_payload["strategy_group_id"] == strategy_group_id
    assert ticket_payload["symbol"] == symbol
    assert ticket_payload["side"] == side
    assert ticket_payload["forbidden_effects"] == ticket_materializer.FORBIDDEN_EFFECTS

    finalgate_payload = finalgate.materialize_action_time_finalgate_preflight(
        pg_control_connection,
        ticket_id=str(ticket_payload["ticket_id"]),
        now_ms=NOW_MS + 3,
    )
    assert finalgate_payload["status"] == "finalgate_ready"
    assert finalgate_payload["ticket_id"] == ticket_payload["ticket_id"]
    assert finalgate_payload["forbidden_effects"] == finalgate.FORBIDDEN_EFFECTS

    handoff_payload = handoff.materialize_action_time_operation_layer_handoff(
        pg_control_connection,
        ticket_id=str(ticket_payload["ticket_id"]),
        finalgate_pass_id=str(finalgate_payload["finalgate_pass_id"]),
        now_ms=NOW_MS + 4,
    )
    assert handoff_payload["status"] == "operation_layer_handoff_ready"
    assert handoff_payload["ticket_id"] == ticket_payload["ticket_id"]
    assert handoff_payload["finalgate_pass_id"] == finalgate_payload["finalgate_pass_id"]
    assert handoff_payload["forbidden_effects"] == handoff.FORBIDDEN_EFFECTS

    safety_payload = safety_state.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=str(ticket_payload["ticket_id"]),
        operation_layer_handoff_id=str(handoff_payload["operation_layer_handoff_id"]),
        now_ms=NOW_MS + 5,
    )
    assert safety_payload["status"] == "runtime_safety_state_ready"
    assert safety_payload["submit_allowed"] is True
    assert safety_payload["blockers"] == []
    assert safety_payload["forbidden_effects"] == safety_state.FORBIDDEN_EFFECTS

    submit_payload = protected_submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=str(ticket_payload["ticket_id"]),
        operation_submit_command_id=str(handoff_payload["operation_submit_command_id"]),
        submit_mode="disabled_smoke",
        now_ms=NOW_MS + 6,
    )
    assert submit_payload["status"] == "disabled_smoke_passed"
    assert submit_payload["submit_allowed"] is True
    assert submit_payload["official_operation_layer_submit_called"] is True
    assert submit_payload["exchange_write_called"] is False
    assert submit_payload["order_created"] is False
    assert submit_payload["order_lifecycle_called"] is False

    assert _count(pg_control_connection, "brc_live_signal_events") == 1
    assert _count(pg_control_connection, "brc_promotion_candidates") == 1
    assert _count(pg_control_connection, "brc_action_time_lane_inputs") == 1
    assert _count(pg_control_connection, "brc_action_time_tickets") == 1
    assert _finalgate_ready_event_count(pg_control_connection) == 1
    assert _count(pg_control_connection, "brc_operation_layer_handoffs") == 1
    assert _count(pg_control_connection, "brc_runtime_safety_state_snapshots") == 1
    assert _count(pg_control_connection, "brc_ticket_bound_protected_submit_attempts") == 1


def test_unsupported_side_is_not_created_by_seed(pg_control_connection):
    unsupported_rows = pg_control_connection.execute(
        text(
            """
            SELECT strategy_group_id, symbol, side
            FROM brc_strategy_group_candidate_scope
            WHERE status = 'active'
              AND (
                (strategy_group_id = 'BRF2-001' AND side != 'short')
                OR (strategy_group_id IN ('CPM-RO-001', 'MI-001', 'MPG-001')
                    AND side != 'long')
              )
            """
        )
    ).all()

    assert unsupported_rows == []


def _count(conn, table_name: str) -> int:
    assert table_name in {
        "brc_action_time_lane_inputs",
        "brc_action_time_tickets",
        "brc_live_signal_events",
        "brc_operation_layer_handoffs",
        "brc_promotion_candidates",
        "brc_runtime_safety_state_snapshots",
        "brc_ticket_bound_protected_submit_attempts",
    }
    return conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()


def _write_monitor_signal_summary_to_pg(
    conn,
    *,
    strategy_group_id: str,
    symbol: str,
    side: str,
) -> dict:
    return runtime_active_observation_monitor.write_runtime_signal_summaries_to_pg(
        {
            "runtime_summaries": [
                {
                    "runtime_instance_id": f"runtime:{strategy_group_id}:{symbol}:{side}",
                    "strategy_family_id": strategy_group_id,
                    "strategy_family_version_id": f"sgv:{strategy_group_id}:v1",
                    "symbol": symbol,
                    "side": side,
                    "status": "waiting_for_signal",
                    "signal_summary": {
                        "signal_type": "would_enter",
                        "side": side,
                        "confidence": "0.90",
                        "reason_codes": ["constructed_monitor_signal_summary"],
                        "trigger_candle_close_time_ms": NOW_MS - 60_000,
                        "time_authority": "trigger_candle_close_time_ms",
                    },
                }
            ],
        },
        database_url="unused://pg-control-test",
        allow_non_postgres_for_test=True,
        now_ms=NOW_MS,
        conn=conn,
    )


def _finalgate_ready_event_count(conn) -> int:
    return conn.execute(
        text(
            """
            SELECT COUNT(*)
            FROM brc_action_time_ticket_events
            WHERE to_status = 'finalgate_ready'
            """
        )
    ).scalar_one()
