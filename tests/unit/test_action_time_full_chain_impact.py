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
from scripts import materialize_ticket_bound_exit_protection_set as exit_protection
from scripts import materialize_ticket_bound_post_submit_closure as post_submit_closure
from scripts import materialize_ticket_bound_protected_submit_attempt as protected_submit
from scripts import materialize_ticket_bound_runner_protection_adjustment as runner_adjuster
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
LIFECYCLE_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-08-091_create_ticket_bound_order_lifecycle.py"
)
RUNNER_LIFECYCLE_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-08-092_extend_ticket_bound_runner_statuses.py"
)
LIFECYCLE_CLOSURE_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-08-093_extend_ticket_bound_lifecycle_closure.py"
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
    lifecycle_migration = _load_module(
        LIFECYCLE_MIGRATION_PATH,
        "migration_091_action_time_full_chain",
    )
    runner_lifecycle_migration = _load_module(
        RUNNER_LIFECYCLE_MIGRATION_PATH,
        "migration_092_action_time_full_chain",
    )
    lifecycle_closure_migration = _load_module(
        LIFECYCLE_CLOSURE_MIGRATION_PATH,
        "migration_093_action_time_full_chain",
    )
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
            old_lifecycle_op = lifecycle_migration.op
            lifecycle_migration.op = migration.op
            try:
                lifecycle_migration.upgrade()
                old_runner_op = runner_lifecycle_migration.op
                runner_lifecycle_migration.op = migration.op
                try:
                    runner_lifecycle_migration.upgrade()
                    old_closure_op = lifecycle_closure_migration.op
                    lifecycle_closure_migration.op = migration.op
                    try:
                        lifecycle_closure_migration.upgrade()
                    finally:
                        lifecycle_closure_migration.op = old_closure_op
                finally:
                    runner_lifecycle_migration.op = old_runner_op
            finally:
                lifecycle_migration.op = old_lifecycle_op
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
    payloads = _run_raw_pg_input_to_runtime_safety(
        pg_control_connection,
        monkeypatch,
        strategy_group_id=strategy_group_id,
        symbol=symbol,
        side=side,
    )

    submit_payload = protected_submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=str(payloads["ticket"]["ticket_id"]),
        operation_submit_command_id=str(payloads["handoff"]["operation_submit_command_id"]),
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


