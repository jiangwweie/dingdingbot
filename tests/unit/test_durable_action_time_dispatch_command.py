from __future__ import annotations

import sqlalchemy as sa

from scripts import run_action_time_dispatch_command_once as dispatch_worker
from src.application.action_time.durable_dispatch_command import (
    claim_next_action_time_dispatch_command,
    complete_claimed_action_time_dispatch_command,
    materialize_action_time_dispatch_command,
)


NOW_MS = 1_770_000_000_000


def test_dispatch_command_is_idempotent_and_claimed_once_then_prepared():
    engine = sa.create_engine("sqlite://")
    _create_table(engine)
    try:
        with engine.begin() as conn:
            first = materialize_action_time_dispatch_command(
                conn,
                action_time_invocation_id="invocation:one",
                ticket_id="ticket:one",
                operation_layer_handoff_id="handoff:one",
                runtime_safety_snapshot=_ready_safety(),
                now_ms=NOW_MS,
            )
            replay = materialize_action_time_dispatch_command(
                conn,
                action_time_invocation_id="invocation:one",
                ticket_id="ticket:one",
                operation_layer_handoff_id="handoff:one",
                runtime_safety_snapshot=_ready_safety(),
                now_ms=NOW_MS + 1,
            )
            claim = claim_next_action_time_dispatch_command(
                conn,
                worker_id="worker:a",
                now_ms=NOW_MS + 2,
            )
            second_claim = claim_next_action_time_dispatch_command(
                conn,
                worker_id="worker:b",
                now_ms=NOW_MS + 3,
            )
            completed = complete_claimed_action_time_dispatch_command(
                conn,
                dispatch_command_id=str(claim["dispatch_command_id"]),
                claim_token=str(claim["claim_token"]),
                protected_submit_attempt_id="attempt:one",
                now_ms=NOW_MS + 4,
            )
    finally:
        engine.dispose()

    assert first["status"] == "materialized"
    assert replay["status"] == "already_materialized"
    assert replay["dispatch_command_id"] == first["dispatch_command_id"]
    assert claim["status"] == "claimed"
    assert second_claim["status"] == "no_pending_command"
    assert completed["status"] == "submit_prepared"
    assert completed["protected_submit_attempt_id"] == "attempt:one"


def test_expired_claim_is_reclaimable_without_reselecting_ticket():
    engine = sa.create_engine("sqlite://")
    _create_table(engine)
    try:
        with engine.begin() as conn:
            materialize_action_time_dispatch_command(
                conn,
                action_time_invocation_id="invocation:one",
                ticket_id="ticket:one",
                operation_layer_handoff_id="handoff:one",
                runtime_safety_snapshot=_ready_safety(),
                now_ms=NOW_MS,
            )
            first = claim_next_action_time_dispatch_command(
                conn,
                worker_id="worker:a",
                now_ms=NOW_MS + 1,
                lease_ms=10,
            )
            second = claim_next_action_time_dispatch_command(
                conn,
                worker_id="worker:b",
                now_ms=NOW_MS + 11,
                lease_ms=10,
            )
    finally:
        engine.dispose()

    assert first["status"] == "claimed"
    assert second["status"] == "claimed"
    assert second["dispatch_command_id"] == first["dispatch_command_id"]
    assert second["claim_token"] != first["claim_token"]


def test_typed_dispatch_worker_prepares_attempt_without_http_or_exchange(monkeypatch):
    engine = sa.create_engine("sqlite://")
    _create_table(engine)
    calls: list[str] = []
    try:
        with engine.begin() as conn:
            materialize_action_time_dispatch_command(
                conn,
                action_time_invocation_id="invocation:one",
                ticket_id="ticket:one",
                operation_layer_handoff_id="handoff:one",
                runtime_safety_snapshot=_ready_safety(),
                now_ms=NOW_MS,
            )

        def decision(*_args, **_kwargs):
            calls.append("decision")
            return {"decision": "real_gateway_action"}

        def attempt(*_args, **_kwargs):
            calls.append("attempt")
            return {
                "status": "submit_prepared",
                "protected_submit_attempt_id": "attempt:one",
                "blockers": [],
            }

        monkeypatch.setattr(
            dispatch_worker,
            "materialize_ticket_bound_submit_mode_decision",
            decision,
        )
        monkeypatch.setattr(
            dispatch_worker,
            "prepare_ticket_bound_protected_submit_attempt",
            attempt,
        )
        report = dispatch_worker.run_once(
            engine,
            worker_id="worker:a",
            production_submit_execution_policy="armed",
            now_ms=NOW_MS + 1,
        )
    finally:
        engine.dispose()

    assert report["status"] == "submit_prepared"
    assert report["protected_submit_attempt_id"] == "attempt:one"
    assert report["official_application_port_called"] is True
    assert report["exchange_write_called"] is False
    assert calls == ["decision", "attempt"]


def _ready_safety() -> dict[str, object]:
    return {
        "runtime_safety_snapshot_id": "safety:one",
        "operation_submit_command_id": "submit:one",
        "strategy_group_id": "SOR-001",
        "symbol": "ETHUSDT",
        "side": "long",
        "runtime_profile_id": "profile:one",
        "safety_state": "live_submit_ready",
        "submit_allowed": True,
        "valid_until_ms": NOW_MS + 60_000,
    }


def _create_table(engine: sa.Engine) -> None:
    metadata = sa.MetaData()
    sa.Table(
        "brc_action_time_dispatch_commands",
        metadata,
        sa.Column("dispatch_command_id", sa.String, primary_key=True),
        sa.Column("action_time_invocation_id", sa.String, nullable=False),
        sa.Column("ticket_id", sa.String, nullable=False),
        sa.Column("operation_layer_handoff_id", sa.String, nullable=False),
        sa.Column("operation_submit_command_id", sa.String, nullable=False, unique=True),
        sa.Column("runtime_safety_snapshot_id", sa.String, nullable=False),
        sa.Column("strategy_group_id", sa.String, nullable=False),
        sa.Column("symbol", sa.String, nullable=False),
        sa.Column("side", sa.String, nullable=False),
        sa.Column("runtime_profile_id", sa.String, nullable=False),
        sa.Column("state", sa.String, nullable=False),
        sa.Column("protected_submit_attempt_id", sa.String),
        sa.Column("first_blocker", sa.String),
        sa.Column("claim_owner", sa.String),
        sa.Column("claim_token", sa.String),
        sa.Column("claim_expires_at_ms", sa.BigInteger),
        sa.Column("created_at_ms", sa.BigInteger, nullable=False),
        sa.Column("updated_at_ms", sa.BigInteger, nullable=False),
    )
    metadata.create_all(engine)
