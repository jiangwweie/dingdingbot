from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

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
from src.application.runtime_strategy_signal_evaluation_service import (
    RuntimeStrategySignalEvaluationService,
    RuntimeStrategySignalEvaluationStatus,
)
from src.application.action_time.full_chain_simulation_harness import (
    bind_simulation_ticket_exposure_episode,
    FULL_CHAIN_FAILURE_SCENARIOS,
    FullChainSimulationInput,
    HistoricalActionTimeAcceptanceCase,
    run_ticket_bound_pre_exchange_acceptance,
    run_ticket_bound_full_chain_simulation,
    run_ticket_bound_full_chain_failure_scenario,
)
from src.application.action_time.lifecycle_safety_core import (
    lifecycle_decision_for_status,
)
from src.application.action_time.lifecycle_mutation_capability import (
    set_lifecycle_mutation_capability,
)
from src.application.readmodels.lifecycle_mutation_enablement_proof import (
    ActionTimeCertificationReferenceV2,
    LaneSourceWatermarkV1,
    LifecycleMutationEnablementProof,
)
from src.application.action_time.ticket_materialization_sequence import (
    materialize_action_time_ticket_sequence,
)
from src.application.action_time.runtime_pg_fact_snapshots import (
    write_account_safe_fact_snapshots,
)
from src.domain.runtime_lane_identity import RuntimeLaneIdentity
from src.interfaces import api as trading_api_module
from src.interfaces import api_trading_console
from tests.unit.test_pg_promotion_action_time_lane_materialization import (
    NOW_MS,
    _insert_ready_fresh_signal,
)
from tests.unit.test_runtime_strategy_signal_evaluation_service import (
    _bear_rally_failure_1h,
    _comparative_snapshot,
    _cpm_long_1h,
    _cpm_up_context_4h,
    _down_context_4h,
    _mi_comparative_snapshot,
    _mi_impulse_1h,
    _mpg_long_1h,
    _signal_input,
    _sor_session_15m,
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
RUNTIME_SUPERVISION_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-10-106_create_runtime_supervision_and_allocation.py"
)
LIFECYCLE_TYPED_SCOPE_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-11-113_create_exchange_account_mode_and_domain_holds.py"
)
LIFECYCLE_COMMAND_EXTENSION_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-11-114_extend_exchange_commands_for_lifecycle.py"
)
DYNAMIC_RISK_POLICY_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-12-115_add_dynamic_execution_risk_policy.py"
)
ACCOUNT_RISK_CURRENT_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-17-127_create_account_risk_current_projections.py"
)
LANE_IDENTITY_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-13-118_conserve_runtime_lane_identity.py"
)
ACTION_TIME_INVOCATION_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-13-119_action_time_invocation_consistency.py"
)
TERMINAL_PREDISPATCH_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-13-120_reconcile_terminal_predispatch_commands.py"
)
EXIT_EXECUTION_SAFETY_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-14-121_add_exit_execution_safety.py"
)
TICKET_EXIT_POLICY_CORE_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-14-122_add_ticket_exit_policy_core.py"
)
ACCOUNT_RISK_POLICY_MIGRATION_PATH = (
    REPO_ROOT / "migrations/versions/2026-07-17-126_create_account_risk_policy.py"
)
ACCOUNT_CAPACITY_SCOPE_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-17-129_add_account_capacity_reservation_scope.py"
)
ACCOUNT_CLAIM_POLICY_EVENT_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-17-130_add_account_capacity_claim_policy_event.py"
)
ASSET_NEUTRAL_EXPAND_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-17-131_expand_asset_neutral_account_risk_identity.py"
)
ASSET_NEUTRAL_BACKFILL_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-17-132_backfill_asset_neutral_account_risk_identity.py"
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

HISTORICAL_ACTION_TIME_ACCEPTANCE_CASES = (
    HistoricalActionTimeAcceptanceCase(
        source_signal_event_id="signal:5bb26bea50c2f6a94503e7b265573bae",
        source_ticket_id=(
            "ticket:e0c3a9d496f79f64983e7efc1bac1528054f3a8a"
            "ced4e32948f3293fd7a8896c"
        ),
        strategy_group_id="CPM-RO-001",
        symbol="AVAXUSDT",
        side="long",
        event_time_ms=1_783_792_799_999,
        observed_at_ms=1_783_793_005_767,
        expires_at_ms=1_783_793_279_000,
        fact_values={
            "htf_trend_intact": True,
            "reclaim_confirmed": True,
            "pullback_low_reference": "6.6820",
            "last_price": "6.7560",
        },
    ),
    HistoricalActionTimeAcceptanceCase(
        source_signal_event_id="signal:3b3a9b3f2e47401c38f188701fcd4d66",
        source_ticket_id=(
            "ticket:999fe1c427c105bde3c1c8a2da833c6dc8294a3"
            "dcb5ad030de39db9f35972331"
        ),
        strategy_group_id="CPM-RO-001",
        symbol="SUIUSDT",
        side="long",
        event_time_ms=1_783_843_199_999,
        observed_at_ms=1_783_843_277_585,
        expires_at_ms=1_783_843_549_009,
        fact_values={
            "htf_trend_intact": True,
            "reclaim_confirmed": True,
            "pullback_low_reference": "0.721100",
            "last_price": "0.738400",
        },
    ),
    HistoricalActionTimeAcceptanceCase(
        source_signal_event_id="signal:24e6194f62ac955403b07a13edac46d5",
        source_ticket_id=(
            "ticket:24e323b0bfd6a9bb90f1dad96abac236471e5f584"
            "325c04ca35ffe0ca24df23d"
        ),
        strategy_group_id="CPM-RO-001",
        symbol="SUIUSDT",
        side="long",
        event_time_ms=1_783_846_799_999,
        observed_at_ms=1_783_846_892_096,
        expires_at_ms=1_783_847_163_000,
        fact_values={
            "htf_trend_intact": True,
            "reclaim_confirmed": True,
            "pullback_low_reference": "0.721100",
            "last_price": "0.739900",
        },
    ),
    HistoricalActionTimeAcceptanceCase(
        source_signal_event_id="signal:fe4b54bf2ea7328cc711831d11d303aa",
        source_ticket_id=(
            "ticket:9e41ab89baac01a830d5160b7ace230070356231"
            "e95ef8bb54128902c0512c54"
        ),
        strategy_group_id="CPM-RO-001",
        symbol="SUIUSDT",
        side="long",
        event_time_ms=1_783_861_199_999,
        observed_at_ms=1_783_861_767_205,
        expires_at_ms=1_783_862_039_000,
        fact_values={
            "htf_trend_intact": True,
            "reclaim_confirmed": True,
            "pullback_low_reference": "0.721100",
            "last_price": "0.742300",
        },
    ),
    HistoricalActionTimeAcceptanceCase(
        source_signal_event_id="signal:225cf22a6e943ab581d564ae4586f18d",
        source_ticket_id=(
            "ticket:3d7cda73572ec04d0c00d73a55e364518223e00"
            "b11306aac6e26f7c1eed487c8"
        ),
        strategy_group_id="CPM-RO-001",
        symbol="ETHUSDT",
        side="long",
        event_time_ms=1_783_868_399_999,
        observed_at_ms=1_783_868_609_563,
        expires_at_ms=1_783_868_880_000,
        fact_values={
            "htf_trend_intact": True,
            "reclaim_confirmed": True,
            "pullback_low_reference": "1778.26",
            "last_price": "1818.73",
        },
    ),
    HistoricalActionTimeAcceptanceCase(
        source_signal_event_id="signal:7dce92f66756ee63fa5612b45cee3ebb",
        source_ticket_id=None,
        strategy_group_id="CPM-RO-001",
        symbol="ETHUSDT",
        side="long",
        event_time_ms=1_783_828_799_999,
        observed_at_ms=1_783_829_348_983,
        expires_at_ms=1_783_829_620_002,
        fact_values={
            "htf_trend_intact": True,
            "reclaim_confirmed": True,
            "pullback_low_reference": "1778.26",
            "last_price": "1810.83",
        },
    ),
)


