from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from src.infrastructure.runtime_control_state_repository import (
    PgBackedRuntimeControlStateRepository,
    RuntimeControlStateRepositoryError,
    is_current_action_time_lane,
    is_current_action_time_ticket,
    is_current_fact_snapshot,
    is_current_live_signal,
    is_current_pretrade_readiness,
    is_current_promotion_candidate,
    runtime_safety_submit_authorized,
)
from src.domain.runtime_lane_identity import RuntimeLaneIdentity
from scripts import runtime_active_observation_monitor
from scripts import materialize_ticket_bound_protected_submit_attempt as submit
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_protected_submit_attempt import (
    _create_ready_protected_submit,
)
from tests.unit.lifecycle_test_schema import apply_enabled_lifecycle_command_schema
from tests.support.runtime_control_state_schema import (
    install_runtime_control_state_revision,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py"
)
RISK_RESERVATION_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-09-103_add_budget_risk_at_stop_reservation.py"
)
EXECUTION_ELIGIBILITY_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-10-104_add_execution_eligibility_authority.py"
)
DYNAMIC_RISK_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-12-115_add_dynamic_execution_risk_policy.py"
)
LANE_IDENTITY_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-13-118_conserve_runtime_lane_identity.py"
)
SEED_PATH = REPO_ROOT / "scripts/seed_runtime_control_state_foundation.py"
VALIDATOR_PATH = REPO_ROOT / "scripts/validate_runtime_control_state_repository.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def pg_control_connection():
    migration = _load_module(MIGRATION_PATH, "migration_086_repository")
    risk_reservation_migration = _load_module(
        RISK_RESERVATION_MIGRATION_PATH,
        "migration_103_repository",
    )
    execution_eligibility_migration = _load_module(
        EXECUTION_ELIGIBILITY_MIGRATION_PATH,
        "migration_104_repository",
    )
    seed = _load_module(SEED_PATH, "seed_runtime_control_state_repository")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        old_op = migration.op
        migration.op = Operations(MigrationContext.configure(conn))
        try:
            migration.upgrade()
            old_risk_op = risk_reservation_migration.op
            risk_reservation_migration.op = migration.op
            try:
                risk_reservation_migration.upgrade()
                old_eligibility_op = execution_eligibility_migration.op
                execution_eligibility_migration.op = migration.op
                try:
                    execution_eligibility_migration.upgrade()
                finally:
                    execution_eligibility_migration.op = old_eligibility_op
            finally:
                risk_reservation_migration.op = old_risk_op
        finally:
            migration.op = old_op
        seed.seed_runtime_control_state_foundation(conn)
        apply_enabled_lifecycle_command_schema(
            conn,
            repo_root=REPO_ROOT,
            module_prefix="runtime_control_repository",
            now_ms=NOW_MS - 1,
        )
        dynamic_risk_migration = _load_module(
            DYNAMIC_RISK_MIGRATION_PATH,
            "migration_115_repository",
        )
        old_dynamic_risk_op = dynamic_risk_migration.op
        dynamic_risk_migration.op = Operations(MigrationContext.configure(conn))
        try:
            dynamic_risk_migration.upgrade()
        finally:
            dynamic_risk_migration.op = old_dynamic_risk_op
        install_runtime_control_state_revision(conn, revision="121")
        install_runtime_control_state_revision(conn, revision="122")
        for revision in ("126", "127", "129", "130", "131", "132"):
            migration_path = next(
                REPO_ROOT.glob(f"migrations/versions/*-{revision}_*.py")
            )
            account_risk_migration = _load_module(
                migration_path,
                f"migration_{revision}_repository",
            )
            old_account_risk_op = account_risk_migration.op
            account_risk_migration.op = Operations(MigrationContext.configure(conn))
            try:
                account_risk_migration.upgrade()
            finally:
                account_risk_migration.op = old_account_risk_op
    with engine.connect() as conn:
        yield conn
    engine.dispose()


def test_pg_backed_runtime_control_state_repository_reads_seeded_state(
    pg_control_connection,
):
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770000120100,
    )

    state = repository.read_control_state()

    assert state["schema"] == "brc.runtime_control_state_repository.v1"
    assert state["source_mode"] == "db_backed"
    assert state["projection_target"] == "production_current"
    assert state["table_counts"]["strategy_groups"] == 5
    assert state["table_counts"]["strategy_side_event_specs"] == 6
    assert state["table_counts"]["candidate_scope"] == 22
    assert state["table_counts"]["runtime_scope_bindings"] == 22
    assert state["table_counts"]["current_projection_ownership"] == 6

    scope = {
        (row["strategy_group_id"], row["symbol"], row["side"])
        for row in state["candidate_scope"]
    }
    assert ("CPM-RO-001", "ETHUSDT", "short") not in scope
    assert ("MI-001", "AVAXUSDT", "short") not in scope
    assert ("BRF2-001", "BTCUSDT", "long") not in scope
    assert ("SOR-001", "ETHUSDT", "long") in scope
    assert ("SOR-001", "ETHUSDT", "short") in scope

    brf2_binding = next(
        row
        for row in state["runtime_scope_bindings"]
        if row["strategy_group_id"] == "BRF2-001"
        and row["symbol"] == "BTCUSDT"
        and row["side"] == "short"
    )
    assert brf2_binding["conditional_hard_gates"] == [
        "short_side_disable_clear",
        "squeeze_clear",
        "liquidity_clear",
    ]


