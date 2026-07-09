from __future__ import annotations

import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from src.application.action_time import finalgate_preflight as finalgate
from src.application.action_time import operation_layer_handoff as handoff
from src.application.action_time import fact_snapshots as fact_materializer
from src.application.action_time import action_time_ticket as ticket_materializer
from src.application.action_time import promotion_action_time_lane as lane_materializer
from src.application.action_time import protected_submit_attempt as protected_submit
from src.application.action_time import runtime_safety_state as safety_state
from scripts import publish_runtime_control_current_projections as publisher
from scripts import runtime_active_observation_monitor
from src.domain.strategy_family_signal import (
    SignalSide,
    SignalType,
    StrategyFamilySignalOutput,
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
    risk_reservation_migration = _load_module(
        RISK_RESERVATION_MIGRATION_PATH,
        "migration_103_pg_promotion_lane",
    )
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
            old_risk_op = risk_reservation_migration.op
            risk_reservation_migration.op = migration.op
            try:
                risk_reservation_migration.upgrade()
            finally:
                risk_reservation_migration.op = old_risk_op
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


def test_materializes_action_time_facts_projection_lane_and_ticket_from_raw_signal(
    pg_control_connection,
    monkeypatch,
):
    _insert_ready_fresh_signal(
        pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "short",
        insert_action_time_fact=False,
    )
    pg_control_connection.execute(text("DELETE FROM brc_pretrade_readiness_rows"))

    fact_payload = fact_materializer.materialize_action_time_fact_snapshots(
        pg_control_connection,
        now_ms=NOW_MS,
    )
    assert fact_payload["status"] == "action_time_fact_snapshots_materialized"
    assert fact_payload["materialized_count"] == 1
    assert fact_payload["blocked_count"] == 0

    monkeypatch.setattr(publisher.time, "time", lambda: NOW_MS / 1000)
    projection_payload = publisher.publish_runtime_control_current_projections(
        pg_control_connection,
    )
    assert projection_payload["status"] == "current_projections_published"

    readiness = pg_control_connection.execute(
        text(
            """
            SELECT readiness_state, promotion_state, first_blocker_class
            FROM brc_pretrade_readiness_rows
            WHERE strategy_group_id = 'SOR-001'
              AND symbol = 'ETHUSDT'
              AND side = 'short'
            """
        )
    ).mappings().one()
    assert readiness["readiness_state"] == "action_time_lane"
    assert readiness["promotion_state"] == "action_time_lane"
    assert readiness["first_blocker_class"] == "action_time_preflight_ready"

    lane_payload = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS + 1,
    )
    assert lane_payload["status"] == "promotion_action_time_lane_created"
    assert lane_payload["strategy_group_id"] == "SOR-001"
    assert lane_payload["symbol"] == "ETHUSDT"
    assert lane_payload["side"] == "short"

    ticket_payload = ticket_materializer.materialize_action_time_ticket(
        pg_control_connection,
        now_ms=NOW_MS + 2,
    )
    assert ticket_payload["status"] == "action_time_ticket_created"
    assert ticket_payload["action_time_lane_input_id"] == lane_payload["action_time_lane_input_id"]

    finalgate_payload = finalgate.materialize_action_time_finalgate_preflight(
        pg_control_connection,
        ticket_id=str(ticket_payload["ticket_id"]),
        now_ms=NOW_MS + 3,
    )
    assert finalgate_payload["status"] == "finalgate_ready"

    handoff_payload = handoff.materialize_action_time_operation_layer_handoff(
        pg_control_connection,
        ticket_id=str(ticket_payload["ticket_id"]),
        finalgate_pass_id=str(finalgate_payload["finalgate_pass_id"]),
        now_ms=NOW_MS + 4,
    )
    assert handoff_payload["status"] == "operation_layer_handoff_ready"

    safety_payload = safety_state.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=str(ticket_payload["ticket_id"]),
        operation_layer_handoff_id=str(handoff_payload["operation_layer_handoff_id"]),
        now_ms=NOW_MS + 5,
    )
    assert safety_payload["status"] == "runtime_safety_state_ready"
    assert safety_payload["submit_allowed"] is True

    submit_payload = protected_submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=str(ticket_payload["ticket_id"]),
        operation_submit_command_id=str(handoff_payload["operation_submit_command_id"]),
        submit_mode="disabled_smoke",
        now_ms=NOW_MS + 6,
    )
    assert submit_payload["status"] == "disabled_smoke_passed"
    assert submit_payload["exchange_write_called"] is False
    assert submit_payload["order_created"] is False


