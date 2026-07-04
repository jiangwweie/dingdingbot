from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_tokyo_runtime_server_monitor.py"
MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py"
)
SEED_PATH = REPO_ROOT / "scripts/seed_runtime_control_state_foundation.py"


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


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _base_paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "daily_table": tmp_path / "daily-table.json",
        "candidate_pool": tmp_path / "candidate-pool.json",
        "public_facts": tmp_path / "public-facts.json",
        "account_safe_facts": tmp_path / "account-safe-facts.json",
        "watcher_status": tmp_path / "watcher-status.json",
        "deploy_health": tmp_path / "deploy-health.json",
        "output": tmp_path / "monitor.json",
        "dedupe": tmp_path / "dedupe.json",
    }


def _write_healthy_sources(paths: dict[str, Path]) -> None:
    _write(
        paths["daily_table"],
        {
            "status": "daily_live_enablement_table_ready",
            "rows": [
                {
                    "strategy_group_id": "CPM-RO-001",
                    "symbol": "ETHUSDT",
                    "first_blocker": "computed_not_satisfied",
                }
            ],
        },
    )
    _write(
        paths["candidate_pool"],
        {
            "status": "strategy_live_candidate_pool_ready",
            "action_time_lane_inputs": [],
            "candidate_rows": [
                {
                    "strategy_group_id": "CPM-RO-001",
                    "selected_symbol": "ETHUSDT",
                    "first_blocker": "computed_not_satisfied",
                    "action_time_readiness": {
                        "status": "waiting_for_market",
                        "action_time_path_ready": False,
                        "public_facts_ready": True,
                    },
                }
            ],
        },
    )
    _write(
        paths["public_facts"],
        {
            "status": "binance_usdm_public_facts_ready",
            "checks": {"public_facts_ready": True},
        },
    )
    _write(
        paths["account_safe_facts"],
        {
            "status": "account_safe_facts_ready",
            "checks": {"account_safe_facts_ready": True},
        },
    )
    _write(paths["watcher_status"], {"status": "ok", "latest_status": "waiting_for_signal"})
    _write(paths["deploy_health"], {"status": "deploy_health_ready", "checks": {"ready": True}})


def _args(module, paths: dict[str, Path]):
    return module._parse_args(
        [
            "--output-json",
            str(paths["output"]),
            "--dedupe-state-json",
            str(paths["dedupe"]),
            "--daily-table-json",
            str(paths["daily_table"]),
            "--candidate-pool-json",
            str(paths["candidate_pool"]),
            "--public-facts-json",
            str(paths["public_facts"]),
            "--account-safe-facts-json",
            str(paths["account_safe_facts"]),
            "--allow-local-file-diagnostic",
            "--watcher-status-json",
            str(paths["watcher_status"]),
            "--deploy-health-json",
            str(paths["deploy_health"]),
            "--database-url",
            "",
            "--skip-systemd",
            "--feishu-webhook-url",
            "https://example.invalid/webhook",
        ]
    )


def _pg_args(module, tmp_path: Path):
    return module._parse_args(
        [
            "--output-json",
            str(tmp_path / "monitor.json"),
            "--dedupe-state-json",
            str(tmp_path / "legacy-dedupe-should-not-be-used.json"),
            "--daily-table-json",
            str(tmp_path / "missing-daily-table.json"),
            "--candidate-pool-json",
            str(tmp_path / "missing-candidate-pool.json"),
            "--public-facts-json",
            str(tmp_path / "missing-public-facts.json"),
            "--account-safe-facts-json",
            str(tmp_path / "missing-account-facts.json"),
            "--watcher-status-json",
            str(tmp_path / "missing-watcher-status.json"),
            "--deploy-health-json",
            str(tmp_path / "missing-deploy-health.json"),
            "--skip-systemd",
            "--feishu-webhook-url",
            "https://example.invalid/webhook",
            "--database-url",
            "sqlite://",
            "--allow-non-postgres-for-test",
        ]
    )


