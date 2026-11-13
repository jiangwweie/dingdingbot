"""Release a static Owner pause only through real Resume and a completed drain."""

import sqlalchemy as sa
from alembic import op

revision: str = "0023_management_recovery"
down_revision: str = "0022_wallet_margin_allocation"
branch_labels = None
depends_on = None


def upgrade():
    c = op.get_bind()
    c.exec_driver_sql(
        "LOCK TABLE brc_trade_tickets, brc_exchange_commands, brc_positions_current, brc_owner_policy_current IN SHARE ROW EXCLUSIVE MODE"
    )
    for table, predicate in {
        "brc_trade_tickets": "terminal_at_ms IS NULL",
        "brc_positions_current": "quantity<>0",
        "brc_exchange_commands": "status IN ('prepared','claimed','dispatch_started','outcome_unknown')",
        "brc_owner_policy_current": "new_entry_submit_enabled",
        "brc_budget_reservations": "status='active'",
        "brc_entry_lane_current": "status<>'idle'",
        "brc_runtime_incidents": "status='open'",
        "brc_account_exposure_current": "active_ticket_count<>0 OR gross_notional<>0 OR gross_risk_at_stop<>0 OR current_reserved_margin<>0",
    }.items():
        if c.scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table} WHERE {predicate})")):
            raise RuntimeError(
                "0023 requires stopped flat terminal-clean paused source"
            )
    op.create_index(
        "ix_brc_management_coverage_epoch_time",
        "brc_management_coverage_events",
        ["scope_key", "epoch_id", "occurred_at_ms"],
    )
    table = "brc_strategy_entry_vacuums_current"
    op.drop_constraint(f"ck_{table}_state_valid", table, type_="check")
    op.create_check_constraint(
        f"ck_{table}_state_valid",
        table,
        "state IN ('OPEN','DRAINING_ENTRY','RECONFIGURING','RECOVERY_PENDING',"
        "'RESOLVED_ACTIVE','RESOLVED_FALLBACK','RESOLVED_CONTINUITY','RESOLVED_OWNER_RESUME',"
        "'VALID_EMPTY','OWNER_PAUSED','SUPERSEDED','FAILED_CLOSED')",
    )
    op.create_check_constraint(
        "ck_brc_static_owner_resume_shape",
        table,
        "state<>'RESOLVED_OWNER_RESUME' OR (strategy_group_id IN ('CPM-RO-001','MPG-001','MI-001','BRF2-001') "
        "AND first_blocker='OWNER_PAUSED' AND source_generation_id IS NULL AND drained_at_ms IS NOT NULL AND resolved_at_ms IS NOT NULL)",
    )
    c.exec_driver_sql("""CREATE FUNCTION brc_static_owner_resume_authorization(vid text, checked_at bigint)
    RETURNS jsonb LANGUAGE sql STABLE AS $$
      SELECT jsonb_build_object('owner_resume_authorization_id',r.authorization_id,
        'owner_pause_authorization_id',p.authorization_id,'latest_owner_pause_authorization_id',latest.authorization_id,
        'owner_control_version',o.control_version,'selection_control_version',s.control_version,'entry_drain_complete',true)
      FROM brc_strategy_entry_vacuums_current v
      JOIN brc_strategy_entry_controls_current o ON o.strategy_group_id=v.strategy_group_id
      JOIN brc_strategy_selection_control_current s ON s.strategy_group_id=v.strategy_group_id
      JOIN brc_strategy_entry_control_events r ON r.strategy_entry_control_event_id=o.last_event_id
      JOIN brc_strategy_entry_control_events latest ON latest.strategy_group_id=o.strategy_group_id AND latest.control_version=r.control_version-1
      JOIN brc_strategy_entry_control_events p ON p.strategy_group_id=o.strategy_group_id AND p.created_at_ms=v.fenced_at_ms AND p.operation='pause'
      JOIN brc_owner_authorizations a ON a.authorization_id=r.authorization_id
      JOIN brc_owner_authorizations pa ON pa.authorization_id=p.authorization_id
      JOIN brc_owner_authorizations la ON la.authorization_id=latest.authorization_id
      WHERE v.entry_vacuum_id=vid AND v.strategy_group_id IN ('CPM-RO-001','MPG-001','MI-001','BRF2-001')
        AND v.state IN ('OPEN','DRAINING_ENTRY','OWNER_PAUSED','RESOLVED_OWNER_RESUME') AND v.first_blocker='OWNER_PAUSED'
        AND v.source_generation_id IS NULL
        AND s.selection_spec_id=v.selection_spec_id AND s.selection_mode='static_baseline'
        AND s.pending_selection_mode IS NULL AND s.pending_authorization_id IS NULL
        AND s.pending_effective_period_anchor_ms IS NULL AND s.updated_at_ms<=v.fenced_at_ms
        AND o.entry_state='enabled' AND r.strategy_group_id=o.strategy_group_id AND r.control_version=o.control_version
        AND r.operation='resume' AND r.target_state='enabled' AND r.created_at_ms=o.updated_at_ms AND r.created_at_ms<=checked_at
        AND p.target_state='paused' AND p.control_version<=latest.control_version
        AND latest.operation='pause' AND latest.target_state='paused' AND latest.created_at_ms>=p.created_at_ms AND latest.created_at_ms<=r.created_at_ms
        AND a.purpose='strategy_resume' AND a.authentication_strength='totp_step_up' AND a.authorized_at_ms=r.created_at_ms
        AND a.target_scope=jsonb_build_object('strategy_group_id',o.strategy_group_id)
        AND pa.purpose='strategy_pause' AND pa.authorized_at_ms=p.created_at_ms
        AND pa.target_scope=jsonb_build_object('strategy_group_id',o.strategy_group_id)
        AND la.purpose='strategy_pause' AND la.authorized_at_ms=latest.created_at_ms
        AND la.target_scope=jsonb_build_object('strategy_group_id',o.strategy_group_id)
        AND EXISTS (SELECT 1 FROM brc_strategy_entry_vacuum_events e WHERE e.entry_vacuum_id=vid
          AND e.event_type='OPEN' AND e.event_sequence=1 AND e.occurred_at_ms=v.fenced_at_ms AND e.payload->>'intended_outcome'='OWNER_PAUSED')
    $$""")
    c.exec_driver_sql("""CREATE FUNCTION brc_static_owner_resume_proof(vid text, checked_at bigint)
    RETURNS jsonb LANGUAGE sql STABLE AS $$
      SELECT brc_static_owner_resume_authorization(vid,checked_at)
      FROM brc_strategy_entry_vacuums_current v
      WHERE v.entry_vacuum_id=vid AND v.state IN ('OWNER_PAUSED','RESOLVED_OWNER_RESUME')
        AND v.drained_at_ms IS NOT NULL AND v.drained_at_ms<=checked_at
        AND EXISTS (SELECT 1 FROM brc_strategy_entry_vacuum_events d WHERE d.entry_vacuum_id=vid
          AND d.event_type='OWNER_PAUSED' AND d.occurred_at_ms=v.drained_at_ms AND d.payload->'entry_drain_complete'='true'::jsonb)
        AND NOT EXISTS (SELECT 1 FROM brc_strategy_universe_materialization_generations g WHERE g.strategy_group_id=v.strategy_group_id
          AND g.lifecycle_state NOT IN ('ACTIVE','FALLBACK_PREVIOUS','ABANDONED','FAILED_CLOSED','SUPERSEDED'))
        AND NOT EXISTS (SELECT 1 FROM brc_trade_tickets t LEFT JOIN brc_trade_aggregates q ON q.ticket_id=t.ticket_id
          WHERE t.strategy_group_id=v.strategy_group_id AND t.terminal_at_ms IS NULL AND (q.ticket_id IS NULL OR q.status IN (
            'leverage_pending','leverage_confirmed','leverage_outcome_unknown','entry_pending','entry_accepted','entry_outcome_unknown',
            'entry_vacuum_cancel_pending','entry_vacuum_cancel_rejected','entry_vacuum_cancel_outcome_unknown','entry_vacuum_cancelled',
            'partial_fill_incident','partial_fill_cancel_rejected','partial_fill_cancel_outcome_unknown','protection_pending',
            'initial_stop_outcome_unknown','post_fill_risk_pending','controlled_flatten_pending','controlled_flatten_accepted',
            'controlled_flatten_rejected','controlled_flatten_outcome_unknown')))
        AND NOT EXISTS (SELECT 1 FROM brc_trade_tickets t JOIN brc_exchange_commands x ON x.ticket_id=t.ticket_id
          WHERE t.strategy_group_id=v.strategy_group_id AND x.status IN ('prepared','claimed','dispatch_started','outcome_unknown'))
    $$""")
    c.exec_driver_sql("""CREATE FUNCTION brc_guard_static_owner_resume() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE proof jsonb;
    BEGIN
      IF TG_OP='UPDATE' THEN
        IF OLD.state='RESOLVED_OWNER_RESUME' THEN RAISE EXCEPTION 'resolved Owner resume is immutable'; END IF;
      END IF;
      IF NEW.state<>'RESOLVED_OWNER_RESUME' THEN RETURN NEW; END IF;
      IF TG_OP='INSERT' THEN RAISE EXCEPTION 'Owner resume requires an existing drained fence'; END IF;
      proof:=brc_static_owner_resume_proof(OLD.entry_vacuum_id,NEW.resolved_at_ms);
      IF OLD.state<>'OWNER_PAUSED' OR proof IS NULL
        OR NEW.entry_vacuum_id<>OLD.entry_vacuum_id OR NEW.strategy_group_id<>OLD.strategy_group_id
        OR NEW.selection_spec_id<>OLD.selection_spec_id OR NEW.period_anchor_ms<>OLD.period_anchor_ms
        OR NEW.source_generation_id IS DISTINCT FROM OLD.source_generation_id OR NEW.first_blocker<>OLD.first_blocker
        OR NEW.fenced_at_ms<>OLD.fenced_at_ms OR NEW.drained_at_ms IS DISTINCT FROM OLD.drained_at_ms
        OR NEW.projection_version<>OLD.projection_version+1 OR NOT EXISTS (
          SELECT 1 FROM brc_strategy_entry_vacuum_events e WHERE e.entry_vacuum_id=OLD.entry_vacuum_id
            AND e.event_sequence=NEW.projection_version AND e.event_type='RESOLVED_OWNER_RESUME'
            AND e.occurred_at_ms=NEW.resolved_at_ms AND e.payload=proof)
      THEN RAISE EXCEPTION 'static Owner resume requires exact authorization drain and event'; END IF;
      RETURN NEW;
    END; $$""")
    c.exec_driver_sql(
        "CREATE TRIGGER trg_brc_static_owner_resume BEFORE INSERT OR UPDATE ON brc_strategy_entry_vacuums_current FOR EACH ROW EXECUTE FUNCTION brc_guard_static_owner_resume()"
    )
    c.exec_driver_sql("""CREATE FUNCTION brc_check_static_owner_resume_ledger() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.event_type='RESOLVED_OWNER_RESUME' AND NOT EXISTS (
        SELECT 1 FROM brc_strategy_entry_vacuums_current v WHERE v.entry_vacuum_id=NEW.entry_vacuum_id
          AND v.state='RESOLVED_OWNER_RESUME' AND v.projection_version=NEW.event_sequence
          AND v.resolved_at_ms=NEW.occurred_at_ms)
      THEN RAISE EXCEPTION 'static Owner resume ledger must resolve the exact current fence'; END IF;
      RETURN NEW;
    END; $$""")
    c.exec_driver_sql(
        "CREATE CONSTRAINT TRIGGER trg_brc_static_owner_resume_ledger AFTER INSERT ON brc_strategy_entry_vacuum_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION brc_check_static_owner_resume_ledger()"
    )


def downgrade():
    raise RuntimeError("0023 is forward-only; preserve Owner control lineage")
