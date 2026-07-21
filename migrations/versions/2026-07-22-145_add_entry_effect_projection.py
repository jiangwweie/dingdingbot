"""Add typed ENTRY effect and protection barrier current truth.

Revision ID: 145
Revises: 144
Create Date: 2026-07-22
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "145"
down_revision: Union[str, None] = "144"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ATTEMPT_TABLE = "brc_ticket_bound_protected_submit_attempts"
EVENT_TABLE = "brc_ticket_bound_lifecycle_events"

LIFECYCLE_EVENTS = (
    "event_type IN ('entry_submitted', 'entry_fill_pending', 'entry_filled', "
    "'exit_protection_materialization_started', 'sl_submitted', "
    "'tp1_submitted', 'exit_protection_reconciled', 'tp1_filled', "
    "'sl_cancel_requested', 'runner_sl_submitted', 'runner_protected', "
    "'final_exit_detected', 'reconciliation_matched', 'budget_settled', "
    "'review_recorded', 'lifecycle_closed', 'hard_stopped', "
    "'submit_failed', 'entry_unknown', 'entry_orphaned', "
    "'entry_partial_fill_detected', 'protection_missing', "
    "'protection_degraded', 'protection_submit_failed', "
    "'protection_reconciliation_mismatch', 'exchange_orphan_detected', "
    "'tp1_or_sl_orphaned', 'runner_mutation_pending', "
    "'runner_mutation_failed', 'runner_reconciliation_mismatch', "
    "'position_closed_protection_live', 'final_exit_unknown', "
    "'settlement_blocked', 'review_blocked', 'presubmit_reconciled_absent')"
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(ATTEMPT_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(ATTEMPT_TABLE)}
    additions = (
        (
            "entry_effect_state",
            sa.String(64),
            False,
            sa.text("'not_called'"),
        ),
        ("entry_effect_observed_at_ms", sa.BIGINT(), True, None),
        (
            "protection_barrier_state",
            sa.String(64),
            False,
            sa.text("'not_started'"),
        ),
        ("initial_stop_deadline_at_ms", sa.BIGINT(), True, None),
        ("initial_stop_confirmed_at_ms", sa.BIGINT(), True, None),
        ("protection_quantity", sa.Numeric(36, 18), True, None),
    )
    for name, column_type, nullable, default in additions:
        if name not in columns:
            op.add_column(
                ATTEMPT_TABLE,
                sa.Column(
                    name,
                    column_type,
                    nullable=nullable,
                    server_default=default,
                ),
            )
    if bind.dialect.name == "sqlite":
        _replace_attempt_checks_sqlite()
        if inspector.has_table(EVENT_TABLE):
            with op.batch_alter_table(EVENT_TABLE, recreate="always") as batch_op:
                batch_op.drop_constraint(
                    "ck_brc_lifecycle_event_type", type_="check"
                )
                batch_op.create_check_constraint(
                    "ck_brc_lifecycle_event_type", LIFECYCLE_EVENTS
                )
        return
    _backfill_entry_effect()
    _replace_attempt_checks()
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_brc_ticket_submit_entry_barrier "
        f"ON {ATTEMPT_TABLE} "
        "(entry_effect_state, protection_barrier_state, updated_at_ms)"
    )
    if inspector.has_table(EVENT_TABLE):
        op.execute(
            f"ALTER TABLE {EVENT_TABLE} "
            "DROP CONSTRAINT IF EXISTS ck_brc_lifecycle_event_type"
        )
        op.create_check_constraint(
            "ck_brc_lifecycle_event_type",
            EVENT_TABLE,
            LIFECYCLE_EVENTS,
        )
    _repair_effect_active_current_truth(inspector)


def downgrade() -> None:
    # Forward-only: effect truth and recovery authority must not be discarded.
    return


def _backfill_entry_effect() -> None:
    op.execute(
        f"""
        UPDATE {ATTEMPT_TABLE} AS attempt
        SET entry_effect_state = CASE
              WHEN command.command_state = 'confirmed_rejected' THEN 'rejected'
              WHEN command.command_state = 'outcome_unknown' THEN 'outcome_unknown'
              WHEN command.command_state = 'confirmed_submitted'
                   AND command.result_facts_complete = true
                   AND command.executed_qty = 0 THEN 'accepted_zero_fill'
              WHEN command.command_state = 'confirmed_submitted'
                   AND command.result_facts_complete = true
                   AND command.executed_qty > 0
                   AND command.average_exec_price > 0 THEN 'accepted_filled'
              ELSE 'outcome_unknown'
            END,
            entry_effect_observed_at_ms = COALESCE(
              attempt.entry_effect_observed_at_ms,
              command.exchange_observed_at_ms,
              command.updated_at_ms
            ),
            protection_barrier_state = CASE
              WHEN command.command_state = 'confirmed_rejected' THEN 'not_started'
              WHEN command.command_state = 'confirmed_submitted'
                   AND command.result_facts_complete = true
                   AND command.executed_qty = 0 THEN 'fill_pending'
              WHEN command.command_state = 'confirmed_submitted'
                   AND command.result_facts_complete = true
                   AND command.executed_qty > 0
                   AND command.average_exec_price > 0 THEN 'initial_stop_pending'
              ELSE 'hard_stopped'
            END,
            protection_quantity = CASE
              WHEN command.command_state = 'confirmed_submitted'
                   AND command.result_facts_complete = true
                   AND command.executed_qty > 0
                   AND command.average_exec_price > 0
              THEN command.executed_qty ELSE NULL END
        FROM brc_ticket_bound_exchange_commands AS command
        WHERE command.protected_submit_attempt_id =
              attempt.protected_submit_attempt_id
          AND command.order_role = 'ENTRY'
          AND command.command_state IN (
            'confirmed_submitted', 'confirmed_rejected', 'outcome_unknown'
          )
        """
    )
    op.execute(
        f"""
        UPDATE {ATTEMPT_TABLE}
        SET entry_effect_state = 'outcome_unknown',
            entry_effect_observed_at_ms = COALESCE(
              entry_effect_observed_at_ms, updated_at_ms
            ),
            protection_barrier_state = 'hard_stopped'
        WHERE exchange_write_called = true
          AND entry_effect_state = 'not_called'
          AND NOT EXISTS (
            SELECT 1 FROM brc_ticket_bound_exchange_commands AS command
            WHERE command.protected_submit_attempt_id =
                  brc_ticket_bound_protected_submit_attempts.protected_submit_attempt_id
              AND command.order_role = 'ENTRY'
              AND command.command_state IN ('hard_stopped', 'confirmed_rejected')
          )
        """
    )


def _repair_effect_active_current_truth(inspector: sa.Inspector) -> None:
    required = {
        "brc_action_time_tickets",
        "brc_action_time_ticket_events",
        "brc_operation_layer_handoffs",
        "brc_ticket_bound_order_lifecycle_runs",
        "brc_ticket_bound_lifecycle_events",
        "brc_ticket_bound_exchange_commands",
    }
    if not required <= set(inspector.get_table_names()):
        return
    op.execute(
        "ALTER TABLE brc_action_time_ticket_events "
        "DROP CONSTRAINT IF EXISTS ck_brc_ticket_event_transition"
    )
    op.create_check_constraint(
        "ck_brc_ticket_event_transition",
        "brc_action_time_ticket_events",
        "(from_status IS NULL AND to_status = 'created') OR "
        "(from_status = 'created' AND to_status IN "
        "('preflight_pending', 'expired', 'superseded', 'invalidated')) OR "
        "(from_status = 'preflight_pending' AND to_status IN "
        "('finalgate_ready', 'finalgate_rejected', 'expired', "
        "'superseded', 'invalidated')) OR "
        "(from_status = 'finalgate_ready' AND to_status IN "
        "('submitted', 'expired', 'superseded', 'invalidated')) OR "
        "(from_status = 'expired' AND to_status = 'submitted' AND "
        "transition_reason IN ('entry_effect_migration_repair', "
        "'entry_exchange_effect_committed', "
        "'entry_effect_prevents_ticket_expiration')) OR "
        "(from_status = 'submitted' AND to_status = 'closed')",
    )
    op.execute(
        """
        INSERT INTO brc_action_time_ticket_events (
          ticket_event_id, ticket_id, action_time_lane_input_id, from_status,
          to_status, transition_reason, trigger_ref, writer, event_payload,
          occurred_at_ms, created_at_ms
        )
        SELECT
          'ticket_event:entry_effect_repair:' ||
            md5(ticket.ticket_id || ':' || attempt.protected_submit_attempt_id),
          ticket.ticket_id, ticket.action_time_lane_input_id, ticket.status,
          'submitted', 'entry_effect_migration_repair',
          attempt.protected_submit_attempt_id, 'migration_145',
          jsonb_build_object(
            'entry_effect_state', attempt.entry_effect_state,
            'repaired_from_status', ticket.status
          ),
          attempt.entry_effect_observed_at_ms,
          attempt.entry_effect_observed_at_ms
        FROM brc_action_time_tickets AS ticket
        JOIN brc_ticket_bound_protected_submit_attempts AS attempt
          ON attempt.ticket_id = ticket.ticket_id
        WHERE ticket.status IN ('finalgate_ready', 'expired')
          AND attempt.entry_effect_state IN (
            'accepted_zero_fill', 'accepted_filled', 'outcome_unknown'
          )
        ON CONFLICT (ticket_event_id) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE brc_action_time_tickets AS ticket
        SET status = 'submitted'
        FROM brc_ticket_bound_protected_submit_attempts AS attempt
        WHERE attempt.ticket_id = ticket.ticket_id
          AND ticket.status IN ('finalgate_ready', 'expired')
          AND attempt.entry_effect_state IN (
            'accepted_zero_fill', 'accepted_filled', 'outcome_unknown'
          )
        """
    )
    op.execute(
        """
        UPDATE brc_operation_layer_handoffs AS handoff
        SET status = 'submitted', updated_at_ms = GREATEST(
          handoff.updated_at_ms, attempt.entry_effect_observed_at_ms
        )
        FROM brc_ticket_bound_protected_submit_attempts AS attempt
        WHERE attempt.operation_layer_handoff_id =
              handoff.operation_layer_handoff_id
          AND attempt.entry_effect_state IN (
            'accepted_zero_fill', 'accepted_filled', 'outcome_unknown'
          )
        """
    )
    op.execute(
        """
        INSERT INTO brc_ticket_bound_order_lifecycle_runs (
          lifecycle_run_id, ticket_id, protected_submit_attempt_id,
          strategy_group_id, symbol, side, runtime_profile_id, status,
          entry_local_order_id, entry_exchange_order_id, entry_fill_confirmed,
          entry_filled_qty, entry_avg_price, exit_protection_set_id,
          first_blocker, blockers, warnings, authority_boundary,
          created_at_ms, updated_at_ms
        )
        SELECT
          'ticket_order_lifecycle:' || md5(attempt.ticket_id),
          attempt.ticket_id, attempt.protected_submit_attempt_id,
          attempt.strategy_group_id, attempt.symbol, attempt.side,
          attempt.runtime_profile_id,
          CASE attempt.entry_effect_state
            WHEN 'accepted_filled' THEN 'entry_filled'
            WHEN 'accepted_zero_fill' THEN 'entry_fill_pending'
            ELSE 'entry_unknown'
          END,
          command.local_order_id, command.exchange_order_id,
          attempt.entry_effect_state = 'accepted_filled',
          attempt.protection_quantity, command.average_exec_price, NULL,
          CASE WHEN attempt.entry_effect_state = 'outcome_unknown'
            THEN 'entry_exchange_outcome_unknown' ELSE NULL END,
          CASE WHEN attempt.entry_effect_state = 'outcome_unknown'
            THEN '["entry_exchange_outcome_unknown"]'::jsonb ELSE '[]'::jsonb END,
          '[]'::jsonb,
          'entry_effect_projection; migration_145_repair',
          attempt.created_at_ms, attempt.entry_effect_observed_at_ms
        FROM brc_ticket_bound_protected_submit_attempts AS attempt
        JOIN brc_ticket_bound_exchange_commands AS command
          ON command.protected_submit_attempt_id =
             attempt.protected_submit_attempt_id
         AND command.order_role = 'ENTRY'
        WHERE attempt.entry_effect_state IN (
          'accepted_zero_fill', 'accepted_filled', 'outcome_unknown'
        )
        ON CONFLICT (ticket_id) DO UPDATE SET
          protected_submit_attempt_id = EXCLUDED.protected_submit_attempt_id,
          status = EXCLUDED.status,
          entry_local_order_id = EXCLUDED.entry_local_order_id,
          entry_exchange_order_id = EXCLUDED.entry_exchange_order_id,
          entry_fill_confirmed = EXCLUDED.entry_fill_confirmed,
          entry_filled_qty = EXCLUDED.entry_filled_qty,
          entry_avg_price = EXCLUDED.entry_avg_price,
          first_blocker = EXCLUDED.first_blocker,
          blockers = EXCLUDED.blockers,
          authority_boundary = EXCLUDED.authority_boundary,
          updated_at_ms = EXCLUDED.updated_at_ms
        WHERE brc_ticket_bound_order_lifecycle_runs.status IN (
          'entry_submit_sent', 'entry_fill_pending', 'entry_filled', 'entry_unknown'
        )
        """
    )
    op.execute(
        """
        INSERT INTO brc_ticket_bound_lifecycle_events (
          lifecycle_event_id, lifecycle_run_id, ticket_id,
          protected_submit_attempt_id, event_type, event_payload, created_at_ms
        )
        SELECT
          'entry_effect_repair:' || md5(
            attempt.protected_submit_attempt_id || ':' ||
            attempt.entry_effect_state
          ),
          lifecycle.lifecycle_run_id, attempt.ticket_id,
          attempt.protected_submit_attempt_id,
          CASE attempt.entry_effect_state
            WHEN 'accepted_filled' THEN 'entry_filled'
            WHEN 'accepted_zero_fill' THEN 'entry_fill_pending'
            ELSE 'entry_unknown'
          END,
          jsonb_build_object(
            'entry_effect_state', attempt.entry_effect_state,
            'migration_revision', '145'
          ),
          attempt.entry_effect_observed_at_ms
        FROM brc_ticket_bound_protected_submit_attempts AS attempt
        JOIN brc_ticket_bound_order_lifecycle_runs AS lifecycle
          ON lifecycle.ticket_id = attempt.ticket_id
        WHERE attempt.entry_effect_state IN (
          'accepted_zero_fill', 'accepted_filled', 'outcome_unknown'
        )
        ON CONFLICT (lifecycle_event_id) DO NOTHING
        """
    )
    if inspector.has_table("brc_budget_reservations"):
        if inspector.has_table("brc_budget_reservation_events"):
            op.execute(
                """
                INSERT INTO brc_budget_reservation_events (
                  budget_reservation_event_id, budget_reservation_id,
                  from_status, to_status, reason, evidence_ref, created_at_ms
                )
                SELECT
                  'budget_reservation_event:migration-145:' ||
                    reservation.budget_reservation_id,
                  reservation.budget_reservation_id,
                  'released', 'consumed',
                  'entry_effect_migration_capacity_repair',
                  'migration:145:entry-effect',
                  attempt.entry_effect_observed_at_ms
                FROM brc_budget_reservations AS reservation
                JOIN brc_ticket_bound_protected_submit_attempts AS attempt
                  ON attempt.ticket_id = reservation.ticket_id
                WHERE reservation.status = 'released'
                  AND attempt.entry_effect_state IN (
                    'accepted_zero_fill', 'accepted_filled', 'outcome_unknown'
                  )
                ON CONFLICT (budget_reservation_event_id) DO NOTHING
                """
            )
        op.execute(
            """
            UPDATE brc_budget_reservations AS reservation
            SET status = 'consumed',
                release_reason = NULL,
                released_at_ms = NULL,
                reconciliation_state = 'pending',
                current_first_blocker =
                  'entry_effect_migration_capacity_revalidation_required'
            FROM brc_ticket_bound_protected_submit_attempts AS attempt
            WHERE reservation.ticket_id = attempt.ticket_id
              AND reservation.status = 'released'
              AND attempt.entry_effect_state IN (
                'accepted_zero_fill', 'accepted_filled', 'outcome_unknown'
              )
            """
        )


def _replace_attempt_checks() -> None:
    for name, expression in _attempt_checks().items():
        op.execute(f"ALTER TABLE {ATTEMPT_TABLE} DROP CONSTRAINT IF EXISTS {name}")
        op.create_check_constraint(name, ATTEMPT_TABLE, expression)


def _replace_attempt_checks_sqlite() -> None:
    with op.batch_alter_table(ATTEMPT_TABLE, recreate="always") as batch_op:
        for name, expression in _attempt_checks().items():
            batch_op.create_check_constraint(name, expression)


def _attempt_checks() -> dict[str, str]:
    return {
        "ck_brc_ticket_submit_entry_effect_state": (
            "entry_effect_state IN ('not_called', 'accepted_zero_fill', "
            "'accepted_filled', 'outcome_unknown', 'rejected', "
            "'reconciled_absent')"
        ),
        "ck_brc_ticket_submit_protection_barrier_state": (
            "protection_barrier_state IN ('not_started', 'fill_pending', "
            "'initial_stop_pending', 'initial_stop_confirmed', 'degraded', "
            "'hard_stopped', 'closed')"
        ),
        "ck_brc_ticket_submit_protection_quantity": (
            "protection_quantity IS NULL OR "
            "(entry_effect_state = 'accepted_filled' AND protection_quantity > 0)"
        ),
        "ck_brc_ticket_submit_entry_filled_quantity": (
            "entry_effect_state <> 'accepted_filled' OR protection_quantity > 0"
        ),
        "ck_brc_ticket_submit_initial_stop_pending_truth": (
            "protection_barrier_state <> 'initial_stop_pending' OR "
            "(entry_effect_state = 'accepted_filled' AND protection_quantity > 0)"
        ),
        "ck_brc_ticket_submit_initial_stop_confirmed_truth": (
            "protection_barrier_state <> 'initial_stop_confirmed' OR "
            "initial_stop_confirmed_at_ms IS NOT NULL"
        ),
        "ck_brc_ticket_submit_entry_effect_observed": (
            "entry_effect_state = 'not_called' OR "
            "entry_effect_observed_at_ms IS NOT NULL"
        ),
    }
