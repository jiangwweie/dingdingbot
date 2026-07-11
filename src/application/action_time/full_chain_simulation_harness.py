"""Local full-chain simulation harness for ticket-bound action-time flow.

The harness constructs typed PG rows and runs the L2-L9 materializers without
using repo JSON/MD files and without calling the exchange. It is intended for
local acceptance tests that must expose engineering defects before server
runtime or live market events do.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import asyncio
from contextlib import contextmanager
import json
import os
from types import SimpleNamespace
from typing import Any, Callable

import sqlalchemy as sa

from scripts import runtime_active_observation_monitor

from src.application.action_time import exit_protection_materializer
from src.application.action_time import finalgate_preflight
from src.application.action_time import orphan_protection_cleanup_command
from src.application.action_time import operation_layer_handoff
from src.application.action_time import post_submit_closure
from src.application.action_time import protection_reconciler
from src.application.action_time import protection_recovery_command
from src.application.action_time import protected_submit_attempt
from src.application.action_time import runner_mutation_command
from src.application.action_time import runner_protection_adjuster
from src.application.action_time import runtime_safety_state
from src.application.action_time.lifecycle_maintenance_scheduler import (
    run_ticket_bound_lifecycle_maintenance_scheduler,
)
from src.application.action_time.lifecycle_exchange_command_materializer import (
    materialize_lifecycle_exchange_commands,
)
from src.application.action_time.exchange_command_worker import (
    run_one_ticket_bound_exchange_command,
)
from src.application.action_time.ticket_materialization_sequence import (
    materialize_action_time_ticket_sequence,
)
from src.application.action_time.runtime_pg_fact_snapshots import (
    write_account_safe_fact_snapshots,
    write_pretrade_public_fact_snapshots,
)
from src.application.action_time.ticket_bound_fill_projector import (
    project_ticket_bound_exchange_fills,
)


ACTIVE_CANDIDATE_SCOPES: tuple[tuple[str, str, str], ...] = (
    ("BRF2-001", "BTCUSDT", "short"),
    ("BRF2-001", "AVAXUSDT", "short"),
    ("BRF2-001", "ETHUSDT", "short"),
    ("CPM-RO-001", "ETHUSDT", "long"),
    ("CPM-RO-001", "SOLUSDT", "long"),
    ("CPM-RO-001", "AVAXUSDT", "long"),
    ("CPM-RO-001", "SUIUSDT", "long"),
    ("MI-001", "AVAXUSDT", "long"),
    ("MI-001", "ETHUSDT", "long"),
    ("MI-001", "SOLUSDT", "long"),
    ("MPG-001", "OPUSDT", "long"),
    ("MPG-001", "SOLUSDT", "long"),
    ("MPG-001", "AVAXUSDT", "long"),
    ("MPG-001", "SUIUSDT", "long"),
    ("SOR-001", "ETHUSDT", "long"),
    ("SOR-001", "ETHUSDT", "short"),
    ("SOR-001", "SOLUSDT", "long"),
    ("SOR-001", "SOLUSDT", "short"),
    ("SOR-001", "AVAXUSDT", "long"),
    ("SOR-001", "AVAXUSDT", "short"),
    ("SOR-001", "BTCUSDT", "long"),
    ("SOR-001", "BTCUSDT", "short"),
)

FULL_CHAIN_FAILURE_SCENARIOS: tuple[str, ...] = (
    "entry_accepted_sl_failed",
    "sl_ok_tp1_failed",
    "entry_partial_fill",
    "tp1_filled_runner_missing",
    "old_sl_cancel_failed",
    "runner_submit_failed_before_old_sl_cancel",
    "pg_protected_exchange_missing",
    "flat_position_live_protection_cleanup",
    "duplicate_tp1_fill_idempotent",
)


@dataclass(frozen=True)
class FullChainSimulationInput:
    strategy_group_id: str
    symbol: str
    side: str
    fact_values: dict[str, Any] | None = None
    now_ms: int = 1_770_000_000_000


def run_ticket_bound_full_chain_simulation(
    conn: sa.engine.Connection,
    simulation_input: FullChainSimulationInput,
    *,
    projection_publisher: Callable[[sa.engine.Connection], dict[str, Any]],
) -> dict[str, Any]:
    now_ms = int(simulation_input.now_ms)
    row = _candidate_runtime_row(
        conn,
        strategy_group_id=simulation_input.strategy_group_id,
        symbol=simulation_input.symbol,
        side=simulation_input.side,
    )
    _insert_constructed_raw_input(
        conn,
        row=row,
        fact_values=simulation_input.fact_values or _fact_values(conn, row),
        now_ms=now_ms,
    )

    sequence_payload = materialize_action_time_ticket_sequence(
        conn,
        now_ms=now_ms,
        projection_publisher=projection_publisher,
        completion_clock_ms=lambda: now_ms + 2,
    )
    _require_payload_status(
        stage="atomic_ticket_sequence",
        payload=sequence_payload,
        expected_status="action_time_ticket_sequence_committed",
    )
    fact_payload = sequence_payload["fact"]
    projection_payload = sequence_payload["projection"]
    lane_payload = sequence_payload["promotion"]
    ticket_payload = sequence_payload["ticket"]
    _require_payload_status(
        stage="ticket",
        payload=ticket_payload,
        expected_status="action_time_ticket_created",
    )
    finalgate_payload = finalgate_preflight.materialize_action_time_finalgate_preflight(
        conn,
        ticket_id=str(ticket_payload["ticket_id"]),
        now_ms=now_ms + 3,
    )
    _require_payload_status(
        stage="finalgate",
        payload=finalgate_payload,
        expected_status="finalgate_ready",
    )
    handoff_payload = (
        operation_layer_handoff.materialize_action_time_operation_layer_handoff(
            conn,
            ticket_id=str(ticket_payload["ticket_id"]),
            finalgate_pass_id=str(finalgate_payload["finalgate_pass_id"]),
            now_ms=now_ms + 4,
        )
    )
    _require_payload_status(
        stage="operation_layer_handoff",
        payload=handoff_payload,
        expected_status="operation_layer_handoff_ready",
    )
    safety_payload = runtime_safety_state.materialize_ticket_bound_runtime_safety_state(
        conn,
        ticket_id=str(ticket_payload["ticket_id"]),
        operation_layer_handoff_id=str(handoff_payload["operation_layer_handoff_id"]),
        now_ms=now_ms + 5,
    )
    _require_payload_status(
        stage="runtime_safety",
        payload=safety_payload,
        expected_status="runtime_safety_state_ready",
    )
    with _mock_submit_decision_env():
        submit_mode_decision_payload = (
            protected_submit_attempt.materialize_ticket_bound_submit_mode_decision(
                conn,
                ticket_id=str(ticket_payload["ticket_id"]),
                operation_submit_command_id=str(
                    handoff_payload["operation_submit_command_id"]
                ),
                production_submit_execution_policy="armed",
                now_ms=now_ms + 5,
            )
        )
    prepared_payload = protected_submit_attempt.prepare_ticket_bound_protected_submit_attempt(
        conn,
        ticket_id=str(ticket_payload["ticket_id"]),
        operation_submit_command_id=str(handoff_payload["operation_submit_command_id"]),
        submit_mode="real_gateway_action",
        now_ms=now_ms + 6,
    )
    submitted_payload = protected_submit_attempt.record_ticket_bound_protected_submit_result(
        conn,
        protected_submit_attempt_id=str(prepared_payload["protected_submit_attempt_id"]),
        submit_result=_mock_exchange_submit_result(prepared_payload),
        now_ms=now_ms + 7,
    )
    protection_payload = (
        exit_protection_materializer.materialize_ticket_bound_exit_protection_set(
            conn,
            protected_submit_attempt_id=str(prepared_payload["protected_submit_attempt_id"]),
            now_ms=now_ms + 8,
        )
    )
    post_submit_pending_payload = (
        post_submit_closure.materialize_ticket_bound_post_submit_closure(
            conn,
            protected_submit_attempt_id=str(prepared_payload["protected_submit_attempt_id"]),
            now_ms=now_ms + 9,
        )
    )

    set_id = str(protection_payload["exit_protection_set_id"])
    attempt_id = str(prepared_payload["protected_submit_attempt_id"])
    initial_snapshot = _production_shaped_protection_snapshot(
        conn,
        exit_protection_set_id=set_id,
        final_exit=False,
        now_ms=now_ms + 10,
    )
    initial_scheduler_payload = asyncio.run(
        run_ticket_bound_lifecycle_maintenance_scheduler(
            conn,
            fetch_exchange_snapshot=False,
            allow_exchange_mutation=False,
            provided_exchange_snapshots={
                attempt_id: _provided_snapshot(initial_snapshot),
                set_id: _provided_snapshot(initial_snapshot),
            },
            now_ms=now_ms + 11,
        )
    )
    final_snapshot = _production_shaped_protection_snapshot(
        conn,
        exit_protection_set_id=set_id,
        final_exit=True,
        now_ms=now_ms + 20,
    )
    final_scheduler_payload = asyncio.run(
        run_ticket_bound_lifecycle_maintenance_scheduler(
            conn,
            fetch_exchange_snapshot=False,
            allow_exchange_mutation=False,
            provided_exchange_snapshots={
                attempt_id: _provided_snapshot(final_snapshot),
                set_id: _provided_snapshot(final_snapshot),
            },
            now_ms=now_ms + 21,
        )
    )
    final_payload = dict(
        conn.execute(
            sa.text(
                """
                SELECT * FROM brc_ticket_bound_post_submit_closures
                WHERE protected_submit_attempt_id = :attempt_id
                """
            ),
            {"attempt_id": attempt_id},
        ).mappings().one()
    )

    return {
        "schema": "brc.ticket_bound_full_chain_simulation.v1",
        "strategy_group_id": simulation_input.strategy_group_id,
        "symbol": simulation_input.symbol,
        "side": simulation_input.side,
        "sequence": sequence_payload,
        "fact": fact_payload,
        "projection": projection_payload,
        "lane": lane_payload,
        "ticket": ticket_payload,
        "finalgate": finalgate_payload,
        "handoff": handoff_payload,
        "safety": safety_payload,
        "submit_mode_decision": submit_mode_decision_payload,
        "prepared_submit": prepared_payload,
        "submitted": submitted_payload,
        "protection": protection_payload,
        "post_submit_pending": post_submit_pending_payload,
        "initial_scheduler": initial_scheduler_payload,
        "final_scheduler": final_scheduler_payload,
        "final": final_payload,
        "authority_boundary": {
            "calls_finalgate": True,
            "calls_operation_layer": True,
            "calls_exchange_write": False,
            "uses_mock_exchange_result": True,
            "uses_production_fill_projector": True,
            "uses_production_reconciliation_scheduler": True,
            "uses_repo_json_or_md_authority": False,
        },
    }


def run_ticket_bound_full_chain_failure_scenario(
    conn: sa.engine.Connection,
    simulation_input: FullChainSimulationInput,
    *,
    projection_publisher: Callable[[sa.engine.Connection], dict[str, Any]],
    scenario: str,
) -> dict[str, Any]:
    """Run one constructed full-chain failure scenario without exchange writes."""

    if scenario not in FULL_CHAIN_FAILURE_SCENARIOS:
        raise ValueError(f"unsupported_full_chain_failure_scenario:{scenario}")
    now_ms = int(simulation_input.now_ms)
    context = _prepare_full_chain_submit_context(
        conn,
        simulation_input,
        projection_publisher=projection_publisher,
    )
    prepared = context["prepared_submit"]

    if scenario == "entry_accepted_sl_failed":
        submitted = protected_submit_attempt.record_ticket_bound_protected_submit_result(
            conn,
            protected_submit_attempt_id=str(prepared["protected_submit_attempt_id"]),
            submit_result=_mock_exchange_submit_result_for_roles(
                prepared,
                roles=("ENTRY",),
                status="protection_submit_failed",
                blockers=["exchange_submit_failed:sl"],
            ),
            now_ms=now_ms + 20,
        )
        recovery = protection_recovery_command.prepare_ticket_bound_protection_recovery_command(
            conn,
            protected_submit_attempt_id=str(prepared["protected_submit_attempt_id"]),
            now_ms=now_ms + 21,
        )
        return _failure_result(
            simulation_input,
            scenario=scenario,
            context=context,
            payloads={"submitted": submitted, "recovery_command": recovery},
        )

    if scenario == "sl_ok_tp1_failed":
        submitted = protected_submit_attempt.record_ticket_bound_protected_submit_result(
            conn,
            protected_submit_attempt_id=str(prepared["protected_submit_attempt_id"]),
            submit_result=_mock_exchange_submit_result_for_roles(
                prepared,
                roles=("ENTRY", "SL"),
                status="protection_submit_failed",
                blockers=["exchange_submit_failed:tp1"],
            ),
            now_ms=now_ms + 20,
        )
        recovery = protection_recovery_command.prepare_ticket_bound_protection_recovery_command(
            conn,
            protected_submit_attempt_id=str(prepared["protected_submit_attempt_id"]),
            now_ms=now_ms + 21,
        )
        return _failure_result(
            simulation_input,
            scenario=scenario,
            context=context,
            payloads={"submitted": submitted, "recovery_command": recovery},
        )

    if scenario == "entry_partial_fill":
        submitted = protected_submit_attempt.record_ticket_bound_protected_submit_result(
            conn,
            protected_submit_attempt_id=str(prepared["protected_submit_attempt_id"]),
            submit_result=_mock_exchange_submit_result_for_roles(
                prepared,
                roles=("ENTRY",),
                status="entry_partial_fill",
                blockers=["entry_partial_fill"],
                partial_entry_fill=True,
            ),
            now_ms=now_ms + 20,
        )
        return _failure_result(
            simulation_input,
            scenario=scenario,
            context=context,
            payloads={"submitted": submitted},
        )

    submitted = protected_submit_attempt.record_ticket_bound_protected_submit_result(
        conn,
        protected_submit_attempt_id=str(prepared["protected_submit_attempt_id"]),
        submit_result=_mock_exchange_submit_result(prepared),
        now_ms=now_ms + 20,
    )
    protection = exit_protection_materializer.materialize_ticket_bound_exit_protection_set(
        conn,
        protected_submit_attempt_id=str(prepared["protected_submit_attempt_id"]),
        now_ms=now_ms + 21,
    )
    set_id = str(protection["exit_protection_set_id"])

    if scenario == "pg_protected_exchange_missing":
        reconciled = protection_reconciler.reconcile_ticket_bound_exit_protection_set(
            conn,
            exit_protection_set_id=set_id,
            exchange_snapshot=_exchange_snapshot_from_pg(
                conn,
                exit_protection_set_id=set_id,
                omit_roles={"SL"},
                position_qty="1",
            ),
            now_ms=now_ms + 22,
        )
        return _failure_result(
            simulation_input,
            scenario=scenario,
            context=context,
            payloads={
                "submitted": submitted,
                "protection": protection,
                "reconciler": reconciled,
            },
        )

    if scenario == "flat_position_live_protection_cleanup":
        reconciled = protection_reconciler.reconcile_ticket_bound_exit_protection_set(
            conn,
            exit_protection_set_id=set_id,
            exchange_snapshot=_exchange_snapshot_from_pg(
                conn,
                exit_protection_set_id=set_id,
                position_qty="0",
                position_flat=True,
            ),
            now_ms=now_ms + 22,
        )
        cleanup = (
            orphan_protection_cleanup_command.prepare_ticket_bound_orphan_protection_cleanup_command(
                conn,
                exit_protection_set_id=set_id,
                now_ms=now_ms + 23,
            )
        )
        cleanup_command_id = str(cleanup["orphan_protection_cleanup_command_id"])
        materialize_lifecycle_exchange_commands(
            conn,
            command_source="orphan_cleanup",
            source_command_id=cleanup_command_id,
            now_ms=now_ms + 24,
        )
        cleanup_results = _run_durable_lifecycle_commands(
            conn,
            command_source="orphan_cleanup",
            gateway=_MockCleanupGateway(),
            now_ms=now_ms + 25,
        )
        return _failure_result(
            simulation_input,
            scenario=scenario,
            context=context,
            payloads={
                "submitted": submitted,
                "protection": protection,
                "reconciler": reconciled,
                "cleanup_command": cleanup,
                "cleanup_result": cleanup_results[-1],
            },
        )

    _project_tp1_fill(conn, exit_protection_set_id=set_id, now_ms=now_ms + 22)

    if scenario == "tp1_filled_runner_missing":
        runner = runner_protection_adjuster.materialize_ticket_bound_runner_protection_adjustment(
            conn,
            exit_protection_set_id=set_id,
            runner_sl_exchange_order_id="",
            now_ms=now_ms + 23,
        )
        return _failure_result(
            simulation_input,
            scenario=scenario,
            context=context,
            payloads={
                "submitted": submitted,
                "protection": protection,
                "runner": runner,
            },
        )

    command = runner_mutation_command.prepare_ticket_bound_runner_mutation_command(
        conn,
        exit_protection_set_id=set_id,
        now_ms=now_ms + 23,
    )

    if scenario == "duplicate_tp1_fill_idempotent":
        _project_tp1_fill(conn, exit_protection_set_id=set_id, now_ms=now_ms + 24)
        duplicate_command = runner_mutation_command.prepare_ticket_bound_runner_mutation_command(
            conn,
            exit_protection_set_id=set_id,
            now_ms=now_ms + 25,
        )
        return _failure_result(
            simulation_input,
            scenario=scenario,
            context=context,
            payloads={
                "submitted": submitted,
                "protection": protection,
                "runner_mutation_command": command,
                "duplicate_runner_mutation_command": duplicate_command,
            },
        )

    gateway = (
        _MockRunnerMutationGateway(cancel_success=False)
        if scenario == "old_sl_cancel_failed"
        else _MockRunnerMutationGateway(place_success=False)
    )
    runner_command_id = str(command["runner_mutation_command_id"])
    materialize_lifecycle_exchange_commands(
        conn,
        command_source="runner_mutation",
        source_command_id=runner_command_id,
        now_ms=now_ms + 24,
    )
    runner_results = _run_durable_lifecycle_commands(
        conn,
        command_source="runner_mutation",
        gateway=gateway,
        now_ms=now_ms + 25,
    )
    return _failure_result(
        simulation_input,
        scenario=scenario,
        context=context,
        payloads={
            "submitted": submitted,
            "protection": protection,
            "runner_mutation_command": command,
            "runner_mutation_result": runner_results[-1],
        },
    )


def _prepare_full_chain_submit_context(
    conn: sa.engine.Connection,
    simulation_input: FullChainSimulationInput,
    *,
    projection_publisher: Callable[[sa.engine.Connection], dict[str, Any]],
) -> dict[str, Any]:
    now_ms = int(simulation_input.now_ms)
    row = _candidate_runtime_row(
        conn,
        strategy_group_id=simulation_input.strategy_group_id,
        symbol=simulation_input.symbol,
        side=simulation_input.side,
    )
    _insert_constructed_raw_input(
        conn,
        row=row,
        fact_values=simulation_input.fact_values or _fact_values(conn, row),
        now_ms=now_ms,
    )
    sequence_payload = materialize_action_time_ticket_sequence(
        conn,
        now_ms=now_ms,
        projection_publisher=projection_publisher,
        completion_clock_ms=lambda: now_ms + 2,
    )
    _require_payload_status(
        stage="atomic_ticket_sequence",
        payload=sequence_payload,
        expected_status="action_time_ticket_sequence_committed",
    )
    fact_payload = sequence_payload["fact"]
    projection_payload = sequence_payload["projection"]
    lane_payload = sequence_payload["promotion"]
    ticket_payload = sequence_payload["ticket"]
    _require_payload_status(
        stage="ticket",
        payload=ticket_payload,
        expected_status="action_time_ticket_created",
    )
    finalgate_payload = finalgate_preflight.materialize_action_time_finalgate_preflight(
        conn,
        ticket_id=str(ticket_payload["ticket_id"]),
        now_ms=now_ms + 3,
    )
    _require_payload_status(
        stage="finalgate",
        payload=finalgate_payload,
        expected_status="finalgate_ready",
    )
    handoff_payload = (
        operation_layer_handoff.materialize_action_time_operation_layer_handoff(
            conn,
            ticket_id=str(ticket_payload["ticket_id"]),
            finalgate_pass_id=str(finalgate_payload["finalgate_pass_id"]),
            now_ms=now_ms + 4,
        )
    )
    _require_payload_status(
        stage="operation_layer_handoff",
        payload=handoff_payload,
        expected_status="operation_layer_handoff_ready",
    )
    safety_payload = runtime_safety_state.materialize_ticket_bound_runtime_safety_state(
        conn,
        ticket_id=str(ticket_payload["ticket_id"]),
        operation_layer_handoff_id=str(handoff_payload["operation_layer_handoff_id"]),
        now_ms=now_ms + 5,
    )
    _require_payload_status(
        stage="runtime_safety",
        payload=safety_payload,
        expected_status="runtime_safety_state_ready",
    )
    with _mock_submit_decision_env():
        submit_mode_decision_payload = (
            protected_submit_attempt.materialize_ticket_bound_submit_mode_decision(
                conn,
                ticket_id=str(ticket_payload["ticket_id"]),
                operation_submit_command_id=str(
                    handoff_payload["operation_submit_command_id"]
                ),
                production_submit_execution_policy="armed",
                now_ms=now_ms + 5,
            )
        )
    prepared_payload = protected_submit_attempt.prepare_ticket_bound_protected_submit_attempt(
        conn,
        ticket_id=str(ticket_payload["ticket_id"]),
        operation_submit_command_id=str(handoff_payload["operation_submit_command_id"]),
        submit_mode="real_gateway_action",
        now_ms=now_ms + 6,
    )
    return {
        "sequence": sequence_payload,
        "fact": fact_payload,
        "projection": projection_payload,
        "lane": lane_payload,
        "ticket": ticket_payload,
        "finalgate": finalgate_payload,
        "handoff": handoff_payload,
        "safety": safety_payload,
        "submit_mode_decision": submit_mode_decision_payload,
        "prepared_submit": prepared_payload,
    }


@contextmanager
def _mock_submit_decision_env():
    values = {
        "TRADING_ENV": "live",
        "EXCHANGE_TESTNET": "false",
        "BRC_EXECUTION_PERMISSION_MAX": "order_allowed",
        "RUNTIME_CONTROL_API_ENABLED": "false",
        "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
        "RUNTIME_EXCHANGE_SUBMIT_GATEWAY_BINDING_ENABLED": "true",
    }
    previous = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _failure_result(
    simulation_input: FullChainSimulationInput,
    *,
    scenario: str,
    context: dict[str, Any],
    payloads: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "brc.ticket_bound_full_chain_failure_scenario.v1",
        "scenario": scenario,
        "strategy_group_id": simulation_input.strategy_group_id,
        "symbol": simulation_input.symbol,
        "side": simulation_input.side,
        **context,
        **payloads,
        "authority_boundary": {
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "uses_mock_exchange_result": True,
            "uses_mock_gateway": True,
            "uses_repo_json_or_md_authority": False,
        },
    }


def _require_payload_status(
    *,
    stage: str,
    payload: dict[str, Any],
    expected_status: str,
) -> None:
    actual_status = str(payload.get("status") or "")
    if actual_status == expected_status:
        return
    blockers = payload.get("blockers") or payload.get("first_blocker") or []
    raise RuntimeError(
        "full_chain_simulation_blocked:"
        f"{stage}:{actual_status}:expected:{expected_status}:blockers:{blockers}"
    )


class _MockRunnerMutationGateway:
    runtime_account_id = "owner-subaccount-runtime-v0"
    runtime_exchange_id = "binance_usdm"

    def __init__(
        self,
        *,
        cancel_success: bool = True,
        place_success: bool = True,
    ) -> None:
        self.cancel_calls: list[dict[str, Any]] = []
        self.place_calls: list[dict[str, Any]] = []
        self.cancel_success = cancel_success
        self.place_success = place_success

    async def cancel_order(self, **kwargs: Any) -> SimpleNamespace:
        self.cancel_calls.append(dict(kwargs))
        if not self.cancel_success:
            return SimpleNamespace(
                is_success=False,
                exchange_order_id=str(kwargs.get("exchange_order_id") or ""),
                status="REJECTED",
                error_message="old sl cancel rejected by simulation",
                error_code=None,
            )
        return SimpleNamespace(
            is_success=True,
            exchange_order_id=str(kwargs.get("exchange_order_id") or ""),
            status="CANCELED",
            error_message=None,
            error_code=None,
        )

    async def place_order(self, **kwargs: Any) -> SimpleNamespace:
        self.place_calls.append(dict(kwargs))
        if not self.place_success:
            return SimpleNamespace(
                is_success=False,
                exchange_order_id="",
                status="REJECTED",
                error_message="runner sl submit rejected by simulation",
                error_code=None,
            )
        return SimpleNamespace(
            is_success=True,
            exchange_order_id="mock-exchange-runner-sl",
            status="OPEN",
            error_message=None,
            error_code=None,
        )


class _MockCleanupGateway:
    runtime_account_id = "owner-subaccount-runtime-v0"
    runtime_exchange_id = "binance_usdm"

    def __init__(self) -> None:
        self.cancel_calls: list[dict[str, Any]] = []

    async def cancel_order(self, **kwargs: Any) -> SimpleNamespace:
        self.cancel_calls.append(dict(kwargs))
        return SimpleNamespace(
            is_success=True,
            exchange_order_id=str(kwargs.get("exchange_order_id") or ""),
            status="CANCELED",
            error_message=None,
            error_code=None,
        )


def _insert_constructed_raw_input(
    conn: sa.engine.Connection,
    *,
    row: dict[str, Any],
    fact_values: dict[str, Any],
    now_ms: int,
) -> None:
    semantic_fact_values = dict(fact_values)
    last_price = semantic_fact_values.pop(
        "last_price",
        "1800" if row["side"] == "short" else "2000",
    )
    public_fact_values = _production_public_fact_values(
        side=str(row["side"]),
        last_price=last_price,
    )
    conn.execute(
        sa.text(
            """
            UPDATE brc_strategy_side_event_specs
            SET declared_signal_grade = 'trial_grade_signal',
                declared_required_execution_mode = 'trial_live',
                execution_eligibility_enabled = true
            WHERE event_spec_id = :event_spec_id
            """
        ),
        {"event_spec_id": row["event_spec_id"]},
    )
    expires_at_ms = now_ms + 600_000
    observed_at_ms = now_ms - 20_000
    generated_at = datetime.fromtimestamp(
        observed_at_ms / 1000,
        tz=timezone.utc,
    ).isoformat()
    coverage = runtime_active_observation_monitor.write_candidate_universe_coverage_to_pg(
        {
            "candidate_universe_coverage": {
                "rows": [
                    {
                        "strategy_group_id": row["strategy_group_id"],
                        "symbol": row["symbol"],
                        "side": row["side"],
                        "state": "active_watcher_scope",
                        "runtime_profile": {
                            "runtime_profile_id": row["runtime_profile_id"]
                        },
                    }
                ]
            }
        },
        database_url="",
        allow_non_postgres_for_test=True,
        now_ms=now_ms,
        conn=conn,
    )
    if coverage.get("status") != "pg_watcher_runtime_coverage_written":
        raise ValueError("simulation_producer_coverage_write_failed")
    public_ids = write_pretrade_public_fact_snapshots(
        conn,
        artifact={
            "generated_at_utc": generated_at,
            "symbols": [
                {
                    "symbol": row["symbol"],
                    "mark_price_observed_at_utc": generated_at,
                    **public_fact_values,
                }
            ],
        },
        source_ref="simulation:public-gateway-response",
        source_kind="live_market",
    )
    if not public_ids:
        raise ValueError("simulation_producer_public_fact_write_failed")
    write_account_safe_fact_snapshots(
        conn,
        artifact={
            "generated_at_utc": generated_at,
            "source_status": "simulation_raw_signed_response",
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
            "facts": {},
            "account_mode": {
                "status": "fresh",
                "account_id": "owner-subaccount-runtime-v0",
                "exchange_id": "binance_usdm",
                "runtime_profile_id": row["runtime_profile_id"],
                "account_mode": "one_way",
                "dual_side_position": False,
                "position_mode_safe": True,
                "observed_at": generated_at,
                "source": (
                    "binance_usdm_signed_get:/fapi/v1/positionSide/dual"
                ),
            },
        },
        source_ref="simulation:signed-account-response",
    )
    required_fact_keys = {
        str(item["fact_key"])
        for item in conn.execute(
            sa.text(
                """
                SELECT fact_key FROM brc_strategy_event_required_facts
                WHERE event_spec_id = :event_spec_id
                  AND status = 'current'
                  AND required_for_promotion = true
                """
            ),
            {"event_spec_id": row["event_spec_id"]},
        ).mappings()
    }
    signal = runtime_active_observation_monitor.write_runtime_signal_summaries_to_pg(
        {
            "runtime_summaries": [
                {
                    "runtime_instance_id": (
                        f"simulation:{row['strategy_group_id']}:"
                        f"{row['symbol']}:{row['side']}"
                    ),
                    "strategy_family_id": row["strategy_group_id"],
                    "strategy_family_version_id": (
                        f"sgv:{row['strategy_group_id']}:v1"
                    ),
                    "symbol": row["symbol"],
                    "side": row["side"],
                    "status": "waiting_for_signal",
                    "signal_summary": {
                        "signal_type": "would_enter",
                        "signal_grade": "trial_grade_signal",
                        "required_execution_mode": "trial_live",
                        "side": row["side"],
                        "confidence": "0.90",
                        "reason_codes": ["simulation_producer_input"],
                        "trigger_candle_close_time_ms": now_ms - 60_000,
                        "time_authority": "trigger_candle_close_time_ms",
                        "fact_observations": [
                            {
                                "fact_key": key,
                                "observed_value": semantic_fact_values[key],
                                "observed_at_ms": now_ms - 60_000,
                                "valid_until_ms": expires_at_ms,
                                "source_ref": (
                                    f"simulation:evaluator:{row['event_spec_id']}:{key}"
                                ),
                            }
                            for key in sorted(required_fact_keys)
                            if key in semantic_fact_values
                        ],
                    },
                }
            ]
        },
        database_url="",
        allow_non_postgres_for_test=True,
        now_ms=now_ms,
        conn=conn,
    )
    if signal.get("status") != "pg_live_signal_events_written":
        raise ValueError(f"simulation_producer_signal_write_failed:{signal}")


def _production_public_fact_values(*, side: str, last_price: Any) -> dict[str, Any]:
    entry = Decimal(str(last_price))
    spread = Decimal("0.01")
    bid = entry if side == "short" else entry - spread
    ask = entry if side == "long" else entry + spread
    return {
        "public_facts_ready": True,
        "exchange_contract_exists": True,
        "mark_price_fresh": True,
        "funding_not_extreme": True,
        "spread_ok": True,
        "min_notional_ok": True,
        "qty_step_ok": True,
        "leverage_available": True,
        "facts": {
            "mark_price": str(entry),
            "bid_price": str(bid),
            "ask_price": str(ask),
            "qty_step": "0.001",
            "min_notional": "5",
            "contract_status": "TRADING",
            "contract_type": "PERPETUAL",
        },
    }


def _candidate_runtime_row(
    conn: sa.engine.Connection,
    *,
    strategy_group_id: str,
    symbol: str,
    side: str,
) -> dict[str, Any]:
    row = conn.execute(
        sa.text(
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
        {
            "strategy_group_id": strategy_group_id,
            "symbol": symbol,
            "side": side,
        },
    ).mappings().first()
    if row is None:
        raise ValueError(
            "candidate_scope_event_binding_missing:"
            f"{strategy_group_id}:{symbol}:{side}"
        )
    return dict(row)


def _insert_coverage(
    conn: sa.engine.Connection,
    row: dict[str, Any],
    *,
    expires_at_ms: int,
    now_ms: int,
) -> None:
    conn.execute(
        sa.text(
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
            "runtime_coverage_id": (
                "coverage:"
                f"{row['strategy_group_id']}:{row['symbol']}:{row['side']}:simulation"
            ),
            "strategy_group_id": row["strategy_group_id"],
            "symbol": row["symbol"],
            "side": row["side"],
            "detector_key": f"detector:{row['strategy_group_id']}:{row['side']}",
            "runtime_profile_id": row["runtime_profile_id"],
            "last_tick_at_ms": now_ms - 5_000,
            "valid_until_ms": expires_at_ms,
            "created_at_ms": now_ms - 5_000,
        },
    )


def _insert_fact(
    conn: sa.engine.Connection,
    *,
    fact_snapshot_id: str,
    row: dict[str, Any],
    fact_surface: str,
    fact_values: dict[str, Any],
    observed_at_ms: int,
    valid_until_ms: int,
    source_kind: str = "simulation",
) -> None:
    conn.execute(
        sa.text(
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
            "source_ref": f"simulation:{fact_surface}",
            "failed_facts": _json([]),
            "fact_values": _json(fact_values),
            "observed_at_ms": observed_at_ms,
            "valid_until_ms": valid_until_ms,
            "created_at_ms": observed_at_ms,
        },
    )


def _insert_signal(
    conn: sa.engine.Connection,
    row: dict[str, Any],
    *,
    public_fact_id: str,
    signal_event_id: str,
    now_ms: int,
    fact_values: dict[str, Any],
) -> None:
    event_time_ms = now_ms - 60_000
    required_fact_keys = {
        str(required_fact["fact_key"])
        for required_fact in conn.execute(
            sa.text(
                """
                SELECT fact_key
                FROM brc_strategy_event_required_facts
                WHERE event_spec_id = :event_spec_id
                  AND status = 'current'
                  AND required_for_promotion = true
                """
            ),
            {"event_spec_id": row["event_spec_id"]},
        ).mappings()
    }
    fact_observations = [
        {
            "fact_key": key,
            "observed_value": fact_values[key],
            "observed_at_ms": event_time_ms,
            "valid_until_ms": now_ms + 600_000,
            "source_ref": f"simulation:evaluator:{row['event_spec_id']}:{key}",
        }
        for key in sorted(required_fact_keys)
        if key in fact_values
    ]
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_live_signal_events (
              signal_event_id, candidate_scope_id, event_spec_id, strategy_group_id,
              symbol, side, detector_key, signal_type, source_kind, status, freshness_state,
              confidence, fact_snapshot_id, reason_codes, signal_payload,
              event_time_ms, trigger_candle_close_time_ms, observed_at_ms,
              expires_at_ms, invalidated_at_ms, created_at_ms,
              signal_grade, required_execution_mode, execution_eligible,
              authority_source_ref
            ) VALUES (
              :signal_event_id, :candidate_scope_id, :event_spec_id, :strategy_group_id,
              :symbol, :side, :detector_key, :signal_type,
              'live_market', 'facts_validated', 'fresh', 0.9, :fact_snapshot_id,
              :reason_codes, :signal_payload, :event_time_ms,
              :trigger_candle_close_time_ms, :observed_at_ms, :expires_at_ms,
              NULL, :created_at_ms, 'trial_grade_signal', 'trial_live', true,
              :authority_source_ref
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
            "fact_snapshot_id": public_fact_id,
            "reason_codes": _json(["simulation_fresh_signal"]),
            "signal_payload": _json(
                {
                    "time_authority": "trigger_candle_close_time_ms",
                    "trigger_candle_close_time_ms": event_time_ms,
                    "signal_summary": {
                        "fact_observations": fact_observations,
                    },
                }
            ),
            "event_time_ms": event_time_ms,
            "trigger_candle_close_time_ms": event_time_ms,
            "observed_at_ms": now_ms - 55_000,
            "expires_at_ms": now_ms + 600_000,
            "created_at_ms": now_ms - 54_000,
            "authority_source_ref": f"event-spec:{row['event_spec_id']}",
        },
    )


def _insert_readiness(
    conn: sa.engine.Connection,
    row: dict[str, Any],
    *,
    public_fact_id: str,
    now_ms: int,
) -> None:
    conn.execute(
        sa.text(
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
              'action_time_preflight_ready', 'simulation fresh action-time path ready',
              'materialize_pg_promotion_action_time_lane',
              'ticket_created_or_lane_expires', :evidence_ref, 'simulation',
              :computed_at_ms, :valid_until_ms
            )
            """
        ),
        {
            "readiness_row_id": (
                "readiness:"
                f"{row['strategy_group_id']}:{row['symbol']}:{row['side']}:simulation"
            ),
            "candidate_scope_id": row["candidate_scope_id"],
            "strategy_group_id": row["strategy_group_id"],
            "symbol": row["symbol"],
            "side": row["side"],
            "evidence_ref": public_fact_id,
            "computed_at_ms": now_ms - 6_000,
            "valid_until_ms": now_ms + 600_000,
        },
    )


