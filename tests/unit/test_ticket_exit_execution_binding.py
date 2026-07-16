from __future__ import annotations

from decimal import Decimal
import json

import pytest
from sqlalchemy import text

from src.application.action_time.ticket_exit_execution_binding import (
    TicketExitExecutionBindingError,
    bind_ticket_exit_execution_snapshot,
    build_ticket_exit_execution_snapshot,
    recover_ticket_exit_execution_snapshot_from_exchange_truth,
)
from src.domain.ticket_exit_policy import TicketExitPolicySnapshot
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)
from tests.unit.test_ticket_exit_policy_binding import _policy_payload
from tests.unit.test_ticket_exit_policy_service import _versioned_exit_fixture


def _policy(*, side: str = "long") -> TicketExitPolicySnapshot:
    return TicketExitPolicySnapshot.with_canonical_hash(
        _policy_payload(
            side=side,
            event_spec_id=(
                "event_spec:SOR-001:SOR-LONG:v2"
                if side == "long"
                else "event_spec:SOR-001:SOR-SHORT:v2"
            ),
        )
    )


@pytest.mark.parametrize(
    ("side", "entry", "stop", "expected_tp1"),
    [
        ("long", "100.03", "95.03", "105.1"),
        ("short", "100.03", "105.03", "95.0"),
    ],
)
def test_execution_snapshot_resolves_actual_fill_r_tp1_and_quantities(
    side,
    entry,
    stop,
    expected_tp1,
):
    snapshot = build_ticket_exit_execution_snapshot(
        ticket_id="ticket-1",
        policy=_policy(side=side),
        side=side,
        entry_avg_fill_price=Decimal(entry),
        entry_filled_qty=Decimal("1.003"),
        initial_stop_price=Decimal(stop),
        minimum_price_tick=Decimal("0.1"),
        quantity_step=Decimal("0.001"),
        entry_fee_amount=Decimal("0.04012"),
        entry_fee_asset="USDT",
        quote_asset="USDT",
        fee_asset_quote_conversion_rate=None,
        certified_exit_taker_fee_rate=Decimal("0.0005"),
    )

    assert snapshot.actual_r_per_unit == Decimal("5.00")
    assert snapshot.resolved_tp1_price == Decimal(expected_tp1)
    assert snapshot.resolved_tp1_target_qty == Decimal("0.501")
    assert snapshot.runner_target_qty == Decimal("0.502")
    assert snapshot.entry_fee_quote == Decimal("0.02008")
    assert snapshot.slippage_buffer_quote == Decimal("0.1004")
    assert snapshot.payload_hash


def test_execution_binding_uses_final_average_fill_not_planned_tp1():
    snapshot = build_ticket_exit_execution_snapshot(
        ticket_id="ticket-1",
        policy=_policy(),
        side="long",
        entry_avg_fill_price=Decimal("101"),
        entry_filled_qty=Decimal("1"),
        initial_stop_price=Decimal("96"),
        minimum_price_tick=Decimal("0.1"),
        quantity_step=Decimal("0.001"),
        entry_fee_amount=Decimal("0.04"),
        entry_fee_asset="USDT",
        quote_asset="USDT",
        fee_asset_quote_conversion_rate=None,
        certified_exit_taker_fee_rate=Decimal("0.0005"),
    )

    assert snapshot.resolved_tp1_price == Decimal("106")
    assert snapshot.resolved_tp1_price != Decimal("105")


@pytest.mark.parametrize(
    "overrides",
    [
        {"initial_stop_price": Decimal("101")},
        {"initial_stop_price": Decimal("100")},
        {"entry_filled_qty": Decimal("0")},
        {"minimum_price_tick": Decimal("0")},
        {"quantity_step": Decimal("0")},
        {"entry_fee_amount": None},
        {"entry_fee_asset": "BNB"},
        {"certified_exit_taker_fee_rate": Decimal("1")},
    ],
)
def test_execution_snapshot_rejects_wrong_stop_zero_r_missing_fee_and_precision(
    overrides,
):
    values = {
        "ticket_id": "ticket-1",
        "policy": _policy(),
        "side": "long",
        "entry_avg_fill_price": Decimal("100"),
        "entry_filled_qty": Decimal("1"),
        "initial_stop_price": Decimal("95"),
        "minimum_price_tick": Decimal("0.1"),
        "quantity_step": Decimal("0.001"),
        "entry_fee_amount": Decimal("0.04"),
        "entry_fee_asset": "USDT",
        "quote_asset": "USDT",
        "fee_asset_quote_conversion_rate": None,
        "certified_exit_taker_fee_rate": Decimal("0.0005"),
    }
    values.update(overrides)
    with pytest.raises(TicketExitExecutionBindingError):
        build_ticket_exit_execution_snapshot(**values)


