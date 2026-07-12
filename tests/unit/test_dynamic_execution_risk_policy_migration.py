from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext


ROOT = Path(__file__).resolve().parents[2]
FOUNDATION = ROOT / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py"
EXCHANGE_COMMANDS = ROOT / "migrations/versions/2026-07-10-105_create_ticket_bound_exchange_commands.py"
DYNAMIC_POLICY = ROOT / "migrations/versions/2026-07-12-115_add_dynamic_execution_risk_policy.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_migration_115_adds_confirmed_dynamic_risk_policy_columns() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        for path, name in (
            (FOUNDATION, "migration_086_for_dynamic_policy"),
            (EXCHANGE_COMMANDS, "migration_105_for_dynamic_policy"),
            (DYNAMIC_POLICY, "migration_115_dynamic_policy"),
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
            for item in sa.inspect(conn).get_columns("brc_owner_policy_current")
        }
        budget_columns = {
            item["name"]
            for item in sa.inspect(conn).get_columns("brc_budget_reservations")
        }
        ticket_columns = {
            item["name"]
            for item in sa.inspect(conn).get_columns("brc_action_time_tickets")
        }
        command_columns = {
            item["name"]
            for item in sa.inspect(conn).get_columns(
                "brc_ticket_bound_exchange_commands"
            )
        }

    assert {
        "planned_stop_risk_fraction",
        "max_initial_margin_utilization",
        "max_leverage",
    } <= columns
    assert {
        "effective_notional",
        "selected_leverage",
        "planned_stop_risk_budget",
        "planned_stop_risk",
    } <= budget_columns
    assert {
        "effective_notional",
        "selected_leverage",
        "planned_stop_risk_budget",
        "planned_stop_risk",
    } <= ticket_columns
    assert "desired_leverage" in command_columns
