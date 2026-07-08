from __future__ import annotations

import json

from sqlalchemy import text

from scripts import materialize_ticket_bound_exit_protection_set as exit_protection
from scripts import materialize_ticket_bound_post_submit_closure as closure
from scripts import materialize_ticket_bound_protected_submit_attempt as submit
from scripts import materialize_ticket_bound_runner_protection_adjustment as runner_adjuster
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_protected_submit_attempt import (
    _create_ready_protected_submit,
    _json_value,
    _submitted_orders,
)
from tests.unit.test_ticket_bound_runner_protection_adjuster import (
    _record_official_runner_mutation_result,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


def test_post_submit_closure_records_reconciliation_pending_after_submitted_attempt(
    pg_control_connection,
):
    ids, prepared = _submitted_attempt(pg_control_connection)

    payload = closure.materialize_ticket_bound_post_submit_closure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )

    assert payload["status"] == "reconciliation_pending"
    assert payload["ticket_id"] == ids["ticket_id"]
    assert payload["operation_submit_command_id"] == ids["operation_submit_command_id"]
    assert payload["protection_state"] == "submitted"
    assert payload["reconciliation_state"] == "not_checked"
    assert payload["settlement_state"] == "blocked"
    assert payload["review_state"] == "blocked"
    assert payload["first_blocker"] == "post_submit_reconciliation_fact_missing"
    assert payload["exchange_write_called"] is False
    assert payload["order_created"] is False
    assert payload["order_lifecycle_called"] is False

    row = _closure_row(pg_control_connection)
    assert row["status"] == "reconciliation_pending"
    assert row["protected_submit_attempt_id"] == prepared["protected_submit_attempt_id"]
    assert _json_value(row["blockers"]) == ["post_submit_reconciliation_fact_missing"]
    assert len(_json_value(row["submitted_order_refs"])) == 3


def test_post_submit_closure_blocks_when_attempt_not_submitted(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="real_gateway_action",
        now_ms=NOW_MS + 4000,
    )

    payload = closure.materialize_ticket_bound_post_submit_closure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )

    assert payload["status"] == "blocked"
    assert "protected_submit_attempt_not_submitted:submit_prepared" in payload["blockers"]
    assert payload["reconciliation_state"] == "blocked"
    assert payload["settlement_state"] == "blocked"
    assert payload["review_state"] == "blocked"


def test_post_submit_closure_blocks_without_exit_protection_set(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _record_submitted_attempt(pg_control_connection, ids)

    payload = closure.materialize_ticket_bound_post_submit_closure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )

    assert payload["status"] == "blocked"
    assert payload["protection_state"] == "missing"
    assert "ticket_bound_exit_protection_set_missing" in payload["blockers"]


def test_post_submit_closure_refreshes_blocked_after_protection_set_materialized(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _record_submitted_attempt(pg_control_connection, ids)
    blocked = closure.materialize_ticket_bound_post_submit_closure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )

    protection = exit_protection.materialize_ticket_bound_exit_protection_set(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 7000,
    )
    refreshed = closure.materialize_ticket_bound_post_submit_closure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 8000,
    )

    assert blocked["status"] == "blocked"
    assert "ticket_bound_exit_protection_set_missing" in blocked["blockers"]
    assert protection["status"] == "position_protected"
    assert refreshed["status"] == "reconciliation_pending"
    assert refreshed["protection_state"] == "submitted"
    assert refreshed["blockers"] == ["post_submit_reconciliation_fact_missing"]
    assert "idempotent_existing_closure" not in refreshed
    row = _closure_row(pg_control_connection)
    assert row["status"] == "reconciliation_pending"
    assert _json_value(row["blockers"]) == ["post_submit_reconciliation_fact_missing"]


def test_post_submit_closure_refreshes_reconciliation_pending_projection(
    pg_control_connection,
):
    _, prepared = _submitted_attempt(pg_control_connection)
    first = closure.materialize_ticket_bound_post_submit_closure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )
    second = closure.materialize_ticket_bound_post_submit_closure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 7000,
    )

    assert second["status"] == first["status"]
    assert "idempotent_existing_closure" not in second
    assert second["post_submit_closure_id"] == first["post_submit_closure_id"]
    row = _closure_row(pg_control_connection)
    assert row["created_at_ms"] == NOW_MS + 6000
    assert row["updated_at_ms"] == NOW_MS + 7000


