from __future__ import annotations

from copy import deepcopy
import json

import pytest
from sqlalchemy import text

from src.application.action_time import action_time_ticket
from src.application.action_time.ticket_exit_policy_binding import (
    TicketExitPolicyBindingError,
    legacy_unbound_ticket_exit_policy_binding,
    load_ticket_exit_policy_binding,
)
from src.domain.ticket_exit_policy import TicketExitPolicySnapshot
from tests.unit.test_action_time_ticket_materialization import (
    NOW_MS,
    _insert_action_time_lane_graph,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


def _policy_payload(
    *,
    strategy_group_id: str = "SOR-001",
    strategy_version: str = "sgv:SOR-001:v2",
    event_spec_id: str = "event_spec:SOR-001:SOR-LONG:v2",
    event_spec_version: str = "v2",
    side: str = "long",
    exit_policy_version: str = "1.0.0",
) -> dict:
    return {
        "exit_policy_id": "sor-right-tail-v1",
        "exit_policy_version": exit_policy_version,
        "strategy_group_id": strategy_group_id,
        "strategy_version": strategy_version,
        "event_spec_id": event_spec_id,
        "event_spec_version": event_spec_version,
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
                "trigger": "close_below_or_equal",
                "reference_key": "opening_range_boundary",
            }
        ],
        "time_stop_rule": {
            "kind": "max_holding_bars",
            "max_holding_bars": 24,
        },
        "runner_rule": {
            "kind": "structural_atr",
            "timeframe": "15m",
            "structure_rule": "confirmed_higher_low",
            "structure_window_bars": 4,
            "atr_period": 14,
            "atr_buffer_multiple": "1.5",
            "minimum_improvement_ticks": 2,
        },
    }


def _insert_policy(conn, payload: dict, *, row_overrides: dict | None = None) -> None:
    snapshot = TicketExitPolicySnapshot.with_canonical_hash(payload)
    row = {
        "exit_policy_id": snapshot.exit_policy_id,
        "exit_policy_version": snapshot.exit_policy_version,
        "strategy_group_id": snapshot.strategy_group_id,
        "strategy_version": snapshot.strategy_version,
        "event_spec_id": snapshot.event_spec_id,
        "event_spec_version": snapshot.event_spec_version,
        "side": snapshot.side,
        "policy_family": snapshot.policy_family.value,
        "policy_payload": snapshot.model_dump(mode="json"),
        "payload_hash": snapshot.payload_hash,
        "status": "current",
        "approved_by": "owner",
        "approved_at_ms": NOW_MS,
        "created_at_ms": NOW_MS,
    }
    row.update(row_overrides or {})
    conn.execute(
        text(
            "INSERT INTO brc_strategy_exit_policies ("
            "exit_policy_id, exit_policy_version, strategy_group_id, strategy_version, "
            "event_spec_id, event_spec_version, side, policy_family, policy_payload, "
            "payload_hash, status, approved_by, approved_at_ms, created_at_ms"
            ") VALUES ("
            ":exit_policy_id, :exit_policy_version, :strategy_group_id, "
            ":strategy_version, :event_spec_id, :event_spec_version, :side, "
            ":policy_family, :policy_payload, :payload_hash, :status, :approved_by, "
            ":approved_at_ms, :created_at_ms)"
        ),
        {
            **row,
            "policy_payload": json.dumps(row["policy_payload"], sort_keys=True),
        },
    )


def test_load_ticket_exit_policy_binding_requires_one_exact_valid_current_row(
    pg_control_connection,
):
    payload = _policy_payload()
    _insert_policy(pg_control_connection, payload)

    binding = load_ticket_exit_policy_binding(
        pg_control_connection,
        strategy_group_id="SOR-001",
        strategy_version="sgv:SOR-001:v2",
        event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
        event_spec_version="v2",
        side="long",
    )

    assert binding.binding_kind == "versioned"
    assert binding.snapshot.exit_policy_version == "1.0.0"
    assert binding.exit_policy_hash == binding.snapshot.payload_hash


def test_missing_and_duplicate_current_policy_fail_closed(pg_control_connection):
    with pytest.raises(TicketExitPolicyBindingError, match="missing"):
        load_ticket_exit_policy_binding(
            pg_control_connection,
            strategy_group_id="SOR-001",
            strategy_version="sgv:SOR-001:v2",
            event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
            event_spec_version="v2",
            side="long",
        )

    pg_control_connection.execute(text("DROP INDEX uq_brc_exit_policy_current_scope"))
    _insert_policy(pg_control_connection, _policy_payload())
    _insert_policy(
        pg_control_connection,
        _policy_payload(exit_policy_version="2.0.0"),
        row_overrides={"exit_policy_id": "sor-right-tail-v2"},
    )
    with pytest.raises(TicketExitPolicyBindingError, match="multiple"):
        load_ticket_exit_policy_binding(
            pg_control_connection,
            strategy_group_id="SOR-001",
            strategy_version="sgv:SOR-001:v2",
            event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
            event_spec_version="v2",
            side="long",
        )


