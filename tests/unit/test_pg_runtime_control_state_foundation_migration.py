from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py"
)
MIGRATION_087_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/2026-07-05-087_harden_live_signal_event_time_authority.py"
)


def _load_migration(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(
        name,
        path,
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


@pytest.fixture()
def connection():
    migration_086 = _load_migration(
        MIGRATION_PATH,
        "migration_086_runtime_control_state_foundation",
    )
    migration_087 = _load_migration(
        MIGRATION_087_PATH,
        "migration_087_live_signal_event_time_authority",
    )
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        _run_migration(conn, migration_086)
        _run_migration(conn, migration_087)
    with engine.connect() as conn:
        yield conn
    engine.dispose()


def _run_migration(conn, migration) -> None:
    old_op = migration.op
    migration.op = Operations(MigrationContext.configure(conn))
    try:
        migration.upgrade()
    finally:
        migration.op = old_op


def _expect_integrity_error(conn, statement: str, params: dict[str, object]) -> None:
    savepoint = conn.begin_nested()
    try:
        with pytest.raises(IntegrityError):
            conn.execute(text(statement), params)
    finally:
        savepoint.rollback()


def test_migration_creates_runtime_control_state_foundation_tables(connection):
    tables = set(inspect(connection).get_table_names())

    assert {
        "brc_strategy_groups",
        "brc_strategy_group_versions",
        "brc_required_fact_contracts",
        "brc_strategy_side_event_specs",
        "brc_strategy_event_required_facts",
        "brc_strategy_group_candidate_scope",
        "brc_candidate_scope_event_bindings",
        "brc_runtime_scope_bindings",
        "brc_market_data_quality_events",
        "brc_live_signal_events",
        "brc_promotion_candidates",
        "brc_action_time_lane_inputs",
        "brc_budget_reservations",
        "brc_protection_references",
        "brc_execution_policies",
        "brc_action_time_tickets",
        "brc_action_time_ticket_events",
        "brc_operation_layer_handoffs",
        "brc_runtime_safety_state_snapshots",
        "brc_projection_runs",
        "brc_current_projection_ownership",
        "brc_legacy_diagnostics",
        "brc_server_monitor_runs",
        "brc_server_monitor_notifications",
        "brc_runtime_incidents",
        "brc_recovery_runs",
        "brc_strategy_intake_cases",
        "brc_strategy_intake_stage_events",
        "brc_strategy_review_outcomes",
        "brc_strategy_governance_decisions",
        "brc_strategy_policy_change_requests",
    }.issubset(tables)


def test_087_upgrades_already_applied_086_live_signal_schema_fail_closed():
    migration_087 = _load_migration(
        MIGRATION_087_PATH,
        "migration_087_old_086_live_signal_upgrade",
    )
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE brc_live_signal_events (
                    signal_event_id VARCHAR(192) PRIMARY KEY,
                    candidate_scope_id VARCHAR(160),
                    event_spec_id VARCHAR(160) NOT NULL,
                    strategy_group_id VARCHAR(128) NOT NULL,
                    symbol VARCHAR(128) NOT NULL,
                    side VARCHAR(32) NOT NULL,
                    detector_key VARCHAR(128) NOT NULL,
                    signal_type VARCHAR(64) NOT NULL,
                    status VARCHAR(64) NOT NULL,
                    freshness_state VARCHAR(64) NOT NULL,
                    confidence NUMERIC(18, 8),
                    fact_snapshot_id VARCHAR(192),
                    reason_codes JSON NOT NULL DEFAULT '[]',
                    signal_payload JSON NOT NULL DEFAULT '{}',
                    observed_at_ms BIGINT NOT NULL,
                    expires_at_ms BIGINT,
                    invalidated_at_ms BIGINT,
                    created_at_ms BIGINT NOT NULL,
                    CONSTRAINT ck_brc_live_signal_side CHECK (side IN ('long', 'short')),
                    CONSTRAINT ck_brc_live_signal_status CHECK (
                        status IN ('detected', 'facts_validated', 'stale', 'rejected', 'superseded')
                    ),
                    CONSTRAINT ck_brc_live_signal_freshness CHECK (
                        freshness_state IN ('fresh', 'stale', 'expired', 'unknown')
                    ),
                    CONSTRAINT ck_brc_live_signal_fresh_valid CHECK (
                        freshness_state <> 'fresh'
                        OR (status = 'facts_validated' AND expires_at_ms IS NOT NULL)
                    ),
                    CONSTRAINT uq_brc_live_signal_identity UNIQUE (
                        strategy_group_id, symbol, side, detector_key, signal_type, observed_at_ms
                    )
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO brc_live_signal_events (
                    signal_event_id, candidate_scope_id, event_spec_id,
                    strategy_group_id, symbol, side, detector_key, signal_type,
                    status, freshness_state, confidence, fact_snapshot_id,
                    reason_codes, signal_payload, observed_at_ms, expires_at_ms,
                    invalidated_at_ms, created_at_ms
                ) VALUES (
                    'legacy-fresh', 'scope-1', 'SOR-LONG-v1', 'SOR-001',
                    'ETHUSDT', 'long', 'sor-detector', 'SOR-LONG',
                    'facts_validated', 'fresh', NULL, 'facts-1', '[]', '{}',
                    1770000000000, 1770000060000, NULL, 1770000001000
                )
                """
            )
        )
        _run_migration(conn, migration_087)

        columns = {column["name"]: column for column in inspect(conn).get_columns("brc_live_signal_events")}
        assert columns["source_kind"]["nullable"] is False
        assert columns["event_time_ms"]["nullable"] is False
        assert columns["trigger_candle_close_time_ms"]["nullable"] is False

        legacy_row = conn.execute(
            text(
                """
                SELECT source_kind, status, freshness_state, event_time_ms,
                       trigger_candle_close_time_ms, observed_at_ms, created_at_ms
                FROM brc_live_signal_events
                WHERE signal_event_id = 'legacy-fresh'
                """
            )
        ).mappings().one()
        assert legacy_row["source_kind"] == "historical"
        assert legacy_row["status"] == "stale"
        assert legacy_row["freshness_state"] == "stale"
        assert legacy_row["event_time_ms"] == legacy_row["trigger_candle_close_time_ms"]
        assert legacy_row["event_time_ms"] == legacy_row["observed_at_ms"]
        assert legacy_row["event_time_ms"] != legacy_row["created_at_ms"]

        upgraded_insert = """
            INSERT INTO brc_live_signal_events (
                signal_event_id, candidate_scope_id, event_spec_id,
                strategy_group_id, symbol, side, detector_key, signal_type,
                source_kind, status, freshness_state, confidence, fact_snapshot_id,
                reason_codes, signal_payload, event_time_ms,
                trigger_candle_close_time_ms, observed_at_ms, expires_at_ms,
                invalidated_at_ms, created_at_ms
            ) VALUES (
                :id, 'scope-1', 'SOR-LONG-v1', 'SOR-001', :symbol, 'long',
                'sor-detector', 'SOR-LONG', :source_kind, 'facts_validated',
                'fresh', NULL, 'facts-1', '[]', '{}', :event_time_ms,
                :trigger_candle_close_time_ms, :observed_at_ms, 1770000300000,
                NULL, :created_at_ms
            )
        """
        conn.execute(
            text(upgraded_insert),
            {
                "id": "upgraded-live-valid",
                "symbol": "SOLUSDT",
                "source_kind": "live_market",
                "event_time_ms": 1770000120000,
                "trigger_candle_close_time_ms": 1770000120000,
                "observed_at_ms": 1770000120001,
                "created_at_ms": 1770000120002,
            },
        )
        _expect_integrity_error(
            conn,
            upgraded_insert,
            {
                "id": "upgraded-replay-fresh",
                "symbol": "AVAXUSDT",
                "source_kind": "replay",
                "event_time_ms": 1770000180000,
                "trigger_candle_close_time_ms": 1770000180000,
                "observed_at_ms": 1770000180001,
                "created_at_ms": 1770000180002,
            },
        )
        _expect_integrity_error(
            conn,
            upgraded_insert,
            {
                "id": "upgraded-event-mismatch",
                "symbol": "BTCUSDT",
                "source_kind": "live_market",
                "event_time_ms": 1770000240000,
                "trigger_candle_close_time_ms": 1770000241000,
                "observed_at_ms": 1770000241001,
                "created_at_ms": 1770000241002,
            },
        )
        _expect_integrity_error(
            conn,
            upgraded_insert,
            {
                "id": "upgraded-generated-at-event-time",
                "symbol": "OPUSDT",
                "source_kind": "live_market",
                "event_time_ms": 1770000300000,
                "trigger_candle_close_time_ms": 1770000300000,
                "observed_at_ms": 1770000300001,
                "created_at_ms": 1770000300000,
            },
        )
    engine.dispose()


def test_strategy_group_versions_have_one_current_version(connection):
    statement = """
        INSERT INTO brc_strategy_group_versions (
            strategy_group_version_id, strategy_group_id, version, status,
            edge_thesis, trade_logic, regime_fit, supported_sides,
            supported_timeframes, risk_envelope, promotion_rules,
            evidence_refs, created_at_ms, created_by
        ) VALUES (
            :id, 'MPG-001', :version, :status, 'momentum edge',
            'trade pullback continuation', 'crypto momentum regime',
            '["long"]', '["1h"]', '{}', '{}', '[]',
            1770000000000, 'codex_seed'
        )
    """
    connection.execute(
        text(statement),
        {"id": "mpg-v1", "version": 1, "status": "current"},
    )

    _expect_integrity_error(
        connection,
        statement,
        {"id": "mpg-v2-current", "version": 2, "status": "current"},
    )
    connection.execute(
        text(statement),
        {"id": "mpg-v2-draft", "version": 2, "status": "draft"},
    )


def test_required_fact_contracts_reject_transitional_v0_semantics(connection):
    statement = """
        INSERT INTO brc_required_fact_contracts (
            fact_contract_id, strategy_group_version_id, fact_key, fact_group,
            required_surface, source_kind, freshness_ms, missing_blocker_class,
            failed_blocker_class, required_for_live_submit, definition_payload,
            created_at_ms
        ) VALUES (
            :id, 'MI-001-v1', :fact_key, 'strategy', 'finalgate',
            'derived', 3600000, 'fact_missing', 'computed_not_satisfied',
            true, '{}', 1770000000000
        )
    """
    connection.execute(
        text(statement),
        {"id": "fact-contract-valid", "fact_key": "relative_strength_confirmed"},
    )

    _expect_integrity_error(
        connection,
        statement,
        {
            "id": "fact-contract-v0-exception",
            "fact_key": "explicit_not_required_for_v0",
        },
    )


def test_required_facts_are_machine_evaluable_and_reject_v0_exception(connection):
    valid_insert = """
        INSERT INTO brc_strategy_event_required_facts (
            event_required_fact_id, event_spec_id, required_facts_version_id,
            fact_key, fact_role, fact_surface, operator, expected_value,
            value_source, disable_on_match, missing_blocker_class,
            failed_blocker_class, freshness_ms, required_for_promotion,
            required_for_ticket, required_for_finalgate, status, created_at_ms
        ) VALUES (
            :id, 'MI-LONG-v1', 'rf-v1', :fact_key, 'required',
            'public_pretrade', :operator, NULL, :value_source, false,
            'fact_missing', 'computed_not_satisfied', 3600000,
            true, true, true, 'current', 1770000000000
        )
    """
    connection.execute(
        text(valid_insert),
        {
            "id": "rf-valid",
            "fact_key": "relative_strength_confirmed",
            "operator": "eq",
            "value_source": "detector_fact",
        },
    )

    _expect_integrity_error(
        connection,
        valid_insert,
        {
            "id": "rf-bad-operator",
            "fact_key": "relative_strength_confirmed_alt",
            "operator": "free_text_condition",
            "value_source": "detector_fact",
        },
    )
    _expect_integrity_error(
        connection,
        valid_insert,
        {
            "id": "rf-v0-exception",
            "fact_key": "explicit_not_required_for_v0",
            "operator": "eq",
            "value_source": "detector_fact",
        },
    )


def test_strategy_side_event_specs_have_one_current_event_version(connection):
    statement = """
        INSERT INTO brc_strategy_side_event_specs (
            event_spec_id, strategy_group_id, strategy_group_version_id,
            event_id, side, timeframe, event_spec_version, status,
            freshness_window_ms, time_authority, protection_ref_type,
            created_at_ms, created_by
        ) VALUES (
            :id, 'SOR-001', 'sgv:SOR-001:v1', 'SOR-LONG', 'long',
            '15m', :version, :status, 900000,
            'trigger_candle_close_time_ms', 'opening_range_low_reference',
            1770000000000, 'codex_seed'
        )
    """
    connection.execute(
        text(statement),
        {"id": "event-spec-current-v1", "version": "v1", "status": "current"},
    )

    _expect_integrity_error(
        connection,
        statement,
        {"id": "event-spec-current-v2", "version": "v2", "status": "current"},
    )
    connection.execute(
        text(statement),
        {"id": "event-spec-retired-v2", "version": "v2", "status": "retired"},
    )


def test_live_signal_freshness_requires_validated_signal(connection):
    statement = """
        INSERT INTO brc_live_signal_events (
            signal_event_id, candidate_scope_id, event_spec_id, strategy_group_id,
            symbol, side, detector_key, signal_type, status, freshness_state,
            source_kind, confidence, fact_snapshot_id, event_time_ms,
            trigger_candle_close_time_ms, observed_at_ms, expires_at_ms,
            invalidated_at_ms, created_at_ms
        ) VALUES (
            :id, 'scope-1', 'SOR-LONG-v1', 'SOR-001', 'ETHUSDT', 'long',
            'sor-detector', 'SOR-LONG', :status, :freshness_state,
            :source_kind, NULL, 'facts-1', :event_time_ms,
            :trigger_candle_close_time_ms, 1770000000002, :expires_at_ms,
            NULL, :created_at_ms
        )
    """
    connection.execute(
        text(statement),
        {
            "id": "signal-valid",
            "status": "facts_validated",
            "freshness_state": "fresh",
            "source_kind": "live_market",
            "event_time_ms": 1770000000000,
            "trigger_candle_close_time_ms": 1770000000000,
            "expires_at_ms": 1770000060000,
            "created_at_ms": 1770000000001,
        },
    )

    _expect_integrity_error(
        connection,
        statement,
        {
            "id": "signal-invalid-detected-fresh",
            "status": "detected",
            "freshness_state": "fresh",
            "source_kind": "live_market",
            "event_time_ms": 1770000060000,
            "trigger_candle_close_time_ms": 1770000060000,
            "expires_at_ms": 1770000060000,
            "created_at_ms": 1770000060001,
        },
    )
    _expect_integrity_error(
        connection,
        statement,
        {
            "id": "signal-invalid-fresh-no-expiry",
            "status": "facts_validated",
            "freshness_state": "fresh",
            "source_kind": "live_market",
            "event_time_ms": 1770000120000,
            "trigger_candle_close_time_ms": 1770000120000,
            "expires_at_ms": None,
            "created_at_ms": 1770000120001,
        },
    )
    _expect_integrity_error(
        connection,
        statement,
        {
            "id": "signal-invalid-fresh-replay-source",
            "status": "facts_validated",
            "freshness_state": "fresh",
            "source_kind": "replay",
            "event_time_ms": 1770000180000,
            "trigger_candle_close_time_ms": 1770000180000,
            "expires_at_ms": 1770000240000,
            "created_at_ms": 1770000180001,
        },
    )
    _expect_integrity_error(
        connection,
        statement,
        {
            "id": "signal-invalid-event-time-mismatch",
            "status": "facts_validated",
            "freshness_state": "fresh",
            "source_kind": "live_market",
            "event_time_ms": 1770000300000,
            "trigger_candle_close_time_ms": 1770000360000,
            "expires_at_ms": 1770000420000,
            "created_at_ms": 1770000300001,
        },
    )
    _expect_integrity_error(
        connection,
        statement,
        {
            "id": "signal-invalid-generated-at-event-time",
            "status": "facts_validated",
            "freshness_state": "fresh",
            "source_kind": "live_market",
            "event_time_ms": 1770000480000,
            "trigger_candle_close_time_ms": 1770000480000,
            "expires_at_ms": 1770000540000,
            "created_at_ms": 1770000480000,
        },
    )


def test_runtime_scope_live_submit_requires_closed_scope(connection):
    statement = """
        INSERT INTO brc_runtime_scope_bindings (
            runtime_scope_binding_id, candidate_scope_id, strategy_group_id,
            symbol, side, runtime_profile_id, selected_strategygroup_scope,
            symbol_side_scope_closed, notional_leverage_scope_closed,
            server_runtime_coverage_required, live_submit_allowed,
            conditional_hard_gates, policy_current_id, status, valid_from_ms,
            valid_until_ms, authority_boundary, created_at_ms, updated_at_ms
        ) VALUES (
            :id, :candidate_scope_id, 'MPG-001', :symbol, 'long',
            'tiny-live-profile', :selected_strategygroup_scope,
            :symbol_side_scope_closed, :notional_leverage_scope_closed,
            true, :live_submit_allowed, '[]', :policy_current_id, 'active',
            1770000000000, NULL, 'non bypass runtime scope boundary',
            1770000000000, 1770000000000
        )
    """
    connection.execute(
        text(statement),
        {
            "id": "runtime-scope-observe-only",
            "candidate_scope_id": "candidate-scope-observe-only",
            "symbol": "OPUSDT",
            "policy_current_id": "policy-current-observe-only",
            "selected_strategygroup_scope": False,
            "symbol_side_scope_closed": False,
            "notional_leverage_scope_closed": False,
            "live_submit_allowed": False,
        },
    )

    _expect_integrity_error(
        connection,
        statement,
        {
            "id": "runtime-scope-live-submit-without-notional",
            "candidate_scope_id": "candidate-scope-without-notional",
            "symbol": "SOLUSDT",
            "policy_current_id": "policy-current-without-notional",
            "selected_strategygroup_scope": True,
            "symbol_side_scope_closed": True,
            "notional_leverage_scope_closed": False,
            "live_submit_allowed": True,
        },
    )
    connection.execute(
        text(statement),
        {
            "id": "runtime-scope-live-submit-closed",
            "candidate_scope_id": "candidate-scope-closed",
            "symbol": "AVAXUSDT",
            "policy_current_id": "policy-current-closed",
            "selected_strategygroup_scope": True,
            "symbol_side_scope_closed": True,
            "notional_leverage_scope_closed": True,
            "live_submit_allowed": True,
        },
    )


def test_only_one_open_real_submit_lane_is_allowed(connection):
    statement = """
        INSERT INTO brc_action_time_lane_inputs (
            action_time_lane_input_id, promotion_candidate_id, strategy_group_id,
            symbol, side, runtime_profile_id, lane_scope, status, signal_event_id,
            public_fact_snapshot_id, action_time_fact_snapshot_id,
            runtime_scope_binding_id, candidate_authorization_ref,
            runtime_safety_snapshot_id, first_blocker_class, created_at_ms,
            expires_at_ms, closed_at_ms, authority_boundary
        ) VALUES (
            :id, :promotion_id, :strategy_group_id, :symbol, 'long',
            'tiny-live-profile', 'real_submit_candidate', :status, 'signal-1',
            'public-facts-1', 'action-facts-1', 'scope-binding-1', NULL, NULL,
            NULL, 1770000000000, 1770000060000, NULL, 'non_authority'
        )
    """
    connection.execute(
        text(statement),
        {
            "id": "lane-open-1",
            "promotion_id": "promo-1",
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "status": "opened",
        },
    )

    _expect_integrity_error(
        connection,
        statement,
        {
            "id": "lane-open-2",
            "promotion_id": "promo-2",
            "strategy_group_id": "MPG-001",
            "symbol": "OPUSDT",
            "status": "facts_refreshing",
        },
    )
    connection.execute(
        text(statement),
        {
            "id": "lane-closed",
            "promotion_id": "promo-3",
            "strategy_group_id": "CPM-RO-001",
            "symbol": "SOLUSDT",
            "status": "closed",
        },
    )


def test_budget_reservation_can_precede_ticket_but_ticket_binding_is_unique(connection):
    statement = """
        INSERT INTO brc_budget_reservations (
            budget_reservation_id, promotion_candidate_id, action_time_lane_input_id,
            ticket_id, signal_event_id, event_spec_id, runtime_profile_id, account_id,
            strategy_group_id, symbol, side, target_notional, leverage,
            reserved_margin, reserved_at_ms, expires_at_ms, status,
            release_reason, policy_version
        ) VALUES (
            :id, :promotion_id, :lane_id, :ticket_id, 'signal-1', 'SOR-LONG-v1',
            'tiny-live-profile', 'subaccount-1', 'SOR-001', :symbol, 'long',
            20, 2, 10, 1770000000000, 1770000060000, :status, NULL, 'policy-v1'
        )
    """
    connection.execute(
        text(statement),
        {
            "id": "reservation-before-ticket",
            "promotion_id": "promo-1",
            "lane_id": "lane-budget-1",
            "ticket_id": None,
            "symbol": "ETHUSDT",
            "status": "active",
        },
    )
    connection.execute(
        text(statement),
        {
            "id": "reservation-with-ticket",
            "promotion_id": "promo-2",
            "lane_id": "lane-budget-2",
            "ticket_id": "ticket-1",
            "symbol": "SOLUSDT",
            "status": "active",
        },
    )

    _expect_integrity_error(
        connection,
        statement,
        {
            "id": "reservation-duplicate-ticket",
            "promotion_id": "promo-3",
            "lane_id": "lane-budget-3",
            "ticket_id": "ticket-1",
            "symbol": "AVAXUSDT",
            "status": "active",
        },
    )
    _expect_integrity_error(
        connection,
        statement,
        {
            "id": "reservation-duplicate-active-lane",
            "promotion_id": "promo-4",
            "lane_id": "lane-budget-1",
            "ticket_id": None,
            "symbol": "BTCUSDT",
            "status": "active",
        },
    )


def test_execution_policy_has_one_current_scope_and_numeric_bounds(connection):
    statement = """
        INSERT INTO brc_execution_policies (
            execution_policy_id, execution_policy_version, runtime_profile_id,
            strategy_group_id, event_spec_id, side, order_type, time_in_force,
            reduce_only, post_only, close_position, allowed_slippage_bps,
            price_protection_mode, submit_deadline_ms,
            cancel_if_not_filled_policy, status, created_at_ms, created_by
        ) VALUES (
            :id, :version, 'tiny-live-profile', 'SOR-001', 'SOR-LONG-v1',
            'long', 'market', 'IOC', false, false, false, :slippage_bps,
            'bounded_market', :deadline_ms, '{}', :status, 1770000000000,
            'codex_seed'
        )
    """
    connection.execute(
        text(statement),
        {
            "id": "exec-policy-current",
            "version": "exec-v1",
            "slippage_bps": 25,
            "deadline_ms": 30000,
            "status": "current",
        },
    )

    _expect_integrity_error(
        connection,
        statement,
        {
            "id": "exec-policy-duplicate-current",
            "version": "exec-v2",
            "slippage_bps": 25,
            "deadline_ms": 30000,
            "status": "current",
        },
    )
    _expect_integrity_error(
        connection,
        statement,
        {
            "id": "exec-policy-invalid-bounds",
            "version": "exec-v3",
            "slippage_bps": -1,
            "deadline_ms": 30000,
            "status": "retired",
        },
    )


def test_action_time_ticket_events_reject_forbidden_status_transitions(connection):
    statement = """
        INSERT INTO brc_action_time_ticket_events (
            ticket_event_id, ticket_id, action_time_lane_input_id, from_status,
            to_status, transition_reason, trigger_ref, writer, event_payload,
            occurred_at_ms, created_at_ms
        ) VALUES (
            :id, 'ticket-1', 'lane-1', :from_status, :to_status,
            'test transition', NULL, 'runtime_ticket_projector', '{}',
            1770000000000, 1770000000001
        )
    """
    connection.execute(
        text(statement),
        {
            "id": "ticket-event-created",
            "from_status": None,
            "to_status": "created",
        },
    )
    connection.execute(
        text(statement),
        {
            "id": "ticket-event-preflight",
            "from_status": "created",
            "to_status": "preflight_pending",
        },
    )

    _expect_integrity_error(
        connection,
        statement,
        {
            "id": "ticket-event-expired-to-finalgate",
            "from_status": "expired",
            "to_status": "finalgate_ready",
        },
    )
    _expect_integrity_error(
        connection,
        statement,
        {
            "id": "ticket-event-rejected-to-submitted",
            "from_status": "finalgate_rejected",
            "to_status": "submitted",
        },
    )


def test_legacy_diagnostics_cannot_set_current_blockers(connection):
    statement = """
        INSERT INTO brc_legacy_diagnostics (
            legacy_diagnostic_id, source_name, diagnostic_type,
            strategy_group_id, symbol, side, diagnostic_payload,
            may_set_current_blocker, observed_at_ms, created_by_projection_run_id
        ) VALUES (
            :id, 'pilot_status.watcher_scope_alignment', 'scope_alignment',
            'MPG-001', 'OPUSDT', 'long', '{}', :may_set_current_blocker,
            1770000000000, 'projection-run-1'
        )
    """
    connection.execute(
        text(statement),
        {"id": "legacy-diagnostic-valid", "may_set_current_blocker": False},
    )

    _expect_integrity_error(
        connection,
        statement,
        {"id": "legacy-diagnostic-invalid", "may_set_current_blocker": True},
    )


def test_strategy_governance_decisions_cannot_directly_grant_authority(connection):
    statement = """
        INSERT INTO brc_strategy_governance_decisions (
            governance_decision_id, review_outcome_id, strategy_group_id,
            decision_type, decision_state, owner_action_required,
            current_authority_effect, decision_payload,
            created_under_versions_hash, created_at_ms
        ) VALUES (
            :id, NULL, 'SOR-001', 'go_live', 'proposed', true,
            :current_authority_effect, '{}', 'versions-hash-1', 1770000000000
        )
    """
    connection.execute(
        text(statement),
        {
            "id": "gov-decision-valid",
            "current_authority_effect": "policy_event_required",
        },
    )

    _expect_integrity_error(
        connection,
        statement,
        {
            "id": "gov-decision-invalid-direct",
            "current_authority_effect": "direct_live_submit_enabled",
        },
    )


def test_projection_current_state_is_db_backed_and_single_owner(connection):
    projection_run_statement = """
        INSERT INTO brc_projection_runs (
            projection_run_id, model_type, owner_projector, code_version,
            source_mode, projection_target, input_watermark, source_priority,
            legacy_diagnostics_read, legacy_diagnostics_affected_current,
            started_at_ms, finished_at_ms, status, error_detail
        ) VALUES (
            :id, 'goal_status', 'goal_status_projector', '086',
            :source_mode, 'production_current', '{}', '[]', false,
            :legacy_diagnostics_affected_current,
            1770000000000, 1770000001000, 'succeeded', NULL
        )
    """
    connection.execute(
        text(projection_run_statement),
        {
            "id": "projection-run-valid",
            "source_mode": "db_backed",
            "legacy_diagnostics_affected_current": False,
        },
    )
    _expect_integrity_error(
        connection,
        projection_run_statement,
        {
            "id": "projection-run-local-file",
            "source_mode": "local_file_inventory",
            "legacy_diagnostics_affected_current": False,
        },
    )
    _expect_integrity_error(
        connection,
        projection_run_statement,
        {
            "id": "projection-run-legacy-current",
            "source_mode": "db_backed",
            "legacy_diagnostics_affected_current": True,
        },
    )

    ownership_statement = """
        INSERT INTO brc_current_projection_ownership (
            projection_key, model_type, projection_scope_key, owner_projector,
            export_paths, legacy_writer_allowed, current_source_mode,
            sunset_condition, updated_at_ms
        ) VALUES (
            :projection_key, 'goal_status', :scope_key, 'goal_status_projector',
            '[]', :legacy_writer_allowed, :current_source_mode, NULL,
            1770000000000
        )
    """
    connection.execute(
        text(ownership_statement),
        {
            "projection_key": "current:goal_status",
            "scope_key": "global",
            "legacy_writer_allowed": False,
            "current_source_mode": "db_backed",
        },
    )

    _expect_integrity_error(
        connection,
        ownership_statement,
        {
            "projection_key": "current:goal_status:duplicate",
            "scope_key": "global",
            "legacy_writer_allowed": False,
            "current_source_mode": "db_backed",
        },
    )
    _expect_integrity_error(
        connection,
        ownership_statement,
        {
            "projection_key": "current:goal_status:legacy",
            "scope_key": "legacy_scope",
            "legacy_writer_allowed": True,
            "current_source_mode": "db_backed",
        },
    )
    _expect_integrity_error(
        connection,
        ownership_statement,
        {
            "projection_key": "current:goal_status:file",
            "scope_key": "file_scope",
            "legacy_writer_allowed": False,
            "current_source_mode": "local_file_inventory",
        },
    )
    _expect_integrity_error(
        connection,
        ownership_statement,
        {
            "projection_key": "current:goal_status:empty-scope",
            "scope_key": "",
            "legacy_writer_allowed": False,
            "current_source_mode": "db_backed",
        },
    )


def test_runtime_safety_submit_allowed_fails_closed(connection):
    statement = """
        INSERT INTO brc_runtime_safety_state_snapshots (
            runtime_safety_snapshot_id, action_time_lane_input_id, strategy_group_id,
            symbol, side, runtime_profile_id, safety_state, submit_allowed,
            finalgate_ready, operation_layer_ready, protection_ready,
            active_position_conflict, facts_fresh, trusted_fact_refs_complete,
            observed_at_ms, valid_until_ms, created_at_ms, authority_boundary
        ) VALUES (
            :id, 'lane-1', 'SOR-001', 'ETHUSDT', 'long', 'tiny-live-profile',
            :safety_state, :submit_allowed, :finalgate_ready,
            :operation_layer_ready, :protection_ready, :active_position_conflict,
            :facts_fresh, :trusted_fact_refs_complete, 1770000000000,
            1770000060000, 1770000000001, 'non_authority'
        )
    """
    _expect_integrity_error(
        connection,
        statement,
        {
            "id": "unsafe-submit",
            "safety_state": "not_ready",
            "submit_allowed": True,
            "finalgate_ready": True,
            "operation_layer_ready": True,
            "protection_ready": True,
            "active_position_conflict": False,
            "facts_fresh": True,
            "trusted_fact_refs_complete": True,
        },
    )
    connection.execute(
        text(statement),
        {
            "id": "safe-submit",
            "safety_state": "live_submit_ready",
            "submit_allowed": True,
            "finalgate_ready": True,
            "operation_layer_ready": True,
            "protection_ready": True,
            "active_position_conflict": False,
            "facts_fresh": True,
            "trusted_fact_refs_complete": True,
        },
    )