def _seed_pg_engine():
    migration = _load_file_module(MIGRATION_PATH, "migration_086_server_monitor")
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


def test_healthy_waiting_is_quiet_without_feishu_notification(tmp_path: Path) -> None:
    module = _load_module()
    paths = _base_paths(tmp_path)
    _write_healthy_sources(paths)

    calls: list[dict] = []

    artifact = module.build_server_monitor_artifact(
        _args(module, paths),
        notifier=lambda *args: calls.append({"args": args}) or {"sent": True},
    )

    assert artifact["status"] == "healthy_waiting_quiet"
    assert artifact["decision"]["decision"] == "quiet"
    assert artifact["notification"]["attempted"] is False
    assert artifact["notification"]["skipped_reason"] == "healthy_waiting_quiet"
    assert calls == []
    assert artifact["safety_invariants"]["calls_finalgate"] is False
    assert artifact["safety_invariants"]["calls_operation_layer"] is False
    assert artifact["safety_invariants"]["calls_exchange_write"] is False
    assert artifact["safety_invariants"]["places_order"] is False
    assert artifact["safety_invariants"]["order_created"] is False
    assert artifact["safety_invariants"]["withdrawal_or_transfer_created"] is False
    assert artifact["safety_invariants"]["credentials_or_secrets_mutated"] is False
    assert artifact["safety_invariants"]["live_profile_changed"] is False
    assert artifact["safety_invariants"]["order_sizing_changed"] is False


def test_pg_healthy_waiting_is_quiet_and_ignores_json_inputs(tmp_path: Path) -> None:
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
            assert calls == []
            assert not (tmp_path / "legacy-dedupe-should-not-be-used.json").exists()
            assert artifact["safety_invariants"]["calls_exchange_write"] is False
            assert artifact["safety_invariants"]["places_order"] is False
            run_count = conn.execute(
                text("SELECT COUNT(*) FROM brc_server_monitor_runs")
            ).scalar_one()
            assert run_count == 1
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
            assert first["decision"]["strategy_group_id"] == "SOR-001"
            assert first["decision"]["symbol"] == "ETHUSDT"
            assert first["decision"]["blocker_class"] == "action_time_ticket_missing"
            assert first["decision"]["checkpoint"] == "materialize_action_time_ticket"
            assert first["notification"]["attempted"] is True
            assert first["notification"]["sent"] is True
            assert second["notification"]["duplicate_suppressed"] is True
            assert second["notification"]["attempted"] is False
            assert len(calls) == 1
            notification_count = conn.execute(
                text("SELECT COUNT(*) FROM brc_server_monitor_notifications")
            ).scalar_one()
            run_count = conn.execute(
                text("SELECT COUNT(*) FROM brc_server_monitor_runs")
            ).scalar_one()
            assert notification_count == 1
            assert run_count == 2
            assert second["safety_invariants"]["notification_state_is_trading_authority"] is False
    finally:
        engine.dispose()


def test_pg_required_database_url_does_not_fall_back_to_json_inputs(
    tmp_path: Path,
) -> None:
    module = _load_module()
    args = module._parse_args(
        [
            "--output-json",
            str(tmp_path / "monitor.json"),
            "--require-database-url",
            "--skip-systemd",
        ]
    )
    args.database_url = ""

    try:
        module.build_server_monitor_artifact(args)
    except ValueError as exc:
        assert "PG_DATABASE_URL is required" in str(exc)
    else:
        raise AssertionError("server monitor fell back to legacy JSON without PG")


def test_default_server_monitor_requires_pg_or_explicit_local_diagnostic(
    tmp_path: Path,
) -> None:
    module = _load_module()
    args = module._parse_args(
        [
            "--output-json",
            str(tmp_path / "monitor.json"),
            "--skip-systemd",
        ]
    )
    args.database_url = ""

    try:
        module.build_server_monitor_artifact(args)
    except ValueError as exc:
        assert "allow-local-file-diagnostic" in str(exc)
    else:
        raise AssertionError("server monitor fell back to legacy JSON without PG")


