from __future__ import annotations

import json

from sqlalchemy import text

from scripts import materialize_action_time_ticket_sequence as sequence_script
from scripts import publish_runtime_control_current_projections as publisher
from src.application.readmodels import strategy_live_candidate_pool as candidate_pool
from src.application.action_time.ticket_materialization_sequence import (
    materialize_action_time_ticket_sequence,
)
from src.infrastructure.runtime_control_state_repository import (
    PgBackedRuntimeControlStateRepository,
)


def test_sequence_cli_requires_database_url_and_postgres_dsn(
    monkeypatch,
    capsys,
):
    monkeypatch.delenv("PG_DATABASE_URL", raising=False)
    assert sequence_script.main(["--require-database-url"]) == 2
    assert "PG_DATABASE_URL is required" in capsys.readouterr().err

    assert sequence_script.main(["--database-url", "sqlite://"]) == 2
    assert "requires PostgreSQL DSN" in capsys.readouterr().err


def test_sequence_cli_keeps_watcher_healthy_for_persisted_business_blocker(
    monkeypatch,
):
    seen = {}
    class FakeTransaction:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, traceback):
            return False

    class FakeEngine:
        def begin(self):
            return FakeTransaction()

        def dispose(self):
            return None

    monkeypatch.setattr(
        sequence_script.sa,
        "create_engine",
        lambda database_url: FakeEngine(),
    )
    monkeypatch.setattr(
        sequence_script,
        "materialize_action_time_ticket_sequence",
        lambda conn, **kwargs: (
            seen.update({"projection_publisher": kwargs["projection_publisher"]})
            or {
                "status": "action_time_ticket_sequence_rolled_back",
                "process_outcome": {
                    "process_state": "business_blocked",
                    "business_state": "temporarily_unavailable",
                    "first_blocker": "unit_engineering_blocker",
                },
            }
        ),
    )

    assert sequence_script.main(
        ["--database-url", "sqlite://", "--allow-non-postgres-for-test"]
    ) == 0
    assert seen["projection_publisher"] is (
        sequence_script.publish_action_time_pretrade_readiness
    )
from tests.unit.test_pg_promotion_action_time_lane_materialization import (
    NOW_MS,
    _candidate_runtime_row,
    _fact_values,
    _insert_ready_fresh_signal,
    pg_control_connection,
)


def test_sequence_commits_fact_reservation_lane_and_ticket_as_one_unit(
    pg_control_connection,
    monkeypatch,
):
    _insert_ready_fresh_signal(
        pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
    )

    monkeypatch.setattr(publisher.time, "time", lambda: NOW_MS / 1000)
    payload = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS,
        projection_publisher=publisher.publish_action_time_pretrade_readiness,
        completion_clock_ms=lambda: NOW_MS + 1,
    )

    assert payload["status"] == "action_time_ticket_sequence_committed"
    assert payload["projection"]["status"] == (
        "action_time_pretrade_readiness_published"
    )
    assert payload["ticket"]["status"] == "action_time_ticket_created"
    assert _count(
        pg_control_connection,
        "brc_runtime_fact_snapshots",
        "fact_surface = 'action_time'",
    ) == 1
    assert _count(pg_control_connection, "brc_promotion_candidates") == 1
    assert _count(pg_control_connection, "brc_budget_reservations") == 1
    assert _count(pg_control_connection, "brc_action_time_lane_inputs") == 1
    assert _count(pg_control_connection, "brc_action_time_tickets") == 1
    budget = pg_control_connection.execute(
        text(
            """
            SELECT status, ticket_id, intended_qty, risk_at_stop
            FROM brc_budget_reservations
            """
        )
    ).mappings().one()
    assert budget["status"] == "consumed"
    assert budget["ticket_id"] == payload["ticket"]["ticket_id"]
    assert float(budget["intended_qty"]) > 0
    assert float(budget["risk_at_stop"]) > 0