def test_watcher_candidate_universe_uses_four_explicit_bounded_queries(
    pg_control_connection,
):
    statements: list[str] = []

    def capture_sql(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(" ".join(statement.split()))

    sa.event.listen(
        pg_control_connection.engine,
        "before_cursor_execute",
        capture_sql,
    )
    try:
        projection = PgBackedRuntimeControlStateRepository(
            pg_control_connection,
            now_ms=1770000120100,
        ).read_watcher_candidate_universe_current()
    finally:
        sa.event.remove(
            pg_control_connection.engine,
            "before_cursor_execute",
            capture_sql,
        )

    assert projection.schema == "brc.watcher_candidate_universe_current.v1"
    assert len(projection.candidate_scope) == 22
    assert len(projection.candidate_scope_event_bindings) == 22
    assert len(projection.runtime_scope_bindings) == 22
    assert len(projection.strategy_side_event_specs) == 6
    assert all(row.exchange_instrument_id for row in projection.candidate_scope)

    row_queries = [
        statement
        for statement in statements
        if statement.startswith("SELECT ") and " FROM brc_" in statement
    ]
    assert len(row_queries) == 4
    assert {
        table
        for table in (
            "brc_strategy_group_candidate_scope",
            "brc_candidate_scope_event_bindings",
            "brc_runtime_scope_bindings",
            "brc_strategy_side_event_specs",
        )
        if any(f" FROM {table}" in statement for statement in row_queries)
    } == {
        "brc_strategy_group_candidate_scope",
        "brc_candidate_scope_event_bindings",
        "brc_runtime_scope_bindings",
        "brc_strategy_side_event_specs",
    }
    assert all(" WHERE " in statement for statement in row_queries)
    assert all(" LIMIT " in statement for statement in row_queries)
    assert all(".*" not in statement for statement in row_queries)


def test_watcher_candidate_universe_fails_closed_on_row_257(
    pg_control_connection,
):
    repository = PgBackedRuntimeControlStateRepository(pg_control_connection)

    with pytest.raises(
        RuntimeControlStateRepositoryError,
        match="watcher_candidate_row_limit_exceeded:candidate_scope:21",
    ):
        repository.read_watcher_candidate_universe_current(row_limit_per_table=21)


def test_deploy_validation_state_uses_five_explicit_bounded_queries(
    pg_control_connection,
):
    statements: list[str] = []

    def capture_sql(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(" ".join(statement.split()))

    sa.event.listen(
        pg_control_connection.engine,
        "before_cursor_execute",
        capture_sql,
    )
    try:
        state = PgBackedRuntimeControlStateRepository(
            pg_control_connection,
            now_ms=1770000120100,
        ).read_deploy_validation_state()
    finally:
        sa.event.remove(
            pg_control_connection.engine,
            "before_cursor_execute",
            capture_sql,
        )

    assert state["read_profile"] == "deploy_validation"
    assert state["strategy_group_count"] == 5
    assert state["table_counts"] == {
        "candidate_scope": 22,
        "candidate_scope_event_bindings": 22,
        "runtime_scope_bindings": 22,
        "strategy_side_event_specs": 6,
        "current_projection_ownership": 6,
    }
    row_queries = [
        statement
        for statement in statements
        if statement.startswith("SELECT ") and " FROM brc_" in statement
    ]
    assert len(row_queries) == 5
    assert all(" WHERE " in statement for statement in row_queries)
    assert all(" LIMIT " in statement for statement in row_queries)
    assert all(".*" not in statement for statement in row_queries)


def test_current_chain_helpers_reject_future_dated_rows() -> None:
    now_ms = 1770001000000

    assert is_current_live_signal(
        {
            "status": "facts_validated",
            "freshness_state": "fresh",
            "source_kind": "live_market",
            "invalidated_at_ms": None,
            "event_time_ms": now_ms + 1,
            "observed_at_ms": now_ms + 1,
            "expires_at_ms": now_ms + 60_000,
        },
        now_ms,
    ) is False
    assert is_current_fact_snapshot(
        {
            "freshness_state": "fresh",
            "observed_at_ms": now_ms + 1,
            "valid_until_ms": now_ms + 60_000,
        },
        now_ms,
    ) is False
    assert is_current_promotion_candidate(
        {
            "status": "eligible",
            "closed_at_ms": None,
            "created_at_ms": now_ms + 1,
            "expires_at_ms": now_ms + 60_000,
        },
        now_ms,
    ) is False
    assert is_current_action_time_lane(
        {
            "lane_scope": "real_submit_candidate",
            "status": "opened",
            "closed_at_ms": None,
            "created_at_ms": now_ms + 1,
            "expires_at_ms": now_ms + 60_000,
        },
        now_ms,
    ) is False
    assert is_current_action_time_ticket(
        {
            "status": "created",
            "created_at_ms": now_ms + 1,
            "expires_at_ms": now_ms + 60_000,
        },
        now_ms,
    ) is False


def test_runtime_safety_submit_authority_requires_concrete_trusted_refs() -> None:
    row = {
        "submit_allowed": True,
        "safety_state": "live_submit_ready",
        "finalgate_ready": True,
        "operation_layer_ready": True,
        "protection_ready": True,
        "active_position_conflict": False,
        "facts_fresh": True,
        "trusted_fact_refs_complete": True,
        "blockers": [],
        "trusted_fact_refs": {},
        "execution_eligible": True,
        "signal_grade": "trial_grade_signal",
        "required_execution_mode": "trial_live",
        "authority_source_ref": "event_spec:SOR-LONG:v2",
    }

    assert runtime_safety_submit_authorized(row) is False


def test_runtime_safety_submit_authority_requires_v2_capacity_fact_pair() -> None:
    refs = {
        "ticket_id": "ticket-1",
        "ticket_hash": "hash-1",
        "ticket_hash_schema_version": "action_time_ticket_hash.v2",
        "finalgate_pass_id": "pass-1",
        "operation_layer_handoff_id": "handoff-1",
        "operation_submit_command_id": "command-1",
        "signal_event_id": "signal-1",
        "budget_reservation_id": "budget-1",
        "protection_ref_id": "protection-1",
        "public_fact_snapshot_id": "public-1",
        "action_time_fact_snapshot_id": "action-1",
        "account_capacity_fact_surface": "account_capacity_base",
        "account_capacity_fact_snapshot_id": "capacity-1",
        "account_mode_snapshot_id": "mode-1",
    }
    row = {
        "submit_allowed": True,
        "safety_state": "live_submit_ready",
        "finalgate_ready": True,
        "operation_layer_ready": True,
        "protection_ready": True,
        "active_position_conflict": False,
        "facts_fresh": True,
        "trusted_fact_refs_complete": True,
        "blockers": [],
        "trusted_fact_refs": refs,
        "execution_eligible": True,
        "signal_grade": "trial_grade_signal",
        "required_execution_mode": "trial_live",
        "authority_source_ref": "event_spec:SOR-LONG:v2",
    }

    assert runtime_safety_submit_authorized(row) is False
    assert runtime_safety_submit_authorized(
        {**row, "trusted_fact_refs_schema_version": "runtime_safety_trusted_refs.v2"}
    ) is True


def test_exact_ticket_bundle_reads_canonical_capacity_base_fact_snapshot() -> None:
    class RecordingRepository(PgBackedRuntimeControlStateRepository):
        def __init__(self):
            self.fact_ids = []

        def _read_exact_rows(self, table_name, id_column, id_value):
            if table_name == "brc_action_time_tickets":
                return [
                    {
                        "ticket_id": "ticket-1",
                        "account_capacity_base_fact_snapshot_id": "capacity-base-1",
                        "account_capacity_fact_snapshot_id": "obsolete-capacity-1",
                    }
                ]
            if table_name == "brc_runtime_fact_snapshots":
                self.fact_ids.append(id_value)
            return []

        def _action_time_bundle_payload(self, rows, *, ticket_id):
            return rows

    repository = RecordingRepository()

    repository._read_action_time_exact_ticket_bundle(ticket_id="ticket-1")

    assert "capacity-base-1" in repository.fact_ids
    assert "obsolete-capacity-1" not in repository.fact_ids


def test_current_readiness_allows_null_validity_until_projector_replaces_row() -> None:
    now_ms = 1770001000000

    assert is_current_pretrade_readiness(
        {
            "computed_at_ms": now_ms - 1,
            "valid_until_ms": None,
        },
        now_ms,
    ) is True


def test_monitor_read_profile_keeps_current_readiness_with_null_validity(
    pg_control_connection,
) -> None:
    now_ms = 1770001000000
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_pretrade_readiness_rows (
              readiness_row_id, candidate_scope_id, strategy_group_id, symbol,
              side, readiness_state, detector_state, watcher_state,
              public_facts_state, signal_lifecycle_status,
              signal_freshness_state, risk_state, scope_state, promotion_state,
              first_blocker_class, first_blocker_detail, next_action,
              stop_condition, evidence_ref, source_watermark, computed_at_ms,
              valid_until_ms
            ) VALUES (
              'readiness:MPG-001:OPUSDT:long:null-validity',
              'candidate_scope:MPG-001:OPUSDT:long:MPG-LONG',
              'MPG-001', 'OPUSDT', 'long', 'market_wait', 'ready', 'fresh',
              'satisfied', 'absent', 'absent', 'acceptable',
              'live_submit_allowed', 'idle', 'market_wait_validated',
              'current until projector replacement',
              'continue_watcher_observation_until_fresh_signal',
              'fresh signal or projector replacement', NULL, 'unit',
              :computed_at_ms, NULL
            )
            """
        ),
        {"computed_at_ms": now_ms - 1},
    )
    pg_control_connection.commit()

    monitor_state = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=now_ms,
    ).read_monitor_control_state()

    assert monitor_state["table_counts"]["pretrade_readiness_rows"] == 1

def test_repository_rejects_typed_live_signal_with_altered_identity_key(
    pg_control_connection,
):
    identity = RuntimeLaneIdentity(
        candidate_scope_id="candidate_scope:SOR-001:ETHUSDT:long:SOR-LONG",
        candidate_scope_event_binding_id="binding:SOR-001:ETHUSDT:long",
        runtime_scope_binding_id="runtime_scope:SOR-001:ETHUSDT:long",
        runtime_instance_id="runtime:SOR-001:ETHUSDT:long",
        runtime_profile_id="owner-runtime-console-v1",
        policy_current_id="policy:SOR-001",
        strategy_group_id="SOR-001",
        strategy_group_version_id="sgv:SOR-001:v2",
        symbol="ETHUSDT",
        exchange_instrument_id="instrument:binance-usdm:ETHUSDT",
        asset_class="crypto_perpetual",
        side="long",
        event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
        event_spec_version="v2",
        event_id="SOR-LONG",
        timeframe="15m",
        time_authority="trigger_candle_close_time_ms",
    )
    signal = {
        **identity.model_dump(mode="json"),
        "signal_event_id": "signal:typed-identity-mismatch",
        "lane_identity_key": "tampered-lane-identity-key",
        "source_watermark": "runtime:SOR-001:ETHUSDT:long:1770000000000",
        "signal_type": identity.event_id,
        "status": "facts_validated",
        "freshness_state": "fresh",
        "source_kind": "live_market",
        "invalidated_at_ms": None,
        "event_time_ms": NOW_MS - 60_000,
        "trigger_candle_close_time_ms": NOW_MS - 60_000,
        "observed_at_ms": NOW_MS - 55_000,
        "created_at_ms": NOW_MS - 54_000,
        "expires_at_ms": NOW_MS + 600_000,
    }
    rows = {
        "candidate_scope": [
            {
                "candidate_scope_id": identity.candidate_scope_id,
                "strategy_group_id": identity.strategy_group_id,
                "symbol": identity.symbol,
                "side": identity.side,
                "status": "active",
            }
        ],
        "candidate_scope_event_bindings": [
            {
                "candidate_scope_id": identity.candidate_scope_id,
                "event_spec_id": identity.event_spec_id,
                "status": "active",
            }
        ],
        "strategy_side_event_specs": [
            {
                "event_spec_id": identity.event_spec_id,
                "event_id": identity.event_id,
                "status": "current",
            }
        ],
        "live_signal_events": [signal],
    }
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    with pytest.raises(
        RuntimeControlStateRepositoryError,
        match="runtime_lane_identity_mismatch:live_signal_identity_key",
    ):
        repository._validate_live_signal_events(rows)


def test_live_signal_writer_output_is_readable_by_repository(pg_control_connection):
    lane_identity_migration = _load_module(
        LANE_IDENTITY_MIGRATION_PATH,
        "migration_118_repository_writer_consumer",
    )
    old_lane_identity_op = lane_identity_migration.op
    lane_identity_migration.op = Operations(
        MigrationContext.configure(pg_control_connection)
    )
    try:
        lane_identity_migration.upgrade()
    finally:
        lane_identity_migration.op = old_lane_identity_op

    lane_row = pg_control_connection.execute(
        text(
            """
            SELECT c.candidate_scope_id,
                   c.policy_current_id,
                   c.strategy_group_id,
                   c.symbol,
                   c.exchange_instrument_id,
                   c.asset_class,
                   c.side,
                   b.binding_id,
                   r.runtime_scope_binding_id,
                   r.runtime_profile_id,
                   e.strategy_group_version_id,
                   e.event_spec_id,
                   e.event_spec_version,
                   e.event_id,
                   e.timeframe,
                   e.time_authority
            FROM brc_strategy_group_candidate_scope c
            JOIN brc_candidate_scope_event_bindings b
              ON b.candidate_scope_id = c.candidate_scope_id
             AND b.status = 'active'
            JOIN brc_runtime_scope_bindings r
              ON r.candidate_scope_id = c.candidate_scope_id
             AND r.status = 'active'
            JOIN brc_strategy_side_event_specs e
              ON e.event_spec_id = b.event_spec_id
             AND e.status = 'current'
            WHERE c.strategy_group_id = 'MPG-001'
              AND c.symbol = 'OPUSDT'
              AND c.side = 'long'
              AND c.status = 'active'
            """
        )
    ).mappings().one()
    runtime_instance_id = "runtime:MPG-001:OPUSDT:long"
    lane_identity = RuntimeLaneIdentity(
        candidate_scope_id=str(lane_row["candidate_scope_id"]),
        candidate_scope_event_binding_id=str(lane_row["binding_id"]),
        runtime_scope_binding_id=str(lane_row["runtime_scope_binding_id"]),
        runtime_instance_id=runtime_instance_id,
        runtime_profile_id=str(lane_row["runtime_profile_id"]),
        policy_current_id=str(lane_row["policy_current_id"]),
        strategy_group_id=str(lane_row["strategy_group_id"]),
        strategy_group_version_id=str(lane_row["strategy_group_version_id"]),
        symbol=str(lane_row["symbol"]),
        exchange_instrument_id=str(lane_row["exchange_instrument_id"]),
        asset_class=str(lane_row["asset_class"]),
        side=str(lane_row["side"]),
        event_spec_id=str(lane_row["event_spec_id"]),
        event_spec_version=str(lane_row["event_spec_version"]),
        event_id=str(lane_row["event_id"]),
        timeframe=str(lane_row["timeframe"]),
        time_authority=str(lane_row["time_authority"]),
    )
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_runtime_fact_snapshots (
              fact_snapshot_id, strategy_group_id, symbol, side, runtime_profile_id,
              fact_surface, source_kind, source_ref, computed, satisfied,
              freshness_state, failed_facts, fact_values, blocker_class,
              observed_at_ms, valid_until_ms, created_at_ms
            ) VALUES (
              'fact:MPG-001:OPUSDT:long:public:writer-consumer',
              'MPG-001', 'OPUSDT', 'long', 'owner-runtime-console-v1',
              'pretrade_public', 'live_market', 'unit-test', 1, 1,
              'fresh', '[]', '{}', NULL,
              1770000120000, 1770003720000, 1770000120001
            )
            """
        )
    )
    pg_control_connection.commit()

    result = runtime_active_observation_monitor.write_runtime_signal_summaries_to_pg(
        {
            "runtime_summaries": [
                {
                    "runtime_instance_id": runtime_instance_id,
                    "strategy_family_id": "MPG-001",
                    "strategy_family_version_id": "MPG-001-v0",
                    "symbol": "OPUSDT",
                    "side": "long",
                    "status": "ready_for_prepare",
                    "lane_identity": lane_identity.model_dump(mode="json"),
                    "can_materialize_live_signal_event": True,
                    "signal_summary": {
                        "signal_type": "would_enter",
                        "side": "long",
                        "timestamp_ms": 1770000120000,
                        "trigger_candle_close_time_ms": 1770000120000,
                        "evaluated_at_ms": 1770000120000,
                        "valid_until_ms": 1770003720000,
                        "confidence": "0.82",
                        "signal_grade": "trial_grade_signal",
                        "required_execution_mode": "trial_live",
                        "reason_codes": ["writer_consumer_contract"],
                    },
                }
            ]
        },
        database_url="unused://repository-test",
        allow_non_postgres_for_test=True,
        now_ms=1770000120100,
        conn=pg_control_connection,
    )

    assert result["status"] == "pg_live_signal_events_written"
    state = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770000120100,
    ).read_control_state()
    signal = next(row for row in state["live_signal_events"])
    payload = signal["signal_payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    assert signal["strategy_group_id"] == "MPG-001"
    assert signal["symbol"] == "OPUSDT"
    assert signal["side"] == "long"
    assert signal["signal_type"] == "MPG-LONG"
    assert signal["lane_identity_key"] == lane_identity.identity_key
    assert signal["source_watermark"] == f"{runtime_instance_id}:1770000120000"
    assert payload["detector_verdict"] == "would_enter"


def test_repository_monitor_read_profile_bounds_high_growth_tables(pg_control_connection):
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_watcher_runtime_coverage (
              runtime_coverage_id, strategy_group_id, symbol, side, detector_key,
              runtime_profile_id, coverage_state, liveness_state,
              last_tick_at_ms, valid_until_ms, is_current, created_at_ms
            ) VALUES (
              'coverage:historical:MPG-001:OPUSDT:long', 'MPG-001', 'OPUSDT',
              'long', 'detector:MPG-001:long', 'owner-runtime-console-v1',
              'covered', 'healthy', 1770000000000, 1770003600000, 0,
              1770000000000
            )
            """
        )
    )
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_live_signal_events (
              signal_event_id, candidate_scope_id, event_spec_id, strategy_group_id,
              symbol, side, detector_key, signal_type, source_kind, status,
              freshness_state, confidence, fact_snapshot_id, reason_codes,
              signal_payload, event_time_ms, trigger_candle_close_time_ms,
              observed_at_ms, expires_at_ms, invalidated_at_ms, created_at_ms
            ) VALUES (
              'signal:SOR-001:ETHUSDT:long:expired-monitor-bound',
              'candidate_scope:SOR-001:ETHUSDT:long:SOR-LONG',
              'event_spec:SOR-001:SOR-LONG:v1', 'SOR-001', 'ETHUSDT',
              'long', 'detector:SOR-001:long', 'SOR-LONG', 'live_market',
              'facts_validated', 'fresh', 0.9, 'fact:SOR:expired-monitor',
              '[]', '{}', 1770000120000, 1770000120000, 1770000120001,
              1770000120002, NULL, 1770000120003
            )
            """
        )
    )
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_pretrade_readiness_rows (
              readiness_row_id, candidate_scope_id, strategy_group_id, symbol, side,
              readiness_state, detector_state, watcher_state, public_facts_state,
              signal_lifecycle_status, signal_freshness_state, risk_state,
              scope_state, promotion_state, first_blocker_class,
              first_blocker_detail, next_action,
              stop_condition, evidence_ref, source_watermark, computed_at_ms,
              valid_until_ms
            ) VALUES (
              'readiness:SOR-001:ETHUSDT:long:expired-monitor-bound',
              'candidate_scope:SOR-001:ETHUSDT:long:SOR-LONG',
              'SOR-001', 'ETHUSDT', 'long', 'ready', 'attached', 'healthy',
              'satisfied', 'facts_validated', 'fresh', 'acceptable',
              'live_submit_allowed', 'action_time_lane',
              'action_time_preflight_ready', 'expired_monitor_bound',
              'materialize_ticket',
              'ticket_created_or_lane_expires', 'fact:SOR:expired-monitor',
              'unit', 1770000120003, 1770000120004
            )
            """
        )
    )
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_promotion_candidates (
              promotion_candidate_id, signal_event_id, readiness_row_id,
              strategy_group_id, symbol, side, promotion_scope, status,
              scope_state, risk_state, facts_snapshot_id, blockers,
              arbitration_rank, created_at_ms, expires_at_ms, closed_at_ms,
              authority_boundary
            ) VALUES (
              'promotion:SOR-001:ETHUSDT:long:expired-monitor-bound',
              'signal:SOR-001:ETHUSDT:long:expired-monitor-bound',
              'readiness:SOR-001:ETHUSDT:long:expired-monitor-bound',
              'SOR-001', 'ETHUSDT', 'long', 'live_submit_candidate',
              'arbitration_won', 'live_submit_allowed', 'acceptable',
              'fact:SOR:expired-monitor', '[]', 1, 1770000120004,
              1770000120005, NULL,
              'expired_pg_current_object_test; no_finalgate_no_operation_layer_no_exchange_write'
            )
            """
        )
    )
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_action_time_lane_inputs (
              action_time_lane_input_id, promotion_candidate_id, strategy_group_id,
              symbol, side, runtime_profile_id, lane_scope, status,
              signal_event_id, public_fact_snapshot_id, action_time_fact_snapshot_id,
              runtime_scope_binding_id, candidate_authorization_ref,
              runtime_safety_snapshot_id, first_blocker_class, created_at_ms,
              expires_at_ms, closed_at_ms, authority_boundary
            ) VALUES (
              'lane:SOR-001:ETHUSDT:long:expired-monitor-bound',
              'promotion:SOR-001:ETHUSDT:long:expired-monitor-bound',
              'SOR-001', 'ETHUSDT', 'long', 'owner-runtime-console-v1',
              'real_submit_candidate', 'ticket_created',
              'signal:SOR-001:ETHUSDT:long:expired-monitor-bound',
              'fact:SOR:expired-monitor', 'fact:SOR:expired-action-monitor',
              'runtime_scope:candidate_scope:SOR-001:ETHUSDT:long:SOR-LONG:owner-runtime-console-v1',
              'ticket:SOR-001:ETHUSDT:long:expired-monitor-bound',
              NULL, 'action_time_preflight_ready', 1770000120006,
              1770000120007, NULL,
              'expired_pg_current_object_test; no_finalgate_no_operation_layer_no_exchange_write'
            )
            """
        )
    )
    pg_control_connection.execute(
        text(
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
              'ticket:SOR-001:ETHUSDT:long:expired-monitor-bound',
              'lane:SOR-001:ETHUSDT:long:expired-monitor-bound',
              'promotion:SOR-001:ETHUSDT:long:expired-monitor-bound',
              'signal:SOR-001:ETHUSDT:long:expired-monitor-bound',
              'event_spec:SOR-001:SOR-LONG:v1',
              'event_spec_version:SOR-001:SOR-LONG:v1',
              'candidate_scope:SOR-001:ETHUSDT:long:SOR-LONG',
              'runtime_scope:candidate_scope:SOR-001:ETHUSDT:long:SOR-LONG:owner-runtime-console-v1',
              'SOR-001', 'strategy_group_version:SOR-001:v1', 'ETHUSDT',
              'binance_usdm:ETHUSDT', 'long', 'SOR-LONG',
              1770000120000, 1770000120000, 'owner-runtime-console-v1',
              'fact:SOR:expired-monitor', 'fact:SOR:expired-action-monitor',
              'fact:SOR:expired-account-safe-monitor',
              'fact:SOR:expired-account-mode-monitor',
              'budget:SOR:expired-monitor', 'protection:SOR:expired-monitor',
              'execution_policy:owner-runtime-console-v1',
              'execution-policy-v1', 'owner-policy-v1', 'sizing-policy-v1',
              'protection-policy-v1', 100, 1, 1770000120008, 'created',
              'expired_pg_current_object_test; no_finalgate_no_operation_layer_no_exchange_write',
              'ticket-hash:expired-monitor-bound',
              'versions-hash:expired-monitor-bound', 1770000120009
            )
            """
        )
    )
    pg_control_connection.commit()

    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770001000000,
    )
    full_state = repository.read_control_state()
    monitor_state = repository.read_monitor_control_state()

    assert full_state["table_counts"]["watcher_runtime_coverage"] == 1
    assert full_state["table_counts"]["live_signal_events"] == 1
    assert full_state["table_counts"]["pretrade_readiness_rows"] == 1
    assert full_state["table_counts"]["promotion_candidates"] == 1
    assert full_state["table_counts"]["action_time_lane_inputs"] == 1
    assert full_state["table_counts"]["action_time_tickets"] == 1
    assert monitor_state["read_profile"] == "monitor_bounded_current"
    assert monitor_state["table_counts"]["watcher_runtime_coverage"] == 0
    assert monitor_state["table_counts"]["live_signal_events"] == 0
    assert monitor_state["table_counts"]["promotion_candidates"] == 0
    assert monitor_state["table_counts"]["action_time_lane_inputs"] == 0
    assert monitor_state["table_counts"]["action_time_tickets"] == 0


