"""Preserve all rows; unify authenticated Generic recovery across an existing gap."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0015_generic_owner_recovery_v1"
down_revision: str | None = "0014_dynamic_risk_budget_v1"
branch_labels = None
depends_on = None


def upgrade():
    c = op.get_bind()
    if c.scalar(sa.text("SELECT version_num FROM alembic_version")) != down_revision:
        raise RuntimeError("0015 requires exact 0014 source")
    gates = {
        "brc_trade_tickets": "terminal_at_ms IS NULL OR active_netting_domain_key IS NOT NULL",
        "brc_positions_current": "quantity<>0",
        "brc_budget_reservations": "status='active'",
        "brc_exchange_commands": "status IN ('prepared','claimed','dispatch_started','outcome_unknown')",
        "brc_runtime_incidents": "status='open'",
        "brc_entry_lane_current": "status<>'idle' OR ticket_id IS NOT NULL",
        "brc_entry_send_authorizations": "completed_at_ms IS NULL",
        "brc_trade_aggregates": "status NOT IN ('terminal','leverage_rejected','entry_rejected','entry_reconciled_absent')",
        "brc_owner_control_operations_current": "state NOT IN ('completed','blocked')",
        "brc_strategy_universe_versions": "lifecycle_state IN ('warming','staged')",
        "brc_strategy_universe_materialization_generations": "lifecycle_state IN ('PENDING','DESIRED','DRAINING_ENTRY','MATERIALIZING','STAGED')",
        "brc_directional_risk_controls": "pending_view IS NOT NULL OR pending_baseline IS NOT NULL",
    }
    c.execute(
        sa.text(
            "LOCK TABLE "
            + ",".join(gates)
            + ",brc_owner_policy_current IN SHARE ROW EXCLUSIVE MODE"
        )
    )
    for table, predicate in gates.items():
        if c.scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table} WHERE {predicate})")):
            raise RuntimeError(f"0015 requires quiescent source: {table}")
    from src.trading_kernel.infrastructure.generic_selection_source_provenance import (
        count_nonquiescent_source_vacuums,
    )

    if count_nonquiescent_source_vacuums(c, allow_paused_failed_generic=True):
        raise RuntimeError("0015 requires quiescent selection Vacuums")

    # Exact current schema function transformation; never an old-table runtime reader.
    signature = "brc_generic_vacuum_owner_resume_matches(text,text,bigint)"
    definition = c.scalar(
        sa.text("SELECT pg_get_functiondef(CAST(:sig AS regprocedure))"),
        {"sig": signature},
    )
    marker = "        );"
    if definition is None or definition.count(marker) != 1:
        raise RuntimeError("0015 exact Resume predicate source differs")
    extension = """        ) OR EXISTS (
          SELECT 1 FROM brc_strategy_entry_vacuums_current v
          JOIN brc_strategy_entry_vacuum_events opened ON opened.entry_vacuum_id=v.entry_vacuum_id
            AND opened.event_type='OPEN' AND opened.event_sequence=1
          JOIN brc_strategy_entry_vacuum_events drained ON drained.entry_vacuum_id=v.entry_vacuum_id
            AND drained.event_type='ENTRY_DRAINED' AND drained.occurred_at_ms=v.drained_at_ms
          JOIN brc_selection_authority_current current_a ON current_a.selection_spec_id=v.selection_spec_id
            AND current_a.selection_authority_id=source_id
          JOIN brc_selection_session_authorities src ON src.selection_authority_id=source_id
          JOIN brc_strategy_entry_controls_current owner ON owner.strategy_group_id=v.strategy_group_id
          JOIN brc_strategy_entry_control_events resumed ON resumed.strategy_entry_control_event_id=owner.last_event_id
            AND resumed.strategy_group_id=owner.strategy_group_id AND resumed.control_version=owner.control_version
          JOIN brc_strategy_entry_control_events paused ON paused.strategy_group_id=owner.strategy_group_id
            AND paused.control_version=resumed.control_version-1
          JOIN brc_owner_authorizations resume_auth ON resume_auth.authorization_id=resumed.authorization_id
          JOIN brc_owner_authorizations pause_auth ON pause_auth.authorization_id=paused.authorization_id
          JOIN brc_strategy_selection_control_current ctl ON ctl.strategy_group_id=owner.strategy_group_id
          WHERE v.entry_vacuum_id=vid AND v.selection_spec_id<>'sor-dynamic-selection-v0'
            AND v.resolved_at_ms IS NULL AND v.state IN ('RECOVERY_PENDING','RECONFIGURING')
            AND v.drained_at_ms>=v.fenced_at_ms AND v.drained_at_ms<=paused.created_at_ms
            AND opened.occurred_at_ms=v.fenced_at_ms
            AND opened.payload->>'intended_outcome'='PRE_FENCE_CONTINUITY'
            AND opened.payload->>'source_selection_authority_id'=source_id
            AND drained.payload->>'target_state' IN ('RECOVERY_PENDING','RECONFIGURING')
            AND src.selection_mode='dynamic_selection'
            AND src.selection_spec_id=v.selection_spec_id AND src.created_at_ms<=v.fenced_at_ms
            AND src.owner_control_version+1=paused.control_version
            AND owner.entry_state='enabled' AND owner.updated_at_ms=resumed.created_at_ms
            AND resumed.operation='resume' AND resumed.target_state='enabled'
            AND paused.operation='pause' AND paused.target_state='paused'
            AND v.fenced_at_ms<paused.created_at_ms AND paused.created_at_ms<=resumed.created_at_ms
            AND resumed.created_at_ms<=checked_at
            AND resume_auth.purpose='strategy_resume' AND resume_auth.authentication_strength='totp_step_up'
            AND resume_auth.authorized_at_ms=resumed.created_at_ms
            AND resume_auth.target_scope=jsonb_build_object('strategy_group_id',v.strategy_group_id)
            AND pause_auth.purpose='strategy_pause' AND pause_auth.authorized_at_ms=paused.created_at_ms
            AND pause_auth.target_scope=jsonb_build_object('strategy_group_id',v.strategy_group_id)
            AND ctl.selection_mode='dynamic_selection' AND ctl.pending_selection_mode IS NULL
            AND ctl.selection_spec_id=v.selection_spec_id AND ctl.selection_epoch_id=src.selection_epoch_id
            AND ctl.control_version=src.selection_control_version
        );"""
    c.exec_driver_sql(definition.replace(marker, extension))
    signature = "brc_generic_static_recovery_proof_matches(jsonb,bigint)"
    definition = c.scalar(
        sa.text("SELECT pg_get_functiondef(CAST(:sig AS regprocedure))"),
        {"sig": signature},
    )
    old = "OR source_authority.owner_control_version<>o.control_version"
    if definition is None or definition.count(old) != 1:
        raise RuntimeError("0015 exact fallback proof source differs")
    new = "OR (source_authority.owner_control_version<>o.control_version AND NOT brc_generic_vacuum_owner_resume_matches(p->>'source_entry_vacuum_id',source_authority.selection_authority_id,checked_at))"
    c.exec_driver_sql(definition.replace(old, new))

    # A fallback after a gap is recovery, never ordinary activation. The INSERT
    # guard already verified the immutable full proof; deferred guards require
    # atomic checkpoint rebase, current Authority and durable resolution events.
    signature = "brc_guard_generic_gap_vacuum_transition()"
    definition = c.scalar(
        sa.text("SELECT pg_get_functiondef(CAST(:sig AS regprocedure))"),
        {"sig": signature},
    )
    old = ")) THEN RAISE EXCEPTION 'Gap Vacuum cannot become ordinary active/fallback'; END IF;"
    if definition is None or definition.count(old) != 1:
        raise RuntimeError("0015 exact gap transition source differs")
    new = """)) AND NOT (NEW.state='RESOLVED_FALLBACK' AND EXISTS (
          SELECT 1 FROM brc_selection_session_authorities a
          JOIN brc_selection_authority_current current_a ON current_a.selection_spec_id=a.selection_spec_id
          WHERE a.selection_spec_id=OLD.selection_spec_id AND a.selection_mode='dynamic_selection'
            AND a.authority_outcome='FALLBACK_PREVIOUS' AND a.created_at_ms=NEW.resolved_at_ms
            AND a.materialization_generation_id=NEW.source_generation_id
            AND a.recovery_grant_proof->>'source_entry_vacuum_id'=OLD.entry_vacuum_id
            AND a.recovery_grant_proof->>'source_selection_authority_id'=current_a.selection_authority_id
            AND a.recovery_grant_proof->>'authority_outcome'='FALLBACK_PREVIOUS'
        )) THEN RAISE EXCEPTION 'Gap Vacuum cannot become ordinary active/fallback'; END IF;"""
    definition = definition.replace(old, new)
    old_reason = (
        "AND a.recovery_grant_proof->'recovery_close_plan'->>'reason'='AUTHORITY_GAP'"
    )
    if definition.count(old_reason) != 1:
        raise RuntimeError("0015 exact gap activation source differs")
    new_reason = """AND a.recovery_grant_proof->>'authority_outcome'='ACTIVE_NEW'
            AND a.selection_spec_id=OLD.selection_spec_id AND a.selection_mode='dynamic_selection'
            AND EXISTS (SELECT 1 FROM brc_selection_authority_current current_a
              WHERE current_a.selection_spec_id=a.selection_spec_id
                AND current_a.selection_authority_id=a.recovery_grant_proof->>'source_selection_authority_id')"""
    c.exec_driver_sql(definition.replace(old_reason, new_reason))


def downgrade():
    raise RuntimeError("Generic recovery is forward-only; fix-forward required")
