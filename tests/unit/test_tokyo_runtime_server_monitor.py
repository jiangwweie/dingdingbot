from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from scripts import materialize_ticket_bound_protected_submit_attempt as submit
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_protected_submit_attempt import (
    _create_ready_protected_submit,
    _prepare_real_submit,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_tokyo_runtime_server_monitor.py"
MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py"
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
SEED_PATH = REPO_ROOT / "scripts/seed_runtime_control_state_foundation.py"
PG_TEST_NOW_MS = 1770001000000


def test_recent_dispatching_exchange_command_is_processing_quiet():
    module = _load_module()
    control_state = {
        "read_now_ms": PG_TEST_NOW_MS,
        "ticket_bound_exchange_commands": [
            {
                "exchange_command_id": "command-1",
                "command_state": "dispatching",
                "strategy_group_id": "SOR-001",
                "symbol": "ETHUSDT",
                "side": "long",
                "updated_at_ms": PG_TEST_NOW_MS - 1_000,
            }
        ],
        "action_time_tickets": [],
        "ticket_bound_protected_submit_attempts": [],
    }

    decision = module._decision_from_pg_sources(
        control_state=control_state,
        goal_status={"status": "fresh_signal_processing", "checks": {}},
        candidate_pool={},
        systemd={"ready": True, "blockers": []},
    )

    assert decision["status"] == "processing"
    assert decision["notify"] is False
    assert decision["checkpoint"] == "ticket_bound_exchange_command"


def test_overdue_unknown_exchange_command_notifies_owner():
    module = _load_module()
    control_state = {
        "read_now_ms": PG_TEST_NOW_MS,
        "ticket_bound_exchange_commands": [
            {
                "exchange_command_id": "command-unknown",
                "command_state": "outcome_unknown",
                "strategy_group_id": "SOR-001",
                "symbol": "ETHUSDT",
                "side": "long",
                "updated_at_ms": PG_TEST_NOW_MS - 120_000,
            }
        ],
        "action_time_tickets": [],
        "ticket_bound_protected_submit_attempts": [],
    }

    decision = module._decision_from_pg_sources(
        control_state=control_state,
        goal_status={"status": "fresh_signal_processing", "checks": {}},
        candidate_pool={},
        systemd={"ready": True, "blockers": []},
    )

    assert decision["status"] == "needs_intervention"
    assert decision["notify"] is True
    assert decision["blocker_class"] == "exchange_command_outcome_unknown"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "run_tokyo_runtime_server_monitor",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_file_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _pg_args(module, tmp_path: Path):
    return module._parse_args(
        [
            "--skip-systemd",
            "--feishu-webhook-url",
            "https://example.invalid/webhook",
            "--database-url",
            "sqlite://",
            "--allow-non-postgres-for-test",
            "--now-ms",
            str(PG_TEST_NOW_MS),
        ]
    )


def _seed_pg_engine():
    migration = _load_file_module(MIGRATION_PATH, "migration_086_server_monitor")
    risk_reservation_migration = _load_file_module(
        RISK_RESERVATION_MIGRATION_PATH,
        "migration_103_server_monitor",
    )
    seed = _load_file_module(SEED_PATH, "seed_runtime_control_state_server_monitor")
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
            old_risk_op = risk_reservation_migration.op
            risk_reservation_migration.op = migration.op
            try:
                risk_reservation_migration.upgrade()
                execution_eligibility_migration = _load_file_module(
                    EXECUTION_ELIGIBILITY_MIGRATION_PATH,
                    "migration_104_server_monitor",
                )
                old_eligibility_op = execution_eligibility_migration.op
                execution_eligibility_migration.op = migration.op
                try:
                    execution_eligibility_migration.upgrade()
                    exchange_command_migration = _load_file_module(
                        EXCHANGE_COMMAND_MIGRATION_PATH,
                        "migration_105_server_monitor",
                    )
                    old_exchange_command_op = exchange_command_migration.op
                    exchange_command_migration.op = migration.op
                    try:
                        exchange_command_migration.upgrade()
                    finally:
                        exchange_command_migration.op = old_exchange_command_op
                finally:
                    execution_eligibility_migration.op = old_eligibility_op
            finally:
                risk_reservation_migration.op = old_risk_op
        finally:
            migration.op = old_op
        seed.seed_runtime_control_state_foundation(conn)
    return engine


def _insert_pg_coverage_and_unsatisfied_facts(conn) -> None:
    rows = conn.execute(
        text(
            """
            SELECT runtime_scope_binding_id, strategy_group_id, symbol, side, runtime_profile_id
            FROM brc_runtime_scope_bindings
            WHERE status = 'active'
            ORDER BY runtime_scope_binding_id
            """
        )
    ).mappings()
    for index, row in enumerate(rows, start=1):
        lane_key = f"{row['strategy_group_id']}:{row['symbol']}:{row['side']}"
        observed_at_ms = 1770000000000 + index
        conn.execute(
            text(
                """
                INSERT INTO brc_watcher_runtime_coverage (
                  runtime_coverage_id,
                  strategy_group_id,
                  symbol,
                  side,
                  detector_key,
                  runtime_profile_id,
                  coverage_state,
                  liveness_state,
                  last_tick_at_ms,
                  valid_until_ms,
                  is_current,
                  created_at_ms
                ) VALUES (
                  :runtime_coverage_id,
                  :strategy_group_id,
                  :symbol,
                  :side,
                  :detector_key,
                  :runtime_profile_id,
                  'covered',
                  'healthy',
                  :observed_at_ms,
                  :valid_until_ms,
                  true,
                  :observed_at_ms
                )
                """
            ),
            {
                "runtime_coverage_id": f"coverage:{lane_key}",
                "strategy_group_id": row["strategy_group_id"],
                "symbol": row["symbol"],
                "side": row["side"],
                "detector_key": f"detector:{row['strategy_group_id']}:{row['side']}",
                "runtime_profile_id": row["runtime_profile_id"],
                "observed_at_ms": observed_at_ms,
                "valid_until_ms": observed_at_ms + 3_600_000,
            },
        )
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
                  :runtime_profile_id,
                  'pretrade_public',
                  'watcher',
                  :source_ref,
                  true,
                  false,
                  'fresh',
                  :failed_facts,
                  :fact_values,
                  'computed_not_satisfied',
                  :observed_at_ms,
                  :valid_until_ms,
                  :observed_at_ms
                )
                """
            ),
            {
                "fact_snapshot_id": f"fact:{lane_key}:public",
                "strategy_group_id": row["strategy_group_id"],
                "symbol": row["symbol"],
                "side": row["side"],
                "runtime_profile_id": row["runtime_profile_id"],
                "source_ref": f"pg_test:{lane_key}",
                "failed_facts": json.dumps(["market_condition_not_satisfied"]),
                "fact_values": json.dumps({"market_condition_not_satisfied": False}),
                "observed_at_ms": observed_at_ms,
                "valid_until_ms": observed_at_ms + 3_600_000,
            },
        )


def _insert_pg_action_time_lane_without_ticket(conn) -> str:
    row = conn.execute(
        text(
            """
            SELECT runtime_scope_binding_id, strategy_group_id, symbol, side, runtime_profile_id
            FROM brc_runtime_scope_bindings
            WHERE status = 'active'
              AND strategy_group_id = 'SOR-001'
              AND symbol = 'ETHUSDT'
              AND side = 'long'
            LIMIT 1
            """
        )
    ).mappings().one()
    lane_id = "lane:SOR-001:ETHUSDT:long:ticket-pending"
    conn.execute(
        text(
            """
            INSERT INTO brc_action_time_lane_inputs (
              action_time_lane_input_id,
              promotion_candidate_id,
              strategy_group_id,
              symbol,
              side,
              runtime_profile_id,
              lane_scope,
              status,
              signal_event_id,
              public_fact_snapshot_id,
              action_time_fact_snapshot_id,
              runtime_scope_binding_id,
              candidate_authorization_ref,
              runtime_safety_snapshot_id,
              first_blocker_class,
              created_at_ms,
              expires_at_ms,
              closed_at_ms,
              authority_boundary
            ) VALUES (
              :lane_id,
              'promotion:SOR-001:ETHUSDT:long',
              :strategy_group_id,
              :symbol,
              :side,
              :runtime_profile_id,
              'real_submit_candidate',
              'ticket_pending',
              'signal:SOR-001:ETHUSDT:long',
              'fact:SOR-001:ETHUSDT:long:public',
              'fact:SOR-001:ETHUSDT:long:action-time',
              :runtime_scope_binding_id,
              'candidate_auth:SOR-001:ETHUSDT:long',
              NULL,
              'action_time_preflight_ready',
              1770001000000,
              1770001900000,
              NULL,
              'non_executing_action_time_lane; no_finalgate_no_operation_layer_no_exchange_write'
            )
            """
        ),
        {
            "lane_id": lane_id,
            "strategy_group_id": row["strategy_group_id"],
            "symbol": row["symbol"],
            "side": row["side"],
            "runtime_profile_id": row["runtime_profile_id"],
            "runtime_scope_binding_id": row["runtime_scope_binding_id"],
        },
    )
    return lane_id


def _insert_pg_stale_action_time_readiness_without_current_signal(conn) -> None:
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
              'fact:SOR-001:ETHUSDT:long:public:stale-action-time-boundary',
              'SOR-001',
              'ETHUSDT',
              'long',
              'owner-runtime-console-v1',
              'pretrade_public',
              'watcher',
              'pg_test:stale-action-time-boundary',
              true,
              true,
              'fresh',
              '[]',
              '{"market_condition_satisfied": true}',
              NULL,
              1770000999000,
              1770004600000,
              1770000999000
            )
            """
        )
    )
    conn.execute(
        text(
            """
            INSERT INTO brc_pretrade_readiness_rows (
              readiness_row_id,
              candidate_scope_id,
              strategy_group_id,
              symbol,
              side,
              readiness_state,
              detector_state,
              watcher_state,
              public_facts_state,
              signal_lifecycle_status,
              signal_freshness_state,
              risk_state,
              scope_state,
              promotion_state,
              first_blocker_class,
              first_blocker_detail,
              next_action,
              stop_condition,
              evidence_ref,
              source_watermark,
              computed_at_ms,
              valid_until_ms
            ) VALUES (
              'readiness:SOR-001:ETHUSDT:long:stale-action-time-boundary',
              'candidate_scope:SOR-001:ETHUSDT:long:SOR-LONG',
              'SOR-001',
              'ETHUSDT',
              'long',
              'ready',
              'attached',
              'healthy',
              'satisfied',
              'none',
              'absent',
              'acceptable',
              'live_submit_allowed',
              'idle',
              'action_time_boundary_not_reproduced',
              'previous action-time diagnostic survived after the signal expired',
              'repair_non_executing_action_time_rehearsal_path',
              'fresh_signal_required_before_action_time_boundary',
              'pg_test:stale-action-time-boundary',
              'unit',
              1770000999000,
              1770004600000
            )
            """
        )
    )