def test_same_signal_is_not_reopened_after_disabled_smoke_completion(
    pg_control_connection,
) -> None:
    _insert_ready_fresh_signal(pg_control_connection, "SOR-001", "ETHUSDT", "long")
    lane_payload = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS,
    )
    ticket_payload = ticket_materializer.materialize_action_time_ticket(
        pg_control_connection,
        now_ms=NOW_MS + 1,
    )
    finalgate_payload = finalgate.materialize_action_time_finalgate_preflight(
        pg_control_connection,
        ticket_id=str(ticket_payload["ticket_id"]),
        now_ms=NOW_MS + 2,
    )
    handoff_payload = handoff.materialize_action_time_operation_layer_handoff(
        pg_control_connection,
        ticket_id=str(ticket_payload["ticket_id"]),
        finalgate_pass_id=str(finalgate_payload["finalgate_pass_id"]),
        now_ms=NOW_MS + 3,
    )
    safety_payload = safety_state.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=str(ticket_payload["ticket_id"]),
        operation_layer_handoff_id=str(handoff_payload["operation_layer_handoff_id"]),
        now_ms=NOW_MS + 4,
    )
    assert safety_payload["submit_allowed"] is True
    submit_payload = protected_submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=str(ticket_payload["ticket_id"]),
        operation_submit_command_id=str(handoff_payload["operation_submit_command_id"]),
        submit_mode="disabled_smoke",
        now_ms=NOW_MS + 5,
    )
    assert submit_payload["status"] == "disabled_smoke_passed"

    signal_event_id = str(lane_payload["signal_event_id"])
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_action_time_tickets
            SET expires_at_ms = :expired_at_ms
            WHERE ticket_id = :ticket_id
            """
        ),
        {"ticket_id": str(ticket_payload["ticket_id"]), "expired_at_ms": NOW_MS + 10},
    )
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_action_time_lane_inputs
            SET expires_at_ms = :expired_at_ms
            WHERE action_time_lane_input_id = :lane_id
            """
        ),
        {
            "lane_id": str(lane_payload["action_time_lane_input_id"]),
            "expired_at_ms": NOW_MS + 10,
        },
    )
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_live_signal_events
            SET observed_at_ms = :observed_at_ms,
                expires_at_ms = :expires_at_ms
            WHERE signal_event_id = :signal_event_id
            """
        ),
        {
            "signal_event_id": signal_event_id,
            "observed_at_ms": NOW_MS + 20,
            "expires_at_ms": NOW_MS + 600_000,
        },
    )

    reopened = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS + 100,
    )

    assert reopened["status"] == "terminal_action_time_identity_not_reopened"
    assert any(
        blocker.startswith(f"signal_event_already_has_action_time_lane:{signal_event_id}")
        for blocker in reopened["blockers"]
    )
    assert any(
        blocker.startswith(f"signal_event_already_has_action_time_ticket:{signal_event_id}")
        for blocker in reopened["blockers"]
    )
    assert any(
        blocker.startswith(
            f"signal_event_already_has_protected_submit_attempt:{signal_event_id}"
        )
        for blocker in reopened["blockers"]
    )
    assert _count(pg_control_connection, "brc_action_time_lane_inputs") == 1
    assert (
        pg_control_connection.execute(
            text("SELECT COUNT(*) FROM brc_action_time_tickets")
        ).scalar_one()
        == 1
    )
    assert (
        pg_control_connection.execute(
            text("SELECT COUNT(*) FROM brc_ticket_bound_protected_submit_attempts")
        ).scalar_one()
        == 1
    )


@pytest.mark.parametrize(
    ("strategy_group_id", "symbol", "side"),
    [
        ("CPM-RO-001", "ETHUSDT", "long"),
        ("MPG-001", "OPUSDT", "long"),
        ("MI-001", "AVAXUSDT", "long"),
        ("SOR-001", "ETHUSDT", "short"),
        ("BRF2-001", "BTCUSDT", "short"),
    ],
)
def test_all_active_strategygroups_reach_ticket_bound_disabled_smoke_from_raw_signal(
    pg_control_connection,
    monkeypatch,
    strategy_group_id: str,
    symbol: str,
    side: str,
):
    _insert_ready_fresh_signal(
        pg_control_connection,
        strategy_group_id,
        symbol,
        side,
        insert_action_time_fact=False,
    )
    pg_control_connection.execute(text("DELETE FROM brc_pretrade_readiness_rows"))

    fact_payload = fact_materializer.materialize_action_time_fact_snapshots(
        pg_control_connection,
        now_ms=NOW_MS,
    )
    assert fact_payload["status"] == "action_time_fact_snapshots_materialized"
    assert fact_payload["materialized_count"] == 1
    assert fact_payload["blocked_count"] == 0

    monkeypatch.setattr(publisher.time, "time", lambda: NOW_MS / 1000)
    projection_payload = publisher.publish_runtime_control_current_projections(
        pg_control_connection,
    )
    assert projection_payload["status"] == "current_projections_published"

    lane_payload = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS + 1,
    )
    assert lane_payload["status"] == "promotion_action_time_lane_created"
    assert lane_payload["strategy_group_id"] == strategy_group_id
    assert lane_payload["symbol"] == symbol
    assert lane_payload["side"] == side

    ticket_payload = ticket_materializer.materialize_action_time_ticket(
        pg_control_connection,
        now_ms=NOW_MS + 2,
    )
    assert ticket_payload["status"] == "action_time_ticket_created"
    assert ticket_payload["strategy_group_id"] == strategy_group_id
    assert ticket_payload["symbol"] == symbol
    assert ticket_payload["side"] == side

    finalgate_payload = finalgate.materialize_action_time_finalgate_preflight(
        pg_control_connection,
        ticket_id=str(ticket_payload["ticket_id"]),
        now_ms=NOW_MS + 3,
    )
    assert finalgate_payload["status"] == "finalgate_ready"

    handoff_payload = handoff.materialize_action_time_operation_layer_handoff(
        pg_control_connection,
        ticket_id=str(ticket_payload["ticket_id"]),
        finalgate_pass_id=str(finalgate_payload["finalgate_pass_id"]),
        now_ms=NOW_MS + 4,
    )
    assert handoff_payload["status"] == "operation_layer_handoff_ready"

    safety_payload = safety_state.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=str(ticket_payload["ticket_id"]),
        operation_layer_handoff_id=str(handoff_payload["operation_layer_handoff_id"]),
        now_ms=NOW_MS + 5,
    )
    assert safety_payload["status"] == "runtime_safety_state_ready"
    assert safety_payload["submit_allowed"] is True

    submit_payload = protected_submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=str(ticket_payload["ticket_id"]),
        operation_submit_command_id=str(handoff_payload["operation_submit_command_id"]),
        submit_mode="disabled_smoke",
        now_ms=NOW_MS + 6,
    )
    assert submit_payload["status"] == "disabled_smoke_passed"
    assert submit_payload["submit_allowed"] is True
    assert submit_payload["official_operation_layer_submit_called"] is True
    assert submit_payload["exchange_write_called"] is False
    assert submit_payload["order_created"] is False
    assert submit_payload["order_lifecycle_called"] is False


def test_action_time_fact_materializer_blocks_missing_protection_reference(
    pg_control_connection,
):
    _insert_ready_fresh_signal(
        pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "short",
        insert_action_time_fact=False,
        fact_values={
            "opening_range_defined": True,
            "breakdown_confirmed": True,
        },
    )

    fact_payload = fact_materializer.materialize_action_time_fact_snapshots(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert fact_payload["status"] == "action_time_fact_snapshots_blocked"
    assert "required_fact_missing:opening_range_high_reference" in fact_payload["blockers"]
    row = pg_control_connection.execute(
        text(
            """
            SELECT satisfied, failed_facts, blocker_class
            FROM brc_runtime_fact_snapshots
            WHERE fact_surface = 'action_time'
            """
        )
    ).mappings().one()
    assert row["satisfied"] in {False, 0}
    assert "opening_range_high_reference" in json.loads(row["failed_facts"])
    assert row["blocker_class"] == "computed_not_satisfied"


def test_action_time_fact_materializer_blocks_missing_required_facts_contract(
    pg_control_connection,
):
    _insert_ready_fresh_signal(
        pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "short",
        insert_action_time_fact=False,
    )
    row = _candidate_runtime_row(pg_control_connection, "SOR-001", "ETHUSDT", "short")
    pg_control_connection.execute(
        text(
            """
            DELETE FROM brc_strategy_event_required_facts
            WHERE event_spec_id = :event_spec_id
            """
        ),
        {"event_spec_id": row["event_spec_id"]},
    )

    fact_payload = fact_materializer.materialize_action_time_fact_snapshots(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert fact_payload["status"] == "action_time_fact_snapshots_blocked"
    assert "required_facts_missing" in fact_payload["blockers"]
    action_time_fact = pg_control_connection.execute(
        text(
            """
            SELECT satisfied, blocker_class
            FROM brc_runtime_fact_snapshots
            WHERE fact_surface = 'action_time'
            """
        )
    ).mappings().one()
    assert action_time_fact["satisfied"] in {False, 0}
    assert action_time_fact["blocker_class"] == "computed_not_satisfied"


def test_writer_repository_to_protected_submit_disabled_smoke_end_to_end(
    pg_control_connection,
    monkeypatch,
):
    _insert_ready_fresh_signal(
        pg_control_connection,
        "MPG-001",
        "OPUSDT",
        "long",
        insert_signal=False,
    )

    class _FakeClient:
        def request_json(self, method, path, *, query=None, body=None):
            return {
                "http_status": 200,
                "body": [
                    {
                        "runtime_instance_id": "runtime:MPG-001:OPUSDT:long",
                        "strategy_family_id": "MPG-001",
                        "strategy_family_version_id": "sgv:MPG-001:v1",
                        "symbol": "OPUSDT",
                        "side": "long",
                        "status": "active",
                    }
                ],
            }

    def _args(**overrides):
        values = {
            "env_file": None,
            "api_base": "http://unit",
            "source": "live_market",
            "include_exchange": False,
            "allow_prepare_records": False,
            "runtime_instance_id": [],
            "strategy_family_id": [],
            "database_url": "sqlite://unit",
            "allow_non_postgres_for_test": True,
            "max_runtimes": 100,
            "max_cycles_per_runtime": 1,
            "interval_seconds": 0.0,
            "continue_on_blocked": False,
            "one_hour_limit": 25,
            "four_hour_limit": 25,
            "timeout_seconds": 10.0,
            "playbook_id": None,
            "include_runtime_artifacts": False,
            "owner_operator_id": "owner",
            "owner_confirmation_reference": "owner-authorized-unit",
            "reason": "unit test",
        }
        values.update(overrides)
        return type("Args", (), values)()

    def _candidate_universe(*, database_url, allow_non_postgres_for_test):
        return {}, {
            "source": "pg_runtime_control_state:candidate_scope",
            "loaded": False,
            "strategy_group_count": 0,
            "side_scope": {},
        }

    def _runtime_artifact_builder(args):
        trigger_candle_open_time_ms = NOW_MS - 3_630_000
        trigger_candle_close_time_ms = NOW_MS - 30_000
        output = StrategyFamilySignalOutput(
            signal_id="signal:MPG-001:OPUSDT:long:unit",
            evaluation_id="eval:MPG-001:OPUSDT:long:unit",
            strategy_family_id="MPG-001",
            strategy_family_version_id="sgv:MPG-001:v1",
            symbol="OPUSDT",
            timestamp_ms=trigger_candle_close_time_ms,
            trigger_candle_close_time_ms=trigger_candle_close_time_ms,
            timeframe="1h",
            signal_type=SignalType.WOULD_ENTER,
            side=SignalSide.LONG,
            confidence=Decimal("0.82"),
            reason_codes=["writer_repository_lane_contract"],
            human_summary="MPG unit would enter long.",
            evidence_payload={
                "trigger_candle_open_time_ms": trigger_candle_open_time_ms,
                "trigger_candle_close_time_ms": trigger_candle_close_time_ms,
            },
        ).model_dump(mode="json")
        return {
            "status": "waiting_for_signal",
            "blockers": [],
            "warnings": [],
            "latest_artifact": {
                "observation_payload": {
                    "signal_artifact": {
                        "evaluation_result": {
                            "status": "observe_only",
                            "evaluator_id": "MPG001UnitEvaluator",
                            "can_call_semantic_binding": True,
                            "semantics_binding_found": True,
                            "strategy_candidate_mode": "shadow_order_candidate_allowed",
                            "output": output,
                        }
                    }
                }
            },
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
            },
        }

    monkeypatch.setattr(
        runtime_active_observation_monitor,
        "_read_candidate_universe_from_pg",
        _candidate_universe,
    )
    monitor_payload = runtime_active_observation_monitor._build_monitor_artifact(
        _args(),
        client=_FakeClient(),
        runtime_artifact_builder=_runtime_artifact_builder,
    )
    signal_summary = monitor_payload["runtime_summaries"][0]["signal_summary"]
    assert signal_summary["trigger_candle_close_time_ms"] == NOW_MS - 30_000

    write_payload = runtime_active_observation_monitor.write_runtime_signal_summaries_to_pg(
        monitor_payload,
        database_url="unused://pg-control-test",
        allow_non_postgres_for_test=True,
        now_ms=NOW_MS,
        conn=pg_control_connection,
    )

    assert write_payload["status"] == "pg_live_signal_events_written"
    signal_event = pg_control_connection.execute(
        text(
            """
            SELECT event_time_ms, trigger_candle_close_time_ms
            FROM brc_live_signal_events
            """
        )
    ).mappings().one()
    assert signal_event["event_time_ms"] == NOW_MS - 30_000
    assert signal_event["trigger_candle_close_time_ms"] == NOW_MS - 30_000
    assert signal_event["event_time_ms"] != NOW_MS - 3_630_000

    payload = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert payload["status"] == "promotion_action_time_lane_created"
    assert payload["strategy_group_id"] == "MPG-001"
    assert payload["symbol"] == "OPUSDT"
    assert payload["side"] == "long"
    lane = pg_control_connection.execute(
        text(
            """
            SELECT status, signal_event_id
            FROM brc_action_time_lane_inputs
            """
        )
    ).mappings().one()
    assert lane["status"] == "ticket_pending"
    assert lane["signal_event_id"] in write_payload["signal_event_ids"]

    ticket_payload = ticket_materializer.materialize_action_time_ticket(
        pg_control_connection,
        now_ms=NOW_MS + 1,
    )
    assert ticket_payload["status"] == "action_time_ticket_created"
    assert ticket_payload["action_time_lane_input_id"] == payload["action_time_lane_input_id"]

    finalgate_payload = finalgate.materialize_action_time_finalgate_preflight(
        pg_control_connection,
        ticket_id=str(ticket_payload["ticket_id"]),
        now_ms=NOW_MS + 2,
    )
    assert finalgate_payload["status"] == "finalgate_ready"

    handoff_payload = handoff.materialize_action_time_operation_layer_handoff(
        pg_control_connection,
        ticket_id=str(ticket_payload["ticket_id"]),
        finalgate_pass_id=str(finalgate_payload["finalgate_pass_id"]),
        now_ms=NOW_MS + 3,
    )
    assert handoff_payload["status"] == "operation_layer_handoff_ready"

    safety_payload = safety_state.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=str(ticket_payload["ticket_id"]),
        operation_layer_handoff_id=str(handoff_payload["operation_layer_handoff_id"]),
        now_ms=NOW_MS + 4,
    )
    assert safety_payload["status"] == "runtime_safety_state_ready"
    assert safety_payload["submit_allowed"] is True

    submit_payload = protected_submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=str(ticket_payload["ticket_id"]),
        operation_submit_command_id=str(handoff_payload["operation_submit_command_id"]),
        submit_mode="disabled_smoke",
        now_ms=NOW_MS + 5,
    )
    assert submit_payload["status"] == "disabled_smoke_passed"
    assert submit_payload["submit_allowed"] is True
    assert submit_payload["official_operation_layer_submit_called"] is True
    assert submit_payload["exchange_write_called"] is False
    assert submit_payload["order_created"] is False
    assert submit_payload["order_lifecycle_called"] is False


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


def test_expired_open_real_lane_is_expired_and_does_not_block_new_lane(
    pg_control_connection,
):
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
    _insert_ready_fresh_signal(pg_control_connection, "MPG-001", "OPUSDT", "long")

    second = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS + 1,
    )

    assert second["status"] == "promotion_action_time_lane_created"
    assert second["action_time_lane_input_id"] != first["action_time_lane_input_id"]
    statuses = {
        row["action_time_lane_input_id"]: row["status"]
        for row in pg_control_connection.execute(
            text(
                """
                SELECT action_time_lane_input_id, status
                FROM brc_action_time_lane_inputs
                """
            )
        ).mappings()
    }
    assert statuses[first["action_time_lane_input_id"]] == "expired"
    assert statuses[second["action_time_lane_input_id"]] == "ticket_pending"
    transition = pg_control_connection.execute(
        text(
            """
            SELECT state_table, entity_id, from_status, to_status, transition_reason,
                   writer
            FROM brc_state_transition_events
            WHERE entity_id = :lane_id
            """
        ),
        {"lane_id": first["action_time_lane_input_id"]},
    ).mappings().one()
    assert transition["state_table"] == "brc_action_time_lane_inputs"
    assert transition["from_status"] == "ticket_pending"
    assert transition["to_status"] == "expired"
    assert transition["transition_reason"] == (
        "action_time_lane_expired_before_materialization"
    )
    assert transition["writer"] == "materialize_pg_promotion_action_time_lane"
    assert _count(pg_control_connection, "brc_action_time_lane_inputs") == 2


def test_terminal_attempt_identity_is_not_reopened_for_same_observation(
    pg_control_connection,
):
    _insert_ready_fresh_signal(pg_control_connection, "SOR-001", "ETHUSDT", "long")
    first = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS,
    )
    _expire_promotion_and_lane(
        pg_control_connection,
        promotion_id=first["promotion_candidate_id"],
        lane_id=first["action_time_lane_input_id"],
    )

    second = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS + 2,
    )

    assert second["status"] == "terminal_action_time_identity_not_reopened"
    assert (
        "terminal_promotion_identity_reuse:" + first["promotion_candidate_id"]
        in second["blockers"]
    )
    assert (
        "terminal_action_time_lane_identity_reuse:"
        + first["action_time_lane_input_id"]
        in second["blockers"]
    )


def test_same_signal_observation_update_does_not_reopen_after_expiry(
    pg_control_connection,
):
    _insert_ready_fresh_signal(pg_control_connection, "SOR-001", "ETHUSDT", "long")
    first = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS,
    )
    _expire_promotion_and_lane(
        pg_control_connection,
        promotion_id=first["promotion_candidate_id"],
        lane_id=first["action_time_lane_input_id"],
    )
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_live_signal_events
            SET observed_at_ms = :observed_at_ms,
                expires_at_ms = :expires_at_ms
            WHERE signal_event_id = :signal_event_id
            """
        ),
        {
            "observed_at_ms": NOW_MS + 1,
            "expires_at_ms": NOW_MS + 600_000,
            "signal_event_id": first["signal_event_id"],
        },
    )

    second = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS + 2,
    )

    assert second["status"] == "terminal_action_time_identity_not_reopened"
    assert any(
        blocker.startswith(
            "signal_event_already_has_action_time_lane:" + first["signal_event_id"]
        )
        for blocker in second["blockers"]
    )
    statuses = {
        row["action_time_lane_input_id"]: row["status"]
        for row in pg_control_connection.execute(
            text(
                """
                SELECT action_time_lane_input_id, status
                FROM brc_action_time_lane_inputs
                """
            )
        ).mappings()
    }
    assert statuses[first["action_time_lane_input_id"]] == "expired"
    assert len(statuses) == 1