def test_post_submit_closure_refreshes_pending_after_protection_mismatch(
    pg_control_connection,
):
    _, prepared = _submitted_attempt(pg_control_connection)
    first = closure.materialize_ticket_bound_post_submit_closure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )
    assert first["status"] == "reconciliation_pending"
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_ticket_bound_exit_protection_sets
            SET status = 'failed',
                protection_complete = 0,
                first_blocker = 'protection_reconciliation_mismatch',
                blockers = '["protection_reconciliation_mismatch"]',
                updated_at_ms = :updated_at_ms
            WHERE protected_submit_attempt_id = :attempt_id
            """
        ),
        {
            "attempt_id": prepared["protected_submit_attempt_id"],
            "updated_at_ms": NOW_MS + 6500,
        },
    )

    refreshed = closure.materialize_ticket_bound_post_submit_closure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 7000,
    )

    assert refreshed["status"] == "blocked"
    assert "idempotent_existing_closure" not in refreshed
    assert "exit_protection_set_status:failed" in refreshed["blockers"]
    assert "exit_protection_set_not_complete" in refreshed["blockers"]
    row = _closure_row(pg_control_connection)
    assert row["status"] == "blocked"
    assert row["created_at_ms"] == NOW_MS + 6000
    assert row["updated_at_ms"] == NOW_MS + 7000


def test_lifecycle_closure_blocks_without_final_exit_proofs(pg_control_connection):
    _, prepared = _runner_protected_attempt(pg_control_connection)

    payload = closure.materialize_ticket_bound_lifecycle_closure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        final_exit_exchange_order_id="",
        final_position_flat_confirmed=False,
        reconciliation_evidence_id="",
        settlement_evidence_id="",
        review_evidence_id="",
        now_ms=NOW_MS + 9000,
    )

    assert payload["status"] == "blocked"
    assert "final_exit_exchange_order_id_required" in payload["blockers"]
    assert "final_position_flat_not_confirmed" in payload["blockers"]
    assert "reconciliation_evidence_id_required" in payload["blockers"]
    assert "settlement_evidence_id_required" in payload["blockers"]
    assert "review_evidence_id_required" in payload["blockers"]
    assert _one(pg_control_connection, "brc_ticket_bound_order_lifecycle_runs")[
        "status"
    ] == "runner_protected"


def test_lifecycle_closure_records_final_exit_reconciliation_settlement_review(
    pg_control_connection,
):
    _, prepared = _runner_protected_attempt(pg_control_connection)
    _record_closure_evidence_events(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        reconciliation_evidence_id="recon-1",
        settlement_evidence_id="settlement-1",
        review_evidence_id="review-1",
        now_ms=NOW_MS + 8500,
    )

    payload = closure.materialize_ticket_bound_lifecycle_closure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        final_exit_exchange_order_id="exchange-runner-sl-1",
        final_exit_role="RUNNER_SL",
        final_position_flat_confirmed=True,
        reconciliation_evidence_id="recon-1",
        settlement_evidence_id="settlement-1",
        review_evidence_id="review-1",
        realized_pnl="12.34",
        now_ms=NOW_MS + 9000,
    )

    assert payload["status"] == "closed"
    assert payload["reconciliation_state"] == "matched"
    assert payload["settlement_state"] == "released"
    assert payload["review_state"] == "recorded"
    assert payload["blockers"] == []
    assert payload["reconciliation_evidence"]["reconciliation_evidence_id"] == "recon-1"
    assert payload["settlement_evidence"]["settlement_evidence_id"] == "settlement-1"
    assert payload["review_evidence"]["review_evidence_id"] == "review-1"

    lifecycle = _one(pg_control_connection, "brc_ticket_bound_order_lifecycle_runs")
    protection_set = _one(pg_control_connection, "brc_ticket_bound_exit_protection_sets")
    assert lifecycle["status"] == "lifecycle_closed"
    assert protection_set["status"] == "closed"
    assert protection_set["reconciled_with_exchange"] in {True, 1}

    runner_order = pg_control_connection.execute(
        text(
            """
            SELECT *
            FROM brc_ticket_bound_exit_protection_orders
            WHERE role = 'RUNNER_SL'
            """
        )
    ).mappings().one()
    assert runner_order["status"] == "filled"

    events = [
        row["event_type"]
        for row in pg_control_connection.execute(
            text(
                """
                SELECT event_type
                FROM brc_ticket_bound_lifecycle_events
                ORDER BY created_at_ms, event_type
                """
            )
        ).mappings()
    ]
    for event_type in (
        "final_exit_detected",
        "reconciliation_matched",
        "budget_settled",
        "review_recorded",
        "lifecycle_closed",
    ):
        assert event_type in events


def test_lifecycle_closure_blocks_when_flat_position_has_live_protection_order(
    pg_control_connection,
):
    _, prepared = _runner_protected_attempt(pg_control_connection)
    _record_closure_evidence_events(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        reconciliation_evidence_id="recon-1",
        settlement_evidence_id="settlement-1",
        review_evidence_id="review-1",
        now_ms=NOW_MS + 8500,
    )
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_ticket_bound_exit_protection_orders
            SET status = 'submitted'
            WHERE role = 'SL'
            """
        )
    )

    payload = closure.materialize_ticket_bound_lifecycle_closure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        final_exit_exchange_order_id="exchange-runner-sl-1",
        final_exit_role="RUNNER_SL",
        final_position_flat_confirmed=True,
        reconciliation_evidence_id="recon-1",
        settlement_evidence_id="settlement-1",
        review_evidence_id="review-1",
        realized_pnl="12.34",
        now_ms=NOW_MS + 9000,
    )

    assert payload["status"] == "blocked"
    assert "position_closed_protection_live:SL" in payload["blockers"]
    assert _one(pg_control_connection, "brc_ticket_bound_order_lifecycle_runs")[
        "status"
    ] == "runner_protected"
    assert _one(pg_control_connection, "brc_ticket_bound_exit_protection_sets")[
        "status"
    ] == "runner_protected"


