from __future__ import annotations

from decimal import Decimal
import json

import pytest
import sqlalchemy as sa
from sqlalchemy import text

from src.application.action_time.ticket_exit_policy_service import (
    maintain_ticket_exit_policy_in_transaction,
)
from src.domain.ticket_exit_policy import (
    TicketExitExecutionSnapshot,
    TicketExitPolicySnapshot,
    calculate_runner_break_even_floor,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_runner_protection_adjuster import (
    _materialized_exit_protection_set,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


def test_disabled_capability_is_no_write(pg_control_connection):
    ticket_id = _versioned_exit_fixture(pg_control_connection)
    pg_control_connection.execute(
        text(
            "UPDATE brc_runtime_capabilities_current SET status = 'disabled' "
            "WHERE capability_id = 'ticket_exit_policy_v1'"
        )
    )
    before = _projection(pg_control_connection, ticket_id)

    result = maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_000,
    )

    assert result["status"] == "exit_policy_capability_disabled"
    assert _commands(pg_control_connection) == []
    assert _projection(pg_control_connection, ticket_id) == before


@pytest.mark.parametrize("completion", ["unfilled", "partial"])
def test_unfilled_or_already_synchronized_partial_creates_no_command(
    pg_control_connection,
    completion,
):
    ticket_id = _versioned_exit_fixture(pg_control_connection)
    current = _projection(pg_control_connection, ticket_id)
    active = _active_order(pg_control_connection)
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_exit_policy_current SET "
            "tp1_completion_state = :completion, remaining_position_qty = :qty "
            "WHERE ticket_id = :ticket_id"
        ),
        {
            "completion": completion,
            "qty": str(active["qty"]),
            "ticket_id": ticket_id,
        },
    )

    result = maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_000,
    )

    assert result["status"] in {"tp1_unfilled", "protection_quantity_synchronized"}
    assert _commands(pg_control_connection) == []
    assert _projection(pg_control_connection, ticket_id)["active_runner_stop"] == (
        current["active_runner_stop"]
    )


def test_partial_fill_resizes_exact_remaining_qty_without_raising_stop(
    pg_control_connection,
):
    ticket_id = _versioned_exit_fixture(pg_control_connection)
    original = _active_order(pg_control_connection)
    remaining = Decimal(str(original["qty"])) - Decimal("0.001")
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_exit_policy_current SET "
            "tp1_cumulative_filled_qty = 0.001, tp1_completion_state = 'partial', "
            "remaining_position_qty = :remaining WHERE ticket_id = :ticket_id"
        ),
        {"remaining": str(remaining), "ticket_id": ticket_id},
    )

    result = maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_000,
    )

    assert result["status"] == "runner_replacement_prepared", result
    command = _commands(pg_control_connection)[0]
    assert command["command_source"] == "exit_policy_runner"
    assert command["command_kind"] == "place_order"
    assert Decimal(str(command["amount"])) == remaining
    assert Decimal(str(command["stop_price"])) == Decimal(
        str(original["trigger_price"])
    )


