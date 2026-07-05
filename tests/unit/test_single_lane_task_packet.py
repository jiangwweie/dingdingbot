from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from src.infrastructure.runtime_control_state_repository import (
    PgBackedRuntimeControlStateRepository,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
BUILDER_PATH = REPO_ROOT / "scripts" / "build_single_lane_task_packet.py"
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate_single_lane_task_packet.py"
MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py"
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


def _builder():
    return _load_module(BUILDER_PATH, "build_single_lane_task_packet")


def _validator():
    return _load_module(VALIDATOR_PATH, "validate_single_lane_task_packet")


@pytest.fixture()
def pg_control_connection():
    migration = _load_module(MIGRATION_PATH, "migration_086_single_lane")
    seed = _load_module(SEED_PATH, "seed_runtime_control_state_single_lane")
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


def _seed_runtime_control_db(db_path: Path) -> str:
    migration = _load_module(MIGRATION_PATH, "migration_086_single_lane_cli")
    seed = _load_module(SEED_PATH, "seed_runtime_control_state_single_lane_cli")
    database_url = f"sqlite:///{db_path}"
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


def _daily_table() -> dict:
    return {
        "schema": "brc.daily_live_enablement_table.v1",
        "status": "daily_live_enablement_table_ready",
        "rows": [
            {
                "strategy_group_id": "MPG-001",
                "symbol": "SOLUSDT",
                "side": "long",
                "stage": "armed",
                "chain_position": "replay_live_parity",
                "first_blocker": "watcher_tick_missing",
                "first_blocker_evidence": (
                    "output/runtime-monitor/latest-replay-live-parity-audit.json:"
                    "MPG-001/SOLUSDT blocker_class=watcher_tick_missing"
                ),
                "owner_action_required": "no",
                "next_engineering_action": (
                    "refresh_or_repair_watcher_public_fact_input"
                ),
                "stop_condition": (
                    "watcher/public facts tick is present for the selected lane"
                ),
                "closest_to_live_rank": 1,
                "authority_boundary": (
                    "daily_table_is_read_model; "
                    "no_finalgate_no_operation_layer_no_exchange_write"
                ),
            },
            {
                "strategy_group_id": "SOR-001",
                "symbol": "ETHUSDT",
                "side": "long",
                "stage": "armed",
                "chain_position": "action_time_boundary",
                "first_blocker": "action_time_boundary_not_reproduced",
                "first_blocker_evidence": "source",
                "owner_action_required": "no",
                "next_engineering_action": (
                    "repair_non_executing_action_time_rehearsal_path"
                ),
                "stop_condition": "candidate/auth boundary is reproduced",
                "closest_to_live_rank": 2,
                "authority_boundary": (
                    "daily_table_is_read_model; "
                    "no_finalgate_no_operation_layer_no_exchange_write"
                ),
            },
        ],
    }


def test_single_lane_packet_builds_from_pg_control_state_seed(pg_control_connection):
    repository = PgBackedRuntimeControlStateRepository(pg_control_connection)
    control_state = repository.read_control_state()

    packet = _builder().build_single_lane_task_packet_from_control_state(
        control_state,
        generated_at_utc="2026-07-04T00:00:00+00:00",
    )

    assert packet["schema"] == "brc.single_lane_task_packet.v1"
    assert packet["source_mode"] == "db_backed"
    assert packet["projection_target"] == "production_current"
    assert packet["source"] == "pg_runtime_control_state:daily_live_enablement_table"
    assert packet["control_state_watermark"]["table_counts"]["candidate_scope"] == 22
    assert packet["active_lane"]["strategy_group_id"] in {
        "CPM-RO-001",
        "MPG-001",
        "MI-001",
        "SOR-001",
        "BRF2-001",
    }
    assert packet["status"] in {
        "single_lane_task_packet_ready",
        "single_lane_task_packet_not_applicable_market_wait",
    }
    assert _validator().validate_single_lane_task_packet(packet) == []


def test_single_lane_packet_pg_cli_requires_pg_dsn_without_test_flag(tmp_path: Path):
    packet_json = tmp_path / "packet.json"
    packet_md = tmp_path / "packet.md"

    build = subprocess.run(
        [
            sys.executable,
            str(BUILDER_PATH),
            "--database-url",
            f"sqlite:///{tmp_path / 'runtime.db'}",
            "--output-json",
            str(packet_json),
            "--output-owner-progress",
            str(packet_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert build.returncode == 2
    assert "requires PostgreSQL DSN" in build.stderr
    assert not packet_json.exists()
    assert not packet_md.exists()


def test_single_lane_packet_pg_cli_round_trip(tmp_path: Path):
    database_url = _seed_runtime_control_db(tmp_path / "runtime.db")
    packet_json = tmp_path / "packet.json"
    packet_md = tmp_path / "packet.md"

    build = subprocess.run(
        [
            sys.executable,
            str(BUILDER_PATH),
            "--database-url",
            database_url,
            "--allow-non-postgres-for-test",
            "--output-json",
            str(packet_json),
            "--output-owner-progress",
            str(packet_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert build.returncode == 0, build.stdout + build.stderr
    packet = json.loads(packet_json.read_text(encoding="utf-8"))
    assert packet["source_mode"] == "db_backed"
    assert packet["source"] == "pg_runtime_control_state:daily_live_enablement_table"
    assert packet_md.exists()
    assert _validator().validate_single_lane_task_packet(packet) == []


def test_single_lane_packet_builds_from_rank_one_daily_row():
    packet = _builder().build_single_lane_task_packet(
        daily_table=_daily_table(),
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    assert packet["schema"] == "brc.single_lane_task_packet.v1"
    assert packet["status"] == "single_lane_task_packet_ready"
    assert packet["task_id"] == "P0-MPG-001-WATCHER-TICK-MISSING-CLOSURE"
    assert packet["active_lane"]["strategy_group_id"] == "MPG-001"
    assert packet["active_lane"]["symbol"] == "SOLUSDT"
    assert packet["first_blocker"] == "watcher_tick_missing"
    assert packet["source_rank"] == 1
    assert "output/runtime-monitor/latest-*.json" not in packet["allowed_files"]
    assert "scripts/build_replay_live_parity_audit.py" in packet["allowed_files"]
    assert _validator().validate_single_lane_task_packet(packet) == []


def test_single_lane_packet_validator_rejects_broad_output_glob():
    packet = _builder().build_single_lane_task_packet(
        daily_table=_daily_table(),
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )
    packet["allowed_files"].append("output/runtime-monitor/latest-*.json")

    errors = _validator().validate_single_lane_task_packet(packet)

    assert any("not glob" in error for error in errors)


def test_single_lane_packet_validator_rejects_exchange_authority():
    packet = _builder().build_single_lane_task_packet(
        daily_table=_daily_table(),
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )
    packet["safety_invariants"]["calls_exchange_write"] = True

    errors = _validator().validate_single_lane_task_packet(packet)

    assert any("calls_exchange_write" in error for error in errors)


def test_single_lane_packet_does_not_create_closure_task_for_market_blocker():
    table = _daily_table()
    rank_one = table["rows"][0]
    rank_one["first_blocker"] = "computed_not_satisfied"
    rank_one["next_engineering_action"] = "continue_observation_with_failed_fact_matrix"

    packet = _builder().build_single_lane_task_packet(
        daily_table=table,
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    assert packet["status"] == "single_lane_task_packet_not_applicable_market_wait"
    assert packet["task_id"] == "OBSERVE-MPG-001-COMPUTED-NOT-SATISFIED"
    assert not packet["task_id"].startswith("P0-")
    assert not packet["task_id"].endswith("-CLOSURE")
    assert "no engineering closure task is created" in packet["expected_state_change"]
    assert _validator().validate_single_lane_task_packet(packet) == []


def test_single_lane_packet_validator_rejects_market_blocker_closure_task():
    table = _daily_table()
    rank_one = table["rows"][0]
    rank_one["first_blocker"] = "market_wait_validated"
    packet = _builder().build_single_lane_task_packet(
        daily_table=table,
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )
    packet["status"] = "single_lane_task_packet_ready"
    packet["task_id"] = "P0-MPG-001-MARKET-WAIT-VALIDATED-CLOSURE"

    errors = _validator().validate_single_lane_task_packet(packet)

    assert any("market blocker" in error for error in errors)


def test_single_lane_packet_creates_preflight_task_for_action_time_ready_lane():
    table = _daily_table()
    rank_one = table["rows"][0]
    rank_one["chain_position"] = "action_time_boundary"
    rank_one["first_blocker"] = "action_time_preflight_ready"
    rank_one["next_engineering_action"] = (
        "prepare_non_executing_finalgate_preflight_input"
    )

    packet = _builder().build_single_lane_task_packet(
        daily_table=table,
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    assert packet["status"] == "single_lane_task_packet_ready"
    assert packet["task_id"] == "P0-MPG-001-ACTION-TIME-PREFLIGHT-INPUT"
    assert packet["next_action"] == "prepare_non_executing_finalgate_preflight_input"
    assert "non-executing FinalGate preflight input" in packet["expected_state_change"]
    assert packet["safety_invariants"]["calls_finalgate"] is False
    assert _validator().validate_single_lane_task_packet(packet) == []


@pytest.mark.parametrize(
    "legacy_args",
    [
        ["--allow-local-file-diagnostic"],
        ["--daily-table-json", "daily.json"],
    ],
)
def test_single_lane_packet_cli_rejects_legacy_file_inputs(
    legacy_args: list[str],
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.delenv("PG_DATABASE_URL", raising=False)
    packet_json = tmp_path / "packet.json"
    packet_md = tmp_path / "packet.md"

    build = subprocess.run(
        [
            sys.executable,
            str(BUILDER_PATH),
            *legacy_args,
            "--output-json",
            str(packet_json),
            "--output-owner-progress",
            str(packet_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert build.returncode == 2
    assert "unrecognized arguments" in build.stderr
    assert not packet_json.exists()
    assert not packet_md.exists()


def test_single_lane_packet_missing_rank_one_does_not_validate():
    table = _daily_table()
    table["rows"][0]["closest_to_live_rank"] = 2
    packet = _builder().build_single_lane_task_packet(
        daily_table=table,
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    errors = _validator().validate_single_lane_task_packet(packet)

    assert any("active_lane.strategy_group_id" in error for error in errors)


def test_single_lane_packet_cli_rejects_daily_table_json_even_without_diagnostic_flag(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.delenv("PG_DATABASE_URL", raising=False)
    daily_table = tmp_path / "daily-table.json"
    packet_json = tmp_path / "packet.json"
    packet_md = tmp_path / "packet.md"
    daily_table.write_text(json.dumps(_daily_table()), encoding="utf-8")

    build = subprocess.run(
        [
            sys.executable,
            str(BUILDER_PATH),
            "--daily-table-json",
            str(daily_table),
            "--output-json",
            str(packet_json),
            "--output-owner-progress",
            str(packet_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert build.returncode == 2
    assert "unrecognized arguments" in build.stderr
    assert not packet_json.exists()
    assert not packet_md.exists()


def test_single_lane_packet_pg_cli_requires_database_url_when_requested(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.delenv("PG_DATABASE_URL", raising=False)
    packet_json = tmp_path / "packet.json"
    packet_md = tmp_path / "packet.md"

    build = subprocess.run(
        [
            sys.executable,
            str(BUILDER_PATH),
            "--require-database-url",
            "--output-json",
            str(packet_json),
            "--output-owner-progress",
            str(packet_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert build.returncode == 2
    assert "PG_DATABASE_URL is required" in build.stderr
    assert not packet_json.exists()
    assert not packet_md.exists()