def test_repository_action_time_read_profile_reuses_bounded_current_truth(
    pg_control_connection,
):
    now_ms = 1770001000000
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_watcher_runtime_coverage (
              runtime_coverage_id, strategy_group_id, symbol, side, detector_key,
              runtime_profile_id, coverage_state, liveness_state,
              last_tick_at_ms, valid_until_ms, is_current, created_at_ms
            ) VALUES (
              'coverage:historical:action-time-hot-path', 'MPG-001', 'OPUSDT',
              'long', 'detector:MPG-001:long', 'owner-runtime-console-v1',
              'covered', 'healthy', 1770000000000, 1770003600000, 0,
              1770000000000
            )
            """
        )
    )
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_runtime_fact_snapshots (
              fact_snapshot_id, strategy_group_id, symbol, side,
              runtime_profile_id, fact_surface, source_kind, source_ref,
              computed, satisfied, freshness_state, failed_facts, fact_values,
              blocker_class, observed_at_ms, valid_until_ms, created_at_ms
            ) VALUES (
              'fact:historical:action-time-hot-path', 'MPG-001', 'OPUSDT',
              'long', 'owner-runtime-console-v1', 'pretrade_public',
              'live_market', 'unit', 1, 1, 'fresh', '[]', '{}', NULL,
              1770000000000, 1770000000001, 1770000000000
            )
            """
        )
    )
    pg_control_connection.commit()

    state = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=now_ms,
    ).read_action_time_control_state()

    assert state["read_profile"] == "action_time_hot_path_current"
    assert state["table_counts"]["watcher_runtime_coverage"] == 0
    assert state["table_counts"]["runtime_fact_snapshots"] == 0