def test_complete_tp1_prepares_immediate_cost_adjusted_floor(
    pg_control_connection,
):
    side = "long"
    ticket_id = _versioned_exit_fixture(pg_control_connection, side=side)
    projection = _projection(pg_control_connection, ticket_id)
    snapshot = TicketExitExecutionSnapshot.model_validate(
        _mapping(projection["exit_execution_snapshot"])
    )
    pg_control_connection.execute(
        text(
            "UPDATE brc_exchange_instruments SET price_tick = NULL, "
            "quantity_step = NULL WHERE exchange_instrument_id = ("
            "SELECT exchange_instrument_id FROM brc_action_time_tickets "
            "WHERE ticket_id = :ticket_id)"
        ),
        {"ticket_id": ticket_id},
    )
    exchange_snapshot = {
        "exchange_instrument_id": _instrument(
            pg_control_connection, ticket_id
        )["exchange_instrument_id"],
        "market_rule": {
            "exchange_instrument_id": _instrument(
                pg_control_connection, ticket_id
            )["exchange_instrument_id"],
            "exchange_id": "binance_usdm",
            "exchange_market_id": "ETHUSDT",
            "price_tick": "1",
            "quantity_step": "0.001",
            "min_notional": "5",
            "source": "binance_usdm_public_exchange_info",
        },
    }
    expected = calculate_runner_break_even_floor(
        side=side,
        entry_avg_fill_price=snapshot.entry_avg_fill_price,
        runner_qty=snapshot.runner_target_qty,
        allocated_entry_fee_quote=snapshot.entry_fee_quote,
        certified_exit_taker_fee_rate=snapshot.certified_exit_taker_fee_rate,
        slippage_buffer_quote=snapshot.slippage_buffer_quote,
        minimum_price_tick=Decimal("1"),
    )
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_exit_policy_current SET "
            "tp1_cumulative_filled_qty = resolved_tp1_target_qty, "
            "tp1_completion_state = 'complete', "
            "remaining_position_qty = :remaining WHERE ticket_id = :ticket_id"
        ),
        {"remaining": str(snapshot.runner_target_qty), "ticket_id": ticket_id},
    )

    result = maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        exchange_snapshot=exchange_snapshot,
        now_ms=NOW_MS + 20_000,
    )

    command = _commands(pg_control_connection)[0]
    assert result["status"] == "runner_replacement_prepared"
    assert Decimal(str(command["stop_price"])).quantize(Decimal("0.1")) == expected
    assert Decimal(
        str(_projection(pg_control_connection, ticket_id)["runner_break_even_floor"])
    ).quantize(Decimal("0.1")) == expected


def test_new_stop_is_confirmed_before_exact_old_cancel_is_prepared(
    pg_control_connection,
):
    ticket_id = _versioned_exit_fixture(pg_control_connection)
    old = _active_order(pg_control_connection)
    _mark_tp1_complete(pg_control_connection, ticket_id)
    first = maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_000,
    )
    place = _commands(pg_control_connection)[0]

    waiting = maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_100,
    )
    assert waiting["status"] == "runner_place_pending"
    assert len(_commands(pg_control_connection)) == 1

    _set_command_state(
        pg_control_connection,
        place["exchange_command_id"],
        state="confirmed_submitted",
        exchange_order_id="exchange-policy-runner-2",
    )
    confirmed = maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_200,
    )
    commands = _commands(pg_control_connection)
    cancel = next(row for row in commands if row["command_kind"] == "cancel_order")

    assert first["status"] == "runner_replacement_prepared"
    assert confirmed["status"] == "runner_cancel_prepared"
    assert cancel["target_exchange_order_id"] == old["exchange_order_id"]
    assert cancel["source_command_id"] == place["source_command_id"]


def test_unknown_place_blocks_cancel_and_restart_is_idempotent(pg_control_connection):
    ticket_id = _versioned_exit_fixture(pg_control_connection)
    _mark_tp1_complete(pg_control_connection, ticket_id)
    maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_000,
    )
    place = _commands(pg_control_connection)[0]
    _set_command_state(
        pg_control_connection,
        place["exchange_command_id"],
        state="outcome_unknown",
        exchange_order_id=None,
    )

    first = maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_100,
    )
    second = maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_200,
    )

    assert first["status"] == "runner_place_outcome_unknown"
    assert second == first
    assert len(_commands(pg_control_connection)) == 1


def test_old_stop_fill_during_replacement_terminates_without_duplicate_close(
    pg_control_connection,
):
    ticket_id = _versioned_exit_fixture(pg_control_connection)
    old = _active_order(pg_control_connection)
    _mark_tp1_complete(pg_control_connection, ticket_id)
    maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_000,
    )
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_exit_protection_orders SET status = 'filled' "
            "WHERE exit_protection_order_id = :order_id"
        ),
        {"order_id": old["exit_protection_order_id"]},
    )
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_exit_policy_current SET remaining_position_qty = 0 "
            "WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ticket_id},
    )

    result = maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_100,
    )

    assert result["status"] == "position_terminal"
    assert len(_commands(pg_control_connection)) == 1
    assert all(row["command_source"] != "exit_policy_close" for row in _commands(pg_control_connection))


