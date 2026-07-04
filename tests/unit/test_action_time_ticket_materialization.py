from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from scripts import materialize_action_time_ticket as ticket_materializer


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
    migration = _load_module(MIGRATION_PATH, "migration_086_action_time_ticket")
    seed = _load_module(SEED_PATH, "seed_action_time_ticket")
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
    result = ticket_materializer.main(
        [
            "--require-database-url",
            "--output-json",
            str(tmp_path / "ticket.json"),
        ]
    )

    assert result == 2
    assert "PG_DATABASE_URL is required" in capsys.readouterr().err
    assert not (tmp_path / "ticket.json").exists()


def test_noops_without_action_time_lane(pg_control_connection):
    payload = ticket_materializer.materialize_action_time_ticket(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert payload["status"] == "no_action_time_lane_input"
    assert payload["ticket_id"] is None
    assert payload["forbidden_effects"]["exchange_write_called"] is False


def test_materializes_pg_action_time_ticket(pg_control_connection):
    lane_id = _insert_action_time_lane_graph(pg_control_connection)

    payload = ticket_materializer.materialize_action_time_ticket(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert payload["status"] == "action_time_ticket_created"
    assert payload["action_time_lane_input_id"] == lane_id
    assert payload["strategy_group_id"] == "SOR-001"
    assert payload["symbol"] == "ETHUSDT"
    assert payload["side"] == "long"
    assert payload["next_action"] == "run_official_action_time_finalgate"
    assert payload["forbidden_effects"] == ticket_materializer.FORBIDDEN_EFFECTS

    ticket = pg_control_connection.execute(
        text(
            """
            SELECT ticket_id, status, action_time_lane_input_id,
                   signal_event_id, budget_reservation_id, protection_ref_id,
                   execution_policy_id, event_time_ms, trigger_candle_close_time_ms
            FROM brc_action_time_tickets
            """
        )
    ).mappings().one()
    assert ticket["ticket_id"] == payload["ticket_id"]
    assert ticket["status"] == "created"
    assert ticket["action_time_lane_input_id"] == lane_id
    assert ticket["signal_event_id"] == "signal:SOR-001:ETHUSDT:long:unit"
    assert ticket["event_time_ms"] == ticket["trigger_candle_close_time_ms"]

    event_count = pg_control_connection.execute(
        text("SELECT COUNT(*) FROM brc_action_time_ticket_events")
    ).scalar_one()
    assert event_count == 1

    lane_status = pg_control_connection.execute(
        text(
            """
            SELECT status
            FROM brc_action_time_lane_inputs
            WHERE action_time_lane_input_id = :lane_id
            """
        ),
        {"lane_id": lane_id},
    ).scalar_one()
    assert lane_status == "ticket_created"

    budget = pg_control_connection.execute(
        text(
            """
            SELECT status, ticket_id
            FROM brc_budget_reservations
            WHERE action_time_lane_input_id = :lane_id
            """
        ),
        {"lane_id": lane_id},
    ).mappings().one()
    assert budget["status"] == "consumed"
    assert budget["ticket_id"] == payload["ticket_id"]


def test_materializer_is_idempotent_for_existing_active_ticket(pg_control_connection):
    _insert_action_time_lane_graph(pg_control_connection)
    first = ticket_materializer.materialize_action_time_ticket(
        pg_control_connection,
        now_ms=NOW_MS,
    )
    second = ticket_materializer.materialize_action_time_ticket(
        pg_control_connection,
        now_ms=NOW_MS + 1,
    )

    assert first["status"] == "action_time_ticket_created"
    assert second["status"] == "action_time_ticket_already_exists"
    assert second["ticket_id"] == first["ticket_id"]
    assert pg_control_connection.execute(
        text("SELECT COUNT(*) FROM brc_action_time_tickets")
    ).scalar_one() == 1
    assert pg_control_connection.execute(
        text("SELECT COUNT(*) FROM brc_action_time_ticket_events")
    ).scalar_one() == 1


def test_materializer_blocks_missing_candidate_authorization_ref(pg_control_connection):
    _insert_action_time_lane_graph(
        pg_control_connection,
        candidate_authorization_ref=None,
    )

    payload = ticket_materializer.materialize_action_time_ticket(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert payload["status"] == "blocked"
    assert "candidate_authorization_ref_missing" in payload["blockers"]
    assert _ticket_count(pg_control_connection) == 0


def test_materializer_blocks_missing_budget_reservation(pg_control_connection):
    _insert_action_time_lane_graph(pg_control_connection, insert_budget=False)

    payload = ticket_materializer.materialize_action_time_ticket(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert payload["status"] == "blocked"
    assert "budget_reservation_missing" in payload["blockers"]
    assert _ticket_count(pg_control_connection) == 0


def test_materializer_blocks_missing_protection_ref(pg_control_connection):
    _insert_action_time_lane_graph(pg_control_connection, insert_protection=False)

    payload = ticket_materializer.materialize_action_time_ticket(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert payload["status"] == "blocked"
    assert "protection_ref_missing" in payload["blockers"]
    assert _ticket_count(pg_control_connection) == 0


def test_materializer_blocks_runtime_scope_side_mismatch(pg_control_connection):
    lane_id = _insert_action_time_lane_graph(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_action_time_lane_inputs
            SET side = 'short'
            WHERE action_time_lane_input_id = :lane_id
            """
        ),
        {"lane_id": lane_id},
    )

    payload = ticket_materializer.materialize_action_time_ticket(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert payload["status"] == "blocked"
    assert any(blocker.endswith("_mismatch:side") for blocker in payload["blockers"])
    assert _ticket_count(pg_control_connection) == 0


def test_materializer_blocks_required_fact_not_satisfied(pg_control_connection):
    _insert_action_time_lane_graph(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_runtime_fact_snapshots
            SET fact_values = :fact_values
            WHERE fact_snapshot_id = 'fact:SOR-001:ETHUSDT:long:action-time:unit'
            """
        ),
        {
            "fact_values": _json(
                {
                    "opening_range_defined": True,
                    "breakout_confirmed": False,
                    "opening_range_low_reference": "1800",
                }
            )
        },
    )

    payload = ticket_materializer.materialize_action_time_ticket(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert payload["status"] == "blocked"
    assert "required_fact_not_satisfied:breakout_confirmed" in payload["blockers"]
    assert _ticket_count(pg_control_connection) == 0


def _insert_action_time_lane_graph(
    conn,
    *,
    candidate_authorization_ref: str | None = "candidate_auth:SOR-001:ETHUSDT:long:unit",
    insert_budget: bool = True,
    insert_protection: bool = True,
) -> str:
    row = conn.execute(
        text(
            """
            SELECT c.candidate_scope_id,
                   c.strategy_group_id,
                   c.symbol,
                   c.side,
                   c.policy_current_id,
                   r.runtime_scope_binding_id,
                   r.runtime_profile_id,
                   b.event_spec_id,
                   e.event_id,
                   e.strategy_group_version_id,
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
            WHERE c.strategy_group_id = 'SOR-001'
              AND c.symbol = 'ETHUSDT'
              AND c.side = 'long'
            LIMIT 1
            """
        )
    ).mappings().one()
    lane_id = "lane:SOR-001:ETHUSDT:long:unit"
    readiness_row_id = "readiness:SOR-001:ETHUSDT:long:unit"
    signal_event_id = "signal:SOR-001:ETHUSDT:long:unit"
    promotion_candidate_id = "promotion:SOR-001:ETHUSDT:long:unit"
    public_fact_id = "fact:SOR-001:ETHUSDT:long:public:unit"
    action_time_fact_id = "fact:SOR-001:ETHUSDT:long:action-time:unit"
    account_safe_fact_id = "fact:SOR-001:ETHUSDT:long:account-safe:unit"
    account_mode_fact_id = "fact:SOR-001:ETHUSDT:long:account-mode:unit"
    expires_at_ms = NOW_MS + 600_000

    _insert_fact(
        conn,
        fact_snapshot_id=public_fact_id,
        row=row,
        fact_surface="pretrade_public",
        source_ref="unit:public",
        fact_values={
            "opening_range_defined": True,
            "breakout_confirmed": True,
            "opening_range_low_reference": "1800",
        },
        observed_at_ms=NOW_MS - 10_000,
        valid_until_ms=expires_at_ms,
    )
    _insert_fact(
        conn,
        fact_snapshot_id=action_time_fact_id,
        row=row,
        fact_surface="action_time",
        source_ref="unit:action-time",
        fact_values={
            "opening_range_defined": True,
            "breakout_confirmed": True,
            "opening_range_low_reference": "1800",
        },
        observed_at_ms=NOW_MS - 5_000,
        valid_until_ms=expires_at_ms,
    )
    _insert_fact(
        conn,
        fact_snapshot_id=account_safe_fact_id,
        row=row,
        fact_surface="account_safe",
        source_ref="unit:account-safe",
        fact_values={"account_safe": True, "open_orders_clear": True},
        observed_at_ms=NOW_MS - 4_000,
        valid_until_ms=expires_at_ms,
    )
    _insert_fact(
        conn,
        fact_snapshot_id=account_mode_fact_id,
        row=row,
        fact_surface="account_mode",
        source_ref="unit:account-mode",
        fact_values={"account_mode": "one_way", "position_mode_safe": True},
        observed_at_ms=NOW_MS - 3_000,
        valid_until_ms=expires_at_ms,
    )
    conn.execute(
        text(
            """
            INSERT INTO brc_live_signal_events (
              signal_event_id, candidate_scope_id, event_spec_id, strategy_group_id,
              symbol, side, detector_key, signal_type, status, freshness_state,
              confidence, fact_snapshot_id, reason_codes, signal_payload,
              observed_at_ms, expires_at_ms, invalidated_at_ms, created_at_ms
            ) VALUES (
              :signal_event_id, :candidate_scope_id, :event_spec_id, :strategy_group_id,
              :symbol, :side, 'detector:SOR-001:long', 'SOR-LONG',
              'facts_validated', 'fresh', 0.9, :fact_snapshot_id, :reason_codes,
              :signal_payload, :observed_at_ms, :expires_at_ms, NULL, :created_at_ms
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
            "fact_snapshot_id": public_fact_id,
            "reason_codes": _json(["unit_fresh_signal"]),
            "signal_payload": _json({"trigger_candle_close_time_ms": NOW_MS - 60_000}),
            "observed_at_ms": NOW_MS - 60_000,
            "expires_at_ms": expires_at_ms,
            "created_at_ms": NOW_MS - 60_000,
        },
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
              'ready', 'running', 'fresh', 'satisfied', 'facts_validated', 'fresh',
              'acceptable', 'live_submit_allowed', 'action_time_lane',
              'action_time_preflight_ready', 'unit fresh action-time path ready',
              'materialize_action_time_ticket', 'ticket_created_or_lane_expires',
              :evidence_ref, 'unit', :computed_at_ms, :valid_until_ms
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
            "computed_at_ms": NOW_MS - 2_000,
            "valid_until_ms": expires_at_ms,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO brc_promotion_candidates (
              promotion_candidate_id, signal_event_id, readiness_row_id,
              strategy_group_id, symbol, side, promotion_scope, status, scope_state,
              risk_state, facts_snapshot_id, blockers, arbitration_rank, created_at_ms,
              expires_at_ms, closed_at_ms, authority_boundary
            ) VALUES (
              :promotion_candidate_id, :signal_event_id, :readiness_row_id,
              :strategy_group_id, :symbol, :side, 'live_submit', 'arbitration_won',
              'live_submit_allowed', 'acceptable', :facts_snapshot_id, :blockers,
              1, :created_at_ms, :expires_at_ms, NULL, :authority_boundary
            )
            """
        ),
        {
            "promotion_candidate_id": promotion_candidate_id,
            "signal_event_id": signal_event_id,
            "readiness_row_id": readiness_row_id,
            "strategy_group_id": row["strategy_group_id"],
            "symbol": row["symbol"],
            "side": row["side"],
            "facts_snapshot_id": public_fact_id,
            "blockers": _json([]),
            "created_at_ms": NOW_MS - 1_000,
            "expires_at_ms": expires_at_ms,
            "authority_boundary": "promotion_only; no_finalgate_no_operation_layer_no_exchange_write",
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO brc_action_time_lane_inputs (
              action_time_lane_input_id, promotion_candidate_id, strategy_group_id,
              symbol, side, runtime_profile_id, lane_scope, status, signal_event_id,
              public_fact_snapshot_id, action_time_fact_snapshot_id,
              runtime_scope_binding_id, candidate_authorization_ref,
              runtime_safety_snapshot_id, first_blocker_class, created_at_ms,
              expires_at_ms, closed_at_ms, authority_boundary
            ) VALUES (
              :lane_id, :promotion_candidate_id, :strategy_group_id, :symbol, :side,
              :runtime_profile_id, 'real_submit_candidate', 'ticket_pending',
              :signal_event_id, :public_fact_snapshot_id, :action_time_fact_snapshot_id,
              :runtime_scope_binding_id, :candidate_authorization_ref, NULL,
              'action_time_preflight_ready', :created_at_ms, :expires_at_ms, NULL,
              :authority_boundary
            )
            """
        ),
        {
            "lane_id": lane_id,
            "promotion_candidate_id": promotion_candidate_id,
            "strategy_group_id": row["strategy_group_id"],
            "symbol": row["symbol"],
            "side": row["side"],
            "runtime_profile_id": row["runtime_profile_id"],
            "signal_event_id": signal_event_id,
            "public_fact_snapshot_id": public_fact_id,
            "action_time_fact_snapshot_id": action_time_fact_id,
            "runtime_scope_binding_id": row["runtime_scope_binding_id"],
            "candidate_authorization_ref": candidate_authorization_ref,
            "created_at_ms": NOW_MS - 500,
            "expires_at_ms": expires_at_ms,
            "authority_boundary": "real_submit_candidate_identity_only; no_finalgate_no_operation_layer_no_exchange_write",
        },
    )
    if insert_budget:
        conn.execute(
            text(
                """
                INSERT INTO brc_budget_reservations (
                  budget_reservation_id, promotion_candidate_id, action_time_lane_input_id,
                  ticket_id, signal_event_id, event_spec_id, runtime_profile_id, account_id,
                  strategy_group_id, symbol, side, target_notional, leverage,
                  reserved_margin, reserved_at_ms, expires_at_ms, status, release_reason,
                  policy_version
                ) VALUES (
                  'budget:SOR-001:ETHUSDT:long:unit', :promotion_candidate_id, :lane_id,
                  NULL, :signal_event_id, :event_spec_id, :runtime_profile_id,
                  'owner-subaccount-runtime-v0', :strategy_group_id, :symbol, :side,
                  20, 2, 10, :reserved_at_ms, :expires_at_ms, 'active', NULL,
                  'owner-policy-v1'
                )
                """
            ),
            {
                "promotion_candidate_id": promotion_candidate_id,
                "lane_id": lane_id,
                "signal_event_id": signal_event_id,
                "event_spec_id": row["event_spec_id"],
                "runtime_profile_id": row["runtime_profile_id"],
                "strategy_group_id": row["strategy_group_id"],
                "symbol": row["symbol"],
                "side": row["side"],
                "reserved_at_ms": NOW_MS - 400,
                "expires_at_ms": expires_at_ms,
            },
        )
    if insert_protection:
        conn.execute(
            text(
                """
                INSERT INTO brc_protection_references (
                  protection_ref_id, event_spec_id, strategy_group_id, symbol, side,
                  reference_type, reference_price, invalidation_condition,
                  stop_order_type, stop_time_in_force, protection_policy_version,
                  source_fact_snapshot_id, expires_at_ms
                ) VALUES (
                  'protection:SOR-001:ETHUSDT:long:unit', :event_spec_id,
                  :strategy_group_id, :symbol, :side, :reference_type, 1800,
                  'breakout invalidated below opening range low', 'stop_market',
                  'GTC', 'protection-v1', :source_fact_snapshot_id, :expires_at_ms
                )
                """
            ),
            {
                "event_spec_id": row["event_spec_id"],
                "strategy_group_id": row["strategy_group_id"],
                "symbol": row["symbol"],
                "side": row["side"],
                "reference_type": row["protection_ref_type"],
                "source_fact_snapshot_id": action_time_fact_id,
                "expires_at_ms": expires_at_ms,
            },
        )
    return lane_id


def _insert_fact(
    conn,
    *,
    fact_snapshot_id: str,
    row,
    fact_surface: str,
    source_ref: str,
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
            "source_ref": source_ref,
            "failed_facts": _json([]),
            "fact_values": _json(fact_values),
            "observed_at_ms": observed_at_ms,
            "valid_until_ms": valid_until_ms,
            "created_at_ms": observed_at_ms,
        },
    )


def _ticket_count(conn) -> int:
    return conn.execute(text("SELECT COUNT(*) FROM brc_action_time_tickets")).scalar_one()


def _json(value) -> str:
    import json

    return json.dumps(value, sort_keys=True)
