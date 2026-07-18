from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import sqlalchemy as sa
import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

from src.application.action_time.action_time_ticket import (
    compute_action_time_ticket_hash,
)


ROOT = Path(__file__).resolve().parents[2]
FOUNDATION = ROOT / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py"
COMMANDS = ROOT / "migrations/versions/2026-07-10-105_create_ticket_bound_exchange_commands.py"
INVOCATION = ROOT / "migrations/versions/2026-07-13-119_action_time_invocation_consistency.py"
ACCOUNT_POLICY = ROOT / "migrations/versions/2026-07-17-126_create_account_risk_policy.py"
ACCOUNT_CURRENT = ROOT / "migrations/versions/2026-07-17-127_create_account_risk_current_projections.py"
ACCOUNT_RESERVATION_SCOPE = (
    ROOT / "migrations/versions/2026-07-17-129_add_account_capacity_reservation_scope.py"
)
ACCOUNT_CLAIM_POLICY_EVENT = (
    ROOT / "migrations/versions/2026-07-17-130_add_account_capacity_claim_policy_event.py"
)
EXPAND = ROOT / "migrations/versions/2026-07-17-131_expand_asset_neutral_account_risk_identity.py"
BACKFILL = ROOT / "migrations/versions/2026-07-17-132_backfill_asset_neutral_account_risk_identity.py"
ENFORCE = ROOT / "migrations/versions/2026-07-17-133_enforce_asset_neutral_account_risk_identity.py"
CAPACITY_FACT_AUTHORITY = (
    ROOT
    / "migrations/versions/2026-07-17-134_repair_account_risk_current_authority.py"
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


def _downgrade(conn: sa.Connection, path: Path, name: str) -> None:
    module = _load(path, name)
    old_op = module.op
    module.op = Operations(MigrationContext.configure(conn))
    try:
        module.downgrade()
    finally:
        module.op = old_op


def _upgrade_to_125(conn: sa.Connection) -> None:
    _upgrade(conn, FOUNDATION, "migration_086_asset_neutral")
    _upgrade(conn, COMMANDS, "migration_105_asset_neutral")
    _upgrade(conn, ACCOUNT_POLICY, "migration_121_asset_neutral")
    _upgrade(conn, ACCOUNT_CURRENT, "migration_122_asset_neutral")
    _upgrade(conn, ACCOUNT_RESERVATION_SCOPE, "migration_124_asset_neutral")
    _upgrade(conn, ACCOUNT_CLAIM_POLICY_EVENT, "migration_125_asset_neutral")


def _upgrade_to_126(conn: sa.Connection) -> None:
    _upgrade_to_125(conn)
    _upgrade(conn, EXPAND, "migration_126_asset_neutral")


def _columns(conn: sa.Connection, table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(conn).get_columns(table_name)}


def test_migration_134_adds_capacity_fact_references_and_v2_runtime_safety_columns() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        _upgrade_to_126(conn)
        _upgrade(conn, INVOCATION, "migration_119_capacity_fact_authority")
        _upgrade(conn, ENFORCE, "migration_133_capacity_fact_authority")
        _upgrade(conn, CAPACITY_FACT_AUTHORITY, "migration_134_capacity_fact_authority")

        invocation_columns = _columns(conn, "brc_action_time_invocations")
        lane_columns = _columns(conn, "brc_action_time_lane_inputs")
        ticket_columns = _columns(conn, "brc_action_time_tickets")
        runtime_safety_columns = _columns(conn, "brc_runtime_safety_state_snapshots")

    assert "account_capacity_base_fact_snapshot_id" in invocation_columns
    assert "account_capacity_base_fact_snapshot_id" in lane_columns
    assert "account_capacity_base_fact_snapshot_id" in ticket_columns
    assert "ticket_hash_schema_version" in ticket_columns
    ticket_safe_fact_column = next(
        column
        for column in sa.inspect(engine).get_columns("brc_action_time_tickets")
        if column["name"] == "account_safe_fact_snapshot_id"
    )
    assert ticket_safe_fact_column["nullable"] is True
    assert {
        "trusted_fact_refs_schema_version",
        "account_capacity_fact_surface",
        "account_capacity_fact_snapshot_id",
    } <= runtime_safety_columns


def test_migration_134_downgrade_aborts_before_ddl_when_v2_history_exists() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        _upgrade_to_126(conn)
        _upgrade(conn, INVOCATION, "migration_119_capacity_fact_downgrade")
        _upgrade(conn, ENFORCE, "migration_133_capacity_fact_downgrade")
        _upgrade(conn, CAPACITY_FACT_AUTHORITY, "migration_134_capacity_fact_downgrade")
        conn.execute(
            sa.text(
                "INSERT INTO brc_runtime_safety_state_snapshots "
                "(runtime_safety_snapshot_id, strategy_group_id, safety_state, "
                "submit_allowed, finalgate_ready, operation_layer_ready, "
                "protection_ready, active_position_conflict, facts_fresh, "
                "trusted_fact_refs_complete, observed_at_ms, created_at_ms, "
                "authority_boundary, trusted_fact_refs_schema_version) "
                "VALUES ('v2-history', 'group', 'blocked_safety', false, false, "
                "false, false, true, false, false, 1, 1, 'unit', "
                "'runtime_safety_trusted_refs.v2')"
            )
        )

        with pytest.raises(RuntimeError, match="capacity_fact_history_not_legacy_compatible"):
            _downgrade(conn, CAPACITY_FACT_AUTHORITY, "migration_134_capacity_fact_downgrade")

        assert "account_capacity_fact_snapshot_id" in _columns(
            conn, "brc_runtime_safety_state_snapshots"
        )


def test_migration_134_keeps_verified_v1_ticket_hash_byte_identical() -> None:
    engine = sa.create_engine("sqlite://")
    legacy_ticket = {"ticket_id": "legacy-ticket-1"}
    legacy_hash = compute_action_time_ticket_hash(legacy_ticket)
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE brc_action_time_tickets "
                "(ticket_id TEXT PRIMARY KEY, ticket_hash TEXT NOT NULL)"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO brc_action_time_tickets VALUES "
                "('legacy-ticket-1', :ticket_hash)"
            ),
            {"ticket_hash": legacy_hash},
        )

        _upgrade(conn, CAPACITY_FACT_AUTHORITY, "migration_134_v1_hash_valid")

        row = conn.execute(
            sa.text(
                "SELECT ticket_hash, ticket_hash_schema_version "
                "FROM brc_action_time_tickets"
            )
        ).mappings().one()
    assert row == {
        "ticket_hash": legacy_hash,
        "ticket_hash_schema_version": "action_time_ticket_hash.v1",
    }


