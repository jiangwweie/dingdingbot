"""Durable management input, exact baselines and independent proof projections."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0019_management_evidence_v2"
down_revision: str = "0018_notice_outbox_v1"
branch_labels = None
depends_on = None


def upgrade():
    c = op.get_bind()
    if c.scalar(sa.text("SELECT version_num FROM alembic_version")) != down_revision:
        raise RuntimeError("0019 requires exact source")
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
        "brc_budget_reservations": "status='active'",
    }.items():
        if c.scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table} WHERE {where})")):
            raise RuntimeError(
                "0019 requires stopped flat terminal-clean paused source"
            )
    # This migration owns a frozen local DDL snapshot, never imports head models.
    metadata = sa.MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_N_name)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )
    sa.Table(
        "brc_exchange_commands",
        metadata,
        sa.Column("command_id", sa.String(160), primary_key=True),
    )

    def define_tables(metadata):
        raw = sa.Table(
            "brc_management_stream_events",
            metadata,
            sa.Column("event_id", sa.String(160), primary_key=True),
            sa.Column("scope_key", sa.String(160), nullable=False),
            sa.Column("epoch_id", sa.String(160), nullable=False),
            sa.Column("receive_sequence", sa.BigInteger, nullable=False),
            sa.Column("received_at_ms", sa.BigInteger, nullable=False),
            sa.Column("exchange_event_at_ms", sa.BigInteger),
            sa.Column("message_kind", sa.String(96), nullable=False),
            sa.Column("safe_payload", JSONB, nullable=False),
            sa.Column("payload_digest", sa.String(71), nullable=False),
            sa.UniqueConstraint("scope_key", "epoch_id", "receive_sequence"),
            sa.CheckConstraint("receive_sequence>0", name="receive_sequence_positive"),
        )
        sa.Index(
            "ix_brc_management_stream_scope_time",
            raw.c.scope_key,
            raw.c.received_at_ms,
            raw.c.receive_sequence,
        )
        sa.Index('ix_brc_management_stream_child',raw.c.scope_key,raw.c.safe_payload['o']['ai'].astext)
        baseline = sa.Table(
            "brc_order_command_baselines",
            metadata,
            sa.Column("baseline_id", sa.String(160), primary_key=True),
            sa.Column(
                "command_id",
                sa.String(160),
                sa.ForeignKey("brc_exchange_commands.command_id"),
                nullable=False,
            ),
            sa.Column("scope_key", sa.String(160), nullable=False),
            sa.Column("order_namespace", sa.String(96), nullable=False),
            sa.Column("exchange_order_id", sa.String(160), nullable=False),
            sa.Column("confirmed_terms", JSONB, nullable=False),
            sa.Column("evidence_id", sa.String(160), nullable=False),
            sa.Column("confirmed_at_ms", sa.BigInteger, nullable=False),
            sa.UniqueConstraint("scope_key", "order_namespace", "exchange_order_id"),
        )
        sa.Index("ix_brc_order_baseline_command", baseline.c.command_id)
        coverage = sa.Table(
            "brc_management_coverage_events",
            metadata,
            sa.Column("coverage_event_id", sa.String(160), primary_key=True),
            sa.Column("scope_key", sa.String(160), nullable=False),
            sa.Column("epoch_id", sa.String(160), nullable=False),
            sa.Column("kind", sa.String(96), nullable=False),
            sa.Column("from_ms", sa.BigInteger, nullable=False),
            sa.Column("to_ms", sa.BigInteger, nullable=False),
            sa.Column("receive_watermark", sa.BigInteger, nullable=False),
            sa.Column("reason", sa.String(256)),
            sa.Column("occurred_at_ms", sa.BigInteger, nullable=False),
        )
        sa.Index(
            "ix_brc_management_coverage_scope_time",
            coverage.c.scope_key,
            coverage.c.from_ms,
            coverage.c.to_ms,
        )
        feed = sa.Table(
            "brc_management_feed_current",
            metadata,
            sa.Column("scope_key", sa.String(160), primary_key=True),
            sa.Column("epoch_id", sa.String(160), nullable=False),
            sa.Column("owner_worker_id", sa.String(160), nullable=False),
            sa.Column("runtime_commit", sa.String(40), nullable=False),
            sa.Column("schema_revision", sa.String(96), nullable=False),
            sa.Column("lease_until_ms", sa.BigInteger, nullable=False),
            sa.Column("connection_state", sa.String(96), nullable=False),
            sa.Column("persisted_watermark", sa.BigInteger, nullable=False),
            sa.Column("applied_watermark", sa.BigInteger, nullable=False),
            sa.Column("connected_at_ms", sa.BigInteger),
            sa.Column("last_successful_at_ms", sa.BigInteger),
            sa.Column("health_reason", sa.String(256)),
            sa.Column("revision", sa.BigInteger, nullable=False),
        )
        return raw, baseline, coverage, feed

    tables = define_tables(metadata)
    c.exec_driver_sql(
        "CREATE FUNCTION brc_management_facts_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'management facts immutable'; END; $$"
    )
    for table in tables:
        table.create(c)
    for table in tables:
        if table.name != "brc_management_feed_current":
            c.exec_driver_sql(
                f"CREATE TRIGGER trg_{table.name}_immutable BEFORE UPDATE OR DELETE ON {table.name} FOR EACH ROW EXECUTE FUNCTION brc_management_facts_immutable()"
            )
    c.exec_driver_sql("CREATE INDEX ix_brc_management_evidence_child ON brc_management_order_evidence (ticket_id,(payload->>'child_exchange_order_id'))")
    op.add_column(
        "brc_management_observation_current",
        sa.Column(
            "current_complete", sa.Boolean, nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "brc_management_observation_current",
        sa.Column(
            "attribution_complete",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "brc_management_observation_current",
        sa.Column(
            "proof_refs", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    )
    op.add_column('brc_management_observation_current',sa.Column('continuity_complete',sa.Boolean,nullable=False,server_default=sa.false()))
    c.exec_driver_sql("UPDATE brc_management_observation_current SET proof_refs=jsonb_build_object('migration',jsonb_build_object('source_revision','0018_notice_outbox_v1','legacy_facts_complete',facts_complete,'status','historical_terminal'))")
    op.drop_column('brc_management_observation_current','facts_complete')
    for role, grants in [
        ("brc_kernel", "SELECT,INSERT,UPDATE"),
        ("brc_owner_console", "SELECT"),
    ]:
        if c.scalar(
            sa.text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:role)"),
            {"role": role},
        ):
            for table in tables:
                c.exec_driver_sql(f"GRANT {grants} ON {table.name} TO {role}")


def downgrade():
    raise RuntimeError("management evidence is forward-only")