def test_lifecycle_closure_blocks_fake_evidence_ids_without_events(
    pg_control_connection,
):
    _, prepared = _runner_protected_attempt(pg_control_connection)

    payload = closure.materialize_ticket_bound_lifecycle_closure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        final_exit_exchange_order_id="exchange-runner-sl-1",
        final_exit_role="RUNNER_SL",
        final_position_flat_confirmed=True,
        reconciliation_evidence_id="fake-recon",
        settlement_evidence_id="fake-settlement",
        review_evidence_id="fake-review",
        realized_pnl="12.34",
        now_ms=NOW_MS + 9000,
    )

    assert payload["status"] == "blocked"
    assert "reconciliation_evidence_event_missing" in payload["blockers"]
    assert "settlement_evidence_event_missing" in payload["blockers"]
    assert "review_evidence_event_missing" in payload["blockers"]
    assert _one(pg_control_connection, "brc_ticket_bound_order_lifecycle_runs")[
        "status"
    ] == "runner_protected"
    assert _one(pg_control_connection, "brc_ticket_bound_exit_protection_sets")[
        "status"
    ] == "runner_protected"


def test_ticket_expiry_after_submit_does_not_block_post_submit_lifecycle(
    pg_control_connection,
):
    ids, prepared = _runner_protected_attempt(pg_control_connection)
    _record_closure_evidence_events(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        reconciliation_evidence_id="recon-after-ticket-expiry",
        settlement_evidence_id="settlement-after-ticket-expiry",
        review_evidence_id="review-after-ticket-expiry",
        now_ms=NOW_MS + 20_500,
    )
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_action_time_tickets
            SET expires_at_ms = :expires_at_ms
            WHERE ticket_id = :ticket_id
            """
        ),
        {"ticket_id": ids["ticket_id"], "expires_at_ms": NOW_MS - 1},
    )

    pending = closure.materialize_ticket_bound_post_submit_closure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 20_000,
    )
    final = closure.materialize_ticket_bound_lifecycle_closure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        final_exit_exchange_order_id="exchange-runner-sl-1",
        final_exit_role="RUNNER_SL",
        final_position_flat_confirmed=True,
        reconciliation_evidence_id="recon-after-ticket-expiry",
        settlement_evidence_id="settlement-after-ticket-expiry",
        review_evidence_id="review-after-ticket-expiry",
        now_ms=NOW_MS + 21_000,
    )

    assert pending["status"] == "reconciliation_pending"
    assert "ticket_expired" not in pending["blockers"]
    assert final["status"] == "closed"
    assert final["blockers"] == []
    assert _one(pg_control_connection, "brc_ticket_bound_order_lifecycle_runs")[
        "status"
    ] == "lifecycle_closed"


def test_lifecycle_closure_is_idempotent(pg_control_connection):
    _, prepared = _runner_protected_attempt(pg_control_connection)
    _record_closure_evidence_events(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        reconciliation_evidence_id="recon-1",
        settlement_evidence_id="settlement-1",
        review_evidence_id="review-1",
        now_ms=NOW_MS + 8500,
    )
    first = closure.materialize_ticket_bound_lifecycle_closure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        final_exit_exchange_order_id="exchange-runner-sl-1",
        final_exit_role="RUNNER_SL",
        final_position_flat_confirmed=True,
        reconciliation_evidence_id="recon-1",
        settlement_evidence_id="settlement-1",
        review_evidence_id="review-1",
        now_ms=NOW_MS + 9000,
    )
    second = closure.materialize_ticket_bound_lifecycle_closure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        final_exit_exchange_order_id="exchange-runner-sl-1",
        final_exit_role="RUNNER_SL",
        final_position_flat_confirmed=True,
        reconciliation_evidence_id="recon-1",
        settlement_evidence_id="settlement-1",
        review_evidence_id="review-1",
        now_ms=NOW_MS + 10_000,
    )

    assert first["status"] == "closed"
    assert second["status"] == "closed"
    assert second["idempotent_existing_lifecycle_closure"] is True
    assert (
        pg_control_connection.execute(
            text(
                """
                SELECT count(*)
                FROM brc_ticket_bound_lifecycle_events
                WHERE event_type = 'lifecycle_closed'
                """
            )
        ).scalar_one()
        == 1
    )


def test_latest_post_submit_closure_noops_without_submitted_attempt(
    pg_control_connection,
):
    payload = closure.materialize_latest_ticket_bound_post_submit_closure(
        pg_control_connection,
        now_ms=NOW_MS + 6000,
    )

    assert payload["status"] == "not_applicable_no_submitted_attempt"
    assert payload["blockers"] == []
    assert payload["next_action"] == "wait_for_ticket_bound_protected_submit"
    assert pg_control_connection.execute(
        text("SELECT COUNT(*) FROM brc_ticket_bound_post_submit_closures")
    ).scalar_one() == 0


def test_latest_post_submit_closure_materializes_newest_unclosed_submitted_attempt(
    pg_control_connection,
):
    _, first = _submitted_attempt(pg_control_connection)
    second = _clone_submitted_attempt(
        pg_control_connection,
        first,
        ticket_suffix="2",
        attempt_offset_ms=1000,
    )
    existing = closure.materialize_ticket_bound_post_submit_closure(
        pg_control_connection,
        protected_submit_attempt_id=first["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )

    payload = closure.materialize_latest_ticket_bound_post_submit_closure(
        pg_control_connection,
        now_ms=NOW_MS + 7000,
    )

    assert existing["protected_submit_attempt_id"] == first["protected_submit_attempt_id"]
    assert payload["status"] == "reconciliation_pending"
    assert payload["protected_submit_attempt_id"] == second["protected_submit_attempt_id"]
    assert "idempotent_existing_closure" not in payload
    assert pg_control_connection.execute(
        text("SELECT COUNT(*) FROM brc_ticket_bound_post_submit_closures")
    ).scalar_one() == 2


def test_latest_post_submit_closure_refreshes_existing_nonclosed_projection(
    pg_control_connection,
):
    _, prepared = _submitted_attempt(pg_control_connection)
    first = closure.materialize_ticket_bound_post_submit_closure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )

    payload = closure.materialize_latest_ticket_bound_post_submit_closure(
        pg_control_connection,
        now_ms=NOW_MS + 7000,
    )

    assert payload["status"] == first["status"]
    assert payload["protected_submit_attempt_id"] == prepared["protected_submit_attempt_id"]
    assert payload["post_submit_closure_id"] == first["post_submit_closure_id"]
    assert "idempotent_existing_closure" not in payload
    row = _closure_row(pg_control_connection)
    assert row["created_at_ms"] == NOW_MS + 6000
    assert row["updated_at_ms"] == NOW_MS + 7000


def _submitted_attempt(
    conn,
    *,
    attempt_offset_ms: int = 0,
):
    ids = _create_ready_protected_submit(conn)
    prepared = _record_submitted_attempt(conn, ids, attempt_offset_ms=attempt_offset_ms)
    protection = exit_protection.materialize_ticket_bound_exit_protection_set(
        conn,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 5500 + attempt_offset_ms,
    )
    assert protection["status"] == "position_protected"
    return ids, prepared


def _runner_protected_attempt(conn):
    ids, prepared = _submitted_attempt(conn)
    set_id = conn.execute(
        text(
            """
            SELECT exit_protection_set_id
            FROM brc_ticket_bound_exit_protection_sets
            WHERE protected_submit_attempt_id = :attempt_id
            """
        ),
        {"attempt_id": prepared["protected_submit_attempt_id"]},
    ).scalar_one()
    conn.execute(
        text(
            """
            UPDATE brc_ticket_bound_exit_protection_orders
            SET status = 'filled', updated_at_ms = :updated_at_ms
            WHERE exit_protection_set_id = :set_id
              AND role = 'TP1'
            """
        ),
        {"set_id": set_id, "updated_at_ms": NOW_MS + 6500},
    )
    _record_official_runner_mutation_result(
        conn,
        set_id,
        runner_exchange_id="exchange-runner-sl-1",
        now_ms=NOW_MS + 6900,
    )
    runner = runner_adjuster.materialize_ticket_bound_runner_protection_adjustment(
        conn,
        exit_protection_set_id=set_id,
        runner_sl_exchange_order_id="exchange-runner-sl-1",
        runner_sl_local_order_id="runner-sl-1",
        now_ms=NOW_MS + 7000,
    )
    assert runner["status"] == "runner_protected"
    return ids, prepared


def _record_submitted_attempt(
    conn,
    ids: dict[str, str],
    *,
    attempt_offset_ms: int = 0,
) -> dict:
    prepared = submit.prepare_ticket_bound_protected_submit_attempt(
        conn,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="real_gateway_action",
        now_ms=NOW_MS + 4000 + attempt_offset_ms,
    )
    submit.record_ticket_bound_protected_submit_result(
        conn,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        submit_result={
            "status": "exchange_submit_orders_submitted",
            "ticket_id": ids["ticket_id"],
            "operation_submit_command_id": ids["operation_submit_command_id"],
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
            "exchange_write_called": True,
            "order_created": True,
            "order_lifecycle_called": True,
            "withdrawal_or_transfer_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
            "submitted_orders": _submitted_orders(prepared),
        },
        now_ms=NOW_MS + 5000 + attempt_offset_ms,
    )
    return prepared


def _record_closure_evidence_events(
    conn,
    *,
    protected_submit_attempt_id: str,
    reconciliation_evidence_id: str,
    settlement_evidence_id: str,
    review_evidence_id: str,
    now_ms: int,
) -> None:
    lifecycle = conn.execute(
        text(
            """
            SELECT *
            FROM brc_ticket_bound_order_lifecycle_runs
            WHERE protected_submit_attempt_id = :attempt_id
            """
        ),
        {"attempt_id": protected_submit_attempt_id},
    ).mappings().one()
    specs = (
        (
            "reconciliation_matched",
            {"reconciliation_evidence_id": reconciliation_evidence_id},
        ),
        ("budget_settled", {"settlement_evidence_id": settlement_evidence_id}),
        ("review_recorded", {"review_evidence_id": review_evidence_id}),
    )
    for offset, (event_type, payload) in enumerate(specs):
        conn.execute(
            text(
                """
                INSERT INTO brc_ticket_bound_lifecycle_events (
                  lifecycle_event_id, lifecycle_run_id, ticket_id,
                  protected_submit_attempt_id, event_type, event_payload, created_at_ms
                ) VALUES (
                  :lifecycle_event_id, :lifecycle_run_id, :ticket_id,
                  :protected_submit_attempt_id, :event_type, :event_payload,
                  :created_at_ms
                )
                """
            ),
            {
                "lifecycle_event_id": (
                    "test-closure-evidence:"
                    f"{protected_submit_attempt_id}:{event_type}"
                ),
                "lifecycle_run_id": lifecycle["lifecycle_run_id"],
                "ticket_id": lifecycle["ticket_id"],
                "protected_submit_attempt_id": protected_submit_attempt_id,
                "event_type": event_type,
                "event_payload": json.dumps(payload, sort_keys=True),
                "created_at_ms": now_ms + offset,
            },
        )


def _clone_submitted_attempt(
    conn,
    prepared: dict,
    *,
    ticket_suffix: str,
    attempt_offset_ms: int,
) -> dict:
    row = conn.execute(
        text(
            """
            SELECT *
            FROM brc_ticket_bound_protected_submit_attempts
            WHERE protected_submit_attempt_id = :attempt_id
            """
        ),
        {"attempt_id": prepared["protected_submit_attempt_id"]},
    ).mappings().one()
    values = dict(row)
    values["protected_submit_attempt_id"] = (
        f"{prepared['protected_submit_attempt_id']}:{ticket_suffix}"
    )
    values["ticket_id"] = f"{values['ticket_id']}:{ticket_suffix}"
    values["operation_submit_command_id"] = (
        f"{values['operation_submit_command_id']}:{ticket_suffix}"
    )
    values["created_at_ms"] = NOW_MS + 4000 + attempt_offset_ms
    values["updated_at_ms"] = NOW_MS + 5000 + attempt_offset_ms
    submit_request = _json_value(values["submit_request"])
    submit_result = _json_value(values["submit_result"])
    submit_request["ticket_id"] = values["ticket_id"]
    submit_request["operation_submit_command_id"] = values["operation_submit_command_id"]
    submit_result["ticket_id"] = values["ticket_id"]
    submit_result["operation_submit_command_id"] = values["operation_submit_command_id"]
    for order in submit_result.get("submitted_orders", []):
        order["exchange_order_id"] = f"{order['exchange_order_id']}:{ticket_suffix}"
    values["submit_request"] = json.dumps(submit_request, sort_keys=True)
    values["submit_result"] = json.dumps(submit_result, sort_keys=True)
    columns = ", ".join(values)
    placeholders = ", ".join(f":{key}" for key in values)
    conn.execute(
        text(
            f"""
            INSERT INTO brc_ticket_bound_protected_submit_attempts ({columns})
            VALUES ({placeholders})
            """
        ),
        values,
    )
    protection = exit_protection.materialize_ticket_bound_exit_protection_set(
        conn,
        protected_submit_attempt_id=values["protected_submit_attempt_id"],
        now_ms=NOW_MS + 5500 + attempt_offset_ms,
    )
    assert protection["status"] == "position_protected"
    return values


def _closure_row(conn):
    return conn.execute(
        text("SELECT * FROM brc_ticket_bound_post_submit_closures")
    ).mappings().one()


def _one(conn, table_name: str):
    row = conn.execute(text(f"SELECT * FROM {table_name}")).mappings().one()
    return {key: _maybe_json_value(value) for key, value in dict(row).items()}


def _maybe_json_value(value):
    if isinstance(value, str) and value[:1] in {"[", "{"}:
        return _json_value(value)
    return value