def test_migration_134_aborts_before_labelling_invalid_v1_ticket_hash() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE brc_action_time_tickets "
                "(ticket_id TEXT PRIMARY KEY, ticket_hash TEXT NOT NULL)"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO brc_action_time_tickets VALUES "
                "('legacy-ticket-corrupt', 'not-a-v1-hash')"
            )
        )

        with pytest.raises(RuntimeError, match="ticket_hash_v1_preflight_invalid"):
            _upgrade(conn, CAPACITY_FACT_AUTHORITY, "migration_134_v1_hash_invalid")

        assert conn.execute(
            sa.text(
                "SELECT ticket_hash_schema_version FROM brc_action_time_tickets"
            )
        ).scalar_one_or_none() is None


def test_migration_134_quarantines_terminal_hash_drift_without_rehashing() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE brc_action_time_tickets "
                "(ticket_id TEXT PRIMARY KEY, status TEXT NOT NULL, ticket_hash TEXT NOT NULL)"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO brc_action_time_tickets VALUES "
                "('legacy-terminal-drift', 'expired', 'old-immutable-hash')"
            )
        )

        _upgrade(conn, CAPACITY_FACT_AUTHORITY, "migration_134_terminal_hash_drift")

        row = conn.execute(
            sa.text(
                "SELECT ticket_hash, ticket_hash_schema_version "
                "FROM brc_action_time_tickets"
            )
        ).mappings().one()
    assert row == {
        "ticket_hash": "old-immutable-hash",
        "ticket_hash_schema_version": (
            "action_time_ticket_hash.legacy_terminal_unverifiable"
        ),
    }


