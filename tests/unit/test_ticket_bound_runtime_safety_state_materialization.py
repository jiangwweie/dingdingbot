from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from src.application.action_time import finalgate_preflight as finalgate
from src.application.action_time import operation_layer_handoff as handoff
from src.application.action_time import action_time_ticket as ticket_materializer
from src.application.action_time import runtime_safety_state as safety
from tests.unit.test_action_time_ticket_materialization import (
    NOW_MS,
    _insert_action_time_lane_graph,
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
POST_SUBMIT_RECONCILIATION_TICK_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-09-101_create_ticket_bound_reconciliation_ticks.py"
)
LIVE_OUTCOME_LEDGER_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-09-102_create_live_outcome_ledger.py"
)
RISK_RESERVATION_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-09-103_add_budget_risk_at_stop_reservation.py"
)
EXECUTION_ELIGIBILITY_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-10-104_add_execution_eligibility_authority.py"
)
EXCHANGE_COMMAND_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-10-105_create_ticket_bound_exchange_commands.py"
)
TYPED_SCOPE_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-11-113_create_exchange_account_mode_and_domain_holds.py"
)
LIFECYCLE_COMMAND_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-11-114_extend_exchange_commands_for_lifecycle.py"
)
DYNAMIC_RISK_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-12-115_add_dynamic_execution_risk_policy.py"
)
OFC_ECONOMICS_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-12-116_add_opportunity_feedback_economics.py"
)
OWNER_NOTIFICATION_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-12-117_extend_owner_notifications.py"
)
LANE_IDENTITY_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-13-118_conserve_runtime_lane_identity.py"
)
ACTION_TIME_INVOCATION_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-13-119_action_time_invocation_consistency.py"
)
EXIT_EXECUTION_SAFETY_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-14-121_add_exit_execution_safety.py"
)
EXIT_POLICY_CORE_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-14-122_add_ticket_exit_policy_core.py"
)
SEED_PATH = REPO_ROOT / "scripts/seed_runtime_control_state_foundation.py"


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
    migration = _load_module(MIGRATION_PATH, "migration_086_runtime_safety")
    lifecycle_migration = _load_module(
        LIFECYCLE_MIGRATION_PATH,
        "migration_091_runtime_safety",
    )
    runner_lifecycle_migration = _load_module(
        RUNNER_LIFECYCLE_MIGRATION_PATH,
        "migration_092_runtime_safety",
    )
    lifecycle_closure_migration = _load_module(
        LIFECYCLE_CLOSURE_MIGRATION_PATH,
        "migration_093_runtime_safety",
    )
    lifecycle_safety_core_migration = _load_module(
        LIFECYCLE_SAFETY_CORE_MIGRATION_PATH,
        "migration_094_runtime_safety",
    )
    runner_mutation_command_migration = _load_module(
        RUNNER_MUTATION_COMMAND_MIGRATION_PATH,
        "migration_095_runtime_safety",
    )
    seed = _load_module(SEED_PATH, "seed_runtime_safety")
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
                                protection_recovery_command_migration = _load_module(
                                    PROTECTION_RECOVERY_COMMAND_MIGRATION_PATH,
                                    "migration_096_runtime_safety",
                                )
                                old_protection_recovery_op = (
                                    protection_recovery_command_migration.op
                                )
                                protection_recovery_command_migration.op = migration.op
                                try:
                                    protection_recovery_command_migration.upgrade()
                                    orphan_cleanup_command_migration = _load_module(
                                        ORPHAN_PROTECTION_CLEANUP_COMMAND_MIGRATION_PATH,
                                        "migration_098_runtime_safety",
                                    )
                                    old_orphan_cleanup_op = (
                                        orphan_cleanup_command_migration.op
                                    )
                                    orphan_cleanup_command_migration.op = migration.op
                                    try:
                                        orphan_cleanup_command_migration.upgrade()
                                        post_submit_reconciliation_migration = _load_module(
                                            POST_SUBMIT_RECONCILIATION_TICK_MIGRATION_PATH,
                                            "migration_101_runtime_safety",
                                        )
                                        old_post_submit_reconciliation_op = (
                                            post_submit_reconciliation_migration.op
                                        )
                                        post_submit_reconciliation_migration.op = (
                                            migration.op
                                        )
                                        try:
                                            post_submit_reconciliation_migration.upgrade()
                                            live_outcome_ledger_migration = _load_module(
                                                LIVE_OUTCOME_LEDGER_MIGRATION_PATH,
                                                "migration_102_runtime_safety",
                                            )
                                            old_live_outcome_ledger_op = (
                                                live_outcome_ledger_migration.op
                                            )
                                            live_outcome_ledger_migration.op = (
                                                migration.op
                                            )
                                            try:
                                                live_outcome_ledger_migration.upgrade()
                                                risk_reservation_migration = _load_module(
                                                    RISK_RESERVATION_MIGRATION_PATH,
                                                    "migration_103_runtime_safety",
                                                )
                                                old_risk_reservation_op = (
                                                    risk_reservation_migration.op
                                                )
                                                risk_reservation_migration.op = (
                                                    migration.op
                                                )
                                                try:
                                                    risk_reservation_migration.upgrade()
                                                    execution_eligibility_migration = _load_module(
                                                        EXECUTION_ELIGIBILITY_MIGRATION_PATH,
                                                        "migration_104_runtime_safety",
                                                    )
                                                    old_eligibility_op = (
                                                        execution_eligibility_migration.op
                                                    )
                                                    execution_eligibility_migration.op = (
                                                        migration.op
                                                    )
                                                    try:
                                                        execution_eligibility_migration.upgrade()
                                                        exchange_command_migration = _load_module(
                                                            EXCHANGE_COMMAND_MIGRATION_PATH,
                                                            "migration_105_runtime_safety",
                                                        )
                                                        old_exchange_command_op = (
                                                            exchange_command_migration.op
                                                        )
                                                        exchange_command_migration.op = (
                                                            migration.op
                                                        )
                                                        try:
                                                            exchange_command_migration.upgrade()
                                                            typed_scope_migration = _load_module(
                                                                TYPED_SCOPE_MIGRATION_PATH,
                                                                "migration_113_runtime_safety",
                                                            )
                                                            old_typed_scope_op = (
                                                                typed_scope_migration.op
                                                            )
                                                            typed_scope_migration.op = (
                                                                migration.op
                                                            )
                                                            try:
                                                                typed_scope_migration.upgrade()
                                                                lifecycle_command_migration = _load_module(
                                                                    LIFECYCLE_COMMAND_MIGRATION_PATH,
                                                                    "migration_114_runtime_safety",
                                                                )
                                                                old_lifecycle_command_op = (
                                                                    lifecycle_command_migration.op
                                                                )
                                                                lifecycle_command_migration.op = (
                                                                    migration.op
                                                                )
                                                                try:
                                                                    lifecycle_command_migration.upgrade()
                                                                finally:
                                                                    lifecycle_command_migration.op = (
                                                                        old_lifecycle_command_op
                                                                    )
                                                            finally:
                                                                typed_scope_migration.op = (
                                                                    old_typed_scope_op
                                                                )
                                                        finally:
                                                            exchange_command_migration.op = (
                                                                old_exchange_command_op
                                                            )
                                                    finally:
                                                        execution_eligibility_migration.op = (
                                                            old_eligibility_op
                                                        )
                                                finally:
                                                    risk_reservation_migration.op = (
                                                        old_risk_reservation_op
                                                    )
                                            finally:
                                                live_outcome_ledger_migration.op = (
                                                    old_live_outcome_ledger_op
                                                )
                                        finally:
                                            post_submit_reconciliation_migration.op = (
                                                old_post_submit_reconciliation_op
                                            )
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
        dynamic_risk_migration = _load_module(
            DYNAMIC_RISK_MIGRATION_PATH,
            "migration_115_runtime_safety",
        )
        old_dynamic_risk_op = dynamic_risk_migration.op
        dynamic_risk_migration.op = Operations(MigrationContext.configure(conn))
        try:
            dynamic_risk_migration.upgrade()
        finally:
            dynamic_risk_migration.op = old_dynamic_risk_op
        ofc_economics_migration = _load_module(
            OFC_ECONOMICS_MIGRATION_PATH,
            "migration_116_runtime_safety",
        )
        old_ofc_economics_op = ofc_economics_migration.op
        ofc_economics_migration.op = Operations(MigrationContext.configure(conn))
        try:
            ofc_economics_migration.upgrade()
        finally:
            ofc_economics_migration.op = old_ofc_economics_op
        owner_notification_migration = _load_module(
            OWNER_NOTIFICATION_MIGRATION_PATH,
            "migration_117_runtime_safety",
        )
        old_owner_notification_op = owner_notification_migration.op
        owner_notification_migration.op = Operations(MigrationContext.configure(conn))
        try:
            owner_notification_migration.upgrade()
        finally:
            owner_notification_migration.op = old_owner_notification_op
        lane_identity_migration = _load_module(
            LANE_IDENTITY_MIGRATION_PATH,
            "migration_118_runtime_safety",
        )
        old_lane_identity_op = lane_identity_migration.op
        lane_identity_migration.op = Operations(MigrationContext.configure(conn))
        try:
            lane_identity_migration.upgrade()
        finally:
            lane_identity_migration.op = old_lane_identity_op
        action_time_invocation_migration = _load_module(
            ACTION_TIME_INVOCATION_MIGRATION_PATH,
            "migration_119_runtime_safety",
        )
        old_action_time_invocation_op = action_time_invocation_migration.op
        action_time_invocation_migration.op = Operations(
            MigrationContext.configure(conn)
        )
        try:
            action_time_invocation_migration.upgrade()
        finally:
            action_time_invocation_migration.op = old_action_time_invocation_op
        exit_execution_safety_migration = _load_module(
            EXIT_EXECUTION_SAFETY_MIGRATION_PATH,
            "migration_121_runtime_safety",
        )
        old_exit_execution_safety_op = exit_execution_safety_migration.op
        exit_execution_safety_migration.op = Operations(
            MigrationContext.configure(conn)
        )
        try:
            exit_execution_safety_migration.upgrade()
        finally:
            exit_execution_safety_migration.op = old_exit_execution_safety_op
        exit_policy_core_migration = _load_module(
            EXIT_POLICY_CORE_MIGRATION_PATH,
            "migration_122_runtime_safety",
        )
        old_exit_policy_core_op = exit_policy_core_migration.op
        exit_policy_core_migration.op = Operations(
            MigrationContext.configure(conn)
        )
        try:
            exit_policy_core_migration.upgrade()
        finally:
            exit_policy_core_migration.op = old_exit_policy_core_op
        seed.seed_runtime_control_state_foundation(conn)
        conn.execute(
            text(
                "UPDATE brc_runtime_capabilities_current "
                "SET status = 'enabled', certification_ref = 'unit-fixture:certified', "
                "updated_at_ms = :now_ms "
                "WHERE capability_id = 'ticket_lifecycle_durable_mutation'"
            ),
            {"now_ms": NOW_MS},
        )
    with engine.connect() as conn:
        yield conn
    engine.dispose()