def test_non_quote_entry_fee_requires_exact_conversion_fact():
    snapshot = build_ticket_exit_execution_snapshot(
        ticket_id="ticket-1",
        policy=_policy(),
        side="long",
        entry_avg_fill_price=Decimal("100"),
        entry_filled_qty=Decimal("1"),
        initial_stop_price=Decimal("95"),
        minimum_price_tick=Decimal("0.1"),
        quantity_step=Decimal("0.001"),
        entry_fee_amount=Decimal("0.001"),
        entry_fee_asset="BNB",
        quote_asset="USDT",
        fee_asset_quote_conversion_rate=Decimal("600"),
        certified_exit_taker_fee_rate=Decimal("0.0005"),
    )
    assert snapshot.entry_fee_quote == Decimal("0.3")


def test_pg_execution_binding_is_immutable_and_idempotent(pg_control_connection):
    policy = _policy()
    pg_control_connection.execute(
        text(
            "INSERT INTO brc_action_time_tickets ("
            "ticket_id, action_time_lane_input_id, promotion_candidate_id, "
            "signal_event_id, event_spec_id, event_spec_version_id, candidate_scope_id, "
            "runtime_scope_binding_id, strategy_group_id, strategy_group_version_id, "
            "symbol, exchange_instrument_id, side, event_id, event_time_ms, "
            "trigger_candle_close_time_ms, runtime_profile_id, public_fact_snapshot_id, "
            "action_time_fact_snapshot_id, account_safe_fact_snapshot_id, "
            "account_mode_snapshot_id, budget_reservation_id, protection_ref_id, "
            "execution_policy_id, execution_policy_version, owner_policy_version, "
            "sizing_policy_version, protection_policy_version, target_notional, leverage, "
            "expires_at_ms, status, authority_boundary, ticket_hash, "
            "created_under_versions_hash, created_at_ms, exit_policy_id, "
            "exit_policy_version, exit_policy_snapshot, exit_policy_hash, "
            "lane_identity_key, source_watermark"
            ") VALUES ("
            "'ticket-exec-1', 'lane-exec-1', 'promotion-1', 'signal-1', "
            ":event_spec_id, 'event-version-1', 'scope-1', 'runtime-scope-1', "
            "'SOR-001', 'sgv:SOR-001:v2', 'ETHUSDT', 'binance_usdm:ETH/USDT:USDT', "
            "'long', 'SOR-LONG', 1, 1, 'profile-1', 'public-1', 'action-1', "
            "'account-1', 'mode-1', 'budget-1', 'protection-1', 'execution-1', "
            "'1', '1', '1', '1', 20, 2, :expires, 'submitted', 'unit', 'hash', "
            "'versions', :created, :policy_id, :policy_version, :policy_snapshot, "
            ":policy_hash, 'lane-key-1', 1)"
        ),
        {
            "event_spec_id": policy.event_spec_id,
            "expires": NOW_MS + 60_000,
            "created": NOW_MS,
            "policy_id": policy.exit_policy_id,
            "policy_version": policy.exit_policy_version,
            "policy_snapshot": json.dumps(policy.model_dump(mode="json")),
            "policy_hash": policy.payload_hash,
        },
    )
    values = {
        "ticket_id": "ticket-exec-1",
        "side": "long",
        "entry_avg_fill_price": Decimal("100"),
        "entry_filled_qty": Decimal("1"),
        "initial_stop_price": Decimal("95"),
        "minimum_price_tick": Decimal("0.1"),
        "quantity_step": Decimal("0.001"),
        "entry_fee_amount": Decimal("0.04"),
        "entry_fee_asset": "USDT",
        "quote_asset": "USDT",
        "fee_asset_quote_conversion_rate": None,
        "certified_exit_taker_fee_rate": Decimal("0.0005"),
        "now_ms": NOW_MS,
    }
    first = bind_ticket_exit_execution_snapshot(pg_control_connection, **values)
    second = bind_ticket_exit_execution_snapshot(pg_control_connection, **values)
    assert first["status"] == "execution_bound"
    assert second["status"] == "execution_binding_idempotent"
    assert first["exit_execution_hash"] == second["exit_execution_hash"]

    with pytest.raises(TicketExitExecutionBindingError, match="contradiction"):
        bind_ticket_exit_execution_snapshot(
            pg_control_connection,
            **{**values, "entry_avg_fill_price": Decimal("101")},
        )


