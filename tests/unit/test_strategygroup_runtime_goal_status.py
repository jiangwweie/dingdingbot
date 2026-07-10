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
from scripts import materialize_ticket_bound_protected_submit_attempt as submit
from src.infrastructure.runtime_control_state_repository import (
    PgBackedRuntimeControlStateRepository,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_protected_submit_attempt import (
    _create_ready_protected_submit,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
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
SEED_PATH = REPO_ROOT / "scripts/seed_runtime_control_state_foundation.py"
PG_TEST_NOW_MS = 1770001000000


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
    risk_reservation_migration = _load_module(
        RISK_RESERVATION_MIGRATION_PATH,
        "migration_103_goal_status",
    )
    execution_eligibility_migration = _load_module(
        EXECUTION_ELIGIBILITY_MIGRATION_PATH,
        "migration_104_goal_status",
    )
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
            old_risk_op = risk_reservation_migration.op
            risk_reservation_migration.op = migration.op
            try:
                risk_reservation_migration.upgrade()
                old_eligibility_op = execution_eligibility_migration.op
                execution_eligibility_migration.op = migration.op
                try:
                    execution_eligibility_migration.upgrade()
                finally:
                    execution_eligibility_migration.op = old_eligibility_op
            finally:
                risk_reservation_migration.op = old_risk_op
        finally:
            migration.op = old_op
        seed.seed_runtime_control_state_foundation(conn)
    with engine.connect() as conn:
        yield conn
    engine.dispose()


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
            SELECT r.runtime_scope_binding_id,
                   r.candidate_scope_id,
                   r.strategy_group_id,
                   r.symbol,
                   r.side,
                   r.runtime_profile_id,
                   b.event_spec_id,
                   e.event_id
            FROM brc_runtime_scope_bindings r
            JOIN brc_candidate_scope_event_bindings b
              ON b.candidate_scope_id = r.candidate_scope_id
             AND b.status = 'active'
            JOIN brc_strategy_side_event_specs e
              ON e.event_spec_id = b.event_spec_id
             AND e.status = 'current'
            WHERE r.status = 'active'
              AND r.strategy_group_id = 'SOR-001'
              AND r.symbol = 'ETHUSDT'
              AND r.side = 'long'
            LIMIT 1
            """
        )
    ).mappings().one()
    lane_id = "lane:SOR-001:ETHUSDT:long:ticket-pending"
    conn.execute(
        text(
            """
            INSERT INTO brc_live_signal_events (
              signal_event_id, candidate_scope_id, event_spec_id,
              strategy_group_id, symbol, side, detector_key, signal_type,
              source_kind, status, freshness_state, confidence, fact_snapshot_id,
              reason_codes, signal_payload, event_time_ms,
              trigger_candle_close_time_ms, observed_at_ms, expires_at_ms,
              invalidated_at_ms, created_at_ms
            ) VALUES (
              'signal:SOR-001:ETHUSDT:long',
              :candidate_scope_id,
              :event_spec_id,
              :strategy_group_id,
              :symbol,
              :side,
              'detector:SOR-001:long',
              :event_id,
              'live_market',
              'facts_validated',
              'fresh',
              0.9,
              'fact:SOR-001:ETHUSDT:long:public',
              '["unit_goal_status_signal"]',
              '{"time_authority": "trigger_candle_close_time_ms"}',
              1770000900000,
              1770000900000,
              1770000900001,
              1770001900000,
              NULL,
              1770000900002
            )
            """
        ),
        {
            "candidate_scope_id": row["candidate_scope_id"],
            "event_spec_id": row["event_spec_id"],
            "strategy_group_id": row["strategy_group_id"],
            "symbol": row["symbol"],
            "side": row["side"],
            "event_id": row["event_id"],
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO brc_pretrade_readiness_rows (
              readiness_row_id, candidate_scope_id, strategy_group_id, symbol,
              side, readiness_state, detector_state, watcher_state,
              public_facts_state, signal_lifecycle_status,
              signal_freshness_state, risk_state, scope_state, promotion_state,
              first_blocker_class, first_blocker_detail, next_action,
              stop_condition, evidence_ref, source_watermark, computed_at_ms,
              valid_until_ms
            ) VALUES (
              'readiness:SOR-001:ETHUSDT:long',
              :candidate_scope_id,
              :strategy_group_id,
              :symbol,
              :side,
              'ready',
              'ready',
              'fresh',
              'satisfied',
              'facts_validated',
              'fresh',
              'acceptable',
              'live_submit_allowed',
              'action_time_lane',
              'action_time_preflight_ready',
              'ready',
              'materialize_action_time_ticket',
              'ticket_created_or_lane_expires',
              'fact:SOR-001:ETHUSDT:long:public',
              'unit',
              1770000950000,
              1770001900000
            )
            """
        ),
        {
            "candidate_scope_id": row["candidate_scope_id"],
            "strategy_group_id": row["strategy_group_id"],
            "symbol": row["symbol"],
            "side": row["side"],
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO brc_promotion_candidates (
              promotion_candidate_id, signal_event_id, readiness_row_id,
              strategy_group_id, symbol, side, promotion_scope, status,
              scope_state, risk_state, facts_snapshot_id, blockers,
              arbitration_rank, created_at_ms, expires_at_ms, closed_at_ms,
              authority_boundary
            ) VALUES (
              'promotion:SOR-001:ETHUSDT:long',
              'signal:SOR-001:ETHUSDT:long',
              'readiness:SOR-001:ETHUSDT:long',
              :strategy_group_id,
              :symbol,
              :side,
              'live_submit_candidate',
              'arbitration_won',
              'live_submit_allowed',
              'acceptable',
              'fact:SOR-001:ETHUSDT:long:public',
              '[]',
              1,
              1770000960000,
              1770001900000,
              NULL,
              'pg_promotion_candidate_non_executing; no_finalgate_no_operation_layer_no_exchange_write'
            )
            """
        ),
        {
            "strategy_group_id": row["strategy_group_id"],
            "symbol": row["symbol"],
            "side": row["side"],
        },
    )
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


def test_pg_non_market_blockers_ignores_action_time_preflight_ready() -> None:
    candidate_pool = {
        "symbol_readiness_rows": [
            {"first_blocker": "action_time_preflight_ready"},
            {"first_blocker": "computed_not_satisfied"},
            {"first_blocker": "event_execution_capability_not_certified"},
            {"first_blocker": "runtime_profile_scope_missing"},
        ]
    }

    assert goal_status._pg_non_market_blockers(candidate_pool) == [
        "candidate_pool_blocker:runtime_profile_scope_missing:1"
    ]


def test_goal_owner_action_required_does_not_escalate_engineering_gaps() -> None:
    assert goal_status._goal_owner_label("runtime_liveness_degraded") == "处理中"
    assert goal_status._goal_owner_label("missing_fact") == "处理中"
    assert goal_status._goal_owner_action_required(
        "runtime_liveness_degraded",
        "需要介入",
    ) is False
    assert goal_status._goal_owner_action_required("missing_fact", "需要介入") is False
    assert goal_status._goal_owner_action_required("hard_safety_stop", "需要介入") is True


def test_goal_status_uses_pg_candidate_pool_without_json_file(
    tmp_path: Path,
    pg_control_connection,
    monkeypatch,
) -> None:
    monkeypatch.delenv("PG_DATABASE_URL", raising=False)
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=PG_TEST_NOW_MS,
    )

    packet = goal_status.build_goal_status_artifact_from_control_state(
        control_state=repository.read_control_state(),
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


def test_pg_goal_status_uses_pg_current_when_current_is_clear(
    tmp_path: Path,
    pg_control_connection,
) -> None:
    _insert_pg_coverage_and_unsatisfied_facts(pg_control_connection)
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=PG_TEST_NOW_MS,
    )

    packet = goal_status.build_goal_status_artifact_from_control_state(
        control_state=repository.read_control_state(),
    )

    assert packet["status"] == "waiting_for_signal"
    assert packet["plain_language_stage"] == "等待市场机会"
    assert packet["plain_language_next_system_action"] == (
        "系统继续观察市场，不需要 Owner 操作"
    )
    assert packet["owner_action_required"] is False
    assert packet["action_time_ticket_explanation"]["plain_language_stage"] == (
        "当前没有 action-time lane"
    )
    assert packet["checks"]["fresh_signal_present"] is False
    assert packet["checks"]["selected_strategygroup_scope_ready"] is True
    assert packet["checks"]["watcher_liveness_healthy"] is True
    assert packet["evidence"]["legacy_report_dir_read"] is False
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
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=PG_TEST_NOW_MS,
    )

    packet = goal_status.build_goal_status_artifact_from_control_state(
        control_state=repository.read_control_state(),
    )

    assert packet["status"] == "fresh_signal_processing"
    assert packet["non_authority_checkpoint"] == "materialize_action_time_ticket"
    assert packet["plain_language_stage"] == "正在把信号推进成正式票据"
    assert packet["plain_language_next_system_action"] == (
        "系统为当前 lane 生成 Action-Time Ticket"
    )
    assert packet["owner_action_required"] is False
    assert packet["checks"]["fresh_signal_present"] is True
    assert packet["evidence"]["pg_action_time_lane_input_count"] == 1
    assert packet["evidence"]["pg_active_ticket_count"] == 0
    assert f"action_time_ticket_missing:{lane_id}" in packet["blockers"]
    assert packet["action_time_ticket_explanation"]["plain_language_stage"] == (
        "尚未生成正式候选交易票据"
    )
    assert packet["action_time_ticket_explanation"]["missing_ticket_lane_ids"] == [
        lane_id
    ]
    assert (
        packet["action_time_ticket_explanation"]["decides_trade_authority"] is False
    )
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
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=PG_TEST_NOW_MS,
    )

    packet = goal_status.build_goal_status_artifact_from_control_state(
        control_state=repository.read_control_state(),
    )

    assert packet["status"] == "action_time_finalgate_ready"
    assert packet["non_authority_checkpoint"] == "run_official_action_time_finalgate"
    assert packet["plain_language_stage"] == "正式票据已生成，等待最终安全检查"
    assert packet["plain_language_next_system_action"] == (
        "系统使用 ticket 进入官方 FinalGate 检查"
    )
    assert packet["owner_action_required"] is False
    assert packet["evidence"]["pg_action_time_lane_input_count"] == 1
    assert packet["evidence"]["pg_active_ticket_count"] == 1
    assert f"action_time_ticket_missing:{lane_id}" not in packet["blockers"]
    assert packet["action_time_ticket_explanation"]["plain_language_stage"] == (
        "已有正式候选交易票据"
    )
    assert packet["action_time_ticket_explanation"]["active_ticket_ids"] == [
        "ticket:SOR-001:ETHUSDT:long:unit"
    ]
    matrix = _matrix_by_key(packet)
    assert matrix["action_time_ticket"]["status"] == "pass"
    assert matrix["action_time_ticket"]["blocks_real_submit"] is False
    assert packet["ready_for_real_order_action"] is False


def test_pg_goal_status_reports_completed_disabled_smoke_after_lane_expires(
    pg_control_connection,
) -> None:
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="disabled_smoke",
        now_ms=NOW_MS + 4000,
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=NOW_MS + 120_000,
    )

    packet = goal_status.build_goal_status_artifact_from_control_state(
        control_state=repository.read_monitor_control_state(),
    )

    assert packet["status"] == "protected_submit_rehearsal_completed"
    assert packet["non_authority_checkpoint"] == "continue_watcher_observation"
    assert packet["ready_for_real_order_action"] is False
    assert packet["owner_action_required"] is False
    assert packet["evidence"]["pg_latest_successful_protected_submit_attempt_id"] == (
        prepared["protected_submit_attempt_id"]
    )
    assert packet["evidence"]["pg_latest_successful_protected_submit_status"] == (
        "disabled_smoke_passed"
    )
    assert not any(
        "action_time_boundary_not_reproduced" in blocker
        for blocker in packet["blockers"]
    )
    assert packet["action_time_ticket_explanation"][
        "latest_protected_submit_attempt_id"
    ] == prepared["protected_submit_attempt_id"]
    assert packet["action_time_ticket_explanation"][
        "latest_protected_submit_status"
    ] == "disabled_smoke_passed"
    matrix = _matrix_by_key(packet)
    assert matrix["action_time_ticket"]["status"] == "pass"
    assert matrix["ticket_bound_protected_submit"]["status"] == "pass"
    assert matrix["ticket_bound_protected_submit"]["blocks_real_submit"] is False


def test_pg_goal_status_newer_lane_supersedes_previous_disabled_smoke_attempt(
    pg_control_connection,
) -> None:
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="disabled_smoke",
        now_ms=NOW_MS + 4000,
    )
    attempt_created_at_ms = int(
        pg_control_connection.execute(
            text(
                """
                SELECT created_at_ms
                FROM brc_ticket_bound_protected_submit_attempts
                WHERE protected_submit_attempt_id = :attempt_id
                """
            ),
            {"attempt_id": prepared["protected_submit_attempt_id"]},
        ).scalar_one()
    )
    newer_lane_created_at_ms = attempt_created_at_ms + 1000
    new_lane_id = "lane:SOR-001:ETHUSDT:long:newer-ticket-pending"
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_action_time_lane_inputs
            SET closed_at_ms = :closed_at_ms,
                expires_at_ms = :closed_at_ms,
                lane_scope = 'rehearsal'
            WHERE action_time_lane_input_id = :lane_id
            """
        ),
        {"lane_id": ids["lane_id"], "closed_at_ms": NOW_MS + 4500},
    )
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_action_time_lane_inputs (
              action_time_lane_input_id, promotion_candidate_id,
              strategy_group_id, symbol, side, runtime_profile_id,
              lane_scope, status, signal_event_id, public_fact_snapshot_id,
              action_time_fact_snapshot_id, runtime_scope_binding_id,
              candidate_authorization_ref, runtime_safety_snapshot_id,
              first_blocker_class, created_at_ms, expires_at_ms, closed_at_ms,
              authority_boundary
            )
            SELECT
              :new_lane_id, promotion_candidate_id,
              strategy_group_id, symbol, side, runtime_profile_id,
              'real_submit_candidate', 'ticket_pending', signal_event_id,
              public_fact_snapshot_id, action_time_fact_snapshot_id,
              runtime_scope_binding_id, candidate_authorization_ref, NULL,
              first_blocker_class, :created_at_ms, :expires_at_ms, NULL,
              authority_boundary
            FROM brc_action_time_lane_inputs
            WHERE action_time_lane_input_id = :old_lane_id
            """
        ),
        {
            "new_lane_id": new_lane_id,
            "old_lane_id": ids["lane_id"],
            "created_at_ms": newer_lane_created_at_ms,
            "expires_at_ms": newer_lane_created_at_ms + 600_000,
        },
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=NOW_MS + 120_000,
    )

    control_state = repository.read_monitor_control_state()
    assert any(
        row["action_time_lane_input_id"] == new_lane_id
        for row in control_state["action_time_lane_inputs"]
    )
    assert (
        goal_status._pg_latest_active_signal_chain_created_at(control_state)
        == newer_lane_created_at_ms
    )

    packet = goal_status.build_goal_status_artifact_from_control_state(
        control_state=control_state,
    )

    assert packet["status"] == "fresh_signal_processing"
    assert packet["non_authority_checkpoint"] == "materialize_action_time_ticket"
    assert packet["ready_for_real_order_action"] is False
    assert packet["evidence"]["active_action_time_lane_input_ids"] == [new_lane_id]
    assert packet["evidence"]["pg_latest_successful_protected_submit_attempt_id"] == ""
    assert packet["action_time_ticket_explanation"][
        "latest_protected_submit_attempt_id"
    ] == ""


def test_pg_goal_status_ignores_expired_open_lane(pg_control_connection) -> None:
    now_ms = 1770002000000
    _insert_pg_coverage_and_unsatisfied_facts(pg_control_connection)
    lane_id = _insert_pg_action_time_lane_without_ticket(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_action_time_lane_inputs
            SET expires_at_ms = :expires_at_ms
            WHERE action_time_lane_input_id = :lane_id
            """
        ),
        {"expires_at_ms": now_ms - 1, "lane_id": lane_id},
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=now_ms,
    )

    packet = goal_status.build_goal_status_artifact_from_control_state(
        control_state=repository.read_control_state(),
    )

    assert packet["evidence"]["pg_action_time_lane_input_count"] == 0
    assert packet["action_time_ticket_explanation"]["plain_language_stage"] == (
        "当前没有 action-time lane"
    )
    assert lane_id not in json.dumps(packet, ensure_ascii=False)


