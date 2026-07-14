from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from src.application.action_time.exchange_command_worker import (
    run_one_ticket_bound_exchange_command,
)
from src.application.action_time.exchange_scope import resolve_ticket_bound_exchange_scope
from src.application.action_time.external_close_attribution import (
    attribute_exact_ticket_bound_external_close,
)
from src.application.action_time.lifecycle_maintenance_scheduler import (
    run_ticket_bound_lifecycle_maintenance_scheduler,
    select_ticket_bound_lifecycle_maintenance_scopes,
)
from src.application.action_time.ticket_bound_lifecycle_finalizer import (
    _stable_id,
    finalize_ticket_bound_lifecycle_if_ready,
)
from src.application.action_time.ticket_bound_fill_projector import (
    project_ticket_bound_exchange_fills,
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
    assert first["lifecycle_decision"]["phase"] == "closed"
    assert first["lifecycle_decision"]["control_state"] == "completed"
    assert first["lifecycle_decision"]["owner_state"] == "completed"
    assert first["runtime_budget_mutated"] is True
    assert first["live_outcome_status"] == "recorded"
    assert second["status"] == "lifecycle_closed"
    assert second["lifecycle_decision"]["status"] == "lifecycle_closed"
    assert second["runtime_budget_mutated"] is False
    assert second["live_outcome_status"] == "recorded"
    assert _scalar(
        pg_control_connection,
        "SELECT status FROM brc_ticket_bound_order_lifecycle_runs",
    ) == "lifecycle_closed"
    assert _scalar(
        pg_control_connection,
        "SELECT status FROM brc_action_time_tickets WHERE ticket_id = :ticket_id",
        ticket_id=ticket_id,
    ) == "closed"
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


def test_finalizer_appends_exact_fact_repair_when_legacy_event_is_incomplete(
    pg_control_connection,
):
    ticket_id = _prepare_reconciled_flat_exit(pg_control_connection)
    lifecycle = pg_control_connection.execute(
        text(
            "SELECT lifecycle_run_id, protected_submit_attempt_id "
            "FROM brc_ticket_bound_order_lifecycle_runs "
            "WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ticket_id},
    ).mappings().one()
    reconciliation_tick_id = pg_control_connection.execute(
        text(
            "SELECT reconciliation_tick_id "
            "FROM brc_ticket_bound_reconciliation_ticks "
            "WHERE ticket_id = :ticket_id AND status = 'matched'"
        ),
        {"ticket_id": ticket_id},
    ).scalar_one()
    legacy_event_id = _stable_id(
        "ticket_lifecycle_event",
        str(lifecycle["lifecycle_run_id"]),
        "reconciliation_matched",
        str(reconciliation_tick_id),
    )
    pg_control_connection.execute(
        text(
            "INSERT INTO brc_ticket_bound_lifecycle_events ("
            "lifecycle_event_id, lifecycle_run_id, ticket_id, "
            "protected_submit_attempt_id, event_type, event_payload, created_at_ms"
            ") VALUES ("
            ":event_id, :lifecycle_run_id, :ticket_id, :attempt_id, "
            "'reconciliation_matched', :payload, :now_ms)"
        ),
        {
            "event_id": legacy_event_id,
            "lifecycle_run_id": lifecycle["lifecycle_run_id"],
            "ticket_id": ticket_id,
            "attempt_id": lifecycle["protected_submit_attempt_id"],
            "payload": json.dumps(
                {"reconciliation_evidence_id": reconciliation_tick_id}
            ),
            "now_ms": NOW_MS + 16_000,
        },
    )

    result = finalize_ticket_bound_lifecycle_if_ready(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_000,
    )

    assert result["status"] == "lifecycle_closed"
    assert _scalar(
        pg_control_connection,
        "SELECT count(*) FROM brc_ticket_bound_lifecycle_events "
        "WHERE ticket_id = :ticket_id AND event_type = 'reconciliation_matched'",
        ticket_id=ticket_id,
    ) == 2


def test_scheduler_selects_closed_incomplete_outcome_until_economics_are_complete(
    pg_control_connection,
):
    ticket_id = _prepare_reconciled_flat_exit(pg_control_connection)
    finalize_ticket_bound_lifecycle_if_ready(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_000,
    )

    selected = select_ticket_bound_lifecycle_maintenance_scopes(
        pg_control_connection,
        max_lifecycle_scopes=4,
    )
    assert [scope["ticket_id"] for scope in selected] == [ticket_id]

    pg_control_connection.execute(
        text(
            "UPDATE brc_live_outcome_ledger SET "
            "final_exit_time_ms = :final_exit_time_ms, final_exit_price = 1990, "
            "fees = 0.03, realized_pnl = -10, net_pnl = -10.03, "
            "r_multiple = -1 WHERE ticket_id = :ticket_id"
        ),
        {
            "ticket_id": ticket_id,
            "final_exit_time_ms": NOW_MS + 15_000,
        },
    )

    selected = select_ticket_bound_lifecycle_maintenance_scopes(
        pg_control_connection,
        max_lifecycle_scopes=4,
    )
    assert selected == []


@pytest.mark.asyncio
async def test_scheduler_repairs_closed_outcome_from_exact_tracked_fill(
    pg_control_connection,
):
    ticket_id = _prepare_reconciled_flat_exit(pg_control_connection)
    entry_event = pg_control_connection.execute(
        text(
            "SELECT lifecycle_event_id, event_payload FROM "
            "brc_ticket_bound_lifecycle_events "
            "WHERE ticket_id = :ticket_id AND event_type = 'entry_filled'"
        ),
        {"ticket_id": ticket_id},
    ).mappings().one()
    entry_payload = entry_event["event_payload"]
    if isinstance(entry_payload, str):
        entry_payload = json.loads(entry_payload)
    entry_payload["entry_fill"]["fee"] = {
        "cost": "0.01",
        "currency": "USDT",
    }
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_lifecycle_events SET event_payload = :payload "
            "WHERE lifecycle_event_id = :event_id"
        ),
        {
            "event_id": entry_event["lifecycle_event_id"],
            "payload": json.dumps(entry_payload),
        },
    )
    finalize_ticket_bound_lifecycle_if_ready(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_000,
    )
    scope = pg_control_connection.execute(
        text(
            "SELECT exit_protection_set_id, protected_submit_attempt_id "
            "FROM brc_ticket_bound_exit_protection_sets "
            "WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ticket_id},
    ).mappings().one()
    sl = pg_control_connection.execute(
        text(
            "SELECT exchange_order_id, qty FROM "
            "brc_ticket_bound_exit_protection_orders "
            "WHERE ticket_id = :ticket_id AND role = 'SL'"
        ),
        {"ticket_id": ticket_id},
    ).mappings().one()
    snapshot = {
        "snapshot_id": f"closed-repair:{ticket_id}",
        "open_orders": [],
        "recent_fills": [
            {
                "exchange_order_id": sl["exchange_order_id"],
                "qty": str(sl["qty"]),
                "price": "1990",
                "fee": {"cost": "0.03", "currency": "USDT"},
                "timestamp_ms": NOW_MS + 15_000,
            }
        ],
        "funding_income": [],
        "position": {
            "qty": "0",
            "position_flat": True,
            "truth_state": "flat",
            "complete": True,
        },
    }

    payload = await run_ticket_bound_lifecycle_maintenance_scheduler(
        pg_control_connection,
        gateway=None,
        allow_exchange_mutation=False,
        fetch_exchange_snapshot=False,
        max_lifecycle_scopes=4,
        provided_exchange_snapshots={
            identity: {
                "status": "snapshot_ready",
                "snapshot": snapshot,
                "exchange_read_called": True,
                "blockers": [],
            }
            for identity in (
                str(scope["exit_protection_set_id"]),
                str(scope["protected_submit_attempt_id"]),
            )
        },
        now_ms=NOW_MS + 30_000,
    )

    assert payload["status"] == "scheduler_complete", payload
    outcome = pg_control_connection.execute(
        text(
            "SELECT final_exit_time_ms, final_exit_price, fees, realized_pnl, "
            "net_pnl, r_multiple FROM brc_live_outcome_ledger "
            "WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ticket_id},
    ).mappings().one()
    assert outcome["final_exit_time_ms"] == NOW_MS + 15_000
    assert outcome["final_exit_price"] == 1990
    assert Decimal(str(outcome["fees"])) == Decimal("0.04")
    assert outcome["realized_pnl"] is not None
    assert outcome["net_pnl"] is not None
    assert outcome["r_multiple"] is not None
    assert _scalar(
        pg_control_connection,
        "SELECT status FROM brc_action_time_tickets WHERE ticket_id = :ticket_id",
        ticket_id=ticket_id,
    ) == "closed"


def test_legitimate_external_close_stops_lineage_repair_after_exact_review(
    pg_control_connection,
):
    ticket_id = _prepare_reconciled_flat_exit(pg_control_connection)
    finalize_ticket_bound_lifecycle_if_ready(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_000,
    )
    pg_control_connection.execute(
        text(
            "UPDATE brc_live_outcome_ledger SET "
            "final_exit_time_ms = :final_exit_time_ms, final_exit_price = 2010, "
            "fees = 0.03, realized_pnl = 10, net_pnl = 9.97, "
            "r_multiple = 1 WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ticket_id, "final_exit_time_ms": NOW_MS + 15_000},
    )
    closure = pg_control_connection.execute(
        text(
            "SELECT post_submit_closure_id, reconciliation_evidence "
            "FROM brc_ticket_bound_post_submit_closures "
            "WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ticket_id},
    ).mappings().one()
    evidence = closure["reconciliation_evidence"]
    if isinstance(evidence, str):
        evidence = json.loads(evidence)
    evidence.update(
        {
            "final_exit_role": "EXTERNAL_CLOSE",
            "final_exit_exchange_order_id": "manual-close-1",
        }
    )
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_post_submit_closures "
            "SET reconciliation_evidence = :evidence "
            "WHERE post_submit_closure_id = :closure_id"
        ),
        {
            "closure_id": closure["post_submit_closure_id"],
            "evidence": json.dumps(evidence),
        },
    )
    assert [
        scope["ticket_id"]
        for scope in select_ticket_bound_lifecycle_maintenance_scopes(
            pg_control_connection,
            max_lifecycle_scopes=4,
        )
    ] == [ticket_id]

    project_ticket_bound_exchange_fills(
        pg_control_connection,
        ticket_id=ticket_id,
        exchange_snapshot={
            "recent_fills": [
                {
                    "exchange_order_id": "manual-close-1",
                    "qty": "0.5",
                    "price": "2010",
                    "timestamp_ms": NOW_MS + 15_000,
                }
            ],
            "conditional_order_lineage": [],
            "conditional_order_lineage_available": True,
        },
        now_ms=NOW_MS + 30_000,
    )

    assert select_ticket_bound_lifecycle_maintenance_scopes(
        pg_control_connection,
        max_lifecycle_scopes=4,
    ) == []


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
    assert payload["lifecycle_decision"]["status"] == (
        "position_closed_protection_live"
    )
    assert payload["lifecycle_decision"]["control_state"] == "recovery_required"
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
    entry_event = pg_control_connection.execute(
        text(
            "SELECT lifecycle_event_id, event_payload FROM "
            "brc_ticket_bound_lifecycle_events "
            "WHERE ticket_id = :ticket_id AND event_type = 'entry_filled'"
        ),
        {"ticket_id": scope["ticket_id"]},
    ).mappings().one()
    entry_payload = entry_event["event_payload"]
    if isinstance(entry_payload, str):
        entry_payload = json.loads(entry_payload)
    entry_payload["entry_fill"]["fee"] = {
        "cost": "0.01",
        "currency": "USDT",
    }
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_lifecycle_events SET event_payload = :payload "
            "WHERE lifecycle_event_id = :event_id"
        ),
        {
            "event_id": entry_event["lifecycle_event_id"],
            "payload": json.dumps(entry_payload),
        },
    )
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