@pytest.mark.parametrize(
    ("strategy_group_id", "symbol", "side"),
    ACTIVE_CANDIDATE_SCOPES,
)
def test_each_active_candidate_scope_reaches_mock_real_submit_and_closure_from_raw_pg_input(
    pg_control_connection,
    monkeypatch,
    strategy_group_id: str,
    symbol: str,
    side: str,
):
    payloads = _run_raw_pg_input_to_runtime_safety(
        pg_control_connection,
        monkeypatch,
        strategy_group_id=strategy_group_id,
        symbol=symbol,
        side=side,
    )

    prepared = protected_submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=str(payloads["ticket"]["ticket_id"]),
        operation_submit_command_id=str(payloads["handoff"]["operation_submit_command_id"]),
        submit_mode="real_gateway_action",
        now_ms=NOW_MS + 6,
    )
    assert prepared["status"] == "submit_prepared"
    assert prepared["submit_allowed"] is True
    assert prepared["exchange_write_called"] is False
    assert prepared["order_created"] is False
    assert prepared["order_lifecycle_called"] is False

    submitted = protected_submit.record_ticket_bound_protected_submit_result(
        pg_control_connection,
        protected_submit_attempt_id=str(prepared["protected_submit_attempt_id"]),
        submit_result=_mock_exchange_submit_result(prepared),
        now_ms=NOW_MS + 7,
    )
    assert submitted["status"] == "submitted"
    assert submitted["blockers"] == []
    assert submitted["exchange_write_called"] is True
    assert submitted["order_created"] is True
    assert submitted["order_lifecycle_called"] is True

    protection_payload = exit_protection.materialize_ticket_bound_exit_protection_set(
        pg_control_connection,
        protected_submit_attempt_id=str(prepared["protected_submit_attempt_id"]),
        now_ms=NOW_MS + 8,
    )
    assert protection_payload["status"] == "position_protected"
    assert protection_payload["protection_complete"] is True
    assert protection_payload["blockers"] == []

    closure_payload = post_submit_closure.materialize_ticket_bound_post_submit_closure(
        pg_control_connection,
        protected_submit_attempt_id=str(prepared["protected_submit_attempt_id"]),
        now_ms=NOW_MS + 9,
    )
    assert closure_payload["status"] == "reconciliation_pending"
    assert closure_payload["ticket_id"] == payloads["ticket"]["ticket_id"]
    assert closure_payload["operation_submit_command_id"] == (
        payloads["handoff"]["operation_submit_command_id"]
    )
    assert closure_payload["first_blocker"] == "post_submit_reconciliation_fact_missing"
    assert closure_payload["exchange_write_called"] is False
    assert closure_payload["order_created"] is False
    assert closure_payload["order_lifecycle_called"] is False

    set_id = pg_control_connection.execute(
        text(
            """
            SELECT exit_protection_set_id
            FROM brc_ticket_bound_exit_protection_sets
            WHERE protected_submit_attempt_id = :attempt_id
            """
        ),
        {"attempt_id": prepared["protected_submit_attempt_id"]},
    ).scalar_one()
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_ticket_bound_exit_protection_orders
            SET status = 'filled', updated_at_ms = :updated_at_ms
            WHERE exit_protection_set_id = :set_id
              AND role = 'TP1'
            """
        ),
        {"set_id": set_id, "updated_at_ms": NOW_MS + 10},
    )
    runner_payload = runner_adjuster.materialize_ticket_bound_runner_protection_adjustment(
        pg_control_connection,
        exit_protection_set_id=set_id,
        runner_sl_exchange_order_id="mock-exchange-runner-sl",
        runner_sl_local_order_id="mock-runner-sl",
        now_ms=NOW_MS + 11,
    )
    assert runner_payload["status"] == "runner_protected"
    assert runner_payload["blockers"] == []

    final_payload = post_submit_closure.materialize_ticket_bound_lifecycle_closure(
        pg_control_connection,
        protected_submit_attempt_id=str(prepared["protected_submit_attempt_id"]),
        final_exit_exchange_order_id="mock-exchange-runner-sl",
        final_exit_role="RUNNER_SL",
        final_position_flat_confirmed=True,
        reconciliation_evidence_id=f"mock-recon:{strategy_group_id}:{symbol}:{side}",
        settlement_evidence_id=f"mock-settlement:{strategy_group_id}:{symbol}:{side}",
        review_evidence_id=f"mock-review:{strategy_group_id}:{symbol}:{side}",
        now_ms=NOW_MS + 12,
    )
    assert final_payload["status"] == "closed"
    assert final_payload["reconciliation_state"] == "matched"
    assert final_payload["settlement_state"] == "released"
    assert final_payload["review_state"] == "recorded"
    assert final_payload["exchange_write_called"] is False
    assert final_payload["order_created"] is False
    assert final_payload["order_lifecycle_called"] is False

    assert _status(
        pg_control_connection,
        "brc_action_time_tickets",
        "ticket_id",
        str(payloads["ticket"]["ticket_id"]),
    ) == "submitted"
    assert _status(
        pg_control_connection,
        "brc_operation_layer_handoffs",
        "operation_layer_handoff_id",
        str(payloads["handoff"]["operation_layer_handoff_id"]),
    ) == "submitted"
    assert _count(pg_control_connection, "brc_ticket_bound_post_submit_closures") == 1
    assert _count(pg_control_connection, "brc_ticket_bound_order_lifecycle_runs") == 1
    assert _count(pg_control_connection, "brc_ticket_bound_exit_protection_sets") == 1
    assert _count(pg_control_connection, "brc_ticket_bound_exit_protection_orders") == 3
    assert _status(
        pg_control_connection,
        "brc_ticket_bound_order_lifecycle_runs",
        "lifecycle_run_id",
        _lifecycle_id(pg_control_connection),
    ) == "lifecycle_closed"
    assert _status(
        pg_control_connection,
        "brc_ticket_bound_post_submit_closures",
        "post_submit_closure_id",
        _post_submit_closure_id(pg_control_connection),
    ) == "closed"


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


@pytest.mark.parametrize(
    ("strategy_group_id", "symbol", "unsupported_side"),
    [
        ("BRF2-001", "BTCUSDT", "long"),
        ("CPM-RO-001", "ETHUSDT", "short"),
        ("MI-001", "AVAXUSDT", "short"),
        ("MPG-001", "OPUSDT", "short"),
    ],
)
def test_raw_pg_input_for_unsupported_side_is_rejected_before_signal_creation(
    pg_control_connection,
    strategy_group_id: str,
    symbol: str,
    unsupported_side: str,
):
    _insert_satisfied_public_fact_for_unsupported_side(
        pg_control_connection,
        strategy_group_id=strategy_group_id,
        symbol=symbol,
        side=unsupported_side,
    )

    signal_payload = _write_monitor_signal_summary_to_pg(
        pg_control_connection,
        strategy_group_id=strategy_group_id,
        symbol=symbol,
        side=unsupported_side,
    )

    assert signal_payload["status"] == "pg_live_signal_events_blocked"
    assert signal_payload["written_count"] == 0
    assert signal_payload["signal_event_ids"] == []
    assert [
        item["blocker"] for item in signal_payload["skipped"]
    ] == ["candidate_scope_event_binding_missing"]
    assert _count(pg_control_connection, "brc_live_signal_events") == 0

    fact_payload = fact_materializer.materialize_action_time_fact_snapshots(
        pg_control_connection,
        now_ms=NOW_MS,
    )
    assert fact_payload["status"] == "no_current_fresh_live_signal"

    lane_payload = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS + 1,
    )
    assert lane_payload["status"] == "no_fresh_signal"
    assert _count(pg_control_connection, "brc_promotion_candidates") == 0
    assert _count(pg_control_connection, "brc_action_time_lane_inputs") == 0
    assert _count(pg_control_connection, "brc_action_time_tickets") == 0


def _count(conn, table_name: str) -> int:
    assert table_name in {
        "brc_action_time_lane_inputs",
        "brc_action_time_tickets",
        "brc_live_signal_events",
        "brc_operation_layer_handoffs",
        "brc_promotion_candidates",
        "brc_runtime_safety_state_snapshots",
        "brc_ticket_bound_exit_protection_orders",
        "brc_ticket_bound_exit_protection_sets",
        "brc_ticket_bound_order_lifecycle_runs",
        "brc_ticket_bound_post_submit_closures",
        "brc_ticket_bound_protected_submit_attempts",
    }
    return conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()


def _status(conn, table_name: str, id_column: str, id_value: str) -> str:
    assert table_name in {
        "brc_action_time_tickets",
        "brc_ticket_bound_order_lifecycle_runs",
        "brc_ticket_bound_post_submit_closures",
        "brc_operation_layer_handoffs",
    }
    assert id_column in {
        "ticket_id",
        "operation_layer_handoff_id",
        "lifecycle_run_id",
        "post_submit_closure_id",
    }
    return conn.execute(
        text(
            f"""
            SELECT status
            FROM {table_name}
            WHERE {id_column} = :id_value
            """
        ),
        {"id_value": id_value},
    ).scalar_one()


def _lifecycle_id(conn) -> str:
    return str(
        conn.execute(
            text("SELECT lifecycle_run_id FROM brc_ticket_bound_order_lifecycle_runs")
        ).scalar_one()
    )


def _post_submit_closure_id(conn) -> str:
    return str(
        conn.execute(
            text("SELECT post_submit_closure_id FROM brc_ticket_bound_post_submit_closures")
        ).scalar_one()
    )


def _run_raw_pg_input_to_runtime_safety(
    conn,
    monkeypatch,
    *,
    strategy_group_id: str,
    symbol: str,
    side: str,
) -> dict[str, dict]:
    _insert_ready_fresh_signal(
        conn,
        strategy_group_id,
        symbol,
        side,
        insert_action_time_fact=False,
        insert_signal=False,
    )
    signal_payload = _write_monitor_signal_summary_to_pg(
        conn,
        strategy_group_id=strategy_group_id,
        symbol=symbol,
        side=side,
    )
    assert signal_payload["status"] == "pg_live_signal_events_written"
    assert signal_payload["written_count"] == 1
    conn.execute(text("DELETE FROM brc_pretrade_readiness_rows"))

    fact_payload = fact_materializer.materialize_action_time_fact_snapshots(
        conn,
        now_ms=NOW_MS,
    )
    assert fact_payload["status"] == "action_time_fact_snapshots_materialized"
    assert fact_payload["materialized_count"] == 1
    assert fact_payload["blocked_count"] == 0

    monkeypatch.setattr(publisher.time, "time", lambda: NOW_MS / 1000)
    projection_payload = publisher.publish_runtime_control_current_projections(conn)
    assert projection_payload["status"] == "current_projections_published"

    lane_payload = lane_materializer.materialize_pg_promotion_action_time_lane(
        conn,
        now_ms=NOW_MS + 1,
    )
    assert lane_payload["status"] == "promotion_action_time_lane_created"
    assert lane_payload["strategy_group_id"] == strategy_group_id
    assert lane_payload["symbol"] == symbol
    assert lane_payload["side"] == side
    assert lane_payload["forbidden_effects"] == lane_materializer.FORBIDDEN_EFFECTS

    ticket_payload = ticket_materializer.materialize_action_time_ticket(
        conn,
        now_ms=NOW_MS + 2,
    )
    assert ticket_payload["status"] == "action_time_ticket_created"
    assert ticket_payload["strategy_group_id"] == strategy_group_id
    assert ticket_payload["symbol"] == symbol
    assert ticket_payload["side"] == side
    assert ticket_payload["forbidden_effects"] == ticket_materializer.FORBIDDEN_EFFECTS

    finalgate_payload = finalgate.materialize_action_time_finalgate_preflight(
        conn,
        ticket_id=str(ticket_payload["ticket_id"]),
        now_ms=NOW_MS + 3,
    )
    assert finalgate_payload["status"] == "finalgate_ready"
    assert finalgate_payload["ticket_id"] == ticket_payload["ticket_id"]
    assert finalgate_payload["forbidden_effects"] == finalgate.FORBIDDEN_EFFECTS

    handoff_payload = handoff.materialize_action_time_operation_layer_handoff(
        conn,
        ticket_id=str(ticket_payload["ticket_id"]),
        finalgate_pass_id=str(finalgate_payload["finalgate_pass_id"]),
        now_ms=NOW_MS + 4,
    )
    assert handoff_payload["status"] == "operation_layer_handoff_ready"
    assert handoff_payload["ticket_id"] == ticket_payload["ticket_id"]
    assert handoff_payload["finalgate_pass_id"] == finalgate_payload["finalgate_pass_id"]
    assert handoff_payload["forbidden_effects"] == handoff.FORBIDDEN_EFFECTS

    safety_payload = safety_state.materialize_ticket_bound_runtime_safety_state(
        conn,
        ticket_id=str(ticket_payload["ticket_id"]),
        operation_layer_handoff_id=str(handoff_payload["operation_layer_handoff_id"]),
        now_ms=NOW_MS + 5,
    )
    assert safety_payload["status"] == "runtime_safety_state_ready"
    assert safety_payload["submit_allowed"] is True
    assert safety_payload["blockers"] == []
    assert safety_payload["forbidden_effects"] == safety_state.FORBIDDEN_EFFECTS

    return {
        "signal": signal_payload,
        "fact": fact_payload,
        "projection": projection_payload,
        "lane": lane_payload,
        "ticket": ticket_payload,
        "finalgate": finalgate_payload,
        "handoff": handoff_payload,
        "safety": safety_payload,
    }


def _mock_exchange_submit_result(prepared: dict) -> dict:
    return {
        "status": "exchange_submit_orders_submitted",
        "ticket_id": prepared["ticket_id"],
        "operation_submit_command_id": prepared["operation_submit_command_id"],
        "strategy_group_id": prepared["strategy_group_id"],
        "symbol": prepared["symbol"],
        "side": prepared["side"],
        "exchange_write_called": True,
        "order_created": True,
        "order_lifecycle_called": True,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "submitted_orders": [
            _mock_submitted_order(prepared, order)
            for order in prepared["submit_request"]["orders"]
        ],
    }


def _mock_submitted_order(prepared: dict, order: dict) -> dict:
    role = order["order_role"]
    row = {
        "local_order_id": order["local_order_id"],
        "exchange_order_id": f"mock-exchange-{role.lower()}",
        "order_role": role,
        "reduce_only": order.get("reduce_only") is True,
        "amount": order["amount"],
        "price": order.get("price") or "",
        "trigger_price": order.get("trigger_price") or "",
    }
    if role == "ENTRY":
        row.update(
            {
                "status": "FILLED",
                "filled_qty": order["amount"],
                "average_exec_price": prepared["submit_request"]["reference_price"],
            }
        )
    return row


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


def _insert_satisfied_public_fact_for_unsupported_side(
    conn,
    *,
    strategy_group_id: str,
    symbol: str,
    side: str,
) -> None:
    conn.execute(
        text(
            """
            INSERT INTO brc_runtime_fact_snapshots (
              fact_snapshot_id,
              strategy_group_id,
              symbol,
              side,
              runtime_profile_id,
              fact_surface,
              source_kind,
              source_ref,
              computed,
              satisfied,
              freshness_state,
              failed_facts,
              fact_values,
              blocker_class,
              observed_at_ms,
              valid_until_ms,
              created_at_ms
            ) VALUES (
              :fact_snapshot_id,
              :strategy_group_id,
              :symbol,
              :side,
              'rtp:tiny-live:default',
              'pretrade_public',
              'live_market',
              'constructed_unsupported_side_guard',
              true,
              true,
              'fresh',
              '[]',
              '{"opening_range_high_reference": 2000, "opening_range_low_reference": 1800}',
              'none',
              :now_ms,
              :valid_until_ms,
              :now_ms
            )
            """
        ),
        {
            "fact_snapshot_id": (
                f"fact:unsupported:{strategy_group_id}:{symbol}:{side}"
            ),
            "strategy_group_id": strategy_group_id,
            "symbol": symbol,
            "side": side,
            "now_ms": NOW_MS,
            "valid_until_ms": NOW_MS + 60_000,
        },
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
