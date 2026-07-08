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
from src.application.action_time.full_chain_simulation_harness import (
    FULL_CHAIN_FAILURE_SCENARIOS,
    FullChainSimulationInput,
    run_ticket_bound_full_chain_simulation,
    run_ticket_bound_full_chain_failure_scenario,
)
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
LIFECYCLE_SAFETY_CORE_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-08-094_extend_ticket_bound_lifecycle_safety_core_statuses.py"
)
RUNNER_MUTATION_COMMAND_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-08-095_create_ticket_bound_runner_mutation_commands.py"
)
PROTECTION_RECOVERY_COMMAND_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-08-096_create_ticket_bound_protection_recovery_commands.py"
)
ORPHAN_PROTECTION_CLEANUP_COMMAND_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-08-098_create_ticket_bound_orphan_protection_cleanup_commands.py"
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
    lifecycle_safety_core_migration = _load_module(
        LIFECYCLE_SAFETY_CORE_MIGRATION_PATH,
        "migration_094_action_time_full_chain",
    )
    runner_mutation_command_migration = _load_module(
        RUNNER_MUTATION_COMMAND_MIGRATION_PATH,
        "migration_095_action_time_full_chain",
    )
    protection_recovery_command_migration = _load_module(
        PROTECTION_RECOVERY_COMMAND_MIGRATION_PATH,
        "migration_096_action_time_full_chain",
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
                        old_safety_core_op = lifecycle_safety_core_migration.op
                        lifecycle_safety_core_migration.op = migration.op
                        try:
                            lifecycle_safety_core_migration.upgrade()
                            old_runner_cmd_op = runner_mutation_command_migration.op
                            runner_mutation_command_migration.op = migration.op
                            try:
                                runner_mutation_command_migration.upgrade()
                                old_protection_recovery_op = (
                                    protection_recovery_command_migration.op
                                )
                                protection_recovery_command_migration.op = migration.op
                                try:
                                    protection_recovery_command_migration.upgrade()
                                    orphan_cleanup_command_migration = _load_module(
                                        ORPHAN_PROTECTION_CLEANUP_COMMAND_MIGRATION_PATH,
                                        "migration_098_action_time_full_chain",
                                    )
                                    old_orphan_cleanup_op = (
                                        orphan_cleanup_command_migration.op
                                    )
                                    orphan_cleanup_command_migration.op = migration.op
                                    try:
                                        orphan_cleanup_command_migration.upgrade()
                                    finally:
                                        orphan_cleanup_command_migration.op = (
                                            old_orphan_cleanup_op
                                        )
                                finally:
                                    protection_recovery_command_migration.op = (
                                        old_protection_recovery_op
                                    )
                            finally:
                                runner_mutation_command_migration.op = old_runner_cmd_op
                        finally:
                            lifecycle_safety_core_migration.op = old_safety_core_op
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
    ("strategy_group_id", "symbol", "side", "fact_values", "expected_tp1"),
    [
        (
            "BRF2-001",
            "AVAXUSDT",
            "short",
            {
                "rally_failure_confirmed": True,
                "short_side_not_disabled": True,
                "rally_high_reference": "20",
                "strong_uptrend_disable": False,
                "last_price": "18",
            },
            "16",
        ),
        (
            "SOR-001",
            "AVAXUSDT",
            "short",
            {
                "opening_range_defined": True,
                "breakdown_confirmed": True,
                "opening_range_high_reference": "20",
                "last_price": "18",
            },
            "16",
        ),
    ],
)
def test_short_raw_pg_input_derives_tp1_before_protected_submit(
    pg_control_connection,
    monkeypatch,
    strategy_group_id: str,
    symbol: str,
    side: str,
    fact_values: dict,
    expected_tp1: str,
):
    payloads = _run_raw_pg_input_to_runtime_safety(
        pg_control_connection,
        monkeypatch,
        strategy_group_id=strategy_group_id,
        symbol=symbol,
        side=side,
        fact_values=fact_values,
    )

    action_time_values = _fact_values_for_surface(
        pg_control_connection,
        strategy_group_id=strategy_group_id,
        symbol=symbol,
        side=side,
        fact_surface="action_time",
    )
    assert action_time_values["take_profit_1"] == expected_tp1
    assert action_time_values["tp1_reference_price"] == expected_tp1
    assert action_time_values["tp1_derivation"] == "entry_to_protection_one_r"

    submit_payload = protected_submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=str(payloads["ticket"]["ticket_id"]),
        operation_submit_command_id=str(payloads["handoff"]["operation_submit_command_id"]),
        submit_mode="disabled_smoke",
        now_ms=NOW_MS + 6,
    )

    assert submit_payload["status"] == "disabled_smoke_passed"
    assert submit_payload["blockers"] == []
    tp1_order = next(
        order
        for order in submit_payload["submit_request"]["orders"]
        if order["order_role"] == "TP1"
    )
    assert tp1_order["gateway_side"] == "buy"
    assert tp1_order["reduce_only"] is True
    assert tp1_order["price"] == expected_tp1


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
    monkeypatch.setattr(publisher.time, "time", lambda: NOW_MS / 1000)
    payloads = run_ticket_bound_full_chain_simulation(
        pg_control_connection,
        FullChainSimulationInput(
            strategy_group_id=strategy_group_id,
            symbol=symbol,
            side=side,
            now_ms=NOW_MS,
        ),
        projection_publisher=publisher.publish_runtime_control_current_projections,
    )

    assert payloads["prepared_submit"]["status"] == "submit_prepared"
    assert payloads["submitted"]["status"] == "submitted"
    assert payloads["protection"]["status"] == "position_protected"
    assert payloads["post_submit_pending"]["status"] == "reconciliation_pending"
    assert payloads["runner_mutation_command"]["status"] == "prepared"
    assert payloads["runner_mutation_result"]["status"] == "result_recorded"
    assert payloads["runner"]["status"] == "runner_protected"
    assert payloads["final"]["status"] == "closed"
    assert payloads["final"]["reconciliation_state"] == "matched"
    assert payloads["final"]["settlement_state"] == "released"
    assert payloads["final"]["review_state"] == "recorded"
    assert payloads["authority_boundary"]["uses_mock_exchange_result"] is True
    assert payloads["authority_boundary"]["calls_exchange_write"] is False

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


