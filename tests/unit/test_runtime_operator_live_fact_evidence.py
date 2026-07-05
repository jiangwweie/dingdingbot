from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

from scripts import build_runtime_operator_live_fact_evidence as module
from scripts.build_runtime_operator_live_fact_evidence import (
    build_operator_live_fact_evidence,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py"
)
SEED_PATH = REPO_ROOT / "scripts/seed_runtime_control_state_foundation.py"
PG_FACT_HELPER_PATH = REPO_ROOT / "scripts/runtime_pg_fact_snapshots.py"


def _load_file_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    loaded = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


def _seed_runtime_control_state_db(tmp_path: Path) -> str:
    migration = _load_file_module(MIGRATION_PATH, "migration_086_operator_fact")
    seed = _load_file_module(SEED_PATH, "seed_operator_fact")
    database_url = f"sqlite:///{tmp_path / 'runtime-control-state.db'}"
    engine = create_engine(database_url)
    with engine.begin() as conn:
        old_op = migration.op
        migration.op = Operations(MigrationContext.configure(conn))
        try:
            migration.upgrade()
        finally:
            migration.op = old_op
        seed.seed_runtime_control_state_foundation(conn)
    engine.dispose()
    return database_url


def _write_account_facts_to_pg(database_url: str) -> None:
    helper = _load_file_module(PG_FACT_HELPER_PATH, "operator_fact_pg_helper")
    artifact = {
        "generated_at_utc": "2026-07-05T00:00:00+00:00",
        "status": "runtime_account_safe_facts_ready",
        "source_status": "ready",
        "checks": {
            "account_safe_facts_ready": True,
            "account_safe": True,
            "private_action_time_facts_ready": True,
            "active_position_or_open_order_clear": True,
            "action_time_available_balance": True,
            "open_orders_clear": True,
            "account_trade_permission": True,
            "source_signed_get_only": True,
            "source_exchange_write_called": False,
            "source_order_created": False,
        },
        "facts": {
            "active_position_or_open_order_clear": True,
            "action_time_available_balance": True,
        },
        "blockers": [],
    }
    engine = create_engine(database_url)
    try:
        with engine.begin() as conn:
            helper.write_account_safe_fact_snapshots(
                conn,
                artifact=artifact,
                source_ref="unit:operator-live-facts",
                source_kind="unit_test",
            )
    finally:
        engine.dispose()


def _complete_account() -> dict:
    return {
        "scope": "read_only_account_facts",
        "source": "tokyo_readonly",
        "timestamp_ms": 1,
    }


def _monitor_artifact(**overrides) -> dict:
    artifact = {
        "active_position_present": True,
        "symbol": "BNB/USDT:USDT",
        "side": "long",
        "local_active_position_count": 1,
        "exchange_active_position_count": 1,
        "local_open_order_count": 2,
        "exchange_open_stop_order_count": 1,
        "protection_status": "hard_stop_present",
        "sl_protection_present": True,
        "tp_protection_present": False,
        "hard_stop_boundary_present": True,
        "can_continue_holding": True,
        "budget_reserved": "0.10",
    }
    artifact.update(overrides)
    return {
        "scope": "runtime_live_position_monitor",
        "status": "holding_with_hard_stop",
        "artifact": artifact,
        "safety_invariants": {
            "exchange_read_only": True,
            "exchange_write_called": False,
            "order_created": False,
            "runtime_state_mutated": False,
        },
    }


def _finalize_artifact(**gate_overrides) -> dict:
    next_gate = {
        "status": "blocked",
        "attempts_remaining": 1,
        "budget_remaining": "0.90",
        "blockers": ["runtime_max_active_positions_in_use"],
    }
    next_gate.update(gate_overrides)
    return {
        "scope": "runtime_post_submit_finalize_probe",
        "status": "finalized_next_attempt_blocked",
        "post_submit_finalize_payload": {
            "status": "finalized_next_attempt_blocked",
            "next_attempt_gate": next_gate,
        },
        "safety_invariants": {"exchange_write_called": False},
    }


