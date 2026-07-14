from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from scripts import materialize_ticket_bound_runner_protection_adjustment as runner_adjuster
from src.application.action_time.capital_safety_guard import current_scope_blockers
from src.application.action_time.protection_reconciler import (
    reconcile_ticket_bound_exit_protection_set,
)
from src.application.action_time.ticket_bound_fill_projector import (
    project_ticket_bound_exchange_fills,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_runner_protection_adjuster import (
    _mark_tp1_filled,
    _materialized_exit_protection_set,
    _record_official_runner_mutation_result,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


def test_protection_reconciler_marks_complete_set_reconciled(pg_control_connection):
    set_id = _materialized_exit_protection_set(pg_control_connection)

    payload = reconcile_ticket_bound_exit_protection_set(
        pg_control_connection,
        exit_protection_set_id=set_id,
        exchange_snapshot=_snapshot(pg_control_connection, set_id),
        now_ms=NOW_MS + 9000,
    )

    assert payload["status"] == "reconciled"
    assert payload["blockers"] == []
    protection_set = _one(
        pg_control_connection,
        "brc_ticket_bound_exit_protection_sets",
        "exit_protection_set_id",
        set_id,
    )
    assert protection_set["status"] == "reconciled"
    assert protection_set["reconciled_with_exchange"] in {True, 1}
    assert _lifecycle_status(pg_control_connection) == "position_protected"


def test_protection_reconciler_does_not_append_duplicate_unchanged_events(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    snapshot = _snapshot(pg_control_connection, set_id)

    first = reconcile_ticket_bound_exit_protection_set(
        pg_control_connection,
        exit_protection_set_id=set_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 9_000,
    )
    second = reconcile_ticket_bound_exit_protection_set(
        pg_control_connection,
        exit_protection_set_id=set_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 10_000,
    )

    assert first["status"] == "reconciled"
    assert second["status"] == "reconciled"
    assert pg_control_connection.execute(
        text(
            "SELECT count(*) FROM brc_ticket_bound_lifecycle_events "
            "WHERE event_type = 'exit_protection_reconciled'"
        )
    ).scalar_one() == 1


def test_protection_reconciler_does_not_resolve_another_sources_scope_hold(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    _insert_scope_freeze(pg_control_connection, first_blocker="protection_missing")

    payload = reconcile_ticket_bound_exit_protection_set(
        pg_control_connection,
        exit_protection_set_id=set_id,
        exchange_snapshot=_snapshot(pg_control_connection, set_id),
        now_ms=NOW_MS + 9000,
    )

    assert payload["status"] == "reconciled"
    freeze = dict(
        pg_control_connection.execute(
            text("SELECT * FROM brc_ticket_bound_scope_freezes")
        ).mappings().one()
    )
    assert freeze["status"] == "active"
    assert freeze["first_blocker"] == "protection_missing"


def test_protection_reconciler_flags_missing_exchange_sl(pg_control_connection):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    snapshot = _snapshot(pg_control_connection, set_id, omit_roles={"SL"})

    payload = reconcile_ticket_bound_exit_protection_set(
        pg_control_connection,
        exit_protection_set_id=set_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 9000,
    )

    assert payload["status"] == "protection_reconciliation_mismatch"
    assert "sl_exchange_order_missing" in payload["blockers"]
    assert payload["lifecycle_decision"] == {
        "status": "protection_reconciliation_mismatch",
        "phase": "open",
        "protection_state": "unknown",
        "reconciliation_state": "mismatch",
        "control_state": "recovery_required",
        "owner_state": "processing",
        "next_action": "run_exchange_protection_reconciler",
        "owner_action_required": False,
    }
    assert _lifecycle_status(pg_control_connection) == "protection_reconciliation_mismatch"


def test_protection_reconciler_blocks_unowned_entry_order_in_same_domain(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    snapshot = _snapshot(pg_control_connection, set_id)
    snapshot["open_orders"].append(
        {
            "exchange_order_id": "exchange-unrelated-entry",
            "qty": "0.5",
            "side": "buy",
            "reduce_only": False,
            "status": "open",
        }
    )

    payload = reconcile_ticket_bound_exit_protection_set(
        pg_control_connection,
        exit_protection_set_id=set_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 9000,
    )

    assert payload["status"] == "exchange_orphan_detected"
    assert payload["blockers"] == ["exchange_only_unknown_order"]
    assert _lifecycle_status(pg_control_connection) == "exchange_orphan_detected"


def test_protection_reconciler_flags_linked_protection_side_mismatch(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    snapshot = _snapshot(pg_control_connection, set_id)
    for order in snapshot["open_orders"]:
        if order["exchange_order_id"] == "exchange-sl-1":
            order["side"] = "buy"

    payload = reconcile_ticket_bound_exit_protection_set(
        pg_control_connection,
        exit_protection_set_id=set_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 9000,
    )

    assert payload["status"] == "protection_reconciliation_mismatch"
    assert "sl_side_mismatch" in payload["blockers"]
    assert _lifecycle_status(pg_control_connection) == "protection_reconciliation_mismatch"


def test_protection_reconciler_flags_linked_protection_qty_exceeds_position(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    snapshot = _snapshot(pg_control_connection, set_id)
    for order in snapshot["open_orders"]:
        if order["exchange_order_id"] == "exchange-sl-1":
            order["qty"] = "9"
    snapshot["position"]["qty"] = "0.5"

    payload = reconcile_ticket_bound_exit_protection_set(
        pg_control_connection,
        exit_protection_set_id=set_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 9000,
    )

    assert payload["status"] == "protection_reconciliation_mismatch"
    assert "sl_qty_exceeds_position" in payload["blockers"]
    assert _lifecycle_status(pg_control_connection) == "protection_reconciliation_mismatch"


def test_protection_reconciler_flags_tp1_fill_without_runner_sl(pg_control_connection):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    _mark_tp1_filled(pg_control_connection, set_id)
    snapshot = _snapshot(pg_control_connection, set_id, omit_roles={"TP1"})
    snapshot["recent_fills"] = [{"exchange_order_id": "exchange-tp1-1"}]
    snapshot["position"]["qty"] = "0.25"

    payload = reconcile_ticket_bound_exit_protection_set(
        pg_control_connection,
        exit_protection_set_id=set_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 9000,
    )

    assert payload["status"] == "runner_mutation_pending"
    assert "tp1_filled_without_runner_sl" in payload["blockers"]
    assert _lifecycle_status(pg_control_connection) == "runner_mutation_pending"


def test_protection_reconciler_accepts_runner_sl_after_old_sl_cancelled(
    pg_control_connection,
):
    set_id = _materialized_runner_protection(pg_control_connection)
    snapshot = _snapshot(pg_control_connection, set_id, omit_roles={"SL", "TP1"})
    snapshot["recent_fills"] = [{"exchange_order_id": "exchange-tp1-1"}]
    snapshot["position"]["qty"] = "0.25"

    payload = reconcile_ticket_bound_exit_protection_set(
        pg_control_connection,
        exit_protection_set_id=set_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 9000,
    )

    assert payload["status"] == "runner_protected"
    assert payload["blockers"] == []
    assert _lifecycle_status(pg_control_connection) == "runner_protected"
    protection_set = _one(
        pg_control_connection,
        "brc_ticket_bound_exit_protection_sets",
        "exit_protection_set_id",
        set_id,
    )
    assert protection_set["status"] == "runner_protected"
    assert protection_set["reconciled_with_exchange"] in {True, 1}


def test_protection_reconciler_flags_old_sl_still_live_after_runner_mutation(
    pg_control_connection,
):
    set_id = _materialized_runner_protection(pg_control_connection)
    snapshot = _snapshot(pg_control_connection, set_id, omit_roles={"TP1"})
    snapshot["recent_fills"] = [{"exchange_order_id": "exchange-tp1-1"}]
    snapshot["position"]["qty"] = "0.25"

    payload = reconcile_ticket_bound_exit_protection_set(
        pg_control_connection,
        exit_protection_set_id=set_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 9000,
    )

    assert payload["status"] == "runner_reconciliation_mismatch"
    assert "old_sl_still_live_after_runner_mutation" in payload["blockers"]
    assert _lifecycle_status(pg_control_connection) == "runner_reconciliation_mismatch"


def test_protection_reconciler_flags_flat_position_with_live_protection(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    snapshot = _snapshot(pg_control_connection, set_id)
    snapshot["position"] = {"qty": "0", "position_flat": True}

    payload = reconcile_ticket_bound_exit_protection_set(
        pg_control_connection,
        exit_protection_set_id=set_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 9000,
    )

    assert payload["status"] == "position_closed_protection_live"
    assert "position_flat_with_live_protection_orders" in payload["blockers"]
    assert _lifecycle_status(pg_control_connection) == "position_closed_protection_live"


def test_protection_reconciler_blocks_missing_position_snapshot_without_flat_inference(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    snapshot = _snapshot(pg_control_connection, set_id)
    snapshot.pop("position")

    payload = reconcile_ticket_bound_exit_protection_set(
        pg_control_connection,
        exit_protection_set_id=set_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 9000,
    )

    assert payload["status"] == "protection_reconciliation_mismatch"
    assert payload["first_blocker"] == "exchange_position_snapshot_missing"
    assert payload["lifecycle_decision"]["next_action"] == (
        "refresh_exchange_position_snapshot"
    )
    assert payload["lifecycle_decision"]["control_state"] == "recovery_required"
    assert "exchange_position_snapshot_missing" in payload["blockers"]
    assert "position_flat_with_live_protection_orders" not in payload["blockers"]
    assert _lifecycle_status(pg_control_connection) == "protection_reconciliation_mismatch"


def test_protection_reconciler_rejects_ambiguous_untracked_flat_exit_fills(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    lifecycle = pg_control_connection.execute(
        text(
            "SELECT entry_exchange_order_id, entry_filled_qty, entry_avg_price "
            "FROM brc_ticket_bound_order_lifecycle_runs"
        )
    ).mappings().one()
    tp1 = pg_control_connection.execute(
        text(
            "SELECT exchange_order_id, qty, price "
            "FROM brc_ticket_bound_exit_protection_orders "
            "WHERE exit_protection_set_id = :set_id AND role = 'TP1'"
        ),
        {"set_id": set_id},
    ).mappings().one()
    remaining = Decimal(str(lifecycle["entry_filled_qty"])) - Decimal(str(tp1["qty"]))
    first_part = remaining / Decimal("2")
    second_part = remaining - first_part
    snapshot = {
        "snapshot_id": f"snapshot:ambiguous-external:{set_id}",
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
                "exchange_order_id": tp1["exchange_order_id"],
                "symbol": "ETH/USDT:USDT",
                "side": "sell",
                "position_side": "BOTH",
                "qty": str(tp1["qty"]),
                "price": str(tp1["price"]),
                "timestamp_ms": NOW_MS + 7_000,
            },
            {
                "exchange_order_id": "manual-exit-part-a",
                "symbol": "ETH/USDT:USDT",
                "side": "sell",
                "position_side": "BOTH",
                "qty": str(first_part),
                "price": "2010",
                "timestamp_ms": NOW_MS + 8_000,
            },
            {
                "exchange_order_id": "manual-exit-part-b",
                "symbol": "ETH/USDT:USDT",
                "side": "sell",
                "position_side": "BOTH",
                "qty": str(second_part),
                "price": "2011",
                "timestamp_ms": NOW_MS + 8_100,
            },
        ],
        "position": {
            "qty": "0",
            "position_flat": True,
            "truth_state": "flat",
        },
    }

    payload = reconcile_ticket_bound_exit_protection_set(
        pg_control_connection,
        exit_protection_set_id=set_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 9_000,
    )

    assert "external_close_fill_attribution_ambiguous" in payload["blockers"]
    assert _lifecycle_status(pg_control_connection) != "reconciliation_matched"
    assert pg_control_connection.execute(
        text("SELECT count(*) FROM brc_ticket_bound_post_submit_closures WHERE status = 'closed'")
    ).scalar_one() == 0


def test_protection_reconciler_attributes_conditional_child_fill_to_sl_parent(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    lifecycle = pg_control_connection.execute(
        text(
            "SELECT entry_exchange_order_id, entry_filled_qty, entry_avg_price "
            "FROM brc_ticket_bound_order_lifecycle_runs"
        )
    ).mappings().one()
    sl = pg_control_connection.execute(
        text(
            "SELECT exit_protection_order_id, exchange_order_id, qty "
            "FROM brc_ticket_bound_exit_protection_orders "
            "WHERE exit_protection_set_id = :set_id AND role = 'SL'"
        ),
        {"set_id": set_id},
    ).mappings().one()
    child_order_id = "39574198157"
    snapshot = {
        "snapshot_id": f"snapshot:conditional-sl:{set_id}",
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
                "exchange_order_id": child_order_id,
                "parent_exchange_order_id": sl["exchange_order_id"],
                "symbol": "ETH/USDT:USDT",
                "side": "sell",
                "position_side": "BOTH",
                "qty": str(sl["qty"]),
                "price": "1990",
                "fee": {"cost": "0.02", "currency": "USDT"},
                "timestamp_ms": NOW_MS + 8_000,
            },
        ],
        "conditional_order_lineage_available": True,
        "position": {
            "qty": "0",
            "position_flat": True,
            "truth_state": "flat",
            "complete": True,
        },
    }

    projection = project_ticket_bound_exchange_fills(
        pg_control_connection,
        ticket_id=pg_control_connection.execute(
            text(
                "SELECT ticket_id FROM brc_ticket_bound_exit_protection_sets "
                "WHERE exit_protection_set_id = :set_id"
            ),
            {"set_id": set_id},
        ).scalar_one(),
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 8_500,
    )
    assert projection["projected_roles"] == ["SL"]

    payload = reconcile_ticket_bound_exit_protection_set(
        pg_control_connection,
        exit_protection_set_id=set_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 9_000,
    )

    assert payload["status"] == "reconciliation_matched"
    stored_sl = pg_control_connection.execute(
        text(
            "SELECT status FROM brc_ticket_bound_exit_protection_orders "
            "WHERE exit_protection_order_id = :order_id"
        ),
        {"order_id": sl["exit_protection_order_id"]},
    ).scalar_one()
    assert stored_sl == "filled"
    final_fill = pg_control_connection.execute(
        text(
            "SELECT event_payload FROM brc_ticket_bound_lifecycle_events "
            "WHERE event_type = 'final_exit_detected'"
        )
    ).mappings().one()
    final_payload = final_fill["event_payload"]
    if isinstance(final_payload, str):
        import json

        final_payload = json.loads(final_payload)
    assert final_payload["fill"]["role"] == "SL"
    assert final_payload["fill"]["exchange_order_id"] == (
        child_order_id
    )
    assert final_payload["fill"][
        "parent_exchange_order_id"
    ] == sl["exchange_order_id"]


def test_protection_reconciler_fails_closed_when_conditional_lineage_read_failed(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    lifecycle = pg_control_connection.execute(
        text(
            "SELECT entry_exchange_order_id, entry_filled_qty, entry_avg_price "
            "FROM brc_ticket_bound_order_lifecycle_runs"
        )
    ).mappings().one()
    snapshot = {
        "snapshot_id": f"snapshot:conditional-lineage-failed:{set_id}",
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
                "exchange_order_id": "unresolved-trigger-child",
                "symbol": "ETH/USDT:USDT",
                "side": "sell",
                "position_side": "BOTH",
                "qty": str(lifecycle["entry_filled_qty"]),
                "price": "1990",
                "timestamp_ms": NOW_MS + 8_000,
            },
        ],
        "conditional_order_lineage_available": False,
        "conditional_order_lineage_error": "NetworkError",
        "position": {
            "qty": "0",
            "position_flat": True,
            "truth_state": "flat",
            "complete": True,
        },
    }

    payload = reconcile_ticket_bound_exit_protection_set(
        pg_control_connection,
        exit_protection_set_id=set_id,
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 9_000,
    )

    assert payload["status"] != "reconciliation_matched"
    assert payload["first_blocker"] == "conditional_order_lineage_unavailable"
    assert pg_control_connection.execute(
        text(
            "SELECT count(*) FROM brc_ticket_bound_lifecycle_events "
            "WHERE event_type = 'final_exit_detected'"
        )
    ).scalar_one() == 0


def _materialized_runner_protection(conn) -> str:
    set_id = _materialized_exit_protection_set(conn)
    _mark_tp1_filled(conn, set_id)
    _record_official_runner_mutation_result(
        conn,
        set_id,
        runner_exchange_id="exchange-runner-sl-1",
        now_ms=NOW_MS + 7500,
    )
    payload = runner_adjuster.materialize_ticket_bound_runner_protection_adjustment(
        conn,
        exit_protection_set_id=set_id,
        runner_sl_exchange_order_id="exchange-runner-sl-1",
        runner_sl_local_order_id="runner-sl-1",
        now_ms=NOW_MS + 8000,
    )
    assert payload["status"] == "runner_protected"
    return set_id


def _snapshot(conn, set_id: str, *, omit_roles: set[str] | None = None) -> dict:
    omit_roles = omit_roles or set()
    orders = [
        dict(row)
        for row in conn.execute(
            text(
                """
                SELECT role, exchange_order_id, qty, side, reduce_only
                FROM brc_ticket_bound_exit_protection_orders
                WHERE exit_protection_set_id = :set_id
                ORDER BY role
                """
            ),
            {"set_id": set_id},
        ).mappings()
        if row["role"] not in omit_roles
    ]
    return {
        "snapshot_id": f"snapshot:{set_id}",
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
        "position": {"qty": "0.5", "position_flat": False},
    }


def _one(conn, table_name: str, id_column: str, id_value: str):
    row = conn.execute(
        text(f"SELECT * FROM {table_name} WHERE {id_column} = :id_value"),
        {"id_value": id_value},
    ).mappings().one()
    return dict(row)


def _lifecycle_status(conn) -> str:
    return str(
        conn.execute(
            text("SELECT status FROM brc_ticket_bound_order_lifecycle_runs")
        ).scalar_one()
    )


def _insert_scope_freeze(conn, *, first_blocker: str) -> None:
    conn.execute(
        text(
            """
            INSERT INTO brc_ticket_bound_scope_freezes (
              scope_freeze_id, strategy_group_id, symbol, side, status,
              source_kind, source_id, first_blocker, blockers, freeze_scope,
              next_action, authority_boundary, created_at_ms, updated_at_ms
            ) VALUES (
              'freeze:SOR-001:ETHUSDT:long', 'SOR-001', 'ETHUSDT', 'long', 'active',
              'unit_test', 'unit_test_freeze', :first_blocker, :blockers,
              :freeze_scope, 'repair_scope', 'unit_test', :now_ms, :now_ms
            )
            """
        ),
        {
            "first_blocker": first_blocker,
            "blockers": f'["{first_blocker}"]',
            "freeze_scope": (
                '{"strategy_group_id":"SOR-001","symbol":"ETHUSDT","side":"long"}'
            ),
            "now_ms": NOW_MS + 8500,
        },
    )