@pytest.mark.parametrize("scenario", FULL_CHAIN_FAILURE_SCENARIOS)
def test_full_chain_failure_matrix_stops_at_exact_lifecycle_state(
    pg_control_connection,
    monkeypatch,
    scenario: str,
):
    monkeypatch.setattr(publisher.time, "time", lambda: NOW_MS / 1000)
    payloads = run_ticket_bound_full_chain_failure_scenario(
        pg_control_connection,
        FullChainSimulationInput(
            strategy_group_id="SOR-001",
            symbol="AVAXUSDT",
            side="short",
            fact_values={
                "opening_range_defined": True,
                "breakdown_confirmed": True,
                "opening_range_high_reference": "20",
                "last_price": "18",
            },
            now_ms=NOW_MS,
        ),
        projection_publisher=publisher.publish_runtime_control_current_projections,
        scenario=scenario,
    )

    assert payloads["prepared_submit"]["status"] == "submit_prepared"
    assert payloads["authority_boundary"]["calls_exchange_write"] is False
    assert payloads["authority_boundary"]["uses_repo_json_or_md_authority"] is False

    expected = {
        "entry_accepted_sl_failed": (
            "protection_missing",
            ["exchange_submit_failed:sl"],
            "prepared",
        ),
        "sl_ok_tp1_failed": (
            "protection_submit_failed",
            ["exchange_submit_failed:tp1"],
            "prepared",
        ),
        "entry_partial_fill": (
            "entry_partial_fill_unhandled",
            ["entry_partial_fill"],
            None,
        ),
        "tp1_filled_runner_missing": (
            "runner_mutation_pending",
            ["runner_sl_exchange_order_id_required"],
            None,
        ),
        "old_sl_cancel_failed": (
            "runner_mutation_failed",
            [
                "old sl cancel rejected by simulation",
                "old_sl_cancel_not_confirmed",
                "runner_sl_exchange_order_id_missing",
                "runner_sl_submit_not_confirmed",
            ],
            None,
        ),
        "runner_submit_failed_after_old_sl_cancel": (
            "runner_mutation_failed",
            [
                "runner sl submit rejected by simulation",
                "runner_sl_exchange_order_id_missing",
                "runner_sl_submit_not_confirmed",
                "runner_unprotected_after_old_sl_cancelled",
            ],
            None,
        ),
        "pg_protected_exchange_missing": (
            "protection_reconciliation_mismatch",
            ["open_position_without_valid_sl", "sl_exchange_order_missing"],
            None,
        ),
        "flat_position_live_protection_cleanup": (
            "reconciliation_matched",
            [],
            "result_recorded",
        ),
        "duplicate_tp1_fill_idempotent": (
            "runner_mutation_pending",
            [],
            "prepared",
        ),
    }
    expected_lifecycle_status, expected_blockers, expected_aux_status = expected[scenario]

    assert _status(
        pg_control_connection,
        "brc_ticket_bound_order_lifecycle_runs",
        "lifecycle_run_id",
        _lifecycle_id(pg_control_connection),
    ) == expected_lifecycle_status
    assert _lifecycle_blockers(pg_control_connection) == expected_blockers

    if scenario in {"entry_accepted_sl_failed", "sl_ok_tp1_failed"}:
        assert payloads["recovery_command"]["status"] == expected_aux_status
    elif scenario == "flat_position_live_protection_cleanup":
        assert payloads["cleanup_result"]["status"] == expected_aux_status
        assert _count(
            pg_control_connection,
            "brc_ticket_bound_orphan_protection_cleanup_commands",
        ) == 1
    elif scenario == "duplicate_tp1_fill_idempotent":
        assert (
            payloads["duplicate_runner_mutation_command"][
                "idempotent_existing_runner_mutation_command"
            ]
            is True
        )
        assert _count(
            pg_control_connection,
            "brc_ticket_bound_runner_mutation_commands",
        ) == 1


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
        "brc_ticket_bound_orphan_protection_cleanup_commands",
        "brc_ticket_bound_post_submit_closures",
        "brc_ticket_bound_protected_submit_attempts",
        "brc_ticket_bound_runner_mutation_commands",
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


