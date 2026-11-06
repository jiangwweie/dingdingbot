"""App product management authority; stopped flat forward-only source."""
import sqlalchemy as sa
from alembic import op

revision: str = '0016_app_manual_takeover_v1'
down_revision: str | None = '0015_generic_owner_recovery_v1'
branch_labels=None
depends_on=None


def upgrade():
    c=op.get_bind()
    if c.scalar(sa.text('SELECT version_num FROM alembic_version'))!=down_revision:
        raise RuntimeError('0016 requires exact 0015 source')
    gates={
        'brc_trade_tickets':'terminal_at_ms IS NULL OR active_netting_domain_key IS NOT NULL',
        'brc_positions_current':'quantity<>0',
        'brc_budget_reservations':"status='active'",
        'brc_exchange_commands':"status IN ('prepared','claimed','dispatch_started','outcome_unknown')",
        'brc_runtime_incidents':"status='open'",
        'brc_entry_lane_current':"status<>'idle' OR ticket_id IS NOT NULL",
        'brc_entry_send_authorizations':'completed_at_ms IS NULL',
        'brc_owner_control_operations_current':"state NOT IN ('completed','blocked')",
        'brc_strategy_universe_versions':"lifecycle_state IN ('warming','staged')",
        'brc_strategy_universe_materialization_generations':"lifecycle_state IN ('PENDING','DESIRED','DRAINING_ENTRY','MATERIALIZING','STAGED')",
        'brc_directional_risk_controls':'pending_view IS NOT NULL OR pending_baseline IS NOT NULL',
        'brc_owner_policy_current':'new_entry_submit_enabled',
    }
    c.execute(sa.text('LOCK TABLE '+','.join(gates)+' IN SHARE ROW EXCLUSIVE MODE'))
    for table,predicate in gates.items():
        if c.scalar(sa.text(f'SELECT EXISTS(SELECT 1 FROM {table} WHERE {predicate})')):
            raise RuntimeError(f'0016 requires stopped flat paused source: {table}')
    from src.trading_kernel.infrastructure.generic_selection_source_provenance import (
        count_nonquiescent_source_vacuums,
    )
    if count_nonquiescent_source_vacuums(c,allow_paused_failed_generic=True):
        raise RuntimeError('0016 requires quiescent source vacuums')
    op.add_column('brc_trade_aggregates',sa.Column('management_mode',sa.String(96),nullable=False,server_default='AUTO'))
    op.add_column('brc_trade_aggregates',sa.Column('management_revision',sa.BigInteger(),nullable=False,server_default='1'))
    op.add_column('brc_trade_aggregates',sa.Column('management_evidence_id',sa.String(160)))
    op.add_column('brc_trade_aggregates',sa.Column('management_reason',sa.String(512)))
    op.add_column('brc_trade_aggregates',sa.Column('manual_takeover_at_ms',sa.BigInteger()))
    op.create_check_constraint('management_shape','brc_trade_aggregates',"""COALESCE(
       management_revision>0 AND (
         (management_mode='AUTO' AND management_evidence_id IS NULL AND management_reason IS NULL AND manual_takeover_at_ms IS NULL)
         OR (management_mode='REVIEW_REQUIRED' AND length(management_evidence_id)>0 AND length(management_reason)>0 AND manual_takeover_at_ms IS NULL)
         OR (management_mode='MANUAL' AND length(management_evidence_id)>0 AND length(management_reason)>0 AND manual_takeover_at_ms>0)
       ),false)""")
    c.exec_driver_sql("""
    CREATE FUNCTION brc_guard_trade_management() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.management_mode='MANUAL' AND (
        NEW.management_mode<>OLD.management_mode OR NEW.management_revision<>OLD.management_revision
        OR NEW.management_evidence_id IS DISTINCT FROM OLD.management_evidence_id
        OR NEW.management_reason IS DISTINCT FROM OLD.management_reason
        OR NEW.manual_takeover_at_ms IS DISTINCT FROM OLD.manual_takeover_at_ms)
      THEN RAISE EXCEPTION 'manual management is permanent'; END IF;
      IF ROW(NEW.management_mode,NEW.management_revision,NEW.management_evidence_id,NEW.management_reason,NEW.manual_takeover_at_ms)
        IS DISTINCT FROM ROW(OLD.management_mode,OLD.management_revision,OLD.management_evidence_id,OLD.management_reason,OLD.manual_takeover_at_ms)
        AND NEW.management_revision<>OLD.management_revision+1
      THEN RAISE EXCEPTION 'management revision must advance exactly once'; END IF;
      RETURN NEW;
    END; $$
    """)
    c.exec_driver_sql('CREATE TRIGGER trg_trade_management BEFORE UPDATE ON brc_trade_aggregates FOR EACH ROW EXECUTE FUNCTION brc_guard_trade_management()')
    c.exec_driver_sql("""
    CREATE FUNCTION brc_validate_management_event() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.management_revision=OLD.management_revision THEN RETURN NULL; END IF;
      IF NEW.management_mode NOT IN ('MANUAL','REVIEW_REQUIRED') OR NOT EXISTS (
        SELECT 1 FROM brc_trade_events e WHERE e.ticket_id=NEW.ticket_id AND e.sequence=NEW.last_event_sequence
        AND e.event_type=CASE WHEN NEW.management_mode='MANUAL' THEN 'ManualTakeoverConfirmed' ELSE 'ManagementReviewRequired' END
        AND e.payload->>'evidence_id'=NEW.management_evidence_id AND e.payload->>'reason'=NEW.management_reason
        AND (NEW.management_mode<>'MANUAL' OR e.occurred_at_ms=NEW.manual_takeover_at_ms)
      ) THEN RAISE EXCEPTION 'management requires atomic evidence event'; END IF;
      RETURN NULL;
    END; $$
    """)
    c.exec_driver_sql('CREATE CONSTRAINT TRIGGER trg_management_event AFTER UPDATE ON brc_trade_aggregates DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION brc_validate_management_event()')


def downgrade():
    raise RuntimeError('manual ownership requires fix-forward; downgrade forbidden')