def test_repository_action_time_read_exposes_account_risk_current_projections(
    pg_control_connection,
):
    state = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=NOW_MS,
    ).read_action_time_control_state()

    assert state["table_counts"]["account_risk_policy_current"] == 0
    assert state["table_counts"]["account_exposure_current"] == 0
    assert state["table_counts"]["account_budget_current"] == 0


def test_repository_exact_ticket_bundle_avoids_unrelated_control_state_scans(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    pg_control_connection.commit()
    statements: list[str] = []

    def capture_sql(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(" ".join(statement.split()))

    sa.event.listen(
        pg_control_connection.engine,
        "before_cursor_execute",
        capture_sql,
    )
    try:
        state = PgBackedRuntimeControlStateRepository(
            pg_control_connection,
            now_ms=NOW_MS + 5000,
        ).read_action_time_control_state(ticket_id=ids["ticket_id"])
    finally:
        sa.event.remove(
            pg_control_connection.engine,
            "before_cursor_execute",
            capture_sql,
        )

    row_queries = [
        statement
        for statement in statements
        if statement.startswith("SELECT ") and " FROM brc_" in statement
    ]
    assert state["read_profile"] == "action_time_exact_ticket_bundle"
    assert state["action_time_ticket_bundle_id"] == ids["ticket_id"]
    assert len(row_queries) <= 20
    assert not any("brc_server_monitor_runs" in statement for statement in row_queries)
    assert not any(
        "brc_control_read_model_snapshots" in statement
        for statement in row_queries
    )


def test_repository_monitor_read_profile_retains_protected_submit_lineage(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="disabled_smoke",
        now_ms=NOW_MS + 4000,
    )
    pg_control_connection.commit()

    monitor_state = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=NOW_MS + 120_000,
    ).read_monitor_control_state()

    assert monitor_state["read_profile"] == "monitor_bounded_current"
    assert monitor_state["table_counts"]["ticket_bound_protected_submit_attempts"] == 1
    assert monitor_state["table_counts"]["runtime_safety_state"] == 1
    assert monitor_state["table_counts"]["operation_layer_handoffs"] == 1
    assert monitor_state["table_counts"]["action_time_tickets"] == 1
    assert monitor_state["table_counts"]["action_time_lane_inputs"] == 1
    assert monitor_state["table_counts"]["promotion_candidates"] == 1
    assert monitor_state["table_counts"]["live_signal_events"] == 1
    assert monitor_state["ticket_bound_protected_submit_attempts"][0][
        "protected_submit_attempt_id"
    ] == prepared["protected_submit_attempt_id"]
    assert monitor_state["action_time_tickets"][0]["ticket_id"] == ids["ticket_id"]


def test_monitor_material_notification_lineage_retains_terminal_signal_and_ticket(
    pg_control_connection,
    monkeypatch,
):
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=NOW_MS + 120_000,
    )
    rows = {
        "server_monitor_notifications": [
            {"correlation_id": "signal:signal-terminal"},
            {"correlation_id": "ticket:ticket-closed"},
        ],
        "ticket_bound_order_lifecycle_runs": [
            {"ticket_id": "ticket-closed", "status": "lifecycle_closed"}
        ],
        "ticket_bound_exchange_commands": [],
        "action_time_tickets": [],
        "live_signal_events": [],
    }

    def fake_read(_table_name, column_name, values):
        if column_name == "ticket_id" and "ticket-closed" in values:
            return [
                {
                    "ticket_id": "ticket-closed",
                    "signal_event_id": "signal-from-ticket",
                }
            ]
        if column_name == "signal_event_id":
            return [
                {"signal_event_id": signal_id, "status": "stale"}
                for signal_id in sorted(values)
            ]
        return []

    monkeypatch.setattr(repository, "_read_rows_where_in", fake_read)
    repository._retain_monitor_material_notification_lineage(rows)

    assert rows["action_time_tickets"] == [
        {"ticket_id": "ticket-closed", "signal_event_id": "signal-from-ticket"}
    ]
    assert {row["signal_event_id"] for row in rows["live_signal_events"]} == {
        "signal-terminal",
        "signal-from-ticket",
    }


