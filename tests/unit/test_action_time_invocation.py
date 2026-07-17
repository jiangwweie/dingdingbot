from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text

from src.application.action_time.action_time_invocation import (
    ActionTimeInvocationBlocked,
    bind_action_time_invocation_fact_refs,
    load_action_time_invocation,
    start_action_time_invocation,
)
from src.application.action_time.runtime_pg_fact_snapshots import (
    write_account_safe_fact_snapshots,
)
from tests.unit.test_pg_promotion_action_time_lane_materialization import (
    NOW_MS,
    _insert_ready_fresh_signal,
    pg_control_connection,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-13-119_action_time_invocation_consistency.py"
)
MIGRATION_134_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-17-134_repair_account_risk_current_authority.py"
)


def _migration():
    spec = importlib.util.spec_from_file_location(
        "migration_119_action_time_invocation",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def invocation_pg_control_connection(pg_control_connection):
    migration = _migration()
    old_op = migration.op
    migration.op = Operations(MigrationContext.configure(pg_control_connection))
    try:
        migration.upgrade()
    finally:
        migration.op = old_op
    spec = importlib.util.spec_from_file_location(
        "migration_134_action_time_invocation", MIGRATION_134_PATH
    )
    assert spec is not None and spec.loader is not None
    migration_134 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration_134)
    old_op = migration_134.op
    migration_134.op = Operations(MigrationContext.configure(pg_control_connection))
    try:
        migration_134.upgrade()
    finally:
        migration_134.op = old_op
    # This SQLite fixture is intentionally a compact subset of the deployed
    # migration chain.  The sequence tests below construct V2 rule facts, so
    # include the columns introduced by migration 136 without treating SQLite
    # as the migration-136 acceptance environment.
    pg_control_connection.execute(text(
        "ALTER TABLE brc_instrument_rule_snapshots "
        "ADD COLUMN risk_calculation_kind TEXT"
    ))
    pg_control_connection.execute(text(
        "ALTER TABLE brc_instrument_rule_snapshots "
        "ADD COLUMN supersedes_instrument_rule_snapshot_id TEXT"
    ))
    return pg_control_connection


def test_start_invocation_binds_one_fresh_typed_signal_and_deadline(
    invocation_pg_control_connection,
):
    _insert_ready_fresh_signal(
        invocation_pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
    )
    signal_event_id = "signal:SOR-001:ETHUSDT:long:unit"

    invocation = start_action_time_invocation(
        invocation_pg_control_connection,
        signal_event_id=signal_event_id,
        opened_at_ms=NOW_MS,
    )
    repeated = start_action_time_invocation(
        invocation_pg_control_connection,
        signal_event_id=signal_event_id,
        opened_at_ms=NOW_MS + 1,
    )

    assert invocation.signal_event_id == signal_event_id
    assert invocation.lane_identity.identity_key.startswith("runtime_lane:")
    assert invocation.opened_at_ms == NOW_MS
    assert invocation.expires_at_ms == NOW_MS + 600_000
    assert repeated == invocation
    assert invocation_pg_control_connection.execute(
        text("SELECT COUNT(*) FROM brc_action_time_invocations")
    ).scalar_one() == 1


def test_invocation_binds_only_existing_account_fact_references(
    invocation_pg_control_connection,
):
    _insert_ready_fresh_signal(
        invocation_pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
    )
    invocation = start_action_time_invocation(
        invocation_pg_control_connection,
        signal_event_id="signal:SOR-001:ETHUSDT:long:unit",
        opened_at_ms=NOW_MS,
    )
    invocation_pg_control_connection.execute(
        text(
            """
            UPDATE brc_runtime_fact_snapshots
            SET observed_at_ms = :stage_at_ms,
                created_at_ms = :stage_at_ms,
                valid_until_ms = :valid_until_ms
            WHERE fact_snapshot_id IN (
              'fact:SOR-001:ETHUSDT:long:unit:account-safe',
              'fact:SOR-001:ETHUSDT:long:unit:account-mode'
            )
            """
        ),
        {"stage_at_ms": NOW_MS + 1, "valid_until_ms": NOW_MS + 600_000},
    )

    bound = bind_action_time_invocation_fact_refs(
        invocation_pg_control_connection,
        action_time_invocation_id=invocation.action_time_invocation_id,
        account_safe_fact_snapshot_id="fact:SOR-001:ETHUSDT:long:unit:account-safe",
        account_mode_fact_snapshot_id="fact:SOR-001:ETHUSDT:long:unit:account-mode",
        stage_at_ms=NOW_MS + 1,
    )

    assert bound.account_safe_fact_snapshot_id.endswith(":account-safe")
    assert bound.account_mode_fact_snapshot_id.endswith(":account-mode")
    assert load_action_time_invocation(
        invocation_pg_control_connection,
        action_time_invocation_id=invocation.action_time_invocation_id,
    ) == bound


def test_invocation_rejects_both_account_fact_kinds_before_any_fact_write(
    invocation_pg_control_connection,
):
    _insert_ready_fresh_signal(
        invocation_pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
    )
    invocation = start_action_time_invocation(
        invocation_pg_control_connection,
        signal_event_id="signal:SOR-001:ETHUSDT:long:unit",
        opened_at_ms=NOW_MS,
    )

    with pytest.raises(
        ActionTimeInvocationBlocked,
        match="action_time_invocation_account_fact_pair_ambiguous",
    ):
        bind_action_time_invocation_fact_refs(
            invocation_pg_control_connection,
            action_time_invocation_id=invocation.action_time_invocation_id,
            account_safe_fact_snapshot_id="does-not-matter",
            account_capacity_base_fact_snapshot_id="does-not-matter-either",
            stage_at_ms=NOW_MS + 1,
        )

    stored = load_action_time_invocation(
        invocation_pg_control_connection,
        action_time_invocation_id=invocation.action_time_invocation_id,
    )
    assert stored.account_safe_fact_snapshot_id is None
    assert stored.account_capacity_base_fact_snapshot_id is None


