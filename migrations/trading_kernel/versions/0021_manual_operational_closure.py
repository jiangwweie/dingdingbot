"""Preserved terminal review enrichment and bounded operational evidence."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0021_manual_operational_closure"
down_revision: str = "0020_manual_exit_regime_v1"
branch_labels = None
depends_on = None


def upgrade():
    c = op.get_bind()
    c.exec_driver_sql("LOCK TABLE brc_trade_tickets,brc_exchange_commands,brc_positions_current,brc_owner_policy_current IN SHARE ROW EXCLUSIVE MODE")
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
            raise RuntimeError("0021 requires stopped flat terminal-clean paused source")
    op.drop_constraint('ck_brc_owner_authorizations_purpose_valid','brc_owner_authorizations',type_='check')
    op.create_check_constraint('ck_brc_owner_authorizations_purpose_valid','brc_owner_authorizations',
        "purpose IN ('strategy_pause','strategy_resume','entry_pause','entry_resume','owner_flatten_all','universe_configure','selection_mode_change','exit_profile_bind','exit_profile_retire','review_revise')")
    for name in ("first_wait_at_ms", "last_checked_at_ms", "escalated_at_ms", "resolved_at_ms"):
        op.add_column("brc_monitor_current", sa.Column(name, sa.BigInteger, nullable=True))
    op.add_column("brc_admission_decisions", sa.Column("failure_basis", JSONB, nullable=True))
    op.create_table("brc_failure_diagnostics",
        sa.Column("diagnostic_id", sa.String(160), primary_key=True),
        sa.Column("stage", sa.String(96), nullable=False),
        sa.Column("subject_id", sa.String(512), nullable=False),
        sa.Column("reason_code", sa.String(512), nullable=False),
        sa.Column("basis", JSONB, nullable=False),
        sa.Column("occurred_at_ms", sa.BigInteger, nullable=False),
        sa.CheckConstraint("octet_length(basis::text)<=16384", name="ck_failure_basis_bounded"))
    op.create_index("ix_brc_failure_diagnostics_subject_time", "brc_failure_diagnostics", ["subject_id", "occurred_at_ms"])
    op.create_index("ix_brc_failure_diagnostics_stage_time", "brc_failure_diagnostics", ["stage", "occurred_at_ms"])
    op.create_table("brc_review_enrichment_requests",
        sa.Column("request_id", sa.String(160), primary_key=True),
        sa.Column("ticket_id", sa.String(160), sa.ForeignKey("brc_trade_tickets.ticket_id"), nullable=False),
        sa.Column("expected_review_id", sa.String(160), sa.ForeignKey("brc_trade_reviews.review_id"), nullable=False),
        sa.Column("state", sa.String(96), nullable=False),
        sa.Column("owner_authorization_id",sa.String(160),sa.ForeignKey("brc_owner_authorizations.authorization_id"),nullable=True),
        sa.Column("preview", JSONB, nullable=True),
        sa.Column("preview_digest", sa.String(71), nullable=True),
        sa.Column("last_reason", sa.String(512), nullable=True),
        sa.Column("created_at_ms", sa.BigInteger, nullable=False),
        sa.Column("next_check_at_ms", sa.BigInteger, nullable=False),
        sa.Column("completed_at_ms", sa.BigInteger, nullable=True),
        sa.UniqueConstraint("ticket_id", "expected_review_id"),
        sa.CheckConstraint("state IN ('pending','preview_ready','approved','applied','superseded')", name="ck_review_enrichment_state"),
        sa.CheckConstraint("state NOT IN ('approved','applied') OR owner_authorization_id IS NOT NULL",name="ck_review_enrichment_approved_authority"))
    c.exec_driver_sql("""CREATE FUNCTION brc_enrichment_preview_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN IF NEW.ticket_id IS DISTINCT FROM OLD.ticket_id OR NEW.expected_review_id IS DISTINCT FROM OLD.expected_review_id
        OR (OLD.preview IS NOT NULL AND (NEW.preview IS DISTINCT FROM OLD.preview OR NEW.preview_digest IS DISTINCT FROM OLD.preview_digest))
        THEN RAISE EXCEPTION 'enrichment preview immutable'; END IF; RETURN NEW; END; $$""")
    c.exec_driver_sql("CREATE TRIGGER trg_brc_enrichment_preview_immutable BEFORE UPDATE ON brc_review_enrichment_requests FOR EACH ROW EXECUTE FUNCTION brc_enrichment_preview_immutable()")
    op.create_index("ix_brc_review_enrichment_due", "brc_review_enrichment_requests", ["state", "next_check_at_ms"])
    for table in ("brc_failure_diagnostics",):
        c.exec_driver_sql(f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION brc_exit_plan_immutable()")
    for role, permissions in (("brc_kernel", "SELECT,INSERT"), ("brc_owner_console", "SELECT"), ("brc_owner_control", "SELECT")):
        if c.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:role)"), {"role": role}):
            c.exec_driver_sql(f"GRANT {permissions} ON brc_failure_diagnostics TO {role}")
            c.exec_driver_sql(f"GRANT {'SELECT,INSERT,UPDATE' if role in {'brc_kernel','brc_owner_control'} else 'SELECT'} ON brc_review_enrichment_requests TO {role}")


def downgrade():
    raise RuntimeError("manual operational closure is forward-only")