def test_pg_backed_runtime_control_state_repository_rejects_non_db_modes(
    pg_control_connection,
):
    with pytest.raises(RuntimeControlStateRepositoryError, match="source_mode='db_backed'"):
        PgBackedRuntimeControlStateRepository(
            pg_control_connection,
            source_mode="local_file_inventory",
        )

    with pytest.raises(RuntimeControlStateRepositoryError, match="production_current"):
        PgBackedRuntimeControlStateRepository(
            pg_control_connection,
            projection_target="diagnostic",
        )


def test_pg_backed_runtime_control_state_repository_fails_closed_without_tables():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        with engine.connect() as conn:
            repository = PgBackedRuntimeControlStateRepository(conn)
            with pytest.raises(
                RuntimeControlStateRepositoryError,
                match="tables missing",
            ):
                repository.read_control_state()
    finally:
        engine.dispose()


def test_pg_backed_runtime_control_state_repository_requires_projection_ownership(
    pg_control_connection,
):
    pg_control_connection.execute(text("DELETE FROM brc_current_projection_ownership"))
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770000120100,
    )

    with pytest.raises(
        RuntimeControlStateRepositoryError,
        match="current projection ownership is empty",
    ):
        repository.read_control_state()


def test_pg_backed_runtime_control_state_repository_requires_event_binding(
    pg_control_connection,
):
    pg_control_connection.execute(
        text(
            """
            DELETE FROM brc_candidate_scope_event_bindings
            WHERE candidate_scope_id = 'candidate_scope:CPM-RO-001:ETHUSDT:long:CPM-LONG'
            """
        )
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770000120100,
    )

    with pytest.raises(RuntimeControlStateRepositoryError, match="has no active event binding"):
        repository.read_control_state()


