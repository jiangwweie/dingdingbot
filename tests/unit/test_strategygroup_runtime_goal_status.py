from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from scripts import build_strategygroup_runtime_goal_status as goal_status
from src.infrastructure.runtime_control_state_repository import (
    PgBackedRuntimeControlStateRepository,
)


HEAD = "3e08c037a4990a268d1ee2b61861601d57423223"
REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py"
)
SEED_PATH = REPO_ROOT / "scripts/seed_runtime_control_state_foundation.py"


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _load_module(path: Path, name: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def pg_control_connection():
    migration = _load_module(MIGRATION_PATH, "migration_086_goal_status")
    seed = _load_module(SEED_PATH, "seed_runtime_control_state_goal_status")
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


def _write_base_artifacts(report_dir: Path) -> None:
    report_dir.mkdir(parents=True)
    _write(
        report_dir / "watcher-tick.json",
        {
            "status": "watching_no_signal",
            "blockers": [
                "runtime-mpg-1:strategy_signal_not_ready_for_shadow_candidate_prepare"
            ],
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "withdrawal_or_transfer_created": False,
            },
        },
    )
    _write(
        report_dir / "latest-summary.json",
        {
            "status": "waiting_for_signal",
            "selected_runtime_instance_ids": ["runtime-mpg-1"],
            "blockers": [
                "runtime-mpg-1:strategy_signal_not_ready_for_shadow_candidate_prepare"
            ],
        },
    )
    _write(
        report_dir / "post-signal-resume-pack.json",
        {
            "status": "waiting_for_market",
            "selected_runtime_instance_ids": ["runtime-mpg-1"],
            "blockers": [
                "runtime-mpg-1:strategy_signal_not_ready_for_shadow_candidate_prepare"
            ],
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "withdrawal_or_transfer_created": False,
            },
        },
    )
    _write(
        report_dir / "resume-dispatch-artifact.json",
        {
            "status": "waiting_for_market",
            "dispatch_status": "no_action_continue_observation",
            "dispatch_action": "continue_watcher_observation",
            "blocker_class": "waiting_for_market",
            "selected_runtime_instance_ids": ["runtime-mpg-1"],
            "blockers": [],
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "withdrawal_or_transfer_created": False,
            },
        },
    )
    _write(
        report_dir / "runtime-dry-run-audit-chain.json",
        {
            "status": "passed",
            "checks": {
                "scenario_count": 14,
                "required_scenarios_present": True,
                "all_scenarios_passed": True,
                "dangerous_effects_absent": True,
                "disabled_smoke_not_real_execution_proof": True,
                "execution_attempt_rehearsal_prepare_checked": True,
                "ticket_bound_operation_layer_handoff_checked": True,
                "ticket_bound_protected_submit_boundary_checked": True,
                "scoped_pipeline_operation_layer_submit_projection_checked": True,
                "fresh_signal_fast_auto_chain_checked": True,
                "required_facts_readiness_checked": True,
                "legacy_authorization_finalgate_ready_retirement_checked": True,
                "legacy_authorization_submit_retirement_checked": True,
                "operation_layer_blocker_review_policy_checked": True,
                "operation_layer_hard_safety_blocker_matrix_checked": True,
                "expanded_watcher_scope_execution_guard_checked": True,
                "operation_layer_authorization_chain_guard_checked": True,
                "post_submit_closed_loop_evidence_guard_checked": True,
                "post_submit_exit_outcome_matrix_checked": True,
                "reduce_only_recovery_standing_authorization_checked": True,
                "operation_layer_submit_result_identity_guard_checked": True,
                "post_submit_finalize_result_identity_guard_checked": True,
                "shared_runtime_pipeline_checked": True,
                "common_execution_chain_reuse_checked": True,
                "strategygroup_adapter_boundary_checked": True,
                "strategy_intake_no_execution_pipeline_fields_checked": True,
                "runtime_tier_policy_checked": True,
                "only_mpg_tiny_real_order_eligible_checked": True,
                "new_strategygroups_default_observe_only_checked": True,
                "selected_strategygroup_dispatch_guard_checked": True,
                "all_selected_strategygroups_reach_finalgate_dispatch_checked": True,
            },
            "scenarios": [
                {
                    "name": "execution_attempt_rehearsal_prepare",
                    "status": "passed",
                    "artifacts": {
                        "resume_dispatch": {
                            "non_executing_prepare_result": {
                                "created_records": {
                                    "execution_intent_created": True,
                                    "submit_authorization_created": True,
                                },
                                "safety_invariants": {
                                    "exchange_write_called": False,
                                    "order_created": False,
                                    "order_lifecycle_called": False,
                                    "withdrawal_or_transfer_created": False,
                                },
                            },
                        },
                    },
                },
            ],
            "safety_invariants": {
                "dangerous_effects": [],
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "withdrawal_or_transfer_created": False,
            },
        },
    )
    _write(
        report_dir / "owner-console-source-readiness.json",
        {
            "status": "ready",
            "owner_summary": {
                "market_opportunity": "等待机会",
                "funds": "资金正常",
                "orders": "暂无订单",
                "positions": "暂无持仓",
                "protection": "保护正常",
                "runtime_dry_run_audit": "审计演练正常",
            },
            "blockers": [],
        },
    )
    _write(
        report_dir / "strategygroup-runtime-pilot-status.json",
        {
            "status": "waiting_for_market",
            "blockers": [],
            "watcher_scope_alignment": {
                "status": "aligned",
                "selected_strategy_group_id": "MPG-001",
                "matched_runtime_signal_summaries": [
                    {
                        "runtime_instance_id": "runtime-mpg-1",
                        "strategy_family_id": "MPG-001",
                        "symbol": "MSTR/USDT:USDT",
                        "side": "long",
                        "status": "waiting_for_signal",
                    }
                ],
                "out_of_scope_runtime_signal_summaries": [],
            },
        },
    )
    _write(
        report_dir / "strategy-group-live-facts-readiness.json",
        {
            "status": "strategy_group_live_facts_ready_for_armed_observation",
            "blockers": [],
        },
    )