def _fact_values(conn: sa.engine.Connection, row: dict[str, Any]) -> dict[str, Any]:
    facts = conn.execute(
        sa.text(
            """
            SELECT fact_key, operator, expected_value, disable_on_match
            FROM brc_strategy_event_required_facts
            WHERE event_spec_id = :event_spec_id
              AND status = 'current'
            """
        ),
        {"event_spec_id": row["event_spec_id"]},
    ).mappings()
    result: dict[str, Any] = {}
    for fact in facts:
        key = str(fact["fact_key"])
        if fact["disable_on_match"]:
            result[key] = False
        elif fact["operator"] == "exists":
            result[key] = "1800"
        elif fact["expected_value"] is not None:
            result[key] = fact["expected_value"]
        else:
            result[key] = True
    if row["side"] == "short":
        result[str(row["protection_ref_type"])] = "2000"
        result["last_price"] = "1800"
        result["take_profit_1"] = "1600"
    else:
        result[str(row["protection_ref_type"])] = "1800"
        result["last_price"] = "2000"
        result["take_profit_1"] = "2200"
    return result


def _production_shaped_protection_snapshot(
    conn: sa.engine.Connection,
    *,
    exit_protection_set_id: str,
    final_exit: bool,
    now_ms: int,
) -> dict[str, Any]:
    protection_set = conn.execute(
        sa.text(
            """
            SELECT symbol, side, entry_filled_qty
            FROM brc_ticket_bound_exit_protection_sets
            WHERE exit_protection_set_id = :set_id
            """
        ),
        {"set_id": exit_protection_set_id},
    ).mappings().one()
    orders = [
        dict(item)
        for item in conn.execute(
            sa.text(
                """
                SELECT role, exchange_order_id, side, qty, price, trigger_price,
                       reduce_only
                FROM brc_ticket_bound_exit_protection_orders
                WHERE exit_protection_set_id = :set_id
                  AND role IN ('SL', 'TP1')
                ORDER BY role
                """
            ),
            {"set_id": exit_protection_set_id},
        ).mappings()
    ]
    by_role = {str(item["role"]): item for item in orders}
    sl = by_role["SL"]
    if final_exit:
        return {
            "snapshot_ref": f"simulation:final:{exit_protection_set_id}",
            "symbol": str(protection_set["symbol"]),
            "exchange_symbol": str(protection_set["symbol"]),
            "open_orders": [],
            "recent_fills": [
                {
                    "exchange_order_id": str(sl["exchange_order_id"]),
                    "qty": str(sl["qty"]),
                    "price": str(sl["trigger_price"]),
                    "fee": {"cost": "0.01", "currency": "USDT"},
                    "timestamp_ms": now_ms,
                }
            ],
            "position": {
                "qty": "0",
                "side": str(protection_set["side"]),
                "position_side": "BOTH",
                "position_mode": "one_way",
                "complete": True,
            },
        }
    return {
        "snapshot_ref": f"simulation:protected:{exit_protection_set_id}",
        "symbol": str(protection_set["symbol"]),
        "exchange_symbol": str(protection_set["symbol"]),
        "open_orders": [
            {
                "exchange_order_id": str(item["exchange_order_id"]),
                "side": str(item["side"]),
                "reduce_only": bool(item["reduce_only"]),
                "qty": str(item["qty"]),
                "price": str(item["price"]) if item["price"] is not None else None,
                "trigger_price": (
                    str(item["trigger_price"])
                    if item["trigger_price"] is not None
                    else None
                ),
                "status": "open",
            }
            for item in orders
        ],
        "recent_fills": [],
        "position": {
            "qty": str(protection_set["entry_filled_qty"]),
            "side": str(protection_set["side"]),
            "position_side": "BOTH",
            "position_mode": "one_way",
            "complete": True,
        },
    }