def _lifecycle_blockers(conn) -> list[str]:
    raw = conn.execute(
        text("SELECT blockers FROM brc_ticket_bound_order_lifecycle_runs")
    ).scalar_one()
    import json

    parsed = raw
    while isinstance(parsed, str):
        parsed = json.loads(parsed)
    return list(parsed)


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
    fact_values: dict | None = None,
) -> dict[str, dict]:
    _insert_ready_fresh_signal(
        conn,
        strategy_group_id,
        symbol,
        side,
        insert_action_time_fact=False,
        insert_signal=False,
        fact_values=fact_values,
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


def _fact_values_for_surface(
    conn,
    *,
    strategy_group_id: str,
    symbol: str,
    side: str,
    fact_surface: str,
) -> dict:
    row = conn.execute(
        text(
            """
            SELECT fact_values
            FROM brc_runtime_fact_snapshots
            WHERE strategy_group_id = :strategy_group_id
              AND symbol = :symbol
              AND side = :side
              AND fact_surface = :fact_surface
            ORDER BY created_at_ms DESC
            LIMIT 1
            """
        ),
        {
            "strategy_group_id": strategy_group_id,
            "symbol": symbol,
            "side": side,
            "fact_surface": fact_surface,
        },
    ).scalar_one()
    import json

    parsed = row
    while isinstance(parsed, str):
        parsed = json.loads(parsed)
    return dict(parsed)


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
