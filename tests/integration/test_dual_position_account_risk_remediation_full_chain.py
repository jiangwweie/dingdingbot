"""T11 production-shaped account-risk certification without current-row seeding.

This certification deliberately reuses the RCI PostgreSQL harness, which
bootstraps the current migration head and exercises the public Action-Time
entry points.  It must never call the legacy test helpers that insert Exposure
or Budget Current rows: those rows are created only by Claim/Projection code.
"""

from __future__ import annotations

from sqlalchemy import text

from tests.integration.runtime_causal_integrity_pg_support import (
    postgres_certification_engine,
    postgres_certification_template,
)
from tests.integration.test_runtime_causal_integrity_postgres import (
    _prepare_exchange_commands_on_connection,
)


def test_raw_capacity_fact_reaches_nonexecuting_ticket_bound_submit_without_current_row_seeding(
    postgres_certification_engine,
) -> None:
    """Raw capacity fact must create one sealed Claim/Ticket authority chain."""

    with postgres_certification_engine.connect() as conn:
        ids, prepared = _prepare_exchange_commands_on_connection(conn)

        budget = conn.execute(
            text(
                """
                SELECT status, ticket_id, capacity_claim_hash,
                       account_source_fact_snapshot_id
                FROM brc_budget_reservations
                """
            )
        ).mappings().one()
        ticket = conn.execute(
            text(
                """
                SELECT ticket_id, action_time_invocation_id,
                       account_capacity_base_fact_snapshot_id
                FROM brc_action_time_tickets
                """
            )
        ).mappings().one()
        handoff = conn.execute(
            text(
                """
                SELECT ticket_id, finalgate_pass_id, operation_layer_handoff_id,
                       operation_layer_called, exchange_write_called, order_created
                FROM brc_operation_layer_handoffs
                """
            )
        ).mappings().one()
        safety = conn.execute(
            text(
                """
                SELECT submit_allowed, safety_state, trusted_fact_refs
                FROM brc_runtime_safety_state_snapshots
                """
            )
        ).mappings().one()

        assert budget["status"] == "consumed"
        assert budget["ticket_id"] == ids["ticket_id"]
        assert budget["capacity_claim_hash"]
        assert budget["account_source_fact_snapshot_id"] == "account-snapshot-1"
        assert ticket["ticket_id"] == ids["ticket_id"]
        assert ticket["action_time_invocation_id"]
        assert ticket["account_capacity_base_fact_snapshot_id"]
        assert handoff["ticket_id"] == ids["ticket_id"]
        assert handoff["finalgate_pass_id"] == ids["finalgate_pass_id"]
        assert handoff["operation_layer_handoff_id"] == ids["operation_layer_handoff_id"]
        assert handoff["operation_layer_called"] is False
        assert handoff["exchange_write_called"] is False
        assert handoff["order_created"] is False
        assert safety["submit_allowed"] is True
        assert safety["safety_state"] == "live_submit_ready"
        assert safety["trusted_fact_refs"]["ticket_id"] == ids["ticket_id"]
        assert prepared["status"] == "submit_prepared"
        assert prepared["exchange_write_called"] is False