def test_historical_ticket_reaches_durable_pre_exchange_boundary_without_gateway(
    pg_control_connection,
    monkeypatch,
):
    _arm_submit_decision_env(monkeypatch)
    case = HistoricalActionTimeAcceptanceCase(
        source_signal_event_id="signal:5bb26bea50c2f6a94503e7b265573bae",
        source_ticket_id=(
            "ticket:e0c3a9d496f79f64983e7efc1bac1528054f3a8a"
            "ced4e32948f3293fd7a8896c"
        ),
        strategy_group_id="CPM-RO-001",
        symbol="AVAXUSDT",
        side="long",
        event_time_ms=1_783_792_799_999,
        observed_at_ms=1_783_793_005_767,
        expires_at_ms=1_783_793_279_000,
        fact_values={
            "htf_trend_intact": True,
            "reclaim_confirmed": True,
            "pullback_low_reference": "6.6820",
            "last_price": "6.7560",
        },
    )

    result = run_ticket_bound_pre_exchange_acceptance(
        pg_control_connection,
        case,
        projection_publisher=lambda conn, now_ms=None: (
            publisher.publish_runtime_control_current_projections(
                conn,
                target_runtime_head="a" * 40,
                now_ms=now_ms,
            )
        ),
    )

    assert result["status"] == "pre_exchange_acceptance_ready"
    assert result["source_lineage"] == {
        "signal_event_id": case.source_signal_event_id,
        "ticket_id": case.source_ticket_id,
        "event_time_ms": case.event_time_ms,
    }
    assert result["ticket"]["ticket_id"] != case.source_ticket_id
    assert [row["order_role"] for row in result["exchange_commands"]] == [
        "ENTRY",
        "SL",
        "TP1",
    ]
    assert result["completed_at_ms"] <= case.expires_at_ms
    assert result["authority_boundary"] == {
        "calls_finalgate": True,
        "calls_operation_layer_handoff": True,
        "prepares_protected_submit": True,
        "prepares_durable_exchange_commands": True,
        "calls_operation_layer_submit": False,
        "calls_exchange_gateway": False,
        "calls_exchange_write": False,
        "uses_repo_json_or_md_authority": False,
        "mutates_production_pg": False,
    }


@pytest.mark.parametrize(
    "acceptance_case",
    HISTORICAL_ACTION_TIME_ACCEPTANCE_CASES,
    ids=lambda case: (
        f"{case.symbol}-{case.source_signal_event_id.removeprefix('signal:')[:8]}"
    ),
)
def test_six_historical_events_reach_current_pre_exchange_boundary(
    pg_control_connection,
    monkeypatch,
    acceptance_case: HistoricalActionTimeAcceptanceCase,
):
    _arm_submit_decision_env(monkeypatch)

    result = run_ticket_bound_pre_exchange_acceptance(
        pg_control_connection,
        acceptance_case,
        projection_publisher=lambda conn, now_ms=None: (
            publisher.publish_runtime_control_current_projections(
                conn,
                target_runtime_head="a" * 40,
                now_ms=now_ms,
            )
        ),
    )

    assert result["status"] == "pre_exchange_acceptance_ready"
    assert result["source_lineage"]["signal_event_id"] == (
        acceptance_case.source_signal_event_id
    )
    assert result["completed_at_ms"] <= acceptance_case.expires_at_ms
    assert result["prepared_submit"]["status"] == "submit_prepared"
    assert result["prepared_submit"]["exchange_write_called"] is False
    assert result["submit_mode_decision"]["decision"] == "real_gateway_action"
    assert result["total_stage_duration_ms"] == sum(
        stage["duration_ms"] for stage in result["stages"]
    )
    assert all(stage["duration_ms"] >= 0 for stage in result["stages"])
    assert {row["command_state"] for row in result["exchange_commands"]} == {
        "prepared"
    }
    assert result["authority_boundary"]["calls_exchange_gateway"] is False
    assert result["authority_boundary"]["calls_exchange_write"] is False
    if acceptance_case.source_ticket_id is None:
        sizing = result["budget_reservation"]
        assert Decimal(str(sizing["intended_qty"])) > 0
        assert Decimal(str(sizing["risk_at_stop"])) > 0
        assert Decimal(str(sizing["reserved_margin"])) > 0


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _upgrade_module(conn, module) -> None:
    previous_op = module.op
    module.op = Operations(MigrationContext.configure(conn))
    try:
        module.upgrade()
    finally:
        module.op = previous_op


