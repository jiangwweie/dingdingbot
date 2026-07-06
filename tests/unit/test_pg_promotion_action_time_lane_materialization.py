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
from sqlalchemy.pool import StaticPool

from scripts import materialize_action_time_ticket as ticket_materializer
from scripts import materialize_pg_promotion_action_time_lane as lane_materializer


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py"
)
SEED_PATH = REPO_ROOT / "scripts/seed_runtime_control_state_foundation.py"
NOW_MS = 1770001000000


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
    migration = _load_module(MIGRATION_PATH, "migration_086_pg_promotion_lane")
    seed = _load_module(SEED_PATH, "seed_pg_promotion_lane")
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
        finally:
            migration.op = old_op
        seed.seed_runtime_control_state_foundation(conn)
    with engine.connect() as conn:
        yield conn
    engine.dispose()


def test_cli_requires_database_url(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.delenv("PG_DATABASE_URL", raising=False)
    result = lane_materializer.main(
        [
            "--require-database-url",
        ]
    )

    assert result == 2
    assert "PG_DATABASE_URL is required" in capsys.readouterr().err
    assert not (tmp_path / "lane.json").exists()


def test_noops_without_fresh_signal(pg_control_connection):
    payload = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert payload["status"] == "no_fresh_signal"
    assert payload["next_action"] == "continue_watcher_observation"
    assert payload["forbidden_effects"] == lane_materializer.FORBIDDEN_EFFECTS
    assert _count(pg_control_connection, "brc_promotion_candidates") == 0
    assert _count(pg_control_connection, "brc_action_time_lane_inputs") == 0
    assert _count(pg_control_connection, "brc_budget_reservations") == 0
    assert _count(pg_control_connection, "brc_protection_references") == 0


def test_materializes_promotion_lane_budget_protection_and_ticket(pg_control_connection):
    _insert_ready_fresh_signal(pg_control_connection, "SOR-001", "ETHUSDT", "long")

    payload = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert payload["status"] == "promotion_action_time_lane_created"
    assert payload["strategy_group_id"] == "SOR-001"
    assert payload["symbol"] == "ETHUSDT"
    assert payload["side"] == "long"
    assert payload["next_action"] == "materialize_action_time_ticket"
    assert payload["forbidden_effects"] == lane_materializer.FORBIDDEN_EFFECTS

    promotion = pg_control_connection.execute(
        text(
            """
            SELECT status, promotion_scope, signal_event_id, blockers
            FROM brc_promotion_candidates
            """
        )
    ).mappings().one()
    assert promotion["status"] == "arbitration_won"
    assert promotion["promotion_scope"] == "live_submit_candidate"
    assert json.loads(promotion["blockers"]) == []

    lane = pg_control_connection.execute(
        text(
            """
            SELECT action_time_lane_input_id, lane_scope, status,
                   signal_event_id, public_fact_snapshot_id,
                   action_time_fact_snapshot_id, candidate_authorization_ref,
                   first_blocker_class
            FROM brc_action_time_lane_inputs
            """
        )
    ).mappings().one()
    assert lane["action_time_lane_input_id"] == payload["action_time_lane_input_id"]
    assert lane["lane_scope"] == "real_submit_candidate"
    assert lane["status"] == "ticket_pending"
    assert lane["signal_event_id"] == payload["signal_event_id"]
    assert lane["public_fact_snapshot_id"]
    assert lane["action_time_fact_snapshot_id"]
    assert lane["candidate_authorization_ref"]
    assert lane["first_blocker_class"] == "action_time_preflight_ready"

    budget = pg_control_connection.execute(
        text(
            """
            SELECT status, target_notional, leverage, reserved_margin
            FROM brc_budget_reservations
            """
        )
    ).mappings().one()
    assert budget["status"] == "active"
    assert str(budget["target_notional"]) in {"20", "20.0000000000"}
    assert str(budget["leverage"]) in {"2", "2.0000000000"}
    assert str(budget["reserved_margin"]) in {"10", "10.0000000000"}

    protection = pg_control_connection.execute(
        text(
            """
            SELECT reference_type, reference_price, source_fact_snapshot_id
            FROM brc_protection_references
            """
        )
    ).mappings().one()
    assert protection["reference_type"] == "opening_range_low_reference"
    assert str(protection["reference_price"]) in {"1800", "1800.0000000000"}
    assert protection["source_fact_snapshot_id"]

    ticket_payload = ticket_materializer.materialize_action_time_ticket(
        pg_control_connection,
        now_ms=NOW_MS,
    )
    assert ticket_payload["status"] == "action_time_ticket_created"
    assert ticket_payload["action_time_lane_input_id"] == payload["action_time_lane_input_id"]
    assert ticket_payload["strategy_group_id"] == "SOR-001"
    assert ticket_payload["symbol"] == "ETHUSDT"
    assert ticket_payload["side"] == "long"


def test_blocks_fresh_signal_without_action_time_facts(pg_control_connection):
    _insert_ready_fresh_signal(
        pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
    )

    payload = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert payload["status"] == "promotion_candidates_blocked"
    assert "action_time_fact_snapshot_missing" in payload["blockers"]
    assert _count(pg_control_connection, "brc_promotion_candidates") == 1
    assert _count(pg_control_connection, "brc_action_time_lane_inputs") == 0
    assert _count(pg_control_connection, "brc_budget_reservations") == 0
    assert _count(pg_control_connection, "brc_protection_references") == 0

    row = pg_control_connection.execute(
        text("SELECT status, blockers FROM brc_promotion_candidates")
    ).mappings().one()
    assert row["status"] == "blocked"
    assert "action_time_fact_snapshot_missing" in json.loads(row["blockers"])


def test_blocks_brf2_promotion_when_disable_fact_is_missing(pg_control_connection):
    _insert_ready_fresh_signal(
        pg_control_connection,
        "BRF2-001",
        "BTCUSDT",
        "short",
        fact_values={
            "rally_failure_confirmed": True,
            "short_side_not_disabled": True,
            "rally_high_reference": "1800",
        },
    )

    payload = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert payload["status"] == "promotion_candidates_blocked"
    assert "disable_fact_missing:strong_uptrend_disable" in payload["blockers"]
    assert _count(pg_control_connection, "brc_promotion_candidates") == 1
    assert _count(pg_control_connection, "brc_action_time_lane_inputs") == 0
    assert _count(pg_control_connection, "brc_budget_reservations") == 0
    assert _count(pg_control_connection, "brc_protection_references") == 0


@pytest.mark.parametrize("disable_value", [None, "unknown", "missing", "null", ""])
def test_blocks_brf2_promotion_when_disable_fact_is_unknown(
    pg_control_connection,
    disable_value,
):
    _insert_ready_fresh_signal(
        pg_control_connection,
        "BRF2-001",
        "BTCUSDT",
        "short",
        fact_values={
            "rally_failure_confirmed": True,
            "short_side_not_disabled": True,
            "rally_high_reference": "1800",
            "strong_uptrend_disable": disable_value,
        },
    )

    payload = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert payload["status"] == "promotion_candidates_blocked"
    assert "disable_fact_missing:strong_uptrend_disable" in payload["blockers"]
    assert "disable_fact_active:strong_uptrend_disable" not in payload["blockers"]
    assert _count(pg_control_connection, "brc_promotion_candidates") == 1
    assert _count(pg_control_connection, "brc_action_time_lane_inputs") == 0
    assert _count(pg_control_connection, "brc_budget_reservations") == 0
    assert _count(pg_control_connection, "brc_protection_references") == 0


def test_conditional_rehearsal_scope_does_not_create_real_submit_lane(pg_control_connection):
    _insert_ready_fresh_signal(pg_control_connection, "SOR-001", "ETHUSDT", "long")
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_strategy_group_candidate_scope
            SET scope_state = 'conditional_action_time_rehearsal_allowed'
            WHERE strategy_group_id = 'SOR-001'
              AND symbol = 'ETHUSDT'
              AND side = 'long'
            """
        )
    )
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_pretrade_readiness_rows
            SET scope_state = 'conditional_action_time_rehearsal_allowed'
            WHERE strategy_group_id = 'SOR-001'
              AND symbol = 'ETHUSDT'
              AND side = 'long'
            """
        )
    )

    payload = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert payload["status"] == "promotion_candidates_blocked"
    assert "candidate_scope_not_live_submit:conditional_action_time_rehearsal_allowed" in payload["blockers"]
    assert "readiness_scope_not_live_submit:conditional_action_time_rehearsal_allowed" in payload["blockers"]
    assert _count(pg_control_connection, "brc_promotion_candidates") == 1
    assert _count(pg_control_connection, "brc_action_time_lane_inputs") == 0
    assert _count(pg_control_connection, "brc_budget_reservations") == 0
    assert _count(pg_control_connection, "brc_protection_references") == 0