def _provided_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "snapshot_ready",
        "exchange_read_called": True,
        "exchange_write_called": False,
        "snapshot": snapshot,
    }


def _run_durable_lifecycle_commands(
    conn: sa.engine.Connection,
    *,
    command_source: str,
    gateway: Any,
    now_ms: int,
) -> list[dict[str, Any]]:
    conn.commit()
    results: list[dict[str, Any]] = []
    for index in range(4):
        result = asyncio.run(
            run_one_ticket_bound_exchange_command(
                conn.engine,
                gateway=gateway,
                worker_id=f"simulation:{command_source}:{index}",
                command_sources=(command_source,),
                now_ms=now_ms + index,
            )
        )
        if result.get("status") in {
            "no_prepared_command",
            "durable_mutation_capability_not_ready",
        }:
            break
        results.append(result)
        if result.get("status") != "command_confirmed":
            break
    if not results:
        raise ValueError("simulation_durable_lifecycle_worker_not_run")
    return results


def _project_tp1_fill(
    conn: sa.engine.Connection,
    *,
    exit_protection_set_id: str,
    now_ms: int,
) -> None:
    row = conn.execute(
        sa.text(
            """
            SELECT s.ticket_id, o.exchange_order_id, o.qty, o.price
            FROM brc_ticket_bound_exit_protection_sets s
            JOIN brc_ticket_bound_exit_protection_orders o
              ON o.exit_protection_set_id = s.exit_protection_set_id
             AND o.role = 'TP1'
            WHERE s.exit_protection_set_id = :exit_protection_set_id
            """
        ),
        {"exit_protection_set_id": exit_protection_set_id},
    ).mappings().one()
    projected = project_ticket_bound_exchange_fills(
        conn,
        ticket_id=str(row["ticket_id"]),
        exchange_snapshot={
            "recent_fills": [
                {
                    "exchange_order_id": str(row["exchange_order_id"]),
                    "qty": str(row["qty"]),
                    "price": str(row["price"]),
                    "timestamp_ms": now_ms,
                }
            ]
        },
        now_ms=now_ms,
    )
    if projected.get("projected_roles") not in (["TP1"], []):
        raise ValueError(f"simulation_tp1_fill_projection_failed:{projected}")