def test_sequence_rolls_back_all_action_rows_when_ticket_blocks(
    pg_control_connection,
):
    _insert_ready_fresh_signal(
        pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
    )

    payload = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS,
        projection_publisher=_projection_ready,
        ticket_materializer=lambda conn, now_ms: {
            "status": "blocked",
            "blockers": ["unit_ticket_blocker"],
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
        },
        completion_clock_ms=lambda: NOW_MS + 1,
    )

    assert payload["status"] == "action_time_ticket_sequence_rolled_back"
    assert payload["blockers"] == ["unit_ticket_blocker"]
    assert _count(
        pg_control_connection,
        "brc_runtime_fact_snapshots",
        "fact_surface = 'action_time'",
    ) == 0
    assert _count(pg_control_connection, "brc_promotion_candidates") == 0
    assert _count(pg_control_connection, "brc_budget_reservations") == 0
    assert _count(pg_control_connection, "brc_action_time_lane_inputs") == 0
    assert _count(pg_control_connection, "brc_action_time_tickets") == 0
    outcome = _sequence_outcome(pg_control_connection)
    assert outcome["scope_key"] == "lane:SOR-001:ETHUSDT:long"
    assert outcome["first_blocker"] == "unit_ticket_blocker"
    assert outcome["business_state"] == "temporarily_unavailable"


def test_fresh_signal_can_recertify_and_clear_previous_lane_engineering_blocker(
    pg_control_connection,
    monkeypatch,
):
    _insert_ready_fresh_signal(
        pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
    )
    monkeypatch.setattr(publisher.time, "time", lambda: NOW_MS / 1000)
    blocked = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS,
        projection_publisher=publisher.publish_runtime_control_current_projections,
        ticket_materializer=lambda conn, now_ms: {
            "status": "blocked",
            "blockers": ["unit_repairable_ticket_blocker"],
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
        },
        completion_clock_ms=lambda: NOW_MS + 1,
    )
    assert blocked["status"] == "action_time_ticket_sequence_rolled_back"
    owner_projection = publisher.publish_runtime_control_current_projections(
        pg_control_connection
    )
    assert owner_projection["status"] == "current_projections_published"
    visible_blocker = pg_control_connection.execute(
        text(
            """
            SELECT first_blocker_class, first_blocker_detail
            FROM brc_pretrade_readiness_rows
            WHERE strategy_group_id = 'SOR-001'
              AND symbol = 'ETHUSDT'
              AND side = 'long'
            """
        )
    ).mappings().one()
    assert visible_blocker["first_blocker_class"] == (
        "action_time_boundary_not_reproduced"
    )
    assert "unit_repairable_ticket_blocker" in visible_blocker[
        "first_blocker_detail"
    ]
    control_state = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=NOW_MS + 2,
    ).read_monitor_control_state()
    assert len(control_state["live_signal_events"]) == 1
    assert set(candidate_pool._unresolved_action_time_sequence_outcomes(control_state)) == {
        ("SOR-001", "ETHUSDT", "long")
    }
    monkeypatch.setattr(publisher.time, "time", lambda: (NOW_MS + 2) / 1000)

    repaired = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS + 2,
        projection_publisher=publisher.publish_runtime_control_current_projections,
        completion_clock_ms=lambda: NOW_MS + 3,
    )

    assert repaired["status"] == "action_time_ticket_sequence_committed", repaired
    outcome = _sequence_outcome(pg_control_connection)
    assert outcome["process_state"] == "succeeded"
    assert outcome["first_blocker"] is None