@pytest.mark.parametrize(
    ("candidate_scope_id", "side"),
    [
        ("candidate_scope:CPM-RO-001:ETHUSDT:long:CPM-LONG", "short"),
        ("candidate_scope:MPG-001:OPUSDT:long:MPG-LONG", "short"),
        ("candidate_scope:MI-001:AVAXUSDT:long:MI-LONG", "short"),
        ("candidate_scope:BRF2-001:BTCUSDT:short:BRF2-SHORT", "long"),
    ],
)
def test_pg_backed_runtime_control_state_repository_rejects_unsupported_active_side(
    pg_control_connection,
    candidate_scope_id: str,
    side: str,
):
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_strategy_group_candidate_scope
            SET side = :side
            WHERE candidate_scope_id = :candidate_scope_id
            """
        ),
        {"candidate_scope_id": candidate_scope_id, "side": side},
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770000120100,
    )

    with pytest.raises(RuntimeControlStateRepositoryError, match="mismatches candidate side"):
        repository.read_control_state()


def test_pg_backed_runtime_control_state_repository_rejects_generic_current_event_spec(
    pg_control_connection,
):
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_strategy_side_event_specs (
                event_spec_id, strategy_group_id, strategy_group_version_id,
                event_id, side, timeframe, event_spec_version, status,
                freshness_window_ms, time_authority, protection_ref_type,
                created_at_ms, created_by
            ) VALUES (
                'event_spec:SOR-001:SOR-GENERIC:v2', 'SOR-001',
                'sgv:SOR-001:v2', 'SOR-GENERIC', 'long', '15m', 'v2',
                'current', 900000, 'trigger_candle_close_time_ms',
                'opening_range_low_reference', 1770000000000, 'unit_test'
            )
            """
        )
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770000120100,
    )

    with pytest.raises(RuntimeControlStateRepositoryError, match="event_id is not side-specific"):
        repository.read_control_state()


def test_pg_backed_runtime_control_state_repository_rejects_event_without_current_version(
    pg_control_connection,
):
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_strategy_side_event_specs (
                event_spec_id, strategy_group_id, strategy_group_version_id,
                event_id, side, timeframe, event_spec_version, status,
                freshness_window_ms, time_authority, protection_ref_type,
                created_at_ms, created_by
            ) VALUES (
                'event_spec:SUPPORT-001:SUPPORT-LONG:v1', 'SUPPORT-001',
                'sgv:SUPPORT-001:v1', 'SUPPORT-LONG', 'long', '1h', 'v1',
                'current', 3600000, 'trigger_candle_close_time_ms',
                'support_reference', 1770000000000, 'unit_test'
            )
            """
        )
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770000120100,
    )

    with pytest.raises(
        RuntimeControlStateRepositoryError,
        match="has no current StrategyGroup version",
    ):
        repository.read_control_state()


def test_pg_backed_runtime_control_state_repository_requires_hard_required_facts(
    pg_control_connection,
):
    pg_control_connection.execute(
        text(
            """
            DELETE FROM brc_strategy_event_required_facts
            WHERE event_spec_id = 'event_spec:MI-001:MI-LONG:v2'
            """
        )
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770000120100,
    )

    with pytest.raises(RuntimeControlStateRepositoryError, match="MI-LONG.*no required facts"):
        repository.read_control_state()


def test_pg_backed_runtime_control_state_repository_requires_exact_required_fact_manifest(
    pg_control_connection,
):
    pg_control_connection.execute(
        text(
            """
            DELETE FROM brc_strategy_event_required_facts
            WHERE event_spec_id = 'event_spec:CPM-RO-001:CPM-LONG:v2'
              AND fact_key = 'htf_trend_intact'
            """
        )
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770000120100,
    )

    with pytest.raises(
        RuntimeControlStateRepositoryError,
        match="CPM-LONG.*RequiredFacts manifest mismatch.*htf_trend_intact",
    ):
        repository.read_control_state()


def test_pg_backed_runtime_control_state_repository_rejects_event_version_id_mismatch(
    pg_control_connection,
):
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_strategy_side_event_specs
            SET event_spec_version = 'v3'
            WHERE event_spec_id = 'event_spec:CPM-RO-001:CPM-LONG:v2'
            """
        )
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770000120100,
    )

    with pytest.raises(
        RuntimeControlStateRepositoryError,
        match="CPM-LONG:v2 mismatches event_spec_version=v3",
    ):
        repository.read_control_state()


def test_pg_backed_runtime_control_state_repository_requires_exact_disable_fact_manifest(
    pg_control_connection,
):
    pg_control_connection.execute(
        text(
            """
            DELETE FROM brc_strategy_event_required_facts
            WHERE event_spec_id = 'event_spec:BRF2-001:BRF2-SHORT:v2'
              AND fact_key = 'strong_uptrend_disable'
            """
        )
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770000120100,
    )

    with pytest.raises(
        RuntimeControlStateRepositoryError,
        match="BRF2-SHORT.*disable manifest mismatch.*strong_uptrend_disable",
    ):
        repository.read_control_state()