def test_confirmed_cancel_activates_new_generation_once(pg_control_connection):
    ticket_id = _versioned_exit_fixture(pg_control_connection)
    old = _active_order(pg_control_connection)
    _mark_tp1_complete(pg_control_connection, ticket_id)
    maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_000,
    )
    place = _commands(pg_control_connection)[0]
    _set_command_state(
        pg_control_connection,
        place["exchange_command_id"],
        state="confirmed_submitted",
        exchange_order_id="exchange-policy-runner-2",
    )
    maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_100,
    )
    cancel = next(
        row for row in _commands(pg_control_connection) if row["command_kind"] == "cancel_order"
    )
    _set_command_state(
        pg_control_connection,
        cancel["exchange_command_id"],
        state="confirmed_submitted",
        exchange_order_id=old["exchange_order_id"],
    )

    first = maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_200,
    )
    second = maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_300,
    )
    projection = _projection(pg_control_connection, ticket_id)

    assert first["status"] == "runner_replacement_completed"
    assert second["status"] == "runner_stop_not_improved"
    assert projection["active_runner_generation"] == 2
    assert projection["pending_generation"] is None
    assert len(_commands(pg_control_connection)) == 2


def test_close_decision_prepares_one_reduce_position_market_command(
    pg_control_connection,
):
    ticket_id = _versioned_exit_fixture(pg_control_connection)
    _mark_tp1_complete(pg_control_connection, ticket_id)
    projection = _projection(pg_control_connection, ticket_id)
    watermark = NOW_MS + 100_000
    _insert_exit_market_fact(
        pg_control_connection,
        ticket_id=ticket_id,
        watermark=watermark,
        invalidation_rule_ids_hit=["opening_range_reclaim_failed"],
    )
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_exit_policy_current SET "
            "last_evaluated_watermark_ms = :watermark, "
            "last_reason_code = 'fact-exit-close' WHERE ticket_id = :ticket_id"
        ),
        {"watermark": watermark, "ticket_id": ticket_id},
    )
    # Make the immediate floor already satisfied so the closed-candle invalidation wins.
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_exit_policy_current SET active_runner_stop = 1000000 "
            "WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ticket_id},
    )

    first = maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 200_000,
    )
    second = maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 200_001,
    )
    commands = _commands(pg_control_connection)

    assert first["status"] == "runner_close_prepared", first
    assert second["status"] == "runner_close_pending"
    assert len(commands) == 1
    assert commands[0]["command_source"] == "exit_policy_close"
    assert commands[0]["order_type"] == "market"
    assert commands[0]["reduce_intent"] == "reduce_position"
    assert Decimal(str(commands[0]["amount"])) == Decimal(
        str(projection["remaining_position_qty"])
    )