def _arm_submit_decision_env(monkeypatch) -> None:
    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")
    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "order_allowed")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_EXCHANGE_SUBMIT_GATEWAY_BINDING_ENABLED", "true")
    monkeypatch.setenv(
        "BRC_RUNTIME_EXCHANGE_ACCOUNT_ID",
        "owner-subaccount-runtime-v0",
    )
    monkeypatch.setenv("BRC_RUNTIME_EXCHANGE_ID", "binance_usdm")


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
                                        post_submit_reconciliation_migration = _load_module(
                                            POST_SUBMIT_RECONCILIATION_TICK_MIGRATION_PATH,
                                            "migration_101_action_time_full_chain",
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
                                                "migration_102_action_time_full_chain",
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
                                                    "migration_103_action_time_full_chain",
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
                                                        "migration_104_action_time_full_chain",
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
                                                            "migration_105_action_time_full_chain",
                                                        )
                                                        old_exchange_command_op = (
                                                            exchange_command_migration.op
                                                        )
                                                        exchange_command_migration.op = (
                                                            migration.op
                                                        )
                                                        try:
                                                            exchange_command_migration.upgrade()
                                                            runtime_supervision_migration = _load_module(
                                                                RUNTIME_SUPERVISION_MIGRATION_PATH,
                                                                "migration_106_action_time_full_chain",
                                                            )
                                                            old_runtime_supervision_op = (
                                                                runtime_supervision_migration.op
                                                            )
                                                            runtime_supervision_migration.op = (
                                                                migration.op
                                                            )
                                                            try:
                                                                runtime_supervision_migration.upgrade()
                                                            finally:
                                                                runtime_supervision_migration.op = (
                                                                    old_runtime_supervision_op
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
        for path, module_name in (
            (
                LIFECYCLE_TYPED_SCOPE_MIGRATION_PATH,
                "migration_113_action_time_full_chain",
            ),
            (
                LIFECYCLE_COMMAND_EXTENSION_MIGRATION_PATH,
                "migration_114_action_time_full_chain",
            ),
            (
                DYNAMIC_RISK_POLICY_MIGRATION_PATH,
                "migration_115_action_time_full_chain",
            ),
            (
                LANE_IDENTITY_MIGRATION_PATH,
                "migration_118_action_time_full_chain",
            ),
            (
                ACTION_TIME_INVOCATION_MIGRATION_PATH,
                "migration_119_action_time_full_chain",
            ),
            (
                TERMINAL_PREDISPATCH_MIGRATION_PATH,
                "migration_120_action_time_full_chain",
            ),
            (
                EXIT_EXECUTION_SAFETY_MIGRATION_PATH,
                "migration_121_action_time_full_chain",
            ),
            (
                TICKET_EXIT_POLICY_CORE_MIGRATION_PATH,
                "migration_122_action_time_full_chain",
            ),
            (
                ACCOUNT_RISK_POLICY_MIGRATION_PATH,
                "migration_126_action_time_full_chain",
            ),
            (
                ACCOUNT_RISK_CURRENT_MIGRATION_PATH,
                "migration_127_action_time_full_chain",
            ),
            (
                ACCOUNT_CAPACITY_SCOPE_MIGRATION_PATH,
                "migration_129_action_time_full_chain",
            ),
            (
                ACCOUNT_CLAIM_POLICY_EVENT_MIGRATION_PATH,
                "migration_130_action_time_full_chain",
            ),
            (
                ASSET_NEUTRAL_EXPAND_MIGRATION_PATH,
                "migration_131_action_time_full_chain",
            ),
        ):
            extension = _load_module(path, module_name)
            old_extension_op = extension.op
            extension.op = Operations(MigrationContext.configure(conn))
            try:
                extension.upgrade()
            finally:
                extension.op = old_extension_op
        seed.seed_runtime_control_state_foundation(conn)
        asset_neutral_backfill = _load_module(
            ASSET_NEUTRAL_BACKFILL_MIGRATION_PATH,
            "migration_132_action_time_full_chain",
        )
        _upgrade_module(conn, asset_neutral_backfill)
        # SQLite cannot ALTER an existing table to add migration 124's check
        # constraint. The unit fixture mirrors its two storage columns; the
        # PostgreSQL integration suite executes the real migration.
        conn.exec_driver_sql(
            "ALTER TABLE brc_runtime_capabilities_current "
            "ADD COLUMN proof_schema VARCHAR(128)"
        )
        conn.exec_driver_sql(
            "ALTER TABLE brc_runtime_capabilities_current "
            "ADD COLUMN proof_payload JSON"
        )
        # The sentinel fixture mirrors migration 125's policy-binding columns;
        # the migration-specific suite owns its constraints and adoption table.
        conn.exec_driver_sql(
            "ALTER TABLE brc_ticket_exit_policy_current "
            "ADD COLUMN binding_source VARCHAR(32) NOT NULL DEFAULT 'ticket'"
        )
        conn.exec_driver_sql(
            "ALTER TABLE brc_ticket_exit_policy_current "
            "ADD COLUMN adoption_event_id VARCHAR(192)"
        )
        action_time_reference = ActionTimeCertificationReferenceV2(
            stage="post_canary",
            target_runtime_head="a" * 40,
            certification_input_digest="sha256:" + "1" * 64,
            release_activation_outcome_id="process:test:release",
            release_activation_source_watermark="release:test:watermark",
            lane_source_watermarks=(
                LaneSourceWatermarkV1(
                    lane_scope_key="lane:test",
                    lane_identity_key="identity:test",
                    source_watermark="watermark:test",
                    process_outcome_id="process:test:lane",
                ),
            ),
            fact_snapshot_ids=("fact:test:one",),
            fact_set_digest="sha256:" + "2" * 64,
            fact_min_valid_until_ms=NOW_MS + 120_000,
            deploy_nonce="test-deploy-nonce",
        )
        proof = LifecycleMutationEnablementProof(
            target_runtime_head="a" * 40,
            lane_identity_digest="sha256:" + "3" * 64,
            action_time_certification_ref=action_time_reference.certification_ref(),
            action_time_certification_payload=action_time_reference,
            certification_projection_digest="sha256:" + "4" * 64,
        )
        enabled = set_lifecycle_mutation_capability(
            conn,
            enabled=True,
            certification_ref=proof.lifecycle_certification_ref(),
            now_ms=NOW_MS - 1,
            proof=proof,
        )
        assert enabled["status"] == "ready"
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
def test_six_event_specs_across_all_active_scopes_reach_disabled_smoke_from_production_shape(
    pg_control_connection,
    monkeypatch,
    strategy_group_id: str,
    symbol: str,
    side: str,
):
    signal_summary, last_price = _evaluator_signal_summary(
        strategy_group_id=strategy_group_id,
        symbol=symbol,
        side=side,
    )
    payloads = _run_raw_pg_input_to_runtime_safety(
        pg_control_connection,
        monkeypatch,
        strategy_group_id=strategy_group_id,
        symbol=symbol,
        side=side,
        fact_values={"last_price": last_price},
        signal_summary=signal_summary,
    )

    public_values = _fact_values_for_surface(
        pg_control_connection,
        strategy_group_id=strategy_group_id,
        symbol=symbol,
        side=side,
        fact_surface="pretrade_public",
    )
    assert "last_price" not in public_values
    assert "entry_reference_price" not in public_values
    assert "mark_price" not in public_values
    assert set(public_values["facts"]) >= {
        "mark_price",
        "bid_price",
        "ask_price",
        "qty_step",
        "min_notional",
    }
    action_values = _fact_values_for_surface(
        pg_control_connection,
        strategy_group_id=strategy_group_id,
        symbol=symbol,
        side=side,
        fact_surface="action_time",
    )
    assert action_values["execution_pricing"]["entry_reference_kind"] == (
        "best_ask" if side == "long" else "best_bid"
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
    budget = pg_control_connection.execute(
        text(
            """
            SELECT intended_qty, risk_at_stop
            FROM brc_budget_reservations
            WHERE ticket_id = :ticket_id
            """
        ),
        {"ticket_id": str(payloads["ticket"]["ticket_id"])},
    ).mappings().one()
    reserved_qty = Decimal(str(budget["intended_qty"]))
    assert reserved_qty > 0
    assert Decimal(str(budget["risk_at_stop"])) > 0
    assert Decimal(submit_payload["submit_request"]["amount"]) == reserved_qty
    assert Decimal(submit_payload["submit_request"]["orders"][0]["amount"]) == reserved_qty
    assert Decimal(submit_payload["submit_request"]["orders"][1]["amount"]) == reserved_qty

    assert _count(pg_control_connection, "brc_live_signal_events") == 1
    assert _count(pg_control_connection, "brc_promotion_candidates") == 1
    assert _count(pg_control_connection, "brc_action_time_lane_inputs") == 1
    assert _count(pg_control_connection, "brc_action_time_tickets") == 1
    assert _finalgate_ready_event_count(pg_control_connection) == 1
    assert _count(pg_control_connection, "brc_operation_layer_handoffs") == 1
    assert _count(pg_control_connection, "brc_runtime_safety_state_snapshots") == 1
    assert _count(pg_control_connection, "brc_ticket_bound_protected_submit_attempts") == 1


@pytest.mark.parametrize(
    (
        "strategy_group_id",
        "symbol",
        "side",
        "fact_key",
        "replacement",
    ),
    [
        ("CPM-RO-001", "ETHUSDT", "long", "reclaim_confirmed", None),
        ("MPG-001", "SOLUSDT", "long", "leader_strength_confirmed", None),
        ("MI-001", "AVAXUSDT", "long", "relative_strength_confirmed", None),
        ("SOR-001", "ETHUSDT", "long", "breakout_confirmed", None),
        ("SOR-001", "ETHUSDT", "short", "breakdown_confirmed", None),
        ("BRF2-001", "BTCUSDT", "short", "rally_high_reference", None),
        ("BRF2-001", "BTCUSDT", "short", "strong_uptrend_disable", True),
        ("BRF2-001", "BTCUSDT", "short", "strong_uptrend_disable", "unknown"),
    ],
)
def test_evaluator_typed_fact_transport_fails_closed_before_lane(
    pg_control_connection,
    strategy_group_id: str,
    symbol: str,
    side: str,
    fact_key: str,
    replacement,
):
    signal_summary, last_price = _evaluator_signal_summary(
        strategy_group_id=strategy_group_id,
        symbol=symbol,
        side=side,
    )
    observations = [
        dict(observation)
        for observation in signal_summary["fact_observations"]
        if replacement is not None or observation["fact_key"] != fact_key
    ]
    if replacement is not None:
        for observation in observations:
            if observation["fact_key"] == fact_key:
                observation["observed_value"] = replacement
    signal_summary["fact_observations"] = observations

    _insert_ready_fresh_signal(
        pg_control_connection,
        strategy_group_id,
        symbol,
        side,
        insert_action_time_fact=False,
        insert_signal=False,
        fact_values={"last_price": last_price},
    )
    signal_payload = _write_monitor_signal_summary_to_pg(
        pg_control_connection,
        strategy_group_id=strategy_group_id,
        symbol=symbol,
        side=side,
        signal_summary=signal_summary,
    )
    assert signal_payload["written_count"] == 1
    pg_control_connection.execute(text("DELETE FROM brc_pretrade_readiness_rows"))

    fact_payload = fact_materializer.materialize_action_time_fact_snapshots(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert fact_payload["status"] == "action_time_fact_snapshots_blocked"
    failed_facts = pg_control_connection.execute(
        text(
            """
            SELECT failed_facts
            FROM brc_runtime_fact_snapshots
            WHERE fact_surface = 'action_time'
            """
        )
    ).scalar_one()
    assert fact_key in json.loads(failed_facts)
    assert _count(pg_control_connection, "brc_action_time_lane_inputs") == 0


@pytest.mark.parametrize(
    ("strategy_group_id", "symbol", "side", "fact_key"),
    [
        ("CPM-RO-001", "ETHUSDT", "long", "reclaim_confirmed"),
        ("MPG-001", "SOLUSDT", "long", "leader_strength_confirmed"),
        ("MI-001", "AVAXUSDT", "long", "relative_strength_confirmed"),
        ("SOR-001", "ETHUSDT", "long", "breakout_confirmed"),
        ("SOR-001", "ETHUSDT", "short", "breakdown_confirmed"),
        ("BRF2-001", "BTCUSDT", "short", "rally_high_reference"),
    ],
)
def test_each_event_spec_stale_typed_fact_blocks_before_lane(
    pg_control_connection,
    strategy_group_id: str,
    symbol: str,
    side: str,
    fact_key: str,
):
    signal_summary, last_price = _evaluator_signal_summary(
        strategy_group_id=strategy_group_id,
        symbol=symbol,
        side=side,
    )
    for observation in signal_summary["fact_observations"]:
        if observation["fact_key"] == fact_key:
            observation["valid_until_ms"] = NOW_MS

    _insert_ready_fresh_signal(
        pg_control_connection,
        strategy_group_id,
        symbol,
        side,
        insert_action_time_fact=False,
        insert_signal=False,
        fact_values={"last_price": last_price},
    )
    _write_monitor_signal_summary_to_pg(
        pg_control_connection,
        strategy_group_id=strategy_group_id,
        symbol=symbol,
        side=side,
        signal_summary=signal_summary,
    )
    pg_control_connection.execute(text("DELETE FROM brc_pretrade_readiness_rows"))

    fact_payload = fact_materializer.materialize_action_time_fact_snapshots(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert fact_payload["status"] == "action_time_fact_snapshots_blocked"
    assert f"required_fact_missing:{fact_key}" in fact_payload["blockers"]
    assert _count(pg_control_connection, "brc_action_time_lane_inputs") == 0


def test_action_time_snapshot_does_not_outlive_typed_fact_observations(
    pg_control_connection,
):
    signal_summary, last_price = _evaluator_signal_summary(
        strategy_group_id="CPM-RO-001",
        symbol="ETHUSDT",
        side="long",
    )
    typed_valid_until_ms = NOW_MS + 30_000
    for observation in signal_summary["fact_observations"]:
        observation["valid_until_ms"] = typed_valid_until_ms

    _insert_ready_fresh_signal(
        pg_control_connection,
        "CPM-RO-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
        insert_signal=False,
        fact_values={"last_price": last_price},
    )
    _write_monitor_signal_summary_to_pg(
        pg_control_connection,
        strategy_group_id="CPM-RO-001",
        symbol="ETHUSDT",
        side="long",
        signal_summary=signal_summary,
    )
    pg_control_connection.execute(text("DELETE FROM brc_pretrade_readiness_rows"))

    fact_payload = fact_materializer.materialize_action_time_fact_snapshots(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert fact_payload["status"] == "action_time_fact_snapshots_materialized"
    assert pg_control_connection.execute(
        text(
            """
            SELECT valid_until_ms
            FROM brc_runtime_fact_snapshots
            WHERE fact_surface = 'action_time'
            """
        )
    ).scalar_one() == typed_valid_until_ms


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


@pytest.mark.asyncio
async def test_raw_pg_input_reaches_real_gateway_submit_boundary(
    pg_control_connection,
    monkeypatch,
):
    _arm_submit_decision_env(monkeypatch)
    payloads = _run_raw_pg_input_to_runtime_safety(
        pg_control_connection,
        monkeypatch,
        strategy_group_id="SOR-001",
        symbol="AVAXUSDT",
        side="short",
        fact_values={
            "opening_range_defined": True,
            "breakdown_confirmed": True,
            "opening_range_high_reference": "20",
            "last_price": "18",
        },
    )

    submit_mode_decision = protected_submit.materialize_ticket_bound_submit_mode_decision(
        pg_control_connection,
        ticket_id=str(payloads["ticket"]["ticket_id"]),
        operation_submit_command_id=str(
            payloads["handoff"]["operation_submit_command_id"]
        ),
        production_submit_execution_policy="armed",
        now_ms=NOW_MS + 6,
    )
    assert submit_mode_decision["decision"] == "real_gateway_action"
    assert submit_mode_decision["blockers"] == []

    prepared_submit = protected_submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=str(payloads["ticket"]["ticket_id"]),
        operation_submit_command_id=str(
            payloads["handoff"]["operation_submit_command_id"]
        ),
        submit_mode="real_gateway_action",
        now_ms=NOW_MS + 7,
    )
    assert prepared_submit["status"] == "submit_prepared"
    assert prepared_submit["submit_allowed"] is True
    assert prepared_submit["submit_mode_decision_id"] == (
        submit_mode_decision["submit_mode_decision_id"]
    )
    assert prepared_submit["exchange_write_called"] is False
    assert prepared_submit["order_created"] is False
    assert prepared_submit["order_lifecycle_called"] is False

    submit_orders = prepared_submit["submit_request"]["orders"]
    assert [order["order_role"] for order in submit_orders] == ["ENTRY", "SL", "TP1"]
    assert submit_orders[0]["gateway_side"] == "sell"
    assert submit_orders[0]["gateway_order_type"] == "market"
    assert submit_orders[0]["reduce_only"] is False
    assert submit_orders[1]["gateway_side"] == "buy"
    assert submit_orders[1]["reduce_only"] is True
    assert submit_orders[2]["gateway_side"] == "buy"
    assert submit_orders[2]["reduce_only"] is True

    gateway = _ExchangeWriteBoundaryGateway()
    order_repository = _InMemoryOrderRepository()
    monkeypatch.setattr(
        trading_api_module,
        "_runtime_exchange_submit_gateway",
        gateway,
        raising=False,
    )
    monkeypatch.setattr(
        trading_api_module,
        "_trading_console_pg_order_repo",
        order_repository,
        raising=False,
    )

    gateway_binding = await api_trading_console._runtime_exchange_submit_gateway_binding(
        trading_api_module
    )
    assert gateway_binding["status"] == "ready"
    assert gateway_binding["blockers"] == []

    pg_control_connection.commit()
    submit_result = await api_trading_console._execute_ticket_bound_real_gateway_submit(
        prepared_submit,
        engine=pg_control_connection.engine,
    )
    assert submit_result["status"] == "entry_submit_failed"
    assert submit_result["blockers"] == ["controlled_exchange_write_boundary"]
    assert submit_result["exchange_write_called"] is True
    assert submit_result["order_created"] is True
    assert submit_result["order_lifecycle_called"] is True
    assert submit_result["submitted_orders"] == []
    assert len(gateway.calls) == 1
    assert gateway.calls[0]["client_order_id"] == submit_orders[0]["client_order_id"]
    assert gateway.calls[0]["side"] == "sell"
    assert gateway.calls[0]["order_type"] == "market"
    assert gateway.calls[0]["reduce_only"] is False
    assert list(order_repository.orders) == [submit_orders[0]["local_order_id"]]

    recorded = protected_submit.record_ticket_bound_protected_submit_result(
        pg_control_connection,
        protected_submit_attempt_id=str(
            prepared_submit["protected_submit_attempt_id"]
        ),
        submit_result=submit_result,
        now_ms=NOW_MS + 8,
    )
    assert recorded["status"] == "submit_failed"
    assert recorded["exchange_write_called"] is True
    assert recorded["order_created"] is True
    assert recorded["order_lifecycle_called"] is True
    assert recorded["blockers"] == ["controlled_exchange_write_boundary"]

    attempt_row = pg_control_connection.execute(
        text(
            """
            SELECT status, submit_mode, exchange_write_called, order_created,
                   order_lifecycle_called
            FROM brc_ticket_bound_protected_submit_attempts
            WHERE protected_submit_attempt_id = :protected_submit_attempt_id
            """
        ),
        {
            "protected_submit_attempt_id": str(
                prepared_submit["protected_submit_attempt_id"]
            )
        },
    ).mappings().one()
    assert attempt_row["status"] == "submit_failed"
    assert attempt_row["submit_mode"] == "real_gateway_action"
    assert bool(attempt_row["exchange_write_called"]) is True
    assert bool(attempt_row["order_created"]) is True
    assert bool(attempt_row["order_lifecycle_called"]) is True


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
    _arm_submit_decision_env(monkeypatch)
    monkeypatch.setattr(publisher.time, "time", lambda: NOW_MS / 1000)
    payloads = run_ticket_bound_full_chain_simulation(
        pg_control_connection,
        FullChainSimulationInput(
            strategy_group_id=strategy_group_id,
            symbol=symbol,
            side=side,
            now_ms=NOW_MS,
        ),
        projection_publisher=lambda conn: (
            publisher.publish_runtime_control_current_projections(
                conn,
                target_runtime_head="a" * 40,
            )
        ),
    )

    assert payloads["submit_mode_decision"]["decision"] == "real_gateway_action"
    assert payloads["prepared_submit"]["status"] == "submit_prepared"
    assert payloads["prepared_submit"]["submit_mode_decision_id"] == (
        payloads["submit_mode_decision"]["submit_mode_decision_id"]
    )
    assert payloads["submitted"]["status"] == "submitted"
    assert payloads["protection"]["status"] == "position_protected"
    assert payloads["post_submit_pending"]["status"] == "reconciliation_pending"
    assert payloads["initial_scheduler"]["exchange_write_called"] is False
    assert payloads["final_scheduler"]["exchange_write_called"] is False
    assert payloads["final"]["status"] == "closed"
    assert payloads["final"]["reconciliation_state"] == "matched"
    assert payloads["final"]["settlement_state"] == "released"
    assert payloads["final"]["review_state"] == "recorded"
    assert payloads["lifecycle_decision"]["status"] == "lifecycle_closed"
    assert payloads["lifecycle_decision"]["phase"] == "closed"
    assert payloads["lifecycle_decision"]["control_state"] == "completed"
    assert payloads["lifecycle_decision"]["owner_state"] == "completed"
    assert payloads["authority_boundary"]["uses_mock_exchange_result"] is True
    assert payloads["authority_boundary"]["calls_exchange_write"] is False
    assert payloads["authority_boundary"]["uses_production_fill_projector"] is True
    assert (
        payloads["authority_boundary"]["uses_production_reconciliation_scheduler"]
        is True
    )

    assert _status(
        pg_control_connection,
        "brc_action_time_tickets",
        "ticket_id",
        str(payloads["ticket"]["ticket_id"]),
    ) == "closed"
    assert _status(
        pg_control_connection,
        "brc_operation_layer_handoffs",
        "operation_layer_handoff_id",
        str(payloads["handoff"]["operation_layer_handoff_id"]),
    ) == "submitted"
    assert _count(pg_control_connection, "brc_ticket_bound_post_submit_closures") == 1
    assert _count(pg_control_connection, "brc_ticket_bound_order_lifecycle_runs") == 1
    assert _count(pg_control_connection, "brc_ticket_bound_exit_protection_sets") == 1
    assert _count(pg_control_connection, "brc_ticket_bound_exit_protection_orders") == 2
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
    _arm_submit_decision_env(monkeypatch)
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
        projection_publisher=lambda conn: (
            publisher.publish_runtime_control_current_projections(
                conn,
                target_runtime_head="a" * 40,
            )
        ),
        scenario=scenario,
    )

    assert payloads["submit_mode_decision"]["decision"] == "real_gateway_action"
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
            "protection_degraded",
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
            ],
            None,
        ),
        "runner_submit_failed_before_old_sl_cancel": (
            "runner_mutation_failed",
            [
                "runner sl submit rejected by simulation",
                "runner_sl_exchange_order_id_missing",
                "runner_sl_submit_not_confirmed",
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
            "command_confirmed",
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
    replay_decision = lifecycle_decision_for_status(
        expected_lifecycle_status,
        blockers=expected_blockers,
    ).to_dict()
    assert payloads["lifecycle_decision"] == replay_decision

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

    assert signal_payload["status"] == "pg_live_signal_events_noop"
    assert signal_payload["written_count"] == 0
    assert signal_payload["signal_event_ids"] == []
    assert signal_payload["reason"] == "would_enter_signal_summary_missing"
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
    signal_summary: dict | None = None,
) -> dict[str, dict]:
    semantic_fact_values = dict(fact_values or {})
    last_price = semantic_fact_values.pop(
        "last_price",
        "100" if side == "long" else "99",
    )
    public_fact_values = _production_public_fact_values(
        side=side,
        last_price=last_price,
    )
    _insert_ready_fresh_signal(
        conn,
        strategy_group_id,
        symbol,
        side,
        insert_action_time_fact=False,
        insert_signal=False,
        fact_values=public_fact_values,
    )
    observed_at = datetime.fromtimestamp(
        (NOW_MS - 1000) / 1000,
        tz=timezone.utc,
    ).isoformat()
    write_account_safe_fact_snapshots(
        conn,
        artifact={
            "generated_at_utc": observed_at,
            "source_status": "unit_raw_signed_response",
            "checks": {
                "account_safe_facts_ready": True,
                "account_safe": True,
                "account_trade_permission": True,
                "open_orders_clear": True,
                "active_position_or_open_order_clear": True,
                "action_time_available_balance": True,
                "source_signed_get_only": True,
                "source_exchange_write_called": False,
                "source_order_created": False,
            },
            "facts": {
                "total_wallet_balance": "100",
                "available_balance": "100",
                "exchange_max_leverage_by_symbol": {symbol: 100},
            },
            "account_mode": {
                "status": "fresh",
                "account_id": "owner-subaccount-runtime-v0",
                "exchange_id": "binance_usdm",
                "runtime_profile_id": "owner-runtime-console-v1",
                "account_mode": "one_way",
                "dual_side_position": False,
                "position_mode_safe": True,
                "observed_at": observed_at,
                "source": "binance_usdm_signed_get:/fapi/v1/positionSide/dual",
            },
        },
        source_ref="unit:signed-account-response",
    )
    signal_payload = _write_monitor_signal_summary_to_pg(
        conn,
        strategy_group_id=strategy_group_id,
        symbol=symbol,
        side=side,
        signal_summary=signal_summary,
        fact_values=semantic_fact_values,
    )
    assert signal_payload["status"] == "pg_live_signal_events_written", signal_payload
    assert signal_payload["written_count"] == 1
    conn.execute(text("DELETE FROM brc_pretrade_readiness_rows"))

    monkeypatch.setattr(publisher.time, "time", lambda: NOW_MS / 1000)
    sequence_payload = materialize_action_time_ticket_sequence(
        conn,
        now_ms=NOW_MS,
        projection_publisher=publisher.publish_action_time_pretrade_readiness,
        completion_clock_ms=lambda: NOW_MS + 2,
    )
    assert sequence_payload["status"] == "action_time_ticket_sequence_committed", {
        "status": sequence_payload.get("status"),
        "blockers": sequence_payload.get("blockers"),
        "promotion": sequence_payload.get("promotion"),
        "ticket": sequence_payload.get("ticket"),
    }
    fact_payload = sequence_payload["fact"]
    readiness_projection_payload = sequence_payload["projection"]
    lane_payload = sequence_payload["promotion"]
    ticket_payload = sequence_payload["ticket"]
    ticket_payload = bind_simulation_ticket_exposure_episode(conn, ticket_payload)
    assert fact_payload["status"] == "action_time_fact_snapshots_materialized"
    assert fact_payload["materialized_count"] == 1
    assert fact_payload["blocked_count"] == 0
    assert readiness_projection_payload["status"] == (
        "action_time_pretrade_readiness_published"
    )
    assert lane_payload["status"] == "promotion_action_time_lane_created"
    assert lane_payload["strategy_group_id"] == strategy_group_id
    assert lane_payload["symbol"] == symbol
    assert lane_payload["side"] == side
    assert lane_payload["forbidden_effects"] == lane_materializer.FORBIDDEN_EFFECTS

    assert ticket_payload["status"] == "action_time_ticket_created"
    assert ticket_payload["strategy_group_id"] == strategy_group_id
    assert ticket_payload["symbol"] == symbol
    assert ticket_payload["side"] == side
    assert ticket_payload["forbidden_effects"] == ticket_materializer.FORBIDDEN_EFFECTS

    projection_payload = publisher.publish_runtime_control_current_projections(
        conn,
        target_runtime_head="a" * 40,
    )
    assert projection_payload["status"] == "current_projections_published"

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
        "sequence": sequence_payload,
        "fact": fact_payload,
        "readiness_projection": readiness_projection_payload,
        "projection": projection_payload,
        "lane": lane_payload,
        "ticket": ticket_payload,
        "finalgate": finalgate_payload,
        "handoff": handoff_payload,
        "safety": safety_payload,
    }


def _production_public_fact_values(*, side: str, last_price) -> dict:
    entry = Decimal(str(last_price))
    spread = Decimal("0.01")
    bid = entry if side == "short" else entry - spread
    ask = entry if side == "long" else entry + spread
    return {
        "public_facts_ready": True,
        "exchange_contract_exists": True,
        "mark_price_fresh": True,
        "funding_not_extreme": True,
        "spread_ok": True,
        "min_notional_ok": True,
        "qty_step_ok": True,
        "leverage_available": True,
        "facts": {
            "mark_price": str(entry),
            "bid_price": str(bid),
            "ask_price": str(ask),
            "min_qty": "0.001",
            "qty_step": "0.001",
            "min_notional": "5",
            "contract_status": "TRADING",
            "contract_type": "PERPETUAL",
        },
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
    signal_summary: dict | None = None,
    fact_values: dict | None = None,
) -> dict:
    summary = signal_summary
    if summary is None:
        required_fact_keys = {
            str(row["fact_key"])
            for row in conn.execute(
                text(
                    """
                    SELECT rf.fact_key
                    FROM brc_strategy_group_candidate_scope c
                    JOIN brc_candidate_scope_event_bindings b
                      ON b.candidate_scope_id = c.candidate_scope_id
                     AND b.status = 'active'
                    JOIN brc_strategy_event_required_facts rf
                      ON rf.event_spec_id = b.event_spec_id
                     AND rf.status = 'current'
                     AND rf.required_for_promotion = true
                    WHERE c.strategy_group_id = :strategy_group_id
                      AND c.symbol = :symbol
                      AND c.side = :side
                      AND c.status = 'active'
                    """
                ),
                {
                    "strategy_group_id": strategy_group_id,
                    "symbol": symbol,
                    "side": side,
                },
            ).mappings()
        }
        observed_values = fact_values or {}
        summary = {
            "signal_type": "would_enter",
            "signal_grade": "trial_grade_signal",
            "required_execution_mode": "trial_live",
            "side": side,
            "confidence": "0.90",
            "reason_codes": ["constructed_monitor_signal_summary"],
            "trigger_candle_close_time_ms": NOW_MS - 60_000,
            "time_authority": "trigger_candle_close_time_ms",
            "fact_observations": [
                {
                    "fact_key": key,
                    "observed_value": observed_values[key],
                    "observed_at_ms": NOW_MS - 60_000,
                    "valid_until_ms": NOW_MS + 600_000,
                    "source_ref": f"unit:evaluator:{strategy_group_id}:{key}",
                }
                for key in sorted(required_fact_keys)
                if key in observed_values
            ],
        }
    summary = dict(summary)
    # ``_evaluator_signal_summary`` exercises the lower-level evaluator, whose
    # successful state is ``ready_for_semantic_binding``.  The runtime API
    # subsequently resolves that result against the typed lane and emits the
    # detector decision consumed here: ``event_satisfied``.  This PG fixture
    # starts at that runtime-lane boundary, not at the lower evaluator layer.
    summary["evaluation_status"] = "event_satisfied"
    if summary.get("evaluated_at_ms") is None:
        summary["evaluated_at_ms"] = NOW_MS - 60_000
    if summary.get("valid_until_ms") is None:
        summary["valid_until_ms"] = NOW_MS + 600_000
    lane_identity = _runtime_lane_identity_for_registered_scope(
        conn,
        strategy_group_id=strategy_group_id,
        symbol=symbol,
        side=side,
    )
    runtime_instance_id = (
        lane_identity.runtime_instance_id
        if lane_identity is not None
        else f"unregistered:{strategy_group_id}:{symbol}:{side}"
    )
    runtime_summary = {
        "runtime_instance_id": runtime_instance_id,
        "strategy_family_id": strategy_group_id,
        "strategy_family_version_id": f"test-evaluator:{strategy_group_id}:v1",
        "status": "waiting_for_signal",
        "signal_summary": summary,
        "can_materialize_live_signal_event": lane_identity is not None,
    }
    if lane_identity is not None:
        runtime_summary["lane_identity"] = lane_identity.model_dump(mode="json")
    runtime_active_observation_monitor.write_runtime_detector_decisions_to_pg(
        {
            "runtime_summaries": [runtime_summary],
        },
        database_url="unused://pg-control-test",
        allow_non_postgres_for_test=True,
        now_ms=NOW_MS,
        conn=conn,
    )
    return runtime_active_observation_monitor.write_runtime_signal_summaries_to_pg(
        {
            "runtime_summaries": [runtime_summary],
        },
        database_url="unused://pg-control-test",
        allow_non_postgres_for_test=True,
        now_ms=NOW_MS,
        conn=conn,
    )


def _runtime_lane_identity_for_registered_scope(
    conn,
    *,
    strategy_group_id: str,
    symbol: str,
    side: str,
) -> RuntimeLaneIdentity | None:
    row = conn.execute(
        text(
            """
            SELECT c.candidate_scope_id,
                   c.strategy_group_id,
                   c.symbol,
                   c.exchange_instrument_id,
                   c.asset_class,
                   c.side,
                   c.policy_current_id,
                   r.runtime_scope_binding_id,
                   r.runtime_profile_id,
                   b.binding_id AS candidate_scope_event_binding_id,
                   b.event_spec_id,
                   e.strategy_group_version_id,
                   e.event_spec_version,
                   e.event_id,
                   e.timeframe,
                   e.time_authority
            FROM brc_strategy_group_candidate_scope c
            JOIN brc_runtime_scope_bindings r
              ON r.candidate_scope_id = c.candidate_scope_id
             AND r.status = 'active'
            JOIN brc_candidate_scope_event_bindings b
              ON b.candidate_scope_id = c.candidate_scope_id
             AND b.status = 'active'
            JOIN brc_strategy_side_event_specs e
              ON e.event_spec_id = b.event_spec_id
             AND e.status = 'current'
            WHERE c.strategy_group_id = :strategy_group_id
              AND c.symbol = :symbol
              AND c.side = :side
              AND c.status = 'active'
            """
        ),
        {
            "strategy_group_id": strategy_group_id,
            "symbol": symbol,
            "side": side,
        },
    ).mappings().one_or_none()
    if row is None:
        return None
    runtime_instance_id = f"test-runtime:{row['candidate_scope_id']}"
    return RuntimeLaneIdentity(
        candidate_scope_id=str(row["candidate_scope_id"]),
        candidate_scope_event_binding_id=str(
            row["candidate_scope_event_binding_id"]
        ),
        runtime_scope_binding_id=str(row["runtime_scope_binding_id"]),
        runtime_instance_id=runtime_instance_id,
        runtime_profile_id=str(row["runtime_profile_id"]),
        policy_current_id=str(row["policy_current_id"]),
        strategy_group_id=str(row["strategy_group_id"]),
        strategy_group_version_id=str(row["strategy_group_version_id"]),
        symbol=str(row["symbol"]),
        exchange_instrument_id=str(row["exchange_instrument_id"]),
        asset_class=str(row["asset_class"]),
        side=str(row["side"]),
        event_spec_id=str(row["event_spec_id"]),
        event_spec_version=str(row["event_spec_version"]),
        event_id=str(row["event_id"]),
        timeframe=str(row["timeframe"]),
        time_authority=str(row["time_authority"]),
    )


def _evaluator_signal_summary(
    *,
    strategy_group_id: str,
    symbol: str,
    side: str,
) -> tuple[dict, str]:
    if strategy_group_id == "CPM-RO-001":
        signal_input = _signal_input(
            family_id=strategy_group_id,
            version_id="CPM-RO-001-v0",
            one_hour=_cpm_long_1h(),
            four_hour=_cpm_up_context_4h(),
        )
        last_price = "105"
    elif strategy_group_id == "MPG-001":
        signal_input = _signal_input(
            family_id=strategy_group_id,
            version_id="MPG-001-v0",
            one_hour=_mpg_long_1h(),
            four_hour=_cpm_up_context_4h(),
            comparative_strength_snapshot=_comparative_for_symbol(
                _comparative_snapshot(),
                strategy_group_id=strategy_group_id,
                symbol=symbol,
            ),
        )
        last_price = "107"
    elif strategy_group_id == "MI-001":
        signal_input = _signal_input(
            family_id=strategy_group_id,
            version_id="MI-001-v0",
            one_hour=_mi_impulse_1h(),
            comparative_strength_snapshot=_comparative_for_symbol(
                _mi_comparative_snapshot(),
                strategy_group_id=strategy_group_id,
                symbol=symbol,
            ),
        )
        last_price = "106"
    elif strategy_group_id == "SOR-001":
        signal_input = _signal_input(
            family_id=strategy_group_id,
            version_id="SOR-001-v0",
            one_hour=_sor_session_15m(side=side),
            four_hour=None,
            primary_timeframe="15m",
        )
        last_price = "103" if side == "long" else "97"
    elif strategy_group_id == "BRF2-001":
        signal_input = _signal_input(
            family_id=strategy_group_id,
            version_id="BRF2-001-v0",
            one_hour=_bear_rally_failure_1h(),
            four_hour=_down_context_4h(),
        )
        last_price = "106"
    else:
        raise AssertionError(f"unexpected active StrategyGroup: {strategy_group_id}")

    trigger_ms = NOW_MS - 60_000
    market_snapshot = signal_input.market_snapshot.model_copy(
        update={
            "symbol": symbol,
            "timestamp_ms": trigger_ms,
            "last_price": Decimal(last_price),
            "mark_price": Decimal(last_price),
        }
    )
    comparative = signal_input.comparative_strength_snapshot
    if comparative is not None:
        comparative = comparative.model_copy(
            update={
                "trigger_candle_close_time_ms": trigger_ms,
                "observed_at_ms": trigger_ms,
                "valid_until_ms": trigger_ms + 3_600_000,
            }
        )
    signal_input = signal_input.model_copy(
        update={
            "evaluation_id": f"eval:{strategy_group_id}:{symbol}:{side}",
            "symbol": symbol,
            "timestamp_ms": trigger_ms,
            "trigger_candle_close_time_ms": trigger_ms,
            "market_snapshot": market_snapshot,
            "comparative_strength_snapshot": comparative,
        }
    )
    evaluation = RuntimeStrategySignalEvaluationService().evaluate(signal_input)
    assert (
        evaluation.status
        == RuntimeStrategySignalEvaluationStatus.READY_FOR_SEMANTIC_BINDING
    )
    assert evaluation.output is not None
    assert evaluation.output.side.value == side
    assert evaluation.output.fact_observations

    summary = runtime_active_observation_monitor._signal_summary(
        {
            "latest_artifact": {
                "observation_payload": {
                    "signal_artifact": {
                        "evaluation_result": evaluation.model_dump(mode="json")
                    }
                }
            }
        }
    )
    return summary, last_price


def _comparative_for_symbol(
    snapshot,
    *,
    strategy_group_id: str,
    symbol: str,
):
    candidate, peer = snapshot.members
    peer_symbol = "BTCUSDT" if symbol != "BTCUSDT" else "ETHUSDT"
    return snapshot.model_copy(
        update={
            "strategy_group_id": strategy_group_id,
            "universe_symbols": (symbol, peer_symbol),
            "members": (
                candidate.model_copy(update={"symbol": symbol}),
                peer.model_copy(update={"symbol": peer_symbol}),
            ),
        }
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


class _ExchangeWriteBoundaryGateway:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def place_order(self, **kwargs):
        self.calls.append(dict(kwargs))
        return SimpleNamespace(
            is_success=False,
            error_message="controlled_exchange_write_boundary",
            error_code="CONTROLLED_EXCHANGE_WRITE_BOUNDARY",
        )

    async def fetch_ticker_price(self, *_args, **_kwargs):
        raise AssertionError("fetch_ticker_price is not part of submit boundary test")

    async def get_market_info(self, *_args, **_kwargs):
        raise AssertionError("get_market_info is not part of submit boundary test")

    async def cancel_order(self, *_args, **_kwargs):
        raise AssertionError("cancel_order is not part of submit boundary test")

    async def fetch_open_orders(self, *_args, **_kwargs):
        raise AssertionError("fetch_open_orders is not part of submit boundary test")

    async def fetch_order(self, *_args, **_kwargs):
        raise AssertionError("fetch_order is not part of submit boundary test")

    async def fetch_positions(self, *_args, **_kwargs):
        raise AssertionError("fetch_positions is not part of submit boundary test")

    async def fetch_my_trades(self, *_args, **_kwargs):
        raise AssertionError("fetch_my_trades is not part of submit boundary test")


class _InMemoryOrderRepository:
    def __init__(self) -> None:
        self.orders: dict[str, object] = {}

    async def save(self, order):
        self.orders[order.id] = order
        return order

    async def get_order(self, order_id: str):
        return self.orders.get(order_id)
