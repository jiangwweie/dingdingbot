"""Frozen notification facts and bounded reliable display-only delivery."""

import sqlalchemy as sa
from alembic import op

revision: str = "0018_notice_outbox_v1"
down_revision: str | None = "0017_app_management_observation"
branch_labels = None
depends_on = None


def upgrade():
    c = op.get_bind()
    if c.scalar(sa.text("SELECT version_num FROM alembic_version")) != down_revision:
        raise RuntimeError("0018 exact source required")
    c.execute(
        sa.text(
            "LOCK TABLE brc_trade_tickets,brc_exchange_commands,brc_positions_current,brc_owner_policy_current IN SHARE ROW EXCLUSIVE MODE"
        )
    )
    for table, where in {
        "brc_trade_tickets": "terminal_at_ms IS NULL",
        "brc_positions_current": "quantity<>0",
        "brc_exchange_commands": "status IN ('prepared','claimed','dispatch_started','outcome_unknown')",
        "brc_owner_policy_current": "new_entry_submit_enabled",
        "brc_runtime_incidents": "status='open'",
    }.items():
        if c.scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table} WHERE {where})")):
            raise RuntimeError("0018 requires stopped flat paused source")
    # Copy this revision's definition, never import the mutable head metadata.
    from sqlalchemy.dialects.postgresql import JSONB

    op.create_table(
        "brc_notice_outbox",
        sa.Column("sequence", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("notice_key", sa.String(160), nullable=False, unique=True),
        sa.Column("stream_key", sa.String(160), nullable=False),
        sa.Column(
            "ticket_id", sa.String(160), sa.ForeignKey("brc_trade_tickets.ticket_id")
        ),
        sa.Column("kind", sa.String(96), nullable=False),
        sa.Column("state_version", sa.BigInteger, nullable=False),
        sa.Column("snapshot", JSONB, nullable=False),
        sa.Column("payload", sa.Text, nullable=False),
        sa.Column("delivery_payload", sa.Text),
        sa.Column("template_version", sa.String(96), nullable=False),
        sa.Column("channel", sa.String(96), nullable=False),
        sa.Column("status", sa.String(96), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("next_attempt_at_ms", sa.BigInteger, nullable=False),
        sa.Column("lease_token", sa.String(160)),
        sa.Column("lease_until_ms", sa.BigInteger),
        sa.Column("accepted_at_ms", sa.BigInteger),
        sa.Column("last_error", sa.String(96)),
        sa.Column("created_at_ms", sa.BigInteger, nullable=False),
        sa.Column("updated_at_ms", sa.BigInteger, nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','delivering','retry','accepted','dead','superseded')",
            name="state_valid",
        ),
        sa.CheckConstraint("attempts BETWEEN 0 AND 5", name="attempts_valid"),
    )
    op.create_index(
        "ix_brc_notice_outbox_actionable",
        "brc_notice_outbox",
        ["next_attempt_at_ms", "sequence"],
        postgresql_where=sa.text("status IN ('pending','retry','delivering')"),
    )
    op.create_index(
        "ix_brc_notice_outbox_stream", "brc_notice_outbox", ["stream_key", "sequence"]
    )
    op.create_index(
        "ix_brc_notice_outbox_delivery", "brc_notice_outbox", ["status", "sequence"]
    )
    c.exec_driver_sql("""CREATE FUNCTION brc_notice_facts_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
    IF (OLD.delivery_payload IS NOT NULL AND NEW.delivery_payload IS DISTINCT FROM OLD.delivery_payload) OR NEW.notice_key IS DISTINCT FROM OLD.notice_key OR NEW.stream_key IS DISTINCT FROM OLD.stream_key OR NEW.ticket_id IS DISTINCT FROM OLD.ticket_id OR NEW.kind IS DISTINCT FROM OLD.kind OR NEW.state_version IS DISTINCT FROM OLD.state_version OR NEW.snapshot IS DISTINCT FROM OLD.snapshot OR NEW.payload IS DISTINCT FROM OLD.payload OR NEW.template_version IS DISTINCT FROM OLD.template_version OR NEW.channel IS DISTINCT FROM OLD.channel OR NEW.created_at_ms IS DISTINCT FROM OLD.created_at_ms
    THEN RAISE EXCEPTION 'notice facts immutable'; END IF; RETURN NEW; END; $$""")
    c.exec_driver_sql(
        "CREATE TRIGGER trg_notice_facts_immutable BEFORE UPDATE ON brc_notice_outbox FOR EACH ROW EXECUTE FUNCTION brc_notice_facts_immutable()"
    )
    # Existing least-privilege roles need the new display-only surface as well.
    for role, grants in {
        "brc_kernel": "GRANT SELECT,INSERT,UPDATE ON brc_notice_outbox TO brc_kernel; GRANT USAGE,SELECT ON SEQUENCE brc_notice_outbox_sequence_seq TO brc_kernel",
        "brc_owner_console": "GRANT SELECT ON brc_notice_outbox TO brc_owner_console",
    }.items():
        if c.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:role)"), {"role":role}):
            for statement in grants.split("; "):
                c.exec_driver_sql(statement)


def downgrade():
    raise RuntimeError("notice lineage is forward-only")