def _versioned_exit_fixture(conn, *, side: str = "long") -> str:
    set_id = _materialized_exit_protection_set(conn)
    protection_set = dict(
        conn.execute(
            text(
                "SELECT * FROM brc_ticket_bound_exit_protection_sets "
                "WHERE exit_protection_set_id = :set_id"
            ),
            {"set_id": set_id},
        ).mappings().one()
    )
    ticket_id = str(protection_set["ticket_id"])
    ticket = dict(
        conn.execute(
            text("SELECT * FROM brc_action_time_tickets WHERE ticket_id = :ticket_id"),
            {"ticket_id": ticket_id},
        ).mappings().one()
    )
    orders = {
        row["role"]: dict(row)
        for row in conn.execute(
            text(
                "SELECT * FROM brc_ticket_bound_exit_protection_orders "
                "WHERE exit_protection_set_id = :set_id"
            ),
            {"set_id": set_id},
        ).mappings()
    }
    entry_price = Decimal(str(protection_set["entry_avg_price"]))
    entry_qty = Decimal(str(protection_set["entry_filled_qty"]))
    initial_stop = Decimal(str(orders["SL"]["trigger_price"]))
    if side == "short":
        conn.execute(
            text("UPDATE brc_action_time_tickets SET side = 'short' WHERE ticket_id = :id"),
            {"id": ticket_id},
        )
        conn.execute(
            text(
                "UPDATE brc_runtime_scope_bindings SET side = 'short' "
                "WHERE runtime_scope_binding_id = :id"
            ),
            {"id": ticket["runtime_scope_binding_id"]},
        )
        conn.execute(
            text(
                "UPDATE brc_budget_reservations SET side = 'short' "
                "WHERE budget_reservation_id = :id"
            ),
            {"id": ticket["budget_reservation_id"]},
        )
        conn.execute(
            text(
                "UPDATE brc_ticket_bound_exit_protection_sets SET side = 'short' "
                "WHERE exit_protection_set_id = :id"
            ),
            {"id": set_id},
        )
        conn.execute(
            text(
                "UPDATE brc_ticket_bound_order_lifecycle_runs SET side = 'short' "
                "WHERE ticket_id = :id"
            ),
            {"id": ticket_id},
        )
        initial_stop = entry_price + abs(entry_price - initial_stop)
        conn.execute(
            text(
                "UPDATE brc_ticket_bound_exit_protection_orders SET "
                "side = 'buy', trigger_price = :stop WHERE role = 'SL' "
                "AND exit_protection_set_id = :id"
            ),
            {"stop": initial_stop, "id": set_id},
        )
    payload = {
        "exit_policy_id": f"unit-right-tail-{side}",
        "exit_policy_version": "1.0.0",
        "strategy_group_id": str(ticket["strategy_group_id"]),
        "strategy_version": str(ticket["strategy_group_version_id"]),
        "event_spec_id": str(ticket["event_spec_id"]),
        "event_spec_version": str(ticket["event_spec_version_id"]),
        "side": side,
        "policy_family": "right_tail_runner",
        "reward_basis": "actual_entry_r",
        "take_profit_legs": [
            {
                "role": "TP1",
                "reward_multiple": "1",
                "quantity_fraction": "0.5",
                "execution_style": "limit_gtc",
                "market_fallback_allowed": False,
            }
        ],
        "tp_completion_tolerance_qty_steps": 1,
        "post_tp1_floor_rule": {
            "kind": "runner_leg_cost_adjusted_break_even",
            "trigger": "tp1_target_quantity_complete",
            "exit_fee_basis": "conservative_taker",
            "slippage_buffer_ticks": 2,
            "minimum_improvement_ticks": 2,
        },
        "invalidation_rules": [
            {
                "kind": "reference_price_cross",
                "rule_id": "opening_range_reclaim_failed",
                "trigger": "close_below_or_equal" if side == "long" else "close_above_or_equal",
                "reference_key": "opening_range_boundary",
            }
        ],
        "time_stop_rule": {"kind": "max_holding_bars", "max_holding_bars": 24},
        "runner_rule": {
            "kind": "structural_atr",
            "timeframe": "15m",
            "structure_rule": "confirmed_higher_low" if side == "long" else "confirmed_lower_high",
            "structure_window_bars": 4,
            "atr_period": 14,
            "atr_buffer_multiple": "1.5",
            "minimum_improvement_ticks": 2,
        },
    }
    policy = TicketExitPolicySnapshot.with_canonical_hash(payload)
    target_qty = Decimal(str(orders["TP1"]["qty"]))
    runner_qty = entry_qty - target_qty
    execution = TicketExitExecutionSnapshot.with_canonical_hash(
        {
            "ticket_id": ticket_id,
            "exit_policy_id": policy.exit_policy_id,
            "exit_policy_version": policy.exit_policy_version,
            "entry_avg_fill_price": entry_price,
            "entry_filled_qty": entry_qty,
            "initial_stop_price": initial_stop,
            "actual_r_per_unit": abs(entry_price - initial_stop),
            "resolved_tp1_price": Decimal(str(orders["TP1"]["price"])),
            "resolved_tp1_target_qty": target_qty,
            "runner_target_qty": runner_qty,
            "entry_fee_quote": Decimal("0.01"),
            "certified_exit_taker_fee_rate": Decimal("0.0005"),
            "slippage_buffer_quote": Decimal("0.01"),
        }
    )
    instruments = sa.Table(
        "brc_exchange_instruments", sa.MetaData(), autoload_with=conn
    )
    conn.execute(
        instruments.update()
        .where(
            instruments.c.exchange_instrument_id == ticket["exchange_instrument_id"]
        )
        .values(price_tick=Decimal("1"), quantity_step=Decimal("0.001"))
    )
    conn.execute(
        text(
            "UPDATE brc_action_time_tickets SET side = :side, exit_policy_id = :policy_id, "
            "exit_policy_version = :version, exit_policy_snapshot = :snapshot, "
            "exit_policy_hash = :hash WHERE ticket_id = :ticket_id"
        ),
        {
            "side": side,
            "policy_id": policy.exit_policy_id,
            "version": policy.exit_policy_version,
            "snapshot": json.dumps(policy.model_dump(mode="json")),
            "hash": policy.payload_hash,
            "ticket_id": ticket_id,
        },
    )
    conn.execute(
        text(
            "INSERT INTO brc_ticket_exit_policy_current ("
            "ticket_id, exit_protection_set_id, exit_policy_id, exit_policy_version, "
            "exit_policy_hash, exit_execution_snapshot, exit_execution_hash, "
            "actual_r_per_unit, resolved_tp1_price, resolved_tp1_target_qty, "
            "tp1_cumulative_filled_qty, tp1_completion_state, remaining_position_qty, "
            "state, active_runner_order_id, active_runner_generation, active_runner_stop, "
            "updated_at_ms) VALUES ("
            ":ticket_id, :set_id, :policy_id, :version, :policy_hash, :execution, "
            ":execution_hash, :actual_r, :tp1_price, :tp1_qty, 0, 'unfilled', "
            ":entry_qty, 'execution_bound', :active_id, 1, :active_stop, :now_ms)"
        ),
        {
            "ticket_id": ticket_id,
            "set_id": set_id,
            "policy_id": policy.exit_policy_id,
            "version": policy.exit_policy_version,
            "policy_hash": policy.payload_hash,
            "execution": json.dumps(execution.model_dump(mode="json")),
            "execution_hash": execution.payload_hash,
            "actual_r": str(execution.actual_r_per_unit),
            "tp1_price": str(execution.resolved_tp1_price),
            "tp1_qty": str(execution.resolved_tp1_target_qty),
            "entry_qty": str(execution.entry_filled_qty),
            "active_id": orders["SL"]["exit_protection_order_id"],
            "active_stop": str(initial_stop),
            "now_ms": NOW_MS + 10_000,
        },
    )
    conn.execute(
        text(
            "UPDATE brc_runtime_capabilities_current SET status = 'enabled', "
            "certification_ref = 'unit-exit-policy' "
            "WHERE capability_id = 'ticket_exit_policy_v1'"
        )
    )
    return ticket_id