def test_start_invocation_rejects_expired_or_identity_corrupted_signal(
    invocation_pg_control_connection,
):
    _insert_ready_fresh_signal(
        invocation_pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
    )
    signal_event_id = "signal:SOR-001:ETHUSDT:long:unit"
    original_lane_identity_key = invocation_pg_control_connection.execute(
        text(
            """
            SELECT lane_identity_key
            FROM brc_live_signal_events
            WHERE signal_event_id = :signal_event_id
            """
        ),
        {"signal_event_id": signal_event_id},
    ).scalar_one()
    invocation_pg_control_connection.execute(
        text(
            """
            UPDATE brc_live_signal_events
            SET lane_identity_key = 'runtime_lane:corrupted'
            WHERE signal_event_id = :signal_event_id
            """
        ),
        {"signal_event_id": signal_event_id},
    )

    with pytest.raises(
        ActionTimeInvocationBlocked,
        match="runtime_lane_identity_mismatch:live_signal_identity_key",
    ):
        start_action_time_invocation(
            invocation_pg_control_connection,
            signal_event_id=signal_event_id,
            opened_at_ms=NOW_MS,
        )
    invocation_pg_control_connection.execute(
        text(
            """
            UPDATE brc_live_signal_events
            SET lane_identity_key = :lane_identity_key,
                expires_at_ms = :expires_at_ms
            WHERE signal_event_id = :signal_event_id
            """
        ),
        {
            "lane_identity_key": original_lane_identity_key,
            "expires_at_ms": NOW_MS,
            "signal_event_id": signal_event_id,
        },
    )
    with pytest.raises(
        ActionTimeInvocationBlocked,
        match="action_time_invocation_signal_not_current",
    ):
        start_action_time_invocation(
            invocation_pg_control_connection,
            signal_event_id=signal_event_id,
            opened_at_ms=NOW_MS,
        )


def test_new_account_facts_bind_to_invocation_at_their_actual_observation_time(
    invocation_pg_control_connection,
):
    _insert_ready_fresh_signal(
        invocation_pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
    )
    invocation = start_action_time_invocation(
        invocation_pg_control_connection,
        signal_event_id="signal:SOR-001:ETHUSDT:long:unit",
        opened_at_ms=NOW_MS,
    )
    observed_at_ms = NOW_MS + 1
    observed_at = datetime.fromtimestamp(
        observed_at_ms / 1000,
        tz=timezone.utc,
    ).isoformat()

    fact_snapshot_ids = write_account_safe_fact_snapshots(
        invocation_pg_control_connection,
        artifact={
            "generated_at_utc": observed_at,
            "source_status": "unit_readonly_account_fact",
            "checks": {
                "account_safe_facts_ready": True,
                "account_safe": True,
                "account_trade_permission": True,
                "open_orders_clear": True,
                "active_position_or_open_order_clear": True,
                "action_time_available_balance": True,
                "source_signed_get_only": True,
                "source_exchange_write_called": False,
                "source_order_created": False,
            },
            "facts": {
                "total_wallet_balance": "100",
                "available_balance": "100",
            },
            "account_mode": {
                "status": "fresh",
                "account_id": "owner-subaccount-runtime-v0",
                "exchange_id": "binance_usdm",
                "runtime_profile_id": "owner-runtime-console-v1",
                "account_mode": "one_way",
                "dual_side_position": False,
                "position_mode_safe": True,
                "observed_at": observed_at,
                "source": "binance_usdm_signed_get:/fapi/v1/positionSide/dual",
            },
        },
        source_ref="unit:invocation-bound-account-facts",
        action_time_invocation_id=invocation.action_time_invocation_id,
    )

    rows = invocation_pg_control_connection.execute(
        text(
            """
            SELECT fact_snapshot_id, fact_surface, observed_at_ms, created_at_ms,
                   action_time_invocation_id
            FROM brc_runtime_fact_snapshots
            WHERE fact_snapshot_id IN :fact_snapshot_ids
            ORDER BY fact_snapshot_id
            """
        ).bindparams(
            sa.bindparam("fact_snapshot_ids", expanding=True)
        ),
        {"fact_snapshot_ids": fact_snapshot_ids},
    ).mappings().all()
    bound = load_action_time_invocation(
        invocation_pg_control_connection,
        action_time_invocation_id=invocation.action_time_invocation_id,
    )

    assert len(rows) == 3
    assert {row["observed_at_ms"] for row in rows} == {observed_at_ms}
    assert {row["created_at_ms"] for row in rows} == {observed_at_ms}
    assert {
        row["action_time_invocation_id"]
        for row in rows
        if row["fact_surface"] != "account_capacity_base"
    } == {
        invocation.action_time_invocation_id
    }
    capacity_base_ids = {
        row["fact_snapshot_id"]
        for row in rows
        if row["fact_surface"] == "account_capacity_base"
    }
    assert len(capacity_base_ids) == 1
    assert all(
        row["action_time_invocation_id"] is None
        for row in rows
        if row["fact_surface"] == "account_capacity_base"
    )
    assert set(fact_snapshot_ids) - capacity_base_ids == {
        bound.account_safe_fact_snapshot_id,
        bound.account_mode_fact_snapshot_id,
    }