def test_fresh_signal_or_action_time_boundary_notifies_once_with_dedupe(
    tmp_path: Path,
) -> None:
    module = _load_module()
    paths = _base_paths(tmp_path)
    _write_healthy_sources(paths)
    candidate_pool = json.loads(paths["candidate_pool"].read_text(encoding="utf-8"))
    candidate_pool["action_time_lane_inputs"] = [
        {"strategy_group_id": "MPG-001", "symbol": "SOLUSDT"}
    ]
    _write(paths["candidate_pool"], candidate_pool)
    calls: list[dict] = []

    def notifier(*args):
        calls.append({"args": args})
        return {"sent": True, "status_code": 200}

    first = module.build_server_monitor_artifact(_args(module, paths), notifier=notifier)
    second = module.build_server_monitor_artifact(_args(module, paths), notifier=notifier)

    assert first["decision"]["decision"] == "notify"
    assert first["decision"]["checkpoint"] == "fresh_signal_action_time_boundary"
    assert first["notification"]["attempted"] is True
    assert first["notification"]["sent"] is True
    assert second["notification"]["duplicate_suppressed"] is True
    assert second["notification"]["attempted"] is False
    assert len(calls) == 1
    dedupe_key = first["notification"]["dedupe_key"]
    assert dedupe_key["automation_id"] == "tokyo-runtime-server-monitor"
    assert dedupe_key["strategy_group_id"] == "MPG-001"
    assert dedupe_key["symbol"] == "SOLUSDT"
    assert dedupe_key["blocker_class"] == "action_time_boundary"
    assert dedupe_key["checkpoint"] == "fresh_signal_action_time_boundary"
    assert dedupe_key["first_seen_at"]
    assert dedupe_key["last_notified_at"]


def test_conditional_action_time_rehearsal_notifies_with_separate_checkpoint(
    tmp_path: Path,
) -> None:
    module = _load_module()
    paths = _base_paths(tmp_path)
    _write_healthy_sources(paths)
    candidate_pool = json.loads(paths["candidate_pool"].read_text(encoding="utf-8"))
    candidate_pool["action_time_lane_inputs"] = [
        {
            "strategy_group_id": "BRF2-001",
            "symbol": "BTCUSDT",
            "scope_state": "conditional_action_time_rehearsal_allowed",
        }
    ]
    _write(paths["candidate_pool"], candidate_pool)

    artifact = module.build_server_monitor_artifact(
        _args(module, paths),
        notifier=lambda *args: {"sent": True, "status_code": 200},
    )

    assert artifact["decision"]["decision"] == "notify"
    assert artifact["decision"]["strategy_group_id"] == "BRF2-001"
    assert artifact["decision"]["symbol"] == "BTCUSDT"
    assert artifact["decision"]["blocker_class"] == "conditional_action_time_rehearsal"
    assert artifact["decision"]["checkpoint"] == "conditional_action_time_rehearsal"
    assert "conditional_action_time_rehearsal_only" in artifact["decision"]["reasons"]
    assert artifact["notification"]["dedupe_key"]["checkpoint"] == (
        "conditional_action_time_rehearsal"
    )
    assert artifact["safety_invariants"]["calls_exchange_write"] is False
    assert artifact["safety_invariants"]["places_order"] is False