@pytest.mark.parametrize(
    ("payload_mutation", "row_overrides", "expected"),
    [
        ({"side": "short"}, {"side": "long"}, "side"),
        ({"event_spec_version": "v3"}, {"event_spec_version": "v2"}, "version"),
        ({"policy_family": "unknown"}, {}, "invalid"),
    ],
)
def test_invalid_policy_payload_or_row_identity_fails_closed(
    pg_control_connection,
    payload_mutation,
    row_overrides,
    expected,
):
    payload = _policy_payload()
    payload.update(payload_mutation)
    if payload_mutation.get("policy_family") == "unknown":
        valid = TicketExitPolicySnapshot.with_canonical_hash(_policy_payload())
        _insert_policy(pg_control_connection, _policy_payload())
        pg_control_connection.execute(
            text(
                "UPDATE brc_strategy_exit_policies "
                "SET policy_payload = :payload WHERE exit_policy_id = :policy_id"
            ),
            {
                "payload": json.dumps({**valid.model_dump(mode="json"), "side": "bad"}),
                "policy_id": valid.exit_policy_id,
            },
        )
    else:
        _insert_policy(pg_control_connection, payload, row_overrides=row_overrides)

    with pytest.raises(TicketExitPolicyBindingError, match=expected):
        load_ticket_exit_policy_binding(
            pg_control_connection,
            strategy_group_id="SOR-001",
            strategy_version="sgv:SOR-001:v2",
            event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
            event_spec_version="v2",
            side="long",
        )


def test_hash_mismatch_and_legacy_binding_are_explicit(pg_control_connection):
    _insert_policy(pg_control_connection, _policy_payload())
    pg_control_connection.execute(
        text(
            "UPDATE brc_strategy_exit_policies SET payload_hash = 'wrong' "
            "WHERE exit_policy_id = 'sor-right-tail-v1'"
        )
    )
    with pytest.raises(TicketExitPolicyBindingError, match="hash"):
        load_ticket_exit_policy_binding(
            pg_control_connection,
            strategy_group_id="SOR-001",
            strategy_version="sgv:SOR-001:v2",
            event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
            event_spec_version="v2",
            side="long",
        )

    legacy = legacy_unbound_ticket_exit_policy_binding()
    assert legacy.binding_kind == "legacy_unbound"
    assert legacy.snapshot is None
    assert legacy.exit_policy_snapshot == {
        "binding_kind": "legacy_unbound",
        "historical_semantics_not_synthesized": True,
    }


def test_ticket_identity_hash_changes_when_policy_version_changes():
    base = {
        field: f"value-{field}"
        for field in action_time_ticket.TICKET_IDENTITY_HASH_FIELDS
    }
    base.update(
        {
            field: "1"
            for field in action_time_ticket.DECIMAL_HASH_FIELDS
        }
    )
    base.update(
        {
            field: 1
            for field in action_time_ticket.INTEGER_HASH_FIELDS
        }
    )
    first = action_time_ticket.compute_action_time_ticket_hash(base)
    changed = deepcopy(base)
    changed["exit_policy_version"] = "2.0.0"

    assert first != action_time_ticket.compute_action_time_ticket_hash(changed)


def test_ticket_identity_hash_normalizes_sqlite_boolean_storage():
    base = {
        field: f"value-{field}"
        for field in action_time_ticket.TICKET_IDENTITY_HASH_FIELDS
    }
    base.update(
        {
            field: "1"
            for field in action_time_ticket.DECIMAL_HASH_FIELDS
        }
    )
    base.update(
        {
            field: 1
            for field in action_time_ticket.INTEGER_HASH_FIELDS
        }
    )
    base["execution_eligible"] = True
    sqlite_row = {**base, "execution_eligible": 1}

    assert action_time_ticket.compute_action_time_ticket_hash(base) == (
        action_time_ticket.compute_action_time_ticket_hash(sqlite_row)
    )


def test_enabled_capability_freezes_exact_policy_into_new_ticket(
    pg_control_connection,
):
    _insert_action_time_lane_graph(pg_control_connection)
    _insert_policy(pg_control_connection, _policy_payload())
    pg_control_connection.execute(
        text(
            "UPDATE brc_runtime_capabilities_current SET status = 'enabled', "
            "certification_ref = 'unit:enabled', updated_at_ms = :now_ms "
            "WHERE capability_id = 'ticket_exit_policy_v1'"
        ),
        {"now_ms": NOW_MS},
    )

    result = action_time_ticket.materialize_action_time_ticket(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert result["status"] == "action_time_ticket_created", result
    assert result["ticket"]["exit_policy_id"] == "sor-right-tail-v1"
    assert result["ticket"]["exit_policy_version"] == "1.0.0"
    assert result["ticket"]["exit_policy_hash"]
    assert result["ticket"]["exit_policy_snapshot"]["side"] == "long"
    projection = pg_control_connection.execute(
        text(
            "SELECT exit_policy_hash, exit_execution_hash "
            "FROM brc_ticket_exit_policy_current WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": result["ticket"]["ticket_id"]},
    ).mappings().one()
    assert projection["exit_policy_hash"] == result["ticket"]["exit_policy_hash"]
    assert projection["exit_execution_hash"] is None