def test_sequence_persists_each_blocked_lane_when_multiple_signals_fail_facts(
    pg_control_connection,
    monkeypatch,
):
    cases = [
        ("CPM-RO-001", "ETHUSDT", "long", "ask_price"),
        ("BRF2-001", "BTCUSDT", "short", "bid_price"),
    ]
    for strategy_group_id, symbol, side, missing_quote in cases:
        row = _candidate_runtime_row(
            pg_control_connection,
            strategy_group_id,
            symbol,
            side,
        )
        values = _fact_values(pg_control_connection, row)
        values.update(
            {
                "public_facts_ready": True,
                "mark_price_fresh": True,
                "spread_ok": True,
                "min_notional_ok": True,
                "qty_step_ok": True,
                "facts": {
                    "mark_price": "100",
                    "bid_price": "99.9",
                    "ask_price": "100.1",
                    "qty_step": "0.001",
                    "min_notional": "5",
                },
            }
        )
        values["facts"][missing_quote] = None
        _insert_ready_fresh_signal(
            pg_control_connection,
            strategy_group_id,
            symbol,
            side,
            insert_action_time_fact=False,
            fact_values=values,
        )

    payload = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS,
        projection_publisher=_projection_ready,
        completion_clock_ms=lambda: NOW_MS + 1,
    )

    assert payload["status"] == "action_time_ticket_sequence_rolled_back"
    outcomes = pg_control_connection.execute(
        text(
            """
            SELECT scope_key, first_blocker
            FROM brc_runtime_process_outcomes
            WHERE process_name = 'action_time_ticket_sequence'
              AND scope_key LIKE 'lane:%'
            ORDER BY scope_key
            """
        )
    ).mappings().all()
    assert {row["scope_key"] for row in outcomes} == {
        "lane:CPM-RO-001:ETHUSDT:long",
        "lane:BRF2-001:BTCUSDT:short",
    }
    assert len(payload["process_outcomes"]) == 2
    monkeypatch.setattr(publisher.time, "time", lambda: NOW_MS / 1000)
    owner_projection = publisher.publish_runtime_control_current_projections(
        pg_control_connection
    )
    assert owner_projection["status"] == "current_projections_published"
    readiness_details = {
        (
            row["strategy_group_id"],
            row["symbol"],
            row["side"],
        ): row["first_blocker_detail"]
        for row in pg_control_connection.execute(
            text(
                """
                SELECT strategy_group_id, symbol, side, first_blocker_detail
                FROM brc_pretrade_readiness_rows
                WHERE strategy_group_id IN ('CPM-RO-001', 'BRF2-001')
                """
            )
        ).mappings()
    }
    assert "action_time_ask_price_invalid" in readiness_details[
        ("CPM-RO-001", "ETHUSDT", "long")
    ]
    assert "action_time_bid_price_invalid" in readiness_details[
        ("BRF2-001", "BTCUSDT", "short")
    ]


def test_sequence_clears_repaired_arbitration_loser_without_opening_second_lane(
    pg_control_connection,
):
    cases = [
        ("CPM-RO-001", "ETHUSDT", "long"),
        ("BRF2-001", "BTCUSDT", "short"),
    ]
    for strategy_group_id, symbol, side in cases:
        _insert_ready_fresh_signal(
            pg_control_connection,
            strategy_group_id,
            symbol,
            side,
            insert_action_time_fact=False,
        )

    payload = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS,
        projection_publisher=_projection_ready,
        completion_clock_ms=lambda: NOW_MS + 1,
    )

    assert payload["status"] == "action_time_ticket_sequence_committed"
    outcomes = {
        row["scope_key"]: row
        for row in payload["process_outcomes"]
        if row["scope_key"].startswith("lane:")
    }
    assert set(outcomes) == {
        "lane:CPM-RO-001:ETHUSDT:long",
        "lane:BRF2-001:BTCUSDT:short",
    }
    assert {row["process_state"] for row in outcomes.values()} == {"succeeded"}
    assert {row["business_state"] for row in outcomes.values()} == {
        "completed",
        "processing",
    }
    assert _count(pg_control_connection, "brc_action_time_lane_inputs") == 1
    assert _count(pg_control_connection, "brc_action_time_tickets") == 1


