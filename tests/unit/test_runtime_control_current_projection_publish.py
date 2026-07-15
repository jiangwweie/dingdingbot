from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
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
TEST_RUNTIME_HEAD = "a" * 40


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
                target_runtime_head=TEST_RUNTIME_HEAD,
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
            projection_heads = conn.execute(
                sa.text(
                    "SELECT DISTINCT code_version FROM brc_projection_runs "
                    "WHERE projection_run_id LIKE 'projection:%'"
                )
            ).scalars().all()
            snapshot_payloads = conn.execute(
                sa.text(
                    "SELECT payload FROM brc_control_read_model_snapshots "
                    "WHERE is_current = true"
                )
            ).scalars().all()
            output_path_count = conn.execute(
                sa.text(
                    "SELECT COUNT(*) FROM brc_control_read_model_snapshots "
                    "WHERE output_path IS NOT NULL"
                )
            ).scalar_one()

        assert report["status"] == "current_projections_published"
        assert readiness_count == report["candidate_pool"]["symbol_readiness_count"]
        assert readiness_count > 0
        assert goal_count == 1
        assert current_snapshot_count == 3
        assert projection_run_count == 3
        assert projection_heads == [TEST_RUNTIME_HEAD]
        assert {
            (
                json.loads(payload)
                if isinstance(payload, str)
                else dict(payload)
            )["code_version"]
            for payload in snapshot_payloads
        } == {TEST_RUNTIME_HEAD}
        assert output_path_count == 0
        assert report["safety_invariants"]["calls_exchange_write"] is False
        assert not (tmp_path / "candidate-pool.json").exists()
        assert not (tmp_path / "daily-table.json").exists()
        assert not (tmp_path / "goal-status.json").exists()
    finally:
        engine.dispose()


@pytest.mark.parametrize("runtime_head", ["", "current", "a" * 39, "g" * 40])
def test_publish_current_projections_rejects_non_exact_runtime_head(runtime_head):
    module = _load_module(
        SCRIPT_PATH,
        f"publish_runtime_control_current_projections_bad_head_{len(runtime_head)}",
    )
    engine = _seeded_engine()
    try:
        with engine.begin() as conn:
            with pytest.raises(
                ValueError,
                match="target_runtime_head_must_be_exact_full_git_sha",
            ):
                module.publish_runtime_control_current_projections(
                    conn,
                    target_runtime_head=runtime_head,
                )
    finally:
        engine.dispose()


def test_projection_runtime_head_validator_rejects_different_sha():
    module = _load_module(
        SCRIPT_PATH,
        "publish_runtime_control_current_projections_mismatched_head",
    )

    with pytest.raises(RuntimeError, match="current projection runtime head mismatch"):
        module._validate_projection_runtime_head(
            [{"model_type": "candidate_pool", "code_version": "b" * 40}],
            "a" * 40,
        )


def test_action_time_readiness_refresh_skips_owner_projection_snapshots():
    module = _load_module(
        SCRIPT_PATH,
        "publish_action_time_pretrade_readiness",
    )
    engine = _seeded_engine()
    try:
        with engine.begin() as conn:
            before_goal_count = conn.execute(
                sa.text("SELECT COUNT(*) FROM brc_goal_status_current")
            ).scalar_one()
            before_snapshot_count = conn.execute(
                sa.text("SELECT COUNT(*) FROM brc_control_read_model_snapshots")
            ).scalar_one()
            before_projection_run_count = conn.execute(
                sa.text("SELECT COUNT(*) FROM brc_projection_runs")
            ).scalar_one()
            report = module.publish_action_time_pretrade_readiness(conn)
            readiness_count = conn.execute(
                sa.text("SELECT COUNT(*) FROM brc_pretrade_readiness_rows")
            ).scalar_one()
            goal_count = conn.execute(
                sa.text("SELECT COUNT(*) FROM brc_goal_status_current")
            ).scalar_one()
            snapshot_count = conn.execute(
                sa.text("SELECT COUNT(*) FROM brc_control_read_model_snapshots")
            ).scalar_one()
            projection_run_count = conn.execute(
                sa.text("SELECT COUNT(*) FROM brc_projection_runs")
            ).scalar_one()

        assert report["status"] == "action_time_pretrade_readiness_published"
        assert readiness_count == report["published_row_count"]
        assert readiness_count > 0
        assert goal_count == before_goal_count
        assert snapshot_count == before_snapshot_count
        assert projection_run_count == before_projection_run_count
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
                target_runtime_head=TEST_RUNTIME_HEAD,
            )
            module.publish_runtime_control_current_projections(
                conn,
                target_runtime_head=TEST_RUNTIME_HEAD,
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


def test_publish_current_projections_uses_bounded_current_control_state(
    tmp_path: Path,
):
    module = _load_module(
        SCRIPT_PATH,
        "publish_runtime_control_current_projections_bounded_read",
    )
    engine = _seeded_engine()
    try:
        with engine.begin() as conn:
            for index in range(150):
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO brc_projection_runs (
                          projection_run_id, model_type, owner_projector,
                          code_version, source_mode, projection_target,
                          input_watermark, source_priority,
                          legacy_diagnostics_read,
                          legacy_diagnostics_affected_current,
                          started_at_ms, finished_at_ms, status, error_detail
                        ) VALUES (
                          :projection_run_id, 'candidate_pool',
                          'pg_candidate_pool_projector', 'old',
                          'db_backed', 'production_current', '{}', '[]',
                          false, false, :started_at_ms, :finished_at_ms,
                          'succeeded', NULL
                        )
                        """
                    ),
                    {
                        "projection_run_id": f"historical-projection:{index}",
                        "started_at_ms": 1_000 + index,
                        "finished_at_ms": 1_000 + index,
                    },
                )
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO brc_control_read_model_snapshots (
                          snapshot_id, model_type, payload, source_watermark,
                          owner_projector, input_watermark, output_path,
                          is_current, generated_at_ms, generated_by
                        ) VALUES (
                          :snapshot_id, 'candidate_pool', '{}', '{}',
                          'pg_candidate_pool_projector', '{}', NULL,
                          false, :generated_at_ms, 'historical-test'
                        )
                        """
                    ),
                    {
                        "snapshot_id": f"historical-snapshot:{index}",
                        "generated_at_ms": 1_000 + index,
                    },
                )

            module.publish_runtime_control_current_projections(
                conn,
                target_runtime_head=TEST_RUNTIME_HEAD,
            )
            watermark_raw = conn.execute(
                sa.text(
                    """
                    SELECT input_watermark
                    FROM brc_projection_runs
                    WHERE projection_run_id LIKE 'projection:candidate_pool:%'
                    ORDER BY finished_at_ms DESC
                    LIMIT 1
                    """
                )
            ).scalar_one()

        watermark = (
            json.loads(watermark_raw)
            if isinstance(watermark_raw, str)
            else dict(watermark_raw)
        )
        table_counts = watermark["table_counts"]
        assert table_counts["projection_runs"] == 100
        assert table_counts["control_read_model_snapshots"] == 0
    finally:
        engine.dispose()