@pytest.mark.asyncio
async def test_production_scheduler_closes_exactly_attributed_manual_exchange_exit(
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
    orders = {
        str(row["role"]): dict(row)
        for row in pg_control_connection.execute(
            text(
                "SELECT role, exchange_order_id, qty, price "
                "FROM brc_ticket_bound_exit_protection_orders "
                "WHERE exit_protection_set_id = :set_id"
            ),
            {"set_id": set_id},
        ).mappings()
    }
    lifecycle = pg_control_connection.execute(
        text(
            "SELECT entry_exchange_order_id, entry_filled_qty, entry_avg_price "
            "FROM brc_ticket_bound_order_lifecycle_runs "
            "WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": scope["ticket_id"]},
    ).mappings().one()
    manual_exit_qty = lifecycle["entry_filled_qty"] - orders["TP1"]["qty"]
    snapshot = {
        "snapshot_ref": f"unit-manual-exit:{set_id}",
        "symbol": "ETHUSDT",
        "exchange_symbol": "ETH/USDT:USDT",
        "open_orders": [],
        "recent_fills": [
            {
                "exchange_order_id": lifecycle["entry_exchange_order_id"],
                "symbol": "ETH/USDT:USDT",
                "side": "buy",
                "position_side": "BOTH",
                "qty": str(lifecycle["entry_filled_qty"]),
                "price": str(lifecycle["entry_avg_price"]),
                "timestamp_ms": NOW_MS + 5_000,
            },
            {
                "exchange_order_id": orders["TP1"]["exchange_order_id"],
                "symbol": "ETH/USDT:USDT",
                "side": "sell",
                "position_side": "BOTH",
                "qty": str(orders["TP1"]["qty"]),
                "price": str(orders["TP1"]["price"]),
                "timestamp_ms": NOW_MS + 20_000,
            },
            {
                "exchange_order_id": "exchange-owner-manual-exit-1",
                "symbol": "ETH/USDT:USDT",
                "side": "sell",
                "position_side": "BOTH",
                "qty": str(manual_exit_qty),
                "price": "2010",
                "realized_pnl": "0.05",
                "timestamp_ms": NOW_MS + 21_000,
            },
        ],
        "position": {
            "qty": "0",
            "side": "long",
            "position_side": "BOTH",
            "position_mode": "one_way",
            "position_flat": True,
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
    resolved = resolve_ticket_bound_exchange_scope(
        pg_control_connection,
        ticket_id=str(scope["ticket_id"]),
        now_ms=NOW_MS + 21_500,
    )
    external_fill, attribution_blockers = attribute_exact_ticket_bound_external_close(
        pg_control_connection,
        lifecycle=dict(
            pg_control_connection.execute(
                text(
                    "SELECT * FROM brc_ticket_bound_order_lifecycle_runs "
                    "WHERE ticket_id = :ticket_id"
                ),
                {"ticket_id": scope["ticket_id"]},
            ).mappings().one()
        ),
        orders=[
            dict(row)
            for row in pg_control_connection.execute(
                text(
                    "SELECT * FROM brc_ticket_bound_exit_protection_orders "
                    "WHERE ticket_id = :ticket_id"
                ),
                {"ticket_id": scope["ticket_id"]},
            ).mappings()
        ],
        exchange_scope=resolved.scope,
        recent_fills=snapshot["recent_fills"],
        position=snapshot["position"],
    )
    assert attribution_blockers == []
    assert external_fill["exchange_order_id"] == "exchange-owner-manual-exit-1"

    payload = await run_ticket_bound_lifecycle_maintenance_scheduler(
        pg_control_connection,
        provided_exchange_snapshots=provided,
        fetch_exchange_snapshot=False,
        allow_exchange_mutation=False,
        now_ms=NOW_MS + 22_000,
    )
    assert payload["exchange_write_called"] is False
    assert _scalar(
        pg_control_connection,
        "SELECT status FROM brc_ticket_bound_order_lifecycle_runs "
        "WHERE ticket_id = :ticket_id",
        ticket_id=scope["ticket_id"],
    ) == "lifecycle_closed", payload
    reconciliation = pg_control_connection.execute(
        text(
            "SELECT reconciliation_evidence "
            "FROM brc_ticket_bound_post_submit_closures "
            "WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": scope["ticket_id"]},
    ).scalar_one()
    if isinstance(reconciliation, str):
        reconciliation = json.loads(reconciliation)
    assert reconciliation["final_exit_role"] == "EXTERNAL_CLOSE"
    assert reconciliation["final_exit_exchange_order_id"] == (
        "exchange-owner-manual-exit-1"
    )
    final_event = pg_control_connection.execute(
        text(
            "SELECT event_payload FROM brc_ticket_bound_lifecycle_events "
            "WHERE ticket_id = :ticket_id AND event_type = 'final_exit_detected' "
            "ORDER BY created_at_ms DESC LIMIT 1"
        ),
        {"ticket_id": scope["ticket_id"]},
    ).scalar_one()
    if isinstance(final_event, str):
        final_event = json.loads(final_event)
    assert final_event["fill"]["role"] == "EXTERNAL_CLOSE"
    assert final_event["fill"]["fill_qty"] == str(manual_exit_qty)
    assert _scalar(
        pg_control_connection,
        "SELECT status FROM brc_budget_reservations WHERE ticket_id = :ticket_id",
        ticket_id=scope["ticket_id"],
    ) == "released"


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
