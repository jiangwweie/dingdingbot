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
    "105": REPO_ROOT
    / "migrations/versions/2026-07-10-105_create_ticket_bound_exchange_commands.py",
    "106": REPO_ROOT
    / "migrations/versions/2026-07-10-106_create_runtime_supervision_and_allocation.py",
    "107": REPO_ROOT
    / "migrations/versions/2026-07-10-107_certify_cpm_long_trial_event.py",
    "108": REPO_ROOT
    / "migrations/versions/2026-07-10-108_certify_mpg_long_trial_event.py",
    "109": REPO_ROOT
    / "migrations/versions/2026-07-10-109_certify_mi_long_trial_event.py",
    "110": REPO_ROOT
    / "migrations/versions/2026-07-10-110_certify_sor_dual_side_trial_events.py",
    "111": REPO_ROOT
    / "migrations/versions/2026-07-10-111_certify_brf2_short_trial_event.py",
    "112": REPO_ROOT
    / "migrations/versions/2026-07-10-112_version_live_signal_identity.py",
    "113": REPO_ROOT
    / "migrations/versions/2026-07-11-113_create_exchange_account_mode_and_domain_holds.py",
    "114": REPO_ROOT
    / "migrations/versions/2026-07-11-114_extend_exchange_commands_for_lifecycle.py",
    "115": REPO_ROOT
    / "migrations/versions/2026-07-12-115_add_dynamic_execution_risk_policy.py",
    "116": REPO_ROOT
    / "migrations/versions/2026-07-12-116_add_opportunity_feedback_economics.py",
}
REVISION_ORDER = (
    "086", "103", "104", "105", "106", "107", "108", "109", "110", "111",
    "112", "113", "114", "115", "116",
)
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
    after_revision: str | None = None,
) -> None:
    """Install the requested runtime-control test schema revision."""

    if through_revision not in REVISION_ORDER:
        raise ValueError(
            f"unsupported runtime-control test revision: {through_revision}"
        )
    if after_revision is not None and after_revision not in REVISION_ORDER:
        raise ValueError(f"unsupported starting revision: {after_revision}")
    if after_revision is not None and REVISION_ORDER.index(after_revision) >= REVISION_ORDER.index(through_revision):
        raise ValueError("after_revision must precede through_revision")
    operations = Operations(MigrationContext.configure(conn))
    for revision in REVISION_ORDER:
        if after_revision is not None and REVISION_ORDER.index(revision) <= REVISION_ORDER.index(after_revision):
            continue
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


def install_runtime_control_state_revision(
    conn: Connection,
    *,
    revision: str,
) -> None:
    """Apply one additive test revision to an already prepared schema."""

    if revision not in MIGRATIONS:
        raise ValueError(f"unsupported runtime-control test revision: {revision}")
    migration = _load_module(
        MIGRATIONS[revision],
        f"test_runtime_control_state_single_migration_{revision}_{id(conn)}",
    )
    previous_op = migration.op
    migration.op = Operations(MigrationContext.configure(conn))
    try:
        migration.upgrade()
    finally:
        migration.op = previous_op


def seed_runtime_control_state(
    conn: Connection,
    *,
    migration_baseline_revision: str | None = None,
) -> None:
    """Seed deterministic StrategyGroup runtime-control rows for tests."""

    seed = _load_module(
        SEED_PATH,
        f"test_runtime_control_state_seed_{id(conn)}",
    )
    seed.seed_runtime_control_state_foundation(
        conn,
        migration_baseline_revision=migration_baseline_revision,
    )
