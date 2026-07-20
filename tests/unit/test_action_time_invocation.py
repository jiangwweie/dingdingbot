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
    close_action_time_invocation_without_ticket,
    load_action_time_invocation,
    start_action_time_invocation,
)
from src.application.action_time.runtime_pg_fact_snapshots import (
    write_account_safe_fact_snapshots,
)
from src.application.action_time.signal_arbitration import ArbitrationDisposition
from src.application.action_time.signal_intake import (
    conserve_and_arbitrate_fresh_signals,
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
    for column in (
        "terminal_kind TEXT",
        "terminal_reason_code TEXT",
        "arbitration_rank INTEGER",
        "winner_signal_event_id TEXT",
    ):
        pg_control_connection.execute(
            text(f"ALTER TABLE brc_action_time_invocations ADD COLUMN {column}")
        )
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


def test_non_ticket_terminal_invocation_conserves_rank_winner_and_is_irreversible(
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

    closed = close_action_time_invocation_without_ticket(
        invocation_pg_control_connection,
        action_time_invocation_id=invocation.action_time_invocation_id,
        terminal_kind="not_selected",
        terminal_reason_code="action_time_arbitration_winner_selected",
        stage_at_ms=NOW_MS + 1,
        arbitration_rank=2,
        winner_signal_event_id="signal:other:unit",
    )

    assert closed.closed_at_ms == NOW_MS + 1
    assert closed.terminal_kind == "not_selected"
    assert closed.arbitration_rank == 2
    assert closed.winner_signal_event_id == "signal:other:unit"
    assert (
        close_action_time_invocation_without_ticket(
            invocation_pg_control_connection,
            action_time_invocation_id=invocation.action_time_invocation_id,
            terminal_kind="not_selected",
            terminal_reason_code="action_time_arbitration_winner_selected",
            stage_at_ms=NOW_MS + 1,
            arbitration_rank=2,
            winner_signal_event_id="signal:other:unit",
        )
        == closed
    )
    with pytest.raises(
        ActionTimeInvocationBlocked,
        match="action_time_invocation_already_terminal",
    ):
        close_action_time_invocation_without_ticket(
            invocation_pg_control_connection,
            action_time_invocation_id=invocation.action_time_invocation_id,
            terminal_kind="expired",
            terminal_reason_code="action_time_signal_expired",
            stage_at_ms=NOW_MS + 1,
        )


def test_pg_signal_intake_conserves_each_fresh_signal_and_closes_nonwinner(
    invocation_pg_control_connection,
):
    _insert_ready_fresh_signal(
        invocation_pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
    )
    _insert_ready_fresh_signal(
        invocation_pg_control_connection,
        "SOR-001",
        "SOLUSDT",
        "long",
        insert_action_time_fact=False,
    )
    invocation_pg_control_connection.execute(
        text(
            """
            UPDATE brc_strategy_group_candidate_scope
            SET priority_rank = CASE symbol
              WHEN 'ETHUSDT' THEN 1
              WHEN 'SOLUSDT' THEN 2
              ELSE priority_rank
            END
            WHERE strategy_group_id = 'SOR-001'
              AND side = 'long'
            """
        )
    )

    persisted = conserve_and_arbitrate_fresh_signals(
        invocation_pg_control_connection,
        now_ms=NOW_MS,
    )

    assert len(persisted) == 2
    selected = [
        item
        for item in persisted
        if item.decision.disposition is ArbitrationDisposition.SELECTED
    ]
    rejected = [
        item
        for item in persisted
        if item.decision.disposition is ArbitrationDisposition.NOT_SELECTED_THIS_ROUND
    ]
    assert len(selected) == 1
    assert selected[0].decision.signal_event_id == "signal:SOR-001:ETHUSDT:long:unit"
    assert len(rejected) == 1
    closed = load_action_time_invocation(
        invocation_pg_control_connection,
        action_time_invocation_id=rejected[0].action_time_invocation_id,
    )
    assert closed.terminal_kind == "not_selected"
    assert closed.winner_signal_event_id == selected[0].decision.signal_event_id
    assert invocation_pg_control_connection.execute(
        text("SELECT COUNT(*) FROM brc_runtime_process_outcomes")
    ).scalar_one() >= 2


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