@pytest.mark.parametrize(
    "flag,value",
    [
        ("--dedupe-state-json", "dedupe.json"),
        ("--daily-table-json", "daily.json"),
        ("--candidate-pool-json", "candidate-pool.json"),
        ("--public-facts-json", "public-facts.json"),
        ("--account-safe-facts-json", "account-facts.json"),
        ("--watcher-status-json", "watcher-status.json"),
        ("--deploy-health-json", "deploy-health.json"),
        ("--allow-local-file-diagnostic", None),
    ],
)
def test_legacy_json_monitor_arguments_are_rejected(
    tmp_path: Path,
    flag: str,
    value: str | None,
) -> None:
    module = _load_module()
    argv = [flag]
    if value is not None:
        argv.append(str(tmp_path / value))

    with pytest.raises(SystemExit) as exc:
        module._parse_args(argv)

    assert exc.value.code == 2


def test_default_server_monitor_requires_pg_without_file_fallback(
    tmp_path: Path,
) -> None:
    module = _load_module()
    args = module._parse_args(
        [
            "--skip-systemd",
        ]
    )
    args.database_url = ""

    with pytest.raises(ValueError, match="PG_DATABASE_URL is required"):
        module.build_server_monitor_artifact(args)


def test_non_postgres_dsn_is_rejected_outside_test_mode(tmp_path: Path) -> None:
    module = _load_module()
    args = module._parse_args(
        [
            "--skip-systemd",
            "--database-url",
            "sqlite://",
        ]
    )

    with pytest.raises(ValueError, match="requires PostgreSQL DSN"):
        module.build_server_monitor_artifact(args)