def test_new_signal_event_id_creates_new_attempt_identity_after_expiry(
    pg_control_connection,
):
    _insert_ready_fresh_signal(pg_control_connection, "SOR-001", "ETHUSDT", "long")
    first = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS,
    )
    _expire_promotion_and_lane(
        pg_control_connection,
        promotion_id=first["promotion_candidate_id"],
        lane_id=first["action_time_lane_input_id"],
    )
    row = _candidate_runtime_row(pg_control_connection, "SOR-001", "ETHUSDT", "long")
    _insert_signal(
        pg_control_connection,
        row,
        public_fact_id="fact:SOR-001:ETHUSDT:long:unit:public",
        signal_event_id="signal:SOR-001:ETHUSDT:long:unit:next-event",
        created_at_ms=NOW_MS + 1,
        event_time_ms=NOW_MS - 30_000,
    )
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_live_signal_events
            SET observed_at_ms = :observed_at_ms,
                expires_at_ms = :expires_at_ms
            WHERE signal_event_id = :signal_event_id
            """
        ),
        {
            "observed_at_ms": NOW_MS + 1,
            "expires_at_ms": NOW_MS + 600_000,
            "signal_event_id": "signal:SOR-001:ETHUSDT:long:unit:next-event",
        },
    )

    second = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS + 2,
    )

    assert second["status"] == "promotion_action_time_lane_created"
    assert second["signal_event_id"] == "signal:SOR-001:ETHUSDT:long:unit:next-event"
    assert second["promotion_candidate_id"] != first["promotion_candidate_id"]
    assert second["action_time_lane_input_id"] != first["action_time_lane_input_id"]
    statuses = {
        row["action_time_lane_input_id"]: row["status"]
        for row in pg_control_connection.execute(
            text(
                """
                SELECT action_time_lane_input_id, status
                FROM brc_action_time_lane_inputs
                """
            )
        ).mappings()
    }
    assert statuses[first["action_time_lane_input_id"]] == "expired"
    assert statuses[second["action_time_lane_input_id"]] == "ticket_pending"


def test_ticket_created_lane_with_current_ticket_is_not_expired(
    pg_control_connection,
):
    _insert_ready_fresh_signal(pg_control_connection, "SOR-001", "ETHUSDT", "long")
    lane_payload = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS,
    )
    ticket_payload = ticket_materializer.materialize_action_time_ticket(
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
            "lane_id": lane_payload["action_time_lane_input_id"],
        },
    )

    transitioned = lane_materializer._expire_stale_open_real_lanes(
        pg_control_connection,
        now_ms=NOW_MS + 1,
    )

    lane = pg_control_connection.execute(
        text(
            """
            SELECT status, closed_at_ms
            FROM brc_action_time_lane_inputs
            WHERE action_time_lane_input_id = :lane_id
            """
        ),
        {"lane_id": lane_payload["action_time_lane_input_id"]},
    ).mappings().one()
    transition_count = pg_control_connection.execute(
        text(
            """
            SELECT COUNT(*)
            FROM brc_state_transition_events
            WHERE entity_id = :lane_id
            """
        ),
        {"lane_id": lane_payload["action_time_lane_input_id"]},
    ).scalar_one()
    assert ticket_payload["status"] == "action_time_ticket_created"
    assert transitioned == 0
    assert lane["status"] == "ticket_created"
    assert lane["closed_at_ms"] is None
    assert transition_count == 0


def test_ticket_created_lane_with_expired_ticket_is_closed_with_transition(
    pg_control_connection,
):
    _insert_ready_fresh_signal(pg_control_connection, "SOR-001", "ETHUSDT", "long")
    lane_payload = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS,
    )
    ticket_payload = ticket_materializer.materialize_action_time_ticket(
        pg_control_connection,
        now_ms=NOW_MS,
    )
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_action_time_lane_inputs
            SET expires_at_ms = :expired_at_ms
            WHERE action_time_lane_input_id = :lane_id
            """
        ),
        {
            "expired_at_ms": NOW_MS - 1,
            "lane_id": lane_payload["action_time_lane_input_id"],
        },
    )
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_action_time_tickets
            SET expires_at_ms = :expired_at_ms
            WHERE ticket_id = :ticket_id
            """
        ),
        {
            "expired_at_ms": NOW_MS - 1,
            "ticket_id": ticket_payload["ticket_id"],
        },
    )

    transitioned = lane_materializer._expire_stale_open_real_lanes(
        pg_control_connection,
        now_ms=NOW_MS + 1,
    )

    lane = pg_control_connection.execute(
        text(
            """
            SELECT status, closed_at_ms
            FROM brc_action_time_lane_inputs
            WHERE action_time_lane_input_id = :lane_id
            """
        ),
        {"lane_id": lane_payload["action_time_lane_input_id"]},
    ).mappings().one()
    transition = pg_control_connection.execute(
        text(
            """
            SELECT from_status, to_status, transition_reason
            FROM brc_state_transition_events
            WHERE entity_id = :lane_id
            """
        ),
        {"lane_id": lane_payload["action_time_lane_input_id"]},
    ).mappings().one()
    assert transitioned == 1
    assert lane["status"] == "closed"
    assert lane["closed_at_ms"] == NOW_MS + 1
    assert transition["from_status"] == "ticket_created"
    assert transition["to_status"] == "closed"
    assert transition["transition_reason"] == (
        "ticket_created_lane_closed_after_ticket_non_current"
    )


def test_expired_open_promotion_is_closed_with_transition(pg_control_connection):
    _insert_ready_fresh_signal(pg_control_connection, "SOR-001", "ETHUSDT", "long")
    payload = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS,
    )
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_promotion_candidates
            SET expires_at_ms = :expired_at_ms,
                closed_at_ms = NULL,
                status = 'arbitration_won'
            WHERE promotion_candidate_id = :promotion_id
            """
        ),
        {
            "expired_at_ms": NOW_MS - 1,
            "promotion_id": payload["promotion_candidate_id"],
        },
    )

    transitioned = lane_materializer._expire_stale_open_promotions(
        pg_control_connection,
        now_ms=NOW_MS + 1,
    )

    promotion = pg_control_connection.execute(
        text(
            """
            SELECT status, closed_at_ms
            FROM brc_promotion_candidates
            WHERE promotion_candidate_id = :promotion_id
            """
        ),
        {"promotion_id": payload["promotion_candidate_id"]},
    ).mappings().one()
    transition = pg_control_connection.execute(
        text(
            """
            SELECT from_status, to_status, transition_reason
            FROM brc_state_transition_events
            WHERE entity_id = :promotion_id
            """
        ),
        {"promotion_id": payload["promotion_candidate_id"]},
    ).mappings().one()
    assert transitioned == 1
    assert promotion["status"] == "expired"
    assert promotion["closed_at_ms"] == NOW_MS + 1
    assert transition["from_status"] == "arbitration_won"
    assert transition["to_status"] == "expired"
    assert transition["transition_reason"] == (
        "promotion_candidate_expired_before_action_time_lane"
    )


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
    insert_signal: bool = True,
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
        source_kind="live_market",
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
            "action_time_available_balance": True,
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
    if insert_signal:
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