def test_cli_requires_database_url_and_postgres_dsn(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.delenv("PG_DATABASE_URL", raising=False)
    assert safety.main(["--require-database-url", "--ticket-id", "ticket-1"]) == 2
    assert "PG_DATABASE_URL is required" in capsys.readouterr().err

    assert safety.main(["--database-url", "sqlite://"]) == 2
    assert "requires PostgreSQL DSN" in capsys.readouterr().err
    assert not (tmp_path / "runtime-safety.json").exists()


def test_runtime_safety_state_noops_without_operation_layer_handoff(
    pg_control_connection,
):
    payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert payload["status"] == "no_operation_layer_handoff"
    assert payload["submit_allowed"] is False
    assert payload["blockers"] == []
    assert payload["next_action"] == "continue_watcher_observation"
    assert payload["forbidden_effects"] == safety.FORBIDDEN_EFFECTS
    assert _runtime_safety_count(pg_control_connection) == 0


def test_runtime_safety_state_materializes_submit_allowed_snapshot(
    pg_control_connection,
):
    ids = _create_handoff_ready(pg_control_connection)

    payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_layer_handoff_id=ids["operation_layer_handoff_id"],
        now_ms=NOW_MS + 3000,
    )

    assert payload["status"] == "runtime_safety_state_ready"
    assert payload["ticket_id"] == ids["ticket_id"]
    assert payload["finalgate_pass_id"] == ids["finalgate_pass_id"]
    assert payload["operation_layer_handoff_id"] == ids["operation_layer_handoff_id"]
    assert payload["operation_submit_command_id"] == ids["operation_submit_command_id"]
    assert payload["action_time_lane_input_id"] == ids["lane_id"]
    assert payload["strategy_group_id"] == "SOR-001"
    assert payload["symbol"] == "ETHUSDT"
    assert payload["side"] == "long"
    assert payload["submit_allowed"] is True
    assert payload["blockers"] == []
    assert payload["forbidden_effects"] == safety.FORBIDDEN_EFFECTS
    row = pg_control_connection.execute(
        text(
            """
            SELECT runtime_safety_snapshot_id, action_time_lane_input_id,
                   safety_state, submit_allowed, finalgate_ready,
                   operation_layer_ready, protection_ready,
                   active_position_conflict, facts_fresh,
                   trusted_fact_refs_complete, blockers, trusted_fact_refs
            FROM brc_runtime_safety_state_snapshots
            """
        )
    ).mappings().one()
    assert row["action_time_lane_input_id"] == ids["lane_id"]
    assert row["safety_state"] == "live_submit_ready"
    assert row["submit_allowed"] in {True, 1}
    assert row["finalgate_ready"] in {True, 1}
    assert row["operation_layer_ready"] in {True, 1}
    assert row["protection_ready"] in {True, 1}
    assert row["active_position_conflict"] in {False, 0}
    assert row["facts_fresh"] in {True, 1}
    assert row["trusted_fact_refs_complete"] in {True, 1}
    assert _json_value(row["blockers"]) == []

    trusted_refs = _json_value(row["trusted_fact_refs"])
    assert trusted_refs["ticket_id"] == ids["ticket_id"]
    assert trusted_refs["signal_event_id"] == "signal:SOR-001:ETHUSDT:long:unit"
    assert trusted_refs["finalgate_pass_id"] == ids["finalgate_pass_id"]
    assert trusted_refs["operation_layer_handoff_id"] == ids["operation_layer_handoff_id"]
    assert trusted_refs["operation_submit_command_id"] == ids["operation_submit_command_id"]

    lane_snapshot_id = pg_control_connection.execute(
        text(
            """
            SELECT runtime_safety_snapshot_id
            FROM brc_action_time_lane_inputs
            WHERE action_time_lane_input_id = :lane_id
            """
        ),
        {"lane_id": ids["lane_id"]},
    ).scalar_one()
    assert lane_snapshot_id == row["runtime_safety_snapshot_id"]