def _mock_exchange_submit_result(prepared: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "exchange_submit_orders_submitted",
        "ticket_id": prepared["ticket_id"],
        "operation_submit_command_id": prepared["operation_submit_command_id"],
        "strategy_group_id": prepared["strategy_group_id"],
        "symbol": prepared["symbol"],
        "side": prepared["side"],
        "exchange_write_called": True,
        "order_created": True,
        "order_lifecycle_called": True,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "submitted_orders": [
            _mock_submitted_order(prepared, order)
            for order in prepared["submit_request"]["orders"]
        ],
    }


def _mock_exchange_submit_result_for_roles(
    prepared: dict[str, Any],
    *,
    roles: tuple[str, ...],
    status: str,
    blockers: list[str],
    partial_entry_fill: bool = False,
) -> dict[str, Any]:
    role_set = {role.upper() for role in roles}
    submitted_orders = [
        _mock_submitted_order(prepared, order)
        for order in prepared["submit_request"]["orders"]
        if str(order["order_role"]).upper() in role_set
    ]
    if partial_entry_fill:
        for order in submitted_orders:
            if str(order.get("order_role") or "").upper() == "ENTRY":
                requested = _decimal(order.get("amount"))
                order["status"] = "PARTIALLY_FILLED"
                order["filled_qty"] = str(requested / Decimal("2"))
    return {
        "status": status,
        "ticket_id": prepared["ticket_id"],
        "operation_submit_command_id": prepared["operation_submit_command_id"],
        "strategy_group_id": prepared["strategy_group_id"],
        "symbol": prepared["symbol"],
        "side": prepared["side"],
        "exchange_write_called": True,
        "order_created": bool(submitted_orders),
        "order_lifecycle_called": True,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "blockers": blockers,
        "submitted_orders": submitted_orders,
    }