def _mark_tp1_complete(conn, ticket_id: str) -> None:
    projection = _projection(conn, ticket_id)
    snapshot = TicketExitExecutionSnapshot.model_validate(
        _mapping(projection["exit_execution_snapshot"])
    )
    conn.execute(
        text(
            "UPDATE brc_ticket_exit_policy_current SET "
            "tp1_cumulative_filled_qty = resolved_tp1_target_qty, "
            "tp1_completion_state = 'complete', remaining_position_qty = :qty "
            "WHERE ticket_id = :ticket_id"
        ),
        {"qty": str(snapshot.runner_target_qty), "ticket_id": ticket_id},
    )


def _insert_exit_market_fact(conn, *, ticket_id, watermark, invalidation_rule_ids_hit):
    projection = _projection(conn, ticket_id)
    ticket = dict(
        conn.execute(
            text("SELECT * FROM brc_action_time_tickets WHERE ticket_id = :ticket_id"),
            {"ticket_id": ticket_id},
        ).mappings().one()
    )
    conn.execute(
        text(
            "INSERT INTO brc_runtime_fact_snapshots ("
            "fact_snapshot_id, strategy_group_id, symbol, side, runtime_profile_id, "
            "fact_surface, source_kind, source_ref, computed, satisfied, freshness_state, "
            "failed_facts, fact_values, observed_at_ms, valid_until_ms, created_at_ms) "
            "VALUES ('fact-exit-close', :strategy_group_id, :symbol, :side, :profile, "
            "'ticket_exit_market', 'unit', 'unit', true, true, 'fresh', '[]', :facts, "
            ":observed, :valid_until, :created)"
        ),
        {
            "strategy_group_id": ticket["strategy_group_id"],
            "symbol": ticket["symbol"],
            "side": ticket["side"],
            "profile": ticket["runtime_profile_id"],
            "facts": json.dumps(
                {
                    "schema": "brc.ticket_exit_market_fact.v1",
                    "ticket_id": ticket_id,
                    "exchange_instrument_id": ticket["exchange_instrument_id"],
                    "venue_id": "binance_usdm",
                    "timeframe": "15m",
                    "watermark_ms": watermark,
                    "invalidation_rule_ids_hit": invalidation_rule_ids_hit,
                    "references": {"opening_range_boundary": "100"},
                    "candles": [
                        {
                            "exchange_instrument_id": ticket["exchange_instrument_id"],
                            "venue_id": "binance_usdm",
                            "timeframe": "15m",
                            "open_time_ms": watermark - 900_000,
                            "close_time_ms": watermark,
                            "observed_at_ms": watermark + 1,
                            "valid_until_ms": watermark + 900_000,
                            "is_final_closed_candle": True,
                            "open": "101",
                            "high": "102",
                            "low": "99",
                            "close": "99",
                            "volume": "1",
                        }
                    ],
                }
            ),
            "observed": watermark + 1,
            "valid_until": watermark + 900_000,
            "created": watermark + 1,
        },
    )