def test_runtime_safety_blocks_entry_when_lifecycle_mutation_capability_disabled(
    pg_control_connection,
):
    ids = _create_handoff_ready(pg_control_connection)
    pg_control_connection.execute(
        text(
            "UPDATE brc_runtime_capabilities_current "
            "SET status = 'disabled', "
            "certification_ref = 'unit:phase-one-fail-closed' "
            "WHERE capability_id = 'ticket_lifecycle_durable_mutation'"
        )
    )

    payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_layer_handoff_id=ids["operation_layer_handoff_id"],
        now_ms=NOW_MS + 3000,
    )

    assert payload["status"] == "runtime_safety_state_blocked"
    assert payload["submit_allowed"] is False
    assert payload["lifecycle_mutation_capability_ready"] is False
    assert "lifecycle_mutation_capability_not_ready" in payload["blockers"]


def test_runtime_safety_blocks_ineligible_ticket_graph(pg_control_connection):
    ids = _create_handoff_ready(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_action_time_tickets
            SET execution_eligible = false
            WHERE ticket_id = :ticket_id
            """
        ),
        {"ticket_id": ids["ticket_id"]},
    )

    payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_layer_handoff_id=ids["operation_layer_handoff_id"],
        now_ms=NOW_MS + 3000,
    )

    assert payload["submit_allowed"] is False
    assert "execution_eligibility_missing_or_false" in payload["blockers"]


def test_runtime_safety_blocks_lane_ticket_authority_mismatch(
    pg_control_connection,
):
    ids = _create_handoff_ready(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_action_time_lane_inputs
            SET signal_grade = 'production_grade_signal',
                required_execution_mode = 'production_live'
            WHERE action_time_lane_input_id = :lane_id
            """
        ),
        {"lane_id": ids["lane_id"]},
    )

    payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_layer_handoff_id=ids["operation_layer_handoff_id"],
        now_ms=NOW_MS + 3000,
    )

    assert payload["submit_allowed"] is False
    assert "execution_eligibility_lane_ticket_mismatch:signal_grade" in payload[
        "blockers"
    ]