def test_existing_open_real_lane_prevents_duplicate(pg_control_connection):
    _insert_ready_fresh_signal(pg_control_connection, "SOR-001", "ETHUSDT", "long")
    first = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS,
    )
    second = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS + 1,
    )

    assert first["status"] == "promotion_action_time_lane_created"
    assert second["status"] == "action_time_lane_already_open"
    assert second["action_time_lane_input_id"] == first["action_time_lane_input_id"]
    assert _count(pg_control_connection, "brc_action_time_lane_inputs") == 1
    assert _count(pg_control_connection, "brc_budget_reservations") == 1
    assert _count(pg_control_connection, "brc_protection_references") == 1


def test_expired_open_real_lane_blocks_with_close_action(pg_control_connection):
    _insert_ready_fresh_signal(pg_control_connection, "SOR-001", "ETHUSDT", "long")
    first = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS,
    )
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_action_time_lane_inputs
            SET expires_at_ms = :expires_at_ms
            WHERE action_time_lane_input_id = :lane_id
            """
        ),
        {
            "expires_at_ms": NOW_MS - 1,
            "lane_id": first["action_time_lane_input_id"],
        },
    )

    second = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS + 1,
    )

    assert second["status"] == "open_action_time_lane_expired"
    assert second["blockers"] == ["open_action_time_lane_expired_not_closed"]
    assert second["next_action"] == "expire_or_close_pg_action_time_lane"
    assert second["action_time_lane_input_id"] == first["action_time_lane_input_id"]
    assert _count(pg_control_connection, "brc_action_time_lane_inputs") == 1


def test_multiple_fresh_candidates_select_one_by_strategy_priority(pg_control_connection):
    _insert_ready_fresh_signal(pg_control_connection, "SOR-001", "ETHUSDT", "long")
    _insert_ready_fresh_signal(pg_control_connection, "MPG-001", "OPUSDT", "long")

    payload = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert payload["status"] == "promotion_action_time_lane_created"
    assert payload["strategy_group_id"] == "MPG-001"
    assert payload["symbol"] == "OPUSDT"
    assert _count(pg_control_connection, "brc_promotion_candidates") == 2
    assert _count(pg_control_connection, "brc_action_time_lane_inputs") == 1
    statuses = {
        row["strategy_group_id"]: row["status"]
        for row in pg_control_connection.execute(
            text("SELECT strategy_group_id, status FROM brc_promotion_candidates")
        ).mappings()
    }
    assert statuses == {"MPG-001": "arbitration_won", "SOR-001": "arbitration_lost"}


def test_stale_high_priority_candidate_loses_to_fresh_lower_priority(pg_control_connection):
    _insert_ready_fresh_signal(pg_control_connection, "MPG-001", "OPUSDT", "long")
    _insert_ready_fresh_signal(pg_control_connection, "SOR-001", "ETHUSDT", "long")
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_live_signal_events
            SET freshness_state = 'stale'
            WHERE signal_event_id = 'signal:MPG-001:OPUSDT:long:unit'
            """
        )
    )

    payload = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert payload["status"] == "promotion_action_time_lane_created"
    assert payload["strategy_group_id"] == "SOR-001"
    assert payload["symbol"] == "ETHUSDT"
    assert _count(pg_control_connection, "brc_promotion_candidates") == 1
    assert _count(pg_control_connection, "brc_action_time_lane_inputs") == 1