def test_server_monitor_normalizes_asyncpg_dsn_for_sync_engine(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = _load_module()
    args = module._parse_args(
        [
            "--skip-systemd",
            "--database-url",
            "postgresql+asyncpg://user:pass@localhost:5432/brc",
        ]
    )
    seen_urls: list[str] = []

    class FakeBegin:
        def __enter__(self):
            return object()

        def __exit__(self, *_exc):
            return False

    class FakeEngine:
        def begin(self):
            return FakeBegin()

        def dispose(self):
            pass

    def fake_create_engine(database_url: str):
        seen_urls.append(database_url)
        return FakeEngine()

    monkeypatch.setattr(module.sa, "create_engine", fake_create_engine)
    monkeypatch.setattr(
        module,
        "build_server_monitor_artifact_from_pg",
        lambda *_args, **_kwargs: {"status": "ok"},
    )

    assert module.build_server_monitor_artifact(args) == {"status": "ok"}
    assert seen_urls == ["postgresql+psycopg://user:pass@localhost:5432/brc"]


def test_pg_healthy_waiting_is_quiet_and_uses_pg_dedupe(
    tmp_path: Path,
) -> None:
    module = _load_module()
    engine = _seed_pg_engine()
    try:
        with engine.begin() as conn:
            _insert_pg_coverage_and_unsatisfied_facts(conn)
            calls: list[dict] = []

            artifact = module.build_server_monitor_artifact(
                _pg_args(module, tmp_path),
                pg_conn=conn,
                notifier=lambda *args: calls.append({"args": args}) or {"sent": True},
            )

            assert artifact["source_mode"] == "db_backed"
            assert artifact["status"] == "healthy_waiting_quiet"
            assert artifact["decision"]["decision"] == "quiet"
            assert artifact["notification"]["attempted"] is False
            assert artifact["notification"]["skipped_reason"] == "healthy_waiting_quiet"
            assert artifact["source_paths"] == {}
            assert artifact["source_errors"] == {}
            assert artifact["dedupe_state"]["source"] == "pg:brc_server_monitor_notifications"
            assert not (tmp_path / "server-monitor-dedupe-state.json").exists()
            assert not (tmp_path / "monitor.json").exists()
            assert calls == []
            assert artifact["safety_invariants"]["calls_finalgate"] is False
            assert artifact["safety_invariants"]["calls_operation_layer"] is False
            assert artifact["safety_invariants"]["calls_exchange_write"] is False
            assert artifact["safety_invariants"]["places_order"] is False
            assert artifact["safety_invariants"]["order_created"] is False
            assert artifact["safety_invariants"]["live_profile_changed"] is False
            assert artifact["safety_invariants"]["order_sizing_changed"] is False
            assert conn.execute(
                text("SELECT COUNT(*) FROM brc_server_monitor_runs")
            ).scalar_one() == 1
            assert conn.execute(
                text("SELECT COUNT(*) FROM brc_server_monitor_notifications")
            ).scalar_one() == 0
    finally:
        engine.dispose()


def test_pg_stale_action_time_boundary_without_current_signal_is_quiet(
    tmp_path: Path,
) -> None:
    module = _load_module()
    engine = _seed_pg_engine()
    try:
        with engine.begin() as conn:
            _insert_pg_coverage_and_unsatisfied_facts(conn)
            _insert_pg_stale_action_time_readiness_without_current_signal(conn)
            calls: list[dict] = []

            artifact = module.build_server_monitor_artifact(
                _pg_args(module, tmp_path),
                pg_conn=conn,
                notifier=lambda *args: calls.append({"args": args}) or {"sent": True},
            )

            assert artifact["source_mode"] == "db_backed"
            assert artifact["status"] == "healthy_waiting_quiet"
            assert artifact["decision"]["decision"] == "quiet"
            assert artifact["decision"]["blocker_class"] == "none"
            assert artifact["decision"]["reasons"] == []
            assert artifact["notification"]["attempted"] is False
            assert artifact["notification"]["skipped_reason"] == "healthy_waiting_quiet"
            assert calls == []
            assert conn.execute(
                text("SELECT COUNT(*) FROM brc_server_monitor_notifications")
            ).scalar_one() == 0
    finally:
        engine.dispose()


def test_pg_completed_disabled_smoke_attempt_is_quiet_not_boundary_blocked(
    tmp_path: Path,
) -> None:
    module = _load_module()
    engine = _seed_pg_engine()
    try:
        with engine.begin() as conn:
            ids = _create_ready_protected_submit(conn)
            prepared = submit.prepare_ticket_bound_protected_submit_attempt(
                conn,
                ticket_id=ids["ticket_id"],
                operation_submit_command_id=ids["operation_submit_command_id"],
                submit_mode="disabled_smoke",
                now_ms=NOW_MS + 4000,
            )
            args = _pg_args(module, tmp_path)
            args.now_ms = NOW_MS + 120_000
            calls: list[dict] = []

            artifact = module.build_server_monitor_artifact(
                args,
                pg_conn=conn,
                notifier=lambda *args: calls.append({"args": args}) or {"sent": True},
            )

            assert artifact["source_mode"] == "db_backed"
            assert artifact["decision"]["decision"] == "quiet"
            assert artifact["decision"]["status"] == (
                "protected_submit_rehearsal_completed_quiet"
            )
            assert artifact["decision"]["blocker_class"] == "none"
            assert artifact["decision"]["checkpoint"] == "ticket_bound_protected_submit"
            assert artifact["notification"]["attempted"] is False
            assert artifact["notification"]["skipped_reason"] == (
                "protected_submit_rehearsal_completed_quiet"
            )
            assert calls == []
            assert prepared["status"] == "disabled_smoke_passed"
            assert artifact["source_refs"]["control_state_watermark"]["table_counts"][
                "ticket_bound_protected_submit_attempts"
            ] == 1
    finally:
        engine.dispose()


def test_pg_overdue_unknown_exchange_command_notifies_from_current_table(
    tmp_path: Path,
) -> None:
    module = _load_module()
    engine = _seed_pg_engine()
    try:
        with engine.begin() as conn:
            ids = _create_ready_protected_submit(conn)
            prepared = _prepare_real_submit(conn, ids)
            conn.execute(
                text(
                    """
                    UPDATE brc_ticket_bound_exchange_commands
                    SET command_state = 'outcome_unknown',
                        outcome_class = 'network_ambiguous',
                        updated_at_ms = :updated_at_ms
                    WHERE order_role = 'ENTRY'
                    """
                ),
                {"updated_at_ms": NOW_MS + 5000},
            )
            args = _pg_args(module, tmp_path)
            args.now_ms = NOW_MS + 120_000
            calls: list[dict] = []

            artifact = module.build_server_monitor_artifact(
                args,
                pg_conn=conn,
                notifier=lambda *args: calls.append({"args": args}) or {"sent": True},
            )

            assert prepared["status"] == "submit_prepared"
            assert artifact["decision"]["status"] == "needs_intervention"
            assert artifact["decision"]["blocker_class"] == (
                "exchange_command_outcome_unknown"
            )
            assert artifact["decision"]["checkpoint"] == (
                "ticket_bound_exchange_command"
            )
            assert artifact["notification"]["attempted"] is True
            assert artifact["source_refs"]["control_state_watermark"][
                "table_counts"
            ]["ticket_bound_exchange_commands"] == 1
            assert calls
    finally:
        engine.dispose()


def test_pg_blocked_protected_submit_attempt_notifies_owner(
    tmp_path: Path,
) -> None:
    module = _load_module()
    engine = _seed_pg_engine()
    try:
        with engine.begin() as conn:
            ids = _create_ready_protected_submit(conn)
            conn.execute(
                text(
                    """
                    UPDATE brc_runtime_fact_snapshots
                    SET fact_values = :fact_values
                    WHERE fact_surface = 'action_time'
                      AND fact_snapshot_id IN (
                        SELECT action_time_fact_snapshot_id
                        FROM brc_action_time_tickets
                        WHERE ticket_id = :ticket_id
                      )
                    """
                ),
                {
                    "ticket_id": ids["ticket_id"],
                    "fact_values": json.dumps(
                        {
                            "opening_range_defined": True,
                            "breakout_confirmed": True,
                            "opening_range_low_reference": "1800",
                            "last_price": "2000",
                        }
                    ),
                },
            )
            prepared = submit.prepare_ticket_bound_protected_submit_attempt(
                conn,
                ticket_id=ids["ticket_id"],
                operation_submit_command_id=ids["operation_submit_command_id"],
                submit_mode="disabled_smoke",
                now_ms=NOW_MS + 4000,
            )
            calls: list[dict] = []

            artifact = module.build_server_monitor_artifact(
                _pg_args(module, tmp_path),
                pg_conn=conn,
                notifier=lambda *args: calls.append({"args": args}) or {"sent": True},
            )

            assert prepared["status"] == "blocked"
            assert "tp1_reference_missing" in prepared["blockers"]
            assert artifact["source_mode"] == "db_backed"
            assert artifact["decision"]["decision"] == "notify"
            assert artifact["decision"]["blocker_class"] == "tp1_reference_missing"
            assert artifact["decision"]["checkpoint"] == (
                "ticket_bound_protected_submit_attempt"
            )
            assert artifact["decision"]["strategy_group_id"] == "SOR-001"
            assert artifact["decision"]["symbol"] == "ETHUSDT:long"
            assert artifact["notification"]["attempted"] is True
            assert calls
    finally:
        engine.dispose()


def test_pg_expired_blocked_attempt_is_quiet_and_resolves_historical_notification(
    tmp_path: Path,
) -> None:
    module = _load_module()
    engine = _seed_pg_engine()
    try:
        with engine.begin() as conn:
            ids = _create_ready_protected_submit(conn)
            conn.execute(
                text(
                    """
                    UPDATE brc_runtime_fact_snapshots
                    SET fact_values = :fact_values
                    WHERE fact_surface = 'action_time'
                      AND fact_snapshot_id IN (
                        SELECT action_time_fact_snapshot_id
                        FROM brc_action_time_tickets
                        WHERE ticket_id = :ticket_id
                      )
                    """
                ),
                {
                    "ticket_id": ids["ticket_id"],
                    "fact_values": json.dumps(
                        {
                            "opening_range_defined": True,
                            "breakout_confirmed": True,
                            "opening_range_low_reference": "1800",
                            "last_price": "2000",
                        }
                    ),
                },
            )
            prepared = submit.prepare_ticket_bound_protected_submit_attempt(
                conn,
                ticket_id=ids["ticket_id"],
                operation_submit_command_id=ids["operation_submit_command_id"],
                submit_mode="disabled_smoke",
                now_ms=NOW_MS + 4000,
            )
            assert prepared["status"] == "blocked"
            assert "tp1_reference_missing" in prepared["blockers"]

            conn.execute(
                text(
                    """
                    UPDATE brc_action_time_tickets
                    SET status = 'expired', expires_at_ms = :expired_at
                    WHERE ticket_id = :ticket_id
                    """
                ),
                {"ticket_id": ids["ticket_id"], "expired_at": NOW_MS + 5000},
            )
            conn.execute(
                text(
                    """
                    UPDATE brc_action_time_lane_inputs
                    SET status = 'expired', closed_at_ms = :closed_at
                    WHERE action_time_lane_input_id = :lane_id
                    """
                ),
                {"lane_id": ids["lane_id"], "closed_at": NOW_MS + 5000},
            )
            conn.execute(
                text(
                    """
                    UPDATE brc_promotion_candidates
                    SET status = 'expired', closed_at_ms = :closed_at
                    WHERE promotion_candidate_id = (
                      SELECT promotion_candidate_id
                      FROM brc_action_time_tickets
                      WHERE ticket_id = :ticket_id
                    )
                    """
                ),
                {"ticket_id": ids["ticket_id"], "closed_at": NOW_MS + 5000},
            )
            conn.execute(
                text(
                    """
                    UPDATE brc_live_signal_events
                    SET status = 'stale',
                        freshness_state = 'expired',
                        invalidated_at_ms = :closed_at
                    WHERE signal_event_id = (
                      SELECT signal_event_id
                      FROM brc_action_time_tickets
                      WHERE ticket_id = :ticket_id
                    )
                    """
                ),
                {"ticket_id": ids["ticket_id"], "closed_at": NOW_MS + 5000},
            )
            _insert_pg_coverage_and_unsatisfied_facts(conn)
            conn.execute(
                text(
                    """
                    INSERT INTO brc_server_monitor_notifications (
                      notification_id, dedupe_key, automation_id,
                      strategy_group_id, symbol, blocker_class, checkpoint,
                      notification_state, first_seen_at_ms, last_notified_at_ms,
                      last_seen_at_ms, send_attempts, last_error,
                      feishu_response, created_at_ms, updated_at_ms
                    ) VALUES (
                      'server_monitor_notification:historical-tp1',
                      'tokyo-runtime-server-monitor|SOR-001|ETHUSDT:long|tp1_reference_missing|ticket_bound_protected_submit_attempt',
                      'tokyo-runtime-server-monitor',
                      'SOR-001',
                      'ETHUSDT:long',
                      'tp1_reference_missing',
                      'ticket_bound_protected_submit_attempt',
                      'sent',
                      :seen_at,
                      :seen_at,
                      :seen_at,
                      1,
                      NULL,
                      '{}',
                      :seen_at,
                      :seen_at
                    )
                    """
                ),
                {"seen_at": NOW_MS + 4500},
            )

            args = _pg_args(module, tmp_path)
            args.now_ms = NOW_MS + 120_000
            calls: list[dict] = []
            artifact = module.build_server_monitor_artifact(
                args,
                pg_conn=conn,
                notifier=lambda *args: calls.append({"args": args}) or {"sent": True},
            )

            assert artifact["decision"]["decision"] == "quiet"
            assert artifact["decision"]["blocker_class"] == "none"
            assert artifact["notification"]["attempted"] is False
            assert artifact["notification"]["resolved_historical_notification_count"] == 1
            assert calls == []
            row = conn.execute(
                text(
                    """
                    SELECT notification_state, feishu_response
                    FROM brc_server_monitor_notifications
                    WHERE notification_id = 'server_monitor_notification:historical-tp1'
                    """
                )
            ).mappings().one()
            assert row["notification_state"] == "resolved"
            response = row["feishu_response"]
            if isinstance(response, str):
                response = json.loads(response)
            assert response["resolved"] is True
            assert response["resolution_reason"] == artifact["decision"]["status"]
    finally:
        engine.dispose()


def test_pg_runtime_coverage_gap_notifies_without_json_sources(
    tmp_path: Path,
) -> None:
    module = _load_module()
    engine = _seed_pg_engine()
    try:
        with engine.begin() as conn:
            artifact = module.build_server_monitor_artifact(
                _pg_args(module, tmp_path),
                pg_conn=conn,
                notifier=lambda *args: {"sent": True, "status_code": 200},
            )

            assert artifact["source_mode"] == "db_backed"
            assert artifact["decision"]["decision"] == "notify"
            assert artifact["decision"]["blocker_class"] in {
                "detector_not_attached",
                "runtime_data_gap",
            }
            assert "candidate_pool_blocker:detector_not_attached" in ",".join(
                artifact["decision"]["reasons"]
            )
            assert artifact["source_paths"] == {}
            assert artifact["source_errors"] == {}
            assert artifact["safety_invariants"]["calls_exchange_write"] is False
    finally:
        engine.dispose()


def test_pg_action_time_lane_notifies_once_with_pg_dedupe(
    tmp_path: Path,
) -> None:
    module = _load_module()
    engine = _seed_pg_engine()
    try:
        with engine.begin() as conn:
            _insert_pg_coverage_and_unsatisfied_facts(conn)
            _insert_pg_action_time_lane_without_ticket(conn)
            calls: list[dict] = []

            def notifier(*args):
                calls.append({"args": args})
                return {"sent": True, "status_code": 200}

            first = module.build_server_monitor_artifact(
                _pg_args(module, tmp_path),
                pg_conn=conn,
                notifier=notifier,
            )
            second = module.build_server_monitor_artifact(
                _pg_args(module, tmp_path),
                pg_conn=conn,
                notifier=notifier,
            )

            assert first["decision"]["decision"] == "notify"
            assert first["decision"]["strategy_group_id"] == "runtime"
            assert first["decision"]["symbol"] == "all"
            assert first["decision"]["blocker_class"] == "runtime_data_gap"
            assert first["decision"]["checkpoint"] == "pg_current_state_repository"
            assert "pg_current_state_repository" in first["source_errors"]
            assert first["notification"]["attempted"] is True
            assert first["notification"]["sent"] is True
            assert calls[0]["args"][2]["text"].startswith(
                "BRC 生产监控：系统运行数据异常"
            )
            assert not calls[0]["args"][2]["text"].startswith("BRC 生产监控：需要介入")
            assert second["notification"]["duplicate_suppressed"] is True
            assert second["notification"]["attempted"] is False
            assert len(calls) == 1
            assert conn.execute(
                text("SELECT COUNT(*) FROM brc_server_monitor_notifications")
            ).scalar_one() == 1
            assert conn.execute(
                text("SELECT COUNT(*) FROM brc_server_monitor_runs")
            ).scalar_one() == 2
            assert second["safety_invariants"]["notification_state_is_trading_authority"] is False
    finally:
        engine.dispose()


def test_pg_feishu_failure_retries_from_pg_notification_state(
    tmp_path: Path,
) -> None:
    module = _load_module()
    engine = _seed_pg_engine()
    try:
        with engine.begin() as conn:
            _insert_pg_coverage_and_unsatisfied_facts(conn)
            _insert_pg_action_time_lane_without_ticket(conn)
            calls: list[str] = []

            def notifier(*args):
                calls.append("called")
                if len(calls) == 1:
                    return {"sent": False, "status_code": 500, "error": "boom"}
                return {"sent": True, "status_code": 200}

            first = module.build_server_monitor_artifact(
                _pg_args(module, tmp_path),
                pg_conn=conn,
                notifier=notifier,
            )
            second = module.build_server_monitor_artifact(
                _pg_args(module, tmp_path),
                pg_conn=conn,
                notifier=notifier,
            )

            assert first["notification"]["attempted"] is True
            assert first["notification"]["sent"] is False
            assert first["decision"]["blocker_class"] == "runtime_data_gap"
            assert first["decision"]["checkpoint"] == "pg_current_state_repository"
            assert "pg_current_state_repository" in first["source_errors"]
            assert second["notification"]["retry_pending"] is True
            assert second["notification"]["attempted"] is True
            assert second["notification"]["sent"] is True
            assert len(calls) == 2
            row = conn.execute(
                text(
                    """
                    SELECT notification_state, send_attempts
                    FROM brc_server_monitor_notifications
                    LIMIT 1
                    """
                )
            ).mappings().one()
            assert row["notification_state"] == "sent"
            assert row["send_attempts"] == 2
            assert second["safety_invariants"]["notification_state_is_trading_authority"] is False
            assert second["safety_invariants"]["places_order"] is False
            assert second["safety_invariants"]["live_profile_changed"] is False
    finally:
        engine.dispose()


def test_pg_systemd_failure_notifies_without_trading_effects(
    tmp_path: Path,
) -> None:
    module = _load_module()
    engine = _seed_pg_engine()
    try:
        with engine.begin() as conn:
            _insert_pg_coverage_and_unsatisfied_facts(conn)
            args = _pg_args(module, tmp_path)
            args.skip_systemd = False
            args.systemd_unit = ["brc-runtime-signal-watcher.service"]

            def runner(unit: str):
                assert unit == "brc-runtime-signal-watcher.service"
                return module.CommandResult(stdout="failed", stderr="", returncode=3)

            artifact = module.build_server_monitor_artifact(
                args,
                pg_conn=conn,
                systemd_runner=runner,
                notifier=lambda *args: {"sent": True, "status_code": 200},
            )

            assert artifact["decision"]["decision"] == "notify"
            assert artifact["decision"]["blocker_class"] == "watcher_or_service_failure"
            assert artifact["decision"]["checkpoint"] == "systemd"
            assert artifact["systemd"]["ready"] is False
            assert artifact["notification"]["sent"] is True
            assert artifact["safety_invariants"]["calls_finalgate"] is False
            assert artifact["safety_invariants"]["calls_operation_layer"] is False
            assert artifact["safety_invariants"]["calls_exchange_write"] is False
            assert artifact["safety_invariants"]["places_order"] is False
    finally:
        engine.dispose()


@pytest.mark.parametrize("stdout,returncode,field", [("inactive", 3, "inactive_success"), ("activating", 0, "transient_active")])
def test_pg_watcher_oneshot_states_do_not_notify_as_systemd_failure(
    tmp_path: Path,
    stdout: str,
    returncode: int,
    field: str,
) -> None:
    module = _load_module()
    engine = _seed_pg_engine()
    try:
        with engine.begin() as conn:
            _insert_pg_coverage_and_unsatisfied_facts(conn)
            args = _pg_args(module, tmp_path)
            args.skip_systemd = False
            args.systemd_unit = [
                "brc-owner-console-backend.service",
                "brc-runtime-signal-watcher.timer",
                "brc-runtime-signal-watcher.service",
            ]

            def runner(unit: str):
                if unit == "brc-runtime-signal-watcher.service":
                    return module.CommandResult(stdout=stdout, stderr="", returncode=returncode)
                return module.CommandResult(stdout="active", stderr="", returncode=0)

            artifact = module.build_server_monitor_artifact(
                args,
                pg_conn=conn,
                systemd_runner=runner,
                notifier=lambda *args: {"sent": True, "status_code": 200},
            )

            assert artifact["status"] == "healthy_waiting_quiet"
            assert artifact["decision"]["decision"] == "quiet"
            assert artifact["notification"]["attempted"] is False
            assert artifact["systemd"]["ready"] is True
            watcher_row = [
                row
                for row in artifact["systemd"]["rows"]
                if row["unit"] == "brc-runtime-signal-watcher.service"
            ][0]
            assert watcher_row[field] is True
    finally:
        engine.dispose()