def test_operator_live_fact_evidence_waits_on_active_position_slot() -> None:
    packet = build_operator_live_fact_evidence(
        runtime_instance_id="runtime-1",
        account_facts=_complete_account(),
        live_position_monitor=_monitor_artifact(),
        post_submit_finalize=_finalize_artifact(),
        next_attempt_release={
            "scope": "runtime_next_attempt_release_from_reports",
            "status": "waiting_for_position_resolution",
            "release_evidence": {"status": "waiting_for_position_resolution"},
        },
        next_attempt_gate_classification={
            "scope": "runtime_next_attempt_gate_blocker_classification",
            "status": "gate_blocked_by_active_position_slot",
            "blockers": ["next_attempt_gate_blocked"],
        },
        generated_at_ms=1,
    )

    assert packet["status"] == "waiting_for_position_resolution"
    assert packet["fact_coverage"]["account"]["status"] == "present"
    assert packet["fact_coverage"]["position"]["active_position_present"] is True
    assert packet["next_attempt_gate_state"]["legacy_authorization_replay_allowed"] is False
    assert "operator_command_plan" not in packet
    assert packet["operator_live_fact_plan"]["places_order"] is False
    assert packet["safety_invariants"]["operator_live_fact_projection_only"] is True
    assert "packet_only" not in packet["safety_invariants"]
    assert packet["safety_invariants"]["no_forbidden_live_side_effects"] is True


def test_operator_live_fact_evidence_waits_on_lifecycle_active_slot_blocker() -> None:
    packet = build_operator_live_fact_evidence(
        runtime_instance_id="runtime-1",
        account_facts=_complete_account(),
        live_position_monitor=_monitor_artifact(
            attempts_remaining=2,
            budget_remaining="8.76",
        ),
        active_position_resolution={
            "scope": "runtime_active_position_resolution_from_reports",
            "status": "position_lifecycle_hold_or_owner_close_ready",
            "artifact": {
                "status": "position_lifecycle_hold_or_owner_close_ready",
                "runtime_instance_id": "runtime-1",
                "recommended_review_checkpoint": "continue_read_only_position_monitoring",
            },
            "blockers": [
                "next_attempt_gate_blocked",
                "runtime_max_active_positions_in_use",
            ],
            "warnings": ["missing_tp_protection_right_tail_exit_not_mounted"],
            "safety_invariants": {"no_forbidden_live_side_effects": True},
        },
        next_attempt_release={
            "scope": "runtime_live_continuation_refresh_flow",
            "status": "continuation_refresh_monitor_position_or_owner_close",
            "blockers": ["runtime-1:next_attempt_gate_blocked"],
        },
        generated_at_ms=1,
    )

    assert packet["status"] == "waiting_for_position_resolution"
    assert packet["fact_coverage"]["budget"]["attempts_remaining"] == 2
    assert packet["fact_coverage"]["budget"]["budget_remaining"] == "8.76"
    assert packet["operator_live_fact_plan"]["next_step"] == (
        "continue_read_only_position_monitoring_until_flat_or_reviewed"
    )