def test_same_session_opposite_side_conflict_blocks_real_submit_lane(pg_control_connection):
    _insert_ready_fresh_signal(pg_control_connection, "SOR-001", "ETHUSDT", "long")
    _insert_ready_fresh_signal(pg_control_connection, "SOR-001", "ETHUSDT", "short")

    payload = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert payload["status"] == "promotion_candidates_blocked"
    assert "same_session_opposite_side_conflict" in payload["blockers"]
    assert _count(pg_control_connection, "brc_promotion_candidates") == 2
    assert _count(pg_control_connection, "brc_action_time_lane_inputs") == 0
    rows = pg_control_connection.execute(
        text("SELECT status, blockers FROM brc_promotion_candidates")
    ).mappings()
    for row in rows:
        assert row["status"] == "blocked"
        assert "same_session_opposite_side_conflict" in json.loads(row["blockers"])


def test_brf2_short_with_active_position_conflict_does_not_open_real_submit_lane(
    pg_control_connection,
):
    _insert_ready_fresh_signal(pg_control_connection, "BRF2-001", "BTCUSDT", "short")
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_runtime_fact_snapshots
            SET fact_values = :fact_values
            WHERE fact_snapshot_id = 'fact:BRF2-001:BTCUSDT:short:unit:account-safe'
            """
        ),
        {
            "fact_values": _json(
                {
                    "account_safe": True,
                    "open_orders_clear": True,
                    "active_position_or_open_order_clear": False,
                }
            )
        },
    )

    payload = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert payload["status"] == "promotion_candidates_blocked"
    assert "active_position_or_open_order_conflict" in payload["blockers"]
    assert _count(pg_control_connection, "brc_promotion_candidates") == 1
    assert _count(pg_control_connection, "brc_action_time_lane_inputs") == 0


def test_db_rejects_replay_as_fresh_live_signal(pg_control_connection):
    row = _candidate_runtime_row(pg_control_connection, "SOR-001", "ETHUSDT", "long")
    with pytest.raises(sa.exc.IntegrityError):
        _insert_signal(
            pg_control_connection,
            row,
            public_fact_id="fact:SOR-001:ETHUSDT:long:public:invalid-replay",
            signal_event_id="signal:SOR-001:ETHUSDT:long:invalid-replay",
            source_kind="replay",
        )


def test_db_rejects_generated_at_as_event_time(pg_control_connection):
    row = _candidate_runtime_row(pg_control_connection, "SOR-001", "ETHUSDT", "long")
    with pytest.raises(sa.exc.IntegrityError):
        _insert_signal(
            pg_control_connection,
            row,
            public_fact_id="fact:SOR-001:ETHUSDT:long:public:invalid-time",
            signal_event_id="signal:SOR-001:ETHUSDT:long:invalid-time",
            created_at_ms=NOW_MS - 60_000,
        )


def _insert_ready_fresh_signal(
    conn,
    strategy_group_id: str,
    symbol: str,
    side: str,
    *,
    insert_action_time_fact: bool = True,
    fact_values: dict | None = None,
) -> None:
    row = _candidate_runtime_row(conn, strategy_group_id, symbol, side)
    suffix = f"{strategy_group_id}:{symbol}:{side}:unit"
    public_fact_id = f"fact:{suffix}:public"
    action_time_fact_id = f"fact:{suffix}:action-time"
    account_safe_fact_id = f"fact:{suffix}:account-safe"
    account_mode_fact_id = f"fact:{suffix}:account-mode"
    signal_event_id = f"signal:{suffix}"
    readiness_row_id = f"readiness:{suffix}"
    expires_at_ms = NOW_MS + 600_000
    fact_values = fact_values or _fact_values(conn, row)

    _insert_coverage(conn, row, expires_at_ms=expires_at_ms)
    _insert_fact(
        conn,
        fact_snapshot_id=public_fact_id,
        row=row,
        fact_surface="pretrade_public",
        fact_values=fact_values,
        observed_at_ms=NOW_MS - 20_000,
        valid_until_ms=expires_at_ms,
    )
    if insert_action_time_fact:
        _insert_fact(
            conn,
            fact_snapshot_id=action_time_fact_id,
            row=row,
            fact_surface="action_time",
            fact_values=fact_values,
            observed_at_ms=NOW_MS - 10_000,
            valid_until_ms=expires_at_ms,
        )
    _insert_fact(
        conn,
        fact_snapshot_id=account_safe_fact_id,
        row=row,
        fact_surface="account_safe",
        fact_values={
            "account_safe": True,
            "open_orders_clear": True,
            "active_position_or_open_order_clear": True,
        },
        observed_at_ms=NOW_MS - 8_000,
        valid_until_ms=expires_at_ms,
    )
    _insert_fact(
        conn,
        fact_snapshot_id=account_mode_fact_id,
        row=row,
        fact_surface="account_mode",
        fact_values={"account_mode": "one_way", "position_mode_safe": True},
        observed_at_ms=NOW_MS - 7_000,
        valid_until_ms=expires_at_ms,
    )
    _insert_signal(
        conn,
        row,
        public_fact_id=public_fact_id,
        signal_event_id=signal_event_id,
    )
    conn.execute(
        text(
            """
            INSERT INTO brc_pretrade_readiness_rows (
              readiness_row_id, candidate_scope_id, strategy_group_id, symbol, side,
              readiness_state, detector_state, watcher_state, public_facts_state,
              signal_lifecycle_status, signal_freshness_state, risk_state, scope_state,
              promotion_state, first_blocker_class, first_blocker_detail, next_action,
              stop_condition, evidence_ref, source_watermark, computed_at_ms, valid_until_ms
            ) VALUES (
              :readiness_row_id, :candidate_scope_id, :strategy_group_id, :symbol, :side,
              'action_time_lane', 'running', 'fresh', 'satisfied', 'facts_validated', 'fresh',
              'acceptable', 'live_submit_allowed', 'action_time_lane',
              'action_time_preflight_ready', 'unit fresh action-time path ready',
              'materialize_pg_promotion_action_time_lane',
              'ticket_created_or_lane_expires', :evidence_ref, 'unit',
              :computed_at_ms, :valid_until_ms
            )
            """
        ),
        {
            "readiness_row_id": readiness_row_id,
            "candidate_scope_id": row["candidate_scope_id"],
            "strategy_group_id": row["strategy_group_id"],
            "symbol": row["symbol"],
            "side": row["side"],
            "evidence_ref": public_fact_id,
            "computed_at_ms": NOW_MS - 6_000,
            "valid_until_ms": expires_at_ms,
        },
    )


def _candidate_runtime_row(conn, strategy_group_id: str, symbol: str, side: str):
    return conn.execute(
        text(
            """
            SELECT c.candidate_scope_id,
                   c.strategy_group_id,
                   c.symbol,
                   c.side,
                   c.policy_current_id,
                   c.priority_rank,
                   r.runtime_scope_binding_id,
                   r.runtime_profile_id,
                   b.event_spec_id,
                   e.event_id,
                   e.protection_ref_type
            FROM brc_strategy_group_candidate_scope c
            JOIN brc_runtime_scope_bindings r
              ON r.candidate_scope_id = c.candidate_scope_id
             AND r.status = 'active'
            JOIN brc_candidate_scope_event_bindings b
              ON b.candidate_scope_id = c.candidate_scope_id
             AND b.status = 'active'
            JOIN brc_strategy_side_event_specs e
              ON e.event_spec_id = b.event_spec_id
             AND e.status = 'current'
            WHERE c.strategy_group_id = :strategy_group_id
              AND c.symbol = :symbol
              AND c.side = :side
            LIMIT 1
            """
        ),
        {"strategy_group_id": strategy_group_id, "symbol": symbol, "side": side},
    ).mappings().one()


def _insert_coverage(conn, row, *, expires_at_ms: int) -> None:
    conn.execute(
        text(
            """
            INSERT INTO brc_watcher_runtime_coverage (
              runtime_coverage_id, strategy_group_id, symbol, side, detector_key,
              runtime_profile_id, coverage_state, liveness_state, last_tick_at_ms,
              valid_until_ms, is_current, created_at_ms
            ) VALUES (
              :runtime_coverage_id, :strategy_group_id, :symbol, :side, :detector_key,
              :runtime_profile_id, 'covered', 'healthy', :last_tick_at_ms,
              :valid_until_ms, true, :created_at_ms
            )
            """
        ),
        {
            "runtime_coverage_id": f"coverage:{row['strategy_group_id']}:{row['symbol']}:{row['side']}:unit",
            "strategy_group_id": row["strategy_group_id"],
            "symbol": row["symbol"],
            "side": row["side"],
            "detector_key": f"detector:{row['strategy_group_id']}:{row['side']}",
            "runtime_profile_id": row["runtime_profile_id"],
            "last_tick_at_ms": NOW_MS - 5_000,
            "valid_until_ms": expires_at_ms,
            "created_at_ms": NOW_MS - 5_000,
        },
    )


def _insert_signal(
    conn,
    row,
    *,
    public_fact_id: str,
    signal_event_id: str,
    source_kind: str = "live_market",
    created_at_ms: int = NOW_MS - 54_000,
) -> None:
    conn.execute(
        text(
            """
            INSERT INTO brc_live_signal_events (
              signal_event_id, candidate_scope_id, event_spec_id, strategy_group_id,
              symbol, side, detector_key, signal_type, source_kind, status, freshness_state,
              confidence, fact_snapshot_id, reason_codes, signal_payload,
              event_time_ms, trigger_candle_close_time_ms, observed_at_ms,
              expires_at_ms, invalidated_at_ms, created_at_ms
            ) VALUES (
              :signal_event_id, :candidate_scope_id, :event_spec_id, :strategy_group_id,
              :symbol, :side, :detector_key, :signal_type,
              :source_kind, 'facts_validated', 'fresh', 0.9, :fact_snapshot_id,
              :reason_codes, :signal_payload, :event_time_ms,
              :trigger_candle_close_time_ms, :observed_at_ms, :expires_at_ms,
              NULL, :created_at_ms
            )
            """
        ),
        {
            "signal_event_id": signal_event_id,
            "candidate_scope_id": row["candidate_scope_id"],
            "event_spec_id": row["event_spec_id"],
            "strategy_group_id": row["strategy_group_id"],
            "symbol": row["symbol"],
            "side": row["side"],
            "detector_key": f"detector:{row['strategy_group_id']}:{row['side']}",
            "signal_type": row["event_id"],
            "source_kind": source_kind,
            "fact_snapshot_id": public_fact_id,
            "reason_codes": _json(["unit_fresh_signal"]),
            "signal_payload": _json(
                {
                    "time_authority": "trigger_candle_close_time_ms",
                    "trigger_candle_close_time_ms": NOW_MS - 60_000,
                }
            ),
            "event_time_ms": NOW_MS - 60_000,
            "trigger_candle_close_time_ms": NOW_MS - 60_000,
            "observed_at_ms": NOW_MS - 55_000,
            "expires_at_ms": NOW_MS + 600_000,
            "created_at_ms": created_at_ms,
        },
    )


def _insert_fact(
    conn,
    *,
    fact_snapshot_id: str,
    row,
    fact_surface: str,
    fact_values: dict,
    observed_at_ms: int,
    valid_until_ms: int,
) -> None:
    conn.execute(
        text(
            """
            INSERT INTO brc_runtime_fact_snapshots (
              fact_snapshot_id, strategy_group_id, symbol, side, runtime_profile_id,
              fact_surface, source_kind, source_ref, computed, satisfied,
              freshness_state, failed_facts, fact_values, blocker_class,
              observed_at_ms, valid_until_ms, created_at_ms
            ) VALUES (
              :fact_snapshot_id, :strategy_group_id, :symbol, :side, :runtime_profile_id,
              :fact_surface, 'unit_test', :source_ref, true, true, 'fresh',
              :failed_facts, :fact_values, 'market_wait_validated',
              :observed_at_ms, :valid_until_ms, :created_at_ms
            )
            """
        ),
        {
            "fact_snapshot_id": fact_snapshot_id,
            "strategy_group_id": row["strategy_group_id"],
            "symbol": row["symbol"],
            "side": row["side"],
            "runtime_profile_id": row["runtime_profile_id"],
            "fact_surface": fact_surface,
            "source_ref": f"unit:{fact_surface}",
            "failed_facts": _json([]),
            "fact_values": _json(fact_values),
            "observed_at_ms": observed_at_ms,
            "valid_until_ms": valid_until_ms,
            "created_at_ms": observed_at_ms,
        },
    )


def _fact_values(conn, row) -> dict:
    facts = conn.execute(
        text(
            """
            SELECT fact_key, operator, expected_value, disable_on_match
            FROM brc_strategy_event_required_facts
            WHERE event_spec_id = :event_spec_id
              AND status = 'current'
            """
        ),
        {"event_spec_id": row["event_spec_id"]},
    ).mappings()
    result: dict[str, object] = {}
    for fact in facts:
        key = fact["fact_key"]
        if fact["disable_on_match"]:
            result[key] = False
        elif fact["operator"] == "exists":
            result[key] = "1800"
        elif fact["expected_value"] is not None:
            result[key] = fact["expected_value"]
        else:
            result[key] = True
    result[row["protection_ref_type"]] = "1800"
    return result


def _count(conn, table_name: str) -> int:
    assert table_name in {
        "brc_action_time_lane_inputs",
        "brc_budget_reservations",
        "brc_promotion_candidates",
        "brc_protection_references",
    }
    return conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()


def _json(value) -> str:
    return json.dumps(value, sort_keys=True)