def _manifest(path: Path, head: str = HEAD) -> Path:
    _write(
        path,
        {
            "local_git": {
                "head": head,
                "short_head": head[:8],
            }
        },
    )
    return path


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
            SELECT runtime_scope_binding_id, candidate_scope_id, strategy_group_id, symbol, side, runtime_profile_id
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


def _insert_pg_action_time_ticket(conn, lane_id: str) -> None:
    conn.execute(
        text(
            """
            INSERT INTO brc_action_time_tickets (
              ticket_id,
              action_time_lane_input_id,
              promotion_candidate_id,
              signal_event_id,
              event_spec_id,
              event_spec_version_id,
              candidate_scope_id,
              runtime_scope_binding_id,
              strategy_group_id,
              strategy_group_version_id,
              symbol,
              exchange_instrument_id,
              side,
              event_id,
              event_time_ms,
              trigger_candle_close_time_ms,
              runtime_profile_id,
              public_fact_snapshot_id,
              action_time_fact_snapshot_id,
              account_safe_fact_snapshot_id,
              account_mode_snapshot_id,
              budget_reservation_id,
              protection_ref_id,
              execution_policy_id,
              execution_policy_version,
              owner_policy_version,
              sizing_policy_version,
              protection_policy_version,
              target_notional,
              leverage,
              expires_at_ms,
              status,
              authority_boundary,
              ticket_hash,
              created_under_versions_hash,
              created_at_ms
            ) VALUES (
              'ticket:SOR-001:ETHUSDT:long:unit',
              :lane_id,
              'promotion:SOR-001:ETHUSDT:long',
              'signal:SOR-001:ETHUSDT:long',
              'event_spec:SOR-001:SOR-LONG:v1',
              'event_spec:SOR-001:SOR-LONG:v1:v1',
              'candidate_scope:SOR-001:ETHUSDT:long:SOR-LONG',
              'runtime_scope:candidate_scope:SOR-001:ETHUSDT:long:SOR-LONG:owner-runtime-console-v1',
              'SOR-001',
              'strategy_group_version:SOR-001:v1',
              'ETHUSDT',
              'binance_usdm:ETH/USDT:USDT',
              'long',
              'SOR-LONG',
              1770001000000,
              1770001000000,
              'owner-runtime-console-v1',
              'fact:SOR-001:ETHUSDT:long:public',
              'fact:SOR-001:ETHUSDT:long:action-time',
              'fact:SOR-001:ETHUSDT:long:account-safe',
              'fact:SOR-001:ETHUSDT:long:account-mode',
              'budget:SOR-001:ETHUSDT:long',
              'protection:SOR-001:ETHUSDT:long',
              'exec_policy:event_spec:SOR-001:SOR-LONG:v1',
              'exec-v1',
              'owner-policy-v1',
              'owner-policy-v1',
              'protection-v1',
              20,
              2,
              1770001900000,
              'created',
              'action_time_ticket_identity_only; no_finalgate_no_operation_layer_no_exchange_write',
              'ticket-hash-sor-eth-long-unit',
              'versions-hash-sor-eth-long-unit',
              1770001000000
            )
            """
        ),
        {"lane_id": lane_id},
    )


