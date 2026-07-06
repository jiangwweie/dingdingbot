from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/publish_runtime_control_current_projections.py"
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


def _seeded_engine():
    migration = _load_module(MIGRATION_PATH, "migration_086_projection_publish")
    seed = _load_module(SEED_PATH, "seed_projection_publish")
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


def test_publish_current_projections_persists_readiness_goal_and_snapshots(tmp_path: Path):
    module = _load_module(SCRIPT_PATH, "publish_runtime_control_current_projections")
    engine = _seeded_engine()
    try:
        with engine.begin() as conn:
            report = module.publish_runtime_control_current_projections(
                conn,
                report_dir=tmp_path / "reports",
                runtime_monitor_dir=tmp_path / "runtime-monitor",
                release_manifest=tmp_path / ".brc-release-manifest.json",
                output_paths={
                    "candidate_pool": tmp_path / "candidate-pool.json",
                    "daily_live_enablement_table": tmp_path / "daily-table.json",
                    "goal_status": tmp_path / "goal-status.json",
                },
            )
            readiness_count = conn.execute(
                sa.text("SELECT COUNT(*) FROM brc_pretrade_readiness_rows")
            ).scalar_one()
            goal_count = conn.execute(
                sa.text("SELECT COUNT(*) FROM brc_goal_status_current")
            ).scalar_one()
            current_snapshot_count = conn.execute(
                sa.text(
                    "SELECT COUNT(*) FROM brc_control_read_model_snapshots "
                    "WHERE is_current = true"
                )
            ).scalar_one()
            projection_run_count = conn.execute(
                sa.text(
                    "SELECT COUNT(*) FROM brc_projection_runs "
                    "WHERE projection_run_id LIKE 'projection:%'"
                )
            ).scalar_one()

        assert report["status"] == "current_projections_published"
        assert readiness_count == report["candidate_pool"]["symbol_readiness_count"]
        assert readiness_count > 0
        assert goal_count == 1
        assert current_snapshot_count == 3
        assert projection_run_count == 3
        assert report["safety_invariants"]["calls_exchange_write"] is False
    finally:
        engine.dispose()


def test_publish_current_projections_keeps_one_current_snapshot_per_model(tmp_path: Path):
    module = _load_module(SCRIPT_PATH, "publish_runtime_control_current_projections")
    engine = _seeded_engine()
    try:
        with engine.begin() as conn:
            module.publish_runtime_control_current_projections(
                conn,
                report_dir=tmp_path / "reports",
                runtime_monitor_dir=tmp_path / "runtime-monitor",
            )
            module.publish_runtime_control_current_projections(
                conn,
                report_dir=tmp_path / "reports",
                runtime_monitor_dir=tmp_path / "runtime-monitor",
            )
            rows = conn.execute(
                sa.text(
                    "SELECT model_type, COUNT(*) AS current_count "
                    "FROM brc_control_read_model_snapshots "
                    "WHERE is_current = true GROUP BY model_type"
                )
            ).mappings().all()

        assert {row["model_type"]: row["current_count"] for row in rows} == {
            "candidate_pool": 1,
            "daily_live_enablement_table": 1,
            "goal_status": 1,
        }
    finally:
        engine.dispose()