def _mock_submitted_order(
    prepared: dict[str, Any],
    order: dict[str, Any],
) -> dict[str, Any]:
    role = str(order["order_role"])
    row = {
        "local_order_id": order["local_order_id"],
        "exchange_order_id": f"mock-exchange-{role.lower()}",
        "order_role": role,
        "reduce_only": order.get("reduce_only") is True,
        "amount": order["amount"],
        "price": order.get("price") or "",
        "trigger_price": order.get("trigger_price") or "",
    }
    if role == "ENTRY":
        row.update(
            {
                "status": "FILLED",
                "filled_qty": order["amount"],
                "average_exec_price": prepared["submit_request"]["reference_price"],
            }
        )
    return row


def _exchange_snapshot_from_pg(
    conn: sa.engine.Connection,
    *,
    exit_protection_set_id: str,
    omit_roles: set[str] | None = None,
    position_qty: str = "1",
    position_flat: bool = False,
) -> dict[str, Any]:
    omit_roles = omit_roles or set()
    orders = [
        dict(row)
        for row in conn.execute(
            sa.text(
                """
                SELECT role, exchange_order_id, qty, side, reduce_only
                FROM brc_ticket_bound_exit_protection_orders
                WHERE exit_protection_set_id = :exit_protection_set_id
                ORDER BY role
                """
            ),
            {"exit_protection_set_id": exit_protection_set_id},
        ).mappings()
        if row["role"] not in omit_roles
    ]
    return {
        "snapshot_id": f"simulation-snapshot:{exit_protection_set_id}",
        "open_orders": [
            {
                "exchange_order_id": row["exchange_order_id"],
                "qty": str(row["qty"]),
                "side": row["side"],
                "reduce_only": row["reduce_only"] in {True, 1},
                "status": "open",
            }
            for row in orders
        ],
        "recent_fills": [],
        "position": {"qty": position_qty, "position_flat": position_flat},
    }


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True)