def test_promotion_candidate_from_candidate_pool_notifies(tmp_path: Path) -> None:
    module = _load_module()
    paths = _base_paths(tmp_path)
    _write_healthy_sources(paths)
    candidate_pool = json.loads(paths["candidate_pool"].read_text(encoding="utf-8"))
    candidate_pool["promotion_candidates"] = [
        {
            "strategy_group_id": "MPG-001",
            "symbol": "OPUSDT",
            "promotion_state": "promotion_candidate",
            "signal_state": "fresh",
            "first_blocker": "scope_not_attached",
        }
    ]
    _write(paths["candidate_pool"], candidate_pool)

    artifact = module.build_server_monitor_artifact(
        _args(module, paths),
        notifier=lambda *args: {"sent": True, "status_code": 200},
    )

    assert artifact["decision"]["decision"] == "notify"
    assert artifact["decision"]["strategy_group_id"] == "MPG-001"
    assert artifact["decision"]["symbol"] == "OPUSDT"
    assert artifact["decision"]["blocker_class"] == "promotion_candidate"
    assert artifact["decision"]["checkpoint"] == "fresh_signal_promotion"
    assert "promotion_candidate_present" in artifact["decision"]["reasons"]
    assert artifact["notification"]["sent"] is True


def test_fresh_symbol_readiness_non_market_blocker_notifies(tmp_path: Path) -> None:
    module = _load_module()
    paths = _base_paths(tmp_path)
    _write_healthy_sources(paths)
    candidate_pool = json.loads(paths["candidate_pool"].read_text(encoding="utf-8"))
    candidate_pool["symbol_readiness_rows"] = [
        {
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "signal_state": "fresh",
            "first_blocker": "watcher_tick_missing",
        }
    ]
    _write(paths["candidate_pool"], candidate_pool)

    artifact = module.build_server_monitor_artifact(
        _args(module, paths),
        notifier=lambda *args: {"sent": True, "status_code": 200},
    )

    assert artifact["decision"]["decision"] == "notify"
    assert artifact["decision"]["strategy_group_id"] == "SOR-001"
    assert artifact["decision"]["symbol"] == "ETHUSDT"
    assert artifact["decision"]["blocker_class"] == "watcher_tick_missing"
    assert artifact["decision"]["checkpoint"] == "fresh_signal_promotion"
    assert (
        "fresh_signal_blocked_by_non_market_blocker:watcher_tick_missing"
        in artifact["decision"]["reasons"]
    )
    assert artifact["notification"]["sent"] is True


def test_non_market_blocker_notifies(tmp_path: Path) -> None:
    module = _load_module()
    paths = _base_paths(tmp_path)
    _write_healthy_sources(paths)
    daily_table = json.loads(paths["daily_table"].read_text(encoding="utf-8"))
    daily_table["rows"][0]["first_blocker"] = "scope_not_attached"
    _write(paths["daily_table"], daily_table)

    artifact = module.build_server_monitor_artifact(
        _args(module, paths),
        notifier=lambda *args: {"sent": True, "status_code": 200},
    )

    assert artifact["decision"]["decision"] == "notify"
    assert artifact["decision"]["blocker_class"] == "scope_not_attached"
    assert artifact["notification"]["sent"] is True


def test_market_blocker_with_action_time_public_fact_status_stays_quiet(
    tmp_path: Path,
) -> None:
    module = _load_module()
    paths = _base_paths(tmp_path)
    _write_healthy_sources(paths)
    candidate_pool = json.loads(paths["candidate_pool"].read_text(encoding="utf-8"))
    candidate_pool["candidate_rows"][0]["first_blocker"] = "computed_not_satisfied"
    candidate_pool["candidate_rows"][0]["action_time_readiness"] = {
        "status": "blocked_public_facts",
        "action_time_path_ready": False,
        "public_facts_ready": False,
        "first_blocker": "fresh_cpm_long_signal_absent",
    }
    _write(paths["candidate_pool"], candidate_pool)

    artifact = module.build_server_monitor_artifact(
        _args(module, paths),
        notifier=lambda *args: {"sent": True, "status_code": 200},
    )

    assert artifact["status"] == "healthy_waiting_quiet"
    assert artifact["decision"]["decision"] == "quiet"
    assert "runtime_data_gap:watcher_or_public_facts" not in artifact["decision"][
        "reasons"
    ]