def test_pg_goal_status_ignores_expired_action_time_ticket(
    pg_control_connection,
) -> None:
    now_ms = 1770002000000
    _insert_pg_coverage_and_unsatisfied_facts(pg_control_connection)
    lane_id = _insert_pg_action_time_lane_without_ticket(pg_control_connection)
    _insert_pg_action_time_ticket(pg_control_connection, lane_id)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_action_time_lane_inputs
            SET expires_at_ms = :expires_at_ms
            WHERE action_time_lane_input_id = :lane_id
            """
        ),
        {"expires_at_ms": now_ms + 600_000, "lane_id": lane_id},
    )
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_action_time_tickets
            SET expires_at_ms = :expires_at_ms
            WHERE action_time_lane_input_id = :lane_id
            """
        ),
        {"expires_at_ms": now_ms - 1, "lane_id": lane_id},
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=now_ms,
    )

    packet = goal_status.build_goal_status_artifact_from_control_state(
        control_state=repository.read_control_state(),
    )

    assert packet["evidence"]["pg_action_time_lane_input_count"] == 1
    assert packet["evidence"]["pg_active_ticket_count"] == 0
    assert packet["action_time_ticket_explanation"]["active_ticket_ids"] == []
    assert f"action_time_ticket_missing:{lane_id}" in packet["blockers"]


