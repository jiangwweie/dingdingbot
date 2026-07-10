"""Canonical test-only runtime-control schema installer."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy.engine import Connection


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = {
    "086": REPO_ROOT
    / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py",
    "103": REPO_ROOT
    / "migrations/versions/2026-07-09-103_add_budget_risk_at_stop_reservation.py",
    "104": REPO_ROOT
    / "migrations/versions/2026-07-10-104_add_execution_eligibility_authority.py",
}
REVISION_ORDER = ("086", "103", "104")
SEED_PATH = REPO_ROOT / "scripts/seed_runtime_control_state_foundation.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load test module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def install_runtime_control_state_schema(
    conn: Connection,
    *,
    through_revision: str = "104",
) -> None:
    """Install the requested runtime-control test schema revision."""

    if through_revision not in REVISION_ORDER:
        raise ValueError(
            f"unsupported runtime-control test revision: {through_revision}"
        )
    operations = Operations(MigrationContext.configure(conn))
    for revision in REVISION_ORDER:
        migration = _load_module(
            MIGRATIONS[revision],
            f"test_runtime_control_state_migration_{revision}_{id(conn)}",
        )
        previous_op = migration.op
        migration.op = operations
        try:
            migration.upgrade()
        finally:
            migration.op = previous_op
        if revision == through_revision:
            break


def seed_runtime_control_state(conn: Connection) -> None:
    """Seed deterministic StrategyGroup runtime-control rows for tests."""

    seed = _load_module(
        SEED_PATH,
        f"test_runtime_control_state_seed_{id(conn)}",
    )
    seed.seed_runtime_control_state_foundation(conn)