def test_terminal_promotion_blocker_cannot_be_hidden_by_candidate_success_outcomes(
    pg_control_connection,
):
    terminal_blocker = "terminal_promotion_identity_reuse:promotion-existing"
    candidates = [
        {
            "strategy_group_id": "CPM-RO-001",
            "symbol": "SUIUSDT",
            "side": "long",
            "signal_event_id": "signal-cpm-sui",
            "status": "arbitration_lost",
            "blockers": [],
        },
        {
            "strategy_group_id": "MPG-001",
            "symbol": "SUIUSDT",
            "side": "long",
            "signal_event_id": "signal-mpg-sui",
            "status": "arbitration_lost",
            "blockers": [],
        },
    ]

    payload = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS,
        projection_publisher=_projection_ready,
        fact_materializer=lambda conn, now_ms: {
            "status": "action_time_fact_snapshots_materialized",
            "materialized": candidates,
            "blocked": [],
            "blockers": [],
        },
        promotion_materializer=lambda conn, now_ms: {
            "status": "terminal_action_time_identity_not_reopened",
            "blockers": [terminal_blocker],
            "per_candidate_results": candidates,
        },
        completion_clock_ms=lambda: NOW_MS + 1,
    )

    assert payload["status"] == "action_time_ticket_sequence_rolled_back"
    outcomes = {
        row["scope_key"]: row
        for row in payload["process_outcomes"]
        if row["scope_key"].startswith("lane:")
    }
    assert set(outcomes) == {
        "lane:CPM-RO-001:SUIUSDT:long",
        "lane:MPG-001:SUIUSDT:long",
    }
    assert {row["process_state"] for row in outcomes.values()} == {
        "business_blocked"
    }
    assert {row["business_state"] for row in outcomes.values()} == {
        "temporarily_unavailable"
    }
    assert {row["first_blocker"] for row in outcomes.values()} == {
        terminal_blocker
    }


def test_sequence_rolls_back_when_shortest_ttl_expires_before_commit(
    pg_control_connection,
):
    _insert_ready_fresh_signal(
        pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "short",
        insert_action_time_fact=False,
    )

    payload = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS,
        projection_publisher=_projection_ready,
        completion_clock_ms=lambda: NOW_MS + 600_000,
    )

    assert payload["status"] == "action_time_ticket_sequence_rolled_back"
    assert payload["blockers"] == [
        "action_time_sequence_ttl_expired_before_ticket_commit"
    ]
    assert _count(pg_control_connection, "brc_promotion_candidates") == 0
    assert _count(pg_control_connection, "brc_budget_reservations") == 0
    assert _count(pg_control_connection, "brc_action_time_lane_inputs") == 0
    assert _count(pg_control_connection, "brc_action_time_tickets") == 0
    assert _sequence_outcome(pg_control_connection)["first_blocker"] == (
        "action_time_sequence_ttl_expired_before_ticket_commit"
    )


def test_sequence_exception_outcome_masks_exception_message(
    pg_control_connection,
):
    def fail_with_sensitive_detail(conn, *, now_ms):
        _ = conn, now_ms
        raise RuntimeError("secret-token-must-not-enter-runtime-state")

    payload = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS,
        projection_publisher=_projection_ready,
        fact_materializer=fail_with_sensitive_detail,
        completion_clock_ms=lambda: NOW_MS + 1,
    )

    assert payload["status"] == "action_time_ticket_sequence_rolled_back"
    assert payload["blockers"] == ["action_time_sequence_exception:RuntimeError"]
    assert payload["process_outcome"]["process_state"] == "retryable_failure"
    assert "secret-token" not in json.dumps(payload, default=str)


def test_readiness_projection_failure_is_process_failure_not_business_blocker(
    pg_control_connection,
):
    _insert_ready_fresh_signal(
        pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
    )

    payload = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS,
        projection_publisher=lambda conn: {"status": "unit_projection_failed"},
        completion_clock_ms=lambda: NOW_MS + 1,
    )

    assert payload["status"] == "action_time_ticket_sequence_rolled_back"
    assert payload["blockers"] == [
        "action_time_current_projection_publish_failed"
    ]
    assert payload["process_outcome"]["process_state"] == "retryable_failure"