def _expire_promotion_and_lane(
    conn,
    *,
    promotion_id: str,
    lane_id: str,
) -> None:
    conn.execute(
        text(
            """
            UPDATE brc_promotion_candidates
            SET status = 'expired',
                expires_at_ms = :expired_at_ms,
                closed_at_ms = :closed_at_ms
            WHERE promotion_candidate_id = :promotion_id
            """
        ),
        {
            "promotion_id": promotion_id,
            "expired_at_ms": NOW_MS - 1,
            "closed_at_ms": NOW_MS + 1,
        },
    )
    conn.execute(
        text(
            """
            UPDATE brc_action_time_lane_inputs
            SET status = 'expired',
                expires_at_ms = :expired_at_ms,
                closed_at_ms = :closed_at_ms
            WHERE action_time_lane_input_id = :lane_id
            """
        ),
        {
            "lane_id": lane_id,
            "expired_at_ms": NOW_MS - 1,
            "closed_at_ms": NOW_MS + 1,
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
    event_time_ms: int = NOW_MS - 60_000,
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
                    "trigger_candle_close_time_ms": event_time_ms,
                }
            ),
            "event_time_ms": event_time_ms,
            "trigger_candle_close_time_ms": event_time_ms,
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
    source_kind: str = "unit_test",
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
              :fact_surface, :source_kind, :source_ref, true, true, 'fresh',
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
            "source_kind": source_kind,
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
    result["last_price"] = "2000"
    result["take_profit_1"] = "2200" if row["side"] == "long" else "1600"
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