def test_pg_backed_runtime_control_state_repository_rejects_signal_event_spec_mismatch(
    pg_control_connection,
):
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_live_signal_events (
              signal_event_id, candidate_scope_id, event_spec_id, strategy_group_id,
              symbol, side, detector_key, signal_type, source_kind, status,
              freshness_state, confidence, fact_snapshot_id, reason_codes,
              signal_payload, event_time_ms, trigger_candle_close_time_ms,
              observed_at_ms, expires_at_ms, invalidated_at_ms, created_at_ms
            ) VALUES (
              'signal:SOR-001:ETHUSDT:long:wrong-event',
              'candidate_scope:SOR-001:ETHUSDT:long:SOR-LONG',
              'event_spec:SOR-001:SOR-SHORT:v2', 'SOR-001', 'ETHUSDT',
              'long', 'detector:SOR-001:long', 'SOR-SHORT', 'live_market',
              'facts_validated', 'fresh', 0.9, 'fact:SOR:wrong-event',
              '[]', '{}', 1770000120000, 1770000120000, 1770000120001,
              1770000720000, NULL, 1770000120002
            )
            """
        )
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770000120100,
    )

    with pytest.raises(RuntimeControlStateRepositoryError, match="mismatches candidate event spec"):
        repository.read_control_state()


def test_pg_backed_runtime_control_state_repository_rejects_generic_sor_signal_type(
    pg_control_connection,
):
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_live_signal_events (
              signal_event_id, candidate_scope_id, event_spec_id, strategy_group_id,
              symbol, side, detector_key, signal_type, source_kind, status,
              freshness_state, confidence, fact_snapshot_id, reason_codes,
              signal_payload, event_time_ms, trigger_candle_close_time_ms,
              observed_at_ms, expires_at_ms, invalidated_at_ms, created_at_ms
            ) VALUES (
              'signal:SOR-001:ETHUSDT:long:generic-type',
              'candidate_scope:SOR-001:ETHUSDT:long:SOR-LONG',
              'event_spec:SOR-001:SOR-LONG:v2', 'SOR-001', 'ETHUSDT',
              'long', 'detector:SOR-001:long', 'SOR-GENERIC', 'live_market',
              'facts_validated', 'fresh', 0.9, 'fact:SOR:generic-type',
              '[]', '{}', 1770000120000, 1770000120000, 1770000120001,
              1770000720000, NULL, 1770000120002
            )
            """
        )
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770000120100,
    )

    with pytest.raises(RuntimeControlStateRepositoryError, match="signal_type must equal event_id"):
        repository.read_control_state()


def test_pg_backed_runtime_control_state_repository_rejects_generated_at_as_event_time(
    pg_control_connection,
):
    with pytest.raises(IntegrityError, match="ck_brc_live_signal_no_generated_at_event_time"):
        pg_control_connection.execute(
            text(
                """
                INSERT INTO brc_live_signal_events (
                  signal_event_id, candidate_scope_id, event_spec_id, strategy_group_id,
                  symbol, side, detector_key, signal_type, source_kind, status,
                  freshness_state, confidence, fact_snapshot_id, reason_codes,
                  signal_payload, event_time_ms, trigger_candle_close_time_ms,
                  observed_at_ms, expires_at_ms, invalidated_at_ms, created_at_ms
                ) VALUES (
                  'signal:SOR-001:ETHUSDT:long:generated-at-time',
                  'candidate_scope:SOR-001:ETHUSDT:long:SOR-LONG',
                  'event_spec:SOR-001:SOR-LONG:v1', 'SOR-001', 'ETHUSDT',
                  'long', 'detector:SOR-001:long', 'SOR-LONG', 'live_market',
                  'facts_validated', 'fresh', 0.9, 'fact:SOR:generated-at-time',
                  '[]', '{}', 1770000120000, 1770000120000, 1770000120001,
                  1770000720000, NULL, 1770000120000
                )
                """
            )
        )


def test_pg_backed_runtime_control_state_repository_rejects_lane_without_arbitration_winner(
    pg_control_connection,
):
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_live_signal_events (
              signal_event_id, candidate_scope_id, event_spec_id, strategy_group_id,
              symbol, side, detector_key, signal_type, source_kind, status,
              freshness_state, confidence, fact_snapshot_id, reason_codes,
              signal_payload, event_time_ms, trigger_candle_close_time_ms,
              observed_at_ms, expires_at_ms, invalidated_at_ms, created_at_ms
            ) VALUES (
              'signal:SOR-001:ETHUSDT:long:lost',
              'candidate_scope:SOR-001:ETHUSDT:long:SOR-LONG',
              'event_spec:SOR-001:SOR-LONG:v2', 'SOR-001', 'ETHUSDT',
              'long', 'detector:SOR-001:long', 'SOR-LONG', 'live_market',
              'facts_validated', 'fresh', 0.9, 'fact:SOR:lost',
              '[]', '{}', 1770000120000, 1770000120000, 1770000120001,
              1770000720000, NULL, 1770000120002
            )
            """
        )
    )
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_pretrade_readiness_rows (
              readiness_row_id, candidate_scope_id, strategy_group_id, symbol,
              side, readiness_state, detector_state, watcher_state,
              public_facts_state, signal_lifecycle_status,
              signal_freshness_state, risk_state, scope_state, promotion_state,
              first_blocker_class, first_blocker_detail, next_action,
              stop_condition, evidence_ref, source_watermark, computed_at_ms,
              valid_until_ms
            ) VALUES (
              'readiness:SOR-001:ETHUSDT:long:lost',
              'candidate_scope:SOR-001:ETHUSDT:long:SOR-LONG',
              'SOR-001', 'ETHUSDT', 'long', 'ready', 'ready', 'fresh',
              'satisfied', 'facts_validated', 'fresh', 'acceptable',
              'live_submit_allowed', 'action_time_lane',
              'action_time_preflight_ready', 'ready', 'materialize_ticket',
              'ticket_created_or_lane_expires', 'fact:SOR:lost', 'unit',
              1770000120003, 1770000720000
            )
            """
        )
    )
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_promotion_candidates (
              promotion_candidate_id, signal_event_id, readiness_row_id,
              strategy_group_id, symbol, side, promotion_scope, status,
              scope_state, risk_state, facts_snapshot_id, blockers,
              arbitration_rank, created_at_ms, expires_at_ms, closed_at_ms,
              authority_boundary
            ) VALUES (
              'promotion:SOR-001:ETHUSDT:long:lost',
              'signal:SOR-001:ETHUSDT:long:lost',
              'readiness:SOR-001:ETHUSDT:long:lost',
              'SOR-001', 'ETHUSDT', 'long', 'live_submit_candidate',
              'arbitration_lost', 'live_submit_allowed', 'acceptable',
              'fact:SOR:lost', '[]', 2, 1770000120004, 1770000720000,
              1770000120005,
              'pg_promotion_candidate_non_executing; no_finalgate_no_operation_layer_no_exchange_write'
            )
            """
        )
    )
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_action_time_lane_inputs (
              action_time_lane_input_id, promotion_candidate_id, strategy_group_id,
              symbol, side, runtime_profile_id, lane_scope, status,
              signal_event_id, public_fact_snapshot_id, action_time_fact_snapshot_id,
              runtime_scope_binding_id, candidate_authorization_ref,
              runtime_safety_snapshot_id, first_blocker_class, created_at_ms,
              expires_at_ms, closed_at_ms, authority_boundary
            ) VALUES (
              'lane:SOR-001:ETHUSDT:long:lost',
              'promotion:SOR-001:ETHUSDT:long:lost', 'SOR-001', 'ETHUSDT',
              'long', 'owner-runtime-console-v1', 'real_submit_candidate',
              'ticket_pending', 'signal:SOR-001:ETHUSDT:long:lost',
              'fact:SOR:lost', 'fact:SOR:action',
              'runtime_scope:candidate_scope:SOR-001:ETHUSDT:long:SOR-LONG:owner-runtime-console-v1',
              NULL, NULL, 'action_time_preflight_ready', 1770000120006,
              1770000720000, NULL,
              'pg_real_submit_candidate_identity_only; no_finalgate_no_operation_layer_no_exchange_write'
            )
            """
        )
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=1770000120010,
    )

    with pytest.raises(RuntimeControlStateRepositoryError, match="does not reference arbitration_won"):
        repository.read_control_state()