def test_runtime_safety_state_blocks_ticket_identity_hash_mismatch(
    pg_control_connection,
):
    ids = _create_handoff_ready(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_action_time_tickets
            SET leverage = 9
            WHERE ticket_id = :ticket_id
            """
        ),
        {"ticket_id": ids["ticket_id"]},
    )

    payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_layer_handoff_id=ids["operation_layer_handoff_id"],
        now_ms=NOW_MS + 3000,
    )

    assert payload["status"] == "runtime_safety_state_blocked"
    assert payload["submit_allowed"] is False
    assert "ticket_hash_mismatch" in payload["blockers"]
    row = _runtime_safety_row(pg_control_connection)
    assert row["safety_state"] == "blocked_safety"
    assert row["submit_allowed"] in {False, 0}


def test_runtime_safety_state_blocks_account_position_conflict(
    pg_control_connection,
):
    ids = _create_handoff_ready(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_runtime_fact_snapshots
            SET fact_values = :fact_values
            WHERE fact_snapshot_id = 'fact:SOR-001:ETHUSDT:long:account-safe:unit'
            """
        ),
        {
            "fact_values": json.dumps(
                {
                    "account_safe": True,
                    "open_orders_clear": True,
                    "active_position_or_open_order_clear": False,
                },
                sort_keys=True,
            )
        },
    )

    payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_layer_handoff_id=ids["operation_layer_handoff_id"],
        now_ms=NOW_MS + 3000,
    )

    assert payload["status"] == "runtime_safety_state_blocked"
    assert "active_position_or_open_order_conflict" in payload["blockers"]
    row = _runtime_safety_row(pg_control_connection)
    assert row["active_position_conflict"] in {True, 1}
    assert row["submit_allowed"] in {False, 0}