def _create_terminal_capacity_repair_tables(conn: sa.Connection) -> None:
    for statement in (
        "CREATE TABLE brc_budget_reservations (budget_reservation_id TEXT PRIMARY KEY, ticket_id TEXT, status TEXT, release_reason TEXT, released_at_ms BIGINT, reserved_at_ms BIGINT, exchange_instrument_id TEXT, reconciliation_state TEXT, current_first_blocker TEXT)",
        "CREATE TABLE brc_action_time_tickets (ticket_id TEXT PRIMARY KEY, status TEXT, exchange_instrument_id TEXT)",
        "CREATE TABLE brc_ticket_bound_protected_submit_attempts (ticket_id TEXT, exchange_write_called BOOLEAN)",
        "CREATE TABLE brc_ticket_bound_exchange_commands (ticket_id TEXT, command_state TEXT, dispatch_started_at_ms BIGINT, exchange_order_id TEXT)",
        "CREATE TABLE brc_account_exposure_current (owner_ticket_id TEXT, position_slot_claimed BOOLEAN)",
        "CREATE TABLE brc_budget_reservation_events (budget_reservation_event_id TEXT PRIMARY KEY, budget_reservation_id TEXT, from_status TEXT, to_status TEXT, reason TEXT, evidence_ref TEXT, created_at_ms BIGINT)",
    ):
        conn.execute(sa.text(statement))


def test_backfill_reclaims_only_terminal_presubmit_capacity_setwise() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        _create_terminal_capacity_repair_tables(conn)
        conn.execute(
            sa.text(
                "INSERT INTO brc_action_time_tickets VALUES "
                "('safe', 'expired', NULL), "
                "('written', 'expired', NULL), "
                "('unknown-command', 'expired', NULL), "
                "('null-command', 'expired', NULL), "
                "('slot-claimed', 'expired', NULL), "
                "('nonterminal', 'ready', NULL)"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO brc_budget_reservations VALUES "
                "('safe-budget', 'safe', 'consumed', NULL, NULL, 10, NULL, NULL, NULL), "
                "('written-budget', 'written', 'consumed', NULL, NULL, 20, NULL, NULL, NULL), "
                "('unknown-budget', 'unknown-command', 'consumed', NULL, NULL, 30, NULL, NULL, NULL), "
                "('null-command-budget', 'null-command', 'consumed', NULL, NULL, 35, NULL, NULL, NULL), "
                "('slot-budget', 'slot-claimed', 'consumed', NULL, NULL, 40, NULL, NULL, NULL), "
                "('nonterminal-budget', 'nonterminal', 'consumed', NULL, NULL, 50, NULL, NULL, NULL)"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO brc_ticket_bound_protected_submit_attempts "
                "VALUES ('written', true)"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO brc_ticket_bound_exchange_commands "
                "VALUES ('unknown-command', 'dispatching', 1, NULL), "
                "('null-command', NULL, NULL, NULL)"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO brc_account_exposure_current "
                "VALUES ('slot-claimed', true)"
            )
        )

        _upgrade(conn, BACKFILL, "migration_127_terminal_capacity")

        statuses = dict(
            conn.execute(
                sa.text(
                    "SELECT budget_reservation_id, status "
                    "FROM brc_budget_reservations"
                )
            ).all()
        )
        safe_release = conn.execute(
            sa.text(
                "SELECT release_reason, released_at_ms "
                "FROM brc_budget_reservations WHERE budget_reservation_id = 'safe-budget'"
            )
        ).mappings().one()
        events = conn.execute(
            sa.text(
                "SELECT budget_reservation_id, from_status, to_status, reason, evidence_ref "
                "FROM brc_budget_reservation_events"
            )
        ).all()

    assert statuses == {
        "safe-budget": "released",
        "written-budget": "consumed",
        "unknown-budget": "consumed",
        "null-command-budget": "consumed",
        "slot-budget": "consumed",
        "nonterminal-budget": "consumed",
    }
    assert dict(safe_release) == {
        "release_reason": "terminal_presubmit_ticket_capacity_reclaimed",
        "released_at_ms": 10,
    }
    assert events == [
        (
            "safe-budget",
            "consumed",
            "released",
            "terminal_presubmit_ticket_capacity_reclaimed",
            "migration:132",
        )
    ]


