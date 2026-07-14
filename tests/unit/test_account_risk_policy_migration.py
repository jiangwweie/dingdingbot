from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext


ROOT = Path(__file__).resolve().parents[2]
FOUNDATION = ROOT / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py"
ACCOUNT_POLICY = ROOT / "migrations/versions/2026-07-14-121_create_account_risk_policy.py"
ACCOUNT_CAPACITY_RESERVATION_SCOPE = (
    ROOT / "migrations/versions/2026-07-14-124_add_account_capacity_reservation_scope.py"
)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _upgrade(conn: sa.Connection, path: Path, name: str) -> None:
    module = _load(path, name)
    old_op = module.op
    module.op = Operations(MigrationContext.configure(conn))
    try:
        module.upgrade()
    finally:
        module.op = old_op


def test_migration_121_creates_account_policy_current_with_single_position_shadow_safe_schema() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        _upgrade(conn, FOUNDATION, "migration_086_for_account_risk_policy")
        _upgrade(conn, ACCOUNT_POLICY, "migration_121_account_risk_policy")

        current_columns = {
            column["name"]
            for column in sa.inspect(conn).get_columns("brc_account_risk_policy_current")
        }
        event_columns = {
            column["name"]
            for column in sa.inspect(conn).get_columns("brc_account_risk_policy_events")
        }
        cluster_columns = {
            column["name"]
            for column in sa.inspect(conn).get_columns("brc_risk_cluster_memberships")
        }

    assert {
        "account_id",
        "runtime_profile_id",
        "risk_policy_version",
        "planned_stop_risk_fraction",
        "max_concurrent_positions",
        "max_portfolio_open_risk_fraction",
        "max_cluster_open_risk_fraction",
        "max_portfolio_initial_margin_fraction",
        "max_leverage",
        "max_new_action_time_lanes",
        "automatic_downsize_enabled",
        "unknown_exposure_policy",
        "activation_state",
    } <= current_columns
    assert {"account_risk_policy_event_id", "event_type", "payload", "created_by"} <= event_columns
    assert {
        "risk_cluster_membership_id",
        "risk_policy_version",
        "exchange_instrument_id",
        "risk_cluster_id",
    } <= cluster_columns


def test_migration_124_binds_budget_reservations_to_account_capacity_scope() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        _upgrade(conn, FOUNDATION, "migration_086_for_account_capacity_scope")
        _upgrade(conn, ACCOUNT_CAPACITY_RESERVATION_SCOPE, "migration_124_account_capacity_scope")
        columns = {
            column["name"]
            for column in sa.inspect(conn).get_columns("brc_budget_reservations")
        }

    assert {
        "exchange_instrument_id",
        "account_risk_policy_version",
        "risk_cluster_id",
        "account_capacity_projection_version",
    } <= columns
