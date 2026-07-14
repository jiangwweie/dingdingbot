from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from decimal import Decimal

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
import pytest
import sqlalchemy as sa
from sqlalchemy import text

from src.application.action_time.ticket_exit_policy_binding import (
    TicketExitPolicyBindingError,
    load_ticket_exit_policy_binding,
)
from src.domain.ticket_exit_policy import TicketExitPolicySnapshot
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/2026-07-15-123_activate_sor_long_exit_policy_canary.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "migration_123_activate_sor_long_exit_policy_canary",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _upgrade(migration, conn) -> None:
    previous_op = migration.op
    migration.op = Operations(MigrationContext.configure(conn))
    try:
        migration.upgrade()
    finally:
        migration.op = previous_op


def _downgrade(migration, conn) -> None:
    previous_op = migration.op
    migration.op = Operations(MigrationContext.configure(conn))
    try:
        migration.downgrade()
    finally:
        migration.op = previous_op


def test_migration_123_activates_one_exact_future_sor_long_policy(
    pg_control_connection,
):
    migration = _load_migration()
    assert migration.revision == "123"
    assert migration.down_revision == "122"
    ticket_count_before = pg_control_connection.execute(
        text("SELECT count(*) FROM brc_action_time_tickets")
    ).scalar_one()

    _upgrade(migration, pg_control_connection)
    _upgrade(migration, pg_control_connection)

    rows = list(
        pg_control_connection.execute(
            text(
                "SELECT * FROM brc_strategy_exit_policies "
                "WHERE status = 'current'"
            )
        ).mappings()
    )
    assert len(rows) == 1
    row = dict(rows[0])
    payload = row["policy_payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    snapshot = TicketExitPolicySnapshot.model_validate(payload)
    assert snapshot.exit_policy_id == migration.EXIT_POLICY_ID
    assert snapshot.exit_policy_version == migration.EXIT_POLICY_VERSION
    assert snapshot.payload_hash == migration.POLICY_HASH
    assert snapshot.event_spec_id == "event_spec:SOR-001:SOR-LONG:v2"
    assert snapshot.take_profit_legs[0].execution_style.value == "limit_gtc"
    assert snapshot.take_profit_legs[0].market_fallback_allowed is False
    assert snapshot.take_profit_legs[0].reward_multiple == 1
    assert snapshot.take_profit_legs[0].quantity_fraction == Decimal("0.5")
    assert snapshot.time_stop_rule.max_holding_bars == 96
    assert snapshot.runner_rule.structure_window_bars == 4
    assert str(snapshot.runner_rule.atr_buffer_multiple) == "0.5"
    assert row["approved_by"] == migration.OWNER_APPROVAL_REF
    assert pg_control_connection.execute(
        text("SELECT count(*) FROM brc_action_time_tickets")
    ).scalar_one() == ticket_count_before

    capability = pg_control_connection.execute(
        text(
            "SELECT status, certification_ref "
            "FROM brc_runtime_capabilities_current "
            "WHERE capability_id = 'ticket_exit_policy_v1'"
        )
    ).mappings().one()
    assert capability["status"] == "enabled"
    assert migration.POLICY_HASH in capability["certification_ref"]
    assert migration.RESEARCH_DECISION_HASH in capability["certification_ref"]

    binding = load_ticket_exit_policy_binding(
        pg_control_connection,
        strategy_group_id="SOR-001",
        strategy_version="sgv:SOR-001:v2",
        event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
        event_spec_version="v2",
        side="long",
    )
    assert binding.binding_kind == "versioned"
    assert binding.exit_policy_hash == migration.POLICY_HASH


def test_migration_123_keeps_non_canary_event_specs_fail_closed(
    pg_control_connection,
):
    migration = _load_migration()
    _upgrade(migration, pg_control_connection)

    with pytest.raises(TicketExitPolicyBindingError, match="missing"):
        load_ticket_exit_policy_binding(
            pg_control_connection,
            strategy_group_id="MPG-001",
            strategy_version="sgv:MPG-001:v2",
            event_spec_id="event_spec:MPG-001:MPG-LONG:v2",
            event_spec_version="v2",
            side="long",
        )


def test_migration_123_downgrade_is_forward_safe_before_any_bound_ticket(
    pg_control_connection,
):
    migration = _load_migration()
    _upgrade(migration, pg_control_connection)

    _downgrade(migration, pg_control_connection)

    assert pg_control_connection.execute(
        text("SELECT count(*) FROM brc_strategy_exit_policies")
    ).scalar_one() == 0
    capability = pg_control_connection.execute(
        text(
            "SELECT status FROM brc_runtime_capabilities_current "
            "WHERE capability_id = 'ticket_exit_policy_v1'"
        )
    ).scalar_one()
    assert capability == "disabled"