def test_watcher_or_systemd_failure_notifies(tmp_path: Path) -> None:
    module = _load_module()
    paths = _base_paths(tmp_path)
    _write_healthy_sources(paths)

    args = _args(module, paths)
    args.skip_systemd = False
    args.systemd_unit = ["brc-runtime-signal-watcher.service"]

    def runner(unit: str):
        assert unit == "brc-runtime-signal-watcher.service"
        return module.CommandResult(stdout="failed", stderr="", returncode=3)

    artifact = module.build_server_monitor_artifact(
        args,
        systemd_runner=runner,
        notifier=lambda *args: {"sent": True, "status_code": 200},
    )

    assert artifact["decision"]["decision"] == "notify"
    assert artifact["decision"]["blocker_class"] == "watcher_or_service_failure"
    assert artifact["decision"]["checkpoint"] == "systemd"
    assert artifact["systemd"]["ready"] is False
    assert artifact["notification"]["sent"] is True


def test_watcher_oneshot_inactive_success_is_not_systemd_failure(tmp_path: Path) -> None:
    module = _load_module()
    paths = _base_paths(tmp_path)
    _write_healthy_sources(paths)

    args = _args(module, paths)
    args.skip_systemd = False
    args.systemd_unit = [
        "brc-owner-console-backend.service",
        "brc-runtime-signal-watcher.timer",
        "brc-runtime-signal-watcher.service",
    ]

    def runner(unit: str):
        if unit == "brc-runtime-signal-watcher.service":
            return module.CommandResult(stdout="inactive", stderr="", returncode=3)
        return module.CommandResult(stdout="active", stderr="", returncode=0)

    artifact = module.build_server_monitor_artifact(
        args,
        systemd_runner=runner,
        notifier=lambda *args: {"sent": True, "status_code": 200},
    )

    assert artifact["status"] == "healthy_waiting_quiet"
    assert artifact["decision"]["decision"] == "quiet"
    assert artifact["systemd"]["ready"] is True
    watcher_row = [
        row
        for row in artifact["systemd"]["rows"]
        if row["unit"] == "brc-runtime-signal-watcher.service"
    ][0]
    assert watcher_row["inactive_success"] is True


def test_watcher_oneshot_activating_is_transient_not_systemd_failure(
    tmp_path: Path,
) -> None:
    module = _load_module()
    paths = _base_paths(tmp_path)
    _write_healthy_sources(paths)

    args = _args(module, paths)
    args.skip_systemd = False
    args.systemd_unit = [
        "brc-owner-console-backend.service",
        "brc-runtime-signal-watcher.timer",
        "brc-runtime-signal-watcher.service",
    ]

    def runner(unit: str):
        if unit == "brc-runtime-signal-watcher.service":
            return module.CommandResult(stdout="activating", stderr="", returncode=0)
        return module.CommandResult(stdout="active", stderr="", returncode=0)

    artifact = module.build_server_monitor_artifact(
        args,
        systemd_runner=runner,
        notifier=lambda *args: {"sent": True, "status_code": 200},
    )

    assert artifact["status"] == "healthy_waiting_quiet"
    assert artifact["decision"]["decision"] == "quiet"
    assert artifact["systemd"]["ready"] is True
    watcher_row = [
        row
        for row in artifact["systemd"]["rows"]
        if row["unit"] == "brc-runtime-signal-watcher.service"
    ][0]
    assert watcher_row["transient_active"] is True
    assert artifact["notification"]["attempted"] is False


def test_watcher_status_failure_notifies(tmp_path: Path) -> None:
    module = _load_module()
    paths = _base_paths(tmp_path)
    _write_healthy_sources(paths)
    _write(paths["watcher_status"], {"status": "stale", "latest_status": "stale"})

    artifact = module.build_server_monitor_artifact(
        _args(module, paths),
        notifier=lambda *args: {"sent": True, "status_code": 200},
    )

    assert artifact["decision"]["decision"] == "notify"
    assert artifact["decision"]["blocker_class"] == "watcher_or_service_failure"
    assert artifact["decision"]["checkpoint"] == "watcher_status"
    assert artifact["notification"]["sent"] is True


