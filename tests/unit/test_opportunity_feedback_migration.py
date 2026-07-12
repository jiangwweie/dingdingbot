from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext


ROOT = Path(__file__).resolve().parents[2]
LIVE_OUTCOME = ROOT / "migrations/versions/2026-07-09-102_create_live_outcome_ledger.py"
DYNAMIC_POLICY = ROOT / "migrations/versions/2026-07-12-115_add_dynamic_execution_risk_policy.py"
OFC_ECONOMICS = ROOT / "migrations/versions/2026-07-12-116_add_opportunity_feedback_economics.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_migration_116_adds_nullable_exit_slippage_and_net_pnl() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        for path, name in (
            (LIVE_OUTCOME, "migration_102_for_ofc"),
            (DYNAMIC_POLICY, "migration_115_for_ofc"),
            (OFC_ECONOMICS, "migration_116_ofc"),
        ):
            module = _load(path, name)
            old_op = module.op
            module.op = Operations(MigrationContext.configure(conn))
            try:
                module.upgrade()
            finally:
                module.op = old_op

        columns = {
            item["name"]
            for item in sa.inspect(conn).get_columns("brc_live_outcome_ledger")
        }

    assert {"entry_slippage", "exit_slippage", "net_pnl"} <= columns