def test_expired_signal_preserves_unresolved_action_time_engineering_blocker(
    pg_control_connection,
    monkeypatch,
):
    _insert_ready_fresh_signal(
        pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
    )
    blocked = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS,
        projection_publisher=_projection_ready,
        ticket_materializer=lambda conn, now_ms: {
            "status": "blocked",
            "blockers": ["unit_persisted_engineering_blocker"],
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
        },
        completion_clock_ms=lambda: NOW_MS + 1,
    )
    assert blocked["status"] == "action_time_ticket_sequence_rolled_back"
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_live_signal_events
            SET freshness_state = 'expired', expires_at_ms = :expired_at_ms
            """
        ),
        {"expired_at_ms": NOW_MS - 1},
    )

    waiting = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS + 2,
        projection_publisher=_projection_ready,
        completion_clock_ms=lambda: NOW_MS + 3,
    )

    assert waiting["status"] == "no_current_fresh_live_signal"
    outcomes = pg_control_connection.execute(
        text(
            """
            SELECT scope_key, business_state, first_blocker
            FROM brc_runtime_process_outcomes
            WHERE process_name = 'action_time_ticket_sequence'
            ORDER BY scope_key
            """
        )
    ).mappings().all()
    assert [row["scope_key"] for row in outcomes] == [
        "global",
        "lane:SOR-001:ETHUSDT:long",
    ]
    lane_outcome = next(row for row in outcomes if row["scope_key"].startswith("lane:"))
    assert lane_outcome["first_blocker"] == "unit_persisted_engineering_blocker"
    assert lane_outcome["business_state"] == "temporarily_unavailable"

    monkeypatch.setattr(publisher.time, "time", lambda: (NOW_MS + 4) / 1000)
    projection = publisher.publish_runtime_control_current_projections(
        pg_control_connection
    )
    assert projection["status"] == "current_projections_published"
    readiness = pg_control_connection.execute(
        text(
            """
            SELECT first_blocker_class, first_blocker_detail
            FROM brc_pretrade_readiness_rows
            WHERE strategy_group_id = 'SOR-001'
              AND symbol = 'ETHUSDT'
              AND side = 'long'
            """
        )
    ).mappings().one()
    assert readiness["first_blocker_class"] == (
        "action_time_boundary_not_reproduced"
    )
    assert readiness["first_blocker_detail"] == (
        "unit_persisted_engineering_blocker"
    )

    snapshots = pg_control_connection.execute(
        text(
            """
            SELECT model_type, payload
            FROM brc_control_read_model_snapshots
            WHERE model_type IN (
              'candidate_pool', 'daily_live_enablement_table', 'goal_status'
            )
              AND is_current = true
            """
        )
    ).mappings().all()
    assert {row["model_type"] for row in snapshots} == {
        "candidate_pool",
        "daily_live_enablement_table",
        "goal_status",
    }
    for row in snapshots:
        payload = row["payload"]
        while isinstance(payload, str):
            payload = json.loads(payload)
        rendered = json.dumps(payload, sort_keys=True)
        assert "unit_persisted_engineering_blocker" in rendered, row["model_type"]


def test_distinct_same_lane_signal_keeps_blocker_until_new_sequence_succeeds(
    pg_control_connection,
):
    _insert_ready_fresh_signal(
        pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
    )
    old_signal_id = pg_control_connection.execute(
        text(
            """
            SELECT signal_event_id
            FROM brc_live_signal_events
            WHERE strategy_group_id = 'SOR-001'
              AND symbol = 'ETHUSDT'
              AND side = 'long'
            """
        )
    ).scalar_one()
    blocked = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS,
        projection_publisher=_projection_ready,
        ticket_materializer=lambda conn, now_ms: {
            "status": "blocked",
            "blockers": ["unit_signal_a_ticket_failure"],
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
        },
        completion_clock_ms=lambda: NOW_MS + 1,
    )
    assert blocked["status"] == "action_time_ticket_sequence_rolled_back"
    lane_outcome = next(
        row
        for row in blocked["process_outcomes"]
        if row["scope_key"] == "lane:SOR-001:ETHUSDT:long"
    )
    assert lane_outcome["source_watermark"] == old_signal_id

    new_signal_id = f"{old_signal_id}:distinct"
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_live_signal_events (
              signal_event_id, candidate_scope_id, event_spec_id,
              strategy_group_id, symbol, side, detector_key, signal_type,
              source_kind, status, freshness_state, confidence,
              fact_snapshot_id, reason_codes, signal_payload,
              signal_grade, required_execution_mode, execution_eligible,
              authority_source_ref,
              event_time_ms, trigger_candle_close_time_ms, observed_at_ms,
              expires_at_ms, invalidated_at_ms, created_at_ms
            )
            SELECT
              :new_signal_id, candidate_scope_id, event_spec_id,
              strategy_group_id, symbol, side, detector_key, signal_type,
              source_kind, 'facts_validated', 'fresh', confidence,
              fact_snapshot_id, reason_codes, signal_payload,
              signal_grade, required_execution_mode, execution_eligible,
              authority_source_ref,
              :event_time_ms, :event_time_ms, :observed_at_ms,
              :expires_at_ms, NULL, :created_at_ms
            FROM brc_live_signal_events
            WHERE signal_event_id = :old_signal_id
            """
        ),
        {
            "new_signal_id": new_signal_id,
            "old_signal_id": old_signal_id,
            "event_time_ms": NOW_MS + 1_000,
            "observed_at_ms": NOW_MS + 2_000,
            "created_at_ms": NOW_MS + 2_000,
            "expires_at_ms": NOW_MS + 600_000,
        },
    )
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_live_signal_events
            SET status = 'stale',
                freshness_state = 'expired',
                expires_at_ms = :expires_at_ms
            WHERE signal_event_id = :old_signal_id
            """
        ),
        {"old_signal_id": old_signal_id, "expires_at_ms": NOW_MS - 1},
    )

    control_state = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=NOW_MS + 10_000,
    ).read_monitor_control_state()
    unresolved = candidate_pool._unresolved_action_time_sequence_outcomes(
        control_state
    )
    assert unresolved[("SOR-001", "ETHUSDT", "long")]["first_blocker"] == (
        "unit_signal_a_ticket_failure"
    )

    resumed = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS + 10_000,
        projection_publisher=_projection_ready,
        completion_clock_ms=lambda: NOW_MS + 10_001,
    )

    assert resumed["status"] == "action_time_ticket_sequence_committed", resumed[
        "blockers"
    ]
    assert pg_control_connection.execute(
        text(
            """
            SELECT signal_event_id
            FROM brc_action_time_tickets
            WHERE strategy_group_id = 'SOR-001'
              AND symbol = 'ETHUSDT'
              AND side = 'long'
            """
        )
    ).scalar_one() == new_signal_id


def _projection_ready(conn):
    _ = conn
    return {"status": "current_projections_published"}


def _sequence_outcome(conn):
    return conn.execute(
        text(
            """
            SELECT scope_key, process_state, business_state, first_blocker
            FROM brc_runtime_process_outcomes
            WHERE process_name = 'action_time_ticket_sequence'
              AND scope_key LIKE 'lane:%'
            """
        )
    ).mappings().one()


def _count(conn, table_name: str, where: str = "1 = 1") -> int:
    assert table_name in {
        "brc_runtime_fact_snapshots",
        "brc_promotion_candidates",
        "brc_budget_reservations",
        "brc_action_time_lane_inputs",
        "brc_action_time_tickets",
    }
    assert where in {"1 = 1", "fact_surface = 'action_time'"}
    return int(
        conn.execute(
            text(f"SELECT COUNT(*) FROM {table_name} WHERE {where}")
        ).scalar_one()
    )