def _matrix_by_key(packet: dict) -> dict[str, dict]:
    return {
        str(item["key"]): item
        for item in packet.get("real_order_readiness_matrix", [])
    }

def test_goal_status_uses_pg_candidate_pool_without_json_file(
    tmp_path: Path,
    pg_control_connection,
    monkeypatch,
) -> None:
    monkeypatch.delenv("PG_DATABASE_URL", raising=False)
    report_dir = tmp_path / "reports"
    _write_base_artifacts(report_dir)
    repository = PgBackedRuntimeControlStateRepository(pg_control_connection)

    packet = goal_status.build_goal_status_artifact_from_control_state(
        control_state=repository.read_control_state(),
        report_dir=report_dir,
        release_manifest=_manifest(tmp_path / "manifest.json"),
        expected_head=HEAD,
    )

    assert packet["source_mode"] == "db_backed"
    assert packet["projection_target"] == "production_current"
    assert packet["control_state_watermark"]["table_counts"]["candidate_scope"] == 22
    assert packet["evidence"]["candidate_pool_status"] == (
        "strategy_live_candidate_pool_ready"
    )
    assert packet["evidence"]["candidate_pool_source_mode"] == "db_backed"
    assert packet["evidence"]["legacy_candidate_pool_json_read"] is False
    assert packet["evidence"]["candidate_pool_action_time_lane_input_count"] == 0
    assert packet["ready_for_real_order_action"] is False
    assert packet["safety_invariants"]["calls_exchange_write"] is False


def test_pg_goal_status_ignores_legacy_report_dir_mismatch_when_pg_current_is_clear(
    tmp_path: Path,
    pg_control_connection,
) -> None:
    _insert_pg_coverage_and_unsatisfied_facts(pg_control_connection)
    pg_control_connection.commit()
    report_dir = tmp_path / "reports"
    _write_base_artifacts(report_dir)
    _write(
        report_dir / "strategygroup-runtime-pilot-status.json",
        {
            "status": "blocked_runtime_scope_mismatch",
            "blockers": ["fresh_signal_outside_selected_strategygroup_scope:runtime-teq-1"],
            "watcher_scope_alignment": {
                "status": "mismatch",
                "matched_runtime_signal_summaries": [],
                "out_of_scope_runtime_signal_summaries": [
                    {
                        "runtime_instance_id": "runtime-teq-1",
                        "strategy_family_id": "TEQ-001",
                        "symbol": "INTC/USDT:USDT",
                        "side": "long",
                        "status": "ready_for_action_time_final_gate",
                    }
                ],
            },
        },
    )
    _write(
        report_dir / "watcher-tick.json",
        {
            "status": "blocked",
            "blockers": ["loop_command_failed"],
            "exchange_write_called": True,
        },
    )
    repository = PgBackedRuntimeControlStateRepository(pg_control_connection)

    packet = goal_status.build_goal_status_artifact_from_control_state(
        control_state=repository.read_control_state(),
        report_dir=report_dir,
        release_manifest=_manifest(tmp_path / "manifest.json"),
        expected_head=HEAD,
    )

    assert packet["status"] == "waiting_for_signal"
    assert packet["checks"]["fresh_signal_present"] is False
    assert packet["checks"]["selected_strategygroup_scope_ready"] is True
    assert packet["checks"]["watcher_liveness_healthy"] is True
    assert packet["evidence"]["legacy_report_dir_read"] is False
    assert packet["evidence"]["report_dir_ignored_for_pg_current"] is True
    assert "selected_strategygroup_scope_mismatch" not in packet["blockers"]
    assert packet["safety_invariants"]["dangerous_effects"] == []
    assert packet["safety_invariants"]["calls_exchange_write"] is False