def test_operator_live_fact_evidence_ready_requires_fresh_signal_and_authorization() -> None:
    monitor = _monitor_artifact(
        active_position_present=False,
        local_active_position_count=0,
        exchange_active_position_count=0,
        local_open_order_count=0,
        exchange_open_stop_order_count=0,
        protection_status="flat_no_open_protection_required",
        sl_protection_present=False,
        tp_protection_present=False,
        hard_stop_boundary_present=False,
        can_continue_holding=False,
    )
    packet = build_operator_live_fact_evidence(
        runtime_instance_id="runtime-1",
        account_facts=_complete_account(),
        live_position_monitor=monitor,
        post_submit_finalize=_finalize_artifact(
            status="ready_for_fresh_signal",
            blockers=[],
        ),
        next_attempt_release={
            "scope": "runtime_next_attempt_release_from_reports",
            "status": "ready_for_strategy_signal",
            "release_evidence": {"status": "ready_for_strategy_signal"},
        },
        next_attempt_gate_classification={
            "scope": "runtime_next_attempt_gate_blocker_classification",
            "status": "gate_blocker_classification_no_next_attempt_gate_blocker",
        },
        generated_at_ms=1,
    )

    assert packet["status"] == "ready_for_strategy_signal"
    assert packet["next_attempt_gate_state"]["requires_fresh_strategy_signal"] is True
    assert packet["next_attempt_gate_state"]["requires_fresh_authorization_before_submit"] is True
    assert packet["next_attempt_gate_state"]["executable_submit_allowed_by_evidence"] is False
    assert packet["operator_live_fact_plan"]["next_step"] == "start_fresh_strategy_signal_observation"


def test_operator_live_fact_evidence_blocks_forbidden_effects() -> None:
    monitor = _monitor_artifact()
    monitor["safety_invariants"]["order_created"] = True

    packet = build_operator_live_fact_evidence(
        runtime_instance_id="runtime-1",
        account_facts=_complete_account(),
        live_position_monitor=monitor,
        post_submit_finalize=_finalize_artifact(),
        next_attempt_release={
            "scope": "runtime_next_attempt_release_from_reports",
            "status": "waiting_for_position_resolution",
            "release_evidence": {"status": "waiting_for_position_resolution"},
        },
        next_attempt_gate_classification={
            "scope": "runtime_next_attempt_gate_blocker_classification",
            "status": "gate_blocked_by_active_position_slot",
        },
        generated_at_ms=1,
    )

    assert packet["status"] == "blocked_forbidden_effect"
    assert packet["safety_invariants"]["no_forbidden_live_side_effects"] is False
    assert "live_position_monitor.safety_invariants.order_created" in packet[
        "safety_invariants"
    ]["forbidden_effects"]


def test_cli_rejects_removed_account_facts_file_arg(tmp_path: Path):
    with pytest.raises(SystemExit):
        module.main(
            [
                "--runtime-instance-id",
                "runtime-1",
                "--account-facts-json",
                str(tmp_path / "latest-account-safe-facts.json"),
            ]
        )


def test_cli_reads_account_facts_from_pg(tmp_path: Path, capsys):
    database_url = _seed_runtime_control_state_db(tmp_path)
    _write_account_facts_to_pg(database_url)
    output_path = tmp_path / "operator-live-fact-evidence.json"

    result = module.main(
        [
            "--runtime-instance-id",
            "runtime-1",
            "--database-url",
            database_url,
            "--allow-non-postgres-for-test",
            "--output-json",
            str(output_path),
        ]
    )

    assert result == 0
    packet = json.loads(output_path.read_text(encoding="utf-8"))
    assert packet["fact_coverage"]["account"]["status"] == "present"
    assert packet["safety_invariants"]["account_facts_source_mode"] == "db_backed"
    assert packet["safety_invariants"]["pg_called_by_builder"] is True
    assert packet["safety_invariants"]["reads_json_reports_only"] is False
    assert "account_facts_missing" not in packet["blockers"]
    assert capsys.readouterr().err == ""


def test_cli_blocks_when_pg_account_facts_missing(tmp_path: Path):
    database_url = _seed_runtime_control_state_db(tmp_path)
    output_path = tmp_path / "operator-live-fact-evidence.json"

    result = module.main(
        [
            "--runtime-instance-id",
            "runtime-1",
            "--database-url",
            database_url,
            "--allow-non-postgres-for-test",
            "--output-json",
            str(output_path),
        ]
    )

    assert result == 0
    packet = json.loads(output_path.read_text(encoding="utf-8"))
    assert packet["fact_coverage"]["account"]["status"] == "missing"
    assert "account_facts_missing" in packet["blockers"]
    assert "account_safe_fact_snapshot_missing" in packet["blockers"]