def test_runtime_safety_state_blocks_missing_stop_risk_reservation(
    pg_control_connection,
):
    ids = _create_handoff_ready(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_budget_reservations
            SET risk_at_stop = NULL
            WHERE ticket_id = :ticket_id
            """
        ),
        {"ticket_id": ids["ticket_id"]},
    )

    payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_layer_handoff_id=ids["operation_layer_handoff_id"],
        now_ms=NOW_MS + 3000,
    )

    assert payload["status"] == "runtime_safety_state_blocked"
    assert payload["submit_allowed"] is False
    assert "risk_at_stop_invalid" in payload["blockers"]
    row = _runtime_safety_row(pg_control_connection)
    assert row["safety_state"] == "blocked_safety"
    assert row["submit_allowed"] in {False, 0}


def test_runtime_safety_state_blocks_expired_fact_snapshot(pg_control_connection):
    ids = _create_handoff_ready(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_runtime_fact_snapshots
            SET valid_until_ms = :valid_until_ms
            WHERE fact_snapshot_id = 'fact:SOR-001:ETHUSDT:long:action-time:unit'
            """
        ),
        {"valid_until_ms": NOW_MS + 1},
    )

    payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_layer_handoff_id=ids["operation_layer_handoff_id"],
        now_ms=NOW_MS + 3000,
    )

    assert payload["status"] == "runtime_safety_state_blocked"
    assert "action_time_fact_snapshot_id_expired" in payload["blockers"]
    row = _runtime_safety_row(pg_control_connection)
    assert row["facts_fresh"] in {False, 0}
    assert row["submit_allowed"] in {False, 0}