def test_backfill_timeout_aborts_before_constraint_phase() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        _upgrade_to_126(conn)
        _insert_mapping(
            conn,
            mapping_id="mapping-timeout",
            exchange_instrument_id="instrument-timeout",
            valid_from_ms=0,
            valid_until_ms=None,
            status="active",
        )
        _insert_reservation(
            conn,
            reservation_id="reservation-timeout",
            reserved_at_ms=100,
        )

        def raise_simulated_statement_timeout(
            _connection,
            _cursor,
            statement,
            _parameters,
            _context,
            _executemany,
        ) -> None:
            normalized = " ".join(statement.split()).lower()
            if (
                normalized.startswith("update brc_budget_reservations")
                and "set exchange_instrument_id" in normalized
            ):
                raise sa.exc.OperationalError(
                    statement,
                    {},
                    RuntimeError("simulated statement timeout"),
                )

        sa.event.listen(
            engine,
            "before_cursor_execute",
            raise_simulated_statement_timeout,
        )
        try:
            with pytest.raises(sa.exc.OperationalError, match="simulated statement timeout"):
                _upgrade(conn, BACKFILL, "migration_127_timeout")
        finally:
            sa.event.remove(
                engine,
                "before_cursor_execute",
                raise_simulated_statement_timeout,
            )

        index_names = {
            index["name"]
            for index in sa.inspect(conn).get_indexes("brc_budget_reservations")
        }

    source = BACKFILL.read_text()
    assert "SET LOCAL lock_timeout = '5s'" in source
    assert "SET LOCAL statement_timeout = '60s'" in source
    assert "uq_brc_budget_reservation_idempotency" not in index_names
    assert "uq_brc_budget_reservation_invocation" not in index_names


def _insert_mapping(
    conn: sa.Connection,
    *,
    mapping_id: str,
    exchange_instrument_id: str,
    valid_from_ms: int,
    valid_until_ms: int | None,
    status: str,
) -> None:
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_symbol_instrument_mappings (
              mapping_id, symbol, exchange_instrument_id, status,
              valid_from_ms, valid_until_ms, created_at_ms
            ) VALUES (
              :mapping_id, 'SOLUSDT', :exchange_instrument_id, :status,
              :valid_from_ms, :valid_until_ms, 1
            )
            """
        ),
        {
            "mapping_id": mapping_id,
            "exchange_instrument_id": exchange_instrument_id,
            "valid_from_ms": valid_from_ms,
            "valid_until_ms": valid_until_ms,
            "status": status,
        },
    )


def _insert_reservation(
    conn: sa.Connection,
    *,
    reservation_id: str,
    reserved_at_ms: int,
    ticket_id: str | None = None,
    status: str = "released",
) -> None:
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_budget_reservations (
              budget_reservation_id, promotion_candidate_id, action_time_lane_input_id,
              ticket_id, signal_event_id, event_spec_id, runtime_profile_id,
              account_id, strategy_group_id, symbol, side, target_notional,
              leverage, reserved_margin, reserved_at_ms, expires_at_ms, status,
              policy_version
            ) VALUES (
              :reservation_id, 'promotion-1', :lane_id, :ticket_id, 'signal-1',
              'event-spec-1', 'profile-1', 'account-1', 'MPG-001', 'SOLUSDT',
              'long', 100, 10, 10, :reserved_at_ms, :expires_at_ms, :status,
              'policy-v1'
            )
            """
        ),
        {
            "reservation_id": reservation_id,
            "lane_id": f"lane:{reservation_id}",
            "ticket_id": ticket_id,
            "reserved_at_ms": reserved_at_ms,
            "expires_at_ms": reserved_at_ms + 60_000,
            "status": status,
        },
    )