def _restart_recovery_snapshot(conn, ticket_id: str) -> dict:
    lifecycle = dict(
        conn.execute(
            text(
                "SELECT * FROM brc_ticket_bound_order_lifecycle_runs "
                "WHERE ticket_id = :ticket_id"
            ),
            {"ticket_id": ticket_id},
        ).mappings().one()
    )
    ticket = dict(
        conn.execute(
            text(
                "SELECT * FROM brc_action_time_tickets WHERE ticket_id = :ticket_id"
            ),
            {"ticket_id": ticket_id},
        ).mappings().one()
    )
    instrument = dict(
        conn.execute(
            text(
                "SELECT * FROM brc_exchange_instruments "
                "WHERE exchange_instrument_id = :instrument_id"
            ),
            {"instrument_id": ticket["exchange_instrument_id"]},
        ).mappings().one()
    )
    qty = Decimal(str(lifecycle["entry_filled_qty"]))
    avg_price = Decimal(str(lifecycle["entry_avg_price"]))
    return {
        "snapshot_id": "snapshot:restart-recovery",
        "account_id": "owner-subaccount-runtime-v0",
        "symbol": ticket["symbol"],
        "exchange_instrument_id": ticket["exchange_instrument_id"],
        "exchange_id": instrument["exchange_id"],
        "recent_fills": [
            {
                "exchange_trade_id": "entry-trade-1",
                "exchange_order_id": lifecycle["entry_exchange_order_id"],
                "side": "buy",
                "qty": str(qty),
                "price": str(avg_price),
                "fee": {"cost": "0.04", "currency": "USDT"},
            }
        ],
        "commission_rate": {
            "symbol": ticket["symbol"],
            "maker_commission_rate": "0.0002",
            "taker_commission_rate": "0.0005",
        },
        "market_rule": {
            "exchange_instrument_id": ticket["exchange_instrument_id"],
            "exchange_id": instrument["exchange_id"],
            "exchange_market_id": ticket["symbol"],
            "price_tick": "1",
            "quantity_step": "0.001",
            "min_notional": "5",
            "quote_asset": "USDT",
            "settle_asset": "USDT",
            "source": "binance_usdm_public_exchange_info",
        },
        "exchange_read_called": True,
        "exchange_write_called": False,
    }


def test_restart_recovery_binds_missing_execution_snapshot_idempotently(
    pg_control_connection,
):
    ticket_id = _versioned_exit_fixture(pg_control_connection)
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_exit_policy_current SET "
            "exit_execution_snapshot = NULL, exit_execution_hash = NULL, "
            "actual_r_per_unit = NULL, resolved_tp1_price = NULL, "
            "resolved_tp1_target_qty = NULL, remaining_position_qty = NULL, "
            "state = 'bound' WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ticket_id},
    )
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_exit_protection_orders SET price = 99999 "
            "WHERE ticket_id = :ticket_id AND role = 'TP1'"
        ),
        {"ticket_id": ticket_id},
    )
    snapshot = _restart_recovery_snapshot(pg_control_connection, ticket_id)

    first = recover_ticket_exit_execution_snapshot_from_exchange_truth(
        pg_control_connection,
        ticket_id=ticket_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 20_000,
    )
    second = recover_ticket_exit_execution_snapshot_from_exchange_truth(
        pg_control_connection,
        ticket_id=ticket_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 20_001,
    )

    assert first["status"] == "execution_bound"
    assert first["pg_projection_mutated"] is True
    assert first["exchange_write_called"] is False
    assert second["status"] == "execution_binding_idempotent"
    assert second["pg_projection_mutated"] is False
    assert second["exit_execution_hash"] == first["exit_execution_hash"]
    projection = dict(
        pg_control_connection.execute(
            text(
                "SELECT * FROM brc_ticket_exit_policy_current "
                "WHERE ticket_id = :ticket_id"
            ),
            {"ticket_id": ticket_id},
        ).mappings().one()
    )
    assert projection["remaining_position_qty"] is not None
    assert projection["state"] == "blocked_tp1_reprice_required"
    assert projection["first_blocker"] == "tp1_reprice_required"


def test_restart_recovery_fails_closed_when_entry_fee_truth_is_missing(
    pg_control_connection,
):
    ticket_id = _versioned_exit_fixture(pg_control_connection)
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_exit_policy_current SET "
            "exit_execution_snapshot = NULL, exit_execution_hash = NULL, "
            "state = 'bound' WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ticket_id},
    )
    snapshot = _restart_recovery_snapshot(pg_control_connection, ticket_id)
    snapshot["recent_fills"][0]["fee"] = None

    result = recover_ticket_exit_execution_snapshot_from_exchange_truth(
        pg_control_connection,
        ticket_id=ticket_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 20_000,
    )

    assert result["status"] == "execution_recovery_blocked"
    assert result["first_blocker"] == "entry_fee_amount_missing"
    assert result["pg_projection_mutated"] is False
    assert result["exchange_write_called"] is False
    assert pg_control_connection.execute(
        text(
            "SELECT exit_execution_hash FROM brc_ticket_exit_policy_current "
            "WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ticket_id},
    ).scalar_one() is None


def test_restart_recovery_rechecks_tp1_when_execution_snapshot_already_exists(
    pg_control_connection,
):
    ticket_id = _versioned_exit_fixture(pg_control_connection)
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_exit_protection_orders SET price = 99999 "
            "WHERE ticket_id = :ticket_id AND role = 'TP1'"
        ),
        {"ticket_id": ticket_id},
    )
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_exit_policy_current SET state = 'execution_bound', "
            "first_blocker = NULL WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ticket_id},
    )

    result = recover_ticket_exit_execution_snapshot_from_exchange_truth(
        pg_control_connection,
        ticket_id=ticket_id,
        exchange_snapshot=_restart_recovery_snapshot(
            pg_control_connection, ticket_id
        ),
        now_ms=NOW_MS + 20_000,
    )

    assert result["status"] == "execution_binding_idempotent"
    assert result["tp1_reprice_required"] is True
    state = pg_control_connection.execute(
        text(
            "SELECT state FROM brc_ticket_exit_policy_current "
            "WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ticket_id},
    ).scalar_one()
    assert state == "blocked_tp1_reprice_required"