def test_runtime_safety_state_blocks_non_live_market_signal_source(
    pg_control_connection,
):
    ids = _create_handoff_ready(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_live_signal_events
            SET source_kind = 'replay',
                status = 'stale',
                freshness_state = 'stale'
            WHERE signal_event_id = 'signal:SOR-001:ETHUSDT:long:unit'
            """
        )
    )

    payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_layer_handoff_id=ids["operation_layer_handoff_id"],
        now_ms=NOW_MS + 3000,
    )

    assert payload["status"] == "runtime_safety_state_blocked"
    assert payload["submit_allowed"] is False
    assert "signal_event_not_live_market:replay" in payload["blockers"]
    assert "signal_event_not_fresh:stale" in payload["blockers"]
    row = _runtime_safety_row(pg_control_connection)
    assert row["safety_state"] == "blocked_safety"
    assert row["submit_allowed"] in {False, 0}


def test_runtime_safety_state_blocks_generated_at_signal_time(
    pg_control_connection,
):
    ids = _create_handoff_ready(pg_control_connection)
    with pytest.raises(IntegrityError):
        pg_control_connection.execute(
            text(
                """
                UPDATE brc_live_signal_events
                SET created_at_ms = event_time_ms
                WHERE signal_event_id = 'signal:SOR-001:ETHUSDT:long:unit'
                """
            )
        )

    assert ids["ticket_id"]
    assert _runtime_safety_count(pg_control_connection) == 0


def test_runtime_safety_state_blocks_finalgate_pass_mismatch(
    pg_control_connection,
):
    ids = _create_handoff_ready(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_operation_layer_handoffs
            SET finalgate_pass_id = 'finalgate_pass:wrong'
            WHERE operation_layer_handoff_id = :handoff_id
            """
        ),
        {"handoff_id": ids["operation_layer_handoff_id"]},
    )

    payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_layer_handoff_id=ids["operation_layer_handoff_id"],
        now_ms=NOW_MS + 3000,
    )

    assert payload["status"] == "runtime_safety_state_blocked"
    assert any(
        blocker.startswith("operation_layer_handoff_finalgate_pass_mismatch:")
        for blocker in payload["blockers"]
    )
    assert _runtime_safety_row(pg_control_connection)["submit_allowed"] in {False, 0}