def test_pg_goal_status_reports_missing_action_time_ticket_for_open_lane(
    tmp_path: Path,
    pg_control_connection,
) -> None:
    _insert_pg_coverage_and_unsatisfied_facts(pg_control_connection)
    lane_id = _insert_pg_action_time_lane_without_ticket(pg_control_connection)
    pg_control_connection.commit()
    report_dir = tmp_path / "reports"
    _write_base_artifacts(report_dir)
    repository = PgBackedRuntimeControlStateRepository(pg_control_connection)

    packet = goal_status.build_goal_status_artifact_from_control_state(
        control_state=repository.read_control_state(),
        report_dir=report_dir,
    )

    assert packet["status"] == "fresh_signal_processing"
    assert packet["non_authority_checkpoint"] == "materialize_action_time_ticket"
    assert packet["checks"]["fresh_signal_present"] is True
    assert packet["evidence"]["pg_action_time_lane_input_count"] == 1
    assert packet["evidence"]["pg_active_ticket_count"] == 0
    assert f"action_time_ticket_missing:{lane_id}" in packet["blockers"]
    matrix = _matrix_by_key(packet)
    assert matrix["action_time_ticket"]["status"] == "waiting_for_chain"
    assert matrix["action_time_ticket"]["blocks_real_submit"] is True
    assert packet["ready_for_real_order_action"] is False


def test_pg_goal_status_advances_open_lane_after_action_time_ticket_exists(
    tmp_path: Path,
    pg_control_connection,
) -> None:
    _insert_pg_coverage_and_unsatisfied_facts(pg_control_connection)
    lane_id = _insert_pg_action_time_lane_without_ticket(pg_control_connection)
    _insert_pg_action_time_ticket(pg_control_connection, lane_id)
    pg_control_connection.commit()
    report_dir = tmp_path / "reports"
    _write_base_artifacts(report_dir)
    repository = PgBackedRuntimeControlStateRepository(pg_control_connection)

    packet = goal_status.build_goal_status_artifact_from_control_state(
        control_state=repository.read_control_state(),
        report_dir=report_dir,
    )

    assert packet["status"] == "action_time_finalgate_ready"
    assert packet["non_authority_checkpoint"] == "run_official_action_time_finalgate"
    assert packet["evidence"]["pg_action_time_lane_input_count"] == 1
    assert packet["evidence"]["pg_active_ticket_count"] == 1
    assert f"action_time_ticket_missing:{lane_id}" not in packet["blockers"]
    matrix = _matrix_by_key(packet)
    assert matrix["action_time_ticket"]["status"] == "pass"
    assert matrix["action_time_ticket"]["blocks_real_submit"] is False
    assert packet["ready_for_real_order_action"] is False