def _insert_ticket(
    conn: sa.Connection,
    *,
    ticket_id: str,
    reservation_id: str,
    exchange_instrument_id: str,
) -> None:
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_action_time_tickets (
              ticket_id, action_time_lane_input_id, promotion_candidate_id,
              signal_event_id, event_spec_id, event_spec_version_id,
              candidate_scope_id, runtime_scope_binding_id, strategy_group_id,
              strategy_group_version_id, symbol, exchange_instrument_id, side,
              event_id, event_time_ms, trigger_candle_close_time_ms,
              runtime_profile_id, public_fact_snapshot_id,
              action_time_fact_snapshot_id, account_safe_fact_snapshot_id,
              account_mode_snapshot_id, budget_reservation_id, protection_ref_id,
              execution_policy_id, execution_policy_version, owner_policy_version,
              sizing_policy_version, protection_policy_version, target_notional,
              leverage, expires_at_ms, status, authority_boundary, ticket_hash,
              created_under_versions_hash, created_at_ms
            ) VALUES (
              :ticket_id, :lane_id, 'promotion-1', 'signal-1', 'event-spec-1',
              'event-spec-version-1', 'scope-1', 'runtime-scope-1', 'MPG-001',
              'strategy-version-1', 'SOLUSDT', :exchange_instrument_id, 'long',
              'event-1', 100, 100, 'profile-1', 'public-fact-1',
              'action-fact-1', 'account-safe-fact-1', 'account-mode-fact-1',
              :reservation_id, 'protection-1', 'execution-policy-1', 'v1', 'v1',
              'v1', 'v1', 100, 10, 60_100, 'closed', 'unit', :ticket_hash,
              'versions-hash-1', 100
            )
            """
        ),
        {
            "ticket_id": ticket_id,
            "lane_id": f"lane:{reservation_id}",
            "reservation_id": reservation_id,
            "exchange_instrument_id": exchange_instrument_id,
            "ticket_hash": f"ticket-hash:{ticket_id}",
        },
    )


def _complete_claim_columns(conn: sa.Connection, reservation_id: str) -> None:
    conn.execute(
        sa.text(
            """
            UPDATE brc_budget_reservations
            SET exchange_instrument_id = 'instrument-1',
                exposure_episode_id = 'episode-1',
                action_time_invocation_id = 'invocation-1',
                asset_class = 'crypto',
                instrument_type = 'perpetual',
                settlement_asset = 'USDT',
                margin_asset = 'USDT',
                instrument_rule_snapshot_id = 'rule-snapshot-1',
                instrument_rule_schema_version = 'v1',
                pricing_source_fact_snapshot_id = 'pricing-fact-1',
                account_source_fact_snapshot_id = 'account-fact-1',
                account_fact_schema_version = 'v1',
                primary_risk_cluster_id = 'cluster-1',
                cluster_membership_snapshot_id = 'membership-snapshot-1',
                capacity_claim_schema_version = 'v1',
                capacity_claim_hash = 'a',
                reservation_idempotency_key = 'claim-key-1',
                account_risk_policy_version = 'risk-policy-v1',
                account_risk_policy_event_id = 'risk-policy-event-1',
                allowed_risk_budget = 2.5,
                margin_accounting_state = 'reserved_unreflected',
                account_capacity_projection_version = 1
            WHERE budget_reservation_id = :reservation_id
            """
        ),
        {"reservation_id": reservation_id},
    )


def _complete_ticket_lineage(
    conn: sa.Connection,
    *,
    ticket_id: str,
) -> None:
    conn.execute(
        sa.text(
            """
            UPDATE brc_action_time_tickets
            SET exposure_episode_id = 'episode-1',
                asset_class = 'crypto',
                instrument_type = 'perpetual',
                capacity_claim_hash = 'a'
            WHERE ticket_id = :ticket_id
            """
        ),
        {"ticket_id": ticket_id},
    )


def test_migration_126_expands_nullable_asset_neutral_identity_structure() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        _upgrade_to_125(conn)
        if "brc_runtime_process_outcomes" not in sa.inspect(conn).get_table_names():
            conn.execute(
                sa.text(
                    "CREATE TABLE brc_runtime_process_outcomes "
                    "(process_outcome_id TEXT PRIMARY KEY)"
                )
            )
        _upgrade(conn, EXPAND, "migration_126_asset_neutral")

        tables = set(sa.inspect(conn).get_table_names())
        candidate_columns = _columns(conn, "brc_strategy_group_candidate_scope")
        live_signal_columns = _columns(conn, "brc_live_signal_events")
        process_outcome_columns = _columns(conn, "brc_runtime_process_outcomes")
        coverage_columns = _columns(conn, "brc_watcher_runtime_coverage")
        instrument_columns = _columns(conn, "brc_exchange_instruments")
        reservation_columns = _columns(conn, "brc_budget_reservations")
        ticket_columns = _columns(conn, "brc_action_time_tickets")
        exposure_columns = _columns(conn, "brc_account_exposure_current")
        command_columns = _columns(conn, "brc_ticket_bound_exchange_commands")
        membership_columns = _columns(conn, "brc_risk_cluster_memberships")

    assert {
        "brc_instrument_rule_snapshots",
        "brc_risk_cluster_membership_snapshots",
    } <= tables
    assert {"exchange_instrument_id"} <= candidate_columns
    assert {"exchange_instrument_id"} <= live_signal_columns
    assert {"exchange_instrument_id"} <= process_outcome_columns
    assert {"exchange_instrument_id"} <= coverage_columns
    assert {
        "instrument_type",
        "settlement_asset",
        "margin_asset",
        "instrument_identity_schema_version",
    } <= instrument_columns
    assert {
        "exposure_episode_id",
        "action_time_invocation_id",
        "asset_class",
        "instrument_type",
        "settlement_asset",
        "margin_asset",
        "instrument_rule_snapshot_id",
        "instrument_rule_schema_version",
        "pricing_source_fact_snapshot_id",
        "account_source_fact_snapshot_id",
        "account_fact_schema_version",
        "primary_risk_cluster_id",
        "cluster_membership_snapshot_id",
        "capacity_claim_schema_version",
        "capacity_claim_hash",
        "reservation_idempotency_key",
        "reconciliation_state",
        "released_at_ms",
        "invalidated_at_ms",
        "current_first_blocker",
    } <= reservation_columns
    assert {
        "exposure_episode_id",
        "asset_class",
        "instrument_type",
        "capacity_claim_hash",
    } <= ticket_columns
    assert {
        "asset_class",
        "instrument_type",
        "current_exposure_episode_id",
        "primary_risk_cluster_id",
        "cluster_membership_snapshot_id",
        "account_source_fact_snapshot_id",
        "account_fact_schema_version",
    } <= exposure_columns
    assert {"exposure_episode_id"} <= command_columns
    assert {
        "cluster_membership_snapshot_id",
        "membership_role",
        "status",
    } <= membership_columns


def test_backfill_uses_mapping_valid_at_reservation_time() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        _upgrade_to_126(conn)
        _insert_mapping(
            conn,
            mapping_id="mapping-old",
            exchange_instrument_id="instrument-old",
            valid_from_ms=0,
            valid_until_ms=200,
            status="retired",
        )
        _insert_mapping(
            conn,
            mapping_id="mapping-current",
            exchange_instrument_id="instrument-current",
            valid_from_ms=200,
            valid_until_ms=None,
            status="active",
        )
        _insert_reservation(
            conn,
            reservation_id="reservation-historical",
            reserved_at_ms=100,
        )

        _upgrade(conn, BACKFILL, "migration_127_historical_mapping")
        instrument_id = conn.execute(
            sa.text(
                "SELECT exchange_instrument_id FROM brc_budget_reservations "
                "WHERE budget_reservation_id = 'reservation-historical'"
            )
        ).scalar_one()

    assert instrument_id == "instrument-old"


def test_current_mapping_cannot_rewrite_historical_ticket() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        _upgrade_to_126(conn)
        _insert_mapping(
            conn,
            mapping_id="mapping-current",
            exchange_instrument_id="instrument-current",
            valid_from_ms=0,
            valid_until_ms=None,
            status="active",
        )
        _insert_reservation(
            conn,
            reservation_id="reservation-ticket-bound",
            reserved_at_ms=100,
            ticket_id="ticket-historical",
        )
        _insert_ticket(
            conn,
            ticket_id="ticket-historical",
            reservation_id="reservation-ticket-bound",
            exchange_instrument_id="instrument-ticket-historical",
        )

        _upgrade(conn, BACKFILL, "migration_127_ticket_truth")
        instrument_id = conn.execute(
            sa.text(
                "SELECT exchange_instrument_id FROM brc_budget_reservations "
                "WHERE budget_reservation_id = 'reservation-ticket-bound'"
            )
        ).scalar_one()

    assert instrument_id == "instrument-ticket-historical"


def test_terminal_released_history_may_remain_audit_only() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        _upgrade_to_126(conn)
        _insert_reservation(
            conn,
            reservation_id="reservation-terminal-unresolved",
            reserved_at_ms=100,
            status="released",
        )

        _upgrade(conn, BACKFILL, "migration_127_terminal_audit")
        row = conn.execute(
            sa.text(
                """
                SELECT exchange_instrument_id, reconciliation_state, current_first_blocker
                FROM brc_budget_reservations
                WHERE budget_reservation_id = 'reservation-terminal-unresolved'
                """
            )
        ).mappings().one()

    assert row["exchange_instrument_id"] is None
    assert row["reconciliation_state"] == "legacy_audit_only"
    assert row["current_first_blocker"] == "legacy_audit_only_identity_unresolved"


def test_unresolved_active_claim_aborts_constraint_phase_before_new_indexes() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        _upgrade_to_126(conn)
        _insert_reservation(
            conn,
            reservation_id="reservation-active-unresolved",
            reserved_at_ms=100,
            status="active",
        )
        _upgrade(conn, BACKFILL, "migration_127_active_unresolved")

        with pytest.raises(RuntimeError, match="asset_neutral_active_claim_unresolved"):
            _upgrade(conn, ENFORCE, "migration_128_active_unresolved")

        index_names = {
            index["name"]
            for index in sa.inspect(conn).get_indexes("brc_strategy_group_candidate_scope")
        }

    assert "uq_brc_candidate_scope_active_instrument_timeframe" not in index_names


def test_migration_128_replaces_legacy_candidate_identity_index_and_adds_hot_path_indexes() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        _upgrade_to_126(conn)
        _upgrade(conn, BACKFILL, "migration_127_empty_enforcement")
        _upgrade(conn, ENFORCE, "migration_128_indexes")

        candidate_indexes = {
            index["name"]
            for index in sa.inspect(conn).get_indexes("brc_strategy_group_candidate_scope")
        }
        reservation_indexes = {
            index["name"]
            for index in sa.inspect(conn).get_indexes("brc_budget_reservations")
        }
        exposure_indexes = {
            index["name"]
            for index in sa.inspect(conn).get_indexes("brc_account_exposure_current")
        }
        command_indexes = {
            index["name"]
            for index in sa.inspect(conn).get_indexes("brc_ticket_bound_exchange_commands")
        }

    assert "uq_brc_candidate_scope_active" not in candidate_indexes
    assert "uq_brc_candidate_scope_active_instrument_timeframe" in candidate_indexes
    assert {
        "uq_brc_budget_reservation_idempotency",
        "uq_brc_budget_reservation_invocation",
        "idx_brc_budget_reservation_effective_hot_path",
    } <= reservation_indexes
    assert "idx_brc_account_exposure_current_hot_path" in exposure_indexes
    assert "idx_brc_exchange_command_nonterminal_evidence" in command_indexes


def test_complete_active_claim_reaches_constraint_phase_and_keeps_idempotency_unique() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        _upgrade_to_126(conn)
        _insert_reservation(
            conn,
            reservation_id="reservation-complete-active",
            reserved_at_ms=100,
            ticket_id="ticket-complete-active",
            status="active",
        )
        _insert_ticket(
            conn,
            ticket_id="ticket-complete-active",
            reservation_id="reservation-complete-active",
            exchange_instrument_id="instrument-1",
        )
        _complete_claim_columns(conn, "reservation-complete-active")
        _complete_ticket_lineage(conn, ticket_id="ticket-complete-active")
        _upgrade(conn, BACKFILL, "migration_127_complete_active")
        _upgrade(conn, ENFORCE, "migration_128_complete_active")
        _insert_reservation(
            conn,
            reservation_id="reservation-second-key",
            reserved_at_ms=200,
            status="released",
        )

        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                sa.text(
                    """
                    UPDATE brc_budget_reservations
                    SET reservation_idempotency_key = 'claim-key-1'
                    WHERE budget_reservation_id = 'reservation-second-key'
                    """
                )
            )


def test_complete_active_claim_without_matching_ticket_aborts_constraint_phase() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        _upgrade_to_126(conn)
        _insert_reservation(
            conn,
            reservation_id="reservation-orphan-active",
            reserved_at_ms=100,
            ticket_id="ticket-missing",
            status="active",
        )
        _complete_claim_columns(conn, "reservation-orphan-active")
        _upgrade(conn, BACKFILL, "migration_127_orphan_active")

        with pytest.raises(
            RuntimeError,
            match="asset_neutral_active_claim_ticket_lineage_unresolved",
        ):
            _upgrade(conn, ENFORCE, "migration_128_orphan_active")