def test_pg_backed_runtime_control_state_repository_ignores_closed_rehearsal_lineage(
    pg_control_connection,
):
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_live_signal_events (
              signal_event_id, candidate_scope_id, event_spec_id, strategy_group_id,
              symbol, side, detector_key, signal_type, source_kind, status,
              freshness_state, confidence, fact_snapshot_id, reason_codes,
              signal_payload, event_time_ms, trigger_candle_close_time_ms,
              observed_at_ms, expires_at_ms, invalidated_at_ms, created_at_ms
            ) VALUES (
              'signal:historical:closed:review', 'candidate_scope:retired',
              'event_spec:SOR-001:SOR-LONG:v1', 'SOR-001', 'ETHUSDT',
              'long', 'detector:SOR-001:long', 'SOR-LONG', 'historical',
              'stale', 'stale', NULL, NULL, '[]', '{}', 1770000120000,
              1770000120000, 1770000120001, NULL, 1770000130000,
              1770000120002
            )
            """
        )
    )
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_promotion_candidates (
              promotion_candidate_id, signal_event_id, readiness_row_id,
              strategy_group_id, symbol, side, promotion_scope, status,
              scope_state, risk_state, facts_snapshot_id, blockers,
              arbitration_rank, created_at_ms, expires_at_ms, closed_at_ms,
              authority_boundary
            ) VALUES (
              'promotion:historical:closed:review',
              'signal:historical:closed:review',
              'readiness:historical:closed:review',
              'SOR-001', 'ETHUSDT', 'long', 'action_time_rehearsal',
              'arbitration_lost', 'live_submit_allowed', 'acceptable',
              NULL, '[]', 2, 1770000120004, 1770000720000,
              1770000120005,
              'historical_rehearsal_lineage; no_finalgate_no_operation_layer_no_exchange_write'
            )
            """
        )
    )
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_action_time_lane_inputs (
              action_time_lane_input_id, promotion_candidate_id, strategy_group_id,
              symbol, side, runtime_profile_id, lane_scope, status,
              signal_event_id, public_fact_snapshot_id, action_time_fact_snapshot_id,
              runtime_scope_binding_id, candidate_authorization_ref,
              runtime_safety_snapshot_id, first_blocker_class, created_at_ms,
              expires_at_ms, closed_at_ms, authority_boundary
            ) VALUES (
              'lane:historical:closed:review',
              'promotion:historical:closed:review', 'SOR-001', 'ETHUSDT',
              'long', 'owner-runtime-console-v1', 'rehearsal',
              'closed', 'signal:historical:closed:review', NULL, NULL,
              'runtime_scope:retired', NULL, NULL, NULL, 1770000120006,
              1770000720000, 1770000120010,
              'closed_rehearsal_lineage; no_finalgate_no_operation_layer_no_exchange_write'
            )
            """
        )
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(pg_control_connection)

    state = repository.read_control_state()

    assert state["table_counts"]["action_time_lane_inputs"] == 1
    assert state["table_counts"]["promotion_candidates"] == 1
    assert state["table_counts"]["live_signal_events"] == 1


def test_pg_backed_runtime_control_state_repository_requires_runtime_policy_binding(
    pg_control_connection,
):
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_runtime_scope_bindings
            SET policy_current_id = 'policy_current:missing'
            WHERE runtime_scope_binding_id =
              'runtime_scope:candidate_scope:MPG-001:OPUSDT:long:MPG-LONG:owner-runtime-console-v1'
            """
        )
    )
    pg_control_connection.commit()
    repository = PgBackedRuntimeControlStateRepository(pg_control_connection)

    with pytest.raises(RuntimeControlStateRepositoryError, match="has no current owner policy"):
        repository.read_control_state()


def test_runtime_control_state_repository_validator_rejects_non_postgres_without_test_flag(
    capsys,
):
    validator = _load_module(VALIDATOR_PATH, "validate_runtime_control_state_repository")

    assert validator.main(["--database-url", "sqlite:///tmp/runtime-control-state.db"]) == 2

    captured = capsys.readouterr()
    assert "requires PostgreSQL DSN" in captured.err


def test_runtime_control_state_repository_validator_reports_seeded_state(
    tmp_path: Path,
    capsys,
):
    database_url = f"sqlite:///{tmp_path / 'runtime-control-state.db'}"
    _seed_database_url(database_url)
    validator = _load_module(VALIDATOR_PATH, "validate_runtime_control_state_repository")

    assert (
        validator.main(
            [
                "--database-url",
                database_url,
                "--allow-non-postgres-for-test",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "runtime_control_state_repository_valid"
    assert payload["strategy_group_count"] == 5
    assert payload["event_spec_count"] == 6
    assert payload["candidate_scope_count"] == 22
    assert payload["runtime_scope_binding_count"] == 22
    assert payload["current_projection_ownership_count"] == 6
    assert all(value is False for value in payload["forbidden_effects"].values())


def _seed_database_url(database_url: str) -> None:
    migration = _load_module(MIGRATION_PATH, "migration_086_repository_validator")
    asset_neutral_expand = _load_module(
        next(REPO_ROOT.glob("migrations/versions/*-131_*.py")),
        "migration_131_repository_validator",
    )
    seed = _load_module(SEED_PATH, "seed_runtime_control_state_repository_validator")
    engine = create_engine(database_url)
    try:
        with engine.begin() as conn:
            old_op = migration.op
            migration.op = Operations(MigrationContext.configure(conn))
            try:
                migration.upgrade()
            finally:
                migration.op = old_op
            old_expand_op = asset_neutral_expand.op
            asset_neutral_expand.op = Operations(MigrationContext.configure(conn))
            try:
                asset_neutral_expand.upgrade()
            finally:
                asset_neutral_expand.op = old_expand_op
            seed.seed_runtime_control_state_foundation(conn)
            conn.execute(
                text(
                    """
                    UPDATE brc_strategy_group_candidate_scope
                    SET exchange_instrument_id = (
                      SELECT mapping.exchange_instrument_id
                      FROM brc_symbol_instrument_mappings AS mapping
                      WHERE mapping.symbol = brc_strategy_group_candidate_scope.symbol
                        AND mapping.status = 'active'
                      ORDER BY mapping.valid_from_ms DESC, mapping.mapping_id DESC
                      LIMIT 1
                    )
                    """
                )
            )
    finally:
        engine.dispose()
