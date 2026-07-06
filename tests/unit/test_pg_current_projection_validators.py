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
MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py"
)
SEED_PATH = REPO_ROOT / "scripts/seed_runtime_control_state_foundation.py"
PUBLISH_PATH = REPO_ROOT / "scripts/publish_runtime_control_current_projections.py"
OWNERSHIP_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_current_projection_ownership.py"
LINEAGE_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_pg_current_projection_lineage.py"
READINESS_VALIDATOR_PATH = (
    REPO_ROOT / "scripts/validate_candidate_readiness_current_projection.py"
)
EXPORT_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_export_matches_pg_projection.py"
TICKET_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_action_time_ticket_identity.py"
NO_FILE_AUTHORITY_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_no_runtime_file_authority.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _seeded_engine():
    migration = _load_module(MIGRATION_PATH, "migration_086_projection_validators")
    seed = _load_module(SEED_PATH, "seed_projection_validators")
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


def test_pg_current_projection_validators_accept_published_current(tmp_path: Path):
    publish = _load_module(PUBLISH_PATH, "publish_projection_validator_accept")
    ownership = _load_module(OWNERSHIP_VALIDATOR_PATH, "ownership_validator_accept")
    lineage = _load_module(LINEAGE_VALIDATOR_PATH, "lineage_validator_accept")
    readiness = _load_module(READINESS_VALIDATOR_PATH, "readiness_validator_accept")
    export = _load_module(EXPORT_VALIDATOR_PATH, "export_validator_accept")
    no_file = _load_module(NO_FILE_AUTHORITY_VALIDATOR_PATH, "no_file_validator_accept")
    engine = _seeded_engine()
    try:
        with engine.begin() as conn:
            publish.publish_runtime_control_current_projections(
                conn,
            )
            assert ownership.validate_current_projection_ownership(conn) == []
            assert lineage.validate_pg_current_projection_lineage(conn) == []
            assert readiness.validate_candidate_readiness_current_projection(conn) == []
            assert export.validate_export_matches_pg_projection(conn) == []
        assert no_file.validate_no_runtime_file_authority(repo_root=REPO_ROOT) == []
    finally:
        engine.dispose()


def test_export_validator_rejects_current_projection_export_path(tmp_path: Path):
    publish = _load_module(PUBLISH_PATH, "publish_projection_validator_mismatch")
    export = _load_module(EXPORT_VALIDATOR_PATH, "export_validator_mismatch")
    engine = _seeded_engine()
    try:
        with engine.begin() as conn:
            publish.publish_runtime_control_current_projections(
                conn,
            )
            conn.execute(
                sa.text(
                    "UPDATE brc_control_read_model_snapshots "
                    "SET output_path = :output_path "
                    "WHERE model_type = 'candidate_pool' AND is_current = true"
                ),
                {"output_path": str(tmp_path / "candidate-pool.json")},
            )
            errors = export.validate_export_matches_pg_projection(conn)

        assert errors == [
            f"candidate_pool current projection must not define export path: {tmp_path / 'candidate-pool.json'}"
        ]
    finally:
        engine.dispose()


def test_action_time_ticket_identity_validator_accepts_one_matching_ticket():
    ticket = _load_module(TICKET_VALIDATOR_PATH, "ticket_validator_accept")
    engine = _ticket_identity_engine(ticket_count=1, lane_count=1)
    try:
        with engine.connect() as conn:
            assert ticket.validate_action_time_ticket_identity(conn) == []
    finally:
        engine.dispose()


def test_action_time_ticket_identity_validator_rejects_missing_ticket():
    ticket = _load_module(TICKET_VALIDATOR_PATH, "ticket_validator_missing")
    engine = _ticket_identity_engine(ticket_count=0, lane_count=1)
    try:
        with engine.connect() as conn:
            errors = ticket.validate_action_time_ticket_identity(conn)

        assert errors == ["open action-time lane missing ticket: lane-1"]
    finally:
        engine.dispose()


def test_action_time_ticket_identity_validator_rejects_mismatch():
    ticket = _load_module(TICKET_VALIDATOR_PATH, "ticket_validator_mismatch")
    engine = _ticket_identity_engine(
        ticket_count=1,
        lane_count=1,
        ticket_symbol="BTCUSDT",
    )
    try:
        with engine.connect() as conn:
            errors = ticket.validate_action_time_ticket_identity(conn)

        assert errors == ["ticket identity mismatch for ticket-1:symbol"]
    finally:
        engine.dispose()


def _ticket_identity_engine(
    *,
    ticket_count: int,
    lane_count: int,
    ticket_symbol: str = "ETHUSDT",
):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                CREATE TABLE brc_action_time_lane_inputs (
                    action_time_lane_input_id TEXT PRIMARY KEY,
                    promotion_candidate_id TEXT,
                    signal_event_id TEXT,
                    strategy_group_id TEXT,
                    symbol TEXT,
                    side TEXT,
                    runtime_profile_id TEXT,
                    lane_scope TEXT,
                    status TEXT
                )
                """
            )
        )
        conn.execute(
            sa.text(
                """
                CREATE TABLE brc_action_time_tickets (
                    ticket_id TEXT PRIMARY KEY,
                    action_time_lane_input_id TEXT,
                    promotion_candidate_id TEXT,
                    signal_event_id TEXT,
                    strategy_group_id TEXT,
                    symbol TEXT,
                    side TEXT,
                    runtime_profile_id TEXT,
                    status TEXT
                )
                """
            )
        )
        for index in range(lane_count):
            suffix = index + 1
            conn.execute(
                sa.text(
                    """
                    INSERT INTO brc_action_time_lane_inputs VALUES (
                        :lane_id,
                        :promotion_id,
                        :signal_id,
                        'SOR-001',
                        'ETHUSDT',
                        'long',
                        'runtime-profile-v0',
                        'real_submit_candidate',
                        'ticket_created'
                    )
                    """
                ),
                {
                    "lane_id": f"lane-{suffix}",
                    "promotion_id": f"promotion-{suffix}",
                    "signal_id": f"signal-{suffix}",
                },
            )
        for index in range(ticket_count):
            suffix = index + 1
            conn.execute(
                sa.text(
                    """
                    INSERT INTO brc_action_time_tickets VALUES (
                        :ticket_id,
                        :lane_id,
                        :promotion_id,
                        :signal_id,
                        'SOR-001',
                        :symbol,
                        'long',
                        'runtime-profile-v0',
                        'created'
                    )
                    """
                ),
                {
                    "ticket_id": f"ticket-{suffix}",
                    "lane_id": f"lane-{suffix}",
                    "promotion_id": f"promotion-{suffix}",
                    "signal_id": f"signal-{suffix}",
                    "symbol": ticket_symbol,
                },
            )
    return engine
