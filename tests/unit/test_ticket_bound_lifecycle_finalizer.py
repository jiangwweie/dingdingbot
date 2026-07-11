from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from src.application.action_time.exchange_command_worker import (
    run_one_ticket_bound_exchange_command,
)
from src.application.action_time.lifecycle_maintenance_scheduler import (
    run_ticket_bound_lifecycle_maintenance_scheduler,
)
from src.application.action_time.ticket_bound_lifecycle_finalizer import (
    finalize_ticket_bound_lifecycle_if_ready,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_runner_protection_adjuster import (
    _materialized_exit_protection_set,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


def test_finalizer_closes_reconciled_flat_lifecycle_and_is_idempotent(
    pg_control_connection,
):
    ticket_id = _prepare_reconciled_flat_exit(pg_control_connection)

    first = finalize_ticket_bound_lifecycle_if_ready(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_000,
    )
    second = finalize_ticket_bound_lifecycle_if_ready(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 21_000,
    )

    assert first["status"] == "lifecycle_closed"
    assert first["runtime_budget_mutated"] is True
    assert first["live_outcome_status"] == "recorded"
    assert second["status"] == "lifecycle_closed"
    assert second["runtime_budget_mutated"] is False
    assert second["live_outcome_status"] == "recorded"
    assert _scalar(
        pg_control_connection,
        "SELECT status FROM brc_ticket_bound_order_lifecycle_runs",
    ) == "lifecycle_closed"
    assert _scalar(
        pg_control_connection,
        "SELECT status FROM brc_budget_reservations WHERE ticket_id = :ticket_id",
        ticket_id=ticket_id,
    ) == "released"
    assert _scalar(
        pg_control_connection,
        "SELECT status FROM brc_ticket_bound_post_submit_closures",
    ) == "closed"
    assert _scalar(
        pg_control_connection,
        "SELECT count(*) FROM brc_live_outcome_ledger WHERE ticket_id = :ticket_id",
        ticket_id=ticket_id,
    ) == 1
    assert _scalar(
        pg_control_connection,
        "SELECT count(*) FROM brc_ticket_bound_lifecycle_events "
        "WHERE event_type IN ('reconciliation_matched', 'budget_settled', "
        "'review_recorded', 'lifecycle_closed')",
    ) == 4


def test_finalizer_does_not_release_budget_while_residual_protection_is_live(
    pg_control_connection,
):
    ticket_id = _prepare_reconciled_flat_exit(
        pg_control_connection,
        leave_tp1_live=True,
    )

    payload = finalize_ticket_bound_lifecycle_if_ready(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_000,
    )

    assert payload["status"] == "finalization_blocked"
    assert payload["first_blocker"] == "position_closed_protection_live:TP1"
    assert payload["runtime_budget_mutated"] is False
    assert _scalar(
        pg_control_connection,
        "SELECT status FROM brc_budget_reservations WHERE ticket_id = :ticket_id",
        ticket_id=ticket_id,
    ) != "released"
    assert _scalar(
        pg_control_connection,
        "SELECT count(*) FROM brc_live_outcome_ledger WHERE ticket_id = :ticket_id",
        ticket_id=ticket_id,
    ) == 0


@pytest.mark.asyncio
async def test_production_scheduler_drives_final_fill_to_closed_outcome_without_event_fixture(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    scope = pg_control_connection.execute(
        text(
            "SELECT ticket_id, protected_submit_attempt_id "
            "FROM brc_ticket_bound_exit_protection_sets "
            "WHERE exit_protection_set_id = :set_id"
        ),
        {"set_id": set_id},
    ).mappings().one()
    sl = pg_control_connection.execute(
        text(
            "SELECT exchange_order_id, qty FROM "
            "brc_ticket_bound_exit_protection_orders "
            "WHERE exit_protection_set_id = :set_id AND role = 'SL'"
        ),
        {"set_id": set_id},
    ).mappings().one()
    tp1 = pg_control_connection.execute(
        text(
            "SELECT exchange_order_id, qty, price FROM "
            "brc_ticket_bound_exit_protection_orders "
            "WHERE exit_protection_set_id = :set_id AND role = 'TP1'"
        ),
        {"set_id": set_id},
    ).mappings().one()
    initial_snapshot = {
        "snapshot_ref": f"unit-initial:{set_id}",
        "symbol": "ETHUSDT",
        "exchange_symbol": "ETH/USDT:USDT",
        "open_orders": [
            {
                "exchange_order_id": sl["exchange_order_id"],
                "side": "sell",
                "reduce_only": True,
                "qty": str(sl["qty"]),
                "trigger_price": "1999.5",
                "status": "open",
            },
            {
                "exchange_order_id": tp1["exchange_order_id"],
                "side": "sell",
                "reduce_only": True,
                "qty": str(tp1["qty"]),
                "price": str(tp1["price"]),
                "status": "open",
            },
        ],
        "recent_fills": [],
        "position": {
            "qty": str(sl["qty"]),
            "side": "long",
            "position_side": "BOTH",
            "position_mode": "one_way",
            "complete": True,
        },
    }
    snapshot = {
        "snapshot_ref": f"unit-final:{set_id}",
        "symbol": "ETHUSDT",
        "exchange_symbol": "ETH/USDT:USDT",
        "open_orders": [],
        "recent_fills": [
            {
                "exchange_order_id": sl["exchange_order_id"],
                "qty": str(sl["qty"]),
                "price": "1990",
                "fee": {"cost": "0.01", "currency": "USDT"},
                "timestamp_ms": NOW_MS + 20_000,
            }
        ],
        "position": {
            "qty": "0",
            "side": "long",
            "position_side": "BOTH",
            "position_mode": "one_way",
            "complete": True,
        },
    }
    provided = {
        set_id: {
            "status": "snapshot_ready",
            "exchange_read_called": True,
            "exchange_write_called": False,
            "snapshot": snapshot,
        },
        str(scope["protected_submit_attempt_id"]): {
            "status": "snapshot_ready",
            "exchange_read_called": True,
            "exchange_write_called": False,
            "snapshot": snapshot,
        },
    }

    initial_provided = {
        key: {**value, "snapshot": initial_snapshot}
        for key, value in provided.items()
    }
    initial = await run_ticket_bound_lifecycle_maintenance_scheduler(
        pg_control_connection,
        provided_exchange_snapshots=initial_provided,
        fetch_exchange_snapshot=False,
        allow_exchange_mutation=False,
        now_ms=NOW_MS + 19_000,
    )
    first = await run_ticket_bound_lifecycle_maintenance_scheduler(
        pg_control_connection,
        provided_exchange_snapshots=provided,
        fetch_exchange_snapshot=False,
        allow_exchange_mutation=False,
        now_ms=NOW_MS + 20_000,
    )
    pg_control_connection.commit()
    worker = await run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=_FinalizerGateway(),
        worker_id="unit-finalizer-worker",
        command_sources=("orphan_cleanup",),
        now_ms=NOW_MS + 21_000,
    )
    with pg_control_connection.engine.begin() as conn:
        second = await run_ticket_bound_lifecycle_maintenance_scheduler(
            conn,
            provided_exchange_snapshots=provided,
            fetch_exchange_snapshot=False,
            allow_exchange_mutation=False,
            now_ms=NOW_MS + 22_000,
        )

    assert initial["exchange_write_called"] is False
    assert first["exchange_write_called"] is False
    assert worker["status"] == "no_prepared_command"
    assert second["exchange_write_called"] is False
    assert second["status"] == "no_maintainable_lifecycle"
    with pg_control_connection.engine.connect() as conn:
        assert conn.execute(
            text(
                "SELECT status FROM brc_ticket_bound_order_lifecycle_runs "
                "WHERE ticket_id = :ticket_id"
            ),
            {"ticket_id": scope["ticket_id"]},
        ).scalar_one() == "lifecycle_closed"
        assert conn.execute(
            text(
                "SELECT count(*) FROM brc_live_outcome_ledger "
                "WHERE ticket_id = :ticket_id"
            ),
            {"ticket_id": scope["ticket_id"]},
        ).scalar_one() == 1


class _FinalizerGateway:
    runtime_account_id = "owner-subaccount-runtime-v0"
    runtime_exchange_id = "binance_usdm"

    async def cancel_order(self, **kwargs):
        return SimpleNamespace(
            is_success=True,
            exchange_order_id=kwargs["exchange_order_id"],
        )

    async def place_order(self, **kwargs):
        return SimpleNamespace(
            is_success=True,
            exchange_order_id=f"exchange-{kwargs['client_order_id']}",
        )


def _prepare_reconciled_flat_exit(conn, *, leave_tp1_live: bool = False) -> str:
    set_id = _materialized_exit_protection_set(conn)
    protection = conn.execute(
        text(
            "SELECT ticket_id FROM brc_ticket_bound_exit_protection_sets "
            "WHERE exit_protection_set_id = :set_id"
        ),
        {"set_id": set_id},
    ).mappings().one()
    ticket_id = str(protection["ticket_id"])
    conn.execute(
        text(
            "UPDATE brc_ticket_bound_exit_protection_orders "
            "SET status = CASE WHEN role = 'SL' THEN 'filled' "
            "WHEN role = 'TP1' THEN :tp1_status ELSE status END, "
            "updated_at_ms = :now_ms WHERE exit_protection_set_id = :set_id"
        ),
        {
            "set_id": set_id,
            "tp1_status": "submitted" if leave_tp1_live else "cancelled",
            "now_ms": NOW_MS + 15_000,
        },
    )
    conn.execute(
        text(
            "UPDATE brc_ticket_bound_exit_protection_sets "
            "SET status = 'closed', reconciled_with_exchange = 1, "
            "first_blocker = NULL, blockers = :blockers, updated_at_ms = :now_ms "
            "WHERE exit_protection_set_id = :set_id"
        ),
        {"set_id": set_id, "blockers": json.dumps([]), "now_ms": NOW_MS + 15_000},
    )
    lifecycle = conn.execute(
        text(
            "SELECT * FROM brc_ticket_bound_order_lifecycle_runs "
            "WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ticket_id},
    ).mappings().one()
    conn.execute(
        text(
            "UPDATE brc_ticket_bound_order_lifecycle_runs "
            "SET status = 'reconciliation_matched', first_blocker = NULL, "
            "blockers = :blockers, updated_at_ms = :now_ms "
            "WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ticket_id, "blockers": json.dumps([]), "now_ms": NOW_MS + 15_000},
    )
    ticket = conn.execute(
        text("SELECT * FROM brc_action_time_tickets WHERE ticket_id = :ticket_id"),
        {"ticket_id": ticket_id},
    ).mappings().one()
    conn.execute(
        text(
            "INSERT INTO brc_ticket_bound_reconciliation_ticks ("
            "reconciliation_tick_id, ticket_id, protected_submit_attempt_id, "
            "tick_kind, status, strategy_group_id, symbol, side, entry_state, "
            "sl_state, tp1_state, position_state, first_blocker, blockers, warnings, "
            "next_action, exchange_snapshot_ref, exchange_snapshot_summary, "
            "visibility_deadline_ms, authority_boundary, created_at_ms, updated_at_ms"
            ") VALUES ("
            ":tick_id, :ticket_id, :attempt_id, 'scheduled', 'matched', "
            ":strategy_group_id, :symbol, :side, 'filled', 'filled', 'cancelled', "
            "'flat', NULL, :blockers, :warnings, 'finalize_lifecycle', :snapshot_ref, "
            ":snapshot, :deadline, 'test_reconciliation_truth', :now_ms, :now_ms)"
        ),
        {
            "tick_id": f"final-flat:{ticket_id}",
            "ticket_id": ticket_id,
            "attempt_id": lifecycle["protected_submit_attempt_id"],
            "strategy_group_id": ticket["strategy_group_id"],
            "symbol": ticket["symbol"],
            "side": ticket["side"],
            "blockers": json.dumps([]),
            "warnings": json.dumps([]),
            "snapshot_ref": f"snapshot:{ticket_id}",
            "snapshot": json.dumps({"position": {"qty": "0"}}),
            "deadline": NOW_MS + 16_000,
            "now_ms": NOW_MS + 15_000,
        },
    )
    return ticket_id


def _scalar(conn, statement: str, **params):
    return conn.execute(text(statement), params).scalar_one()