def test_runtime_safety_state_blocks_handoff_command_ticket_mismatch(
    pg_control_connection,
):
    ids = _create_handoff_ready(pg_control_connection)
    command_plan = _json_value(
        pg_control_connection.execute(
            text(
                """
                SELECT command_plan
                FROM brc_operation_layer_handoffs
                WHERE operation_layer_handoff_id = :handoff_id
                """
            ),
            {"handoff_id": ids["operation_layer_handoff_id"]},
        ).scalar_one()
    )
    command_plan["ticket_id"] = "ticket:wrong"
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_operation_layer_handoffs
            SET command_plan = :command_plan
            WHERE operation_layer_handoff_id = :handoff_id
            """
        ),
        {
            "handoff_id": ids["operation_layer_handoff_id"],
            "command_plan": json.dumps(command_plan, sort_keys=True),
        },
    )

    payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_layer_handoff_id=ids["operation_layer_handoff_id"],
        now_ms=NOW_MS + 3000,
    )

    assert payload["status"] == "runtime_safety_state_blocked"
    assert "operation_layer_handoff_command_ticket_mismatch" in payload["blockers"]
    assert _runtime_safety_row(pg_control_connection)["submit_allowed"] in {False, 0}


def test_runtime_safety_selector_fails_closed_on_multiple_current_handoffs():
    selected = safety._select_handoff(
        {
            "action_time_tickets": [
                {
                    "ticket_id": "ticket:current-a",
                    "status": "finalgate_ready",
                    "expires_at_ms": NOW_MS + 60_000,
                },
                {
                    "ticket_id": "ticket:current-b",
                    "status": "finalgate_ready",
                    "expires_at_ms": NOW_MS + 60_000,
                },
            ],
            "operation_layer_handoffs": [
                {
                    "operation_layer_handoff_id": "handoff:current-a",
                    "ticket_id": "ticket:current-a",
                    "operation_submit_command_id": "operation-submit:current-a",
                    "status": "handoff_ready",
                },
                {
                    "operation_layer_handoff_id": "handoff:current-b",
                    "ticket_id": "ticket:current-b",
                    "operation_submit_command_id": "operation-submit:current-b",
                    "status": "handoff_ready",
                },
            ],
        },
        ticket_id="",
        operation_layer_handoff_id="",
        now_ms=NOW_MS,
    )

    assert selected["handoff"] == {}
    assert selected["blockers"] == ["multiple_ready_operation_layer_handoffs"]


def test_runtime_safety_selector_ignores_handoffs_without_current_ticket():
    selected = safety._select_handoff(
        {
            "action_time_tickets": [
                {
                    "ticket_id": "ticket:expired",
                    "status": "finalgate_ready",
                    "expires_at_ms": NOW_MS - 1,
                },
                {
                    "ticket_id": "ticket:current",
                    "status": "finalgate_ready",
                    "expires_at_ms": NOW_MS + 60_000,
                },
                {
                    "ticket_id": "ticket:closed",
                    "status": "expired",
                    "expires_at_ms": NOW_MS + 60_000,
                },
            ],
            "operation_layer_handoffs": [
                {
                    "operation_layer_handoff_id": "handoff:expired",
                    "ticket_id": "ticket:expired",
                    "operation_submit_command_id": "operation-submit:expired",
                    "status": "handoff_ready",
                },
                {
                    "operation_layer_handoff_id": "handoff:current",
                    "ticket_id": "ticket:current",
                    "operation_submit_command_id": "operation-submit:current",
                    "status": "handoff_ready",
                },
                {
                    "operation_layer_handoff_id": "handoff:closed",
                    "ticket_id": "ticket:closed",
                    "operation_submit_command_id": "operation-submit:closed",
                    "status": "handoff_ready",
                },
            ],
        },
        ticket_id="",
        operation_layer_handoff_id="",
        now_ms=NOW_MS,
    )

    assert selected["blockers"] == []
    assert selected["handoff"]["operation_layer_handoff_id"] == "handoff:current"


def _create_handoff_ready(
    conn,
    *,
    fact_values: dict | None = None,
) -> dict[str, str]:
    lane_id = _insert_action_time_lane_graph(conn, fact_values=fact_values)
    ticket_payload = ticket_materializer.materialize_action_time_ticket(
        conn,
        now_ms=NOW_MS,
    )
    assert ticket_payload["status"] == "action_time_ticket_created"
    ticket_id = str(ticket_payload["ticket_id"])
    finalgate_payload = finalgate.materialize_action_time_finalgate_preflight(
        conn,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 1000,
    )
    assert finalgate_payload["status"] == "finalgate_ready", finalgate_payload
    finalgate_pass_id = str(finalgate_payload["finalgate_pass_id"])
    handoff_payload = handoff.materialize_action_time_operation_layer_handoff(
        conn,
        ticket_id=ticket_id,
        finalgate_pass_id=finalgate_pass_id,
        now_ms=NOW_MS + 2000,
    )
    assert handoff_payload["status"] == "operation_layer_handoff_ready"
    return {
        "lane_id": lane_id,
        "ticket_id": ticket_id,
        "finalgate_pass_id": finalgate_pass_id,
        "operation_layer_handoff_id": str(handoff_payload["operation_layer_handoff_id"]),
        "operation_submit_command_id": str(handoff_payload["operation_submit_command_id"]),
    }


def _runtime_safety_count(conn) -> int:
    return conn.execute(
        text("SELECT COUNT(*) FROM brc_runtime_safety_state_snapshots")
    ).scalar_one()


def _runtime_safety_row(conn):
    return conn.execute(
        text("SELECT * FROM brc_runtime_safety_state_snapshots")
    ).mappings().one()


def _json_value(value):
    if isinstance(value, str):
        return json.loads(value)
    return value