def test_feishu_failure_records_retry_without_trading_state_change(tmp_path: Path) -> None:
    module = _load_module()
    paths = _base_paths(tmp_path)
    _write_healthy_sources(paths)
    candidate_pool = json.loads(paths["candidate_pool"].read_text(encoding="utf-8"))
    candidate_pool["action_time_lane_inputs"] = [
        {"strategy_group_id": "SOR-001", "symbol": "ETHUSDT"}
    ]
    _write(paths["candidate_pool"], candidate_pool)
    calls: list[str] = []

    def notifier(*args):
        calls.append("called")
        if len(calls) == 1:
            return {"sent": False, "status_code": 500, "error": "boom"}
        return {"sent": True, "status_code": 200}

    first = module.build_server_monitor_artifact(_args(module, paths), notifier=notifier)
    second = module.build_server_monitor_artifact(_args(module, paths), notifier=notifier)

    assert first["notification"]["attempted"] is True
    assert first["notification"]["sent"] is False
    assert first["notification"]["retry_pending"] is False
    assert second["notification"]["attempted"] is True
    assert second["notification"]["sent"] is True
    assert second["safety_invariants"]["notification_state_is_trading_authority"] is False
    assert second["safety_invariants"]["places_order"] is False
    assert second["safety_invariants"]["live_profile_changed"] is False
    assert len(calls) == 2


def test_public_facts_failure_is_runtime_data_gap(
    tmp_path: Path,
) -> None:
    module = _load_module()
    paths = _base_paths(tmp_path)
    _write_healthy_sources(paths)
    _write(paths["public_facts"], {"status": "binance_usdm_public_facts_unavailable"})

    artifact = module.build_server_monitor_artifact(
        _args(module, paths),
        notifier=lambda *args: {"sent": True, "status_code": 200},
    )

    assert artifact["decision"]["decision"] == "notify"
    assert artifact["decision"]["blocker_class"] == "runtime_data_gap"
    assert "runtime_data_gap:public_facts" in artifact["decision"]["reasons"]


def test_account_safe_facts_missing_is_quiet_until_fresh_or_action_time(
    tmp_path: Path,
) -> None:
    module = _load_module()
    paths = _base_paths(tmp_path)
    _write_healthy_sources(paths)
    paths["account_safe_facts"].unlink()

    artifact = module.build_server_monitor_artifact(
        _args(module, paths),
        notifier=lambda *args: {"sent": True, "status_code": 200},
    )

    assert artifact["decision"]["decision"] == "quiet"
    assert artifact["status"] == "healthy_waiting_quiet"
    assert artifact["source_errors"]["account_safe_facts"] == "missing"
    assert "runtime_data_gap:account_safe_facts" not in artifact["decision"]["reasons"]


def test_account_safe_facts_failure_blocks_action_time_lane(
    tmp_path: Path,
) -> None:
    module = _load_module()
    paths = _base_paths(tmp_path)
    _write_healthy_sources(paths)
    candidate_pool = json.loads(paths["candidate_pool"].read_text(encoding="utf-8"))
    candidate_pool["action_time_lane_inputs"] = [
        {"strategy_group_id": "SOR-001", "symbol": "ETHUSDT"}
    ]
    _write(paths["candidate_pool"], candidate_pool)
    _write(paths["account_safe_facts"], {"status": "account_safe_facts_unavailable"})
    artifact = module.build_server_monitor_artifact(
        _args(module, paths),
        notifier=lambda *args: {"sent": True, "status_code": 200},
    )

    assert artifact["decision"]["decision"] == "notify"
    assert artifact["decision"]["blocker_class"] == "runtime_data_gap"
    assert "runtime_data_gap:account_safe_facts" in artifact["decision"]["reasons"]
    assert (
        "fresh_or_action_time_blocked_by:runtime_data_gap"
        in artifact["decision"]["reasons"]
    )