def test_publish_current_projections_rejects_legacy_projection_owner(tmp_path: Path):
    module = _load_module(
        SCRIPT_PATH,
        "publish_runtime_control_current_projections_owner_guard",
    )
    engine = _seeded_engine()
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "UPDATE brc_current_projection_ownership "
                    "SET owner_projector = 'legacy_goal_status_writer' "
                    "WHERE model_type = 'goal_status'"
                )
            )
            with pytest.raises(RuntimeError, match="current projection owner mismatch"):
                module.publish_runtime_control_current_projections(
                    conn,
                    target_runtime_head=TEST_RUNTIME_HEAD,
                )
    finally:
        engine.dispose()


def test_publisher_normalizes_asyncpg_dsn_for_direct_cli_use():
    module = _load_module(SCRIPT_PATH, "publish_runtime_control_current_projections_dsn")

    assert module._normalized_database_url(
        "postgresql+asyncpg://user:pass@localhost:5432/brc"
    ) == "postgresql+psycopg://user:pass@localhost:5432/brc"


def test_projection_publisher_rejects_cross_projection_first_blocker_drift():
    module = _load_module(
        SCRIPT_PATH,
        "publish_runtime_control_current_projections_blocker_guard",
    )
    candidate = {
        "symbol_readiness_rows": [
            {
                "strategy_group_id": "CPM-RO-001",
                "symbol": "ETHUSDT",
                "side": "long",
                "first_blocker": "action_time_boundary_not_reproduced",
            }
        ]
    }
    daily = {
        "rows": [
            {
                "strategy_group_id": "CPM-RO-001",
                "symbol": "ETHUSDT",
                "side": "long",
                "first_blocker": "market_wait_validated",
            }
        ]
    }
    goal = {
        "evidence": {
            "pg_blocker_counts": {"action_time_boundary_not_reproduced": 1}
        }
    }

    with pytest.raises(
        RuntimeError,
        match="current projection first blocker mismatch",
    ):
        module._validate_projection_blocker_consistency(
            candidate_pool=candidate,
            daily_table=daily,
            goal_status=goal,
        )


def test_projection_publisher_does_not_feed_materialized_readiness_back_into_goal(monkeypatch):
    module = _load_module(
        SCRIPT_PATH,
        "publish_runtime_control_current_projections_no_stale_goal_feedback",
    )
    candidate_row = {
        "strategy_group_id": "CPM-RO-001",
        "symbol": "ETHUSDT",
        "side": "long",
        "first_blocker": "action_time_boundary_not_reproduced",
    }
    stale_materialized_row = {
        **candidate_row,
        "first_blocker": "market_wait_validated",
    }
    projection_control_state = {
        "source_mode": "db_backed",
        "pretrade_readiness_rows": [],
    }
    monkeypatch.setattr(
        module,
        "_build_candidate_readiness",
        lambda *args, **kwargs: (
            {"source_mode": "db_backed"},
            projection_control_state,
            {"symbol_readiness_rows": [candidate_row]},
            [stale_materialized_row],
        ),
    )
    monkeypatch.setattr(
        module,
        "build_daily_live_enablement_table_from_control_state",
        lambda *args, **kwargs: {"rows": [candidate_row]},
    )

    seen = {}

    def goal_builder(*, control_state):
        seen["readiness_rows"] = control_state["pretrade_readiness_rows"]
        return {
            "evidence": {
                "pg_blocker_counts": {"action_time_boundary_not_reproduced": 1}
            }
        }

    monkeypatch.setattr(module, "build_goal_status_artifact_from_control_state", goal_builder)
    monkeypatch.setattr(
        module,
        "_validate_projection_ownership",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("stop_after_models")),
    )

    with pytest.raises(RuntimeError, match="stop_after_models"):
        module.publish_runtime_control_current_projections(
            None,
            target_runtime_head=TEST_RUNTIME_HEAD,
        )

    assert seen["readiness_rows"] == []