def test_pg_goal_status_ignores_expired_runtime_safety_conflict(
    pg_control_connection,
) -> None:
    now_ms = 1770002000000
    _insert_pg_coverage_and_unsatisfied_facts(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_runtime_safety_state_snapshots (
              runtime_safety_snapshot_id, action_time_lane_input_id,
              strategy_group_id, symbol, side, runtime_profile_id, safety_state,
              submit_allowed, finalgate_ready, operation_layer_ready,
              protection_ready, active_position_conflict, facts_fresh,
              trusted_fact_refs_complete, blockers, trusted_fact_refs,
              observed_at_ms, valid_until_ms, created_at_ms, authority_boundary
            ) VALUES (
              'runtime_safety:expired-conflict', 'lane:expired-conflict',
              'SOR-001', 'ETHUSDT', 'long',
              'runtime-profile:SOR-001:ETHUSDT:long:v1', 'blocked_safety',
              false, false, false, false, true, false, false,
              '["active_position_resolution"]', '{}',
              :observed_at_ms, :valid_until_ms, :created_at_ms,
              'unit no exchange write'
            )
            """
        ),
        {
            "observed_at_ms": now_ms - 1000,
            "valid_until_ms": now_ms - 1,
            "created_at_ms": now_ms - 1000,
        },
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=now_ms,
    )

    packet = goal_status.build_goal_status_artifact_from_control_state(
        control_state=repository.read_control_state(),
    )

    assert packet["status"] == "waiting_for_signal"
    assert packet["ready_for_real_order_action"] is False
    assert "active_position_resolution" not in packet["blockers"]


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
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=PG_TEST_NOW_MS,
    )

    packet = goal_status.build_goal_status_artifact_from_control_state(
        control_state=repository.read_control_state(),
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

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_strategygroup_runtime_goal_status.py",
        ],
    )

    assert goal_status.main() == 2
    assert "PG_DATABASE_URL is required" in capsys.readouterr().err


def test_goal_status_pg_cli_round_trip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
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

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_strategygroup_runtime_goal_status.py",
            "--database-url",
            database_url,
            "--allow-non-postgres-for-test",
            "--json",
        ],
    )

    assert goal_status.main() == 0

    artifact = json.loads(capsys.readouterr().out)
    assert artifact["source_mode"] == "db_backed"
    assert artifact["evidence"]["candidate_pool_source_mode"] == "db_backed"
    assert artifact["evidence"]["legacy_candidate_pool_json_read"] is False


def test_goal_status_pg_cli_normalizes_asyncpg_dsn(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, str] = {}

    class FakeEngine:
        def connect(self):
            return self

        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

        def dispose(self):
            return None

    def fake_create_engine(database_url: str):
        captured["database_url"] = database_url
        return FakeEngine()

    monkeypatch.setattr(goal_status.sa, "create_engine", fake_create_engine)
    monkeypatch.setattr(
        goal_status,
        "PgBackedRuntimeControlStateRepository",
        lambda conn: type("Repo", (), {"read_control_state": lambda self: {}})(),
    )
    monkeypatch.setattr(
        goal_status,
        "build_goal_status_artifact_from_control_state",
        lambda control_state: {
            "status": "waiting_for_opportunity",
            "ready_for_real_order_action": False,
            "non_authority_checkpoint": "continue_observation",
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_strategygroup_runtime_goal_status.py",
            "--database-url",
            "postgresql+asyncpg://user:pass@localhost/db",
        ],
    )

    assert goal_status.main() == 0
    assert captured["database_url"].startswith("postgresql+psycopg://")
    assert json.loads(capsys.readouterr().out)["status"] == "waiting_for_opportunity"


def test_goal_status_pg_cli_requires_database_url_when_requested(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("PG_DATABASE_URL", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_strategygroup_runtime_goal_status.py",
            "--require-database-url",
        ],
    )

    assert goal_status.main() == 2
    assert "PG_DATABASE_URL is required" in capsys.readouterr().err

def test_goal_status_rejects_legacy_candidate_pool_json_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("PG_DATABASE_URL", raising=False)
    candidate_pool = tmp_path / "candidate-pool.json"

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

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_strategygroup_runtime_goal_status.py",
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
        )
