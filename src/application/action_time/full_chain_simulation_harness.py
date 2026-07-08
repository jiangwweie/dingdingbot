"""Local full-chain simulation harness for ticket-bound action-time flow.

The harness constructs typed PG rows and runs the L2-L9 materializers without
using repo JSON/MD files and without calling the exchange. It is intended for
local acceptance tests that must expose engineering defects before server
runtime or live market events do.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import asyncio
import json
from types import SimpleNamespace
from typing import Any, Callable

import sqlalchemy as sa

from src.application.action_time import action_time_ticket
from src.application.action_time import exit_protection_materializer
from src.application.action_time import fact_snapshots
from src.application.action_time import finalgate_preflight
from src.application.action_time import operation_layer_handoff
from src.application.action_time import post_submit_closure
from src.application.action_time import promotion_action_time_lane
from src.application.action_time import protected_submit_attempt
from src.application.action_time import runner_mutation_command
from src.application.action_time import runner_mutation_executor
from src.application.action_time import runner_protection_adjuster
from src.application.action_time import runtime_safety_state


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

    fact_payload = fact_snapshots.materialize_action_time_fact_snapshots(
        conn,
        now_ms=now_ms,
    )
    projection_payload = projection_publisher(conn)
    lane_payload = promotion_action_time_lane.materialize_pg_promotion_action_time_lane(
        conn,
        now_ms=now_ms + 1,
    )
    ticket_payload = action_time_ticket.materialize_action_time_ticket(
        conn,
        now_ms=now_ms + 2,
    )
    finalgate_payload = finalgate_preflight.materialize_action_time_finalgate_preflight(
        conn,
        ticket_id=str(ticket_payload["ticket_id"]),
        now_ms=now_ms + 3,
    )
    handoff_payload = (
        operation_layer_handoff.materialize_action_time_operation_layer_handoff(
            conn,
            ticket_id=str(ticket_payload["ticket_id"]),
            finalgate_pass_id=str(finalgate_payload["finalgate_pass_id"]),
            now_ms=now_ms + 4,
        )
    )
    safety_payload = runtime_safety_state.materialize_ticket_bound_runtime_safety_state(
        conn,
        ticket_id=str(ticket_payload["ticket_id"]),
        operation_layer_handoff_id=str(handoff_payload["operation_layer_handoff_id"]),
        now_ms=now_ms + 5,
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
    _mark_tp1_filled(conn, exit_protection_set_id=set_id, now_ms=now_ms + 10)
    runner_command_payload = (
        runner_mutation_command.prepare_ticket_bound_runner_mutation_command(
            conn,
            exit_protection_set_id=set_id,
            now_ms=now_ms + 11,
        )
    )
    runner_command_result_payload = asyncio.run(
        runner_mutation_executor.execute_ticket_bound_runner_mutation_command(
            conn,
            runner_mutation_command_id=str(
                runner_command_payload["runner_mutation_command_id"]
            ),
            gateway=_MockRunnerMutationGateway(),
            now_ms=now_ms + 12,
        )
    )
    runner_payload = (
        runner_protection_adjuster.materialize_ticket_bound_runner_protection_adjustment(
            conn,
            exit_protection_set_id=set_id,
            runner_sl_exchange_order_id=str(
                runner_command_result_payload["result_payload"][
                    "runner_sl_exchange_order_id"
                ]
            ),
            runner_sl_local_order_id=str(
                runner_command_result_payload["result_payload"][
                    "runner_sl_local_order_id"
                ]
            ),
            now_ms=now_ms + 13,
        )
    )
    final_payload = post_submit_closure.materialize_ticket_bound_lifecycle_closure(
        conn,
        protected_submit_attempt_id=str(prepared_payload["protected_submit_attempt_id"]),
        final_exit_exchange_order_id="mock-exchange-runner-sl",
        final_exit_role="RUNNER_SL",
        final_position_flat_confirmed=True,
        reconciliation_evidence_id=(
            "simulation-recon:"
            f"{simulation_input.strategy_group_id}:{simulation_input.symbol}:{simulation_input.side}"
        ),
        settlement_evidence_id=(
            "simulation-settlement:"
            f"{simulation_input.strategy_group_id}:{simulation_input.symbol}:{simulation_input.side}"
        ),
        review_evidence_id=(
            "simulation-review:"
            f"{simulation_input.strategy_group_id}:{simulation_input.symbol}:{simulation_input.side}"
        ),
        now_ms=now_ms + 14,
    )

    return {
        "schema": "brc.ticket_bound_full_chain_simulation.v1",
        "strategy_group_id": simulation_input.strategy_group_id,
        "symbol": simulation_input.symbol,
        "side": simulation_input.side,
        "fact": fact_payload,
        "projection": projection_payload,
        "lane": lane_payload,
        "ticket": ticket_payload,
        "finalgate": finalgate_payload,
        "handoff": handoff_payload,
        "safety": safety_payload,
        "prepared_submit": prepared_payload,
        "submitted": submitted_payload,
        "protection": protection_payload,
        "post_submit_pending": post_submit_pending_payload,
        "runner_mutation_command": runner_command_payload,
        "runner_mutation_result": runner_command_result_payload,
        "runner": runner_payload,
        "final": final_payload,
        "authority_boundary": {
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "uses_mock_exchange_result": True,
            "uses_mock_runner_mutation_gateway": True,
            "uses_repo_json_or_md_authority": False,
        },
    }


class _MockRunnerMutationGateway:
    def __init__(self) -> None:
        self.cancel_calls: list[dict[str, Any]] = []
        self.place_calls: list[dict[str, Any]] = []

    async def cancel_order(self, **kwargs: Any) -> SimpleNamespace:
        self.cancel_calls.append(dict(kwargs))
        return SimpleNamespace(
            is_success=True,
            exchange_order_id=str(kwargs.get("exchange_order_id") or ""),
            status="CANCELED",
        )

    async def place_order(self, **kwargs: Any) -> SimpleNamespace:
        self.place_calls.append(dict(kwargs))
        return SimpleNamespace(
            is_success=True,
            exchange_order_id="mock-exchange-runner-sl",
            status="OPEN",
        )


def _insert_constructed_raw_input(
    conn: sa.engine.Connection,
    *,
    row: dict[str, Any],
    fact_values: dict[str, Any],
    now_ms: int,
) -> None:
    suffix = f"{row['strategy_group_id']}:{row['symbol']}:{row['side']}:simulation"
    public_fact_id = f"fact:{suffix}:public"
    expires_at_ms = now_ms + 600_000
    _insert_coverage(conn, row, expires_at_ms=expires_at_ms, now_ms=now_ms)
    _insert_fact(
        conn,
        fact_snapshot_id=public_fact_id,
        row=row,
        fact_surface="pretrade_public",
        fact_values=fact_values,
        observed_at_ms=now_ms - 20_000,
        valid_until_ms=expires_at_ms,
        source_kind="live_market",
    )
    _insert_fact(
        conn,
        fact_snapshot_id=f"fact:{suffix}:account-safe",
        row=row,
        fact_surface="account_safe",
        fact_values={
            "account_safe": True,
            "open_orders_clear": True,
            "active_position_or_open_order_clear": True,
            "action_time_available_balance": True,
        },
        observed_at_ms=now_ms - 8_000,
        valid_until_ms=expires_at_ms,
    )
    _insert_fact(
        conn,
        fact_snapshot_id=f"fact:{suffix}:account-mode",
        row=row,
        fact_surface="account_mode",
        fact_values={"account_mode": "one_way", "position_mode_safe": True},
        observed_at_ms=now_ms - 7_000,
        valid_until_ms=expires_at_ms,
    )
    _insert_signal(
        conn,
        row,
        public_fact_id=public_fact_id,
        signal_event_id=f"signal:{suffix}",
        now_ms=now_ms,
    )
    conn.execute(sa.text("DELETE FROM brc_pretrade_readiness_rows"))
    _insert_readiness(conn, row, public_fact_id=public_fact_id, now_ms=now_ms)


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
) -> None:
    event_time_ms = now_ms - 60_000
    conn.execute(
        sa.text(
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
              'live_market', 'facts_validated', 'fresh', 0.9, :fact_snapshot_id,
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
            "fact_snapshot_id": public_fact_id,
            "reason_codes": _json(["simulation_fresh_signal"]),
            "signal_payload": _json(
                {
                    "time_authority": "trigger_candle_close_time_ms",
                    "trigger_candle_close_time_ms": event_time_ms,
                }
            ),
            "event_time_ms": event_time_ms,
            "trigger_candle_close_time_ms": event_time_ms,
            "observed_at_ms": now_ms - 55_000,
            "expires_at_ms": now_ms + 600_000,
            "created_at_ms": now_ms - 54_000,
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
    result[str(row["protection_ref_type"])] = "1800"
    result["last_price"] = "2000"
    result["take_profit_1"] = "2200" if row["side"] == "long" else "1600"
    return result


def _mark_tp1_filled(
    conn: sa.engine.Connection,
    *,
    exit_protection_set_id: str,
    now_ms: int,
) -> None:
    conn.execute(
        sa.text(
            """
            UPDATE brc_ticket_bound_exit_protection_orders
            SET status = 'filled', updated_at_ms = :updated_at_ms
            WHERE exit_protection_set_id = :exit_protection_set_id
              AND role = 'TP1'
            """
        ),
        {
            "exit_protection_set_id": exit_protection_set_id,
            "updated_at_ms": now_ms,
        },
    )


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


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True)
