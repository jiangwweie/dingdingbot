from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations/versions/2026-07-14-122_create_account_risk_current_projections.py"


def _load() -> object:
    spec = importlib.util.spec_from_file_location("migration_122_account_risk_current", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["migration_122_account_risk_current"] = module
    spec.loader.exec_module(module)
    return module


def test_migration_122_creates_current_projections_and_unique_account_keys() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        module = _load()
        old_op = module.op
        module.op = Operations(MigrationContext.configure(conn))
        try:
            module.upgrade()
        finally:
            module.op = old_op

        inspector = sa.inspect(conn)
        assert {
            "brc_account_exposure_current",
            "brc_account_budget_current",
            "brc_account_risk_projection_events",
            "brc_budget_reservation_events",
        } <= set(inspector.get_table_names())
        exposure_unique = {
            tuple(item["column_names"])
            for item in inspector.get_unique_constraints("brc_account_exposure_current")
        }
        budget_unique = {
            tuple(item["column_names"])
            for item in inspector.get_unique_constraints("brc_account_budget_current")
        }

    assert (
        "account_id",
        "exchange_instrument_id",
        "position_mode",
        "position_bucket",
    ) in exposure_unique
    assert (
        "account_id",
        "runtime_profile_id",
        "risk_policy_version",
    ) in budget_unique