def test_pg_goal_status_blocks_open_lane_with_invalid_runtime_scope_binding(
    tmp_path: Path,
    pg_control_connection,
) -> None:
    _insert_pg_coverage_and_unsatisfied_facts(pg_control_connection)
    _insert_pg_action_time_lane_without_ticket(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_action_time_lane_inputs
            SET runtime_scope_binding_id = 'runtime_scope:missing'
            WHERE action_time_lane_input_id = 'lane:SOR-001:ETHUSDT:long:ticket-pending'
            """
        )
    )
    pg_control_connection.commit()
    report_dir = tmp_path / "reports"
    _write_base_artifacts(report_dir)
    repository = PgBackedRuntimeControlStateRepository(pg_control_connection)

    packet = goal_status.build_goal_status_artifact_from_control_state(
        control_state=repository.read_control_state(),
        report_dir=report_dir,
    )

    assert packet["status"] == "runtime_scope_mismatch"
    assert packet["checks"]["selected_strategygroup_scope_ready"] is False
    assert "selected_strategygroup_scope_mismatch" in packet["blockers"]
    matrix = _matrix_by_key(packet)
    assert matrix["selected_strategygroup_scope"]["status"] == "blocked"
    assert matrix["symbol_side_notional_leverage_scope"]["status"] == "blocked"
    assert packet["ready_for_real_order_action"] is False


def test_goal_status_cli_blocks_local_file_fallback_without_diagnostic_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("PG_DATABASE_URL", raising=False)
    report_dir = tmp_path / "reports"
    _write_base_artifacts(report_dir)
    output_json = tmp_path / "goal-status.json"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_strategygroup_runtime_goal_status.py",
            "--report-dir",
            str(report_dir),
            "--output-json",
            str(output_json),
        ],
    )

    assert goal_status.main() == 2
    assert "PG_DATABASE_URL is required" in capsys.readouterr().err
    assert not output_json.exists()


def test_goal_status_pg_cli_round_trip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_module(MIGRATION_PATH, "migration_086_goal_status_cli")
    seed = _load_module(SEED_PATH, "seed_runtime_control_state_goal_status_cli")
    database_url = f"sqlite:///{tmp_path / 'runtime.db'}"
    engine = create_engine(database_url)
    try:
        with engine.begin() as conn:
            old_op = migration.op
            migration.op = Operations(MigrationContext.configure(conn))
            try:
                migration.upgrade()
            finally:
                migration.op = old_op
            seed.seed_runtime_control_state_foundation(conn)
    finally:
        engine.dispose()

    report_dir = tmp_path / "reports"
    _write_base_artifacts(report_dir)
    output_json = tmp_path / "goal-status.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_strategygroup_runtime_goal_status.py",
            "--report-dir",
            str(report_dir),
            "--database-url",
            database_url,
            "--allow-non-postgres-for-test",
            "--release-manifest",
            str(_manifest(tmp_path / "manifest.json")),
            "--expected-head",
            HEAD,
            "--output-json",
            str(output_json),
        ],
    )

    assert goal_status.main() == 0

    artifact = json.loads(output_json.read_text(encoding="utf-8"))
    assert artifact["source_mode"] == "db_backed"
    assert artifact["evidence"]["candidate_pool_source_mode"] == "db_backed"
    assert artifact["evidence"]["legacy_candidate_pool_json_read"] is False


def test_goal_status_pg_cli_requires_database_url_when_requested(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("PG_DATABASE_URL", raising=False)
    report_dir = tmp_path / "reports"
    _write_base_artifacts(report_dir)
    output_json = tmp_path / "goal-status.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_strategygroup_runtime_goal_status.py",
            "--report-dir",
            str(report_dir),
            "--require-database-url",
            "--output-json",
            str(output_json),
        ],
    )

    assert goal_status.main() == 2
    assert "PG_DATABASE_URL is required" in capsys.readouterr().err
    assert not output_json.exists()

def test_goal_status_rejects_legacy_candidate_pool_json_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("PG_DATABASE_URL", raising=False)
    candidate_pool = tmp_path / "candidate-pool.json"
    _write(candidate_pool, {"status": "strategy_live_candidate_pool_ready"})

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_strategygroup_runtime_goal_status.py",
            "--candidate-pool-json",
            str(candidate_pool),
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        goal_status.main()

    assert excinfo.value.code == 2
    assert "unrecognized arguments: --candidate-pool-json" in capsys.readouterr().err


def test_goal_status_rejects_legacy_local_file_diagnostic_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("PG_DATABASE_URL", raising=False)
    report_dir = tmp_path / "reports"
    _write_base_artifacts(report_dir)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_strategygroup_runtime_goal_status.py",
            "--report-dir",
            str(report_dir),
            "--allow-local-file-diagnostic",
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        goal_status.main()

    assert excinfo.value.code == 2
    assert "unrecognized arguments: --allow-local-file-diagnostic" in capsys.readouterr().err


def test_goal_status_rejects_non_db_control_state(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires DB-backed state"):
        goal_status.build_goal_status_artifact_from_control_state(
            control_state={"source_mode": "local_migration_comparison"},
            report_dir=tmp_path / "reports",
        )