def _set_command_state(conn, command_id, *, state, exchange_order_id):
    conn.execute(
        text(
            "UPDATE brc_ticket_bound_exchange_commands SET command_state = :state, "
            "exchange_order_id = :exchange_order_id WHERE exchange_command_id = :id"
        ),
        {"state": state, "exchange_order_id": exchange_order_id, "id": command_id},
    )


def _projection(conn, ticket_id):
    return dict(
        conn.execute(
            text(
                "SELECT * FROM brc_ticket_exit_policy_current "
                "WHERE ticket_id = :ticket_id"
            ),
            {"ticket_id": ticket_id},
        ).mappings().one()
    )


def _active_order(conn):
    return dict(
        conn.execute(
            text(
                "SELECT * FROM brc_ticket_bound_exit_protection_orders "
                "WHERE role IN ('SL', 'RUNNER_SL') AND status IN ('submitted', 'open') "
                "ORDER BY generation DESC LIMIT 1"
            )
        ).mappings().one()
    )


def _commands(conn):
    return [
        dict(row)
        for row in conn.execute(
            text(
                "SELECT * FROM brc_ticket_bound_exchange_commands "
                "WHERE command_source IN ('exit_policy_runner', 'exit_policy_close') "
                "ORDER BY prepared_at_ms, command_kind DESC"
            )
        ).mappings()
    ]


def _instrument(conn, ticket_id):
    return dict(
        conn.execute(
            text(
                "SELECT i.* FROM brc_exchange_instruments i "
                "JOIN brc_action_time_tickets t ON t.exchange_instrument_id = i.exchange_instrument_id "
                "WHERE t.ticket_id = :ticket_id"
            ),
            {"ticket_id": ticket_id},
        ).mappings().one()
    )


def _mapping(value):
    if isinstance(value, dict):
        return value
    return json.loads(value)
